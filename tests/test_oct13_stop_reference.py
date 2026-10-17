"""Authorized 5 m SDK-to-authored-entry policy, not a painted-line claim."""
import math

import pytest

from core.longitudinal import signal_stop_speed_limit
from tests.test_oct10_native_signal_direction import authored_heads, selection
from tools.audit_oct11_stop_geometry import model_case
from tools.run_oct11_terminal_stop_bench import metrics
from tools.compare_oct13_stop_reference import compare


@pytest.mark.parametrize('case,slot', [(0,3),(1,1)])
def test_same_real_directed_entry_has_authorized_five_metre_offset(tmp_path, case, slot):
    _, heads = authored_heads()
    selected, plan = selection(tmp_path, [heads[slot]], case=case)
    assert selected['valid'], selected
    candidate = selected['candidate']
    assert candidate['distance'] == pytest.approx(plan['passages'][0]['entry_progress_m']-5.)
    assert candidate['front_allowance_m']+candidate['junction_standoff_m'] == 5.
    assert candidate['stop_line_verified'] is False
    assert 'unmeasured' in candidate['front_geometry_status']
    assert selected['observed_at'] == 1000. and selected['frame_us'] == 100
    # No second fixed subtraction. Reserve response travel at the reference
    # speed (Oct17 rebound repair), not at an unrelated measured 4 m/s.
    cap = signal_stop_speed_limit(candidate,4.)
    assert cap*1.5+cap*cap/2. == pytest.approx(candidate['distance'])
    assert signal_stop_speed_limit(candidate,0.) == pytest.approx(cap)


@pytest.mark.parametrize('speed', [20.,35.,50.])
@pytest.mark.parametrize('mode', [0,3])
def test_authorized_target_through_real_producers_and_physical_writes(tmp_path, speed, mode):
    result = model_case(tmp_path, speed=speed, mode=mode)
    value = metrics(result)
    assert result['stop']['reference_offset_m'] == 5.
    assert 0. <= value['gap_m']
    assert value['red_target_overruns'] == value['red_entry_overrun_samples'] == 0
    assert value['positive_pedal_overlap'] == value['parking_writes'] == 0
    assert value['hold_zero_writes'] == value['red_standstill_drive_writes'] == 0
    assert value['active'] and value['resumed_without_n']
    assert value['far_low_speed_s'] == 0.
    assert value['painted_line_gap_m'] is None


@pytest.mark.parametrize('curvature', [1./60.,-1./60.])
def test_changed_reference_uses_same_arc_and_preserves_other_stop(tmp_path, curvature):
    result = model_case(tmp_path, approach_curvature=curvature, other_stop=True)
    value = metrics(result)
    assert result['stop']['reference_offset_m'] == 5.
    assert value['active'] and not value['resumed_without_n']
    assert result['rows'][-1]['throttle'] == 0. and result['rows'][-1]['brake'] > 0.
    assert value['hold_zero_writes'] == value['positive_pedal_overlap'] == 0


def test_paired_reference_experiment_reports_offset_separately_from_residual(tmp_path):
    pair = compare(tmp_path)
    a,b = pair['before'],pair['after']
    assert a['reference_offset_m'] == 8. and b['reference_offset_m'] == 5.
    for value in (a,b):
        assert value['sdk_reference_to_authored_entry_m'] == pytest.approx(
            value['reference_offset_m']+value['gap_m'])
        assert value['physical_bumper_to_painted_line_m'] is None
        assert not value['game_verified']
        assert value['active'] and value['resumed_without_n']
