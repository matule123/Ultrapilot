"""The offline report must not hide gaps, missing data or reference changes."""
import math
import json
from datetime import datetime

from tools.analyze_phase6_stage1 import distribution, summarize, replay_report, log_report


def row(t, cte, *, identity='route-a', phase='active', steer=None):
    return dict(time_s=t, cte_m=cte, identity=identity, phase=phase,
                reference='cab', steer=steer, heading_rad=None)


def test_rms_is_from_signed_samples_not_mean_error():
    result = summarize([row(0, -3), row(.1, 4)])
    assert result['cte_rms_m'] == math.sqrt(12.5)
    assert result['cte_abs']['mean'] == 3.5
    assert result['cte_abs']['p95'] == 3.95


def test_time_weighted_rms_uses_elapsed_intervals_not_sample_count():
    result = summarize([row(0, 3), row(1, 4), row(4, 8)], gap_s=5)
    assert result['cte_time_weighted_rms_m'] == math.sqrt((9+16*3)/4)
    assert result['cte_weighted_duration_s'] == 4


def test_identity_state_gap_and_missing_cte_are_not_interpolated():
    rows = [row(0, 1), row(.1, None), row(.2, 3),
            row(.3, 20, identity='route-b'), row(.4, 30, phase='manual'),
            row(2, 100, phase='manual')]
    result = summarize(rows)
    assert result['segments'] == 4
    assert result['cte_time_weighted_rms_m'] is None
    assert result['cte_missing_or_invalid'] == 1
    assert result['heading_abs_rad']['n'] == 0
    assert result['known_saturation_time_s'] is None


def test_derivatives_use_actual_time_and_midpoint_spacing():
    result = summarize([row(0, None, steer=0), row(.1, None, steer=.1),
                        row(.3, None, steer=.5)])
    assert math.isclose(result['steering_rate_abs_per_s']['maximum'], 2)
    assert math.isclose(result['steering_acceleration_abs_per_s2']['maximum'], 1/.15)
    assert result['cte_rms_m'] is None


def test_nonfinite_values_and_boolean_channels_are_not_measurements():
    result = distribution([None, float('nan'), float('inf'), True, 2])
    assert result['n'] == 1
    assert result['rms'] == 2


def test_backwards_clock_breaks_derivative_chain():
    result = summarize([row(1, 1, steer=1), row(.9, 1, steer=-1)])
    assert result['segments'] == 2
    assert result['steering_step']['n'] == 0


def test_rejected_packet_does_not_contaminate_immutable_execution(tmp_path):
    source = dict(authority_revision=7, route_build_id='build', calculation_sequence=1,
                  computed_at=1., observation_timestamp=.99, authority_valid=True)
    rejected = dict(source, authority_valid=False, command=0)
    replay = tmp_path/'replay.json'
    replay.write_text(json.dumps(dict(samples=[], execution_samples=[
        dict(source_packet=source, executor_active=True, output=.2, execution_monotonic_s=1.01),
        dict(source_packet=rejected, executor_active=True, output=0, execution_monotonic_s=1.02),
        dict(source_packet=source, executor_active=True, output=.3, execution_monotonic_s=1.03)])))
    result = replay_report(replay)
    assert result['immutable_execution_samples'] == 2
    assert result['invalid_immutable_source_rows'] == 1
    assert result['execution_segments'][0]['steering_step']['n'] == 0
    assert len(result['execution_segments']) == 2


def test_log_window_filters_build_and_never_exports_unrelated_profile_data(tmp_path):
    log = tmp_path/'app.log'
    log.write_text("2026-10-01 18:21:26,630 [Engine] Drive boundary: "
                   "{'route_build_id': 'chosen', 'observed_gear': 8, 'private': 'hidden'}\n"
                   "2026-10-01 18:21:27,630 [Engine] Drive boundary: "
                   "{'route_build_id': 'other', 'observed_gear': -1}\n")
    result = log_report(log, datetime(2026,10,1,18,21), datetime(2026,10,1,18,22), 'chosen')
    assert len(result['boundaries']) == 1
    assert result['boundaries'][0]['observed_gear'] == 8
    assert 'hidden' not in json.dumps(result)


def test_passive_timings_do_not_pool_different_route_identities(tmp_path):
    replay = tmp_path/'timing.json'
    replay.write_text(json.dumps(dict(sample_kind='passive_phase_timing', samples=[
        dict(identity_matches=True, packet_available=True, revision=1,
             route_build_id='a', monotonic_s=1., observation_age_at_read_s=.1),
        dict(identity_matches=True, packet_available=True, revision=2,
             route_build_id='b', monotonic_s=1.1, observation_age_at_read_s=.4),
        dict(identity_matches=False, packet_available=True, revision=2,
             route_build_id='b', monotonic_s=1.2, observation_age_at_read_s=.01)])))
    result = replay_report(replay)
    assert result['excluded_identity_or_packet_rows'] == 1
    assert len(result['timing_by_segment']) == 2
    assert result['timing_by_segment'][0]['metrics']['observation_age_at_read_ms']['median'] == 100
    assert result['timing_by_segment'][1]['metrics']['observation_age_at_read_ms']['median'] == 400
