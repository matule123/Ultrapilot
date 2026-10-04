"""Production producers/AP/Engine/Controller, with an explicitly modeled SDK.

Speed/ratio observations are test inputs, not measured ETS2 brake consumption.
The mapping records every pedal edge, including intermediate writes.
"""
import io
import struct

import pytest

from core.longitudinal import context, publish
from core.sdk.signal_snapshot import SignalReader, RouteSignalSelector
from sdk.plugin_sdk import PluginSDK
from plugins.drivepolicy.main import Plugin as DrivePolicy
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_longitudinal_arbitration import strict_flow
from tests.test_longitudinal_evidence_diagnostics import attach
from tests.test_roundabout_intervention_reporting import pedal
from tests.test_signal_stop_resume import source_bytes
from tests.test_continuous_service_stop import UserObservedGearbox
from tests.test_rolling_longitudinal_authority import rolling  # noqa: F401


def lifecycle(flow, mode=0, *, full_identity=False):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow, mode=mode)
    if full_identity:
        names = {'test-session': '12345678901234567890', 'test-map': 'promods-1.59',
                 'test-fingerprint': 'd6cc7936fce4e902761abb5d',
                 'test-build': 'd07082acabf84d9083eae872034230d9',
                 'intent': '44fa1cc1999f481892cbba00c928b8aa'}
        def expand(value):
            if isinstance(value, dict):
                return {k: expand(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return type(value)(expand(v) for v in value)
            return names.get(value, value) if isinstance(value, str) else value
        state.update_batch(expand(state.values))
    collected = attach(engine)
    policy = DrivePolicy(PluginSDK(state.values, 'drivepolicy'))
    policy.on_start()
    engine._signal_reader = SignalReader()
    engine._signal_selector = RouteSignalSelector()
    engine._signal_route_token = None
    lane = state.get('lane_trajectory')
    lane['points'] = [[0., 10., 0.], [0., 10., -50.]]
    state.set('lane_trajectory', lane)
    state.set('lane_trajectory_publication_token', 'a'*64 if full_identity else 'oct4-lifecycle')
    from core.navigation.lane_model import LaneId
    lane_id = dict(road_uid=11, direction=1, lane_index=0)
    match = state.get('lane_match')
    match['active_lane_id'] = lane_id
    state.set('lane_match', match)
    packet = state.get('nav_steering_debug')
    packet['authority_lane_id'] = LaneId(**lane_id).sort_key()
    packet['tracking_progress_m'] = 0.
    state.set('nav_steering_debug', packet)
    writes = []
    writer = engine.controller.scs
    writer.test_gearbox = UserObservedGearbox()

    class Buffer(io.BytesIO):
        def write(self, data):
            channel = next((k for k in ('aforward', 'abackward', 'parkingbrake')
                            if writer._offsets[k] == self.tell()), None)
            if channel:
                value = struct.unpack('f', data)[0] if len(data) == 4 else bytes(data)
                writes.append((clock[0], channel, value, truck['speed']))
                writer.test_gearbox.write(channel, value, truck['speed'])
            return super().write(data)

    writer._buf = Buffer(writer._buf.getvalue())
    generation = [0]

    def tick(gear, speed, color=8, dt=.05, *, flush=True, engine_first=False):
        update(gear, speed, dt=dt)
        generation[0] += 1
        engine._signal_reader.buffer = source_bytes(
            clock[0], generation[0], truck['sdkFrameTimeUs'], color=color)
        signal = engine._signal_observation(state.get('telemetry')['truck'], context(state))
        assert signal['valid'], signal
        publish(state, state.get('telemetry')['truck'], 'traffic', signal=signal,
                light=signal['candidate'], light_brake=engine._light_brake(signal['candidate']),
                traffic_brake=0., following=None)
        policy.on_tick(dt)
        acc.on_tick(dt)
        if engine_first:
            engine._flush_controls()
        ap.on_tick(dt)
        if flush:
            engine._flush_controls()
        return signal

    tick(0, 0.)
    n()  # one actual production hotkey, no manual throttle
    tick(0, 0.)
    assert pedal(engine, 'aforward') == pytest.approx(.12 if mode == 0 else 0.)
    tick(4, .001)
    tick(4, .2)
    tick(4, .3)
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert pedal(engine, 'aforward') > 0
    return state, truck, engine, ap, tick, n, clock, writes, collected


@pytest.mark.parametrize('first_brake_gear', [0, 4])
def test_first_planned_brake_seeds_real_continuity_then_waits(flow, first_brake_gear):
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow, full_identity=True)
    tick(first_brake_gear, .2, color=2)
    assert pedal(engine, 'abackward') > 0
    assert state.get('simple_auto_service_hold') is not None
    count = len(writes)
    for speed in (.12, .0673753545, .0186600498855, 0., 0.):
        tick(0, speed, color=2)
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
        assert pedal(engine, 'abackward') > 0 and pedal(engine, 'aforward') == 0
    assert state.get('autopilot_control_state') == 'planned_wait'
    assert not engine.controller.current_hazard
    assert all(value > 0 for _, channel, value, _ in writes[count:] if channel == 'abackward')
    assert not any(channel == 'parkingbrake' for _, channel, _, _ in writes)


@pytest.mark.parametrize('mode', [0, 3])
@pytest.mark.parametrize('engine_first', [False, True])
def test_full_producer_flow_repeats_wait_green_launch_without_another_n(flow, mode, engine_first):
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow, mode)
    token = state.get('simple_auto_activation_token')
    for _ in range(3):
        tick(4, .2, color=2, engine_first=engine_first)
        assert pedal(engine, 'abackward') > 0
        count = len(writes)  # Continuity begins at the first actual positive write.
        for speed in (.0673753545, .0186600498855, 0., 0.):
            tick(0 if mode == 0 else 4, speed, color=2, engine_first=engine_first)
            assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
            assert pedal(engine, 'aforward') == 0 and pedal(engine, 'abackward') > 0
        hold = state.get('simple_auto_service_hold')
        assert hold['signal_lock']['candidate']['id'] == 19
        assert hold['stop_evidence']['policy']['sdk_frame_us'] == hold['started_frame']
        assert hold['stop_evidence']['traffic']['signal']['valid']
        assert all(v > 0 for _, ch, v, _ in writes[count:] if ch == 'abackward')
        assert state.get('autopilot_control_state') == 'planned_wait'
        assert not engine.controller.current_hazard
        tick(0 if mode == 0 else 4, 0., color=8)
        assert pedal(engine, 'abackward') > 0 and pedal(engine, 'aforward') == 0
        tick(0 if mode == 0 else 4, 0., color=8, dt=.12)
        for gear, speed in ((4, .001), (4, .2), (4, .3), (4, .4)):
            tick(gear, speed)
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
        assert pedal(engine, 'aforward') > 0 and pedal(engine, 'abackward') == 0
        assert state.get('simple_auto_service_hold') is None
        assert state.get('simple_auto_activation_token') == token
    assert engine.controller.scs.test_gearbox.reverse_edges == 0
    assert not any(ch == 'parkingbrake' for _, ch, _, _ in writes)
    # Confirm chronological writes, not only final tick values.
    paired = {'aforward': 0., 'abackward': 0.}
    for _, ch, value, _ in writes:
        if ch in paired:
            paired[ch] = value
            assert not (paired['aforward'] > 0 and paired['abackward'] > 0)


