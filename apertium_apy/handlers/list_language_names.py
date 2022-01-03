import logging
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor

from tornado import gen

from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils import to_alpha2_code, iso639_codes  # noqa: F401

if False:
    from typing import Optional  # noqa: F401


# single-threaded for thread-safety
lang_names_db_thread = ThreadPoolExecutor(1)
lang_names_db_conn = None  # type: Optional[sqlite3.Connection]


def get_language_names(locale, db_path):
    global lang_names_db_conn

    if not lang_names_db_conn:
        if os.path.exists(db_path):
            lang_names_db_conn = sqlite3.connect(db_path)
        else:
            return None

    cursor = lang_names_db_conn.cursor()
    return cursor.execute('SELECT * FROM languageNames WHERE lg=?', (locale, )).fetchall()


@gen.coroutine
def get_localized_languages(locale, db_path, languages=[]):
    locale = to_alpha2_code(locale)
    languages = list(set(languages))

    language_results = yield lang_names_db_thread.submit(get_language_names, locale, db_path)

    if language_results is None:
        logging.error('Failed to locate language name DB: %s', db_path)
        return {}

    converted_languages, duplicated_languages = {}, {}

    for language in languages:
        if language in iso639_codes and iso639_codes[language] in languages:
            duplicated_languages[iso639_codes[language]] = language
            duplicated_languages[language] = iso639_codes[language]

        converted_languages[to_alpha2_code(language)] = language

    output = {}

    if languages:
        for language_result in language_results:
            if language_result[2] in converted_languages:
                language, language_name = language_result[2], language_result[3]
                output[converted_languages[language]] = language_name

                if language in duplicated_languages:
                    output[language] = language_name
                    output[duplicated_languages[language]] = language_name
    else:
        for language_result in language_results:
            output[language_result[2]] = language_result[3]

    return output


class ListLanguageNamesHandler(BaseHandler):
    @gen.coroutine
    def get(self):
        locale_arg = self.get_argument('locale', default=None)
        languages_arg = self.get_argument('languages', default=None)

        if not self.lang_names:
            self.send_response({})
            return

        if locale_arg:
            if languages_arg:
                result = yield get_localized_languages(locale_arg, self.lang_names, languages=languages_arg.split(' '))
            else:
                result = yield get_localized_languages(locale_arg, self.lang_names)

            self.send_response(result)
            return

        if 'Accept-Language' in self.request.headers:
            locales = [locale.split(';')[0].strip() for locale in self.request.headers['Accept-Language'].split(',')]

            for locale in locales:
                result = yield get_localized_languages(locale, self.lang_names)

                if result:
                    self.send_response(result)
                    return

        result = yield get_localized_languages('en', self.lang_names)
        self.send_response(result)
