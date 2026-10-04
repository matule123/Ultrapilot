"""Real SCS mapping writes; game model follows user observation, not SDK proof."""
import io
import struct
import copy
from dataclasses import replace

import pytest

from core.longitudinal import publish
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_roundabout_intervention_reporting import started, pedal


class UserObservedGearbox:
    """Manual-pedal semantic model; intentionally not a claim about SDK input."""
    def __init__(self):
        self.brake = 0.
        self.reverse_edges = 0

    def write(self, name, value, speed):
        if name == 'abackward':
            if value > 0 and self.brake == 0 and abs(speed) < .05:
                self.reverse_edges += 1
            self.brake = value


def continuous_stop(flow):
    values = started(flow, mode=0)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    writes = []
    writer = engine.controller.scs
    writer.test_gearbox = UserObservedGearbox()
    writer.test_offsets = []
    class Buffer(io.BytesIO):
        def write(self, data):
            writer.test_offsets.append((self.tell(), len(data)))
            name = next((k for k in ('aforward', 'abackward')
                         if writer._offsets[k] == self.tell()), None)
            if name:
                writes.append((clock[0], name, struct.unpack('f', data)[0]))
                writer.test_gearbox.write(name, struct.unpack('f', data)[0], truck['speed'])
            return super().write(data)
    writer._buf = Buffer(writer._buf.getvalue())
    for speed in (5., 2., .2, 0., 0.):
        update(8 if speed else 0, speed)
        publish(state, state.get('telemetry')['truck'], 'traffic',
                traffic_brake=0., light_brake=1.,
                light={'id': 19, 'color': 'red', 'distance': 5.})
        publish(state, state.get('telemetry')['truck'], 'acc', throttle=0.,
                brake=.4, emergency=False, control_target_kmh=0.)
        ap.on_tick(.05)
        engine._flush_controls()
    return values, writes


def test_continuous_forward_braking_keeps_authority_at_zero_ratio(flow):
    values, writes = continuous_stop(flow)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    brakes = [v for _, channel, v in writes if channel == 'abackward']
    assert brakes and all(v > 0 for v in brakes), brakes
    assert all(v == 0 for _, channel, v in writes if channel == 'aforward')
    assert state.get('autopilot_control_state') == 'planned_wait'
    assert pedal(engine, 'abackward') > 0
    parking = engine.controller.scs._offsets['parkingbrake']
    assert not any(offset <= parking < offset+size
                   for offset, size in engine.controller.scs.test_offsets)


@pytest.mark.parametrize('light', [None, 'unknown', 'green', 'red'])
def test_unknown_or_unversioned_clearance_never_releases_hold(flow, light):
    values, writes = continuous_stop(flow)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    original = state.get('simple_auto_service_hold')['stop_evidence']
    count = len(writes)
    for _ in range(20):  # Longer than the ordinary zero-ratio bridge.
        update(0, 0., dt=.1)
        publish(state, state.get('telemetry')['truck'], 'traffic',
                traffic_brake=0., light_brake=float(light == 'red'),
                light=None if light is None else {'id': 19, 'color': light}, following=None)
        publish(state, state.get('telemetry')['truck'], 'acc', throttle=.4,
                brake=0., emergency=False, control_target_kmh=50.)
        ap.on_tick(.1)
        engine._flush_controls()
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
        assert state.get('simple_auto_service_hold')['stop_evidence'] == original
        assert pedal(engine, 'aforward') == 0 and pedal(engine, 'abackward') > 0
    assert all(v > 0 for _, name, v in writes[count:] if name == 'abackward')
    assert state.get('simple_auto_service_hold')['automatic_restart_supported'] is False


@pytest.mark.parametrize('fault', ['zero_edge', 'release_all', 'backend', 'stale',
    'reverse', 'backward', 'roll', 'identity', 'driver_parking_brake'])
