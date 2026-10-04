"""Real reader/selector/arbitration/AP/Engine/Controller; no live game.

The simple gearbox plant follows manual-pedal observation, not SDK consumption.
"""
import io
import math
import struct

import pytest

from core.sdk.signal_snapshot import LAYOUT, decode, SignalReader, RouteSignalSelector
from core.longitudinal import context, publish
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_rolling_longitudinal_authority import rolling  # noqa: F401
from tests.test_roundabout_intervention_reporting import started, pedal
from tests.test_signal_clearance_source_contract import semaphore_buffer


def source_bytes(clock, generation, frame, color=2, lifecycle=11, flags=3, signal_id=19):
    seq = generation*2
    return LAYOUT.pack(seq, 0x32535055, 2, LAYOUT.size, lifecycle,
        generation, frame, clock, flags, 1, bytes(semaphore_buffer(state=color, signal_id=signal_id)), seq)


def signal_tick(values, generation, color=2, gear=0, speed=0., dt=.1, **fault):
    state, truck, engine, ap, update, n, clock, acc, collected = values
    update(gear, speed, dt=dt)
    packet = state.get('nav_steering_debug')
    packet['tracking_progress_m'] = 0.
    state.set('nav_steering_debug', packet)
    engine._signal_reader.buffer = source_bytes(clock[0]+fault.pop('age', 0),
        generation, truck['sdkFrameTimeUs'], color=color, **fault)
    signal = engine._signal_observation(state.get('telemetry')['truck'], context(state))
    publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0.,
        light_brake=engine._light_brake(signal.get('candidate')), light=signal.get('candidate'),
        signal=signal, following=None)
    publish(state, state.get('telemetry')['truck'], 'acc', throttle=.4 if color == 8 else 0.,
        brake=0. if color == 8 else .4, emergency=False, control_target_kmh=50. if color == 8 else 0.)
    ap.on_tick(dt)
    engine._flush_controls()
    return signal


def signal_stop(flow, mode=0):
    values = started(flow, mode=mode)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    engine._signal_reader = SignalReader()
    engine._signal_selector = RouteSignalSelector()
    engine._signal_route_token = None
    lane = state.get('lane_trajectory')
    lane['points'] = [[0.,10.,0.],[0.,10.,-50.]]
    state.set('lane_trajectory', lane)
    state.set('lane_trajectory_publication_token', 'signal-test-publication')
    lane_id=dict(road_uid=11, direction=1, lane_index=0)
    match=state.get('lane_match');match['active_lane_id']=lane_id;state.set('lane_match',match)
    from core.navigation.lane_model import LaneId
    packet=state.get('nav_steering_debug');packet['authority_lane_id']=LaneId(**lane_id).sort_key();state.set('nav_steering_debug',packet)
    writes = []
    writer = engine.controller.scs
    class Buffer(io.BytesIO):
        def write(self, data):
            channel = next((k for k in ('aforward','abackward','parkingbrake')
                            if writer._offsets[k] == self.tell()), None)
            if channel:
                writes.append((clock[0], channel, struct.unpack('f',data)[0] if len(data)==4 else bytes(data)))
            return super().write(data)
    writer._buf = Buffer(writer._buf.getvalue())
    for gen, speed in enumerate((5.,2.,.2,0.,0.), 1):
        signal = signal_tick(values, gen, gear=8 if speed or mode == 3 else 0, speed=speed)
        assert signal['valid'], signal
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert pedal(engine,'abackward') > 0 and pedal(engine,'aforward') == 0
    assert state.get('simple_auto_service_hold')['automatic_restart_supported']
    assert state.get('simple_auto_service_hold')['restart_blocker']=='locked signal is not green'
    return values, writes


