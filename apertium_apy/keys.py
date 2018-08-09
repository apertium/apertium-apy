import logging

try:
    from commentjson import loads as jsonload
except ImportError:
    from json import loads as jsonload

import os
from collections import defaultdict

if False:
    from typing import Dict  # noqa: F401


class ApiKeys:
    def __init__(self, api_keys_conf):
        keys_raw = {
            # add keys here
        }  # type: Dict

        if api_keys_conf and os.path.isfile(api_keys_conf):
            logging.info('Loading keys from %s' % api_keys_conf)

            with open(api_keys_conf) as handle:
                try:
                    keys_raw = jsonload(handle.read())
                except Exception:
                    logging.warning('Could not read keys from %s' % api_keys_conf)

        self.keys = defaultdict(lambda: 'null', keys_raw)

    def get_key(self, key):
        return self.keys[key]