def test_invalidated_hold_never_represses_brake_at_rest(flow, fault):
    values, writes = continuous_stop(flow)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    if fault == 'zero_edge':
        engine.controller.set_brake(0.)
    elif fault == 'release_all':
        engine.controller.release_all()
    elif fault == 'backend':
        engine.controller.scs.connected = False
    elif fault == 'stale':
        clock[0] += .501
    elif fault == 'identity':
        lane = state.get('lane_trajectory')
        lane['revision'] += 1
        state.set('lane_trajectory', lane)
    else:
        if fault == 'driver_parking_brake':
            truck['parkBrake'] = True
        update(-1 if fault == 'reverse' else 0,
               -.3 if fault == 'backward' else (.3 if fault == 'roll' else 0.))
    count = len(writes)
    engine._flush_controls()
    assert not state.get('autopilot_active')
    assert state.get('simple_auto_service_hold') is None
    assert all(v == 0 for _, name, v in writes[count:] if name in ('aforward', 'abackward'))


def test_manual_disable_destroys_hold_and_new_n_cannot_reuse_it(flow):
    values, writes = continuous_stop(flow)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    old_token = state.get('simple_auto_activation_token')
    n()
    engine._flush_controls()
    assert state.get('simple_auto_service_hold') is None
    assert pedal(engine, 'abackward') == pedal(engine, 'aforward') == 0
    update(0, 0.)
    n()
    engine._flush_controls()
    assert state.get('simple_auto_service_hold') is None
    assert not state.get('autopilot_active')  # red stop still prevents launch
    assert state.get('simple_auto_activation_token') != old_token
    assert pedal(engine, 'aforward') == 0


def test_brake_receipt_is_independent_of_combined_diagnostics(flow):
    values, writes = continuous_stop(flow)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    engine.controller._pedal_journal.enabled = False
    before = state.get('simple_auto_service_hold')['write_sequence']
    update(0, 0.)
    publish(state, state.get('telemetry')['truck'], 'acc', throttle=0., brake=.4)
    publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0., light_brake=1.)
    ap.on_tick(.05)
    engine._flush_controls()
    assert state.get('autopilot_active')
    assert state.get('simple_auto_service_hold')['write_sequence'] > before
    assert state.get('simple_auto_service_hold')['game_consumption_verified'] is False


def test_break_between_validation_and_write_cannot_create_fresh_brake_edge(flow):
    values, writes = continuous_stop(flow)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    original = engine.controller.set_steering
    def interrupt(value):
        original(value)
        engine.controller.set_brake(0.)
    engine.controller.set_steering = interrupt
    count = len(writes)
    engine._flush_controls()
    assert not state.get('autopilot_active')
    assert all(v == 0 for _, name, v in writes[count:] if name == 'abackward')


@pytest.mark.parametrize('mass_kg', [12000., 40000.])
@pytest.mark.parametrize('grade', [-.08, 0., .08])
def test_user_semantics_model_holds_load_only_with_sufficient_actual_brake(flow, mass_kg, grade):
    values, writes = continuous_stop(flow)
    # Explicit model: 160 kN maximum service-brake force; static friction
    # opposes grade, no tyre slip, no pneumatic lag, no ETS2 calibration claim.
    # Gear rule follows manual-pedal observation, NOT measured DLL consumption.
    state, truck, engine, ap, update, n, clock, acc, collected = values
    model = engine.controller.scs.test_gearbox
    held_brake = model.brake
    assert held_brake > 0
    resistance = held_brake * 160000. / mass_kg
    grade_acceleration = abs(grade) * 9.81
    assert resistance > grade_acceleration
    assert model.reverse_edges == 0
    # Static friction in this explicit model gives zero acceleration for
    # 10 seconds of holding; insufficient force would roll and fail above.
    speed = 0.
    for _ in range(1000):
        acceleration = max(0., grade_acceleration-resistance)
        speed += acceleration*.01
    assert speed == 0


