import importlib.util
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('sdk161_static',ROOT/'tools/sdk161_probe/static_profile.py')
profile=importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)


class Static161ProfileTests(unittest.TestCase):
    def test_multiple_sites_are_accepted_only_if_decoded_values_all_agree(self):
        self.assertEqual(profile.consensus([0x4128,0x4128]),0x4128)
        for values in ([],[1,2],[1,1,2]):
            with self.subTest(values=values),self.assertRaises(ValueError):profile.consensus(values)

    def test_rip_displacement_is_signed_relative_to_end_of_instruction(self):
        code=bytes.fromhex('48 8b 05')+struct.pack('<i',-0x100)
        self.assertEqual(profile.decode_operand(code,0x200,0,'48 8b 05','rip_relative_global'),0x107)

    def test_member_decoder_checks_opcode_and_operand_width(self):
        code=bytes.fromhex('48 8d 88 28 41 00 00')
        self.assertEqual(profile.decode_operand(code,0,0,'48 8d 88','member_offset'),0x4128)
        with self.assertRaises(ValueError):profile.decode_operand(code,0,0,'48 8b 88','member_offset')
        with self.assertRaises(ValueError):profile.decode_operand(code[:5],0,0,'48 8d 88','member_offset')

    def test_binding_rejects_unbacked_instructions_and_bad_global_slots(self):
        text=SimpleNamespace(Characteristics=0x60000020,VirtualAddress=0x1000,Misc_VirtualSize=0x100,SizeOfRawData=0x100)
        data=SimpleNamespace(Characteristics=0xc0000040,VirtualAddress=0x2000,Misc_VirtualSize=0x100,SizeOfRawData=0x100)
        def fake(target=0x2000):
            return SimpleNamespace(get_section_by_rva=lambda r: text if 0x1000<=r<0x1100 else data if 0x2000<=r<0x2100 else None,
                get_data=lambda r,n: bytes.fromhex('48 8b 05')+struct.pack('<i',target-r-7))
        result=profile.resolve_binding(fake(),[0x1000],0,'48 8b 05','rip_relative_global')
        self.assertEqual(result['value'],0x2000)
        for target in (0x1000,0x2001,0x2100):
            with self.subTest(target=target),self.assertRaises(ValueError):
                profile.resolve_binding(fake(target),[0x1000],0,'48 8b 05','rip_relative_global')
        with self.assertRaises(ValueError):profile.resolve_binding(fake(),[0x10fc],0,'48 8b 05','rip_relative_global')
        text.SizeOfRawData=2
        with self.assertRaises(ValueError):profile.resolve_binding(fake(),[0x1000],0,'48 8b 05','rip_relative_global')

    def test_binding_rejects_divergent_members_and_invalid_alignment(self):
        section=SimpleNamespace(Characteristics=0x60000020,VirtualAddress=0x1000,Misc_VirtualSize=0x100,SizeOfRawData=0x100)
        pe=SimpleNamespace(get_section_by_rva=lambda r:section,
            get_data=lambda r,n:bytes.fromhex('48 8d 88')+struct.pack('<I',0x4128 if r==0x1000 else 0x4130))
        with self.assertRaises(ValueError):profile.resolve_binding(pe,[0x1000,0x1010],0,'48 8d 88','member_offset')
        for value in (0,3,0x100000):
            pe.get_data=lambda r,n:bytes.fromhex('48 8d 88')+struct.pack('<I',value)
            with self.subTest(value=value),self.assertRaises(ValueError):
                profile.resolve_binding(pe,[0x1000],0,'48 8d 88','member_offset')

    def test_saved_occurrences_cannot_omit_a_second_match(self):
        code=bytes.fromhex('48 8b 00 01 02 ff 48 8b 0a 01 02 ff')
        pe=SimpleNamespace(sections=[SimpleNamespace(Characteristics=0x20000000,VirtualAddress=0x1000,get_data=lambda:code)])
        row=dict(pattern='48 8b ? 01 02 ff',executable_rvas=[0x1000,0x1006])
        profile.verify_occurrences(pe,row)
        row['executable_rvas']=[0x1000]
        with self.assertRaises(ValueError):profile.verify_occurrences(pe,row)

    def test_profile_records_all_occurrences_and_never_claims_runtime_layouts(self):
        result=json.loads((profile.AUDIT/'static-profile-161.json').read_text())
        self.assertEqual(len(result['bindings']),10)
        self.assertFalse(result['production_ready']);self.assertFalse(result['dynamic_layouts_verified'])
        self.assertFalse(result['game_memory_read'])
        self.assertEqual(len(result['bindings']['base_ctrl_global']['sites']),2)
        self.assertEqual(len(result['bindings']['gps_manager_member']['sites']),2)
        for row in result['bindings'].values():
            self.assertEqual({s['operand'] for s in row['sites']},{row['value']})
            self.assertFalse(row['object_layout_verified'])
        self.assertGreater(len(result['unverified']),3)
