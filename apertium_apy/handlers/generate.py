import re

from tornado import gen

from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils import to_alpha3_code
from apertium_apy.utils.translation import translate_simple


class GenerateHandler(BaseHandler):
    def preproc_text(self, in_text):
        lexical_units = re.findall(r'(\^[^\$]*\$[^\^]*)', in_text)  # TODO: replace with streamparser
        if len(lexical_units) == 0:
            lexical_units = ['^%s$' % (in_text,)]
        return lexical_units, '[SEP]'.join(lexical_units)

    def postproc_text(self, lexical_units, result):
        return [(generation, lexical_units[i])
                for (i, generation)
                in enumerate(result.split('[SEP]'))]

    @gen.coroutine
    def get(self):
        in_text = self.get_argument('q')
        in_mode = to_alpha3_code(self.get_argument('lang'))
        if '-' in in_mode:
            l1, l2 = map(to_alpha3_code, in_mode.split('-', 1))
            in_mode = '%s-%s' % (l1, l2)
        in_mode = self.find_fallback_mode(in_mode, self.generators)
        if in_mode in self.generators:
            [path, mode] = self.generators[in_mode]
            formatting = 'none'
            commands = [['apertium', '-d', path, '-f', formatting, mode]]
            lexical_units, to_generate = self.preproc_text(in_text)
            result = yield translate_simple(to_generate, commands)
            self.send_response(self.postproc_text(lexical_units, result))
        else:
            self.send_error(400, explanation='That mode is not installed')
