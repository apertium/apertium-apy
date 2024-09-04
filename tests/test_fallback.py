from unittest import TestCase

from apertium_apy.utils import to_fallback_code


class TestRootHandler(TestCase):
    def test_existing_mode_returns(self):
        mode = 'spa-cat_valencia_uni'
        installed_modes = {
            'spa-cat': '/modes/spa-cat',
            'spa-cat_valencia': '/modes/spa-cat-valencia',
            'spa-cat_valencia_uni': '/modes/spa-cat_valencia_uni',
        }

        output = to_fallback_code(mode, installed_modes)

        self.assertEqual(output, mode)

    def test_fallback_one_level(self):
        mode = 'spa-cat_valencia_uni'
        installed_modes = {
            'spa-cat': '/modes/spa-cat',
            'spa-cat_valencia': '/modes/spa-cat-valencia',
        }

        output = to_fallback_code(mode, installed_modes)

        self.assertEqual(output, 'spa-cat_valencia')

    def test_fallback_root(self):
        mode = 'spa-cat_valencia_uni'
        installed_modes = {
            'spa-cat': '/modes/spa-cat',
        }

        output = to_fallback_code(mode, installed_modes)

        self.assertEqual(output, 'spa-cat')

    def test_fallback_target_has_priority(self):
        mode = 'src_srcvariant-trg_trgvariant'
        installed_modes = {
            'src-trg': '/modes/src-trg',
            'src_srcvariant-trg': '/modes/src_srcvariant-trg',
            'src-trg_trgvariant': '/modes/src-trg_trgvariant',
        }

        output = to_fallback_code(mode, installed_modes)

        self.assertEqual(output, 'src-trg_trgvariant')

    def test_fallback_source(self):
        mode = 'src_srcvariant-trg_trgvariant'
        installed_modes = {
            'src-trg': '/modes/src-trg',
            'src_srcvariant-trg': '/modes/src_srcvariant-trg',
        }

        output = to_fallback_code(mode, installed_modes)

        self.assertEqual(output, 'src_srcvariant-trg')

    def test_two_fallbacks(self):
        mode = 'src_srcvariant-trg_trgvariant'
        installed_modes = {
            'src-trg': '/modes/src-trg',
            'src_srcvariant-trg_trgvariant': '/modes/src_srcvariant-trg_trgvariant',
        }

        output = to_fallback_code(mode, installed_modes)

        self.assertEqual(output, mode)
