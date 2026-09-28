"""The ETS2 gearbox setting is separate from the observed engaged ratio."""

import time
import unittest
import os
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from core.engine import UltraPilotEngine
from core.transmission_mode import (
    TransmissionModeObserver, confirmed_mode, read_transmission_mode,
)
from sdk.plugin_sdk import CTL_BRAKE
from tests.test_drive_engagement_safety import DriveEngagementSafetyTests as _Fixture


class ProfileModeEvidenceTests(unittest.TestCase):
    def test_active_steam_profile_and_game_log_must_agree(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]
                                / "docs" / "steering-audit") as directory:
            root = Path(directory)
            profile = "driver"
            encoded = profile.encode().hex().upper()
            config = root / "steam_profiles" / encoded / "config_local.cfg"
            config.parent.mkdir(parents=True)
            config.write_text('uset g_trans "0"\n', encoding="utf-8")
            log = root / "game.log.txt"
            log.write_text(
                "************ : log created on : "
                + datetime.now().strftime("%A %B %d %Y @ %H:%M:%S") + "\n"
                '00:00:01.000 : uset g_trans "0"\n'
                "00:00:01.100 : Set profile finished: 'driver'\n"
                f'00:00:02.000 : /steam/profiles/{encoded}/save/autosave/game.sii\n',
                encoding="utf-8")
            found = read_transmission_mode(root)
            self.assertEqual(confirmed_mode(found), 0)
            self.assertIn("steam_profiles/", found["source"])
            os.utime(config, (time.time() + 10, time.time() + 10))
            self.assertIsNone(confirmed_mode(read_transmission_mode(root)))
            config.write_text('uset g_trans "3"\n', encoding="utf-8")
            self.assertIsNone(confirmed_mode(read_transmission_mode(root)))
            config.write_text('uset g_trans "oops"\n', encoding="utf-8")
            self.assertIsNone(confirmed_mode(read_transmission_mode(root)))
            config.unlink()
            self.assertIsNone(confirmed_mode(read_transmission_mode(root)))

    def test_config_edit_requires_new_game_confirmation(self):
        observer = TransmissionModeObserver()
        old = {"mode": 0, "status": "confirmed", "profile": "p",
               "observed_at": time.monotonic(), "log_identity": "log:a",
               "config_mtime_ns": 1}
        self.assertEqual(confirmed_mode(observer.accept(old)), 0)
        changed = dict(old, config_mtime_ns=2)
        self.assertIsNone(confirmed_mode(observer.accept(changed)))
        self.assertIsNone(confirmed_mode(observer.accept(changed)))
        self.assertEqual(confirmed_mode(observer.accept(dict(
            changed, log_identity="log:b"))), 0)

    def test_profile_change_does_not_inherit_old_log_mode(self):
        with TemporaryDirectory(dir=Path(__file__).resolve().parents[1]
                                / "docs" / "steering-audit") as directory:
            root = Path(directory)
            encoded = "driver".encode().hex().upper()
            config = root / "steam_profiles" / encoded / "config_local.cfg"
            config.parent.mkdir(parents=True)
            config.write_text('uset g_trans "0"\n', encoding="utf-8")
            log = root / "game.log.txt"
            log.write_text(
                "************ : log created on : "
                + datetime.now().strftime("%A %B %d %Y @ %H:%M:%S") + "\n"
                '00:00:01.000 : uset g_trans "0"\n'
                "00:00:01.100 : Set profile finished: 'old'\n"
                "00:00:02.100 : Set profile finished: 'driver'\n"
                f'00:00:02.200 : /steam/profiles/{encoded}/save/autosave/game.sii\n',
                encoding="utf-8")
            self.assertIsNone(confirmed_mode(read_transmission_mode(root)))


