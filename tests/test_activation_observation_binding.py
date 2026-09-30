"""Exercise the real producer, hotkey, PluginSDK and physical Engine boundary."""

import copy
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.engine import UltraPilotEngine
from plugins.autopilot.main import Plugin
from sdk.plugin_sdk import CTL_THROTTLE, PluginSDK
from tests import test_drive_engagement_safety as engagement


class IPCState:
    """Manager.dict semantics: consumers receive copies, never live aliases."""

    def __init__(self, values):
        self.values = copy.deepcopy(values)
        self.hook = None

    def get(self, key, default=None):
        if self.hook:
            self.hook(key)
        return copy.deepcopy(self.values.get(key, default))

    def set(self, key, value):
        self.values[key] = copy.deepcopy(value)

    def update_batch(self, values):
        self.values.update(copy.deepcopy(values))


@pytest.fixture
def flow():
    clock = [1000.0]
    with patch("time.monotonic", side_effect=lambda: clock[0]):
        old, truck, engine = engagement.DriveEngagementSafetyTests()._parked_request(
            park_brake=False)
        state = IPCState(old.values)
        engine.shared_state = state
        engine._has_win32 = True
        engine._hotkey_vk = ord("N")
        engine._hotkey_was_down = False
        engine._game_window_active = lambda: True
        state.update_batch({"telemetry_control_schema": 1,
                            "navigation_source": "gps_lane",
                            "navigation_intent_id": "intent",
                            "nav_recalc_request": "intent",
                            "system_state": "CRUISE", "acc_throttle": 0.4})
        lane = state.get("lane_trajectory")
        lane.update(navigation_intent_id="intent", request_id="intent")
        state.set("lane_trajectory", lane)
        packet = state.get("nav_steering_debug")
        packet["navigation_intent_id"] = "intent"
        state.set("nav_steering_debug", packet)
        state.set("ets2_transmission_mode", dict(
            state.get("ets2_transmission_mode"), mode=0, generation="profile:0"))
        truck.update(pose_valid=True, x=0.0, y=10.0, z=0.0, rotation=0.0)

        def publish(gear=0, speed=0.0, dt=0.033333, valid=True):
            clock[0] += dt
            truck.update(gear=gear, speed=speed, pose_valid=valid,
                         sdkFrameTimeUs=truck["sdkFrameTimeUs"] + int(dt * 1e6))
            state.update_batch(engine._vehicle_telemetry_payload(
                {"truck": truck, "raw": {"sdkActive": True}}, clock[0]))
            state.set("lane_trajectory_heartbeat", clock[0])
            state.set("autopilot_control_heartbeat", clock[0])
            packet = state.get("nav_steering_debug")
            packet.update(computed_at=clock[0], observation_timestamp=clock[0],
                          sdk_frame_us=truck["sdkFrameTimeUs"],
                          calculation_sequence=packet["calculation_sequence"] + 1)
            state.set("nav_steering_debug", packet)
            evidence = state.get("ets2_transmission_mode")
            evidence["observed_at"] = clock[0]
            state.set("ets2_transmission_mode", evidence)
            return dt

        def n():
            engine._hotkey_was_down = False
            with patch.dict(sys.modules, {
                    "win32api": SimpleNamespace(GetAsyncKeyState=lambda _: 0x8000)}):
                engine._check_hotkey()

        publish()
        plugin = Plugin(PluginSDK(state.values, "autopilot"))
        plugin.on_start()
        yield state, truck, engine, plugin, publish, n, clock


