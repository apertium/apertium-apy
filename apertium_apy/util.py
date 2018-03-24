#!/usr/bin/env python3
# vim: set ts=4 sw=4 sts=4 et :

import logging
import os
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from subprocess import Popen, PIPE

from tornado import gen

from .missingdb import timedelta_to_milliseconds
from .wiki_util import wiki_get_page, wiki_edit_page, wiki_add_text

iso639Codes = {'abk': 'ab', 'aar': 'aa', 'afr': 'af', 'aka': 'ak', 'sqi': 'sq', 'amh': 'am', 'ara': 'ar', 'arg': 'an', 'hye': 'hy', 'asm': 'as', 'ava': 'av', 'ave': 'ae', 'aym': 'ay', 'aze': 'az', 'bam': 'bm', 'bak': 'ba', 'eus': 'eu', 'bel': 'be', 'ben': 'bn', 'bih': 'bh', 'bis': 'bi', 'bos': 'bs', 'bre': 'br', 'bul': 'bg', 'mya': 'my', 'cat': 'ca', 'cha': 'ch', 'che': 'ce', 'nya': 'ny', 'zho': 'zh', 'chv': 'cv', 'cor': 'kw', 'cos': 'co', 'cre': 'cr', 'hrv': 'hr', 'ces': 'cs', 'dan': 'da', 'div': 'dv', 'nld': 'nl', 'dzo': 'dz', 'eng': 'en', 'epo': 'eo', 'est': 'et', 'ewe': 'ee', 'fao': 'fo', 'fij': 'fj', 'fin': 'fi', 'fra': 'fr', 'ful': 'ff', 'glg': 'gl', 'kat': 'ka', 'deu': 'de', 'ell': 'el', 'grn': 'gn', 'guj': 'gu', 'hat': 'ht', 'hau': 'ha', 'heb': 'he', 'her': 'hz', 'hin': 'hi', 'hmo': 'ho', 'hun': 'hu', 'ina': 'ia', 'ind': 'id', 'ile': 'ie', 'gle': 'ga', 'ibo': 'ig', 'ipk': 'ik', 'ido': 'io', 'isl': 'is', 'ita': 'it', 'iku': 'iu', 'jpn': 'ja', 'jav': 'jv', 'kal': 'kl', 'kan': 'kn', 'kau': 'kr', 'kas': 'ks', 'kaz': 'kk', 'khm': 'km', 'kik': 'ki', 'kin': 'rw', 'kir': 'ky', 'kom': 'kv', 'kon': 'kg', 'kor': 'ko', 'kur': 'ku', 'kua': 'kj', 'lat': 'la', 'ltz': 'lb', 'lug': 'lg', 'lim': 'li', 'lin': 'ln', 'lao': 'lo', 'lit': 'lt', 'lub': 'lu', 'lav': 'lv', 'glv': 'gv', 'mkd': 'mk', 'mlg': 'mg', 'msa': 'ms', 'mal': 'ml', 'mlt': 'mt', 'mri': 'mi', 'mar': 'mr', 'mah': 'mh', 'mon': 'mn', 'nau': 'na', 'nav': 'nv', 'nob': 'nb', 'nde': 'nd', 'nep': 'ne', 'ndo': 'ng', 'nno': 'nn', 'nor': 'no', 'iii': 'ii', 'nbl': 'nr', 'oci': 'oc', 'oji': 'oj', 'chu': 'cu', 'orm': 'om', 'ori': 'or', 'oss': 'os', 'pan': 'pa', 'pli': 'pi', 'fas': 'fa', 'pol': 'pl', 'pus': 'ps', 'por': 'pt', 'que': 'qu', 'roh': 'rm', 'run': 'rn', 'ron': 'ro', 'rus': 'ru', 'san': 'sa', 'srd': 'sc', 'snd': 'sd', 'sme': 'se', 'smo': 'sm', 'sag': 'sg', 'srp': 'sr', 'gla': 'gd', 'sna': 'sn', 'sin': 'si', 'slk': 'sk', 'slv': 'sl', 'som': 'so', 'sot': 'st', 'azb': 'az', 'spa': 'es', 'sun': 'su', 'swa': 'sw', 'ssw': 'ss', 'swe': 'sv', 'tam': 'ta', 'tel': 'te', 'tgk': 'tg', 'tha': 'th', 'tir': 'ti', 'bod': 'bo', 'tuk': 'tk', 'tgl': 'tl', 'tsn': 'tn', 'ton': 'to', 'tur': 'tr', 'tso': 'ts', 'tat': 'tt', 'twi': 'tw', 'tah': 'ty', 'uig': 'ug', 'ukr': 'uk', 'urd': 'ur', 'uzb': 'uz', 'ven': 've', 'vie': 'vi', 'vol': 'vo', 'wln': 'wa', 'cym': 'cy', 'wol': 'wo', 'fry': 'fy', 'xho': 'xh', 'yid': 'yi', 'yor': 'yo', 'zha': 'za', 'zul': 'zu', 'hbs': 'sh', 'arg': 'an', 'pes': 'fa'}  # noqa: E501
"""
    Bootstrapped from https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes using
        var out = {};
        $.each($('tr', $('table').get(1)), function(i, elem) { var rows = $('td', elem); out[$(rows[5]).text()] = $(rows[4]).text(); });
        JSON.stringify(out);
"""

