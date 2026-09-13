"""Phase 5C: bind one local maneuver to proven route and prefab topology.

This module is an authority *gate*, not another controller.  It extracts an
exact road/prefab/road window from the current revision-bound LanePath, proves
the selected PPD connector from authored input/output lanes, navNodeIndex and
reciprocal nextLines/prevLines, resolves the independently confirmed 5B2
surface, binds the confirmed 5B1 vehicle profile and invokes the pure 5B3
planner.

An accepted result is still ``runtime_authorized=False``.  Phase 5C has no
traffic-conflict authority and therefore cannot publish steering.  Missing
body, ground, boundary or connector evidence stays fail-closed; neither map
centrelines nor display polygons are promoted to a road surface.
"""
from dataclasses import asdict, dataclass, replace
import math

from core.navigation.drivable_surface import (
    DrivableSurfaceCatalog, digest, lane_path_fingerprint,
)
from core.navigation.lane_model import LanePath, LaneSegment
from core.navigation.lane_trajectory import (
    build_lane_trajectory, validate_lane_trajectory,
)
from core.navigation.maneuver_planner import (
    ManeuverPlan, PlannerLimits, plan_maneuver, validate_plan_request,
)
from core.swept_envelope import EnvelopeError, Frame, Identity
from core.vehicle_profile import (
    ProfileToken, VehicleProfile, bind_envelope_vehicle,
)


SENSITIVE_LANE_TYPES = frozenset(("prefab", "roundabout", "merge", "split"))
GROUND_REFERENCE_FRAME = "ETS2_WORLD_FIXED_AXLE_GROUND"
SUPPORTED_GROUND_METHODS = frozenset((
    "independent_fixed_axle_ground_survey_v1",
    "scs_wheel_contact_ground_projection_v1",
))


def require(condition, reason):
    if not condition:
        raise EnvelopeError(reason)


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _sha256(value):
    return (type(value) is str and len(value) == 64
            and all(char in "0123456789abcdef" for char in value))


@dataclass(frozen=True)
class GroundReferenceEvidence:
    """External proof that Frame poses are fixed axles on one support plane.

    SDK article positions are chassis origins and cannot be silently used as
    5A axle/ground poses.  A producer must explicitly perform and attest that
    conversion.  This contract intentionally does not guess it from wheel
    track or PPD geometry.
    """
    schema_version: int
    source: str
    evidence_sha256: str
    method: str
    coordinate_frame: str
    confirmed: bool
    profile_token: ProfileToken
    sdk_frame_us: int
    observed_at: float
    frame: Frame
    position_uncertainty_m: float

    def validate(self, current_profile, identity):
        require(type(self.schema_version) is int and self.schema_version == 1,
                "INVALID_GROUND_REFERENCE_SCHEMA")
        require(self.method in SUPPORTED_GROUND_METHODS,
                "UNSUPPORTED_GROUND_REFERENCE_METHOD")
        require(self.coordinate_frame == GROUND_REFERENCE_FRAME,
                "UNSUPPORTED_GROUND_REFERENCE_FRAME")
        require(self.confirmed is True and type(self.source) is str
                and bool(self.source.strip()) and _sha256(self.evidence_sha256),
                "UNPROVEN_GROUND_REFERENCE")
        require(isinstance(current_profile, VehicleProfile)
                and self.profile_token == current_profile.token,
                "STALE_GROUND_REFERENCE_PROFILE")
        observation = current_profile.observation
        require(observation is not None and type(self.sdk_frame_us) is int
                and self.sdk_frame_us > 0
                and self.sdk_frame_us == observation.sdk_frame_us,
                "STALE_GROUND_REFERENCE_SDK_FRAME")
        require(_number(self.observed_at)
                and abs(self.observed_at-current_profile.observed_at) <= 1e-9,
                "STALE_GROUND_REFERENCE_TIME")
        require(_number(self.position_uncertainty_m)
                and .0001 <= self.position_uncertainty_m <= .25,
                "INVALID_GROUND_REFERENCE_UNCERTAINTY")
        require(isinstance(self.frame, Frame)
                and self.frame.identity == identity,
                "STALE_GROUND_REFERENCE_IDENTITY")
        require(abs(self.frame.time_s-self.observed_at) <= 1e-9,
                "STALE_GROUND_REFERENCE_TIME")


