#!/usr/bin/env python3

import argparse, logging, sys, json, itertools, functools, random, socket, servlet, pprint
from collections import OrderedDict, defaultdict
import tornado, tornado.httpserver, tornado.web, tornado.httpclient
from tornado.web import RequestHandler
try: #3.1
    from tornado.log import enable_pretty_logging
except ImportError: #2.1
    from tornado.options import enable_pretty_logging
    
global verifySSLCert

def genServerName(server, port):
    if len(server.split('/')) > 3: #true if there's a separate "path" element
        server = server.rsplit('/', 1)
        server_port = '%s:%s/%s' %(server[0],port, server[1])
    else:
        server_port = '%s:%s' % (server, port)
    return server_port

class requestHandler(RequestHandler):
    '''Handler for non-list requests -- all requests that must be redirected.'''
    def initialize(self, balancer):
        self.balancer = balancer
    
    @tornado.web.asynchronous
    def get(self):
        path = self.request.path
        mode, langPair, perWordModes = [None] * 3
        pathToMode = defaultdict(lambda: None, 
            {'/translate': 'pairs', '/analyze': 'analyzers',
             '/analyse': 'analyzers', '/generate': 'generators',
             '/perWord': 'perWord', '/coverage': 'coverage',
             '/listLanguageNames': 'languageNames', '/identifyLang': 'identifyLang',
             '/getLocale': 'getLocale'
        })
        mode = pathToMode[path]

        if path == '/translate':
            langPair = self.get_argument('langpair')
            langPair = langPair.replace('|', '-') #langpair=lang|pair only in /translate
        elif path == '/analyze' or path == '/analyse':
            langPair = self.get_argument('mode')
        elif path == '/generate':
            langPair = self.get_argument('mode')
        elif path == '/perWord':
            langPair = self.get_argument('lang')
            perWordModes = self.get_argument('modes').split()
        elif path == '/coverage':
            langPair = self.get_argument('mode')

        if not mode:
            return self.send_error(400)

        query = self.request.query
        headers = self.request.headers
        
        serverTuple = self.balancer.get_server(langPair, mode, perWordModes=perWordModes)
        if serverTuple:
            server, port = serverTuple
        else:
            logging.warning('No server available for request: %s' % self.request.uri)
            return self.send_error(400)
        server_port = genServerName(server, port)
        logging.info('Redirecting %s?%s to %s%s?%s' % (path, query, server_port, path, query))
        
        http = tornado.httpclient.AsyncHTTPClient()
        http.fetch(server_port + path + "?" + query, functools.partial(self._on_download, (server, port), langPair), validate_cert=verifySSLCert, headers=headers)
        self.balancer.inform('start', (server, port), url=path)
        
    def _on_download(self, server, langPair, response):
        responseBody = response.body
        if response.error is not None and response.error.code == 599:
            self.balancer.inform('drop', server, response=response, lang=langPair)
            logging.info('Request failed with code %d, trying next server after %s' % (response.error.code, str(server)))
            return self.get()
        if response.error is None:
            self.balancer.inform('complete', server, response=response, lang=langPair)
            self.write(responseBody)
        else:
            self.set_status(response.code)
        for (hname, hvalue) in response.headers.get_all():
            self.set_header(hname, hvalue)
        self.finish()
    
    @tornado.web.asynchronous
    def post(self):
        self.get()

class listRequestHandler(servlet.BaseHandler):
    '''Handler for list requests. Takes a language-pair-server map and aggregates the language-pairs of all of the servers.'''
    def initialize(self, serverLangPairMap):
        self.serverLangPairMap = serverLangPairMap
        callbacks = self.get_arguments('callback')
        if callbacks:
            self.callback = callbacks[0]
    
    @tornado.web.asynchronous
    def get(self):
        logging.info("Overriding list call: %s %s" %(self.request.path, self.get_arguments('q')))
        if self.request.path != '/listPairs' and self.request.path != '/list':
            self.send_error(400)
        else:
            query = self.get_arguments('q')
            if query:
                query = query[0]
            if self.request.path == '/listPairs' or query == 'pairs':
                logging.info("Responding to request for pairs")
                responseData = []
                for pair in self.serverLangPairMap['pairs']:
                    (l1, l2) = pair
                    responseData.append({'sourceLanguage': l1, 'targetLanguage': l2})
                self.sendResponse({'responseData': responseData, 'responseDetails': None, 'responseStatus': 200})
            elif query == 'analyzers' or query == 'analysers':
                self.sendResponse({pair: self.serverLangPairMap['analyzers'][pair][0] for pair in self.serverLangPairMap['analyzers']})
            elif query == 'generators':
                self.sendResponse({pair: self.serverLangPairMap['generators'][pair][0] for pair in self.serverLangPairMap['generators']})
            elif query == 'taggers' or query == 'disambiguators':
                self.sendResponse({pair: self.serverLangPairMap['taggers'][pair][0] for pair in self.serverLangPairMap['taggers']})
            else:
                self.send_error(400)

