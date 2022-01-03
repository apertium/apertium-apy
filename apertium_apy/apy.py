#!/usr/bin/env python3
# coding=utf-8
# -*- indent-tabs-mode: nil -*-

__author__ = 'Kevin Brubeck Unhammer, Sushain K. Cherivirala'
__copyright__ = 'Copyright 2013--2020, Kevin Brubeck Unhammer, Sushain K. Cherivirala'
__credits__ = ['Kevin Brubeck Unhammer', 'Sushain K. Cherivirala', 'Jonathan North Washington', 'Xavi Ivars', 'Shardul Chiplunkar']
__license__ = 'GPLv3'
__status__ = 'Beta'
__version__ = '0.12.0'

import argparse
import configparser
import logging
import os
import re
import signal
import sys
from importlib import util as importlib_util
from datetime import timedelta
from logging import handlers as logging_handlers  # type: ignore

import tornado
import tornado.httpserver
import tornado.httputil
import tornado.iostream
import tornado.process
import tornado.web
from tornado.locks import Semaphore
from tornado.log import enable_pretty_logging

from typing import Sequence, Iterable, Type, List, Tuple, Any  # noqa: F401

from apertium_apy import BYPASS_TOKEN, missing_freqs_db  # noqa: F401
from apertium_apy import missingdb
from apertium_apy import systemd
from apertium_apy.mode_search import search_path, search_prefs
from apertium_apy.utils.wiki import wiki_login, wiki_get_token

from apertium_apy.handlers import (
    AnalyzeHandler,
    BaseHandler,
    CoverageHandler,
    GenerateHandler,
    IdentifyLangHandler,
    ListHandler,
    ListLanguageNamesHandler,
    PerWordHandler,
    PipeDebugHandler,
    SpellerHandler,
    StatsHandler,
    SuggestionHandler,
    TranslateChainHandler,
    TranslateDocHandler,
    TranslateHandler,
    PairPrefsHandler,
    TranslateRawHandler,
    TranslateWebpageHandler,
)


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


class RootHandler(BaseHandler):
    def get(self):
        self.render('../index.html')


class GetLocaleHandler(BaseHandler):
    def get(self):
        if 'Accept-Language' in self.request.headers:
            locales = [locale.split(';')[0] for locale in self.request.headers['Accept-Language'].split(',')]
            self.send_response(locales)
        else:
            self.send_error(400, explanation='Accept-Language missing from request headers')


