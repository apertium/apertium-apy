from tornado import gen

from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils import to_alpha3_code
from apertium_apy.utils.translation import parse_mode_file, translate_pipeline


class PipeDebugHandler(BaseHandler):
    @gen.coroutine
    def get(self):
        to_translate = self.get_argument('q')

        try:
            l1, l2 = map(to_alpha3_code, self.get_argument('langpair').split('|'))
        except ValueError:
            self.send_error(400, explanation='That pair is invalid, use e.g. eng|spa')

        mode_path = self.pairs['%s-%s' % (l1, l2)]
        try:
            _, commands = parse_mode_file(mode_path)
        except Exception:
            self.send_error(500)
            return

        res = yield translate_pipeline(to_translate, commands)
        if self.get_status() != 200:
            self.send_error(self.get_status())
            return

        output, pipeline = res

        self.send_response({
            'responseData': {'output': output, 'pipeline': pipeline},
            'responseDetails': None,
            'responseStatus': 200,
        })
