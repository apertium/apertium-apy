#!/usr/bin/env python3
# -*- indent-tabs-mode: nil -*-
# coding=utf-8
# -*- encoding: utf-8 -*-

import sys, os, re, argparse, logging, time, signal, tempfile, zipfile
from subprocess import Popen, PIPE
from multiprocessing import Pool, TimeoutError
from functools import wraps
from threading import Thread
from datetime import datetime
import heapq

import tornado, tornado.web, tornado.httpserver, tornado.process, tornado.iostream
from tornado import escape, gen
from tornado.escape import utf8
try: # 3.1
    from tornado.log import enable_pretty_logging
except ImportError: # 2.1
    from tornado.options import enable_pretty_logging

from modeSearch import searchPath
from util import getLocalizedLanguages, stripTags, processPerWord, getCoverage, getCoverages, toAlpha3Code, toAlpha2Code, noteUnknownToken, scaleMtLog, TranslationInfo, closeDb, flushUnknownWords, inMemoryUnknownToken

if sys.version_info.minor < 3:
    import translation_py32 as translation
else:
    import translation

import util
from keys import getKey

try:
    import cld2full as cld2
except:
    cld2 = None


def run_async_thread(func):
    @wraps(func)
    def async_func(*args, **kwargs):
        func_hl = Thread(target=func, args=args, kwargs=kwargs)
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
        else:  # we are one of the children
            flushUnknownWords(missingFreqsDb)
    logging.warning('Caught signal: %s', sig)
    closeDb()
    exit()


class BaseHandler(tornado.web.RequestHandler):
    pairs = {}
    analyzers = {}
    generators = {}
    taggers = {}
    pipelines = {} # (l1, l2): [translation.Pipeline], only contains flushing pairs!
    pipelines_holding = []
    callback = None
    timeout = None
    scaleMtLogs = False
    inMemoryUnknown = False
    inMemoryLimit = -1
    verbosity = 0

    stats = {
        'useCount': {},
        'vmsize': 0,
    }

    pipeline_cmds = {} # (l1, l2): translation.ParsedModes
    max_pipes_per_pair = 1
    min_pipes_per_pair = 0
    max_users_per_pipe = 5
    max_idle_secs = 0
    restart_pipe_after = 1000

    def initialize(self):
        self.callback = self.get_argument('callback', default=None)

    def log_vmsize(self):
        if self.verbosity < 1:
            return
        scale = {'kB': 1024, 'mB': 1048576,
                 'KB': 1024, 'MB': 1048576}
        try:
            for line in open('/proc/%d/status' % os.getpid()):
                if line.startswith('VmSize:'):
                    _, num, unit = line.split()
                    break
            vmsize = int(num) * scale[unit]
            if vmsize > self.stats['vmsize']:
                logging.warning("VmSize of %s from %d to %d" % (os.getpid(), self.stats['vmsize'], vmsize))
                self.stats['vmsize'] = vmsize
        except:
            # don't let a stupid logging function mess us up
            pass


    def sendResponse(self, data):
        self.log_vmsize()
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
            'responseData': {
                'useCount': { '%s-%s' % pair: useCount
                              for pair, useCount in self.stats['useCount'].items() },
                'runningPipes': { '%s-%s' % pair: len(pipes)
                                  for pair, pipes in self.pipelines.items()
                                  if pipes != [] },
                'holdingPipes': len(self.pipelines_holding),
            },
            'responseDetails': None,
            'responseStatus': 200
        })


class RootHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        self.redirect("http://wiki.apertium.org/wiki/Apertium-apy")


