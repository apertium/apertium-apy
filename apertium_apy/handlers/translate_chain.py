from tornado import gen

from apertium_apy.handlers.translate import TranslateHandler
from apertium_apy.utils import to_alpha3_code
from apertium_apy.utils.translation import coreduce


class TranslateChainHandler(TranslateHandler):
    def pair_list(self, langs):
        return [(langs[i], langs[i + 1]) for i in range(0, len(langs) - 1)]

    def get_pairs_or_error(self, langpairs, text_length):
        langs = [to_alpha3_code(lang) for lang in langpairs.split('|')]
        if len(langs) < 2:
            self.send_error(400, explanation='Need at least two languages, use e.g. eng|spa')
            self.log_after_translation(self.log_before_translation(), text_length)
            return None
        if len(langs) == 2:
            if langs[0] == langs[1]:
                self.send_error(400, explanation='Need at least two languages, use e.g. eng|spa')
                self.log_after_translation(self.log_before_translation(), text_length)
                return None
            return self.paths.get(langs[0], {}).get(langs[1])
        for lang1, lang2 in self.pair_list(langs):
            if '{:s}-{:s}'.format(lang1, lang2) not in self.pairs:
                self.send_error(400, explanation='Pair {:s}-{:s} is not installed'.format(lang1, lang2))
                self.log_after_translation(self.log_before_translation(), text_length)
                return None
        return langs

    @gen.coroutine
    def translate_and_respond(self, pairs, pipelines, to_translate, mark_unknown, nosplit=False, deformat=True, reformat=True):
        mark_unknown = mark_unknown in ['yes', 'true', '1']
        chain, pairs = pairs, self.pair_list(pairs)
        for pair in pairs:
            self.note_pair_usage(pair)
        before = self.log_before_translation()
        translated = yield coreduce(to_translate, [p.translate for p in pipelines], nosplit, deformat, reformat)
        self.log_after_translation(before, len(to_translate))
        self.send_response({
            'responseData': {
                'translatedText': self.maybe_strip_marks(mark_unknown, (pairs[0][0], pairs[-1][1]), translated),
                'translationChain': chain,
            },
            'responseDetails': None,
            'responseStatus': 200,
        })
        self.clean_pairs()

    def prepare(self):
        if not self.pairs_graph:
            self.init_pairs_graph()

    @gen.coroutine
    def get(self):
        q = self.get_argument('q', default=None)
        langpairs = self.get_argument('langpairs')
        pairs = self.get_pairs_or_error(langpairs, len(q or []))
        if pairs:
            if not q:
                self.send_response({
                    'responseData': {
                        'translationChain': self.get_pairs_or_error(self.get_argument('langpairs'), 0),
                    },
                    'responseDetails': None,
                    'responseStatus': 200,
                })
            else:
                pipelines = [self.get_pipeline(pair) for pair in self.pair_list(pairs)]
                deformat, reformat = self.get_format()
                yield self.translate_and_respond(pairs, pipelines, q,
                                                 self.get_argument('markUnknown', default='yes'),
                                                 nosplit=False, deformat=deformat, reformat=reformat)
        else:
            self.send_error(400, explanation='No path found for {:s}-{:s}'.format(*langpairs.split('|')))
            self.log_after_translation(self.log_before_translation(), 0)
