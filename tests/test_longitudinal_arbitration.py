"""Phase 7.1: producer and physical-boundary conflict counterexamples."""
import time

import pytest

from core.engine import UltraPilotEngine
from plugins.acc.main import Plugin as ACC
from sdk.plugin_sdk import PluginSDK
from tests.test_control_safety_regressions import (
    Controller, State, autopilot, ready_navigation_state,
)
from tests.test_activation_observation_binding import flow  # noqa: F401
from core.longitudinal import (
    choose, context, packet, publish, rejection, engine_decision, finalize, read,
)
from plugins.drivepolicy.main import Plugin as Policy
from plugins.ecodrive.main import Plugin as Eco
from plugins.map.main import Plugin as Map
from core.longitudinal import curve_input
from core.ipc.shared_state import SharedState


def test_acc_deceleration_reaches_autopilot_brake():
    state = ready_navigation_state(system_state="CRUISE", nav_active=True,
        nav_steering=0., acc_throttle=0., acc_brake=.3)
    plugin = autopilot({"speed": 12., "gear": 5}, state)
    plugin.on_tick(.05)
    assert plugin.sdk.controller.brake > 0
    assert plugin.sdk.controller.throttle == 0


@pytest.mark.parametrize("eco", [False, True])
def test_brake_cancels_existing_throttle_without_ramp_or_eco_revival(eco):
    state = ready_navigation_state(eco_active=eco, eco_smoothing=.15)
    plugin = autopilot({"speed": 12., "gear": 5}, state)
    plugin._last_throttle = .5
    plugin._set_brake(.3, .05)
    plugin._apply_throttle(0., .05)
    assert plugin.sdk.controller.brake > 0
    assert plugin.sdk.controller.throttle == 0


def test_acc_danger_never_raises_existing_speed_constraint():
    values = {"telemetry": {"truck": {"speed": 5., "speedLimit": 10.}},
              "acc_target_speed": 80., "danger_level": .2,
              "road_speed_cap": 30., "planned_speed_ms": 6.}
    plugin = ACC(PluginSDK(values, "acc"))
    plugin.on_start()
    plugin.on_tick(.05)
    assert plugin.tags.acc_speed <= 6. * 3.6


def test_engine_never_physically_applies_positive_throttle_and_brake():
    state = State({"autopilot_active": True,
        "autopilot_control_heartbeat": time.monotonic(),
        "telemetry": {"truck": {"speed": 12., "gear": 5}},
        "ctl_throttle": .7, "ctl_brake": .4, "ctl_steering": 0.})
    engine = UltraPilotEngine.__new__(UltraPilotEngine)
    engine.shared_state, engine.controller = state, Controller()
    engine._was_active = True
    engine._drive_selector_pressed = False
    engine._flush_controls()
    assert engine.controller.throttle == 0
    assert engine.controller.brake == .4


def test_stopped_toll_payment_cannot_keep_cruise_throttle():
    state = ready_navigation_state(system_state="PAY_TOLL", nav_active=True,
                                   nav_steering=0.)
    plugin = autopilot({"speed": 0., "gear": 5}, state)
    plugin._was_active = True
    plugin._last_throttle = plugin.sdk.controller.throttle = .5
    plugin.on_tick(.05)
    assert plugin.sdk.controller.throttle == 0
    assert plugin._last_throttle == 0


def strict_flow(flow, *, mode=0):
    state, truck, engine, plugin, update, n, clock = flow
    state.set("longitudinal_control_schema", 1)
    evidence = state.get("ets2_transmission_mode")
    evidence.update(mode=mode, generation=f"profile:{mode}")
    state.set("ets2_transmission_mode", evidence)
    acc = ACC(PluginSDK(state.values, "acc"))
    acc.on_start()
    return (*flow, acc)


