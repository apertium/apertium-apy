import csv
import sqlite3
import sys
import textwrap


def insert_values(c, filename, tablename):
    c.execute(textwrap.dedent("""
        CREATE TABLE IF NOT EXISTS {} (
            id INTEGER PRIMARY KEY,
            lg TEXT,
            inLg TEXT,
            name TEXT,
            UNIQUE(lg, inLg) ON CONFLICT REPLACE);
        """.format(tablename)))
    with open(filename, 'r') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            c.execute('INSERT INTO {} VALUES (?, ?, ?, ?)'.format(tablename), (None, row['lg'], row['inLg'], row['name']))


def populate_database():
    conn = sqlite3.connect('langNames.db')
    c = conn.cursor()
    c.execute('PRAGMA foreign_keys=OFF;')
    c.execute('BEGIN TRANSACTION;')
    insert_values(c, sys.argv[1], 'fixes')
    insert_values(c, sys.argv[2], 'additions')
    insert_values(c, sys.argv[3], 'fixes')
    insert_values(c, sys.argv[4], 'languageNames')
    insert_values(c, sys.argv[5], 'languageNames')
    insert_values(c, sys.argv[6], 'languageNames')
    insert_values(c, sys.argv[7], 'languageNames')
    conn.commit()
    c.close()


if __name__ == '__main__':
    populate_database()
