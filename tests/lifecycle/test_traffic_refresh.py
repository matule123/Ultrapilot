"""Real signal producer/Policy/ACC/AP/Engine/Controller; simulated clocks only.

The native byte fixture is a source acquisition, never a read-time renewal.
Backend mapping writes prove software output, not ETS2 input consumption.
"""
import copy

import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.signals.test_signal_lifecycle import lifecycle
from tests.test_roundabout_intervention_reporting import pedal
from tests.lifecycle.test_joint_regressions import joint  # noqa: F401


def expiring_signal(flow, mode):
    values = lifecycle(flow, mode, full_identity=True)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    old = copy.deepcopy(state.get('longitudinal_traffic'))
    tick(4, 3., dt=.40, flush=False)
    fresh = copy.deepcopy(state.get('longitudinal_traffic'))
    state.set('longitudinal_traffic', old)
    tick.policy.on_tick(.033); tick.acc.on_tick(.033); ap.on_tick(.033)
    command = copy.deepcopy(state.get('longitudinal_command'))
    assert command['valid'] and not command['handoff_required']
    assert command['expires_at'] == old['expires_at']
    state.set('longitudinal_traffic', fresh)
    return values, command


@pytest.mark.parametrize('mode', [0, 3])
@pytest.mark.parametrize('point', ['steering', 'binding'])
def test_traffic_expires_after_selection_gets_bounded_zero_drive_not_disable(flow, monkeypatch, mode, point):
    values, command = expiring_signal(flow, mode)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    original = engine.controller.set_steering if point == 'steering' else engine._bind_longitudinal_output
    delayed = []
    def delay(*args, **kwargs):
        result = original(*args, **kwargs)
        if not delayed and (point == 'steering' or args[0] == 'active'):
            delayed.append(True)
            # Exact incident overrun; producer/SDK renewal occurs during I/O.
            clock[0] = command['expires_at'] + .0011735
            tick(4, 3., dt=.000001, flush=False)
        return result
    if point == 'steering':
        monkeypatch.setattr(engine.controller, 'set_steering', delay)
    else:
        monkeypatch.setattr(engine, '_bind_longitudinal_output', delay)
    first = len(writes)
    engine._flush_controls()
    assert delayed
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert not engine.controller.current_hazard
    assert state.get('longitudinal_applied')['refresh_pending']
    assert not any(ch == 'aforward' and v > 0 for _, ch, v, _ in writes[first:])
    request = state.get('longitudinal_refresh_request')
    assert request['rejected']['valid'] is True
    assert request['rejected']['observation_timestamp'] == command['observation_timestamp']
    assert request['rejected']['expires_at'] == command['expires_at']
    # A genuinely recomputed full decision takes over, with unchanged epoch.
    activation = state.get('autopilot_failure_epoch')
    for _ in range(4):
        tick(4, 3.)
    assert state.get('autopilot_active')
    assert state.get('autopilot_failure_epoch') == activation
    assert pedal(engine, 'aforward') > 0 and pedal(engine, 'abackward') == 0


@pytest.mark.parametrize('mode', [0, 3])
def test_unrecoverable_late_expiry_retains_exact_selected_dependency(flow, monkeypatch, tmp_path, mode):
    values, command = expiring_signal(flow, mode)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    original = engine.controller.set_steering
    engine._automatic_replay_directory = str(tmp_path)
    def delay(value):
        original(value)
        clock[0] = command['expires_at'] + .0011735
        state.set('longitudinal_traffic', None)
    monkeypatch.setattr(engine.controller, 'set_steering', delay)
    engine._flush_controls()
    assert pedal(engine, 'aforward') == 0
    fault = state.get('autopilot_first_fault_engine')
    assert fault and fault['reason'] == 'longitudinal input lease expired before write'
    events = engine.controller._pedal_journal.snapshot()['events']
    safety = next(e for e in events if e['source'].get('phase') == 'safety_stop')
    assert safety['source']['rejected_decision']['expires_at'] == command['expires_at']
    assert safety['source']['rejected_decision']['deadline_basis'] == command['deadline_basis']
    assert safety['source']['requested']['source'] == 'autopilot'
    assert safety['source']['requested']['observation_timestamp'] == command['observation_timestamp']
    assert safety['source']['inputs']['traffic'] is not None
    journal = engine.controller._pedal_journal
    engine._finish_automatic_longitudinal_incident(journal, shutdown=True)
    exported = engine._automatic_replay_writer.wait(5.)
    assert not exported['error'] and exported['path']
    from core.steering_replay import inspect_replay
    checked = inspect_replay(exported['path'])
    assert checked['integrity_valid']
    assert checked['confirmed'] is checked['runtime_authorized'] is False
    block = checked['replay']['longitudinal']
    assert block['first_intervention']['details']['expires_at'] == command['expires_at']
    saved = next(e['source'] for e in block['events'] if e['source'].get('rejected_decision'))
    assert saved['requested']['source'] == 'autopilot'
    assert saved['rejected_decision']['expires_at'] == command['expires_at']
    assert saved['inputs']['traffic']['observation_timestamp'] > command['deadline_basis']['observation_timestamp']
    assert saved['input_read_timing']['traffic'][1] <= saved['input_read_timing']['traffic'][2]