class Balancer(object):
    def __init__(self, servers):
        self.serverlist = servers
        
    def get_server(self):
        raise NotImplementedError
        
    def inform(self, action, server, *args, **kwargs):
        pass
        
class Random(Balancer):
    def get_server(self):
        return random.choice(self.serverlist)
        
class RoundRobin(Balancer):
    '''Contains the list of the server / ports / their capabilities
        and cycles between the available/possible ones.'''
    def __init__(self, servers, langpairmap):
        super(RoundRobin, self).__init__(servers)
        self.langpairmap = langpairmap
        self.generator = itertools.cycle(self.serverlist)
    
    def get_server(self, langPair, mode = "pairs", *args, **kwargs):
        #when we get a /perWord request, we have multiple modes, all of which have to be on the server
        #the modes will not be "pairs"
        if 'perWordModes' in kwargs and kwargs['perWordModes'] is not None:
            perWordModes = {'morph': 'analyzers', 'biltrans': 'analyzers', 'tagger': 'taggers', 'translate': 'taggers'}
            modes = set(map(lambda _: perWordModes[_], kwargs['perWordModes']))
            logging.info("Handling a /perWord request with modes %s for langpair %s" %(modes, langPair))
            def isIn(modes, server):
                for mode in modes:
                    if langPair not in self.langpairmap[mode] or server not in self.langpairmap[mode][langPair][1]:
                        return False
                else:
                    return True
            if not any(isIn(modes, server) for server in self.serverlist):
                logging.error("Language pair %s not found for modes %s" %(langPair, modes))
                return next(self.generator)
            else:
                server = next(self.generator)
                while not isIn(modes, server):
                    server = next(self.generator)
                return server
        #for everything that isn't a /perWord call
        if langPair is not None and mode == "pairs": #for mode "pairs", the key is ('lang', 'pair') rather than 'lang-pair'
            langPair = tuple(langPair.split('-'))
        if langPair is None or not langPair in self.langpairmap[mode]:
            logging.error("Language pair %s for mode %s not found" %(langPair, mode))
            return next(self.generator)
        server = next(self.generator)
        if mode == "pairs":
            serverlist = self.langpairmap[mode][langPair]
        else:
            serverlist = self.langpairmap[mode][langPair][1]
        while server not in serverlist:
            server = next(self.generator)
        return server
        
    def inform(self, action, server, *args, **kwargs):
        if action == 'drop':
            serverlist = [x for x in self.serverlist if x != server]
            if not len(self.serverlist):
                logging.critical('Empty serverlist')
                sys.exit(-1)
            self.generator = itertools.cycle(self.serverlist)
        
class LeastConnections(Balancer):
    def __init__(self, servers):
        self.serverlist = OrderedDict([(server, 0) for server in servers])
    
    def get_server(self, *args, **kwargs):
        return list(self.serverlist.items())[0][0]
        
    def inform(self, action, server, *args, **kwargs):
        actions = {'start': 1, 'complete': -1}
        if not action in actions:
            raise ValueError('invalid argument action: %s' % action)
        else:
            self.serverlist[server] += actions[action]
            self.serverlist = OrderedDict(sorted(self.serverlist.items(), key = lambda x: x[1]))
            
class WeightedRandom(Balancer):
    def __init__(self, servers):
        self.serverlist = OrderedDict([(server, 0) for server in servers])
        allTestResults = [testServerPool([server[0] for server in self.serverlist.items()]) for _ in range(0, 5)]
        
        for testResults in allTestResults:
            for testResult in testResults.items():
                server = testResult[0]
                results = testResult[1]
                testScore = sum([result[1] for testPath, result in results.items()])
                self.serverlist[server] += testScore / 5
        self.serverlist = OrderedDict(sorted(self.serverlist.items(), key = lambda x: x[1]))
    
    def get_server(self, *args, **kwargs):
        servers = list(filter(lambda x: not x[1] == float('inf'), list(self.serverlist.items())))
        total = sum(weight for (server, weight) in servers)
        r = random.uniform(0, total)
        currentPos = 0
        for (server, weight) in servers:
            if currentPos + weight >= r:
                return server
            currentPos += weight
        assert False, 'failed to get server'
        
    def inform(self, action, server, *args, **kwargs):
        raise NotImplementedError
        
    def updateWeights(self):
        raise NotImplementedError
        
