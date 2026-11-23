import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import subprocess
import unittest

import pefile

ROOT=Path(__file__).resolve().parents[2]
AUDIT=ROOT/'docs/steering-audit/oct22-sdk161'
CANDIDATE=AUDIT/'read-candidate-e'


def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class Read161CandidateTests(unittest.TestCase):
    def test_array_hypothesis_rejects_invalid_lengths_and_pointers(self):
        module=load_module('layout161_bounds',ROOT/'tools/sdk161_probe/layout_probe.py')
        raw=struct.pack('<5Q',0,0x10000,2,3,0)
        self.assertEqual(module.checked_array(raw)['size'],2)
        for data,size,capacity in ((0,1,1),(0x10001,1,1),(0x10000,3,2),(0x10000,65,65)):
            with self.subTest(data=data,size=size,capacity=capacity),self.assertRaises(ValueError):
                module.checked_array(struct.pack('<5Q',0,data,size,capacity,0))
        with self.assertRaises(ValueError):module.checked_array(raw[:-1])

    def test_placement_uses_signed_16bit_cells_and_rejects_bad_rotation(self):
        module=load_module('layout161_placement',ROOT/'tools/sdk161_probe/layout_probe.py')
        value=module.decode_placement(struct.pack('<3f2h4f',10,20,30,-2,3,1,0,0,0))
        self.assertEqual(value['world'],[-1014,20,1566])
        for w in (0,math.nan,math.inf):
            with self.subTest(w=w),self.assertRaises(ValueError):
                module.decode_placement(struct.pack('<3f2h4f',0,0,0,0,0,w,0,0,0))

    def test_layout_reader_has_read_only_access_and_never_calls_methods(self):
        source=(ROOT/'tools/sdk161_probe/layout_probe.py').read_text()
        self.assertIn('OpenProcess(0x410,False,pid)',source)
        self.assertIn('MAX_TOTAL=2*1024*1024',source)
        self.assertNotIn('WriteProcessMemory',source)
        self.assertNotIn('CreateRemoteThread',source)
        self.assertNotIn('CFUNCTYPE',source)

    def test_candidate_receipt_pins_every_generated_source(self):
        receipt=json.loads((CANDIDATE/'build-receipt.json').read_text())
        self.assertEqual(receipt['baseline_dll_sha256'],'fd06c12985fb67c48a7b9aaf5dd500d81e6ac23b928b79c95997bb8ed5d55d27')
        for name,digest in receipt['files'].items():
            with self.subTest(path=name):self.assertEqual(hashlib.sha256((CANDIDATE/name).read_bytes()).hexdigest(),digest)
        for name in ('production_ready','deployed','game_verified','controls_enabled'):self.assertFalse(receipt[name])
        self.assertTrue(receipt['isolated_mappings'])

    def test_candidate_has_no_production_buffers_and_only_telemetry_exports(self):
        data=(CANDIDATE/'UltraPilot161ReadCandidate.dll').read_bytes();pe=pefile.PE(data=data)
        self.assertEqual({entry.name for entry in pe.DIRECTORY_ENTRY_EXPORT.symbols},
            {b'scs_telemetry_init',b'scs_telemetry_shutdown'})
        for name in ('ETS2LATraffic','ETS2LASemaphore','ETS2LARoute','ETS2LACameraProps',
                     'Local\\UltraPilotTrafficV1','Local\\UltraPilotSemaphoreV2','Local\\UltraPilotSemaphoreV3'):
            # Match a whole wide literal, not the suffix in CandidateETS2LATraffic.
            with self.subTest(mapping=name):self.assertFalse(
                ('\0'+name+'\0').encode('utf-16le') in data,'Production mapping literal present: '+name)
        for name in ('Local\\UltraPilot161CandidateTrafficV1','Local\\UltraPilot161CandidateSemaphoreV3'):
            self.assertTrue((name+'\0').encode('utf-16le') in data,'Missing diagnostic mapping: '+name)
        core=(CANDIDATE/'src/core.cpp').read_text()
        self.assertIn('void CCore::override_inputs() const {}',core)
        self.assertNotIn('this->override_inputs();',core)
        self.assertIn('!up161::image_matches() || !this->scan_for_required_patterns()',core)
        self.assertIn('if(!prism::base_ctrl_u::scan_patterns())return false;',core)
        self.assertNotIn('initialize_memory_file(input_mmap_data',
            (CANDIDATE/'src/memory/virtual/memory_handler.cpp').read_text())

    def test_native_host_actual_dll_refuses_wrong_executable_and_cleans_up(self):
        result=subprocess.run([str(CANDIDATE/'verification/candidate-host.exe'),
            str(CANDIDATE/'UltraPilot161ReadCandidate.dll')],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('init-failure cleanup',result.stdout)

    def test_map_evidence_is_sampled_and_not_called_full_game_verification(self):
        result=json.loads((CANDIDATE/'verification/result.json').read_text())
        proof=result['map_comparison']
        self.assertTrue(proof['all_sampled_match']);self.assertFalse(proof['full_world_verified'])
        self.assertEqual(len(proof['gps_nodes']),4);self.assertEqual(len(proof['prefabs']),3)
        self.assertTrue(all(p['error_m']==0 for p in proof['gps_nodes']))
        self.assertTrue(all(p['native_origin_118']!=p['dataset_origin'] and
            p['native_origin_120']==p['dataset_origin'] for p in proof['prefabs']))
        self.assertFalse(result['game_verified']);self.assertFalse(result['production_ready'])

    def test_real_acquisition_method_reproduces_original_crash_and_fixed_path(self):
        folder=CANDIDATE/'sentinel-regression-v2'
        result=json.loads((folder/'result.json').read_text())
        self.assertEqual(result['before_exception'],'C0000005')
        self.assertIsNone(result['after_exception']);self.assertTrue(result['nonempty_rejected'])
        self.assertEqual(hashlib.sha256((CANDIDATE/'src/processing/traffic.cpp').read_bytes()).hexdigest(),
            result['patched_source_sha256'])
        process=subprocess.run([str(folder/'sentinel.exe')],
            capture_output=True,text=True,timeout=20)
        self.assertEqual(process.returncode,0,process.stdout+process.stderr)
        self.assertIn('real before method faults 0xc0000005',process.stdout)
        self.assertIn('MATRIX: empty=15 nonempty_rejected=3 invalid_headers_rejected=2',process.stdout)
        self.assertEqual(result['empty_configurations'],15)
        self.assertEqual(result['invalid_header_rejections'],2)

    def test_empty_non_ai_list_never_traverses_a_sentinel(self):
        from tools.verify_oct17_native_records import method
        source=(CANDIDATE/'src/processing/traffic.cpp').read_text()
        actual=method(source,'void TrafficProcessor::get_truckersmp_traffic_data()')
        self.assertIn('if(list->size==0)return;',actual)
        self.assertNotIn('->begin',actual)
        self.assertNotIn('get_unit_descriptor',actual)
        self.assertIn('throw std::runtime_error("Candidate multiplayer motion layout unverified")',actual)

    def test_known_crashing_candidate_installer_is_revoked(self):
        source=(ROOT/'tools/install_oct24_sdk161_candidate.ps1').read_text()
        self.assertLess(source.index("throw 'Candidate-d is REVOKED"),source.index('[System.IO.File]::Copy'))


def test_map_comparison_rejects_original_origin_offset(tmp_path):
    module=load_module('verify161_map',ROOT/'tools/verify_oct24_sdk161_candidate.py')
    layout=dict(snapshot=dict(hypotheses=dict(prefabs=dict(items=[
        dict(uid=123,nodes=[1,2,0,0,0,0],origin_candidates=[0,1,0])]),
        gps=dict(first_items=[dict(uid=1,node_coords=[256,512,768])]))))
    (tmp_path/'europe-prefabs.json').write_text(json.dumps([
        dict(uid='7b',nodeUids=['1','2'],originNodeIndex=1)]))
    (tmp_path/'europe-nodes.json').write_text(json.dumps([dict(uid='1',x=1,z=2,y=3)]))
    assert module.compare_map(layout,tmp_path)['all_sampled_match']
    old=copy.deepcopy(layout);old['snapshot']['hypotheses']['prefabs']['items'][0]['origin_candidates'][1]=0
    import pytest
    with pytest.raises(ValueError,match='prefab ownership'):module.compare_map(old,tmp_path)
    bad=copy.deepcopy(layout);bad['snapshot']['hypotheses']['gps']['first_items'][0]['node_coords'][0]=512
    with pytest.raises(ValueError,match='GPS nodes'):module.compare_map(bad,tmp_path)
