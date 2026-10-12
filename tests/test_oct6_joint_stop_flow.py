"""Oct 6 production regressions; SDK pedal semantics remain a model."""
import pytest

from core.longitudinal import context, publish
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct4_signal_lifecycle import lifecycle
from tests.test_roundabout_intervention_reporting import pedal


@pytest.mark.parametrize('engine_first', [False, True])
def test_late_first_brake_at_zero_ratio_does_not_require_new_drive(flow, engine_first):
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow)
    # Independently scheduled Plugin publishes current commands; Engine's
    # committed confirmation is older than .5 s when it first sees zero.
    for _ in range(6):
        tick(4, .5424093604, dt=.09, flush=False)
    # Approach the derived target (1 m from the initial SDK position) so the
    # red really requests the first brake, rather than permitting coasting.
    truck['z'] = -1.
    tick(0, .5424093604, color=2, engine_first=engine_first)
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert pedal(engine, 'aforward') == 0 and pedal(engine, 'abackward') > 0
    assert state.get('simple_auto_service_hold')
    count = len(writes)
    for speed in (.2, .06, .01, 0., 0.):
        tick(0, speed, color=2)
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert all(v > 0 for _, name, v, _ in writes[count:] if name == 'abackward')
    assert not engine.controller.current_hazard


def test_expired_zero_window_cannot_reject_already_written_service_hold(flow):
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow)
    tick(0, .3, color=2)
    # The bounded first-zero history expires, but a current actual brake chain
    # has since replaced it. It must be checked before the obsolete deadline.
    history = state.get('simple_auto_forward_history')
    history['zero_deadline_at'] = clock[0] - .001
    engine._simple_auto_forward_history = history
    state.set('simple_auto_forward_history', history)
    tick(0, .02, color=2)
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert pedal(engine, 'abackward') > 0


def test_yellow_started_brake_is_locked_before_red_or_color_flicker(flow, monkeypatch):
    import tests.test_oct4_signal_lifecycle as source
    from core.sdk.signal_snapshot import LAYOUT
    from tests.test_signal_clearance_source_contract import semaphore_buffer
    def at_twenty(now, generation, frame, color=8):
        return LAYOUT.pack(generation*2, 0x32535055, 2, LAYOUT.size, 11,
            generation, frame, now, 3, 1, bytes(semaphore_buffer(state=color, z=-20.)), generation*2)
    monkeypatch.setattr(source, 'source_bytes', at_twenty)
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow)
    tick(4, 2., color=4)  # source ABI: yellow
    assert pedal(engine, 'abackward') > 0
    hold = state.get('simple_auto_service_hold')
    assert hold and hold.get('signal_lock'), hold
    count = len(writes)
    # A one-frame green while moving is not clearance for the latched stop.
    tick(4, 1.8, color=8)
    tick(0, .2, color=2)
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert all(v > 0 for _, name, v, _ in writes[count:] if name == 'abackward')
    assert all(v == 0 for _, name, v, _ in writes[count:] if name == 'aforward')


def test_two_crossing_actors_on_directed_turn_are_both_protective_candidates():
    from core.acc_following import RouteLeadSelector
    route = RouteLeadSelector()
    route.prepare([[0., 10., 0.], [0., 10., -10.], [10., 10., -10.]], ('route',))
    truck = dict(x=0., y=10., z=0., rotation=0., speed=2.)
    # Both are currently behind the old ahead-axis gate, but cross the selected
    # turn. Removing the first must not discard the second.
    actors = [dict(id=i, x=6., y=10., z=2.+offset, yaw=0., speed=3.,
                   dimensions_whl=(2., 2., 4.)) for i, offset in [(1, 0.), (2, 3.)]]
    first = route.crossing(actors, truck, 0.)
    assert {x['id'] for x in first['conflicts']} == {1, 2}
    assert first['brake'] > 0 and first['clearance_confirmed'] is False
    second = route.crossing(actors[1:], truck, 0.)
    assert second['brake'] > 0 and second['conflicts'][0]['id'] == 2
    assert route.crossing([], truck, 0.)['clearance_confirmed'] is False