@pytest.mark.parametrize('mode', [0, 3])
def test_new_green_resumes_through_existing_bounded_launch_without_another_n(flow, mode):
    values, writes = signal_stop(flow, mode)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    token = state.get('simple_auto_activation_token')
    signal_tick(values, 6, color=8, gear=8 if mode == 3 else 0)
    assert pedal(engine,'abackward') > 0 and pedal(engine,'aforward') == 0
    signal_tick(values, 7, color=8, dt=.12, gear=8 if mode == 3 else 0)
    signal_tick(values, 8, color=8, gear=8 if mode == 3 else 0)
    if mode == 0:
        assert pedal(engine,'aforward') > 0, (state.get('navigation_status'), writes)
    else:
        # Real automatic retains its existing confirmation tick with zero
        # power; only the next valid Plugin command can propel the vehicle.
        assert pedal(engine,'aforward') == 0
    for generation in range(9,14):
        signal_tick(values, generation, color=8, gear=8, speed=.3)
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert state.get('simple_auto_activation_token') == token
    assert pedal(engine,'aforward') > 0 and pedal(engine,'abackward') == 0
    assert not any(channel == 'parkingbrake' for _,channel,_ in writes)


@pytest.mark.parametrize('fault', ['stale_green','future_green','same_generation',
    'reset','paused','different_id','orange','missing','other_brake','lost_following'])
def test_unproven_clearance_keeps_positive_continuous_brake(flow, fault):
    values, writes = signal_stop(flow)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    count = len(writes)
    for generation in range(6, 12):
        kw = {}; color=8; gen=generation
        if fault=='stale_green': kw['age']=-.501
        if fault=='future_green': kw['age']=.01
        if fault=='same_generation': gen=1
        if fault=='reset': kw['lifecycle']=12
        if fault=='paused': kw['flags']=0
        if fault=='different_id': kw['signal_id']=20
        if fault=='orange': color=4
        if fault=='missing': kw['signal_id']=20
        if fault in ('other_brake','lost_following'):
            update(0,0.,dt=.1)
            data=source_bytes(clock[0], gen, truck['sdkFrameTimeUs'], color=8)
            engine._signal_reader.buffer=data
            signal=engine._signal_observation(state.get('telemetry')['truck'], context(state))
            publish(state,state.get('telemetry')['truck'],'traffic',traffic_brake=0.,light_brake=0.,signal=signal)
            publish(state,state.get('telemetry')['truck'],'acc', throttle=0.,brake=.2,
                    following_status='source_lost' if fault=='lost_following' else None)
            ap.on_tick(.1);engine._flush_controls()
        else:
            signal_tick(values, gen, color=color, **kw)
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
        assert pedal(engine,'aforward') == 0 and pedal(engine,'abackward') > 0
    assert all(value > 0 for _, channel, value in writes[count:] if channel=='abackward')


def test_short_green_flicker_requires_new_stable_acquisitions(flow):
    values, writes=signal_stop(flow)
    signal_tick(values,6,color=8)
    signal_tick(values,7,color=2)
    signal_tick(values,8,color=8)
    engine=values[2]
    assert pedal(engine,'abackward') > 0
    signal_tick(values,9,color=8,dt=.12)
    assert pedal(engine,'aforward') > 0


@pytest.mark.parametrize('fault',['reverse','backward','stale_sdk','manual','identity','backend'])
def test_cancelled_restart_never_recovers_automatically(flow,fault):
    values,writes=signal_stop(flow)
    state,truck,engine,ap,update,n,clock,acc,collected=values
    signal_tick(values,6,color=8)
    signal_tick(values,7,color=8,dt=.12)
    if fault=='manual': n()
    elif fault=='identity':
        lane=state.get('lane_trajectory');lane['revision']+=1;state.set('lane_trajectory',lane)
    elif fault=='backend': engine.controller.scs.connected=False
    elif fault=='stale_sdk': clock[0]+=.501
    else: update(-1 if fault=='reverse' else 0, -.3 if fault=='backward' else 0.)
    count=len(writes)
    engine._flush_controls()
    assert not state.get('autopilot_active'),state.get('navigation_status')
    assert engine._drive_engagement is None
    assert all(value==0 for _,channel,value in writes[count:] if channel=='aforward')


