#!/usr/bin/env python3
# coding=utf-8

import logging
import unittest
import os
import shlex
import sys

from tornado.log import enable_pretty_logging
from tornado.testing import AsyncHTTPTestCase

sys.path.append(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../apertium_apy'))
from apy import check_utf8, parse_args, setup_application  # noqa: E402

logging.getLogger().setLevel(logging.DEBUG)

PORT = os.environ.get('APY_PORT', '2737')  # TODO: use tornado.testing.bind_unused_port
NONPAIRS = os.environ.get('NONPAIRS', '/usr/share/apertium')
INSTALLEDPAIRS = os.environ.get('INSTALLEDPAIRS', '/l/a/languages')

check_utf8()
cli_args = shlex.split('-p {} -j1 -i3 -u1 -n1 -m3 -s "{}"  -- "{}"'.format(PORT, NONPAIRS, INSTALLEDPAIRS))
args = parse_args(cli_args=cli_args)
enable_pretty_logging()
application = setup_application(args)
print(application)


class BaseTestCase(AsyncHTTPTestCase):
    def get_app(self):
        return application

    def get_http_port(self):
        return PORT


class TestListHandler(BaseTestCase):
    def test_list_pairs(self):
        response = self.fetch('/list?q=pairs')
        print(response)
        self.assertEqual(response.code, 200)


class TestTranslateHandler(BaseTestCase):
    def get_url(self, path):
        return super().get_url('/translate{}'.format(path))

    # def test_valid_pair(self):
    #     response = self.fetch('?q=house&langpair=en|es')
    #     print(response)
    #     self.assertEqual(response.code, 200)
    #     self.assertFalse(True)


if __name__ == '__main__':
    unittest.main()