@pytest.mark.parametrize('fault',['other_deck','parallel','moving_away','nan','duplicate_id','dense_route'])
def test_crossing_rejection_never_becomes_confirmed_clearance(fault):
    from core.acc_following import RouteLeadSelector
    route=RouteLeadSelector()
    points=[[0.,10.,0.],[0.,10.,-10.],[10.,10.,-10.]]
    if fault=='dense_route':points=[[0.,10.,-i*.01] for i in range(2000)]
    route.prepare(points,('route',))
    actor=dict(id=1,x=6.,y=10.,z=2.,yaw=0.,speed=3.,dimensions_whl=(2.,2.,4.))
    if fault=='other_deck':actor['y']=30.
    if fault=='parallel':actor.update(x=0.,z=-4.)
    if fault=='moving_away':actor['yaw']=3.141592653589793
    if fault=='nan':actor['speed']=float('nan')
    actors=[actor,actor] if fault=='duplicate_id' else [actor]
    result=route.crossing(actors,dict(x=0.,y=10.,z=0.,rotation=0.,speed=2.),0.)
    assert result['brake']==0
    assert not result['clearance_confirmed'] and not result['coverage_confirmed']


def test_invalid_planned_brake_cannot_seed_a_new_zero_ratio_exception(flow):
    from core.longitudinal import planned_braking_input
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow)
    tick(4,.54,color=2)
    traffic=state.get('longitudinal_traffic');traffic['light_brake']=float('nan')
    state.set('longitudinal_traffic',traffic)
    assert not planned_braking_input(state)


def test_sdk_control_read_uses_one_stable_byte_image():
    from core.sdk.scs_sdk import SCSTelemetry
    import struct
    # A writer changes the mapped image between field reads. Capture must retry
    # boundedly, then decode all control fields from the same stable image.
    old, new = bytearray(32768), bytearray(32768)
    for data, frame, gear, speed in [(old, 100, 4, 2.), (new, 200, 0, .54)]:
        data[0] = 1
        struct.pack_into('Q', data, 8, frame)
        struct.pack_into('i', data, 504, gear)
        struct.pack_into('f', data, 948, speed)
        struct.pack_into('I', data, 40, 12)
    class Changing:
        def __init__(self): self.calls = 0
        def __getitem__(self, key):
            self.calls += 1
            # Old reader gets frame=100 then new ratio/speed; the bounded
            # image reader observes a changed copy and retries without mixing.
            whole = isinstance(key, slice) and key.start is None and key.stop > 10000
            return bytes((old if self.calls == 1 or (not whole and self.calls <= 3) else new)[key])
    sdk = SCSTelemetry(); sdk.mm = Changing()
    result = sdk.update()
    assert result['time'] == 200
    assert result['truckInt']['gear'] == 0
    assert result['truckFloat']['speed'] == pytest.approx(.54)
    assert result['controlRead']['stable'] is True
    assert result['controlRead']['sdk_frame_us'] == 200


def test_failed_sdk_read_cannot_be_normalized_as_success():
    from core.telemetry import Telemetry
    class Reader:
        def update(self): return {}
    telemetry = Telemetry.__new__(Telemetry)
    telemetry.use_sdk = True; telemetry.sdk_reader = Reader(); telemetry.data = {}
    assert telemetry.update() is False
    assert telemetry.use_sdk is True  # no silent transport switch on a read overlap


def test_detected_overlap_preserves_original_sample_only_until_its_real_expiry(flow, monkeypatch):
    from copy import deepcopy
    from tests.test_stage4d_control_timing import EngineRealtimeBoundaryTests
    state, truck, _, _, _, _, clock = flow
    engine = EngineRealtimeBoundaryTests.bare_engine(state)
    start = clock[0]
    samples = []
    class Reader:
        data = {}; last_read_failure = ''
        count = 0
        def update(self):
            self.count += 1
            clock[0] = start + (0.02, .06, .4, .54)[self.count-1]
            if self.count == 1:
                self.data = dict(truck=deepcopy(truck), raw=dict(sdkActive=True,
                    controlRead=dict(stable=True, observed_at=start+.01)))
                return True
            self.last_read_failure = 'SDK_CONTROL_READ_CHANGED'
            return False
    engine.telemetry = Reader()
    def next_tick(*args):
        samples.append(state.get('telemetry'))
        return clock[0], len(samples)==4
    monkeypatch.setattr('core.engine.wait_for_next_tick', next_tick)
    engine._telemetry_loop()
    assert [s['truck']['sdkFrameTimeUs'] for s in samples[:3]] == [truck['sdkFrameTimeUs']]*3
    assert all(s['truck']['_control_observation']['observed_at']==start+.01 for s in samples[:3])
    assert samples[-1]['truck']['sdkFrameTimeUs'] == 0
    assert state.get('telemetry_valid') is False
    assert state.get('telemetry_read_failure') == 'SDK_CONTROL_READ_CHANGED'


