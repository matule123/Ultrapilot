"""Phase 5D hand-off from an authorised maneuver to the sole Route controller.

The expensive geometry validation and ``Route`` construction run in a bounded
single-worker executor.  The Map tick only selects an already prepared result
and checks its short lease and exact navigation/SDK identity.  This module does
not calculate or write steering.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
import math
import threading
import time

from core.navigation.drivable_surface import digest
from core.navigation.lane_model import wrap_angle
from core.navigation.maneuver_runtime import (
    ManeuverDecision, ManeuverRuntime, ManeuverState, approach_demand,
    decision_rejection_reason,
)
from core.navigation.route import Route
from core.swept_envelope import EnvelopeError, require


REFERENCE_SCHEMA_VERSION = 1
REFERENCE_LEASE_MAX_S = .1
REFERENCE_MAX_POINTS = 10_000
SEAM_POSITION_M = .001
SEAM_HEADING_RAD = math.radians(1.)
SEAM_CURVATURE_M_INV = .002
ENTRY_CTE_M = .05

IDENTITY_FIELDS = (
    "navigation_intent_id", "route_build_id", "revision",
    "source_game_session_id", "source_map_key",
    "source_dataset_fingerprint",
)


def _identity(snapshot):
    return tuple((snapshot or {}).get(key) for key in IDENTITY_FIELDS)


def _lane_value(lane_id):
    value = (lane_id.sort_key() if hasattr(lane_id, "sort_key")
             else tuple(lane_id))
    return (value[0], value[1], value[2], value[3], value[4],
            tuple(value[5]))


def _reference_geometry(points, authorities):
    return {
        "points": [[float(v) for v in point] for point in points],
        "point_authorities": [
            [_lane_value(authority[0]), int(authority[1])]
            for authority in authorities
        ],
    }


def _packet_base(runtime, live, sequence, state):
    result = runtime.request.result
    context = result.context
    snapshot = live.snapshot
    return {
        "schema_version": REFERENCE_SCHEMA_VERSION,
        "sequence": int(sequence),
        "state": state,
        "computed_at": float(live.now_s),
        "valid_until": min(float(live.now_s) + REFERENCE_LEASE_MAX_S,
                           float(live.ground.observed_at)
                           + REFERENCE_LEASE_MAX_S),
        "sdk_frame_us": int(live.ground.sdk_frame_us),
        "binding": runtime.binding,
        "plan_token": result.plan.token,
        "lane_path_fingerprint": context.full_lane_path_fingerprint,
        "request_id": context.request_id,
        "execution_start_s": getattr(runtime.timing, "start_s", None),
        "initial_speed_mps": getattr(runtime.timing, "initial_speed_mps", None),
        **{key: snapshot.get(key) for key in IDENTITY_FIELDS},
    }


def _plan_geometry(runtime):
    plan = runtime.request.result.plan
    local_path = runtime.request.result.context.local_lane_path
    elevation = {segment.lane_id: int(segment.elevation_layer)
                 for segment in local_path.segments}
    points = [(sample.frame.poses[0].x, sample.frame.poses[0].y,
               sample.frame.poses[0].z) for sample in plan.samples]
    authorities = [(sample.source_lane_id,
                    elevation[sample.source_lane_id])
                   for sample in plan.samples]
    return _reference_geometry(points, authorities)


def build_prepared_reference_packet(runtime, sequence, prepared_at=None):
    """Serialize immutable 5B3 geometry before any entry lease is requested."""
    require(isinstance(runtime, ManeuverRuntime)
            and runtime.request is not None
            and runtime.state not in (ManeuverState.NO_MANEUVER,
                                      ManeuverState.GEOMETRY_REJECTED,
                                      ManeuverState.CANCELLED_STALE,
                                      ManeuverState.EMERGENCY_ABORT,
                                      ManeuverState.COMPLETED),
            "NO_PREPARABLE_MANEUVER_GEOMETRY")
    result = runtime.request.result
    context = result.context
    geometry = _plan_geometry(runtime)
    snapshot = runtime.request.snapshot
    return {
        "schema_version": REFERENCE_SCHEMA_VERSION,
        "sequence": int(sequence),
        "state": "LOCAL_PREPARED",
        "prepared_at": float(time.monotonic() if prepared_at is None
                             else prepared_at),
        "binding": runtime.binding,
        "plan_token": result.plan.token,
        "lane_path_fingerprint": context.full_lane_path_fingerprint,
        "request_id": context.request_id,
        **{key: snapshot.get(key) for key in IDENTITY_FIELDS},
        **geometry,
        "geometry_sha256": digest(geometry),
    }


def build_local_reference_packet(runtime, decision, live, traffic, sequence,
                                 prepared_packet):
    """Serialize one consumed EXECUTING decision for the Map worker.

    Calling this is the final worker-side revalidation.  A decision that no
    longer matches the exact traffic, ground frame, profile or route cannot be
    serialized as a local reference.
    """
    reason = decision_rejection_reason(decision, runtime, live, traffic)
    if reason:
        raise EnvelopeError(reason)
    require(isinstance(prepared_packet, dict)
            and prepared_packet.get("state") == "LOCAL_PREPARED"
            and prepared_packet.get("binding") == runtime.binding
            and prepared_packet.get("plan_token")
                == runtime.request.result.plan.token
            and _identity(prepared_packet) == _identity(live.snapshot),
            "STALE_PREPARED_LOCAL_REFERENCE")
    geometry = _plan_geometry(runtime)
    geometry_sha256 = digest(geometry)
    require(prepared_packet.get("geometry_sha256") == geometry_sha256,
            "MUTATED_PREPARED_LOCAL_REFERENCE")
    packet = _packet_base(runtime, live, sequence, "LOCAL_EXECUTING")
    packet["geometry_sha256"] = geometry_sha256
    packet["prepared_sequence"] = int(prepared_packet["sequence"])
    packet["traffic_snapshot_id"] = traffic.snapshot_id
    packet["traffic_sequence"] = int(traffic.sequence)
    packet["traffic_sha256"] = digest(asdict(traffic))
    packet["runtime_decision_binding"] = decision.binding
    packet["runtime_decision_computed_at"] = decision.computed_at_s
    packet["runtime_decision_valid_until"] = decision.valid_until_s
    return packet


def build_return_reference_packet(runtime, decision, live, sequence,
                                  prepared_packet):
    """Build a short-lived, identity-bound request to restore the LanePath."""
    require(runtime.state == ManeuverState.COMPLETED
            and isinstance(decision, ManeuverDecision)
            and decision.state == ManeuverState.COMPLETED
            and not decision.runtime_authorized,
            "MANEUVER_EXIT_NOT_REVALIDATED")
    # COMPLETED was produced only after the runtime revalidated current ground,
    # traffic and exit alignment.  Recheck the live non-traffic binding here;
    # a changed frame between completion and publication must fail closed.
    runtime._validate_live(live)
    packet = _packet_base(runtime, live, sequence, "RETURN_TO_GLOBAL")
    require(isinstance(prepared_packet, dict)
            and prepared_packet.get("binding") == runtime.binding
            and prepared_packet.get("plan_token")
                == runtime.request.result.plan.token,
            "STALE_PREPARED_LOCAL_REFERENCE")
    packet["geometry_sha256"] = prepared_packet.get("geometry_sha256")
    packet["prepared_sequence"] = int(prepared_packet["sequence"])
    packet["runtime_completion_reason"] = decision.failure_reason
    return packet


def build_approach_control_packet(runtime, decision, live, traffic, sequence,
                                  distance_to_stop_m, acceleration_mps2, dt_s):
    """Publish a bounded longitudinal request while retaining global steering.

    The distance must be measured by the worker to the already confirmed stop
    point.  This function neither invents that point nor searches geometry.
    """
    require(isinstance(runtime, ManeuverRuntime)
            and isinstance(decision, ManeuverDecision)
            and decision.state == runtime.state
            and runtime.state in (ManeuverState.WAITING_FOR_TRAFFIC,
                                  ManeuverState.READY_FOR_ENTRY)
            and decision.computed_at_s == live.now_s,
            "STALE_MANEUVER_APPROACH_DECISION")
    runtime._validate_live(live)
    require(traffic is not None
            and digest(asdict(traffic)) == runtime._traffic_digest,
            "STALE_MANEUVER_APPROACH_TRAFFIC")
    blocked = runtime.state == ManeuverState.WAITING_FOR_TRAFFIC
    demand = approach_demand(
        live.speed_mps, acceleration_mps2, distance_to_stop_m, dt_s, blocked,
        entry_speed_mps=runtime.request.result.plan.speed_mps)
    require(demand.accepted, demand.failure_reason)
    packet = _packet_base(runtime, live, sequence, runtime.state.value)
    packet.update({
        "release_throttle": bool(demand.release_throttle),
        "target_speed_mps": float(demand.target_speed_mps),
        "acceleration_mps2": float(demand.acceleration_mps2),
        # The existing brake ramp consumes this bounded request.  The 0.70
        # scale is its existing controlled-stop demand; approach_demand ramps
        # the requested physical deceleration at 0.5 m/s^3 before this mapping.
        "brake_request": float(min(.70, max(
            0., -.70 * demand.acceleration_mps2))),
        "required_stopping_distance_m": float(
            demand.stopping_distance_m),
        "distance_to_stop_m": float(distance_to_stop_m),
        "traffic_snapshot_id": traffic.snapshot_id,
        "traffic_sequence": int(traffic.sequence),
        "traffic_sha256": digest(asdict(traffic)),
    })
    return packet


def approach_packet_rejection_reason(packet, snapshot, now, sdk_frame_us):
    if not isinstance(packet, dict) or packet.get("state") not in (
            ManeuverState.WAITING_FOR_TRAFFIC.value,
            ManeuverState.READY_FOR_ENTRY.value):
        return ""
    reason = reference_packet_rejection_reason(
        packet, snapshot, now, sdk_frame_us,
        expected_state=packet.get("state"))
    if reason:
        return reason
    try:
        release = packet.get("release_throttle")
        brake = float(packet.get("brake_request"))
        acceleration = float(packet.get("acceleration_mps2"))
        target = float(packet.get("target_speed_mps"))
        distance = float(packet.get("distance_to_stop_m"))
        required = float(packet.get("required_stopping_distance_m"))
        if (type(release) is not bool
                or not all(math.isfinite(value) for value in (
                    brake, acceleration, target, distance, required))
                or not 0. <= brake <= .70 or target < 0. or distance < 0.
                or required < 0. or not -1. <= acceleration <= 1.):
            return "MALFORMED_MANEUVER_APPROACH_DEMAND"
        if packet["state"] == ManeuverState.WAITING_FOR_TRAFFIC.value:
            if not release or target != 0.:
                return "UNSAFE_MANEUVER_WAITING_DEMAND"
        elif target <= 0.:
            return "UNNECESSARY_MANEUVER_READY_STOP"
    except (TypeError, ValueError, OverflowError, KeyError, AttributeError):
        return "MALFORMED_MANEUVER_APPROACH_DEMAND"
    return ""


def _normalise_authority(value):
    require(isinstance(value, (list, tuple)) and len(value) == 2,
            "MALFORMED_LOCAL_REFERENCE_AUTHORITY")
    lane, layer = value
    require(isinstance(lane, (list, tuple)) and len(lane) == 6,
            "MALFORMED_LOCAL_REFERENCE_LANE_ID")
    connector = lane[5]
    require(isinstance(connector, (list, tuple)),
            "MALFORMED_LOCAL_REFERENCE_LANE_ID")
    normalised = (int(lane[0]), int(lane[1]), int(lane[2]), str(lane[3]),
                  int(lane[4]), tuple(int(v) for v in connector))
    return normalised, int(layer)


def _xz(point):
    return float(point[0]), float(point[2])


def _heading(a, b):
    dx, dz = b[0] - a[0], b[1] - a[1]
    require(math.hypot(dx, dz) > 1e-6, "DEGENERATE_REFERENCE_SEAM")
    return math.atan2(-dx, -dz)


def _curvature(a, b, c):
    ab, bc, ca = math.dist(a, b), math.dist(b, c), math.dist(c, a)
    if min(ab, bc, ca) <= 1e-6:
        return 0.
    cross = ((b[0] - a[0]) * (c[1] - a[1])
             - (b[1] - a[1]) * (c[0] - a[0]))
    return 2. * cross / (ab * bc * ca)


def _find_exact_point(points, target):
    distances = [math.dist(_xz(point), target) for point in points]
    index = min(range(len(distances)), key=distances.__getitem__)
    require(distances[index] <= SEAM_POSITION_M,
            "LOCAL_REFERENCE_ENDPOINT_NOT_ON_GLOBAL_LANEPATH")
    return index, distances[index]


def _seam(local, global_points, *, entry):
    target = _xz(local[0] if entry else local[-1])
    index, position = _find_exact_point(global_points, target)
    require((index < len(global_points) - 1 if entry else index > 0),
            "GLOBAL_LANEPATH_SEAM_TANGENT_UNAVAILABLE")
    if entry:
        local_heading = _heading(_xz(local[0]), _xz(local[1]))
        global_heading = _heading(_xz(global_points[index]),
                                  _xz(global_points[index + 1]))
        local_curvature = _curvature(*map(_xz, local[:3]))
        gi = max(0, min(index, len(global_points) - 3))
    else:
        local_heading = _heading(_xz(local[-2]), _xz(local[-1]))
        global_heading = _heading(_xz(global_points[index - 1]),
                                  _xz(global_points[index]))
        local_curvature = _curvature(*map(_xz, local[-3:]))
        gi = max(0, min(index - 2, len(global_points) - 3))
    global_curvature = _curvature(*map(_xz, global_points[gi:gi + 3]))
    heading_delta = abs(wrap_angle(local_heading - global_heading))
    curvature_delta = abs(local_curvature - global_curvature)
    require(heading_delta <= SEAM_HEADING_RAD,
            "LOCAL_REFERENCE_HEADING_SEAM_DISCONTINUITY")
    require(curvature_delta <= SEAM_CURVATURE_M_INV,
            "LOCAL_REFERENCE_CURVATURE_SEAM_DISCONTINUITY")
    return {
        "global_index": index,
        "position_delta_m": position,
        "heading_delta_rad": heading_delta,
        "curvature_delta_m_inv": curvature_delta,
        "position_xz": target,
        "heading_rad": local_heading,
    }


@dataclass(frozen=True)
class PreparedReference:
    sequence: int
    packet: dict
    route: Route
    entry_seam: dict
    exit_seam: dict


@dataclass(frozen=True)
class ReferenceSelection:
    route: Route | None
    mode: str
    authority_valid: bool
    failure_reason: str
    packet: dict | None = None
    seam: dict | None = None


def _prepare(packet, snapshot):
    require(isinstance(packet, dict)
            and packet.get("schema_version") == REFERENCE_SCHEMA_VERSION,
            "UNKNOWN_LOCAL_REFERENCE_SCHEMA")
    require(packet.get("state") == "LOCAL_PREPARED",
            "LOCAL_REFERENCE_IS_NOT_PREPARED")
    require(_identity(packet) == _identity(snapshot),
            "STALE_LOCAL_REFERENCE_ROUTE_IDENTITY")
    require(packet.get("lane_path_fingerprint")
            and packet.get("lane_path_fingerprint")
                == snapshot.get("lane_path_fingerprint"),
            "STALE_LOCAL_REFERENCE_LANEPATH")
    points = packet.get("points")
    authorities = packet.get("point_authorities")
    require(isinstance(points, (list, tuple))
            and 3 <= len(points) <= REFERENCE_MAX_POINTS,
            "INVALID_LOCAL_REFERENCE_POINT_COUNT")
    require(isinstance(authorities, (list, tuple))
            and len(authorities) == len(points),
            "INVALID_LOCAL_REFERENCE_AUTHORITIES")
    clean_points = []
    for point in points:
        require(isinstance(point, (list, tuple)) and len(point) == 3,
                "MALFORMED_LOCAL_REFERENCE_POINT")
        clean = tuple(float(value) for value in point)
        require(all(math.isfinite(value) for value in clean),
                "NONFINITE_LOCAL_REFERENCE_POINT")
        clean_points.append(clean)
    clean_authorities = [_normalise_authority(value)
                         for value in authorities]
    geometry = _reference_geometry(clean_points, clean_authorities)
    require(digest(geometry) == packet.get("geometry_sha256"),
            "MUTATED_LOCAL_REFERENCE_GEOMETRY")
    global_points = (snapshot or {}).get("points") or ()
    require(isinstance(global_points, (list, tuple)) and len(global_points) >= 3,
            "GLOBAL_LANEPATH_GEOMETRY_UNAVAILABLE")
    entry = _seam(clean_points, global_points, entry=True)
    exit_seam = _seam(clean_points, global_points, entry=False)
    route = Route(clean_points, name="authorized-local-maneuver",
                  point_authorities=clean_authorities)
    require(len(route) == len(clean_points), "LOCAL_REFERENCE_ROUTE_BUILD_FAILED")
    return PreparedReference(int(packet["sequence"]), dict(packet), route,
                             entry, exit_seam)


def reference_packet_rejection_reason(packet, snapshot, now, sdk_frame_us,
                                      *, expected_state=None):
    try:
        require(isinstance(packet, dict)
                and packet.get("schema_version") == REFERENCE_SCHEMA_VERSION,
                "MISSING_LOCAL_REFERENCE_PACKET")
        if expected_state is not None:
            require(packet.get("state") == expected_state,
                    "UNEXPECTED_LOCAL_REFERENCE_STATE")
        require(_identity(packet) == _identity(snapshot),
                "STALE_LOCAL_REFERENCE_ROUTE_IDENTITY")
        require(packet.get("lane_path_fingerprint")
                == snapshot.get("lane_path_fingerprint"),
                "STALE_LOCAL_REFERENCE_LANEPATH")
        computed = float(packet.get("computed_at"))
        valid_until = float(packet.get("valid_until"))
        now = float(now)
        require(all(math.isfinite(value) for value in
                    (computed, valid_until, now))
                and computed <= now < valid_until
                and valid_until - computed <= REFERENCE_LEASE_MAX_S + 1e-12,
                "EXPIRED_LOCAL_REFERENCE_PACKET")
        require(int(packet.get("sdk_frame_us")) == int(sdk_frame_us)
                and int(sdk_frame_us) > 0,
                "STALE_LOCAL_REFERENCE_SDK_FRAME")
        require(type(packet.get("sequence")) is int
                and packet["sequence"] > 0,
                "INVALID_LOCAL_REFERENCE_SEQUENCE")
        require(isinstance(packet.get("binding"), str)
                and bool(packet["binding"])
                and isinstance(packet.get("plan_token"), str)
                and bool(packet["plan_token"]),
                "MISSING_LOCAL_REFERENCE_BINDING")
        return ""
    except EnvelopeError as error:
        return str(error)
    except (TypeError, ValueError, OverflowError, KeyError, AttributeError):
        return "MALFORMED_LOCAL_REFERENCE_PACKET"


class ManeuverReferencePublisher:
    """Publish one coherent worker result outside the control tick.

    Runtime revalidation, traffic geometry and packet construction happen on
    the caller's bounded worker.  The only shared-state mutation is one
    ``update_batch`` call, so Map and Autopilot cannot observe a new reference
    with an approach request left over from an older decision.
    """
    def __init__(self, shared_state):
        if getattr(shared_state, "get", lambda *_: False)("maneuver_production_guard_required", False):
            from core.navigation.evidence_worker import ProductionPublicationSink
            self._state = ProductionPublicationSink(shared_state)
        else:
            self._state = shared_state
        self._lock = threading.RLock()
        self._sequence = 0
        self._prepared = None

    def _next_sequence(self):
        self._sequence += 1
        return self._sequence

    def bind_production_evidence(self, bundle):
        """Bind a worker-verified 5E bundle before publishing any 5D authority."""
        from core.navigation.evidence_worker import ProductionPublicationSink
        require(isinstance(self._state, ProductionPublicationSink),
                "PRODUCTION_PUBLICATION_GUARD_NOT_CONFIGURED")
        with self._lock:
            self._state.bind(bundle)

    def _publish(self, reference, approach, runtime_state, reason=""):
        status = {
            "schema_version": REFERENCE_SCHEMA_VERSION,
            "state": runtime_state.value if isinstance(
                runtime_state, ManeuverState) else str(runtime_state),
            "failure_reason": str(reason or ""),
            "sequence": self._sequence,
        }
        self._state.update_batch({
            "maneuver_reference_packet": dict(reference or {}),
            "maneuver_approach_packet": dict(approach or {}),
            "maneuver_runtime_status": status,
        })
        return dict(reference or {}), dict(approach or {})

    def publish_prepared(self, runtime, prepared_at=None):
        """Serialize and publish immutable geometry before entry is possible."""
        with self._lock:
            try:
                prepared = build_prepared_reference_packet(
                    runtime, self._next_sequence(), prepared_at)
                self._prepared = prepared
                self._publish(prepared, {}, "LOCAL_PREPARED")
                return dict(prepared)
            except (EnvelopeError, AttributeError, TypeError, ValueError,
                    OverflowError, KeyError, IndexError) as error:
                self.revoke(str(error) or
                            "LOCAL_REFERENCE_PREPARATION_FAILED")
                return {}

    def publish_decision(self, runtime, decision, live, traffic, *,
                         distance_to_stop_m=None, acceleration_mps2=0.,
                         dt_s=.02):
        """Revalidate and atomically publish a fresh state-machine decision."""
        with self._lock:
            try:
                require(self._prepared is not None,
                        "LOCAL_REFERENCE_GEOMETRY_NOT_PREPARED")
                sequence = self._next_sequence()
                if runtime.state in (ManeuverState.WAITING_FOR_TRAFFIC,
                                      ManeuverState.READY_FOR_ENTRY):
                    require(distance_to_stop_m is not None,
                            "MANEUVER_STOP_DISTANCE_UNAVAILABLE")
                    approach = build_approach_control_packet(
                        runtime, decision, live, traffic, sequence,
                        distance_to_stop_m, acceleration_mps2, dt_s)
                    return self._publish(
                        self._prepared, approach, runtime.state,
                        decision.failure_reason)
                if runtime.state == ManeuverState.EXECUTING:
                    reference = build_local_reference_packet(
                        runtime, decision, live, traffic, sequence,
                        self._prepared)
                    return self._publish(
                        reference, {}, runtime.state, decision.failure_reason)
                if runtime.state == ManeuverState.COMPLETED:
                    reference = build_return_reference_packet(
                        runtime, decision, live, sequence, self._prepared)
                    result = self._publish(
                        reference, {}, runtime.state, decision.failure_reason)
                    self._prepared = None
                    return result
                return self.revoke(
                    decision.failure_reason or runtime.state.value,
                    runtime.state)
            except (EnvelopeError, AttributeError, TypeError, ValueError,
                    OverflowError, KeyError, IndexError) as error:
                return self.revoke(
                    str(error) or "LOCAL_REFERENCE_PUBLICATION_FAILED",
                    getattr(runtime, "state", ManeuverState.CANCELLED_STALE))

    def revoke(self, reason, runtime_state=ManeuverState.CANCELLED_STALE):
        """Remove both authority channels in the same shared-state update."""
        with self._lock:
            self._prepared = None
            self._next_sequence()
            return self._publish({}, {}, runtime_state, reason)


class ManeuverReferenceMux:
    """Atomically select global/local/global geometry before one controller.

    ``offer`` never validates polygons or runs a planner.  New geometry is
    prepared on one bounded worker.  ``select`` is constant-time apart from a
    small endpoint calculation and never invokes ``Route.steering``.
    """
    def __init__(self):
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="maneuver-reference")
        self._lock = threading.Lock()
        self._future = None
        self._offered_key = None
        self._prepared = None
        self._prepare_failure = ""
        self._active_token = None
        self._last_sequence = 0
        self._faulted = False

    def close(self):
        self._executor.shutdown(wait=False, cancel_futures=True)

    def reject_production_evidence(self, reason):
        """Latch loss during execution; never jump back to the global curve."""
        if self._active_token is not None:
            self._faulted = True
        return ReferenceSelection(None, "revoked", False, reason)

    def offer(self, packet, snapshot):
        """Queue only the newest bounded local reference for worker validation."""
        prepared_offer = (isinstance(packet, dict)
                          and packet.get("state") == "LOCAL_PREPARED")
        key = ((packet.get("sequence"), packet.get("geometry_sha256"),
                _identity(packet)) if prepared_offer else None)
        with self._lock:
            future = self._future
            if future is not None and future.done():
                try:
                    prepared = future.result()
                    if self._offered_key == (prepared.sequence,
                                             prepared.packet.get("geometry_sha256"),
                                             _identity(prepared.packet)):
                        self._prepared = prepared
                        self._prepare_failure = ""
                except (EnvelopeError, TypeError, ValueError, OverflowError,
                        KeyError, IndexError) as error:
                    self._prepare_failure = str(error) or "LOCAL_REFERENCE_PREPARATION_FAILED"
                self._future = None
            # Harvesting is independent of the currently published state. The
            # worker may finish between the last LOCAL_PREPARED tick and the
            # first LOCAL_EXECUTING tick; that completion must remain usable.
            if not prepared_offer:
                return
            if key == self._offered_key:
                return
            # One pending build is the hard resource bound. A newer packet is
            # offered again after the current build completes; no queue grows.
            if self._future is not None:
                return
            self._offered_key = key
            self._future = self._executor.submit(
                _prepare, dict(packet), dict(snapshot or {}))

    @staticmethod
    def _at_seam(pos, heading, seam):
        return (math.dist((float(pos[0]), float(pos[1])),
                          tuple(seam["position_xz"])) <= ENTRY_CTE_M
                and abs(wrap_angle(float(heading)
                                   - float(seam["heading_rad"])))
                    <= SEAM_HEADING_RAD)

    def select(self, global_route, snapshot, packet, pos, heading, now,
               sdk_frame_us, enabled):
        """Return one reference. Invalid active hand-offs revoke authority."""
        self.offer(packet, snapshot)
        state = packet.get("state") if isinstance(packet, dict) else None
        if self._active_token is None and state == "LOCAL_PREPARED":
            return ReferenceSelection(global_route, "global_lane", True, "")
        if self._active_token is None and state != "LOCAL_EXECUTING":
            return ReferenceSelection(global_route, "global_lane", True, "")
        if not enabled:
            if self._active_token is not None:
                self._faulted = True
                return ReferenceSelection(None, "revoked", False,
                                          "MANUAL_AUTOPILOT_DISABLED")
            return ReferenceSelection(global_route, "global_lane", True, "")
        expected = ("RETURN_TO_GLOBAL" if state == "RETURN_TO_GLOBAL"
                    else "LOCAL_EXECUTING")
        reason = reference_packet_rejection_reason(
            packet, snapshot, now, sdk_frame_us, expected_state=expected)
        if reason:
            if self._active_token is not None:
                self._faulted = True
                return ReferenceSelection(None, "revoked", False, reason)
            return ReferenceSelection(global_route, "global_lane", True, "")
        if self._faulted:
            return ReferenceSelection(None, "revoked", False,
                                      "LOCAL_REFERENCE_AUTHORITY_LATCHED_OFF")
        if int(packet["sequence"]) <= self._last_sequence:
            return ReferenceSelection(None, "revoked", False,
                                      "STALE_LOCAL_REFERENCE_SEQUENCE")
        if state == "RETURN_TO_GLOBAL":
            prepared = self._prepared
            if (prepared is None or self._active_token != packet.get("plan_token")
                    or prepared.packet.get("binding") != packet.get("binding")
                    or _identity(prepared.packet) != _identity(packet)
                    or prepared.packet.get("lane_path_fingerprint")
                        != packet.get("lane_path_fingerprint")):
                self._faulted = True
                return ReferenceSelection(None, "revoked", False,
                                          "STALE_LOCAL_REFERENCE_RETURN_BINDING")
            if not self._at_seam(pos, heading, prepared.exit_seam):
                self._faulted = True
                return ReferenceSelection(None, "revoked", False,
                                          "VEHICLE_NOT_AT_BUMPLESS_EXIT_SEAM")
            self._last_sequence = int(packet["sequence"])
            self._active_token = None
            self._prepared = None
            self._offered_key = None
            return ReferenceSelection(global_route, "global_lane", True, "",
                                      dict(packet), prepared.exit_seam)
        prepared = self._prepared
        if (prepared is None
                or prepared.sequence != int(packet.get("prepared_sequence", 0))
                or prepared.packet.get("geometry_sha256")
                    != packet.get("geometry_sha256")
                or prepared.packet.get("binding") != packet.get("binding")
                or prepared.packet.get("plan_token") != packet.get("plan_token")
                or _identity(prepared.packet) != _identity(packet)
                or prepared.packet.get("lane_path_fingerprint")
                    != packet.get("lane_path_fingerprint")):
            reason = self._prepare_failure or "LOCAL_REFERENCE_PREPARATION_PENDING"
            if self._active_token is not None:
                self._faulted = True
                return ReferenceSelection(None, "revoked", False, reason)
            return ReferenceSelection(global_route, "global_lane", True, reason)
        if self._active_token is None:
            if not self._at_seam(pos, heading, prepared.entry_seam):
                return ReferenceSelection(global_route, "global_lane", True,
                                          "VEHICLE_NOT_AT_BUMPLESS_ENTRY_SEAM")
            self._active_token = packet["plan_token"]
        elif self._active_token != packet.get("plan_token"):
            self._faulted = True
            return ReferenceSelection(None, "revoked", False,
                                      "LOCAL_REFERENCE_PLAN_CHANGED_DURING_EXECUTION")
        self._last_sequence = int(packet["sequence"])
        return ReferenceSelection(prepared.route, "local_maneuver", True, "",
                                  dict(packet), prepared.entry_seam)

    def preparation_payload(self):
        with self._lock:
            prepared = self._prepared
            pending = self._future is not None
            return {
                "schema_version": REFERENCE_SCHEMA_VERSION,
                "ready": prepared is not None,
                "pending": pending,
                "sequence": prepared.sequence if prepared is not None else 0,
                "geometry_sha256": (prepared.packet.get("geometry_sha256", "")
                                    if prepared is not None else ""),
                "failure_reason": self._prepare_failure,
            }


def active_reference_payload(selection, snapshot, sdk_frame_us, now=None):
    now = time.monotonic() if now is None else float(now)
    packet = selection.packet or {}
    return {
        "schema_version": REFERENCE_SCHEMA_VERSION,
        "mode": selection.mode,
        "authority_valid": bool(selection.authority_valid),
        "failure_reason": str(selection.failure_reason or ""),
        "sequence": packet.get("sequence", 0),
        "plan_token": packet.get("plan_token", ""),
        "binding": packet.get("binding", ""),
        "production_evidence_receipt": packet.get("production_evidence_receipt", ""),
        "execution_start_s": packet.get("execution_start_s"),
        "initial_speed_mps": packet.get("initial_speed_mps"),
        "computed_at": now,
        "valid_until": packet.get("valid_until") if selection.packet else None,
        "sdk_frame_us": int(sdk_frame_us or 0),
        **{key: (snapshot or {}).get(key) for key in IDENTITY_FIELDS},
    }
