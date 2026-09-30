"""A slow preparation cannot lend its timestamp to the control observation."""
import time
import threading
from unittest import mock

import pytest

from plugins.autopilot.main import navigation_command
from plugins.autopilot.main import Plugin as AutopilotPlugin
from tests.test_lane_authority_integration import build_map_plugin, Tags


def prepared_map():
    plugin, sdk, point = build_map_plugin()
    plugin.tags = Tags()
    sdk.set("truck_world_pos", (point.x, point.z))
    sdk.set("truck_heading", point.heading)
    sdk.set("truck_speed_ms", 0.)
    sdk.set("telemetry_valid", True)
    observation = {
        "timestamp": time.monotonic(), "sdk_frame_us": 1_000_000,
        "tractor_position": (point.x, point.y, point.z),
        "tractor_heading": point.heading, "tractor_speed_ms": 0.,
        "tractor_reference_geometry": dict(valid=True, source="synthetic_4x2",
            wheelbase_m=3.8, reference_ahead_m=2.1),
    }
    sdk.set("vehicle_envelope_snapshot", observation)
    return plugin, sdk, point, observation


@pytest.mark.parametrize("active", [False, True])
@pytest.mark.parametrize("phase,delay", [
    ("road_type", .369), ("reference", .369), ("lane_build", 1.171)])
def test_slow_preparation_uses_new_pose_frame_and_original_timestamp(active, phase, delay):
    plugin, sdk, point, old = prepared_map()
    sdk.set("autopilot_active", active)
    now = [old["timestamp"]]
    new = dict(old, sdk_frame_us=old["sdk_frame_us"] + int(delay * 1_000_000),
               tractor_position=(point.x, point.y, point.z + .1))

    def preparation(_pos):
        now[0] += delay
        new["timestamp"] = now[0]
        sdk.set("vehicle_envelope_snapshot", new)

    target, method = {
        "road_type": (plugin, "_publish_road_type"),
        "reference": (plugin._maneuver_reference_mux, "offer"),
        "lane_build": (plugin, "_update_lane_trajectory"),
    }[phase]
    original = getattr(target, method)
    prepared = [False]

    def slow(*args, **kwargs):
        result = original(*args, **kwargs)
        if not prepared[0]:
            preparation(None)
            prepared[0] = True
        return result

    with mock.patch("plugins.map.main.time.monotonic", side_effect=lambda: now[0]):
        with mock.patch.object(target, method, side_effect=slow):
            plugin.on_tick(.02)
    packet = sdk.get("nav_steering_debug")
    assert packet["sdk_frame_us"] == new["sdk_frame_us"]
    assert packet["observation_timestamp"] == new["timestamp"]
    assert tuple(packet["observation_xz"]) == (new["tractor_position"][0], new["tractor_position"][2])
    assert packet["computed_at"] - packet["observation_timestamp"] < .05
    snapshot = dict(sdk.get("lane_trajectory"))
    packet = dict(packet)
    for key, value in (("source_game_session_id", "synthetic-session"),
                       ("source_map_key", "test-map"),
                       ("source_dataset_fingerprint", "test-data")):
        snapshot[key] = packet[key] = value
    assert navigation_command(sdk.shared_state, snapshot, gps_active=True,
        packet=packet, now=now[0] + .204)[2] == ""


@pytest.mark.parametrize("key,value", [
    ("navigation_intent_id", "replacement-intent"),
    ("lane_trajectory_revision", 999), ("game_session_id", 999),
    ("active_map_key", "replacement-map"),
    ("active_dataset_fingerprint", "replacement-data"),
])
def test_identity_change_during_preparation_never_publishes_authority(key, value):
    plugin, sdk, point, observation = prepared_map()
    with mock.patch.object(plugin, "_publish_road_type",
                           side_effect=lambda _pos: sdk.set(key, value)):
        plugin.on_tick(.02)
    assert sdk.get("nav_active") is False
    assert sdk.get("nav_steering", 0.) == 0.


def test_expired_observation_is_not_retimestamped_or_published():
    plugin, sdk, point, observation = prepared_map()
    with mock.patch("plugins.map.main.time.monotonic", return_value=observation["timestamp"] + .6):
        plugin.on_tick(.02)
    assert sdk.get("nav_active") is False
    assert sdk.get("nav_steering", 0.) == 0.
    assert sdk.get("vehicle_envelope_snapshot")["timestamp"] == observation["timestamp"]


def test_handoff_delay_keeps_the_existing_500_ms_rejection():
    plugin, sdk, point, observation = prepared_map()
    plugin.on_tick(.02)
    packet = sdk.get("nav_steering_debug")
    snapshot = sdk.get("lane_trajectory")
    for key, value in (("source_game_session_id", 1),
                       ("source_map_key", "test-map"),
                       ("source_dataset_fingerprint", "test-data")):
        packet[key] = snapshot[key] = value
    assert navigation_command(sdk.shared_state, snapshot, gps_active=True,
        packet=packet, now=packet["observation_timestamp"] + .204)[2] == ""
    assert navigation_command(sdk.shared_state, snapshot, gps_active=True,
        packet=packet, now=packet["observation_timestamp"] + .501)[2] in (
            "steering command observation_timestamp is stale",
            "steering command computed_at is stale")


