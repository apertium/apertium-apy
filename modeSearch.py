import re, os
from util import toAlpha3Code

def searchPath(path):
    variant_mode = re.compile(r'([a-z]{2,3})(_[a-zA-Z]+)?-([a-z]{2,3})(_[a-zA-Z]+)?\.mode');
    modes = {
        'pair': (re.compile(r'([a-z]{2,3})-([a-z]{2,3})\.mode'), []),
        'analyzer': (re.compile(r'(([a-z]{2,3}(-[a-z]{2,3})?)-(an)?mor(ph)?)\.mode'), []),
        'generator': (re.compile(r'(([a-z]{2,3}(-[a-z]{2,3})?)-gener[A-z]*)\.mode'), []),
        'tagger': (re.compile(r'(([a-z]{2,3}(-[a-z]{2,3})?)-tagger)\.mode'), [])
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
                    elif variant_mode.match(filename): 
                        l1 = filename.replace('.mode', '').split('-')[0];
                        l2 = filename.replace('.mode', '').split('-')[1];
                        l1code = '';
                        l2code = '';
                        l1variant = '';
                        l2variant = '';
                        print('var:', filename, 'l1:',l1,'l2:',l2);
                        if '_' in l1: #{
                            l1code = toAlpha3Code(l1.split('_')[0])
                            l1variant = l1.split('_')[1];
                        else: #{
                            l1code = toAlpha3Code(l1);
                        #}
                        if '_' in l2: #{
                            l2code = toAlpha3Code(l2.split('_')[0])
                            l2variant = l2.split('_')[1];
                        else: #{
                            l2code = toAlpha3Code(l2);
                        #}
                        if l1variant != '': #{
                            l1code = l1code + '_' + l1variant;
                        #}
                        if l2variant != '': #{
                            l2code = l2code + '_' + l2variant;
                        #}
                        pairTuple = (os.path.join(dirpath, filename), l1code, l2code)
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