@pytest.mark.parametrize('fault', ['R', 'backward', 'stale', 'identity', 'manual',
                                  'broken_chain', 'backend', 'parking_brake'])
def test_full_producer_wait_rejects_actual_safety_fault_and_never_self_resumes(flow, fault):
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow)
    tick(4, .2, color=2)
    tick(0, 0., color=2)
    count = len(writes)
    if fault == 'R':
        tick(-1, 0., color=2, flush=False)
    elif fault == 'backward':
        tick(0, -.3, color=2, flush=False)
    elif fault == 'stale':
        clock[0] += .501
    elif fault == 'identity':
        lane = state.get('lane_trajectory')
        lane['revision'] += 1
        state.set('lane_trajectory', lane)
    elif fault == 'manual':
        n()
    elif fault == 'broken_chain':
        engine.controller.set_brake(0.)
    elif fault == 'backend':
        engine.controller.scs.connected = False
    else:
        truck['parkBrake'] = True
        tick(0, 0., color=2, flush=False)
    engine._flush_controls()
    assert not state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert state.get('simple_auto_service_hold') is None
    assert pedal(engine, 'aforward') == 0
    assert all(v == 0 for _, ch, v, _ in writes[count:] if ch in ('aforward', 'abackward'))
    for _ in range(4):
        tick(4, 0., color=8)
        assert not state.get('autopilot_active') and pedal(engine, 'aforward') == 0


