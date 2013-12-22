#!/usr/bin/env python3

import argparse, logging, sys, json
import tornado, tornado.httpserver, tornado.web, tornado.httpclient
from tornado.web import RequestHandler
try: #3.1
    from tornado.log import enable_pretty_logging
except ImportError: #2.1
    from tornado.options import enable_pretty_logging

class roundRobinHandler(RequestHandler):
    def initialize(self, roundRobin):
        self.roundRobin = roundRobin
    
    @tornado.web.asynchronous
    def get(self):
        path = self.request.path
        query = self.request.query
        server, port = self.roundRobin.get_server()
        server_port = server + ":" + str(port)
        logging.info("Got path: " + path)
        logging.info("Got query: " + query)
        logging.info("redirecting to: " + server_port + path + "?" + query)
        
        http = tornado.httpclient.AsyncHTTPClient()
        http.fetch(server_port + path + "?" + query, self._on_download)
        
    def _on_download(self, response):
        for (hname, hvalue) in response.headers.get_all():
            self.set_header(hname, hvalue)
        self.set_status(response.code)
        self.write(response.body)
        self.finish()
    
    @tornado.web.asynchronous
    def post(self):
        self.get()

class roundRobin:
    '''Contains the list of the server / ports and keeps track
    of which was last used and which should be used next.'''
    def __init__(self, servers):
        self.current_number = 0
        self.serverlist = servers
    
    def get_server(self):
        '''Ideally this'd be a generator function.'''
        server_port = self.serverlist[self.current_number]
        self.current_number += 1
        self.current_number %= len(self.serverlist)
        return server_port
        
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
    testResults = {'%s:%s' % (domain, port): {} for (domain, port) in serverList}
    http = tornado.httpclient.HTTPClient()
    
    def handleResult(result, testFn):
        serverUrl, test = result.request.url.rsplit('/', 1)
        if not result.code == 200:
            testResults[serverUrl][test] = (result.code, result.request_time)
        else:
            try:
                testResults[serverUrl][test] = (testFn(json.loads(result.body.decode('utf-8'))), result.request_time)
            except ValueError:
                testResults[serverUrl][test] = (False, result.request_time)
    
    for (domain, port) in serverList:
        for (testPath, testFn) in tests.items():
            requestURL = '%s:%s%s' % (domain, port, testPath)
            handleResult(http.fetch(requestURL, request_timeout = 15), testFn) #, validate_cert = False when testing locally
                
    return testResults

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Start Apertium APY Gateway")
    parser.add_argument('serverlist', help="path to file with list of servers and ports available")
    parser.add_argument('-t', '--tests', help="perform tests on server pool", action='store_true', default=False)
    parser.add_argument('-p', '--port', help="port to run gateway on (default = 2738)", type=int, default=2738)
    parser.add_argument('-c', '--ssl-cert', help='path to SSL Certificate', default=None)
    parser.add_argument('-k', '--ssl-key', help='path to SSL Key File', default=None)
    parser.add_argument('-j', '--num-processes', help='number of processes to run (default = number of cores)', type=int, default=0)
    args = parser.parse_args()
    
    logging.getLogger().setLevel(logging.INFO)
    enable_pretty_logging()
    
    # read the serverlist file
    try:
        with open(args.serverlist) as serverlist:
            server_port_list = []
            for serverPortPair in serverlist:
                if serverPortPair[0] != '#': #filter out the commented lines
                    srv, port = serverPortPair.split()
                    server_port_list.append((srv, int(port)))
    except:
        logging.critical("Could not open serverlist " + args.serverlist)
        sys.exit(-1)
    
    if args.tests:
        logging.info(testServerPool(server_port_list))
      
    rR = roundRobin(server_port_list)
    logging.info("Server/port list used: " + str(server_port_list))
    
    application = tornado.web.Application([
        (r'/.*', roundRobinHandler, {"roundRobin": rR})
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
    tornado.ioloop.IOLoop.instance().start()
   
