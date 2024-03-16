import tornado.gen

from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils import to_alpha2_code


class ListHandler(BaseHandler):
    @tornado.gen.coroutine
    def get(self):
        query = self.get_argument('q', default='all')

        if query == 'all':
            src = self.get_argument('src', default=None)
            response_data = []
            if src:
                pairs = [(src, trg) for trg in self.paths[src]]
            else:
                pairs = [(p[0], p[1]) for par in self.pairs for p in [par.split('-')]]
            for (l1, l2) in pairs:
                response_data.append({'sourceLanguage': l1, 'targetLanguage': l2})
                if self.get_arguments('include_deprecated_codes'):
                    response_data.append({'sourceLanguage': to_alpha2_code(l1), 'targetLanguage': to_alpha2_code(l2)})
            response = {
                'responseData': response_data,
                'generators': {pair: modename for (pair, (path, modename)) in self.generators.items()},
                'taggers': {pair: modename for (pair, (path, modename)) in self.taggers.items()},
                'spellers': {lang_src: modename for (lang_src, (path, modename)) in self.spellers.items()},
                'responseDetails': None,
                'responseStatus': 200
            }
            self.send_response(response)
        elif query == 'analyzers' or query == 'analysers':
            self.send_response({pair: modename for (pair, (path, modename)) in self.analyzers.items()})
        elif query == 'generators':
            self.send_response({pair: modename for (pair, (path, modename)) in self.generators.items()})
        elif query == 'taggers' or query == 'disambiguators':
            self.send_response({pair: modename for (pair, (path, modename)) in self.taggers.items()})
        elif query == 'spellers':
            self.send_response({lang_src: modename for (lang_src, (path, modename)) in self.spellers.items()})
        else:
            self.send_error(400, explanation='Expecting q argument to be one of analysers, generators, spellers, disambiguators, or pairs')

class ListPairHandler(BaseHandler):
    @tornado.gen.coroutine
    def get(self):
        src = self.get_argument('src', default=None)
        response_data = []
        if src:
            pairs = [(src, trg) for trg in self.paths[src]]
        else:
            pairs = [(p[0], p[1]) for par in self.pairs for p in [par.split('-')]]
        for (l1, l2) in pairs:
            response_data.append({'sourceLanguage': l1, 'targetLanguage': l2})
            if self.get_arguments('include_deprecated_codes'):
                response_data.append({'sourceLanguage': to_alpha2_code(l1), 'targetLanguage': to_alpha2_code(l2)})
        self.send_response({'responseData': response_data, 'responseDetails': None, 'responseStatus': 200})
