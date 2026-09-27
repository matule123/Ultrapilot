"""Regression for the 27 Sep repeated automatic Drive-selector pulses."""

import time
import unittest

from core.engine import UltraPilotEngine
from sdk.plugin_sdk import PluginSDK, CTL_SELECT_DRIVE, CTL_THROTTLE
from plugins.autopilot.main import Plugin as AutopilotPlugin
from tests.test_control_safety_regressions import (
    Controller, State, autopilot, ready_navigation_state,
)


class DriveEngagementSafetyTests(unittest.TestCase):
    def _runtime(self, gear=0, speed=0.0):
        state = ready_navigation_state(
            system_state="CRUISE", acc_throttle=0.5,
            autopilot_control_heartbeat=time.monotonic())
        truck = {"speed": speed, "gear": gear,
                 "sdkFrameTimeUs": 290205058}
        state.set("telemetry", {"truck": truck})
        sdk = PluginSDK(state.values, "autopilot")
        plugin = AutopilotPlugin(sdk)
        plugin.on_start()
        engine = UltraPilotEngine.__new__(UltraPilotEngine)
        engine.shared_state = sdk.shared_state
        engine.controller = Controller()
        engine._was_active = False
        engine._drive_selector_pressed = False
        return state, truck, plugin, engine

    def _tick(self, truck, plugin, engine):
        plugin.on_tick(0.05)
        engine._flush_controls()
        return (engine.controller.drive_events[:],
                engine.controller.throttle, engine.controller.brake,
                engine.controller.steering,
                bool(engine.shared_state.get("autopilot_active")))

    def test_neutral_engagement_never_sends_an_automatic_drive_pulse(self):
        state = ready_navigation_state()
        truck = {"speed": 0.0, "gear": 0, "sdkFrameTimeUs": 290205058}
        plugin = autopilot(truck, state)

        plugin.on_tick(0.05)

        self.assertFalse(state.get("autopilot_active"))
        self.assertEqual(plugin.sdk.controller.throttle, 0.0)
        self.assertNotIn(True, plugin.sdk.controller.drive_events)

    def test_activation_rejects_observed_neutral_before_output(self):
        state = State({
            "autopilot_navigation_readiness": {
                "ready": True, "timestamp": time.monotonic(),
            },
            "telemetry_valid": True,
            "telemetry_timestamp": time.monotonic(),
            "telemetry": {"truck": {
                "gear": 0, "speed": 0.0, "sdkFrameTimeUs": 290205058,
            }},
        })
        engine = UltraPilotEngine.__new__(UltraPilotEngine)
        engine.shared_state = state

        self.assertIn("forward gear", engine._autopilot_activation_rejection_reason())

    def test_activation_rejects_old_forward_gear_frame(self):
        state = State({
            "autopilot_navigation_readiness": {
                "ready": True, "timestamp": time.monotonic(),
            },
            "telemetry_valid": True,
            "telemetry_timestamp": time.monotonic() - 0.8,
            "telemetry": {"truck": {
                "gear": 4, "speed": 0.0, "sdkFrameTimeUs": 290205058,
            }},
        })
        engine = UltraPilotEngine.__new__(UltraPilotEngine)
        engine.shared_state = state
        self.assertIn("stale", engine._autopilot_activation_rejection_reason())

    def test_manual_forward_gear_is_only_path_to_active_output(self):
        state, truck, plugin, engine = self._runtime(gear=4)
        output = self._tick(truck, plugin, engine)
        self.assertTrue(output[-1])
        self.assertNotIn(True, output[0])
        self.assertGreaterEqual(output[1], 0.0)

    def test_delayed_manual_drive_after_neutral_disable_does_not_resume(self):
        state, truck, plugin, engine = self._runtime()
        first = self._tick(truck, plugin, engine)
        self.assertFalse(first[-1])
        self.assertEqual(first[1:], (0.0, 0.0, 0.0, False))
        truck["gear"] = 4
        truck["sdkFrameTimeUs"] += 1_900_000
        late = self._tick(truck, plugin, engine)
        self.assertFalse(late[-1])
        self.assertEqual(late[1:], (0.0, 0.0, 0.0, False))
        self.assertNotIn(True, late[0])

    def test_reverse_and_repeated_neutral_activation_never_pulse_drive(self):
        state, truck, plugin, engine = self._runtime()
        for gear in (0, 0, -1, 0):
            truck["gear"] = gear
            truck["sdkFrameTimeUs"] += 33_333
            state.set("autopilot_active", True)
            output = self._tick(truck, plugin, engine)
            self.assertFalse(output[-1])
            self.assertEqual(output[1], 0.0)
            self.assertNotIn(True, output[0])

    def test_stale_old_selector_intent_is_discarded_after_reactivation(self):
        state, truck, plugin, engine = self._runtime(gear=4)
        state.set(CTL_SELECT_DRIVE, True)
        output = self._tick(truck, plugin, engine)
        self.assertTrue(output[-1])
        self.assertNotIn(True, output[0])
        self.assertIsNone(state.get(CTL_SELECT_DRIVE))

    def test_manual_shift_to_neutral_revokes_existing_authority(self):
        state, truck, plugin, engine = self._runtime(gear=4)
        self.assertTrue(self._tick(truck, plugin, engine)[-1])
        truck["gear"] = 0
        truck["sdkFrameTimeUs"] += 33_333
        output = self._tick(truck, plugin, engine)
        self.assertFalse(output[-1])
        self.assertEqual(output[1], 0.0)
        self.assertNotIn(True, output[0])

    def test_manual_disable_releases_physical_wheel_and_pedals(self):
        state, truck, plugin, engine = self._runtime(gear=4)
        self.assertTrue(self._tick(truck, plugin, engine)[-1])
        state.set("autopilot_active", False)
        truck["gameSteer"] = -0.18
        output = self._tick(truck, plugin, engine)
        self.assertEqual(output[1:4], (0.0, 0.0, 0.0))
        self.assertFalse(output[-1])
        self.assertAlmostEqual(plugin._steering_dynamics.command, 0.18)

    def test_stale_steering_packet_prevents_activation_even_in_forward_gear(self):
        state, truck, plugin, engine = self._runtime(gear=4)
        state.set("autopilot_active", False)
        now = time.monotonic()
        state.set("autopilot_navigation_readiness", {
            "ready": True, "source": "gps_lane", "revision": 7,
            "timestamp": now,
        })
        state.set("nav_steering_debug", {
            "controller": "frenet_bicycle",
            "calculation_packet_schema_version": 1,
            "authority_valid": True, "authority_revision": 7,
            "navigation_intent_id": None,
            "route_build_id": "test-build",
            "source_game_session_id": "test-session",
            "source_map_key": "test-map",
            "source_dataset_fingerprint": "test-fingerprint",
            "computed_at": now,
            "observation_timestamp": now - 1.0,
            "sdk_frame_us": truck["sdkFrameTimeUs"],
            "calculation_sequence": 1,
            "output": 0.0, "local_curvature": 0.0,
        })
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._last_autopilot_command = None
        engine._process_autopilot_command()
        self.assertFalse(state.get("autopilot_active"))
        self.assertIn("observation_timestamp is stale",
                      state.get("autopilot_disable_reason"))
        self.assertNotIn(True, engine.controller.drive_events)
        self.assertEqual(self._tick(truck, plugin, engine)[1:4],
                         (0.0, 0.0, 0.0))

    def test_observed_reverse_discards_queued_drive_and_propulsion(self):
        state, truck, plugin, engine = self._runtime(gear=-1, speed=-0.1)
        plugin.on_tick(0.05)
        state.set(CTL_SELECT_DRIVE, True)
        state.set(CTL_THROTTLE, 0.6)
        engine._flush_controls()
        self.assertFalse(state.get("autopilot_active"))
        self.assertEqual(engine.controller.throttle, 0.0)
        self.assertNotIn(True, engine.controller.drive_events)
        self.assertIsNone(state.get(CTL_SELECT_DRIVE))


if __name__ == "__main__":
    unittest.main()