def test_cached_geometry_avoids_repeated_ipc_and_changes_with_build():
    plugin, sdk, point, observation = prepared_map()
    plugin.on_tick(.02)
    snapshot = sdk.get("lane_trajectory")
    packet = sdk.get("nav_steering_debug")
    for key, value in (("source_game_session_id", 1),
                       ("source_map_key", "test-map"),
                       ("source_dataset_fingerprint", "test-data")):
        snapshot[key] = packet[key] = value
    ap = AutopilotPlugin(sdk)
    original = sdk.shared_state.get
    reads = []

    def read(key, default=None):
        reads.append(key)
        return original(key, default)

    with mock.patch.object(sdk.shared_state, "get", side_effect=read):
        first, first_packet = ap._read_navigation_inputs()
        second, second_packet = ap._read_navigation_inputs()
        assert first is second
        assert first_packet == second_packet
        assert reads.count("lane_trajectory") == 1
        snapshot["route_build_id"] = packet["route_build_id"] = "new-build"
        ap._read_navigation_inputs()
        assert reads.count("lane_trajectory") == 2


def test_route_build_change_with_same_revision_during_preparation_is_rejected():
    plugin, sdk, point, observation = prepared_map()

    def changed(_pos):
        snapshot = dict(sdk.get("lane_trajectory"))
        snapshot["route_build_id"] = "replacement-build"
        sdk.set("lane_trajectory", snapshot)

    with mock.patch.object(plugin, "_publish_road_type", side_effect=changed):
        plugin.on_tick(.02)
    assert sdk.get("nav_active") is False
    assert "route" in sdk.get("steering_observation_failure")


def test_new_observation_on_other_height_cannot_use_old_lane_match():
    plugin, sdk, point, observation = prepared_map()

    def changed(_pos):
        sdk.set("vehicle_envelope_snapshot", dict(observation,
            sdk_frame_us=1_100_000, timestamp=time.monotonic(),
            tractor_position=(point.x, point.y + 15., point.z)))

    with mock.patch.object(plugin, "_publish_road_type", side_effect=changed):
        plugin.on_tick(.02)
    assert sdk.get("nav_active") is False
    assert sdk.get("lane_match")["valid"] is False


def test_optional_export_does_not_hold_fresh_packet_and_has_no_queue():
    plugin, sdk, point, observation = prepared_map()
    entered, release = threading.Event(), threading.Event()
    sdk.set("route_diagnostic_export_request", "test-build")

    def export():
        entered.set()
        assert release.wait(2.)

    try:
        with mock.patch.object(plugin, "_handle_diagnostic_export", side_effect=export) as handler:
            plugin.on_tick(.02)
            assert entered.wait(1.)
            assert sdk.get("nav_active") is True
            plugin._schedule_diagnostic_export()
            assert handler.call_count == 1
    finally:
        release.set()


def activation_reason_after_read(delay, packet_age):
    from core.engine import UltraPilotEngine
    from tests.test_control_safety_regressions import ready_navigation_state
    now = [100.]
    state = ready_navigation_state(autopilot_active=False, nav_active=True)
    snapshot = state.get("lane_trajectory")
    state.set("lane_trajectory_heartbeat", 100.)
    state.set("autopilot_navigation_readiness", {
        "ready": True, "timestamp": 100., "source": "gps_lane", "revision": 7})
    state.set("telemetry", {"truck": {
        "gear": 4, "speed": 0.0, "sdkFrameTimeUs": 1_000_000}})
    state.set("telemetry_timestamp", 100.)
    packet = dict(snapshot, controller="frenet_bicycle",
        calculation_packet_schema_version=1, authority_valid=True,
        authority_revision=7, observation_timestamp=100. - packet_age,
        computed_at=100. - packet_age,
        output=0., local_curvature=0.)
    state.set("nav_steering_debug", packet)
    original = state.get

    def read(key, default=None):
        if key == "telemetry":
            now[0] += delay
        if key == "lane_trajectory_heartbeat":
            return now[0]  # heartbeat is fresh, independently of the packet
        return original(key, default)

    engine = UltraPilotEngine.__new__(UltraPilotEngine)
    engine.shared_state = state
    with mock.patch.object(state, "get", side_effect=read):
        with mock.patch("core.engine.time.monotonic", side_effect=lambda: now[0]):
            reason = engine._autopilot_activation_rejection_reason()
    return reason


def test_activation_validates_packet_after_slow_telemetry_ipc():
    reason = activation_reason_after_read(.369, .2)
    assert "steering command" in reason and "stale" in reason


def test_almost_expired_packet_does_not_grant_an_instant_of_authority():
    reason = activation_reason_after_read(0., .494)
    assert "next control tick" in reason


def test_same_frame_mutation_during_preparation_is_rejected():
    plugin, sdk, point, observation = prepared_map()
    with mock.patch.object(plugin, "_publish_road_type", side_effect=lambda _pos:
        sdk.set("vehicle_envelope_snapshot", dict(observation,
            tractor_position=(point.x, point.y, point.z + .1)))):
        plugin.on_tick(.02)
    assert sdk.get("nav_active") is False
    assert "one SDK frame changed" in sdk.get("steering_observation_failure")


def test_slow_preparation_without_a_new_sdk_frame_does_not_publish_old_work():
    plugin, sdk, point, observation = prepared_map()
    now = [observation["timestamp"]]
    with mock.patch("plugins.map.main.time.monotonic", side_effect=lambda: now[0]):
        with mock.patch.object(plugin, "_publish_road_type",
                               side_effect=lambda _pos: now.__setitem__(0, now[0] + .369)):
            plugin.on_tick(.02)
    assert sdk.get("nav_active") is False
    assert "frame did not advance" in sdk.get("steering_observation_failure")
