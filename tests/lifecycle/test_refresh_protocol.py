"""Refresh-response races on real producers, SCS Controller and byte backend.

Injected clocks model IPC scheduling. They do not establish ETS2 consumption.
"""
import copy

import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.lifecycle.test_joint_regressions import joint  # noqa: F401
from tests.lifecycle.test_traffic_refresh import native_publish


def pending(joint):
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    native_publish(joint, 1)
    old = copy.deepcopy(state.get('longitudinal_traffic'))
    clock[0] += .40
    native_publish(joint, 2)
    fresh = state.get('longitudinal_traffic')
    state.set('longitudinal_traffic', old)
    policy.on_tick(.033); acc.on_tick(.033)
    state.set('longitudinal_traffic', fresh)
    clock[0] = old['expires_at'] + .005
    ap.on_tick(.033)
    command = copy.deepcopy(state.get('longitudinal_command'))
    assert command['refresh_pending'], command
    assert command['throttle'] == command['brake'] == 0
    return command


@pytest.mark.parametrize('where', ['receipt', 'steering', 'binding'])
def test_expired_pending_accepts_one_new_complete_reply_through_all_guards(joint, monkeypatch, where):
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    command = pending(joint)
    deadline = command['expires_at']
    # A fresh complete owner reply exists before the fixed refresh deadline.
    clock[0] = deadline - .04
    native_publish(joint, 3)
    policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033)
    reply = copy.deepcopy(state.get('longitudinal_command'))
    assert not reply['refresh_pending'] and reply['valid']
    state.set('longitudinal_command', command)
    original = (engine.controller.set_steering if where == 'steering' else
                engine._bind_longitudinal_output if where == 'binding' else state.get)
    triggered = []
    def publish(*args, **kwargs):
        value = original(*args, **kwargs)
        eligible = where != 'receipt' or args[0] == 'longitudinal_command'
        if where == 'binding':
            eligible = args[0] == 'active'
        if eligible and not triggered:
            triggered.append(True)
            state.set('longitudinal_command', reply)
            clock[0] = deadline + .0014947
        return value
    if where == 'receipt':
        monkeypatch.setattr(state, 'get', publish)
    elif where == 'steering':
        monkeypatch.setattr(engine.controller, 'set_steering', publish)
    else:
        monkeypatch.setattr(engine, '_bind_longitudinal_output', publish)
    first = len(writes)
    engine._flush_controls()
    assert triggered
    assert state.get('autopilot_active'), state.get('autopilot_intervention')
    assert state.get('autopilot_control_state') != 'controlled_stop'
    assert not engine.controller.current_hazard
    assert physical('aforward') > 0 and physical('abackward') == 0
    applied = state.get('longitudinal_applied')
    assert applied['source_observation_timestamp'] == reply['observation_timestamp']
    assert applied['write_started_at'] <= reply['expires_at']
    assert all(not (ch == 'aforward' and v > 0 and at > reply['expires_at'])
               for at, ch, v in writes[first:])


def test_pending_keeps_original_cause_and_token_in_actual_command(joint):
    command = pending(joint)
    state = joint[0]
    request = state.get('longitudinal_refresh_request')
    assert command['refresh_protocol']['token'] == request['token']
    assert command['refresh_protocol']['cause'] == request['rejected']['deadline_basis']
    assert command['deadline_basis']['kind'] == 'bounded_refresh'
    assert command['expires_at'] == request['expires_at']


@pytest.mark.parametrize('fault', ['missing', 'late', 'old_input', 'future', 'foreign',
                                  'reverse', 'invalid_sdk', 'cancel', 'backend'])