class TranslateHandler(BaseHandler):
    def notePairUsage(self, pair):
        self.stats['useCount'][pair] = 1 + self.stats['useCount'].get(pair, 0)

    unknownMarkRE = re.compile(r'\*([^.,;:\t\* ]+)')
    def maybeStripMarks(self, markUnknown, l1, l2, translated):
        self.noteUnknownTokens("%s-%s" % (l1, l2), translated)
        if markUnknown:
            return translated
        else:
            return re.sub(self.unknownMarkRE, r'\1', translated)

    def noteUnknownTokens(self, pair, text):
        if self.missingFreqs:
            for token in re.findall(self.unknownMarkRE, text):
                if self.inMemoryUnknown:
                    inMemoryUnknownToken(token, pair, self.missingFreqs, self.inMemoryLimit)
                else:
                    noteUnknownToken(token, pair, self.missingFreqs)

    def cleanable(self, i, pair, pipe):
        if pipe.useCount > self.restart_pipe_after:
            # Not affected by min_pipes_per_pair
            logging.info('A pipe for pair %s-%s has handled %d requests, scheduling restart',
                         pair[0], pair[1], self.restart_pipe_after)
            return True
        elif (i >= self.min_pipes_per_pair
              and self.max_idle_secs != 0
              and time.time() - pipe.lastUsage > self.max_idle_secs):
            logging.info("A pipe for pair %s-%s hasn't been used in %d secs, scheduling shutdown",
                         pair[0], pair[1], self.max_idle_secs)
            return True
        else:
            return False

    def cleanPairs(self):
        for pair in self.pipelines:
            pipes = self.pipelines[pair]
            to_clean = set(p for i, p in enumerate(pipes)
                           if self.cleanable(i, pair, p))
            self.pipelines_holding += to_clean
            pipes[:] = [p for p in pipes if p not in to_clean]
            heapq.heapify(pipes)
        # The holding area lets us restart pipes after n usages next
        # time round, since with lots of traffic an active pipe may
        # never reach 0 users
        self.pipelines_holding[:] = [p for p in self.pipelines_holding
                                     if p.users > 0]
        if self.pipelines_holding:
            logging.info("%d pipelines still scheduled for shutdown", len(self.pipelines_holding))

    def getPipeCmds(self, l1, l2):
        if (l1, l2) not in self.pipeline_cmds:
            mode_path = self.pairs['%s-%s' % (l1, l2)]
            self.pipeline_cmds[(l1, l2)] = translation.parseModeFile(mode_path)
        return self.pipeline_cmds[(l1, l2)]

    def shouldStartPipe(self, l1, l2):
        pipes = self.pipelines.get((l1, l2), [])
        if pipes == []:
            logging.info("%s-%s not in pipelines of this process",
                         l1, l2)
            return True
        else:
            min_p = pipes[0]
            if len(pipes) < self.max_pipes_per_pair and min_p.users > self.max_users_per_pipe:
                logging.info("%s-%s has ≥%d users per pipe but only %d pipes",
                             l1, l2, min_p.users, len(pipes))
                return True
            else:
                return False

    def getPipeline(self, l1, l2):
        pair = (l1, l2)
        if self.shouldStartPipe(l1, l2):
            logging.info("Starting up a new pipeline for %s-%s …", l1, l2)
            if pair not in self.pipelines:
                self.pipelines[pair] = []
            p = translation.makePipeline(self.getPipeCmds(l1, l2))
            heapq.heappush(self.pipelines[pair], p)
        return self.pipelines[pair][0]

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

    @gen.coroutine
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

        if '%s-%s' % (l1, l2) in self.pairs:
            before = self.logBeforeTranslation()
            pipeline = self.getPipeline(l1, l2)
            self.notePairUsage((l1, l2))
            translated = yield pipeline.translate(toTranslate)
            self.logAfterTranslation(before, toTranslate)
            self.sendResponse({
                'responseData': {
                    'translatedText': self.maybeStripMarks(markUnknown, l1, l2, translated)
                },
                'responseDetails': None,
                'responseStatus': 200
            })
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

                        self.write(translation.translateDoc(tempFile, allowedMimeTypes[mtype], self.pairs['%s-%s' % (l1, l2)]))
                        self.finish()
                    else:
                        self.send_error(400, explanation='Invalid file type %s' % mtype)
        else:
            self.send_error(400, explanation='That pair is not installed')


