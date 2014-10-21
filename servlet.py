#!/usr/bin/env python3
# -*- indent-tabs-mode: nil -*-
# coding=utf-8
# -*- encoding: utf-8 -*-

import sys, threading, os, re, ssl, argparse, logging, time, signal, tempfile, zipfile
from lxml import etree
from subprocess import Popen, PIPE
from multiprocessing import Pool, TimeoutError
from functools import wraps
from threading import Thread
from datetime import datetime

import tornado, tornado.web, tornado.httpserver
from tornado import escape, gen
from tornado.escape import utf8
try: #3.1
    from tornado.log import enable_pretty_logging
except ImportError: #2.1
    from tornado.options import enable_pretty_logging

from modeSearch import searchPath
from util import getLocalizedLanguages, apertium, bilingualTranslate, removeLast, stripTags, processPerWord, getCoverage, getCoverages, toAlpha3Code, toAlpha2Code, noteUnknownToken, scaleMtLog, TranslationInfo, closeDb, flushUnknownWords, inMemoryUnknownToken
from translation import translate, translateDoc, parseModeFile
from keys import getKey

try:
    import cld2full as cld2
except:
    cld2 = None

def run_async(func):
    @wraps(func)
    def async_func(*args, **kwargs):
        func_hl = Thread(target = func, args = args, kwargs = kwargs)
        func_hl.start()
        return func_hl

    return async_func

def sig_handler(sig, frame):
    global missingFreqsDb
    if missingFreqsDb:
        if 'children' in frame.f_locals:
            for child in frame.f_locals['children']:
                os.kill(child, signal.SIGTERM)
            flushUnknownWords(missingFreqsDb)
        else: # we are one of the children
            flushUnknownWords(missingFreqsDb)
        closeDb()
    logging.warning('Caught signal: %s', sig)
    exit()

class BaseHandler(tornado.web.RequestHandler):
    pairs = {}
    analyzers = {}
    generators = {}
    taggers = {}
    pipelines = {} # (l1, l2): (inpipe, outpipe, do_flush)
    callback = None
    timeout = None
    scaleMtLogs = False
    inMemoryUnknown = False
    inMemoryLimit = -1

    stats = {
        'useCount': {},
        'lastUsage': {},
    }

    # The lock is needed so we don't let two threads write
    # simultaneously to a pipeline; then the first thread to read
    # might read translations of text put there by the second
    # thread …
    pipeline_locks = {} # (l1, l2): threading.RLock() for (l1, l2) in pairs

    def initialize(self):
        self.callback = self.get_argument('callback', default=None)

    def sendResponse(self, data):
        if isinstance(data, dict) or isinstance(data, list):
            data = escape.json_encode(data)
            self.set_header('Content-Type', 'application/json; charset=UTF-8')

        if self.callback:
            self.set_header('Content-Type', 'application/javascript; charset=UTF-8')
            self._write_buffer.append(utf8('%s(%s)' % (self.callback, data)))
        else:
            self._write_buffer.append(utf8(data))
        self.finish()

    def write_error(self, status_code, **kwargs):
        # TODO: Is there a tornado fn to get the full list?
        http_messages = {
            400: 'Bad Request',
            404: 'Not Found',
            408: 'Request Timeout',
            500: 'Internal Error'
        }

        result = {
            'status': 'error',
            'code': status_code,
            'message': http_messages.get(status_code, ''),
            'explanation': kwargs.get('explanation', '')
        }

        data = escape.json_encode(result)
        self.set_header('Content-Type', 'application/json; charset=UTF-8')

        if self.callback:
            self.set_header('Content-Type', 'application/javascript; charset=UTF-8')
            self._write_buffer.append(utf8('%s(%s)' % (self.callback, data)))
        else:
            self._write_buffer.append(utf8(data))
        self.finish()

    def set_default_headers(self):
        self.set_header('Access-Control-Allow-Origin', '*')
        self.set_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.set_header('Access-Control-Allow-Headers', 'accept, cache-control, origin, x-requested-with, x-file-name, content-type')

    @tornado.web.asynchronous
    def post(self):
        self.get()

    def options(self):
        self.set_status(204)
        self.finish()

class ListHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        query = self.get_argument('q', default='pairs')

        if query == 'pairs':
            responseData = []
            for pair in self.pairs:
                (l1, l2) = pair.split('-')
                responseData.append({'sourceLanguage': l1, 'targetLanguage': l2})
                if self.get_arguments('include_deprecated_codes'):
                    responseData.append({'sourceLanguage': toAlpha2Code(l1), 'targetLanguage': toAlpha2Code(l2)})
            self.sendResponse({'responseData': responseData, 'responseDetails': None, 'responseStatus': 200})
        elif query == 'analyzers' or query == 'analysers':
            self.sendResponse({pair: modename for (pair, (path, modename)) in self.analyzers.items()})
        elif query == 'generators':
            self.sendResponse({pair: modename for (pair, (path, modename)) in self.generators.items()})
        elif query == 'taggers' or query == 'disambiguators':
            self.sendResponse({pair: modename for (pair, (path, modename)) in self.taggers.items()})
        else:
            self.send_error(400, explanation='Expecting q argument to be one of analysers, generators, disambiguators or pairs')

class StatsHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        self.sendResponse({
            'responseData': { '%s-%s' % pair: useCount for pair, useCount in self.stats['useCount'].items() },
            'responseDetails': None,
            'responseStatus': 200
        })

class ThreadableMixin:
    '''To use:

    1) inherit this class
    2) define a self._worker that sets self.res to whatever the result value should be.
    3) define a self._handler that checks for hasattr(self, 'res')
    4) start the worker with self.start_worker(self._handler, arg1, arg2, …, argn)
       where arg1…argn are passed on to self._worker

    '''
    def start_worker(self, *args):
        # TODO: max threads, using https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.ThreadPoolExecutor
        threading.Thread(target=self.run_worker, args=args).start()

    def run_worker(self, result_handler, *worker_args):
        try:
            self._worker(*worker_args)
        except tornado.web.HTTPError:
            self.set_status(408) # TODO e.status_code
        except:
            logging.error('_worker problem ', exc_info=True)
            self.set_status(500)
        tornado.ioloop.IOLoop.instance().add_callback(result_handler)