@pytest.mark.parametrize("mode", [0, 3])
def test_one_n_complete_start_without_driver_throttle(flow, mode):
    state, truck, engine, plugin, publish, n, clock = flow
    evidence = state.get("ets2_transmission_mode")
    evidence.update(mode=mode, generation=f"profile:{mode}")
    state.set("ets2_transmission_mode", evidence)
    n()
    assert state.get("auto_drive_pending")
    publish()
    engine._flush_controls()
    if mode == 0:
        assert engine.controller.throttle == 0.12
        assert True not in engine.controller.drive_events
    else:
        assert engine.controller.throttle == 0
        assert engine.controller.drive_events.count(True) == 1
    assert engine.controller.brake == engine.controller.steering == 0
    publish(8, 0.2)
    engine._flush_controls()
    assert state.get("autopilot_active")
    for _ in range(4):
        plugin.on_tick(publish(8, 0.4))
        engine._flush_controls()
        assert state.get("autopilot_active"), state.get("autopilot_disable_reason")
        assert engine.controller.throttle > 0
    if mode == 0:
        plugin.on_tick(publish(0, 0.891608476638794))
        engine._flush_controls()
        assert state.get("autopilot_active")
        assert engine.controller.throttle > 0
        plugin.on_tick(publish(8, 0.9))
        engine._flush_controls()
        assert state.get("autopilot_active")
    n()
    engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == engine.controller.brake == engine.controller.steering == 0


def test_slow_ipc_new_observation_does_not_have_negative_age(flow):
    state, truck, engine, plugin, publish, n, clock = flow
    publish(8, 3.0816168785095215)
    n()
    captured = state.get("telemetry")["truck"]["_control_observation"]
    fired = []

    def during_ipc(key):
        if key == "simple_auto_activation_token" and not fired:
            fired.append(True)
            state.hook = None
            publish(8, 3.0816168785095215, dt=0.02)

    state.hook = during_ipc
    state.set(CTL_THROTTLE, 0.3)
    engine._flush_controls()
    assert fired
    assert state.get("autopilot_active"), state.get("autopilot_disable_reason")
    assert engine.controller.throttle == 0.3
    history = state.get("simple_auto_forward_history")
    assert history["last_frame"] == captured["sdk_frame_us"]
    assert history["last_observed_at"] == captured["observed_at"]
    assert clock[0] - history["last_observed_at"] == pytest.approx(0.02)


def test_producer_binds_gear_validity_and_original_timestamp(flow):
    state, truck, engine, plugin, publish, n, clock = flow
    publish(8, 3.0816168785095215)
    row = state.get("telemetry")["truck"]
    metadata = row.get("_control_observation")
    assert metadata is not None
    assert metadata["sdk_frame_us"] == row["sdkFrameTimeUs"]
    assert metadata["observed_at"] == clock[0]
    assert metadata["valid"] is True
    assert "_control_observation" not in truck  # Producer input was not mutated.


@pytest.mark.parametrize("fault", ["invalid", "stale", "identity", "reverse", "backwards"])
def test_production_observation_failures_cancel_outputs(flow, fault):
    state, truck, engine, plugin, publish, n, clock = flow
    publish(8, 3.0)
    n()
    engine._flush_controls()
    if fault == "invalid":
        publish(8, 3.0, valid=False)
    elif fault == "stale":
        clock[0] += 0.6
        # Keep navigation fresh to isolate the original vehicle observation.
        packet = state.get("nav_steering_debug")
        packet.update(observation_timestamp=clock[0], computed_at=clock[0])
        state.set("nav_steering_debug", packet)
        state.set("lane_trajectory_heartbeat", clock[0])
        state.set("autopilot_control_heartbeat", clock[0])
    elif fault == "identity":
        lane = state.get("lane_trajectory")
        lane["route_build_id"] = "other"
        state.set("lane_trajectory", lane)
    elif fault == "reverse":
        publish(-1, 0.0)
    else:
        publish(8, -0.2)
    state.set(CTL_THROTTLE, 0.4)
    engine._flush_controls()
    assert engine.controller.throttle == 0
    n() if state.get("autopilot_active") else None
    engine._flush_controls()
    assert engine.controller.throttle == engine.controller.brake == engine.controller.steering == 0


