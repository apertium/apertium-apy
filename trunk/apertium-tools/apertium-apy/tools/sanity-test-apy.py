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
    "bul-mkd": ("", ""),
    "cat-eng": ("", ""),
    "cat-eng_US": ("", ""),
    "cat-epo": ("", ""),
    "cat-fra": ("", ""),
    "cat-oci": ("", ""),
    "cat-oci_aran": ("", ""),
    "cat-por": ("", ""),
    "cat-spa": ("", ""),
    "cym-eng": ("", ""),
    "dan-swe": ("hvad", "vad"),
    "eng-cat": ("", ""),
    "eng-epo": ("", ""),
    "eng-glg": ("", ""),
    "eng-spa": ("hello", "hola"),
    "epo-eng": ("", ""),
    "eus-eng": ("", ""),
    "eus-spa": ("", ""),
    "fra-cat": ("", ""),
    "fra-epo": ("", ""),
    "fra-spa": ("", ""),
    "glg-eng": ("", ""),
    "glg-por": ("", ""),
    "glg-spa": ("", ""),
    "hat-eng": ("", ""),
    "hbs-slv": ("", ""),
    "ind-msa": ("", ""),
    "isl-eng": ("Grein", "Article"),
    "isl-swe": ("af", "av"),
    "ita-cat": ("", ""),
    "kaz-tat": ("ул", "ол"),
    "mkd-bul": ("", ""),
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
    "por-cat": ("", ""),
    "por-glg": ("", ""),
    "por-spa": ("", ""),
    "ron-spa": ("", ""),
    "slv-hbs_BS": ("", ""),
    "slv-hbs_HR": ("", ""),
    "slv-hbs_SR": ("", ""),
    "sme-nob": ("ja", "og"),
    "spa-ast": ("ni", "nin"),
    "spa-cat": ("", ""),
    "spa-cat_valencia": ("", ""),
    "spa-eng": ("hola", "hello"),
    "spa-eng_US": ("hola", "hello"),
    "spa-epo": ("", ""),
    "spa-fra": ("", ""),
    "spa-glg": ("", ""),
    "spa-oci": ("", ""),
    "spa-oci_aran": ("", ""),
    "spa-por": ("", ""),
    "spa-por_BR": ("", ""),
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
    for pair in tests:
        test_pair(pair, host)


if __name__ == "__main__":
    test_all(argv[1])
