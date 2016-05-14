#!/usr/bin/env python3
# vim: set ts=4 sw=4 sts=4 et :

import sqlite3, logging
from datetime import datetime
import threading
from collections import defaultdict
from contextlib import closing

class MissingDb(object):
    def __init__(self, dbPath, wordmemlimit):
        self.lock = threading.RLock()
        self.conn = None
        self.dbPath = dbPath
        self.words = defaultdict(lambda: defaultdict(lambda: 0))
        self.wordcount = 0
        self.wordmemlimit = wordmemlimit

    def noteUnknown(self, token, pair):
        self.words[pair][token] += 1
        self.wordcount += 1
        # so if wordmemlimit is 0, we commit on each word
        if self.wordcount > self.wordmemlimit:
            self.commit()
            self.words.clear()
            self.wordcount = 0

    def commit(self):
        timeBefore = datetime.now()
        with self.lock:
            if not self.conn:
                self.conn = sqlite3.connect(self.dbPath)

            with closing(self.conn.cursor()) as c:
                c.execute("PRAGMA synchronous = NORMAL")
                c.execute('CREATE TABLE IF NOT EXISTS missingFreqs (pair TEXT, token TEXT, frequency INTEGER, UNIQUE(pair, token))')
                c.executemany('INSERT OR REPLACE INTO missingFreqs VALUES (:pair, :token, COALESCE((SELECT frequency FROM missingFreqs WHERE pair=:pair AND token=:token), 0) + :amount)',
                            ({'pair': pair,
                                'token': token,
                                'amount' : self.words[pair][token]}
                            for pair in self.words
                            for token in self.words[pair]))
            self.conn.commit()
        ms = timedeltaToMilliseconds(datetime.now() - timeBefore)
        logging.info("\tSaving %s unknown words to the DB (%s ms)", self.wordcount, ms)

    def closeDb(self):
        if not self.conn:
            logging.warning('no connection on closeDb')
            return
        logging.warning('closing connection')
        self.conn.commit()
        self.conn.close()
        self.conn = None


def timedeltaToMilliseconds(td):
    return td.days*86400000 + td.seconds*1000 + int(td.microseconds/1000)
