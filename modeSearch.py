import re, os
from tools import toAlpha3Code

def searchPath(path):
    modes = {
        'pair': (re.compile(r'([a-z]{2,3})-([a-z]{2,3})\.mode'), []),
        'analyzer': (re.compile(r'(([a-z]{2,3}(-[a-z]{2,3})?)-(an)?mor(ph)?)\.mode'), []),
        'generator': (re.compile(r'(([a-z]{2,3}(-[a-z]{2,3})?)-gener[A-z]*)\.mode'), []),
        'tagger': (re.compile(r'(([a-z]{2,3}(-[a-z]{2,3})?)-tagger)\.mode'), [])
    }
    langDirRE = re.compile(r'apertium-([a-z]{2,3})(-([a-z]{2,3}))?$')

    for (dirpath, dirnames, filenames) in os.walk(path):
        currentDir = os.path.normpath(dirpath).split(os.sep)[-1]
        if langDirRE.match(currentDir):
            if any([filename == 'modes.xml' for filename in filenames]):
                for filename in filenames:
                    if modes['pair'][0].match(filename):
                        l1, l2 = modes['pair'][0].sub('\g<1>', filename), modes['pair'][0].sub('\g<2>', filename)
                        pairTuple = (dirpath, toAlpha3Code(l1), toAlpha3Code(l2))
                        modes['pair'][1].append(pairTuple)
        elif currentDir == 'modes':
            for filename in filenames:
                for mode, info in modes.items():
                    if mode != 'pair' and info[0].match(filename):
                        mode = info[0].sub('\g<1>', filename) #e.g. en-es-anmorph
                        lang = '-'.join(map(toAlpha3Code, info[0].sub('\g<2>', filename).split('-'))) #e.g. en-es
                        info[1].append((dirpath, mode, lang))
    
    return {mode: result[1] for mode, result in modes.items()}
