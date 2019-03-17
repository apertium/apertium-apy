import csv
import sqlite3
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
    insert_values(c, 'fixes.tsv', 'fixes')
    insert_values(c, 'additions.tsv', 'additions')
    insert_values(c, 'turkic_fixes.tsv', 'fixes')
    insert_values(c, 'turkic_langNames.tsv', 'languageNames')
    insert_values(c, 'scraped.tsv', 'languageNames')
    insert_values(c, 'scraped-sil.tsv', 'languageNames')
    insert_values(c, 'variants.tsv', 'languageNames')
    conn.commit()
    c.close()


if __name__ == '__main__':
    populate_database()
