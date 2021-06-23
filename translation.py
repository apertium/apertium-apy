#!/usr/bin/env python3
# -*- indent-tabs-mode: nil -*-
# coding=utf-8

import re
import os
from subprocess import Popen, PIPE
from tornado import gen
import tornado.process
import tornado.iostream
try:  # >=4.2
    import tornado.locks as locks
except ImportError:
    import toro as locks
import logging
from select import PIPE_BUF
from contextlib import contextmanager
from collections import namedtuple
from shutil import copyfile
from time import time
from urllib.parse import quote_plus


class Pipeline(object):

    def __init__(self, *args, **kwargs):
        # The lock is needed so we don't let two coroutines write
        # simultaneously to a pipeline; then the first call to read might
        # read translations of text put there by the second call …
        self.lock = locks.Lock()
        # The users count is how many requests have picked this
        # pipeline for translation. If this is 0, we can safely shut
        # down the pipeline.
        self.users = 0
        self.lastUsage = 0
        self.useCount = 0

    @contextmanager
    def use(self):
        self.lastUsage = time()
        self.users += 1
        try:
            yield
        finally:
            self.users -= 1
            self.lastUsage = time()
            self.useCount += 1

    def __lt__(self, other):
        return self.users < other.users

    @gen.coroutine
    def translate(self, toTranslate, nosplit, deformat, reformat):
        raise Exception("Not implemented, subclass me!")


class FlushingPipeline(Pipeline):

    def __init__(self, commands, *args, **kwargs):
        self.inpipe, self.outpipe = startPipeline(commands)
        super().__init__(*args, **kwargs)

    def __del__(self):
        logging.debug("shutting down FlushingPipeline that was used %d times", self.useCount)
        self.inpipe.stdin.close()
        self.inpipe.stdout.close()
        # TODO: It seems the process immediately becomes <defunct>,
        # but only completely removed after a second request to the
        # server – why?

    @gen.coroutine
    def translate(self, toTranslate, nosplit=False, deformat=True, reformat=True):
        with self.use():
            if nosplit:
                res = yield translateNULFlush(toTranslate, self, deformat, reformat)
                return res
            else:
                all_split = splitForTranslation(toTranslate, n_users=self.users)
                parts = yield [translateNULFlush(part, self, deformat, reformat)
                               for part in all_split]
                return "".join(parts)


class SimplePipeline(Pipeline):

    def __init__(self, commands, *args, **kwargs):
        self.commands = list(commands)
        super().__init__(*args, **kwargs)

    @gen.coroutine
    def translate(self, toTranslate, nosplit="ignored", deformat="ignored", reformat="ignored"):
        with self.use():
            with (yield self.lock.acquire()):
                res = yield translateSimple(toTranslate, self.commands)
                return res


class CatPipeline(Pipeline):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @gen.coroutine
    def translate(self, output, nosplit="ignored", deformat="ignored", reformat="ignored"):
        return output


ParsedModes = namedtuple('ParsedModes', 'do_flush commands')


def makePipeline(modes_parsed):
    if modes_parsed.do_flush:
        return FlushingPipeline(modes_parsed.commands)
    else:
        return SimplePipeline(modes_parsed.commands)


def startPipeline(commands):
    procs = []  # type: List[tornado.process.Subprocess]
    for i, cmd in enumerate(commands):
        if i == 0:
            in_from = tornado.process.Subprocess.STREAM
        else:
            in_from = procs[-1].stdout
        if i == len(commands) - 1:
            out_from = tornado.process.Subprocess.STREAM
        else:
            out_from = PIPE
        procs.append(tornado.process.Subprocess(cmd,
                                                stdin=in_from,
                                                stdout=out_from))
    return procs[0], procs[-1]


def cmdNeedsZ(cmd):
    exceptions = r'^\s*([^ ]*/)?(vislcg3|cg-mwesplit|hfst-tokeni[sz]e|divvun-suggest)'
    return re.match(exceptions, cmd) is None


