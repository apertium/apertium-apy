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
    def lookup_and_respond(self, pair, query):
        try:
            path, mode = self.billookup["-".join(pair)]
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
            allowed = {
                "n": ["m", "f", "nt", "aa", "nn"],
                "np": ["ant", "top", "cog", "m", "f", "nt", "mf", "aa", "nn"],
                "v": ["tv", "iv"],
            }

            def normalize(form):
                word = form.split("<", 1)[0]
                tags = re.findall(r"<([^>]+)>", form)
                if not tags:
                    return word
                pos = tags[0]
                subcats = allowed.get(pos, [])
                filtered = []
                for t in tags[1:]:
                    if t in subcats and t not in filtered:
                        filtered.append(t)
                tag_str = f"<{pos}>" + "".join(f"<{t}>" for t in filtered)
                return f"{word}{tag_str}"

            consolidated = {}
            for item in raw_results:
                for src in item:
                    norm_src = normalize(src)
                    if norm_src not in consolidated:
                        consolidated[norm_src] = []
                    for tgt in item[src]:
                        norm_tgt = normalize(tgt)
                        if norm_tgt not in consolidated[norm_src]:
                            consolidated[norm_src].append(norm_tgt)

            results = []
            for src, tgts in consolidated.items():
                tgt_list = []
                for t in tgts:
                    tgt_list.append(t)
                entry = {}
                entry[src] = tgt_list
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
