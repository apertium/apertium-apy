import os
import shutil
import subprocess
import tempfile
import zipfile

import tornado
from tornado import gen

from apertium_apy.handlers.translate import TranslateHandler

FILE_SIZE_LIMIT_BYTES = 32E6

MIMETYPE_COMMANDS = {
    'mimetype': lambda x: subprocess.check_output(['mimetype', '-b', x], universal_newlines=True).strip(),
    'xdg-mime': lambda x: subprocess.check_output(['xdg-mime', 'query', 'filetype', x], universal_newlines=True).strip(),
    'file': lambda x: subprocess.check_output(['file', '--mime-type', '-b', x], universal_newlines=True).strip(),
}

ALLOWED_MIME_TYPES = {
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

OPEN_OFFICE_XML_FILE_MARKERS = {
    'word/document.xml': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'ppt/presentation.xml': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'xl/workbook.xml': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
}


async def translate_doc(file_to_translate, fmt, mode_file, unknown_marks=False):
    modes_dir = os.path.dirname(os.path.dirname(mode_file))
    mode = os.path.splitext(os.path.basename(mode_file))[0]
    if unknown_marks:
        cmd = ['apertium', '-f', fmt, '-d', modes_dir, mode]
    else:
        cmd = ['apertium', '-f', fmt, '-u', '-d', modes_dir, mode]
    proc = tornado.process.Subprocess(cmd,
                                      stdin=file_to_translate,
                                      stdout=tornado.process.Subprocess.STREAM)
    translated = await proc.stdout.read_until_close()
    proc.stdout.close()
    # TODO: raises but not caught:
    # check_ret_code(' '.join(cmd), proc)
    return translated


class TranslateDocHandler(TranslateHandler):
    mime_type_command = None

    @classmethod
    def get_mime_type(cls, f):
        if not cls.mime_type_command:
            for command in MIMETYPE_COMMANDS.keys():
                if shutil.which(command):
                    cls.mime_type_command = command
                    break

        if not cls.mime_type_command:
            return None
        mime_command = MIMETYPE_COMMANDS[cls.mime_type_command]
        mime_type = mime_command(f).split(';')[0]
        if mime_type == 'application/zip':
            with zipfile.ZipFile(f) as zf:
                file_names = zf.namelist()

                for marker_file, office_mime_type in OPEN_OFFICE_XML_FILE_MARKERS.items():
                    if marker_file in file_names:
                        return office_mime_type

                if 'mimetype' in file_names:
                    return zf.read('mimetype').decode('utf-8')
        return mime_type

    # TODO: Some kind of locking. Although we can't easily re-use open
    # pairs here (would have to reimplement lots of
    # /usr/bin/apertium), we still want some limits on concurrent doc
    # translation.
    @gen.coroutine
    def get(self):
        pair = self.get_pair_or_error(self.get_argument('langpair'), -1)
        if pair is not None:
            body = self.request.files['file'][0]['body']
            if len(body) > FILE_SIZE_LIMIT_BYTES:
                self.send_error(413, explanation='That file is too large')
                return

            with tempfile.NamedTemporaryFile() as temp_file:
                temp_file.write(body)
                temp_file.seek(0)

                mtype = self.get_mime_type(temp_file.name)
                if mtype not in ALLOWED_MIME_TYPES:
                    self.send_error(400, explanation='Invalid file type %s' % mtype)
                    return
                self.request.headers['Content-Type'] = 'application/octet-stream'
                self.request.headers['Content-Disposition'] = 'attachment'
                with (yield self.doc_pipe_sem.acquire()):
                    t = yield translate_doc(temp_file,
                                            ALLOWED_MIME_TYPES[mtype],
                                            self.pairs['%s-%s' % pair],
                                            self.mark_unknown)
                self.write(t)
                self.finish()
