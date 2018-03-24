#!/usr/bin/env python3

from typing import Dict  # noqa: F401

from collections import defaultdict


def getKey(key):
    return keys[key]


keys_raw = {
    # add keys here
}  # type: Dict
keys = defaultdict(lambda: 'null', keys_raw)
