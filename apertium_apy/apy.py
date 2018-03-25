#!/usr/bin/env python3
# coding=utf-8
# -*- indent-tabs-mode: nil -*-

__author__ = 'Kevin Brubeck Unhammer, Sushain K. Cherivirala'
__copyright__ = 'Copyright 2013--2018, Kevin Brubeck Unhammer, Sushain K. Cherivirala'
__credits__ = ['Kevin Brubeck Unhammer', 'Sushain K. Cherivirala', 'Jonathan North Washington', 'Xavi Ivars', 'Shardul Chiplunkar']
__license__ = 'GPLv3'
__status__ = 'Beta'
__version__ = '0.11.0.rc1'

import argparse
import configparser
import heapq
import html
import logging
import os
import random
import re
import signal
import string
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timedelta
from functools import wraps
from hashlib import sha1
from logging import handlers as logging_handlers  # type: ignore
from multiprocessing import Pool
from multiprocessing import TimeoutError  # type: ignore
from subprocess import Popen, PIPE
from threading import Thread
from urllib.parse import urlparse, urlunsplit

import tornado
import tornado.httpserver
import tornado.httputil
import tornado.iostream
import tornado.process
import tornado.web
from tornado import escape
from tornado import gen
from tornado import httpclient
from tornado.escape import utf8
from tornado.locks import Semaphore
from tornado.log import enable_pretty_logging

try:
    import cld2full as cld2  # type: ignore
except ImportError:
    cld2 = None

try:
    import chardet
except ImportError:
    chardet = None

try:
    import requests
except ImportError:
    requests = None  # type: ignore

try:
    import streamparser
except ImportError:
    streamparser = None

from .keys import get_key
from .mode_search import search_path
from .util import (get_localized_languages, strip_tags, process_per_word, get_coverage, get_coverages, to_alpha3_code,
                   to_alpha2_code, scale_mt_log, TranslationInfo, remove_dot_from_deformat)
from .wiki_util import wiki_login, wiki_get_token
from . import missingdb
from . import systemd
from . import translation

if False:
    from typing import Dict, List, Optional, Tuple  # noqa: F401

RECAPTCHA_VERIFICATION_URL = 'https://www.google.com/recaptcha/api/siteverify'
BYPASS_TOKEN = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(24))


def run_async_thread(func):
    @wraps(func)
    def async_func(*args, **kwargs):
        func_hl = Thread(target=func, args=args, kwargs=kwargs)
        func_hl.start()
        return func_hl

    return async_func


missing_freqs_db = None       # has to be global for sig_handler :-/


def sig_handler(sig, frame):
    global missing_freqs_db
    if missing_freqs_db is not None:
        if 'children' in frame.f_locals:
            for child in frame.f_locals['children']:
                os.kill(child, signal.SIGTERM)
            missing_freqs_db.commit()
        else:
            # we are one of the children
            missing_freqs_db.commit()
        missing_freqs_db.close_db()
    logging.warning('Caught signal: %s', sig)
    exit()


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
                logging.warning('VmSize of %s from %d to %d' % (os.getpid(), self.stats['vmsize'], vmsize))
                self.stats['vmsize'] = vmsize
        except Exception as e:
            # Don't fail just because we couldn't log:
            logging.info('Exception in log_vmsize: %s' % e)

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


class ListHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        query = self.get_argument('q', default='pairs')

        if query == 'pairs':
            src = self.get_argument('src', default=None)
            response_data = []
            if src:
                pairs_list = self.paths[src]

                def langs(foo):
                    return (src, foo)
            else:
                pairs_list = self.pairs

                def langs(foo):
                    return (foo.split('-')[0], foo.split('-')[1])
            for pair in pairs_list:
                l1, l2 = langs(pair)
                response_data.append({'sourceLanguage': l1, 'targetLanguage': l2})
                if self.get_arguments('include_deprecated_codes'):
                    response_data.append({'sourceLanguage': to_alpha2_code(l1), 'targetLanguage': to_alpha2_code(l2)})
            self.send_response({'responseData': response_data, 'responseDetails': None, 'responseStatus': 200})
        elif query == 'analyzers' or query == 'analysers':
            self.send_response({pair: modename for (pair, (path, modename)) in self.analyzers.items()})
        elif query == 'generators':
            self.send_response({pair: modename for (pair, (path, modename)) in self.generators.items()})
        elif query == 'taggers' or query == 'disambiguators':
            self.send_response({pair: modename for (pair, (path, modename)) in self.taggers.items()})
        elif query == 'spellers':
            self.send_response({lang_src: modename for (lang_src, (path, modename)) in self.spellers.items()})
        else:
            self.send_error(400, explanation='Expecting q argument to be one of analysers, generators, spellers, disambiguators, or pairs')


class StatsHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        num_requests = self.get_argument('requests', 1000)
        try:
            num_requests = int(num_requests)
        except ValueError:
            num_requests = 1000

        period_stats = self.stats['timing'][-num_requests:]
        times = sum([x[1] - x[0] for x in period_stats],
                    timedelta())
        chars = sum(x[2] for x in period_stats)
        if times.total_seconds() != 0:
            chars_per_sec = round(chars / times.total_seconds(), 2)
        else:
            chars_per_sec = 0.0
        nrequests = len(period_stats)
        max_age = (datetime.now() - period_stats[0][0]).total_seconds() if period_stats else 0

        uptime = int((datetime.now() - self.stats['startdate']).total_seconds())
        use_count = {'%s-%s' % pair: use_count
                     for pair, use_count in self.stats['useCount'].items()}
        running_pipes = {'%s-%s' % pair: len(pipes)
                         for pair, pipes in self.pipelines.items()
                         if pipes != []}
        holding_pipes = len(self.pipelines_holding)

        self.send_response({
            'responseData': {
                'uptime': uptime,
                'useCount': use_count,
                'runningPipes': running_pipes,
                'holdingPipes': holding_pipes,
                'periodStats': {
                    'charsPerSec': chars_per_sec,
                    'totChars': chars,
                    'totTimeSpent': times.total_seconds(),
                    'requests': nrequests,
                    'ageFirstRequest': max_age,
                },
            },
            'responseDetails': None,
            'responseStatus': 200,
        })


class RootHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        self.redirect('http://wiki.apertium.org/wiki/Apertium-apy')