def test_source_lost_following_is_latched_even_after_it_disappears(flow):
    values,writes=signal_stop(flow)
    state,truck,engine,ap,update,n,clock,acc,collected=values
    update(0,0.,dt=.1)
    publish(state,state.get('telemetry')['truck'],'acc',throttle=0.,brake=.4,following_status='source_lost')
    ap.on_tick(.1);engine._flush_controls()
    for gen in range(6,12): signal_tick(values,gen,color=8)
    assert pedal(engine,'aforward')==0 and pedal(engine,'abackward')>0
    assert state.get('simple_auto_service_hold')['other_stop_unverified']


def test_real_auto_zero_ratio_waits_for_drive_before_power(flow):
    values,writes=signal_stop(flow,3)
    state,truck,engine,ap,update,n,clock,acc,collected=values
    signal_tick(values,6,color=8,gear=0)
    signal_tick(values,7,color=8,gear=0,dt=.12)
    signal_tick(values,8,color=8,gear=0)
    assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
    assert pedal(engine,'aforward')==0
    signal_tick(values,9,color=8,gear=8)
    signal_tick(values,10,color=8,gear=8,speed=.3)
    assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
    assert pedal(engine,'aforward')>0 and pedal(engine,'abackward')==0


def test_reverse_arriving_during_brake_release_prevents_any_positive_throttle(flow):
    values,writes=signal_stop(flow)
    state,truck,engine,ap,update,n,clock,acc,collected=values
    signal_tick(values,6,color=8)
    original=engine.controller.set_brake
    fired=[]
    def write(value):
        original(value)
        if value==0 and not fired:
            fired.append(True)
            update(-1,0.,dt=.001)
    engine.controller.set_brake=write
    count=len(writes)
    signal_tick(values,7,color=8,dt=.12)
    assert fired and not state.get('autopilot_active')
    assert all(value==0 for _,channel,value in writes[count:] if channel=='aforward')


def test_locked_head_is_not_replaced_by_a_new_closer_head_or_list_order(flow):
    values,writes=signal_stop(flow)
    state,truck,engine,ap,update,n,clock,acc,collected=values
    for generation in (6,7):
        update(0,0.,dt=.12)
        raw=list(LAYOUT.unpack(source_bytes(clock[0],generation,truck['sdkFrameTimeUs'])))
        first=bytes(semaphore_buffer(state=8,signal_id=20,z=-1.))[:48]
        locked=bytes(semaphore_buffer(state=2,signal_id=19))[:48]
        raw[9]=2;raw[10]=(first+locked if generation==6 else locked+first)+bytes(1920-96)
        engine._signal_reader.buffer=LAYOUT.pack(*raw)
        signal=engine._signal_observation(state.get('telemetry')['truck'],context(state))
        assert signal['valid'] and signal['candidate']['id']==19
        publish(state,state.get('telemetry')['truck'],'traffic',traffic_brake=0.,light_brake=1.,signal=signal)
        publish(state,state.get('telemetry')['truck'],'acc',throttle=0.,brake=.4)
        ap.on_tick(.12);engine._flush_controls()
        assert pedal(engine,'abackward')>0 and pedal(engine,'aforward')==0


def test_missing_lane_id_or_publication_never_proves_green_relevance(flow):
    values,writes=signal_stop(flow)
    state,truck,engine,ap,update,n,clock,acc,collected=values
    state.set('lane_trajectory_publication_token',None)
    signal=engine._signal_observation(state.get('telemetry')['truck'],context(state))
    assert not signal['valid'] and signal['candidate'] is None


def test_reader_rejects_regressing_generation_and_in_place_retimestamping(flow):
    clock=flow[-1]
    reader=SignalReader();reader.buffer=source_bytes(clock[0],2,100)
    assert reader.read()['valid']
    reader.buffer=source_bytes(clock[0],1,99)
    assert not reader.read()['valid']
    clock[0]+=.01
    reader.buffer=source_bytes(clock[0],2,100)
    assert not reader.read()['valid']


