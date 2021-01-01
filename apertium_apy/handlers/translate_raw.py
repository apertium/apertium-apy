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
        pair = self.get_pair_or_error(self.get_argument('langpair'),
                                      len(self.get_argument('q', strip=False)))
        if pair is not None:
            pipeline = self.get_pipeline(pair)
            deformat = self.get_argument('deformat', default='True') != 'False'
            yield self.translate_and_respond(pair,
                                             pipeline,
                                             self.get_argument('q', strip=False),
                                             self.get_argument('markUnknown', default='yes'),
                                             nosplit=False,
                                             deformat=deformat,
                                             reformat=False)
