import re, threading
from subprocess import Popen, PIPE
import logging
        
def translateNULFlush(toTranslate, translock, pipeline):
    with translock:
        proc_in, proc_out, do_flush = pipeline
        assert(do_flush)

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
            
def hardbreakFn():
    """If others are waiting on us, we send short requests, otherwise we
    try to minimise the number of requests, but without
    letting buffers fill up.

    Unfortunately, if we've already started a long
    request, the next one to come along will have to wait
    one long request until they start getting shorter.

    These numbers could probably be tweaked a lot.
    """
    if threading.active_count()>2:
        hardbreak=1000
        # TODO: would prefer "translock.waiting_count", but doesn't seem exist
    else:
        hardbreak=5000
    return hardbreak
    
def translateSplitting(toTranslate, translock, pipeline):
    """Splitting it up a bit ensures we don't fill up FIFO buffers (leads
    to processes hanging on read/write)."""
    allSplit = []	# [].append and join faster than str +=
    last=0
    while last<len(toTranslate):
        hardbreak = hardbreakFn()
        # We would prefer to split on a period or space seen before
        # the hardbreak, if we can:
        softbreak = int(hardbreak*0.9)
        dot=toTranslate.find(".", last+softbreak, last+hardbreak)
        if dot>-1:
            next=dot
        else:
            space=toTranslate.find(" ", last+softbreak, last+hardbreak)
            if space>-1:
                next=space
            else:
                next=last+hardbreak
        allSplit.append(translateNULFlush(toTranslate[last:next], translock, pipeline))
        last=next
    return "".join(allSplit)

def translateWithoutFlush(toTranslate, translock, pipeline):
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


def translateSimple(toTranslate, translock, pipeline):
    with translock:
        proc_in, proc_out, do_flush = pipeline
        assert(not do_flush)
        assert(proc_in==proc_out)
        translated = proc_in.communicate(input=bytes(toTranslate, 'utf-8'))[0]
        return translated.decode('utf-8')

def translate(toTranslate, translock, pipeline, tInfo):
    _, _, do_flush = pipeline
    if do_flush:
        return translateSplitting(toTranslate, translock, pipeline)
    else:
        return translateSimple(toTranslate, translock, pipeline)
