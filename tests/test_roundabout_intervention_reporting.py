"""Single physical owner, first stop reason, no unproven gap authorization."""
import logging
import struct
import copy
import math
from dataclasses import replace

import pytest

from core.longitudinal import publish
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_longitudinal_arbitration import strict_flow
from tests.test_longitudinal_evidence_diagnostics import attach


def started(flow, mode=3):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow, mode=mode)
    collected = attach(engine)
    update(8, 10.)
    n()
    acc.on_tick(.033)
    ap.on_tick(.033)
    engine._flush_controls()
    assert state.get('autopilot_active')
    return state, truck, engine, ap, update, n, clock, acc, collected


def pedal(engine, name):
    return struct.unpack_from('f', engine.controller.scs._buf.getvalue(),
                              engine.controller.scs._offsets[name])[0]


@pytest.mark.parametrize('planner_state', ['EMERGENCY', 'AVOID_OBSTACLE'])
def test_old_planner_emergency_cannot_override_current_no_demand_packet(flow, planner_state):
    state, truck, engine, ap, update, n, clock, acc, collected = started(flow)
    # Slower perception/planner can retain its old presentation state while
    # a complete, newer traffic request has already removed that demand.
    publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0., light_brake=0.)
    state.set('system_state', planner_state)
    acc.on_tick(.033)
    ap.on_tick(.033)
    engine._flush_controls()
    assert pedal(engine, 'abackward') == 0
    assert not state.get('longitudinal_applied')['emergency']


def test_engine_only_stop_is_logged_once_and_preserves_causal_reason(flow, caplog):
    state, truck, engine, ap, update, n, clock, acc, collected = started(flow, mode=0)
    caplog.set_level(logging.WARNING)
    # No Plugin tick between first rejection and physical stopping: the exact
    # previously silent Engine path must publish the reason itself.
    clock[0] += .501
    engine._flush_controls()
    first = state.get('autopilot_first_fault_engine')
    assert first and first['reason']
    assert any(first['reason'] in r.message for r in caplog.records)
    engine._flush_controls()
    assert sum('Control intervention' in r.message for r in caplog.records) == 1
    update(0, 0.)
    engine._flush_controls()
    assert not state.get('autopilot_active')
    assert state.get('autopilot_disable_reason') == first['reason']
    assert state.get('autopilot_intervention')['code'] == 'TECHNICAL_CONTROL_STOP'
    assert pedal(engine, 'aforward') == pedal(engine, 'abackward') == 0
    assert state.get('longitudinal_command') is None


@pytest.mark.parametrize('invalid_packet', ['invalid', [1]])
def test_malformed_gps_packet_logging_cannot_interrupt_safe_stop(flow, invalid_packet):
    state, truck, engine, ap, update, n, clock, acc, collected = started(flow)
    state.set('nav_steering_debug', invalid_packet)
    engine._flush_controls()
    first = state.get('autopilot_intervention')
    assert first['reason'] == 'GPS steering packet is incomplete'
    assert first['details']['packet_status'] == 'INVALID_TYPE'
    assert state.get('autopilot_control_state') == 'controlled_stop'
    assert pedal(engine, 'aforward') == 0


def test_new_emergency_after_plugin_tick_is_immediate_bound_and_survives_stop(flow, caplog):
    state, truck, engine, ap, update, n, clock, acc, collected = started(flow, mode=0)
    caplog.set_level(logging.WARNING)
    basis = dict(kind='linear_crossing_heuristic', actor={'target_id': 91},
                 conflict_time_s=.8, producer_timestamp=None, confirmed_route_conflict=False)
    original = publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=1.,
                       light_brake=0., brake_basis=basis)
    engine._flush_controls()  # No intervening AP tick or comfort ramp.
    first = copy.deepcopy(state.get('autopilot_intervention'))
    assert first['code'] == 'EMERGENCY_BRAKE'
    assert first['details']['evidence']['traffic']['brake_basis'] == basis
    assert first['details']['evidence']['traffic']['sdk_frame_us'] == original['sdk_frame_us']
    assert pedal(engine, 'aforward') == 0 and pedal(engine, 'abackward') == 1
    event = collected.samples[-1].longitudinal['events'][-1]
    assert event['intervention'] == first
    assert event['source']['selected']['source'] == 'traffic_emergency'
    engine._flush_controls()
    assert sum('Control intervention' in r.message for r in caplog.records) == 1
    update(0, 0.)
    publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=1., light_brake=0.)
    acc.on_tick(.033)
    ap.on_tick(.033)
    engine._flush_controls()
    assert not state.get('autopilot_active')
    assert state.get('autopilot_disable_reason') == first['reason']
    assert state.get('autopilot_intervention') == first
    assert pedal(engine, 'aforward') == pedal(engine, 'abackward') == 0
    assert not engine._drive_selector_pressed


