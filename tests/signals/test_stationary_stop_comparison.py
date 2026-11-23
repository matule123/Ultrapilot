import math

import pytest

from tools.compare_oct11_stationary_stop import measured_edges, project


def observations():
    return [dict(tracking_segment_index=7, tracking_segment_fraction=f,
                 tracking_projection_xz=[2*f, 10-4*f],
                 tracking_progress_m=100+f*math.sqrt(20)) for f in (.2, .8)]


def test_recovers_measured_segment_and_original_progress():
    edges = measured_edges(observations())
    result = project([1, 8], edges)
    assert result['fraction'] == pytest.approx(.5)
    assert result['progress_m'] == pytest.approx(100+math.sqrt(20)/2)
    assert result['lateral_distance_m'] == pytest.approx(0)
    assert result['route_heading_rad'] == pytest.approx(math.atan2(-2, 4))


def test_projection_reports_lateral_offset_without_altering_progress():
    result = project([1+4/math.sqrt(20), 8+2/math.sqrt(20)], measured_edges(observations()))
    assert result['lateral_distance_m'] == pytest.approx(1)
    assert result['fraction'] == pytest.approx(.5)


def test_missing_fraction_span_does_not_invent_segment():
    with pytest.raises(ValueError, match='no measured edges'):
        measured_edges([observations()[0]])


def test_inconsistent_original_progress_is_rejected():
    rows = observations()
    rows[-1]['tracking_progress_m'] += 1
    with pytest.raises(ValueError, match='inconsistent'):
        measured_edges(rows)