class Fastest(Balancer):
    def __init__(self, servers, serverCapabilities, numResponses):
        self.servers = servers
        self.originalServers = servers
        self.serverCycle = itertools.cycle(self.servers)
        self.numResponses = numResponses
        self.initServerList(serverCapabilities=serverCapabilities)
    
    def get_server(self, langPair, mode, *args, **kwargs):
        if len(self.serverlist):
            modeToURL = {'pairs': 'translate', 'generators': 'generate', 'analyzers': 'analyze', 'taggers': 'tag', 'coverage': 'analyze'}
            if mode in modeToURL:
                if (modeToURL[mode], langPair) in self.serverlist:
                    possibleServers = list(self.serverlist[(modeToURL[mode], langPair)])
                    if len(possibleServers):
                        return possibleServers[0]
            elif mode == 'languageNames' or mode == 'identifyLang' or mode == 'getLocale':
                return next(self.serverCycle)
            elif mode == 'perWord':
                modes = kwargs['perWordModes']
                possibleServers = set()
                if ('morph' in modes or 'biltrans' in modes) and ('analyze', langPair) in self.serverlist:
                        possibleServers.update(self.serverlist[('analyze', langPair)])
                elif ('tagger' in modes or 'disambig' in modes or 'translate' in modes) and ('tag', langPair) in self.serverlist:
                    if possibleServers:
                        possibleServers &= self.serverlist[('tag', langPair)]
                    else:
                        possibleServers.update(self.serverlist[('tag', langPair)])
                if len(possibleServers):
                    return list(possibleServers)[0]
        else:
            logging.critical('Empty serverlist')
            sys.exit(-1)
    
    def inform(self, action, server, *args, **kwargs):
        actions = {'start', 'complete', 'drop'}
        if not action in actions:
            raise ValueError('invalid argument action: %s' % action)
        elif action == 'start':
            return
        elif action == 'complete' or action == 'drop':
            response = kwargs['response']
            url = response.request.url
            requestTime = response.request_time
            if response.body:
                responseLen = len(response.body)
            path = url.rsplit('/', 1)[1] if not '?' in url else url.rsplit('/', 1)[1].split('?')[0]
            mode = (path, kwargs['lang'])
            
            if mode in self.serverlist:
                if action == 'complete':
                    if self.serverlist[mode][server]:
                        self.serverlist[mode][server] = (self.serverlist[mode][server] * (self.numResponses - 1) + requestTime/responseLen) / self.numResponses
                    else:
                        self.serverlist[mode][server] = requestTime/responseLen / self.numResponses
                elif action == 'drop':
                    logging.error('Dropping server: %s', repr(server))
                    self.servers.remove(server)
                    self.serverCycle = itertools.cycle(self.servers)
                    del self.serverlist[mode][server]
            
                pprint.pprint(self.serverlist[mode])
                self.serverlist[mode] = OrderedDict(sorted(self.serverlist[mode].items(), key=lambda x: x[1]))
                
    def initServerList(self, serverCapabilities=None):
        if serverCapabilities == None:
            serverCapabilities = determineServerCapabilities(self.originalServers)
        self.serverlist = {}
        
        modeToURL = {'pairs': 'translate', 'generators': 'generate', 'analyzers': 'analyze', 'taggers': 'tag'}
        for lang, servers in serverCapabilities['pairs'].items():
            self.serverlist[(modeToURL['pairs'], '%s-%s' % lang)] = OrderedDict([(server, 0) for server in servers])
        
        for mode, capabiltities in serverCapabilities.items():
            if mode != 'pairs':
                for lang, servers in serverCapabilities[mode].items():
                    self.serverlist[(modeToURL[mode], lang)] = OrderedDict([(server, 0) for server in servers[1]])
                    
        pprint.pprint(self.serverlist)
    
    def initWeights(self):
        self.serverlist = OrderedDict([(server, [0, {}]) for server in self.servers])
        allTestResults = [testServerPool([server[0] for server in self.serverlist.items()]) for _ in range(0, self.numResponses)]
        for testResults in allTestResults:
            for testResult in testResults.items():
                server = testResult[0]
                results = testResult[1]
                testSum = sum([result[1] for testPath, result in results.items()])
                if not '/list' in self.serverlist[server][1]:
                    self.serverlist[server][1]['list'] = 0
                self.serverlist[server][1]['list'] += testSum / (self.numResponses * len(results.items()))
        self.calcAggregateScores()
        self.serverlist = OrderedDict(filter(lambda x: x[1][0] != float('inf'), self.serverlist.items()))
        self.sortServerList()
        
