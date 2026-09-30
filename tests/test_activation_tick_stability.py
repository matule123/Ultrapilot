"""30 September: pending N, concurrent Map publication and causal shutdown."""
from unittest import mock

import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_simple_auto_launch_handoff import start_handoff
from tests.test_steering_fresh_handoff import prepared_map


def test_first_n_waits_for_next_fresh_packet_without_another_hotkey(flow):
    state, truck, engine, plugin, publish, n, clock = start_handoff(flow)
    packet = state.get("nav_steering_debug")
    # Incident: 6913.7233742 - 6913.3169732 = 406.401 ms. The
    # packet remains below 500 ms, but cannot cover the 100 ms reserve.
    packet.update(observation_timestamp=clock[0] - .406401,
                  computed_at=clock[0] - .361371)
    state.set("nav_steering_debug", packet)
    engine._flush_controls()
    assert engine._drive_engagement is not None, state.get("autopilot_disable_reason")
    assert engine.controller.throttle == engine.controller.steering == 0
    plugin.on_tick(publish(8, 0.0, dt=.02))
    engine._flush_controls()
    assert state.get("autopilot_active")
    assert engine._drive_engagement is None
    assert engine.controller.throttle > 0
    assert True not in engine.controller.drive_events


def test_waiting_for_packet_cannot_renew_handoff_deadline(flow):
    state, truck, engine, plugin, publish, n, clock = start_handoff(flow)
    deadline = engine._drive_engagement["handoff_deadline_at"]
    packet = state.get("nav_steering_debug")
    for _ in range(30):
        publish(8, 0.0, dt=.02)
        packet.update(observation_timestamp=clock[0] - .406401,
                      computed_at=clock[0] - .361371)
        state.set("nav_steering_debug", packet)
        engine._flush_controls()
        assert engine.controller.throttle == 0
        if engine._drive_engagement is not None:
            assert engine._drive_engagement["handoff_deadline_at"] == deadline
    assert not state.get("autopilot_active")
    assert engine._drive_engagement is None


def test_slow_ipc_can_expire_packet_and_future_heartbeat_is_rejected(flow):
    state, truck, engine, plugin, publish, n, clock = flow
    publish(8, 3.4)
    n()
    plugin.on_tick(.02)
    fired = []

    def during_ipc(key):
        if key == "lane_trajectory_heartbeat" and not fired:
            fired.append(True)
            clock[0] += .501
            state.set("lane_trajectory_heartbeat", clock[0])

    state.hook = during_ipc
    engine._flush_controls()
    assert engine.controller.throttle == 0
    assert engine._gps_propulsion_suppressed
    assert "observation_timestamp" in state.get("autopilot_first_fault_engine")["reason"]
    state.hook = None
    publish(8, 3.4)
    state.set("lane_trajectory_heartbeat", clock[0] + .02)
    assert engine._gps_output_packet_rejection_reason(
        clock[0], state.get("lane_trajectory")) == "map plugin heartbeat is stale"


def test_map_publication_during_engine_ipc_is_not_a_future_heartbeat(flow):
    state, truck, engine, plugin, publish, n, clock = flow
    publish(8, 3.4)
    n()
    plugin.on_tick(.02)
    map_plugin, map_sdk, point, observation = prepared_map()
    map_sdk.set("vehicle_envelope_snapshot", dict(observation,
        timestamp=clock[0], tractor_speed_ms=3.4))
    map_plugin.on_tick(.02)
    packet = dict(map_sdk.get("nav_steering_debug"))
    snapshot = state.get("lane_trajectory")
    for key in ("navigation_intent_id", "route_build_id", "source_game_session_id",
                "source_map_key", "source_dataset_fingerprint"):
        packet[key] = snapshot[key]
    packet["authority_revision"] = snapshot["revision"]
    packet["sdk_frame_us"] = truck["sdkFrameTimeUs"]
    state.set("nav_steering_debug", packet)
    fired = []

    def during_ipc(key):
        if key == "lane_trajectory_heartbeat" and not fired:
            fired.append(True)
            clock[0] += .02
            # A newer valid localization is published while the reader is in
            # flight. Its original timestamp is retained, not renewed here.
            state.set("lane_trajectory_heartbeat", clock[0])

    state.hook = during_ipc
    engine._flush_controls()
    assert fired
    assert engine.controller.throttle > 0
    assert state.get("autopilot_active")
    assert not engine._gps_propulsion_suppressed
    assert packet["observation_timestamp"] == clock[0] - .02


