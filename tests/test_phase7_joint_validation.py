"""Phase 7.4: joint producer/physical-boundary and existing export scope.

The export-scope test distinguishes bound writes from unrelated shared mirrors.
"""
from dataclasses import replace
from itertools import permutations

import pytest

from core.longitudinal import publish
from core.navigation.evidence_diagnostics import (
    EvidenceDiagnosticCollector, capture_diagnostic_application,
    inspect_collection, read_json,
)
from plugins.drivepolicy.main import Plugin as Policy
from plugins.ecodrive.main import Plugin as Eco
from sdk.plugin_sdk import PluginSDK
from tests.test_acc_following import arc, capture, car_on, route_input
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_control_safety_regressions import State
from tests.test_longitudinal_arbitration import strict_flow
from tests.test_real_evidence_diagnostics import capture as diagnostic_capture, command


def producers(state):
    policy = Policy(PluginSDK(state.values, 'drivepolicy'))
    eco = Eco(PluginSDK(state.values, 'ecodrive'))
    policy.on_start()
    eco.on_start()
    return policy, eco


def offer_route_candidate(state, engine, clock):
    truck = state.get('telemetry')['truck']
    points = arc()
    binding = route_input(state, engine, truck, points)
    captured = capture([car_on(points, 70, speed=10.)], clock[0])
    captured = replace(captured, session=str(binding[1]))
    following = engine._route_lead_observation(captured, truck, binding)
    assert following['status'] == 'candidate'
    assert following['confirmed'] is False
    publish(state, truck, 'traffic', traffic_brake=0., light_brake=0.,
            light=None, lead_distance=following['gap_m'], following=following,
            expires_at=following['expires_at'])
    return following


def record_pedals(engine):
    writes = []
    for key in ('throttle', 'brake'):
        original = getattr(engine.controller, 'set_' + key)

        def record(value, key=key, original=original):
            original(value)
            writes.append((key, value, engine.controller.throttle, engine.controller.brake))

        setattr(engine.controller, 'set_' + key, record)
    return writes


@pytest.mark.parametrize('mode', [0, 3])
def test_one_n_joint_launch_then_constraint_following_emergency_and_disable(flow, mode):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow, mode=mode)
    policy, eco = producers(state)
    writes = record_pedals(engine)
    n()
    # All required producers get a new-activation observation before launch.
    update()
    policy.on_tick(.033)
    eco.on_tick(.033)
    acc.on_tick(.033)
    engine._flush_controls()
    assert engine.controller.throttle == (.12 if mode == 0 else 0.)
    assert engine.controller.drive_events.count(True) == (0 if mode == 0 else 1)
    update(8, .2)
    policy.on_tick(.033)
    acc.on_tick(.033)
    engine._flush_controls()
    dt = update(8, .4)
    policy.on_tick(dt)
    eco.on_tick(dt)
    acc.on_tick(dt)
    ap.on_tick(dt)
    engine._flush_controls()
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert engine.controller.throttle > 0

    # Same live consumers now combine actual route selection, map and curve.
    dt = update(8, 12., dt=.08)
    following = offer_route_candidate(state, engine, clock)
    current = state.get('telemetry')['truck']
    publish(state, current, 'road', speed_cap_kmh=30.)
    debug = state.get('nav_steering_debug')
    debug['longitudinal_curve_profile'] = {'radius_m': 83., 'distance_m': 0.}
    state.set('nav_steering_debug', debug)
    policy.on_tick(dt)
    eco.on_tick(dt)
    acc.on_tick(dt)
    request = state.get('longitudinal_acc')
    assert request['following_required']
    assert request['constrained_speed_kmh'] <= min(30., following['speed_cap_mps']*3.6)
    ap.on_tick(dt)
    engine._flush_controls()
    assert engine.controller.throttle == 0
    assert engine.controller.brake > 0
    applied = state.get('longitudinal_applied')
    assert applied['throttle'] == engine.controller.throttle
    assert applied['brake'] == engine.controller.brake
    assert applied['source_sdk_frame_us'] == current['sdkFrameTimeUs']
    assert applied['written_at'] == clock[0]

    # New emergency after every Plugin tick: no comfort/producer-order wait.
    publish(state, current, 'traffic', traffic_brake=.9, light_brake=0.,
            light=None, following=following)
    engine._flush_controls()
    assert engine.controller.throttle == 0
    assert engine.controller.brake == 1.
    assert state.get('longitudinal_applied')['source'] == 'traffic_emergency'

    n()
    engine._flush_controls()
    assert engine.controller.throttle == engine.controller.brake == 0
    assert state.get('longitudinal_command') is None
    assert all(t == 0 or b == 0 for _, _, t, b in writes)


@pytest.mark.parametrize('order', list(permutations(('road', 'traffic', 'eco'))))
def test_joint_latest_sources_cannot_restore_drive_by_update_order(flow, order):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 12.)
    n()
    policy, eco = producers(state)
    following = offer_route_candidate(state, engine, clock)
    policy.on_tick(.033)
    acc.on_tick(.033)
    ap.on_tick(.033)
    assert state.get('longitudinal_command')['throttle'] > 0
    current = state.get('telemetry')['truck']
    writes = record_pedals(engine)
    # An already composed positive command exists. Only latest sources change.
    for source in order:
        if source == 'road':
            publish(state, current, 'road', speed_cap_kmh=20.)
        elif source == 'traffic':
            publish(state, current, 'traffic', traffic_brake=.9, light_brake=0.,
                    light=None, following=following)
        else:
            eco.on_tick(.033)
    engine._flush_controls()
    assert engine.controller.throttle == 0 and engine.controller.brake == 1.
    assert state.get('longitudinal_applied')['source'] == 'traffic_emergency'
    assert all(t == 0 or b == 0 for _, _, t, b in writes)