def test_runtime_stop_witness_is_independent_of_optional_diagnostic_text(flow):
    from core.longitudinal import engine_decision
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow)
    tick(4, .2, color=2, flush=False)
    acc = state.get('longitudinal_acc')
    acc['speed_control_reason'] = 'optional diagnostic detail ' * 1000
    state.set('longitudinal_acc', acc)
    decision, reason = engine_decision(state, state.get('telemetry')['truck'])
    assert not reason
    evidence = decision['stopping_evidence']
    assert evidence['traffic']['light']['id'] == 19
    assert evidence['traffic']['signal']['generation'] > 0
    assert evidence['policy']['sdk_frame_us'] == truck['sdkFrameTimeUs']
    assert 'snapshot_status' not in evidence
    # The runtime witness owns its small nested copies, not shared packet aliases.
    original = evidence['traffic']['signal']['candidate']['color']
    packet = state.get('longitudinal_traffic')
    packet['signal']['candidate']['color'] = 'green'
    state.set('longitudinal_traffic', packet)
    assert evidence['traffic']['signal']['candidate']['color'] == original == 'red'


def test_actual_map_window_with_both_real_producers_preserves_stop(rolling):
    # rolling uses the actual directed LanePath build, Map packet publication,
    # navigation window classifier and real Controller/memory backend.
    state, engine, ap, acc, policy, map_tick, observe, n, physical, writes, clock = rolling
    engine._signal_reader = SignalReader()
    engine._signal_selector = RouteSignalSelector()
    engine._signal_route_token = None
    token = state.get('simple_auto_activation_token')
    for step in range(1, 81):
        map_tick(speed=10., z=15.+step*.5)
        engine._flush_controls()

    def light_tick(gen, speed, z):
        map_tick(speed=speed, z=z, pedals=False)
        truck = state.get('telemetry')['truck']
        from core.sdk.signal_snapshot import LAYOUT
        payload = struct.pack('<fffhhffffifii', 2.25, 10., 100., 0, 0,
                              1., 0., 0., 0., 1, 10., 2, 19)+bytes(1920-48)
        engine._signal_reader.buffer = LAYOUT.pack(gen*2, 0x32535055, 2, LAYOUT.size,
            11, gen, truck['sdkFrameTimeUs'], clock[0], 3, 1, payload, gen*2)
        signal = engine._signal_observation(truck, context(state))
        assert signal['valid'], signal
        publish(state, truck, 'traffic', traffic_brake=0.,
                light_brake=engine._light_brake(signal['candidate']), signal=signal,
                light=signal['candidate'])
        policy.on_tick(.033333)
        acc.on_tick(.033333)
        ap.on_tick(.033333)
        engine._flush_controls()
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')

    light_tick(1, 2., 55.)
    lock = state.get('simple_auto_service_hold')['signal_lock']
    assert observe(list(range(2, 9))).classification.value == 'ADVANCED_PREFIX'
    light_tick(2, 1., 55.5)
    assert observe(list(range(2, 9))).classification.value == 'SAME_EXACT'
    light_tick(3, 0., 55.5)
    assert state.get('simple_auto_service_hold')['signal_lock'] == lock
    assert state.get('simple_auto_activation_token') == token
    assert state.get('autopilot_control_state') == 'planned_wait'
    assert physical('aforward') == 0 and physical('abackward') > 0


