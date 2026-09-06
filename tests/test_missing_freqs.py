import os
import sqlite3
import tempfile
from unittest import TestCase

from apertium_apy.handlers.base import BaseHandler
from apertium_apy.handlers.translate import TranslateHandler
from apertium_apy.missingdb import MissingDb


def make_handler():
    # TranslateHandler.__init__ wants a live application and request, but
    # note_unknown_tokens only touches class attributes, so bypass it.
    return object.__new__(TranslateHandler)


class TestMissingDb(TestCase):
    def setUp(self):
        self.db_path = os.path.join(tempfile.mkdtemp(), 'missingFreqs.db')

    def rows(self):
        with sqlite3.connect(self.db_path) as conn:
            return sorted(conn.execute('SELECT pair, token, frequency FROM missingFreqs'))

    def test_commit_writes_tokens(self):
        db = MissingDb(self.db_path, 1000)
        db.note_unknown('fooword', 'cat-spa')
        db.note_unknown('barword', 'cat-spa')
        db.commit()

        self.assertEqual(self.rows(), [('cat-spa', 'barword', 1), ('cat-spa', 'fooword', 1)])

    def test_repeated_tokens_accumulate(self):
        db = MissingDb(self.db_path, 1000)
        for _ in range(3):
            db.note_unknown('fooword', 'cat-spa')
        db.commit()

        self.assertEqual(self.rows(), [('cat-spa', 'fooword', 3)])

    def test_same_token_different_pairs_kept_apart(self):
        db = MissingDb(self.db_path, 1000)
        db.note_unknown('fooword', 'cat-spa')
        db.note_unknown('fooword', 'spa-cat')
        db.commit()

        self.assertEqual(self.rows(), [('cat-spa', 'fooword', 1), ('spa-cat', 'fooword', 1)])

    def test_commits_when_memory_limit_reached(self):
        db = MissingDb(self.db_path, 1)
        db.note_unknown('fooword', 'cat-spa')
        db.note_unknown('barword', 'cat-spa')

        # No explicit commit: exceeding the limit must have flushed to disk.
        self.assertTrue(os.path.exists(self.db_path))
        self.assertEqual(self.rows(), [('cat-spa', 'barword', 1), ('cat-spa', 'fooword', 1)])

    def test_nothing_written_before_commit(self):
        db = MissingDb(self.db_path, 1000)
        db.note_unknown('fooword', 'cat-spa')

        self.assertFalse(os.path.exists(self.db_path))


class TestNoteUnknownTokens(TestCase):
    def setUp(self):
        self.db_path = os.path.join(tempfile.mkdtemp(), 'missingFreqs.db')
        # setup_handler() installs the db here; commit on every token so the
        # assertions can read it straight back off disk.
        BaseHandler.missing_freqs_db = MissingDb(self.db_path, 0)

    def tearDown(self):
        BaseHandler.missing_freqs_db = None

    def rows(self):
        with sqlite3.connect(self.db_path) as conn:
            return sorted(conn.execute('SELECT pair, token, frequency FROM missingFreqs'))

    def test_marked_tokens_are_recorded(self):
        # Regression test: the db used to be a module-level global reached via
        # `from apertium_apy import missing_freqs_db`, which bound a copy of
        # None into each importing module. setup_handler()'s assignment was
        # therefore invisible here and no unknown word was ever recorded.
        make_handler().note_unknown_tokens('cat-spa', 'Hola *fooword i *barword')
        BaseHandler.missing_freqs_db.commit()

        self.assertEqual(self.rows(), [('cat-spa', 'barword', 1), ('cat-spa', 'fooword', 1)])

    def test_repeated_tokens_accumulate(self):
        make_handler().note_unknown_tokens('cat-spa', '*fooword i *fooword')
        BaseHandler.missing_freqs_db.commit()

        self.assertEqual(self.rows(), [('cat-spa', 'fooword', 2)])

    def test_unmarked_text_records_nothing(self):
        make_handler().note_unknown_tokens('cat-spa', 'Hola com estas')
        BaseHandler.missing_freqs_db.commit()

        self.assertEqual(self.rows(), [])

    def test_recorded_even_when_marks_are_stripped(self):
        # markUnknown=no strips the asterisks from the response, but the words
        # are still unknown and must be counted.
        handler = make_handler()
        translated = handler.maybe_strip_marks(False, ('cat', 'spa'), 'Hola *fooword')
        BaseHandler.missing_freqs_db.commit()

        self.assertEqual(translated, 'Hola fooword')
        self.assertEqual(self.rows(), [('cat-spa', 'fooword', 1)])

    def test_no_db_configured_is_a_noop(self):
        BaseHandler.missing_freqs_db = None

        make_handler().note_unknown_tokens('cat-spa', 'Hola *fooword')

        self.assertFalse(os.path.exists(self.db_path))
