"""Actual compiled native publication and new DLL ABI; no game initialization."""
import ctypes
import os
from pathlib import Path
import subprocess
import time

import pytest
from core.sdk.traffic_snapshot import LAYOUT, decode

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'docs/steering-audit/oct14-completion'


@pytest.mark.skipif(os.name!='nt' or not (AUDIT/'traffic_probe.exe').exists(),reason='compiled traffic probe unavailable')
def test_native_qpc_lifecycle_repeat_speed_frame_and_wire(tmp_path):
    before=time.monotonic()
    subprocess.run([str(AUDIT/'traffic_probe.exe'),str(tmp_path)],check=True,timeout=10)
    after=time.monotonic()
    def read(name):
        raw=(tmp_path/(name+'.bin')).read_bytes()
        stamp=LAYOUT.unpack(raw)[7]
        assert before<=stamp<=after
        return raw,decode(raw,stamp)
    first,active=read('active'); repeated,repeat=read('repeat')
    assert first==repeated and active==repeat and active['valid']
    _,next_=read('next')
    assert next_['generation']>active['generation'] and next_['frame_us']>active['frame_us']
    assert next_['ego_speed_mps']==9. and next_['ego_body_flags']==1
    assert next_['ego_anchor']==(12.,10.,20.)
    assert not read('paused')[1]['valid']
    assert read('reset')[1]['lifecycle']!=active['lifecycle']
    missing=read('missing_speed')[1]
    assert missing['valid'] and missing['ego_body_flags']==0  # never reuse old speed as this frame


@pytest.mark.skipif(os.name!='nt' or not (AUDIT/'native-candidate-c/ets2la_plugin.dll').exists(),reason='compiled candidate unavailable')
def test_native_candidate_telemetry_exports_load_without_game_init():
    dll=ctypes.WinDLL(str(AUDIT/'native-candidate-c/ets2la_plugin.dll'))
    assert dll.scs_telemetry_init and dll.scs_telemetry_shutdown
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.FreeLibrary.argtypes=[ctypes.c_void_p]
    assert kernel.FreeLibrary(dll._handle)
