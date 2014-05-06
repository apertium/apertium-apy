#!/usr/bin/python3

import urllib.request
import urllib.parse
import json
from sys import argv

import html.parser
unescape = html.parser.HTMLParser().unescape

tests = {
    "afr-nld": ("ek", "ik"),
    "ara-mlt": ("و", "u"),
    "arg-spa": ("a", "la"),
    "ast-spa": ("nin", "ni"),
    "bre-fra": ("Na", "Ni"),
    "bul-mkd": ("аз", "јас"),
    "cat-eng": ("Ens", "Us"),
    "cat-eng_US": ("Ens", "Us"),
    "cat-epo": ("Per", "Por"),
    "cat-fra": ("per", "pour"),
    "cat-oci": ("", ""),
    "cat-oci_aran": ("", ""),
    "cat-por": ("tinc", "tenho"),
    "cat-spa": ("Jo", "Yo"),
    "cym-eng": ("", ""),
    "dan-swe": ("hvad", "vad"),
    "eng-cat": ("us", "ens"),
    "eng-epo": ("And", "Kaj"),
    "eng-glg": ("Only", "Só"),
    "eng-spa": ("hello", "hola"),
    "epo-eng": ("kaj", "and"),
    "eus-eng": ("", ""),
    "eus-spa": ("", ""),
    "fra-cat": ("pour", "per"),
    "fra-epo": ("Pour", "Por"),
    "fra-spa": ("Je", "Yo"),
    "glg-eng": ("Teño", "Have"),
    "glg-por": ("teño", "tenho"),
    "glg-spa": ("Só", "Solo"),
    "hat-eng": ("", ""),
    "hbs-slv": ("", ""),
    "ind-msa": ("", ""),
    "isl-eng": ("Grein", "Article"),
    "isl-swe": ("af", "av"),
    "ita-cat": ("", ""),
    "kaz-tat": ("ул", "ол"),
    "mkd-bul": ("јас", "аз"),
    "mkd-eng": ("", ""),
    "mlt-ara": ("u", "و"),
    "nld-afr": ("ik", "ek"),
    "nno-dan": ("kva", "hvad"),
    "nno-nno_a": ("å ete", "å eta"),
    "nno-nob": ("korleis", "hvordan"),
    "nno_a-nno": ("", ""),
    "nno_a-nno": ("å eta", "å ete"),
    "nob-dan": ("hva", "hvad"),
    "nob-nno": ("hvordan", "korleis"),
    "nob-nno_a": ("å spise", "å eta"),
    "oci-cat": ("", ""),
    "oci-spa": ("", ""),
    "oci_aran-cat": ("", ""),
    "oci_aran-spa": ("", ""),
    "por-cat": ("tenho", "tinc"),
    "por-glg": ("tenho", "teño"),
    "por-spa": ("", ""),
    "ron-spa": ("", ""),
    "slv-hbs_BS": ("", ""),
    "slv-hbs_HR": ("", ""),
    "slv-hbs_SR": ("", ""),
    "sme-nob": ("ja", "og"),
    "spa-ast": ("ni", "nin"),
    "spa-cat": ("yo", "jo"),
    "spa-cat_valencia": ("", ""),
    "spa-eng": ("hola", "hello"),
    "spa-eng_US": ("hola", "hello"),
    "spa-epo": ("", ""),
    "spa-fra": ("", ""),
    "spa-glg": ("", ""),
    "spa-oci": ("", ""),
    "spa-oci_aran": ("", ""),
    "spa-por": ("tengo", "tenho"),
    "spa-por_BR": ("tengo", "tenho"),
    "swe-dan": ("vad", "hvad"),
    "swe-isl": ("Av", "Af"),
    "tat-kaz": ("ол", "ул"),
}

def test_pair(pair, host):
    intext=urllib.parse.quote_plus( tests[pair][0].strip() )
    if not intext:
        print ("no input text for %s" %(pair,))
        return False
    expected=tests[pair][1].strip()
    langpair=pair.replace('-', '|')
    try:
        response = urllib.request.urlopen('%s/translate?langpair=%s&q=%s' % (host, langpair, intext)).read().decode('utf-8')
    except urllib.error.HTTPError as e:
        print( "%s failed with error code %s and reason: %s" %(pair,e.code,e.reason))
        return False
    js = json.loads(response)
    translation_raw = js['responseData']['translatedText']
    translation = unescape(urllib.parse.unquote_plus(translation_raw)).strip()
    if translation != expected:
        print ("%s: expected '%s', got '%s' (for input: %s)" %(pair, expected, translation, intext))
        return False
    else:
        return True

def test_all(host):
    total=len(tests)
    good=0
    for pair in tests:
        if test_pair(pair, host):
            good+=1
    print("\n%d of %d tests passed" % (good, total))


if __name__ == "__main__":
    test_all(argv[1])
