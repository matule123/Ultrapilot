"""Phase 5D production-boundary tests; all evidence remains synthetic."""
import copy
from dataclasses import replace
from pathlib import Path
import unittest

from core.navigation.maneuver_availability import production_data_availability
from core.navigation.maneuver_reference import (
    ManeuverReferenceMux, ManeuverReferencePublisher,
    approach_packet_rejection_reason,
    build_approach_control_packet, build_local_reference_packet,
    build_prepared_reference_packet, build_return_reference_packet,
)
from core.navigation.maneuver_runtime import ManeuverRuntime, ManeuverState
from core.navigation.route import Route
from plugins.autopilot.main import maneuver_reference_rejection_reason
from tests.maneuver_runtime_cases import clear_traffic, live_state, runtime_request


class Stage5DRuntimeIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = runtime_request()
        cls.prepared_runtime = ManeuverRuntime(cls.request)

    def setUp(self):
        self.runtime = self._runtime()
        self.snapshot = dict(self.request.snapshot)
        self.snapshot["lane_path_fingerprint"] = (
            self.request.result.context.full_lane_path_fingerprint)
        self.global_route = Route(self.snapshot["points"], "original-lane-path")
        self.prepared = build_prepared_reference_packet(
            self.runtime, 1, prepared_at=9.0)

    def _runtime(self):
        runtime = copy.copy(self.prepared_runtime)
        runtime.transitions = list(self.prepared_runtime.transitions)
        return runtime

    def _prepared_mux(self):
        mux = ManeuverReferenceMux()
        mux.offer(self.prepared, self.snapshot)
        mux._future.result(timeout=5.0)
        mux.offer(self.prepared, self.snapshot)  # harvest completed worker
        self.assertTrue(mux.preparation_payload()["ready"])
        return mux

    def _enter(self, runtime=None, now=10.0, sequence=2):
        runtime = runtime or self.runtime
        live = live_state(runtime, now)
        traffic = clear_traffic(runtime.request.result.context.identity, now)
        decision = runtime.update(live, traffic, enter=True)
        self.assertTrue(decision.runtime_authorized, decision.failure_reason)
        packet = build_local_reference_packet(
            runtime, decision, live, traffic, sequence, self.prepared)
        return live, traffic, decision, packet

    def test_bumpless_entry_and_exit_restore_same_global_route(self):
        mux = self._prepared_mux()
        try:
            live, _traffic, _decision, packet = self._enter()
            pose = live.ground.frame.poses[0]
            selected = mux.select(
                self.global_route, self.snapshot, packet,
                (pose.x, pose.z), pose.heading, live.now_s,
                live.ground.sdk_frame_us, True)
            self.assertTrue(selected.authority_valid, selected.failure_reason)
            self.assertEqual(selected.mode, "local_maneuver")
            self.assertIsNot(selected.route, self.global_route)
            self.assertLessEqual(selected.seam["position_delta_m"], 1e-12)
            self.assertLessEqual(selected.seam["heading_delta_rad"], 1e-12)
            self.assertLessEqual(selected.seam["curvature_delta_m_inv"], 1e-12)

            end = self.runtime.timing.times_s[-1]
            self.runtime._last_decision = replace(
                self.runtime._last_decision, computed_at_s=end - .05,
                valid_until_s=end + .05)
            end_live = live_state(
                self.runtime, end,
                speed=self.request.result.plan.speed_mps,
                sample_index=len(self.request.result.plan.samples) - 1)
            completed = self.runtime.update(
                end_live, clear_traffic(
                    self.request.result.context.identity, end))
            self.assertEqual(completed.state, ManeuverState.COMPLETED)
            returning = build_return_reference_packet(
                self.runtime, completed, end_live, 3, self.prepared)
            end_pose = end_live.ground.frame.poses[0]
            selected = mux.select(
                self.global_route, self.snapshot, returning,
                (end_pose.x, end_pose.z), end_pose.heading, end,
                end_live.ground.sdk_frame_us, True)
            self.assertTrue(selected.authority_valid, selected.failure_reason)
            self.assertEqual(selected.mode, "global_lane")
            self.assertIs(selected.route, self.global_route)
            self.assertLessEqual(selected.seam["position_delta_m"], 1e-12)
            self.assertLessEqual(selected.seam["heading_delta_rad"], 1e-12)
            self.assertLessEqual(selected.seam["curvature_delta_m_inv"], 1e-12)
        finally:
            mux.close()

    def test_local_cte_heading_and_curvature_match_global_at_entry(self):
        mux = self._prepared_mux()
        try:
            live, _traffic, _decision, packet = self._enter()
            pose = live.ground.frame.poses[0]
            selected = mux.select(
                self.global_route, self.snapshot, packet,
                (pose.x, pose.z), pose.heading, 10.,
                live.ground.sdk_frame_us, True)
            local = selected.route
            gi = selected.seam["global_index"]
            global_cte = self.global_route.cross_track_error(
                gi, (pose.x, pose.z))
            local_cte = local.cross_track_error(0, (pose.x, pose.z))
            self.assertAlmostEqual(global_cte, local_cte, places=12)
            self.assertEqual(selected.seam["heading_delta_rad"], 0.)
            self.assertEqual(selected.seam["curvature_delta_m_inv"], 0.)
        finally:
            mux.close()

    def test_first_execution_tick_harvests_completed_preparation(self):
        mux = ManeuverReferenceMux()
        try:
            mux.offer(self.prepared, self.snapshot)
            mux._future.result(timeout=5.)
            live, _traffic, _decision, packet = self._enter()
            pose = live.ground.frame.poses[0]
            selected = mux.select(
                self.global_route, self.snapshot, packet,
                (pose.x, pose.z), pose.heading, live.now_s,
                live.ground.sdk_frame_us, True)
            self.assertTrue(selected.authority_valid, selected.failure_reason)
            self.assertEqual(selected.mode, "local_maneuver")
        finally:
            mux.close()

    def test_stale_callback_and_delayed_engine_tick_revoke_local_authority(self):
        for change in ("sequence", "time"):
            with self.subTest(change=change):
                runtime = self._runtime()
                self.runtime = runtime
                self.prepared = build_prepared_reference_packet(runtime, 1, 9.)
                mux = self._prepared_mux()
                try:
                    live, _traffic, _decision, packet = self._enter(runtime)
                    pose = live.ground.frame.poses[0]
                    first = mux.select(
                        self.global_route, self.snapshot, packet,
                        (pose.x, pose.z), pose.heading, 10.,
                        live.ground.sdk_frame_us, True)
                    self.assertEqual(first.mode, "local_maneuver")
                    now = 10.01 if change == "sequence" else 10.11
                    stale = mux.select(
                        self.global_route, self.snapshot, packet,
                        (pose.x, pose.z), pose.heading, now,
                        live.ground.sdk_frame_us, True)
                    self.assertFalse(stale.authority_valid)
                    self.assertEqual(stale.mode, "revoked")
                    self.assertIn("STALE_LOCAL_REFERENCE_SEQUENCE" if change == "sequence"
                                  else "EXPIRED_LOCAL_REFERENCE_PACKET",
                                  stale.failure_reason)
                finally:
                    mux.close()

    def test_revision_intent_build_change_during_execution_revokes(self):
        for key in ("revision", "navigation_intent_id", "route_build_id"):
            with self.subTest(key=key):
                runtime = self._runtime()
                self.runtime = runtime
                self.prepared = build_prepared_reference_packet(runtime, 1, 9.)
                mux = self._prepared_mux()
                try:
                    live, _traffic, _decision, packet = self._enter(runtime)
                    pose = live.ground.frame.poses[0]
                    self.assertTrue(mux.select(
                        self.global_route, self.snapshot, packet,
                        (pose.x, pose.z), pose.heading, 10.,
                        live.ground.sdk_frame_us, True).authority_valid)
                    changed = dict(self.snapshot)
                    changed[key] = (9 if key == "revision" else "changed")
                    newer = dict(packet, sequence=3, computed_at=10.01,
                                 valid_until=10.1)
                    result = mux.select(
                        self.global_route, changed, newer,
                        (pose.x, pose.z), pose.heading, 10.01,
                        live.ground.sdk_frame_us, True)
                    self.assertFalse(result.authority_valid)
                    self.assertEqual(result.failure_reason,
                                     "STALE_LOCAL_REFERENCE_ROUTE_IDENTITY")
                finally:
                    mux.close()

    def test_manual_disable_immediately_revokes_and_latches(self):
        mux = self._prepared_mux()
        try:
            live, _traffic, _decision, packet = self._enter()
            pose = live.ground.frame.poses[0]
            self.assertTrue(mux.select(
                self.global_route, self.snapshot, packet,
                (pose.x, pose.z), pose.heading, 10.,
                live.ground.sdk_frame_us, True).authority_valid)
            result = mux.select(
                self.global_route, self.snapshot, {},
                (pose.x, pose.z), pose.heading, 10.01,
                live.ground.sdk_frame_us, False)
            self.assertFalse(result.authority_valid)
            self.assertEqual(result.failure_reason, "MANUAL_AUTOPILOT_DISABLED")
        finally:
            mux.close()

    def test_waiting_brakes_only_inside_bounded_envelope_and_clear_path_continues(self):
        blocked_traffic = clear_traffic(
            self.request.result.context.identity, 10., ())
        # Force WAITING without relying on actor placement; missing complete
        # coverage is itself a valid fail-closed wait reason.
        incomplete = replace(blocked_traffic, complete=False)
        waiting = self.runtime.update(live_state(self.runtime), incomplete)
        self.assertEqual(waiting.state, ManeuverState.WAITING_FOR_TRAFFIC)
        # A fresh, complete conflicting proof is needed for a publishable
        # approach packet; use the runtime's explicit traffic test fixture.
        from tests.maneuver_runtime_cases import actor
        runtime = self._runtime()
        live = live_state(runtime)
        conflict = clear_traffic(
            self.request.result.context.identity, 10., (actor(now=10.),))
        waiting = runtime.update(live, conflict)
        far = build_approach_control_packet(
            runtime, waiting, live, conflict, 2, 100., 0., .02)
        self.assertTrue(far["release_throttle"])
        self.assertEqual(far["brake_request"], 0.)
        self.assertEqual(approach_packet_rejection_reason(
            far, self.snapshot, 10., live.ground.sdk_frame_us), "")

        clear_runtime = self._runtime()
        clear_live = live_state(clear_runtime)
        clear = clear_traffic(self.request.result.context.identity, 10.)
        ready = clear_runtime.update(clear_live, clear)
        go = build_approach_control_packet(
            clear_runtime, ready, clear_live, clear, 3, 100., 0., .02)
        self.assertFalse(go["release_throttle"])
        self.assertGreater(go["target_speed_mps"], 0.)
        self.assertEqual(go["brake_request"], 0.)

    def test_autopilot_rejects_non_atomic_or_expired_local_reference(self):
        runtime = self.runtime
        live, _traffic, _decision, packet = self._enter(runtime)
        active = {
            "schema_version": 1, "mode": "local_maneuver",
            "authority_valid": True, "sequence": packet["sequence"],
            "plan_token": packet["plan_token"], "binding": packet["binding"],
            "computed_at": 10., "valid_until": 10.1,
            "sdk_frame_us": live.ground.sdk_frame_us,
            **{key: self.snapshot[key] for key in (
                "navigation_intent_id", "route_build_id", "revision",
                "source_game_session_id", "source_map_key",
                "source_dataset_fingerprint")},
        }
        steering = {
            "reference_mode": "local_maneuver",
            "maneuver_reference_sequence": packet["sequence"],
            "maneuver_plan_token": packet["plan_token"],
            "maneuver_reference_binding": packet["binding"],
            "maneuver_reference_valid_until": 10.1,
            "sdk_frame_us": live.ground.sdk_frame_us,
            **{key: self.snapshot[key] for key in (
                "navigation_intent_id", "route_build_id", "revision",
                "source_game_session_id", "source_map_key",
                "source_dataset_fingerprint")},
        }
        state = {"active_navigation_reference": active}
        self.assertEqual(maneuver_reference_rejection_reason(
            state, self.snapshot, steering, 10.01), "")
        self.assertIn("sequence", maneuver_reference_rejection_reason(
            state, self.snapshot, dict(steering,
                maneuver_reference_sequence=99), 10.01))
        self.assertIn("lease", maneuver_reference_rejection_reason(
            state, self.snapshot, steering, 10.11))

    def test_worker_publishes_reference_and_longitudinal_state_atomically(self):
        class State:
            def __init__(self):
                self.batches = []

            def update_batch(self, values):
                self.batches.append(copy.deepcopy(values))

        state = State()
        publisher = ManeuverReferencePublisher(state)
        prepared = publisher.publish_prepared(self.runtime, prepared_at=9.)
        self.assertEqual(len(state.batches), 1)
        self.assertEqual(set(state.batches[-1]), {
            "maneuver_reference_packet", "maneuver_approach_packet",
            "maneuver_runtime_status",
        })
        self.assertEqual(state.batches[-1]["maneuver_approach_packet"], {})

        live = live_state(self.runtime)
        traffic = clear_traffic(self.request.result.context.identity, 10.)
        decision = self.runtime.update(live, traffic, enter=True)
        reference, approach = publisher.publish_decision(
            self.runtime, decision, live, traffic)
        self.assertEqual(reference["state"], "LOCAL_EXECUTING")
        self.assertEqual(reference["prepared_sequence"], prepared["sequence"])
        self.assertEqual(approach, {})
        self.assertEqual(len(state.batches), 2)
        self.assertEqual(state.batches[-1]["maneuver_reference_packet"],
                         reference)
        self.assertEqual(state.batches[-1]["maneuver_approach_packet"], {})

        failed_reference, failed_approach = publisher.publish_decision(
            self.runtime, decision, live, None)
        self.assertEqual((failed_reference, failed_approach), ({}, {}))
        self.assertEqual(state.batches[-1]["maneuver_reference_packet"], {})
        self.assertEqual(state.batches[-1]["maneuver_approach_packet"], {})
        self.assertTrue(
            state.batches[-1]["maneuver_runtime_status"]["failure_reason"])

        publisher.revoke("MANUAL_AUTOPILOT_DISABLED")
        self.assertEqual(state.batches[-1]["maneuver_reference_packet"], {})
        self.assertEqual(state.batches[-1]["maneuver_approach_packet"], {})
        self.assertEqual(
            state.batches[-1]["maneuver_runtime_status"]["failure_reason"],
            "MANUAL_AUTOPILOT_DISABLED")

    def test_legacy_runtime_sources_remain_explicitly_fail_closed(self):
        class Reader:
            _traffic_buf = object()
        state = {
            "traffic": [{"x": 1., "z": 2., "length": 4.5}],
            "vehicle_envelope_snapshot": {"tractor_position": [0., 0., 0.]},
        }
        audit = production_data_availability(
            state, Reader(), {"vehicle_profiles": {"profiles": []},
                              "drivable_surfaces": {"surfaces": []}}, 10.)
        self.assertFalse(audit["runtime_activation_ready"])
        self.assertTrue(audit["sources"]["traffic"]["legacy_reader_connected"])
        self.assertFalse(audit["sources"]["traffic"]["phase5d_evidence_available"])
        self.assertEqual(set(audit["blockers"]), {
            "MISSING_COMPLETE_TRAFFIC_HISTORY_COVERAGE_AND_BODY_PRODUCER",
            "MISSING_CONFIRMED_BODY_PROFILE",
            "MISSING_FIXED_AXLE_GROUND_REFERENCE_PRODUCER",
            "MISSING_CONFIRMED_DRIVABLE_SURFACE_PRODUCER",
        })

    def test_no_second_lateral_or_physical_controller_is_added(self):
        root = Path(__file__).resolve().parents[1]
        reference = (root / "core/navigation/maneuver_reference.py").read_text(
            encoding="utf-8")
        map_source = (root / "plugins/map/main.py").read_text(encoding="utf-8")
        autopilot = (root / "plugins/autopilot/main.py").read_text(encoding="utf-8")
        for forbidden in ("SteeringDynamics(", "SteeringExecutor(",
                          "set_steering(", "lateral_controller"):
            self.assertNotIn(forbidden, reference)
        self.assertEqual(map_source.count("steer = route.steering("), 1)
        self.assertEqual(autopilot.count("SteeringDynamics()"), 1)
        self.assertEqual(autopilot.count("SteeringExecutor("), 1)


if __name__ == "__main__":
    unittest.main()
