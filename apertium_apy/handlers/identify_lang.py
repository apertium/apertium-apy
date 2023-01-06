from datetime import timedelta

from tornado import gen

try:
    import fasttext
except ImportError:
    fasttext = None
try:
    import cld2full as cld2  # type: ignore
except ImportError:
    cld2 = None

from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils import get_coverages, to_alpha3_code


def fasttext_strip_prefix(s):
    """Remove the initial __label__ prefix"""
    return s[9:]


def fasttext_identify(model, text):
    # grab a bunch since currently the model might predict stuff outside possible_langs – it's still fast:
    results = model.predict(text, k=200, threshold=0.001)
    if results[0]:
        possible_langs = zip(map(fasttext_strip_prefix, results[0]),
                             results[1])
        return {to_alpha3_code(possible_lang[0]): possible_lang[1]
                for possible_lang in possible_langs}
    else:
        return {'nob': 1.0}  # TODO: better default


def cld_identify(text):
    cld_results = cld2.detect(text)
    if cld_results[0]:
        possible_langs = filter(lambda x: x[1] != 'un', cld_results[2])
        return {to_alpha3_code(possible_lang[1]): possible_lang[2]
                for possible_lang in possible_langs}
    else:
        return {'nob': 1.0}  # TODO: better default


class IdentifyLangHandler(BaseHandler):
    fasttext = None

    @gen.coroutine
    def get(self):
        text = self.get_argument('q')
        if not text:
            return self.send_error(400, explanation='Missing q argument')

        if self.fasttext is not None:
            self.send_response(fasttext_identify(self.fasttext, text))
        elif cld2:
            self.send_response(cld_identify(text))
        else:
            try:
                coverages = yield gen.with_timeout(
                    timedelta(seconds=self.timeout),
                    get_coverages(text, self.analyzers, penalize=True),
                )
                self.send_response(coverages)

            except gen.TimeoutError:
                self.send_error(408, explanation='Request timed out')
