"""Actual x86 bytes must not turn privileged register reads into C variables."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime/xboxrecomp'))
from tools.recomp.disasm import Disassembler
from tools.recomp.lifter import Lifter, _EFLAGS_PRESERVE


class PrivilegedMoveTest(unittest.TestCase):
    def test_wbinvd_publishes_coherent_guest_memory(self):
        instruction = Disassembler().disassemble_function(bytes.fromhex('0f09'), 0x1000, 0x1002)[0]
        lifter = Lifter()
        self.assertIn('recomp_cache_writeback_invalidate();', '\n'.join(lifter.lift_instruction(instruction)))
        self.assertFalse(lifter.unimplemented)
        self.assertIn('wbinvd', _EFLAGS_PRESERVE)

    def test_control_and_debug_register_moves_are_reported(self):
        for raw in ('0f20d0', '0f22d0', '0f21c0', '0f23c0'):
            with self.subTest(raw=raw):
                data = bytes.fromhex(raw)
                instruction = Disassembler().disassemble_function(data, 0x1000, 0x1000 + len(data))[0]
                lifter = Lifter()
                code = '\n'.join(lifter.lift_instruction(instruction))
                self.assertEqual(lifter.unimplemented, {'mov': [0x1000]})
                self.assertIn('RECOMP_UNIMPL(', code)
                self.assertNotIn('eax = cr', code)
                self.assertNotIn('eax = dr', code)

    def test_ordinary_register_move_still_translates(self):
        instruction = Disassembler().disassemble_function(bytes.fromhex('89d8'), 0x2000, 0x2002)[0]
        lifter = Lifter()
        code = '\n'.join(lifter.lift_instruction(instruction))
        self.assertEqual(lifter.unimplemented, {})
        self.assertIn('eax = ebx;', code)


if __name__ == '__main__':
    unittest.main()
