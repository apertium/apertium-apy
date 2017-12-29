#!/usr/bin/env python3

try:
    from typing import Dict  # noqa: F401
except ImportError:  # 3.2
    pass

from collections import defaultdict


def getKey(key):
    return keys[key]


keys_raw = {
    # add keys here
}  # type: Dict
keys = defaultdict(lambda: 'null', keys_raw)
