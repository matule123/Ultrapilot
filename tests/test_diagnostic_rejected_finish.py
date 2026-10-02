"""Repeated SDK reads and rejected partial exports are never new authority."""
from copy import deepcopy
from dataclasses import replace

import pytest

from core.navigation.evidence_diagnostics import (
    EvidenceDiagnosticCollector, atomic_json_write, inspect_collection, read_json,
)
from tests.test_real_evidence_diagnostics import capture, command, root


def collector_at(tmp_path, count=3):
    collector = EvidenceDiagnosticCollector(root(tmp_path), capacity=130)
    collector.apply_command(command(1))
    for index in range(count):
        collector._ingest(capture(index))
    return collector


@pytest.mark.parametrize("same_time", [False, True])
def test_duplicate_is_skipped_without_renewing_evidence_and_next_frame_continues(tmp_path, same_time):
    collector = collector_at(tmp_path)
    old = deepcopy(collector._rows[-1])
    duplicate = capture(2)
    if not same_time:
        duplicate = replace(duplicate, sequence=4, captured_at_s=10.3)
    collector._ingest(duplicate)
    status = collector.status()
    assert status["state"] == "COLLECTING"
    assert status["sample_count"] == 3
    assert status["skipped_duplicate_samples"] == 1
    assert collector._rows[-1] == old
    assert collector._last_capture_s == old["captured_at_s"]
    collector._ingest(capture(4))
    assert collector.status()["sample_count"] == 4
    assert collector._rows[-1]["sdk_frame_us"] == 1_000_004


@pytest.mark.parametrize("fault", ["expired_duplicate", "expired_new_frame", "time", "frame", "invalid", "nonfinite_frame"])
def test_invalid_frame_rejects_and_cannot_resume_implicitly(tmp_path, fault):
    collector = collector_at(tmp_path)
    bad = capture(3)
    if fault == "expired_duplicate":
        bad = replace(capture(2), sequence=4, captured_at_s=10.6)
    elif fault == "expired_new_frame":
        bad.profile["observation"]["captured_at"] = 9.8
    elif fault == "time":
        bad = replace(bad, captured_at_s=10.1)
    elif fault == "frame":
        bad.truck["sdkFrameTimeUs"] = 999_999
    elif fault == "nonfinite_frame":
        bad.truck["sdkFrameTimeUs"] = float("nan")
    else:
        bad = replace(bad, telemetry_valid=False)
    collector._ingest(bad)
    rejected = collector.status()
    assert rejected["state"] == "REJECTED_STALE"
    assert rejected["sample_count"] == 3
    assert rejected["rejected_samples"] == 1
    assert rejected["rejection_detail"]
    assert not rejected["accepting_samples"]
    collector._ingest(capture(5))
    assert collector.status() == rejected


@pytest.mark.parametrize("key", ["source_game_session_id", "source_map_key", "source_dataset_fingerprint"])
def test_session_map_or_dataset_change_is_not_mislabeled_frame_regression(tmp_path, key):
    collector = collector_at(tmp_path)
    bad = capture(3)
    bad.lane[key] = "different"
    bad.truck["sdkFrameTimeUs"] = 1  # A new session may restart the SDK clock.
    collector._ingest(bad)
    assert collector.status()["state"] == "REJECTED_IDENTITY_CHANGED"
    assert collector.status()["reason"] == "DIAGNOSTIC_SESSION_OR_DATASET_CHANGED"
    assert collector.status()["rejection_detail"] == key
    assert collector.status()["sample_count"] == 3


def test_fresh_route_identity_change_remains_distinct_raw_evidence(tmp_path):
    collector = collector_at(tmp_path)
    fresh = capture(3)
    fresh.lane.update(revision=5, navigation_intent_id="new-intent", route_build_id="new-build")
    fresh.applied_target["source_packet"].update(
        revision=5, authority_revision=5, navigation_intent_id="new-intent", route_build_id="new-build")
    collector._ingest(fresh)
    assert collector.state == "COLLECTING"
    assert collector._rows[-1]["revision"] == 5
    assert collector._rows[-2]["revision"] == 4