def parseModeFile(mode_path):
    mode_str = open(mode_path, 'r').read().strip()
    if mode_str:
        if 'ca-oc@aran' in mode_str:
            do_flush = False
            modes_parentdir = os.path.dirname(os.path.dirname(mode_path))
            mode_name = os.path.splitext(os.path.basename(mode_path))[0]
            commands = [[
                'apertium',
                '-f', 'html-noent',
                # Get the _parent_ dir of the mode file:
                '-d', modes_parentdir,
                mode_name
            ]]
        else:
            do_flush = True
            commands = []
            for cmd in mode_str.strip().split('|'):
                # TODO: we should make language pairs install
                # modes.xml instead; this is brittle (what if a path
                # has | or " in it?)
                cmd = cmd.replace('$2', '').replace('$1', '-g')
                if(cmdNeedsZ(cmd)):
                    cmd = re.sub(r'^\s*(\S*)', r'\g<1> -z', cmd)
                commands.append([c.strip("'")
                                 for c in cmd.split()])
        return ParsedModes(do_flush, commands)
    else:
        logging.error('Could not parse mode file %s', mode_path)
        raise Exception('Could not parse mode file %s', mode_path)


def upToBytes(string, max_bytes):
    """Find the unicode string length of the first up-to-max_bytes bytes.

    At least it's much faster than going through the string adding
    bytes of each char.

    """
    b = bytes(string, 'utf-8')
    bl = max_bytes
    while bl:
        try:
            dec = b[:bl].decode('utf-8')
            return len(dec)
        except UnicodeDecodeError:
            bl -= 1
    return 0


def hardbreakFn(string, n_users):
    """If others are queueing up to translate at the same time, we send
    short requests, otherwise we try to minimise the number of
    requests, but without letting buffers fill up.

    These numbers could probably be tweaked a lot.

    """
    if n_users > 2:
        return 1000
    else:
        return upToBytes(string, PIPE_BUF)


def preferPunctBreak(string, last, hardbreak):
    """We would prefer to split on a period or space seen before the
    hardbreak, if we can. If the remaining string is smaller or equal
    than the hardbreak, return end of the string

    """

    if(len(string[last:]) <= hardbreak):
        return last + hardbreak + 1

    softbreak = int(hardbreak / 2) + 1
    softnext = last + softbreak
    hardnext = last + hardbreak
    dot = string.rfind(".", softnext, hardnext)
    if dot > -1:
        return dot + 1
    else:
        space = string.rfind(" ", softnext, hardnext)
        if space > -1:
            return space + 1
        else:
            return hardnext


def splitForTranslation(toTranslate, n_users):
    """Splitting it up a bit ensures we don't fill up FIFO buffers (leads
    to processes hanging on read/write)."""
    allSplit = []              # [].append and join faster than str +=
    last = 0
    rounds = 0
    while last < len(toTranslate) and rounds < 10:
        rounds += 1
        hardbreak = hardbreakFn(toTranslate[last:], n_users)
        next = preferPunctBreak(toTranslate, last, hardbreak)
        allSplit.append(toTranslate[last:next])
        # logging.getLogger().setLevel(logging.DEBUG)
        logging.debug("splitForTranslation: last:%s hardbreak:%s next:%s appending:%s" % (last, hardbreak, next, toTranslate[last:next]))
        last = next
    return allSplit


def validateFormatters(deformat, reformat):
    def valid1(elt, lst):
        if elt in lst:
            return elt
        else:
            return lst[0]
    # First is fallback:
    deformatters = ["apertium-deshtml", "apertium-destxt", "apertium-desrtf", False]
    reformatters = ["apertium-rehtml-noent", "apertium-rehtml", "apertium-retxt", "apertium-rertf", False]
    return valid1(deformat, deformatters), valid1(reformat, reformatters)


class ProcessFailure(Exception):
    pass


def checkRetCode(name, proc):
    if proc.returncode != 0:
        raise ProcessFailure("%s failed, exit code %s", name, proc.returncode)


@gen.coroutine
def coreduce(init, funcs, *args):
    '''
    Like the reduce() function in functools, this function applies the
    next function in the list to the output of the previous function
    (starting with init), supplying the additional args; this is just a
    coroutine version for use with the asynchronous translation pipelines.
    '''
    result = yield funcs[0](init, *args)
    for func in funcs[1:]:
        result = yield func(result, *args)
    return result


