import sqlite3
import textwrap
import csv


def insert_values(c, filename):
    c.execute(textwrap.dedent("""
        CREATE TABLE IF NOT EXISTS {} (
            id INTEGER PRIMARY KEY,
            lg TEXT,
            inLg TEXT,
            name TEXT,
            UNIQUE(lg, inLg) ON CONFLICT REPLACE);
        """.format(filename)))
    with open('{}.tsv'.format(filename), 'r') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            c.execute('INSERT INTO {} VALUES (?, ?, ?, ?)'.format(filename), (None, row['lg'], row['inLg'], row['name']))


def populate_database():
    conn = sqlite3.connect('langNames.db')
    c = conn.cursor()
    c.execute("""PRAGMA foreign_keys=OFF;""")
    c.execute("""BEGIN TRANSACTION;""")
    insert_values(c, 'fixes')
    insert_values(c, 'additions')
    conn.commit()
    c.close()


if __name__ == '__main__':
    populate_database()