@pytest.mark.parametrize("count", [3, 130])
def test_finish_control_exports_rejected_samples_with_original_termination(tmp_path, count):
    collector = collector_at(tmp_path, count)
    bad = replace(capture(count), captured_at_s=9.0)
    collector._ingest(bad)
    assert collector.state == "REJECTED_STALE"
    atomic_json_write(collector.control_path, command(2, "finish"))
    collector._poll_command()
    status = collector.status()  # Inspect the original export failure, not a missing-file symptom.
    assert status["state"] == "REJECTED_EXPORTED", status
    assert status["reason"] == "STALE_OR_REGRESSING_DIAGNOSTIC_FRAME"
    target = root(tmp_path) / "cab-01"
    manifest = read_json(target / "manifest.json")
    assert manifest["qualification"] == "INCOMPLETE_REJECTED_COLLECTION"
    assert manifest["collection_complete"] is False
    assert manifest["termination"]["state"] == "REJECTED_STALE"
    assert manifest["termination"]["reason"] == status["reason"]
    assert manifest["termination"]["detail"] == "DIAGNOSTIC_CAPTURE_TIME_REGRESSED"
    assert manifest["rejected_samples"] == 1
    assert manifest["sample_count"] == count
    assert manifest["confirmed"] is False and manifest["runtime_authorized"] is False
    inspected = inspect_collection(target)
    assert inspected["integrity_valid"] is True
    assert inspected["collection_complete"] is False
    assert inspected["qualification"] == "INCOMPLETE_REJECTED_COLLECTION"
    assert inspected["confirmed"] is False and inspected["runtime_authorized"] is False
    before = (target / "manifest.json").read_bytes()
    collector._poll_command()
    assert (target / "manifest.json").read_bytes() == before


@pytest.mark.parametrize("damage", ["missing", "changed"])
def test_incomplete_export_still_verifies_every_chunk(tmp_path, damage):
    collector = collector_at(tmp_path, 130)
    collector._ingest(replace(capture(130), captured_at_s=9.0))
    collector.apply_command(command(2, "finish"))
    assert collector.status()["state"] == "REJECTED_EXPORTED", collector.status()
    target = root(tmp_path) / "cab-01"
    manifest = read_json(target / "manifest.json")
    entry = next(e for e in manifest["files"] if e.get("role") == "chunk")
    path = target / entry["name"]
    if damage == "missing":
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="INTEGRITY"):
        inspect_collection(target)


def test_duplicate_does_not_break_chunk_time_order_or_hide_counts(tmp_path):
    collector = collector_at(tmp_path)
    collector._ingest(replace(capture(2), sequence=4, captured_at_s=10.3))
    for index in range(4, 131):
        collector._ingest(capture(index))
    collector.apply_command(command(2, "finish"))
    assert collector.state == "READY_FOR_OFFLINE_REVIEW", collector.status()
    target = root(tmp_path) / "cab-01"
    manifest = read_json(target / "manifest.json")
    assert manifest["sample_count"] == 130
    assert manifest["skipped_duplicate_samples"] == 1
    assert manifest["rejected_samples"] == 0
    assert inspect_collection(target)["integrity_valid"]


def test_duplicate_cannot_renew_its_original_observation_time(tmp_path):
    collector = collector_at(tmp_path)
    repeated = replace(capture(2), sequence=4, captured_at_s=10.9)
    repeated.profile["observation"]["captured_at"] = 10.9
    collector._ingest(repeated)
    assert collector.state == "REJECTED_STALE"
    assert collector.status()["sample_count"] == 3
    assert collector._last_sdk_observed_at == 10.2


def test_interrupted_rejected_export_preserves_termination_without_public_manifest(tmp_path, monkeypatch):
    from core.navigation import evidence_diagnostics

    collector = collector_at(tmp_path, 130)
    collector._ingest(replace(capture(130), captured_at_s=9.0))
    original = evidence_diagnostics.atomic_json_write

    def interrupted(path, value):
        if path.name == "automatic-observations.part-0001.json":
            raise OSError("interrupted test write")
        return original(path, value)

    monkeypatch.setattr(evidence_diagnostics, "atomic_json_write", interrupted)
    collector.apply_command(command(2, "finish"))
    status = collector.status()
    assert status["state"] == "INSUFFICIENT_EVIDENCE"
    assert status["reason"] == "DIAGNOSTIC_EXPORT_WRITE_FAILED"
    assert status["termination"]["reason"] == "STALE_OR_REGRESSING_DIAGNOSTIC_FRAME"
    assert not (root(tmp_path) / "cab-01").exists()
