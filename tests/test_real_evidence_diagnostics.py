"""Diagnostic collection is bounded, atomic and has no driving authority."""

import json

import pytest

from core.navigation.evidence_diagnostics import (
    DiagnosticCapture, EvidenceDiagnosticCollector, atomic_json_write,
    inspect_collection, read_json,
)
from core.navigation.traffic_producer import TrafficCapture
from core.sdk.ets2la_data import _PARKED_SIZE, _TRAFFIC_SIZE
from tools.manage_maneuver_diagnostics import main as diagnostic_cli


def root(tmp_path):
    return tmp_path / "evidence-diagnostics"


def command(sequence, action="arm", collection_id="cab-01", **values):
    result = {"schema_version": 1, "sequence": sequence, "action": action,
              "collection_id": collection_id}
    if action == "arm":
        result.update(purpose="combined", max_duration_s=180.0,
                      sample_period_s=0.1)
    result.update(values)
    return result


def capture(index, *, when=10.0, configuration="cfg-a", map_key="map-a"):
    observed = when + index * 0.1
    identity = {
        "navigation_intent_id": "intent-a", "route_build_id": "build-a",
        "revision": 4, "source_game_session_id": "session-a",
        "source_map_key": map_key, "source_dataset_fingerprint": "dataset-a",
    }
    profile = {
        "token": {"configuration": configuration},
        "observation": {
            "sdk_frame_us": 1_000_000 + index,
            "captured_at": observed, "atomic": False, "stable_read": True,
            "articles": [{
                "slot": -1, "attached": True, "vehicle_id": "truck.a",
                "brand_id": "brand.a", "body_type": "tractor",
                "chain_type": "", "cargo_accessory_id": "",
                "hook_local_m": [0.0, 1.0, 2.0],
                "position_m": [100.0 + index * 0.1, 12.0, 200.0],
                "rotation_rad": [0.0, 0.0, 0.0],
                "wheels": [{"index": 0, "position_m": [-1.0, -0.5, 1.0],
                            "radius_m": 0.5, "steerable": False,
                            "simulated": True, "powered": True,
                            "liftable": False, "on_ground": True,
                            "lift": 0.0, "lift_offset_m": 0.0,
                            "steering_right_rad": 0.0}],
            }],
        },
    }
    source = {**identity, "authority_revision": identity["revision"],
              "sdk_frame_us": 1_000_000 + index,
              "calculation_sequence": index + 1, "reference_mode": "global_lane",
              "lane_match_snapshot": {"active_lane_id": {"uid": 7, "lane": 1},
                                      "lateral_error_m": 0.02,
                                      "heading_error_rad": 0.001},
              "local_curvature": 0.002, "tracking_projection_xz": [100.0, 200.0],
              "local_tangent_heading_rad": 0.0}
    return DiagnosticCapture(
        index + 1, observed, 0.2, True, True, True,
        {"sdkFrameTimeUs": 1_000_000 + index, "speed": 3.0,
         "gameSteer": -0.2, "rotation": 0.0, "x": 100.0 + index * 0.1,
         "y": 12.0, "z": 200.0, "pose_valid": True,
         "roadWheelAnglesRad": [0.1], "yawRateRadS": 0.006,
         "yawRateValid": True},
        profile, TrafficCapture("session-a", observed, bytes(_TRAFFIC_SIZE),
                                bytes(_PARKED_SIZE), True),
        {**identity, "valid": True, "confidence": 1.0,
         "active_lane_id": {"uid": 7, "lane": 1},
         "source_gps_uids": [7, 8], "elevation_layer": 12},
        {**identity, "mode": "global_lane", "authority_valid": True,
         "sequence": index + 1},
        {"output": 0.2, "raw": 0.2, "executor_active": True,
         "target_fresh": True, "execution_monotonic_s": observed,
         "submission_sequence": index + 1, "source_packet": source},
        {"schema_version": 1, "tyre_angle_per_input_rad": 0.7,
         "command_delay_s": 0.067, "observation_delay_s": 0.067,
         "source": "measured-candidate"},
        0.0, None, None)


def test_diagnostic_default_is_disabled_and_never_authorizes(tmp_path):
    collector = EvidenceDiagnosticCollector(root(tmp_path), capacity=30)
    status = collector.status()
    assert status["state"] == "DISABLED"
    assert status["runtime_authorized"] is False
    assert status["confirmed"] is False
    assert not collector.should_sample(10.0)


