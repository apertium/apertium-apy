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
import urllib.parse

from tornado.log import enable_pretty_logging
from tornado.testing import AsyncHTTPTestCase

base_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), '..')
sys.path.append(base_path)
from apertium_apy.apy import check_utf8, parse_args, setup_application  # noqa: E402

logging.getLogger().setLevel(logging.DEBUG)

PORT = int(os.environ.get('APY_PORT', '2737'))  # TODO: consider tornado.testing.bind_unused_port and/or validating input
NONPAIRS = os.environ.get('NONPAIRS', '/l/a/languages')
INSTALLEDPAIRS = os.environ.get('INSTALLEDPAIRS', '/usr/share/apertium')

MAX_STARTUP_SECONDS = 10

check_utf8()
cli_args = shlex.split('-p {} -v2 -j1 -i3 -u1 -n1 -m3 -s "{}"  -- "{}"'.format(PORT, NONPAIRS, INSTALLEDPAIRS))
args = parse_args(cli_args=cli_args)
enable_pretty_logging()
application = setup_application(args)

server_handle = None


def setUpModule():  # noqa: N802
    global server_handle
    coverage_cli_args = shlex.split('coverage run --branch --source apertium_apy') + [os.path.join(base_path, 'servlet.py')] + cli_args
    server_handle = subprocess.Popen(coverage_cli_args)  # TODO: swallow output and print on error?

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
        server_handle.terminate()  # don't kill so that coverage works


class BaseTestCase(AsyncHTTPTestCase):
    def get_app(self):
        return application

    def get_http_port(self):
        return PORT

    def fetch(self, path, params={}, **kwargs):
        if params:
            method = kwargs.get('method', 'GET')
            if method == 'GET':
                path += '?' + urllib.parse.urlencode(params)
            elif method == 'POST':
                kwargs['body'] = kwargs.get('body', '') + urllib.parse.urlencode(params)

        return super().fetch(path, **kwargs)

    def fetch_json(self, path, params={}, **kwargs):
        expect_success = kwargs.pop('expect_success', True)
        response = self.fetch(path, params=params, **kwargs)

        body = None
        if expect_success:
            self.assertEqual(response.code, 200, msg='Request unsuccessful: {}'.format(response.body))

            body = json.loads(response.body.decode('utf-8'))
            if 'responseStatus' in body:
                self.assertEqual(body['responseStatus'], 200)

        return body or json.loads(response.body.decode('utf-8'))

# TODO: split the handler tests into another file


class TestListHandler(BaseTestCase):
    def test_list_pairs(self):
        response = self.fetch_json('/list', {'q': 'pairs'})
        self.assertIsNone(response['responseDetails'])
        self.assertEqual(response['responseStatus'], 200)
        expect = set(map(lambda x: frozenset(x.items()), [
            {'sourceLanguage': 'sme', 'targetLanguage': 'nob'},
            {'sourceLanguage': 'eng', 'targetLanguage': 'spa'},
            {'sourceLanguage': 'spa', 'targetLanguage': 'eng_US'},
            {'sourceLanguage': 'spa', 'targetLanguage': 'eng'},
        ]))
        response_data = set(map(lambda x: frozenset(x.items()), response['responseData']))
        self.assertTrue(response_data >= expect, '{} is missing one of {}'.format(response_data, expect))

    def test_list_generators(self):
        response = self.fetch_json('/list', {'q': 'generators'})
        expect = {'nno': 'nno-gener'}
        self.assertTrue(response.items() >= expect.items(), '{} is missing {}'.format(response, expect))

    def test_list_analyzers(self):
        response = self.fetch_json('/list', {'q': 'analyzers'})
        expect = {'nno': 'nno-morph'}
        self.assertTrue(response.items() >= expect.items(), '{} is missing {}'.format(response, expect))

    def test_list_taggers(self):
        response = self.fetch_json('/list', {'q': 'taggers'})
        expect = {'nno': 'nno-tagger'}
        self.assertTrue(response.items() >= expect.items(), '{} is missing {}'.format(response, expect))


