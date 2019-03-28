#!/usr/bin/env python3

import argparse
import csv
import itertools
import json
import logging
import os
import sys
import time
import urllib.request

from lxml import etree

sys.path.append(os.path.join(os.path.abspath(os.path.dirname(__file__)), '../apertium_apy'))
from utils import to_alpha2_code  # noqa: E402

logging.basicConfig(level=logging.INFO)

html_tools_languages = set(map(to_alpha2_code, {
    'arg', 'ava', 'cat', 'deu', 'eng', 'eus', 'fin', 'fra', 'glg', 'heb', 'kaa',
    'kaz', 'kir', 'mar', 'nno', 'nob', 'oci', 'por', 'ron', 'rus', 'sme', 'spa',
    'srd', 'swe', 'tat', 'tur', 'uig', 'uzb', 'zho', 'szl',
}))

apertium_languages = html_tools_languages | {'sr', 'bs', 'hr'}  # Add more manually as necessary


def get_apertium_languages():
    packages = json.load(urllib.request.urlopen('https://apertium.projectjj.com/stats-service/packages'))['packages']  # type: ignore
    lang_codes = itertools.chain.from_iterable(map(lambda x: list(map(to_alpha2_code, x['name'].split('-')[1:])), packages))
    apertium_languages.update(lang_codes)
    logging.info('Found %s apertium languages: %s.', len(apertium_languages), ', '.join(apertium_languages))
    return apertium_languages


def scrape_cldr(args):
    names = []
    for locale in args.languages:
        locale = (locale, to_alpha2_code(locale))
        try:
            tree = etree.parse('http://www.unicode.org/repos/cldr/tags/latest/common/main/%s.xml' % locale[1])
            languages = tree.xpath('//language')
            scraped = set()
            for language in languages:
                if language.text:
                    if not args.apertium_names or (args.apertium_names and language.get('type') in apertium_languages):
                        names.append({'lg': locale[1], 'inLg': language.get('type'), 'name': language.text})
                        scraped.add(language.get('type'))
            logging.info('Scraped %d localized language names for %s, missing %d (%s).',
                         len(scraped),
                         locale[1] if locale[0] == locale[1] else '%s -> %s' % locale,
                         len(apertium_languages) - len(scraped) if args.apertium_names else 0,
                         ', '.join(apertium_languages - scraped if args.apertium_names else set()))
            time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            logging.warn('Failed to retrieve language %s, exception: %s', locale[1], e)
    names = sorted(names, key=lambda x: list(x.values()))

    with open(args.filename, 'w') as f:
        fieldnames = ['lg', 'inLg', 'name']
        writer = csv.DictWriter(f, delimiter='\t', lineterminator='\n', fieldnames=fieldnames)
        writer.writeheader()
        for name in names:
            writer.writerow(name)
        logging.info('Scraped %d language names', len(names))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Scrape Unicode.org for language names in different locales.')
    parser.add_argument('languages', nargs='*', help='list of languages to add to DB')
    parser.add_argument('-f', '--filename', help='output TSV filename', default='language_names/scraped-cldr.tsv')
    parser.add_argument('-n', '--apertium-names', help='only save names of Apertium languages to database',
                        action='store_true', default=False)
    parser.add_argument('-l', '--apertium-langs', help='scrape localized names in all Apertium languages',
                        action='store_true', default=False)
    args = parser.parse_args()

    if not (len(args.languages) or args.apertium_names or args.apertium_langs):
        parser.print_help()
        sys.exit(-1)

    if args.apertium_names or args.apertium_langs:
        get_apertium_languages()

    if args.apertium_langs:
        args.languages = apertium_languages

    scrape_cldr(args)