def test_arm_collect_finish_exports_only_unconfirmed_candidates(tmp_path):
    collector = EvidenceDiagnosticCollector(root(tmp_path), capacity=30)
    collector.apply_command(command(1))
    assert collector.state == "ARMED"
    for index in range(30):
        collector._ingest(capture(index))
    collector.apply_command(command(2, "finish"))
    assert collector.state == "READY_FOR_OFFLINE_REVIEW"
    result = inspect_collection(root(tmp_path) / "cab-01")
    assert result == {"integrity_valid": True, "file_count": 8,
                      "sample_count": 30, "confirmed": False,
                      "runtime_authorized": False,
                      "qualification": "READY_FOR_OFFLINE_REVIEW"}
    profile = read_json(root(tmp_path) / "cab-01" / "body-profile-candidate.json")
    configuration = read_json(
        root(tmp_path) / "cab-01" / "configuration-identity-candidate.json")
    traffic = read_json(root(tmp_path) / "cab-01" / "traffic-coverage-observations.json")
    survey = read_json(root(tmp_path) / "cab-01" / "surface-survey-candidate.json")
    tracking = read_json(root(tmp_path) / "cab-01" / "tracking-samples-candidate.json")
    assert profile["qualification"] == "MISSING_CONFIRMED_BODY_PROFILE"
    assert configuration["truck_model_identifier"] == "truck.a"
    assert configuration["cabin_identifier"] is None
    assert configuration["chassis_identifier"] is None
    assert configuration["accessory_inventory_complete"] is False
    assert configuration["qualification"] == "MISSING_COMPLETE_ACTIVE_CONFIGURATION"
    assert configuration["confirmed"] is False
    assert configuration["runtime_authorized"] is False
    assert profile["manual_article_measurements"][0]["measurements"][0]["value"] is None
    assert not traffic["complete"] and traffic["sensor_range_m"] is None
    assert survey["exterior_xyz"] == [] and not survey["trace_is_drivable_boundary"]
    assert not tracking["local_maneuver_qualification"]
    assert all(not value["runtime_authorized"] and not value["confirmed"]
               for value in (profile, traffic, survey, tracking))


def test_stale_frame_rejects_and_disable_clears_ring(tmp_path):
    collector = EvidenceDiagnosticCollector(root(tmp_path), capacity=30)
    collector.apply_command(command(1))
    collector._ingest(capture(0))
    collector._ingest(capture(1, when=9.8))
    assert collector.state == "REJECTED_STALE"
    collector.apply_command(command(2, "disable", collection_id=None))
    assert collector.state == "DISABLED"
    assert collector.status()["sample_count"] == 0


def test_ring_and_work_queue_are_bounded(tmp_path):
    collector = EvidenceDiagnosticCollector(root(tmp_path), capacity=30)
    collector.apply_command(command(1))
    for index in range(35):
        collector._ingest(capture(index))
    assert collector.status()["sample_count"] == 30
    assert collector.status()["dropped_samples"] == 5
    first = capture(100)
    second = capture(101)
    assert collector.offer(first)
    assert not collector.offer(second)


def test_interrupted_atomic_write_preserves_previous_file(tmp_path):
    path = root(tmp_path) / "status.json"
    atomic_json_write(path, {"old": True})
    with pytest.raises(OSError):
        atomic_json_write(path, {"new": True},
                          replace=lambda *_: (_ for _ in ()).throw(OSError("interrupted")))
    assert json.loads(path.read_text(encoding="utf-8")) == {"old": True}
    assert not list(path.parent.glob(".status.json.*.tmp"))