@pytest.mark.parametrize('mode', [0, 3])
def test_valid_short_remaining_lease_is_not_replaced_by_an_extra_timeout(flow, monkeypatch, mode):
    values, command = expiring_signal(flow, mode)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    original = engine.controller.set_steering
    def delay(value):
        original(value)
        clock[0] = command['expires_at'] - .02
    monkeypatch.setattr(engine.controller, 'set_steering', delay)
    first = len(writes)
    engine._flush_controls()
    assert state.get('autopilot_active')
    applied = state.get('longitudinal_applied')
    assert not applied['refresh_pending']
    assert applied['expires_at'] == command['expires_at']
    assert any(ch == 'aforward' and v > 0 for _, ch, v, _ in writes[first:])
    assert all(at <= command['expires_at'] for at, ch, v, _ in writes[first:] if ch == 'aforward' and v > 0)


@pytest.mark.parametrize('mode', [0, 3])
@pytest.mark.parametrize('fault', ['future', 'stale', 'invalid', 'session', 'intent', 'activation', 'reverse'])
def test_late_refresh_cannot_accept_invalid_or_foreign_evidence(flow, monkeypatch, mode, fault):
    values, command = expiring_signal(flow, mode)
    state, truck, engine, ap, tick, n, clock, writes, collected = values
    original = engine.controller.set_steering
    once = []
    def delay(value):
        original(value)
        if once:
            return
        once.append(True)
        clock[0] = command['expires_at'] + .0011735
        traffic = state.get('longitudinal_traffic')
        if fault in ('session', 'intent', 'activation'):
            key = dict(session='game_session_id', intent='navigation_intent_id',
                       activation='autopilot_failure_epoch')[fault]
            state.set(key, 'foreign')
        elif fault == 'future':
            traffic['computed_at'] = clock[0] + .01
        elif fault == 'invalid':
            traffic['valid'] = False
        elif fault == 'stale':
            traffic = command  # wrong source/old dependency is not a renewal
        else:
            tick(-1, -.2, dt=.001, flush=False)
        if fault != 'reverse':
            state.set('longitudinal_traffic', traffic)
    monkeypatch.setattr(engine.controller, 'set_steering', delay)
    first = len(writes)
    engine._flush_controls()
    assert not any(ch == 'aforward' and v > 0 for _, ch, v, _ in writes[first:])
    if fault == 'reverse':
        engine._flush_controls()  # Next actual observation also rejects R.
    assert state.get('autopilot_control_state') == 'controlled_stop' or not state.get('autopilot_active')
    assert pedal(engine, 'aforward') == 0


def native_publish(joint, generation, *, speed=3., emergency=False):
    """The actual timed DLL reader/selector, not manually fabricated IDs."""
    import math
    from types import SimpleNamespace
    from core.navigation.traffic_producer import capture_traffic
    from core.longitudinal import context
    from core.sdk.traffic_snapshot import TrafficReader
    from tests.test_acc_following import capture
    from tests.lifecycle.test_longitudinal_completion import native_bytes
    state, engine, ap, acc, policy, tick, _, _, _, _, clock = joint
    tick(gear=4, speed=speed, z=15., pedals=False)
    truck = state.get('telemetry')['truck']
    raw = capture([dict(id=29, x=2.25, y=10., z=18. if emergency else 80.,
                        yaw=math.pi, speed=0. if emergency else 5.)], clock[0])
    reader = SimpleNamespace(_timed_traffic_reader=TrafficReader())
    reader._timed_traffic_reader.buffer = native_bytes(raw, clock[0], generation,
        truck['sdkFrameTimeUs'], anchor=(truck['x'], truck['y'], truck['z']), ego_speed=speed)
    consumed = capture_traffic(reader, str(context(state)[1]), clock[0])
    following, brake = engine._traffic_control_observation(consumed, truck, context(state), [])
    engine._publish_traffic_control(truck, truck['_control_observation']['observed_at'],
        context(state), [], consumed, following, brake,
        dict(valid=False, candidate=None, reason='no head', coverage={}), None)
    return following


