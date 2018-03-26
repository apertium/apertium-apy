import logging

from tornado import gen

try:
    import streamparser
except ImportError:
    streamparser = None

from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils import to_alpha3_code
from apertium_apy.utils.translation import translate_simple


class SpellerHandler(BaseHandler):
    @gen.coroutine
    def get(self):
        in_text = self.get_argument('q') + '*'
        in_mode = to_alpha3_code(self.get_argument('lang'))
        logging.info(in_text)
        logging.info(self.get_argument('lang'))
        logging.info(in_mode)
        logging.info(self.spellers)
        if in_mode in self.spellers:
            logging.info(self.spellers[in_mode])
            [path, mode] = self.spellers[in_mode]
            logging.info(path)
            logging.info(mode)
            formatting = 'none'
            commands = [['apertium', '-d', path, '-f', formatting, self.get_argument('lang') + '-tokenise']]
            result = yield translate_simple(in_text, commands)

            tokens = streamparser.parse(result)
            units = []
            for token in tokens:
                if token.knownness == streamparser.known:
                    units.append({'token': token.wordform, 'known': True, 'sugg': []})
                else:
                    suggestion = []
                    commands = [['apertium', '-d', path, '-f', formatting, mode]]

                    result = yield translate_simple(token.wordform, commands)
                    found_sugg = False
                    for line in result.splitlines():
                        if line.count('Corrections for'):
                            found_sugg = True
                            continue
                        if found_sugg and '\t' in line:
                            s, w = line.split('\t')
                            suggestion.append((s, w))

                    units.append({'token': token.wordform, 'known': False, 'sugg': suggestion})

            self.send_response(units)
        else:
            error_explanation = '{} on spellchecker mode: {}'.format('Error 404', 'Spelling mode for ' + in_mode + ' is not installed')
            self.send_error(404, explanation=error_explanation)