def test_fixed_bound_never_authorizes_missing_or_unsafe_response(joint, monkeypatch, fault):
    state, engine, ap, acc, policy, tick, _, n, physical, writes, clock = joint
    command = pending(joint)
    deadline = command['expires_at']
    clock[0] = deadline - .04
    native_publish(joint, 3)
    policy.on_tick(.033); acc.on_tick(.033)
    if fault != 'late':
        ap.on_tick(.033)
    reply = copy.deepcopy(state.get('longitudinal_command'))
    if fault == 'late':
        clock[0] = deadline + .001
        policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033)
        reply = state.get('longitudinal_command')
        assert not reply.get('refresh_protocol')
    elif fault == 'old_input':
        reply = command
    elif fault == 'future':
        reply['computed_at'] = deadline + .05
    elif fault == 'foreign':
        reply['context'] = ('previous-activation', *reply['context'][1:])
    elif fault in ('reverse', 'invalid_sdk'):
        telemetry = state.get('telemetry')
        if fault == 'reverse':
            telemetry['truck'].update(gear=-1, speed=-.2)
        else:
            telemetry['truck']['_control_observation']['valid'] = False
        state.set('telemetry', telemetry)
    elif fault == 'missing':
        reply = None
    state.set('longitudinal_command', command)
    original = engine.controller.set_steering
    once = []
    def publish(value):
        original(value)
        if not once:
            once.append(True)
            clock[0] = deadline + .0014947
            state.set('longitudinal_command', reply)
            if fault == 'cancel':
                n()
            elif fault == 'backend':
                engine.controller.scs.connected = False
    monkeypatch.setattr(engine.controller, 'set_steering', publish)
    first = len(writes)
    engine._flush_controls()
    assert not any(ch == 'aforward' and v > 0 for _, ch, v in writes[first:])
    if fault != 'backend':
        assert physical('aforward') == 0
    else:
        # A disconnected mapping cannot acknowledge even a zero write. Its
        # stale test bytes are not a successful physical output/consumption.
        assert not engine.controller.scs.connected
        assert state.get('ctl_throttle', 0.) == 0
    assert state.get('autopilot_control_state') == 'controlled_stop' or not state.get('autopilot_active')


def test_repeated_pending_does_not_extend_token_and_new_cause_gets_new_token(joint):
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    first = pending(joint)
    request = state.get('longitudinal_refresh_request')
    for _ in range(2):
        clock[0] += .005
        ap.on_tick(.005)
        assert state.get('longitudinal_refresh_request')['token'] == request['token']
        assert state.get('longitudinal_command')['expires_at'] == first['expires_at']
        engine._flush_controls()
        assert physical('aforward') == 0
    # Complete response closes only that token through the actual writer.
    native_publish(joint, 3)
    policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033); engine._flush_controls()
    assert state.get('longitudinal_refresh_completed')['token'] == request['token']
    second = pending(joint)
    assert second['refresh_protocol']['token'] != first['refresh_protocol']['token']
    assert state.get('autopilot_active')


def test_refresh_timeout_export_keeps_original_cause_and_fixed_token(joint, tmp_path):
    from core.steering_replay import inspect_replay
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    command = pending(joint)
    engine._automatic_replay_directory = str(tmp_path)
    clock[0] = command['expires_at'] + .0014947
    engine._flush_controls()
    fault = state.get('autopilot_first_fault_engine')
    assert fault
    assert fault['details']['refresh_protocol']['token'] == command['refresh_protocol']['token']
    journal = engine.controller._pedal_journal
    engine._finish_automatic_longitudinal_incident(journal, shutdown=True)
    export = engine._automatic_replay_writer.wait(5.)
    checked = inspect_replay(export['path'])
    assert checked['integrity_valid'] and not checked['confirmed']
    block = checked['replay']['longitudinal']
    proof = block['first_intervention']['details']['refresh_protocol']
    assert proof == command['refresh_protocol']
    assert block['first_intervention']['details']['refresh_attempt']['candidate']['sdk_frame_us'] == command['sdk_frame_us']
    assert block['events'][-1]['source']['phase'] == 'safety_stop'


def test_response_published_after_fixed_bound_cannot_silently_rearm(joint):
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    command = pending(joint)
    clock[0] = command['expires_at'] + .002
    native_publish(joint, 3)
    policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033)
    assert state.get('longitudinal_command')['valid']
    first = len(writes)
    engine._flush_controls()
    assert not any(ch == 'aforward' and v > 0 for _, ch, v in writes[first:])
    fault = state.get('autopilot_first_fault_engine')
    assert fault['reason'] == 'longitudinal refresh response missed fixed deadline'
    assert fault['details']['refresh_protocol']['token'] == command['refresh_protocol']['token']


