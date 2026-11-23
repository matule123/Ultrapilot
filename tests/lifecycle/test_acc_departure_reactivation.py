"""Real policy/ACC/AP/Engine/SCS writes; software fixtures are not game evidence."""
import pytest

from core.longitudinal import publish
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_roundabout_intervention_reporting import started, pedal
from tests.lifecycle.test_joint_regressions import joint, traffic_step  # noqa: F401


@pytest.mark.parametrize('mode', [0, 3])
def test_traffic_stop_retains_first_cause_without_inventing_clearance(flow, mode):
    state, truck, engine, ap, update, n, clock, acc, collected = started(flow, mode)
    update(8, 10.)
    publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=.2,
            light_brake=0., brake_basis={'kind': 'directed_crossing_heuristic',
                'confirmed_route_conflict': False, 'producer_timestamp': None})
    acc.on_tick(.033); ap.on_tick(.033); engine._flush_controls()
    assert pedal(engine, 'aforward') == 0.
    assert pedal(engine, 'abackward') > 0.
    original = state.get('simple_auto_service_hold')['stop_reason']
    assert original['brake_basis']['kind'] == 'directed_crossing_heuristic'
    # This does not prove that the actor left the conflict. Withdrawal alone
    # cannot become clearance or rewrite the original consumed stop receipt.
    for _ in range(8):
        update(8, 8.)
        publish(state, state.get('telemetry')['truck'], 'traffic',
                traffic_brake=0., light_brake=0.)
        acc.on_tick(.033); ap.on_tick(.033); engine._flush_controls()
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert state.get('simple_auto_service_hold')['stop_reason'] == original
    assert pedal(engine, 'abackward') > 0.
    assert pedal(engine, 'aforward') == 0.


@pytest.mark.parametrize('mode', [0, 3])
def test_new_epoch_revokes_acc_following_fault_before_invalid_startup_snapshot(flow, mode):
    state, truck, engine, ap, update, n, clock, acc, collected = started(flow, mode)
    acc._followed_target = True
    acc._following_fault = 'old target observation failed'
    acc._following_target_id = 'previous-actor'
    old = acc._following_binding
    n(); update(8, 10.); n()
    assert state.get('autopilot_failure_epoch') != old[0]
    # An invalid acquisition must still publish an invalid zero demand, but it
    # must not carry an old activation's private target latch into this epoch.
    acc.on_tick(.6)
    packet = state.get('longitudinal_acc')
    assert not packet['valid'] and packet['throttle'] == packet['brake'] == 0.
    assert acc._following_fault == ''
    assert not acc._followed_target and acc._following_target_id is None
    update(8, 10.)
    publish(state, state.get('telemetry')['truck'], 'traffic',
            traffic_brake=0., light_brake=0.)
    acc.on_tick(.033); ap.on_tick(.033); engine._flush_controls()
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert not acc._following_fault


@pytest.mark.parametrize('mode', [0, 3])
def test_old_zero_invalid_acc_cannot_cancel_new_epoch_initialization(flow, tmp_path, mode):
    from tests.lifecycle.test_reactivation_traffic import reactivation
    values, step, old_traffic = reactivation(flow, tmp_path, mode)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    old_acc = state.get('longitudinal_acc')
    assert old_acc['context'][0] != state.get('autopilot_failure_epoch')
    state.set('longitudinal_acc', dict(old_acc, valid=False, throttle=0., brake=0.,
        speed_control_reason='previous activation rejected input'))
    start = len(writes)
    tick.policy.on_tick(.02)  # Independent producer cadence: ACC has not run.
    ap.on_tick(.02); engine._flush_controls()
    assert state.get('autopilot_control_state') != 'controlled_stop'
    assert not state.get('autopilot_intervention')
    assert not any(ch == 'aforward' and value > 0 for _, ch, value, _ in writes[start:])
    for generation in range(31, 36):
        step(generation, 'green', speed=2., gear=4)
    assert state.get('autopilot_active'), state.get('navigation_status')
    assert pedal(engine, 'aforward') > 0 and pedal(engine, 'abackward') == 0


def test_actual_crossing_producer_retains_decisive_stop_cause(joint):
    import math
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = joint
    actors = [dict(id=1, x=-15., y=10., z=50., yaw=-math.pi/2, speed=5.)]
    result = traffic_step(joint, actors)
    assert result['crossing']['conflicts']
    demand = state.get('longitudinal_traffic')
    assert 0 < demand['traffic_brake'] <= .7
    assert demand['brake_basis']['kind'] == 'directed_crossing_heuristic'
    hold = state.get('simple_auto_service_hold')
    assert hold['stop_reason']['brake_basis']['decisive']['id'] == 1
    assert hold['stop_reason']['brake_basis']['decisive']['distance_m'] > 0
    assert physical('abackward') > 0 and physical('aforward') == 0


def test_nominal_acceleration_mapping_preserves_exclusive_pedals():
    from core.acc_acceleration import pedal_acceleration
    for value in (0., .0001, .01, .2, .35, 1.):
        for throttle, brake in ((value, 0.), (0., value)):
            actual_throttle, actual_brake, acceleration = pedal_acceleration(throttle, brake)
            assert actual_throttle == pytest.approx(throttle, abs=1e-15)
            assert actual_brake == pytest.approx(brake, abs=1e-15)
            assert acceleration == pytest.approx(2.2*throttle-4.*brake)


