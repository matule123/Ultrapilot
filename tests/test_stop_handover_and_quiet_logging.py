"""Real pedal writer; unsupported hill hold must remain a driver handover."""
import copy
import io
import logging
from dataclasses import replace
from unittest.mock import patch

import pytest

from core.longitudinal import publish
from core.telemetry import Telemetry
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_roundabout_intervention_reporting import started, pedal
from tests.test_stage5b1_vehicle_profile import observation


def stopping(flow, *, mode=0, park=False, pitch=0.):
    values = started(flow, mode=mode)
    state, truck, engine, ap, update, n, clock, acc, collected = values
    truck.update(parkBrake=park, pitch=pitch)
    update(8, 0.)
    publish(state, state.get('telemetry')['truck'], 'traffic',
            traffic_brake=0., light_brake=1.,
            light={'color': 'red', 'distance': 5., 'producer_timestamp': None})
    publish(state, state.get('telemetry')['truck'], 'acc', throttle=0.,
            brake=.4, emergency=False, control_target_kmh=0.)
    ap.on_tick(.05)
    return values


@pytest.mark.parametrize('park', [False, True])
@pytest.mark.parametrize('pitch', [0., -.08, .08])
def test_simple_auto_stop_reports_hold_unavailable_without_parking_toggle(flow, park, pitch):
    state, truck, engine, ap, update, n, clock, acc, collected = stopping(
        flow, park=park, pitch=pitch)
    parking_offset = engine.controller.scs._offsets['parkingbrake']
    before = engine.controller.scs._buf.getvalue()[parking_offset]
    class Writes(io.BytesIO):
        def write(self, data):
            writes.append((self.tell(), len(data)))
            return super().write(data)
    writes = []
    engine.controller.scs._buf = Writes(engine.controller.scs._buf.getvalue())
    engine._flush_controls()
    record = state.get('autopilot_intervention')
    assert record['code'] == 'STOP_HOLD_UNAVAILABLE'
    assert record['kind'] == 'handover'
    assert record['details']['automatic_hold_supported'] is False
    assert record['details']['automatic_restart_supported'] is False
    assert record['details']['parking_brake_observed'] is park
    assert record['details']['holding_verified'] is False  # Applied SDK flag is not a hill-hold proof.
    evidence = record['details']['decision']
    assert evidence['traffic']['light']['color'] == 'red'
    assert evidence['traffic']['light']['producer_timestamp'] is None
    assert record['sdk_frame_us'] == state.get('telemetry')['truck']['sdkFrameTimeUs']
    assert state.get('autopilot_control_state') == 'driver_handover'
    assert not state.get('autopilot_active')
    assert pedal(engine, 'aforward') == pedal(engine, 'abackward') == 0.
    assert engine.controller.scs._buf.getvalue()[parking_offset] == before
    assert not any(offset <= parking_offset < offset+size for offset, size in writes)
    assert not engine._drive_selector_pressed
    assert state.get('simple_auto_activation_token') is None
    event = collected.samples[-1].longitudinal['events'][-1]
    assert event['intervention'] == record


@pytest.mark.parametrize('next_light', ['green', 'red', None])
def test_handover_never_restarts_from_green_or_disappearing_candidate(flow, next_light):
    state, truck, engine, ap, update, n, clock, acc, collected = stopping(flow)
    engine._flush_controls()
    first = copy.deepcopy(state.get('autopilot_intervention'))
    for _ in range(3):
        update(8, 0.)
        publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0.,
                light_brake=float(next_light == 'red'),
                light=None if next_light is None else {'color': next_light}, following=None)
        acc.on_tick(.05)
        ap.on_tick(.05)
        engine._flush_controls()
        assert not state.get('autopilot_active')
        assert pedal(engine, 'aforward') == pedal(engine, 'abackward') == 0.
        assert state.get('autopilot_intervention') == first
    from core.control_timing import record_control_fault
    record_control_fault(state, 'autopilot', 'later token cleanup')
    assert state.get('autopilot_intervention') == first


