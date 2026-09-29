"""A parked, inactive autopilot still retains a readable phase trace."""

import json
import tempfile
import time
from pathlib import Path
from unittest import mock

from plugins.autopilot.main import Plugin as AutopilotPlugin
from plugins.autopilot.main import navigation_command
from core.steering_replay import (
    PUBLISH_IDENTITY_FIELDS, SteeringReplayBuffer, publish_receipt_matches,
)
from tests.test_lane_authority_integration import (
    Controller, Tags, Telemetry, build_map_plugin,
)


def test_inactive_autopilot_exports_bound_timing_on_orderly_stop():
    map_plugin, sdk, point = build_map_plugin()
    map_plugin.tags = Tags()
    sdk.set("truck_world_pos", (point.x, point.z))
    sdk.set("truck_heading", point.heading)
    sdk.set("truck_speed_ms", 0.0)
    sdk.set("telemetry_valid", True)
    sdk.set("vehicle_envelope_snapshot", {
        "timestamp": time.monotonic(), "sdk_frame_us": 1_000_000,
        "tractor_position": (point.x, point.y, point.z),
        "tractor_heading": point.heading, "tractor_speed_ms": 0.0,
        "tractor_reference_geometry": dict(
            valid=True, source="synthetic_4x2", wheelbase_m=3.8,
            reference_ahead_m=2.1),
    })
    map_plugin.on_tick(0.02)
    sdk.controller = Controller()
    sdk.telemetry = Telemetry()
    sdk.set("autopilot_active", False)
    autopilot = AutopilotPlugin(sdk)
    autopilot.tags = Tags()
    autopilot.on_start()
    autopilot.on_tick(0.02)
    assert len(autopilot._passive_steering_timing) == 1

    audit_dir = Path(__file__).resolve().parents[1] / "docs" / "steering-audit"
    with tempfile.TemporaryDirectory(prefix="passive-timing-", dir=audit_dir) as target:
        with mock.patch("plugins.autopilot.main.app_dir", return_value=target):
            autopilot.on_stop()
        exports = list((Path(target) / "route-diagnostics").glob(
            "steering-timing-*.json"))
        assert len(exports) == 1
        document = json.loads(exports[0].read_text(encoding="utf-8"))
    assert document["sample_kind"] == "passive_phase_timing"
    assert document["sample_count"] == 1
    row = document["samples"][0]
    packet = sdk.get("nav_steering_debug")
    assert row["calculation_sequence"] == packet["calculation_sequence"]
    assert row["sdk_frame_us"] == packet["sdk_frame_us"]
    assert row["route_build_id"] == packet["route_build_id"]
    assert row["map_packet_publish_completed_at"] >= row[
        "map_packet_publish_started_at"]
    assert row["autopilot_active"] is False


def test_inactive_missing_packet_is_exported_as_missing_not_faked():
    plugin = AutopilotPlugin.__new__(AutopilotPlugin)
    state = type("State", (), {"get": lambda self, key, default=None: {
        "autopilot_active": False,
    }.get(key, default)})()
    plugin.sdk = type("SDK", (), {"shared_state": state})()
    plugin._passive_steering_timing = SteeringReplayBuffer(8)
    plugin._last_passive_timing_at = 0.0
    plugin._last_passive_timing_sequence = None
    plugin._record_passive_steering_timing(
        {"sdkFrameTimeUs": 456}, {"revision": 8, "route_build_id": "build"},
        {}, 10.0, 10.02)
    row = plugin._passive_steering_timing.snapshot()[0]
    assert row["packet_available"] is False
    assert row["identity_matches"] is False
    assert row["calculation_sequence"] is None
    assert row["route_build_id"] == "build"


def test_incident_231_plus_204_ms_is_visible_and_expires_without_renewal():
    identity = {
        "navigation_intent_id": "intent-28", "route_build_id": "build-28",
        "source_game_session_id": 1, "source_map_key": "promods-1.59",
        "source_dataset_fingerprint": "dataset-28",
    }
    snapshot = {**identity, "revision": 8}
    packet = {
        **identity, "controller": "frenet_bicycle",
        "calculation_packet_schema_version": 1,
        "authority_valid": True, "authority_revision": 8,
        "calculation_sequence": 302, "sdk_frame_us": 127228244,
        "observation_timestamp": 3170.513,
        "map_lane_update_finished_at": 3170.571,
        "map_calculation_started_at": 3170.802,
        "computed_at": 3170.803,
        "map_packet_publish_started_at": 3170.804,
        "output": -0.065, "local_curvature": 0.0,
    }
    state = type("State", (), {"get": lambda self, key, default=None: {
        "map_steering_publish_receipt": {
            "sequence": 302, "sdk_frame_us": 127228244,
            "identity": {key: packet.get(key) for key in (
                "navigation_intent_id", "route_build_id",
                "authority_revision", "source_game_session_id",
                "source_map_key", "source_dataset_fingerprint")},
            "completed_at": 3170.850},
        "autopilot_active": False,
    }.get(key, default)})()
    plugin = AutopilotPlugin.__new__(AutopilotPlugin)
    plugin.sdk = type("SDK", (), {"shared_state": state})()
    plugin._passive_steering_timing = SteeringReplayBuffer(8)
    plugin._last_passive_timing_at = 0.0
    plugin._last_passive_timing_sequence = None
    plugin._record_passive_steering_timing(
        {"sdkFrameTimeUs": 127678226}, snapshot, packet,
        3170.990, 3171.007)
    row = plugin._passive_steering_timing.snapshot()[0]
    assert round((row["map_calculation_started_at"]
                  - row["map_lane_update_finished_at"]) * 1000) == 231
    assert round((row["autopilot_packet_read_finished_at"]
                  - row["computed_at"]) * 1000) == 204
    assert round(row["observation_age_at_read_s"] * 1000) == 494
    _steer, _curve, before = navigation_command(
        state, snapshot, gps_active=True, now=3171.007, packet=packet)
    _steer, _curve, after = navigation_command(
        state, snapshot, gps_active=True, now=3171.020, packet=packet)
    assert before == ""
    assert after == "steering command observation_timestamp is stale"


def test_publish_receipt_needs_frame_and_route_identity_not_just_sequence():
    packet = {"calculation_sequence": 4, "sdk_frame_us": 200,
              **{key: "route-a" for key in PUBLISH_IDENTITY_FIELDS}}
    receipt = {"sequence": 4, "sdk_frame_us": 200,
               "identity": {key: "route-a" for key in PUBLISH_IDENTITY_FIELDS}}
    assert publish_receipt_matches(receipt, packet)
    assert not publish_receipt_matches({**receipt, "sdk_frame_us": 201}, packet)
    assert not publish_receipt_matches({**receipt, "identity": {
        **receipt["identity"], "route_build_id": "route-b"}}, packet)
