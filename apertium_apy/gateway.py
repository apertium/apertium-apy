#!/usr/bin/env python3

import argparse
import itertools
import json
import logging
import pprint
import random
import socket
import sys
from collections import OrderedDict

import tornado
import tornado.httpclient
import tornado.httpserver
import tornado.gen
import tornado.web
from tornado.options import enable_pretty_logging  # type: ignore
from tornado.web import RequestHandler

import apy

if False:
    from typing import Any, Dict, List, Set, Tuple  # noqa: F401


global verify_ssl_cert


def gen_server_name(server, port):
    if len(server.split('/')) > 3:  # true if there's a separate 'path' element
        server = server.rsplit('/', 1)
        server_port = '%s:%s/%s' % (server[0], port, server[1])
    else:
        server_port = '%s:%s' % (server, port)
    return server_port


class RedirectRequestHandler(RequestHandler):
    """Handler for non-list requests -- all requests that must be redirected."""

    def initialize(self, balancer):
        self.balancer = balancer

    async def get(self):
        path = self.request.path
        mode, lang_pair, per_word_modes = [None] * 3
        path_to_mode = {
            '/translate': 'pairs', '/analyze': 'analyzers',
            '/analyse': 'analyzers', '/generate': 'generators',
            '/perWord': 'perWord', '/coverage': 'coverage',
            '/listLanguageNames': 'languageNames', '/identifyLang': 'identifyLang',
            '/getLocale': 'getLocale',
        }

        if path not in path_to_mode:
            return self.send_error(400)

        mode = path_to_mode[path]

        if path == '/translate':
            lang_pair = self.get_argument('langpair')
            lang_pair = lang_pair.replace('|', '-')  # lang_pair=lang|pair only in /translate
        elif path == '/analyze' or path == '/analyse':
            lang_pair = self.get_argument('mode')
        elif path == '/generate':
            lang_pair = self.get_argument('mode')
        elif path == '/perWord':
            lang_pair = self.get_argument('lang')
            per_word_modes = self.get_argument('modes').split()
        elif path == '/coverage':
            lang_pair = self.get_argument('mode')

        query = self.request.query
        headers = self.request.headers

        server_tuple = self.balancer.get_server(lang_pair, mode, per_word_modes=per_word_modes)
        if server_tuple:
            server, port = server_tuple
        else:
            logging.warning('No server available for request: %s', self.request.uri)
            return self.send_error(400)
        server_port = gen_server_name(server, port)
        logging.info('Redirecting %s?%s to %s%s?%s', path, query, server_port, path, query)

        http = tornado.httpclient.AsyncHTTPClient()
        response = await http.fetch(
            server_port + path + '?' + query,
            raise_error=False,
            validate_cert=verify_ssl_cert, headers=headers)
        self.balancer.inform('start', (server, port), url=path)
        self._on_download((server, port), lang_pair, response)

    def _on_download(self, server, lang_pair, response):
        response_body = response.body
        if response.error is not None and response.error.code == 599:
            self.balancer.inform('drop', server, response=response, lang=lang_pair)
            logging.info('Request failed with code %d, trying next server after %s', response.error.code, str(server))
            return self.get()
        if response.error is None:
            self.balancer.inform('complete', server, response=response, lang=lang_pair)
            self.write(response_body)
        else:
            self.set_status(response.code)
        for (hname, hvalue) in response.headers.get_all():
            self.set_header(hname, hvalue)
        self.finish()

    @tornado.gen.coroutine
    def post(self):
        self.get()