@pytest.mark.parametrize('fault', ['expired_policy', 'identity'])
def test_rejected_actual_snapshot_and_difference_are_exportable(flow, fault):
    state, truck, engine, ap, update, n, clock, acc, collected = started(flow)
    if fault == 'expired_policy':
        original = publish(state, state.get('telemetry')['truck'], 'policy', brake=0.,
                           planned_speed_ms=20.)
        original.update(observation_timestamp=clock[0]-.501, computed_at=clock[0]-.501,
                        expires_at=clock[0]-.001)
        state.update_batch({'longitudinal_policy': original, 'longitudinal_policy_active': True})
    else:
        original = copy.deepcopy(state.get('longitudinal_command'))
        original['context'] = (*original['context'][:3], 'different-dataset', *original['context'][4:])
        state.set('longitudinal_command', original)
    engine._flush_controls()
    first = state.get('autopilot_intervention')
    details = first['details']
    assert details['actual_context'] == list(original['context']) or details['actual_context'] == original['context']
    if fault == 'expired_policy':
        assert details['source'] == 'policy'
        assert details['observation_age_s'] == pytest.approx(.501)
        assert details['different_fields'] == []
    else:
        assert details['different_fields'] == ['dataset']
    assert pedal(engine, 'aforward') == 0
    events = collected.samples[-1].longitudinal['events']
    assert events[-1]['intervention']['sequence'] == first['sequence']


def test_first_reason_survives_combined_chunk_export_and_analysis(flow, tmp_path):
    from core.navigation.evidence_diagnostics import EvidenceDiagnosticCollector
    from tests.test_real_evidence_diagnostics import capture, command
    from tools.analyze_longitudinal_evidence import load_rows, analyze_rows
    state, truck, engine, ap, update, n, clock, acc, collected = started(flow, mode=0)
    # Fresh SDK, expired pedal lease: the collector must retain this actual
    # valid sample, not disguise a stale SDK sample as accepted evidence.
    update(8, 10., dt=.501)
    engine._flush_controls()
    first = state.get('autopilot_intervention')
    update(0, 0.)
    engine._flush_controls()
    for _ in range(27):
        update(0, 0., dt=.1)
        engine._flush_controls()
    root = tmp_path / 'evidence-diagnostics'
    exporter = EvidenceDiagnosticCollector(root, capacity=30)
    exporter.apply_command(command(1, collection_id='roundabout-first-stop'))
    for i, saved in enumerate(collected.samples):
        profile = copy.deepcopy(capture(i, when=1000.).profile)
        profile['observation'].update(sdk_frame_us=saved.truck['sdkFrameTimeUs'],
                                      captured_at=saved.captured_at_s)
        profile['observation']['articles'][0]['position_m'] = [saved.truck[k] for k in ('x', 'y', 'z')]
        exporter._ingest(replace(saved, profile=profile))
    exporter.finalize()
    assert exporter.status()['state'] == 'READY_FOR_OFFLINE_REVIEW', exporter.status()
    rows, verified = load_rows(root / 'roundabout-first-stop')
    assert verified['integrity_valid'] and not verified['confirmed'] and not verified['runtime_authorized']
    interventions = [e['intervention'] for r in rows for e in r['longitudinal']['events'] if e.get('intervention')]
    assert interventions and all(e['sequence'] == first['sequence'] for e in interventions)
    analyzed = analyze_rows(rows)
    assert any(w['intervention'] and w['intervention']['reason'] == first['reason'] for w in analyzed['write_series'])
    assert analyzed['simultaneous_positive_pair_observations'] == 0


@pytest.mark.parametrize('actor,emergency', [
    (dict(id=71, x=-8., z=-8., yaw=-math.pi/2, speed=8.), True),
    (dict(id=72, x=15., z=-8., yaw=-math.pi/2, speed=8.), False),
    (dict(id=73, x=-8., z=-8., yaw=None, speed=8.), False),
    (dict(id=74, x=-8., z=-8., yaw=-math.pi/2, speed=8., y=8.), False),
])
def test_existing_crossing_guard_and_actual_candidate_basis(flow, actor, emergency):
    state, truck, engine, ap, update, n, clock, acc, collected = started(flow)
    demand = engine._lead_brake([actor], (0., 0.), 0., 8., crossing_only=True)
    assert (demand > .7) == emergency
    publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=demand,
            light_brake=0., brake_basis=engine._traffic_brake_basis)
    acc.on_tick(.033)
    ap.on_tick(.033)
    engine._flush_controls()
    assert state.get('longitudinal_applied')['emergency'] == emergency
    if emergency:
        basis = state.get('autopilot_intervention')['details']['evidence']['traffic']['brake_basis']
        assert basis['actor']['target_id'] == actor['id']
        assert basis['producer_timestamp'] is None
        assert not basis['confirmed_route_conflict'] and not basis['coverage_confirmed']


