import logging
import os
from tornado import gen
from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils import to_alpha3_code
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
        
        if '-' in in_mode:
            l1, l2 = map(to_alpha3_code, in_mode.split('-', 1))
            in_mode = '%s-%s' % (l1, l2)
        in_mode = self.find_fallback_mode(in_mode, self.spellers)
        logging.info(in_text)
        logging.info(self.get_argument('lang'))
        logging.info(in_mode)
        logging.info(self.spellers)
        
        if in_mode in self.spellers:
            tokens = in_text.split()
            logging.info(self.spellers[in_mode])
            [base_path, mode] = self.spellers[in_mode]

            path = self.find_speller_path(base_path, in_mode)

            units = []
            for token in tokens:
                result = yield self.check_spelling(token, mode, base_path, path, spell_checker)
                units.append(self.parse_result(token, result, spell_checker))
            
            self.send_response(units)
        else:
            error_explanation = f"Error 404: Spelling mode for {in_mode} is not installed"
            self.send_error(404, explanation=error_explanation)
    
    def find_speller_path(self, base_path, in_mode):
        for root, _, files in os.walk(base_path):
            for file in files:
                if file == f"{in_mode}.zhfst":
                    return os.path.join(root, file)
        return base_path

    @gen.coroutine
    def check_spelling(self, token, mode, base_path, path, spell_checker):
        if spell_checker == 'voikko':
            formatting = 'none'
            commands = [['apertium', '-d', base_path, '-f', formatting, mode]]
        elif spell_checker == 'divvun':
            commands = [['divvunspell', 'suggest', '-a', path]]

        result = yield translate_simple(token, commands)
        return result
    
    def parse_result(self, token, result, spell_checker):
        if spell_checker == 'voikko':
            return self.parse_voikko_result(token, result)
        elif spell_checker == 'divvun':
            return self.parse_divvun_result(token, result)
    
    def parse_voikko_result(self, token, result):
        known = False
        suggestions = []
        lines = result.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if f'"{token}" is in the lexicon' in line:
                known = True
                break
            elif f'"{token}" is NOT in the lexicon' in line:
                known = False
            elif line.startswith('Corrections for'):
                continue
            elif line.startswith('Unable to correct'):
                suggestions = []
                break
            elif line:
                suggestion = line.split()[0].strip()
                suggestions.append(suggestion)
        
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
