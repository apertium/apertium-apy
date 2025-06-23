import logging
from tornado import gen

from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils.translation import translate_simple
from apertium_apy.utils import to_alpha3_code


class BillookupHandler(BaseHandler):
    def get_pair_or_error(self, langpair):
        try:
            l1, l2 = map(to_alpha3_code, langpair.split('|'))
            in_mode = f"{l1}-{l2}"
        except ValueError:
            self.send_error(400, explanation='That pair is invalid, use e.g. eng|spa')
            return None

        in_mode = self.find_fallback_mode(in_mode, self.pairs)
        if in_mode not in self.pairs:
            self.send_error(400, explanation='That pair is not installed')
            return None
        return tuple(in_mode.split('-'))

    @gen.coroutine
    def lookup_and_respond(self, pair, query):
        try:
            path, mode = self.billookup["-".join(pair)]
            formatting = 'none'
            commands = [['apertium', '-d', path, '-f', formatting, mode]]
            result = yield translate_simple(query, commands)

            entries = result.strip().split('^')
            results = []
            for entry in entries:
                entry = entry.strip()
                if not entry or '$' not in entry:
                    continue
                entry = entry.split('$')[0]
                parts = entry.split('/')
                if len(parts) < 2:
                    continue
                source = parts[0]
                targets = parts[1:]
                results.append({source: targets})

            self.send_response({
                'responseData': {
                    'lookupResults': results,
                },
                'responseDetails': None,
                'responseStatus': 200,
            })
        except Exception as e:
            logging.warning('Lookup error in pair %s-%s: %s', pair[0], pair[1], e)
            self.send_error(503, explanation='internal error')

    @gen.coroutine
    def get(self):
        pair = self.get_pair_or_error(self.get_argument('langpair'))
        
        if pair is not None:
            yield self.lookup_and_respond(pair, self.get_argument('q'))