def test_shutdown_preserves_first_output_fault_across_token_cleanup(flow):
    state, truck, engine, plugin, publish, n, clock = flow
    publish(8, 3.4)
    n()
    plugin.on_tick(.02)
    state.set("lane_trajectory_heartbeat", clock[0] - .6)
    engine._flush_controls()
    assert engine.controller.throttle == 0
    # Later stopping/cleanup is a consequence of the first failed boundary.
    publish(0, 0.0)
    engine._revoke_simple_auto_launch(truck, "simple automatic zero ratio lacks continuing forward motion")
    with mock.patch.object(plugin, "_export_and_rotate_steering_replay") as export:
        plugin._publish_automatic_disable("simple automatic activation or route identity changed")
    assert state.get("autopilot_disable_reason") == "map plugin heartbeat is stale"
    assert "map plugin heartbeat is stale" in state.get("autopilot_log_event")["message"]
    assert export.call_args.args[1] == "map plugin heartbeat is stale"
    assert "map plugin heartbeat is stale" in state.get("navigation_status")
    n()  # A separate engagement must not inherit the preceding failure.
    engine._revoke_simple_auto_launch(truck, "new safety failure")
    assert state.get("autopilot_disable_reason") == "new safety failure"


def test_inflight_disable_cannot_replace_manual_off_or_a_new_n(flow):
    state, truck, engine, plugin, publish, n, clock = flow
    publish(8, 3.4)
    n()
    plugin.on_tick(.02)
    old_epoch = state.get("autopilot_failure_epoch")
    n()
    assert state.get("autopilot_disable_reason") == "manual hotkey"
    assert state.get("autopilot_failure_epoch") != old_epoch
    plugin._publish_automatic_disable("old packet became stale")
    assert state.get("autopilot_disable_reason") == "manual hotkey"
    n()
    assert state.get("autopilot_active")
    plugin._publish_automatic_disable("old packet became stale")
    assert state.get("autopilot_active")


@pytest.mark.parametrize("fault", ["stale", "intent", "revision", "manual"])
def test_real_loss_during_handoff_still_releases_outputs(flow, fault):
    state, truck, engine, plugin, publish, n, clock = start_handoff(flow)
    if fault == "stale":
        clock[0] += .501
    elif fault == "manual":
        n()
    elif fault == "intent":
        state.set("navigation_intent_id", "replacement")
    else:
        state.set("lane_trajectory_revision", 8)
    engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == engine.controller.steering == engine.controller.brake == 0


def test_map_packet_atomically_carries_same_frame_localization_and_heartbeat():
    map_plugin, sdk, point, observation = prepared_map()
    clock = [observation["timestamp"]]
    original = map_plugin._publish_road_type

    def slow_preparation(pos):
        original(pos)
        clock[0] += .369
        sdk.set("vehicle_envelope_snapshot", dict(observation,
            timestamp=clock[0], sdk_frame_us=observation["sdk_frame_us"] + 369000,
            tractor_position=(point.x, point.y, point.z + .1)))

    with mock.patch("time.monotonic", side_effect=lambda: clock[0]), mock.patch.object(
            map_plugin, "_publish_road_type", side_effect=slow_preparation):
        map_plugin.on_tick(.02)
    batch = next(batch for batch in sdk.shared_state.batches
                 if batch.get("nav_active") and batch.get("nav_steering_debug"))
    packet = batch["nav_steering_debug"]
    assert packet["observation_timestamp"] == clock[0]
    assert packet["sdk_frame_us"] == observation["sdk_frame_us"] + 369000
    assert batch["lane_trajectory_heartbeat"] == packet["map_packet_publish_started_at"]
    assert batch["lane_match"]["revision"] == packet["authority_revision"]


