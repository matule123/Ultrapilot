"""Production paths with source-timed native frames; no ETS2 consumption proof."""
import math
import os
import subprocess
import sys
from types import ModuleType
from types import SimpleNamespace

import pytest

from core.navigation.traffic_producer import capture_traffic
from tests.test_oct11_joint_regressions import joint  # noqa: F401
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_acc_following import capture


@pytest.fixture(autouse=True)
def frozen_production_baseline(monkeypatch):
    """Re-run the same new scenarios on committed production, no checkout edit."""
    if os.environ.get('ULTRAPILOT_OCT14_BASELINE') != '1':
        return
    from pathlib import Path
    import ast
    import core.engine as engine_module
    from core.engine import UltraPilotEngine
    root=Path(__file__).resolve().parents[1]
    def source(path):
        return subprocess.check_output(['git','show','b11777d:'+path],cwd=root).decode('utf-8')
    for name,path in (('core.acc_following','core/acc_following.py'),
                      ('core.service_brake_hold','core/service_brake_hold.py')):
        module=ModuleType(name)
        exec(compile(source(path),'frozen/'+path,'exec'),module.__dict__)
        monkeypatch.setitem(sys.modules,name,module)
    cls=next(n for n in ast.parse(source('core/engine.py')).body if isinstance(n,ast.ClassDef)
             and n.name=='UltraPilotEngine')
    for name in ('_route_lead_observation','_route_crossing_brake','_traffic_control_observation','_publish_traffic_control'):
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
        namespace=dict(engine_module.__dict__)
        exec(compile(ast.Module(body=[method],type_ignores=[]),'frozen/engine','exec'),namespace)
        monkeypatch.setattr(UltraPilotEngine,name,namespace[name])


def native_bytes(raw, clock, generation=1, frame=100000, lifecycle=73, flags=3, ego=(), anchor=None, ego_speed=10.):
    import struct
    from core.sdk.traffic_snapshot import LAYOUT
    return LAYOUT.pack(2*generation, 0x31545055, 1, LAYOUT.size, lifecycle,
        generation, frame, clock, flags, raw.moving, raw.parked, len(ego), 1 if ego else 0,
        struct.pack('<40f', *[v for body in ego for v in body], *([0.]*(40-10*len(ego)))),
        *(anchor or (ego[0][:3] if ego else (0.,0.,0.))), ego_speed, clock, 2*generation)


def timed_step(joint, actors, *, generation, speed=10., gear=4, z=15., lifecycle=73, ego=()):
    from core.sdk.traffic_snapshot import TrafficReader
    from core.longitudinal import context
    state, engine, ap, acc, policy, tick, _, _, _, _, clock = joint
    tick(gear=gear,speed=speed, z=z, pedals=False)
    truck = state.get('telemetry')['truck']
    raw = capture(actors, clock[0])
    reader = SimpleNamespace(_traffic_buf=raw.moving, _parked_buf=raw.parked,
        _timed_traffic_reader=TrafficReader())
    reader._timed_traffic_reader.buffer = native_bytes(raw, clock[0], generation,
        truck['sdkFrameTimeUs'], lifecycle, ego=ego,
        anchor=(truck['x'],truck['y'],truck['z']),ego_speed=speed)
    consumed = capture_traffic(reader, str(context(state)[1]), clock[0])
    following, brake = engine._traffic_control_observation(consumed, truck, context(state), [])
    engine._publish_traffic_control(truck, truck['_control_observation']['observed_at'],
        context(state), [], consumed, following, brake,
        dict(valid=False, candidate=None, reason='no head', coverage={}), None)
    policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033); engine._flush_controls()
    return following


def test_source_time_is_not_receiver_time_and_repeated_buffer_cannot_renew():
    from core.sdk.traffic_snapshot import TrafficReader
    from core.acc_following import observation
    raw = capture([dict(id=9, x=1., y=10., z=40., yaw=math.pi, speed=5.)], 100.)
    native = TrafficReader(); native.buffer = native_bytes(raw, 100.)
    reader = SimpleNamespace(_timed_traffic_reader=native)
    first = capture_traffic(reader, 'session', 100.02)
    second = capture_traffic(reader, 'session', 100.2)
    assert observation(first, 100.02)['source_timestamp'] == 100.
    assert observation(second, 100.2)['source_timestamp'] == 100.
    assert observation(second, 100.2)['source_sequence'] == 1
    stale = capture_traffic(reader, 'session', 100.501)
    assert observation(stale, 100.501)['status'] == 'stale_source_capture'


