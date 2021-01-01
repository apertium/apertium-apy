import logging
import os
import re
from collections import namedtuple
from contextlib import contextmanager
from select import PIPE_BUF
from subprocess import Popen, PIPE
from time import time
import asyncio
from secrets import token_urlsafe

import tornado.iostream
import tornado.locks as locks
import tornado.process
from tornado import gen

if False:
    from typing import List  # noqa: F401


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
        self.last_usage = 0.0
        self.use_count = 0
        self.stuck = False

    @contextmanager
    def use(self):
        self.last_usage = time()
        self.users += 1
        try:
            yield
        finally:
            self.users -= 1
            self.last_usage = time()
            self.use_count += 1

    def __lt__(self, other):
        return self.users < other.users

    @gen.coroutine
    def translate(self, to_translate, nosplit, deformat, reformat):
        raise Exception('Not implemented, subclass me!')


class FlushingPipeline(Pipeline):
    def __init__(self, timeout, commands, *args, **kwargs):
        self.timeout = timeout
        self.inpipe, self.outpipe = start_pipeline(commands)
        super().__init__(*args, **kwargs)

    def __del__(self):
        logging.debug('shutting down FlushingPipeline that was used %d times', self.use_count)
        self.inpipe.stdin.close()
        self.inpipe.stdout.close()
        # TODO: It seems the process immediately becomes <defunct>,
        # but only completely removed after a second request to the
        # server – why?

    @gen.coroutine
    def translate(self, to_translate, nosplit=False, deformat=True, reformat=True):
        with self.use():
            if nosplit:
                res = yield translate_nul_flush(to_translate, self, deformat, reformat, self.timeout)
                return res
            else:
                all_split = split_for_translation(to_translate, n_users=self.users)
                parts = yield [translate_nul_flush(part, self, deformat, reformat, self.timeout)
                               for part in all_split]
                return ''.join(parts)


class SimplePipeline(Pipeline):
    def __init__(self, commands, *args, **kwargs):
        self.commands = list(commands)
        super().__init__(*args, **kwargs)

    @gen.coroutine
    def translate(self, to_translate, nosplit='ignored', deformat='ignored', reformat='ignored'):
        with self.use():
            with (yield self.lock.acquire()):
                res = yield translate_simple(to_translate, self.commands)
                return res


ParsedModes = namedtuple('ParsedModes', 'do_flush commands')


def make_pipeline(modes_parsed, timeout):
    if modes_parsed.do_flush:
        return FlushingPipeline(timeout, modes_parsed.commands)
    else:
        return SimplePipeline(modes_parsed.commands)


def start_pipeline(commands):
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


def cmd_needs_z(cmd):
    exceptions = r'^\s*(vislcg3|cg-mwesplit|hfst-tokeni[sz]e|divvun-suggest)'
    return re.match(exceptions, cmd) is None


def parse_mode_file(mode_path):
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
                mode_name,
            ]]
        else:
            do_flush = True
            commands = []
            for cmd in mode_str.strip().split('|'):
                # TODO: we should make language pairs install
                # modes.xml instead; this is brittle (what if a path
                # has | or ' in it?)
                cmd = cmd.replace('$2', '').replace('$1', '-g')
                if cmd_needs_z(cmd):
                    cmd = re.sub(r'^\s*(\S*)', r'\g<1> -z', cmd)
                commands.append([c.strip("'")
                                 for c in cmd.split()])
        return ParsedModes(do_flush, commands)
    else:
        logging.error('Could not parse mode file %s', mode_path)
        raise Exception('Could not parse mode file %s', mode_path)


def up_to_bytes(string, max_bytes):
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


def hardbreak_fn(string, n_users):
    """If others are queueing up to translate at the same time, we send
    short requests, otherwise we try to minimise the number of
    requests, but without letting buffers fill up.

    These numbers could probably be tweaked a lot.
    """
    if n_users > 2:
        return 1000
    else:
        return up_to_bytes(string, PIPE_BUF)


def prefer_punct_break(string, last, hardbreak):
    """We would prefer to split on a period or space seen before the
    hardbreak, if we can. If the remaining string is smaller or equal
    than the hardbreak, return end of the string
    """

    if len(string[last:]) <= hardbreak:
        return last + hardbreak + 1

    softbreak = int(hardbreak / 2) + 1
    softnext = last + softbreak
    hardnext = last + hardbreak
    dot = string.rfind('.', softnext, hardnext)
    if dot > -1:
        return dot + 1
    else:
        space = string.rfind(' ', softnext, hardnext)
        if space > -1:
            return space + 1
        else:
            return hardnext


def split_for_translation(to_translate, n_users):
    """Splitting it up a bit ensures we don't fill up FIFO buffers (leads
    to processes hanging on read/write)."""
    all_split = []              # [].append and join faster than str +=
    last = 0
    rounds = 0
    while last < len(to_translate) and rounds < 10:
        rounds += 1
        hardbreak = hardbreak_fn(to_translate[last:], n_users)
        next = prefer_punct_break(to_translate, last, hardbreak)
        all_split.append(to_translate[last:next])
        # logging.getLogger().setLevel(logging.DEBUG)
        logging.debug('split_for_translation: last:%s hardbreak:%s next:%s appending:%s', last, hardbreak, next, to_translate[last:next])
        last = next
    return all_split


