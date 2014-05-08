#!/usr/bin/env python3
# -*- indent-tabs-mode: nil -*-

import sys, threading, os, re, ssl, argparse, logging, time, signal
from lxml import etree
from subprocess import Popen, PIPE
from multiprocessing import Pool, TimeoutError

import tornado, tornado.web, tornado.httpserver
try: #3.1
    from tornado.log import enable_pretty_logging
except ImportError: #2.1
    from tornado.options import enable_pretty_logging
from tornado import escape
from tornado.escape import utf8

from modeSearch import searchPath
from util import getLocalizedLanguages, apertium, bilingualTranslate, removeLast, stripTags, processPerWord, getCoverage, getCoverages, toAlpha3Code
from translation import translate

try:
    import cld2full as cld2
except:
    logging.warning('Unable to import CLD2, continuing using naive method of language detection')
    cld2 = None

def sig_handler(sig, frame):
    if 'children' in frame.f_locals:
        for child in frame.f_locals['children']:
            os.kill(child, signal.SIGTERM)
    # else: we are one of the children
    logging.warning('Caught signal: %s', sig)
    exit()

class BaseHandler(tornado.web.RequestHandler):
    pairs = {}
    analyzers = {}
    generators = {}
    taggers = {}
    pipelines = {}
    callback = None
    timeout = None
    stats = {
        'useCount': {},
        'lastUsage': {},
    }

    # The lock is needed so we don't let two threads write
    # simultaneously to a pipeline; then the first thread to read
    # might read translations of text put there by the second
    # thread …
    pipeline_locks = {}     # (l1,l2): threading.RLock() for (l1,l2) in pairs

    def initialize(self):
        callbacks = self.get_arguments('callback')
        if callbacks:
            self.callback = callbacks[0]

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

    def notePairUsage(self, pair):
        self.stats['useCount'][pair] = 1 + self.stats['useCount'].get(pair, 0)
        if self.max_idle_secs:
            self.stats['lastUsage'][pair] = time.time()

    def cleanPairs(self):
        if not self.max_idle_secs:
            return
        for pair,lastUsage in self.stats['lastUsage'].items():
            if time.time() - lastUsage > self.max_idle_secs and pair in self.pipelines:
                logging.info("Shutting down pair %s-%s since it hasn't been used in %d secs"%(pair[0],pair[1],self.max_idle_secs))
                # Killing the first one should bring down the rest:
                self.pipelines[pair][0].kill()
                self.pipelines.pop(pair)
                self.pipeline_locks.pop(pair)


    @tornado.web.asynchronous
    def post(self):
        self.get()

class ListHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        query = self.get_arguments('q')
        if query:
            query = query[0]

        if self.request.path == '/listPairs' or query == 'pairs':
            responseData = []
            for pair in self.pairs:
                (l1, l2) = pair.split('-')
                responseData.append({'sourceLanguage': l1, 'targetLanguage': l2})
            self.sendResponse({'responseData': responseData, 'responseDetails': None, 'responseStatus': 200})
        elif query == 'analyzers' or query == 'analysers':
            self.sendResponse({pair: modename for (pair, (path,modename)) in self.analyzers.items()})
        elif query == 'generators':
            self.sendResponse({pair: modename for (pair, (path,modename)) in self.generators.items()})
        elif query == 'taggers' or query == 'disambiguators':
            self.sendResponse({pair: modename for (pair, (path,modename)) in self.taggers.items()})
        else:
            self.send_error(400)


class StatsHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        self.sendResponse({'responseData': { '%s-%s'%pair: useCount
                                             for pair,useCount
                                             in self.stats['useCount'].items() },
                           'responseDetails': None, 'responseStatus': 200})

class ThreadableMixin:
    """To use:

    1) inherit this class
    2) define a self._worker that sets self.res to whatever the result value should be.
    3) define a self._handler that checks for hasattr(self, 'res')
    4) start the worker with self.start_worker(self._handler, arg1, arg2, …, argn)
       where arg1…argn are passed on to self._worker

    """
    def start_worker(self, *args):
        # TODO: max threads, using https://docs.python.org/3/library/concurrent.futures.html#concurrent.futures.ThreadPoolExecutor
        threading.Thread(target=self.run_worker, args=args).start()

    def run_worker(self, result_handler, *worker_args):
        try:
            self._worker(*worker_args)
        except tornado.web.HTTPError:
            self.set_status(408) # TODO e.status_code
        except:
            logging.error("_worker problem ", exc_info=True)
            self.set_status(500)
        tornado.ioloop.IOLoop.instance().add_callback(self.async_callback(result_handler))

