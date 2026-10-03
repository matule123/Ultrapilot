"""Passive provenance; no control/ACC semantics may change."""
import copy
import io
import struct
import time
import threading
from dataclasses import replace

import pytest

from core.controller import Controller
from core.sdk.scs_controller_writer import SCSControlsWriter, _FIELDS, _SIZE
from core.navigation.evidence_diagnostics import capture_diagnostic_application
from tests.test_phase7_joint_validation import State
from tests.test_real_evidence_diagnostics import capture
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_longitudinal_arbitration import strict_flow
from tests.test_phase7_joint_validation import offer_route_candidate
from core.longitudinal import publish
from core.navigation.evidence_diagnostics import EvidenceDiagnosticCollector, inspect_collection
from tests.test_real_evidence_diagnostics import command
from tools.analyze_longitudinal_evidence import analyze_rows, load_rows


def test_combined_capture_retains_sdk_pedals_without_inventing_game_binding():
    template = capture(0)
    state = State({'telemetry': {'truck': {**template.truck, 'gear': 8,
        'gameThrottle': .12, 'gameBrake': 0.}}, 'lane_trajectory': template.lane})
    result = capture_diagnostic_application(state, None, 10., 1)
    assert result.truck['gameThrottle'] == .12
    assert result.longitudinal['events'] == []
    assert result.longitudinal['game_consumption_verified'] is False


def test_actual_controller_exposes_returned_mapping_write_only():
    controller = memory_controller()
    from core.navigation.longitudinal_diagnostics import PedalJournal
    controller._pedal_journal = PedalJournal()
    controller._pedal_journal.enabled = True
    controller.set_brake(0.)
    controller.set_throttle(.12)
    events = controller._pedal_journal.drain()['events']
    assert [e['channel'] for e in events] == ['brake', 'throttle']
    assert events[-1]['backend']['status'] == 'MAPPING_WRITE_RETURNED'
    assert events[-1]['backend']['value'] == struct.unpack('f', struct.pack('f', .12))[0]
    assert events[-1]['source'] is None
    assert events[-1]['game_consumption_verified'] is False


def memory_controller():
    writer = SCSControlsWriter.__new__(SCSControlsWriter)
    writer.connected = True
    writer._buf = io.BytesIO(bytes(sum(_SIZE[t] for _, t in _FIELDS)))
    writer._offsets = {}
    offset = 0
    for name, typ in _FIELDS:
        writer._offsets[name] = offset
        offset += _SIZE[typ]
    writer.invert_steering = False
    writer._retry = 0
    result = Controller.__new__(Controller)
    result.mode = 'SCS_SDK'
    result.scs = writer
    result.current_blinker = 'off'
    result._scs_blinker_button = None
    result._observed_blinker = None
    result._blinker_pending_signature = None
    result._blinker_pending_at = 0.
    result.current_hazard = False
    result._scs_hazard_button = False
    result._blinker_keys = {}
    return result


class Captures:
    state = 'COLLECTING'

    def __init__(self):
        self.samples = []

    def should_sample(self, now):
        return True

    def offer(self, value):
        self.samples.append(value)


def attach(engine):
    engine.controller = memory_controller()
    engine._maneuver_diagnostic_collector = Captures()
    engine._telemetry_lock = threading.Lock()
    engine._latest_telemetry_success = True
    return engine._maneuver_diagnostic_collector


