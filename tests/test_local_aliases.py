"""Opt-in recovery cannot discard a real external entry."""
from pathlib import Path
import copy
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime/xboxrecomp'))
from tools.recomp import config
from tools.recomp.translator import FunctionTranslator
BASE=0x10000
CODE=bytes.fromhex('89f1eb00404975fcc3')
ALIAS=BASE+4
END=BASE+len(CODE)

def subject():
    raw=bytearray(b'\xCC'*0x400)
    raw[:len(CODE)]=CODE
    db={
        BASE:{'_addr':BASE,'start':hex(BASE),'end':ALIAS,'size':4,'section':'.text'},
        ALIAS:{'_addr':ALIAS,'start':hex(ALIAS),'end':END,'size':END-ALIAS,
               'section':'.text','detection_method':'tail_jump_alias','called_by':[]}}
    return FunctionTranslator(bytes(raw),db)

class LocalAliasTests(unittest.TestCase):
    def setUp(self):
        layout=patch.object(config,'_SECTIONS',[config.Section('.text',BASE,0x400,0,0x400,True)])
        layout.start()
        self.addCleanup(layout.stop)
    def reject(self,s):
        before=copy.deepcopy(s.func_db)
        with self.assertRaises(ValueError):
            s.coalesce_function(BASE,END,[ALIAS],local_aliases=[ALIAS])
        self.assertEqual(before,s.func_db)
    def test_default_still_protects_alias(self):
        with self.assertRaisesRegex(ValueError,'independent evidence'):
            subject().coalesce_function(BASE,END,[ALIAS])
    def test_proven_local_label_is_owned(self):
        s=subject()
        s.coalesce_function(BASE,END,[ALIAS],local_aliases=[ALIAS])
        self.assertEqual(list(s.func_db),[BASE])
        self.assertEqual(s.func_db[BASE]['end'],END)
    def test_absolute_reference_anywhere_rejects(self):
        s=subject()
        raw=bytearray(s.xbe_data)
        raw[0x300:0x304]=ALIAS.to_bytes(4,'little')
        s.xbe_data=bytes(raw)
        self.reject(s)
    def test_external_short_branch_rejects(self):
        s=subject()
        raw=bytearray(s.xbe_data)
        raw[0x40:0x42]=b'\xEB'+(ALIAS-(BASE+0x42)).to_bytes(1,'little',signed=True)
        s.xbe_data=bytes(raw)
        self.reject(s)
    def test_external_near_conditional_rejects(self):
        s=subject()
        raw=bytearray(s.xbe_data)
        raw[0x40:0x46]=b'\x0F\x85'+(ALIAS-(BASE+0x46)).to_bytes(4,'little',signed=True)
        s.xbe_data=bytes(raw)
        self.reject(s)
    def test_external_call_rejects(self):
        s=subject()
        raw=bytearray(s.xbe_data)
        raw[0x40:0x45]=b'\xE8'+(ALIAS-(BASE+0x45)).to_bytes(4,'little',signed=True)
        s.xbe_data=bytes(raw)
        self.reject(s)
    def test_independent_metadata_rejects(self):
        for evidence in ({'has_prologue':True},{'external_entry':True},
                         {'called_by':[hex(BASE+0x80)]},{'detection_method':'call_target'}):
            with self.subTest(evidence=evidence):
                s=subject()
                s.func_db[ALIAS].update(evidence)
                self.reject(s)
    def test_protected_entry_rejects(self):
        s=subject()
        s.protected_function_starts.add(ALIAS)
        self.reject(s)

    def collision(self, code, *, strong=True):
        s=subject()
        raw=bytearray(s.xbe_data)
        raw[0x80:0x80+len(code)]=code
        s.xbe_data=bytes(raw)
        start=BASE+0x80
        s.func_db[start]={'_addr':start,'start':hex(start),'end':start+len(code),
            'section':'.text','detection_method':'call_target' if strong else 'cc_boundary',
            'called_by':[hex(BASE+0x200)] if strong else []}
        return s

    def test_relative_call_displacement_is_not_absolute_pointer(self):
        s=self.collision(b'\xE8'+ALIAS.to_bytes(4,'little')+b'\xC3')
        s.coalesce_function(BASE,END,[ALIAS],local_aliases=[ALIAS])
        self.assertNotIn(ALIAS,s.func_db)

    def test_literal_immediate_in_independent_function_still_rejects(self):
        self.reject(self.collision(b'\x68'+ALIAS.to_bytes(4,'little')+b'\xC3'))

    def test_absolute_memory_displacement_still_rejects(self):
        self.reject(self.collision(b'\x8B\x83'+ALIAS.to_bytes(4,'little')+b'\xC3'))

    def test_weak_owner_cannot_classify_pointer_bytes(self):
        self.reject(self.collision(b'\xE8'+ALIAS.to_bytes(4,'little')+b'\xC3',strong=False))

    def frame_collision(self, *, called=True, frame_bytes=True):
        prefix=b'\x55\x8B\xEC' if frame_bytes else b'\x90\x90\x90'
        s=self.collision(prefix+b'\xE8'+ALIAS.to_bytes(4,'little')+b'\xC9\xC3')
        s.func_db[BASE+0x80].update(detection_method='prologue',has_prologue=True,
                                 called_by=[hex(BASE+0x200)] if called else [])
        return s

    def test_independently_called_real_frame_prologue_can_classify(self):
        s=self.frame_collision()
        s.coalesce_function(BASE,END,[ALIAS],local_aliases=[ALIAS])
        self.assertNotIn(ALIAS,s.func_db)

    def test_uncalled_frame_prologue_still_rejects(self):
        self.reject(self.frame_collision(called=False))

    def test_prologue_metadata_without_frame_bytes_still_rejects(self):
        self.reject(self.frame_collision(frame_bytes=False))

    def test_frame_prologue_with_real_pointer_still_rejects(self):
        s=self.frame_collision()
        raw=bytearray(s.xbe_data)
        raw[0x83]=0x68  # PUSH immediate instead of relative CALL
        s.xbe_data=bytes(raw)
        self.reject(s)

    def test_unreachable_bytes_after_return_still_reject(self):
        self.reject(self.collision(b'\xC3\xE8'+ALIAS.to_bytes(4,'little')+b'\xC3'))

    def test_match_spanning_instruction_boundary_still_rejects(self):
        # 04 00 / 01 00 decode as ADD AL,0; ADD [EAX],EAX. The four
        # address bytes are not wholly inside one proven instruction.
        self.reject(self.collision(ALIAS.to_bytes(4,'little')+b'\xC3'))

    def test_conditional_owner_edge_proves_local_alias(self):
        s=subject()
        raw=bytearray(s.xbe_data)
        raw[:len(CODE)]=bytes.fromhex('85c97500404975fcc3')
        s.xbe_data=bytes(raw)
        s.coalesce_function(BASE,END,[ALIAS],local_aliases=[ALIAS])
        self.assertNotIn(ALIAS,s.func_db)

    def test_alias_without_decoded_owner_edge_rejects(self):
        s=subject()
        raw=bytearray(s.xbe_data)
        raw[:len(CODE)]=bytes.fromhex('89f1909040484990c3')
        s.xbe_data=bytes(raw)
        self.reject(s)

if __name__=='__main__': unittest.main()
