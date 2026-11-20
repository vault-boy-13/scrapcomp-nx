"""Static callback proofs must remain current across cached rescans."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime/xboxrecomp'))
from tools.recomp import config
from tools.recomp.translator import FunctionTranslator

BASE = 0x10000


def function(start, end):
    return {'_addr': start, 'start': hex(start), 'end': end,
            'size': end - start, 'section': '.text'}


def pattern(table):
    return (b'\xbe' + table.to_bytes(4, 'little') + b'\xbf'
            + (table + 4).to_bytes(4, 'little') + bytes.fromhex('39feffd0c3'))


class CallbackRescanTest(unittest.TestCase):
    def setUp(self):
        self.layout = patch.object(config, '_SECTIONS', [
            config.Section('.text', BASE, 0x400, 0, 0x400, True)])
        self.layout.start()
        self.addCleanup(self.layout.stop)
        raw = bytearray(b'\xcc' * 0x400)
        code = pattern(BASE + 0x300)
        raw[:len(code)] = code
        raw[0x180] = raw[0x190] = 0xC3
        raw[0x300:0x308] = ((BASE + 0x180).to_bytes(4, 'little')
                              + (BASE + 0x190).to_bytes(4, 'little'))
        self.subject = FunctionTranslator(bytes(raw), {
            BASE: function(BASE, BASE + len(code)),
            BASE + 0x180: function(BASE + 0x180, BASE + 0x181),
            BASE + 0x190: function(BASE + 0x190, BASE + 0x191),
        })

    def test_repeated_scan_revalidates_targets_without_decoding_unchanged_code(self):
        subject = self.subject
        with patch.object(subject.disasm, 'disassemble_function',
                          wraps=subject.disasm.disassemble_function) as decode:
            subject.discover_static_indirect_targets(coalescing=True)
            first_count = decode.call_count
            self.assertGreater(first_count, 0)
            subject.func_db[BASE + 0x180]['called_by'] = []
            subject.discover_static_indirect_targets(coalescing=True)
            self.assertEqual(decode.call_count, first_count)
        self.assertEqual(subject.func_db[BASE + 0x180]['called_by'], [f'0x{BASE:08X}'])

    def test_changed_owner_extent_discovers_new_callback(self):
        subject = self.subject
        subject.func_db[BASE]['end'] = BASE + 5
        subject.discover_static_indirect_targets(coalescing=True)
        self.assertFalse(subject.func_db[BASE + 0x180].get('called_by'))
        subject.func_db[BASE]['end'] = BASE + len(pattern(BASE + 0x300))
        subject.discover_static_indirect_targets(coalescing=True)
        self.assertEqual(subject.func_db[BASE + 0x180]['called_by'], [f'0x{BASE:08X}'])

    def test_recovered_cfg_change_at_same_end_invalidates_cached_bounds(self):
        subject = self.subject
        subject.discover_static_indirect_targets(coalescing=True)
        for table in (BASE + 0x300, BASE + 0x304):
            code = pattern(table)
            subject._recovered_cfg[BASE] = {
                'end': BASE + len(code), 'instructions':
                    subject.disasm.disassemble_function(code, BASE, BASE + len(code)),
            }
            subject.discover_static_indirect_targets(coalescing=True)
        self.assertEqual(subject.func_db[BASE + 0x190]['called_by'], [f'0x{BASE:08X}'])


if __name__ == '__main__':
    unittest.main()
