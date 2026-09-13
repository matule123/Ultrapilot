"""Phase 5C route/prefab/profile/surface integration regressions."""
from dataclasses import replace
import hashlib
import math
import unittest

from core.navigation.drivable_surface import (
    COORDINATE_FRAME, DrivableSurfaceCatalog, identity_fingerprint,
    lane_path_fingerprint,
)
from core.navigation.lane_model import LaneConnection, LaneId, LanePath
from core.navigation.lane_trajectory import build_lane_trajectory
from core.navigation.maneuver_integration import (
    GROUND_REFERENCE_FRAME, GroundReferenceEvidence,
    audit_prefab_transition, build_maneuver_route_context,
    prepare_maneuver, validate_integration_result,
)
from core.navigation.maneuver_planner import PlannerLimits
from core.navigation.road_network import RoadNetwork
from core.sdk.vehicle_observation import VehicleObservation
from core.swept_envelope import Frame, Identity
from core.vehicle_profile import ProfileToken, VehicleProfile
from tests.maneuver_cases import junction
from tests.test_service_prefab_diagnostics import (
    ModGer63DiagnosticReplayTests,
)


def snapshot(path, *, intent="intent", build="build", request="request",
             session="session", map_key="map", dataset="dataset"):
    return {
        "valid": True,
        "revision": path.revision,
        "request_id": request,
        "navigation_intent_id": intent,
        "route_build_id": build,
        "source_game_session_id": session,
        "source_map_key": map_key,
        "source_dataset_fingerprint": dataset,
        "covered_gps_uids": list(path.source_gps_uids),
        "points": [[p.x, p.y, p.z] for p in path.points],
    }


def synthetic_network(path, *, duplicate=False, nav_node_index=1):
    net = RoadNetwork()
    segment = path.segments[1]
    token = segment.lane_id.prefab_token
    descriptor = (segment.start_uid, segment.end_uid)
    instance = (token, descriptor, 0, True)
    curves = (
        {"nav_node_index": nav_node_index, "next_lines": (1,),
         "prev_lines": ()},
        {"nav_node_index": nav_node_index, "next_lines": (2,),
         "prev_lines": (0,)},
        {"nav_node_index": nav_node_index, "next_lines": (),
         "prev_lines": (1,)},
    )
    net._prefab_lane_data[token] = {
        "path": "synthetic/confirmed_junction.ppd",
        "nodes": (
            {"input_lanes": (0,), "output_lanes": (), "y": 0.},
            {"input_lanes": (), "output_lanes": (2,), "y": 0.},
        ),
        "curves": curves,
    }
    net._prefab_desc[token] = (
        ((0., 0., 0.), (1., 1., 0.)), (),
        (("physical", 0, ((1, (0, 1, 2)),)),
         ("physical", 1, ())),
    )
    pair = (min(descriptor), max(descriptor))
    net._prefab_pairs[pair] = [instance, instance] if duplicate else [instance]
    return net


def surface_catalog(context, source_surface):
    surface = source_surface.surface
    raw = {
        "schema_version": 1,
        "method": "independent_drivable_surface_survey_v1",
        "source": "synthetic confirmed Phase 5C fixture",
        "evidence_sha256": hashlib.sha256(b"stage5c surface").hexdigest(),
        "confirmed": True,
        "coordinate_frame": COORDINATE_FRAME,
        "horizontal": True,
        "elevation_layer": context.local_lane_path.segments[0].elevation_layer,
        "identity_fingerprint": identity_fingerprint(context.identity),
        "lane_path_fingerprint": lane_path_fingerprint(context.local_lane_path),
        "boundary_uncertainty_m": source_surface.boundary_uncertainty_m,
        "exterior_xyz": [[x, surface.y_m, z] for x, z in surface.exterior],
        "holes_xyz": [
            [[x, surface.y_m, z] for x, z in ring]
            for ring in surface.holes
        ],
    }
    return DrivableSurfaceCatalog({"schema_version": 1, "surfaces": [raw]})


def profile(vehicle, now=10.):
    token = ProfileToken("provider", 1, "c" * 64, "e" * 64)
    observation = VehicleObservation(
        1, "synthetic_stage5c_fixture", "", now,
        sdk_frame_us=1_000_000, active=True, stable_read=True)
    value = VehicleProfile(
        1, token, observation, now, "", "", vehicle, (), ())
    return value


def ground(start, identity, token):
    return GroundReferenceEvidence(
        1, "synthetic fixed-axle survey", hashlib.sha256(
            b"stage5c ground").hexdigest(),
        "independent_fixed_axle_ground_survey_v1",
        GROUND_REFERENCE_FRAME, True, token,
        1_000_000, 10., replace(start, identity=identity, time_s=10.), .001)