# single-threaded for thread-safety
lang_names_db_thread = ThreadPoolExecutor(1)
lang_names_db_conn = None


def to_alpha2_code(code):
    if '_' in code:
        code, variant = code.split('_')
        return '%s_%s' % ((iso639Codes[code], variant) if code in iso639Codes else (code, variant))
    else:
        return iso639Codes[code] if code in iso639Codes else code


def to_alpha3_code(code):
    iso639_codes_inverse = {v: k for k, v in iso639Codes.items()}
    if '_' in code:
        code, variant = code.split('_')
        return '%s_%s' % ((iso639_codes_inverse[code], variant) if code in iso639_codes_inverse else (code, variant))
    else:
        return iso639_codes_inverse[code] if code in iso639_codes_inverse else code


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
        logging.error('Failed to locate language name DB: %s' % db_path)
        return {}

    converted_languages, duplicated_languages = {}, {}

    for language in languages:
        if language in iso639Codes and iso639Codes[language] in languages:
            duplicated_languages[iso639Codes[language]] = language
            duplicated_languages[language] = iso639Codes[language]

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


def apertium(input, mode_dir, mode, formatting='txt'):
    p1 = Popen(['echo', input], stdout=PIPE)
    logging.getLogger().info('util.apertium({}, {}, {}, {})'
                             .format(repr(input), repr(mode_dir),
                                     repr(mode), repr(formatting)))
    cmd = ['apertium', '-d', mode_dir, '-f', formatting, mode]
    p2 = Popen(cmd, stdin=p1.stdout, stdout=PIPE)
    p1.stdout.close()
    output = p2.communicate()[0].decode('utf-8')
    return output


def bilingual_translate(to_translate, mode_dir, mode):
    p1 = Popen(['echo', to_translate], stdout=PIPE)
    p2 = Popen(['lt-proc', '-b', mode], stdin=p1.stdout, stdout=PIPE, cwd=mode_dir)
    p1.stdout.close()
    output = p2.communicate()[0].decode('utf-8')
    return output


def remove_dot_from_deformat(query, analyses):
    """When using the txt format, a dot is added at EOF (also, double line
    breaks) if the last part of the query isn't itself a dot"""
    if not query[-1] == '.':
        return analyses[:-1]
    else:
        return analyses


def strip_tags(analysis):
    if '<' in analysis:
        return analysis[:analysis.index('<')]
    else:
        return analysis


def get_coverages(text, modes, penalize=False):
    coverages = {}
    for mode, mode_tuple in modes.items():
        coverages[mode] = get_coverage(text, mode_tuple[0], mode_tuple[1], penalize=penalize)
    return coverages


def get_coverage(text, mode, mode_dir, penalize=False):
    analysis = apertium(text, mode, mode_dir)
    lexical_units = remove_dot_from_deformat(text, re.findall(r'\^([^\$]*)\$([^\^]*)', analysis))
    analyzed_lexical_units = list(filter(lambda x: not x[0].split('/')[1][0] in '*&#', lexical_units))
    if len(lexical_units) and not penalize:
        return len(analyzed_lexical_units) / len(lexical_units)
    elif len(lexical_units) and len(text) and penalize:
        return len(analyzed_lexical_units) / len(lexical_units) - (1 - sum([len(lu[0].split('/')[0]) for lu in lexical_units]) / len(text))
    else:
        return -1


