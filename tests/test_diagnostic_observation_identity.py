"""Game observation identity is independent of a removed GPS destination."""
from copy import deepcopy

import pytest

from core.navigation.evidence_diagnostics import (
    EvidenceDiagnosticCollector, capture_diagnostic_application, inspect_collection,
)
from tests.test_real_evidence_diagnostics import capture, command, root


def state_at(index):
    seed = capture(index)
    return dict(telemetry={"truck": seed.truck}, telemetry_valid=True,
        vehicle_profile_snapshot=seed.profile, lane_trajectory=seed.lane,
        maneuver_diagnostic_applied_target=seed.applied_target,
        game_session_id="session-a", active_map_key="map-a",
        active_dataset_fingerprint="dataset-a", autopilot_active=True)


def take(state, index):
    return capture_diagnostic_application(state, .2, 10. + index * .1, index + 1)


def test_removed_destination_is_not_a_new_game_session(tmp_path):
    collector = EvidenceDiagnosticCollector(root(tmp_path), capacity=130)
    collector.apply_command(command(1))
    collector._ingest(take(state_at(0), 0))
    state = state_at(1)
    # Exact invalid snapshot shape published by Engine when GPS target clears.
    state["lane_trajectory"] = dict(revision=5, valid=False, confidence=0.,
        active_lane_id=None, lane_match=None, points=[], display_points=[],
        distance_m=0., failure_reason="V hernom GPS nie je zvolený cieľ",
        source_gps_uids=[], request_id=None)
    state["autopilot_active"] = False
    collector._ingest(take(state, 1))
    assert collector.state == "COLLECTING", collector.status()
    assert collector.status()["sample_count"] == 2
    assert collector._rows[-1]["lane"]["valid"] is False
    assert collector._rows[-1]["lane"]["source_game_session_id"] is None


@pytest.mark.parametrize("key,new", [("game_session_id", "session-b"),
    ("active_map_key", "map-b"), ("active_dataset_fingerprint", "dataset-b")])
def test_current_domain_change_rejects_even_with_old_route_packet(tmp_path, key, new):
    collector = EvidenceDiagnosticCollector(root(tmp_path), capacity=130)
    collector.apply_command(command(1))
    collector._ingest(take(state_at(0), 0))
    state = state_at(1)
    state[key] = new  # Still old lane/source packet: must not hide actual change.
    collector._ingest(take(state, 1))
    assert collector.state == "REJECTED_IDENTITY_CHANGED", collector.status()
    assert collector.status()["sample_count"] == 1
    collector.apply_command(command(2, "finish"))
    checked = inspect_collection(root(tmp_path) / "cab-01")
    assert checked["integrity_valid"] and not checked["collection_complete"]
    assert checked["termination"]["observed_identity"] != checked["termination"]["previous_identity"]


def test_missing_domain_skips_without_guessing_then_resumes(tmp_path):
    collector = EvidenceDiagnosticCollector(root(tmp_path), capacity=130)
    collector.apply_command(command(1))
    collector._ingest(take(state_at(0), 0))
    state = state_at(1)
    state["game_session_id"] = None
    collector._ingest(take(state, 1))
    assert collector.state == "COLLECTING", collector.status()
    assert collector.status()["sample_count"] == 1
    assert collector.status()["skipped_identity_samples"] == 1
    assert collector._last_sdk_frame == 1_000_000
    collector._ingest(take(state_at(2), 2))
    assert collector.status()["sample_count"] == 2


def test_concurrent_domain_publication_does_not_mix_sessions(tmp_path):
    collector = EvidenceDiagnosticCollector(root(tmp_path), capacity=130)
    collector.apply_command(command(1))
    collector._ingest(take(state_at(0), 0))

    class ChangingState(dict):
        def get(self, key, default=None):
            if key == "vehicle_profile_snapshot":
                self["game_session_id"] = "session-b"
            return super().get(key, default)

    state = ChangingState(deepcopy(state_at(1)))
    collector._ingest(take(state, 1))
    assert collector.state == "COLLECTING", collector.status()
    assert collector.status()["sample_count"] == 1
    assert collector.status()["skipped_identity_samples"] == 1
    later = state_at(2)
    later["game_session_id"] = "session-b"
    collector._ingest(take(later, 2))
    assert collector.state == "REJECTED_IDENTITY_CHANGED"


def test_new_route_build_in_same_observation_domain_is_retained(tmp_path):
    collector = EvidenceDiagnosticCollector(root(tmp_path), capacity=130)
    collector.apply_command(command(1))
    collector._ingest(take(state_at(0), 0))
    state = state_at(1)
    state["lane_trajectory"].update(revision=5, route_build_id="build-b")
    state["maneuver_diagnostic_applied_target"]["source_packet"].update(
        revision=5, authority_revision=5, route_build_id="build-b")
    collector._ingest(take(state, 1))
    assert collector.state == "COLLECTING"
    assert [r["route_build_id"] for r in collector._rows] == ["build-a", "build-b"]


@pytest.mark.parametrize("key,value", [("game_session_id", 0),
    ("active_map_key", None), ("active_dataset_fingerprint", "unavailable")])
def test_startup_unknown_domain_is_not_bound_or_inferred_from_lane(tmp_path, key, value):
    collector = EvidenceDiagnosticCollector(root(tmp_path), capacity=130)
    collector.apply_command(command(1))
    state = state_at(0)
    state[key] = value
    collector._ingest(take(state, 0))
    assert collector.state == "ARMED"
    assert collector.status()["sample_count"] == 0
    assert collector._last_observation_identity is None
    collector._ingest(take(state_at(1), 1))
    assert collector.state == "COLLECTING"
    assert collector._rows[-1]["observation_identity"]["atomic"] is False
    assert collector._rows[-1]["sdk_frame_us"] == 1_000_001


def test_partial_identity_does_not_hide_expired_sdk_or_renew_last_frame(tmp_path):
    collector = EvidenceDiagnosticCollector(root(tmp_path), capacity=130)
    collector.apply_command(command(1))
    collector._ingest(take(state_at(0), 0))
    state = state_at(1)
    state["game_session_id"] = None
    state["vehicle_profile_snapshot"]["observation"]["captured_at"] = 9.
    collector._ingest(take(state, 1))
    assert collector.state == "REJECTED_STALE"
    assert collector.status()["rejection_detail"] == "DIAGNOSTIC_SDK_OBSERVATION_EXPIRED"
    assert collector._last_sdk_frame == 1_000_000


def test_finish_keeps_skipped_identity_count_without_claiming_authority(tmp_path):
    collector = EvidenceDiagnosticCollector(root(tmp_path), capacity=130)
    collector.apply_command(command(1))
    collector._ingest(take(state_at(0), 0))
    state = state_at(1)
    state["game_session_id"] = None
    collector._ingest(take(state, 1))
    for index in range(2, 31):
        collector._ingest(take(state_at(index), index))
    collector.apply_command(command(2, "finish"))
    assert collector.state == "READY_FOR_OFFLINE_REVIEW", collector.status()
    checked = inspect_collection(root(tmp_path) / "cab-01")
    assert checked["sample_count"] == 30
    assert checked["skipped_identity_samples"] == 1
    assert checked["confirmed"] is False and checked["runtime_authorized"] is False
