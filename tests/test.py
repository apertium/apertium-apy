#!/usr/bin/env python3
# coding=utf-8

import json
import logging
import os
import shlex
import subprocess
import sys
import time
import unittest
import urllib.request

from tornado.log import enable_pretty_logging
from tornado.testing import AsyncHTTPTestCase

apy_folder = os.path.join(os.path.abspath(os.path.dirname(__file__)), '../apertium_apy')
sys.path.append(apy_folder)
from apy import check_utf8, parse_args, setup_application  # noqa: E402

logging.getLogger().setLevel(logging.DEBUG)

PORT = int(os.environ.get('APY_PORT', '2737'))  # TODO: consider tornado.testing.bind_unused_port and/or validating input
NONPAIRS = os.environ.get('NONPAIRS', '/l/a/languages')
INSTALLEDPAIRS = os.environ.get('INSTALLEDPAIRS', '/usr/share/apertium')

MAX_STARTUP_SECONDS = 10

check_utf8()
cli_args = shlex.split('-p {} -j1 -i3 -u1 -n1 -m3 -s "{}"  -- "{}"'.format(PORT, NONPAIRS, INSTALLEDPAIRS))
args = parse_args(cli_args=cli_args)
enable_pretty_logging()
application = setup_application(args)

server_handle = None


def setUpModule():  # noqa: N802
    global server_handle
    server_handle = subprocess.Popen([os.path.join(apy_folder, 'apy.py')] + cli_args)  # TODO: swallow output and print on error?

    started = False
    waited = 0
    while not started and waited < MAX_STARTUP_SECONDS:
        try:
            urllib.request.urlopen('http://localhost:{}'.format(PORT))  # TODO: consider using sockets instead
            started = True
            logging.info('APy started on port {} with PID {}'.format(PORT, server_handle.pid))
        except urllib.error.URLError:  # type: ignore
            print('.', end='')
            waited += 1
            time.sleep(1)

    if not started:
        raise Exception('Starting APy failed after waiting for {} seconds'.format(MAX_STARTUP_SECONDS))


def tearDownModule():  # noqa: N802
    if server_handle:
        server_handle.kill()


class BaseTestCase(AsyncHTTPTestCase):
    def get_app(self):
        return application

    def get_http_port(self):
        return PORT

    def fetch_json(self, *args, **kwargs):
        expect_success = kwargs.pop('expect_success', True)
        response = self.fetch(*args, **kwargs)
        if expect_success:
            self.assertEqual(response.code, 200)
        return json.loads(response.body.decode('utf-8'))

# TODO: split the handler tests into another file


class TestListHandler(BaseTestCase):
    def test_list_pairs(self):
        response = self.fetch_json('/list?q=pairs')
        self.assertTrue('responseData' in response)
        self.assertTrue('responseDetails' in response)
        self.assertEqual(response['responseStatus'], 200)
        print(response)  # TODO: validate more

    def test_list_generators(self):
        response = self.fetch_json('/list?q=generators')
        expect = {'nno': 'nno-gener'}
        self.assertTrue(response.items() >= expect.items(), '{} is missing {}'.format(response, expect))

    def test_list_analyzers(self):
        response = self.fetch_json('/list?q=analysers')
        expect = {'nno': 'nno-morph'}
        self.assertTrue(response.items() >= expect.items(), '{} is missing {}'.format(response, expect))


class TestTranslateHandler(BaseTestCase):
    def fetch_translation(self, query, pair, **kwargs):
        expect_success = kwargs.get('expect_success', True)
        response = self.fetch_json('/translate?q={}&langpair={}'.format(query, pair), **kwargs)
        if expect_success:
            self.assertEqual(response['responseStatus'], 200)
        return response

    def test_valid_pair(self):
        response = self.fetch_translation('government', 'eng|spa')
        self.assertEqual(response['responseData']['translatedText'], 'Gobierno')

    def test_valid_pair_2(self):  # TODO: a better name (why are we testing both?)
        response = self.fetch_translation('ja', 'sme|nob')
        self.assertEqual(response['responseData']['translatedText'], 'og')

    def test_invalid_pair(self):
        response = self.fetch_translation('ignored', 'typomode', expect_success=False)
        self.assertDictEqual(response, {
            'status': 'error',
            'code': 400,
            'message': 'Bad Request',
            'explanation': 'That pair is invalid, use e.g. eng|spa',
        })

    def test_missing_pair(self):
        response = self.fetch_translation('ignored', 'non|mod', expect_success=False)
        self.assertDictEqual(response, {
            'status': 'error',
            'code': 400,
            'message': 'Bad Request',
            'explanation': 'That pair is not installed',
        })


class TestAnalyzeHandler(BaseTestCase):
    def test_analyze(self):
        response = self.fetch_json('/analyze?q=ikkje&lang=nno')
        self.assertEqual(response, [['ikkje/ikkje<adv>', 'ikkje']])


class TestGenerateHandler(BaseTestCase):
    def test_generate(self):
        response = self.fetch_json('/generate?q=ja<ij>&lang=nno')
        self.assertEqual(response, [['ja', '^ja<ij>$']])

    def test_generate_2(self):  # TODO: a better name
        response = self.fetch_json('/generate?q=^ja<ij>$&lang=nno')
        self.assertEqual(response, [['ja', '^ja<ij>$']])


if __name__ == '__main__':
    unittest.main()
