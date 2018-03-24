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
NONPAIRS = os.environ.get('NONPAIRS', '/usr/share/apertium')
INSTALLEDPAIRS = os.environ.get('INSTALLEDPAIRS', '/l/a/languages')

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
        except urllib.error.URLError:
            print('.', end='')
            waited += 1
            time.sleep(1)

    if not started:
        raise Exception('Starting APy failed after waiting for {} seconds'.foramt(MAX_STARTUP_SECONDS))


def tearDownModule():  # noqa: N802
    server_handle.kill()


class BaseTestCase(AsyncHTTPTestCase):
    def get_app(self):
        return application

    def get_http_port(self):
        return PORT

    def fetch_json(self, *args, **kwargs):
        response = self.fetch(*args, **kwargs)
        self.assertEqual(response.code, 200)
        return json.loads(response.body.decode('utf-8'))


class TestListHandler(BaseTestCase):
    def test_list_pairs(self):
        response = self.fetch_json('/list?q=pairs')
        self.assertTrue('responseData' in response)
        self.assertTrue('responseDetails' in response)
        self.assertEqual(response['responseStatus'], 200)
        # TODO: validate more

    def test_list_generators(self):
        response = self.fetch_json('/list?q=generators')
        print(response)  # TODO: validate it

    def test_list_analyzers(self):
        response = self.fetch_json('/list?q=analysers')
        print(response)  # TODO: validate it


class TestTranslateHandler(BaseTestCase):
    def get_url(self, path):
        return super().get_url('/translate{}'.format(path))

    # def test_valid_pair(self):
    #     response = self.fetch_json('?q=house&langpair=en|es')
    #     print(response)


if __name__ == '__main__':
    unittest.main()
