from datetime import timedelta

from tornado import gen

try:
    import cld2full as cld2  # type: ignore
except ImportError:
    cld2 = None

from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils import get_coverages, to_alpha3_code


class IdentifyLangHandler(BaseHandler):
    @gen.coroutine
    def get(self):
        text = self.get_argument('q')
        if not text:
            return self.send_error(400, explanation='Missing q argument')

        if cld2:
            cld_results = cld2.detect(text)
            if cld_results[0]:
                possible_langs = filter(lambda x: x[1] != 'un', cld_results[2])
                self.send_response({to_alpha3_code(possible_lang[1]): possible_lang[2] for possible_lang in possible_langs})
            else:
                self.send_response({'nob': 100})  # TODO: Some more reasonable response
        else:
            try:
                coverages = yield gen.with_timeout(
                    timedelta(seconds=self.timeout),
                    get_coverages(text, self.analyzers, penalize=True),
                )
                self.send_response(coverages)

            except gen.TimeoutError:
                self.send_error(408, explanation='Request timed out')
