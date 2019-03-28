#!/usr/bin/env python3

import argparse
import csv
import logging
import sqlite3
import textwrap

logging.basicConfig(level=logging.INFO)


def count_language_names(c, table):
    return c.execute('SELECT COUNT(*) FROM %s' % table).fetchone()[0]


def populate_database(args):
    conn = sqlite3.connect(args.db)
    c = conn.cursor()

    # Set up the database.
    c.execute('PRAGMA foreign_keys=OFF')
    c.execute(textwrap.dedent("""
        CREATE TABLE IF NOT EXISTS %s (
            id INTEGER PRIMARY KEY,
            lg TEXT,
            inLg TEXT,
            name TEXT,
            UNIQUE(lg, inLg) ON CONFLICT REPLACE)
        """ % args.table))
    conn.commit()

    # Add names from each TSV.
    for filename in args.files:
        initial_count = count_language_names(c, args.table)
        c.execute('BEGIN TRANSACTION')
        with open(filename) as f:
            rows = list(csv.DictReader(f, delimiter='\t'))
            insertion_count = len(rows)
            for row in rows:
                c.execute('INSERT INTO %s VALUES (?, ?, ?, ?)' % args.table,
                          (None, row['lg'], row['inLg'], row['name']))
        conn.commit()
        new_insertions_count = count_language_names(c, args.table) - initial_count
        logging.info('Inserted %d names from %s (%d new, %d updates)',
                     insertion_count, filename, new_insertions_count,
                     insertion_count - new_insertions_count)

    c.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build language names database from TSVs.')
    parser.add_argument('db', help='language names database', default='langNames.db')
    parser.add_argument('files', nargs='+', help='TSV files with language names')
    parser.add_argument('--table', help='language names table', default='languageNames')
    args = parser.parse_args()
    populate_database(args)