@pytest.mark.parametrize("mode", [0, 3])
def test_whole_production_start_and_cancel(flow, mode):
    state, truck, engine, plugin, update, n, clock, acc = strict_flow(flow, mode=mode)
    writes = []
    for key in ("throttle", "brake"):
        original = getattr(engine.controller, "set_" + key)
        def write(v, key=key, original=original):
            original(v)
            writes.append((key, v, engine.controller.throttle, engine.controller.brake))
        setattr(engine.controller, "set_" + key, write)
    n()
    update()
    acc.on_tick(.033)
    engine._flush_controls()
    assert engine.controller.throttle == (.12 if mode == 0 else 0.)
    update(8, .2)
    acc.on_tick(.033)
    engine._flush_controls()
    plugin.on_tick(update(8, .4))
    acc.on_tick(.033)
    engine._flush_controls()
    assert state.get("autopilot_active"), state.get("autopilot_disable_reason")
    assert engine.controller.throttle > 0
    assert all(t == 0 or b == 0 for _, _, t, b in writes)
    assert state.get("longitudinal_applied")["source"] == "acc"
    if mode == 0:
        acc.on_tick(update(0, .8))
        plugin.on_tick(.033)
        engine._flush_controls()
        assert engine.controller.throttle > 0
    n()
    engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == engine.controller.brake == 0
    assert state.get("longitudinal_command") is None


def test_changed_order_cannot_restore_drive_over_latest_emergency(flow):
    state, truck, engine, plugin, update, n, clock, acc = strict_flow(flow)
    update(8, 12.)
    n()
    acc.on_tick(.033)
    plugin.on_tick(.033)
    original = state.get("longitudinal_command")
    assert original["throttle"] > 0
    # Emergency arrives AFTER the completed plugin tick; no plugin tick needed.
    publish(state, state.get("telemetry")["truck"], "traffic",
            traffic_brake=.9, light_brake=0., light=None, lead_distance=2.)
    engine._flush_controls()
    assert engine.controller.brake == 1.
    assert engine.controller.throttle == 0.
    # Even a scalar writer cannot overwrite the paired result.
    state.set("ctl_throttle", 1.)
    engine._flush_controls()
    assert engine.controller.throttle == 0.
    assert state.get("longitudinal_applied")["source"] == "traffic_emergency"


@pytest.mark.parametrize("fault", ["expired", "missing", "nan", "future", "identity", "frame", "disabled"])
def test_final_physical_boundary_rejects_bad_complete_output(flow, fault):
    state, truck, engine, plugin, update, n, clock, acc = strict_flow(flow)
    update(8, 12.)
    n()
    acc.on_tick(.033)
    plugin.on_tick(.033)
    p = state.get("longitudinal_command")
    if fault == "expired":
        p["observation_timestamp"] -= .501
    elif fault == "missing":
        p = None
    elif fault == "nan":
        p["throttle"] = float("nan")
    elif fault == "future":
        p["observation_timestamp"] += 1
    elif fault == "identity":
        p["context"] = ["old-activation", *p["context"][1:]]
    elif fault == "frame":
        p["sdk_frame_us"] += 1
    elif fault == "disabled":
        state.set("autopilot_active", False)
    state.set("longitudinal_command", p)
    engine._flush_controls()
    assert engine.controller.throttle == 0
    assert not (engine.controller.throttle > 0 and engine.controller.brake > 0)


def test_brake_then_release_and_disabled_ecodrive_do_not_restore_old_drive(flow):
    state, truck, engine, plugin, update, n, clock, acc = strict_flow(flow)
    update(8, 12.)
    n()
    eco = Eco(PluginSDK(state.values, "ecodrive"))
    eco.on_start()
    eco.on_tick(.033)
    publish(state, state.get("telemetry")["truck"], "acc", throttle=.8,
            brake=.4, emergency=False)
    plugin._last_throttle = .8
    plugin.on_tick(.05)
    engine._flush_controls()
    assert engine.controller.throttle == 0 and engine.controller.brake > 0
    # An explicit zero is cancellation, not absence. The brake ramp still owns
    # deceleration while releasing; Eco cannot resurrect the pre-brake value.
    for _ in range(4):
        update(8, 12.)
        publish(state, state.get("telemetry")["truck"], "acc", throttle=0., brake=0., emergency=False)
        plugin.on_tick(.05)
        engine._flush_controls()
        assert engine.controller.throttle == 0
    n()
    eco.on_tick(.033)
    plugin.on_tick(.05)
    engine._flush_controls()
    assert engine.controller.throttle == engine.controller.brake == 0