def testServerPool(serverList):
    tests = {
        '/list?q=pairs': lambda x: isinstance(x, dict)
                        and set(x.keys()) == {'responseStatus', 'responseData', 'responseDetails'}
                        and isinstance(x['responseStatus'], int)
                        and isinstance(x['responseData'], list)
                        and all([isinstance(langPair, dict) for langPair in x['responseData']])
                        and all([set(langPair.keys()) == {'sourceLanguage', 'targetLanguage'} for langPair in x['responseData']])
                        and all([all(map(lambda y: isinstance(y, str), langPair.values())) for langPair in x['responseData']]),
        '/list?q=analyzers': lambda x: isinstance(x, dict) and all(map(lambda y: isinstance(y, str), list(x.keys()) + list(x.values()))),
        '/list?q=taggers': lambda x: isinstance(x, dict) and all(map(lambda y: isinstance(y, str), list(x.keys()) + list(x.values()))),
        '/list?q=generators': lambda x: isinstance(x, dict) and all(map(lambda y: isinstance(y, str), list(x.keys()) + list(x.values())))
    }
    testResults = {server: {} for server in serverList}
    http = tornado.httpclient.HTTPClient()
    
    def handleResult(result, test, server):
        testPath, testFn = test
        if not result:
            testResults[server][testPath] = (False, float('inf'))
        elif not result.code == 200:
            testResults[server][testPath] = (result.code, float('inf'))
        else:
            try:
                if testFn(json.loads(result.body.decode('utf-8'))):
                    testResults[server][testPath] = (True, result.request_time)
                else:
                    testResults[server][testPath] = (False, float('inf'))
            except ValueError: #Not valid JSON
                testResults[server][testPath] = (False, float('inf'))
    
    for (domain, port) in serverList:
        for (testPath, testFn) in tests.items():
            requestURL = '%s%s' % (genServerName(domain, port), testPath)
            try:
                result = http.fetch(requestURL, request_timeout = 15, validate_cert = verifySSLCert)
                handleResult(result, (testPath, testFn), (domain, port))
            except:
                handleResult(None, (testPath, testFn), (domain, port))
                
    return testResults