@dataclass(frozen=True)
class PrefabConnectorProof:
    lane_id: object
    gps_pair: tuple[int, int]
    prefab_token: str
    descriptor_node_uids: tuple[int, ...]
    origin_node_index: int
    input_descriptor_node_index: int
    output_descriptor_node_index: int
    connector_path: tuple[int, ...]
    nav_node_indices: tuple[int, ...]
    reciprocal_edges: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class ManeuverRouteContext:
    identity: Identity
    request_id: str
    full_lane_path_fingerprint: str
    local_lane_path: LanePath
    source_segment_indices: tuple[int, ...]
    source_gps_pair_indices: tuple[int, ...]
    snapshot_fingerprint: str
    connector_proofs: tuple[PrefabConnectorProof, ...]


@dataclass(frozen=True)
class PrefabTransitionAudit:
    accepted: bool
    failure_reason: str
    prefab_token: str
    source_connector_path: tuple[int, ...]
    required_connector_path: tuple[int, ...]
    source_output_descriptor_nodes: tuple[int, ...]
    required_input_descriptor_nodes: tuple[int, ...]
    direct_curve_edge: bool
    gap_m: float
    vertical_residual_m: float
    heading_residual_deg: float


@dataclass(frozen=True)
class ManeuverIntegrationResult:
    accepted: bool
    failure_reason: str
    context: ManeuverRouteContext | None = None
    plan: ManeuverPlan | None = None
    token: str = ""
    surface_token: str = ""
    vehicle_profile_token: ProfileToken | None = None
    ground_evidence_sha256: str = ""
    # Traffic occupancy is intentionally outside Phase 5C.
    runtime_authorized: bool = False
    runtime_blockers: tuple[str, ...] = ()
    diagnostics: tuple = ()


def _snapshot_hash(snapshot, full_path_hash):
    return digest({
        "valid": snapshot.get("valid"),
        "revision": snapshot.get("revision"),
        "request_id": snapshot.get("request_id"),
        "intent": snapshot.get("navigation_intent_id"),
        "build": snapshot.get("route_build_id"),
        "session": snapshot.get("source_game_session_id"),
        "map": snapshot.get("source_map_key"),
        "dataset": snapshot.get("source_dataset_fingerprint"),
        "covered_gps_uids": snapshot.get("covered_gps_uids"),
        "points": snapshot.get("points"),
        "lane_path": full_path_hash,
    })


def _prove_snapshot(lane_path, snapshot):
    validation = validate_lane_trajectory(lane_path)
    require(validation.valid, "INVALID_AUTHORITATIVE_LANE_PATH")
    require(type(snapshot) is dict and snapshot.get("valid") is True,
            "INVALID_LANE_TRAJECTORY_SNAPSHOT")
    require(type(snapshot.get("revision")) is int
            and snapshot["revision"] == lane_path.revision,
            "STALE_LANE_TRAJECTORY_REVISION")
    required = ("request_id", "navigation_intent_id", "route_build_id",
                "source_game_session_id", "source_map_key",
                "source_dataset_fingerprint")
    require(all(snapshot.get(name) is not None
                and str(snapshot.get(name)).strip() for name in required),
            "MISSING_LANE_TRAJECTORY_IDENTITY")
    covered = tuple(int(uid) for uid in
                    (snapshot.get("covered_gps_uids") or ()))
    require(covered == tuple(lane_path.source_gps_uids),
            "STALE_LANE_TRAJECTORY_GPS_WINDOW")
    points = snapshot.get("points")
    require(type(points) is list and len(points) == len(lane_path.points),
            "STALE_LANE_TRAJECTORY_GEOMETRY")
    for raw, point in zip(points, lane_path.points):
        require(type(raw) in (list, tuple) and len(raw) >= 3
                and all(_number(raw[index]) for index in range(3))
                and max(abs(float(raw[0])-point.x),
                        abs(float(raw[1])-point.y),
                        abs(float(raw[2])-point.z)) <= 1e-7,
                "STALE_LANE_TRAJECTORY_GEOMETRY")


def _sensitive(segment):
    return (segment.lane_type in SENSITIVE_LANE_TYPES
            or segment.lane_id.prefab_token not in (None, "graph"))


