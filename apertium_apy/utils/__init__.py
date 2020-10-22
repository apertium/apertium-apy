import logging
import re
from datetime import datetime
from functools import wraps
from threading import Thread

from tornado import gen
from tornado.process import Subprocess

from apertium_apy.missingdb import timedelta_to_milliseconds

iso639_codes = {'abk': 'ab', 'aar': 'aa', 'afr': 'af', 'aka': 'ak', 'sqi': 'sq', 'amh': 'am', 'ara': 'ar', 'arg': 'an', 'hye': 'hy', 'asm': 'as', 'ava': 'av', 'ave': 'ae', 'aym': 'ay', 'aze': 'az', 'bam': 'bm', 'bak': 'ba', 'eus': 'eu', 'bel': 'be', 'ben': 'bn', 'bih': 'bh', 'bis': 'bi', 'bos': 'bs', 'bre': 'br', 'bul': 'bg', 'mya': 'my', 'cat': 'ca', 'cha': 'ch', 'che': 'ce', 'nya': 'ny', 'zho': 'zh', 'chv': 'cv', 'cor': 'kw', 'cos': 'co', 'cre': 'cr', 'hrv': 'hr', 'ces': 'cs', 'dan': 'da', 'div': 'dv', 'nld': 'nl', 'dzo': 'dz', 'eng': 'en', 'epo': 'eo', 'est': 'et', 'ewe': 'ee', 'fao': 'fo', 'fij': 'fj', 'fin': 'fi', 'fra': 'fr', 'ful': 'ff', 'glg': 'gl', 'kat': 'ka', 'deu': 'de', 'ell': 'el', 'grn': 'gn', 'guj': 'gu', 'hat': 'ht', 'hau': 'ha', 'heb': 'he', 'her': 'hz', 'hin': 'hi', 'hmo': 'ho', 'hun': 'hu', 'ina': 'ia', 'ind': 'id', 'ile': 'ie', 'gle': 'ga', 'ibo': 'ig', 'ipk': 'ik', 'ido': 'io', 'isl': 'is', 'ita': 'it', 'iku': 'iu', 'jpn': 'ja', 'jav': 'jv', 'kal': 'kl', 'kan': 'kn', 'kau': 'kr', 'kas': 'ks', 'kaz': 'kk', 'khm': 'km', 'kik': 'ki', 'kin': 'rw', 'kir': 'ky', 'kom': 'kv', 'kon': 'kg', 'kor': 'ko', 'kur': 'ku', 'kua': 'kj', 'lat': 'la', 'ltz': 'lb', 'lug': 'lg', 'lim': 'li', 'lin': 'ln', 'lao': 'lo', 'lit': 'lt', 'lub': 'lu', 'lav': 'lv', 'glv': 'gv', 'mkd': 'mk', 'mlg': 'mg', 'msa': 'ms', 'mal': 'ml', 'mlt': 'mt', 'mri': 'mi', 'mar': 'mr', 'mah': 'mh', 'mon': 'mn', 'nau': 'na', 'nav': 'nv', 'nob': 'nb', 'nde': 'nd', 'nep': 'ne', 'ndo': 'ng', 'nno': 'nn', 'nor': 'no', 'iii': 'ii', 'nbl': 'nr', 'oci': 'oc', 'oji': 'oj', 'chu': 'cu', 'orm': 'om', 'ori': 'or', 'oss': 'os', 'pan': 'pa', 'pli': 'pi', 'fas': 'fa', 'pol': 'pl', 'pus': 'ps', 'por': 'pt', 'que': 'qu', 'roh': 'rm', 'run': 'rn', 'ron': 'ro', 'rus': 'ru', 'san': 'sa', 'srd': 'sc', 'snd': 'sd', 'sme': 'se', 'smo': 'sm', 'sag': 'sg', 'srp': 'sr', 'gla': 'gd', 'sna': 'sn', 'sin': 'si', 'slk': 'sk', 'slv': 'sl', 'som': 'so', 'sot': 'st', 'azb': 'az', 'spa': 'es', 'sun': 'su', 'swa': 'sw', 'ssw': 'ss', 'swe': 'sv', 'tam': 'ta', 'tel': 'te', 'tgk': 'tg', 'tha': 'th', 'tir': 'ti', 'bod': 'bo', 'tuk': 'tk', 'tgl': 'tl', 'tsn': 'tn', 'ton': 'to', 'tur': 'tr', 'tso': 'ts', 'tat': 'tt', 'twi': 'tw', 'tah': 'ty', 'uig': 'ug', 'ukr': 'uk', 'urd': 'ur', 'uzb': 'uz', 'ven': 've', 'vie': 'vi', 'vol': 'vo', 'wln': 'wa', 'cym': 'cy', 'wol': 'wo', 'fry': 'fy', 'xho': 'xh', 'yid': 'yi', 'yor': 'yo', 'zha': 'za', 'zul': 'zu', 'hbs': 'sh', 'arg': 'an', 'pes': 'fa'}  # noqa: E501
"""
    Bootstrapped from https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes using
        var out = {};
        $.each($('tr', $('table').get(1)), function(i, elem) { var rows = $('td', elem); out[$(rows[5]).text()] = $(rows[4]).text(); });
        JSON.stringify(out);
"""