@pytest.mark.parametrize('park', [False, True])
@pytest.mark.parametrize('pitch', [0., -.08, .08])
def test_real_auto_retains_service_braking_without_parking_ownership(flow, park, pitch):
    state, truck, engine, ap, update, n, clock, acc, collected = stopping(flow, mode=3, park=park, pitch=pitch)
    engine._flush_controls()
    assert state.get('autopilot_active')
    assert pedal(engine, 'aforward') == 0. and pedal(engine, 'abackward') > 0.
    assert state.get('autopilot_intervention') is None


def test_failed_release_is_not_a_successful_hold_acknowledgement(flow):
    state, truck, engine, ap, update, n, clock, acc, collected = stopping(flow)
    engine.controller.scs._buf.close()
    engine._flush_controls()
    record = state.get('autopilot_intervention')
    assert not state.get('autopilot_active')
    assert record['details']['holding_verified'] is False
    assert record['details']['automatic_restart_supported'] is False
    events = collected.samples[-1].longitudinal['events']
    assert events and all(e['requested_value'] == 0 for e in events)
    assert all(e['backend']['status'] != 'MAPPING_WRITE_RETURNED' for e in events)
    assert all(not e['game_consumption_verified'] for e in events)


def test_consumed_stop_evidence_cannot_be_reassigned_to_later_light(flow):
    state, truck, engine, ap, update, n, clock, acc, collected = stopping(flow)
    from core.longitudinal import engine_decision
    decision, reason = engine_decision(state, state.get('telemetry')['truck'])
    assert not reason
    publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0.,
            light_brake=0., light={'color': 'green'})
    assert decision['stopping_evidence']['traffic']['light']['color'] == 'red'


def test_intervention_is_explicit_handover_in_island():
    from UI.dynamic_island import _intervention_message
    text = _intervention_message({'kind': 'handover', 'reason': 'hold unavailable'})
    assert 'Prevezmite' in text and 'brzdu' in text
    assert 'Technická chyba' not in text and 'Čakám' not in text


def test_nested_release_retains_first_intervention_and_fixed_journal_limits():
    from core.navigation.longitudinal_diagnostics import PedalJournal
    from tests.test_longitudinal_evidence_diagnostics import memory_controller
    controller = memory_controller()
    journal = controller._pedal_journal = PedalJournal()
    journal.enabled = True
    event = {'epoch': 42, 'code': 'STOP_HOLD_UNAVAILABLE', 'kind': 'handover'}
    journal.bind({'activation': 42, 'intervention': event})
    controller.release_all()
    written = journal.drain()['events']
    assert written and all(e['intervention'] == event for e in written)
    assert all(e['requested_value'] == 0. for e in written)
    assert journal.source()['intervention'] == event
    assert journal.CAPACITY == 128 and journal.MAX_BYTES == 65536


@pytest.mark.parametrize('fault', ['expired_light', 'foreign_light', 'reverse', 'backward', 'invalid_sdk'])
def test_untrusted_stop_data_never_authorizes_waiting_or_restart(flow, fault):
    state, truck, engine, ap, update, n, clock, acc, collected = stopping(flow)
    if fault in ('expired_light', 'foreign_light'):
        light = state.get('longitudinal_traffic')
        if fault == 'expired_light':
            light.update(observation_timestamp=clock[0]-.501,
                         computed_at=clock[0]-.501, expires_at=clock[0]-.001)
        else:
            light['context'] = ('old-activation', *light['context'][1:])
        state.set('longitudinal_traffic', light)
    elif fault == 'reverse':
        update(-1, 0.)
    elif fault == 'backward':
        update(8, -.3)
    else:
        update(8, 0., valid=False)
    engine._flush_controls()
    record = state.get('autopilot_intervention')
    if fault in ('expired_light', 'foreign_light'):
        # A positive light-brake demand is required evidence, not optional
        # perception. Its stale/foreign lease must fail before hold/restart.
        assert record['kind'] == 'technical'
        assert record['code'] == 'TECHNICAL_CONTROL_STOP'
        expected = ('longitudinal observation is stale or incoherent'
                    if fault == 'expired_light'
                    else 'longitudinal identity or activation changed')
        assert record['reason'] == 'traffic: ' + expected
        assert record['details']['rejected_source'] == 'traffic'
        assert record['details']['traffic_comparison']['light_brake'] == 1.
        assert record['details']['rejection_cause'] == expected
        assert not state.get('autopilot_active')
    else:
        assert record['kind'] == 'technical'
        assert record['code'] != 'STOP_HOLD_UNAVAILABLE'
    assert pedal(engine, 'aforward') == 0.
    assert not (pedal(engine, 'aforward') > 0 and pedal(engine, 'abackward') > 0)


