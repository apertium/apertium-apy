#!/usr/bin/env python3
# -*- indent-tabs-mode: t -*-

import sys, threading, os, re, ssl, argparse, logging
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
from tools import getLocalizedLanguages, apertium, bilingualTranslate, removeLast, stripTags, processPerWord
    
class BaseHandler(tornado.web.RequestHandler):
    pairs = {}
    analyzers = {}
    generators = {}
    taggers = {}
    pipelines = {}
    callback = None
    timeout = None

    # The lock is needed so we don't let two threads write
    # simultaneously to a pipeline; then the first thread to read
    # might read translations of text put there by the second
    # thread …
    translock = threading.RLock()
    # TODO: one lock per pipeline, if the es-ca pipeline is free,
    # we don't need to wait just because mk-en is currently
    # translating. In that case, should also make hardbreak()
    # pipeline dependent.
    
    def initialize(self):
        callbacks = self.get_arguments('callback')
        if callbacks:
            self.callback = callbacks[0]

    def translateApertium(self, toTranslate, pair):
        strPair = '%s-%s' % pair
        if strPair in self.pairs:
            p1 = Popen(["echo", toTranslate], stdout=PIPE)
            p2 = Popen(["apertium", "-d %s" % self.pairs[strPair], strPair], stdin=p1.stdout, stdout=PIPE)
            p1.stdout.close()  # Allow p1 to receive a SIGPIPE if p2 exits.
            output = p2.communicate()[0].decode('utf-8')
            #print(output)
            return output
        else:
            return False

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
                #if re.search('lrx-proc', command):
                #	outCommand = command
                #else:
                #	outCommand = re.sub('^(.*?)\s(.*)$', '\g<1> -z \g<2>', command)

                #print(command)

                #if re.search('automorf', command) or re.search('cg-proc', command) or re.search('autobil', command) or re.search('lrx-proc', command):
                #if not (re.search('lrx-proc', command) or re.search('transfer', command) or re.search('hfst-proc', command) or re.search('autopgen', command)):
                #if re.search('automorf', command) or re.search('cg-proc', command) or re.search('autobil', command):
                #if not re.search('apertium-pretransfer', command):
                #if not (re.search('lrx-proc', command)):
                if 1==1:
                    if re.search('apertium-pretransfer', command):
                        outCommand = command+" -z"
                    else:
                        outCommand = re.sub('^(.*?)\s(.*)$', '\g<1> -z \g<2>', command)
                    outCommand = re.sub('\s{2,}', ' ', outCommand)
                    outCommands.append(outCommand)
                    #print(outCommand)
            toReturn = ' | '.join(outCommands)
            toReturn = re.sub('\s*\$2', '', re.sub('\$1', '-g', toReturn))
            print(toReturn)
            return toReturn
        else:
            return False

    def translateNULFlush(self, toTranslate, pair):
        with self.translock:
            strPair = '%s-%s' % pair
            #print(self.pairs, self.pipelines)
            if strPair in self.pairs:
                #print("DEBUG 0.6")
                if strPair not in self.pipelines:
                    #print("DEBUG 0.7")
                    modeFile = "%s/modes/%s.mode" % (self.pairs[strPair], strPair)
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

                        self.pipelines[strPair] = (commandsDone[0], commandsDone[-1])

                #print("DEBUG 0.8")
                if strPair in self.pipelines:
                    (procIn, procOut) = self.pipelines[strPair]
                    deformat = Popen("apertium-deshtml", stdin=PIPE, stdout=PIPE)
                    deformat.stdin.write(bytes(toTranslate, 'utf-8'))
                    procIn.stdin.write(deformat.communicate()[0])
                    procIn.stdin.write(bytes('\0', "utf-8"))
                    procIn.stdin.flush()
                    #print("DEBUG 1 %s\\0" % toTranslate)
                    d = procOut.stdout.read(1)
                    #print("DEBUG 2 %s" % d)
                    output = []
                    while d and d != b'\0':
                        output.append(d)
                        d = procOut.stdout.read(1)
                    #print("DEBUG 3 %s" % output)
                    reformat = Popen("apertium-rehtml", stdin=PIPE, stdout=PIPE)
                    reformat.stdin.write(b"".join(output))
                    return reformat.communicate()[0].decode('utf-8')
                else:
                    print("no pair in pipelines")
                    return False
            else:
                print("strpair not in pairs")
                return False

    def translateModeDirect(self, toTranslate, pair):
        strPair = '%s-%s' % pair
        if strPair in self.pairs:
            modeFile = "%s/modes/%s.mode" % (self.pairs[strPair], strPair)
            modeFileLine = self.getModeFileLine(modeFile)
            commandList = []
            if modeFileLine:
                for command in modeFileLine.split('|'):
                    thisCommand = command.strip().split(' ')
                    commandList.append(thisCommand)
                p1 = Popen(["echo", toTranslate], stdout=PIPE)
                commandsDone = [p1]
                for command in commandList:
                    #print(command, commandsDone, commandsDone[-1])
                    #print(command)
                    newP = Popen(command, stdin=commandsDone[-1].stdout, stdout=PIPE)
                    commandsDone.append(newP)

                p1.stdout.close()  # Allow p1 to receive a SIGPIPE if p2 exits.
                output = commandsDone[-1].communicate()[0].decode('utf-8')
                print(output)
                return output
            else:
                return False
        else:
            return False

    def translateModeSimple(self, toTranslate, pair):
        strPair = '%s-%s' % pair
        if strPair in self.pairs:
            modeFile = "%s/modes/%s.mode" % (self.pairs[strPair], strPair)
            p1 = Popen(["echo", toTranslate], stdout=PIPE)
            p2 = Popen(["sh", modeFile, "-g"], stdin=p1.stdout, stdout=PIPE)
            p1.stdout.close()  # Allow p1 to receive a SIGPIPE if p2 exits.
            output = p2.communicate()[0].decode('utf-8')
            print(output)
            return output
        else:
            return False

    def hardbreak(self):
        """If others are waiting on us, we send short requests, otherwise we
        try to minimise the number of requests, but without
        letting buffers fill up.

        Unfortunately, if we've already started a long
        request, the next one to come along will have to wait
        one long request until they start getting shorter.

        These numbers could probably be tweaked a lot.
        """
        if threading.active_count()>2:
            hardbreak=10000
            # (would prefer "self.translock.waiting_count", but doesn't seem exist)
        else:
            hardbreak=50000
        print((threading.active_count(), hardbreak))
        return hardbreak

    def translateSplitting(self, toTranslate, pair):
        """Splitting it up a bit ensures we don't fill up FIFO buffers (leads
        to processes hanging on read/write)."""
        allSplit = []	# [].append and join faster than str +=
        last=0
        while last<len(toTranslate):
            hardbreak = self.hardbreak()
            # We would prefer to split on a period seen before the
            # hardbreak, if we can:
            softbreak = int(hardbreak*0.9)
            dot=toTranslate.find(".", last+softbreak, last+hardbreak)
            if dot>-1:
                next=dot
            else:
                next=last+hardbreak
            print("toTranslate[%d:%d]" %(last,next))
            allSplit.append(self.translateNULFlush(toTranslate[last:next],
                                   pair))
            last=next
        return "".join(allSplit)

    def translate(self, toTranslate, pair):
        # TODO: should probably check whether we have the pair
        # here, instead of for each split …
        return self.translateSplitting(toTranslate, pair)
        
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
            self.sendResponse({pair: info[1] for (pair, info) in self.analyzers.items()})
        elif query == 'generators':
            self.sendResponse({pair: info[1] for (pair, info) in self.generators.items()})
        elif query == 'taggers' or query == 'disambiguators':
            self.sendResponse({pair: info[1] for (pair, info) in self.taggers.items()})
        else:
            self.send_error(400)

