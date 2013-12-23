#!/usr/bin/env python3

import argparse, logging, sys, json, itertools, functools, random, socket
from collections import OrderedDict
import tornado, tornado.httpserver, tornado.web, tornado.httpclient
from tornado.web import RequestHandler
try: #3.1
    from tornado.log import enable_pretty_logging
except ImportError: #2.1
    from tornado.options import enable_pretty_logging
    
global verifySSLCert

class requestHandler(RequestHandler):
    def initialize(self, balancer):
        self.balancer = balancer
    
    @tornado.web.asynchronous
    def get(self):
        path = self.request.path
        query = self.request.query
        server, port = self.balancer.get_server()
        server_port = '%s:%s' % (server, port)
        logging.info('Redirecting %s?%s to %s%s?%s' % (path, query, server_port, path, query))
        
        http = tornado.httpclient.AsyncHTTPClient()
        http.fetch(server_port + path + "?" + query, functools.partial(self._on_download, (server, port)), validate_cert = verifySSLCert)
        self.balancer.inform('start', (server, port))
        
    def _on_download(self, server, response):
        self.balancer.inform('complete', server)
        for (hname, hvalue) in response.headers.get_all():
            self.set_header(hname, hvalue)
        self.set_status(response.code)
        self.write(response.body)
        self.finish()
    
    @tornado.web.asynchronous
    def post(self):
        self.get()

class Balancer(object):
    def __init__(self, servers):
        self.serverlist = servers
        
    def get_server(self):
        raise NotImplementedError
        
    def inform(self, action, server):
        pass
        
class Random(Balancer):
    def get_server(self):
        return random.choice(self.serverlist)
        
class RoundRobin(Balancer):
    '''Contains the list of the server / ports and keeps track
    of which was last used and which should be used next.'''
    def __init__(self, servers):
        super(RoundRobin, self).__init__(servers)
        self.generator = itertools.cycle(self.serverlist)
    
    def get_server(self):
        return next(self.generator)
        
class LeastConnections(Balancer):
    def __init__(self, servers):
        self.serverlist = OrderedDict([(server, 0) for server in servers])
    
    def get_server(self):
        return list(self.serverlist.items())[0][0]
        
    def inform(self, action, server):
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
        print(self.serverlist)
    
    def get_server(self):
        servers = list(filter(lambda x: not x[1] == float('inf'), list(self.serverlist.items())))
        total = sum(weight for (server, weight) in servers)
        print(list(servers))
        r = random.uniform(0, total)
        currentPos = 0
        for (server, weight) in servers:
            if currentPos + weight >= r:
                return server
            currentPos += weight
        assert False, 'failed to get server'
        
    def inform(self, action, server):
        pass
        #raise NotImplementedError
        
    def updateWeights(self):
        pass
        #raise NotImplementedError
        
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
            requestURL = '%s:%s%s' % (domain, port, testPath)
            try:
                result = http.fetch(requestURL, request_timeout = 15, validate_cert = verifySSLCert)
                handleResult(result, (testPath, testFn), (domain, port))
            except:
                handleResult(None, (testPath, testFn), (domain, port))
                
    return testResults

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Start Apertium APY Gateway")
    parser.add_argument('serverlist', help="path to file with list of servers and ports available")
    parser.add_argument('-t', '--tests', help="perform tests on server pool", action='store_true', default=False)
    parser.add_argument('-p', '--port', help="port to run gateway on (default = 2738)", type=int, default=2738)
    parser.add_argument('-c', '--ssl-cert', help='path to SSL Certificate', default=None)
    parser.add_argument('-k', '--ssl-key', help='path to SSL Key File', default=None)
    parser.add_argument('-d', '--debug', help='debug mode (do not verify SSL certs)', action='store_false', default=True)
    parser.add_argument('-j', '--num-processes', help='number of processes to run (default = number of cores)', type=int, default=0)
    parser.add_argument('-i', '--test-interval', help="interval to perform tests in ms (default = 100000)", type=int, default=100000)
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
      
    balancer = RoundRobin(server_port_list)
    #balancer = LeastConnections(server_port_list)
    #balancer = WeightedRandom(server_port_list)
    logging.info("Server/port list used: " + str(server_port_list))
    
    application = tornado.web.Application([
        (r'/.*', requestHandler, {"balancer": balancer})
    ])
    
    #find an open socket
    result = 0
    while result == 0:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', args.port))
        if result == 0:
            logging.info("port %d already in use, trying next" % args.port)
            args.port += 1
        sock.close()
    
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
    if isinstance(balancer, WeightedRandom):
        tornado.ioloop.PeriodicCallback(lambda: balancer.updateWeights(), args.test_interval, io_loop = main_loop).start()
    main_loop.start()
    
