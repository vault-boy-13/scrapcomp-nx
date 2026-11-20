"""Actual x86 OUT encodings route width/register slices and preserve flags."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime/xboxrecomp'))
from tools.recomp.disasm import Disassembler
from tools.recomp.lifter import Lifter, _EFLAGS_PRESERVE


class PortOutTest(unittest.TestCase):
    def test_real_in_encodings(self):
        for raw, port, assignment, width in [
            ('ec', 'LO16(edx)', 'SET_LO8(eax,', 1),
            ('66ed', 'LO16(edx)', 'SET_LO16(eax,', 2),
            ('ed', 'LO16(edx)', 'eax =', 4),
            ('e4c0', '0xC0', 'SET_LO8(eax,', 1),
            ('66e5c0', '0xC0', 'SET_LO16(eax,', 2),
            ('e5c0', '0xC0', 'eax =', 4),
        ]:
            with self.subTest(raw=raw):
                data = bytes.fromhex(raw)
                instruction = Disassembler().disassemble_function(data, 0x1000, 0x1000 + len(data))[0]
                lifter = Lifter()
                code = '\n'.join(lifter.lift_instruction(instruction))
                self.assertFalse(lifter.unimplemented)
                self.assertIn(assignment, code)
                self.assertIn('recomp_port_in(', code)
                self.assertIn(port, code)
                self.assertIn(f'{width}u, 0x00001000u', code)
        self.assertIn('in', _EFLAGS_PRESERVE)

    def test_real_out_encodings(self):
        for raw, port, value, width in [
            ('ee', 'LO16(edx)', 'LO8(eax)', 1),
            ('66ef', 'LO16(edx)', 'LO16(eax)', 2),
            ('ef', 'LO16(edx)', 'eax', 4),
            ('e6c0', '0xC0', 'LO8(eax)', 1),
            ('66e7c0', '0xC0', 'LO16(eax)', 2),
            ('e7c0', '0xC0', 'eax', 4),
        ]:
            with self.subTest(raw=raw):
                data = bytes.fromhex(raw)
                instruction = Disassembler().disassemble_function(data, 0x1000, 0x1000 + len(data))[0]
                lifter = Lifter()
                code = '\n'.join(lifter.lift_instruction(instruction))
                self.assertFalse(lifter.unimplemented)
                self.assertIn('recomp_port_out(', code)
                self.assertIn(port, code)
                self.assertIn(value, code)
                self.assertIn(f'{width}u, 0x00001000u', code)
        self.assertIn('out', _EFLAGS_PRESERVE)


if __name__ == '__main__':
    unittest.main()
