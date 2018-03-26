import os
import tempfile
import zipfile
from subprocess import Popen, PIPE

import tornado
from tornado import gen

from apertium_apy.handlers.translate import TranslateHandler
from apertium_apy.utils import to_alpha3_code


@gen.coroutine
def translate_doc(file_to_translate, fmt, mode_file, unknown_marks=False):
    modes_dir = os.path.dirname(os.path.dirname(mode_file))
    mode = os.path.splitext(os.path.basename(mode_file))[0]
    if unknown_marks:
        cmd = ['apertium', '-f', fmt, '-d', modes_dir, mode]
    else:
        cmd = ['apertium', '-f', fmt, '-u', '-d', modes_dir, mode]
    proc = tornado.process.Subprocess(cmd,
                                      stdin=file_to_translate,
                                      stdout=tornado.process.Subprocess.STREAM)
    translated = yield gen.Task(proc.stdout.read_until_close)
    proc.stdout.close()
    # TODO: raises but not caught:
    # check_ret_code(' '.join(cmd), proc)
    return translated


class TranslateDocHandler(TranslateHandler):
    mime_type_command = None

    def get_mime_type(self, f):
        commands = {
            'mimetype': lambda x: Popen(['mimetype', '-b', x], stdout=PIPE).communicate()[0].strip(),
            'xdg-mime': lambda x: Popen(['xdg-mime', 'query', 'filetype', x], stdout=PIPE).communicate()[0].strip(),
            'file': lambda x: Popen(['file', '--mime-type', '-b', x], stdout=PIPE).communicate()[0].strip(),
        }

        type_files = {
            'word/document.xml': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'ppt/presentation.xml': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'xl/workbook.xml': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }

        if not self.mime_type_command:
            for command in ['mimetype', 'xdg-mime', 'file']:
                if Popen(['which', command], stdout=PIPE).communicate()[0]:
                    TranslateDocHandler.mime_type_command = command
                    break

        mime_type = commands[self.mime_type_command](f).decode('utf-8')
        if mime_type == 'application/zip':
            with zipfile.ZipFile(f) as zf:
                for type_file in type_files:
                    if type_file in zf.namelist():
                        return type_files[type_file]

                if 'mimetype' in zf.namelist():
                    return zf.read('mimetype').decode('utf-8')

                return mime_type

        else:
            return mime_type

    # TODO: Some kind of locking. Although we can't easily re-use open
    # pairs here (would have to reimplement lots of
    # /usr/bin/apertium), we still want some limits on concurrent doc
    # translation.
    @gen.coroutine
    def get(self):
        try:
            l1, l2 = map(to_alpha3_code, self.get_argument('langpair').split('|'))
        except ValueError:
            self.send_error(400, explanation='That pair is invalid, use e.g. eng|spa')

        mark_unknown = self.get_argument('markUnknown', default='yes') in ['yes', 'true', '1']

        allowed_mime_types = {
            'text/plain': 'txt',
            'text/html': 'html-noent',
            'text/rtf': 'rtf',
            'application/rtf': 'rtf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
            # 'application/msword', 'application/vnd.ms-powerpoint', 'application/vnd.ms-excel'
            'application/vnd.oasis.opendocument.text': 'odt',
            'application/x-latex': 'latex',
            'application/x-tex': 'latex',
        }

        if '%s-%s' % (l1, l2) not in self.pairs:
            self.send_error(400, explanation='That pair is not installed')
            return

        body = self.request.files['file'][0]['body']
        if len(body) > 32E6:
            self.send_error(413, explanation='That file is too large')
            return

        with tempfile.NamedTemporaryFile() as temp_file:
            temp_file.write(body)
            temp_file.seek(0)

            mtype = self.get_mime_type(temp_file.name)
            if mtype not in allowed_mime_types:
                self.send_error(400, explanation='Invalid file type %s' % mtype)
                return
            self.request.headers['Content-Type'] = 'application/octet-stream'
            self.request.headers['Content-Disposition'] = 'attachment'
            with (yield self.doc_pipe_sem.acquire()):
                t = yield translate_doc(temp_file,
                                        allowed_mime_types[mtype],
                                        self.pairs['%s-%s' % (l1, l2)],
                                        mark_unknown)
            self.write(t)
            self.finish()
