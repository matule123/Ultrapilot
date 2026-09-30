"""Real hotkey/producer/PluginSDK/Engine order with a disengageable launch model.

This is an offline counterexample to the output gap, not a model calibrated to
the ETS2 clutch and not evidence that the gap caused the recorded gear reset.
"""

import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from plugins.acc.main import Plugin as ACCPlugin
from sdk.plugin_sdk import PluginSDK


class SimpleAutomaticPlant:
    """Select forward under throttle; release before motion can lose the ratio."""

    def __init__(self, controller, clock):
        self.controller, self.clock = controller, clock
        self.gear, self.speed, self.powered_since = 0, 0.0, None
        self.writes, self.lost_ratios = [], 0
        for channel in ("throttle", "brake", "steering"):
            original = getattr(controller, "set_" + channel)

            def write(value, channel=channel, original=original):
                self.writes.append((clock[0], channel, value))
                original(value)

            setattr(controller, "set_" + channel, write)
        original_release = controller.release_all

        def release():
            self.writes.append((clock[0], "release", 0.0))
            self.powered_since = None
            original_release()

        controller.release_all = release

    def step(self, dt):
        if self.controller.throttle <= 0 or self.controller.brake > 0:
            # The physics/input consumer samples the final held command. Do
            # not force failure from an infinitesimal intermediate zero write.
            if self.gear > 0 and self.speed < 0.05:
                self.lost_ratios += 1
                self.gear = 0
            self.powered_since = None
            return
        if self.powered_since is None:
            self.powered_since = self.clock[0]
        powered = self.clock[0] - self.powered_since
        if powered >= 0.20:
            self.gear = 8
        if powered >= 0.40:
            self.speed += 0.8 * dt


@pytest.mark.parametrize("plugin_delay", [0.0, 0.16])
def test_one_n_real_output_handoff_has_no_zero_gap(flow, plugin_delay):
    state, truck, engine, plugin, publish, n, clock = flow
    plant = SimpleAutomaticPlant(engine.controller, clock)
    acc = ACCPlugin(PluginSDK(state.values, "acc"))
    acc.on_start()
    n()
    confirmed_at = None
    for _ in range(60):
        plant.step(0.02)
        dt = publish(plant.gear, plant.speed, dt=0.02)
        if state.get("autopilot_active"):
            confirmed_at = confirmed_at or clock[0]
            if clock[0] >= confirmed_at + plugin_delay:
                acc.on_tick(dt)
                plugin.on_tick(dt)
        engine._flush_controls()
    assert plant.lost_ratios == 0, plant.writes
    assert plant.speed > 0.2
    assert state.get("autopilot_active"), state.get("autopilot_disable_reason")
    assert state.get("autopilot_engagement_confirmed") is not None
    assert engine.controller.throttle > 0
    assert True not in engine.controller.drive_events


def start_handoff(flow):
    state, truck, engine, plugin, publish, n, clock = flow
    n()
    publish()
    engine._flush_controls()
    publish(8, 0.0, dt=0.228)
    engine._flush_controls()
    assert state.get("autopilot_active")
    return flow


def test_stationary_zero_after_launch_confirmation_is_bounded(flow):
    state, truck, engine, plugin, publish, n, clock = start_handoff(flow)
    publish(0, 0.0, dt=0.107)
    plugin.on_tick(0.02)
    engine._flush_controls()
    assert state.get("autopilot_active"), state.get("autopilot_disable_reason")
    assert engine.controller.throttle > 0
    deadline = state.get("simple_auto_forward_history")["launch_deadline_at"]
    while clock[0] <= deadline + 0.04:
        plugin.on_tick(publish(0, 0.0, dt=0.02))
        engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == 0
    assert "launch" in state.get("autopilot_disable_reason")


@pytest.mark.parametrize("fault", ["cancel", "timeout", "reverse", "park", "stale",
                                       "identity", "backend", "backwards"])
def test_handoff_loss_releases_all_outputs(flow, fault):
    state, truck, engine, plugin, publish, n, clock = start_handoff(flow)
    if fault == "cancel":
        n()
    elif fault == "timeout":
        for _ in range(30):
            publish(8, 0.0, dt=0.02)
            engine._flush_controls()  # No completed Plugin tick.
    elif fault == "reverse":
        publish(-1, 0.0)
    elif fault == "backwards":
        publish(8, -0.2)
    elif fault == "park":
        truck["parkBrake"] = True
        publish(8, 0.0)
    elif fault == "stale":
        clock[0] += 0.6
    elif fault == "identity":
        lane = state.get("lane_trajectory")
        lane["route_build_id"] = "other"
        state.set("lane_trajectory", lane)
    else:
        engine.controller.scs.connected = False
    engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == engine.controller.brake == engine.controller.steering == 0
    assert not state.get("simple_auto_launch")