@pytest.mark.parametrize('mode', [0, 3])
def test_launch_whole_engine_write_and_release_are_bound_without_changing_outputs(flow, mode):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow, mode=mode)
    collected = attach(engine)
    n()
    update()
    acc.on_tick(.033)
    engine._flush_controls()
    events = collected.samples[-1].longitudinal['events']
    throttle = next(e for e in events if e['channel'] == 'throttle')
    assert throttle['requested_value'] == (.12 if mode == 0 else 0.)
    assert throttle['source']['phase'] == 'launch'
    assert throttle['source']['sdk_frame_us'] == truck['sdkFrameTimeUs']
    assert throttle['source']['observation_timestamp'] == clock[0]
    assert throttle['source']['requested'] is None  # Not an ACC-authorized command.
    update(8, .2)
    acc.on_tick(.033)
    engine._flush_controls()
    ap.on_tick(update(8, .4))
    acc.on_tick(.033)
    ap.on_tick(.033)
    engine._flush_controls()
    normal = collected.samples[-1].longitudinal['events'][-1]
    assert normal['source']['selected']['throttle'] > 0
    assert normal['source']['inputs']['acc']['control_target_kmh'] is not None
    old = copy.deepcopy(normal)
    state.set('longitudinal_command', {'throttle': .99})
    assert normal == old
    n()
    engine._flush_controls()
    released = [e for c in collected.samples for e in c.longitudinal['events'] if (e.get('source') or {}).get('phase') == 'release']
    assert released and all(e['requested_value'] == 0 for e in released)


@pytest.mark.parametrize('fault', ['acc_brake', 'emergency', 'old_command', 'identity', 'backend_failure'])
def test_actual_arbitration_engine_backend_provenance(flow, fault):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    collected = attach(engine)
    update(8, 10.)
    n()
    acc.on_tick(.033)
    ap.on_tick(.033)
    before = state.get('longitudinal_command')
    if fault == 'acc_brake':
        offer_route_candidate(state, engine, clock)
        publish(state, state.get('telemetry')['truck'], 'acc', throttle=0., brake=.4, emergency=False,
            requested_speed_kmh=50., constrained_speed_kmh=20., control_target_kmh=20.,
            speed_control_reason='speed service brake')
        ap.on_tick(.033)
    elif fault == 'emergency':
        published = publish(state, state.get('telemetry')['truck'], 'traffic', traffic_brake=1., light_brake=0.)
        from core.longitudinal import read, context
        accepted, rejected = read(state, 'traffic', required=True)
        assert accepted is not None, (rejected, published, context(state))
    elif fault == 'old_command':
        update(8, 10., dt=.501)
    elif fault == 'identity':
        state.set('active_dataset_fingerprint', 'new-dataset')
    elif fault == 'backend_failure':
        engine.controller.scs._buf.close()
    engine._flush_controls()
    events = collected.samples[-1].longitudinal['events']
    assert events
    if fault == 'backend_failure':
        assert any(e['backend']['status'] in ('MAPPING_WRITE_FAILED', 'MAPPING_NOT_CONNECTED') for e in events)
        assert not any(e['backend']['status'] == 'MAPPING_WRITE_RETURNED' for e in events)
    else:
        assert all(e['requested_value'] == 0 for e in events if e['channel'] == 'throttle'), (
            events[-1]['source'].get('selected'), events[-1]['source'].get('inputs'))
        assert all(e['pair_after']['throttle'] is None or e['pair_after']['brake'] is None
            or e['pair_after']['throttle'] == 0 or e['pair_after']['brake'] == 0 for e in events)
        if fault == 'emergency':
            assert events[-1]['backend']['value'] == 1.
            assert events[-1]['source']['selected']['source'] == 'traffic_emergency'
        if fault in ('old_command', 'identity'):
            assert events[-1]['source']['phase'] == 'safety_stop'
            # Record the rejected source, never relabel it as fresh/new identity.
            requested = events[-1]['source']['requested']
            if requested is not None:
                assert requested['context'] == list(before['context'])


def test_journal_is_bounded_and_failure_cannot_reuse_previous_success():
    controller = memory_controller()
    from core.navigation.longitudinal_diagnostics import PedalJournal
    journal = controller._pedal_journal = PedalJournal()
    journal.enabled = True
    source = {'context': [1, 's', 'm', 'd', 'i', 1, 'b', 'p'], 'requested': {'throttle': .2}}
    journal.bind(source)
    controller.set_throttle(.2)
    source['requested']['throttle'] = .9
    first = journal.drain()['events'][0]
    assert first['source']['requested']['throttle'] == .2
    controller.scs._buf.close()
    controller.set_throttle(.3)
    failed = journal.drain()['events'][0]
    assert failed['backend']['status'] == 'MAPPING_WRITE_FAILED'
    assert failed['backend']['value'] is None and failed['pair_after']['throttle'] is None
    for _ in range(150):
        journal.record('brake', 0., 1., 1., 'NONE', {'status': 'BACKEND_RESULT_UNVERIFIED'})
    saved = journal.drain()
    assert len(saved['events']) <= journal.CAPACITY
    assert len(saved['events']) + saved['dropped_events'] == 150
    assert journal._bytes == 0 and saved['byte_budget'] == journal.MAX_BYTES