def test_island_reports_technical_emergency_and_yield_without_creating_authority(flow):
    from PyQt6.QtWidgets import QApplication, QWidget
    from UI.dynamic_island import DynamicIsland, _intervention_message
    app = QApplication.instance() or QApplication([])
    state, truck, engine, ap, update, n, clock, acc, collected = started(flow, mode=0)
    clock[0] += .501
    engine._flush_controls()
    host = QWidget()
    host.state = state
    island = DynamicIsland(host)
    try:
        island._poll_log()
        assert 'Technická chyba' in island.msg_lbl.text()
        assert not island._hide_timer.isActive()
        update(0, 0.)
        engine._flush_controls()
        island._poll_log()
        assert 'Technická chyba' in island.msg_lbl.text()
        assert island._hide_timer.isActive()
        assert 'Núdzové brzdenie' in _intervention_message({'kind': 'emergency'})
        assert 'Čakám na prednosť' in _intervention_message({'kind': 'yield'})
        assert not state.get('autopilot_active')  # Banner never creates authority.
    finally:
        island.close()
        host.close()


def test_slow_planner_does_not_upgrade_technical_stop_but_current_emergency_does(flow):
    state, truck, engine, ap, update, n, clock, acc, collected = started(flow)
    update(8, 10., dt=.501)
    publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0., light_brake=0.)
    state.set('system_state', 'EMERGENCY')
    engine._flush_controls()
    assert state.get('autopilot_control_state') == 'controlled_stop'
    assert 0 < pedal(engine, 'abackward') < .7
    first = copy.deepcopy(state.get('autopilot_intervention'))
    publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=1., light_brake=0.)
    engine._flush_controls()
    assert pedal(engine, 'aforward') == 0 and pedal(engine, 'abackward') == 1
    assert state.get('autopilot_intervention') == first


@pytest.mark.parametrize('stopped', [False, True])
def test_current_emergency_published_during_stop_read_is_not_future_dated(flow, stopped):
    state, truck, engine, ap, update, n, clock, acc, collected = started(flow, mode=0)
    update(8, 10., dt=.501)  # Fresh vehicle, expired active command.
    published = []
    def during_read(key):
        if key == 'longitudinal_traffic' and not published:
            published.append(True)
            state.hook = None
            update(0 if stopped else 8, 0. if stopped else 10., dt=.003)
            publish(state, state.get('telemetry')['truck'], 'traffic',
                    traffic_brake=1., light_brake=0.)
    state.hook = during_read
    engine._flush_controls()
    assert published
    assert state.get('autopilot_control_state') == 'controlled_stop'
    assert pedal(engine, 'aforward') == 0
    assert pedal(engine, 'abackward') == (0 if stopped else 1)
    if stopped:
        assert not state.get('autopilot_active')  # Brake at rest cannot request R.


def test_intervention_does_not_reread_later_actor_or_reuse_previous_activation(flow):
    state, truck, engine, ap, update, n, clock, acc, collected = started(flow)
    basis = dict(kind='linear_crossing_heuristic', actor={'target_id': 91})
    publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=1., light_brake=0., brake_basis=basis)
    swapped = []
    def after_arbitration(key):
        if key == 'autopilot_intervention' and not swapped:
            swapped.append(True)
            state.hook = None
            publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=0., light_brake=0.,
                    brake_basis={'actor': {'target_id': 99}})
    state.hook = after_arbitration
    engine._flush_controls()
    assert swapped and pedal(engine, 'abackward') == 1
    first = state.get('autopilot_intervention')
    assert first['details']['evidence']['traffic']['brake_basis']['actor']['target_id'] == 91
    n()
    engine._flush_controls()
    assert pedal(engine, 'aforward') == pedal(engine, 'abackward') == 0
    update(8, 10.)
    n()
    acc.on_tick(.033)
    ap.on_tick(.033)
    engine._flush_controls()
    assert state.get('autopilot_active')
    assert state.get('autopilot_failure_epoch') != first['epoch']
    assert not collected.samples[-1].longitudinal['events'][-1].get('intervention')


@pytest.mark.parametrize('manual', [False, True])
def test_engine_disable_replay_classification_and_first_cause(flow, tmp_path, manual):
    import json
    from unittest.mock import patch
    state, truck, engine, ap, update, n, clock, acc, collected = started(flow, mode=0)
    for _ in range(22):
        acc.on_tick(update(8, 10.))
        ap.on_tick(.033)
        engine._flush_controls()
    update(8, 10., dt=.501)
    engine._flush_controls()
    first = state.get('autopilot_intervention')
    if manual:
        n()  # Explicit manual off advances the epoch; don't relabel it automatic.
    else:
        update(0, 0.)
    engine._flush_controls()
    assert not state.get('autopilot_active')
    with patch('plugins.autopilot.main.app_dir', return_value=str(tmp_path)):
        ap.on_tick(.033)
    files = list((tmp_path / 'route-diagnostics').glob('steering-replay*.json'))
    assert len(files) == 1
    document = json.loads(files[0].read_text(encoding='utf-8'))
    assert document['reason'] == ('manual_disable' if manual else 'automatic_disable')
    if not manual:
        assert document['identity']['detail'] == first['reason']
        assert document['identity']['control_intervention'] == first
