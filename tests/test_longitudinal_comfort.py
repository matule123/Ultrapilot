"""Phase 7.2 counterexamples and whole-flow safety regressions."""
import math
from unittest.mock import patch

import pytest

from plugins.acc.main import Plugin as ACC
from sdk.plugin_sdk import PluginSDK
from tests.test_control_safety_regressions import autopilot, ready_navigation_state
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_longitudinal_arbitration import strict_flow
from core.longitudinal import publish


def acc_at(speed=40., target=40., active=True):
    state = {"telemetry": {"truck": {"speed": speed / 3.6, "speedLimit": 0.}},
             "autopilot_active": active, "acc_target_speed": target}
    plugin = ACC(PluginSDK(state, "acc"))
    plugin.on_start()
    return state, plugin


def test_small_target_change_does_not_kick_derivative():
    state, acc = acc_at()
    acc.on_tick(.05)
    state["acc_target_speed"] = 40.1
    acc.on_tick(.05)
    assert state["acc_throttle"] < .09


def test_inactive_acc_does_not_charge_integral():
    _, acc = acc_at(speed=0, target=50, active=False)
    for _ in range(100):
        acc.on_tick(.05)
    assert acc.speed_pid._integral == 0


def test_external_braking_does_not_charge_positive_integral():
    state, acc = acc_at(speed=20, target=50)
    state["system_state"] = "CONTROLLED_STOP"
    for _ in range(20):
        acc.on_tick(.05)
    assert acc.speed_pid._integral == 0
    assert state["acc_throttle"] == 0


def test_parking_brake_inhibits_speed_integrator():
    state, acc = acc_at(speed=39.7, target=40)
    state["telemetry"]["truck"]["parkBrake"] = True
    for _ in range(10):
        acc.on_tick(.05)
    assert acc.speed_pid._integral == 0
    assert state["acc_throttle"] == 0


def test_eco_rise_uses_elapsed_time_not_tick_count():
    outputs = []
    for dt in (.02, .05, .1):
        state = ready_navigation_state(eco_active=True, eco_smoothing=.15)
        ap = autopilot({"speed": 12., "gear": 5}, state)
        for _ in range(round(1 / dt)):
            ap._apply_throttle(.05, dt)
        outputs.append(ap._last_throttle)
    assert max(outputs) - min(outputs) < 1e-6


def test_zero_drive_withdrawal_is_not_delayed_by_eco():
    state = ready_navigation_state(eco_active=True, eco_smoothing=.15)
    ap = autopilot({"speed": 12., "gear": 5}, state)
    ap._last_throttle = .5
    ap._apply_throttle(0., .05)
    assert ap.sdk.controller.throttle == 0


@pytest.mark.parametrize("dt", [float("nan"), float("inf"), 0., -.1, .6])
def test_invalid_or_delayed_speed_tick_cannot_authorize_drive(dt):
    state, acc = acc_at(speed=0, target=50)
    acc.on_tick(.05)
    acc.on_tick(dt)
    assert state["acc_throttle"] == 0
    assert acc.speed_pid._integral == 0


def test_saturated_speed_output_does_not_wind_up():
    _, acc = acc_at(speed=0, target=80)
    for _ in range(100):
        acc.on_tick(.05)
    assert acc.speed_pid._integral == 0


def test_target_noise_preserves_load_integral():
    state, acc = acc_at(speed=39.7, target=40)
    for _ in range(50):
        acc.on_tick(.05)
    before = acc.speed_pid._integral
    state["acc_target_speed"] = 40.01
    acc.on_tick(.05)
    assert acc.speed_pid._integral >= before


@pytest.mark.parametrize("mode", [0, 3])
def test_speed_controller_to_real_engine_boundary_and_emergency(flow, mode):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow, mode=mode)
    update(8, 12.)
    n()
    state.set("acc_target_speed", 50.)
    for _ in range(5):
        dt = update(8, 12.)
        acc.on_tick(dt)
        ap.on_tick(dt)
        engine._flush_controls()
        assert state.get("autopilot_active"), state.get("autopilot_disable_reason")
        assert engine.controller.throttle > 0 and engine.controller.brake == 0
    publish(state, state.get("telemetry")["truck"], "traffic",
            traffic_brake=.9, light_brake=0., light=None, lead_distance=2.)
    engine._flush_controls()  # No ACC or Autopilot tick required for emergency.
    assert engine.controller.throttle == 0 and engine.controller.brake == 1
    n()
    engine._flush_controls()
    assert engine.controller.throttle == engine.controller.brake == 0


