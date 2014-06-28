#!/usr/bin/env python3

import sqlite3, argparse, os, subprocess, re, sys
from lxml import etree

sys.path.append(os.path.join(os.path.abspath(os.path.dirname(__file__)), '..'))
from util import toAlpha2Code

apertiumLanguages = {'sr', 'bs', 'hr'} # Add more manually as necessary

def getApertiumLanguages():
    dirs = [('incubator', r'<name>apertium-(\w{2,3})(?:-(\w{2,3}))?</name>'), 
            ('nursery', r'<name>apertium-(\w{2,3})(?:-(\w{2,3}))?</name>'), 
            ('staging', r'<name>apertium-(\w{2,3})(?:-(\w{2,3}))?</name>'), 
            ('trunk', r'<name>(apertium)-(\w{2,3})-(\w{2,3})</name>'), 
            ('languages', r'<name>(apertium)-(\w{3})</name>'), 
           ]
    for (dirPath, dirRegex) in dirs:
        svnData = str(subprocess.check_output('svn list --xml https://svn.code.sf.net/p/apertium/svn/%s/' % dirPath, stderr=subprocess.STDOUT, shell=True), 'utf-8')
        for langCodes in re.findall(dirRegex, svnData, re.DOTALL):
            apertiumLanguages.update([convertISOCode(langCode)[1] for langCode in langCodes if not langCode == 'apertium'])
            
    print('Found %s apertium languages' % len(apertiumLanguages))
    return apertiumLanguages

def convertISOCode(code):
    return (code, toAlpha2Code(code))

def populateDatabase(args):
    conn = sqlite3.connect(args.database)
    c = conn.cursor()
    c.execute('''create table if not exists languageNames (id integer primary key, lg text, inLg text, name text, unique(lg, inLg) on conflict replace)''')
    for locale in args.languages:
        locale = convertISOCode(locale)
        try:
            tree = etree.parse('http://www.unicode.org/repos/cldr/tags/latest/common/main/%s.xml' % locale[1])
            languages = tree.xpath('//language')
            changes = conn.total_changes
            for language in languages:
                if language.text:
                    if not args.apertiumNames or (args.apertiumNames and language.get('type') in apertiumLanguages):
                        c.execute('''insert into languageNames values (?, ?, ?, ?)''', (None, locale[1], language.get('type'), language.text))
            print('Scraped %s localized language names for %s' % (conn.total_changes - changes, locale[1] if locale[0] == locale[1] else '%s -> %s' % locale))
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            print('Failed to retreive language %s' % locale[1])
        
    conn.commit()
    c.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Scrape Unicode.org for language names in different locales.')
    parser.add_argument('languages', nargs='*', help='list of languages to add to DB')
    parser.add_argument('-d', '--database', help='name of database file', default='langNames.db')
    parser.add_argument('-n', '--apertiumNames', help='only save names of Apertium languages to database', action='store_true', default=False)
    parser.add_argument('-l', '--apertiumLangs', help='scrape localized names in all Apertium languages', action='store_true', default=False)
    args = parser.parse_args()
    
    if not (len(args.languages) or args.apertiumNames or args.apertiumLangs):
        parser.print_help()
    
    if args.apertiumNames or args.apertiumLangs:
        getApertiumLanguages()
    if args.apertiumLangs:
        args.languages = apertiumLanguages
    populateDatabase(args)
