#!/usr/bin/env python3
# -*- indent-tabs-mode: t -*-

import sys, threading, os, re, ssl, argparse, sqlite3, logging
from lxml import etree
from subprocess import Popen, PIPE
from multiprocessing import Pool

import tornado, tornado.web, tornado.httpserver
from tornado.options import enable_pretty_logging
from tornado import escape
from tornado.escape import utf8

def searchPath(pairsPath):
    # TODO: this doesn't get es-en_GB and such. If it's supposed
    # to work on the SVN directories (as opposed to installed
    # pairs), it should parse modes.xml and grab all and only
    # modes that have install="yes"
    REmodeFile = re.compile("([a-z]{2,3})-([a-z]{2,3})\.mode")
    REmorphFile = re.compile("(([a-z]{2,3}(-[a-z]{2,3})?)-(an)?mor(ph)?)\.mode")
    REgenerFile = re.compile("(([a-z]{2,3}(-[a-z]{2,3})?)-gener[A-z]*)\.mode")
    REtaggerFile = re.compile("(([a-z]{2,3}(-[a-z]{2,3})?)-tagger)\.mode")

    pairs = []
    analyzers = []
    generators = []
    taggers = []
    
    contents = os.listdir(pairsPath)
    for content in contents:
        curContent = os.path.join(pairsPath, content)
        if os.path.isdir(curContent):
            curMode = os.path.join(curContent, "modes")
            if os.path.isdir(curMode):
                modeFiles = os.listdir(curMode)
                for modeFile in modeFiles:
                    if REmodeFile.match(modeFile):
                        l1 = REmodeFile.sub("\g<1>", modeFile)
                        l2 = REmodeFile.sub("\g<2>", modeFile)
                        #pairTuple = (os.path.join(curMode, modeFile), l1, l2)
                        pairTuple = (curContent, l1, l2)
                        pairs.append(pairTuple)
                    elif REmorphFile.match(modeFile):
                        mode = REmorphFile.sub("\g<1>", modeFile) #en-es-anmorph
                        lang = REmorphFile.sub("\g<2>", modeFile) #en-es
                        analyzerTuple = (curContent, mode, lang)
                        analyzers.append(analyzerTuple)
                    elif REgenerFile.match(modeFile):
                        mode = REgenerFile.sub("\g<1>", modeFile) #en-es-generador
                        lang = REgenerFile.sub("\g<2>", modeFile) #en-es
                        generatorTuple = (curContent, mode, lang)
                        generators.append(generatorTuple)
                    elif REtaggerFile.match(modeFile):
                        mode = REtaggerFile.sub("\g<1>", modeFile) #en-es-tagger
                        lang = REtaggerFile.sub("\g<2>", modeFile) #en-es
                        taggerTuple = (curContent, mode, lang)
                        taggers.append(taggerTuple)
                        
    return pairs, analyzers, generators, taggers

