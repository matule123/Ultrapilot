"""Actual producers and returned mapping writes; no ETS2 consumption claim."""
import copy
import json

import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct4_signal_lifecycle import lifecycle
from tests.test_roundabout_intervention_reporting import pedal


def race(flow, mode=0, *, fault=None, warmup_ticks=0):
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow, mode)
    for _ in range(warmup_ticks):
        tick(4, .4)
    tick(4, .3, flush=False)
    initial = state.get('telemetry')['truck']
    fired = []
    command = []
    rereads = []

    def publish_during_command_read(key):
        if key != 'longitudinal_command' or fired:
            return
        fired.append(True)
        state.hook = None
        count = len(writes)
        # The real producer publishes from the next SDK frame while Engine
        # still holds the previous truck snapshot. It performs no physical I/O.
        tick(4, .4, dt=.016666, flush=False)
        assert len(writes) == count
        command.append(copy.deepcopy(state.get('longitudinal_command')))
        if fault in ('future', 'expired'):
            packet = state.get('longitudinal_command')
            if fault == 'future':
                packet['sdk_frame_us'] += 16666
            else:
                packet['expires_at'] = clock[0] + .010
                packet['deadline_basis']['expires_at'] = packet['expires_at']
            state.set('longitudinal_command', packet)
            command[-1] = copy.deepcopy(packet)
        elif fault in ('invalid', 'stale', 'future_timestamp', 'R', 'backward', 'missing'):
            telemetry = state.get('telemetry')
            if fault == 'missing':
                telemetry['truck'] = {}
            elif fault == 'invalid':
                telemetry['truck']['_control_observation']['valid'] = False
            elif fault == 'stale':
                telemetry['truck']['_control_observation']['observed_at'] -= .501
            elif fault == 'future_timestamp':
                telemetry['truck']['_control_observation']['observed_at'] += .01
            elif fault == 'R':
                telemetry['truck']['gear'] = -1
            else:
                telemetry['truck']['speed'] = -.3
            state.set('telemetry', telemetry)
        def during_retry(key):
            if key != 'telemetry':
                return
            state.hook = None
            rereads.append(True)
            assert len(writes) == count  # no pedal I/O before full validation
            if fault == 'expired':
                clock[0] += .015  # SDK stays fresh; pinned decision expires.
            elif fault == 'identity':
                state.set('active_dataset_fingerprint', 'different-dataset')
            elif fault == 'activation':
                state.set('autopilot_failure_epoch', state.get('autopilot_failure_epoch') + 1)
            elif fault == 'disabled':
                state.set('autopilot_active', False)
        state.hook = during_retry

    state.hook = publish_during_command_read
    count = len(writes)
    engine._flush_controls()
    state.hook = None
    assert fired
    return state, engine, initial, command[0], writes[count:], collected


@pytest.mark.parametrize('mode', [0, 3])
def test_new_command_gets_one_actual_observation_before_backend_write(flow, mode):
    state, engine, initial, command, writes, collected = race(flow, mode)
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert pedal(engine, 'aforward') > 0
    assert pedal(engine, 'abackward') == 0
    applied = state.get('longitudinal_applied')
    assert command['sdk_frame_us'] > initial['sdkFrameTimeUs']
    assert applied['sdk_frame_us'] == command['sdk_frame_us']
    event = next(e for e in reversed(collected.samples[-1].longitudinal['events'])
                 if e['channel'] == 'throttle' and e['requested_value'] > 0)
    source = event['source']
    assert source['requested']['sdk_frame_us'] == command['sdk_frame_us']
    assert source['sdk_frame_us'] == command['sdk_frame_us']
    pairing = source['command_observation_pairing']
    assert pairing['reread_count'] == 1
    assert pairing['initial_vehicle']['sdk_frame_us'] == initial['sdkFrameTimeUs']
    assert pairing['compared_vehicle']['sdk_frame_us'] == command['sdk_frame_us']
    assert pairing['checked_after_read_at'] >= command['computed_at']
    if mode == 0:
        assert state.get('simple_auto_forward_history')['last_frame'] == command['sdk_frame_us']
    assert any(ch == 'aforward' and value > 0 for _, ch, value, _ in writes)


@pytest.mark.parametrize('fault', ['future', 'expired', 'identity', 'activation', 'disabled',
                                  'invalid', 'stale', 'future_timestamp', 'R', 'backward', 'missing'])
def test_retry_cannot_bypass_real_failures_or_write_drive_before_validation(flow, fault):
    state, engine, initial, command, writes, collected = race(flow, fault=fault)
    assert not any(ch == 'aforward' and value > 0 for _, ch, value, _ in writes)
    assert pedal(engine, 'aforward') == 0
    # Existing moving safety fallback retains active controlled-stop authority
    # until standstill. Rejection must revoke DRIVE, not erase that safety state.
    assert (not state.get('autopilot_active')
            or state.get('autopilot_control_state') == 'controlled_stop'
            or fault == 'expired' and state.get('longitudinal_refresh_request'))
    if fault == 'future':
        assert 'ahead of vehicle observation' in state.get('automatic_safety_stop_reason')


