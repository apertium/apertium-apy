import re

from tornado import gen

from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils import to_alpha3_code, remove_dot_from_deformat
from apertium_apy.utils.translation import translate_simple


class AnalyzeHandler(BaseHandler):
    @staticmethod
    def postproc_text(in_text, result):
        lexical_units = remove_dot_from_deformat(in_text, re.findall(r'\^([^\$]*)\$([^\^]*)', result))  # TODO: replace with streamparser
        return [(lu[0], lu[0].split('/')[0] + lu[1])
                for lu
                in lexical_units]

    @gen.coroutine
    def get(self):
        in_text = self.get_argument('q')
        in_mode = to_alpha3_code(self.get_argument('lang'))
        if in_mode in self.analyzers:
            [path, mode] = self.analyzers[in_mode]
            formatting = 'txt'
            commands = [['apertium', '-d', path, '-f', formatting, mode]]
            result = yield translate_simple(in_text, commands)
            self.send_response(self.postproc_text(in_text, result))
        else:
            self.send_error(400, explanation='That mode is not installed')
