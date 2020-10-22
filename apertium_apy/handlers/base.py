import json
import logging
import os
import sys
from datetime import datetime, timedelta

import tornado
import tornado.gen
import tornado.web
from tornado.escape import utf8
from tornado.locks import Semaphore

from typing import Union, Dict, Optional, List, Any, Tuple  # noqa: F401
from apertium_apy.utils.translation import FlushingPipeline, SimplePipeline


def dump_json(data):
    # This acts very similarly to Tornado's escape.json_encode but doesn't
    # result in ugly \u codes. Tornado does not support this natively.
    return json.dumps(data, ensure_ascii=False).replace('</', '<\\/')


class Stats:
    startdate = datetime.now()
    usecount = {}               # type: Dict[Tuple[str, str], int]
    vmsize = 0
    timing = []                 # type: List[Tuple[datetime, datetime, int]]


class BaseHandler(tornado.web.RequestHandler):
    pairs = {}  # type: Dict[str, str]
    analyzers = {}  # type: Dict[str, Tuple[str, str]]
    generators = {}  # type: Dict[str, Tuple[str, str]]
    taggers = {}  # type: Dict[str, Tuple[str, str]]
    spellers = {}  # type: Dict[str, Tuple[str, str]]
    # (l1, l2): [translation.Pipeline], only contains flushing pairs!
    pipelines = {}  # type: Dict[Tuple[str, str], List[Union[FlushingPipeline, SimplePipeline]]]
    pipelines_holding = []  # type: List
    callback = None
    timeout = 10
    lang_names = None           # type: Optional[str]
    scale_mt_logs = False
    verbosity = 0
    api_keys_conf = None
    stat_period_max_age = timedelta.max

    # dict representing a graph of translation pairs; keys are source languages
    # e.g. pairs_graph['eng'] = ['fra', 'spa']
    pairs_graph = {}  # type: Dict[str, List[str]]
    # 2-D dict storing the shortest path for a chained translation pair
    # keys are source and target languages
    # e.g. paths['eng']['fra'] = ['eng', 'spa', 'fra']
    paths = {}  # type: Dict[str, Dict[str, List[str]]]

    stats = Stats()

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
    url_cache = {}       # type: Dict[Tuple[str, str], Dict[str, Tuple[str, str]]]
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
            prev = prevs[u]     # type: Optional[str]
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
            if vmsize > self.stats.vmsize:
                logging.warning('VmSize of %s from %d to %d', os.getpid(), self.stats.vmsize, vmsize)
                self.stats.vmsize = vmsize
        except Exception as e:
            # Don't fail just because we couldn't log:
            logging.info('Exception in log_vmsize: %s', e)

    def send_response(self, data):
        self.log_vmsize()
        if isinstance(data, dict) or isinstance(data, list):
            data = dump_json(data)
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

        data = dump_json(result)
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

    @tornado.gen.coroutine
    def post(self):
        yield self.get()

    def options(self):
        self.set_status(204)
        self.finish()
