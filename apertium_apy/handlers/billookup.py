import logging
import re
from tornado import gen

from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils.translation import translate_simple
from apertium_apy.utils import to_alpha3_code


class BillookupHandler(BaseHandler):
    def get_pair_or_error(self, langpair):
        try:
            l1, l2 = map(to_alpha3_code, langpair.split('|'))
            in_mode = f'{l1}-{l2}'
        except ValueError:
            self.send_error(400, explanation='That pair is invalid, use e.g. eng|spa')
            return None

        in_mode = self.find_fallback_mode(in_mode, self.pairs)
        if in_mode not in self.pairs:
            self.send_error(400, explanation='That pair is not installed')
            return None
        return tuple(in_mode.split('-'))

    @gen.coroutine
    def lookup_and_respond(self, pair, query):
        try:
            path, mode = self.billookup['-'.join(pair)]
            formatting = 'none'
            commands = [['apertium', '-d', path, '-f', formatting, mode]]
            result = yield translate_simple(query, commands)

            entries = result.strip().split('^')
            raw_results = []
            for entry in entries:
                entry = entry.strip()
                if not entry or '$' not in entry:
                    continue
                entry = entry.split('$')[0]
                parts = entry.split('/')
                if len(parts) < 2:
                    continue
                source = parts[0]
                targets = [t for t in parts[1:] if not t.startswith('*')]
                if targets:
                    raw_results.append({source: targets})

            # allowed subcategories per POS (to be filled out)
            # could separate this out in a language specific way
            allowed = {
                'n': ['m', 'f', 'nt', 'aa', 'nn'],
                'np': ['ant', 'top', 'cog', 'm', 'f', 'nt', 'mf', 'aa', 'nn'],
                'v': ['tv', 'iv'],
                'vblex': [],
            }

            def normalize(form):
                word = form.split('<', 1)[0]
                tags = re.findall(r'<([^>]+)>', form)
                if not tags:
                    return word, []
                pos = tags[0]
                subcats = allowed.get(pos, [])
                filtered = []
                extra = []
                for t in tags[1:]:
                    if t in subcats:
                        if t not in filtered:
                            filtered.append(t)
                    else:
                        tag_with_brackets = f'<{t}>'
                        if tag_with_brackets not in extra:
                            extra.append(tag_with_brackets)
                tag_str = f'<{pos}>' + ''.join(f'<{t}>' for t in filtered)
                return f'{word}{tag_str}', extra

            consolidated = {}
            for item in raw_results:
                for src in item:
                    norm_src, extra_src = normalize(src)
                    if norm_src not in consolidated:
                        consolidated[norm_src] = {'targets': {}, 'extra_tags': []}
                    for tag in extra_src:
                        if tag not in consolidated[norm_src]['extra_tags']:
                            consolidated[norm_src]['extra_tags'].append(tag)
                    for tgt in item[src]:
                        norm_tgt, _ = normalize(tgt)
                        if norm_tgt not in consolidated[norm_src]['targets']:
                            consolidated[norm_src]['targets'][norm_tgt] = True

            results = []
            for src, data in consolidated.items():
                tgt_list = list(data['targets'].keys())
                if data['extra_tags']:
                    extra_combined = ''.join(data['extra_tags'])
                    entry = {
                        src: tgt_list,
                        'extra-tags': [extra_combined],
                    }
                else:
                    entry = {
                        src: tgt_list,
                        'extra-tags': [],
                    }
                results.append(entry)

            self.send_response({
                'responseData': {
                    'lookupResults': results,
                },
                'responseDetails': None,
                'responseStatus': 200,
            })
        except Exception as e:
            logging.warning('Lookup error in pair %s-%s: %s', pair[0], pair[1], e)
            self.send_error(503, explanation='internal error')

    @gen.coroutine
    def get(self):
        pair = self.get_pair_or_error(self.get_argument('langpair'))

        if pair is not None:
            yield self.lookup_and_respond(pair, self.get_argument('q'))