def test_fault_diagnostics_use_compared_snapshot_not_later_sdk_read(flow):
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow)
    tick(4, .3, flush=False)
    fired = []
    compared = []
    rejected = []

    def concurrent_read(key):
        if key == 'longitudinal_command' and not fired:
            fired.append(True)
            state.hook = None
            tick(4, .4, dt=.016666, flush=False)
            packet = state.get('longitudinal_command')
            packet['sdk_frame_us'] += 16666  # still ahead after the single reread
            state.set('longitudinal_command', packet)
            rejected.append(packet)
            compared.append(state.get('telemetry')['truck'])
            state.hook = concurrent_read
        elif key == 'autopilot_first_fault_engine' and fired:
            state.hook = None
            tick(4, .5, dt=.016666, flush=False)

    state.hook = concurrent_read
    engine._flush_controls()
    fault = state.get('autopilot_first_fault_engine')
    assert fault['sdk_frame_us'] == compared[0]['sdkFrameTimeUs']
    assert fault['observation_timestamp'] == compared[0]['_control_observation']['observed_at']
    assert fault['details']['sdk_frame_us'] == rejected[0]['sdk_frame_us']
    assert fault['details']['command_observation_pairing']['reread_count'] == 1
    assert state.get('telemetry')['truck']['sdkFrameTimeUs'] > fault['sdk_frame_us']
    assert pedal(engine, 'aforward') == 0


def test_normal_command_does_not_reread_vehicle_or_inflate_passive_journal(flow):
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow)
    tick(4, .4)
    source = collected.samples[-1].longitudinal['events'][-1]['source']
    assert source['requested']['sdk_frame_us'] == source['sdk_frame_us']
    assert 'command_observation_pairing' not in source
    assert collected.samples[-1].longitudinal['dropped_events'] == 0


@pytest.mark.parametrize('full_identity', [False, True])
def test_retry_receipt_fits_existing_fault_budget_without_losing_values(flow, full_identity):
    from core.navigation.longitudinal_diagnostics import bounded_fault_details
    from core.longitudinal import capture_command_observation, command_observation_details
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow, full_identity=full_identity)
    initial = state.get('telemetry')['truck']
    tick(4, .4, dt=.016666, flush=False)
    pair = capture_command_observation(state, initial)
    assert pair.provenance['reread_count'] == 1
    foreign = list(pair.binding)
    foreign[1] = 'a-different-game-session'
    for binding in (pair.binding, tuple(foreign)):
        expected = command_observation_details(pair, clock[0], binding=binding)
        actual = bounded_fault_details(expected)
        assert actual == json.loads(json.dumps(expected))  # public JSON uses arrays


@pytest.mark.parametrize('mode', [0, 3])
def test_repeated_publication_races_do_not_replace_activation_or_repeat_retry(flow, mode):
    state, truck, engine, ap, tick, n, clock, writes, collected = lifecycle(flow, mode)
    epoch = state.get('autopilot_failure_epoch')
    for _ in range(20):
        tick(4, .4, flush=False)
        old_frame = truck['sdkFrameTimeUs']
        def concurrent_producer(key):
            if key == 'longitudinal_command':
                state.hook = None
                tick(4, .4, dt=.016666, flush=False)
        state.hook = concurrent_producer
        engine._flush_controls()
        assert state.get('autopilot_active') and not state.get('safety_hazard_active')
        assert state.get('autopilot_failure_epoch') == epoch
        assert pedal(engine, 'aforward') > 0 and pedal(engine, 'abackward') == 0
        paired = collected.samples[-1].longitudinal['events'][-1]['source']['command_observation_pairing']
        assert paired['reread_count'] == 1
        assert paired['initial_vehicle']['sdk_frame_us'] == old_frame
        assert paired['compared_vehicle']['sdk_frame_us'] == truck['sdkFrameTimeUs']


def test_retried_actual_write_survives_existing_combined_export(flow, tmp_path):
    from dataclasses import replace
    from core.navigation.evidence_diagnostics import EvidenceDiagnosticCollector
    from tests.test_real_evidence_diagnostics import capture, command as arm_command
    from tools.analyze_longitudinal_evidence import load_rows
    # Honor the existing minimum of 30 fresh frames; never weaken the exporter
    # or manufacture duplicate evidence just to exercise this additive receipt.
    state, engine, initial, command, writes, collected = race(flow, warmup_ticks=30)
    root = tmp_path/'evidence-diagnostics'
    exporter = EvidenceDiagnosticCollector(root, capacity=120)
    exporter.apply_command(arm_command(1, collection_id='oct7-paired-write'))
    for index, saved in enumerate(collected.samples):
        profile = copy.deepcopy(capture(index, when=1000.).profile)
        profile['observation'].update(sdk_frame_us=saved.truck['sdkFrameTimeUs'],
                                      captured_at=saved.captured_at_s)
        profile['observation']['articles'][0]['position_m'] = [saved.truck[k] for k in ('x', 'y', 'z')]
        exporter._ingest(replace(saved, profile=profile))
    exporter.finalize()
    assert exporter.status()['state'] == 'READY_FOR_OFFLINE_REVIEW', exporter.status()
    rows, checked = load_rows(root/'oct7-paired-write')
    assert checked['integrity_valid'] and len(rows) == len(collected.samples)
    assert checked['confirmed'] is checked['runtime_authorized'] is False
    event = next(e for e in rows[-1]['longitudinal']['events']
                 if e['channel'] == 'throttle' and e['requested_value'] > 0)
    assert event['source']['requested']['sdk_frame_us'] == command['sdk_frame_us']
    assert event['source']['command_observation_pairing']['reread_count'] == 1
    assert event['source']['command_observation_pairing']['compared_vehicle']['sdk_frame_us'] == command['sdk_frame_us']
    assert event['backend']['status'] == 'MAPPING_WRITE_RETURNED'
    assert event['game_consumption_verified'] is False
