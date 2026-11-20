"""Secondary entry addresses survive recovery, including data references."""
from pathlib import Path
import sys,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime/xboxrecomp'))
from tools.recomp import config
from tools.recomp.translator import FunctionTranslator
BASE=0x10000
ALIAS=BASE+8
CODE=bytes.fromhex('5389cb85c97901cc83fb007e0501d84bebf65bc3')
END=BASE+len(CODE)

def subject(code=CODE):
    raw=bytearray(b'\xCC'*0x400)
    raw[:len(code)]=code
    raw[0x300:0x304]=ALIAS.to_bytes(4,'little')
    db={BASE:{'_addr':BASE,'start':hex(BASE),'end':ALIAS,'size':8,'section':'.text'},
        ALIAS:{'_addr':ALIAS,'start':hex(ALIAS),'end':BASE+len(code),'size':len(code)-8,
               'section':'.text','detection_method':'tail_jump_alias','called_by':[]}}
    return FunctionTranslator(bytes(raw),db)

class RetainedEntryTests(unittest.TestCase):
    def setUp(self):
        p=patch.object(config,'_SECTIONS',[config.Section('.text',BASE,0x400,0,0x400,True)])
        p.start();self.addCleanup(p.stop)
    def test_data_reference_does_not_disappear(self):
        s=subject()
        s.coalesce_function(BASE,END,[ALIAS],retained_entries=[ALIAS])
        self.assertIn(ALIAS,s.func_db)
        self.assertEqual(s.retained_entry_owners,{ALIAS:BASE})
        owner=s.translate_function(BASE,s.func_db[BASE])
        alias=s.translate_function(ALIAS,s.func_db[ALIAS])
        self.assertIn('recomp_shared_00010000(uint32_t _entry)',owner)
        self.assertIn('goto loc_00010008;',owner)
        self.assertIn('recomp_shared_00010000(0x00010008u)',alias)
    def test_same_address_cannot_be_removed_and_retained(self):
        with self.assertRaisesRegex(ValueError,'also be removed'):
            subject().coalesce_function(BASE,END,[ALIAS],local_aliases=[ALIAS],retained_entries=[ALIAS])
    def test_immediate_reference_entry_preserves_dispatch(self):
        s=subject();s.func_db[ALIAS]['detection_method']='imm_ref_target'
        s.coalesce_function(BASE,END,[ALIAS],retained_entries=[ALIAS])
        self.assertIn(ALIAS,s.func_db)
        self.assertIn('recomp_shared_00010000(0x00010008u)',
                      s.translate_function(ALIAS,s.func_db[ALIAS]))
    def test_immediate_reference_own_prologue_is_rejected(self):
        s=subject();s.func_db[ALIAS].update(detection_method='imm_ref_target',has_prologue=True)
        with self.assertRaisesRegex(ValueError,'own prologue'):
            s.coalesce_function(BASE,END,[ALIAS],retained_entries=[ALIAS])
    def test_immediate_reference_incoming_flags_are_rejected(self):
        code=bytearray(CODE);code[8:11]=bytes.fromhex('750190')
        s=subject(bytes(code));s.func_db[ALIAS]['detection_method']='imm_ref_target'
        with self.assertRaises(ValueError):
            s.coalesce_function(BASE,END,[ALIAS],retained_entries=[ALIAS])
    def test_own_prologue_remains_independent(self):
        s=subject();s.func_db[ALIAS]['has_prologue']=True
        with self.assertRaisesRegex(ValueError,'own prologue'):
            s.coalesce_function(BASE,END,[ALIAS],retained_entries=[ALIAS])
    def test_incoming_flags_are_not_fabricated(self):
        code=bytearray(CODE);code[8:11]=bytes.fromhex('750190')
        with self.assertRaises(ValueError):
            subject(bytes(code)).coalesce_function(BASE,END,[ALIAS],retained_entries=[ALIAS])
    def test_unreferenced_entry_cannot_be_invented(self):
        s=subject();s.func_db[ALIAS]['detection_method']='call_target'
        with self.assertRaises(ValueError):
            s.coalesce_function(BASE,END,[ALIAS],retained_entries=[ALIAS])
    def test_data_backed_fallthrough_entry_keeps_its_own_label(self):
        code=bytes.fromhex('5389cb909090909083fb0001d85bc3')
        s=subject(code)
        s.coalesce_function(BASE,BASE+len(code),[ALIAS],retained_entries=[ALIAS])
        owner=s.translate_function(BASE,s.func_db[BASE])
        self.assertIn('loc_00010008: ;',owner)
        self.assertIn('goto loc_00010008;',owner)

if __name__=='__main__': unittest.main()
