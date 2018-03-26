from multiprocessing import Pool

from tornado import gen

from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils import to_alpha3_code, get_coverage, run_async_thread


class CoverageHandler(BaseHandler):
    @gen.coroutine
    def get(self):
        mode = to_alpha3_code(self.get_argument('lang'))
        text = self.get_argument('q')
        if not text:
            self.send_error(400, explanation='Missing q argument')
            return

        def handle_coverage(coverage):
            if coverage is None:
                self.send_error(408, explanation='Request timed out')
            else:
                self.send_response([coverage])

        if mode in self.analyzers:
            pool = Pool(processes=1)
            result = pool.apply_async(get_coverage, [text, self.analyzers[mode][0], self.analyzers[mode][1]])
            pool.close()

            @run_async_thread
            def worker(callback):
                try:
                    callback(result.get(timeout=self.timeout))
                except TimeoutError:
                    pool.terminate()
                    callback(None)

            coverage = yield gen.Task(worker)
            handle_coverage(coverage)
        else:
            self.send_error(400, explanation='That mode is not installed')