def test_real_engine_export_readback_and_analyzer(flow, tmp_path):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    collected = attach(engine)
    update(8, 10.)
    n()
    for _ in range(30):
        acc.on_tick(update(8, 10., dt=.1))
        ap.on_tick(.1)
        engine._flush_controls()
    root = tmp_path / 'evidence-diagnostics'
    exporter = EvidenceDiagnosticCollector(root, capacity=30)
    exporter.apply_command(command(1, collection_id='pedal-e2e'))
    for index, saved in enumerate(collected.samples):
        # Supply the independently simulated SDK profile that these narrow
        # activation fixtures omit. Pedal context/write/time remains untouched.
        template = capture(index, when=1000.)
        profile = copy.deepcopy(template.profile)
        profile['observation'].update(sdk_frame_us=saved.truck['sdkFrameTimeUs'], captured_at=saved.captured_at_s)
        profile['observation']['articles'][0]['position_m'] = [saved.truck[k] for k in ('x', 'y', 'z')]
        exporter._ingest(replace(saved, profile=profile))
    exporter.finalize()
    assert exporter.status()['state'] == 'READY_FOR_OFFLINE_REVIEW', exporter.status()
    rows, checked = load_rows(root / 'pedal-e2e')
    assert checked['integrity_valid'] is True
    assert checked['confirmed'] is checked['runtime_authorized'] is False
    assert len(rows) == 30
    assert rows[0]['longitudinal']['events'] == collected.samples[0].longitudinal['events']
    result = analyze_rows(rows)
    assert result['returned_mapping_writes'] == 60
    assert result['simultaneous_positive_pair_observations'] == 0
    assert result['write_series'][0]['subsequent_sdk_candidate'] is not None
    assert result['game_consumption_verified'] is False
    # An integrity-checked file must still fail readback when altered later.
    (root / 'pedal-e2e' / 'automatic-observations.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='INTEGRITY'):
        load_rows(root / 'pedal-e2e')


def test_diagnostic_failure_and_disabled_state_do_not_change_backend_contract():
    from core.navigation.longitudinal_diagnostics import PedalJournal
    baseline, diagnosed = memory_controller(), memory_controller()
    journal = diagnosed._pedal_journal = PedalJournal()
    journal.enabled = True
    journal.record = lambda *args: (_ for _ in ()).throw(ValueError('diagnostic failure'))
    for channel, value in [('brake', 0.), ('throttle', .12), ('throttle', 0.), ('brake', 1.)]:
        assert getattr(baseline, 'set_'+channel)(value) is None
        assert getattr(diagnosed, 'set_'+channel)(value) is None
    assert baseline.scs._buf.getvalue() == diagnosed.scs._buf.getvalue()
    journal.enabled = False
    baseline.release_all()
    diagnosed.release_all()
    assert baseline.scs._buf.getvalue() == diagnosed.scs._buf.getvalue()


def test_oversized_snapshot_is_unverified_not_an_unbounded_allocation():
    from core.navigation.longitudinal_diagnostics import PedalJournal, bounded_input
    journal = PedalJournal()
    journal.bind({'requested': {'reason': 'x'*40000}})
    assert journal.source() == {'snapshot_status': 'UNVERIFIED_SNAPSHOT_BUDGET_EXCEEDED'}
    assert bounded_input({'context': ['x'*40000]})['snapshot_status'].startswith('UNVERIFIED')
    journal.enabled = True
    journal.record('throttle', .1, 1., 1., 'SCS_SDK', {'status': 'MAPPING_WRITE_RETURNED', 'value': .1})
    journal.suspend()
    assert journal._held == {'throttle': None, 'brake': None} and not journal.drain()['events']


def test_derivatives_require_original_chronology_and_never_fill_missing_channels():
    def row(t, frame, speed, activation=1, revision=4):
        return dict(telemetry_valid=True, sdk_frame_us=frame, captured_at_s=t,
            observation_identity={'reads_match': True, 'after': {
                'source_game_session_id': 's', 'source_map_key': 'm', 'source_dataset_fingerprint': 'd'}},
            lane={'navigation_intent_id': 'i', 'revision': revision, 'route_build_id': 'b'},
            truck={'speed': speed, '_control_observation': {'valid': True, 'sdk_frame_us': frame, 'observed_at': t}},
            longitudinal={'events': [], 'sampled_state': {'autopilot_active': True, 'activation': activation}})
    rows = [row(1., 1, 1.), row(1.1, 2, 1.2), row(1.2, 3, 1.4),
            row(1.2, 3, 1.4), row(2., 4, 2.), row(2.1, 5, 2.1, revision=5),
            row(2.2, 6, None), row(2.3, 7, 2.3)]
    result = analyze_rows(rows)
    assert result['acceleration_mps2']['n'] == 2
    assert result['acceleration_mps2']['mean'] == pytest.approx(2.)
    assert result['jerk_mps3']['n'] == 1
    assert abs(result['jerk_mps3']['maximum']) < 1e-10
    assert result['observation_series'][0]['game_throttle'] is None
    assert result['returned_mapping_writes'] == 0
    assert result['excluded']['invalid_or_missing_original_observation_time'] == 1


def test_engine_output_matches_without_diagnostics_and_measure_overhead(flow, tmp_path):
    """Paired in-process measurement, not an ETS2/IPC latency claim."""
    import json
    from collections import deque

    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    collected = attach(engine)
    collected.samples = deque(maxlen=1)
    update(8, 10.)
    n()
    acc.on_tick(.033)
    ap.on_tick(.033)
    elapsed = {False: [], True: []}
    # Identical immutable command, steering packet and clock for each pair.
    for _ in range(500):
        original = copy.deepcopy(state.values)
        pair = []
        for enabled in (False, True):
            state.values.clear()
            state.values.update(copy.deepcopy(original))
            engine._maneuver_diagnostic_collector = collected if enabled else None
            start = time.perf_counter_ns()
            engine._flush_controls()
            elapsed[enabled].append((time.perf_counter_ns()-start)/1000.)
            pair.append(engine.controller.scs._buf.getvalue())
        assert pair[0] == pair[1]
    from tools.analyze_phase6_stage1 import distribution
    report = {'iterations_per_mode': 500, 'microseconds': {
        'disabled': distribution(elapsed[False]), 'enabled': distribution(elapsed[True])},
        'paired_overhead_us': distribution([b-a for a,b in zip(elapsed[False], elapsed[True])]),
        'outputs_byte_identical': True,
        'scope': 'Actual Engine/arbitration/Controller/capture; in-process deep-copy IPC fixture and BytesIO mapping; capture on EVERY flush, bounded one-element offer sink; excludes OS IPC, real mmap latency, worker/disk/export.'}
    (tmp_path/'overhead.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('\nPEDAL_DIAGNOSTIC_OVERHEAD '+json.dumps(report))


def test_chunked_pedal_evidence_retains_bound_events_and_hash_checks(tmp_path):
    from core.navigation.longitudinal_diagnostics import PedalJournal
    controller = memory_controller()
    journal = controller._pedal_journal = PedalJournal()
    journal.enabled = True
    root = tmp_path/'evidence-diagnostics'
    collector = EvidenceDiagnosticCollector(root, capacity=150)
    collector.apply_command(command(1, collection_id='pedal-chunks'))
    for index in range(150):
        value = capture(index)
        source = dict(context=[1, 'session-a', 'map-a', 'dataset-a', 'intent-a', 4, 'build-a', 'pub'],
            sdk_frame_us=value.truck['sdkFrameTimeUs'], observation_timestamp=value.captured_at_s,
            decision_sequence=index+1, activation=1, phase='active', requested={'throttle': .12, 'brake': 0.})
        journal.bind(source)
        controller.set_brake(0.)
        controller.set_throttle(.12)
        collector._ingest(replace(value, longitudinal=journal.drain()))
    collector.finalize()
    assert collector.status()['state'] == 'READY_FOR_OFFLINE_REVIEW', collector.status()
    rows, checked = load_rows(root/'pedal-chunks')
    assert len(rows) == 150 and checked['integrity_valid']
    assert rows[-1]['longitudinal']['events'][-1]['source']['decision_sequence'] == 150
    import json
    manifest = json.loads((root/'pedal-chunks'/'manifest.json').read_text(encoding='utf-8'))
    chunk = next(e for e in manifest['files'] if e.get('role') == 'chunk')
    (root/'pedal-chunks'/chunk['name']).unlink()
    with pytest.raises(ValueError, match='INTEGRITY'):
        load_rows(root/'pedal-chunks')


def test_new_packet_during_backend_call_cannot_relabel_older_write(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    collected = attach(engine)
    update(8, 10.)
    n()
    acc.on_tick(.033)
    ap.on_tick(.033)
    original_command = state.get('longitudinal_command')
    original_acc = state.get('longitudinal_acc')
    physical = engine.controller.scs.set_throttle

    def interleave(value):
        newer = state.get('longitudinal_command')
        newer.update(throttle=.99, computed_at=clock[0]+.01, sdk_frame_us=truck['sdkFrameTimeUs']+100)
        state.set('longitudinal_command', newer)
        state.set('longitudinal_acc', {'control_target_kmh': 999.})
        physical(value)

    engine.controller.scs.set_throttle = interleave
    engine._flush_controls()
    event = collected.samples[-1].longitudinal['events'][-1]
    assert event['source']['requested']['sdk_frame_us'] == original_command['sdk_frame_us']
    assert event['source']['requested']['throttle'] == original_command['throttle']
    assert event['source']['inputs']['acc']['control_target_kmh'] == original_acc['control_target_kmh']
    assert event['backend']['value'] == pytest.approx(original_command['throttle'])


def test_raised_backend_exception_keeps_failure_event_and_exception():
    from core.navigation.longitudinal_diagnostics import PedalJournal
    controller = memory_controller()
    journal = controller._pedal_journal = PedalJournal()
    journal.enabled = True

    def fail(value):
        raise OSError('offline failure')

    controller.scs.set_brake = fail
    with pytest.raises(OSError):
        controller.set_brake(.4)
    event = journal.drain()['events'][0]
    assert event['call_returned'] is False and event['error'] == 'OSError'
    assert event['backend']['value'] is None


def test_rejected_partial_export_keeps_original_pedal_binding(tmp_path):
    from core.navigation.longitudinal_diagnostics import PedalJournal
    controller = memory_controller()
    journal = controller._pedal_journal = PedalJournal()
    journal.enabled = True
    root = tmp_path/'evidence-diagnostics'
    collector = EvidenceDiagnosticCollector(root, capacity=30)
    collector.apply_command(command(1, collection_id='pedal-partial'))
    template = capture(0)
    journal.bind({'sdk_frame_us': template.truck['sdkFrameTimeUs'], 'observation_timestamp': 10.,
                  'decision_sequence': 1, 'phase': 'active'})
    controller.set_throttle(.12)
    accepted = replace(template, longitudinal=journal.drain())
    collector._ingest(accepted)
    changed = capture(1, map_key='changed-map')
    collector._ingest(changed)
    assert collector.status()['state'] == 'REJECTED_IDENTITY_CHANGED'
    collector.finalize()
    assert collector.status()['state'] == 'REJECTED_EXPORTED'
    rows, checked = load_rows(root/'pedal-partial')
    assert checked['integrity_valid'] and len(rows) == 1
    assert rows[0]['longitudinal']['events'] == accepted.longitudinal['events']
    assert checked['confirmed'] is checked['runtime_authorized'] is False