def test_source_expiring_during_clearance_ipc_cannot_release_the_brake(flow):
    values,writes=signal_stop(flow)
    state,truck,engine,ap,update,n,clock,acc,collected=values
    signal_tick(values,6,color=8)
    signal_tick(values,7,color=8,dt=.12)
    from core.service_brake_hold import resume_rejection
    witness=engine._drive_engagement['signal_resume']
    fired=[]
    def delay(key):
        if key=='longitudinal_traffic' and not fired:
            fired.append(True)
            clock[0]+=.501
    state.hook=delay
    assert resume_rejection(witness,state)
    state.hook=None
    count=len(writes)
    engine._flush_controls()
    assert not state.get('autopilot_active')
    assert all(v==0 for _,name,v in writes[count:] if name=='aforward')


def test_geometry_publication_race_never_authorizes_a_signal(flow):
    values,writes=signal_stop(flow)
    state,truck,engine,ap,update,n,clock,acc,collected=values
    engine._signal_route_token=None
    fired=[]
    def rebase(key):
        if key=='lane_trajectory' and not fired:
            fired.append(True)
            state.set('lane_trajectory_publication_token','changed-during-capture')
    state.hook=rebase
    result=engine._signal_observation(state.get('telemetry')['truck'],context(state))
    state.hook=None
    assert fired and not result['valid'] and result['candidate'] is None


def test_waiting_ui_updates_the_blocker_without_repeating_identical_messages(flow):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from UI.dynamic_island import DynamicIsland
    values,_=signal_stop(flow)
    state=values[0]
    island=SimpleNamespace(parentWidget=lambda:SimpleNamespace(state=state),
        show_record=Mock(),_hide_timer=Mock())
    DynamicIsland._poll_log(island)
    state.set('navigation_status','Čakám – semafor nie je čerstvý')
    DynamicIsland._poll_log(island)
    DynamicIsland._poll_log(island)
    assert island.show_record.call_count==2
    assert 'nie je čerstvý' in island.show_record.call_args.args[0]


def test_actual_map_prefix_rebase_preserves_locked_signal_and_activation(rolling):
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=rolling
    engine._signal_reader=SignalReader()
    engine._signal_selector=RouteSignalSelector()
    engine._signal_route_token=None
    activation=state.get('autopilot_failure_epoch')
    def light_tick(generation,z,speed,color=2):
        tick(speed=speed,z=z,pedals=False)
        truck=state.get('telemetry')['truck']
        payload=struct.pack('<fffhhffffifii',2.25,10.,100.,0,0,1.,0.,0.,0.,1,10.,color,19)+bytes(1920-48)
        engine._signal_reader.buffer=LAYOUT.pack(generation*2,0x32535055,2,LAYOUT.size,
            11,generation,truck['sdkFrameTimeUs'],clock[0],3,1,payload,generation*2)
        signal=engine._signal_observation(truck,context(state))
        import json
        debug=state.get('nav_steering_debug')
        assert signal['valid'],json.dumps(dict(signal=signal,context=context(state),
            packet={k:debug.get(k) for k in ('navigation_intent_id','authority_revision','route_build_id',
                'source_game_session_id','source_map_key','source_dataset_fingerprint','authority_valid',
                'authority_lane_id','observation_timestamp')},match=state.get('lane_match'),now=clock[0]))
        publish(state,truck,'traffic',traffic_brake=0.,light_brake=engine._light_brake(signal['candidate']),signal=signal)
        publish(state,truck,'acc',throttle=0.,brake=.4,control_target_kmh=0.)
        ap.on_tick(.033333);engine._flush_controls()
        assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
    for step in range(1,81):
        tick(speed=10.,z=15.+step*.5)
        engine._flush_controls()
    light_tick(1,55.,2.)
    lock=state.get('simple_auto_service_hold')['signal_lock']
    assert observe(list(range(2,9))).classification.value=='ADVANCED_PREFIX'
    light_tick(2,55.5,1.)
    assert state.get('simple_auto_service_hold')['signal_lock']==lock
    assert context(state)==tuple(lock['authority'])
    assert state.get('autopilot_failure_epoch')==activation
    assert physical('abackward')>0 and physical('aforward')==0
    assert observe(list(range(2,9))).classification.value=='SAME_EXACT'
    light_tick(3,55.5,0.)
    assert state.get('autopilot_control_state')=='planned_wait'


