from datetime import datetime, timedelta

import tornado.gen

from apertium_apy.handlers.base import BaseHandler


class StatsHandler(BaseHandler):
    @tornado.gen.coroutine
    def get(self):
        num_requests_arg = self.get_argument('requests', default='1000')
        try:
            num_requests = int(num_requests_arg)
        except ValueError:
            num_requests = 1000

        period_stats = self.stats.timing[-num_requests:]
        times = sum([x[1] - x[0] for x in period_stats],
                    timedelta())
        chars = sum(x[2] for x in period_stats)
        if times.total_seconds() != 0:
            chars_per_sec = round(chars / times.total_seconds(), 2)
        else:
            chars_per_sec = 0.0
        nrequests = len(period_stats)
        max_age = (datetime.now() - period_stats[0][0]).total_seconds() if period_stats else 0

        uptime = int((datetime.now() - self.stats.startdate).total_seconds())
        use_count = {'%s-%s' % pair: use_count
                     for pair, use_count in self.stats.usecount.items()}
        running_pipes = {'%s-%s' % (l1, l2): len(pipes)
                         for (l1, l2), pipes in self.pipelines.items()
                         if pipes != []}
        holding_pipes = len(self.pipelines_holding)

        self.send_response({
            'responseData': {
                'uptime': uptime,
                'useCount': use_count,
                'runningPipes': running_pipes,
                'holdingPipes': holding_pipes,
                'periodStats': {
                    'charsPerSec': chars_per_sec,
                    'totChars': chars,
                    'totTimeSpent': times.total_seconds(),
                    'requests': nrequests,
                    'ageFirstRequest': max_age,
                },
            },
            'responseDetails': None,
            'responseStatus': 200,
        })
