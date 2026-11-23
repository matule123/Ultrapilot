import os
import subprocess
import time
from pathlib import Path

import pytest

from core.sdk.signal_snapshot import LAYOUT,SCOPED_LAYOUT,OWNER_LAYOUT,decode
from tests.signals.test_signal_coverage import signal_bytes

ROOT=Path(__file__).resolve().parents[1]
PROBE=ROOT/'docs/steering-audit/signal-plugin-20261009/scope_probe.exe'


def scoped(now=1000.,*,owner=900,nodes=(11,12,13),origin=2,flags=1):
    legacy=list(LAYOUT.unpack(
        signal_bytes(now,1,100,(0.,14.,-5.,3.141592653589793,19,2))))
    legacy[1:4]=[0x33535055,3,SCOPED_LAYOUT.size]
    values=(owner,*nodes,*([0]*(6-len(nodes))),origin,4,flags)
    owners=OWNER_LAYOUT.pack(*values)+bytes(2880-OWNER_LAYOUT.size)
    return SCOPED_LAYOUT.pack(*legacy[:-1],owners,legacy[-1])


def test_scoped_decode_binds_owner_to_original_row_without_retiming():
    r=decode(scoped(),1000.1)
    assert r['valid'] and r['schema']==3 and r['observed_at']==1000.
    h=r['lights'][0]
    assert h['ownership_valid'] and h['owner_prefab_uid']==900
    assert h['owner_node_uids']==[11,12,13] and h['owner_origin_index']==2


@pytest.mark.parametrize('fault',['time','torn','flags','owner','nodes'])
def test_scoped_invalidity_never_manufactures_binding(fault):
    raw=scoped(now=999. if fault=='time' else 1000.,flags=0 if fault=='flags' else 1,
               owner=0 if fault=='owner' else 900,nodes=(11,11,13) if fault=='nodes' else (11,12,13))
    if fault=='torn':raw=raw[:-4]+bytes(4)
    r=decode(raw,1000.1)
    assert not r['valid'] if fault in ('time','torn') else not r['lights'][0]['ownership_valid']


@pytest.mark.skipif(os.name!='nt' or not PROBE.exists(),reason='scoped native probe not built')
def test_compiled_dual_schema_publication_is_consistent(tmp_path):
    subprocess.run([str(PROBE),str(tmp_path)],check=True,timeout=10)
    def read(name,version):
        raw=(tmp_path/f'{name}-v{version}.bin').read_bytes()
        stamp=SCOPED_LAYOUT.unpack(raw)[7] if version==3 else LAYOUT.unpack(raw)[7]
        return raw,decode(raw,stamp)
    a,red=read('red',3);b,repeat=read('repeat',3)
    assert a==b and red['valid'] and red==repeat
    assert red['lights'][0]['owner_prefab_uid']==900
    assert red['lights'][0]['color']=='red' and read('green',3)[1]['lights'][0]['color']=='green'
    assert red['observed_at']==read('red',2)[1]['observed_at']
    assert not read('paused',3)[1]['valid']
    assert read('reset',3)[1]['lifecycle']!=red['lifecycle']


@pytest.mark.skipif(os.name!='nt',reason='Windows plugin candidate')
def test_candidate_exports_scs_entrypoints_without_initializing_game_plugin():
    import ctypes
    candidate=PROBE.parent/'scoped-candidate/ets2la_plugin.dll'
    if not candidate.exists():pytest.skip('scoped candidate not built')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LoadLibraryW.argtypes=[ctypes.c_wchar_p];kernel.LoadLibraryW.restype=ctypes.c_void_p
    kernel.GetProcAddress.argtypes=[ctypes.c_void_p,ctypes.c_char_p];kernel.GetProcAddress.restype=ctypes.c_void_p
    kernel.FreeLibrary.argtypes=[ctypes.c_void_p];kernel.FreeLibrary.restype=ctypes.c_int
    handle=kernel.LoadLibraryW(str(candidate))
    assert handle,ctypes.get_last_error()
    try:
        for name in (b'scs_telemetry_init',b'scs_telemetry_shutdown'):
            assert kernel.GetProcAddress(handle,name)
    finally:assert kernel.FreeLibrary(handle)
