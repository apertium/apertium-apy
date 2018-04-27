from tornado import gen

try:
    import streamparser
except ImportError:
    streamparser = None

from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils import to_alpha3_code, remove_dot_from_deformat
from apertium_apy.utils.translation import translate_simple


class AnalyzeHandler(BaseHandler):
    def postproc_text(self, in_text, result):
        lexical_units_with_text = remove_dot_from_deformat(in_text, list(streamparser.parse(result, with_text=True)))
        return [
            (text_and_lu[1].lexical_unit, text_and_lu[0] + text_and_lu[1].wordform)
            for text_and_lu
            in lexical_units_with_text
        ]

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