class TranslateHandler(BaseHandler):
    def note_pair_usage(self, pair):
        self.stats['useCount'][pair] = 1 + self.stats['useCount'].get(pair, 0)

    unknown_mark_re = re.compile(r'[*]([^.,;:\t\* ]+)')

    def maybe_strip_marks(self, mark_unknown, pair, translated):
        self.note_unknown_tokens('%s-%s' % pair, translated)
        if mark_unknown:
            return translated
        else:
            return re.sub(self.unknown_mark_re, r'\1', translated)

    def note_unknown_tokens(self, pair, text):
        global missing_freqs_db
        if missing_freqs_db is not None:
            for token in re.findall(self.unknown_mark_re, text):
                missing_freqs_db.note_unknown(token, pair)

    def cleanable(self, i, pair, pipe):
        if pipe.use_count > self.restart_pipe_after:
            # Not affected by min_pipes_per_pair
            logging.info('A pipe for pair %s-%s has handled %d requests, scheduling restart',
                         pair[0], pair[1], self.restart_pipe_after)
            return True
        elif (i >= self.min_pipes_per_pair and
                self.max_idle_secs != 0 and
                time.time() - pipe.last_usage > self.max_idle_secs):
            logging.info("A pipe for pair %s-%s hasn't been used in %d secs, scheduling shutdown",
                         pair[0], pair[1], self.max_idle_secs)
            return True
        else:
            return False

    def clean_pairs(self):
        for pair in self.pipelines:
            pipes = self.pipelines[pair]
            to_clean = set(p for i, p in enumerate(pipes)
                           if self.cleanable(i, pair, p))
            self.pipelines_holding += to_clean
            pipes[:] = [p for p in pipes if p not in to_clean]
            heapq.heapify(pipes)
        # The holding area lets us restart pipes after n usages next
        # time round, since with lots of traffic an active pipe may
        # never reach 0 users
        self.pipelines_holding[:] = [p for p in self.pipelines_holding
                                     if p.users > 0]
        if self.pipelines_holding:
            logging.info('%d pipelines still scheduled for shutdown', len(self.pipelines_holding))

    def get_pipe_cmds(self, l1, l2):
        if (l1, l2) not in self.pipeline_cmds:
            mode_path = self.pairs['%s-%s' % (l1, l2)]
            self.pipeline_cmds[(l1, l2)] = translation.parse_mode_file(mode_path)
        return self.pipeline_cmds[(l1, l2)]

    def should_start_pipe(self, l1, l2):
        pipes = self.pipelines.get((l1, l2), [])
        if pipes == []:
            logging.info('%s-%s not in pipelines of this process',
                         l1, l2)
            return True
        else:
            min_p = pipes[0]
            if len(pipes) < self.max_pipes_per_pair and min_p.users > self.max_users_per_pipe:
                logging.info('%s-%s has ≥%d users per pipe but only %d pipes',
                             l1, l2, min_p.users, len(pipes))
                return True
            else:
                return False

    def get_pipeline(self, pair):
        (l1, l2) = pair
        if self.should_start_pipe(l1, l2):
            logging.info('Starting up a new pipeline for %s-%s …', l1, l2)
            if pair not in self.pipelines:
                self.pipelines[pair] = []
            p = translation.make_pipeline(self.get_pipe_cmds(l1, l2))
            heapq.heappush(self.pipelines[pair], p)
        return self.pipelines[pair][0]

    def log_before_translation(self):
        return datetime.now()

    def log_after_translation(self, before, length):
        after = datetime.now()
        if self.scale_mt_logs:
            t_info = TranslationInfo(self)
            key = get_key(t_info.key)
            scale_mt_log(self.get_status(), after - before, t_info, key, length)

        if self.get_status() == 200:
            oldest = self.stats['timing'][0][0] if self.stats['timing'] else datetime.now()
            if datetime.now() - oldest > self.STAT_PERIOD_MAX_AGE:
                self.stats['timing'].pop(0)
            self.stats['timing'].append(
                (before, after, length))

    def get_pair_or_error(self, langpair, text_length):
        try:
            l1, l2 = map(to_alpha3_code, langpair.split('|'))
        except ValueError:
            self.send_error(400, explanation='That pair is invalid, use e.g. eng|spa')
            self.log_after_translation(self.log_before_translation(), text_length)
            return None
        if '%s-%s' % (l1, l2) not in self.pairs:
            self.send_error(400, explanation='That pair is not installed')
            self.log_after_translation(self.log_before_translation(), text_length)
            return None
        else:
            return (l1, l2)

    def get_format(self):
        dereformat = self.get_argument('format', default=None)
        deformat = ''
        reformat = ''
        if dereformat:
            deformat = 'apertium-des' + dereformat
            reformat = 'apertium-re' + dereformat
        else:
            deformat = self.get_argument('deformat', default='html')
            if 'apertium-des' not in deformat:
                deformat = 'apertium-des' + deformat
            reformat = self.get_argument('reformat', default='html-noent')
            if 'apertium-re' not in reformat:
                reformat = 'apertium-re' + reformat

        return deformat, reformat

    @gen.coroutine
    def translate_and_respond(self, pair, pipeline, to_translate, mark_unknown, nosplit=False, deformat=True, reformat=True):
        mark_unknown = mark_unknown in ['yes', 'true', '1']
        self.note_pair_usage(pair)
        before = self.log_before_translation()
        translated = yield pipeline.translate(to_translate, nosplit, deformat, reformat)
        self.log_after_translation(before, len(to_translate))
        self.send_response({
            'responseData': {
                'translatedText': self.maybe_strip_marks(mark_unknown, pair, translated),
            },
            'responseDetails': None,
            'responseStatus': 200,
        })
        self.clean_pairs()

    @gen.coroutine
    def get(self):
        pair = self.get_pair_or_error(self.get_argument('langpair'),
                                      len(self.get_argument('q')))
        if pair is not None:
            pipeline = self.get_pipeline(pair)
            deformat, reformat = self.get_format()
            yield self.translate_and_respond(pair,
                                             pipeline,
                                             self.get_argument('q'),
                                             self.get_argument('markUnknown', default='yes'),
                                             nosplit=False,
                                             deformat=deformat,
                                             reformat=reformat)


