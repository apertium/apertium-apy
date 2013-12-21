#!/usr/bin/env python3

import argparse, logging, sys
import tornado, tornado.httpserver, tornado.web, tornado.httpclient
from tornado.web import RequestHandler
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
        # assuming we don't need any headers
        self.set_status(response.code)
        self.write(response.body)
        self.finish()

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

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Start Apertium APY Gateway")
    parser.add_argument('serverlist', help="path to file with list of servers and ports available")
    parser.add_argument('-p', '--port', help="port to run gateway on", type=int, default=2737)
    parser.add_argument('-c', '--sslCert', help='path to SSL Certificate', default=None)
    parser.add_argument('-k', '--sslKey', help='path to SSL Key File', default=None)
    args = parser.parse_args()
    logging.getLogger().setLevel(logging.INFO)
    
    # read the serverlist file
    try:
        serverlist = open(args.serverlist)
    except:
        logging.critical("Could not open serverlist " + args.serverlist)
        sys.exit(-1)
    server_port_list = []
    for serverPortPair in serverlist:
        if serverPortPair[0] != '#': #filter out the commented lines
            srv, port = serverPortPair.split()
            server_port_list.append([srv, int(port)])
    serverlist.close()
    rR = roundRobin(server_port_list)
    logging.info("Server/port list used: " + str(server_port_list))
    enable_pretty_logging()
    
    application = tornado.web.Application([
        (r'/.*', roundRobinHandler, {"roundRobin": rR})
    ])
    
    if args.sslCert and args.sslKey:
        http_server = tornado.httpserver.HTTPServer(application, ssl_options = {
            'certfile': args.sslCert,
            'keyfile': args.sslKey,
        })
        print('Gateway-ing at https://localhost:%s' % args.port)
    else:
        http_server = tornado.httpserver.HTTPServer(application)
        print('Gateway-ing at http://localhost:%s' % args.port)
    http_server.listen(args.port)
    tornado.ioloop.IOLoop.instance().start()
