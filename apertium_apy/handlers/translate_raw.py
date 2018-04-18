from tornado import gen
from tornado.escape import utf8

from apertium_apy.handlers.translate import TranslateHandler


class TranslateRawHandler(TranslateHandler):
    """Assumes the pipeline itself outputs as JSON"""
    def send_response(self, data):
        translated_text = data.get('responseData', {}).get('translatedText', {})
        if translated_text == {}:
            super().send_response(data)
        else:
            self.log_vmsize()
            translated_text = data.get('responseData', {}).get('translatedText', {})
            self.set_header('Content-Type', 'application/json; charset=UTF-8')
            self._write_buffer.append(utf8(translated_text))
            self.finish()

    @gen.coroutine
    def get(self):
        query = self.get_argument('q', strip=False)
        pair = self.get_pair_or_error(self.get_argument('langpair'), len(query))
        if pair is not None:
            pipeline = self.get_pipeline(pair)
            self.note_pair_usage(pair)
            before = self.log_before_translation()
            translated = yield pipeline.translate(query, 
                                                  nosplit=False, 
                                                  deformat=self.get_argument('deformat', default=True), 
                                                  reformat=False)
            self.log_after_translation(before, len(query))
            self.send_response({
                'responseData': {
                    'translatedText': self.maybe_strip_marks(self.mark_unknown, pair, translated),
                },
                'responseDetails': None,
                'responseStatus': 200,
            })
            self.clean_pairs()