def test_repeated_profile_error_does_not_hide_different_error(caplog):
    from core.vehicle_profile import VehicleProfileProvider
    from types import SimpleNamespace
    telemetry = Telemetry.__new__(Telemetry)
    valid = VehicleProfileProvider().update(observation(1), 10.)
    caplog.set_level(logging.INFO)
    for failure in ['NONFINITE_SDK_FIELD', '', 'NONFINITE_SDK_FIELD', 'INVALID_SDK_BOOLEAN']:
        profile = replace(valid, observation_failure=failure)
        telemetry.vehicle_profiles = SimpleNamespace(update=lambda o, now: profile)
        with patch('time.monotonic', return_value=10.):
            telemetry._vehicle_profile(observation(1))
    warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == ['Vehicle profile observation: NONFINITE_SDK_FIELD',
                        'Vehicle profile observation: INVALID_SDK_BOOLEAN']


def test_debug_profile_still_contains_wheels(caplog):
    telemetry = Telemetry.__new__(Telemetry)
    caplog.set_level(logging.DEBUG)
    with patch('time.monotonic', return_value=10.):
        telemetry._vehicle_profile(observation(1))
    detailed = [r.message for r in caplog.records if r.message.startswith('Vehicle profile:')]
    assert len(detailed) == 1 and '"wheels"' in detailed[0]


def test_quiet_handover_survives_combined_export_and_inspect(flow, tmp_path, caplog):
    from core.navigation.evidence_diagnostics import EvidenceDiagnosticCollector
    from tests.test_real_evidence_diagnostics import capture, command
    from tools.analyze_longitudinal_evidence import load_rows
    caplog.set_level(logging.WARNING)
    state, truck, engine, ap, update, n, clock, acc, collected = stopping(flow)
    engine._flush_controls()
    first = state.get('autopilot_intervention')
    for _ in range(28):
        update(0, 0., dt=.1)
        engine._flush_controls()
    root = tmp_path / 'evidence-diagnostics'
    exporter = EvidenceDiagnosticCollector(root, capacity=40)
    exporter.apply_command(command(1, collection_id='quiet-stop-handover'))
    for i, saved in enumerate(collected.samples):
        # Existing synthetic profile fixture, not a body/profile confirmation.
        profile = copy.deepcopy(capture(i, when=1000.).profile)
        profile['observation'].update(sdk_frame_us=saved.truck['sdkFrameTimeUs'],
                                      captured_at=saved.captured_at_s)
        profile['observation']['articles'][0]['position_m'] = [saved.truck[k] for k in ('x', 'y', 'z')]
        exporter._ingest(replace(saved, profile=profile))
    exporter.finalize()
    if exporter.status()['state'] != 'READY_FOR_OFFLINE_REVIEW':
        print('Collector finalize status:', exporter.status())
    assert exporter.status()['state'] == 'READY_FOR_OFFLINE_REVIEW', exporter.status()
    rows, verified = load_rows(root / 'quiet-stop-handover')
    assert verified['integrity_valid'] and not verified['confirmed'] and not verified['runtime_authorized']
    events = [e for r in rows for e in r['longitudinal']['events'] if e.get('intervention')]
    assert events and all(e['intervention'] == first for e in events)
    assert any(e['source']['phase'] == 'release' for e in events)
    assert sum('Control intervention' in r.message for r in caplog.records) == 1


