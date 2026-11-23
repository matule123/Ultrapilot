"""Oct 3: real producer/Engine IPC ordering and re-engagement lifetime."""
import threading
import struct

import pytest

from core.longitudinal import publish
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_longitudinal_arbitration import strict_flow
from tests.test_phase7_joint_validation import producers, record_pedals
from tests.test_longitudinal_evidence_diagnostics import memory_controller


def running(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(4, .3)
    n()
    policy, eco = producers(state)
    policy.on_tick(.033)
    acc.on_tick(.033)
    ap.on_tick(.033)
    engine._flush_controls()
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    return state, truck, engine, ap, update, n, clock, acc, policy


@pytest.mark.parametrize('slot', ['longitudinal_policy', 'longitudinal_command'])
def test_new_publication_during_engine_ipc_is_not_a_future_packet(flow, slot):
    state, truck, engine, ap, update, n, clock, acc, policy = running(flow)
    writes = record_pedals(engine)

    def publish_during_read(key):
        if key != slot:
            return
        state.hook = None
        # A new computation can use the still-fresh SAME SDK observation.
        # A command from a later SDK frame must remain independently blocked.
        clock[0] += .005
        policy.on_tick(.005)
        if slot == 'longitudinal_command':
            acc.on_tick(.005)
            ap.on_tick(.005)

    state.hook = publish_during_read
    engine._flush_controls()
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert engine.controller.throttle > 0
    assert all(t == 0 or b == 0 for _, _, t, b in writes)


@pytest.mark.parametrize('fault', ['delay', 'future', 'invalid', 'session', 'revision', 'ahead'])
def test_actual_invalid_policy_or_slow_ipc_still_removes_propulsion(flow, fault):
    state, truck, engine, ap, update, n, clock, acc, policy = running(flow)
    if fault == 'delay':
        def slow_read(key):
            if key == 'longitudinal_policy':
                state.hook = None
                clock[0] += .501
        state.hook = slow_read
    elif fault in ('future', 'invalid'):
        value = state.get('longitudinal_policy')
        if fault == 'future':
            value['computed_at'] += .01
        else:
            value['valid'] = False
        state.set('longitudinal_policy', value)
    elif fault == 'ahead':
        value = state.get('longitudinal_command')
        value['sdk_frame_us'] += 1
        state.set('longitudinal_command', value)
    else:
        state.set('game_session_id' if fault == 'session' else 'lane_trajectory_revision', 'changed')
    engine._flush_controls()
    assert engine.controller.throttle == 0


@pytest.mark.parametrize('case', ['ready', 'timeout', 'reverse', 'backwards', 'stale',
                                'manual', 'emergency', 'identity', 'backend'])
def test_first_current_pedal_command_wait_has_fixed_deadline_and_real_writes(flow, case):
    state, truck, engine, ap, update, n, clock, acc, policy = running(flow)
    n()
    engine._flush_controls()
    update(4, .3)
    engine.controller = memory_controller()
    n()

    def pedal(channel):
        return struct.unpack_from('f', engine.controller.scs._buf.getvalue(),
                                  engine.controller.scs._offsets[channel])[0]

    engine._flush_controls()
    assert pedal('aforward') == pedal('abackward') == 0
    assert state.get('autopilot_active')
    started = engine._first_pedal_started_at
    if case == 'timeout':
        for _ in range(3):
            update(4, .3, dt=.15)
            engine._flush_controls()
            assert engine._first_pedal_started_at == started
        update(4, .3, dt=.06)
    elif case == 'reverse':
        update(-1, .3)
    elif case == 'backwards':
        update(4, -.2)
    elif case == 'stale':
        clock[0] += .501
    elif case == 'manual':
        n()
    elif case == 'emergency':
        current = state.get('telemetry')['truck']
        publish(state, current, 'traffic', traffic_brake=.9, light_brake=0., light=None)
    elif case == 'identity':
        state.set('navigation_intent_id', 'other-intent')
    elif case == 'backend':
        engine.controller.scs.connected = False
    else:
        for _ in range(5):
            dt = update(4, .3)
            policy.on_tick(dt)
            acc.on_tick(dt)
            ap.on_tick(dt)
            engine._flush_controls()
            assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
            assert pedal('aforward') > 0 and pedal('abackward') == 0
        n()
        engine._flush_controls()
        assert pedal('aforward') == pedal('abackward') == 0
        assert engine._simple_auto_forward_history is None
        return
    engine._flush_controls()
    assert pedal('aforward') == 0
    assert state.get('autopilot_control_state') == 'controlled_stop' or not state.get('autopilot_active')


def test_one_n_stationary_launch_and_ratio_zero_use_real_controller_writes(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    policy, eco = producers(state)
    engine.controller = memory_controller()
    pairs = []
    original = engine.controller.scs._write_float

    def write(name, value):
        original(name, value)
        if name in ('aforward', 'abackward'):
            pairs.append(tuple(struct.unpack_from('f', engine.controller.scs._buf.getvalue(),
                engine.controller.scs._offsets[k])[0] for k in ('aforward', 'abackward')))

    engine.controller.scs._write_float = write
    n()
    for gear, speed in [(0, 0.), (4, 0.), (0, .02), (4, .15), (4, .3), (4, .5)]:
        dt = update(gear, speed)
        policy.on_tick(dt)
        acc.on_tick(dt)
        ap.on_tick(dt)
        engine._flush_controls()
        assert pairs[-1][0] > 0 and pairs[-1][1] == 0
        assert state.get('auto_drive_pending') or state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert state.get('autopilot_active')
    assert engine._drive_engagement is None
    assert all(t == 0 or b == 0 for t, b in pairs)
    n()
    engine._flush_controls()
    assert pairs[-1] == (0., 0.)


@pytest.mark.parametrize('activation', ['hotkey', 'ui'])
def test_inactive_output_tick_cannot_clear_the_next_activation_history(flow, activation):
    state, truck, engine, ap, update, n, clock, acc, policy = running(flow)
    n()
    engine._flush_controls()
    update(4, .3)
    # This is the production I/O mutex. The new activation and idle release
    # must be serialized, including nested cancellation/release helpers.
    engine._controller_io_lock = threading.RLock()
    original = state.update_batch
    entered = threading.Event()
    finished = threading.Event()
    workers = []

    def publish_activation(batch):
        if batch.get('autopilot_active') is True:
            state.update_batch = original

            def idle_output():
                entered.set()
                engine._flush_controls()
                finished.set()

            worker = threading.Thread(target=idle_output)
            workers.append(worker)
            worker.start()
            assert entered.wait(1.)
            # Before the fix the output tick sees inactive and clears the
            # just-seeded token/history before this activation is published.
            finished.wait(.03)
        original(batch)

    state.update_batch = publish_activation
    if activation == 'hotkey':
        n()
    else:
        state.set('autopilot_command', {'seq': 88, 'enabled': True})
        engine._process_autopilot_command()
    for worker in workers:
        worker.join(1.)
        assert not worker.is_alive()
    assert state.get('simple_auto_activation_token') is not None
    assert state.get('simple_auto_forward_history') is not None
    for _ in range(4):
        dt = update(4, .3)
        policy.on_tick(dt)
        acc.on_tick(dt)
        ap.on_tick(dt)
        engine._flush_controls()
        assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
        assert engine.controller.throttle > 0