class TranslateHandler(BaseHandler): #TODO: Make Async
    def get(self):
        (l1, l2) = self.get_argument('langpair').split('|')
        toTranslate = self.get_argument('q')
        
        translated = self.translate(toTranslate, (l1, l2))
        #translated = self.translateModeSimple(toTranslate, (l1, l2))
        if not translated:
            self.send_error(400)
        else:
            toReturn = {"responseData":
                {"translatedText": translated},
                "responseDetails": None,
                "responseStatus": 200}
            self.sendResponse(toReturn)
    
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
            try:
                analysis = result.get(timeout = self.timeout)
            except TimeoutError:
                self.send_error(408)

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
            try:
                generated = result.get(timeout = self.timeout)
            except TimeoutError:
                self.send_error(408)
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
        try:
            outputs = result.get(timeout = self.timeout)
        except TimeoutError:
            self.send_error(408)
                
class GetLocaleHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        if 'Accept-Language' in self.request.headers:
            locales = [locale.split(';')[0] for locale in self.request.headers['Accept-Language'].split(',')]
            self.sendResponse(locales)
        else:
            self.send_error(400)

def setupHandler(port, pairsPath, langnames, timeout):
    Handler = BaseHandler
    Handler.langnames = langnames
    Handler.timeout = timeout

    rawPairs, rawAnalyzers, rawGenerators, rawTaggers = searchPath(pairsPath)
    for pair in rawPairs:
        (f, l1, l2) = pair
        Handler.pairs['%s-%s' % (l1, l2)] = f
    for analyzer in rawAnalyzers:
        Handler.analyzers[analyzer[2]] = (analyzer[0], analyzer[1])
    for generator in rawGenerators:
        Handler.generators[generator[2]] = (generator[0], generator[1])
    for tagger in rawTaggers:
        Handler.taggers[tagger[2]] = (tagger[0], tagger[1])

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Start Apertium APY')
    parser.add_argument('pairsPath', help='path to Apertium trunk')
    parser.add_argument('-l', '--lang-names', help='path to localised language names sqlite database (default = unicode.db)', default='unicode.db')
    parser.add_argument('-p', '--port', help='port to run server on (default = 2737)', type=int, default=2737)
    parser.add_argument('-c', '--ssl-cert', help='path to SSL Certificate', default=None)
    parser.add_argument('-k', '--ssl-key', help='path to SSL Key File', default=None)
    parser.add_argument('-t', '--timeout', help='timeout for requests (default = 10)', type=int, default=10)
    parser.add_argument('-j', '--num-processes', help='number of processes to run (default = number of cores)', type=int, default=0)
    args = parser.parse_args()
    
    setupHandler(args.port, args.pairsPath, args.lang_names, args.timeout)
   
    logging.getLogger().setLevel(logging.INFO)
    enable_pretty_logging()
    application = tornado.web.Application([
        (r'/list', ListHandler),
        (r'/listPairs', ListHandler),
        (r'/translate', TranslateHandler),
        (r'/analy[sz]e', AnalyzeHandler),
        (r'/generate', GenerateHandler),
        (r'/listLanguageNames', ListLanguageNamesHandler),
        (r'/perWord', PerWordHandler),
        (r'/getLocale', GetLocaleHandler)
    ])
    
    if args.ssl_cert and args.ssl_key:
        http_server = tornado.httpserver.HTTPServer(application, ssl_options = {
            'certfile': args.ssl_cert,
            'keyfile': args.ssl_key,
        })
        logging.info('Serving at https://localhost:%s' % args.port)
    else:
        http_server = tornado.httpserver.HTTPServer(application)
        logging.info('Serving at http://localhost:%s' % args.port)
    http_server.bind(args.port)
    http_server.start(args.num_processes)
    tornado.ioloop.IOLoop.instance().start()