def test_island_refreshes_brake_takeover_without_replacing_emergency_cause(flow):
    from PyQt6.QtWidgets import QApplication, QWidget
    from UI.dynamic_island import DynamicIsland
    app = QApplication.instance() or QApplication([])
    state, truck, engine, ap, update, n, clock, acc, collected = started(flow, mode=0)
    publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=1., light_brake=0.)
    engine._flush_controls()
    first = copy.deepcopy(state.get('autopilot_intervention'))
    host = QWidget()
    host.state = state
    island = DynamicIsland(host)
    try:
        island._poll_log()
        assert 'Núdzové' in island.msg_lbl.text()
        update(8, 0.)
        publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=1., light_brake=0.)
        acc.on_tick(.05)
        ap.on_tick(.05)
        engine._flush_controls()
        island._poll_log()
        assert state.get('autopilot_intervention') == first
        assert not state.get('autopilot_active')
        assert 'Prevezmite brzdu' in island.msg_lbl.text()
        assert 'Núdzové' in island.msg_lbl.text()
    finally:
        island.close()
        host.close()


def test_routine_drive_frames_do_not_exhaust_important_event_log(flow, caplog):
    state, truck, engine, ap, update, n, clock, acc, collected = started(flow)
    caplog.set_level(logging.INFO)
    caplog.clear()
    for _ in range(260):
        engine._record_drive_boundary('sdk_gear_observed', truck)
    engine._record_drive_boundary('simple_auto_handoff_complete', truck, throttle=.12)
    assert len(caplog.records) == 1
    assert 'simple_auto_handoff_complete' in caplog.records[0].message
    assert state.get('drive_boundary_event')['action'] == 'simple_auto_handoff_complete'


def test_vehicle_profile_does_not_serialize_full_json_at_info(caplog):
    telemetry = Telemetry.__new__(Telemetry)
    caplog.set_level(logging.INFO)
    from core.vehicle_profile import VehicleProfileProvider
    from types import SimpleNamespace
    profile = VehicleProfileProvider().update(observation(1), 10.)
    telemetry.vehicle_profiles = SimpleNamespace(update=lambda o, now: profile)
    # Fingerprint generation legitimately uses JSON. Isolate only log
    # serialization after the actual provider has already produced a profile.
    with patch('json.dumps', side_effect=AssertionError('full profile serialization at INFO')), \
            patch('time.monotonic', return_value=10.):
        first = telemetry._vehicle_profile(observation(1))
    for i in range(1, 10):
        with patch('time.monotonic', return_value=10.+i):
            telemetry._vehicle_profile(replace(observation(1), captured_at=10.+i, sdk_frame_us=100+i))
    assert sum('Vehicle profile changed' in r.message for r in caplog.records) == 1
    assert first.observation.articles[1].wheels  # Evidence is retained, not stripped.


def test_camera_repeated_fault_quiet_but_new_fault_visible(flow, caplog):
    state, truck, engine, ap, update, n, clock, acc, collected = started(flow)
    engine._last_camera_diagnostic = 0.
    engine._last_camera_diagnostic_signature = None
    engine._last_camera_diagnostic_log = 0.
    caplog.set_level(logging.INFO)
    caplog.clear()
    for _ in range(40):
        clock[0] += 2.
        engine._camera_diagnostic({'valid': False, 'failure_reason': 'MISSING_VIEWPORT'})
    engine._camera_diagnostic({'valid': False, 'failure_reason': 'NEW_CAMERA_FAULT'})
    clock[0] += 2.
    engine._camera_diagnostic({'valid': False, 'failure_reason': 'NEW_CAMERA_FAULT'})
    assert len(caplog.records) == 2
    assert 'NEW_CAMERA_FAULT' in caplog.records[-1].message
    assert state.get('camera_diagnostics')['failure_reason'] == 'NEW_CAMERA_FAULT'
