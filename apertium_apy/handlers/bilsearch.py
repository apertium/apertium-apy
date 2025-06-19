import logging
from tornado import gen

from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils.translation import translate_simple
from apertium_apy.utils import to_alpha3_code

class BilsearchHandler(BaseHandler):
    def get_pair_or_error(self, langpair):
        try:
            l1, l2 = map(to_alpha3_code, langpair.split('|'))
            in_mode = '%s-%s' % (l1, l2)
        except ValueError:
            self.send_error(400, explanation='That pair is invalid, use e.g. eng|spa')
            return None
        in_mode = self.find_fallback_mode(in_mode, self.pairs)
        if in_mode not in self.pairs:
            self.send_error(400, explanation='That pair is not installed')
            return None
        else:
            return tuple(in_mode.split('-'))

    @gen.coroutine
    def search_and_respond(self, pair, query):
        try:
            path, mode = self.bilsearch["-".join(pair)]
            commands = [['apertium', '-d', path, '-f', 'none', mode]]
            result = yield translate_simple(query, commands)
            resultPerSearch = result.split('\n\n')
            results = []
            for i, resultSet in enumerate(resultPerSearch):
                results.append({})
                for word in resultSet.strip().split('\n'):
                    (l,r) = word.split(':')
                    if l not in results[i]:
                        results[i][l] = []
                    results[i][l].append(r)
            self.send_response({
                'responseData': {
                    'searchResults': results,
                },
                'responseDetails': None,
                'responseStatus': 200,
            })
        except Exception as e:
            logging.warning('Search error in pair %s-%s: %s', pair[0], pair[1], e)
            self.send_error(503, explanation='internal error')

    @gen.coroutine
    def get(self):
        pair = self.get_pair_or_error(self.get_argument('langpair'))

        if pair is not None:
            yield self.search_and_respond(pair, self.get_argument('q'))
