#!/usr/bin/env python3

import argparse
import os
import re
import subprocess
import sys

from lxml import etree

sys.path.append(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../apertium_apy'))
from utils import to_alpha2_code  # noqa: E402

html_tools_languages = set(map(to_alpha2_code, {
    'arg', 'heb', 'cat', 'sme', 'deu', 'eng', 'eus', 'fra', 'spa', 'ava', 'nno',
    'nob', 'oci', 'por', 'kaz', 'kaa', 'kir', 'ron', 'rus', 'fin', 'tat', 'tur',
    'uig', 'uzb', 'zho', 'srd', 'swe',
}))

apertium_languages = html_tools_languages | {'sr', 'bs', 'hr'}  # Add more manually as necessary


def get_apertium_languages():
    dirs = [
        ('incubator', r'<name>apertium-(\w{2,3})(?:-(\w{2,3}))?</name>'),
        ('nursery', r'<name>apertium-(\w{2,3})(?:-(\w{2,3}))?</name>'),
        ('staging', r'<name>apertium-(\w{2,3})(?:-(\w{2,3}))?</name>'),
        ('trunk', r'<name>(apertium)-(\w{2,3})-(\w{2,3})</name>'),
        ('languages', r'<name>(apertium)-(\w{3})</name>'),
        ('incubator', r'<name>(apertium)-(\w{3})</name>'),
    ]
    for (dir_path, dir_regex) in dirs:
        svn_data = str(subprocess.check_output('svn list --xml https://github.com/apertium/apertium-%s.git/trunk' %
                                               dir_path, stderr=subprocess.STDOUT, shell=True), 'utf-8')
        for lang_codes in re.findall(dir_regex, svn_data, re.DOTALL):
            apertium_languages.update(
                convert_iso_code(lang_code)[1] for lang_code in lang_codes if lang_code and not lang_code == 'apertium'
            )

    print('Found %s apertium languages: %s.' % (len(apertium_languages), ', '.join(apertium_languages)))
    return apertium_languages


def convert_iso_code(code):
    return (code, to_alpha2_code(code))


def populate_database(args):
    with open('language_names/scraped-cldr.tsv', 'w') as f:
        f.write('lg	inLg	name\n')
        for locale in args.languages:
            locale = convert_iso_code(locale)
            try:
                tree = etree.parse('http://www.unicode.org/repos/cldr/tags/latest/common/main/%s.xml' % locale[1])
                languages = tree.xpath('//language')
                scraped = set()
                for language in languages:
                    if language.text:
                        if not args.apertium_names or (args.apertium_names and language.get('type') in apertium_languages):
                            f.write('%s	%s	%s\n' % (locale[1], language.get('type'), language.text))
                            scraped.add(language.get('type'))
                print('Scraped %d localized language names for %s, missing %d (%s).' % (
                    len(scraped),
                    locale[1] if locale[0] == locale[1] else '%s -> %s' % locale,
                    len(apertium_languages) - len(scraped) if args.apertium_names else 0,
                    ', '.join(apertium_languages - scraped if args.apertium_names else set()),
                ))
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as e:
                print('Failed to retrieve language %s, exception: %s' % (locale[1], e))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Scrape Unicode.org for language names in different locales.')
    parser.add_argument('languages', nargs='*', help='list of languages to add to DB')
    parser.add_argument('-d', '--database', help='name of database file', default='../langNames.db')
    parser.add_argument('-n', '--apertium-names', help='only save names of Apertium languages to database',
                        action='store_true', default=False)
    parser.add_argument('-l', '--apertium-langs', help='scrape localized names in all Apertium languages',
                        action='store_true', default=False)
    args = parser.parse_args()

    if not (len(args.languages) or args.apertium_names or args.apertium_langs):
        parser.print_help()

    if args.apertium_names or args.apertium_langs:
        get_apertium_languages()

    if args.apertium_langs:
        args.languages = apertium_languages

    populate_database(args)