class AnalyzeHandler(BaseHandler):
    def postproc_text(self, in_text, result):
        lexical_units = util.removeDotFromDeformat(in_text, re.findall(r'\^([^\$]*)\$([^\^]*)', result))
        return [(lu[0], lu[0].split('/')[0] + lu[1])
                for lu
                in lexical_units]

    @tornado.web.asynchronous
    @gen.coroutine
    def get(self):
        in_text = self.get_argument('q')
        in_mode = toAlpha3Code(self.get_argument('lang'))
        if in_mode in self.analyzers:
            [path, mode] = self.analyzers[in_mode]
            formatting = 'txt'
            commands = [['apertium', '-d', path, '-f', formatting, mode]]
            result = yield translation.translateSimple(in_text, commands)
            self.sendResponse(self.postproc_text(in_text, result))
        else:
            self.send_error(400, explanation='That mode is not installed')


class GenerateHandler(BaseHandler):
    def preproc_text(self, in_text):
        lexical_units = re.findall(r'(\^[^\$]*\$[^\^]*)', in_text)
        if len(lexical_units) == 0:
            lexical_units = ['^%s$' % (in_text,)]
        return lexical_units, '[SEP]'.join(lexical_units)

    def postproc_text(self, lexical_units, result):
        return [(generation, lexical_units[i])
                for (i, generation)
                in enumerate(result.split('[SEP]'))]

    @tornado.web.asynchronous
    @gen.coroutine
    def get(self):
        in_text = self.get_argument('q')
        in_mode = toAlpha3Code(self.get_argument('lang'))
        if in_mode in self.generators:
            [path, mode] = self.generators[in_mode]
            formatting = 'none'
            commands = [['apertium', '-d', path, '-f', formatting, mode]]
            lexical_units, to_generate = self.preproc_text(in_text)
            result = yield translation.translateSimple(to_generate, commands)
            self.sendResponse(self.postproc_text(lexical_units, result))
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

        @run_async_thread
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

            @run_async_thread
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
                self.sendResponse({'nob': 100})  # TODO: Some more reasonable response
        else:
            def handleCoverages(coverages):
                self.sendResponse(coverages)

            pool = Pool(processes=1)
            result = pool.apply_async(getCoverages, [text, self.analyzers], {'penalize': True}, callback=handleCoverages)
            pool.close()
            try:
                coverages = result.get(timeout=self.timeout)
                # TODO: Coverages are not actually sent!!
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


class PipeDebugHandler(BaseHandler):

    @gen.coroutine
    def get(self):

        toTranslate = self.get_argument('q')

        try:
            l1, l2 = map(toAlpha3Code, self.get_argument('langpair').split('|'))
        except ValueError:
            self.send_error(400, explanation='That pair is invalid, use e.g. eng|spa')

        mode_path = self.pairs['%s-%s' % (l1, l2)]
        try:
            _, commands = translation.parseModeFile(mode_path)
        except Exception:
            self.send_error(500)
            return

        res = yield translation.translatePipeline(toTranslate, commands)
        if self.get_status() != 200:
            self.send_error(self.get_status())
            return

        output, pipeline = res

        self.sendResponse({
            'responseData': {'output': output, 'pipeline': pipeline},
            'responseDetails': None,
            'responseStatus': 200
        })

missingFreqsDb = ''


def setupHandler(port, pairs_path, nonpairs_path, langNames, missingFreqs, timeout, max_pipes_per_pair, min_pipes_per_pair, max_users_per_pipe, max_idle_secs, restart_pipe_after, verbosity=0, scaleMtLogs=False, memory=0):

    global missingFreqsDb
    missingFreqsDb = missingFreqs

    Handler = BaseHandler
    Handler.langNames = langNames
    Handler.missingFreqs = missingFreqs
    Handler.timeout = timeout
    Handler.max_pipes_per_pair = max_pipes_per_pair
    Handler.min_pipes_per_pair = min_pipes_per_pair
    Handler.max_users_per_pipe = max_users_per_pipe
    Handler.max_idle_secs = max_idle_secs
    Handler.restart_pipe_after = restart_pipe_after
    Handler.scaleMtLogs = scaleMtLogs
    Handler.inMemoryUnknown = True if memory > 0 else False
    Handler.inMemoryLimit = memory
    Handler.verbosity = verbosity

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


