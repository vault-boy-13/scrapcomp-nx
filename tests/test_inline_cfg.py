"""Inline dword tables must remain data, including signed/one-based indices."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime/xboxrecomp'))
from tools.recomp import config
from tools.recomp.translator import FunctionTranslator

BASE = 0x10000


class InlineCfgTest(unittest.TestCase):
    def setUp(self):
        layout = patch.object(config, '_SECTIONS', [
            config.Section('.text', BASE, 0x200, 0, 0x200, True)])
        layout.start()
        self.addCleanup(layout.stop)

    def subject(self, raw):
        return FunctionTranslator(raw.ljust(0x200, b'\xcc'), {
            BASE: {'_addr': BASE, 'start': hex(BASE), 'end': BASE + len(raw),
                   'size': len(raw), 'section': '.text'},
        })

    def test_zero_one_based_and_negative_table_indices(self):
        for mode in ('zero', 'one', 'negative'):
            with self.subTest(mode=mode):
                table_base = BASE + {'zero': 16, 'one': 12, 'negative': 24}[mode]
                prefix = bytes.fromhex('83f901771f')
                prefix += {'zero': b'', 'one': b'\x41', 'negative': bytes.fromhex('83e902')}[mode]
                prefix += bytes.fromhex('ff248d') + table_base.to_bytes(4, 'little')
                prefix = prefix.ljust(16, b'\x90')
                raw = (prefix + (BASE + 24).to_bytes(4, 'little')
                       + (BASE + 30).to_bytes(4, 'little')
                       + bytes.fromhex('b834120000c3b878560000c331c0c3'))
                subject = self.subject(raw)
                subject.coalesce_function(BASE, BASE + len(raw), [])
                cfg = subject._recovered_cfg[BASE]
                self.assertNotIn(BASE + 16, {i.address for i in cfg['instructions']})
                self.assertEqual(set(cfg['jump_tables'][table_base]), {BASE + 24, BASE + 30})
                code = subject.translate_function(BASE, subject.func_db[BASE])
                self.assertIn('eax = 0x1234', code)
                self.assertIn('eax = 0x5678', code)
                self.assertFalse(subject.lifter.unimplemented)

    def test_empty_recovery_does_not_change_extent(self):
        subject = self.subject(b'\xc3')
        with self.assertRaisesRegex(ValueError, 'preserve the detected extent'):
            subject.coalesce_function(BASE, BASE + 2, [])

    def test_empty_recovery_requires_a_table(self):
        subject = self.subject(b'\xc3')
        with self.assertRaisesRegex(ValueError, 'requires an inline jump table'):
            subject.coalesce_function(BASE, BASE + 1, [])


if __name__ == '__main__':
    unittest.main()