@pytest.mark.parametrize('fault', ['current_epoch', 'stale', 'future', 'foreign_route',
                                  'nonzero', 'emergency'])
def test_invalid_acc_quarantine_cannot_mask_current_or_unsafe_input(flow, tmp_path, fault):
    from tests.lifecycle.test_reactivation_traffic import reactivation
    from core.longitudinal import context
    values, step, _ = reactivation(flow, tmp_path)
    state, truck, engine, ap, tick, n, clock, writes, collector = values
    old = state.get('longitudinal_acc')
    value = dict(old, valid=False, throttle=0., brake=0., emergency=False)
    if fault == 'current_epoch':
        value['context'] = context(state)
    elif fault == 'stale':
        value.update(observation_timestamp=clock[0]-.501, computed_at=clock[0]-.501,
                     expires_at=clock[0]-.001)
    elif fault == 'future':
        value.update(observation_timestamp=clock[0]+.1, computed_at=clock[0]+.1,
                     expires_at=clock[0]+.6)
    elif fault == 'foreign_route':
        changed = list(value['context']); changed[4] = 'another-intent'
        value['context'] = changed
    elif fault == 'nonzero':
        value['throttle'] = .12
    else:
        value.update(emergency=True, brake=1.)
    state.set('longitudinal_acc', value)
    start = len(writes)
    tick.policy.on_tick(.02); ap.on_tick(.02); engine._flush_controls()
    assert state.get('autopilot_intervention')
    assert not any(ch == 'aforward' and value > 0 for _, ch, value, _ in writes[start:])


def test_real_policy_worker_survives_missing_startup_speed_then_publishes(monkeypatch):
    import threading
    from core.plugin_manager import plugin_worker
    from plugins.drivepolicy.main import Plugin as Policy
    shared = dict(longitudinal_control_schema=1, telemetry_control_schema=1,
        telemetry={'truck': {}}, autopilot_failure_epoch=1,
        game_session_id='startup', active_map_key='map', active_dataset_fingerprint='data',
        navigation_intent_id='intent', lane_trajectory_revision=1,
        lane_trajectory_identity={'route_build_id':'build'})
    stop = threading.Event(); clock = [1000.]; invalid = []; valid = []
    class Worker(Policy):
        def on_tick(self, dt):
            clock[0] += .02
            if len(invalid) >= 5:
                shared['telemetry'] = {'truck': dict(speed=0., gear=0, speedLimit=0.,
                    parkBrake=False, sdkFrameTimeUs=1000000,
                    _control_observation=dict(schema_version=1, valid=True,
                        sdk_frame_us=1000000, observed_at=clock[0]))}
            super().on_tick(.02)
            packet = shared['longitudinal_policy']
            if packet['valid']:
                valid.append(packet); stop.set()
            else:
                invalid.append(packet)
    monkeypatch.setattr('core.logger.setup', lambda **kw: None)
    monkeypatch.setattr('core.plugin_manager.time.sleep', lambda *_: None)
    monkeypatch.setattr('time.monotonic', lambda: clock[0])
    plugin_worker(Worker, 'drivepolicy', shared, stop)
    assert len(invalid) == 5 and len(valid) == 1
    assert all(p['brake'] == 0. and not p['valid'] for p in invalid)
    assert not shared['plugin_exit.drivepolicy'].get('first_failure')


@pytest.mark.parametrize('speed', [None, float('nan'), 'bad'])
def test_policy_invalid_speed_revokes_plan_without_exception(speed):
    from plugins.drivepolicy.main import Plugin as Policy
    from sdk.plugin_sdk import PluginSDK
    state = dict(telemetry={'truck': {'speed': speed}})
    policy = Policy(PluginSDK(state, 'drivepolicy')); policy.on_start()
    policy.on_tick(.02)
    assert not state['longitudinal_policy']['valid']
    assert state['longitudinal_policy']['brake'] == 0.
    assert state['planned_speed_ms'] is None


def test_policy_startup_unavailability_recovers_full_map_to_backend_without_restart(joint):
    state, engine, ap, acc, policy, tick, observe, n, physical, writes, clock = joint
    n(); engine._flush_controls()
    state.set('telemetry', {'truck': {}})
    for _ in range(6):
        policy.on_tick(.02)
        assert not state.get('longitudinal_policy')['valid']
        assert state.get('longitudinal_policy_active') is True
    # The same actual producer survives. No manager restart, fault-latch clear
    # or invented observation is used to recover after real SDK data arrive.
    tick(gear=0, speed=0., pedals=False)
    policy.on_tick(.033)
    assert state.get('longitudinal_policy')['valid']
    n()
    for gear, speed in [(0, 0.), (4, 0.), (4, .2), (4, 2.), (4, 4.)]:
        tick(gear=gear, speed=speed); engine._flush_controls()
    assert state.get('autopilot_active'), state.get('navigation_status')
    assert physical('aforward') > 0. and physical('abackward') == 0.
