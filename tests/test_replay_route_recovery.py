import pytest
from tools.recover_steering_route import recover


def row(index,fraction,point,build='a'):
    return dict(tracking_segment_index=index,tracking_segment_fraction=fraction,
                tracking_projection_xz=point,calculation_trajectory_identity={'route_build_id':build})


def test_original_fraction_equations_recover_exact_shared_vertices():
    result=recover([row(0,.2,[.4,0.]),row(0,.8,[1.6,0.]),
                    row(1,.2,[2.,.4]),row(1,.8,[2.,1.6])])
    assert len(result['points']) == 3
    for actual,expected in zip(result['points'],[[0.,0.],[2.,0.],[2.,2.]],strict=True):
        assert actual == pytest.approx(expected)


def test_missing_vertex_is_not_interpolated():
    with pytest.raises(ValueError,match='unmeasured'):
        recover([row(0,.2,[.4,0.]),row(0,.8,[1.6,0.]),
                 row(4,.2,[4.,4.4]),row(4,.8,[4.,5.6])])


def test_different_builds_cannot_be_joined():
    with pytest.raises(ValueError,match='mixed'):
        recover([row(0,.2,[.4,0.]),row(0,.8,[1.6,0.],build='b')])


def test_inconsistent_endpoints_cannot_be_called_recovered_geometry():
    with pytest.raises(ValueError,match='inconsistent'):
        recover([row(0,.2,[.4,0.]),row(0,.8,[1.6,0.]),
                 row(1,.2,[3.,.4]),row(1,.8,[3.,1.6])])
