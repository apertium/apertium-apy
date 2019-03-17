import sqlite3
import textwrap
import csv


def insert_values(c, filename):
    c.execute(textwrap.dedent(f"""
        CREATE TABLE IF NOT EXISTS {filename} (
            id INTEGER PRIMARY KEY,
            lg TEXT,
            inLg TEXT,
            name TEXT,
            UNIQUE(lg, inLg) ON CONFLICT REPLACE);
        """))
    with open(f'{filename}.tsv', 'r') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            c.execute(f'INSERT INTO {filename} VALUES (?, ?, ?, ?)', (None, row['lg'], row['inLg'], row['name']))


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