class TranslateChainHandler(TranslateHandler):
    def pair_list(self, langs):
        return [(langs[i], langs[i + 1]) for i in range(0, len(langs) - 1)]

    def get_pairs_or_error(self, langpairs, text_length):
        langs = [to_alpha3_code(lang) for lang in langpairs.split('|')]
        if len(langs) < 2:
            self.send_error(400, explanation='Need at least two languages, use e.g. eng|spa')
            self.log_after_translation(self.log_before_translation(), text_length)
            return None
        if len(langs) == 2:
            if langs[0] == langs[1]:
                self.send_error(400, explanation='Need at least two languages, use e.g. eng|spa')
                self.log_after_translation(self.log_before_translation(), text_length)
                return None
            return self.paths.get(langs[0], {}).get(langs[1])
        for lang1, lang2 in self.pair_list(langs):
            if '{:s}-{:s}'.format(lang1, lang2) not in self.pairs:
                self.send_error(400, explanation='Pair {:s}-{:s} is not installed'.format(lang1, lang2))
                self.log_after_translation(self.log_before_translation(), text_length)
                return None
        return langs

    @gen.coroutine
    def translate_and_respond(self, pairs, pipelines, to_translate, mark_unknown, nosplit=False, deformat=True, reformat=True):
        mark_unknown = mark_unknown in ['yes', 'true', '1']
        chain, pairs = pairs, self.pair_list(pairs)
        for pair in pairs:
            self.note_pair_usage(pair)
        before = self.log_before_translation()
        translated = yield translation.coreduce(to_translate, [p.translate for p in pipelines], nosplit, deformat, reformat)
        self.log_after_translation(before, len(to_translate))
        self.send_response({
            'responseData': {
                'translatedText': self.maybe_strip_marks(mark_unknown, (pairs[0][0], pairs[-1][1]), translated),
                'translationChain': chain,
            },
            'responseDetails': None,
            'responseStatus': 200,
        })
        self.clean_pairs()

    def prepare(self):
        if not self.pairs_graph:
            self.init_pairs_graph()

    @gen.coroutine
    def get(self):
        q = self.get_argument('q', default=None)
        langpairs = self.get_argument('langpairs')
        pairs = self.get_pairs_or_error(langpairs, len(q or []))
        if pairs:
            if not q:
                self.send_response({
                    'responseData': {
                        'translationChain': self.get_pairs_or_error(self.get_argument('langpairs'), 0),
                    },
                    'responseDetails': None,
                    'responseStatus': 200,
                })
            else:
                pipelines = [self.get_pipeline(pair) for pair in self.pair_list(pairs)]
                deformat, reformat = self.get_format()
                yield self.translate_and_respond(pairs, pipelines, q,
                                                 self.get_argument('markUnknown', default='yes'),
                                                 nosplit=False, deformat=deformat, reformat=reformat)
        else:
            self.send_error(400, explanation='No path found for {:s}-{:s}'.format(*langpairs.split('|')))
            self.log_after_translation(self.log_before_translation(), 0)


class TranslatePageHandler(TranslateHandler):
    def url_repl(self, base, attr, quote, aurl):
        a = urlparse(aurl)
        if a.netloc == '':
            newurl = urlunsplit((base.scheme,
                                 base.netloc,
                                 a.path,
                                 a.query,
                                 a.fragment))
        else:
            newurl = aurl
        return ' {a}={q}{u}{q}'.format(a=attr, u=newurl, q=quote)

    def unescape(self, page):
        # First workaround old bug that exists in a lot of
        # Windows-based web pages, see
        # http://stackoverflow.com/a/1398921/69663 :
        page = page.replace('&#150;', '&#8211;')
        # Unescape all other entities the regular way:
        return html.unescape(page)

    def clean_html(self, page, urlbase):
        page = self.unescape(page)
        if urlbase.netloc in ['www.avvir.no', 'avvir.no']:
            page = re.sub(r'([a-zæøåášžđŋ])=([a-zæøåášžđŋ])',
                          '\\1\\2',
                          page)
        page = page.replace('\u00ad', '')  # soft hyphen
        return page

    def html_to_text(self, page, url):
        encoding = 'utf-8'
        if chardet:
            encoding = chardet.detect(page).get('encoding', 'utf-8') or encoding
        base = urlparse(url)
        text = self.clean_html(page.decode(encoding), base)  # type: str
        return re.sub(r' (href|src)=([\'"])(..*?)\2',
                      lambda m: self.url_repl(base, m.group(1), m.group(2), m.group(3)),
                      text)

    def set_cached(self, pair, url, translated, origtext):
        """Cache translated text for a pair and url to memory, and disk.
        Also caches origtext to disk; see cache_path."""
        if pair not in self.url_cache:
            self.url_cache[pair] = {}
        elif len(self.url_cache[pair]) > self.max_inmemory_url_cache:
            self.url_cache[pair] = {}
        ts = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(time.time()))
        self.url_cache[pair][url] = (ts, translated)
        if self.url_cache_path is None:
            logging.info('No --url-cache-path, not storing cached url to disk')
            return
        dirname, basename = self.cache_path(pair, url)
        os.makedirs(dirname, exist_ok=True)
        statvfs = os.statvfs(dirname)
        if (statvfs.f_frsize * statvfs.f_bavail) < self.min_free_space_disk_url_cache:
            logging.warn('Disk of --url-cache-path has < {} free, not storing cached url to disk'.format(
                self.min_free_space_disk_url_cache))
            return
        # Note: If we make this a @gen.coroutine, we will need to lock
        # the file to avoid concurrent same-url requests clobbering:
        path = os.path.join(dirname, basename)
        with open(path, 'w') as f:
            f.write(ts)
            f.write('\n')
            f.write(translated)
        origpath = os.path.join(dirname, pair[0])
        with open(origpath, 'w') as f:
            f.write(origtext)

    def cache_path(self, pair, url):
        """Give the directory for where to cache the translation of this url,
        and the file name to use for this pair."""
        hsh = sha1(url.encode('utf-8')).hexdigest()
        dirname = os.path.join(self.url_cache_path,
                               # split it to avoid too many files in one dir:
                               hsh[:1], hsh[1:2], hsh[2:])
        return (dirname, '{}-{}'.format(*pair))

    def get_cached(self, pair, url):
        if not self.url_cache_path:
            return None
        if pair not in self.url_cache:
            self.url_cache[pair] = {}
        if url in self.url_cache[pair]:
            logging.info('Got cache from memory')
            return self.url_cache[pair][url]
        dirname, basename = self.cache_path(pair, url)
        path = os.path.join(dirname, basename)
        if os.path.exists(path):
            logging.info('Got cache on disk, we want to retranslate in background …')
            with open(path, 'r') as f:
                return (f.readline().strip(), f.read())

    def retranslate_cache(self, pair, url, cached):
        """If we've got something from the cache, and it isn't in memory, then
        it was from disk. We want to retranslate anything we found on
        disk, since it's probably using older versions of the language
        pair.
        """
        mem_cached = self.url_cache.get(pair, {}).get(url)
        if mem_cached is None and cached is not None:
            dirname, _ = self.cache_path(pair, url)
            origpath = os.path.join(dirname, pair[0])
            if os.path.exists(origpath):
                return open(origpath, 'r').read()

    def handle_fetch(self, response):
        if response.error is None:
            return
        elif response.code == 304:  # means we can use cache, so don't fail on this
            return
        else:
            self.send_error(503, explanation='{} on fetching url: {}'.format(response.code, response.error))

    @gen.coroutine
    def get(self):
        pair = self.get_pair_or_error(self.get_argument('langpair'),
                                      # Don't yet know the size of the text, and don't want to fetch it unnecessarily:
                                      -1)
        if pair is None:
            return
        self.note_pair_usage(pair)
        mode_path = self.pairs['%s-%s' % pair]
        mark_unknown = self.get_argument('markUnknown', default='yes') in ['yes', 'true', '1']
        url = self.get_argument('url')
        if not url.startswith('http'):
            url = 'http://' + url
        got304 = False
        cached = self.get_cached(pair, url)
        request = httpclient.HTTPRequest(url=url,
                                         # TODO: tweak timeouts:
                                         connect_timeout=20.0,
                                         request_timeout=20.0)

        try:
            response = yield httpclient.AsyncHTTPClient().fetch(request)
        except Exception as e:
            logging.info('%s exception has occurred' % e)
            self.send_error(404, explanation='{} on fetching url: {}'.format('Error 404', e))
            return
        try:
            response = yield httpclient.AsyncHTTPClient().fetch(request, self.handle_fetch)
        except httpclient.HTTPError as e:
            if e.code == 304:
                got304 = True
                logging.info('304, can use cache')
            else:
                logging.error(e)
                return
        if got304 and cached is not None:
            translation_catpipeline = translation.CatPipeline  # type: ignore
            translated = yield translation_catpipeline().translate(cached[1])
        else:
            if response.body is None:
                self.send_error(503, explanation='got an empty file on fetching url: {}'.format(url))
                return
            page = response.body  # type: bytes
            try:
                to_translate = self.html_to_text(page, url)
            except UnicodeDecodeError as e:
                logging.info("/translatePage '{}' gave UnicodeDecodeError {}".format(url, e))
                self.send_error(503, explanation="Couldn't decode (or detect charset/encoding of) {}".format(url))
                return
            before = self.log_before_translation()
            translated = yield translation.translate_html_mark_headings(to_translate, mode_path)
            self.log_after_translation(before, len(to_translate))
            self.set_cached(pair, url, translated, to_translate)
        self.send_response({
            'responseData': {
                'translatedText': self.maybe_strip_marks(mark_unknown, pair, translated),
            },
            'responseDetails': None,
            'responseStatus': 200,
        })
        retranslate = self.retranslate_cache(pair, url, cached)
        if got304 and retranslate is not None:
            logging.info('Retranslating {}'.format(url))
            translated = yield translation.translate_html_mark_headings(retranslate, mode_path)
            logging.info('Done retranslating {}'.format(url))
            self.set_cached(pair, url, translated, retranslate)


