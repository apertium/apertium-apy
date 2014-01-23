import re, os
from tools import toAlpha3Code

def searchPath(pairsPath):
    # TODO: this doesn't get es-en_GB and such. If it's supposed
    # to work on the SVN directories (as opposed to installed
    # pairs), it should parse modes.xml and grab all and only
    # modes that have install="yes"
    REmodeFile = re.compile("([a-z]{2,3})-([a-z]{2,3})\.mode")
    REmorphFile = re.compile("(([a-z]{2,3}(-[a-z]{2,3})?)-(an)?mor(ph)?)\.mode")
    REgenerFile = re.compile("(([a-z]{2,3}(-[a-z]{2,3})?)-gener[A-z]*)\.mode")
    REtaggerFile = re.compile("(([a-z]{2,3}(-[a-z]{2,3})?)-tagger)\.mode")

    pairs = []
    analyzers = []
    generators = []
    taggers = []
    
    contents = os.listdir(pairsPath)
    for content in contents:
        curContent = os.path.join(pairsPath, content)
        if os.path.isdir(curContent):
            curMode = os.path.join(curContent, "modes")
            if os.path.isdir(curMode):
                modeFiles = os.listdir(curMode)
                for modeFile in modeFiles:
                    if REmodeFile.match(modeFile):
                        l1 = REmodeFile.sub("\g<1>", modeFile)
                        l2 = REmodeFile.sub("\g<2>", modeFile)
                        pairTuple = (os.path.join(curContent, 'modes', modeFile), toAlpha3Code(l1), toAlpha3Code(l2))
                        pairs.append(pairTuple)
                    elif REmorphFile.match(modeFile):
                        mode = REmorphFile.sub("\g<1>", modeFile) #en-es-anmorph
                        lang = '-'.join(map(toAlpha3Code, REmorphFile.sub("\g<2>", modeFile).split('-'))) #en-es
                        analyzerTuple = (curContent, mode, lang)
                        analyzers.append(analyzerTuple)
                    elif REgenerFile.match(modeFile):
                        mode = REgenerFile.sub("\g<1>", modeFile) #en-es-generador
                        lang = '-'.join(map(toAlpha3Code, REgenerFile.sub("\g<2>", modeFile).split('-'))) #en-es
                        generatorTuple = (curContent, mode, lang)
                        generators.append(generatorTuple)
                    elif REtaggerFile.match(modeFile):
                        mode = REtaggerFile.sub("\g<1>", modeFile) #en-es-tagger
                        lang = '-'.join(map(toAlpha3Code, REtaggerFile.sub("\g<2>", modeFile).split('-'))) #en-es
                        taggerTuple = (curContent, mode, lang)
                        taggers.append(taggerTuple)
                        
    return pairs, analyzers, generators, taggers
    
    