@pytest.mark.parametrize('fault', ['paused','inactive','unchanged_frame'])
def test_real_sdk_loss_or_pause_does_not_renew_control_sample(flow, monkeypatch, fault):
    from copy import deepcopy
    from tests.test_stage4d_control_timing import EngineRealtimeBoundaryTests
    state, truck, _, _, _, _, clock = flow
    engine = EngineRealtimeBoundaryTests.bare_engine(state)
    start = clock[0]
    class Reader:
        count = 0
        def update(self):
            self.count += 1
            clock[0] = start+(.02 if self.count==1 else (.54 if fault=='unchanged_frame' else .08))
            self.data = dict(truck=deepcopy(truck),raw=dict(
                sdkActive=not(self.count>1 and fault=='inactive'),
                pause=self.count>1 and fault=='paused',
                controlRead=dict(stable=True, observed_at=clock[0])))
            if fault!='unchanged_frame':
                self.data['truck']['sdkFrameTimeUs'] += self.count*1000
            return True
    engine.telemetry = Reader()
    monkeypatch.setattr('core.engine.wait_for_next_tick', lambda *args:(clock[0],engine.telemetry.count==2))
    engine._telemetry_loop()
    assert state.get('telemetry_valid') is False
    assert state.get('telemetry')['truck']['sdkFrameTimeUs'] == 0
    assert engine._telemetry_snapshot(clock[0])[0] is False


def test_raw_capture_second_crossing_flows_through_policy_acc_and_real_backend(flow):
    from dataclasses import replace
    from core.navigation.traffic_producer import capture_traffic
    from core.sdk.ets2la_data import ETS2LAData
    from tests.test_acc_following import capture, route_input
    from tests.test_longitudinal_arbitration import strict_flow
    from tests.test_longitudinal_evidence_diagnostics import attach
    from sdk.plugin_sdk import PluginSDK
    from plugins.drivepolicy.main import Plugin as Policy
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    collected = attach(engine)
    policy = Policy(PluginSDK(state.values,'drivepolicy')); policy.on_start()
    update(4,2.);n()
    actors = [dict(id=i,x=6.,y=0.,z=2.+offset,yaw=0.,speed=3.) for i,offset in ((1,0.),(2,3.))]
    for available in (actors,list(reversed(actors)),actors[1:]):
        update(4,2.)
        current = state.get('telemetry')['truck']
        binding = route_input(state,engine,current,[[0.,0.,0.],[0.,0.,-10.],[10.,0.,-10.]])
        raw = capture(available,clock[0])
        reader=ETS2LAData();reader._traffic_buf,reader._parked_buf=raw.moving,raw.parked
        from core.sdk.ets2la_data import _SEM_SIZE
        reader._sem_buf=bytes(_SEM_SIZE)  # no live mapping/device connection
        captured = capture_traffic(reader,str(binding[1]),clock[0])
        observed = engine._route_lead_observation(captured,current,binding)
        crossing = observed.get('crossing') or dict(brake=0.,conflicts=[])
        traffic_brake = engine._lead_brake(reader.read_traffic(),
            (current['x'],current['z']),current['rotation'],current['speed'],crossing_only=True)
        # Run the original producer's actual legacy brake path when loading
        # the baseline in memory, so its counterexample reaches physical I/O
        # rather than failing merely because the new capability is absent.
        merge = getattr(engine,'_route_crossing_brake',None)
        if merge is not None:
            traffic_brake = merge(observed, traffic_brake)
        publish(state,current,'traffic',traffic_brake=traffic_brake,
            following=observed,light=None,light_brake=0.,brake_basis=engine._traffic_brake_basis)
        policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
        assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
        assert pedal(engine,'aforward')==0 and pedal(engine,'abackward')>0
        assert {v['id'] for v in crossing['conflicts']}=={a['id'] for a in available}
        events = collected.samples[-1].longitudinal['events']
        written = next(e for e in reversed(events) if e['channel'] == 'brake')
        assert written['backend']['status'] == 'MAPPING_WRITE_RETURNED'
        import json
        # Journal/export snapshots use JSON arrays, whereas the byte decoder's
        # immutable dimension vector is a tuple. Compare the full wire value.
        assert written['source']['inputs']['traffic']['brake_basis'] == json.loads(
            json.dumps(engine._traffic_brake_basis))
        assert written['pair_after']['throttle'] == 0 and written['pair_after']['brake'] > 0
        assert written['game_consumption_verified'] is False
    lost=replace(captured,moving=None)
    unavailable=engine._route_lead_observation(lost,current,binding)
    assert unavailable['status']=='incomplete_buffers'
    assert not unavailable['confirmed']