def validate_formatters(deformat, reformat):
    def valid1(elt, lst):
        if elt in lst:
            return elt
        else:
            return lst[0]
    # First is fallback:
    deformatters = ['apertium-deshtml', 'apertium-destxt', 'apertium-desrtf', False]
    reformatters = ['apertium-rehtml-noent', 'apertium-rehtml', 'apertium-retxt', 'apertium-rertf', False]
    return valid1(deformat, deformatters), valid1(reformat, reformatters)


class ProcessFailure(Exception):
    pass


def check_ret_code(name, proc):
    if proc.returncode != 0:
        raise ProcessFailure('%s failed, exit code %s', name, proc.returncode)


@gen.coroutine
def coreduce(init, funcs, *args):
    """
    Like the reduce() function in functools, this function applies the
    next function in the list to the output of the previous function
    (starting with init), supplying the additional args; this is just a
    coroutine version for use with the asynchronous translation pipelines.
    """
    result = yield funcs[0](init, *args)
    for func in funcs[1:]:
        result = yield func(result, *args)
    return result


async def translate_nul_flush(to_translate, pipeline, unsafe_deformat, unsafe_reformat, timeout):
    with (await pipeline.lock.acquire()):
        proc_in, proc_out = pipeline.inpipe, pipeline.outpipe
        deformat, reformat = validate_formatters(unsafe_deformat, unsafe_reformat)

        if deformat:
            proc_deformat = Popen(deformat, stdin=PIPE, stdout=PIPE)
            assert proc_deformat.stdin is not None  # stupid mypy
            proc_deformat.stdin.write(bytes(to_translate, 'utf-8'))
            deformatted = proc_deformat.communicate()[0]
            check_ret_code('Deformatter', proc_deformat)
        else:
            deformatted = bytes(to_translate, 'utf-8')

        nonce = '[/NONCE:' + token_urlsafe(8) + ']'
        proc_in.stdin.write(deformatted)
        proc_in.stdin.write(bytes('\0' + nonce + '\0', 'utf-8'))
        # TODO: PipeIOStream has no flush, but seems to work anyway?
        # proc_in.stdin.flush()

        # If the output has no \0, this hangs, locking the pipeline, so we use a timeout
        noncereader = proc_out.stdout.read_until(bytes(nonce + '\0', 'utf-8'))
        output = await asyncio.wait_for(noncereader, timeout=timeout)
        output = output.replace(bytes(nonce, 'utf-8'), b'')

        if reformat:
            proc_reformat = Popen(reformat, stdin=PIPE, stdout=PIPE)
            assert proc_reformat.stdin is not None  # stupid mypy
            proc_reformat.stdin.write(output)
            result = proc_reformat.communicate()[0]
            check_ret_code('Reformatter', proc_reformat)
        else:
            result = output.replace(b'\0', b'')
        return result.decode('utf-8')


@gen.coroutine
def translate_pipeline(to_translate, commands):
    proc_deformat = Popen('apertium-deshtml', stdin=PIPE, stdout=PIPE)
    assert proc_deformat.stdin is not None  # stupid mypy
    proc_deformat.stdin.write(bytes(to_translate, 'utf-8'))
    deformatted = proc_deformat.communicate()[0]
    check_ret_code('Deformatter', proc_deformat)

    towrite = deformatted

    output = []
    output.append(to_translate)
    output.append(towrite.decode('utf-8'))

    all_cmds = []
    all_cmds.append('apertium-deshtml')

    for cmd in commands:
        proc = Popen(cmd, stdin=PIPE, stdout=PIPE)
        assert proc.stdin is not None  # stupid mypy
        proc.stdin.write(towrite)
        towrite = proc.communicate()[0]
        check_ret_code(' '.join(cmd), proc)

        output.append(towrite.decode('utf-8'))
        all_cmds.append(cmd)

    proc_reformat = Popen('apertium-rehtml-noent', stdin=PIPE, stdout=PIPE)
    assert proc_reformat.stdin is not None  # stupid mypy
    proc_reformat.stdin.write(towrite)
    towrite = proc_reformat.communicate()[0]
    check_ret_code('Reformatter', proc_reformat)

    output.append(towrite)
    all_cmds.append('apertium-rehtml-noent')

    return output, all_cmds


async def translate_simple(to_translate, commands):
    proc_in, proc_out = start_pipeline(commands)
    assert proc_in == proc_out
    await proc_in.stdin.write(bytes(to_translate, 'utf-8'))
    proc_in.stdin.close()
    translated = await proc_out.stdout.read_until_close()
    proc_in.stdout.close()
    return translated.decode('utf-8')


def start_pipeline_from_modefile(mode_file, fmt, unknown_marks=False):
    modes_dir = os.path.dirname(os.path.dirname(mode_file))
    mode = os.path.splitext(os.path.basename(mode_file))[0]
    if unknown_marks:
        cmd = ['apertium', '-f', fmt, '-d', modes_dir, mode]
    else:
        cmd = ['apertium', '-f', fmt, '-u', '-d', modes_dir, mode]
    return start_pipeline([cmd])


async def translate_modefile_bytes(to_translate_bytes, fmt, mode_file, unknown_marks=False):
    proc_in, proc_out = start_pipeline_from_modefile(mode_file, fmt, unknown_marks)
    assert proc_in == proc_out
    await proc_in.stdin.write(to_translate_bytes)
    proc_in.stdin.close()
    translated_bytes = await proc_out.stdout.read_until_close()
    proc_in.stdout.close()
    return translated_bytes


@gen.coroutine
def translate_html_mark_headings(to_translate, mode_file, unknown_marks=False):
    translated = yield translate_modefile_bytes(bytes(to_translate, 'utf-8'), 'html', mode_file, unknown_marks)
    return translated.decode('utf-8')
