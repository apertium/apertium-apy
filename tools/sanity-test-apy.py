#!/usr/bin/python3

import urllib.request
import urllib.parse
import socket
import json
import sys

import html.parser
unescape = html.parser.HTMLParser().unescape

TIMEOUT=15
tests = {
    "hbs-eng": ("jeziku", "language"),
    "hin-urd": ("लेख हैं", "تحریر ہیں"),
    "urd-hin": ("تحریر ہیں", "लेख हैं"),
    "afr-nld": ("ek", "ik"),
    "ara-mlt": ("و", "u"),
    "ara-mlt_translit": ("و", "u"),
    "arg-cat": ("e", "és"),
    "cat-arg": ("la", "a"),
    "arg-spa": ("e", "es"),
    "spa-arg": ("la", "a"),
    "ast-spa": ("nin", "ni"),
    "bre-fra": ("Na", "Ni"),
    "bul-mkd": ("аз", "јас"),
    "cat-eng": ("Ens", "Us"),
    "cat-eng_US": ("Ens", "Us"),
    "cat-epo": ("Per", "Por"),
    "cat-fra": ("per", "pour"),
    "cat-oci": ("Tinc", "Ai"),
    "cat-oci_aran": ("Tinc", "È"),
    "cat-por": ("tinc", "tenho"),
    "cat-spa": ("Jo", "Yo"),
    "cym-eng": ("Yn", "In"),
    "eng-cat": ("us", "ens"),
    "eng-epo": ("And", "Kaj"),
    "eng-glg": ("Only", "Só"),
    "eng-spa": ("hello", "hola"),
    "epo-eng": ("kaj", "and"),
    "eus-eng": ("kaixo", "hello"),
    "eus-spa": ("kaixo", "hola"),
    "fra-cat": ("pour", "per"),
    "fra-epo": ("Pour", "Por"),
    "fra-spa": ("Je", "Yo"),
    "glg-eng": ("Teño", "Have"),
    "glg-por": ("teño", "tenho"),
    "glg-spa": ("Teño", "Tengo"),
    "hbs-slv": ("Slobodnu", "Svobodnemu"),
    "ind-msa": ("sedangkan", "manakala"),
    "msa-ind": ("manakala", "sedangkan"),
    "isl-eng": ("Grein", "Article"),
    "isl-swe": ("af", "av"),
    "ita-cat": ("dire", "dir"),
    "kaz-tat": ("ол", "ул"),
    "mkd-bul": ("јас", "аз"),
    "mkd-eng": ("триесет", "thirty"),
    "mlt-ara": ("u", "و"),
    "nld-afr": ("ik", "ek"),
    "nno-dan": ("kva", "hvad"),
    "dan-nno": ("hvad", "kva"),
    "dan-nob": ("hvad", "hva"),
    "nno_e-nno": ("korleis", "korleis"),
    "nno-nob": ("korleis", "hvordan"),
    "nno-nno_e": ("korleis", "korleis"),
    "nob-dan": ("hva", "hvad"),
    "nob-nno": ("hvordan", "korleis"),
    "nob-nno_e": ("å spise", "å ete"),
    "oci-cat": ("Mès tanben", "Sinó també"),
    "oci-spa": ("Mès tanben", "Sino también"),
    "oci_aran-cat": ("Mas tanben", "Sinó també"),
    "oci_aran-spa": ("Mas tanben", "Sino también"),
    "por-cat": ("tenho", "tinc"),
    "por-glg": ("tenho", "teño"),
    "por-spa": ("tenho", "tengo"),
    "ron-spa": ("Liberă", "Libre"),
    "slv-hbs_BS": ("Svobodnemu", "Slobodnu"),
    "slv-hbs_HR": ("Svobodnemu", "Slobodnu"),
    "slv-hbs_SR": ("Svobodnemu", "Slobodnu"),
    "slv-bos": ("Svobodnemu", "Slobodnu"),
    "slv-hrv": ("Svobodnemu", "Slobodnu"),
    "slv-srp": ("Svobodnemu", "Slobodnu"),
    "sme-nob": ("ja", "og"),
    "spa-ast": ("ni", "nin"),
    "spa-cat": ("yo", "jo"),
    "spa-cat_valencia": ("tengo", "tinc"),
    "spa-eng": ("hola", "hello"),
    "spa-eng_US": ("hola", "hello"),
    "spa-epo": ("Tengo", "Havas"),
    "spa-fra": ("Tengo", "J'ai"),
    "spa-glg": ("Tengo", "Teño"),
    "spa-oci": ("Tengo", "Ai"),
    "spa-oci_aran": ("Tengo", "È"),
    "spa-por": ("tengo", "tenho"),
    "spa-por_BR": ("tengo", "tenho"),
    "swe-dan": ("vad", "hvad"),
    "swe-isl": ("Av", "Af"),
    "tat-kaz": ("ул", "ол"),
}

def test_pair(pair, host):
    intext=urllib.parse.quote_plus( tests[pair][0].strip() )
    if not intext:
        print ("no input text for %s" %(pair,))
        return False
    expected=tests[pair][1].strip()
    langpair=pair.replace('-', '|')
    try:
        response = urllib.request.urlopen('%s/translate?langpair=%s&q=%s' % (host, langpair, intext), timeout=TIMEOUT).read().decode('utf-8')
    except urllib.error.HTTPError as e:
        print("%s failed with error code %s and reason: %s" %(pair,e.code,e.reason))
        return False
    except socket.timeout as e:
        print("%s failed: %s" %(pair, e,))
        return False
    js = json.loads(response)
    translation_raw = js['responseData']['translatedText']
    translation = unescape(urllib.parse.unquote_plus(translation_raw)).strip()
    if translation != expected:
        print ("%s: expected '%s', got '%s' (for input: %s)" %(pair, expected, translation, intext))
        return False
    else:
        return True

def missing_tests(host):
    try:
        response = urllib.request.urlopen('%s/listPairs' % (host,), timeout=TIMEOUT).read().decode('utf-8')
    except urllib.error.HTTPError as e:
        print("listPairs failed with error code %s and reason: %s" %(e.code,e.reason))
        return False
    except socket.timeout as e:
        print("listPairs failed: %s" %(e,))
        return False
    js = json.loads(response)
    allgood=True
    for pair in js['responseData']:
        pairstr = "%s-%s" % (pair['sourceLanguage'],pair['targetLanguage'])
        if pairstr not in tests:
            print("Missing a test for %s" % (pairstr,))
            allgood = False
    return allgood

def dot():
    sys.stdout.write('.')
    sys.stdout.flush()

def test_all(host):
    missing_tests(host)
    dot()
    total=len(tests)
    good=0
    for pair in tests:
        if test_pair(pair, host):
            good+=1
        dot()
    print("\n%d of %d tests passed" % (good, total))
    print("\nNow run the script again to see which pipelines got clogged.\n")
    if good != total:
        exit(1)


if __name__ == "__main__":
    test_all(sys.argv[1])