def getLocalizedLanguages(locale, dbPath, languages = []):
    iso639Codes = {"abk":"ab","aar":"aa","afr":"af","aka":"ak","sqi":"sq","amh":"am","ara":"ar","arg":"an","hye":"hy","asm":"as","ava":"av","ave":"ae","aym":"ay","aze":"az","bam":"bm","bak":"ba","eus":"eu","bel":"be","ben":"bn","bih":"bh","bis":"bi","bos":"bs","bre":"br","bul":"bg","mya":"my","cat":"ca","cha":"ch","che":"ce","nya":"ny","zho":"zh","chv":"cv","cor":"kw","cos":"co","cre":"cr","hrv":"hr","ces":"cs","dan":"da","div":"dv","nld":"nl","dzo":"dz","eng":"en","epo":"eo","est":"et","ewe":"ee","fao":"fo","fij":"fj","fin":"fi","fra":"fr","ful":"ff","glg":"gl","kat":"ka","deu":"de","ell":"el","grn":"gn","guj":"gu","hat":"ht","hau":"ha","heb":"he","her":"hz","hin":"hi","hmo":"ho","hun":"hu","ina":"ia","ind":"id","ile":"ie","gle":"ga","ibo":"ig","ipk":"ik","ido":"io","isl":"is","ita":"it","iku":"iu","jpn":"ja","jav":"jv","kal":"kl","kan":"kn","kau":"kr","kas":"ks","kaz":"kk","khm":"km","kik":"ki","kin":"rw","kir":"ky","kom":"kv","kon":"kg","kor":"ko","kur":"ku","kua":"kj","lat":"la","ltz":"lb","lug":"lg","lim":"li","lin":"ln","lao":"lo","lit":"lt","lub":"lu","lav":"lv","glv":"gv","mkd":"mk","mlg":"mg","msa":"ms","mal":"ml","mlt":"mt","mri":"mi","mar":"mr","mah":"mh","mon":"mn","nau":"na","nav":"nv","nob":"nb","nde":"nd","nep":"ne","ndo":"ng","nno":"nn","nor":"no","iii":"ii","nbl":"nr","oci":"oc","oji":"oj","chu":"cu","orm":"om","ori":"or","oss":"os","pan":"pa","pli":"pi","fas":"fa","pol":"pl","pus":"ps","por":"pt","que":"qu","roh":"rm","run":"rn","ron":"ro","rus":"ru","san":"sa","srd":"sc","snd":"sd","sme":"se","smo":"sm","sag":"sg","srp":"sr","gla":"gd","sna":"sn","sin":"si","slk":"sk","slv":"sl","som":"so","sot":"st","azb":"az","spa":"es","sun":"su","swa":"sw","ssw":"ss","swe":"sv","tam":"ta","tel":"te","tgk":"tg","tha":"th","tir":"ti","bod":"bo","tuk":"tk","tgl":"tl","tsn":"tn","ton":"to","tur":"tr","tso":"ts","tat":"tt","twi":"tw","tah":"ty","uig":"ug","ukr":"uk","urd":"ur","uzb":"uz","ven":"ve","vie":"vi","vol":"vo","wln":"wa","cym":"cy","wol":"wo","fry":"fy","xho":"xh","yid":"yi","yor":"yo","zha":"za","zul":"zu"}
    if locale in iso639Codes:
        locale = iso639Codes[locale]
    languages = list(set(languages))
    
    convertedLanguages = {}
    for language in languages:
        convertedLanguages[iso639Codes[language] if language in iso639Codes else language] = language
    
    output = {}
    if os.path.exists(dbPath):
        conn = sqlite3.connect(dbPath)
        c = conn.cursor()
        languageResults = c.execute('select * from languageNames where lg=?', (locale, )).fetchall()
        if languages:
            for languageResult in languageResults:
                if languageResult[2] in convertedLanguages:
                    output[convertedLanguages[languageResult[2]]] = languageResult[3]
        else:
            for languageResult in languageResults:
                output[languageResult[2]] = languageResult[3]
    else:
        print('failed to locate language name DB')
    return output

def apertium(*args, **kwargs):
    return BaseHandler.apertium(None, *args, **kwargs)
    
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

    def apertium(self, input, dir, mode, formatting=None):
        p1 = Popen(['echo', input], stdout=PIPE)
        if formatting:
            p2 = Popen(['apertium', '-d . -f %s' % formatting, mode], stdin=p1.stdout, stdout=PIPE, cwd=dir)
        else:
            p2 = Popen(['apertium', '-d .', mode], stdin=p1.stdout, stdout=PIPE, cwd=dir)
        p1.stdout.close()
        output = p2.communicate()[0].decode('utf-8')
        return output
        
    def bilingualTranslate(self, toTranslate, dir, mode):
        p1 = Popen(["echo", toTranslate], stdout=PIPE)
        p2 = Popen(["lt-proc", "-b", mode], stdin=p1.stdout, stdout=PIPE, cwd=dir)
        p1.stdout.close()
        output = p2.communicate()[0].decode('utf-8')
        return output

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
    
    @tornado.web.asynchronous
    def post(self):
        self.get()
        self.finish()
    
    def removeLast(self, input, analyses):
        if not input[-1] == '.':
            return analyses[:-1]
        else:
            return analyses

class ListHandler(BaseHandler):
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
        query = self.get_argument('q')
        
        toTranslate = query[0]
        translated = self.translate(toTranslate, (l1, l2))
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
            lexicalUnits = self.removeLast(toAnalyze, re.findall(r'\^([^\$]*)\$([^\^]*)', analysis))
            self.sendResponse([(lexicalUnit[0], lexicalUnit[0].split('/')[0] + lexicalUnit[1]) for lexicalUnit in lexicalUnits])
            self.finish()
        
        if mode in self.analyzers:
            with Pool(processes = 1) as pool:
                result = pool.apply_async(apertium, [toAnalyze, self.analyzers[mode][0], self.analyzers[mode][1]], callback = handleAnalysis)
                analysis = result.get(timeout = self.timeout)
        else:
            self.send_error(400)

class GenerateHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        mode = self.get_argument('mode')
        toGenerate = self.get_argument('q')
        
        def handleGeneration(generated):
            generated = self.removeLast(toGenerate, generated)
            self.sendResponse([(generation, lexicalUnits[index]) for (index, generation) in enumerate(generated.split('[SEP]'))])
            self.finish()
            
        if mode in self.generators:
            lexicalUnits = re.findall(r'(\^[^\$]*\$[^\^]*)', toGenerate)
            if len(lexicalUnits) == 0:
                lexicalUnits = ['^%s$' % toGenerate]
            with Pool(processes = 1) as pool:
                result = pool.apply_async(apertium, ('[SEP]'.join(lexicalUnits), self.generators[mode][0], self.generators[mode][1]), {'formatting': 'none'}, callback = handleGeneration)
                generated = result.get(timeout = self.timeout)
        else:
            self.send_error(400)
        