def test_completed_ack_cannot_erase_a_concurrently_published_request(joint, monkeypatch):
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    pending(joint)
    original = state.get('longitudinal_refresh_request')
    native_publish(joint, 3)
    policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033)
    reply = state.get('longitudinal_command')
    get = state.get
    sent = []
    def concurrently_publish(key, default=None):
        value = get(key, default)
        applied = state.values.get('longitudinal_applied') or {}
        if (key == 'longitudinal_refresh_request'
                and applied.get('write_started_at', 0.) >= reply['computed_at'] and not sent):
            sent.append(True)
            state.set(key, dict(original, token='next-causal-request'))
        return value
    monkeypatch.setattr(state, 'get', concurrently_publish)
    engine._flush_controls()
    assert sent and state.get('longitudinal_refresh_request')['token'] == 'next-causal-request'
    assert state.get('longitudinal_refresh_completed')['token'] == original['token']


def test_complete_response_can_precede_the_consumers_request_during_ipc(joint, monkeypatch):
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    native_publish(joint, 1)
    old = state.get('longitudinal_traffic')
    clock[0] += .40
    native_publish(joint, 2)
    fresh = state.get('longitudinal_traffic')
    state.set('longitudinal_traffic', old)
    policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033)
    command = state.get('longitudinal_command')
    state.set('longitudinal_traffic', fresh)
    original = engine.controller.set_steering
    published = []
    def publish(value):
        original(value)
        if not published:
            clock[0] = command['expires_at'] + .001
            native_publish(joint, 3)
            policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033)
            published.append(state.get('longitudinal_command'))
            assert not published[-1].get('refresh_protocol')
    monkeypatch.setattr(engine.controller, 'set_steering', publish)
    engine._flush_controls()
    assert state.get('longitudinal_applied')['refresh_pending']
    request = state.get('longitudinal_refresh_request')
    engine._flush_controls()
    assert physical('aforward') > 0
    assert state.get('longitudinal_refresh_completed')['token'] == request['token']
    native_publish(joint, 4)
    policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033); engine._flush_controls()
    assert state.get('autopilot_control_state') != 'controlled_stop'


def test_timely_response_survives_later_owner_ticks_before_engine_ack(joint):
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    command = pending(joint)
    native_publish(joint, 3)
    policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033)
    timely = state.get('longitudinal_command')
    assert timely['computed_at'] < command['expires_at']
    # AP's independently scheduled next tick may replace its slot before
    # Engine writes/acks. A timely full response must not be forgotten.
    clock[0] = command['expires_at'] + .002
    native_publish(joint, 4)
    policy.on_tick(.033); acc.on_tick(.033); ap.on_tick(.033)
    engine._flush_controls()
    assert physical('aforward') > 0
    assert state.get('autopilot_control_state') != 'controlled_stop'
    events = engine.controller._pedal_journal.snapshot()['events']
    source = events[-1]['source']
    witness = source['requested']['refresh_protocol']['publication']
    assert witness['sdk_frame_us'] == timely['sdk_frame_us']
    assert witness['observation_timestamp'] == timely['observation_timestamp']
    assert witness['publish_completed_at'] <= command['expires_at']
    assert source['selected']['refresh_protocol']['publication'] == witness