def _extract_window(lane_path, target_segment_index):
    segments = tuple(lane_path.segments)
    require(type(target_segment_index) is int
            and 0 <= target_segment_index < len(segments),
            "INVALID_MANEUVER_SEGMENT_INDEX")
    require(_sensitive(segments[target_segment_index]),
            "SEGMENT_IS_NOT_A_MANEUVER")
    first = last = target_segment_index
    while first > 0 and _sensitive(segments[first-1]):
        first -= 1
    while last+1 < len(segments) and _sensitive(segments[last+1]):
        last += 1
    require(first > 0 and last+1 < len(segments),
            "MANEUVER_REQUIRES_CONFIRMED_APPROACH_AND_EXIT")
    first -= 1
    last += 1
    selected = segments[first:last+1]
    require(selected[0].lane_type == "road"
            and selected[0].lane_id.prefab_token is None,
            "MISSING_CONFIRMED_ROAD_APPROACH")
    require(selected[-1].lane_type == "road"
            and selected[-1].lane_id.prefab_token is None,
            "MISSING_CONFIRMED_ROAD_EXIT")
    require(not any(segment.lane_type == "lane_change"
                    or segment.lane_change is not None for segment in selected),
            "UNSUPPORTED_PREEXISTING_LANE_CHANGE_IN_MANEUVER")
    layers = {segment.elevation_layer for segment in selected}
    require(len(layers) == 1, "MANEUVER_SPANS_MULTIPLE_ELEVATION_LAYERS")
    for before, after in zip(selected, selected[1:]):
        matches = tuple(connection for connection in before.successors
                        if connection.target == after.lane_id)
        require(len(matches) == 1, "AMBIGUOUS_OR_MISSING_MANEUVER_TOPOLOGY")
        require(before.end_uid == after.start_uid,
                "MANEUVER_UID_TOPOLOGY_MISMATCH")

    pairs = tuple(segment.gps_pair_index for segment in selected)
    require(all(type(value) is int and value >= 0 for value in pairs),
            "MANEUVER_OUTSIDE_CONFIRMED_GPS_PAIRS")
    first_pair, last_pair = min(pairs), max(pairs)
    require(tuple(dict.fromkeys(pairs)) == tuple(range(first_pair, last_pair+1)),
            "MANEUVER_GPS_PAIR_ORDER_GAP")
    source_uids = tuple(lane_path.source_gps_uids[first_pair:last_pair+2])
    require(len(source_uids) == last_pair-first_pair+2,
            "MANEUVER_GPS_WINDOW_INCOMPLETE")
    rebased = tuple(replace(segment,
        gps_pair_index=segment.gps_pair_index-first_pair)
        for segment in selected)
    raw = LanePath(rebased, (), source_uids, confidence=lane_path.confidence,
                   valid=True, revision=lane_path.revision,
                   expected_first_gps_pair_index=0)
    local = build_lane_trajectory(raw)
    require(local.valid, "INVALID_LOCAL_MANEUVER_LANE_PATH")
    return local, tuple(range(first, last+1)), pairs