def sanity_check():
    locale_vars = ["LANG", "LC_ALL"]
    u8 = re.compile("UTF-?8", re.IGNORECASE)
    if not any(re.search(u8, os.environ.get(key, ""))
               for key in locale_vars):
        print("servlet.py: error: APY needs a UTF-8 locale, please set LANG or LC_ALL",
              file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    sanity_check()
    parser = argparse.ArgumentParser(description='Start Apertium APY')
    parser.add_argument('pairs_path', help='path to Apertium installed pairs (all modes files in this path are included)')
    parser.add_argument('-s', '--nonpairs-path', help='path to Apertium SVN (only non-translator debug modes are included from this path)')
    parser.add_argument('-l', '--lang-names', help='path to localised language names sqlite database (default = langNames.db)', default='langNames.db')
    parser.add_argument('-f', '--missing-freqs', help='path to missing frequency sqlite database (default = None)', default=None)
    parser.add_argument('-p', '--port', help='port to run server on (default = 2737)', type=int, default=2737)
    parser.add_argument('-c', '--ssl-cert', help='path to SSL Certificate', default=None)
    parser.add_argument('-k', '--ssl-key', help='path to SSL Key File', default=None)
    parser.add_argument('-t', '--timeout', help='timeout for requests (default = 10)', type=int, default=10)
    parser.add_argument('-j', '--num-processes', help='number of processes to run (default = 1; use 0 to run one http server per core, where each http server runs all available language pairs)', nargs='?', type=int, default=1)
    parser.add_argument('-d', '--daemon', help='daemon mode: redirects stdout and stderr to files apertium-apy.log and apertium-apy.err ; use with --log-path', action='store_true')
    parser.add_argument('-P', '--log-path', help='path to log output files to in daemon mode; defaults to local directory', default='./')
    parser.add_argument('-i', '--max-pipes-per-pair', help='how many pipelines we can spin up per language pair (default = 1)', type=int, default=1)
    parser.add_argument('-n', '--min-pipes-per-pair', help='when shutting down pipelines, keep at least this many open per language pair (default = 0)', type=int, default=0)
    parser.add_argument('-u', '--max-users-per-pipe', help='how many concurrent requests per pipeline before we consider spinning up a new one (default = 5)', type=int, default=5)
    parser.add_argument('-m', '--max-idle-secs', help='if specified, shut down pipelines that have not been used in this many seconds', type=int, default=0)
    parser.add_argument('-r', '--restart-pipe-after', help='restart a pipeline if it has had this many requests (default = 1000)', type=int, default=1000)
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
        loggingHandler = logging.handlers.TimedRotatingFileHandler(smtlog, 'midnight', 0)
        loggingHandler.suffix = "%Y-%m-%d"
        logger.addHandler(loggingHandler)

        # if scalemt_logs is enabled, disable tornado.access logs
        if(args.daemon):
            logging.getLogger("tornado.access").propagate = False

    if not cld2:
        logging.warning('Unable to import CLD2, continuing using naive method of language detection')

    setupHandler(args.port, args.pairs_path, args.nonpairs_path, args.lang_names, args.missing_freqs, args.timeout, args.max_pipes_per_pair, args.min_pipes_per_pair, args.max_users_per_pipe, args.max_idle_secs, args.restart_pipe_after, args.verbosity, args.scalemt_logs, args.unknown_memory_limit)

    application = tornado.web.Application([
        (r'/', RootHandler),
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
        (r'/getLocale', GetLocaleHandler),
        (r'/pipedebug', PipeDebugHandler)
    ])

    global http_server
    if args.ssl_cert and args.ssl_key:
        http_server = tornado.httpserver.HTTPServer(application, ssl_options={
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
