import csv
import sqlite3
import sys
import textwrap


def insert_values(c, filename):
    c.execute(textwrap.dedent("""
        CREATE TABLE IF NOT EXISTS languageNames (
            id INTEGER PRIMARY KEY,
            lg TEXT,
            inLg TEXT,
            name TEXT,
            UNIQUE(lg, inLg) ON CONFLICT REPLACE);
        """))
    with open(filename, 'r') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            c.execute('INSERT INTO languageNames VALUES (?, ?, ?, ?)', (None, row['lg'], row['inLg'], row['name']))


def populate_database():
    conn = sqlite3.connect(sys.argv[-1])
    c = conn.cursor()
    c.execute('PRAGMA foreign_keys=OFF;')
    c.execute('BEGIN TRANSACTION;')
    for i in range(1, len(sys.argv) - 1):
        insert_values(c, sys.argv[i])
    conn.commit()
    c.close()


if __name__ == '__main__':
    populate_database()
