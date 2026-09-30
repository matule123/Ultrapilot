"""29 Sep: gear 8 -> 0 at +0.891608 m/s is not proof of Reverse/Neutral."""

from unittest.mock import patch

import pytest

from plugins.autopilot.main import Plugin
from sdk.plugin_sdk import CTL_BRAKE, CTL_STEERING, CTL_THROTTLE, PluginSDK
from tests import test_drive_engagement_safety as engagement


@pytest.fixture
def drive():
    clock = [1000.0]
    with patch("time.monotonic", side_effect=lambda: clock[0]):
        state, truck, engine = engagement.DriveEngagementSafetyTests()._parked_request(
            park_brake=False)
        truck.update(gear=8, speed=0.891608476638794)
        state.set("ets2_transmission_mode", dict(
            state.get("ets2_transmission_mode"), mode=0, generation="profile:0"))
        state.set("system_state", "CRUISE")
        state.set("acc_throttle", 0.4)
        state.set("navigation_source", "gps_lane")
        state.set("navigation_intent_id", "test-intent")
        state.set("nav_recalc_request", "test-intent")
        state.get("lane_trajectory").update(
            navigation_intent_id="test-intent", request_id="test-intent")
        state.get("nav_steering_debug")["navigation_intent_id"] = "test-intent"
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        plugin = Plugin(PluginSDK(state.values, "autopilot"))
        plugin.on_start()
        # Model the active producer before Engine's first control flush.
        state.set("autopilot_control_heartbeat", clock[0])

        def sample(gear, speed=0.891608476638794, dt=0.033333):
            clock[0] += dt
            truck.update(gear=gear, speed=speed,
                         sdkFrameTimeUs=truck["sdkFrameTimeUs"] + int(dt * 1e6))
            state.set("telemetry_timestamp", clock[0])
            state.set("lane_trajectory_heartbeat", clock[0])
            state.set("autopilot_control_heartbeat", clock[0])
            state.get("ets2_transmission_mode")["observed_at"] = clock[0]
            packet = state.get("nav_steering_debug")
            packet.update(computed_at=clock[0], observation_timestamp=clock[0],
                          sdk_frame_us=truck["sdkFrameTimeUs"],
                          calculation_sequence=packet["calculation_sequence"] + 1)
            return dt

        yield state, truck, engine, plugin, sample, clock


def test_plugin_accepts_incident_zero_ratio_and_engine_passes_throttle(drive):
    state, truck, engine, plugin, sample, clock = drive
    plugin.on_tick(sample(8))
    engine._flush_controls()
    plugin.on_tick(sample(0))
    assert state.get("autopilot_active"), state.get("autopilot_disable_reason")
    assert state.get(CTL_THROTTLE) > 0
    engine._flush_controls()
    assert engine.controller.throttle > 0
    assert True not in engine.controller.drive_events
    plugin.on_tick(sample(8))
    engine._flush_controls()
    assert state.get("autopilot_active")
    assert engine.controller.throttle > 0


def test_engine_independently_accepts_zero_before_plugin_consumes_frame(drive):
    state, truck, engine, plugin, sample, clock = drive
    state.set(CTL_THROTTLE, 0.3)
    engine._flush_controls()
    sample(0)
    state.set(CTL_THROTTLE, 0.3)
    engine._flush_controls()
    assert engine.controller.throttle == 0.3
    assert state.get("autopilot_active")


@pytest.mark.parametrize("consumer", ["plugin", "engine"])
def test_continuous_zero_expires_without_renewal(drive, consumer):
    state, truck, engine, plugin, sample, clock = drive
    engine._flush_controls()
    for dt in (0.03, 0.20, 0.20, 0.20):
        step = sample(0, dt=dt)
        state.set(CTL_THROTTLE, 0.3)
        if consumer == "plugin":
            plugin.on_tick(step)
        engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == 0
    assert "zero-ratio transition expired" in state.get("autopilot_disable_reason")
    assert True not in engine.controller.drive_events


@pytest.mark.parametrize("fault", ["reverse", "backwards", "stale", "invalid",
                                    "mode", "identity", "packet", "manual"])
def test_zero_transition_never_survives_loss_of_safety(drive, fault):
    state, truck, engine, plugin, sample, clock = drive
    engine._flush_controls()
    sample(0)
    state.set(CTL_THROTTLE, 0.3)
    engine._flush_controls()
    assert state.get("autopilot_active")
    sample(0)
    if fault == "reverse":
        truck["gear"] = -1
    elif fault == "backwards":
        truck["speed"] = -0.2
    elif fault == "stale":
        state.set("telemetry_timestamp", clock[0] - 0.6)
    elif fault == "invalid":
        state.set("telemetry_valid", False)
    elif fault == "mode":
        state.get("ets2_transmission_mode").update(mode=3, generation="profile:3")
    elif fault == "identity":
        state.get("lane_trajectory")["route_build_id"] = "other-build"
    elif fault == "packet":
        state.get("nav_steering_debug")["observation_timestamp"] -= 0.6
    else:
        state.set("autopilot_command", {"seq": 2, "enabled": False})
        engine._process_autopilot_command()
    state.set(CTL_THROTTLE, 0.3)
    engine._flush_controls()
    assert engine.controller.throttle == 0
    if fault not in ("invalid", "packet"):
        assert not state.get("autopilot_active")
    assert True not in engine.controller.drive_events