class Stage5CManeuverIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = junction(half_width=3.5)
        cls.vehicle, cls.start, cls.path, cls.source_surface, _ = cls.request
        # The generic 5B3 fixture predates PPD integration and therefore does
        # not duplicate LaneId.connector_path into the source-segment field.
        # Production RoadNetwork segments always carry both identities.
        middle = replace(cls.path.segments[1],
                         connector_curve_indices=(0, 1, 2))
        cls.path = replace(cls.path, segments=(cls.path.segments[0], middle,
                                               cls.path.segments[2]))
        cls.snapshot = snapshot(cls.path)
        cls.network = synthetic_network(cls.path)
        cls.context = build_maneuver_route_context(
            cls.network, cls.path, cls.snapshot, 1)
        cls.catalog = surface_catalog(cls.context, cls.source_surface)
        cls.profile = profile(cls.vehicle)
        cls.ground = ground(cls.start, cls.context.identity, cls.profile.token)
        cls.limits = PlannerLimits(max_candidates=9)
        cls.result = prepare_maneuver(
            cls.network, cls.path, cls.snapshot, 1, cls.catalog,
            cls.profile, cls.profile, cls.ground, 10., cls.profile.token,
            "synthetic accessory confirmation", cls.limits)

    def test_road_prefab_road_is_bound_to_exact_authoritative_snapshot(self):
        context = self.context
        self.assertEqual(context.source_segment_indices, (0, 1, 2))
        self.assertEqual(context.source_gps_pair_indices, (0, 1, 2))
        self.assertEqual(context.local_lane_path.revision, self.path.revision)
        self.assertEqual(context.identity.lanes,
                         tuple(s.lane_id for s in self.path.segments))
        self.assertEqual(context.identity.gps_pairs,
                         tuple((s.start_uid, s.end_uid)
                               for s in self.path.segments))

    def test_exact_ppd_connector_proof_contains_all_authored_fields(self):
        proof = self.context.connector_proofs[0]
        self.assertEqual(proof.prefab_token, "synthetic_junction")
        self.assertEqual(proof.connector_path, (0, 1, 2))
        self.assertEqual(proof.descriptor_node_uids, (2, 3))
        self.assertEqual(proof.input_descriptor_node_index, 0)
        self.assertEqual(proof.output_descriptor_node_index, 1)
        self.assertEqual(proof.nav_node_indices, (1, 1, 1))
        self.assertEqual(proof.reciprocal_edges, ((0, 1), (1, 2)))

    def test_complete_chain_produces_offline_plan_but_no_control_authority(self):
        result = self.result
        self.assertTrue(result.accepted, result.failure_reason)
        self.assertTrue(result.plan.accepted)
        self.assertGreater(result.plan.envelope.minimum_clearance_m, .10)
        self.assertFalse(result.runtime_authorized)
        self.assertFalse(result.plan.runtime_authorized)
        self.assertEqual(result.runtime_blockers, (
            "TRAFFIC_CLEARANCE_NOT_EVALUATED",
            "LIVE_ENTRY_STATE_NOT_REVALIDATED"))
        self.assertEqual(validate_integration_result(
            result, self.network, self.path, self.snapshot, 1, self.catalog,
            self.profile, self.ground, 10., self.limits), "")

    def test_roundabout_uses_same_strict_connector_gate(self):
        middle = replace(self.path.segments[1], lane_type="roundabout")
        path = replace(self.path, segments=(self.path.segments[0], middle,
                                            self.path.segments[2]))
        # Geometry is already the authoritative trajectory; update point/path
        # identity is unchanged because the LaneId remains exact.
        context = build_maneuver_route_context(
            synthetic_network(path), path, snapshot(path), 1)
        self.assertEqual(context.connector_proofs[0].connector_path,
                         (0, 1, 2))

    def test_merge_and_split_keep_exact_directed_lane_connections(self):
        for kind in ("merge", "split"):
            with self.subTest(kind=kind):
                middle_id = LaneId(102, 1, 0)
                first = replace(
                    self.path.segments[0],
                    successors=(LaneConnection(middle_id, kind),))
                middle = replace(
                    self.path.segments[1], lane_id=middle_id,
                    lane_type=kind, connector_curve_indices=(),
                    successors=(LaneConnection(
                        self.path.segments[2].lane_id, kind),))
                raw = LanePath(
                    (first, middle, self.path.segments[2]), (),
                    self.path.source_gps_uids, confidence=self.path.confidence,
                    valid=True, revision=self.path.revision)
                path = build_lane_trajectory(raw)
                self.assertTrue(path.valid, path.failure_reason)
                context = build_maneuver_route_context(
                    RoadNetwork(), path, snapshot(path), 1)
                self.assertEqual(context.connector_proofs, ())
                self.assertEqual(context.identity.lanes[1], middle_id)
                self.assertEqual(context.source_gps_pair_indices, (0, 1, 2))

    def test_missing_description_instance_and_nav_node_fail_closed(self):
        cases = []
        no_desc = synthetic_network(self.path); no_desc._prefab_desc.clear()
        cases.append((no_desc, "MISSING_PREFAB_DESCRIPTION"))
        duplicate = synthetic_network(self.path, duplicate=True)
        cases.append((duplicate, "MISSING_OR_AMBIGUOUS_PREFAB_INSTANCE"))
        no_nav = synthetic_network(self.path, nav_node_index=-1)
        cases.append((no_nav, "GPS_PREFAB_CONNECTOR_NOT_AUTHORED"))
        for network, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(ValueError, reason):
                    build_maneuver_route_context(
                        network, self.path, self.snapshot, 1)

    def test_wrong_curve_chain_and_wrong_descriptor_uid_fail_closed(self):
        network = synthetic_network(self.path)
        data = network._prefab_lane_data["synthetic_junction"]
        curves = list(data["curves"])
        curves[1] = dict(curves[1], prev_lines=())
        network._prefab_lane_data["synthetic_junction"] = dict(
            data, curves=tuple(curves))
        with self.assertRaisesRegex(ValueError,
                                    "GPS_PREFAB_CONNECTOR_NOT_AUTHORED"):
            build_maneuver_route_context(network, self.path, self.snapshot, 1)

        network = synthetic_network(self.path)
        pair = (2, 3)
        network._prefab_pairs[pair] = [
            ("synthetic_junction", (3, 2), 0, True)]
        with self.assertRaisesRegex(ValueError,
                                    "GPS_PREFAB_CONNECTOR_NOT_AUTHORED"):
            build_maneuver_route_context(network, self.path, self.snapshot, 1)

    def test_elevation_bridge_and_missing_approach_do_not_form_a_maneuver(self):
        middle = replace(self.path.segments[1], elevation_layer=7)
        path = replace(self.path, segments=(self.path.segments[0], middle,
                                            self.path.segments[2]))
        with self.assertRaisesRegex(
                ValueError, "MANEUVER_SPANS_MULTIPLE_ELEVATION_LAYERS"):
            build_maneuver_route_context(
                synthetic_network(path), path, snapshot(path), 1)
        first_is_merge = replace(self.path.segments[0], lane_type="merge")
        no_approach = replace(
            self.path, segments=(first_is_merge, self.path.segments[1],
                                 self.path.segments[2]))
        with self.assertRaisesRegex(
                ValueError, "MANEUVER_REQUIRES_CONFIRMED_APPROACH_AND_EXIT"):
            build_maneuver_route_context(
                synthetic_network(no_approach), no_approach,
                snapshot(no_approach), 0)

    def test_missing_surface_body_and_ground_report_exact_blocker(self):
        empty = DrivableSurfaceCatalog({"schema_version": 1, "surfaces": []})
        result = prepare_maneuver(
            self.network, self.path, self.snapshot, 1, empty,
            self.profile, self.profile, self.ground, 10., self.profile.token,
            "confirmed", self.limits)
        self.assertEqual(result.failure_reason,
                         "MISSING_CONFIRMED_DRIVABLE_BOUNDARY")

        no_model = replace(self.profile, model=None,
                           model_failure="MISSING_CONFIRMED_BODY_PROFILE")
        result = prepare_maneuver(
            self.network, self.path, self.snapshot, 1, self.catalog,
            no_model, no_model, self.ground, 10., no_model.token,
            "confirmed", self.limits)
        self.assertEqual(result.failure_reason,
                         "MISSING_CONFIRMED_BODY_PROFILE")

        result = prepare_maneuver(
            self.network, self.path, self.snapshot, 1, self.catalog,
            self.profile, self.profile, None, 10., self.profile.token,
            "confirmed", self.limits)
        self.assertEqual(result.failure_reason,
                         "MISSING_CONFIRMED_GROUND_REFERENCE")

    def test_profile_and_ground_reference_staleness_fail_closed(self):
        newer = replace(self.profile, token=replace(
            self.profile.token, generation=2))
        result = prepare_maneuver(
            self.network, self.path, self.snapshot, 1, self.catalog,
            self.profile, newer, self.ground, 10., self.profile.token,
            "confirmed", self.limits)
        self.assertEqual(result.failure_reason, "STALE_VEHICLE_PROFILE")
        self.assertEqual(validate_integration_result(
            self.result, self.network, self.path, self.snapshot, 1,
            self.catalog, newer, self.ground, 10., self.limits),
            "STALE_MANEUVER_VEHICLE_PROFILE")

        # The profile token describes configuration and may remain identical
        # while the vehicle moves. The exact SDK frame/time binding must still
        # reject an old axle pose.
        next_observation = replace(
            self.profile.observation, sdk_frame_us=1_020_000,
            captured_at=10.02)
        next_frame = replace(
            self.profile, observation=next_observation, observed_at=10.02)
        self.assertEqual(validate_integration_result(
            self.result, self.network, self.path, self.snapshot, 1,
            self.catalog, next_frame, self.ground, 10.02, self.limits),
            "STALE_GROUND_REFERENCE_SDK_FRAME")
        self.assertEqual(validate_integration_result(
            self.result, self.network, self.path, self.snapshot, 1,
            self.catalog, self.profile, self.ground, 10.6, self.limits),
            "STALE_VEHICLE_OBSERVATION")

    def test_revision_intent_build_session_map_dataset_and_geometry_are_stale(self):
        mutations = {
            "revision": self.path.revision + 1,
            "navigation_intent_id": "other-intent",
            "route_build_id": "other-build",
            "source_game_session_id": "other-session",
            "source_map_key": "other-map",
            "source_dataset_fingerprint": "other-dataset",
        }
        for key, value in mutations.items():
            changed = dict(self.snapshot); changed[key] = value
            with self.subTest(key=key):
                self.assertNotEqual(validate_integration_result(
                    self.result, self.network, self.path, changed, 1,
                    self.catalog, self.profile, self.ground, 10.,
                    self.limits), "")
        changed = dict(self.snapshot)
        changed["points"] = [row[:] for row in self.snapshot["points"]]
        changed["points"][3][0] += .01
        self.assertEqual(validate_integration_result(
            self.result, self.network, self.path, changed, 1,
            self.catalog, self.profile, self.ground, 10., self.limits),
            "STALE_LANE_TRAJECTORY_GEOMETRY")

    def test_rolling_window_and_repeated_uid_occurrence_cannot_reuse_result(self):
        changed = dict(self.snapshot)
        changed["covered_gps_uids"] = changed["covered_gps_uids"][1:]
        self.assertEqual(validate_integration_result(
            self.result, self.network, self.path, changed, 1,
            self.catalog, self.profile, self.ground, 10., self.limits),
            "STALE_LANE_TRAJECTORY_GPS_WINDOW")
        changed = dict(self.snapshot)
        changed["covered_gps_uids"] = [1, 2, 1, 2]
        self.assertEqual(validate_integration_result(
            self.result, self.network, self.path, changed, 1,
            self.catalog, self.profile, self.ground, 10., self.limits),
            "STALE_LANE_TRAJECTORY_GPS_WINDOW")

    def test_changed_result_token_cannot_become_a_control_packet(self):
        changed = replace(self.result, token="0" * 64)
        self.assertEqual(validate_integration_result(
            changed, self.network, self.path, self.snapshot, 1, self.catalog,
            self.profile, self.ground, 10., self.limits),
            "MANEUVER_INTEGRATION_RESULT_INTEGRITY_MISMATCH")
        self.assertEqual(validate_integration_result(
            replace(self.result, runtime_authorized=True),
            self.network, self.path, self.snapshot, 1, self.catalog,
            self.profile, self.ground, 10., self.limits),
            "INVALID_MANEUVER_INTEGRATION_RESULT")

    def test_real_mod_ger_63_is_not_connected_across_the_4_5m_gap(self):
        fixture = ModGer63DiagnosticReplayTests(methodName="runTest")
        fixture.setUp()
        audit = audit_prefab_transition(
            fixture.net, fixture.source, fixture.required)
        self.assertFalse(audit.accepted)
        self.assertEqual(audit.prefab_token, "mod_ger_63")
        self.assertEqual(audit.source_connector_path, (1, 22, 16, 12))
        self.assertEqual(audit.required_connector_path, (13, 29, 17, 25))
        self.assertEqual(audit.source_output_descriptor_nodes, (2,))
        self.assertEqual(audit.required_input_descriptor_nodes, (2,))
        self.assertFalse(audit.direct_curve_edge)
        # Raw connector endpoints in the captured fixture are 4.443647 m
        # apart; the complete LanePath failure measured a 4.500000 m lateral
        # boundary gap. Neither value is below any topology bridge limit.
        self.assertAlmostEqual(audit.gap_m, 4.4436471507, places=8)
        self.assertEqual(audit.failure_reason,
            "PREFAB_CONNECTOR_CHANGE_REQUIRES_PROVEN_APPROACH_LANE")


if __name__ == "__main__":
    unittest.main()
