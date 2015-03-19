import re, os, tempfile
from subprocess import Popen, PIPE
from tornado import gen
import tornado.process, tornado.iostream
import logging
from select import PIPE_BUF

def startPipeline(commands):
    procs = []
    for i, cmd in enumerate(commands):
        if i == 0:
            in_from = tornado.process.Subprocess.STREAM
        else:
            in_from = procs[-1].stdout
        if i == len(commands)-1:
            out_from = tornado.process.Subprocess.STREAM
        else:
            out_from = PIPE
        procs.append(tornado.process.Subprocess(cmd,
                                                stdin=in_from,
                                                stdout=out_from))

    return procs[0], procs[-1]

def parseModeFile(mode_path):
    mode_str = open(mode_path, 'r').read().strip()
    if mode_str:
        if 'hfst-proc ' in mode_str or 'lrx-proc ' in mode_str:
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
                cmd = cmd.replace('$2', '').replace('$1', '-g')
                cmd = re.sub('^(\S*)', '\g<1> -z', cmd)
                commands.append(cmd.split())
        return do_flush, commands
    else:
        logging.error('Could not parse mode file %s' % mode_path)
        raise Exception('Could not parse mode file %s' % mode_path)


def upToBytes(string, max_bytes):
    """Find the unicode string length of the first up-to-max_bytes bytes.

    At least it's much faster than going through the string adding
    bytes of each char.

    """
    b = bytes(string,'utf-8')
    l = max_bytes
    while l:
        try:
            dec = b[:l].decode('utf-8')
            return len(dec)
        except UnicodeDecodeError:
            l -= 1
    return 0

def hardbreakFn(string, rush_hour):
    """If others are queueing up to translate at the same time, we send
    short requests, otherwise we try to minimise the number of
    requests, but without letting buffers fill up.

    These numbers could probably be tweaked a lot.

    """
    if rush_hour:
        return 1000
    else:
        return upToBytes(string, PIPE_BUF)

def preferPunctBreak(string, last, hardbreak):
    """We would prefer to split on a period or space seen before the
    hardbreak, if we can.

    """
    softbreak = int(hardbreak/2)+1
    softnext = last + softbreak
    hardnext = last + hardbreak
    dot = string.rfind(".", softnext, hardnext)
    if dot>-1:
        return dot
    else:
        space = string.rfind(" ", softnext, hardnext)
        if space>-1:
            return space
        else:
            return hardnext

def splitForTranslation(toTranslate, rush_hour):
    """Splitting it up a bit ensures we don't fill up FIFO buffers (leads
    to processes hanging on read/write)."""
    allSplit = []	# [].append and join faster than str +=
    last=0
    rounds=0
    while last < len(toTranslate) and rounds<10:
        rounds+=1
        hardbreak = hardbreakFn(toTranslate[last:], rush_hour)
        next = preferPunctBreak(toTranslate, last, hardbreak)
        allSplit.append(toTranslate[last:next])
        last = next
    return allSplit

@gen.coroutine
def translateNULFlush(toTranslate, lock, pipeline):
    with (yield lock.acquire()):
        proc_in, proc_out = pipeline

        proc_deformat = Popen("apertium-deshtml", stdin=PIPE, stdout=PIPE)
        proc_deformat.stdin.write(bytes(toTranslate, 'utf-8'))
        deformatted = proc_deformat.communicate()[0]

        proc_in.stdin.write(deformatted)
        proc_in.stdin.write(bytes('\0', "utf-8"))
        # TODO: PipeIOStream has no flush, but seems to work anyway?
        #proc_in.stdin.flush()

        output = yield proc_out.stdout.read_until(bytes('\0', 'utf-8'))

        proc_reformat = Popen("apertium-rehtml-noent", stdin=PIPE, stdout=PIPE)
        proc_reformat.stdin.write(output)
        return proc_reformat.communicate()[0].decode('utf-8')


def translateWithoutFlush(toTranslate, lock, pipeline):
    proc_deformat = Popen("apertium-deshtml", stdin=PIPE, stdout=PIPE)
    proc_deformat.stdin.write(bytes(toTranslate, 'utf-8'))
    deformatted = proc_deformat.communicate()[0]

    proc_in.stdin.write(deformatted)
    proc_in.stdin.write(bytes('\0', "utf-8"))
    proc_in.stdin.flush()

    d = proc_out.stdout.read(1)
    output = []
    while d and d != b'\x00':
        output.append(d)
        d = proc_out.stdout.read(1)

    proc_reformat = Popen("apertium-rehtml-noent", stdin=PIPE, stdout=PIPE)
    proc_reformat.stdin.write(b"".join(output))
    return proc_reformat.communicate()[0].decode('utf-8')

@gen.coroutine
def translatePipeline(toTranslate, commands):

    proc_deformat = Popen("apertium-deshtml", stdin=PIPE, stdout=PIPE)
    proc_deformat.stdin.write(bytes(toTranslate, 'utf-8'))
    deformatted = proc_deformat.communicate()[0]

    towrite = deformatted

    output = []
    output.append(toTranslate)
    output.append(towrite.decode('utf-8'))

    pipeline = []
    pipeline.append("apertium-deshtml")

    for cmd in commands:
        proc = Popen(cmd, stdin=PIPE, stdout=PIPE)
        proc.stdin.write(towrite)
        towrite = proc.communicate()[0]

        output.append(towrite.decode('utf-8'))
        pipeline.append(cmd)

    proc_reformat = Popen("apertium-rehtml-noent", stdin=PIPE, stdout=PIPE)
    proc_reformat.stdin.write(towrite)
    towrite = proc_reformat.communicate()[0].decode('utf-8')

    output.append(towrite)
    pipeline.append("apertium-rehtml-noent")

    return output, pipeline

@gen.coroutine
def translateSimple(toTranslate, commands):
    proc_in, proc_out = startPipeline(commands)
    assert(proc_in==proc_out)
    yield proc_in.stdin.write(bytes(toTranslate, 'utf-8'))
    proc_in.stdin.close()
    translated = yield proc_out.stdout.read_until_close()
    proc_in.stdout.close()
    return translated.decode('utf-8')

def translateDoc(fileToTranslate, format, modeFile):
    return Popen(['apertium', '-f %s' % format, '-d %s' % os.path.dirname(os.path.dirname(modeFile)), os.path.splitext(os.path.basename(modeFile))[0]], stdin=fileToTranslate, stdout=PIPE).communicate()[0]

@gen.coroutine
def translate(toTranslate, lock, pipeline, commands):
    if pipeline:
        allSplit = splitForTranslation(toTranslate, rush_hour = lock.locked())
        parts = yield [translateNULFlush(part, lock, pipeline) for part in allSplit]
        return "".join(parts)
    else:
        with (yield lock.acquire()):
            res = yield translateSimple(toTranslate, commands)
            return res