def test_crossing_attribution_is_bounded_and_cannot_weaken_emergency(flow):
    from core.navigation.longitudinal_diagnostics import bounded_input
    engine = flow[2]
    conflicts = [dict(id=i,brake=.3+i/160.) for i in range(80)]
    following = dict(crossing=dict(brake=conflicts[-1]['brake'],conflicts=conflicts))
    assert engine._route_crossing_brake(following, 0.) == conflicts[-1]['brake']
    basis = engine._traffic_brake_basis
    assert basis['conflict_count'] == 80 and len(basis['candidate_ids']) == 16
    assert basis['decisive']['id'] == 79 and basis['omitted_candidate_ids'] == 64
    bounded = bounded_input(dict(brake_basis=basis))
    assert bounded['brake_basis'] == basis
    assert not basis['clearance_confirmed'] and basis['producer_timestamp'] is None
    engine._traffic_brake_basis = {'kind':'existing_emergency'}
    assert engine._route_crossing_brake(following, 1.) == 1.
    assert engine._traffic_brake_basis['kind'] == 'existing_emergency'


@pytest.mark.parametrize('fault', ['truncated', 'nan_speed', 'invalid_header', 'unavailable'])
def test_invalid_sdk_image_is_rejected_whole(fault):
    from core.sdk.scs_sdk import SCSTelemetry
    import struct
    image = bytearray(32768)
    image[0] = 1
    struct.pack_into('Q', image, 8, 100)
    if fault == 'truncated': image = image[:1000]
    if fault == 'nan_speed': struct.pack_into('f', image, 948, float('nan'))
    if fault == 'invalid_header': image[0] = 2
    sdk = SCSTelemetry()
    sdk.mm = None if fault == 'unavailable' else image
    assert sdk.update() == {}
    assert sdk.last_read_failure in ('SDK_CONTROL_READ_INVALID','SDK_CONTROL_READ_UNAVAILABLE')


@pytest.mark.parametrize('fault',['no_stop','expired_stop','identity','R','backwards'])
def test_old_ratio_history_never_grants_new_zero_ratio_propulsion(flow,fault):
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow)
    for _ in range(6):
        tick(4,.54,dt=.09,flush=False)
    if fault=='expired_stop':
        p=state.get('longitudinal_traffic');p['expires_at']=clock[0]-.001;state.set('longitudinal_traffic',p)
    elif fault=='identity':
        lane=state.get('lane_trajectory');lane['route_build_id']='foreign';state.set('lane_trajectory',lane)
    if fault in ('no_stop','expired_stop','identity'):
        flow[4](0,.54)
    else:
        flow[4](-1 if fault=='R' else 4,-.2 if fault=='backwards' else .54)
    engine._flush_controls()
    assert pedal(engine,'aforward')==0
    assert not state.get('autopilot_active')