class TranslateDocHandler(TranslateHandler):
    mime_type_command = None

    def get_mime_type(self, f):
        commands = {
            'mimetype': lambda x: Popen(['mimetype', '-b', x], stdout=PIPE).communicate()[0].strip(),
            'xdg-mime': lambda x: Popen(['xdg-mime', 'query', 'filetype', x], stdout=PIPE).communicate()[0].strip(),
            'file': lambda x: Popen(['file', '--mime-type', '-b', x], stdout=PIPE).communicate()[0].strip(),
        }

        type_files = {
            'word/document.xml': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'ppt/presentation.xml': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'xl/workbook.xml': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }

        if not self.mime_type_command:
            for command in ['mimetype', 'xdg-mime', 'file']:
                if Popen(['which', command], stdout=PIPE).communicate()[0]:
                    TranslateDocHandler.mime_type_command = command
                    break

        mime_type = commands[self.mime_type_command](f).decode('utf-8')
        if mime_type == 'application/zip':
            with zipfile.ZipFile(f) as zf:
                for type_file in type_files:
                    if type_file in zf.namelist():
                        return type_files[type_file]

                if 'mimetype' in zf.namelist():
                    return zf.read('mimetype').decode('utf-8')

                return mime_type

        else:
            return mime_type

    # TODO: Some kind of locking. Although we can't easily re-use open
    # pairs here (would have to reimplement lots of
    # /usr/bin/apertium), we still want some limits on concurrent doc
    # translation.
    @gen.coroutine
    def get(self):
        try:
            l1, l2 = map(to_alpha3_code, self.get_argument('langpair').split('|'))
        except ValueError:
            self.send_error(400, explanation='That pair is invalid, use e.g. eng|spa')

        mark_unknown = self.get_argument('markUnknown', default='yes') in ['yes', 'true', '1']

        allowed_mime_types = {
            'text/plain': 'txt',
            'text/html': 'html-noent',
            'text/rtf': 'rtf',
            'application/rtf': 'rtf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
            # 'application/msword', 'application/vnd.ms-powerpoint', 'application/vnd.ms-excel'
            'application/vnd.oasis.opendocument.text': 'odt',
            'application/x-latex': 'latex',
            'application/x-tex': 'latex',
        }

        if '%s-%s' % (l1, l2) not in self.pairs:
            self.send_error(400, explanation='That pair is not installed')
            return

        body = self.request.files['file'][0]['body']
        if len(body) > 32E6:
            self.send_error(413, explanation='That file is too large')
            return

        with tempfile.NamedTemporaryFile() as temp_file:
            temp_file.write(body)
            temp_file.seek(0)

            mtype = self.get_mime_type(temp_file.name)
            if mtype not in allowed_mime_types:
                self.send_error(400, explanation='Invalid file type %s' % mtype)
                return
            self.request.headers['Content-Type'] = 'application/octet-stream'
            self.request.headers['Content-Disposition'] = 'attachment'
            with (yield self.doc_pipe_sem.acquire()):
                t = yield translation.translate_doc(temp_file,
                                                    allowed_mime_types[mtype],
                                                    self.pairs['%s-%s' % (l1, l2)],
                                                    mark_unknown)
            self.write(t)
            self.finish()


