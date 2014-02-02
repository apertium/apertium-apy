import sqlite3, re, os, logging
from subprocess import Popen, PIPE

iso639Codes = {"abk":"ab","aar":"aa","afr":"af","aka":"ak","sqi":"sq","amh":"am","ara":"ar","arg":"an","hye":"hy","asm":"as","ava":"av","ave":"ae","aym":"ay","aze":"az","bam":"bm","bak":"ba","eus":"eu","bel":"be","ben":"bn","bih":"bh","bis":"bi","bos":"bs","bre":"br","bul":"bg","mya":"my","cat":"ca","cha":"ch","che":"ce","nya":"ny","zho":"zh","chv":"cv","cor":"kw","cos":"co","cre":"cr","hrv":"hr","ces":"cs","dan":"da","div":"dv","nld":"nl","dzo":"dz","eng":"en","epo":"eo","est":"et","ewe":"ee","fao":"fo","fij":"fj","fin":"fi","fra":"fr","ful":"ff","glg":"gl","kat":"ka","deu":"de","ell":"el","grn":"gn","guj":"gu","hat":"ht","hau":"ha","heb":"he","her":"hz","hin":"hi","hmo":"ho","hun":"hu","ina":"ia","ind":"id","ile":"ie","gle":"ga","ibo":"ig","ipk":"ik","ido":"io","isl":"is","ita":"it","iku":"iu","jpn":"ja","jav":"jv","kal":"kl","kan":"kn","kau":"kr","kas":"ks","kaz":"kk","khm":"km","kik":"ki","kin":"rw","kir":"ky","kom":"kv","kon":"kg","kor":"ko","kur":"ku","kua":"kj","lat":"la","ltz":"lb","lug":"lg","lim":"li","lin":"ln","lao":"lo","lit":"lt","lub":"lu","lav":"lv","glv":"gv","mkd":"mk","mlg":"mg","msa":"ms","mal":"ml","mlt":"mt","mri":"mi","mar":"mr","mah":"mh","mon":"mn","nau":"na","nav":"nv","nob":"nb","nde":"nd","nep":"ne","ndo":"ng","nno":"nn","nor":"no","iii":"ii","nbl":"nr","oci":"oc","oji":"oj","chu":"cu","orm":"om","ori":"or","oss":"os","pan":"pa","pli":"pi","fas":"fa","pol":"pl","pus":"ps","por":"pt","que":"qu","roh":"rm","run":"rn","ron":"ro","rus":"ru","san":"sa","srd":"sc","snd":"sd","sme":"se","smo":"sm","sag":"sg","srp":"sr","gla":"gd","sna":"sn","sin":"si","slk":"sk","slv":"sl","som":"so","sot":"st","azb":"az","spa":"es","sun":"su","swa":"sw","ssw":"ss","swe":"sv","tam":"ta","tel":"te","tgk":"tg","tha":"th","tir":"ti","bod":"bo","tuk":"tk","tgl":"tl","tsn":"tn","ton":"to","tur":"tr","tso":"ts","tat":"tt","twi":"tw","tah":"ty","uig":"ug","ukr":"uk","urd":"ur","uzb":"uz","ven":"ve","vie":"vi","vol":"vo","wln":"wa","cym":"cy","wol":"wo","fry":"fy","xho":"xh","yid":"yi","yor":"yo","zha":"za","zul":"zu", "hbs":"sh", "arg":"an", "pes":"fa"}
'''
    Bootstrapped from https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes using
        var out = {};
        $.each($('tr', $('table').get(1)), function(i, elem) { var rows = $('td', elem); out[$(rows[5]).text()] = $(rows[4]).text(); });
        JSON.stringify(out);
'''

dbConn = None

def openDB(dbPath):
    global dbConn
    if not dbConn:
        if os.path.exists(dbPath):
            dbConn = sqlite3.connect(dbPath)


def toAlpha2Code(code):
    return iso639Codes[code] if code in iso639Codes else code

def toAlpha3Code(code):
    iso639CodesInverse = {v: k for k, v in iso639Codes.items()}
    return iso639CodesInverse[code] if code in iso639CodesInverse else code

def getLocalizedLanguages(locale, dbPath, languages=[]):
    global dbConn
    locale = toAlpha2Code(locale)
    languages = list(set(languages))
    
    convertedLanguages, duplicatedLanguages = {}, {}
    for language in languages:
        if language in iso639Codes and iso639Codes[language] in languages:
            duplicatedLanguages[iso639Codes[language]] = language
            duplicatedLanguages[language] = iso639Codes[language]
        convertedLanguages[toAlpha2Code(language)] = language

    output = {}
    #if os.path.exists(dbPath):
    #    conn = sqlite3.connect(dbPath)
    openDB(dbPath)
        c = dbConn.cursor()
        languageResults = c.execute('select * from languageNames where lg=?', (locale, )).fetchall()
        if languages:
            for languageResult in languageResults:
                if languageResult[2] in convertedLanguages:
                    language, languageName = languageResult[2], languageResult[3]
                    output[convertedLanguages[language]] = languageName
                    if language in duplicatedLanguages:
                        output[language] = languageName
                        output[duplicatedLanguages[language]] = languageName
        else:
            for languageResult in languageResults:
                output[languageResult[2]] = languageResult[3]
    else:
        logging.error('Failed to locate language name DB: %s' % dbPath)
    return output
    