class SimpleAutomaticEngagementTests(unittest.TestCase):
    def test_one_n_in_simple_automatic_probes_forward_without_d_selector(self):
        state, truck, engine = _Fixture()._parked_request(
            park_brake=False)
        state.set("ets2_transmission_mode", {
            "mode": 0, "status": "confirmed", "profile": "active",
            "observed_at": time.monotonic(), "generation": "profile-a:0",
        })
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        self.assertTrue(state.get("auto_drive_pending"))
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertGreater(engine.controller.throttle, 0.0)
        self.assertEqual(engine.controller.brake, 0.0)
        self.assertEqual(engine.controller.steering, 0.0)
        self.assertNotIn(True, engine.controller.drive_events)
        self.assertFalse(state.get("autopilot_active"))
        truck["gear"] = 4
        truck["speed"] = 0.6
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertTrue(state.get("autopilot_active"))
        self.assertEqual(engine.controller.throttle, 0.0)

    def test_confirmed_forward_ratio_while_moving_engages_directly(self):
        state, truck, engine = _Fixture()._parked_request(
            park_brake=False)
        truck.update(gear=4, speed=50.0 / 3.6)
        state.set("ets2_transmission_mode", dict(
            state.get("ets2_transmission_mode"), mode=0,
            generation="test-profile:0"))
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        self.assertTrue(state.get("autopilot_active"))
        self.assertNotIn(True, engine.controller.drive_events)
        self.assertEqual(engine._active_transmission_mode, 0)
        truck["speed"] = 0.0
        state.set(CTL_BRAKE, 0.4)
        state.set("autopilot_control_heartbeat", time.monotonic())
        engine._flush_controls()
        self.assertFalse(state.get("autopilot_active"))
        self.assertEqual(engine.controller.brake, 0.0)

    def test_mode0_park_brake_releases_before_probe(self):
        state, truck, engine = _Fixture()._parked_request()
        state.set("ets2_transmission_mode", dict(
            state.get("ets2_transmission_mode"), mode=0,
            generation="test-profile:0"))
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertEqual(engine.controller.throttle, 0.0)
        self.assertEqual(engine.controller.brake, 0.0)
        truck["parkBrake"] = False
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertGreater(engine.controller.throttle, 0.0)

    def test_mode0_stale_frame_or_timeout_releases_probe(self):
        for fault in ("frame", "timeout"):
            with self.subTest(fault=fault):
                state, truck, engine = _Fixture()._parked_request(
                    park_brake=False)
                state.set("ets2_transmission_mode", dict(
                    state.get("ets2_transmission_mode"), mode=0,
                    generation="test-profile:0"))
                state.set("autopilot_command", {"seq": 1, "enabled": True})
                engine._process_autopilot_command()
                truck["sdkFrameTimeUs"] += 33_333
                state.set("telemetry_timestamp", time.monotonic())
                engine._flush_controls()
                self.assertGreater(engine.controller.throttle, 0.0)
                if fault == "frame":
                    engine._drive_engagement["last_new_frame_at"] -= 0.2
                else:
                    engine._drive_engagement["deadline_at"] -= 3.0
                engine._flush_controls()
                self.assertFalse(state.get("auto_drive_pending"))
                self.assertEqual(engine.controller.throttle, 0.0)

    def test_mode0_reversing_and_profile_change_cancel_probe(self):
        for fault in ("reverse", "motion", "profile", "packet", "backend"):
            with self.subTest(fault=fault):
                state, truck, engine = _Fixture()._parked_request(
                    park_brake=False)
                state.set("ets2_transmission_mode", dict(
                    state.get("ets2_transmission_mode"), mode=0,
                    generation="test-profile:0"))
                state.set("autopilot_command", {"seq": 1, "enabled": True})
                engine._process_autopilot_command()
                truck["sdkFrameTimeUs"] += 33_333
                state.set("telemetry_timestamp", time.monotonic())
                engine._flush_controls()
                self.assertGreater(engine.controller.throttle, 0.0)
                if fault == "reverse":
                    truck["gear"] = -1
                elif fault == "motion":
                    truck["speed"] = -0.2
                elif fault == "profile":
                    state.set("ets2_transmission_mode", dict(
                        state.get("ets2_transmission_mode"),
                        generation="other-profile:0"))
                elif fault == "packet":
                    state.get("nav_steering_debug")["observation_timestamp"] = 0.0
                else:
                    engine.controller.scs.connected = False
                truck["sdkFrameTimeUs"] += 33_333
                state.set("telemetry_timestamp", time.monotonic())
                engine._flush_controls()
                self.assertFalse(state.get("auto_drive_pending"))
                self.assertFalse(state.get("autopilot_active"))
                self.assertEqual(engine.controller.throttle, 0.0)
                self.assertNotIn(True, engine.controller.drive_events)

    def test_mode0_backend_write_failure_cancels_without_active_authority(self):
        state, truck, engine = _Fixture()._parked_request(park_brake=False)
        state.set("ets2_transmission_mode", dict(
            state.get("ets2_transmission_mode"), mode=0,
            generation="test-profile:0"))
        original = engine.controller.set_throttle

        def fail_write(value):
            original(value)
            if value > 0.0:
                engine.controller.scs.connected = False

        engine.controller.set_throttle = fail_write
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertFalse(state.get("autopilot_active"))
        self.assertFalse(state.get("auto_drive_pending"))
        self.assertEqual(engine.controller.throttle, 0.0)

    def test_mode0_stop_brake_releases_instead_of_requesting_reverse(self):
        state, truck, engine = _Fixture()._parked_request(park_brake=False)
        state.set("ets2_transmission_mode", dict(
            state.get("ets2_transmission_mode"), mode=0,
            generation="test-profile:0"))
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        truck["gear"] = 4
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertTrue(state.get("autopilot_active"))
        state.set(CTL_BRAKE, 0.6)
        state.set("autopilot_control_heartbeat", time.monotonic())
        engine._flush_controls()
        self.assertFalse(state.get("autopilot_active"))
        self.assertEqual(engine.controller.brake, 0.0)
        self.assertEqual(engine.controller.throttle, 0.0)

    def test_mode_change_after_engagement_revokes_authority(self):
        state, truck, engine = _Fixture()._parked_request(park_brake=False)
        state.set("ets2_transmission_mode", dict(
            state.get("ets2_transmission_mode"), mode=0,
            generation="test-profile:0"))
        state.set("autopilot_command", {"seq": 1, "enabled": True})
        engine._process_autopilot_command()
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        truck["gear"] = 4
        truck["sdkFrameTimeUs"] += 33_333
        state.set("telemetry_timestamp", time.monotonic())
        engine._flush_controls()
        self.assertTrue(state.get("autopilot_active"))
        state.set("ets2_transmission_mode", dict(
            state.get("ets2_transmission_mode"), generation="new-profile:0"))
        engine._flush_controls()
        self.assertFalse(state.get("autopilot_active"))
        self.assertEqual(engine.controller.throttle, 0.0)

    def test_unsupported_or_unknown_mode_rejects_neutral_auto_start(self):
        for mode in (None, 1, 2):
            with self.subTest(mode=mode):
                state, _truck, engine = _Fixture()._parked_request()
                state.set("ets2_transmission_mode", {
                    "mode": mode, "status": "confirmed" if mode is not None else "unknown",
                    "observed_at": time.monotonic(), "generation": str(mode)})
                state.set("autopilot_command", {"seq": 1, "enabled": True})
                engine._process_autopilot_command()
                self.assertFalse(state.get("auto_drive_pending", False))
                self.assertNotIn(True, engine.controller.drive_events)