class ListLanguageNamesHandler(BaseHandler):
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
            
class PerWordHandler(BaseHandler): #TODO: Make Async
    def get(self):
        lang = self.get_argument('lang')
        modes = set(self.get_argument('modes').split(' '))
        query = self.get_argument('q')
        
        if not modes <= {'morph', 'biltrans', 'tagger', 'disambig', 'translate'}:
            self.send_error(400)
            return
        
        def stripTags(analysis):
            if '<' in analysis:
                return analysis[:analysis.index('<')]
            else:
                return analysis
        
        outputs = {}
        morph_lexicalUnits = None
        tagger_lexicalUnits = None
        lexicalUnitRE = r'\^([^\$]*)\$'
        
        if 'morph' in modes or 'biltrans' in modes:
            if lang in self.analyzers:
                modeInfo = self.analyzers[lang]
                analysis = self.apertium(query, modeInfo[0], modeInfo[1])
                morph_lexicalUnits = self.removeLast(query, re.findall(lexicalUnitRE, analysis))
                outputs['morph'] = [lexicalUnit.split('/')[1:] for lexicalUnit in morph_lexicalUnits]
                outputs['morph_inputs'] = [stripTags(lexicalUnit.split('/')[0]) for lexicalUnit in morph_lexicalUnits]
            else:
                self.send_error(400)
                return
                
        if 'tagger' in modes or 'disambig' in modes or 'translate' in modes:
            if lang in self.taggers:
                modeInfo = self.taggers[lang]
                analysis = self.apertium(query, modeInfo[0], modeInfo[1])
                tagger_lexicalUnits = self.removeLast(query, re.findall(lexicalUnitRE, analysis))
                outputs['tagger'] = [lexicalUnit.split('/')[1:] if '/' in lexicalUnit else lexicalUnit for lexicalUnit in tagger_lexicalUnits]
                outputs['tagger_inputs'] = [stripTags(lexicalUnit.split('/')[0]) for lexicalUnit in tagger_lexicalUnits]
            else:
                self.send_error(400)
                return
                
        if 'biltrans' in modes:
            if morph_lexicalUnits:
                outputs['biltrans'] = []
                for lexicalUnit in morph_lexicalUnits:
                    splitUnit = lexicalUnit.split('/')
                    forms = splitUnit[1:] if len(splitUnit) > 1 else splitUnit
                    rawTranslations = self.bilingualTranslate(''.join(['^%s$' % form for form in forms]), modeInfo[0], lang + '.autobil.bin')
                    translations = re.findall(lexicalUnitRE, rawTranslations)
                    outputs['biltrans'].append(list(map(lambda x: '/'.join(x.split('/')[1:]), translations)))
                    outputs['translate_inputs'] = outputs['morph_inputs']
            else:
                self.send_error(400)
                return
                
        if 'translate' in modes:
            if tagger_lexicalUnits:
                outputs['translate'] = []
                for lexicalUnit in tagger_lexicalUnits:
                    splitUnit = lexicalUnit.split('/')
                    forms = splitUnit[1:] if len(splitUnit) > 1 else splitUnit
                    rawTranslations = self.bilingualTranslate(''.join(['^%s$' % form for form in forms]), modeInfo[0], lang + '.autobil.bin')
                    translations = re.findall(lexicalUnitRE, rawTranslations)
                    outputs['translate'].append(list(map(lambda x: '/'.join(x.split('/')[1:]), translations)))
                    outputs['translate_inputs'] = outputs['tagger_inputs']
            else:
                self.send_error(400)
                return

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
            
class GetLocaleHandler(BaseHandler):
    def get(self): 
        locales = [locale.split(';')[0] for locale in self.request.headers['Accept-Language'].split(',')]
        self.sendResponse(locales)

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
    parser.add_argument('-l', '--langNames', help='path to localised language names sqlite database', default='unicode.db')
    parser.add_argument('-p', '--port', help='port to run server on', type=int, default=2737)
    parser.add_argument('-c', '--sslCert', help='path to SSL Certificate', default=None)
    parser.add_argument('-k', '--sslKey', help='path to SSL Key File', default=None)
    parser.add_argument('-t', '--timeout', help='timeout for requests', type=int, default=10)
    args = parser.parse_args()
    
    setupHandler(args.port, args.pairsPath, args.langNames, args.timeout)
   
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
    
    if args.sslCert and args.sslKey:
        http_server = tornado.httpserver.HTTPServer(application, ssl_options = {
            'certfile': args.sslCert,
            'keyfile': args.sslKey,
        })
        logging.info('Serving at https://localhost:%s' % args.port)
    else:
        http_server = tornado.httpserver.HTTPServer(application)
        logging.info('Serving at http://localhost:%s' % args.port)
    http_server.listen(args.port)
    tornado.ioloop.IOLoop.instance().start()
