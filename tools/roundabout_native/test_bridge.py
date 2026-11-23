"""Boundary regressions for the explicitly enabled offline component."""

import math
import os
from unittest.mock import patch

import pytest

from tools.roundabout_native.bridge import CrossingBatch


def crossing_fixture(z):
    from core.acc_following import RouteLeadSelector
    from core.actor_motion import ActorMotionGraph

    route = RouteLeadSelector()
    route.prepare([(0., 10., float(i)) for i in range(513)], 'geometry')
    graph = {'schema': 1, 'status': 'prepared', 'curves': [
        {'id': 'across', 'points': [[-30., 10., z], [60., 10., z]], 'next': []}]}
    body = dict(x=-10., y=10., z=z, yaw=-math.pi / 2., dimensions_whl=(2., 2., 4.))
    actor = dict(body, id=7, speed=5., source='moving', slot=7, bodies=[body, dict(body)])
    motion = ActorMotionGraph(graph).hypotheses(actor, history_valid=True)
    branch = motion['branches'][0]
    motion.update(branch_count=2, branches=[branch, dict(branch, curve_chain=['other'])])
    route.actor_motion = lambda value: motion
    return route, actor, motion


def test_mapped_crossing_keeps_cab_trailer_and_first_tied_branch():
    route, actor, _ = crossing_fixture(20.)
    truck = dict(x=0., y=10., z=0., rotation=math.pi, speed=5.)
    conflicts = route.crossing([actor], truck, 0.)['conflicts']
    assert [(c['id'], c['body_index'], c['hypothesis_index']) for c in conflicts] == [(7, 0, 0), (7, 1, 0)]
    assert all(c['brake'] > 0. and c['branch_count'] == 2 for c in conflicts)
    assert route.crossing([actor, actor], truck, 0.)['status'] == 'crossing_projection_unavailable'
    assert route.crossing([actor], dict(truck, speed=-1.), 0.)['status'] == 'crossing_projection_unavailable'


def test_native_edge_word_boundary_and_invalid_or_missing_output():
    route, actor, motion = crossing_fixture(64.)
    jobs = [(actor, actor['bodies'], motion, route.actor_body_motion(actor, motion))]
    args = (jobs, route._crossing_bounds, route._crossing_values, 7)
    batch = CrossingBatch(os.environ['UP_ROUNDABOUT_OFFLINE_DLL'], check_pairs=True)
    result, = batch.admit(*args)
    assert list(result) == [0, 1]
    assert any(indices == [70, 71] for _, indices in result[0])
    assert batch.admit(jobs, route._crossing_bounds[:0], route._crossing_values[:0], 7) == [{}]

    invalid_bounds = route._crossing_bounds.copy()
    invalid_bounds[0, 0] = float('nan')
    with pytest.raises(RuntimeError, match='invalid row count'):
        batch.admit(jobs, invalid_bounds, route._crossing_values, 7)

    for count in (-1, 1 << 30, 1, 0, None):
        with patch.object(batch, 'call', return_value=count), pytest.raises(RuntimeError):
            batch.admit(*args)

    def falsely_complete(*arguments):
        arguments[-1]._obj.value = arguments[1]
        return 0

    with patch.object(batch, 'call', side_effect=falsely_complete), pytest.raises(RuntimeError, match='pair mismatch'):
        batch.admit(*args)