class ListRequestHandler(apy.BaseHandler):
    """Handler for list requests. Takes a language-pair-server map and aggregates the language-pairs of all of the servers."""

    def initialize(self, server_lang_pair_map):
        self.server_lang_pair_map = server_lang_pair_map
        callbacks = self.get_arguments('callback')
        if callbacks:
            self.callback = callbacks[0]

    @tornado.gen.coroutine
    def get(self):
        logging.info('Overriding list call: %s %s', self.request.path, self.get_arguments('q'))
        if self.request.path != '/listPairs' and self.request.path != '/list':
            self.send_error(400)
        else:
            q = self.get_arguments('q')
            query = q[0] if q else None
            if self.request.path == '/listPairs' or query == 'pairs':
                logging.info('Responding to request for pairs')
                response_data = []
                for pair in self.server_lang_pair_map['pairs']:
                    (l1, l2) = pair
                    response_data.append({'sourceLanguage': l1, 'targetLanguage': l2})
                self.send_response({'responseData': response_data, 'responseDetails': None, 'responseStatus': 200})
            elif query == 'analyzers' or query == 'analysers':
                self.send_response({
                    pair: self.server_lang_pair_map['analyzers'][pair][0] for pair in self.server_lang_pair_map['analyzers']
                })
            elif query == 'generators':
                self.send_response({
                    pair: self.server_lang_pair_map['generators'][pair][0] for pair in self.server_lang_pair_map['generators']
                })
            elif query == 'taggers' or query == 'disambiguators':
                self.send_response({
                    pair: self.server_lang_pair_map['taggers'][pair][0] for pair in self.server_lang_pair_map['taggers']
                })
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
    """Contains the list of the server / ports / their capabilities
        and cycles between the available/possible ones."""

    def __init__(self, servers, langpairmap):
        super(RoundRobin, self).__init__(servers)
        self.langpairmap = langpairmap
        self.generator = itertools.cycle(self.serverlist)

    def get_server(self, lang_pair, mode='pairs', *args, **kwargs):
        # when we get a /perWord request, we have multiple modes, all of which have to be on the server
        # the modes will not be 'pairs'
        if 'per_word_modes' in kwargs and kwargs['per_word_modes'] is not None:
            per_word_modes = {'morph': 'analyzers', 'biltrans': 'analyzers', 'tagger': 'taggers', 'translate': 'taggers'}
            modes = set(map(lambda _: per_word_modes[_], kwargs['per_word_modes']))
            logging.info('Handling a /perWord request with modes %s for langpair %s', modes, lang_pair)

            def is_in(modes, server):
                for mode in modes:
                    if lang_pair not in self.langpairmap[mode] or server not in self.langpairmap[mode][lang_pair][1]:
                        return False
                else:
                    return True
            if not any(is_in(modes, server) for server in self.serverlist):
                logging.error('Language pair %s not found for modes %s', lang_pair, modes)
                return next(self.generator)
            else:
                server = next(self.generator)
                while not is_in(modes, server):
                    server = next(self.generator)
                return server
        # for everything that isn't a /perWord call
        if lang_pair is not None and mode == 'pairs':  # for mode 'pairs', the key is ('lang', 'pair') rather than 'lang-pair'
            lang_pair = tuple(lang_pair.split('-'))
        if lang_pair is None or lang_pair not in self.langpairmap[mode]:
            logging.error('Language pair %s for mode %s not found', lang_pair, mode)
            return next(self.generator)
        server = next(self.generator)
        if mode == 'pairs':
            serverlist = self.langpairmap[mode][lang_pair]
        else:
            serverlist = self.langpairmap[mode][lang_pair][1]
        while server not in serverlist:
            server = next(self.generator)
        return server

    def inform(self, action, server, *args, **kwargs):
        if action == 'drop':
            self.serverlist = [x for x in self.serverlist if x != server]
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
        if action not in actions:
            raise ValueError('invalid argument action: %s' % action)
        else:
            self.serverlist[server] += actions[action]
            self.serverlist = OrderedDict(sorted(self.serverlist.items(), key=lambda x: x[1]))


class WeightedRandom(Balancer):
    def __init__(self, servers):
        self.serverlist = OrderedDict([(server, 0) for server in servers])
        all_test_results = [test_server_pool([server[0] for server in self.serverlist.items()]) for _ in range(0, 5)]

        for test_results in all_test_results:
            for test_result in test_results.items():
                server = test_result[0]
                results = test_result[1]
                test_score = sum([result[1] for test_path, result in results.items()])
                self.serverlist[server] += test_score / 5
        self.serverlist = OrderedDict(sorted(self.serverlist.items(), key=lambda x: x[1]))

    def get_server(self, *args, **kwargs):
        servers = list(filter(lambda x: not x[1] == float('inf'), list(self.serverlist.items())))
        total = sum(weight for (server, weight) in servers)
        r = random.uniform(0, total)
        current_pos = 0
        for (server, weight) in servers:
            if current_pos + weight >= r:
                return server
            current_pos += weight
        assert False, 'failed to get server'

    def inform(self, action, server, *args, **kwargs):
        raise NotImplementedError

    def update_weights(self):
        raise NotImplementedError


