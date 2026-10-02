"""An observation read before localization is not fresh after a long lookup."""
from unittest import mock

import pytest

from plugins.autopilot.main import navigation_command
from tests.test_steering_fresh_handoff import prepared_map
from tests.test_activation_observation_binding import flow  # noqa: F401


@pytest.mark.parametrize("fault", [None, "sdk_loss", "identity", "no_new_frame"])
def test_delayed_refresh_rechecks_real_observation_after_locator(fault):
    plugin, sdk, point, initial = prepared_map()
    now = [initial["timestamp"]]
    first = dict(initial, sdk_frame_us=1_016_667,
                 tractor_position=(point.x, point.y, point.z + .01))
    final = dict(first, sdk_frame_us=1_466_667,
                 tractor_position=(point.x, point.y, point.z + .02))
    original = plugin.road_net._runtime_lane_locator.locate
    calls = []
    preparing_reference = [False]

    def prepare(_pos):
        sdk.set("vehicle_envelope_snapshot", first)
        preparing_reference[0] = True

    def slow_lookup(*args, **kwargs):
        result = original(*args, **kwargs)
        if not preparing_reference[0]:
            return result
        calls.append(args[0])
        if len(calls) == 1:
            now[0] += .4561553  # Recorded road-type -> reference gap at sequence 2294.
            final["timestamp"] = now[0]
            if fault == "sdk_loss":
                sdk.set("telemetry_valid", False)
            elif fault == "identity":
                sdk.set("navigation_intent_id", "changed-during-localization")
            elif fault != "no_new_frame":
                sdk.set("vehicle_envelope_snapshot", final)
        return result

    with mock.patch("plugins.map.main.time.monotonic", side_effect=lambda: now[0]), \
            mock.patch.object(plugin, "_publish_road_type", side_effect=prepare), \
            mock.patch.object(plugin.road_net._runtime_lane_locator, "locate", side_effect=slow_lookup):
        plugin.on_tick(.02)
    packet = sdk.get("nav_steering_debug")
    if fault:
        assert sdk.get("nav_active") is False
        assert not packet or packet["authority_valid"] is False
        return
    assert packet.get("sdk_frame_us") == final["sdk_frame_us"], packet
    assert packet["observation_timestamp"] == final["timestamp"]
    assert tuple(packet["observation_xz"]) == (final["tractor_position"][0], final["tractor_position"][2])
    assert packet["computed_at"] - packet["observation_timestamp"] < .05
    snapshot = sdk.get("lane_trajectory")
    for key, value in (("source_game_session_id", "session"),
                       ("source_map_key", "test-map"),
                       ("source_dataset_fingerprint", "test-data")):
        snapshot[key] = packet[key] = value
    # Delayed downstream consumption does not inherit the pre-localization age.
    assert navigation_command(sdk.shared_state, snapshot, gps_active=True,
        packet=packet, now=now[0] + .06)[2] == ""
    assert navigation_command(sdk.shared_state, snapshot, gps_active=True,
        packet=packet, now=now[0] + .501)[2]
    assert len(calls) == 2  # Hard bound; there is no growing preparation queue.


def test_delayed_localization_reaches_real_autopilot_and_engine_without_old_packet(flow):
    state, truck, engine, autopilot, publish, n, clock = flow
    mp, sdk, point, observation = prepared_map()
    snapshot = dict(sdk.get("lane_trajectory"))
    context = state.get("lane_trajectory")
    for key in ("source_game_session_id", "source_map_key", "source_dataset_fingerprint"):
        snapshot[key] = context[key]
    snapshot.update(navigation_intent_id="intent", request_id="intent")
    mp._lane_authority_identity = tuple(snapshot[key] for key in (
        "navigation_intent_id", "request_id", "route_build_id",
        "source_game_session_id", "source_map_key", "source_dataset_fingerprint"))
    state.update_batch(dict(lane_trajectory=snapshot, lane_trajectory_revision=snapshot['revision'],
        game_route_node_uids=list(snapshot['source_gps_uids']), navigation_intent_id='intent',
        nav_recalc_request='intent', lane_match=sdk.get('lane_match')))
    sdk.shared_state = state
    truck.update(x=point.x, y=point.y, z=point.z, rotation=point.heading,
                 referenceGeometry=observation['tractor_reference_geometry'])

    def telemetry(dt=.02, gear=8, speed=3.4):
        previous = state.get('nav_steering_debug')
        heartbeat = state.get('lane_trajectory_heartbeat')
        publish(gear, speed, dt=dt)
        state.set('nav_steering_debug', previous)
        state.set('lane_trajectory_heartbeat', heartbeat)

    def tick(gear, speed, dt=.02):
        telemetry(dt, gear, speed)
        mp.on_tick(dt)
        autopilot.on_tick(dt)

    tick(0, 0.)
    n()
    tick(0, 0.)
    engine._flush_controls()
    assert engine.controller.throttle == .12
    tick(8, 0., .228)
    engine._flush_controls()
    tick(8, .2)
    engine._flush_controls()
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    original = mp.road_net._runtime_lane_locator.locate
    reference_phase = [False]; delayed = [False]

    def prepare(_pos):
        telemetry()
        reference_phase[0] = True

    def locate(*args, **kwargs):
        value = original(*args, **kwargs)
        if reference_phase[0] and not delayed[0]:
            delayed[0] = True
            telemetry(.4561553)
        return value

    telemetry()
    with mock.patch.object(mp, '_publish_road_type', side_effect=prepare), \
            mock.patch.object(mp.road_net._runtime_lane_locator, 'locate', side_effect=locate):
        mp.on_tick(.02)
    expected = clock[0]
    clock[0] += .06  # Enough to expire the old 456 ms source at Engine.
    autopilot.on_tick(.02); engine._flush_controls()
    packet = state.get('nav_steering_debug')
    assert packet['observation_timestamp'] == expected
    assert packet['sdk_frame_us'] == truck['sdkFrameTimeUs']
    assert state.get('autopilot_active'), state.get('autopilot_disable_reason')
    assert not engine._gps_propulsion_suppressed
    assert engine.controller.throttle > 0
    # Real loss still enters the existing safety path without propulsion.
    clock[0] += .501
    autopilot.on_tick(.02); engine._flush_controls()
    assert engine.controller.throttle == 0
    assert not state.get('autopilot_active') or state.get('safety_hazard_active')


def test_second_slow_localization_cannot_retry_forever():
    plugin, sdk, point, initial = prepared_map()
    now = [initial['timestamp']]
    calls = []
    preparing = [False]
    original = plugin.road_net._runtime_lane_locator.locate

    def update():
        sdk.set('vehicle_envelope_snapshot', dict(initial,
            timestamp=now[0], sdk_frame_us=1_000_000 + 20_000 * (len(calls) + 1),
            tractor_position=(point.x, point.y, point.z + .01 * (len(calls) + 1))))

    def prepare(_pos):
        update()
        preparing[0] = True

    def locate(*args, **kwargs):
        result = original(*args, **kwargs)
        if preparing[0]:
            calls.append(True)
            now[0] += .4561553
            update()
        return result

    with mock.patch('time.monotonic', side_effect=lambda: now[0]), \
            mock.patch.object(plugin, '_publish_road_type', side_effect=prepare), \
            mock.patch.object(plugin.road_net._runtime_lane_locator, 'locate', side_effect=locate):
        plugin.on_tick(.02)
    assert len(calls) == 2
    assert not sdk.get('nav_active')
    assert sdk.get('steering_observation_failure') == 'steering localization exceeded the fresh observation budget'
