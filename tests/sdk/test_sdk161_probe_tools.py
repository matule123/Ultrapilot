import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

import pefile

ROOT=Path(__file__).resolve().parents[2]
AUDIT=ROOT/'docs/steering-audit/oct22-sdk161'


class Passive161ProbeTests(unittest.TestCase):
    def test_pattern_parser_requires_full_pattern_and_counts_repeated_matches(self):
        spec=importlib.util.spec_from_file_location('sdk161_patterns',ROOT/'tools/audit_oct22_sdk161_patterns.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        pattern=module.compile_pattern('48 8b ? 01 02 ff')
        self.assertEqual(len(list(pattern.finditer(bytes.fromhex('48 8b 00 01 02 ff 48 8b 0a 01 02 ff')))),2)
        with self.assertRaises(ValueError):module.compile_pattern('48 8b')

    def test_public_inputs_retain_pinned_hashes(self):
        root=AUDIT/'inputs';receipt=json.loads((root/'receipt.json').read_text())
        for row in receipt['artifacts']:
            with self.subTest(path=row['path']):
                data=(root/row['path']).read_bytes();self.assertEqual(hashlib.sha256(data).hexdigest(),row['sha256'])
        self.assertFalse(receipt['executed']);self.assertFalse(receipt['installed'])

    def test_static_audit_does_not_certify_ambiguous_signatures_or_layouts(self):
        receipt=json.loads((AUDIT/'pattern-audit.json').read_text())
        self.assertFalse(receipt['dynamic_layouts_verified'])
        self.assertTrue(receipt['public_source_declares_160'])
        rows=receipt['official_binaries']['official161']['patterns']
        self.assertEqual(len(rows),10)
        self.assertEqual(sum(len(r['executable_rvas'])>1 for r in rows),2)
        self.assertFalse(receipt['official160_text_equals_161'])

    def test_dll_exports_telemetry_only_and_no_control_injection_apis(self):
        dll=AUDIT/'read-only-probe/UltraPilot161ReadOnlyProbe.dll';data=dll.read_bytes();pe=pefile.PE(data=data)
        self.assertEqual(pe.FILE_HEADER.Machine,0x8664)
        names={r.name.decode() for r in pe.DIRECTORY_ENTRY_EXPORT.symbols}
        self.assertEqual(names,{'scs_telemetry_init','scs_telemetry_shutdown'})
        imports={r.name.decode() for group in pe.DIRECTORY_ENTRY_IMPORT for r in group.imports if r.name}
        self.assertFalse(imports&{'WriteProcessMemory','CreateRemoteThread','SendInput','SetWindowsHookExW'})
        # MSVC's static CRT imports VirtualProtect itself. Import presence is
        # not proof that probe code calls it; forbid it in the probe source.
        source=(ROOT/'tools/sdk161_probe/probe.cpp').read_text()
        for api in ('VirtualProtect','WriteProcessMemory','SendInput','override_inputs','set_brake_input','set_throttle_input'):
            self.assertNotIn(api,source)
        self.assertIn('CreateFileMappingW',imports)
        for name in ('ETS2LAPluginInput','SCSControls','UltraPilotTrafficSnapshot','UltraPilotSignalSnapshot'):
            self.assertNotIn(name.encode(),data);self.assertNotIn(name.encode('utf-16le'),data)

    def test_build_receipt_matches_and_does_not_claim_production_ready(self):
        folder=AUDIT/'read-only-probe';receipt=json.loads((folder/'receipt.json').read_text())
        self.assertEqual(hashlib.sha256((folder/'UltraPilot161ReadOnlyProbe.dll').read_bytes()).hexdigest(),receipt['dll_sha256'])
        self.assertEqual(hashlib.sha256((ROOT/'tools/sdk161_probe/probe.cpp').read_bytes()).hexdigest(),receipt['source_sha256'])
        self.assertTrue(receipt['read_only'])
        for flag in ('production_ready','native_layouts_verified','game_verified','deployed'):self.assertFalse(receipt[flag])

    def test_actual_native_callbacks_restart_pause_and_invalid_inputs(self):
        result=subprocess.run([str(AUDIT/'read-only-probe/test_probe.exe')],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS:',result.stdout)

    def test_collector_only_opens_existing_mapping_read_only(self):
        text=(ROOT/'tools/collect_oct22_sdk161_probe.py').read_text()
        self.assertIn('OpenFileMappingW(4,False',text)
        self.assertIn('MapViewOfFile(handle,4,',text)
        self.assertNotIn('CreateFileMapping',text)
        self.assertNotIn('FILE_MAP_WRITE',text)
