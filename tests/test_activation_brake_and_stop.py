"""Launch handoff and stale GPS output must have unambiguous ownership."""
from unittest import mock

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_simple_auto_launch_handoff import start_handoff


def test_unfinished_brake_intent_waits_without_cancelling_first_n(flow):
    state, truck, engine, plugin, publish, n, clock = start_handoff(flow)
    # A separate scalar cannot prove a completed output for this launch.
    state.set("ctl_brake", .04)
    engine._flush_controls()
    assert engine._drive_engagement is not None
    assert engine.controller.throttle == engine.controller.brake == 0
    plugin.on_tick(publish(8, 0.))
    engine._flush_controls()
    assert state.get("autopilot_active"), state.get("autopilot_disable_reason")
    assert engine.controller.throttle > 0


def test_completed_safety_brake_still_cancels_launch(flow):
    state, truck, engine, plugin, publish, n, clock = start_handoff(flow)
    state.set("collision_brake_request", .7)
    plugin.on_tick(publish(8, 0.))
    engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine.controller.throttle == 0
    assert engine._drive_engagement is None


def test_brake_written_after_a_completed_output_cannot_be_ignored(flow):
    state, truck, engine, plugin, publish, n, clock = start_handoff(flow)
    plugin.on_tick(publish(8, 0.))
    state.set("ctl_brake", .04)  # Next tick has begun, receipt still precedes it.
    engine._flush_controls()
    assert engine._drive_engagement is not None
    assert engine.controller.throttle == 0
    state.set("collision_brake_request", .7)
    plugin.on_tick(publish(8, 0.))
    engine._flush_controls()
    assert not state.get("autopilot_active")
    assert engine._drive_engagement is None
    assert engine.controller.throttle == 0


def test_stale_engine_packet_cannot_apply_previous_wheel_as_normal_control(flow):
    state, truck, engine, plugin, publish, n, clock = flow
    publish(8, 10.)
    n()
    plugin.on_tick(.02)
    state.update_batch({"ctl_steering": .25, "ctl_throttle": .4,
                        "lane_trajectory_heartbeat": clock[0] - .6})
    engine._flush_controls()
    assert engine.controller.throttle == 0
    assert state.get("autopilot_control_state") == "controlled_stop"
    assert "spomaľujem" in state.get("navigation_status").lower()
    assert engine.controller.steering != .25


def test_transient_stale_packet_does_not_resume_with_latched_hazards(flow):
    state, truck, engine, plugin, publish, n, clock = flow
    publish(8, 10.)
    n()
    plugin.on_tick(.02)
    engine._flush_controls()
    packet = state.get("nav_steering_debug")
    packet["observation_timestamp"] = clock[0] - .51
    state.set("nav_steering_debug", packet)
    plugin.on_tick(.02)
    engine._flush_controls()
    assert state.get("safety_hazard_active")
    for _ in range(3):
        plugin.on_tick(publish(8, 9.))
        engine._flush_controls()
        assert engine.controller.throttle == 0
        assert state.get("autopilot_control_state") == "controlled_stop"
    plugin.on_tick(publish(8, 0.))
    engine._flush_controls()
    assert not state.get("autopilot_active")
    plugin.on_tick(publish(8, 0.))  # Passive fresh readiness before a new N.
    n()
    plugin.on_tick(publish(8, 1.))
    engine._flush_controls()
    assert not state.get("safety_hazard_active")
    assert state.get("autopilot_control_state") != "controlled_stop"
    assert engine.controller.throttle > 0


def test_packet_expiring_after_validation_is_not_written_to_backend(flow):
    state, truck, engine, plugin, publish, n, clock = flow
    publish(8, 10.)
    n()
    plugin.on_tick(.02)
    packet = state.get("nav_steering_debug")
    packet["observation_timestamp"] = clock[0] - .3
    state.set("nav_steering_debug", packet)
    state.set("ctl_steering", .25)
    update = state.update_batch
    delayed = []

    def delayed_output_publication(values):
        if "engine_applied_steering" in values and not delayed:
            delayed.append(True)
            clock[0] += .204  # Fresh at validation, expired at physical write.
        update(values)

    with mock.patch.object(state, "update_batch", side_effect=delayed_output_publication):
        engine._flush_controls()
    assert engine.controller.throttle == 0
    assert engine.controller.steering != .25
    assert state.get("autopilot_control_state") == "controlled_stop"
    assert state.get("engine_applied_steering") == engine.controller.steering