class TranslateRawHandler(TranslateHandler):
    """Assumes the pipeline itself outputs as JSON"""
    def send_response(self, data):
        translated_text = data.get('responseData', {}).get('translatedText', {})
        if translated_text == {}:
            super().send_response(data)
        else:
            self.log_vmsize()
            translated_text = data.get('responseData', {}).get('translatedText', {})
            self.set_header('Content-Type', 'application/json; charset=UTF-8')
            self._write_buffer.append(utf8(translated_text))
            self.finish()

    @gen.coroutine
    def get(self):
        pair = self.get_pair_or_error(self.get_argument('langpair'),
                                      len(self.get_argument('q', strip=False)))
        if pair is not None:
            pipeline = self.get_pipeline(pair)
            yield self.translate_and_respond(pair,
                                             pipeline,
                                             self.get_argument('q', strip=False),
                                             self.get_argument('markUnknown', default='yes'),
                                             nosplit=False,
                                             deformat=self.get_argument('deformat', default=True),
                                             reformat=False)


class AnalyzeHandler(BaseHandler):
    def postproc_text(self, in_text, result):
        lexical_units = remove_dot_from_deformat(in_text, re.findall(r'\^([^\$]*)\$([^\^]*)', result))
        return [(lu[0], lu[0].split('/')[0] + lu[1])
                for lu
                in lexical_units]

    @gen.coroutine
    def get(self):
        in_text = self.get_argument('q')
        in_mode = to_alpha3_code(self.get_argument('lang'))
        if in_mode in self.analyzers:
            [path, mode] = self.analyzers[in_mode]
            formatting = 'txt'
            commands = [['apertium', '-d', path, '-f', formatting, mode]]
            result = yield translation.translate_simple(in_text, commands)
            self.send_response(self.postproc_text(in_text, result))
        else:
            self.send_error(400, explanation='That mode is not installed')


class SpellerHandler(BaseHandler):
    @gen.coroutine
    def get(self):
        in_text = self.get_argument('q') + '*'
        in_mode = to_alpha3_code(self.get_argument('lang'))
        logging.info(in_text)
        logging.info(self.get_argument('lang'))
        logging.info(in_mode)
        logging.info(self.spellers)
        if in_mode in self.spellers:
            logging.info(self.spellers[in_mode])
            [path, mode] = self.spellers[in_mode]
            logging.info(path)
            logging.info(mode)
            formatting = 'none'
            commands = [['apertium', '-d', path, '-f', formatting, self.get_argument('lang') + '-tokenise']]
            result = yield translation.translate_simple(in_text, commands)

            tokens = streamparser.parse(result)
            units = []
            for token in tokens:
                if token.knownness == streamparser.known:
                    units.append({'token': token.wordform, 'known': True, 'sugg': []})
                else:
                    suggestion = []
                    commands = [['apertium', '-d', path, '-f', formatting, mode]]

                    result = yield translation.translate_simple(token.wordform, commands)
                    found_sugg = False
                    for line in result.splitlines():
                        if line.count('Corrections for'):
                            found_sugg = True
                            continue
                        if found_sugg and '\t' in line:
                            s, w = line.split('\t')
                            suggestion.append((s, w))

                    units.append({'token': token.wordform, 'known': False, 'sugg': suggestion})

            self.send_response(units)
        else:
            error_explanation = '{} on spellchecker mode: {}'.format('Error 404', 'Spelling mode for ' + in_mode + ' is not installed')
            self.send_error(404, explanation=error_explanation)


class GenerateHandler(BaseHandler):
    def preproc_text(self, in_text):
        lexical_units = re.findall(r'(\^[^\$]*\$[^\^]*)', in_text)
        if len(lexical_units) == 0:
            lexical_units = ['^%s$' % (in_text,)]
        return lexical_units, '[SEP]'.join(lexical_units)

    def postproc_text(self, lexical_units, result):
        return [(generation, lexical_units[i])
                for (i, generation)
                in enumerate(result.split('[SEP]'))]

    @gen.coroutine
    def get(self):
        in_text = self.get_argument('q')
        in_mode = to_alpha3_code(self.get_argument('lang'))
        if in_mode in self.generators:
            [path, mode] = self.generators[in_mode]
            formatting = 'none'
            commands = [['apertium', '-d', path, '-f', formatting, mode]]
            lexical_units, to_generate = self.preproc_text(in_text)
            result = yield translation.translate_simple(to_generate, commands)
            self.send_response(self.postproc_text(lexical_units, result))
        else:
            self.send_error(400, explanation='That mode is not installed')


class ListLanguageNamesHandler(BaseHandler):
    @tornado.web.asynchronous
    @gen.coroutine
    def get(self):
        locale_arg = self.get_argument('locale')
        languages_arg = self.get_argument('languages', default=None)

        if not self.lang_names:
            self.send_response({})
            return

        if locale_arg:
            if languages_arg:
                result = yield get_localized_languages(locale_arg, self.lang_names, languages=languages_arg.split(' '))
            else:
                result = yield get_localized_languages(locale_arg, self.lang_names)

            self.send_response(result)
            return

        if 'Accept-Language' in self.request.headers:
            locales = [locale.split(';')[0] for locale in self.request.headers['Accept-Language'].split(',')]

            for locale in locales:
                result = yield get_localized_languages(locale, self.lang_names)

                if result:
                    self.send_response(result)
                    return

        result = yield get_localized_languages('en', self.langNames)
        self.send_response(result)


class PerWordHandler(BaseHandler):
    @gen.coroutine
    def get(self):
        lang = to_alpha3_code(self.get_argument('lang'))
        modes = set(self.get_argument('modes').split(' '))
        query = self.get_argument('q')

        if not modes <= {'morph', 'biltrans', 'tagger', 'disambig', 'translate'}:
            self.send_error(400, explanation='Invalid mode argument')
            return

        def handle_output(output):
            """to_return = {}
            for mode in modes:
                to_return[mode] = outputs[mode]
            for mode in modes:
                to_return[mode] = {outputs[mode + '_inputs'][index]: output for (index, output) in enumerate(outputs[mode])}
            for mode in modes:
                to_return[mode] = [(outputs[mode + '_inputs'][index], output) for (index, output) in enumerate(outputs[mode])]
            for mode in modes:
                to_return[mode] = {'outputs': outputs[mode], 'inputs': outputs[mode + '_inputs']}
            self.send_response(to_return)"""

            if output is None:
                self.send_error(400, explanation='No output')
                return
            elif not output:
                self.send_error(408, explanation='Request timed out')
                return
            else:
                outputs, tagger_lexical_units, morph_lexical_units = output

            to_return = []

            for (index, lexical_unit) in enumerate(tagger_lexical_units if tagger_lexical_units else morph_lexical_units):
                unit_to_return = {}
                unit_to_return['input'] = strip_tags(lexical_unit.split('/')[0])
                for mode in modes:
                    unit_to_return[mode] = outputs[mode][index]
                to_return.append(unit_to_return)

            if self.get_argument('pos', default=None):
                requested_pos = int(self.get_argument('pos')) - 1
                current_pos = 0
                for unit in to_return:
                    input = unit['input']
                    current_pos += len(input.split(' '))
                    if requested_pos < current_pos:
                        self.send_response(unit)
                        return
            else:
                self.send_response(to_return)

        pool = Pool(processes=1)
        result = pool.apply_async(process_per_word, (self.analyzers, self.taggers, lang, modes, query))
        pool.close()

        @run_async_thread
        def worker(callback):
            try:
                callback(result.get(timeout=self.timeout))
            except TimeoutError:
                pool.terminate()
                callback(None)

        output = yield tornado.gen.Task(worker)
        handle_output(output)


