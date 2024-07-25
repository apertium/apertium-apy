import logging
from tornado import gen
from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils import to_alpha2_code
from apertium_apy.utils.translation import translate_simple

class VoikkoSpellerHandler(BaseHandler):
    @gen.coroutine
    def get(self):
        in_text = self.get_argument('q')
        in_mode = self.get_argument('lang')
        in_mode = self.find_fallback_mode(in_mode, self.voikko_modes)
        logging.info(in_text)
        logging.info(self.get_argument('lang'))
        logging.info(in_mode)
        logging.info(self.voikko_modes)
        
        if in_mode in self.voikko_modes:
            mode = to_alpha2_code(in_mode)
            logging.info(mode)

            tokens = in_text.split()
            units = []
            for token in tokens:
                commands = [['voikkospell', '-d', mode, '-s']]
                result = yield translate_simple(token, commands)
                known = False
                suggestions = []
                lines = result.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line.startswith('C: '):
                        known = True
                        suggestions = []
                        break  
                    elif line.startswith('W: '):
                        known = False
                    elif line.startswith('S: '):
                        suggestions.append(line[3:].strip())

                units.append({'token': token, 'known': known, 'sugg': suggestions})

            self.send_response(units)
        else:
            error_explanation = '{} on spellchecker mode: {}'.format('Error 404', 'Spelling mode for ' + in_mode + ' is not installed')
            self.send_error(404, explanation=error_explanation)