def determineServerCapabilities(serverlist):
    '''Find which APYs can do what.
    
    The return data from this function is a little complex, better illustrated than described:
    capabilities = {
        "pairs": { #note that pairs is a special mode compared to taggers/generators/analyzers
            ("lang", "pair"): [(server1, port1), (server2, port2)]
            }
        "taggers|generators|analyzers": {
            "lang-pair": ("lang-pair-moreinfo", [(server1, port1), (server2, port2)])
            #"moreinfo" tends to be "anmor" or "generador" or "tagger"
            }
         }
            '''
    # TODO: scaleMT doesn't support /list?q=mode calls. Find a way to figure out which language-pairs each mode supports
    # on scaleMT survers.
    # You will probably need to batch-translate or batch-analyze with the language pairs from /listPairs and
    # look at the return codes in order to do this.
    http = tornado.httpclient.HTTPClient()
    modes = ("pairs", "taggers", "generators", "analyzers")
    capabilities = {}
    for (domain, port) in serverlist:
        server = (domain, port)
        for mode in modes:
            if mode not in capabilities:
                capabilities[mode] = {}
            if mode == "pairs": # for compatibility with scaleMT, we request /listPairs
                requestURL = "%s/listPairs" %genServerName(domain, port)
            else:
                requestURL = "%s/list?q=%s" % (genServerName(domain, port), mode)
            logging.info("Getting information from %s" %requestURL)
            # make the request
            try:
                result = http.fetch(requestURL, request_timeout = 15, validate_cert = verifySSLCert)
            except:
                logging.error("Fetch for data from %s for %s failed, dropping server" %(genServerName(domain, port), mode))
                continue
            #parse the return
            try:
                response = json.loads(result.body.decode('utf-8'))
            except ValueError: #Not valid JSON, we stop using the server
                logging.error("Received invalid JSON from %s on query for %s, dropping server" %(genServerName(domain, port), mode))
                continue
            if mode == "pairs": #pairs has a slightly different response format
                if "responseStatus" not in response or response["responseStatus"] != 200 or "responseData" not in response:
                    logging.error("JSON return format unexpected from %s:%s on query for %s, dropping server"%(domain, port, mode))
                    continue
                for lang_pair in response['responseData']:
                    lang_pair_tuple = (lang_pair["sourceLanguage"], lang_pair["targetLanguage"])
                    if lang_pair_tuple in capabilities[mode]:
                        capabilities[mode][lang_pair_tuple].append(server)
                    else:
                        capabilities[mode][lang_pair_tuple] = [server]
            else:
                for lang_pair in response:
                    if lang_pair in capabilities[mode]:
                        capabilities[mode][lang_pair][1].append(server)
                    else:
                        capabilities[mode][lang_pair] = (response[lang_pair], [server])
    return capabilities
                
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Start Apertium APY Gateway")
    parser.add_argument('serverlist', help="path to file with list of servers and ports available")
    parser.add_argument('-t', '--tests', help="perform tests on server pool", action='store_true', default=False)
    parser.add_argument('-p', '--port', help="port to run gateway on (default = 2738)", type=int, default=2738)
    parser.add_argument('-c', '--ssl-cert', help='path to SSL Certificate', default=None)
    parser.add_argument('-k', '--ssl-key', help='path to SSL Key File', default=None)
    parser.add_argument('-d', '--debug', help='debug mode (do not verify SSL certs)', action='store_false', default=True)
    parser.add_argument('-j', '--num-processes', help='number of processes to run (default = number of cores)', type=int, default=0)
    parser.add_argument('-i', '--test-interval', help="interval to perform tests in ms (default = 3600000)", type=int, default=3600000)
    args = parser.parse_args()
    
    global verifySSLCert
    verifySSLCert = args.debug
    
    logging.getLogger().setLevel(logging.INFO)
    enable_pretty_logging()
    
    # read the serverlist file
    try:
        with open(args.serverlist) as serverlist:
            server_port_list = []
            for serverPortPair in serverlist:
                if serverPortPair[0] != '#': #filter out the commented lines
                    srv, port = serverPortPair.rsplit(':', 1)
                    server_port_list.append((srv, int(port)))
    except IOError:
        logging.critical("Could not open serverlist: %s" % args.serverlist)
        sys.exit(-1)

    if len(server_port_list) == 0:
        logging.critical('Serverlist must not be empty')
        sys.exit(-1)  
    
    #find an open socket
    result = 0
    while result == 0:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', args.port))
        if result == 0:
            logging.info('Port %d already in use, trying next' % args.port)
            args.port += 1
        sock.close()

    logging.info("Server/port list used: " + str(server_port_list))    
    server_lang_pair_map = determineServerCapabilities(server_port_list)
    logging.info("Using server language-pair mapping: %s" % str(server_lang_pair_map))
    #balancer = RoundRobin(server_port_list, server_lang_pair_map)
    #balancer = LeastConnections(server_port_list)
    #balancer = WeightedRandom(server_port_list)
    balancer = Fastest(server_port_list, server_lang_pair_map, 5)   
    
    application = tornado.web.Application([
        (r'/list', listRequestHandler, {"serverLangPairMap": server_lang_pair_map}),
        (r'/listPairs', listRequestHandler, {"serverLangPairMap": server_lang_pair_map}),
        (r'/.*', requestHandler, {"balancer": balancer}),
    ])
    
    if args.ssl_cert and args.ssl_key:
        http_server = tornado.httpserver.HTTPServer(application, ssl_options = {
            'certfile': args.ssl_cert,
            'keyfile': args.ssl_key,
        })
        logging.info('Gateway-ing at https://localhost:%s' % args.port)
    else:
        http_server = tornado.httpserver.HTTPServer(application)
        logging.info('Gateway-ing at http://localhost:%s' % args.port)
    
    http_server.bind(args.port)
    http_server.start(args.num_processes)
    main_loop = tornado.ioloop.IOLoop.instance()
    if isinstance(balancer, Fastest):
        tornado.ioloop.PeriodicCallback(lambda: balancer.initServerList(), args.test_interval, io_loop = main_loop).start()
    main_loop.start()
    
