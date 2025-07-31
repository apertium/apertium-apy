import logging
import os
from tornado import gen

from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils.translation import translate_simple
from apertium_apy.utils import to_alpha3_code

class EmbeddingsHandler(BaseHandler):
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
    def embed_and_respond(self, pair, query):
        try:
            raw_path, mode = self.embeddings["-".join(pair)]
            path = os.path.abspath(raw_path)

            commands = [['apertium', '-d', path, '-f', 'none', mode]]
            raw = yield translate_simple(query + '\n', commands)

            segments = [seg for seg in raw.strip().split('^') if seg and '/' in seg]
            results = []

            for seg in segments:
                entry = seg.rstrip('~').rstrip('$')
                parts = entry.split('/')
                src = parts[0]
                forms = []
                for t in parts[1:]:
                    t_clean = t.split('~', 1)[0]
                    if t_clean:
                        forms.append(t_clean)
                if forms:
                    results.append({src: forms})

            self.send_response({
                'responseData': {'embeddingResults': results},
                'responseDetails': None,
                'responseStatus': 200,
            })
        except Exception:
            logging.exception('Embedding error in %s-%s', *pair)
            self.send_error(503, explanation='internal error')

    @gen.coroutine
    def get(self):
        pair = self.get_pair_or_error(self.get_argument('langpair'))
        if pair is not None:
            yield self.embed_and_respond(pair, self.get_argument('q'))