def test_minimum_constraints_not_tick_order_or_acc_target_override(flow):
    state, truck, engine, plugin, update, n, clock, acc = strict_flow(flow)
    update(8, 12.)
    n()
    truck_value = state.get("telemetry")["truck"]
    publish(state, truck_value, "road", speed_cap_kmh=30.)
    publish(state, truck_value, "policy", brake=.2, planned_speed_ms=6.)
    publish(state, truck_value, "traffic", traffic_brake=.2, light_brake=.4,
            light={"color": "red", "distance": 10.}, lead_distance=15.)
    acc.on_tick(.05)
    assert acc.tags.acc_speed <= 21.6
    plugin.on_tick(.05)
    engine._flush_controls()
    assert engine.controller.throttle == 0 and engine.controller.brake > 0
    # A newer lower cap suppresses old positive drive at the final boundary.
    publish(state, truck_value, "traffic", traffic_brake=0., light_brake=0., light=None, lead_distance=None)
    publish(state, truck_value, "acc", throttle=.8, brake=0., emergency=False)
    publish(state, truck_value, "policy", brake=0., planned_speed_ms=25.)
    finalize(state, truck_value, .8, 0., {"source": "acc"}, context(state))
    publish(state, truck_value, "road", speed_cap_kmh=20.)
    engine._flush_controls()
    assert engine.controller.throttle == 0
    assert state.get("longitudinal_applied")["source"] == "speed_constraint"


def test_required_acc_expiry_is_not_restamped_by_new_autopilot_tick(flow):
    state, truck, engine, plugin, update, n, clock, acc = strict_flow(flow)
    update(8, 12.)
    n()
    acc.on_tick(.05)
    original = state.get("longitudinal_acc")["observation_timestamp"]
    update(8, 12., dt=.49)
    plugin.on_tick(.05)
    assert state.get("longitudinal_command")["expires_at"] == original + .5
    update(8, 12., dt=.03)
    engine._flush_controls()
    assert engine.controller.throttle == 0


def test_deterministic_brake_floors_and_emergency_precedence():
    from itertools import permutations
    requests = [("traffic", "traffic", .4), ("curve", "curve", .6), ("acc", "acc", .3)]
    results = [choose(.8, list(p)) for p in permutations(requests)]
    assert all(r == results[0] for r in results)
    assert results[0]["source"] == "curve" and results[0]["brake"] == .6
    assert choose(.8, [*requests, ("panic", "emergency", 1.)])["brake"] == 1.
    mixed = choose(.8, [("safety", "safety", .7), ("obstacle", "obstacle", .9)])
    assert mixed["source"] == "safety" and mixed["brake"] == .9


@pytest.mark.parametrize("value", [-.1, 1.1, float("nan"), float("inf"), True])
def test_invalid_producer_values_never_become_valid_pedals(value):
    with pytest.raises(ValueError):
        choose(value, [])


def test_policy_hard_constraint_cannot_be_overridden_by_slow_preference():
    values = {"telemetry": {"truck": {"speed": 10., "speedLimit": 40.}}}
    plugin = Policy(PluginSDK(values, "drivepolicy"))
    plugin.on_start()
    plugin._planned = 40.
    values["telemetry"]["truck"]["speedLimit"] = 5.
    assert plugin._compute_planned_speed(.05) <= 5.


def test_navigation_loss_does_not_delay_current_emergency(flow):
    state, truck, engine, plugin, update, n, clock, acc = strict_flow(flow)
    update(8, 12.)
    n()
    acc.on_tick(.033)
    plugin.on_tick(.033)
    packet_value = state.get("nav_steering_debug")
    packet_value["observation_timestamp"] -= .6
    state.set("nav_steering_debug", packet_value)
    publish(state, state.get("telemetry")["truck"], "traffic",
            traffic_brake=.9, light_brake=0., light=None, lead_distance=2.)
    engine._flush_controls()
    assert engine.controller.throttle == 0.
    assert engine.controller.brake == 1.


