"""Post-breakpoint code is retained without treating a trap as successful."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime/xboxrecomp'))
from tools.recomp import config
from tools.recomp.translator import FunctionTranslator
BASE=0x10000
CODE=bytes.fromhex('85c97402eb06ccba0700000089d0c3')
CONT=BASE+7
END=BASE+len(CODE)
def subject(code=CODE):
    raw=code.ljust(0x400,b'\xCC')
    return FunctionTranslator(raw,{
        BASE:{'_addr':BASE,'start':hex(BASE),'end':CONT,'size':7,'section':'.text'},
        CONT:{'_addr':CONT,'start':hex(CONT),'end':END,'size':END-CONT,'section':'.text',
              'detection_method':'cc_boundary'}})
class AssertionContinuationTests(unittest.TestCase):
    def setUp(self):
        layout=patch.object(config,'_SECTIONS',[config.Section('.text',BASE,0x400,0,0x400,True)])
        layout.start()
        self.addCleanup(layout.stop)
    def test_conditional_breakpoint_continuation_is_retained(self):
        s=subject()
        s.coalesce_function(BASE,END,[CONT])
        instructions=s._recovered_cfg[BASE]['instructions']
        self.assertIn(CONT,{i.address for i in instructions})
        body=s.translate_function(BASE,s.func_db[BASE])
        self.assertIn('RECOMP_UNIMPL("int3", 0x00010006u)',body)
    def test_unconditional_breakpoint_does_not_justify_new_owner(self):
        code=bytes.fromhex('85c9eb02eb06ccba0700000089d0c3')
        with self.assertRaises(ValueError):
            subject(code).coalesce_function(BASE,END,[CONT])
    def test_non_boundary_metadata_does_not_seed_continuation(self):
        s=subject()
        s.func_db[CONT]['detection_method']='gap'
        with self.assertRaises(ValueError):
            s.coalesce_function(BASE,END,[CONT])
    def test_unsplit_fallback_after_targeted_trap_is_retained(self):
        s=subject()
        del s.func_db[CONT]
        other=BASE+12
        s.func_db[other]={'_addr':other,'start':hex(other),'end':END,'size':END-other,
                          'section':'.text','detection_method':'cc_boundary'}
        s.coalesce_function(BASE,END,[other])
        instructions=s._recovered_cfg[BASE]['instructions']
        self.assertIn(CONT,{i.address for i in instructions})
        body=s.translate_function(BASE,s.func_db[BASE])
        self.assertIn('RECOMP_UNIMPL("int3", 0x00010006u)',body)
if __name__=='__main__': unittest.main()