@pytest.mark.parametrize("fault, expected", [
    ("metadata", "bound metadata is missing"),
    ("binding", "SDK frame binding does not match"),
    ("valid", "telemetry_valid is false"),
    ("frame", "SDK frame is not positive"),
    ("future", "timestamp is in the future"),
    ("stale", "vehicle observation is stale"),
])
def test_each_rejection_identifies_its_exact_predicate(flow, fault, expected):
    state, truck, engine, plugin, publish, n, clock = flow
    publish(8, 3.0)
    n()
    row = state.get("telemetry")
    metadata = row["truck"]["_control_observation"]
    if fault == "metadata":
        del row["truck"]["_control_observation"]
    elif fault == "binding":
        metadata["sdk_frame_us"] += 1
    elif fault == "valid":
        metadata["valid"] = False
    elif fault == "frame":
        metadata["sdk_frame_us"] = row["truck"]["sdkFrameTimeUs"] = 0
    elif fault == "future":
        metadata["observed_at"] = clock[0] + 0.02
    else:
        metadata["observed_at"] = clock[0] - 0.6
    state.set("telemetry", row)
    state.set(CTL_THROTTLE, 0.4)
    engine._flush_controls()
    reason = (state.get("autopilot_disable_reason", "") + " "
              + state.get("automatic_safety_stop_reason", ""))
    assert expected in reason
    assert engine.controller.throttle == 0


def test_pending_start_does_not_mix_later_drive_with_captured_reverse(flow):
    state, truck, engine, plugin, publish, n, clock = flow
    n()
    publish(-1, 0.0)
    fired = []

    def publish_during_validation(key):
        if key == "autopilot_navigation_readiness" and not fired:
            fired.append(True)
            state.hook = None
            publish(8, 0.0, dt=0.02)

    state.hook = publish_during_validation
    engine._flush_controls()
    assert fired
    assert not state.get("autopilot_active")
    assert not state.get("auto_drive_pending")
    assert engine.controller.throttle == engine.controller.brake == engine.controller.steering == 0


def test_plugin_reads_history_before_vehicle_when_engine_progresses(flow):
    state, truck, engine, plugin, publish, n, clock = flow
    publish(8, 3.0)
    n()
    engine._flush_controls()
    original = plugin.sdk.shared_state.get
    progressed = []

    def rpc(key, default=None):
        value = original(key, default)
        if key == "simple_auto_forward_history" and not progressed:
            progressed.append(True)
            publish(8, 3.1, dt=0.02)
            engine._flush_controls()
        return value

    plugin.sdk.shared_state.get = rpc
    plugin.on_tick(0.02)
    engine._flush_controls()
    assert progressed
    assert state.get("autopilot_active"), state.get("autopilot_disable_reason")


def test_expired_observation_during_ipc_is_not_restamped(flow):
    state, truck, engine, plugin, publish, n, clock = flow
    publish(8, 3.0)
    n()
    captured_at = state.get("telemetry")["truck"]["_control_observation"]["observed_at"]
    fired = []

    def delay(key):
        if key == "simple_auto_activation_token" and not fired:
            fired.append(True)
            clock[0] += 0.6

    state.hook = delay
    engine._flush_controls()
    state.hook = None
    assert fired
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == 0
    assert "vehicle observation is stale" in state.get("autopilot_disable_reason")
    assert state.get("telemetry")["truck"]["_control_observation"]["observed_at"] == captured_at


@pytest.mark.parametrize("from_neutral", [False, True])
def test_expiry_during_history_initialization_never_grants_authority(flow, from_neutral):
    state, truck, engine, plugin, publish, n, clock = flow
    if from_neutral:
        n()
    publish(8, 0.2)
    active_writes = []
    original = state.update_batch

    def record(values):
        if "autopilot_active" in values:
            active_writes.append(values["autopilot_active"])
        original(values)

    state.update_batch = record
    fired = []

    def delay(key):
        if key == "simple_auto_activation_token" and not fired:
            fired.append(True)
            clock[0] += 0.6

    state.hook = delay
    engine._flush_controls() if from_neutral else n()
    state.hook = None
    assert fired
    assert not state.get("autopilot_active")
    assert True not in active_writes
    assert not state.get("auto_drive_pending", False)
    assert engine.controller.throttle == engine.controller.brake == engine.controller.steering == 0
