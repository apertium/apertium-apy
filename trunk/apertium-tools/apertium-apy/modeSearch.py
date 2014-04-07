import re, os
from util import toAlpha3Code

def searchPath(path):
    langCode = r'[a-z]{2,3}(?:_[A-Za-z]+)?'
    modes = {
        'pair': (re.compile(r'({0})-({0})\.mode'.format(langCode)), []),
        'analyzer': (re.compile(r'(({0}(-{0})?)-(an)?mor(ph)?)\.mode'.format(langCode)), []),
        'generator': (re.compile(r'(({0}(-{0})?)-gener[A-z]*)\.mode'.format(langCode)), []),
        'tagger': (re.compile(r'(({0}(-{0})?)-tagger)\.mode'.format(langCode)), [])
    }
    langDirRE = re.compile(r'apertium-([a-z]{2,3})(-([a-z]{2,3}))?$')

    for (dirpath, dirnames, filenames) in os.walk(path, followlinks=True):
        currentDir = os.path.normpath(dirpath).split(os.sep)[-1]
        if langDirRE.match(currentDir):
            if any([filename == 'modes.xml' for filename in filenames]):
                for filename in filenames:
                    if modes['pair'][0].match(filename):
                        l1, l2 = modes['pair'][0].sub('\g<1>', filename), modes['pair'][0].sub('\g<2>', filename)
                        pairTuple = (os.path.join(dirpath, filename), toAlpha3Code(l1), toAlpha3Code(l2))
                        modes['pair'][1].append(pairTuple)

            modesPath = os.path.join(dirpath, 'modes')
            if os.path.isdir(modesPath):
                for filename in next(os.walk(modesPath))[2]:
                    for mode, info in modes.items():
                        if mode != 'pair' and info[0].match(filename):
                            mode = info[0].sub('\g<1>', filename) #e.g. en-es-anmorph
                            lang = '-'.join(map(toAlpha3Code, info[0].sub('\g<2>', filename).split('-'))) #e.g. en-es
                            info[1].append((dirpath, mode, lang))

            del dirnames[:]
        elif len(os.path.normpath(dirpath).replace(os.path.normpath(path), '').split(os.sep)) > 5:
            del dirnames[:]

    return {mode: result[1] for mode, result in modes.items()}