@pytest.mark.parametrize('fault', ['previous_activation', 'source_expired', 'identity'])
def test_joint_following_pipeline_rejects_late_old_authority(flow, fault):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 10.)
    n()
    policy, eco = producers(state)
    offer_route_candidate(state, engine, clock)
    policy.on_tick(.05)
    eco.on_tick(.05)
    acc.on_tick(.05)
    ap.on_tick(.05)
    engine._flush_controls()
    previous = state.get('longitudinal_command')
    assert engine.controller.throttle > 0
    if fault == 'previous_activation':
        n()
        engine._flush_controls()
        assert engine.controller.throttle == engine.controller.brake == 0
        update(8, 10.)
        n()
        offer_route_candidate(state, engine, clock)
        policy.on_tick(.05)
        eco.on_tick(.05)
        acc.on_tick(.05)
        ap.on_tick(.05)
        # A late completion from the cancelled activation cannot overwrite it.
        state.set('longitudinal_command', previous)
    elif fault == 'source_expired':
        # New vehicle/steering data cannot renew the old traffic/PID lease.
        update(8, 10., dt=.501)
    else:
        state.set('active_dataset_fingerprint', 'different-dataset')
    engine._flush_controls()
    assert engine.controller.throttle == 0
    assert not (engine.controller.throttle > 0 and engine.controller.brake > 0)


def test_existing_combined_export_preserves_steering_and_marks_unbound_pedals(tmp_path):
    """Export cannot claim Phase 7 readiness merely because integrity passes."""
    root = tmp_path / 'evidence-diagnostics'
    collector = EvidenceDiagnosticCollector(root, capacity=30)
    collector.apply_command(command(1, collection_id='phase74-isolated-schema'))
    for index in range(30):
        template = diagnostic_capture(index)
        lane = template.lane
        state = State({
            'game_session_id': lane['source_game_session_id'],
            'active_map_key': lane['source_map_key'],
            'active_dataset_fingerprint': lane['source_dataset_fingerprint'],
            'autopilot_active': True, 'telemetry_valid': True,
            'telemetry': {'truck': {**template.truck, 'userThrottle': .1, 'gameThrottle': .2,
                                    'userBrake': 0., 'gameBrake': 0.}},
            'vehicle_profile_snapshot': template.profile,
            'maneuver_traffic_capture': template.traffic_capture,
            'lane_trajectory': lane,
            'active_navigation_reference': template.reference,
            'maneuver_diagnostic_applied_target': template.applied_target,
            'longitudinal_command': {'throttle': .2, 'brake': 0., 'reason': 'normal drive'},
            'longitudinal_applied': {'throttle': .2, 'brake': 0.,
                                     'written_at': template.captured_at_s, 'source': 'acc'},
            'longitudinal_acc': {'requested_speed_kmh': 50., 'control_target_kmh': 40.,
                                 'constrained_speed_kmh': 40.},
            'longitudinal_traffic': {'following': {'status': 'candidate', 'target_id': '7',
                                                   'gap_m': 40., 'confirmed': False}},
            'autopilot_disable_reason': '', 'automatic_safety_stop_reason': '',
        })
        captured = capture_diagnostic_application(
            state, .2, template.captured_at_s, index+1,
            application_sdk_frame_us=template.truck['sdkFrameTimeUs'],
            steering_write_returned_at_s=template.captured_at_s)
        # Live state changes after capture must not relabel its source packet.
        state.get('maneuver_diagnostic_applied_target')['source_packet']['calculation_sequence'] = -1
        assert captured.applied_target['source_packet']['calculation_sequence'] == index+1
        collector._ingest(captured)
    collector.finalize()
    status = collector.status()
    assert status['state'] == 'READY_FOR_OFFLINE_REVIEW', status
    target = root / 'phase74-isolated-schema'
    result = inspect_collection(target)
    assert result['integrity_valid'] is True
    assert result['confirmed'] is result['runtime_authorized'] is False
    rows = read_json(target / 'automatic-observations.json')['samples']
    assert len(rows) == 30
    for index, row in enumerate(rows):
        assert row['speed_mps'] == 3.
        assert row['autopilot_active'] is True
        assert row['sdk_frame_us'] == 1_000_000+index
        assert row['executor']['source_packet']['calculation_sequence'] == index+1
        assert row['steering_boundary']['steering_write_returned_at_s'] == row['captured_at_s']
        assert row['command_binding_proven'] is True
        for missing in ('longitudinal_command', 'longitudinal_applied', 'longitudinal_acc',
                        'longitudinal_traffic', 'autopilot_disable_reason',
                        'automatic_safety_stop_reason'):
            assert missing not in row
        assert row['truck']['gameThrottle'] == .2 and row['truck']['gameBrake'] == 0.
        assert row['longitudinal']['events'] == []
        assert row['longitudinal']['game_consumption_verified'] is False