def test_zero_active_command_is_not_masked_by_probe(flow):
    state, truck, engine, plugin, publish, n, clock = start_handoff(flow)
    state.update_batch({"acc_throttle": 0.0, "acc_brake": 0.0})
    plugin.on_tick(publish(8, 0.0))
    engine._flush_controls()
    assert engine.controller.throttle == 0
    assert not state.get("autopilot_active")
    assert "nulový" in state.get("autopilot_disable_reason")
    for _ in range(3):
        publish(0, 0.0)
        engine._flush_controls()
        assert engine.controller.throttle == 0


def test_pending_ui_describes_simple_auto_launch_not_d_selector(flow):
    state, truck, engine, plugin, publish, n, clock = flow
    n()
    assert "Vyberám D" not in state.get("navigation_status")
    assert "Rozbieham" in state.get("navigation_status")


def test_confirmation_does_not_write_zero_to_physical_backend(flow):
    state, truck, engine, plugin, publish, n, clock = flow
    plant = SimpleAutomaticPlant(engine.controller, clock)
    n()
    publish()
    engine._flush_controls()
    plant.gear = 8
    writes_before = len(plant.writes)
    publish(8, 0.0, dt=0.228)
    engine._flush_controls()
    throttle_writes = [value for _, channel, value in plant.writes[writes_before:]
                       if channel == "throttle"]
    assert throttle_writes == [0.12]
    assert plant.lost_ratios == 0
    assert engine._drive_engagement["phase"] == "handoff"


@pytest.mark.parametrize("fault", ["request", "context", "frame", "timestamp", "target"])
def test_handoff_rejects_invalid_completion_receipt(flow, fault):
    state, truck, engine, plugin, publish, n, clock = start_handoff(flow)
    plugin.on_tick(publish(8, 0.0))
    output = state.get("simple_auto_launch_output")
    assert output
    if fault == "request":
        output["request_id"] = "old-request"
    elif fault == "context":
        output["context"] = ("old",)
    elif fault == "frame":
        output["sdk_frame_us"] -= 1_000_000
    elif fault == "timestamp":
        output["observation_timestamp"] = clock[0] - 0.6
    else:
        output["target_throttle"] = "invalid"
    state.set("simple_auto_launch_output", output)
    engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == 0


def test_partial_plugin_tick_is_not_a_zero_active_command(flow):
    state, truck, engine, plugin, publish, n, clock = start_handoff(flow)
    publish(8, 0.0)
    sdk = PluginSDK(state.values, "autopilot")
    sdk.controller.set_throttle(0.0)  # Incomplete tick, no receipt.
    engine._flush_controls()
    assert engine.controller.throttle == 0.12
    assert state.get("autopilot_active")
    plugin.on_tick(0.02)
    engine._flush_controls()
    assert engine.controller.throttle > 0
    assert engine._drive_engagement is None


def test_late_receipt_after_manual_n_cannot_relaunch(flow):
    state, truck, engine, plugin, publish, n, clock = start_handoff(flow)
    plugin.on_tick(publish(8, 0.0))
    old = state.get("simple_auto_launch_output")
    n()
    state.set("simple_auto_launch_output", old)
    engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == engine.controller.brake == engine.controller.steering == 0
    publish(0, 0.0)
    n()
    publish()
    engine._flush_controls()
    publish(8, 0.0)
    engine._flush_controls()
    state.set("simple_auto_launch_output", old)
    engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == 0


def test_launch_deadline_does_not_renew_on_forward_ratio_at_rest(flow):
    state, truck, engine, plugin, publish, n, clock = start_handoff(flow)
    initial_deadline = state.get("simple_auto_forward_history")["launch_deadline_at"]
    for _ in range(120):
        plugin.on_tick(publish(8, 0.0, dt=0.02))
        engine._flush_controls()
        history = state.get("simple_auto_forward_history")
        if state.get("autopilot_active"):
            assert history["launch_deadline_at"] == initial_deadline
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == 0


def test_park_brake_never_released_or_powered_by_launch(flow):
    state, truck, engine, plugin, publish, n, clock = flow
    truck["parkBrake"] = True
    publish()
    n()
    for _ in range(10):
        publish()
        engine._flush_controls()
        assert engine.controller.throttle == engine.controller.brake == 0
        assert truck["parkBrake"] is True
    n()
    engine._flush_controls()
    assert engine.controller.throttle == 0


@pytest.mark.parametrize("fault", ["packet", "invalid", "repeated_frame", "mode"])
def test_handoff_other_safety_gates_cancel_probe(flow, fault):
    state, truck, engine, plugin, publish, n, clock = start_handoff(flow)
    if fault == "packet":
        packet = state.get("nav_steering_debug")
        packet["observation_timestamp"] = clock[0] - 0.6
        state.set("nav_steering_debug", packet)
    elif fault == "invalid":
        publish(8, 0.0, valid=False)
    elif fault == "repeated_frame":
        clock[0] += 0.16  # Fresh by 500 ms age, but launch stopped advancing.
    else:
        evidence = state.get("ets2_transmission_mode")
        evidence["mode"] = 3
        state.set("ets2_transmission_mode", evidence)
    engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == engine.controller.brake == engine.controller.steering == 0