class CoverageHandler(BaseHandler):
    @gen.coroutine
    def get(self):
        mode = to_alpha3_code(self.get_argument('lang'))
        text = self.get_argument('q')
        if not text:
            self.send_error(400, explanation='Missing q argument')
            return

        def handle_coverage(coverage):
            if coverage is None:
                self.send_error(408, explanation='Request timed out')
            else:
                self.send_response([coverage])

        if mode in self.analyzers:
            pool = Pool(processes=1)
            result = pool.apply_async(get_coverage, [text, self.analyzers[mode][0], self.analyzers[mode][1]])
            pool.close()

            @run_async_thread
            def worker(callback):
                try:
                    callback(result.get(timeout=self.timeout))
                except TimeoutError:
                    pool.terminate()
                    callback(None)

            coverage = yield tornado.gen.Task(worker)
            handle_coverage(coverage)
        else:
            self.send_error(400, explanation='That mode is not installed')


class IdentifyLangHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        text = self.get_argument('q')
        if not text:
            return self.send_error(400, explanation='Missing q argument')

        if cld2:
            cld_results = cld2.detect(text)
            if cld_results[0]:
                possible_langs = filter(lambda x: x[1] != 'un', cld_results[2])
                self.send_response({to_alpha3_code(possible_lang[1]): possible_lang[2] for possible_lang in possible_langs})
            else:
                self.send_response({'nob': 100})  # TODO: Some more reasonable response
        else:
            def handle_coverages(coverages):
                self.send_response(coverages)

            pool = Pool(processes=1)
            result = pool.apply_async(get_coverages, [text, self.analyzers], {'penalize': True}, callback=handle_coverages)
            pool.close()
            try:
                result.get(timeout=self.timeout)
                # coverages = result.get(timeout=self.timeout)
                # TODO: Coverages are not actually sent!!
            except TimeoutError:
                self.send_error(408, explanation='Request timed out')
                pool.terminate()


class GetLocaleHandler(BaseHandler):
    @tornado.web.asynchronous
    def get(self):
        if 'Accept-Language' in self.request.headers:
            locales = [locale.split(';')[0] for locale in self.request.headers['Accept-Language'].split(',')]
            self.send_response(locales)
        else:
            self.send_error(400, explanation='Accept-Language missing from request headers')


class SuggestionHandler(BaseHandler):
    wiki_session = None  # type: Optional[requests.Session]
    wiki_edit_token = None
    SUGGEST_URL = None
    recaptcha_secret = None

    @gen.coroutine
    def get(self):
        self.send_error(405, explanation='GET request not supported')

    @gen.coroutine
    def post(self):
        context = self.get_argument('context', None)
        word = self.get_argument('word', None)
        new_word = self.get_argument('newWord', None)
        langpair = self.get_argument('langpair', None)
        recap = self.get_argument('g-recaptcha-response', None)

        if not new_word:
            self.send_error(400, explanation='A suggestion is required')
            return

        if not recap:
            self.send_error(400, explanation='The ReCAPTCHA is required')
            return

        if not all([context, word, langpair, new_word, recap]):
            self.send_error(400, explanation='All arguments were not provided')
            return

        logging.info('Suggestion (%s): Context is %s \n Word: %s ; New Word: %s ' % (langpair, context, word, new_word))
        logging.info('Now verifying ReCAPTCHA.')

        if not self.recaptcha_secret:
            logging.error('No ReCAPTCHA secret provided!')
            self.send_error(400, explanation='Server not configured correctly for suggestions')
            return

        if recap == BYPASS_TOKEN:
            logging.info('Adding data to wiki with bypass token')
        else:
            # for nginx or when behind a proxy
            x_real_ip = self.request.headers.get('X-Real-IP')
            user_ip = x_real_ip or self.request.remote_ip
            payload = {
                'secret': self.recaptcha_secret,
                'response': recap,
                'remoteip': user_ip,
            }
            recap_request = self.wiki_session.post(RECAPTCHA_VERIFICATION_URL, data=payload)
            if recap_request.json()['success']:
                logging.info('ReCAPTCHA verified, adding data to wiki')
            else:
                logging.info('ReCAPTCHA verification failed, stopping')
                self.send_error(400, explanation='ReCAPTCHA verification failed')
                return

        from util import add_suggestion
        data = {
            'context': context, 'langpair': langpair,
            'word': word, 'newWord': new_word,
        }
        result = add_suggestion(self.wiki_session,
                                self.SUGGEST_URL, self.wiki_edit_token,
                                data)

        if result:
            self.send_response({
                'responseData': {
                    'status': 'Success',
                },
                'responseDetails': None,
                'responseStatus': 200,
            })
        else:
            logging.info('Page update failed, trying to get new edit token')
            self.wiki_edit_token = wiki_get_token(
                SuggestionHandler.wiki_session, 'edit', 'info|revisions')
            logging.info('Obtained new edit token. Trying page update again.')
            result = add_suggestion(self.wiki_session,
                                    self.SUGGEST_URL, self.wiki_edit_token,
                                    data)
            if result:
                self.send_response({
                    'responseData': {
                        'status': 'Success',
                    },
                    'responseDetails': None,
                    'responseStatus': 200,
                })
            else:
                self.send_error(400, explanation='Page update failed')