class TranslateHandler(BaseHandler, ThreadableMixin):
    def getModeFileLine(self, modeFile):
        modeFileContents = open(modeFile, 'r').readlines()
        modeFileLine = None
        for line in modeFileContents:
            if '|' in line:
                modeFileLine = line
        if modeFileLine != None:
            commands = modeFileLine.split('|')
            outCommands = []
            for command in commands:
                command = command.strip()
                if re.search('apertium-pretransfer', command):
                    outCommand = command+" -z"
                else:
                    outCommand = re.sub('^(.*?)\s(.*)$', '\g<1> -z \g<2>', command)
                outCommand = re.sub('\s{2,}', ' ', outCommand)
                outCommands.append(outCommand)
            toReturn = ' | '.join(outCommands)
            toReturn = re.sub('\s*\$2', '', re.sub('\$1', '-g', toReturn))
            return toReturn
        else:
            self.send_error(400)

    def runPipeline(self, l1, l2):
        if (l1,l2) not in self.pipelines:
            logging.info("%s,%s not in pipelines of this process, starting …" %(l1,l2))
            modeFile = self.pairs['%s-%s' %(l1,l2)]
            modeFileLine = self.getModeFileLine(modeFile)
            commandList = []
            if modeFileLine:
                commandList = [ c.strip().split() for c in
                                modeFileLine.split('|') ]
                commandsDone = []
                for command in commandList:
                    if len(commandsDone)>0:
                        newP = Popen(command, stdin=commandsDone[-1].stdout, stdout=PIPE)
                    else:
                        newP = Popen(command, stdin=PIPE, stdout=PIPE)
                    commandsDone.append(newP)

                self.pipeline_locks[(l1,l2)] = threading.RLock()
                self.pipelines[(l1,l2)] = (commandsDone[0], commandsDone[-1])

    def _worker (self, toTranslate, l1, l2):
        self.res = translate(toTranslate,
                             self.pipeline_locks[(l1,l2)],
                             self.pipelines[(l1,l2)])

    @tornado.web.asynchronous
    def get(self):
        (l1, l2) = self.get_argument('langpair').split('|')
        toTranslate = self.get_argument('q')

        def handleTranslation():
            if self.get_status () != 200:
                self.send_error (self.get_status ())
                return
            if hasattr(self, 'res'):
                self.sendResponse({"responseData":
                                   {"translatedText": self.res},
                                   "responseDetails": None,
                                   "responseStatus": 200})
                return
            if hasattr(self, 'redir'):
                self.redirect(self.redir)
                return
            self.send_error (500)


        if '%s-%s' % (l1, l2) in self.pairs:
            self.runPipeline(l1, l2)
            self.start_worker(handleTranslation, toTranslate, l1, l2)
            self.notePairUsage((l1, l2))
            self.cleanPairs()
        else:
            self.send_error(400)

class AnalyzeHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        mode = self.get_argument('mode')
        toAnalyze = self.get_argument('q')

        def handleAnalysis(analysis):
            lexicalUnits = removeLast(toAnalyze, re.findall(r'\^([^\$]*)\$([^\^]*)', analysis))
            self.sendResponse([(lexicalUnit[0], lexicalUnit[0].split('/')[0] + lexicalUnit[1]) for lexicalUnit in lexicalUnits])

        if mode in self.analyzers:
            pool = Pool(processes = 1)
            result = pool.apply_async(apertium, [toAnalyze, self.analyzers[mode][0], self.analyzers[mode][1]], callback = handleAnalysis)
            pool.close()
            try:
                analysis = result.get(timeout = self.timeout)
            except TimeoutError:
                self.send_error(408)
                pool.terminate()
        else:
            self.send_error(400)

class GenerateHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        mode = self.get_argument('mode')
        toGenerate = self.get_argument('q')

        def handleGeneration(generated):
            generated = removeLast(toGenerate, generated)
            self.sendResponse([(generation, lexicalUnits[index]) for (index, generation) in enumerate(generated.split('[SEP]'))])

        if mode in self.generators:
            lexicalUnits = re.findall(r'(\^[^\$]*\$[^\^]*)', toGenerate)
            if len(lexicalUnits) == 0:
                lexicalUnits = ['^%s$' % toGenerate]
            pool = Pool(processes = 1)
            result = pool.apply_async(apertium, ('[SEP]'.join(lexicalUnits), self.generators[mode][0], self.generators[mode][1]), {'formatting': 'none'}, callback = handleGeneration)
            pool.close()
            try:
                generated = result.get(timeout = self.timeout)
            except TimeoutError:
                self.send_error(408)
                pool.terminate()
        else:
            self.send_error(400)

class ListLanguageNamesHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        localeArg = self.get_arguments('locale')
        languagesArg = self.get_arguments('languages')

        if self.langnames:
            if localeArg:
                if languagesArg:
                    self.sendResponse(getLocalizedLanguages(localeArg[0], self.langnames, languages = languagesArg[0].split(' ')))
                else:
                    self.sendResponse(getLocalizedLanguages(localeArg[0], self.langnames))
            elif 'Accept-Language' in self.request.headers:
                locales = [locale.split(';')[0] for locale in self.request.headers['Accept-Language'].split(',')]
                for locale in locales:
                    languageNames = getLocalizedLanguages(locale, self.langnames)
                    if languageNames:
                        self.sendResponse(languageNames)
                        return
                self.sendResponse(getLocalizedLanguages('en', self.langnames))
            else:
                self.sendResponse(getLocalizedLanguages('en', self.langnames))
        else:
            self.sendResponse({})

class PerWordHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        lang = self.get_argument('lang')
        modes = set(self.get_argument('modes').split(' '))
        query = self.get_argument('q')

        if not modes <= {'morph', 'biltrans', 'tagger', 'disambig', 'translate'}:
            self.send_error(400)
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

            if not output:
                self.send_error(400)
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

        pool = Pool(processes = 1)
        result = pool.apply_async(processPerWord, (self.analyzers, self.taggers, lang, modes, query), callback = handleOutput)
        pool.close()
        try:
            outputs = result.get(timeout = self.timeout)
        except TimeoutError:
            self.send_error(408)
            pool.terminate()

class CoverageHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        mode = self.get_argument('mode')
        text = self.get_argument('q')
        if not text:
            return self.send_error(400)

        def handleCoverage(coverage):
            self.sendResponse([coverage])

        if mode in self.analyzers:
            pool = Pool(processes = 1)
            result = pool.apply_async(getCoverage, [text, self.analyzers[mode][0], self.analyzers[mode][1]], callback = handleCoverage)
            pool.close()
            try:
                analysis = result.get(timeout = self.timeout)
            except TimeoutError:
                self.send_error(408)
                pool.terminate()
        else:
            self.send_error(400)

class IdentifyLangHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        text = self.get_argument('q')
        if not text:
            return self.send_error(400)

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

            pool = Pool(processes = 1)
            result = pool.apply_async(getCoverages, [text, self.analyzers], {'penalize': True}, callback = handleCoverages)
            pool.close()
            try:
                coverages = result.get(timeout = self.timeout)
            except TimeoutError:
                self.send_error(408)
                pool.terminate()

class GetLocaleHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        if 'Accept-Language' in self.request.headers:
            locales = [locale.split(';')[0] for locale in self.request.headers['Accept-Language'].split(',')]
            self.sendResponse(locales)
        else:
            self.send_error(400)

def setupHandler(port, pairs_path, nonpairs_path, langnames, timeout, max_idle_secs, verbosity=0):
    Handler = BaseHandler
    Handler.langnames = langnames
    Handler.timeout = timeout
    Handler.max_idle_secs = max_idle_secs

    modes = searchPath(pairs_path, verbosity=verbosity)
    if nonpairs_path:
        src_modes = searchPath(nonpairs_path, include_pairs=False, verbosity=verbosity)
        for mtype in modes:
            modes[mtype] += src_modes[mtype]

    [logging.info("%d %s modes found" % (len(modes[mtype]), mtype)) for mtype in modes]

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
    parser.add_argument('-l', '--lang-names', help='path to localised language names sqlite database (default = unicode.db)', default='unicode.db')
    parser.add_argument('-p', '--port', help='port to run server on (default = 2737)', type=int, default=2737)
    parser.add_argument('-c', '--ssl-cert', help='path to SSL Certificate', default=None)
    parser.add_argument('-k', '--ssl-key', help='path to SSL Key File', default=None)
    parser.add_argument('-t', '--timeout', help='timeout for requests (default = 10)', type=int, default=10)
    parser.add_argument('-j', '--num-processes', help='number of processes to run (default = number of cores)', type=int, default=0)
    parser.add_argument('-d', '--daemon', help='daemon mode: redirects stdout and stderr to files apertium-apy.log and apertium-apy.err ; use with --log-path', action='store_true')
    parser.add_argument('-P', '--log-path', help='path to log output files to in daemon mode; defaults to local directory', default='./')
    parser.add_argument('-m', '--max-idle-secs', help="shut down pipelines it haven't been used in this many seconds", type=int, default=0)
    parser.add_argument('-v', '--verbosity', help='logging verbosity', type=int, default=0)
    args = parser.parse_args()

    if (args.daemon):
        # regular content logs are output stderr
        # python messages are mostly output to stdout
        # hence swapping the filenames?
        sys.stderr = open(os.path.join(args.log_path, "apertium-apy.log"), 'a+')
        sys.stdout = open(os.path.join(args.log_path, "apertium-apy.err"), 'a+')

    logging.getLogger().setLevel(logging.INFO)
    enable_pretty_logging()

    setupHandler(args.port, args.pairs_path, args.nonpairs_path, args.lang_names, args.timeout, args.max_idle_secs, args.verbosity)

    application = tornado.web.Application([
        (r'/list', ListHandler),
        (r'/listPairs', ListHandler),
        (r'/stats', StatsHandler),
        (r'/translate', TranslateHandler),
        (r'/analy[sz]e', AnalyzeHandler),
        (r'/generate', GenerateHandler),
        (r'/listLanguageNames', ListLanguageNamesHandler),
        (r'/perWord', PerWordHandler),
        (r'/coverage', CoverageHandler),
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