@gen.coroutine
def translateNULFlush(toTranslate, pipeline, unsafe_deformat, unsafe_reformat):
    """This function should only be used when toTranslate is smaller than the pipe buffer."""
    with (yield pipeline.lock.acquire()):
        proc_in, proc_out = pipeline.inpipe, pipeline.outpipe
        deformat, reformat = validateFormatters(unsafe_deformat, unsafe_reformat)

        if deformat:
            proc_deformat = Popen([deformat, "-o"], stdin=PIPE, stdout=PIPE)
            deformatted = proc_deformat.communicate(bytes(toTranslate, 'utf-8'))[0]
            checkRetCode("Deformatter", proc_deformat)
        else:
            deformatted = bytes(toTranslate, 'utf-8')

        # Calls to .write will block if we exceed the pipe buffer
        # (that's why we use .communicate elsewhere):
        proc_in.stdin.write(deformatted)
        proc_in.stdin.write(bytes('\0', "utf-8"))
        # TODO: PipeIOStream has no flush, but seems to work anyway?
        # proc_in.stdin.flush()

        # TODO: If the output has no \0, this hangs, locking the
        # pipeline. If there's no way to put a timeout right here, we
        # might need a timeout using Pipeline.use(), like servlet.py's
        # cleanable but called *before* trying to translate anew
        output = yield gen.Task(proc_out.stdout.read_until, bytes('\0', 'utf-8'))

        if reformat:
            proc_reformat = Popen(reformat, stdin=PIPE, stdout=PIPE)
            result = proc_reformat.communicate(output)[0]
            checkRetCode("Reformatter", proc_reformat)
        else:
            result = re.sub(rb'\0$', b'', output)
        return result.decode('utf-8')


@gen.coroutine
def translatePipeline(toTranslate, commands):

    proc_deformat = Popen(['apertium-deshtml', '-o'], stdin=PIPE, stdout=PIPE)
    deformatted = proc_deformat.communicate(bytes(toTranslate, 'utf-8'))[0]
    checkRetCode("Deformatter", proc_deformat)

    towrite = deformatted

    output = []
    output.append(toTranslate)
    output.append(towrite.decode('utf-8'))

    all_cmds = []
    all_cmds.append("apertium-deshtml")

    for cmd in commands:
        proc = Popen(cmd, stdin=PIPE, stdout=PIPE)
        towrite = proc.communicate(towrite)[0]
        checkRetCode(" ".join(cmd), proc)

        output.append(towrite.decode('utf-8'))
        all_cmds.append(cmd)

    proc_reformat = Popen("apertium-rehtml-noent", stdin=PIPE, stdout=PIPE)
    towrite = proc_reformat.communicate(towrite)[0].decode('utf-8')
    checkRetCode("Reformatter", proc_reformat)

    output.append(towrite)
    all_cmds.append("apertium-rehtml-noent")

    return output, all_cmds


@gen.coroutine
def translateSimple(toTranslate, commands):
    proc_in, proc_out = startPipeline(commands)
    assert proc_in == proc_out
    yield gen.Task(proc_in.stdin.write, bytes(toTranslate, 'utf-8'))
    proc_in.stdin.close()
    translated = yield gen.Task(proc_out.stdout.read_until_close)
    proc_in.stdout.close()
    return translated.decode('utf-8')


def startPipelineFromModeFile(modeFile, fmt, unknownMarks=False):
    modesdir = os.path.dirname(os.path.dirname(modeFile))
    mode = os.path.splitext(os.path.basename(modeFile))[0]
    if unknownMarks:
        cmd = ['apertium', '-f', fmt,       '-d', modesdir, mode]
    else:
        cmd = ['apertium', '-f', fmt, '-u', '-d', modesdir, mode]
    return startPipeline([cmd])


@gen.coroutine
def translateModefileBytes(toTranslateBytes, fmt, modeFile, unknownMarks=False):
    proc_in, proc_out = startPipelineFromModeFile(modeFile, fmt, unknownMarks)
    assert proc_in == proc_out
    yield gen.Task(proc_in.stdin.write, toTranslateBytes)
    proc_in.stdin.close()
    translatedBytes = yield gen.Task(proc_out.stdout.read_until_close)
    proc_in.stdout.close()
    return translatedBytes


@gen.coroutine
def translateSimpleMode(toTranslate, fmt, modeFile, unknownMarks=False):
    translated = yield translateModefileBytes(bytes(toTranslate, 'utf-8'),
                                              fmt, modeFile, unknownMarks)
    return translated.decode('utf-8')