def run_repeated_response_races(joint, monkeypatch, *, diagnostics=True, cycles=125,
                                export_directory=None, clear_mock_history=False):
    """Independent source/ACC/AP phases + final-boundary IPC publication races.

    This drives a fixed observed speed, NOT a closed-loop vehicle physics model.
    Native source period is ~0.5 s, ACC and AP run at separate causal times;
    Engine captures the previous wait before the new AP publication is delivered.
    """
    import time
    from core.steering_replay import AsyncReplayExporter, SteeringReplayBuffer, inspect_replay
    state, engine, ap, acc, policy, tick, _, _, physical, writes, clock = joint
    engine._maneuver_diagnostic_collector = None
    engine._automatic_longitudinal_diagnostics = diagnostics
    original = engine.controller.set_steering
    delivery = [None]
    def ipc_publication(value):
        original(value)
        if delivery[0] is not None:
            reply, bound = delivery[0]
            delivery[0] = None
            state.set('longitudinal_command', reply)
            clock[0] = bound + .0014947
    monkeypatch.setattr(engine.controller, 'set_steering', ipc_publication)
    start = clock[0]
    wall, cpu, margins, published, received, ages = [], [], [], [], [], []
    recovered, failure = 0, None
    writer = AsyncReplayExporter()
    exports = []
    for cycle in range(cycles):
        command = pending(joint)
        bound = command['expires_at']
        # Alternating phases/RPC completion reserve, all within the fixed bound.
        clock[0] = bound - .048 + (cycle % 4)*.002
        native_publish(joint, 1000+cycle)
        policy.on_tick(.059)
        clock[0] += .001
        acc.on_tick(.023)
        clock[0] += .001
        ap.on_tick(.026)
        reply = state.get('longitudinal_command')
        published.append(reply['expires_at']-clock[0])
        state.set('longitudinal_command', command)
        delivery[0] = (reply, bound)
        before, cpu_before = time.perf_counter(), time.process_time()
        engine._flush_controls()
        wall.append(time.perf_counter()-before)
        cpu.append(time.process_time()-cpu_before)
        applied = state.get('longitudinal_applied') or {}
        if (state.get('autopilot_control_state') == 'controlled_stop'
                or not state.get('autopilot_active') or physical('aforward') <= 0):
            failure = state.get('autopilot_first_fault_engine') or 'drive did not recover'
            break
        recovered += 1
        margins.append(applied['expires_at']-applied['write_started_at'])
        ages.append(applied['write_started_at']-applied['source_observation_timestamp'])
        if diagnostics:
            sources = engine.controller._pedal_journal.snapshot()['events']
            evidence = next((e['source'].get('command_observation_pairing', {}).get('refresh_recovery')
                             for e in reversed(sources)
                             if e['source'].get('command_observation_pairing', {}).get('refresh_recovery')), None)
            assert evidence, 'successful retry provenance must survive the existing journal codec'
            received.append(reply['expires_at']-evidence['received_at'])
        assert margins[-1] >= 0 and ages[-1] <= .5
        if export_directory and cycle % 40 == 39:
            snapshot = engine.controller._pedal_journal.snapshot()
            assert writer.submit(lambda saved=snapshot: SteeringReplayBuffer(2).export(
                export_directory, reason='manual_disable', longitudinal=saved,
                sample_kind='longitudinal_boundary_incident'))
            exports.append(writer.wait(5.)['path'])
        if clear_mock_history:
            # The fixture patches monotonic with unittest.Mock. Its unbounded
            # call journal is not a runtime collector or production allocation.
            reset = getattr(time.monotonic, 'reset_mock', None)
            if reset:
                reset()
    if export_directory and failure is None:
        assert exports and all(inspect_replay(p)['integrity_valid'] for p in exports)
    journal = engine.controller._pedal_journal
    held = {'aforward': 0., 'abackward': 0.}
    for _, channel, value in writes:
        if channel in held:
            held[channel] = value
            assert not all(held.values())
    return dict(duration_s=clock[0]-start, recovered=recovered, failure=failure,
        wall=wall, cpu=cpu, write_margins=margins, publication_margins=published,
        reception_margins=received, observation_ages=ages,
        detail_bytes=journal._bytes, detail_budget=journal.MAX_BYTES,
        exports=len(exports))


@pytest.mark.parametrize('diagnostics', [False, True])
def test_many_distinct_refresh_responses_under_staggered_source_phases(joint, monkeypatch, tmp_path, diagnostics):
    result = run_repeated_response_races(joint, monkeypatch, diagnostics=diagnostics,
        export_directory=tmp_path if diagnostics else None)
    assert result['recovered'] == 125 and not result['failure'], result
    assert result['duration_s'] >= 75.
    assert result['detail_bytes'] <= result['detail_budget']