def test_observed_crossing_clearance_releases_original_stop_without_absence(joint):
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    actor = dict(id=1, x=-15., y=10., z=50., yaw=-math.pi/2, speed=5.)
    timed_step(joint, [actor], generation=1)
    hold = state.get('simple_auto_service_hold')
    assert hold and physical('abackward') > 0
    # The SAME observed body has crossed and now travels away. Missing/zero
    # demand is not the witness. Two new native acquisitions confirm release.
    # Advance the original body at its declared speed through consecutive
    # native acquisitions. The old fixture teleported 23 m in one 33 ms frame.
    for generation, x in enumerate((-15.+5./30.*i for i in range(1,170)), start=2):
        timed_step(joint, [dict(actor, x=x)], generation=generation)
    assert state.get('autopilot_active'), state.get('autopilot_intervention')
    assert state.get('simple_auto_service_hold') is None
    assert physical('abackward') == 0. and physical('aforward') > 0.


def test_native_leader_braking_changes_actual_acc_demand_before_gap_closes(joint):
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    lead = dict(id=29, x=2.25, y=10., z=47., yaw=math.pi, speed=10.)
    timed_step(joint, [lead], generation=1)
    baseline = state.get('longitudinal_acc')
    # Qualified finite differences, not the unqualified legacy acceleration slot.
    timed_step(joint, [dict(lead, z=47.1, speed=9.9)], generation=2)
    packet = state.get('longitudinal_acc')
    assert packet['leader_prediction']['basis'] == 'native_source_speed_difference'
    assert packet['constrained_speed_kmh'] < baseline['constrained_speed_kmh']
    assert packet['requested_acceleration_ms2'] < baseline['requested_acceleration_ms2']
    assert not (physical('aforward') > 0 and physical('abackward') > 0)


def test_speed_noise_acceleration_feedback_reduces_model_jerk_without_steady_regression():
    from tools.run_longitudinal_comfort_bench import CASES, classes, simulate
    case = next(c for c in CASES if c['name'] == 'steady_noise')
    before = simulate(case, classes('b11777d'))
    after = simulate(case)
    # Fixed BEFORE tuning: at least 20% reduction on the existing seeded noisy
    # case, plus unchanged Phase 7.2 speed/safety criteria. This is model jerk.
    assert after['p95_abs_model_jerk_mps3'] <= .8*before['p95_abs_model_jerk_mps3']
    assert after['steady_rms_kmh'] <= before['steady_rms_kmh']+.3
    assert after['steady_rms_kmh'] <= 1.
    assert after['steady_pedal_reversals'] <= before['steady_pedal_reversals']


@pytest.mark.parametrize('fault', ['missing', 'still_crossing', 'duplicate', 'reset'])
def test_uncertain_original_conflict_never_clears_hold(joint, fault):
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    actor = dict(id=1, x=-15., y=10., z=50., yaw=-math.pi/2, speed=5.)
    timed_step(joint, [actor], generation=1)
    for generation in range(2, 10):
        actors = [] if fault == 'missing' else [actor,dict(actor,x=9.)] if fault == 'duplicate' else [actor]
        timed_step(joint, actors, generation=generation, lifecycle=74 if fault == 'reset' else 73)
        assert physical('aforward') == 0.
    assert state.get('simple_auto_service_hold') or state.get('autopilot_intervention')


@pytest.mark.parametrize('fault', ['paused', 'future', 'torn', 'regression', 'changed_duplicate'])
def test_invalid_native_frames_do_not_renew_evidence(fault):
    from core.sdk.traffic_snapshot import TrafficReader, LAYOUT
    from core.acc_following import observation
    raw = capture([dict(id=9,x=1.,y=10.,z=40.,yaw=math.pi,speed=5.)], 100.)
    native = TrafficReader(); native.buffer = native_bytes(raw, 100., generation=2)
    reader=SimpleNamespace(_timed_traffic_reader=native)
    assert observation(capture_traffic(reader,'session',100.),100.)['status']=='observed'
    if fault == 'changed_duplicate':
        altered=capture([dict(id=9,x=2.,y=10.,z=40.,yaw=math.pi,speed=5.)],100.)
        native.buffer=native_bytes(altered,100.,generation=2)
    else:
        data=list(LAYOUT.unpack(native.buffer))
        if fault=='paused':data[8]=2
        elif fault=='future':data[7]=100.1
        elif fault=='torn':data[-1]+=2
        else:data[5]-=1
        native.buffer=LAYOUT.pack(*data)
    invalid=observation(capture_traffic(reader,'session',100.),100.)
    assert invalid['status'] not in ('observed','empty_unproven_coverage')


def test_native_ego_trailer_predicted_contact_reaches_emergency_backend(joint):
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    # Tractor is laterally clear. The actual observed ego trailer box is on a
    # contact path that centreline-only lead/crossing selection does not see.
    ego = [(2.25,10.,15.,0.,0.,1.,0.,2.5,4.,6.),
           (2.25,10.,6.,0.,0.,1.,0.,4.,4.,12.)]
    car=dict(id=77,x=5.,y=10.,z=17.,yaw=math.pi,speed=0.)
    following=timed_step(joint,[car],generation=1,ego=ego)
    body=following['body_prediction']
    assert body['conflicts'] and body['conflicts'][0]['predicted_contact_s'] <= 1.
    assert physical('aforward') == 0. and physical('abackward') == 1.
    assert not body['complete_envelope_verified']