class TranslateHandler(BaseHandler, ThreadableMixin):
    def notePairUsage(self, pair):
        self.stats['useCount'][pair] = 1 + self.stats['useCount'].get(pair, 0)
        if self.max_idle_secs:
            self.stats['lastUsage'][pair] = time.time()

    unknownMarkRE = re.compile(r'\*([^.,;:\t\* ]+)')
    def stripUnknownMarks(self, text):
        return re.sub(self.unknownMarkRE, r'\1', text)

    def noteUnknownTokens(self, pair, text):
        if self.missingFreqs:
            for token in re.findall(self.unknownMarkRE, text):
                if self.inMemoryUnknown:
                    inMemoryUnknownToken(token, pair, self.missingFreqs, self.inMemoryLimit)
                else:
                    noteUnknownToken(token, pair, self.missingFreqs)

    def shutdownPair(self, pair):
        if self.pipelines[pair][0].poll():
            # Killing the first one should bring down the rest:
            self.pipelines[pair][0].kill()
        self.pipelines.pop(pair)
        self.pipeline_locks.pop(pair)

    def cleanPairs(self):
        if not self.max_idle_secs:
            return
        for pair, lastUsage in self.stats['lastUsage'].items():
            if time.time() - lastUsage > self.max_idle_secs and pair in self.pipelines:
                logging.info('Shutting down pair %s-%s since it has not been used in %d seconds' % (pair[0], pair[1], self.max_idle_secs))
                self.shutdownPair(pair)

    def runPipeline(self, l1, l2):
        if (l1, l2) not in self.pipelines:
            logging.info('%s-%s not in pipelines of this process, starting …' % (l1, l2))
            mode_path = self.pairs['%s-%s' % (l1, l2)]
            try:
                do_flush, commands = parseModeFile(mode_path)
            except Exception:
                self.send_error(500)
                return

            procs = []
            for cmd in commands:
                if len(procs)>0:
                    newP = Popen(cmd, stdin=procs[-1].stdout, stdout=PIPE)
                else:
                    newP = Popen(cmd, stdin=PIPE, stdout=PIPE)
                procs.append(newP)

            self.pipeline_locks[(l1, l2)] = threading.RLock()
            self.pipelines[(l1, l2)] = (procs[0], procs[-1], do_flush)

    def logBeforeTranslation(self):
        if self.scaleMtLogs:
            return datetime.now()
        return

    def logAfterTranslation(self, before, toTranslate):
        if self.scaleMtLogs:
            after = datetime.now()
            tInfo = TranslationInfo(self)
            key = getKey(tInfo.key)
            scaleMtLog(self.get_status(), after-before, tInfo, key, len(toTranslate))

    def _worker (self, toTranslate, l1, l2):
        before = self.logBeforeTranslation()

        self.runPipeline(l1, l2)
        self.res = translate(toTranslate, self.pipeline_locks[(l1, l2)], self.pipelines[(l1, l2)])
        self.logAfterTranslation(before, toTranslate)

        _, _, do_flush = self.pipelines[(l1, l2)]
        if not do_flush:
            self.shutdownPair((l1, l2))

    @tornado.web.asynchronous
    def get(self):
        toTranslate = self.get_argument('q')
        markUnknown = self.get_argument('markUnknown', default='yes') in ['yes', 'true', '1']

        try:
            l1, l2 = map(toAlpha3Code, self.get_argument('langpair').split('|'))
        except ValueError:
            self.send_error(400, explanation='That pair is invalid, use e.g. eng|spa')

            if self.scaleMtLogs:
                before = datetime.now()
                tInfo = TranslationInfo(self)
                key = getKey(tInfo.key)
                after = datetime.now()
                scaleMtLog(400, after-before, tInfo, key, len(toTranslate))

            return

        def handleTranslation():
            if self.get_status() != 200:
                self.send_error(self.get_status())
                return
            if hasattr(self, 'res'):
                self.noteUnknownTokens('-'.join((l1, l2)), self.res)
                self.res = self.res if markUnknown else self.stripUnknownMarks(self.res)
                self.sendResponse({
                    'responseData': {'translatedText': self.res},
                   'responseDetails': None,
                   'responseStatus': 200
                })
                return
            if hasattr(self, 'redir'):
                self.redirect(self.redir)
                return
            logging.error('handleTranslation reached a thought-to-be-unreachable line')
            self.send_error(500)

        if '%s-%s' % (l1, l2) in self.pairs:
            self.start_worker(handleTranslation, toTranslate, l1, l2)
            self.notePairUsage((l1, l2))
            self.cleanPairs()
        else:
            self.send_error(400, explanation='That pair is not installed')
            if self.scaleMtLogs:
                before = datetime.now()
                tInfo = TranslationInfo(self)
                key = getKey(tInfo.key)
                after = datetime.now()
                scaleMtLog(400, after-before, tInfo, key, len(toTranslate))

