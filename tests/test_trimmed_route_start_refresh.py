"""A confirmed pose behind an old route trim requires a real rebuild."""
import math
import time

import pytest

from tests.test_steering_fresh_handoff import prepared_map


def retreat(plugin, sdk, point, observation, distance=3.0):
    pose = (point.x + math.sin(point.heading) * distance, point.y,
            point.z + math.cos(point.heading) * distance)
    sdk.set('truck_world_pos', (pose[0], pose[2]))
    sdk.set('vehicle_envelope_snapshot', dict(observation,
        timestamp=time.monotonic(), sdk_frame_us=1_020_000,
        tractor_position=pose))
    return pose


def test_inactive_pose_behind_trim_gets_new_validated_build_and_packet():
    plugin, sdk, point, observation = prepared_map()
    old = dict(sdk.get('lane_trajectory'))
    pose = retreat(plugin, sdk, point, observation)
    match = plugin._lane_match
    metadata = plugin._lane_runtime_metadata(match.lane_id)
    plugin._lane_route.steering((pose[0], pose[2]), point.heading, 0.,
        control_authority={'lane_identity': match.lane_id.sort_key(),
                           'elevation_layer': metadata['elevation_layer']})
    assert plugin._lane_route.last_steering_debug['control_failure'] == (
        'live LaneId has no reachable projection on the validated trajectory')
    plugin.on_tick(.02)
    new = sdk.get('lane_trajectory')
    assert new['valid']
    assert new['route_build_id'] != old['route_build_id']
    packet = sdk.get('nav_steering_debug')
    assert packet['authority_valid'], packet
    assert packet['route_build_id'] == new['route_build_id']
    assert tuple(packet['observation_xz']) == (pose[0], pose[2])
    assert packet['sdk_frame_us'] == 1_020_000
    assert math.dist((new['points'][0][0], new['points'][0][2]),
                     (pose[0], pose[2])) < .01
    for _ in range(3):
        plugin._update_lane_trajectory((pose[0], pose[2]), point.heading)
        assert sdk.get('lane_trajectory')['route_build_id'] == new['route_build_id']


@pytest.mark.parametrize('state', ['autopilot_active', 'auto_drive_pending'])
def test_active_or_pending_drive_does_not_rebuild_to_mask_projection_failure(state):
    plugin, sdk, point, observation = prepared_map()
    old = dict(sdk.get('lane_trajectory'))
    retreat(plugin, sdk, point, observation)
    sdk.set(state, True)
    plugin.on_tick(.02)
    assert sdk.get('lane_trajectory')['route_build_id'] == old['route_build_id']
    assert sdk.get('nav_steering_debug')['authority_valid'] is False
    assert sdk.get('nav_steering') == 0.


def test_normal_forward_motion_keeps_geometry_identity():
    plugin, sdk, point, observation = prepared_map()
    old = dict(sdk.get('lane_trajectory'))
    retreat(plugin, sdk, point, observation, distance=-3.)
    plugin.on_tick(.02)
    assert sdk.get('lane_trajectory')['route_build_id'] == old['route_build_id']
    assert sdk.get('nav_steering_debug')['authority_valid'] is True


def test_different_deck_or_repeated_lane_cannot_refresh_trimmed_start():
    from dataclasses import replace
    plugin, sdk, point, observation = prepared_map()
    pose = retreat(plugin, sdk, point, observation)
    match = replace(plugin._lane_match,
        point=replace(plugin._lane_match.point, x=pose[0], z=pose[2]))
    path = plugin._lane_path
    first = path.segments[0]
    plugin._lane_path = replace(path, segments=(replace(first,
        elevation_layer=first.elevation_layer+1),) + path.segments[1:])
    assert not plugin._trimmed_start_requires_refresh(match)
    plugin._lane_path = replace(path, segments=path.segments + (first,))
    assert not plugin._trimmed_start_requires_refresh(match)


def test_failed_refresh_cannot_make_old_trim_authoritative():
    from dataclasses import replace
    from unittest import mock
    plugin, sdk, point, observation = prepared_map()
    old = dict(sdk.get('lane_trajectory'))
    retreat(plugin, sdk, point, observation)
    failure = replace(plugin._lane_path, valid=False,
                      failure_reason='unconfirmed topology')
    with mock.patch.object(plugin.road_net, 'build_lane_path',
                           return_value=(failure, plugin._lane_match)):
        plugin.on_tick(.02)
    assert sdk.get('lane_trajectory')['route_build_id'] == old['route_build_id']
    assert sdk.get('nav_active') is False
    assert sdk.get('nav_steering') == 0.
    assert sdk.get('nav_steering_debug')['authority_valid'] is False


def test_stale_pose_cannot_publish_control_after_retreat():
    from unittest import mock
    plugin, sdk, point, observation = prepared_map()
    retreat(plugin, sdk, point, observation)
    stale = dict(sdk.get('vehicle_envelope_snapshot'),
                 timestamp=observation['timestamp'] - 1.)
    sdk.set('vehicle_envelope_snapshot', stale)
    with mock.patch('plugins.map.main.time.monotonic',
                    return_value=observation['timestamp']):
        plugin.on_tick(.02)
    assert sdk.get('nav_active') is False
    assert sdk.get('nav_steering') == 0.
    assert sdk.get('vehicle_envelope_snapshot')['timestamp'] == stale['timestamp']
