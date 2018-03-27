import re
from multiprocessing import Pool
from subprocess import Popen, PIPE

from tornado import gen

from apertium_apy.handlers.base import BaseHandler
from apertium_apy.utils import apertium, run_async_thread, remove_dot_from_deformat, to_alpha3_code


def bilingual_translate(to_translate, mode_dir, mode):
    p1 = Popen(['echo', to_translate], stdout=PIPE)
    p2 = Popen(['lt-proc', '-b', mode], stdin=p1.stdout, stdout=PIPE, cwd=mode_dir)
    p1.stdout.close()
    output = p2.communicate()[0].decode('utf-8')
    return output


def strip_tags(analysis):
    if '<' in analysis:
        return analysis[:analysis.index('<')]
    else:
        return analysis


def process_per_word(analyzers, taggers, lang, modes, query):
    outputs = {}
    morph_lexical_units = None
    tagger_lexical_units = None
    lexical_unit_re = r'\^([^\$]*)\$'

    if 'morph' in modes or 'biltrans' in modes:
        if lang in analyzers:
            mode_info = analyzers[lang]
            analysis = apertium(query, mode_info[0], mode_info[1])
            morph_lexical_units = remove_dot_from_deformat(query, re.findall(lexical_unit_re, analysis))
            outputs['morph'] = [lu.split('/')[1:] for lu in morph_lexical_units]
            outputs['morph_inputs'] = [strip_tags(lu.split('/')[0]) for lu in morph_lexical_units]
        else:
            return

    if 'tagger' in modes or 'disambig' in modes or 'translate' in modes:
        if lang in taggers:
            mode_info = taggers[lang]
            analysis = apertium(query, mode_info[0], mode_info[1])
            tagger_lexical_units = remove_dot_from_deformat(query, re.findall(lexical_unit_re, analysis))
            outputs['tagger'] = [lu.split('/')[1:] if '/' in lu else lu for lu in tagger_lexical_units]
            outputs['tagger_inputs'] = [strip_tags(lu.split('/')[0]) for lu in tagger_lexical_units]
        else:
            return

    if 'biltrans' in modes:
        if morph_lexical_units:
            outputs['biltrans'] = []
            for lu in morph_lexical_units:
                split_unit = lu.split('/')
                forms = split_unit[1:] if len(split_unit) > 1 else split_unit
                raw_translations = bilingual_translate(''.join(['^%s$' % form for form in forms]), mode_info[0], lang + '.autobil.bin')
                translations = re.findall(lexical_unit_re, raw_translations)
                outputs['biltrans'].append(list(map(lambda x: '/'.join(x.split('/')[1:]), translations)))
                outputs['translate_inputs'] = outputs['morph_inputs']
        else:
            return

    if 'translate' in modes:
        if tagger_lexical_units:
            outputs['translate'] = []
            for lu in tagger_lexical_units:
                split_unit = lu.split('/')
                forms = split_unit[1:] if len(split_unit) > 1 else split_unit
                raw_translations = bilingual_translate(''.join(['^%s$' % form for form in forms]), mode_info[0], lang + '.autobil.bin')
                translations = re.findall(lexical_unit_re, raw_translations)
                outputs['translate'].append(list(map(lambda x: '/'.join(x.split('/')[1:]), translations)))
                outputs['translate_inputs'] = outputs['tagger_inputs']
        else:
            return

    return outputs, tagger_lexical_units, morph_lexical_units


class PerWordHandler(BaseHandler):
    @gen.coroutine
    def get(self):
        lang = to_alpha3_code(self.get_argument('lang'))
        modes = set(self.get_argument('modes').split(' '))
        query = self.get_argument('q')

        if not modes <= {'morph', 'biltrans', 'tagger', 'disambig', 'translate'}:
            self.send_error(400, explanation='Invalid mode argument')
            return

        def handle_output(output):
            """to_return = {}
            for mode in modes:
                to_return[mode] = outputs[mode]
            for mode in modes:
                to_return[mode] = {outputs[mode + '_inputs'][index]: output for (index, output) in enumerate(outputs[mode])}
            for mode in modes:
                to_return[mode] = [(outputs[mode + '_inputs'][index], output) for (index, output) in enumerate(outputs[mode])]
            for mode in modes:
                to_return[mode] = {'outputs': outputs[mode], 'inputs': outputs[mode + '_inputs']}
            self.send_response(to_return)"""

            if output is None:
                self.send_error(400, explanation='No output')
                return
            elif not output:
                self.send_error(408, explanation='Request timed out')
                return
            else:
                outputs, tagger_lexical_units, morph_lexical_units = output

            to_return = []

            for (index, lexical_unit) in enumerate(tagger_lexical_units if tagger_lexical_units else morph_lexical_units):
                unit_to_return = {}
                unit_to_return['input'] = strip_tags(lexical_unit.split('/')[0])
                for mode in modes:
                    unit_to_return[mode] = outputs[mode][index]
                to_return.append(unit_to_return)

            if self.get_argument('pos', default=None):
                requested_pos = int(self.get_argument('pos')) - 1
                current_pos = 0
                for unit in to_return:
                    input = unit['input']
                    current_pos += len(input.split(' '))
                    if requested_pos < current_pos:
                        self.send_response(unit)
                        return
            else:
                self.send_response(to_return)

        pool = Pool(processes=1)
        result = pool.apply_async(process_per_word, (self.analyzers, self.taggers, lang, modes, query))
        pool.close()

        @run_async_thread
        def worker(callback):
            try:
                callback(result.get(timeout=self.timeout))
            except TimeoutError:
                pool.terminate()
                callback(None)

        output = yield gen.Task(worker)
        handle_output(output)
