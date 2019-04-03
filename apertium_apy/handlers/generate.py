from tornado import gen

try:
    import streamparser
except ImportError:
    streamparser = None

from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils import to_alpha3_code
from apertium_apy.utils.translation import translate_simple


class GenerateHandler(BaseHandler):
    seperator = '[SEP]'

    def wrap(self, text):
        return '^{}$'.format(text)

    def preproc_text(self, in_text):
        lexical_units_with_text = list(streamparser.parse(in_text, with_text=True))
        if len(lexical_units_with_text) == 0:
            lexical_units_with_text = list(streamparser.parse(self.wrap(in_text), with_text=True))
        lexical_units = [self.wrap(text_and_lu[1].lexical_unit) for text_and_lu in lexical_units_with_text]
        return lexical_units_with_text, self.seperator.join(lexical_units)

    def postproc_text(self, lexical_units_with_text, result):
        return [
            (generation, self.wrap(text_and_lu[0] + text_and_lu[1].lexical_unit))
            for (generation, text_and_lu)
            in zip(result.split(self.seperator), lexical_units_with_text)
        ]

    @gen.coroutine
    def get(self):
        in_text = self.get_argument('q')
        in_mode = to_alpha3_code(self.get_argument('lang'))
        if in_mode in self.generators:
            [path, mode] = self.generators[in_mode]
            formatting = 'none'
            commands = [['apertium', '-d', path, '-f', formatting, mode]]
            lexical_units_with_text, to_generate = self.preproc_text(in_text)
            result = yield translate_simple(to_generate, commands)
            self.send_response(self.postproc_text(lexical_units_with_text, result))
        else:
            self.send_error(400, explanation='That mode is not installed')