def _prove_prefab_connector(network, segment):
    token = segment.lane_id.prefab_token
    require(type(token) is str and token not in ("", "graph"),
            "MISSING_PREFAB_TOKEN")
    path = tuple(segment.lane_id.connector_path or ())
    require(path and tuple(segment.connector_curve_indices) == path
            and segment.lane_id.connector_index == path[0],
            "PREFAB_CONNECTOR_IDENTITY_MISMATCH")
    pair = (min(segment.start_uid, segment.end_uid),
            max(segment.start_uid, segment.end_uid))
    instances = tuple(instance for instance in
                      network._prefab_pairs.get(pair, ())
                      if instance[0] == token)
    require(len(instances) == 1, "MISSING_OR_AMBIGUOUS_PREFAB_INSTANCE")
    instance = instances[0]
    require(network._prefab_desc.get(token) is not None,
            "MISSING_PREFAB_DESCRIPTION")
    authored = set(network._prefab_connector_options(
        instance, segment.start_uid, segment.end_uid))
    authored.update(network._prefab_parallel_lane_options(
        instance, segment.start_uid, segment.end_uid))
    require(path in authored, "GPS_PREFAB_CONNECTOR_NOT_AUTHORED")
    evidence = network._prefab_lane_topology_evidence(segment, instance)
    require(type(evidence) is dict
            and evidence.get("curve_chain_links_proven") is True,
            "PREFAB_CURVE_CHAIN_NOT_PROVEN")
    descriptor_uids = tuple(evidence.get("descriptor_node_uids") or ())
    inputs = tuple(evidence.get("input_descriptor_node_indices") or ())
    outputs = tuple(evidence.get("output_descriptor_node_indices") or ())
    require(len(inputs) == 1 and len(outputs) == 1,
            "AMBIGUOUS_PREFAB_INPUT_OR_OUTPUT_LANE")
    require(0 <= inputs[0] < len(descriptor_uids)
            and descriptor_uids[inputs[0]] == segment.start_uid,
            "PREFAB_INPUT_DESCRIPTOR_UID_MISMATCH")
    require(0 <= outputs[0] < len(descriptor_uids)
            and descriptor_uids[outputs[0]] == segment.end_uid,
            "PREFAB_OUTPUT_DESCRIPTOR_UID_MISMATCH")
    chain = tuple(evidence.get("curve_chain") or ())
    require(len(chain) == len(path)
            and all(type(row.get("nav_node_index")) is int
                    and row["nav_node_index"] >= 0 for row in chain),
            "MISSING_PREFAB_NAV_NODE_IDENTITY")
    edges = tuple((first, second) for first, second in zip(path, path[1:]))
    return PrefabConnectorProof(
        segment.lane_id, (segment.start_uid, segment.end_uid), token,
        descriptor_uids, int(evidence["origin_node_index"]), inputs[0],
        outputs[0], path,
        tuple(int(row["nav_node_index"]) for row in chain), edges)


def build_maneuver_route_context(network, lane_path, snapshot,
                                 target_segment_index):
    """Build an immutable 5C request from the exact published LanePath."""
    _prove_snapshot(lane_path, snapshot)
    local, source_indices, pair_indices = _extract_window(
        lane_path, target_segment_index)
    proofs = tuple(_prove_prefab_connector(network, segment)
                   for segment in local.segments
                   if segment.lane_id.prefab_token not in (None, "graph"))
    require(proofs or any(segment.lane_type in ("merge", "split")
                          for segment in local.segments),
            "MANEUVER_HAS_NO_PROVEN_PREFAB_OR_MERGE_TOPOLOGY")
    layer = next(iter({segment.elevation_layer
                       for segment in local.segments}))
    identity = Identity(
        str(snapshot["navigation_intent_id"]), lane_path.revision,
        str(snapshot["route_build_id"]),
        str(snapshot["source_game_session_id"]),
        str(snapshot["source_map_key"]),
        str(snapshot["source_dataset_fingerprint"]),
        f"elevation:{layer}",
        tuple(segment.lane_id for segment in local.segments),
        tuple((segment.start_uid, segment.end_uid)
              for segment in local.segments),
    )
    identity.validate()
    full_hash = lane_path_fingerprint(lane_path)
    return ManeuverRouteContext(
        identity, str(snapshot["request_id"]), full_hash, local,
        source_indices, pair_indices, _snapshot_hash(snapshot, full_hash),
        proofs)


