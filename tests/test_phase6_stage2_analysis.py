"""Active source measurements cannot include manual rows or invented writes."""
import json
import math

import pytest

from tools import analyze_phase6_stage2 as analysis


def inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis, 'inspect_collection', lambda _: {'integrity_valid': True})
    monkeypatch.setattr(analysis, 'collection_report', lambda _: {})
    monkeypatch.setattr(analysis, 'replay_report', lambda _: {})
    collection = tmp_path / 'collection'
    collection.mkdir()
    (collection / 'manifest.json').write_text(json.dumps({'files': [], 'dropped_samples': 0}))
    source = dict(navigation_intent_id='intent', route_build_id='build',
        authority_revision=8, source_game_session_id=1, source_map_key='map',
        source_dataset_fingerprint='dataset', sdk_frame_us=100, calculation_sequence=1,
        observation_timestamp=10., computed_at=10.01, authority_valid=True,
        lane_match_snapshot={'active_lane_id': {'road_uid': 5337536093791584855},
                             'lateral_error_m': 1.},
        body_tracking_error_rad=.01, observation_speed_ms=3., tracking_progress_m=0.)
    second = dict(source, sdk_frame_us=101, calculation_sequence=2,
        observation_timestamp=10.7, computed_at=10.71,
        lane_match_snapshot={**source['lane_match_snapshot'], 'lateral_error_m': 2.},
        tracking_progress_m=3.)
    execution = lambda s, t: dict(source_packet=s, executor_active=True, execution_monotonic_s=t)
    replay = tmp_path / 'replay.json'
    replay.write_text(json.dumps({'execution_samples': [execution(source,10.02),
        execution(source,10.03), execution(second,10.72),
        execution(dict(second, calculation_sequence=3, authority_valid=False),10.73)]}))
    write = dict(captured_at_s=10.04, autopilot_active=True, backend_sent=True,
        command_binding_proven=True, engine_steer=.2,
        executor=dict(source_packet=source, output=.2),
        steering_boundary={'steering_write_returned_at_s':10.04})
    (collection/'automatic-observations.json').write_text(json.dumps({'samples': [write,
        dict(write, autopilot_active=False), dict(write, command_binding_proven=False)]}))
    timing = tmp_path/'timing.json'
    timing.write_text(json.dumps({'samples': []}))
    return collection, replay, timing


def test_window_identity_and_binding_precede_metrics(tmp_path, monkeypatch):
    paths = inputs(tmp_path, monkeypatch)
    r = analysis.analyze(*paths, 'build', 10., 11.)
    assert r['active_source_packets'] == 2  # Repeated execution is not a new pose.
    assert r['active_measurements']['cte_rms_m'] == pytest.approx(math.sqrt(2.5))
    assert r['active_measurements']['cte_time_weighted_rms_m'] is None  # No weight over the gap.
    assert r['submitted_intervals_above_500ms'] == 1  # Do not censor missing packets.
    assert r['sampled_write_count'] == 1
    assert r['excluded_writes']['outside_active_build_or_window'] == 1
    assert r['excluded_writes']['unbound_physical_write'] == 1
    assert r['excluded_sources']['invalid_or_incomplete_source'] == 1


def test_two_active_sessions_are_not_pooled(tmp_path, monkeypatch):
    paths = inputs(tmp_path, monkeypatch)
    replay = json.loads(paths[1].read_text())
    replay['execution_samples'][2]['source_packet']['source_game_session_id'] = 2
    paths[1].write_text(json.dumps(replay))
    with pytest.raises(ValueError, match='AMBIGUOUS_ACTIVE_ROUTE_IDENTITY'):
        analysis.analyze(*paths, 'build', 10., 11.)


def test_invalid_integrity_prevents_analysis(tmp_path, monkeypatch):
    paths = inputs(tmp_path, monkeypatch)
    monkeypatch.setattr(analysis, 'inspect_collection', lambda _: {'integrity_valid': False})
    with pytest.raises(ValueError, match='INVALID_COLLECTION_INTEGRITY'):
        analysis.analyze(*paths, 'build', 10., 11.)
