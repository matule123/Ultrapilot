"""Regression for the 27 Sep repeated automatic Drive-selector pulses."""

import time
import unittest
import sys
from types import SimpleNamespace
from unittest import mock

from core.engine import UltraPilotEngine
from sdk.plugin_sdk import (
    PluginSDK, CTL_SELECT_DRIVE, CTL_STEERING, CTL_THROTTLE,
)
from plugins.autopilot.main import Plugin as AutopilotPlugin
from tests.test_control_safety_regressions import (
    Controller, State, autopilot, ready_navigation_state,
)


class DriveEngagementSafetyTests(unittest.TestCase):
    def _parked_request(self, *, park_brake=True, backend="SCS_SDK"):
        now = time.monotonic()
        state = ready_navigation_state(autopilot_active=False, nav_active=True)
        truck = {"gear": 0, "speed": 0.0, "parkBrake": park_brake,
                 "sdkFrameTimeUs": 290205058}
        state.set("telemetry", {"truck": truck})
        state.set("telemetry_timestamp", now)
        state.set("ets2_transmission_mode", {
            "mode": 3, "status": "confirmed", "profile": "test-profile",
            "observed_at": now, "generation": "test-profile:3",
        })
        state.set("autopilot_navigation_readiness", {
            "ready": True, "timestamp": now, "source": "gps_lane",
            "revision": 7,
        })
        state.get("lane_match").update({
            "valid": True, "confidence": 0.95,
            "authority_confidence": 0.95,
        })
        state.set("nav_steering_debug", {
            "controller": "frenet_bicycle",
            "calculation_packet_schema_version": 1,
            "authority_valid": True, "authority_revision": 7,
            "navigation_intent_id": None, "route_build_id": "test-build",
            "source_game_session_id": "test-session",
            "source_map_key": "test-map",
            "source_dataset_fingerprint": "test-fingerprint",
            "computed_at": now, "observation_timestamp": now,
            "sdk_frame_us": truck["sdkFrameTimeUs"],
            "calculation_sequence": 1,
            "output": 0.0, "local_curvature": 0.0,
        })
        engine = UltraPilotEngine.__new__(UltraPilotEngine)
        engine.shared_state = state
        engine.controller = Controller()
        engine.controller.mode = backend
        engine.controller.scs = type("ConnectedSCS", (), {"connected": True})()
        engine._last_autopilot_command = None
        engine._was_active = False
        engine._drive_selector_pressed = False
        return state, truck, engine

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

        reason = engine._autopilot_activation_rejection_reason()
        self.assertIn("forward gear", reason)
        self.assertIn("Zaraďte D a potom stlačte N", reason)

    def test_inactive_selector_release_is_not_a_pending_drive_request(self):
        state, truck, plugin, engine = self._runtime(gear=0)
        state.set("autopilot_active", False)
        state.set(CTL_SELECT_DRIVE, None)
        plugin.on_tick(0.05)
        self.assertIsNone(state.get(CTL_SELECT_DRIVE))
        engine._last_drive_observed_gear = 0
        sequence = getattr(engine, "_drive_boundary_sequence", 0)
        for _ in range(3):
            engine._flush_controls()
        self.assertEqual(getattr(engine, "_drive_boundary_sequence", 0),
                         sequence)
        state.set(CTL_SELECT_DRIVE, True)
        engine._flush_controls()
        self.assertEqual(state.get("drive_boundary_event")["action"],
                         "discard_unconsumed_selector_intent")
        self.assertIsNone(state.get(CTL_SELECT_DRIVE))

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

    def test_auto_drive_rejects_invalid_gear_value_without_exception(self):
        state, truck, engine = self._parked_request()
        truck["gear"] = "unknown"
        self.assertTrue(engine._autopilot_activation_rejection_reason(
            allow_neutral=True))
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        self.assertFalse(state.get("auto_drive_pending", False))
        self.assertNotIn(True, engine.controller.drive_events)

    def test_one_activation_request_accepts_fresh_forward_gear_and_packet(self):
        now = time.monotonic()
        state = ready_navigation_state(autopilot_active=False, nav_active=True)
        truck = {"gear": 4, "speed": 0.0, "sdkFrameTimeUs": 290205058}
        state.set("telemetry", {"truck": truck})
        state.set("telemetry_timestamp", now)
        state.set("autopilot_navigation_readiness", {
            "ready": True, "timestamp": now, "source": "gps_lane",
            "revision": 7,
        })
        state.get("lane_match").update({
            "valid": True, "confidence": 0.95,
            "authority_confidence": 0.95,
        })
        state.set("nav_steering_debug", {
            "controller": "frenet_bicycle",
            "calculation_packet_schema_version": 1,
            "authority_valid": True, "authority_revision": 7,
            "navigation_intent_id": None, "route_build_id": "test-build",
            "source_game_session_id": "test-session",
            "source_map_key": "test-map",
            "source_dataset_fingerprint": "test-fingerprint",
            "computed_at": now, "observation_timestamp": now,
            "sdk_frame_us": truck["sdkFrameTimeUs"],
            "calculation_sequence": 1,
            "output": 0.0, "local_curvature": 0.0,
        })
        engine = UltraPilotEngine.__new__(UltraPilotEngine)
        engine.shared_state = state
        engine.controller = Controller()
        engine._last_autopilot_command = None
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        self.assertTrue(state.get("autopilot_active"))
        self.assertEqual(state.get("autopilot_engagement_request"), 1)
        self.assertNotIn(True, engine.controller.drive_events)
        plugin = autopilot(truck, state)
        plugin.on_tick(0.05)
        self.assertTrue(state.get("autopilot_active"))
        self.assertEqual(state.get("autopilot_engagement_confirmed"), 1)
        self.assertNotIn(True, plugin.sdk.controller.drive_events)

    def test_one_n_starts_single_parked_drive_request_without_propulsion(self):
        state, truck, engine = self._parked_request()
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        self.assertFalse(state.get("autopilot_active"))
        self.assertTrue(state.get("auto_drive_pending"))
        self.assertNotIn(True, engine.controller.drive_events)
        self.assertEqual(engine.controller.throttle, 0.0)
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertEqual(engine.controller.drive_events.count(True), 1)
        self.assertEqual(engine.controller.throttle, 0.0)
        self.assertFalse(state.get("autopilot_active"))
        engine._drive_engagement["pressed_at"] -= 0.20
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertEqual(engine.controller.drive_events.count(True), 1)
        truck["gear"] = 4
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertTrue(state.get("autopilot_active"))
        self.assertFalse(state.get("auto_drive_pending"))
        self.assertEqual(state.get("autopilot_engagement_request"), 1)
        self.assertEqual(engine.controller.throttle, 0.0)
        plugin = autopilot(truck, state)
        plugin.on_tick(0.05)
        self.assertIn("parkovaciu brzdu", state.get("navigation_status"))
        self.assertTrue(state.get("autopilot_active"))
        engine._flush_controls()
        self.assertEqual(engine.controller.throttle, 0.0)

    def test_stationary_neutral_without_park_brake_can_request_one_d(self):
        state, truck, engine = self._parked_request(park_brake=False)
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        self.assertTrue(state.get("auto_drive_pending"))
        self.assertFalse(state.get("autopilot_active"))
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertEqual(engine.controller.drive_events.count(True), 1)
        self.assertEqual((engine.controller.throttle,
                          engine.controller.brake,
                          engine.controller.steering), (0.0, 0.0, 0.0))

    def test_releasing_park_brake_during_d_handshake_does_not_cancel(self):
        state, truck, engine = self._parked_request()
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        truck["parkBrake"] = False
        truck["gear"] = 4
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertTrue(state.get("autopilot_active"))
        self.assertEqual(engine.controller.drive_events.count(True), 1)
        self.assertFalse(state.get("auto_drive_park_hold"))
        state.set(CTL_THROTTLE, 0.25)
        state.set("autopilot_control_heartbeat", time.monotonic())
        engine._flush_controls()
        self.assertGreater(engine.controller.throttle, 0.0)

    def test_one_n_at_50_kmh_in_confirmed_drive_uses_current_controls(self):
        state, truck, engine = self._parked_request(park_brake=False)
        truck["gear"] = 4
        truck["speed"] = 50.0 / 3.6
        state.set("acc_throttle", 0.5)
        state.set("acc_brake", 0.0)
        state.set("autopilot_control_heartbeat", time.monotonic())
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        self.assertTrue(state.get("autopilot_active"))
        self.assertFalse(state.get("auto_drive_pending", False))
        plugin = autopilot(truck, state)
        plugin.on_tick(0.05)
        state.set(CTL_THROTTLE, 0.3)
        state.set(CTL_STEERING, 0.12)
        state.set("autopilot_control_heartbeat", time.monotonic())
        engine._flush_controls()
        self.assertTrue(state.get("autopilot_active"))
        self.assertNotIn(True, engine.controller.drive_events)
        self.assertGreater(engine.controller.throttle, 0.0)
        self.assertNotEqual(engine.controller.steering, 0.0)
        self.assertGreaterEqual(engine.controller.brake, 0.0)

    def test_auto_drive_requires_scs_backend_even_without_park_brake(self):
        for brake, backend in ((False, "VJOY"), (None, "VJOY"),
                               (True, "VJOY")):
            with self.subTest(brake=brake, backend=backend):
                state, _truck, engine = self._parked_request(
                    park_brake=brake, backend=backend)
                state.set("autopilot_command", {"seq": 1, "enabled": True})
                engine._process_autopilot_command()
                self.assertFalse(state.get("autopilot_active"))
                self.assertFalse(state.get("auto_drive_pending", False))
                self.assertNotIn(True, engine.controller.drive_events)

    def test_auto_drive_rejects_reverse_changed_route_and_manual_cancel(self):
        for fault in ("reverse", "route", "manual"):
            with self.subTest(fault=fault):
                state, truck, engine = self._parked_request()
                state.set("autopilot_command", {"seq": 1, "enabled": True})
                engine._process_autopilot_command()
                truck["sdkFrameTimeUs"] += 33_333
                state.set("telemetry_timestamp", time.monotonic())
                engine._flush_controls()
                self.assertEqual(engine.controller.drive_events.count(True), 1)
                if fault == "reverse":
                    truck["gear"] = -1
                elif fault == "route":
                    state.get("lane_trajectory")["route_build_id"] = "new-build"
                else:
                    state.set("autopilot_command", {"seq": 2, "enabled": False})
                    engine._process_autopilot_command()
                truck["sdkFrameTimeUs"] += 33_333
                state.set("telemetry_timestamp", time.monotonic())
                engine._flush_controls()
                self.assertFalse(state.get("autopilot_active"))
                self.assertFalse(state.get("auto_drive_pending"))
                self.assertEqual(engine.controller.throttle, 0.0)
                self.assertEqual(engine.controller.drive_events.count(True), 1)

    def test_auto_drive_timeout_never_reengages_on_late_gear(self):
        state, truck, engine = self._parked_request()
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        engine._drive_engagement["deadline_at"] = time.monotonic() - 0.01
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertFalse(state.get("auto_drive_pending"))
        boundary = state.get("drive_boundary_event")
        self.assertEqual(boundary["action"], "cancel_drive_selection")
        self.assertEqual(boundary["observed_gear"], 0)
        self.assertIn("SDK gear 0", boundary["reason"])
        self.assertEqual(boundary["throttle_command"], 0.0)
        self.assertEqual(boundary["steering_command"], 0.0)
        truck["gear"] = 4
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertFalse(state.get("autopilot_active"))
        self.assertEqual(engine.controller.throttle, 0.0)
        self.assertEqual(engine.controller.drive_events.count(True), 1)

    def test_auto_drive_requires_new_sdk_frame_for_gear_confirmation(self):
        state, truck, engine = self._parked_request()
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        press_frame = truck["sdkFrameTimeUs"]
        truck["gear"] = 4
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertEqual(truck["sdkFrameTimeUs"], press_frame)
        self.assertFalse(state.get("autopilot_active"))

    def test_auto_drive_does_not_engage_when_selector_release_fails(self):
        state, truck, engine = self._parked_request()
        original = engine.controller.select_drive
        engine.controller.select_drive = lambda pressed=True: (
            False if not pressed else original(True))
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        truck["gear"] = 4
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertFalse(state.get("autopilot_active"))
        self.assertFalse(state.get("auto_drive_pending"))
        self.assertEqual(engine.controller.throttle, 0.0)

    def test_failed_selector_press_cancels_without_propulsion(self):
        state, truck, engine = self._parked_request(park_brake=False)
        original = engine.controller.select_drive
        engine.controller.select_drive = lambda pressed=True: (
            False if pressed else original(False))
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertFalse(state.get("auto_drive_pending"))
        self.assertFalse(state.get("autopilot_active"))
        self.assertNotIn(True, engine.controller.drive_events)
        self.assertEqual((engine.controller.throttle,
                          engine.controller.brake,
                          engine.controller.steering), (0.0, 0.0, 0.0))
        event = state.get("drive_boundary_event")
        self.assertEqual(event["action"], "cancel_drive_selection")
        self.assertIn("nepotvrdil zápis", event["reason"])

    def test_failed_selector_release_is_retried_only_as_false(self):
        state, truck, engine = self._parked_request()
        original = engine.controller.select_drive
        release_failures = []

        def selector(pressed=True):
            if not pressed and release_failures:
                release_failures.pop()
                return False
            return original(pressed)

        engine.controller.select_drive = selector
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        release_failures.append(True)
        truck["gear"] = 4
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertFalse(state.get("autopilot_active"))
        self.assertTrue(engine._selector_release_pending)
        engine._flush_controls()
        self.assertFalse(engine._selector_release_pending)
        self.assertEqual(engine.controller.drive_events.count(True), 1)

    def test_new_n_cannot_start_while_selector_release_is_unconfirmed(self):
        state, _truck, engine = self._parked_request()
        engine._selector_release_pending = True
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        self.assertFalse(state.get("autopilot_active"))
        self.assertFalse(state.get("auto_drive_pending", False))
        self.assertNotIn(True, engine.controller.drive_events)

    def test_cancelled_drive_with_failed_release_blocks_next_n(self):
        state, truck, engine = self._parked_request()
        original = engine.controller.select_drive
        engine.controller.select_drive = lambda pressed=True: (
            False if not pressed else original(True))
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertEqual(engine.controller.drive_events.count(True), 1)
        state.set("autopilot_command", {"seq": 2, "enabled": False})
        engine._process_autopilot_command()
        self.assertTrue(engine._selector_release_pending)
        state.set("autopilot_command", {"seq": 3, "enabled": True})
        engine._process_autopilot_command()
        self.assertFalse(state.get("auto_drive_pending"))
        self.assertEqual(engine.controller.drive_events.count(True), 1)

    def test_confirmed_drive_holds_throttle_until_park_brake_released(self):
        state, truck, engine = self._parked_request()
        state.set("autopilot_control_heartbeat", time.monotonic())
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        truck["gear"] = 4
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertTrue(state.get("auto_drive_park_hold"))
        state.set(CTL_THROTTLE, 0.4)
        engine._flush_controls()
        self.assertEqual(engine.controller.throttle, 0.0)
        self.assertTrue(state.get("auto_drive_park_hold"))
        truck["parkBrake"] = False
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        state.set(CTL_THROTTLE, 0.4)
        engine._flush_controls()
        self.assertFalse(state.get("auto_drive_park_hold"))
        self.assertGreater(engine.controller.throttle, 0.0)

    def test_auto_drive_rejects_stale_telemetry_or_invalid_speed(self):
        for fault in ("stale", "invalid_speed"):
            with self.subTest(fault=fault):
                state, truck, engine = self._parked_request()
                state.set("autopilot_command", {"seq": 1, "enabled": True})
                engine._process_autopilot_command()
                if fault == "stale":
                    state.set("telemetry_timestamp", time.monotonic() - 0.8)
                else:
                    truck["speed"] = float("nan")
                truck["sdkFrameTimeUs"] += 33_333
                engine._flush_controls()
                self.assertFalse(state.get("auto_drive_pending"))
                self.assertFalse(state.get("autopilot_active"))
                self.assertNotIn(True, engine.controller.drive_events)
                self.assertEqual(engine.controller.throttle, 0.0)

    def test_auto_drive_cancels_on_stale_packet_or_map_heartbeat(self):
        for fault in ("packet", "heartbeat"):
            with self.subTest(fault=fault):
                state, truck, engine = self._parked_request()
                state.set("autopilot_command", {"seq": 1, "enabled": True})
                engine._process_autopilot_command()
                truck["sdkFrameTimeUs"] += 33_333
                state.set("telemetry_timestamp", time.monotonic())
                engine._flush_controls()
                self.assertEqual(engine.controller.drive_events.count(True), 1)
                if fault == "packet":
                    state.get("nav_steering_debug")[
                        "observation_timestamp"] = time.monotonic() - 0.8
                else:
                    state.set("lane_trajectory_heartbeat",
                              time.monotonic() - 0.8)
                truck["sdkFrameTimeUs"] += 33_333
                state.set("telemetry_timestamp", time.monotonic())
                engine._flush_controls()
                self.assertFalse(state.get("auto_drive_pending"))
                self.assertFalse(state.get("autopilot_active"))
                self.assertEqual(engine.controller.throttle, 0.0)
                self.assertEqual(engine.controller.drive_events.count(True), 1)

    def test_second_n_cancels_pending_drive_without_second_press(self):
        state, truck, engine = self._parked_request()
        engine._has_win32 = True
        engine._hotkey_vk = 78
        engine._hotkey_was_down = False
        engine._game_window_active = lambda: True
        key = {"down": True}
        fake = SimpleNamespace(GetAsyncKeyState=lambda _vk: 0x8000 if
                               key["down"] else 0)
        with mock.patch.dict(sys.modules, {"win32api": fake}):
            engine._check_hotkey()
            self.assertTrue(state.get("auto_drive_pending"))
            truck["sdkFrameTimeUs"] += 33_333
            state.set("telemetry_timestamp", time.monotonic())
            engine._flush_controls()
            self.assertEqual(engine.controller.drive_events.count(True), 1)
            key["down"] = False
            engine._check_hotkey()
            key["down"] = True
            engine._check_hotkey()
            self.assertFalse(state.get("auto_drive_pending"))
            self.assertFalse(state.get("autopilot_active"))
            self.assertEqual(engine.controller.drive_events.count(True), 1)

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