class PipeDebugHandler(BaseHandler):
    @gen.coroutine
    def get(self):
        to_translate = self.get_argument('q')

        try:
            l1, l2 = map(to_alpha3_code, self.get_argument('langpair').split('|'))
        except ValueError:
            self.send_error(400, explanation='That pair is invalid, use e.g. eng|spa')

        mode_path = self.pairs['%s-%s' % (l1, l2)]
        try:
            _, commands = translation.parse_mode_file(mode_path)
        except Exception:
            self.send_error(500)
            return

        res = yield translation.translate_pipeline(to_translate, commands)
        if self.get_status() != 200:
            self.send_error(self.get_status())
            return

        output, pipeline = res

        self.send_response({
            'responseData': {'output': output, 'pipeline': pipeline},
            'responseDetails': None,
            'responseStatus': 200,
        })


def setup_handler(
    port, pairs_path, nonpairs_path, lang_names, missing_freqs_path, timeout,
    max_pipes_per_pair, min_pipes_per_pair, max_users_per_pipe, max_idle_secs,
    restart_pipe_after, max_doc_pipes, verbosity=0, scale_mt_logs=False, memory=1000,
):

    global missing_freqs_db
    if missing_freqs_path:
        missing_freqs_db = missingdb.MissingDb(missing_freqs_path, memory)

    handler = BaseHandler
    handler.lang_names = lang_names
    handler.timeout = timeout
    handler.max_pipes_per_pair = max_pipes_per_pair
    handler.min_pipes_per_pair = min_pipes_per_pair
    handler.max_users_per_pipe = max_users_per_pipe
    handler.max_idle_secs = max_idle_secs
    handler.restart_pipe_after = restart_pipe_after
    handler.scale_mt_logs = scale_mt_logs
    handler.verbosity = verbosity
    handler.doc_pipe_sem = Semaphore(max_doc_pipes)

    modes = search_path(pairs_path, verbosity=verbosity)
    if nonpairs_path:
        src_modes = search_path(nonpairs_path, include_pairs=False, verbosity=verbosity)
        for mtype in modes:
            modes[mtype] += src_modes[mtype]

    for mtype in modes:
        logging.info('%d %s modes found' % (len(modes[mtype]), mtype))

    for path, lang_src, lang_trg in modes['pair']:
        handler.pairs['%s-%s' % (lang_src, lang_trg)] = path
    for dirpath, modename, lang_pair in modes['analyzer']:
        handler.analyzers[lang_pair] = (dirpath, modename)
    for dirpath, modename, lang_pair in modes['generator']:
        handler.generators[lang_pair] = (dirpath, modename)
    for dirpath, modename, lang_pair in modes['tagger']:
        handler.taggers[lang_pair] = (dirpath, modename)
    for dirpath, modename, lang_src in modes['spell']:
        if (any(lang_src == elem[2] for elem in modes['tokenise'])):
            handler.spellers[lang_src] = (dirpath, modename)

    handler.init_pairs_graph()
    handler.init_paths()


def check_utf8():
    locale_vars = ['LANG', 'LC_ALL']
    u8 = re.compile('UTF-?8', re.IGNORECASE)
    if not any(re.search(u8, os.environ.get(key, '')) for key in locale_vars):
        logging.fatal('apy.py: APy needs a UTF-8 locale, please set LANG or LC_ALL')
        sys.exit(1)


def apply_config(args, parser, apy_section):
    for (name, value) in vars(args).items():
        if name in apy_section:
            # Get default from private variables of argparse
            default = None
            for action in parser._actions:  # type: ignore
                if action.dest == name:
                    default = action.default

            # Try typecasting string to type of argparse argument
            fn = type(value)
            res = None
            try:
                if fn is None:
                    if apy_section[name] == 'None':
                        res = None
                    else:
                        res = apy_section[name]
                elif fn is bool:
                    if apy_section[name] == 'False':
                        res = False
                    elif apy_section[name] == 'True':
                        res = True
                    else:
                        res = bool(apy_section[name])
                else:
                    res = fn(apy_section[name])
            except ValueError:
                print('Warning: Unable to cast {} to expected type'.format(apy_section[name]))

            # only override is value (argument) is default
            if res is not None and value == default:
                setattr(args, name, res)


def parse_args(cli_args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description='Apertium APY -- API server for machine translation and language analysis')
    parser.add_argument('pairs_path', help='path to Apertium installed pairs (all modes files in this path are included)')
    parser.add_argument('-s', '--nonpairs-path', help='path to Apertium tree (only non-translator debug modes are included from this path)')
    parser.add_argument('-l', '--lang-names',
                        help='path to localised language names sqlite database (default = langNames.db)', default='langNames.db')
    parser.add_argument('-f', '--missing-freqs', help='path to missing word frequency sqlite database (default = None)', default=None)
    parser.add_argument('-p', '--port', help='port to run server on (default = 2737)', type=int, default=2737)
    parser.add_argument('-c', '--ssl-cert', help='path to SSL Certificate', default=None)
    parser.add_argument('-k', '--ssl-key', help='path to SSL Key File', default=None)
    parser.add_argument('-t', '--timeout', help='timeout for requests (default = 10)', type=int, default=10)
    parser.add_argument('-j', '--num-processes',
                        help='number of processes to run (default = 1; use 0 to run one http server per core, '
                             'where each http server runs all available language pairs)',
                        nargs='?', type=int, default=1)
    parser.add_argument('-d', '--daemon',
                        help='daemon mode: redirects stdout and stderr to files apertium-apy.log and apertium-apy.err; use with --log-path',
                        action='store_true')
    parser.add_argument('-P', '--log-path', help='path to log output files to in daemon mode; defaults to local directory', default='./')
    parser.add_argument('-i', '--max-pipes-per-pair',
                        help='how many pipelines we can spin up per language pair (default = 1)', type=int, default=1)
    parser.add_argument('-n', '--min-pipes-per-pair',
                        help='when shutting down pipelines, keep at least this many open per language pair (default = 0)',
                        type=int, default=0)
    parser.add_argument('-u', '--max-users-per-pipe',
                        help='how many concurrent requests per pipeline before we consider spinning up a new one (default = 5)',
                        type=int, default=5)
    parser.add_argument('-m', '--max-idle-secs',
                        help='if specified, shut down pipelines that have not been used in this many seconds', type=int, default=0)
    parser.add_argument('-r', '--restart-pipe-after',
                        help='restart a pipeline if it has had this many requests (default = 1000)', type=int, default=1000)
    parser.add_argument('-v', '--verbosity', help='logging verbosity', type=int, default=0)
    parser.add_argument('-V', '--version', help='show APY version', action='version', version='%(prog)s version ' + __version__)
    parser.add_argument('-S', '--scalemt-logs', help='generates ScaleMT-like logs; use with --log-path; disables', action='store_true')
    parser.add_argument('-M', '--unknown-memory-limit',
                        help='keeps unknown words in memory until a limit is reached; use with --missing-freqs (default = 1000)',
                        type=int, default=1000)
    parser.add_argument('-T', '--stat-period-max-age',
                        help='How many seconds back to keep track request timing stats (default = 3600)', type=int, default=3600)
    parser.add_argument('-wp', '--wiki-password', help='Apertium Wiki account password for SuggestionHandler', default=None)
    parser.add_argument('-wu', '--wiki-username', help='Apertium Wiki account username for SuggestionHandler', default=None)
    parser.add_argument('-b', '--bypass-token', help='ReCAPTCHA bypass token', action='store_true')
    parser.add_argument('-rs', '--recaptcha-secret', help='ReCAPTCHA secret for suggestion validation', default=None)
    parser.add_argument('-md', '--max-doc-pipes',
                        help='how many concurrent document translation pipelines we allow (default = 3)', type=int, default=3)
    parser.add_argument('-C', '--config', help='Configuration file to load options from', default=None)

    args = parser.parse_args(cli_args)

    if args.config:
        conf = configparser.ConfigParser()
        conf.read(args.config)

        if not os.path.isfile(args.config):
            logging.warning('Configuration file does not exist,'
                            ' please see http://wiki.apertium.org/'
                            'wiki/Apy#Configuration for more information')
        elif 'APY' not in conf:
            logging.warning('Configuration file does not have APY section,'
                            ' please see http://wiki.apertium.org/'
                            'wiki/Apy#Configuration for more information')
        else:
            logging.info('Using configuration file ' + args.config)
            apy_section = conf['APY']
            apply_config(args, parser, apy_section)

    return args


