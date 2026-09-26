"""Passive Engine-to-game boundary observations, with no control authority."""

from copy import deepcopy
from dataclasses import replace
import io
import math
import struct
import time

from core.engine import UltraPilotEngine
from core.navigation.evidence_diagnostics import EvidenceDiagnosticCollector
from core.sdk.scs_controller_writer import SCSControlsWriter, _FIELDS, _SIZE
from tests.test_real_evidence_diagnostics import capture, command, root
from tests.test_stage4d_control_timing import EngineRealtimeBoundaryTests


def test_scs_steering_readback_is_read_only_and_not_dll_acknowledgement():
    offsets, total = {}, 0
    for name, kind in _FIELDS:
        offsets[name] = total
        total += _SIZE[kind]
    payload = bytearray(total)
    struct.pack_into("f", payload, offsets["steering"], 0.15)
    writer = SCSControlsWriter.__new__(SCSControlsWriter)
    writer.connected = True
    writer._buf = io.BytesIO(payload)
    writer._offsets = offsets
    before = writer._buf.getvalue()
    observed = writer.read_steering_diagnostic()
    assert writer._buf.getvalue() == before
    assert observed["status"] == "SHARED_MEMORY_READBACK_ONLY"
    assert math.isclose(observed["value"], 0.15, abs_tol=1e-7)
    assert observed["read_started_s"] <= observed["read_completed_s"]

    writer.connected = False
    assert writer.read_steering_diagnostic()["status"] == "SCS_MAPPING_NOT_CONNECTED"
    assert writer._buf.getvalue() == before


def test_engine_offers_bounded_passive_capture_with_distinct_frames():
    class State(dict):
        def set(self, key, value):
            self[key] = value

    class Controller:
        def read_steering_diagnostic(self):
            now = time.monotonic()
            return {"status": "SHARED_MEMORY_READBACK_ONLY", "value": 0.15,
                    "read_started_s": now, "read_completed_s": now}

        def set_steering(self, _value):
            raise AssertionError("diagnostic may not write steering")

    class Collector:
        def __init__(self):
            self.samples = []

        def should_sample(self, _now):
            return True

        def offer(self, sample):
            self.samples.append(sample)

    engine = UltraPilotEngine.__new__(UltraPilotEngine)
    engine.shared_state = State(telemetry={"truck": {
        "sdkFrameTimeUs": 1020, "userSteer": 0.04,
        "gameSteer": -0.058, "roadWheelAnglesRad": [0.04]}})
    engine.controller = Controller()
    engine._maneuver_diagnostic_collector = Collector()
    engine._maneuver_diagnostic_sequence = 0
    wrote_at = time.monotonic() - 0.01
    engine._offer_maneuver_evidence_diagnostic(
        0.15, wrote_at, application_sdk_frame_us=1000,
        steering_write_returned_at_s=wrote_at)
    sample = engine._maneuver_diagnostic_collector.samples[0]
    assert sample.truck["sdkFrameTimeUs"] == 1020
    assert sample.truck["userSteer"] == 0.04
    assert sample.application_sdk_frame_us == 1000
    assert sample.steering_write_returned_at_s == wrote_at
    assert sample.steering_boundary["value"] == 0.15


def test_parked_manual_branch_never_writes_drive_throttle_or_steering():
    class State(dict):
        def set(self, key, value):
            self[key] = value

    class Controller(EngineRealtimeBoundaryTests.FakeController):
        def set_steering(self, _value):
            raise AssertionError("manual diagnostic wrote steering")

        def set_throttle(self, _value):
            raise AssertionError("manual diagnostic wrote throttle")

        def set_brake(self, _value):
            raise AssertionError("manual diagnostic wrote brake")

        def select_drive(self, _pressed=True):
            raise AssertionError("manual diagnostic selected Drive")

        def release_all(self):
            raise AssertionError("no prior autopilot authority to release")

        def read_steering_diagnostic(self):
            now = time.monotonic()
            return {"status": "SHARED_MEMORY_READBACK_ONLY", "value": 0.0,
                    "read_started_s": now, "read_completed_s": now}

    class Collector:
        def should_sample(self, _now):
            return True

        def __init__(self):
            self.samples = []

        def offer(self, sample):
            self.samples.append(sample)

    state = State(autopilot_active=False, telemetry_valid=True,
                  telemetry={"truck": {"sdkFrameTimeUs": 123,
                                        "speed": 0.0, "userSteer": 0.0,
                                        "gameSteer": 0.0}})
    engine = EngineRealtimeBoundaryTests.bare_engine(state)
    engine.controller = Controller()
    engine._maneuver_diagnostic_collector = Collector()
    engine._maneuver_diagnostic_sequence = 0
    engine._flush_controls_unlocked()
    assert len(engine._maneuver_diagnostic_collector.samples) == 1
    assert engine._maneuver_diagnostic_collector.samples[0].backend_sent is False


def test_exported_channels_distinguish_normal_and_attenuated_response(tmp_path):
    ratios = []
    # Exact command/observation pairs from the lag-aware sn2 and incident
    # replays. The readback is deliberately simulated: neither old replay
    # measured Local\SCSControls, so it must not be presented as a real ACK.
    replay_pairs = (
        (-0.18528245297157492, -0.18528245389461517,
         457148380, 457381704, 0.11243970000032277),
        (0.07973232650626008, 0.030694816261529922,
         148494060, 148627388, 0.07775059999949008),
    )
    for index, (command_value, observed_right, command_frame,
                observation_frame, age_s) in enumerate(replay_pairs):
        collector = EvidenceDiagnosticCollector(root(tmp_path / str(index)),
                                                capacity=30)
        collector.apply_command(command(1, collection_id="steering-boundary"))
        collector._publish = lambda: None
        sample = capture(index)
        profile = deepcopy(sample.profile)
        profile["observation"]["sdk_frame_us"] = observation_frame
        sample = replace(
            sample, engine_steer=command_value, profile=profile,
            truck={**sample.truck, "userSteer": 0.0,
                           "gameSteer": -observed_right,
                           "roadWheelAnglesRad": [observed_right * 0.7],
                           "sdkFrameTimeUs": observation_frame},
            applied_target={**sample.applied_target, "output": command_value,
                            "raw": command_value,
                            "source_packet": {
                                **sample.applied_target["source_packet"],
                                "sdk_frame_us": command_frame}},
            steering_boundary={"status": "SHARED_MEMORY_READBACK_ONLY",
                               "value": command_value,
                               "read_started_s": sample.captured_at_s - age_s,
                               "read_completed_s": sample.captured_at_s - age_s + 0.001},
            application_sdk_frame_us=command_frame,
            steering_write_returned_at_s=sample.captured_at_s - age_s,
        )
        collector._ingest(sample)
        row = collector._rows[-1]
        boundary = row["steering_boundary"]
        assert row["sdk_frame_us"] > boundary["application_sdk_frame_us"]
        assert 0.067 <= row["captured_at_s"] - boundary["steering_write_returned_at_s"] <= 0.18
        assert math.isclose(row["engine_steer"], boundary["value"], abs_tol=1e-7)
        assert row["user_steer"] == 0.0
        assert boundary["dll_consumed_value"] is None
        assert boundary["physical_axis_value"] is None
        assert boundary["dll_consumption_observed"] is False
        ratios.append(-row["game_steer"] / boundary["value"])
    assert math.isclose(ratios[0], 1.0, abs_tol=1e-5)
    assert math.isclose(ratios[1], 0.38497329259694885, abs_tol=1e-12)
    assert ratios[0] - ratios[1] > 0.6