def test_emergency_while_holding_preserves_first_cause_and_never_drives(flow):
    values, writes = continuous_stop(flow)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    update(0, 0.)
    publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=1., light_brake=0.)
    engine._flush_controls()
    assert not state.get('autopilot_active')
    assert state.get('autopilot_intervention')['code'] == 'EMERGENCY_BRAKE'
    assert state.get('simple_auto_service_hold') is None
    assert pedal(engine, 'aforward') == 0


def test_waiting_export_keeps_original_reason_and_actual_paired_write(flow):
    values, writes = continuous_stop(flow)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    events = collected.samples[-1].longitudinal['events']
    assert events and all(e['source']['snapshot_status'] != 'UNVERIFIED_SNAPSHOT_BUDGET_EXCEEDED'
                          for e in events if 'snapshot_status' in (e['source'] or {}))
    event = next(e for e in reversed(events) if e['channel'] == 'brake')
    assert event['source']['phase'] == 'planned_wait'
    assert event['source']['selected']['source'] == 'continuous_service_hold'
    assert event['source']['service_hold']['stop_reason']['signal_id'] == 19
    assert event['pair_after']['throttle'] == 0
    assert event['pair_after']['brake'] > 0
    assert not event['game_consumption_verified']


def test_stale_pedal_command_ends_hold_without_a_new_positive_edge(flow):
    values, writes = continuous_stop(flow)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    command = state.get('longitudinal_command')
    command['observation_timestamp'] = clock[0]-.501
    state.set('longitudinal_command', command)
    count = len(writes)
    engine._flush_controls()
    assert not state.get('autopilot_active')
    assert state.get('simple_auto_service_hold') is None
    assert all(v == 0 for _, name, v in writes[count:] if name in ('aforward', 'abackward'))


def test_zero_then_positive_at_rest_is_reverse_in_user_model():
    model = UserObservedGearbox()
    model.write('abackward', .4, 5.)
    model.write('abackward', .4, 0.)
    assert model.reverse_edges == 0
    model.write('abackward', 0., 0.)
    model.write('abackward', .4, 0.)
    assert model.reverse_edges == 1


def test_original_stop_witness_is_not_relabelled_after_physical_write(flow):
    values, writes = continuous_stop(flow)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    original = state.get('simple_auto_service_hold')['command_context']
    set_brake = engine.controller.set_brake
    def concurrent(value):
        set_brake(value)
        lane = state.get('lane_trajectory')
        lane['revision'] += 1
        state.set('lane_trajectory', lane)
    engine.controller.set_brake = concurrent
    engine._flush_controls()
    assert state.get('simple_auto_service_hold')['command_context'] == original
    engine._flush_controls()
    assert not state.get('autopilot_active')