@gen.coroutine
def translateHtmlMarkHeadings(toTranslate, modeFile, unknownMarks=False):
    proc_deformat = Popen(['apertium-deshtml', '-o'], stdin=PIPE, stdout=PIPE)
    deformatted = proc_deformat.communicate(bytes(toTranslate, 'utf-8'))[0]
    checkRetCode("Deformatter", proc_deformat)

    translated = yield translateModefileBytes(deformatted, 'none', modeFile, unknownMarks)

    proc_reformat = Popen(['apertium-rehtml-noent'], stdin=PIPE, stdout=PIPE)
    reformatted = proc_reformat.communicate(translated)[0]
    checkRetCode("Reformatter", proc_reformat)
    return reformatted.decode('utf-8')


@gen.coroutine
def translateDoc(fileToTranslate, fmt, modeFile, unknownMarks=False):
    modesdir = os.path.dirname(os.path.dirname(modeFile))
    mode = os.path.splitext(os.path.basename(modeFile))[0]
    os.environ['APERTIUM_TRANSFUSE'] = 'no'
    if unknownMarks:
        cmd = ['apertium', '-H', '-f', fmt,       '-d', modesdir, mode]
    else:
        cmd = ['apertium', '-H', '-f', fmt, '-u', '-d', modesdir, mode]
    proc = tornado.process.Subprocess(cmd,
                                      stdin=fileToTranslate,
                                      stdout=tornado.process.Subprocess.STREAM)
    translated = yield gen.Task(proc.stdout.read_until_close)
    proc.stdout.close()
    os.environ['APERTIUM_TRANSFUSE'] = 'yes'
    # TODO: raises but not caught:
    # checkRetCode(" ".join(cmd), proc)
    return translated


@gen.coroutine
def pdf2html(pdfconverter, pdffile, sourceLang, xslfile=None):
    """Convert pdffile into html, returning bytestring.
    Optional xslfile is value from `walkGTCorpus`."""
    if xslfile is not None:
        logging.info("Using pdfconverter.py with xsl {}".format(xslfile))
        try:
            copyfile(xslfile, pdffile.name + '.xsl')
        except Exception as e:
            logging.warn("Couldn't copy {} to {}, will end up with plain xsl. Reason: {}".format(xslfile, pdffile.name, e))
        commands = [["pdftohtml", "-hidden", "-enc", "UTF-8", "-stdout", "-nodrm", "-i", "-xml", pdffile.name]]
        converter = pdfconverter.PDF2XMLConverter(pdffile.name)
        converter.metadata.set_variable('mainlang', sourceLang)
        converter.metadata.set_variable('skip_pages', '')
        pdfhtml = yield translateSimple("", commands)
        converted = converter.pdftohtml2html(pdfhtml.encode('utf-8'))
    else:
        logging.info("Using plain pdftotext since no xsl")
        commands = [["pdftotext",
                     "-y", "50", "-x", "0", "-W", "99999", "-H", "99999",  # for SDÁ
                     "-raw", "-enc", "UTF-8", "-htmlmeta", pdffile.name, "-"]]
        pdfhtml = yield translateSimple("", commands)
        converted = re.sub(r'<head>', '<head><meta charset="utf-8"/><style>pre{font-family:Times,serif;line-height:1.5em}</style>', pdfhtml, count=1).encode('utf-8')
    return converted


def walkGTCorpus(corpuspath, xsls={}):
    """Make a map from language to url to xsl path.

    We assume the top-level path has folders with names corresponding
    to ISO 639-3 three-letter language codes; from there on we find all
    xsl files and map from url to xsl path.

    The xsl path values may be used as arguments to `pdf2html`"""
    corpuspath = os.path.abspath(corpuspath)  # allow relative paths
    for lang in os.listdir(corpuspath):
        langdir = os.path.join(corpuspath, lang)
        if not os.path.isdir(langdir):
            continue
        xsls[lang] = {}
        for root, _subs, files in os.walk(langdir):
            for xsl in (os.path.join(root, f)
                        for f in files
                        if re.search(r'[.]pdf[.]xsl$', f)):
                with open(xsl, 'r') as f:
                    # TODO: Is there a way to only read the file until the first match, like grep?
                    m = re.search(r'filename.*select="([^"]*)"', f.read())
                    if not m:
                        continue
                    url = m.group(1).strip("'")
                    if not url:
                        continue
                    xsls[lang][url] = xsl
                    xsls[lang][quote_plus(url)] = xsl
    return xsls
