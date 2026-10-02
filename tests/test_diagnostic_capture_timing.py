"""Paused SDK transport is waiting, not new geometry or a control input."""
from copy import deepcopy

import pytest

from core.navigation.evidence_diagnostics import EvidenceDiagnosticCollector
from tests.test_real_evidence_diagnostics import command, parked_trailer_capture, root
from tests.test_stage4d_control_timing import State


def setup_engine(tmp_path, monkeypatch):
    from tests.test_stage4d_control_timing import EngineRealtimeBoundaryTests
    now = [1340.099922]
    monkeypatch.setattr("core.engine.time.monotonic", lambda: now[0])
    state = State({"autopilot_active": False, "telemetry_valid": True})
    engine = EngineRealtimeBoundaryTests.bare_engine(state)
    engine.controller = EngineRealtimeBoundaryTests.FakeController()
    collector = EvidenceDiagnosticCollector(root(tmp_path), capacity=30, clock=lambda: now[0])
    collector.apply_command(command(1))
    engine._maneuver_diagnostic_collector = collector
    engine._maneuver_diagnostic_sequence = 0
    return engine, collector, state, now


def offer_and_ingest(engine, collector):
    engine._flush_controls_unlocked()  # Manual branch, including its current sample clock.
    value = collector._queue.get_nowait()
    collector._ingest(value)
    return value


def publish(engine, state, now, *, frame, paused, control_valid=True):
    seed = parked_trailer_capture(0)
    seed.truck["sdkFrameTimeUs"] = frame
    seed.profile["observation"].update(sdk_frame_us=frame, captured_at=now[0], paused=paused)
    data = {"truck": deepcopy(seed.truck), "vehicle_profile": deepcopy(seed.profile)}
    engine._latest_telemetry_data = data
    engine._latest_telemetry_timestamp = now[0]
    engine._latest_telemetry_success = control_valid
    engine._store_diagnostic_sdk_read(data, now[0])
    state.update_batch({"telemetry": {"truck": seed.truck},
        "telemetry_valid": control_valid, "vehicle_profile_snapshot": seed.profile,
        "lane_trajectory": seed.lane})
    return seed


def test_incident_paused_frame_waits_through_control_staleness_then_new_frame_collects(tmp_path, monkeypatch):
    engine, collector, state, now = setup_engine(tmp_path, monkeypatch)
    seed = publish(engine, state, now, frame=54_564_484, paused=True)
    seed.profile["observation"]["captured_at"] = 1339.8679709
    state.set("vehicle_profile_snapshot", seed.profile)
    offer_and_ingest(engine, collector)
    assert collector.status()["sample_count"] == 0  # Paused pose is not fresh geometry.
    assert collector.state == "ARMED"
    for timestamp in (1340.2107078, 1341.0, 1342.0):
        now[0] = timestamp
        # The existing control producer rejects a frozen frame after 500 ms.
        # Its private SDK read still explicitly reports a coherent paused game.
        publish(engine, state, now, frame=54_564_484, paused=True, control_valid=False)
        state.update_batch({"telemetry_valid": False,
                            "telemetry": {"truck": {"sdkFrameTimeUs": 0}},
                            "vehicle_profile_snapshot": None})
        offer_and_ingest(engine, collector)
        assert collector.state == "ARMED"
        assert collector.status()["reason"] == "WAITING_FOR_UNPAUSED_SDK_FRAME"
        assert collector.status()["sample_count"] == 0
    now[0] = 1343.0
    publish(engine, state, now, frame=54_581_151, paused=False)
    offer_and_ingest(engine, collector)
    assert collector.state == "COLLECTING"
    assert collector.status()["sample_count"] == 1
    assert collector.status()["skipped_paused_samples"] == 4
    assert engine.controller.steering_writes == []