def setup_application(args):
    if args.daemon:
        # regular content logs are output stderr
        # python messages are mostly output to stdout
        # hence swapping the filenames?
        sys.stderr = open(os.path.join(args.log_path, 'apertium-apy.log'), 'a+')
        sys.stdout = open(os.path.join(args.log_path, 'apertium-apy.err'), 'a+')

    if args.scalemt_logs:
        logger = logging.getLogger('scale-mt')
        logger.propagate = False
        smtlog = os.path.join(args.log_path, 'ScaleMTRequests.log')
        logging_handler = logging_handlers.TimedRotatingFileHandler(smtlog, 'midnight', 0)
        # internal attribute, should not use
        logging_handler.suffix = '%Y-%m-%d'  # type: ignore
        logger.addHandler(logging_handler)

        # if scalemt_logs is enabled, disable tornado.access logs
        if args.daemon:
            logging.getLogger('tornado.access').propagate = False

    if args.stat_period_max_age:
        BaseHandler.STAT_PERIOD_MAX_AGE = timedelta(0, args.stat_period_max_age, 0)

    setup_handler(args.port, args.pairs_path, args.nonpairs_path, args.lang_names, args.missing_freqs, args.timeout,
                  args.max_pipes_per_pair, args.min_pipes_per_pair, args.max_users_per_pipe, args.max_idle_secs,
                  args.restart_pipe_after, args.max_doc_pipes, args.verbosity, args.scalemt_logs, args.unknown_memory_limit)

    handlers = [
        (r'/', RootHandler),
        (r'/list', ListHandler),
        (r'/listPairs', ListHandler),
        (r'/stats', StatsHandler),
        (r'/translate', TranslateHandler),
        (r'/translateChain', TranslateChainHandler),
        (r'/translateDoc', TranslateDocHandler),
        (r'/translatePage', TranslatePageHandler),
        (r'/translateRaw', TranslateRawHandler),
        (r'/analy[sz]e', AnalyzeHandler),
        (r'/generate', GenerateHandler),
        (r'/listLanguageNames', ListLanguageNamesHandler),
        (r'/perWord', PerWordHandler),
        (r'/calcCoverage', CoverageHandler),
        (r'/identifyLang', IdentifyLangHandler),
        (r'/getLocale', GetLocaleHandler),
        (r'/pipedebug', PipeDebugHandler),
    ]

    if streamparser:
        handlers.append((r'/speller', SpellerHandler))

    if all([args.wiki_username, args.wiki_password]) and requests:
        logging.info('Logging into Apertium Wiki with username %s' % args.wiki_username)

        SuggestionHandler.SUGGEST_URL = 'User:' + args.wiki_username
        SuggestionHandler.recaptcha_secret = args.recaptcha_secret
        SuggestionHandler.wiki_session = requests.Session()
        SuggestionHandler.auth_token = wiki_login(
            SuggestionHandler.wiki_session,
            args.wiki_username,
            args.wiki_password)
        SuggestionHandler.wiki_edit_token = wiki_get_token(
            SuggestionHandler.wiki_session, 'edit', 'info|revisions')

        handlers.append((r'/suggest', SuggestionHandler))

    return tornado.web.Application(handlers)


def main():
    check_utf8()
    logging.getLogger().setLevel(logging.INFO)
    args = parse_args()
    enable_pretty_logging()

    if not cld2:
        logging.warning('Unable to import CLD2, continuing using naive method of language detection')

    if not chardet:
        logging.warning('Unable to import chardet, assuming utf-8 encoding for all websites')

    if not streamparser:
        logging.warning('Apertium streamparser not installed, spelling handler disabled')

    if not requests:
        logging.warning('requests not installed, suggestions disabled')

    if args.bypass_token:
        logging.info('reCaptcha bypass for testing: %s' % BYPASS_TOKEN)

    application = setup_application(args)

    if args.ssl_cert and args.ssl_key:
        http_server = tornado.httpserver.HTTPServer(application, ssl_options={
            'certfile': args.ssl_cert,
            'keyfile': args.ssl_key,
        })
        logging.info('Serving at https://localhost:%s' % args.port)
    else:
        http_server = tornado.httpserver.HTTPServer(application)
        logging.info('Serving at http://localhost:%s' % args.port)

    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)

    http_server.bind(args.port)
    http_server.start(args.num_processes)

    loop = tornado.ioloop.IOLoop.instance()
    wd = systemd.setup_watchdog()
    if wd is not None:
        wd.systemd_ready()
        logging.info('Initialised systemd watchdog, pinging every {}s'.format(1000 * wd.period))
        tornado.ioloop.PeriodicCallback(wd.watchdog_ping, 1000 * wd.period, loop).start()
    loop.start()


if __name__ == '__main__':
    main()