class TestTranslateHandler(BaseTestCase):
    def fetch_translation(self, query, pair, **kwargs):
        params = kwargs.get('params', {})
        params.update({'q': query, 'langpair': pair})
        kwargs['params'] = params

        response = self.fetch_json('/translate', **kwargs)
        return response

    def test_valid_pair(self):
        response = self.fetch_translation('government', 'eng|spa')
        self.assertEqual(response['responseData']['translatedText'], 'Gobierno')

    def test_valid_pair_unknown(self):
        response = self.fetch_translation('notaword', 'eng|spa')
        self.assertEqual(response['responseData']['translatedText'], '*notaword')

        response = self.fetch_translation('notaword', 'eng|spa', params={'markUnknown': False})
        self.assertEqual(response['responseData']['translatedText'], 'notaword')

    def test_valid_giella_pair(self):
        response = self.fetch_translation('ja', 'sme|nob')
        self.assertEqual(response['responseData']['translatedText'], 'og')

    def test_valid_pair_post(self):
        response = self.fetch_translation('government', 'eng|spa', method='POST')
        self.assertEqual(response['responseData']['translatedText'], 'Gobierno')

    def test_valid_pair_jsonp(self):
        callback_fn_name = 'callback123456'
        response = self.fetch('/translate', params={
            'q': 'government',
            'langpair': 'eng|spa',
            'callback': callback_fn_name,
        })
        body_text = response.body.decode('utf-8')
        self.assertTrue(body_text.startswith(callback_fn_name))
        self.assertTrue(body_text.endswith(')'))
        body = json.loads(body_text[len(callback_fn_name) + 1:-1])
        self.assertEqual(body['responseData']['translatedText'], 'Gobierno')

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


class TestTranslatePageHandler(BaseTestCase):
    @unittest.skip('Failing for unknown reasons')
    def test_translate(self):
        response = self.fetch_json('/translatePage', params={
            'langpair': 'eng|spa',
            'url': 'http://example.com/',
        })
        print(response)


class TestAnalyzeHandler(BaseTestCase):
    def test_analyze(self):
        response = self.fetch_json('/analyze', {'q': 'ikkje', 'lang': 'nno'})
        self.assertEqual(response, [['ikkje/ikkje<adv>', 'ikkje']])

    def test_invalid_analyze(self):
        response = self.fetch_json('/analyze', {'q': 'ignored', 'lang': 'zzz'}, expect_success=False)
        self.assertDictEqual(response, {
            'status': 'error',
            'code': 400,
            'message': 'Bad Request',
            'explanation': 'That mode is not installed',
        })


class TestGenerateHandler(BaseTestCase):
    def test_generate(self):
        response = self.fetch_json('/generate', {'q': '^ja<ij>$', 'lang': 'nno'})
        self.assertEqual(response, [['ja', '^ja<ij>$']])

    def test_generate_single(self):
        response = self.fetch_json('/generate', {'q': 'ja<ij>', 'lang': 'nno'})
        self.assertEqual(response, [['ja', '^ja<ij>$']])

    def test_invalid_generate(self):
        response = self.fetch_json('/generate', {'q': 'ignored', 'lang': 'zzz'}, expect_success=False)
        self.assertDictEqual(response, {
            'status': 'error',
            'code': 400,
            'message': 'Bad Request',
            'explanation': 'That mode is not installed',
        })


class TestStatsHandler(BaseTestCase):
    def test_stats(self):
        response = self.fetch_json('/stats')
        data = response['responseData']
        self.assertGreater(data['uptime'], 0)
        for key in ['useCount', 'runningPipes', 'holdingPipes', 'periodStats']:
            self.assertIn(key, data)
        for periodKey in ['charsPerSec', 'totChars', 'totTimeSpent', 'requests', 'ageFirstRequest']:
            self.assertIn(periodKey, data['periodStats'])


class TestListLanguageNamesHandler(BaseTestCase):
    def test_english_lang_names_list(self):
        response = self.fetch_json('/listLanguageNames', params={'locale': 'eng'})
        self.assertEqual(response['en'], 'English')
        self.assertGreater(len(response.keys()), 50, msg='Should have at least 100 English language names')

    def test_limited_english_lang_names_list(self):
        response = self.fetch_json('/listLanguageNames', params={'locale': 'eng', 'languages': 'spa arg cat'})
        self.assertDictEqual(response, {
            'spa': 'Spanish',
            'arg': 'Aragonese',
            'cat': 'Catalan',
        })

    def test_no_locale_lang_names_list(self):
        response = self.fetch_json('/listLanguageNames')
        self.assertEqual(response['en'], 'English')

    @unittest.skip('Failing for unknown reasons')
    def test_accept_languages_header_lang_names_list(self):
        response = self.fetch_json('/listLanguageNames', headers={
            'Accept-Language': 'fr-CH, fr;q=0.9, en;q=0.8, de;q=0.7, *;q=0.5',
        })
        self.assertEqual(response['en'], 'Anglais')


if __name__ == '__main__':
    unittest.main()