def apertium(input, dir, mode, formatting=None):
    p1 = Popen(['echo', input], stdout=PIPE)
    if formatting:
        p2 = Popen(['apertium', '-d . -f %s' % formatting, mode], stdin=p1.stdout, stdout=PIPE, cwd=dir)
    else:
        p2 = Popen(['apertium', '-d .', mode], stdin=p1.stdout, stdout=PIPE, cwd=dir)
    p1.stdout.close()
    output = p2.communicate()[0].decode('utf-8')
    return output
    
def bilingualTranslate(toTranslate, dir, mode):
    p1 = Popen(["echo", toTranslate], stdout=PIPE)
    p2 = Popen(["lt-proc", "-b", mode], stdin=p1.stdout, stdout=PIPE, cwd=dir)
    p1.stdout.close()
    output = p2.communicate()[0].decode('utf-8')
    return output
    
def removeLast(query, analyses):
    if not query[-1] == '.':
        return analyses[:-1]
    else:
        return analyses
        
def stripTags(analysis):
    if '<' in analysis:
        return analysis[:analysis.index('<')]
    else:
        return analysis
        
def getCoverages(text, modes, penalize=False):
    coverages = {}
    for mode, modeTuple in modes.items():
        coverages[mode] = getCoverage(text, modeTuple[0], modeTuple[1], penalize=penalize)
    return coverages
        
def getCoverage(text, mode, modeDir, penalize=False):
    analysis = apertium(text, mode, modeDir)
    lexicalUnits = removeLast(text, re.findall(r'\^([^\$]*)\$([^\^]*)', analysis))
    analyzedLexicalUnits = list(filter(lambda x: not x[0].split('/')[1][0] in '*&#', lexicalUnits))
    if len(lexicalUnits) and not penalize:
        return len(analyzedLexicalUnits) / len(lexicalUnits)
    elif len(lexicalUnits) and len(text) and penalize:
        return len(analyzedLexicalUnits) / len(lexicalUnits) - (1 - sum([len(lexicalUnit[0].split('/')[0]) for lexicalUnit in lexicalUnits]) / len(text))
    else:
        return -1

def processPerWord(analyzers, taggers, lang, modes, query):
    outputs = {}
    morph_lexicalUnits = None
    tagger_lexicalUnits = None
    lexicalUnitRE = r'\^([^\$]*)\$'
    
    if 'morph' in modes or 'biltrans' in modes:
        if lang in analyzers:
            modeInfo = analyzers[lang]
            analysis = apertium(query, modeInfo[0], modeInfo[1])
            morph_lexicalUnits = removeLast(query, re.findall(lexicalUnitRE, analysis))
            outputs['morph'] = [lexicalUnit.split('/')[1:] for lexicalUnit in morph_lexicalUnits]
            outputs['morph_inputs'] = [stripTags(lexicalUnit.split('/')[0]) for lexicalUnit in morph_lexicalUnits]
        else:
            return
            
    if 'tagger' in modes or 'disambig' in modes or 'translate' in modes:
        if lang in taggers:
            modeInfo = taggers[lang]
            analysis = apertium(query, modeInfo[0], modeInfo[1])
            tagger_lexicalUnits = removeLast(query, re.findall(lexicalUnitRE, analysis))
            outputs['tagger'] = [lexicalUnit.split('/')[1:] if '/' in lexicalUnit else lexicalUnit for lexicalUnit in tagger_lexicalUnits]
            outputs['tagger_inputs'] = [stripTags(lexicalUnit.split('/')[0]) for lexicalUnit in tagger_lexicalUnits]
        else:
            return
            
    if 'biltrans' in modes:
        if morph_lexicalUnits:
            outputs['biltrans'] = []
            for lexicalUnit in morph_lexicalUnits:
                splitUnit = lexicalUnit.split('/')
                forms = splitUnit[1:] if len(splitUnit) > 1 else splitUnit
                rawTranslations = bilingualTranslate(''.join(['^%s$' % form for form in forms]), modeInfo[0], lang + '.autobil.bin')
                translations = re.findall(lexicalUnitRE, rawTranslations)
                outputs['biltrans'].append(list(map(lambda x: '/'.join(x.split('/')[1:]), translations)))
                outputs['translate_inputs'] = outputs['morph_inputs']
        else:
            return
            
    if 'translate' in modes:
        if tagger_lexicalUnits:
            outputs['translate'] = []
            for lexicalUnit in tagger_lexicalUnits:
                splitUnit = lexicalUnit.split('/')
                forms = splitUnit[1:] if len(splitUnit) > 1 else splitUnit
                rawTranslations = bilingualTranslate(''.join(['^%s$' % form for form in forms]), modeInfo[0], lang + '.autobil.bin')
                translations = re.findall(lexicalUnitRE, rawTranslations)
                outputs['translate'].append(list(map(lambda x: '/'.join(x.split('/')[1:]), translations)))
                outputs['translate_inputs'] = outputs['tagger_inputs']
        else:
            return
            
    return (outputs, tagger_lexicalUnits, morph_lexicalUnits)
    
