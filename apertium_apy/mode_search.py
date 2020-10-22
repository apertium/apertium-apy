import re
import os
import logging

from apertium_apy.utils import to_alpha3_code

if False:
    from typing import Dict, List, Tuple  # noqa: F401


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


def search_path(rootpath, include_pairs=True, verbosity=1):
    lang_code = r'[a-z]{2,3}(?:_[A-Za-z0-9]+)?'
    type_re = {
        'pair': re.compile(r'({0})-({0})\.mode'.format(lang_code)),
        'analyzer': re.compile(r'(({0}(-{0})?)-(an)?mor(ph)?)\.mode'.format(lang_code)),
        'generator': re.compile(r'(({0}(-{0})?)-gener[A-z]*)\.mode'.format(lang_code)),
        'tagger': re.compile(r'(({0}(-{0})?)-tagger)\.mode'.format(lang_code)),
        'spell': re.compile(r'(({0}(-{0})?)-spell)\.mode'.format(lang_code)),
        'tokenise': re.compile(r'(({0}(-{0})?)-tokenise)\.mode'.format(lang_code)),
    }
    modes = {
        'pair': [],
        'analyzer': [],
        'generator': [],
        'tagger': [],
        'spell': [],
        'tokenise': [],
    }  # type: Dict[str, List[Tuple[str, str, str]]]

    real_root = os.path.abspath(os.path.realpath(rootpath))

    for dirpath, dirnames, files in os.walk(rootpath, followlinks=True):
        if is_loop(dirpath, rootpath, real_root):
            dirnames[:] = []
            continue
        for filename in [f for f in files if f.endswith('.mode')]:
            for mtype, regex in type_re.items():
                m = regex.match(filename)
                if m:
                    if mtype != 'pair':
                        modename = m.group(1)  # e.g. en-es-anmorph
                        langlist = [to_alpha3_code(x) for x in m.group(2).split('-')]
                        lang_pair = '-'.join(langlist)  # e.g. en-es
                        dir_of_modes = os.path.dirname(dirpath)
                        mode = (dir_of_modes,
                                modename,
                                lang_pair)
                        modes[mtype].append(mode)
                    elif include_pairs:
                        lang_src = m.group(1)
                        lang_trg = m.group(2)
                        mode = (os.path.join(dirpath, filename),
                                to_alpha3_code(lang_src),
                                to_alpha3_code(lang_trg))
                        modes[mtype].append(mode)

    if verbosity > 1:
        _log_modes(modes)

    return modes


def _log_modes(modes):
    """Print given modes to log."""
    for mtype in modes:
        if modes[mtype]:
            logging.info('"%s" modes found:\n%s', mtype, '\n'.join(['\t'.join(m) for m in modes[mtype]]))
