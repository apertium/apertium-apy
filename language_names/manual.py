import sqlite3
import textwrap
import csv


def insert_values(c, filename):
    c.execute(textwrap.dedent("""
        CREATE TABLE IF NOT EXISTS {file} (
            id INTEGER PRIMARY KEY,
            lg TEXT,
            inLg TEXT,
            name TEXT,
            UNIQUE(lg, inLg) ON CONFLICT REPLACE);
        """.format(file=filename)))
    with open(filename + '.tsv', 'r') as f:
        reader = csv.reader(f, delimiter='\t')
        next(reader)
        for row in reader:
            c.execute('INSERT INTO ' + filename + ' VALUES (?, ?, ?, ?)', (None, row[0], row[1], row[2]))


def populate_database():
    conn = sqlite3.connect('langNames.db')
    c = conn.cursor()
    c.execute("""
        PRAGMA foreign_keys=OFF;
        """)
    c.execute("""
        BEGIN TRANSACTION;
        """)
    insert_values(c, 'fixes')
    insert_values(c, 'additions')
    conn.commit()
    c.close()


if __name__ == '__main__':
    populate_database()