def run_async_thread(func):
    @wraps(func)
    def async_func(*args, **kwargs):
        func_hl = Thread(target=func, args=args, kwargs=kwargs)
        func_hl.start()
        return func_hl

    return async_func


def to_alpha2_code(code):
    if '_' in code:
        code, variant = code.split('_')
        return '%s_%s' % ((iso639_codes[code], variant) if code in iso639_codes else (code, variant))
    else:
        return iso639_codes[code] if code in iso639_codes else code


def to_alpha3_code(code):
    iso639_codes_inverse = {v: k for k, v in iso639_codes.items()}
    if '_' in code:
        code, variant = code.split('_')
        return '%s_%s' % ((iso639_codes_inverse[code], variant) if code in iso639_codes_inverse else (code, variant))
    else:
        return iso639_codes_inverse[code] if code in iso639_codes_inverse else code


def remove_dot_from_deformat(query, analyses):
    """When using the txt format, a dot is added at EOF (also, double line
    breaks) if the last part of the query isn't itself a dot"""
    dotana = re.compile(r'^\.[/<]')
    if len(query) > 0 and len(analyses) > 0 and not query[-1] == '.' and re.search(dotana, analyses[-1][0]):
        return analyses[:-1]
    else:
        return analyses


async def apertium(apertium_input, mode_dir, mode, formatting='txt'):
    logging.debug('util.apertium({!r}, {!r}, {!r}, {!r})'.format(apertium_input, mode_dir, mode, formatting))
    proc = Subprocess(['apertium', '-d', mode_dir, '-f', formatting, mode], stdin=Subprocess.STREAM, stdout=Subprocess.STREAM)
    await proc.stdin.write(apertium_input.encode('utf-8'))
    proc.stdin.close()
    output = await proc.stdout.read_until_close()
    proc.stdout.close()
    return output.decode('utf-8')


@gen.coroutine
def get_coverages(text, modes, penalize=False):
    coverages = {}
    for mode, mode_tuple in modes.items():
        coverages[mode] = yield get_coverage(text, mode_tuple[0], mode_tuple[1], penalize=penalize)
    return coverages


@gen.coroutine
def get_coverage(text, mode, mode_dir, penalize=False):
    analysis = yield apertium(text, mode, mode_dir)
    lexical_units = remove_dot_from_deformat(text, re.findall(r'\^([^\$]*)\$([^\^]*)', analysis))
    analyzed_lexical_units = list(filter(lambda x: not x[0].split('/')[1][0] in '*&#', lexical_units))
    if len(lexical_units) and not penalize:
        return len(analyzed_lexical_units) / len(lexical_units)
    elif len(lexical_units) and len(text) and penalize:
        return len(analyzed_lexical_units) / len(lexical_units) - (1 - sum([len(lu[0].split('/')[0]) for lu in lexical_units]) / len(text))
    else:
        return -1


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