class Fastest(Balancer):
    def __init__(self, servers, server_capabilities, num_responses):
        self.servers = servers
        self.original_servers = servers
        self.server_cycle = itertools.cycle(self.servers)
        self.num_responses = num_responses
        self.init_server_list(server_capabilities=server_capabilities)

    def get_server(self, lang_pair, mode, *args, **kwargs):
        if len(self.serverlist):
            mode_to_url = {'pairs': 'translate', 'generators': 'generate', 'analyzers': 'analyze', 'taggers': 'tag', 'coverage': 'analyze'}
            if mode in mode_to_url:
                if (mode_to_url[mode], lang_pair) in self.serverlist:
                    possible_servers_list = list(self.serverlist[(mode_to_url[mode], lang_pair)])
                    if len(possible_servers_list):
                        return possible_servers_list[0]
            elif mode == 'languageNames' or mode == 'identifyLang' or mode == 'getLocale':
                return next(self.server_cycle)
            elif mode == 'perWord':
                modes = kwargs['per_word_modes']
                possible_servers_set = set()  # type: Set
                if ('morph' in modes or 'biltrans' in modes) and ('analyze', lang_pair) in self.serverlist:
                    possible_servers_set.update(self.serverlist[('analyze', lang_pair)])
                elif ('tagger' in modes or 'disambig' in modes or 'translate' in modes) and ('tag', lang_pair) in self.serverlist:
                    if possible_servers_set:
                        possible_servers_set &= self.serverlist[('tag', lang_pair)]
                    else:
                        possible_servers_set.update(self.serverlist[('tag', lang_pair)])
                if len(possible_servers_set):
                    return list(possible_servers_set)[0]
        else:
            logging.critical('Empty serverlist')
            sys.exit(-1)

    def inform(self, action, server, *args, **kwargs):
        actions = {'start', 'complete', 'drop'}
        if action not in actions:
            raise ValueError('invalid argument action: %s' % action)
        elif action == 'start':
            return
        elif action == 'complete' or action == 'drop':
            response = kwargs['response']
            url = response.request.url
            request_time = response.request_time
            if response.body:
                response_len = len(response.body)
            path = url.rsplit('/', 1)[1] if '?' not in url else url.rsplit('/', 1)[1].split('?')[0]
            mode = (path, kwargs['lang'])

            if mode in self.serverlist:
                if action == 'complete':
                    if self.serverlist[mode][server]:
                        self.serverlist[mode][server] = (self.serverlist[mode][server] *
                                                         (self.num_responses - 1) + request_time / response_len) / self.num_responses
                    else:
                        self.serverlist[mode][server] = request_time / response_len / self.num_responses
                elif action == 'drop':
                    logging.error('Dropping server: %s', repr(server))
                    self.servers.remove(server)
                    self.server_cycle = itertools.cycle(self.servers)
                    del self.serverlist[mode][server]

                pprint.pprint(self.serverlist[mode])
                self.serverlist[mode] = OrderedDict(sorted(self.serverlist[mode].items(), key=lambda x: x[1]))

    def init_server_list(self, server_capabilities=None):
        if server_capabilities is None:
            server_capabilities = determine_server_capabilities(self.original_servers)
        self.serverlist = {}

        mode_to_url = {'pairs': 'translate', 'generators': 'generate', 'analyzers': 'analyze', 'taggers': 'tag'}
        for lang, servers in server_capabilities['pairs'].items():
            self.serverlist[(mode_to_url['pairs'], '%s-%s' % lang)] = OrderedDict([(server, 0) for server in servers])

        for mode, capabiltities in server_capabilities.items():
            if mode != 'pairs':
                for lang, servers in server_capabilities[mode].items():
                    self.serverlist[(mode_to_url[mode], lang)] = OrderedDict([(server, 0) for server in servers[1]])

        pprint.pprint(self.serverlist)

    def init_weights(self):
        self.serverlist = OrderedDict([(server, [0, {}]) for server in self.servers])
        all_test_results = [test_server_pool([server[0] for server in self.serverlist.items()]) for _ in range(0, self.num_responses)]
        for test_results in all_test_results:
            for test_result in test_results.items():
                server = test_result[0]
                results = test_result[1]
                test_sum = sum([result[1] for test_path, result in results.items()])
                if '/list' not in self.serverlist[server][1]:
                    self.serverlist[server][1]['list'] = 0
                self.serverlist[server][1]['list'] += test_sum / (self.num_responses * len(results.items()))
        # self.calcAggregateScores()  TODO: Does not exist
        self.serverlist = OrderedDict(filter(lambda x: x[1][0] != float('inf'), self.serverlist.items()))
        # self.sortServerList()  TODO: Does not exist


