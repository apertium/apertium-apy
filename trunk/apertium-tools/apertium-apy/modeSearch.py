import re, os, logging
from util import toAlpha3Code

def is_loop(dirpath, rootpath, real_root=None):
    if os.path.islink(dirpath):
        # We just descended into a directory via a symbolic link
        # Check if we're referring to a directory that is
        # a parent of our nominal directory
        if not real_root:
            real_root = os.path.abspath(os.path.realpath(rootpath))
        relative = os.path.relpath(dirpath, rootpath)
        nominal_path = os.path.join(real_root, relative)
        real_path = os.path.abspath(os.path.realpath(dirpath))
        for nominal, real in zip(nominal_path.split(os.sep),
                                 real_path.split(os.sep)):
            if nominal != real:
                return False
        else:
            return True
    else:
        return False


def searchPath(rootpath, include_pairs=True, verbosity=1):
    lang_code = r'[a-z]{2,3}(?:_[A-Za-z]+)?'
    type_re = {
        'pair': re.compile(r'({0})-({0})\.mode'.format(lang_code)),
        'analyzer': re.compile(r'(({0}(-{0})?)-(an)?mor(ph)?)\.mode'.format(lang_code)),
        'generator': re.compile(r'(({0}(-{0})?)-gener[A-z]*)\.mode'.format(lang_code)),
        'tagger': re.compile(r'(({0}(-{0})?)-tagger)\.mode'.format(lang_code))
    }
    modes = {
        'pair': [],
        'analyzer': [],
        'generator': [],
        'tagger': [],
    }

    real_root = os.path.abspath(os.path.realpath(rootpath))

    for dirpath, dirnames, files in os.walk(rootpath, followlinks=True):
        if is_loop(dirpath, rootpath, real_root):
            dirnames[:]=[]
            continue
        for filename in [f for f in files if f.endswith('.mode')]:
            for mtype, regex in type_re.items():
                m = regex.match(filename)
                if m:
                    if mtype != 'pair':
                        modename = m.group(1) # e.g. en-es-anmorph
                        langlist = [toAlpha3Code(l) for l in m.group(2).split('-')]
                        lang_src = langlist[0]         # e.g. en
                        lang_pair = '-'.join(langlist) # e.g. en-es
                        dir_of_modes = os.path.dirname(dirpath)
                        mode = (dir_of_modes,
                                modename,
                                lang_pair)
                        modes[mtype].append(mode)
                    elif include_pairs:
                        lang_src = m.group(1)
                        lang_trg = m.group(2)
                        mode = (os.path.join(dirpath, filename),
                                toAlpha3Code(lang_src),
                                toAlpha3Code(lang_trg))
                        modes[mtype].append(mode)

    if verbosity>1:
        for mtype in modes:
            if modes[mtype]:
                logging.info("\"%s\" modes found:\n%s" % (
                    mtype,
                    "\n".join(["\t".join(m) for m in modes[mtype]])))


    return modes