def test_real_automatic_still_rejects_zero_ratio(drive):
    state, truck, engine, plugin, sample, clock = drive
    state.get("ets2_transmission_mode").update(mode=3, generation="profile:3")
    engine._pin_confirmed_transmission_mode()
    plugin.on_tick(sample(0))
    engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == 0


def test_no_prior_activation_cannot_authorize_zero(drive):
    state, truck, engine, plugin, sample, clock = drive
    state.set("autopilot_command", {"seq": 2, "enabled": False})
    engine._process_autopilot_command()
    sample(0)
    state.set("autopilot_command", {"seq": 3, "enabled": True})
    engine._process_autopilot_command()
    assert not state.get("autopilot_active")
    assert not state.get("auto_drive_pending", False)
    assert engine.controller.throttle == 0


def test_one_n_launch_without_manual_throttle_then_ratio_transition(drive):
    state, truck, engine, plugin, sample, clock = drive
    state.set("autopilot_command", {"seq": 2, "enabled": False})
    engine._process_autopilot_command()
    sample(0, speed=0.0)
    state.set("autopilot_command", {"seq": 3, "enabled": True})
    engine._process_autopilot_command()
    assert state.get("auto_drive_pending")
    assert not state.get("autopilot_active")
    sample(0, speed=0.0)
    engine._flush_controls()
    assert engine.controller.throttle == 0.12
    assert engine.controller.steering == engine.controller.brake == 0
    assert True not in engine.controller.drive_events
    sample(8, speed=0.2)
    engine._flush_controls()
    assert state.get("autopilot_active")
    assert not state.get("auto_drive_pending")
    plugin.on_tick(sample(0, speed=0.3))
    engine._flush_controls()
    assert state.get("autopilot_active")
    assert engine.controller.throttle > 0


@pytest.mark.parametrize("fault", ["same_frame", "regressed_frame", "missing_gear",
                                    "missing_frame", "nonfinite_speed", "stopped",
                                    "park_brake", "expired_confirmation"])
def test_invalid_observation_cannot_open_zero_window(drive, fault):
    state, truck, engine, plugin, sample, clock = drive
    engine._flush_controls()
    confirmed_frame = truck["sdkFrameTimeUs"]
    sample(0)
    if fault == "same_frame":
        truck["sdkFrameTimeUs"] = confirmed_frame
    elif fault == "regressed_frame":
        truck["sdkFrameTimeUs"] = confirmed_frame - 1
    elif fault == "missing_gear":
        del truck["gear"]
    elif fault == "missing_frame":
        del truck["sdkFrameTimeUs"]
    elif fault == "nonfinite_speed":
        truck["speed"] = float("nan")
    elif fault == "stopped":
        truck["speed"] = 0.0
    elif fault == "park_brake":
        truck["parkBrake"] = True
    else:
        sample(0, dt=0.6)
    state.set(CTL_THROTTLE, 0.3)
    engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == engine.controller.brake == engine.controller.steering == 0


@pytest.mark.parametrize("key", ["navigation_intent_id", "revision", "route_build_id",
                                "source_game_session_id", "source_map_key",
                                "source_dataset_fingerprint"])
def test_each_identity_change_revokes_transition(drive, key):
    state, truck, engine, plugin, sample, clock = drive
    engine._flush_controls()
    sample(0)
    state.get("lane_trajectory")[key] = "changed"
    state.set(CTL_THROTTLE, 0.3)
    engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == 0
    assert state.get("simple_auto_forward_history") is None


def test_repeat_frame_does_not_renew_confirmation_or_zero_deadline(drive):
    state, truck, engine, plugin, sample, clock = drive
    engine._flush_controls()
    sample(0)
    engine._flush_controls()
    deadline = state.get("simple_auto_forward_history")["zero_deadline_at"]
    for _ in range(4):
        clock[0] += 0.1
        # Even a producer re-read timestamp cannot restamp the same SDK frame.
        state.set("telemetry_timestamp", clock[0])
        state.set("autopilot_control_heartbeat", clock[0])
        state.set(CTL_THROTTLE, 0.3)
        engine._flush_controls()
        assert state.get("simple_auto_forward_history")["zero_deadline_at"] == deadline
    clock[0] += 0.2
    state.set("telemetry_timestamp", clock[0])
    state.set("autopilot_control_heartbeat", clock[0])
    engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == 0


def test_stop_brake_protection_is_unchanged_after_ratio_recovery(drive):
    state, truck, engine, plugin, sample, clock = drive
    engine._flush_controls()
    sample(0)
    engine._flush_controls()
    sample(8, speed=0.0)
    state.set(CTL_BRAKE, 0.4)
    state.set(CTL_THROTTLE, 0.0)
    engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine.controller.brake == 0
    assert state.get(CTL_STEERING) == 0


def test_manual_disable_clears_history_and_all_physical_outputs(drive):
    state, truck, engine, plugin, sample, clock = drive
    engine._flush_controls()
    sample(0)
    state.set(CTL_THROTTLE, 0.3)
    engine._flush_controls()
    state.set("autopilot_command", {"seq": 2, "enabled": False})
    engine._process_autopilot_command()
    assert state.get("simple_auto_forward_history") is None
    assert state.get("simple_auto_activation_token") is None
    assert engine.controller.throttle == engine.controller.brake == engine.controller.steering == 0