def test_cli_requires_explicit_arm_and_writes_no_authority(tmp_path, capsys):
    settings = tmp_path / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    output = root(tmp_path)
    assert diagnostic_cli(["status", "--output", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "DISABLED"
    assert diagnostic_cli(["arm", "--settings", str(settings), "--output", str(output),
                           "--collection-id", "truck-a", "--purpose", "cab_profile",
                           "--duration", "60"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["armed"] and not result["runtime_authorized"]
    configured = json.loads(settings.read_text(encoding="utf-8"))
    assert configured["maneuver_evidence_diagnostics"]["enabled"] is True
    control = read_json(output / "control.json")
    assert control["action"] == "arm" and control["collection_id"] == "truck-a"


def test_manifest_tampering_and_wrong_output_are_rejected(tmp_path):
    with pytest.raises(ValueError, match="OUTPUT"):
        EvidenceDiagnosticCollector(tmp_path / "other", capacity=30)
    with pytest.raises(ValueError, match="OUTPUT"):
        EvidenceDiagnosticCollector(
            tmp_path / "route-diagnostics" / "maneuver-evidence", capacity=30)
    collector = EvidenceDiagnosticCollector(root(tmp_path), capacity=30)
    collector.apply_command(command(1))
    for index in range(30):
        collector._ingest(capture(index))
    collector.finalize()
    target = root(tmp_path) / "cab-01" / "tracking-samples-candidate.json"
    target.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="INTEGRITY"):
        inspect_collection(root(tmp_path) / "cab-01")


def test_command_binding_rejects_stale_executor_packet(tmp_path):
    collector = EvidenceDiagnosticCollector(root(tmp_path), capacity=30)
    collector.apply_command(command(1))
    value = capture(0)
    value = DiagnosticCapture(**{**value.__dict__, "applied_target": {
        **value.applied_target, "execution_monotonic_s": value.captured_at_s - 0.2}})
    collector._ingest(value)
    assert collector._rows[-1]["command_binding_proven"] is False


def test_engine_boundary_only_offers_after_unchanged_physical_write():
    from tests.test_stage4d_control_timing import EngineRealtimeBoundaryTests, State

    class Collector:
        def __init__(self):
            self.offered = []

        def should_sample(self, _now):
            return True

        def offer(self, value):
            self.offered.append(value)
            return True

    state = State({
        "autopilot_active": True, "telemetry_valid": True,
        "autopilot_control_heartbeat": __import__("time").monotonic(),
        "ctl_steering": 0.2, "ctl_throttle": 0.0, "ctl_brake": 0.0,
        "truck_speed_ms": 3.0, "navigation_source": "gps_lane", "nav_active": True,
        "lane_trajectory_revision": 4, "autopilot_lane_revision": 4,
        "lane_trajectory": {"valid": True, "revision": 4},
        "telemetry": {"truck": {"sdkFrameTimeUs": 1_000_000}},
        "active_navigation_reference": {"mode": "global_lane", "authority_valid": True},
    })
    engine = EngineRealtimeBoundaryTests.bare_engine(state)
    engine.controller = EngineRealtimeBoundaryTests.FakeController()
    engine._maneuver_diagnostic_collector = Collector()
    engine._maneuver_diagnostic_sequence = 0
    engine._maneuver_tracking_recorder = None
    engine._flush_controls_unlocked()
    assert engine.controller.steering_writes == [0.2]
    assert len(engine._maneuver_diagnostic_collector.offered) == 1
    assert engine._maneuver_diagnostic_collector.offered[0].engine_steer == 0.2
    assert state.get("runtime_authorized") is None


def test_manual_driver_can_collect_profile_without_backend_command():
    from tests.test_stage4d_control_timing import EngineRealtimeBoundaryTests, State

    class Collector:
        def __init__(self):
            self.offered = []

        def should_sample(self, _now):
            return True

        def offer(self, value):
            self.offered.append(value)
            return True

    state = State({"autopilot_active": False, "telemetry_valid": True,
                   "telemetry": {"truck": {"sdkFrameTimeUs": 1_000_000}}})
    engine = EngineRealtimeBoundaryTests.bare_engine(state)
    engine.controller = EngineRealtimeBoundaryTests.FakeController()
    engine._maneuver_diagnostic_collector = Collector()
    engine._maneuver_diagnostic_sequence = 0
    engine._flush_controls_unlocked()
    assert engine.controller.steering_writes == []
    captured = engine._maneuver_diagnostic_collector.offered[0]
    assert captured.backend_sent is False and captured.engine_steer is None
    assert state.get("runtime_authorized") is None


def test_control_boundary_contains_no_json_or_planner_work():
    import inspect
    from core.engine import UltraPilotEngine

    code = inspect.getsource(UltraPilotEngine._flush_controls_unlocked)
    helper = inspect.getsource(UltraPilotEngine._offer_maneuver_evidence_diagnostic)
    assert "json." not in code + helper
    assert "self.planner" not in code + helper
    assert "build_maneuver" not in code + helper
    assert ".export(" not in code + helper
    producer = (__import__("pathlib").Path(__file__).resolve().parents[1]
                / "core" / "navigation" / "evidence_diagnostics.py").read_text()
    for forbidden in (".set_steering(", ".set_throttle(", ".set_brake(",
                      "SteeringDynamics(", "SteeringExecutor("):
        assert forbidden not in producer


def test_autopilot_diagnostic_binding_is_observational_only():
    from plugins.autopilot.main import Plugin

    class State(dict):
        def set(self, key, value):
            self[key] = value

    class Executor:
        running = True
        output = 0.125
        last_debug = {"output": 0.125}

        def submit(self, target, **values):
            self.target = target
            self.values = values

    plugin = Plugin.__new__(Plugin)
    plugin.sdk = type("SDK", (), {"shared_state": State(
        maneuver_evidence_diagnostic_active=True)})()
    plugin._steering_executor = Executor()
    plugin._accepted_navigation_command = {
        "reference_mode": "global_lane", "calculation_sequence": 8}
    plugin._steering_dynamics_debug = {}
    plugin._last_steering = 0.125
    assert plugin._ramp_steering(0.2, 0.02, speed_ms=3.0,
                                 curvature_per_m=0.01) == 0.125
    assert plugin._steering_executor.values["source_packet"]["calculation_sequence"] == 8
    assert plugin._steering_executor.target == 0.2

    plugin._steering_replay = None
    plugin._last_execution_timing_publish = 20.0
    plugin._accepted_navigation_command = {}
    plugin._observe_steering_execution({
        "output": 0.125, "execution_monotonic_s": 10.0,
        "source_packet": {"reference_mode": "global_lane"}})
    assert plugin.sdk.shared_state["maneuver_diagnostic_applied_target"]["output"] == 0.125