def setup_handler(
    pairs_path, nonpairs_path, lang_names, missing_freqs_path, timeout,
    max_pipes_per_pair, min_pipes_per_pair, max_users_per_pipe, max_idle_secs,
    restart_pipe_after, max_doc_pipes, verbosity=0, scale_mt_logs=False,
    memory=1000, apy_keys=None,
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
    handler.api_keys_conf = apy_keys

    modes = search_path(pairs_path, verbosity=verbosity)
    if nonpairs_path:
        src_modes = search_path(nonpairs_path, include_pairs=False, verbosity=verbosity)
        for mtype in modes:
            modes[mtype] += src_modes[mtype]
    handler.pairprefs = search_prefs(pairs_path)

    for mtype in modes:
        logging.info('%d %s modes found', len(modes[mtype]), mtype)

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
    parser.add_argument('-ak', '--api-keys', help='Configuration file to load API keys', default=None)

    args = parser.parse_args(cli_args)

    if args.config:
        conf = configparser.ConfigParser()
        conf.read(args.config)

        if not os.path.isfile(args.config):
            logging.warning('Configuration file does not exist,'
                            ' please see https://wiki.apertium.org/'
                            'wiki/Apy#Configuration for more information')
        elif 'APY' not in conf:
            logging.warning('Configuration file does not have APY section,'
                            ' please see https://wiki.apertium.org/'
                            'wiki/Apy#Configuration for more information')
        else:
            logging.info('Using configuration file ' + args.config)
            apy_section = conf['APY']
            apply_config(args, parser, apy_section)

    return args


def setup_application(args):
    if args.stat_period_max_age:
        BaseHandler.stat_period_max_age = timedelta(0, args.stat_period_max_age, 0)

    setup_handler(args.pairs_path, args.nonpairs_path, args.lang_names, args.missing_freqs, args.timeout,
                  args.max_pipes_per_pair, args.min_pipes_per_pair, args.max_users_per_pipe, args.max_idle_secs,
                  args.restart_pipe_after, args.max_doc_pipes, args.verbosity, args.scalemt_logs,
                  args.unknown_memory_limit, args.api_keys)

    handlers = [
        (r'/', RootHandler),
        (r'/list', ListHandler),
        (r'/listPairs', ListHandler),
        (r'/stats', StatsHandler),
        (r'/pairprefs', PairPrefsHandler),
        (r'/translate', TranslateHandler),
        (r'/translateChain', TranslateChainHandler),
        (r'/translateDoc', TranslateDocHandler),
        (r'/translatePage', TranslateWebpageHandler),
        (r'/translateRaw', TranslateRawHandler),
        (r'/analy[sz]e', AnalyzeHandler),
        (r'/generate', GenerateHandler),
        (r'/listLanguageNames', ListLanguageNamesHandler),
        (r'/perWord', PerWordHandler),
        (r'/calcCoverage', CoverageHandler),
        (r'/identifyLang', IdentifyLangHandler),
        (r'/getLocale', GetLocaleHandler),
        (r'/pipedebug', PipeDebugHandler),
    ]  # type: List[Tuple[str, Type[tornado.web.RequestHandler]]]

    if importlib_util.find_spec('streamparser'):
        handlers.append((r'/speller', SpellerHandler))

    if all([args.wiki_username, args.wiki_password]) and importlib_util.find_spec('requests'):
        import requests
        logging.info('Logging into Apertium Wiki with username %s', args.wiki_username)

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

    # TODO: fix mypy. Application expects List but List is invariant and we use subclasses
    return tornado.web.Application(handlers)  # type:ignore


def setup_logging(args):
    if args.daemon:
        # regular content logs are output stderr
        # python messages are mostly output to stdout
        # hence swapping the filenames?
        logfile = os.path.join(args.log_path, 'apertium-apy.log')
        errfile = os.path.join(args.log_path, 'apertium-apy.err')
        sys.stderr = open(logfile, 'a+')
        sys.stdout = open(errfile, 'a+')
        logging.basicConfig(filename=logfile, filemode='a')  # NB. Needs to happen *before* we use logs for anything
        logging.getLogger().setLevel(logging.INFO)
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
    enable_pretty_logging()


def main():
    check_utf8()
    args = parse_args()
    setup_logging(args)  # before we start logging anything!

    if importlib_util.find_spec('cld2full') is None:
        logging.warning('Unable to import CLD2, continuing using naive method of language detection')

    if importlib_util.find_spec('chardet') is None:
        logging.warning('Unable to import chardet, assuming utf-8 encoding for all websites')

    if importlib_util.find_spec('streamparser') is None:
        logging.warning('Apertium streamparser not installed, spelling handler disabled')

    if importlib_util.find_spec('requests') is None:
        logging.warning('requests not installed, suggestions disabled')

    if args.bypass_token:
        logging.info('reCaptcha bypass for testing: %s', BYPASS_TOKEN)

    application = setup_application(args)

    if args.ssl_cert and args.ssl_key:
        http_server = tornado.httpserver.HTTPServer(application, ssl_options={
            'certfile': args.ssl_cert,
            'keyfile': args.ssl_key,
        })
        logging.info('Serving on all interfaces/families, e.g. https://localhost:%s', args.port)
    else:
        http_server = tornado.httpserver.HTTPServer(application)
        logging.info('Serving on all interfaces/families, e.g. http://localhost:%s', args.port)

    signal.signal(signal.SIGTERM, sig_handler)
    signal.signal(signal.SIGINT, sig_handler)

    http_server.bind(args.port)
    http_server.start(args.num_processes)

    loop = tornado.ioloop.IOLoop.instance()
    wd = systemd.setup_watchdog()
    if wd is not None:
        wd.systemd_ready()
        logging.info('Initialised systemd watchdog, pinging every {}s'.format(1000 * wd.period))
        tornado.ioloop.PeriodicCallback(wd.watchdog_ping, 1000 * wd.period).start()
    loop.start()


if __name__ == '__main__':
    main()