@pytest.mark.parametrize("fault", [None, "stale", "revision", "intent", "manual"])
def test_one_n_and_driving_through_real_map_plugin_sdk_and_engine(flow, fault):
    state, truck, engine, plugin, publish, n, clock = flow
    map_plugin, map_sdk, point, observation = prepared_map()
    snapshot = dict(map_sdk.get("lane_trajectory"))
    context = state.get("lane_trajectory")
    for key in ("source_game_session_id", "source_map_key", "source_dataset_fingerprint"):
        snapshot[key] = context[key]
    snapshot.update(navigation_intent_id="intent", request_id="intent")
    map_plugin._lane_authority_identity = tuple(snapshot[key] for key in (
        "navigation_intent_id", "request_id", "route_build_id",
        "source_game_session_id", "source_map_key", "source_dataset_fingerprint"))
    state.update_batch({
        "lane_trajectory": snapshot,
        "lane_trajectory_revision": snapshot["revision"],
        "game_route_node_uids": list(snapshot["source_gps_uids"]),
        "nav_recalc_request": "intent", "navigation_intent_id": "intent",
        "lane_match": map_sdk.get("lane_match"),
    })
    map_sdk.shared_state = state
    truck.update(x=point.x, y=point.y, z=point.z, rotation=point.heading,
                 referenceGeometry=observation["tractor_reference_geometry"])

    def tick(gear, speed, dt=.02):
        old_packet = state.get("nav_steering_debug")
        old_heartbeat = state.get("lane_trajectory_heartbeat")
        publish(gear, speed, dt=dt)
        # The telemetry producer doesn't create navigation packets. Only the
        # actual Map tick below is permitted to update the previous reference.
        state.set("nav_steering_debug", old_packet)
        state.set("lane_trajectory_heartbeat", old_heartbeat)
        map_plugin.on_tick(dt)
        plugin.on_tick(dt)

    tick(0, 0.)
    n()
    assert state.get("auto_drive_pending"), state.get("autopilot_disable_reason")
    tick(0, 0.)
    engine._flush_controls()
    assert engine.controller.throttle == .12
    tick(8, 0., .228)
    engine._flush_controls()
    tick(8, .2)
    engine._flush_controls()
    assert state.get("autopilot_active"), state.get("autopilot_disable_reason")
    assert engine._drive_engagement is None
    for speed in (1., 3.4, 9.2):
        tick(8, speed)
        engine._flush_controls()
        assert not engine._gps_propulsion_suppressed
        assert engine.controller.throttle > 0
        packet = state.get("nav_steering_debug")
        assert packet["sdk_frame_us"] == truck["sdkFrameTimeUs"]
        assert packet["observation_timestamp"] == clock[0]
    if fault is None:
        original_road_type = map_plugin._publish_road_type

        def slow_preparation(pos):
            original_road_type(pos)
            previous = state.get("nav_steering_debug")
            publish(8, 9.2, dt=.369)
            state.set("nav_steering_debug", previous)

        with mock.patch.object(map_plugin, "_publish_road_type", side_effect=slow_preparation):
            tick(8, 9.2)
        clock[0] += .204  # Delayed Engine consumption, not a renewed SDK time.
        engine._flush_controls()
        packet = state.get("nav_steering_debug")
        assert packet["observation_timestamp"] == clock[0] - .204
        assert packet["sdk_frame_us"] == truck["sdkFrameTimeUs"]
        assert state.get("autopilot_active"), state.get("autopilot_disable_reason")
        assert engine.controller.throttle > 0
        assert not engine._gps_propulsion_suppressed
        return
    if fault == "stale":
        clock[0] += .501
    elif fault == "revision":
        state.set("lane_trajectory_revision", snapshot["revision"] + 1)
    elif fault == "intent":
        state.set("navigation_intent_id", "replacement")
    else:
        n()
    plugin.on_tick(.02)
    engine._flush_controls()
    assert engine.controller.throttle == 0
    assert True not in engine.controller.drive_events
    assert not state.get("autopilot_active") or state.get("safety_hazard_active")