def test_all_producers_hold_resume_roundtrips_actual_writes_through_combined_export(flow, tmp_path):
    import copy
    from dataclasses import replace
    from core.navigation.evidence_diagnostics import EvidenceDiagnosticCollector
    from tests.test_real_evidence_diagnostics import capture, command
    from tools.analyze_longitudinal_evidence import load_rows
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow, full_identity=True)
    for gear, speed in ((4, .2), (0, .0673753545), (0, .0186600498855), (0, 0.)):
        tick(gear, speed, color=2)
    for _ in range(20):
        tick(0, 0., color=2)
    for gear, speed in ((0, 0.), (0, 0.), (4, .001), (4, .2), (4, .3)):
        tick(gear, speed, color=8, dt=.12)
    assert state.get('autopilot_active') and pedal(engine, 'aforward') > 0
    root = tmp_path/'evidence-diagnostics'
    exporter = EvidenceDiagnosticCollector(root, capacity=120)
    exporter.apply_command(command(1, collection_id='oct4-production-lifecycle'))
    for index, saved in enumerate(collected.samples):
        profile = copy.deepcopy(capture(index, when=1000.).profile)
        profile['observation'].update(sdk_frame_us=saved.truck['sdkFrameTimeUs'],
                                      captured_at=saved.captured_at_s)
        profile['observation']['articles'][0]['position_m'] = [saved.truck[k] for k in ('x','y','z')]
        exporter._ingest(replace(saved, profile=profile))
    exporter.finalize()
    assert exporter.status()['state'] == 'READY_FOR_OFFLINE_REVIEW', exporter.status()
    rows, checked = load_rows(root/'oct4-production-lifecycle')
    assert checked['integrity_valid'] and len(rows) == len(collected.samples)
    assert checked['confirmed'] is checked['runtime_authorized'] is False
    events = [e for row in rows for e in row['longitudinal']['events']]
    assert events and all(not e['game_consumption_verified'] for e in events)
    assert sum(row['longitudinal']['dropped_events'] for row in rows) == 0
    waits = [e for e in events if e['source'].get('phase') == 'planned_wait']
    resumes = [e for e in events if e['source'].get('phase') == 'signal_resume']
    assert waits and resumes
    for e in waits:
        source = e['source']
        assert source['service_hold']['stop_reason']['signal_id'] == 19
        assert source['service_hold']['signal_lock']['id'] == 19
        assert source['selected']['source'] == 'continuous_service_hold'
        assert source['sdk_frame_us'] > 0 and source['observation_timestamp'] > 0
        assert source['context']
        if source['service_hold']['phase'] == 'holding':
            assert abs(source['actual_speed_mps']) < .05
        assert source['observed_gear'] in (0, 4)
        assert e['pair_after']['throttle'] == 0 and e['pair_after']['brake'] > 0
    assert any(e['pair_after']['throttle'] > 0 for e in resumes)


def test_diagnostic_references_never_relabel_an_older_or_different_source():
    import copy
    from core.navigation.longitudinal_diagnostics import compact_decision
    binding = [1, 'session', 'map', 'dataset', 'intent', 7, 'build', 'geometry']
    packet = dict(context=tuple(binding), sdk_frame_us=20, observation_timestamp=100.,
                  computed_at=100.01, valid=True, expires_at=100.5, source='policy',
                  brake=.2, planned_speed_ms=5.)
    source = dict(context=binding, sdk_frame_us=20, observation_timestamp=100.,
        inputs={'policy': packet}, limits={'policy': {k: v for k, v in packet.items() if k != 'brake'}}, selected=dict(packet),
        requested=dict(packet, source='autopilot', throttle=0.))
    saved = compact_decision(source)
    assert saved['inputs']['policy']['context_reference'] == 'decision'
    assert saved['inputs']['policy']['observation_reference'] == 'decision'
    assert saved['limits']['policy'] == {'input_reference': 'policy'}
    original = copy.deepcopy(source)
    for key in ('inputs', 'limits'):
        source[key]['policy'] = dict(source[key]['policy'], context=[0]+binding[1:],
                                     sdk_frame_us=19, observation_timestamp=99.)
    source['requested'] = dict(source['requested'], context=[0]+binding[1:],
                               sdk_frame_us=19, observation_timestamp=99.)
    changed = compact_decision(source)
    for packet in (changed['inputs']['policy'], changed['requested']):
        assert packet['context'][0] == 0 and packet['sdk_frame_us'] == 19
        assert packet['observation_timestamp'] == 99.
        assert 'context_reference' not in packet and 'observation_reference' not in packet
    assert source != original and original['inputs']['policy']['sdk_frame_us'] == 20


def test_bounded_journal_counts_shared_provenance_once_and_eviction_reclaims_it():
    from core.navigation.longitudinal_diagnostics import PedalJournal
    journal = PedalJournal()
    journal.enabled = True
    source = dict(context=[1, 'session', 'map', 'dataset', 'intent', 7, 'build', 'geometry'],
                  reason='x'*4000)
    journal.bind(source)
    backend = dict(status='MAPPING_WRITE_RETURNED', value=0.)
    journal.record('throttle', 0., 1., 1., 'SCS_SDK', backend)
    journal.record('brake', .4, 1., 1., 'SCS_SDK', dict(backend, value=.4))
    assert len(journal._events) == 2 and journal._dropped == 0
    assert journal._bytes <= journal.MAX_BYTES
    for i in range(150):
        journal.bind(dict(source, observation_timestamp=float(i)))
        journal.record('brake', .4, 1., 1., 'SCS_SDK', dict(backend, value=.4))
        assert journal._bytes <= journal.MAX_BYTES
        assert len(journal._source_uses) <= len(journal._events) <= journal.CAPACITY
    saved = journal.drain()
    assert len(saved['events'])+saved['dropped_events'] == 152
    assert journal._bytes == 0 and not journal._source_uses