def test_server_pool(server_list):
    tests = {
        '/list?q=pairs': lambda x:
            isinstance(x, dict) and
            set(x.keys()) == {'responseStatus', 'responseData', 'responseDetails'} and
            isinstance(x['responseStatus'], int) and
            isinstance(x['responseData'], list) and
            all([isinstance(lang_pair, dict) for lang_pair in x['responseData']]) and
            all([set(lang_pair.keys()) == {'sourceLanguage', 'targetLanguage'} for lang_pair in x['responseData']]),
        '/list?q=analyzers': lambda x: isinstance(x, dict) and all(map(lambda y: isinstance(y, str), list(x.keys()) + list(x.values()))),
        '/list?q=taggers': lambda x: isinstance(x, dict) and all(map(lambda y: isinstance(y, str), list(x.keys()) + list(x.values()))),
        '/list?q=generators': lambda x: isinstance(x, dict) and all(map(lambda y: isinstance(y, str), list(x.keys()) + list(x.values()))),
    }
    test_results = {server: {} for server in server_list}  # type: Dict[Any, Dict[str, Tuple[bool, float]]]
    http = tornado.httpclient.HTTPClient()

    def handle_result(result, test, server):
        test_path, test_fn = test
        if not result:
            test_results[server][test_path] = (False, float('inf'))
        elif not result.code == 200:
            test_results[server][test_path] = (result.code, float('inf'))
        else:
            try:
                if test_fn(json.loads(result.body.decode('utf-8'))):
                    test_results[server][test_path] = (True, result.request_time)
                else:
                    test_results[server][test_path] = (False, float('inf'))
            except ValueError:  # Not valid JSON
                test_results[server][test_path] = (False, float('inf'))

    for (domain, port) in server_list:
        for (test_path, test_fn) in tests.items():
            request_url = '%s%s' % (gen_server_name(domain, port), test_path)
            try:
                result = http.fetch(request_url, request_timeout=15, validate_cert=verify_ssl_cert)
                handle_result(result, (test_path, test_fn), (domain, port))
            except Exception as e:
                logging.warning('Exception in test_server_pool: %s', e)
                handle_result(None, (test_path, test_fn), (domain, port))

    return test_results


