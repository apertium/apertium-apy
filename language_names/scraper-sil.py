#!/usr/bin/env python3

import argparse
import urllib.request
import re
import sys

sil_names = 'http://www-01.sil.org/iso639-3/iso-639-3.tab'

user_agent = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'}  # noqa: E501
tsv_format = re.compile(r'(?P<Id>.*?)\t(?P<Part2B>.*?)\t(?P<Part2T>.*?)\t(?P<Part1>.*?)\t(?P<tcope>.*?)\t(?P<Language_Type>.*?)\t(?P<Ref_Name>.*?)\t(?P<Comment>.*?)')  # noqa: E501
insert_template = 'INSERT OR IGNORE INTO "%s" VALUES(NULL,"%s","%s","%s");'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Scrape SIL for language names in English.')
    parser.add_argument('-t', '--table', help='language names table', default='languageNames')
    args = parser.parse_args()

    request = urllib.request.Request(sil_names, headers=user_agent)
    sil_tsv = urllib.request.urlopen(request).read().decode('utf-8')  # Python's csv module chokes badly on this
    tsv_contents = sil_tsv.splitlines()

    with open('language_names/scraped-sil.tsv', 'a') as f:
        for tsv_line in tsv_contents[1:]:  # skip the header
            matches = tsv_format.match(tsv_line)

            if matches:
                iso639_3 = matches.group('Id')
                iso639_1 = matches.group('Part1')
                iso639 = iso639_1 or iso639_3

                name = matches.group('Ref_Name')

                if iso639 and name:
                    f.write('%s	%s	%s\n' % ('en', iso639, name))
                else:
                    sys.stdout.write('!!! Unable to parse %s !!!\n' % repr(tsv_line))
            else:
                sys.stdout.write('!!! Unable to parse %s !!!\n' % repr(tsv_line))
