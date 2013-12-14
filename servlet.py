#!/usr/bin/env python3
# -*- indent-tabs-mode: t -*-

import sys, threading, os, re, ssl, argparse, sqlite3
import http.server, socketserver, urllib.parse, json
from lxml import etree
from subprocess import Popen, PIPE #call

Handler = None
httpd = None


def searchPath(pairsPath):
    # TODO: this doesn't get es-en_GB and such. If it's supposed
    # to work on the SVN directories (as opposed to installed
    # pairs), it should parse modes.xml and grab all and only
    # modes that have install="yes"
    REmodeFile = re.compile("([a-z]{2,3})-([a-z]{2,3})\.mode")
    REmorphFile = re.compile("(([a-z]{2,3}(-[a-z]{2,3})?)-(an)?mor(ph)?)\.mode")
    REgenerFile = re.compile("(([a-z]{2,3}(-[a-z]{2,3})?)-gener[A-z]*)\.mode")

    pairs = []
    analyzers = []
    generators = []
    
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
                        
    return pairs, analyzers, generators

def getLocalizedLanguages(locale, dbPath, languages = []):
    iso639Codes = {"abk":"ab","aar":"aa","afr":"af","aka":"ak","sqi":"sq","amh":"am","ara":"ar","arg":"an","hye":"hy","asm":"as","ava":"av","ave":"ae","aym":"ay","aze":"az","bam":"bm","bak":"ba","eus":"eu","bel":"be","ben":"bn","bih":"bh","bis":"bi","bos":"bs","bre":"br","bul":"bg","mya":"my","cat":"ca","cha":"ch","che":"ce","nya":"ny","zho":"zh","chv":"cv","cor":"kw","cos":"co","cre":"cr","hrv":"hr","ces":"cs","dan":"da","div":"dv","nld":"nl","dzo":"dz","eng":"en","epo":"eo","est":"et","ewe":"ee","fao":"fo","fij":"fj","fin":"fi","fra":"fr","ful":"ff","glg":"gl","kat":"ka","deu":"de","ell":"el","grn":"gn","guj":"gu","hat":"ht","hau":"ha","heb":"he","her":"hz","hin":"hi","hmo":"ho","hun":"hu","ina":"ia","ind":"id","ile":"ie","gle":"ga","ibo":"ig","ipk":"ik","ido":"io","isl":"is","ita":"it","iku":"iu","jpn":"ja","jav":"jv","kal":"kl","kan":"kn","kau":"kr","kas":"ks","kaz":"kk","khm":"km","kik":"ki","kin":"rw","kir":"ky","kom":"kv","kon":"kg","kor":"ko","kur":"ku","kua":"kj","lat":"la","ltz":"lb","lug":"lg","lim":"li","lin":"ln","lao":"lo","lit":"lt","lub":"lu","lav":"lv","glv":"gv","mkd":"mk","mlg":"mg","msa":"ms","mal":"ml","mlt":"mt","mri":"mi","mar":"mr","mah":"mh","mon":"mn","nau":"na","nav":"nv","nob":"nb","nde":"nd","nep":"ne","ndo":"ng","nno":"nn","nor":"no","iii":"ii","nbl":"nr","oci":"oc","oji":"oj","chu":"cu","orm":"om","ori":"or","oss":"os","pan":"pa","pli":"pi","fas":"fa","pol":"pl","pus":"ps","por":"pt","que":"qu","roh":"rm","run":"rn","ron":"ro","rus":"ru","san":"sa","srd":"sc","snd":"sd","sme":"se","smo":"sm","sag":"sg","srp":"sr","gla":"gd","sna":"sn","sin":"si","slk":"sk","slv":"sl","som":"so","sot":"st","azb":"az","spa":"es","sun":"su","swa":"sw","ssw":"ss","swe":"sv","tam":"ta","tel":"te","tgk":"tg","tha":"th","tir":"ti","bod":"bo","tuk":"tk","tgl":"tl","tsn":"tn","ton":"to","tur":"tr","tso":"ts","tat":"tt","twi":"tw","tah":"ty","uig":"ug","ukr":"uk","urd":"ur","uzb":"uz","ven":"ve","vie":"vi","vol":"vo","wln":"wa","cym":"cy","wol":"wo","fry":"fy","xho":"xh","yid":"yi","yor":"yo","zha":"za","zul":"zu"}
    if locale in iso639Codes:
        locale = iso639Codes[locale]
        
    convertedLanguages = []
    for language in languages:
        convertedLanguages.append(iso639Codes[language] if language in iso639Codes else language)
        
    output = {}
    if os.path.exists(dbPath):
        conn = sqlite3.connect(dbPath)
        c = conn.cursor()
        languageResults = c.execute('select * from languageNames where lg=?', (locale, )).fetchall()
        if languages:
            for languageResult in languageResults:
                try:
                    loc = convertedLanguages.index(languageResult[2])
                    output[languages[loc]] = languageResult[3]
                    del languages[languages.index(languageResult[2])]
                except ValueError:
                    pass
        else:
            for languageResult in languageResults:
                output[languageResult[2]] = languageResult[3]
    return output

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    pass

