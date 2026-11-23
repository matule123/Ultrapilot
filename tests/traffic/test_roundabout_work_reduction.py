"""Conservative arrival bounds and private publication reuse."""

import math
from unittest.mock import patch

import numpy as np
import pytest

from core import actor_motion
from core.acc_body_prediction import predict
from core.acc_following import RouteLeadSelector
from core.engine import UltraPilotEngine
from tests.traffic.test_actor_motion_contract import actor, graph


@pytest.mark.parametrize('retained', [False, True])
def test_timed_crossing_matches_unfiltered_at_window_boundaries(retained):
    original = actor_motion.crossing_pairs
    route = RouteLeadSelector()
    truck = dict(x=0., y=10., z=0., speed=4., rotation=math.pi)
    seen = []
    for position in (math.nextafter(12., 0.), 12., math.nextafter(12., math.inf), 50.):
        route.prepare([(0., 10., 0.), (0., 10., position), (0., 10., 100.)], position)
        cab = dict(x=-4., y=10., z=position, yaw=-math.pi / 2., dimensions_whl=(2., 2., 4.))
        vehicle = dict(cab, id=7, source='moving', speed=4., bodies=[cab, dict(cab)])
        motion_graph = dict(schema=1, status='prepared', curves=[dict(id='across',
            points=[[-10., 10., position], [50., 10., position]], next=[])])
        motion = actor_motion.ActorMotionGraph(motion_graph).hypotheses(vehicle, history_valid=True)
        route.source_motion([vehicle], dict(valid=True, lifecycle=7, generation=2, frame_us=200, observed_at=3.))
        route.actor_motion = lambda value: motion
        if retained:
            route._target_is_crossing, route.target_id = True, '7'
        actual = route.crossing([vehicle], truck, 0.)

        def unfiltered(*args, **kwargs):
            return original(*args, **dict(kwargs, arrival_windows=None))

        with patch.object(actor_motion, 'crossing_pairs', unfiltered):
            assert actual == route.crossing([vehicle], truck, 0.)
        seen.append(actual)
    assert [conflict['body_index'] for conflict in seen[0]['conflicts']] == [0, 1]
    assert bool(seen[-1]['conflicts']) == retained


@pytest.mark.parametrize('speed', [-.039795611, 0., 7.6])
def test_contact_prefilter_keeps_cab_trailer_and_touching_intervals(speed):
    route = RouteLeadSelector()
    route.prepare([(0., 10., 0.), (0., 10., 100.)], 'route', actor_motion=graph())
    original = actor()
    original['bodies'].append(dict(original['bodies'][0], z=1.))
    motion = route._actor_motion_graph.hypotheses(original, history_valid=True)
    route.actor_motion = lambda value: motion
    for x in (0., 2., math.nextafter(2., math.inf), 30.):
        body = dict(x=x, y=10., z=17., yaw=math.pi, dimensions_whl=(2., 2., 4.))
        bodies = [body, dict(body, x=0., z=13.)]
        inputs = route, bodies, [original], speed, 17., (x, 10., 17.)
        before, after = {}, {}
        assert predict(*inputs, debug_geometry=before, prefilter=False) == predict(*inputs, debug_geometry=after)
        assert before == after


def test_control_lane_snapshot_reloads_on_each_publication_and_state_change():
    class State(dict):
        loads = 0

        def get(self, key, default=None):
            if key == 'lane_trajectory':
                self.loads += 1
                return dict(self[key])
            return super().get(key, default)

    engine = UltraPilotEngine.__new__(UltraPilotEngine)
    state = engine.shared_state = State(lane_trajectory={'valid': True}, lane_trajectory_publication_token='a')
    assert engine._read_control_lane_snapshot()['valid']
    assert engine._read_control_lane_snapshot()['valid']
    assert state.loads == 1
    state.update(lane_trajectory={'valid': False}, lane_trajectory_publication_token='b')
    assert not engine._read_control_lane_snapshot()['valid']
    assert state.loads == 2
    engine.shared_state = State(lane_trajectory={'valid': True}, lane_trajectory_publication_token='b')
    assert engine._read_control_lane_snapshot()['valid']
    engine.shared_state.pop('lane_trajectory_publication_token')
    engine._read_control_lane_snapshot()
    engine._read_control_lane_snapshot()
    assert engine.shared_state.loads == 3


def test_duplicate_source_update_without_output_does_not_recompute_predictions():
    route = RouteLeadSelector()
    source = dict(valid=True, lifecycle=27, generation=2, frame_us=200, observed_at=3.)
    with patch.object(route, '_native_predictions', return_value={'exact': 1}) as predict:
        assert route.source_motion([actor()], source) == {'exact': 1}
        assert route.source_motion([actor()], source, include_predictions=False) == {}
        predict.assert_called_once_with()
    assert route._native_current[0] == (27, 2, 200, 3.)


def test_crossing_horizontal_projection_is_reused_by_full_body_consumer():
    route = RouteLeadSelector()
    route.prepare([(-10., 10., 15.), (10., 10., 15.)], 'route', actor_motion=graph())
    vehicle = actor()
    vehicle['bodies'].append(dict(vehicle['bodies'][0], x=1., y=11., z=1., yaw=2.))
    motion = route._actor_motion_graph.hypotheses(vehicle, history_valid=True)
    horizontal = route.actor_body_motion(vehicle, motion, horizontal_only=True)
    assert not horizontal.flags.writeable
    assert route.actor_body_motion(vehicle, motion, horizontal_only=True) is horizontal
    complete = route.actor_body_motion(vehicle, motion)
    direct = actor_motion.projected_bodies(vehicle, vehicle['bodies'], motion)
    np.testing.assert_array_equal(complete, direct)
    assert np.shares_memory(horizontal, complete)
    assert not horizontal.flags.writeable
    assert np.shares_memory(complete, route.actor_body_motion(vehicle, motion, horizontal_only=True))
    assert route.actor_body_motion(vehicle, motion) is complete

    def crossing(prepared):
        return actor_motion.crossing_pairs(vehicle, vehicle['bodies'], motion,
                                           route._crossing_bounds, 0, prepared=prepared,
                                           edge_values=route._crossing_values)

    assert crossing(horizontal) == crossing(complete)
    assert crossing(horizontal)


def test_forward_context_reads_compact_publication_and_tracks_revision():
    from core.ipc.shared_state import lane_publication_batch
    from core.transmission_mode import simple_auto_context

    class State(dict):
        def get(self, key, default=None):
            assert key != 'lane_trajectory'
            return super().get(key, default)

    route = dict(revision=5, navigation_intent_id='intent', route_build_id='build',
                 source_game_session_id='session', source_map_key='map', source_dataset_fingerprint='dataset')
    state = State(simple_auto_activation_token='token', ets2_transmission_mode={'generation': 2})
    state.update(lane_publication_batch({'lane_trajectory': route}))
    legacy = dict(state)
    legacy.pop('lane_trajectory_publication_token')
    assert simple_auto_context(state) == simple_auto_context(legacy)
    route = dict(route, revision=6, route_build_id='new')
    state.update(lane_publication_batch({'lane_trajectory': route}))
    assert simple_auto_context(state) != simple_auto_context(legacy)
