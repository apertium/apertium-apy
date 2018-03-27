import logging
import os
import sys
from datetime import datetime

import tornado
from tornado import escape
from tornado.escape import utf8
from tornado.locks import Semaphore

if False:
    from typing import Dict, Optional, List, Tuple  # noqa: F401


class BaseHandler(tornado.web.RequestHandler):
    pairs = {}  # type: Dict[str, str]
    analyzers = {}  # type: Dict[str, Tuple[str, str]]
    generators = {}  # type: Dict[str, Tuple[str, str]]
    taggers = {}  # type: Dict[str, Tuple[str, str]]
    spellers = {}  # type: Dict[str, Tuple[str, str]]
    # (l1, l2): [translation.Pipeline], only contains flushing pairs!
    pipelines = {}  # type: Dict[str, List]
    pipelines_holding = []  # type: List
    callback = None
    timeout = None
    scale_mt_logs = False
    verbosity = 0

    # dict representing a graph of translation pairs; keys are source languages
    # e.g. pairs_graph['eng'] = ['fra', 'spa']
    pairs_graph = {}  # type: Dict[str, List[str]]
    # 2-D dict storing the shortest path for a chained translation pair
    # keys are source and target languages
    # e.g. paths['eng']['fra'] = ['eng', 'spa', 'fra']
    paths = {}  # type: Dict[str, Dict[str, List[str]]]

    stats = {
        'startdate': datetime.now(),
        'useCount': {},
        'vmsize': 0,
        'timing': [],
    }

    # (l1, l2): translation.ParsedModes
    pipeline_cmds = {}  # type: Dict
    max_pipes_per_pair = 1
    min_pipes_per_pair = 0
    max_users_per_pipe = 5
    max_idle_secs = 0
    restart_pipe_after = 1000
    doc_pipe_sem = Semaphore(3)
    # Empty the url_cache[pair] when it's this full:
    max_inmemory_url_cache = 1000  # type: int
    url_cache = {}  # type: Dict[Tuple[str, str], Dict[str, str]]
    url_cache_path = None  # type: Optional[str]
    # Keep half a gig free when storing url_cache to disk:
    min_free_space_disk_url_cache = 512 * 1024 * 1024  # type: int

    def initialize(self):
        self.callback = self.get_argument('callback', default=None)

    @classmethod
    def init_pairs_graph(cls):
        for pair in cls.pairs:
            lang1, lang2 = pair.split('-')
            if lang1 in cls.pairs_graph:
                cls.pairs_graph[lang1].append(lang2)
            else:
                cls.pairs_graph[lang1] = [lang2]

    @classmethod
    def calculate_paths(cls, start):
        nodes = set()
        for pair in map(lambda x: x.split('-'), cls.pairs):
            nodes.add(pair[0])
            nodes.add(pair[1])
        dists = {}
        prevs = {}
        dists[start] = 0

        while nodes:
            u = min(nodes, key=lambda u: dists.get(u, sys.maxsize))
            nodes.remove(u)
            for v in cls.pairs_graph.get(u, []):
                if v in nodes:
                    other = dists.get(u, sys.maxsize) + 1   # TODO: weight(u, v) -- lower weight = better translation
                    if other < dists.get(v, sys.maxsize):
                        dists[v] = other
                        prevs[v] = u

        cls.paths[start] = {}
        for u in prevs:
            prev = prevs[u]
            path = [u]
            while prev:
                path.append(prev)
                prev = prevs.get(prev)
            cls.paths[start][u] = list(reversed(path))

    @classmethod
    def init_paths(cls):
        for lang in cls.pairs_graph:
            cls.calculate_paths(lang)

    def log_vmsize(self):
        if self.verbosity < 1:
            return
        scale = {'kB': 1024, 'mB': 1048576,
                 'KB': 1024, 'MB': 1048576}
        try:
            for line in open('/proc/%d/status' % os.getpid()):
                if line.startswith('VmSize:'):
                    _, num, unit = line.split()
                    break
            vmsize = int(num) * scale[unit]
            if vmsize > self.stats['vmsize']:
                logging.warning('VmSize of %s from %d to %d', os.getpid(), self.stats['vmsize'], vmsize)
                self.stats['vmsize'] = vmsize
        except Exception as e:
            # Don't fail just because we couldn't log:
            logging.info('Exception in log_vmsize: %s', e)

    def send_response(self, data):
        self.log_vmsize()
        if isinstance(data, dict) or isinstance(data, list):
            data = escape.json_encode(data)
            self.set_header('Content-Type', 'application/json; charset=UTF-8')

        if self.callback:
            self.set_header('Content-Type', 'application/javascript; charset=UTF-8')
            self._write_buffer.append(utf8('%s(%s)' % (self.callback, data)))
        else:
            self._write_buffer.append(utf8(data))
        self.finish()

    def write_error(self, status_code, **kwargs):
        http_explanations = {
            400: 'Request not properly formatted or contains languages that Apertium APy does not support',
            404: 'Resource requested does not exist. URL may have been mistyped',
            408: 'Server did not receive a complete request within the time it was prepared to wait. Try again',
            500: 'Unexpected condition on server. Request could not be fulfilled.',
        }
        explanation = kwargs.get('explanation', http_explanations.get(status_code, ''))
        if 'exc_info' in kwargs and len(kwargs['exc_info']) > 1:
            exception = kwargs['exc_info'][1]
            if hasattr(exception, 'log_message') and exception.log_message:
                explanation = exception.log_message % exception.args
            elif hasattr(exception, 'reason'):
                explanation = exception.reason or tornado.httputil.responses.get(status_code, 'Unknown')
            else:
                explanation = tornado.httputil.responses.get(status_code, 'Unknown')

        result = {
            'status': 'error',
            'code': status_code,
            'message': tornado.httputil.responses.get(status_code, 'Unknown'),
            'explanation': explanation,
        }

        data = escape.json_encode(result)
        self.set_header('Content-Type', 'application/json; charset=UTF-8')

        if self.callback:
            self.set_header('Content-Type', 'application/javascript; charset=UTF-8')
            self._write_buffer.append(utf8('%s(%s)' % (self.callback, data)))
        else:
            self._write_buffer.append(utf8(data))
        self.finish()

    def set_default_headers(self):
        self.set_header('Access-Control-Allow-Origin', '*')
        self.set_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.set_header('Access-Control-Allow-Headers', 'accept, cache-control, origin, x-requested-with, x-file-name, content-type')

    @tornado.web.asynchronous
    def post(self):
        self.get()

    def options(self):
        self.set_status(204)
        self.finish()