def test_capture_time_is_after_shared_reads_without_retimestamping_sdk(tmp_path, monkeypatch):
    engine, collector, state, now = setup_engine(tmp_path, monkeypatch)
    seed = publish(engine, state, now, frame=54_564_484, paused=False)
    started = now[0]
    original_get = state.get

    def concurrent_get(key, *args):
        if key == "vehicle_profile_snapshot":
            now[0] = started + 0.005
            seed.profile["observation"]["captured_at"] = now[0]
            return seed.profile
        return original_get(key, *args)

    state.get = concurrent_get
    value = offer_and_ingest(engine, collector)
    assert collector.state == "COLLECTING", collector.status()
    assert value.capture_started_at_s == started
    assert value.captured_at_s == started + 0.005
    assert value.profile["observation"]["captured_at"] == started + 0.005


@pytest.mark.parametrize("offset,detail", [
    (-0.4, "DIAGNOSTIC_SDK_OBSERVATION_EXPIRED"),
    (0.1, "DIAGNOSTIC_SDK_OBSERVATION_IN_FUTURE"),
])
def test_real_expiration_and_future_timestamp_still_reject(tmp_path, offset, detail):
    collector = EvidenceDiagnosticCollector(root(tmp_path), capacity=30)
    collector.apply_command(command(1))
    seed = parked_trailer_capture(0)
    seed.profile["observation"]["captured_at"] = seed.captured_at_s + offset
    collector._ingest(seed)
    assert collector.state == "REJECTED_STALE"
    termination = collector.status()["termination"]
    assert termination["detail"] == detail
    assert termination["observation_captured_at_s"] == seed.captured_at_s + offset
    assert termination["observation_age_s"] == pytest.approx(-offset)


def test_old_paused_read_does_not_hide_telemetry_loss(tmp_path, monkeypatch):
    engine, collector, state, now = setup_engine(tmp_path, monkeypatch)
    publish(engine, state, now, frame=54_564_484, paused=True)
    now[0] += 1.0  # No new transport read, even though its old paused flag remains.
    state.set("telemetry_valid", False)
    offer_and_ingest(engine, collector)
    assert collector.state == "REJECTED_STALE"
    assert collector.status()["rejection_detail"] == "DIAGNOSTIC_TELEMETRY_INVALID"


def test_actual_worker_updates_paused_transport_without_renewing_control_frame(tmp_path, monkeypatch):
    engine, collector, state, now = setup_engine(tmp_path, monkeypatch)
    seed = parked_trailer_capture(0)
    seed.truck["sdkFrameTimeUs"] = 54_564_484
    timestamps = iter((1340.1, 1340.4, 1340.8, 1341.0))
    accepted_control_times = []

    class Telemetry:
        data = {}

        def update(self):
            now[0] = next(timestamps)
            if now[0] == 1341.0:
                return False  # Genuine read loss must clear the paused evidence.
            profile = deepcopy(seed.profile)
            profile["observation"].update(
                sdk_frame_us=54_564_484, captured_at=now[0], paused=True)
            self.data = {"raw": {"sdkActive": True}, "truck": seed.truck,
                         "vehicle_profile": profile, "trailer": {}}
            return True

    def next_tick(*args):
        accepted_control_times.append(engine._latest_telemetry_timestamp)
        offer_and_ingest(engine, collector)
        if now[0] < 1341.0:
            assert collector.status()["reason"] == "WAITING_FOR_UNPAUSED_SDK_FRAME"
            assert collector.status()["sample_count"] == 0
            assert engine._latest_diagnostic_sdk_read["read_at_s"] == now[0]
        return now[0], now[0] == 1341.0

    engine.telemetry = Telemetry()
    monkeypatch.setattr("core.engine.wait_for_next_tick", next_tick)
    engine._telemetry_loop()
    # At 300 ms, the accepted control observation is still the original one.
    assert accepted_control_times[:2] == [1340.1, 1340.1]
    assert state.get("telemetry_valid") is False
    assert collector.status()["skipped_paused_samples"] == 3
    assert collector.status()["rejection_detail"] == "DIAGNOSTIC_TELEMETRY_INVALID"
    assert engine.controller.steering_writes == []