def audit_prefab_transition(network, source, required):
    """Explain a real mismatched prefab connector without bridging it."""
    try:
        require(isinstance(source, LaneSegment)
                and isinstance(required, LaneSegment),
                "INVALID_PREFAB_TRANSITION")
        require(source.lane_id.prefab_token
                and source.lane_id.prefab_token == required.lane_id.prefab_token,
                "PREFAB_TOKEN_MISMATCH")
        token = source.lane_id.prefab_token
        pair = (min(source.start_uid, source.end_uid),
                max(source.start_uid, source.end_uid))
        instances = tuple(instance for instance in
                          network._prefab_pairs.get(pair, ())
                          if instance[0] == token)
        require(len(instances) == 1, "MISSING_OR_AMBIGUOUS_PREFAB_INSTANCE")
        instance = instances[0]
        a = network._prefab_lane_topology_evidence(source, instance)
        b = network._prefab_lane_topology_evidence(required, instance)
        require(a and b, "MISSING_PREFAB_TOPOLOGY_EVIDENCE")
        source_path = tuple(a["connector_path"])
        required_path = tuple(b["connector_path"])
        edges = {(row["curve_index"], int(target))
                 for row in a["curve_chain"]
                 for target in row["next_lines"]}
        direct = bool(source_path and required_path
                      and (source_path[-1], required_path[0]) in edges)
        p, q = source.centerline[-1], required.centerline[0]
        gap = math.dist((p.x, p.y, p.z), (q.x, q.y, q.z))
        vertical = abs(p.y-q.y)
        heading = abs(math.degrees(
            (q.heading-p.heading+math.pi) % (2*math.pi)-math.pi))
        same_boundary = bool(set(a["output_descriptor_node_indices"])
                             & set(b["input_descriptor_node_indices"]))
        accepted = (source.lane_id == required.lane_id)
        reason = "" if accepted else (
            "PREFAB_CONNECTOR_CHANGE_REQUIRES_PROVEN_APPROACH_LANE"
            if same_boundary and not direct else
            "PREFAB_CONNECTOR_TRANSITION_NOT_PROVEN")
        return PrefabTransitionAudit(
            accepted, reason, token, source_path, required_path,
            tuple(a["output_descriptor_node_indices"]),
            tuple(b["input_descriptor_node_indices"]), direct,
            gap, vertical, heading)
    except EnvelopeError as error:
        return PrefabTransitionAudit(False, str(error), "", (), (), (), (),
                                     False, math.inf, math.inf, math.inf)
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return PrefabTransitionAudit(False, "MALFORMED_PREFAB_TRANSITION",
                                     "", (), (), (), (), False,
                                     math.inf, math.inf, math.inf)


def prepare_maneuver(network, lane_path, snapshot, target_segment_index,
                     surface_catalog, profile, current_profile,
                     ground_reference, now, confirmed_profile_token=None,
                     profile_confirmation_source="", limits=None,
                     entry_speed_mps=0., entry_tyre_rad=0.):
    """Prepare one geometric plan; never grant traffic/control authority."""
    diagnostics = []
    try:
        context = build_maneuver_route_context(
            network, lane_path, snapshot, target_segment_index)
        diagnostics.append(("route_topology", "accepted", {
            "segments": context.source_segment_indices,
            "gps_pairs": context.source_gps_pair_indices,
            "prefab_connectors": tuple(proof.connector_path
                                       for proof in context.connector_proofs),
        }))
        require(isinstance(surface_catalog, DrivableSurfaceCatalog),
                "MISSING_DRIVABLE_SURFACE_CATALOG")
        surface = surface_catalog.resolve(
            context.local_lane_path, context.identity, context.identity)
        require(not surface.failure_reason, surface.failure_reason)
        diagnostics.append(("surface", "accepted", surface.token))
        binding = bind_envelope_vehicle(
            profile, current_profile, context.identity, context.identity, now,
            confirmed_profile_token, profile_confirmation_source)
        require(isinstance(ground_reference, GroundReferenceEvidence),
                "MISSING_CONFIRMED_GROUND_REFERENCE")
        ground_reference.validate(current_profile, context.identity)
        # The independent axle-pose uncertainty is additive to the confirmed
        # body uncertainty; never count the 5B2 boundary uncertainty here.
        vehicle = replace(binding.vehicle, uncertainty_m=
                          binding.vehicle.uncertainty_m
                          + ground_reference.position_uncertainty_m)
        vehicle.validate()
        limits = limits or PlannerLimits()
        plan = plan_maneuver(
            vehicle, ground_reference.frame, context.local_lane_path, surface,
            context.identity, limits=limits, entry_speed_mps=entry_speed_mps,
            entry_tyre_rad=entry_tyre_rad)
        require(plan.accepted, plan.failure_reason)
        diagnostics.append(("geometric_plan", "accepted", {
            "plan_token": plan.token, "speed_mps": plan.speed_mps,
            "minimum_clearance_m": plan.envelope.minimum_clearance_m,
        }))
        token = digest({
            "schema": 1,
            "snapshot": context.snapshot_fingerprint,
            "full_path": context.full_lane_path_fingerprint,
            "segments": context.source_segment_indices,
            "gps_pair_indices": context.source_gps_pair_indices,
            "local_path": lane_path_fingerprint(context.local_lane_path),
            "surface": surface.token,
            "profile_token": asdict(binding.profile_token),
            "ground": ground_reference.evidence_sha256,
            "plan": plan.token,
        })
        return ManeuverIntegrationResult(
            True, "", context, plan, token, surface.token,
            binding.profile_token, ground_reference.evidence_sha256,
            False, ("TRAFFIC_CLEARANCE_NOT_EVALUATED",
                    "LIVE_ENTRY_STATE_NOT_REVALIDATED"), tuple(diagnostics))
    except EnvelopeError as error:
        diagnostics.append(("rejected", str(error), None))
        return ManeuverIntegrationResult(
            False, str(error), diagnostics=tuple(diagnostics))
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError,
            IndexError):
        diagnostics.append(("rejected", "MALFORMED_MANEUVER_INTEGRATION_INPUT",
                            None))
        return ManeuverIntegrationResult(
            False, "MALFORMED_MANEUVER_INTEGRATION_INPUT",
            diagnostics=tuple(diagnostics))