class TranslateDocHandler(TranslateHandler):
    mimeTypeCommand = None

    def getMimeType(self, f):
        commands = {
            'mimetype': lambda x: Popen(['mimetype', '-b', x], stdout=PIPE).communicate()[0].strip(),
            'xdg-mime': lambda x: Popen(['xdg-mime', 'query', 'filetype', x], stdout=PIPE).communicate()[0].strip(),
            'file': lambda x: Popen(['file', '--mime-type', '-b', x], stdout=PIPE).communicate()[0].strip()
        }

        typeFiles = {
            'word/document.xml': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'ppt/presentation.xml': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'xl/workbook.xml': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        }

        if not self.mimeTypeCommand:
            for command in ['mimetype', 'xdg-mime', 'file']:
                if Popen(['which', command], stdout=PIPE).communicate()[0]:
                    TranslateDocHandler.mimeTypeCommand = command
                    break

        mimeType = commands[self.mimeTypeCommand](f).decode('utf-8')
        if mimeType == 'application/zip':
            with zipfile.ZipFile(f) as zf:
                for typeFile in typeFiles:
                    if typeFile in zf.namelist():
                        return typeFiles[typeFile]

                if 'mimetype' in zf.namelist():
                    return zf.read('mimetype').decode('utf-8')

                return mimeType

        else:
            return mimeType

    @tornado.web.asynchronous
    def get(self):
        try:
            l1, l2 = map(toAlpha3Code, self.get_argument('langpair').split('|'))
        except ValueError:
            self.send_error(400, explanation='That pair is invalid, use e.g. eng|spa')

        allowedMimeTypes = {
            'text/plain': 'txt',
            'text/html': 'html-noent',
            'text/rtf': 'rtf',
            'application/rtf': 'rtf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
            # 'application/msword', 'application/vnd.ms-powerpoint', 'application/vnd.ms-excel'
            'application/vnd.oasis.opendocument.text': 'odt',
            'application/x-latex': 'latex',
            'application/x-tex': 'latex'
        }

        if '%s-%s' % (l1, l2) in self.pairs:
            body = self.request.files['file'][0]['body']
            if len(body) > 32E6:
                self.send_error(413, explanation='That file is too large')
            else:
                with tempfile.NamedTemporaryFile() as tempFile:
                    tempFile.write(body)
                    tempFile.seek(0)

                    mtype = self.getMimeType(tempFile.name)
                    if mtype in allowedMimeTypes:
                        self.request.headers['Content-Type'] = 'application/octet-stream'
                        self.request.headers['Content-Disposition'] = 'attachment'

                        self.write(translateDoc(tempFile, allowedMimeTypes[mtype], self.pairs['%s-%s' % (l1, l2)]))
                        self.finish()
                    else:
                        self.send_error(400, explanation='Invalid file type %s' % mtype)
        else:
            self.send_error(400, explanation='That pair is not installed')

class AnalyzeHandler(BaseHandler):
    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self):
        mode = toAlpha3Code(self.get_argument('lang'))
        toAnalyze = self.get_argument('q')

        def handleAnalysis(analysis):
            if analysis is None:
                self.send_error(408, explanation='Request timed out')
            else:
                lexicalUnits = removeLast(toAnalyze, re.findall(r'\^([^\$]*)\$([^\^]*)', analysis))
                self.sendResponse([(lexicalUnit[0], lexicalUnit[0].split('/')[0] + lexicalUnit[1]) for lexicalUnit in lexicalUnits])

        if mode in self.analyzers:
            pool = Pool(processes=1)
            result = pool.apply_async(apertium, [toAnalyze, self.analyzers[mode][0], self.analyzers[mode][1]])
            pool.close()

            @run_async
            def worker(callback):
                try:
                    callback(result.get(timeout=self.timeout))
                except TimeoutError:
                    pool.terminate()
                    callback(None)

            analysis = yield tornado.gen.Task(worker)
            handleAnalysis(analysis)
        else:
            self.send_error(400, explanation='That mode is not installed')

class GenerateHandler(BaseHandler):
    @tornado.web.asynchronous
    @gen.coroutine
    def get(self):
        mode = toAlpha3Code(self.get_argument('lang'))
        toGenerate = self.get_argument('q')

        def handleGeneration(generated):
            if generated is None:
                self.send_error(408, explanation='Request timed out')
            else:
                generated = removeLast(toGenerate, generated)
                self.sendResponse([(generation, lexicalUnits[index]) for (index, generation) in enumerate(generated.split('[SEP]'))])

        if mode in self.generators:
            lexicalUnits = re.findall(r'(\^[^\$]*\$[^\^]*)', toGenerate)
            if len(lexicalUnits) == 0:
                lexicalUnits = ['^%s$' % toGenerate]
            pool = Pool(processes=1)
            result = pool.apply_async(apertium, ('[SEP]'.join(lexicalUnits), self.generators[mode][0], self.generators[mode][1]), {'formatting': 'none'})
            pool.close()

            @run_async
            def worker(callback):
                try:
                    callback(result.get(timeout=self.timeout))
                except TimeoutError:
                    pool.terminate()
                    callback(None)

            generated = yield tornado.gen.Task(worker)
            handleGeneration(generated)
        else:
            self.send_error(400, explanation='That mode is not installed')

class ListLanguageNamesHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        localeArg = self.get_argument('locale')
        languagesArg = self.get_argument('languages', default=None)

        if self.langNames:
            if localeArg:
                if languagesArg:
                    self.sendResponse(getLocalizedLanguages(localeArg, self.langNames, languages=languagesArg.split(' ')))
                else:
                    self.sendResponse(getLocalizedLanguages(localeArg, self.langNames))
            elif 'Accept-Language' in self.request.headers:
                locales = [locale.split(';')[0] for locale in self.request.headers['Accept-Language'].split(',')]
                for locale in locales:
                    languageNames = getLocalizedLanguages(locale, self.langNames)
                    if languageNames:
                        self.sendResponse(languageNames)
                        return
                self.sendResponse(getLocalizedLanguages('en', self.langNames))
            else:
                self.sendResponse(getLocalizedLanguages('en', self.langNames))
        else:
            self.sendResponse({})

class PerWordHandler(BaseHandler):
    @tornado.web.asynchronous
    @gen.coroutine
    def get(self):
        lang = toAlpha3Code(self.get_argument('lang'))
        modes = set(self.get_argument('modes').split(' '))
        query = self.get_argument('q')

        if not modes <= {'morph', 'biltrans', 'tagger', 'disambig', 'translate'}:
            self.send_error(400, explanation='Invalid mode argument')
            return

        def handleOutput(output):
            '''toReturn = {}
            for mode in modes:
                toReturn[mode] = outputs[mode]
            for mode in modes:
                toReturn[mode] = {outputs[mode + '_inputs'][index]: output for (index, output) in enumerate(outputs[mode])}
            for mode in modes:
                toReturn[mode] = [(outputs[mode + '_inputs'][index], output) for (index, output) in enumerate(outputs[mode])]
            for mode in modes:
                toReturn[mode] = {'outputs': outputs[mode], 'inputs': outputs[mode + '_inputs']}
            self.sendResponse(toReturn)'''

            if output is None:
                self.send_error(400, explanation='No output')
                return
            elif not output:
                self.send_error(408, explanation='Request timed out')
                return
            else:
                outputs, tagger_lexicalUnits, morph_lexicalUnits = output

            toReturn = []

            for (index, lexicalUnit) in enumerate(tagger_lexicalUnits if tagger_lexicalUnits else morph_lexicalUnits):
                unitToReturn = {}
                unitToReturn['input'] = stripTags(lexicalUnit.split('/')[0])
                for mode in modes:
                    unitToReturn[mode] = outputs[mode][index]
                toReturn.append(unitToReturn)

            if self.get_argument('pos', default=None):
                requestedPos = int(self.get_argument('pos')) - 1
                currentPos = 0
                for unit in toReturn:
                    input = unit['input']
                    currentPos += len(input.split(' '))
                    if requestedPos < currentPos:
                        self.sendResponse(unit)
                        return
            else:
                self.sendResponse(toReturn)

        pool = Pool(processes=1)
        result = pool.apply_async(processPerWord, (self.analyzers, self.taggers, lang, modes, query))
        pool.close()

        @run_async
        def worker(callback):
            try:
                callback(result.get(timeout=self.timeout))
            except TimeoutError:
                pool.terminate()
                callback(None)

        output = yield tornado.gen.Task(worker)
        handleOutput(output)