def test_compact_identity_does_not_transfer_lane_geometry():
    class Counting(dict):
        def get(self, key, default=None):
            assert key != "lane_trajectory", "pedal arbitration copied geometry"
            return super().get(key, default)
    raw = Counting()
    state = SharedState(raw)
    state.set("lane_trajectory", {"revision": 1, "route_build_id": "a",
                                  "points": [[i, 0] for i in range(10000)]})
    first = context(state)
    state.set("lane_trajectory", {"revision": 1, "route_build_id": "b"})
    assert context(state) != first


@pytest.mark.parametrize("fault", ["invalid", "stale", "future", "binding"])
def test_latest_invalid_sdk_cannot_apply_an_older_valid_drive(flow, fault):
    state, truck, engine, plugin, update, n, clock, acc = strict_flow(flow, mode=3)
    update(8, 12.)
    n()
    acc.on_tick(.033)
    plugin.on_tick(.033)
    current = state.get("telemetry")["truck"]
    metadata = current["_control_observation"]
    if fault == "invalid":
        metadata["valid"] = False
    elif fault == "stale":
        metadata["observed_at"] -= .6
    elif fault == "future":
        metadata["observed_at"] += 1
    else:
        metadata["sdk_frame_us"] += 1
    state.set("telemetry", {"truck": current})
    engine._flush_controls()
    assert engine.controller.throttle == 0


def test_disable_between_releasing_brake_and_drive_never_writes_positive(flow):
    state, truck, engine, plugin, update, n, clock, acc = strict_flow(flow)
    update(8, 12.)
    n()
    acc.on_tick(.033)
    plugin.on_tick(.033)
    original = engine.controller.set_brake
    def disable(value):
        original(value)
        state.set("autopilot_active", False)
    engine.controller.set_brake = disable
    engine._flush_controls()
    assert engine.controller.throttle == 0


def test_curve_and_road_limits_keep_original_observation_and_identity(flow):
    state, truck, engine, plugin, update, n, clock, acc = strict_flow(flow)
    update(8, 12.)
    value = state.get("nav_steering_debug")
    lane = state.get("lane_trajectory")
    value.update(trajectory_identity={k: lane.get(k) for k in (
        "revision", "route_build_id", "navigation_intent_id", "source_game_session_id",
        "source_map_key", "source_dataset_fingerprint")},
        longitudinal_curve_profile={"radius_m": 35., "distance_m": 20.})
    state.set("nav_steering_debug", value)
    original = curve_input(state)
    assert original["radius_m"] == 35.
    state.set("path_curvature_radius", 99999.)  # A separate scalar cannot override it.
    assert curve_input(state) == original
    lane["route_build_id"] = "new-build"
    state.set("lane_trajectory", lane)
    assert curve_input(state) is None

    mp = Map(PluginSDK(state.values, "map"))
    mp.road_net = type("Roads", (), {"loaded": True,
        "road_type_at": lambda self, pos: {"type": "dirt", "lanes": 1}})()
    mp._road_type_observation = {"tractor_position": [0., 10., 0.],
        "timestamp": clock[0], "sdk_frame_us": truck["sdkFrameTimeUs"]}
    mp._publish_road_type((0., 0.))
    p = state.get("longitudinal_road")
    assert p["observation_timestamp"] == clock[0] and p["valid"]
    clock[0] += .6
    mp._publish_road_type((0., 0.))
    assert rejection(state.get("longitudinal_road"), context(state), clock[0])
    mp._publish_road_type((1., 0.))
    assert state.get("longitudinal_road")["valid"] is False


