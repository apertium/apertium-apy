#!/usr/bin/env python3

import argparse
import csv
import logging
import re
import urllib.request

logging.basicConfig(level=logging.INFO)

sil_names = 'http://www-01.sil.org/iso639-3/iso-639-3.tab'
headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}  # noqa: E501
tsv_format = re.compile(r'(?P<Id>.*?)\t(?P<Part2B>.*?)\t(?P<Part2T>.*?)\t(?P<Part1>.*?)\t(?P<tcope>.*?)\t(?P<Language_Type>.*?)\t(?P<Ref_Name>.*?)\t(?P<Comment>.*?)')  # noqa: E501


def scrape_sil(filename):
    request = urllib.request.Request(sil_names, headers=headers)
    sil_tsv = urllib.request.urlopen(request).read().decode('utf-8')  # Python's csv module chokes badly on this
    tsv_contents = sil_tsv.splitlines()

    names = []
    for line in tsv_contents[1:]:  # skip the header
        matches = tsv_format.match(line)

        if matches:
            iso639_3 = matches.group('Id')
            iso639_1 = matches.group('Part1')
            iso639 = iso639_1 or iso639_3

            name = matches.group('Ref_Name')

            if iso639 and name:
                names.append({'lg': 'en', 'inLg': iso639, 'name': name})
            else:
                logging.error('Unable to parse %s', repr(line))
        else:
            logging.error('Unable to parse %s', repr(line))
    names = sorted(names, key=lambda x: list(x.values()))

    with open(filename, 'w') as f:
        fieldnames = ['lg', 'inLg', 'name']
        writer = csv.DictWriter(f, delimiter='\t', lineterminator='\n', fieldnames=fieldnames)
        writer.writeheader()
        for row in names:
            writer.writerow(row)
        logging.info('Scraped %d language names', len(names))


def main():
    parser = argparse.ArgumentParser(description='Scrape SIL for English language names.')
    parser.add_argument('-f', '--filename', help='output TSV filename', default='language_names/scraped-sil.tsv')
    args = parser.parse_args()
    scrape_sil(args.filename)


if __name__ == '__main__':
    main()