def test_combined_export_retains_original_signal_provenance_and_ordered_release(flow,tmp_path):
    import copy
    from dataclasses import replace
    from core.navigation.evidence_diagnostics import EvidenceDiagnosticCollector
    from tests.test_real_evidence_diagnostics import capture, command
    from tools.analyze_longitudinal_evidence import load_rows
    values,writes=signal_stop(flow)
    state,truck,engine,ap,update,n,clock,acc,collected=values
    for generation in range(6,36):
        signal_tick(values,generation,color=8,gear=8 if generation>=8 else 0,
                    speed=.3 if generation>=8 else 0.,dt=.12)
    root=tmp_path/'evidence-diagnostics'
    exporter=EvidenceDiagnosticCollector(root,capacity=60)
    exporter.apply_command(command(1,collection_id='signal-release'))
    for index,saved in enumerate(collected.samples):
        profile=copy.deepcopy(capture(index,when=1000.).profile)
        profile['observation'].update(sdk_frame_us=saved.truck['sdkFrameTimeUs'],captured_at=saved.captured_at_s)
        profile['observation']['articles'][0]['position_m']=[saved.truck[k] for k in ('x','y','z')]
        exporter._ingest(replace(saved,profile=profile))
    exporter.finalize()
    import json
    assert exporter.status()['state']=='READY_FOR_OFFLINE_REVIEW',json.dumps(exporter.status())
    rows,checked=load_rows(root/'signal-release')
    assert checked['integrity_valid'] and not checked['confirmed'] and not checked['runtime_authorized']
    events=[e for r in rows for e in r['longitudinal']['events']]
    assert events and all(not e['game_consumption_verified'] for e in events)
    release=[e for e in events if e['source'].get('phase')=='signal_resume']
    assert release and any(e['pair_after']['throttle']>0 for e in release)
    known=[e['pair_after'] for e in events if all(e['pair_after'][k] is not None for k in ('throttle','brake'))]
    assert known and all(not(p['throttle']>0 and p['brake']>0) for p in known)
    held=[e for e in events if (e['source'].get('service_hold') or {}).get('signal_lock')]
    assert held
    assert all(e['source']['service_hold']['signal_lock']['id']==19 for e in held)


@pytest.mark.parametrize('fault', ['stale','future','torn','inactive','schema','reset'])
def test_source_contract_rejects_faults(fault):
    raw = source_bytes(100., 2, 99)
    if fault=='stale': now=100.501
    elif fault=='future': now=99.99
    else: now=100.
    data=list(LAYOUT.unpack(raw))
    if fault=='torn': data[-1]+=2
    if fault=='inactive': data[8]=2
    if fault=='schema': data[2]=1
    if fault=='reset': data[6]=0
    assert not decode(LAYOUT.pack(*data), now)['valid']


def test_repeat_read_preserves_original_time_and_generation():
    reader=SignalReader(); reader.buffer=source_bytes(100.,2,90)
    first=decode(reader.buffer,100.)
    second=decode(reader.buffer,100.1)
    assert first==second


def test_route_selection_rejects_ambiguity_height_and_direction():
    selector=RouteSignalSelector()
    snapshot=decode(source_bytes(100.,2,90),100.)
    truck=dict(x=0.,y=10.,z=0.,rotation=0.)
    points=[[0.,10.,0.],[0.,10.,-50.]]
    first=selector.select(snapshot,points,'a',('session',),truck,0.)
    assert first['valid'] and first['candidate']['id']==19
    for change in (dict(id=20,x=3.),dict(y=30.),dict(z=5.),dict(yaw=0.)):
        other=dict(snapshot['lights'][0],**change)
        snap=dict(snapshot,lights=([snapshot['lights'][0],other] if 'id' in change else [other]))
        result=selector.select(snap,points,'a',('session',),truck,0.)
        assert not result['valid'], result