@pytest.mark.parametrize('emergency', [False, True])
def test_source_timed_native_traffic_late_handoff_recomputes_changed_content(joint, monkeypatch, emergency):
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    native_publish(joint, 1)
    old = state.get('longitudinal_traffic')
    clock[0] += .36
    native_publish(joint, 2)
    fresh = state.get('longitudinal_traffic')
    state.set('longitudinal_traffic', old)
    policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033)
    command = state.get('longitudinal_command')
    assert command['deadline_basis']['source'] in ('traffic', 'route_projection')
    assert not command['handoff_required']
    state.set('longitudinal_traffic', fresh)
    original = engine.controller.set_steering
    once = []
    def delay(value):
        original(value)
        if not once:
            once.append(True)
            clock[0] = command['expires_at'] + .0011735
            native_publish(joint, 3, emergency=emergency)
    monkeypatch.setattr(engine.controller, 'set_steering', delay)
    first = len(writes)
    engine._flush_controls()
    assert state.get('autopilot_active'), state.get('autopilot_intervention')
    assert state.get('autopilot_control_state') != 'controlled_stop'
    assert not state.get('autopilot_first_fault_engine')
    assert physical('aforward') == 0.
    assert physical('abackward') == (1. if emergency else 0.)
    assert not any(ch == 'aforward' and v > 0 for _, ch, v in writes[first:])
    if not emergency:
        for generation in range(4, 8):
            native_publish(joint, generation)
            policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033); engine._flush_controls()
        assert physical('aforward') > 0 and physical('abackward') == 0


@pytest.mark.parametrize('mode', [0, 3])
@pytest.mark.parametrize('diagnostics', [False, True])
def test_repeated_late_refresh_and_signal_cycles_exceed_a_minute(flow, monkeypatch, mode, diagnostics):
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow, mode)
    journal = engine.controller._pedal_journal
    journal.enabled = diagnostics
    engine._automatic_longitudinal_diagnostics = diagnostics
    # Model normal unarmed operation. The fixture's unbounded Captures list
    # is a test observation sink, not the production combined collector.
    engine._maneuver_diagnostic_collector = None
    original = engine.controller.set_steering
    next_expiry = [None]
    def delay(value):
        original(value)
        if next_expiry[0] is not None:
            deadline, next_expiry[0] = next_expiry[0], None
            clock[0] = deadline + .0011735
            tick(4, 3., dt=.000001, flush=False)
    monkeypatch.setattr(engine.controller, 'set_steering', delay)
    start = clock[0]
    activation = state.get('autopilot_failure_epoch')
    for cycle in range(125):
        old = state.get('longitudinal_traffic')
        tick(4, 3., dt=.40, flush=False)
        fresh = state.get('longitudinal_traffic')
        state.set('longitudinal_traffic', old)
        tick.policy.on_tick(.033); tick.acc.on_tick(.033); ap.on_tick(.033)
        command = state.get('longitudinal_command')
        state.set('longitudinal_traffic', fresh)
        next_expiry[0] = command['expires_at']
        engine._flush_controls()
        assert state.get('longitudinal_applied')['refresh_pending']
        assert pedal(engine, 'aforward') == 0
        tick(4, 3.); tick(4, 3.)
        assert state.get('autopilot_active') and not engine.controller.current_hazard
        assert state.get('autopilot_failure_epoch') == activation
        if cycle % 25 == 24:
            tick(4, .2, color=2)
            tick(0 if mode == 0 else 4, 0., color=2)
            first = len(writes)
            for _ in range(3):
                tick(0 if mode == 0 else 4, 0., color=2)
            assert all(v > 0 for _, ch, v, _ in writes[first:] if ch == 'abackward')
            assert pedal(engine, 'aforward') == 0 and pedal(engine, 'abackward') > 0
            tick(0 if mode == 0 else 4, 0., color=8)
            tick(0 if mode == 0 else 4, 0., color=8, dt=.12)
            for speed in (.001, .2, .3, 3.):
                tick(4, speed)
            assert pedal(engine, 'aforward') > 0 and pedal(engine, 'abackward') == 0
    assert clock[0] - start > 75.
    assert state.get('autopilot_active') and not state.get('autopilot_first_fault_engine')
    held = {'aforward': 0., 'abackward': 0.}
    for _, ch, v, _ in writes:
        if ch in held:
            held[ch] = v
            assert not all(held.values())