def test_hold_provenance_roundtrips_through_existing_combined_export(flow, tmp_path):
    from core.navigation.evidence_diagnostics import EvidenceDiagnosticCollector
    from tests.test_real_evidence_diagnostics import capture, command
    from tools.analyze_longitudinal_evidence import load_rows
    values, writes = continuous_stop(flow)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    collected.samples.clear()
    for _ in range(30):
        update(0, 0., dt=.1)
        publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0., light_brake=1.)
        publish(state, state.get('telemetry')['truck'], 'acc', throttle=0., brake=.4)
        ap.on_tick(.1)
        engine._flush_controls()
    root = tmp_path / 'evidence-diagnostics'
    exporter = EvidenceDiagnosticCollector(root, capacity=30)
    exporter.apply_command(command(1, collection_id='continuous-hold'))
    for index, saved in enumerate(collected.samples):
        profile = copy.deepcopy(capture(index, when=1000.).profile)
        profile['observation'].update(sdk_frame_us=saved.truck['sdkFrameTimeUs'],
                                      captured_at=saved.captured_at_s)
        profile['observation']['articles'][0]['position_m'] = [saved.truck[k] for k in ('x', 'y', 'z')]
        exporter._ingest(replace(saved, profile=profile))
    exporter.finalize()
    assert exporter.status()['state'] == 'READY_FOR_OFFLINE_REVIEW', exporter.status()
    rows, checked = load_rows(root / 'continuous-hold')
    assert checked['integrity_valid'] and len(rows) == 30
    assert checked['confirmed'] is checked['runtime_authorized'] is False
    for row in rows:
        events = row['longitudinal']['events']
        assert events and all(not e['game_consumption_verified'] for e in events)
        assert all(e['source']['service_hold']['stop_reason']['signal_id'] == 19 for e in events)
        assert all(e['source']['phase'] == 'planned_wait' for e in events)
        assert all(e['pair_after']['throttle'] == 0 for e in events)
    (root / 'continuous-hold' / 'automatic-observations.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='INTEGRITY'):
        load_rows(root / 'continuous-hold')


def test_waiting_ui_shows_transition_once(flow):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from UI.dynamic_island import DynamicIsland
    values, writes = continuous_stop(flow)
    state = values[0]
    island = SimpleNamespace(parentWidget=lambda: SimpleNamespace(state=state),
                             show_record=Mock(), _hide_timer=Mock())
    DynamicIsland._poll_log(island)
    DynamicIsland._poll_log(island)
    assert island.show_record.call_count == 1
    assert 'Čakám' in island.show_record.call_args.args[0]


def test_other_stop_source_cannot_release_original_signal_stop(flow):
    values, writes = continuous_stop(flow)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    original_chain = state.get('simple_auto_service_hold')['chain']
    count = len(writes)
    for source in ('acc', 'red', 'unknown'):
        update(0, 0., dt=.1)
        publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0.,
                light_brake=1. if source == 'red' else 0.,
                light={'id': 19, 'color': 'green' if source == 'acc' else source})
        publish(state, state.get('telemetry')['truck'], 'acc', throttle=0.,
                brake=.7 if source == 'acc' else 0., emergency=False)
        ap.on_tick(.1)
        engine._flush_controls()
        assert state.get('autopilot_active')
        hold = state.get('simple_auto_service_hold')
        assert hold['chain'] == original_chain
        assert hold['stop_reason']['signal_id'] == 19
    assert all(v > 0 for _, name, v in writes[count:] if name == 'abackward')


def test_short_backend_brake_write_is_not_a_continuity_acknowledgement(flow):
    values, writes = continuous_stop(flow)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    writer = engine.controller.scs
    class Partial(io.BytesIO):
        def write(self, data):
            return super().write(data[:2]) if self.tell() == writer._offsets['abackward'] else super().write(data)
    writer._buf = Partial(writer._buf.getvalue())
    engine._flush_controls()
    assert not state.get('autopilot_active')
    assert state.get('simple_auto_service_hold') is None
    assert not writer._brake_write_receipt['positive']
    assert not writer.connected
    assert pedal(engine, 'aforward') == 0


def test_hold_age_is_checked_after_slow_ipc_receives_a_new_actual_write(flow):
    from core.transmission_mode import simple_auto_forward_transition
    values, writes = continuous_stop(flow)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    update(0, 0., dt=.01)
    triggered = []
    def delayed_read(key):
        if key != 'simple_auto_service_hold' or triggered:
            return
        triggered.append(key)
        clock[0] += .03
        witness = dict(engine._service_brake_hold)
        engine.controller.set_brake(witness['brake'])  # actual isolated write
        receipt = engine.controller.scs._brake_write_receipt
        witness.update(returned_at=receipt['returned_at'], write_sequence=receipt['sequence'])
        state.set('simple_auto_service_hold', witness)
    state.hook = delayed_read
    history, reason = simple_auto_forward_transition(
        state, state.get('telemetry')['truck'], engine._simple_auto_forward_history)
    state.hook = None
    assert triggered and not reason
    assert history['last_observed_at'] == state.get('telemetry')['truck']['_control_observation']['observed_at']
    assert history['last_observed_at'] < clock[0]  # never refresh the SDK timestamp