def test_new_tick_returns_stale_receipt_after_cancel_without_authority(flow):
    state, truck, engine, plugin, publish, n, clock = start_handoff(flow)
    original = plugin._control_tick

    def cancel_after_calculation(dt):
        original(dt)
        n()  # Simulate the driver cancelling while the worker finishes.

    plugin._control_tick = cancel_after_calculation
    plugin.on_tick(publish(8, 0.0))
    engine._flush_controls()
    assert not state.get("autopilot_active")
    assert state.get("simple_auto_launch_output") is None
    assert engine.controller.throttle == engine.controller.brake == engine.controller.steering == 0


def test_handoff_deadline_is_capped_by_original_start_deadline(flow):
    state, truck, engine, plugin, publish, n, clock = flow
    n()
    deadline = engine._drive_engagement["deadline_at"]
    while clock[0] < deadline - 0.10:
        plugin.on_tick(publish(0, 0.0, dt=0.02))
        engine._flush_controls()
    publish(8, 0.0, dt=0.02)
    engine._flush_controls()
    assert engine._drive_engagement["handoff_deadline_at"] == deadline
    while clock[0] <= deadline + 0.02:
        # Keep the last valid readiness current without completing the first
        # active tick; the test isolates deadline renewal, not plugin heartbeat.
        ready = state.get("autopilot_navigation_readiness")
        ready["timestamp"] = clock[0]
        state.set("autopilot_navigation_readiness", ready)
        publish(8, 0.0, dt=0.02)
        engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == 0


@pytest.mark.parametrize("fault", ["packet", "backend", "park", "reverse", "backwards"])
def test_first_active_output_keeps_launch_guards_until_actual_motion(flow, fault):
    state, truck, engine, plugin, publish, n, clock = start_handoff(flow)
    plugin.on_tick(publish(8, 0.0))
    engine._flush_controls()
    assert engine._drive_engagement is None
    assert state.get("simple_auto_forward_history")["launch_deadline_at"]
    if fault == "packet":
        packet = state.get("nav_steering_debug")
        packet["observation_timestamp"] = clock[0] - 0.6
        state.set("nav_steering_debug", packet)
    elif fault == "backend":
        engine.controller.scs.connected = False
    elif fault == "park":
        truck["parkBrake"] = True
        publish(8, 0.0)
    elif fault == "reverse":
        publish(-1, 0.0)
    else:
        publish(8, -0.2)
    engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == engine.controller.brake == engine.controller.steering == 0


@pytest.mark.parametrize("fault", ["cancel", "identity", "slow_ipc"])
def test_handoff_rechecks_authority_after_receipt_ipc(flow, fault):
    state, truck, engine, plugin, publish, n, clock = start_handoff(flow)
    plugin.on_tick(publish(8, 0.0))
    fired = []

    def during_receipt(key):
        if key != "simple_auto_launch_output" or fired:
            return
        fired.append(True)
        state.hook = None
        if fault == "cancel":
            n()
        elif fault == "identity":
            # A wholly coherent NEW build is still not this launch's build.
            lane = state.get("lane_trajectory")
            lane["route_build_id"] = "new-build"
            state.set("lane_trajectory", lane)
            packet = state.get("nav_steering_debug")
            packet["route_build_id"] = "new-build"
            state.set("nav_steering_debug", packet)
        else:
            clock[0] += 0.6

    state.hook = during_receipt
    engine._flush_controls()
    state.hook = None
    assert fired
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == engine.controller.brake == engine.controller.steering == 0


def test_first_plugin_output_continues_from_actual_probe_not_artificial_zero(flow):
    state, truck, engine, plugin, publish, n, clock = start_handoff(flow)
    assert plugin._last_throttle == 0  # Worker has not yet accepted engagement.
    plugin.on_tick(publish(8, 0.0, dt=0.01))
    output = state.get("simple_auto_launch_output")
    assert output["throttle"] >= 0.12
    engine._flush_controls()
    assert engine.controller.throttle == output["throttle"]


def test_backend_loss_during_first_active_write_revokes_launch(flow):
    state, truck, engine, plugin, publish, n, clock = start_handoff(flow)
    plugin.on_tick(publish(8, 0.0))
    original = engine.controller.set_throttle

    def disconnected_write(value):
        original(value)
        if value > 0:
            engine.controller.scs.connected = False

    engine.controller.set_throttle = disconnected_write
    engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == engine.controller.brake == engine.controller.steering == 0