def test_brake_hysteresis_prevents_threshold_flutter():
    state, acc = acc_at(speed=42.1, target=40)
    acc.on_tick(.05)
    assert state["acc_brake"] > 0
    state["telemetry"]["truck"]["speed"] = 41.9 / 3.6
    acc.on_tick(.05)
    assert state["acc_brake"] > 0  # Same braking episode, not drive/brake flip.
    state["telemetry"]["truck"]["speed"] = 40.4 / 3.6
    acc.on_tick(.05)
    assert state["acc_brake"] == 0


def test_lower_cap_is_immediate_and_only_rise_is_paced():
    state, acc = acc_at(speed=30, target=60)
    acc.on_tick(.05)
    state["road_speed_cap"] = 20.
    acc.on_tick(.05)
    assert acc.speed_pid.setpoint == 20
    assert state["acc_throttle"] == 0
    state["road_speed_cap"] = 60.
    acc.on_tick(.05)
    assert acc.speed_pid.setpoint == pytest.approx(20.3)


@pytest.mark.parametrize("target", [None, "bad", float("nan"), float("inf"), -1, 170])
def test_invalid_target_does_not_restore_drive(target):
    state, acc = acc_at(speed=10, target=40)
    acc.on_tick(.05)
    state["acc_target_speed"] = target
    acc.on_tick(.05)
    if target is None:
        assert math.isfinite(state["acc_throttle"])  # Persisted preference fallback.
    else:
        assert state["acc_throttle"] == 0
        assert acc.speed_pid._integral == 0


def test_duplicate_frame_does_not_integrate_or_republish(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 12.)
    n()
    acc.on_tick(.033)
    original = state.get("longitudinal_acc")
    integral = acc.speed_pid._integral
    clock[0] += .02
    acc.on_tick(.02)
    assert state.get("longitudinal_acc") == original
    assert acc.speed_pid._integral == integral
    assert original["observation_timestamp"] == clock[0] - .02


def test_sdk_elapsed_time_not_plugin_period_drives_integration(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 40 / 3.6)
    n()
    state.set("acc_target_speed", 40.3)
    acc.on_tick(.03)
    old = acc.speed_pid._integral
    update(8, 40 / 3.6, dt=.08)
    acc.on_tick(.02)  # Plugin invocation period differs from SDK observations.
    assert acc.speed_pid._integral-old == pytest.approx(.3*.08)


@pytest.mark.parametrize("fault", ["stale", "frame", "identity", "disabled"])
def test_bad_authority_does_not_revive_old_drive(flow, fault):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 12.)
    n()
    acc.on_tick(.033)
    ap.on_tick(.033)
    engine._flush_controls()
    assert engine.controller.throttle > 0
    if fault == "stale":
        clock[0] += .6
    elif fault == "frame":
        row = state.get("telemetry")
        row["truck"]["_control_observation"]["sdk_frame_us"] += 1
        state.set("telemetry", row)
    elif fault == "identity":
        state.set("game_session_id", "changed")
    else:
        n()
    acc.on_tick(.033)
    ap.on_tick(.033)
    engine._flush_controls()
    assert engine.controller.throttle == 0


def test_integrator_unwinds_when_output_is_limited():
    from core.pid import PID
    pid = PID(.15, .06, .015, setpoint=40., output_limits=(0., 1.),
              derivative_on_measurement=True, anti_windup=True, reset_on_setpoint=False)
    pid._integral = 10.
    pid.update(41., .05)
    assert pid._integral < 10.


def test_valid_paired_output_limits_integral_during_drive_ramp(flow):
    from core.longitudinal import context, finalize
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 40 / 3.6)
    n()
    state.set("acc_target_speed", 42.)
    acc.on_tick(.033)
    old = acc.speed_pid._integral
    finalize(state, state.get("telemetry")["truck"], 0., 0.,
             {"source": "acc", "reason": "ordinary drive ramp"}, context(state))
    update(8, 40 / 3.6)
    acc.on_tick(.033)
    assert acc.speed_pid._integral == old


