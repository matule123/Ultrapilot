"""17 October: real native methods/reader and production physical outputs."""
import math
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.longitudinal import context
from core.navigation.traffic_producer import capture_traffic
from core.sdk.traffic_snapshot import TrafficReader
from core.acc_following import observation
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.lifecycle.test_joint_regressions import joint  # noqa: F401
from tests.signals.test_signal_timing import timing_flow
from tests.lifecycle.test_longitudinal_completion import native_bytes
from tests.test_acc_following import capture

ROOT=Path(__file__).resolve().parents[2]
PROBE=ROOT/os.environ.get('UP_OCT17_NATIVE_PARKED','docs/steering-audit/oct17-joint-lifecycle/native-candidate-b-probe/parked.bin')


def test_compiled_native_parent_trailer_records_are_distinct():
    from core.sdk.ets2la_data import _PARKED_FMT
    import struct
    values=struct.unpack(_PARKED_FMT,PROBE.read_bytes())
    records=[values[i*12:(i+1)*12] for i in range(40) if values[i*12]!=0]
    assert len(records)==3
    assert len({r[10] for r in records})==3, 'Producer repeated parent pointer instead of trailer'
    assert sorted(r[2] for r in records)==[120.,125.,130.]


@pytest.mark.parametrize('speed',[0.,1.,10.])
def test_native_parked_chain_cannot_blind_current_box_conflict(joint,speed):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    tick(gear=4,speed=speed,z=15.,pedals=False)
    truck=state.get('telemetry')['truck']
    # Moving vehicle approaching our ACTUAL body, not an invented ego launch.
    hazard=dict(id=21,x=-3.,y=10.,z=15.+speed*.75,yaw=-math.pi/2,speed=4.)
    raw=capture([hazard],clock[0])
    raw=type(raw)(raw.session,raw.observed_at,raw.moving,PROBE.read_bytes(),True)
    reader=SimpleNamespace(_timed_traffic_reader=TrafficReader())
    reader._timed_traffic_reader.buffer=native_bytes(raw,clock[0],1,truck['sdkFrameTimeUs'],
        ego=[(2.25,10.,15.,0.,0.,1.,0.,2.5,4.,6.)],anchor=(2.25,10.,15.),ego_speed=speed)
    consumed=capture_traffic(reader,str(context(state)[1]),clock[0])
    decoded=observation(consumed,clock[0])
    following,brake=engine._traffic_control_observation(consumed,truck,context(state),[])
    assert brake==1., (decoded['status'],following)
    engine._publish_traffic_control(truck,truck['_control_observation']['observed_at'],context(state),
        [],consumed,following,brake,dict(valid=False,candidate=None,reason='no head',coverage={}),None)
    policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
    assert physical('aforward')==0.
    if speed>.05:
        assert physical('abackward')>0.
    # At zero, simple-auto must not seed an unsafe fresh brake edge; takeover
    # is acceptable. The conflict MUST still exist upstream, unlike baseline.
    assert not following.get('coverage_confirmed')


def test_candidate_native_abi_source_scope_and_exports():
    import ctypes
    import hashlib
    import json
    candidate=ROOT/'docs/steering-audit/oct17-joint-lifecycle/native-candidate-b'
    receipt=json.loads((candidate/'build-receipt.json').read_text())
    original=ROOT/'docs/steering-audit/oct14-completion/native-candidate-c'
    before=json.loads((original/'build-receipt.json').read_text())
    changed=[]
    for name,digest in receipt['files'].items():
        assert hashlib.sha256((candidate/name).read_bytes()).hexdigest()==digest
        if before['files'].get(name)!=digest:changed.append(name.replace('\\','/'))
    assert set(changed)=={'ets2la_plugin.dll','src/version.hpp','src/processing/traffic.cpp'}
    assert receipt['schema']==3 and receipt['traffic_schema']==1 and receipt['abi_changed'] is False
    dll=ctypes.WinDLL(str(candidate/'ets2la_plugin.dll'))
    try:assert dll.scs_telemetry_init and dll.scs_telemetry_shutdown
    finally:
        kernel=ctypes.WinDLL('kernel32');kernel.FreeLibrary.argtypes=[ctypes.c_void_p]
        assert kernel.FreeLibrary(dll._handle)


@pytest.mark.parametrize('enabled,rpm',[(True,1200.),(False,0.),(None,None),(None,float('nan'))])
def test_powertrain_optional_values_reuse_consumed_snapshot_and_export(tmp_path,enabled,rpm):
    from core.telemetry import powertrain_diagnostic_observation
    from core.navigation.longitudinal_diagnostics import PedalJournal,local_source_snapshot
    from core.steering_replay import SteeringReplayBuffer,inspect_replay
    observation=powertrain_diagnostic_observation({'engineEnabled':enabled},{'engineRpm':rpm})
    assert observation['engine_enabled']==enabled
    assert observation['engine_rpm']==(None if isinstance(rpm,float) and math.isnan(rpm) else rpm)
    truck=dict(speed=.1,gear=4,sdkFrameTimeUs=100,
        _control_observation=dict(sdk_frame_us=100,observed_at=100.,valid=True),powertrainObservation=observation)
    journal=PedalJournal();journal.enabled=True;journal.begin_decision()
    source=local_source_snapshot(truck)
    source.update(phase='active',selected=dict(source='acc',throttle=.2,brake=0.))
    journal.bind(source)
    truck['powertrainObservation']['engine_rpm']=999.
    journal.record('throttle',.2,100.,100.001,'SCS_SDK',{'status':'MAPPING_WRITE_RETURNED'})
    journal.finish_decision(100.002)
    snapshot=journal.snapshot(include_history=True)
    path=SteeringReplayBuffer(2).export(tmp_path,reason='automatic_disable',longitudinal=snapshot)
    result=inspect_replay(path)
    assert result['integrity_valid'] and not result['confirmed']
    expected=None if isinstance(rpm,float) and math.isnan(rpm) else rpm
    assert result['replay']['longitudinal']['events'][0]['source']['powertrain_observation']['engine_rpm']==expected
    assert result['replay']['longitudinal']['decision_history']['regular_samples'][0]['powertrain_observation']['engine_rpm']==expected