class MyHandler(http.server.SimpleHTTPRequestHandler):

    pairs = {}
    analyzers = {}
    generators = {}
    pipelines = {}

    # The lock is needed so we don't let two threads write
    # simultaneously to a pipeline; then the first thread to read
    # might read translations of text put there by the second
    # thread …
    translock = threading.RLock()
    # TODO: one lock per pipeline, if the es-ca pipeline is free,
    # we don't need to wait just because mk-en is currently
    # translating. In that case, should also make hardbreak()
    # pipeline dependent.

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
            
    def morphAnalysis(self, toAnalyze, dir, mode):
        p1 = Popen(["echo", toAnalyze], stdout=PIPE)
        p2 = Popen(["apertium", "-d %s" % dir, mode], stdin=p1.stdout, stdout=PIPE)
        p1.stdout.close()
        output = p2.communicate()[0].decode('utf-8')
        return output
        
    def morphGeneration(self, toGenerate, dir, mode):
        p1 = Popen(["echo", toGenerate], stdout=PIPE)
        p2 = Popen(["apertium", "-f none -d %s" % dir, mode], stdin=p1.stdout, stdout=PIPE)
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

    def sendResponse(self, status, data, callback=None):
        outData = json.dumps(data)

        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        if callback==None:
            self.wfile.write(outData.encode('utf-8'))
        else:
            returner = callback+"("+outData+")"
            self.wfile.write(returner.encode('utf-8'))

        #self.send_response(403)


    def handleListPairs(self, data):
        if "callback" in data:
            callback = data["callback"][0]
        else:
            callback = None
        responseData = []
        for pair in self.pairs:
            (l1, l2) = pair.split('-')
            responseData.append({"sourceLanguage": l1, "targetLanguage": l2})
        status = 200

        toReturn = {"responseData": responseData,
            "responseDetails": None,
            "responseStatus": status}

        self.sendResponse(status, toReturn, callback)

    def handleListAnalyzers(self, data):
        if "callback" in data:
            callback = data["callback"][0]
        else:
            callback = None
            
        self.sendResponse(200, self.analyzers, callback)
        
    def handleListGenerators(self, data):
        if "callback" in data:
            callback = data["callback"][0]
        else:
            callback = None
            
        self.sendResponse(200, self.generators, callback)

    def handleTranslate(self, data):
        pair = data["langpair"][0]
        if "callback" in data:
            callback = data["callback"][0]
        else:
            callback = None
        (l1, l2) = pair.split('|')
        if "q" in data:
            toTranslate = data["q"][0]
            #print(toTranslate, l1, l2)

            translated = self.translate(toTranslate, (l1, l2))
            if translated:
                status = 200
            else:
                status = 404
                print("nothing returned")
        else:
            status = 404
            print("no query")
            #print(data)
            translated = False

        toReturn = {"responseData":
            {"translatedText": translated},
            "responseDetails": None,
            "responseStatus": status}

        self.sendResponse(status, toReturn, callback)
        
    def handleAnalyze(self, data):
        if "callback" in data:
            callback = data["callback"][0]
        else:
            callback = None
            
        mode = data["mode"][0]
        toAnalyze = data["q"][0]
        if mode in self.analyzers:
            status = 200
            analysis = self.morphAnalysis(toAnalyze, self.analyzers[mode][0], self.analyzers[mode][1])
            lexicalUnits = re.findall(r'\^([^\$]*)\$([^\^]*)', analysis)
            toReturn = [(lexicalUnit[0], lexicalUnit[0].split('/')[0] + lexicalUnit[1]) for lexicalUnit in lexicalUnits]
        else:
            status = 400
            print('analyzer mode not found')
            toReturn = 'analyzer mode not found'
        self.sendResponse(status, toReturn, callback)
    
    def handleGenerate(self, data):
        if "callback" in data:
            callback = data["callback"][0]
        else:
            callback = None
        
        mode = data["mode"][0]
        toGenerate = data["q"][0]
        if mode in self.generators:
            status = 200
            lexicalUnits = re.findall(r'(\^[^\$]*\$[^\^]*)', toGenerate)
            if len(lexicalUnits) == 0:
                lexicalUnits = ['^%s$' % toGenerate]
            generated = self.morphGeneration('[SEP]'.join(lexicalUnits), self.generators[mode][0], self.generators[mode][1])
            toReturn = [(generation, lexicalUnits[index]) for (index, generation) in enumerate(generated.split('[SEP]'))]
        else:
            status = 400
            print('generator mode not found')
            toReturn = 'generator mode not found'
        self.sendResponse(status, toReturn, callback)
        
    def handleListLanguageNames(self, data, headers):
        if "callback" in data:
            callback = data["callback"][0]
        else:
            callback = None
        
        if self.languageNamesDBPath:
            if 'locale' in data:
                if 'languages' in data:
                    self.sendResponse(200, getLocalizedLanguages(data['locale'][0], self.languageNamesDBPath, languages = data['languages'][0].split(' ')), callback)
                else:
                    self.sendResponse(200, getLocalizedLanguages(data['locale'][0], self.languageNamesDBPath), callback)
            elif 'Accept-Language' in headers:
                locales = [locale.split(';')[0] for locale in headers['Accept-Language'].split(',')]
                print(locales)
                for locale in locales:
                    languageNames = getLocalizedLanguages(locale, self.languageNamesDBPath)
                    if languageNames:
                        self.sendResponse(200, languageNames, callback)
                        return
                self.sendResponse(200, getLocalizedLanguages('en', self.languageNamesDBPath), callback)
            else:
                self.sendResponse(200, getLocalizedLanguages('en', self.languageNamesDBPath), callback)
        else:
            self.sendResponse(200, {}, callback)
    
    def routeAction(self, path, data, headers):
        print(path)
        if path=="/listPairs":
            self.handleListPairs(data)
        if path=="/listAnalyzers" or path=="/listAnalysers":
            self.handleListAnalyzers(data)
        if path=="/listGenerators":
            self.handleListGenerators(data)
        elif path=="/translate":
            self.handleTranslate(data)
        elif path=="/analyze" or path=="/analyse":
            self.handleAnalyze(data)
        elif path=="/generate":
            self.handleGenerate(data)
        elif path=="/listLanguageNames":
            self.handleListLanguageNames(data, headers)

    def do_GET(self):
        params_parsed = urllib.parse.urlparse(self.path)
        query_parsed = urllib.parse.parse_qs(params_parsed.query)
        self.routeAction(params_parsed.path, query_parsed, self.headers)


    def do_POST(self):
        cur_thread = threading.current_thread()
        print("{}".format(cur_thread.name))
        length = int(self.headers['Content-Length'])
        indata = self.rfile.read(length)
        query_parsed = urllib.parse.parse_qs(indata.decode('utf-8'))
        params_parsed = urllib.parse.urlparse(self.path)
        self.routeAction(params_parsed.path, query_parsed)

