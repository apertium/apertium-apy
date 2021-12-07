from datetime import timedelta

from tornado import gen

from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils import to_alpha3_code, get_coverage


class CoverageHandler(BaseHandler):
    @gen.coroutine
    def get(self):
        mode = to_alpha3_code(self.get_argument('lang'))
        if '-' in mode:
            l1, l2 = map(to_alpha3_code, mode.split('-', 1))
            mode = '%s-%s' % (l1, l2)
        mode = self.find_fallback_mode(mode, self.analyzers)
        text = self.get_argument('q')
        if not text:
            self.send_error(400, explanation='Missing q argument')
            return

        if mode in self.analyzers:
            try:
                coverage = yield gen.with_timeout(
                    timedelta(seconds=self.timeout),
                    get_coverage(text, self.analyzers[mode][0], self.analyzers[mode][1]),
                )
                self.send_response([coverage])
            except gen.TimeoutError:
                self.send_error(408, explanation='Request timed out')
        else:
            self.send_error(400, explanation='That mode is not installed')