def validate_integration_result(result, network, lane_path, snapshot,
                                target_segment_index, surface_catalog,
                                current_profile, ground_reference, now,
                                limits=None,
                                entry_speed_mps=0., entry_tyre_rad=0.):
    """Reject stale callbacks before a future traffic/runtime stage sees them."""
    try:
        require(isinstance(result, ManeuverIntegrationResult)
                and result.accepted and result.runtime_authorized is False
                and result.plan is not None and result.context is not None,
                "INVALID_MANEUVER_INTEGRATION_RESULT")
        current = build_maneuver_route_context(
            network, lane_path, snapshot, target_segment_index)
        require(current == result.context,
                "STALE_MANEUVER_ROUTE_CONTEXT")
        require(isinstance(current_profile, VehicleProfile)
                and current_profile.token == result.vehicle_profile_token,
                "STALE_MANEUVER_VEHICLE_PROFILE")
        require(_number(now) and 0 <= now-current_profile.observed_at <= .5,
                "STALE_VEHICLE_OBSERVATION")
        require(current_profile.model is not None,
                current_profile.model_failure or
                "MISSING_CONFIRMED_BODY_PROFILE")
        require(isinstance(ground_reference, GroundReferenceEvidence),
                "MISSING_CONFIRMED_GROUND_REFERENCE")
        ground_reference.validate(current_profile, current.identity)
        require(ground_reference.evidence_sha256
                == result.ground_evidence_sha256,
                "STALE_MANEUVER_GROUND_REFERENCE")
        require(isinstance(surface_catalog, DrivableSurfaceCatalog),
                "MISSING_DRIVABLE_SURFACE_CATALOG")
        surface = surface_catalog.resolve(
            current.local_lane_path, current.identity, current.identity)
        require(not surface.failure_reason, surface.failure_reason)
        require(surface.token == result.surface_token,
                "STALE_MANEUVER_SURFACE")
        vehicle = replace(current_profile.model, uncertainty_m=
                          current_profile.model.uncertainty_m
                          + ground_reference.position_uncertainty_m)
        reason = validate_plan_request(
            result.plan, vehicle, ground_reference.frame,
            current.local_lane_path, surface, current.identity,
            limits or PlannerLimits(), entry_speed_mps, entry_tyre_rad)
        require(not reason, reason)
        expected = digest({
            "schema": 1,
            "snapshot": current.snapshot_fingerprint,
            "full_path": current.full_lane_path_fingerprint,
            "segments": current.source_segment_indices,
            "gps_pair_indices": current.source_gps_pair_indices,
            "local_path": lane_path_fingerprint(current.local_lane_path),
            "surface": surface.token,
            "profile_token": asdict(current_profile.token),
            "ground": ground_reference.evidence_sha256,
            "plan": result.plan.token,
        })
        require(result.token == expected,
                "MANEUVER_INTEGRATION_RESULT_INTEGRITY_MISMATCH")
        return ""
    except EnvelopeError as error:
        return str(error)
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return "MALFORMED_MANEUVER_INTEGRATION_INPUT"