class CoverageHandler(BaseHandler):
    @tornado.web.asynchronous
    @gen.coroutine
    def get(self):
        mode = toAlpha3Code(self.get_argument('lang'))
        text = self.get_argument('q')
        if not text:
            self.send_error(400, explanation='Missing q argument')
            return

        def handleCoverage(coverage):
            if coverage is None:
                self.send_error(408, explanation='Request timed out')
            else:
                self.sendResponse([coverage])

        if mode in self.analyzers:
            pool = Pool(processes=1)
            result = pool.apply_async(getCoverage, [text, self.analyzers[mode][0], self.analyzers[mode][1]])
            pool.close()

            @run_async
            def worker(callback):
                try:
                    callback(result.get(timeout=self.timeout))
                except TimeoutError:
                    pool.terminate()
                    callback(None)

            coverage = yield tornado.gen.Task(worker)
            handleCoverage(coverage)
        else:
            self.send_error(400, explanation='That mode is not installed')

class IdentifyLangHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        text = self.get_argument('q')
        if not text:
            return self.send_error(400, explanation='Missing q argument')

        if cld2:
            cldResults = cld2.detect(text)
            if cldResults[0]:
                possibleLangs = filter(lambda x: x[1] != 'un', cldResults[2])
                self.sendResponse({toAlpha3Code(possibleLang[1]): possibleLang[2] for possibleLang in possibleLangs})
            else:
                self.sendResponse({'nob': 100}) # TODO: Some more reasonable response
        else:
            def handleCoverages(coverages):
                self.sendResponse(coverages)

            pool = Pool(processes=1)
            result = pool.apply_async(getCoverages, [text, self.analyzers], {'penalize': True}, callback=handleCoverages)
            pool.close()
            try:
                coverages = result.get(timeout=self.timeout)
            except TimeoutError:
                self.send_error(408, explanation='Request timed out')
                pool.terminate()

class GetLocaleHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        if 'Accept-Language' in self.request.headers:
            locales = [locale.split(';')[0] for locale in self.request.headers['Accept-Language'].split(',')]
            self.sendResponse(locales)
        else:
            self.send_error(400, explanation='Accept-Language missing from request headers')

missingFreqsDb = ''