@pytest.mark.parametrize("source", ["acc", "policy"])
def test_one_n_waits_without_power_for_new_epoch_producer(flow, source):
    state, truck, engine, plugin, update, n, clock, acc = strict_flow(flow)
    state.set("longitudinal_" + source + "_active", True)
    n()
    update()
    if source == "policy":
        acc.on_tick(.033)
    engine._flush_controls()
    assert state.get("auto_drive_pending")
    assert engine.controller.throttle == engine.controller.brake == 0
    assert True not in engine.controller.drive_events
    acc.on_tick(.033)
    if source == "policy":
        publish(state, state.get("telemetry")["truck"], "policy", brake=0., planned_speed_ms=25.)
    engine._flush_controls()
    assert engine.controller.throttle == .12


@pytest.mark.parametrize("source", ["acc", "policy"])
def test_enabled_missing_producer_causes_controlled_stop_not_old_drive(flow, source):
    state, truck, engine, plugin, update, n, clock, acc = strict_flow(flow)
    update(8, 12.)
    n()
    acc.on_tick(.033)
    state.set("longitudinal_" + source + "_active", True)
    state.set("longitudinal_" + source, None)
    plugin.on_tick(.033)
    engine._flush_controls()
    assert engine.controller.throttle == 0
    assert state.get("autopilot_control_state") == "controlled_stop"


@pytest.mark.parametrize("source", ["acc", "policy"])
def test_final_boundary_does_not_wait_for_plugin_to_notice_required_producer_loss(flow, source):
    state, truck, engine, plugin, update, n, clock, acc = strict_flow(flow)
    update(8, 12.)
    n()
    acc.on_tick(.033)
    plugin.on_tick(.033)
    state.set("longitudinal_" + source + "_active", True)
    state.set("longitudinal_" + source, None)
    engine._flush_controls()  # No subsequent Autopilot tick.
    assert engine.controller.throttle == 0


@pytest.mark.parametrize("brake,emergency", [(.3, False), (1., True), (0., False)])
def test_latest_acc_brake_or_coast_cannot_be_overwritten_by_old_drive(flow, brake, emergency):
    state, truck, engine, plugin, update, n, clock, acc = strict_flow(flow)
    update(8, 12.)
    n()
    acc.on_tick(.033)
    plugin.on_tick(.033)
    publish(state, state.get("telemetry")["truck"], "acc", throttle=0.,
            brake=brake, emergency=emergency)
    engine._flush_controls()
    assert engine.controller.throttle == 0
    if emergency:
        assert engine.controller.brake == 1.


@pytest.mark.parametrize("source,values", [("road", {}), ("policy", {"brake": 0.})])
def test_malformed_constraint_is_not_a_valid_producer_packet(flow, source, values):
    state, truck, engine, plugin, update, n, clock, acc = strict_flow(flow)
    publish(state, state.get("telemetry")["truck"], source, **values)
    value, reason = read(state, source, required=True)
    assert value is None and "invalid longitudinal producer values" in reason


@pytest.mark.parametrize("key,value", [("emergency", "false"), ("reason", None),
                                     ("decision_source", None)])
def test_final_boundary_rejects_malformed_decision_metadata(flow, key, value):
    state, truck, engine, plugin, update, n, clock, acc = strict_flow(flow)
    update(8, 12.)
    n()
    acc.on_tick(.033)
    plugin.on_tick(.033)
    current = state.get("longitudinal_command")
    current[key] = value
    state.set("longitudinal_command", current)
    engine._flush_controls()
    assert engine.controller.throttle == 0


def test_simple_auto_safety_stop_does_not_hold_reverse_pedal_at_rest(flow):
    state, truck, engine, plugin, update, n, clock, acc = strict_flow(flow)
    update(8, 12.)
    n()
    acc.on_tick(.033)
    plugin.on_tick(.033)
    update(-1, 0.)
    state.set("autopilot_control_state", "controlled_stop")
    state.set("autopilot_stop_epoch", state.get("autopilot_failure_epoch"))
    engine._flush_controls()
    assert engine.controller.throttle == engine.controller.brake == 0.
    assert state.get("autopilot_active") is False