def test_actual_map_build_late_zero_brake_and_repeated_green_restart(flow,tmp_path):
    import math
    from plugins.map.main import Plugin as Map
    from plugins.drivepolicy.main import Plugin as Policy
    from sdk.plugin_sdk import PluginSDK
    from core.sdk.signal_snapshot import SignalReader,RouteSignalSelector
    from tests.test_lane_route_builder import SyntheticMap
    from tests.test_longitudinal_arbitration import strict_flow
    from tests.test_longitudinal_evidence_diagnostics import memory_controller
    from tests.test_prefab_signal_binding import parsed_path,signal_bytes
    net,_,_=parsed_path(tmp_path,reverse=True,lane_shift=-2.25)
    synthetic=SyntheticMap();synthetic.net=net
    for uid,z in ((10,-230.),(12,-130.),(11,-100.)):
        synthetic.node(uid,0.,z,10.)
    synthetic.road(10,12,1)
    state,truck,engine,ap,update,n,clock,acc=strict_flow(flow)
    plugin=Map(PluginSDK(state.values,'map'));plugin.on_start();plugin.road_net=net;plugin._net_attempted=True
    engine.controller=memory_controller();engine._signal_reader=SignalReader()
    engine._signal_selector=RouteSignalSelector();engine._signal_route_token=None
    policy=Policy(PluginSDK(state.values,'drivepolicy'));policy.on_start()
    state.set('game_route_node_uids',[10,12,11]);state.set('acc_target_speed',35.)
    writes=[];original=engine.controller.scs._write_float
    def write(channel,value):
        original(channel,value)
        if channel in ('aforward','abackward'):writes.append((clock[0],channel,value))
    engine.controller.scs._write_float=write
    generation=0
    def tick(gear,speed,z,color=8,*,flush=True,dt=.1):
        nonlocal generation
        generation+=1
        truck.update(x=-2.25,y=10.,z=z,rotation=math.pi)
        update(gear,speed,dt=dt)
        obs=state.get('telemetry')['truck']['_control_observation']
        state.update_batch(dict(truck_world_pos=(-2.25,z),truck_altitude=10.,truck_heading=math.pi,
            truck_speed_ms=speed,vehicle_envelope_snapshot=dict(timestamp=obs['observed_at'],
                sdk_frame_us=truck['sdkFrameTimeUs'],tractor_position=(-2.25,10.,z),
                tractor_heading=math.pi,tractor_speed_ms=speed,tractor_reference_geometry=dict(
                    valid=True,source='synthetic_4x2',wheelbase_m=3.8,reference_ahead_m=2.1))))
        plugin.on_tick(dt)
        assert state.get('nav_steering_debug')['authority_valid']
        engine._signal_reader.buffer=signal_bytes(clock[0],generation,truck['sdkFrameTimeUs'],
            [dict(id=4,x=-5.,y=10.,z=-110.,yaw=0.,state=color)])
        signal=engine._signal_observation(state.get('telemetry')['truck'],context(state))
        assert signal['valid'],signal
        publish(state,state.get('telemetry')['truck'],'traffic',traffic_brake=0.,
            light_brake=engine._light_brake(signal['candidate']),light=signal['candidate'],signal=signal)
        policy.on_tick(dt);acc.on_tick(dt);ap.on_tick(dt)
        if flush:engine._flush_controls()
    try:
        tick(0,0.,-220.);n();tick(0,0.,-220.)
        assert pedal(engine,'aforward')==pytest.approx(.12)
        tick(4,.001,-220.);tick(4,.2,-220.);tick(4,.3,-220.)
        # At the derived stop target the real planner requests braking even
        # at crawl speed. A red head 7 m farther away permits approach, and
        # would not be a valid first-brake reproduction at .54 m/s.
        for i in range(1,165):tick(4,.54,-220.+i*.5)
        for _ in range(6):tick(4,.54,-138.,flush=False)
        activation=state.get('simple_auto_activation_token')
        for _ in range(3):
            tick(0,.54,-138.,color=2)
            assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
            assert pedal(engine,'abackward')>0 and pedal(engine,'aforward')==0
            count=len(writes)
            for speed in (.2,.06,.01,0.,0.):tick(0,speed,-138.,color=2)
            assert all(v>0 for _,c,v in writes[count:] if c=='abackward')
            assert not engine.controller.current_hazard
            tick(0,0.,-138.,color=8);tick(0,0.,-138.,color=8,dt=.12)
            tick(0,0.,-138.,color=8)
            for gear,speed in ((4,.001),(4,.2),(4,.3), (4,.54)):tick(gear,speed,-138.)
            assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
            assert pedal(engine,'aforward')>0 and pedal(engine,'abackward')==0
            assert state.get('simple_auto_activation_token')==activation
        held={'aforward':0.,'abackward':0.}
        for _,c,v in writes:
            held[c]=v
            assert not(held['aforward']>0 and held['abackward']>0)
    finally:
        plugin._maneuver_evidence_worker.close();plugin._maneuver_reference_mux.close()