def test_external_brake_release_resets_observation_interval(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 12.)
    n()
    acc.on_tick(.033)
    for _ in range(20):
        update(8, 12., dt=.05)
        publish(state, state.get("telemetry")["truck"], "traffic",
                traffic_brake=.2, light_brake=0., light=None, lead_distance=30.)
        acc.on_tick(.05)
        assert state.get("longitudinal_acc")["throttle"] == 0
        assert acc.speed_pid._integral == 0
    update(8, 12.)
    publish(state, state.get("telemetry")["truck"], "traffic",
            traffic_brake=0., light_brake=0., light=None)
    acc.on_tick(.033)
    assert state.get("longitudinal_acc")["valid"] is True


@pytest.mark.parametrize("park", [True, False])
def test_original_start_owner_is_unchanged_and_no_selector_in_simple_auto(flow, park):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    truck["parkBrake"] = park
    update(0, 0.)
    n()
    acc.on_tick(update(0, 0.))
    engine._flush_controls()
    assert True not in engine.controller.drive_events
    if park:
        assert engine.controller.throttle == 0
    else:
        assert engine.controller.throttle == .12


def test_brake_release_has_bounded_drive_recovery_at_backend(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 12.)
    n()
    for _ in range(15):
        dt = update(8, 12.)
        acc.on_tick(dt)
        ap.on_tick(dt)
        engine._flush_controls()
    publish(state, state.get("telemetry")["truck"], "traffic",
            traffic_brake=.2, light_brake=0., light=None)
    ap.on_tick(.033)
    engine._flush_controls()
    assert engine.controller.throttle == 0
    last = 0.
    for _ in range(10):
        dt = update(8, 12.)
        publish(state, state.get("telemetry")["truck"], "traffic",
                traffic_brake=0., light_brake=0., light=None)
        acc.on_tick(dt)
        ap.on_tick(dt)
        engine._flush_controls()
        assert engine.controller.throttle - last <= .8*dt+1e-8
        assert engine.controller.throttle == 0 or engine.controller.brake == 0
        last = engine.controller.throttle


def test_manual_off_resets_acc_before_reactivation(flow):
    state, truck, engine, ap, update, n, clock, acc = strict_flow(flow)
    update(8, 40/3.6)
    n()
    state.set("acc_target_speed", 41.)
    for _ in range(5):
        dt = update(8, 40/3.6)
        acc.on_tick(dt)
        ap.on_tick(dt)
        engine._flush_controls()
    n()
    engine._flush_controls()
    acc.on_tick(update(8, 40/3.6))
    assert acc.speed_pid._integral == 0
    assert engine.controller.throttle == engine.controller.brake == 0
    n()
    acc.on_tick(update(8, 40/3.6))
    ap.on_tick(.033)
    engine._flush_controls()
    assert state.get("autopilot_active")
    assert engine.controller.throttle > 0


def test_closed_loop_fixed_acceptance_matrix():
    from tools.run_longitudinal_comfort_bench import CASES, classes, simulate
    baseline = classes("7adf8c8")
    for case in CASES:
        before, after = simulate(case, baseline), simulate(case)
        assert after["steady_rms_kmh"] <= 1., (case["name"], after)
        assert after["steady_rms_kmh"] <= before["steady_rms_kmh"]+.3, case["name"]
        assert after["final_target_overshoot_kmh"] <= 2., case["name"]
        assert after["settling_s"] is not None and after["settling_s"] <= 60., case["name"]
        assert after["steady_pedal_reversals"] <= before["steady_pedal_reversals"], case["name"]
        assert after["max_throttle_rise_per_s"] <= .8+1e-9, case["name"]
        assert after["max_observation_age_s"] <= .5
        if case.get("emergency"):
            assert before["emergency_reaction_s"] == after["emergency_reaction_s"] == 0.


def test_downhill_requires_signed_speed_control_not_only_overspeed_threshold():
    from tools.run_longitudinal_comfort_bench import simulate
    result = simulate(dict(name="downhill_braking", initial=30., target=30., load=1.4, grade=-.06))
    assert result["steady_rms_kmh"] <= 1.
    assert result["final_target_overshoot_kmh"] <= 2.