def setupHandler(port, pairs_path, nonpairs_path, langNames, missingFreqs, timeout, max_idle_secs, verbosity=0, scaleMtLogs=False, memory=0):

    global missingFreqsDb
    missingFreqsDb= missingFreqs

    Handler = BaseHandler
    Handler.langNames = langNames
    Handler.missingFreqs = missingFreqs
    Handler.timeout = timeout
    Handler.max_idle_secs = max_idle_secs
    Handler.scaleMtLogs = scaleMtLogs
    Handler.inMemoryUnknown = True if memory > 0 else False
    Handler.inMemoryLimit = memory

    modes = searchPath(pairs_path, verbosity=verbosity)
    if nonpairs_path:
        src_modes = searchPath(nonpairs_path, include_pairs=False, verbosity=verbosity)
        for mtype in modes:
            modes[mtype] += src_modes[mtype]

    [logging.info('%d %s modes found' % (len(modes[mtype]), mtype)) for mtype in modes]

    for path, lang_src, lang_trg in modes['pair']:
        Handler.pairs['%s-%s' % (lang_src, lang_trg)] = path
    for dirpath, modename, lang_pair in modes['analyzer']:
        Handler.analyzers[lang_pair] = (dirpath, modename)
    for dirpath, modename, lang_pair in modes['generator']:
        Handler.generators[lang_pair] = (dirpath, modename)
    for dirpath, modename, lang_pair in modes['tagger']:
        Handler.taggers[lang_pair] = (dirpath, modename)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Start Apertium APY')
    parser.add_argument('pairs_path', help='path to Apertium installed pairs (all modes files in this path are included)')
    parser.add_argument('-s', '--nonpairs-path', help='path to Apertium SVN (only non-translator debug modes are included from this path)')
    parser.add_argument('-l', '--lang-names', help='path to localised language names sqlite database (default = langNames.db)', default='langNames.db')
    parser.add_argument('-f', '--missing-freqs', help='path to missing frequency sqlite database (default = None)', default=None)
    parser.add_argument('-p', '--port', help='port to run server on (default = 2737)', type=int, default=2737)
    parser.add_argument('-c', '--ssl-cert', help='path to SSL Certificate', default=None)
    parser.add_argument('-k', '--ssl-key', help='path to SSL Key File', default=None)
    parser.add_argument('-t', '--timeout', help='timeout for requests (default = 10)', type=int, default=10)
    parser.add_argument('-j', '--num-processes', help='number of processes to run (default = number of cores)', type=int, default=0)
    parser.add_argument('-d', '--daemon', help='daemon mode: redirects stdout and stderr to files apertium-apy.log and apertium-apy.err ; use with --log-path', action='store_true')
    parser.add_argument('-P', '--log-path', help='path to log output files to in daemon mode; defaults to local directory', default='./')
    parser.add_argument('-m', '--max-idle-secs', help='shut down pipelines it have not been used in this many seconds', type=int, default=0)
    parser.add_argument('-v', '--verbosity', help='logging verbosity', type=int, default=0)
    parser.add_argument('-S', '--scalemt-logs', help='generates ScaleMT-like logs; use with --log-path; disables', action='store_true')
    parser.add_argument('-M', '--unknown-memory-limit', help="keeps unknown words in memory until a limit is reached", type=int, default=0)
    args = parser.parse_args()

    if args.daemon:
        # regular content logs are output stderr
        # python messages are mostly output to stdout
        # hence swapping the filenames?
        sys.stderr = open(os.path.join(args.log_path, 'apertium-apy.log'), 'a+')
        sys.stdout = open(os.path.join(args.log_path, 'apertium-apy.err'), 'a+')

    logging.getLogger().setLevel(logging.INFO)
    enable_pretty_logging()

    if args.scalemt_logs:
        logger = logging.getLogger('scale-mt')
        logger.propagate = False
        smtlog = os.path.join(args.log_path, 'ScaleMTRequests.log')
        loggingHandler = logging.handlers.TimedRotatingFileHandler(smtlog,'midnight',0)
        loggingHandler.suffix = "%Y-%m-%d"
        logger.addHandler(loggingHandler)

        # if scalemt_logs is enabled, disable tornado.access logs
        if(args.daemon):
            logging.getLogger("tornado.access").propagate = False

    if not cld2:
        logging.warning('Unable to import CLD2, continuing using naive method of language detection')

    setupHandler(args.port, args.pairs_path, args.nonpairs_path, args.lang_names, args.missing_freqs, args.timeout, args.max_idle_secs, args.verbosity, args.scalemt_logs, args.unknown_memory_limit)

    application = tornado.web.Application([
        (r'/list', ListHandler),
        (r'/listPairs', ListHandler),
        (r'/stats', StatsHandler),
        (r'/translate', TranslateHandler),
        (r'/translateDoc', TranslateDocHandler),
        (r'/analy[sz]e', AnalyzeHandler),
        (r'/generate', GenerateHandler),
        (r'/listLanguageNames', ListLanguageNamesHandler),
        (r'/perWord', PerWordHandler),
        (r'/calcCoverage', CoverageHandler),
        (r'/identifyLang', IdentifyLangHandler),
        (r'/getLocale', GetLocaleHandler)
    ])

    global http_server
    if args.ssl_cert and args.ssl_key:
        http_server = tornado.httpserver.HTTPServer(application, ssl_options = {
            'certfile': args.ssl_cert,
            'keyfile': args.ssl_key,
        })
        logging.info('Serving at https://localhost:%s' % args.port)
    else:
        http_server = tornado.httpserver.HTTPServer(application)
        logging.info('Serving at http://localhost:%s' % args.port)

    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)

    http_server.bind(args.port)
    http_server.start(args.num_processes)
    tornado.ioloop.IOLoop.instance().start()
