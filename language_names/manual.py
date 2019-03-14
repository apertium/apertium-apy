import sqlite3
import textwrap
import csv


def populate_database():
    conn = sqlite3.connect('test.db')
    c = conn.cursor()
    c.execute(textwrap.dedent("""
        PRAGMA foreign_keys=OFF;"""))
    c.execute(textwrap.dedent("""
        BEGIN TRANSACTION;"""))
    c.execute(textwrap.dedent("""
        CREATE TABLE IF NOT EXISTS fixes (id integer primary key, lg text, inLg text, name text, unique(lg, inLg) on conflict replace);
        """))
    with open('fixes.tsv', 'r') as f:
        reader = csv.reader(f, delimiter='\t')
        for row in reader:
            c.execute('INSERT INTO fixes VALUES (?, ?, ?, ?)', (None, row[1], row[2], row[3]))
    c.execute(textwrap.dedent("""
        CREATE TABLE IF NOT EXISTS additions (id integer primary key, lg text, inLg text, name text, unique(lg, inLg) on conflict replace);
        """))
    with open('additions.tsv', 'r') as f:
        reader = csv.reader(f, delimiter='\t')
        for row in reader:
            c.execute('INSERT INTO additions VALUES (?, ?, ?, ?)', (None, row[1], row[2], row[3]))
    conn.commit()
    c.close()


if __name__ == "__main__":
    populate_database()