def test_swept_box_contact_between_samples_and_separate_elevation():
    from core.acc_body_prediction import contact_interval
    a=dict(x=0.,y=0.,z=0.,yaw=0.,dimensions_whl=(2.,2.,4.))
    b=dict(a,x=-10.)
    assert contact_interval(a,b,(0.,0.),(100.,0.),.25)==pytest.approx(.08)
    assert contact_interval(a,dict(b,y=5.),(0.,0.),(100.,0.),.25) is None


def test_native_crossing_stop_wait_restart_and_second_cycle_without_n(joint):
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    activation=state.get('autopilot_failure_epoch')
    mode=state.get('ets2_transmission_mode')['mode']
    generation=0
    for cycle in range(2):
        actor=dict(id=91+cycle,x=8.,y=10.,z=20.,yaw=math.pi/2,speed=2.)
        for gear,speed in ((4,4.),(4,2.),(4,.5),(0,.2),(0,.039),(0,0.)):
            generation+=1
            timed_step(joint,[actor],generation=generation,gear=4 if mode==3 else gear,speed=speed)
            assert state.get('autopilot_active'),state.get('autopilot_intervention')
            assert physical('aforward')==0. and physical('abackward')>0.
        holding_start=len(writes)
        for _ in range(3):
            generation+=1
            timed_step(joint,[actor],generation=generation,gear=4 if mode==3 else 0,speed=0.)
        assert not any(ch=='abackward' and value==0. for _,ch,value in writes[holding_start:])
        # The original body is still present, now left of the reference and
        # moving farther away. No actor disappearance is substituted.
        for i in range(1,280):
            generation+=1
            # Gear/movement follow a physical launch write, never a scripted
            # success while the output still owns brake hold.
            launched=physical('aforward')>0. and physical('abackward')==0.
            gear=4 if mode==3 or launched else 0
            speed=.2 if launched else 0.
            # Native motion must remain continuous all the way across. A
            # new pair after the former 16 m teleport is not original clearance.
            timed_step(joint,[dict(actor,x=8.-i*2./30.)],generation=generation,gear=gear,speed=speed)
            assert state.get('autopilot_active'),state.get('autopilot_intervention')
        assert state.get('autopilot_failure_epoch')==activation
        import json
        assert state.get('simple_auto_service_hold') is None, json.dumps({
            k:state.get('simple_auto_service_hold').get(k) for k in
            ('traffic_lock','other_stop_sources','restart_blocker','traffic_clear_candidate')})
        assert physical('abackward')==0. and physical('aforward')>0.
        assert all(not(ch=='aforward' and value>0 and physical('abackward')>0)
                   for _,ch,value in writes[-2:])


def test_native_decision_fields_survive_existing_incident_codec(joint,tmp_path):
    from core.navigation.longitudinal_diagnostics import PedalJournal
    from core.steering_replay import SteeringReplayBuffer,inspect_replay
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    engine.controller._pedal_journal=PedalJournal()
    lead=dict(id=29,x=2.25,y=10.,z=47.,yaw=math.pi,speed=10.)
    timed_step(joint,[lead],generation=1)
    timed_step(joint,[dict(lead,z=47.1,speed=9.9)],generation=2)
    expected=state.get('longitudinal_acc')['leader_prediction']
    path=SteeringReplayBuffer(2).export(tmp_path,reason='manual_disable',
        longitudinal=engine.controller._pedal_journal.snapshot(expanded=False,include_history=True))
    result=inspect_replay(path)
    assert result['integrity_valid']
    def objects(value):
        if isinstance(value,dict):
            yield value
            for item in value.values():yield from objects(item)
        elif isinstance(value,list):
            for item in value:yield from objects(item)
    assert any(v==expected for v in objects(result['replay']['longitudinal']))
    assert not result['replay']['longitudinal']['game_consumption_verified']


def test_existing_combined_traffic_producer_retains_actual_native_origin():
    from core.sdk.traffic_snapshot import TrafficReader
    from core.navigation.traffic_producer import LegacyTrafficProducer
    raw=capture([dict(id=9,x=1.,y=10.,z=40.,yaw=math.pi,speed=5.)],100.)
    native=TrafficReader();native.buffer=native_bytes(raw,100.)
    value=capture_traffic(SimpleNamespace(_timed_traffic_reader=native),'session',100.02)
    producer=LegacyTrafficProducer()
    snapshot=producer.produce(value,100.02)
    assert snapshot.sensor_time_s==100. and snapshot.receiver_time_s==100.02
    assert snapshot.producer_generation==1 and snapshot.producer_frame_us==100000
    assert snapshot.producer_lifecycle==73
    assert not snapshot.complete and snapshot.sensor_range_m is None