def determine_server_capabilities(serverlist):
    """Find which APYs can do what.

    The return data from this function is a little complex, better illustrated than described:
    capabilities = {
        'pairs': {  #note that pairs is a special mode compared to taggers/generators/analyzers
            ('lang', 'pair'): [(server1, port1), (server2, port2)]
            }
        'taggers|generators|analyzers': {
            'lang-pair': ('lang-pair-moreinfo', [(server1, port1), (server2, port2)])
            #'moreinfo' tends to be 'anmor' or 'generador' or 'tagger'
            }
         }
            """
    # TODO: scaleMT doesn't support /list?q=mode calls. Find a way to figure out which language-pairs each mode supports
    # on scaleMT survers.
    # You will probably need to batch-translate or batch-analyze with the language pairs from /listPairs and
    # look at the return codes in order to do this.
    http = tornado.httpclient.HTTPClient()
    modes = ('pairs', 'taggers', 'generators', 'analyzers')
    capabilities = {}  # type: Dict[str, Dict]
    for (domain, port) in serverlist:
        server = (domain, port)
        for mode in modes:
            if mode not in capabilities:
                capabilities[mode] = {}
            if mode == 'pairs':  # for compatibility with scaleMT, we request /listPairs
                request_url = '%s/listPairs' % gen_server_name(domain, port)
            else:
                request_url = '%s/list?q=%s' % (gen_server_name(domain, port), mode)
            logging.info('Getting information from %s', request_url)
            # make the request
            try:
                result = http.fetch(request_url, request_timeout=15, validate_cert=verify_ssl_cert)
            except Exception as e:
                logging.error('Fetch for data from %s for %s failed with %s, dropping server', gen_server_name(domain, port), mode, e)
                continue
            # parse the return
            try:
                response = json.loads(result.body.decode('utf-8'))
            except ValueError:  # Not valid JSON, we stop using the server
                logging.error('Received invalid JSON from %s on query for %s, dropping server', gen_server_name(domain, port), mode)
                continue
            if mode == 'pairs':  # pairs has a slightly different response format
                if 'responseStatus' not in response or response['responseStatus'] != 200 or 'responseData' not in response:
                    logging.error('JSON return format unexpected from %s:%s on query for %s, dropping server', domain, port, mode)
                    continue
                for lang_pair in response['responseData']:
                    lang_pair_tuple = (lang_pair['sourceLanguage'], lang_pair['targetLanguage'])
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
    parser = argparse.ArgumentParser(description='Start Apertium APY Gateway')
    parser.add_argument('serverlist', help='path to file with list of servers and ports available')
    parser.add_argument('-t', '--tests', help='perform tests on server pool', action='store_true', default=False)
    parser.add_argument('-p', '--port', help='port to run gateway on (default = 2738)', type=int, default=2738)
    parser.add_argument('-c', '--ssl-cert', help='path to SSL Certificate', default=None)
    parser.add_argument('-k', '--ssl-key', help='path to SSL Key File', default=None)
    parser.add_argument('-d', '--debug', help='debug mode (do not verify SSL certs)', action='store_false', default=True)
    parser.add_argument('-j', '--num-processes', help='number of processes to run (default = number of cores)', type=int, default=0)
    parser.add_argument('-i', '--test-interval', help='interval to perform tests in ms (default = 3600000)', type=int, default=3600000)
    args = parser.parse_args()

    global verify_ssl_cert
    verify_ssl_cert = args.debug

    logging.getLogger().setLevel(logging.INFO)
    enable_pretty_logging()

    # read the serverlist file
    try:
        with open(args.serverlist) as serverlist:
            server_port_list = []
            for server_port_pair in serverlist:
                if server_port_pair[0] != '#':  # filter out the commented lines
                    srv, port = server_port_pair.rsplit(':', 1)
                    server_port_list.append((srv, int(port)))
    except IOError:
        logging.critical('Could not open serverlist: %s', args.serverlist)
        sys.exit(-1)

    if len(server_port_list) == 0:
        logging.critical('Serverlist must not be empty')
        sys.exit(-1)

    # find an open socket
    result = 0
    while result == 0:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', args.port))
        if result == 0:
            logging.info('Port %d already in use, trying next', args.port)
            args.port += 1
        sock.close()

    logging.info('Server/port list used: ' + str(server_port_list))
    server_lang_pair_map = determine_server_capabilities(server_port_list)
    logging.info('Using server language-pair mapping: %s', server_lang_pair_map)
    # balancer = RoundRobin(server_port_list, server_lang_pair_map)
    # balancer = LeastConnections(server_port_list)
    # balancer = WeightedRandom(server_port_list)
    balancer = Fastest(server_port_list, server_lang_pair_map, 5)

    application = tornado.web.Application([
        (r'/list', ListRequestHandler, {'serverLangPairMap': server_lang_pair_map}),
        (r'/listPairs', ListRequestHandler, {'serverLangPairMap': server_lang_pair_map}),
        (r'/.*', RedirectRequestHandler, {'balancer': balancer}),
    ])

    if args.ssl_cert and args.ssl_key:
        http_server = tornado.httpserver.HTTPServer(application, ssl_options={
            'certfile': args.ssl_cert,
            'keyfile': args.ssl_key,
        })
        logging.info('Gateway-ing at https://localhost:%s', args.port)
    else:
        http_server = tornado.httpserver.HTTPServer(application)
        logging.info('Gateway-ing at http://localhost:%s', args.port)

    http_server.bind(args.port)
    http_server.start(args.num_processes)
    main_loop = tornado.ioloop.IOLoop.instance()
    if isinstance(balancer, Fastest):
        tornado.ioloop.PeriodicCallback(lambda: balancer.init_server_list(), args.test_interval).start()
    main_loop.start()
