import logging
import os
from tornado import gen
from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils import to_alpha2_code
from apertium_apy.utils.translation import translate_simple

class MultiSpellerHandler(BaseHandler):
    @gen.coroutine
    def get(self):
        in_text = self.get_argument('q')
        in_mode = self.get_argument('lang')
        spell_checker = self.get_argument('spellchecker', 'voikko')  # Default to 'voikko'

        if spell_checker not in ['voikko', 'divvun']:
            self.send_error(400, explanation="Invalid spell checker specified. Only 'voikko' and 'divvun' are allowed.")
            return
        
        in_mode = self.find_fallback_mode(in_mode, self.spell_modes)
        
        if in_mode in self.spell_modes:
            mode = to_alpha2_code(in_mode)
            tokens = in_text.split()
            units = []
            
            for token in tokens:
                result = yield self.check_spelling(token, mode, spell_checker)
                units.append(self.parse_result(token, result, spell_checker))
            
            self.send_response(units)
        else:
            error_explanation = f"Error 404: Spelling mode for {in_mode} is not installed"
            self.send_error(404, explanation=error_explanation)
    
    @gen.coroutine
    def check_spelling(self, token, mode, spell_checker):
        if spell_checker == 'voikko':
            commands = [['voikkospell', '-d', mode, '-s']]
        elif spell_checker == 'divvun':
            speller_path = os.path.expanduser(f'~/.voikko/3/{mode}.zhfst')
            commands = [['divvunspell', 'suggest', '-a', speller_path]]

        result = yield translate_simple(token, commands)
        return result
    
    def parse_result(self, token, result, spell_checker):
        if spell_checker == 'voikko':
            return self.parse_voikko_result(token, result)
        elif spell_checker == 'divvun':
            return self.parse_divvun_result(token, result)
        else:
            self.send_error(500, explanation="Unknown spell checker specified.")
            return {'token': token, 'known': False, 'sugg': []}
    
    def parse_voikko_result(self, token, result):
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
        return {'token': token, 'known': known, 'sugg': suggestions}
    
    def parse_divvun_result(self, token, result):
        known = False
        suggestions = []
        lines = result.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('Input:') and '[CORRECT]' in line:
                known = True
            elif line.startswith('Input:') and '[INCORRECT]' in line:
                known = False
            elif line and '\t' in line:
                suggestion = line.split('\t')[0].strip()
                suggestions.append(suggestion)
        return {'token': token, 'known': known, 'sugg': suggestions}