import heapq
import logging
import re
import time
from datetime import datetime

from tornado import gen
import tornado.iostream
import asyncio

from apertium_apy import missing_freqs_db  # noqa: F401
from apertium_apy.handlers.base import BaseHandler
from apertium_apy.keys import ApiKeys
from apertium_apy.utils import to_alpha3_code, scale_mt_log
from apertium_apy.utils.translation import parse_mode_file, make_pipeline, FlushingPipeline, SimplePipeline
from typing import Union


class TranslationInfo:
    def __init__(self, handler):
        self.langpair = handler.get_argument('langpair')
        self.key = handler.get_argument('key', default='null')
        self.ip = handler.request.headers.get('X-Real-IP', handler.request.remote_ip)
        self.referer = handler.request.headers.get('Referer', 'null')


class TranslateHandler(BaseHandler):
    unknown_mark_re = re.compile(r'[*]([^.,;:\t\* ]+)')
    api_keys = None

    def __init__(self, application, request, **kwargs):
        super().__init__(application, request, **kwargs)

    @property
    def mark_unknown(self):
        return self.get_argument('markUnknown', default='yes').lower() in ['yes', 'true', '1']

    def note_pair_usage(self, pair):
        self.stats.usecount[pair] = 1 + self.stats.usecount.get(pair, 0)

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
        if pipe.stuck:
            logging.info('A pipe for pair %s-%s seems stuck, scheduling restart',
                         pair[0], pair[1])
            return True
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
            self.pipeline_cmds[(l1, l2)] = parse_mode_file(mode_path)
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
            p = make_pipeline(self.get_pipe_cmds(l1, l2), self.timeout)
            heapq.heappush(self.pipelines[pair], p)
        return self.pipelines[pair][0]

    def log_before_translation(self):
        return datetime.now()

    def log_after_translation(self, before, length):
        after = datetime.now()
        if self.scale_mt_logs:
            t_info = TranslationInfo(self)
            key = self.get_api_key(t_info.key)
            scale_mt_log(self.get_status(), after - before, t_info, key, length)

        if self.get_status() == 200:
            timings = self.stats.timing
            oldest = timings[0][0] if timings else datetime.now()
            if datetime.now() - oldest > self.stat_period_max_age:
                self.stats.timing.pop(0)
            self.stats.timing.append(
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
        try:
            translated = yield pipeline.translate(to_translate, nosplit, deformat, reformat)
            self.log_after_translation(before, len(to_translate))
            self.send_response({
                'responseData': {
                    'translatedText': self.maybe_strip_marks(mark_unknown, pair, translated),
                },
                'responseDetails': None,
                'responseStatus': 200,
            })
        except asyncio.TimeoutError as e:
            logging.warning('Translation error in pair %s-%s: %s', pair[0], pair[1], e)
            pipeline.stuck = True
            self.send_error(503, explanation='internal error')
        except tornado.iostream.StreamClosedError as e:
            logging.warning('Translation error in pair %s-%s: %s', pair[0], pair[1], e)
            pipeline.stuck = True
            self.send_error(503, explanation='internal error')
        self.clean_pairs()

    @gen.coroutine
    def get(self):
        pair = self.get_pair_or_error(self.get_argument('langpair'),
                                      len(self.get_argument('q')))
        if pair is not None:
            pipeline = self.get_pipeline(pair)  # type: Union[FlushingPipeline, SimplePipeline]
            deformat, reformat = self.get_format()
            yield self.translate_and_respond(pair,
                                             pipeline,
                                             self.get_argument('q'),
                                             self.get_argument('markUnknown', default='yes'),
                                             nosplit=False,
                                             deformat=deformat,
                                             reformat=reformat)

    @classmethod
    def get_api_key(cls, key):
        if not cls.api_keys:
            cls.api_keys = ApiKeys(cls.api_keys_conf)

        return cls.api_keys.get_key(key)
