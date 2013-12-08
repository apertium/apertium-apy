#!/usr/bin/env python3
# -*- indent-tabs-mode: t -*-

import sys, threading, os, re, ssl, argparse
import http.server, socketserver, urllib.parse, json
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

    def routeAction(self, path, data):
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

    def do_GET(self):
        params_parsed = urllib.parse.urlparse(self.path)
        query_parsed = urllib.parse.parse_qs(params_parsed.query)
        self.routeAction(params_parsed.path, query_parsed)


    def do_POST(self):
        cur_thread = threading.current_thread()
        print("{}".format(cur_thread.name))
        length = int(self.headers['Content-Length'])
        indata = self.rfile.read(length)
        query_parsed = urllib.parse.parse_qs(indata.decode('utf-8'))
        params_parsed = urllib.parse.urlparse(self.path)
        self.routeAction(params_parsed.path, query_parsed)


def setup_server(port, pairsPath, sslPath):
    global Handler, httpd
    Handler = MyHandler

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
   parser.add_argument('-p', '--port', help='port to run server on', type=int, default=2737)
   parser.add_argument('--ssl', help='path to SSL Certificate', default=False)
   args = parser.parse_args()
   setup_server(args.port, args.pairsPath, args.ssl)
