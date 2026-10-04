"""Compiled real sidecar publication and load/exports, isolated from ETS2.

Build artifacts are intentionally ignored, not a requirement for the full Python
suite. Missing compiled probe is a skip, never evidence of a successful DLL test.
"""
import ctypes
import os
from pathlib import Path
import subprocess
import time

import pytest

from core.sdk.signal_snapshot import LAYOUT, decode, RouteSignalSelector

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'docs/steering-audit/signal-plugin-20261003'


@pytest.mark.skipif(os.name!='nt' or not (AUDIT/'signal_probe.exe').exists(), reason='compiled Windows probe unavailable')
def test_compiled_publisher_lifecycle_and_qpc_match_python(tmp_path):
    before=time.monotonic()
    subprocess.run([str(AUDIT/'signal_probe.exe'),str(tmp_path)],check=True,timeout=10)
    after=time.monotonic()
    def read(name):
        raw=(tmp_path/(name+'.bin')).read_bytes()
        stamp=LAYOUT.unpack(raw)[7]
        assert before <= stamp <= after  # same QPC domain, no clock conversion
        return raw,decode(raw,stamp)
    first,red=read('active')
    repeated,again=read('repeat')
    assert first==repeated and red==again and red['valid']
    _,green=read('next')
    assert green['valid'] and green['generation']>red['generation']
    assert red['lights'][0]['color']=='red' and green['lights'][0]['color']=='green'
    selector=RouteSignalSelector()
    selected=selector.select(green,[[0.,10.,0.],[0.,10.,-50.]],'route',('session',),
        dict(x=0.,y=10.,z=0.,rotation=0.),0.)
    assert selected['valid'] and selected['candidate']['id']==19
    for stage in ('paused','incomplete','shutdown'):
        assert not read(stage)[1]['valid']
    reset=read('reset')[1]
    assert reset['valid'] and reset['lifecycle']!=red['lifecycle']


@pytest.mark.skipif(os.name!='nt' or not (AUDIT/'candidate-e/ets2la_plugin.dll').exists(), reason='compiled candidate unavailable')
def test_candidate_loads_required_telemetry_entrypoints_and_unloads():
    # Deliberately NOT scs_telemetry_init: game pattern scans require ETS2.
    candidate=AUDIT/'candidate-e/ets2la_plugin.dll'
    dll=ctypes.WinDLL(str(candidate))
    assert dll.scs_telemetry_init and dll.scs_telemetry_shutdown
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.FreeLibrary.argtypes=[ctypes.c_void_p]
    assert kernel.FreeLibrary(dll._handle)