def setup_server(port, pairsPath, languageNamesDBPath, sslPath):
    global Handler, httpd
    Handler = MyHandler
    Handler.languageNamesDBPath = languageNamesDBPath

    rawPairs, rawAnalyzers, rawGenerators = searchPath(pairsPath)
    for pair in rawPairs:
        (f, l1, l2) = pair
        Handler.pairs["%s-%s" % (l1, l2)] = f
    for analyzer in rawAnalyzers:
        Handler.analyzers[analyzer[2]] = (analyzer[0], analyzer[1])
    for generator in rawGenerators:
        Handler.generators[generator[2]] = (generator[0], generator[1])

    socketserver.TCPServer.allow_reuse_address = True
    # is useful when debugging, possibly risky: http://thread.gmane.org/gmane.comp.python.general/509706

    httpd = ThreadedTCPServer(("", port), Handler)
    if sslPath:
        httpd.socket = ssl.wrap_socket(httpd.socket, certfile=sslPath, server_side=True)
    print("Server is up and running on port %s" % port)
    try:
        httpd.serve_forever()
    except TypeError:
        httpd.shutdown()
    except KeyboardInterrupt:
        httpd.shutdown()
    except NameError:
        httpd.shutdown()

if __name__ == '__main__':
   parser = argparse.ArgumentParser(description='Start Apertium APY')
   parser.add_argument('pairsPath', help='path to Apertium trunk')
   parser.add_argument('-langNamesDB', '--languageNamesDBPath', help='path to localized language names sqlite database', default='')
   parser.add_argument('-p', '--port', help='port to run server on', type=int, default=2737)
   parser.add_argument('--ssl', help='path to SSL Certificate', default=False)
   args = parser.parse_args()
   setup_server(args.port, args.pairsPath, args.languageNamesDBPath, args.ssl)