def process_per_word(analyzers, taggers, lang, modes, query):
    outputs = {}
    morph_lexical_units = None
    tagger_lexical_units = None
    lexical_unit_re = r'\^([^\$]*)\$'

    if 'morph' in modes or 'biltrans' in modes:
        if lang in analyzers:
            mode_info = analyzers[lang]
            analysis = apertium(query, mode_info[0], mode_info[1])
            morph_lexical_units = remove_dot_from_deformat(query, re.findall(lexical_unit_re, analysis))
            outputs['morph'] = [lu.split('/')[1:] for lu in morph_lexical_units]
            outputs['morph_inputs'] = [strip_tags(lu.split('/')[0]) for lu in morph_lexical_units]
        else:
            return

    if 'tagger' in modes or 'disambig' in modes or 'translate' in modes:
        if lang in taggers:
            mode_info = taggers[lang]
            analysis = apertium(query, mode_info[0], mode_info[1])
            tagger_lexical_units = remove_dot_from_deformat(query, re.findall(lexical_unit_re, analysis))
            outputs['tagger'] = [lu.split('/')[1:] if '/' in lu else lu for lu in tagger_lexical_units]
            outputs['tagger_inputs'] = [strip_tags(lu.split('/')[0]) for lu in tagger_lexical_units]
        else:
            return

    if 'biltrans' in modes:
        if morph_lexical_units:
            outputs['biltrans'] = []
            for lu in morph_lexical_units:
                split_unit = lu.split('/')
                forms = split_unit[1:] if len(split_unit) > 1 else split_unit
                raw_translations = bilingual_translate(''.join(['^%s$' % form for form in forms]), mode_info[0], lang + '.autobil.bin')
                translations = re.findall(lexical_unit_re, raw_translations)
                outputs['biltrans'].append(list(map(lambda x: '/'.join(x.split('/')[1:]), translations)))
                outputs['translate_inputs'] = outputs['morph_inputs']
        else:
            return

    if 'translate' in modes:
        if tagger_lexical_units:
            outputs['translate'] = []
            for lu in tagger_lexical_units:
                split_unit = lu.split('/')
                forms = split_unit[1:] if len(split_unit) > 1 else split_unit
                raw_translations = bilingual_translate(''.join(['^%s$' % form for form in forms]), mode_info[0], lang + '.autobil.bin')
                translations = re.findall(lexical_unit_re, raw_translations)
                outputs['translate'].append(list(map(lambda x: '/'.join(x.split('/')[1:]), translations)))
                outputs['translate_inputs'] = outputs['tagger_inputs']
        else:
            return

    return (outputs, tagger_lexical_units, morph_lexical_units)


def get_timestamp():
    return datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]


def scale_mt_log(status, time, t_info, key, length):
    logging.getLogger('scale-mt').error('%s %s %s html %s %s %s %s %s %s',
                                        get_timestamp(),
                                        timedelta_to_milliseconds(time),
                                        t_info.langpair,
                                        key,
                                        t_info.ip,
                                        t_info.referer,
                                        status,
                                        length,
                                        'null',
                                        )


class TranslationInfo:
    def __init__(self, handler):
        self.langpair = handler.get_argument('langpair')
        self.key = handler.get_argument('key', default='null')
        self.ip = handler.request.headers.get('X-Real-IP', handler.request.remote_ip)
        self.referer = handler.request.headers.get('Referer', 'null')


def add_suggestion(s, suggest_url, edit_token, data):
    content = wiki_get_page(s, suggest_url)
    content = wiki_add_text(content, data)
    edit_result = wiki_edit_page(s, suggest_url, content, edit_token)

    try:
        if edit_result['edit']['result'] == 'Success':
            logging.info('Update of page %s' % (suggest_url))
            return True
        else:
            logging.error('Update of page %s failed: %s' % (suggest_url,
                                                            edit_result))
            return False
    except KeyError:
        return False
