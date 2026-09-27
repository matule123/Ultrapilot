"""Bounded, offline hybrid trailer references for road placement or surveyed lanes.

This is a reference generator, never a steering/traffic authority. Axle-path
clearance is explicitly NOT body clearance. Optional 5A validation needs the
real body model and surface. A derived width is an uncertain placement budget,
never a physical clearance claim. Sharp turns use the existing 5B3 planner.
Nothing in this module infers road edges from lane widths or wheels.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
import math
import time

import numpy as np

from core.navigation.drivable_surface import (
    DrivableSurfaceSnapshot, digest, evaluate_on_confirmed_surface,
    identity_fingerprint, lane_path_fingerprint, validate_path_identity,
    SUPPORTED_METHODS, FORBIDDEN_SOURCE_TERMS,
)
from core.navigation.lane_model import wrap_angle
from core.navigation.lane_model import LanePoint
from core.navigation.lane_trajectory import _resample_polyline, _with_kinematics
from core.navigation.maneuver_reference import _seam
from core.navigation.route import Route
from core.swept_envelope import EnvelopeError, Frame, Pose, clearance, require


@dataclass(frozen=True)
class TrailerGeometry:
    """One calibrated fixed-axle semitrailer; dimensions are not wheel track.

    SDK's average tandem axle and chassis placement alone cannot instantiate
    this proof. configuration includes the complete active combination.
    """
    wheelbase_m: float
    hitch_ahead_m: float
    hitch_to_axle_m: float
    configuration: str
    source: str
    confirmed: bool
    uncertainty_m: float = .15

    def validate(self):
        require(self.confirmed is True and bool(self.source.strip())
                and len(self.configuration) == 64
                and all(c in '0123456789abcdef' for c in self.configuration),
                'MISSING_CONFIRMED_TRAILER_KINEMATICS')
        require(all(math.isfinite(v) for v in (
            self.wheelbase_m, self.hitch_ahead_m, self.hitch_to_axle_m,
            self.uncertainty_m)) and 2 <= self.wheelbase_m <= 8
            and abs(self.hitch_ahead_m) <= 3
            and 3 <= self.hitch_to_axle_m <= 15
            and .01 <= self.uncertainty_m <= .5,
            'UNSUPPORTED_TRAILER_KINEMATICS')


@dataclass(frozen=True)
class GuidancePlan:
    accepted: bool
    failure_reason: str
    identity: object
    path_fingerprint: str = ''
    configuration: str = ''
    token: str = ''
    points: tuple = ()
    predicted_poses: tuple = ()
    baseline_trailer_max_cte_m: float = 0.
    trailer_max_cte_m: float = 0.
    tractor_max_offset_m: float = 0.
    minimum_axle_reserve_m: float = 0.
    body_envelope: object = None
    runtime_authorized: bool = False
    corridor_token: str = ''
    design_speed_mps: float = 0.
    corridor_basis: str = ''
    speed_reduction_distance_m: float = 0.
    handoff_before_m: float = 0.


@dataclass(frozen=True)
class UsableLaneCorridor:
    """Surveyed usable SAME-LANE strip, not all asphalt at an intersection.

    Surface provenance proves the physical edges. This additional survey
    attestation proves that the region contains no opposing/adjacent lane.
    Both proofs are required; a broad Phase 5 maneuver zone is insufficient.
    """
    boundary: DrivableSurfaceSnapshot
    lanes: tuple
    source: str
    evidence_sha256: str
    same_lane_only: bool

    def validate(self, identity):
        require(self.same_lane_only is True and self.lanes == identity.lanes
                and bool(self.source.strip()) and len(self.evidence_sha256) == 64
                and all(c in '0123456789abcdef' for c in self.evidence_sha256),
                'MISSING_CONFIRMED_SAME_LANE_USE_CORRIDOR')


@dataclass(frozen=True)
class DerivedLaneCorridor:
    """Uncertain lane-placement budget, never a physical road boundary."""
    identity_fingerprint: str
    path_fingerprint: str
    lanes: tuple
    width_m: float
    width_source: str
    uncertainty_m: float

    def validate(self, path, identity):
        require(self.identity_fingerprint == identity_fingerprint(identity)
                and self.path_fingerprint == lane_path_fingerprint(path)
                and self.lanes == identity.lanes,
                'STALE_DERIVED_LANE_CORRIDOR')
        require(self.width_source == 'derived'
                and math.isfinite(self.width_m) and self.width_m >= 4.5
                and math.isfinite(self.uncertainty_m)
                and .5 <= self.uncertainty_m <= 1.5
                and all(s.width_source == 'derived'
                        and s.width_m == self.width_m for s in path.segments),
                'UNSUPPORTED_DERIVED_LANE_WIDTH')


def derived_lane_corridor(path, identity, *, uncertainty_m=.65):
    """Bind one conservative placement budget to an exact LanePath."""
    require(path.valid and path.segments and
            all(s.lane_type == 'road' and s.lane_id.prefab_token is None
                for s in path.segments),
            'SENSITIVE_TURN_REQUIRES_PHASE5_PLANNER')
    result = DerivedLaneCorridor(identity_fingerprint(identity),
        lane_path_fingerprint(path), identity.lanes, path.segments[0].width_m,
        'derived', uncertainty_m)
    result.validate(path, identity)
    return result


def guidance_source_status(path):
    """Cheap diagnostic only. A dataset/derived lane width proves no boundary."""
    if path is None or not path.valid:
        return 'MISSING_VALID_REVISION_BOUND_LANEPATH'
    return 'MISSING_CONFIRMED_USABLE_LANE_CORRIDOR'


def _reference_token(path_hash, configuration, corridor_token, identity, points):
    return digest((path_hash, configuration, corridor_token,
                   identity_fingerprint(identity), [asdict(p) for p in points]))


def _project(points, positions):
    """Independent signed axle error against the original directed polyline."""
    a = points[:-1]
    d = np.diff(points, axis=0)
    q = np.sum(d*d, axis=1)
    result = []
    for pos in positions:
        u = np.clip(np.sum((pos-a)*d, axis=1)/q, 0., 1.)
        residual = pos-a-u[:, None]*d
        j = int(np.argmin(np.sum(residual*residual, axis=1)))
        result.append((residual[j, 0]*d[j, 1]-residual[j, 1]*d[j, 0])
                      /math.sqrt(q[j]))
    return np.asarray(result)


def _predict(points, model, trailer_heading):
    """Spatial RK4 for an off-axle hitch; independent of steering gain/lag."""
    xy = np.array([(p.x, p.z) for p in points])
    ss = np.array([p.s for p in points])
    heads = np.unwrap([p.heading for p in points])
    trailer = float(trailer_heading)
    poses = []
    for i, (pos, h) in enumerate(zip(xy, heads)):
        if i:
            ds = ss[i]-ss[i-1]
            yaw = (h-heads[i-1])/ds

            def rate(theta, fraction):
                tractor = heads[i-1]+fraction*(h-heads[i-1])
                hx = -math.sin(tractor)-model.hitch_ahead_m*yaw*math.cos(tractor)
                hz = -math.cos(tractor)+model.hitch_ahead_m*yaw*math.sin(tractor)
                return (-hx*math.cos(theta)+hz*math.sin(theta))/model.hitch_to_axle_m

            k1 = rate(trailer, 0.)
            k2 = rate(trailer+ds*k1/2, .5)
            k3 = rate(trailer+ds*k2/2, .5)
            k4 = rate(trailer+ds*k3, 1.)
            trailer += ds*(k1+2*k2+2*k3+k4)/6
        hitch = pos-model.hitch_ahead_m*np.array((math.sin(h), math.cos(h)))
        axle = hitch+model.hitch_to_axle_m*np.array((math.sin(trailer), math.cos(trailer)))
        poses.append((Pose(float(pos[0]), points[i].y, float(pos[1]), float(h)),
                      Pose(float(axle[0]), points[i].y, float(axle[1]), float(trailer))))
    return tuple(poses)


def _reserve(poses, surface, pad, spacing, deadline, clock):
    # Conservatively cover unsampled axle travel; this is never a body sweep.
    margin = pad+spacing
    minimum = math.inf
    for row in poses:
        require(clock() < deadline, 'GUIDANCE_DEADLINE_EXPIRED')
        for p in row:
            box = ((p.x-margin, p.z-margin), (p.x+margin, p.z-margin),
                   (p.x+margin, p.z+margin), (p.x-margin, p.z+margin))
            minimum = min(minimum, clearance(box, surface))
            if minimum <= 0:
                return 0.
    return minimum


def plan_trailer_guidance(path, identity, geometry, corridor, *,
                          initial_trailer_heading, speed_mps,
                          vehicle=None, actuator_response_s=.60,
                          actuator_delay_s=.15, deadline=None,
                          clock=time.monotonic):
    """At most twelve smooth, physically motivated references plus baseline.

    The compensation scale follows steady-state trailer offtracking L²*k/2;
    actual acceptance uses articulated prediction and the observed corridor.
    No random lateral offsets, neighbour lane or endpoint substitution.
    """
    first_bend = 0.
    try:
        deadline = clock()+10. if deadline is None else deadline
        require(math.isfinite(deadline) and clock() < deadline, 'GUIDANCE_DEADLINE_EXPIRED')
        require(30 <= path.distance_m <= 350 and 3 <= len(path.points) <= 2000,
                'GUIDANCE_HORIZON_OUTSIDE_BUDGET')
        validate_path_identity(path, identity, identity)
        require(geometry is not None, 'MISSING_CONFIRMED_TRAILER_KINEMATICS')
        geometry.validate()
        derived = isinstance(corridor, DerivedLaneCorridor)
        if derived:
            corridor.validate(path, identity)
            lane_use_token = digest(asdict(corridor))
            derived_width = corridor.width_m
            derived_uncertainty = corridor.uncertainty_m
            corridor = None
        else:
            require(isinstance(corridor, UsableLaneCorridor),
                    'MISSING_CONFIRMED_USABLE_LANE_CORRIDOR')
            corridor.validate(identity)
            lane_use_token = digest((tuple(lane.sort_key() for lane in corridor.lanes),
                                     corridor.source, corridor.evidence_sha256))
            corridor = corridor.boundary
            require(isinstance(corridor, DrivableSurfaceSnapshot)
                    and corridor.surface is not None and not corridor.failure_reason,
                    'MISSING_CONFIRMED_USABLE_LANE_CORRIDOR')
            require(corridor.identity_fingerprint == identity_fingerprint(identity)
                    and corridor.lane_path_fingerprint == lane_path_fingerprint(path)
                    and corridor.surface.identity == identity,
                    'STALE_GUIDANCE_CORRIDOR')
            corridor.surface.validate()
            require(corridor.evidence_method in SUPPORTED_METHODS
                    and not any(term in corridor.source.casefold() for term in FORBIDDEN_SOURCE_TERMS)
                    and math.isfinite(corridor.boundary_uncertainty_m)
                    and .001 <= corridor.boundary_uncertainty_m <= 2.,
                    'UNPROVEN_GUIDANCE_CORRIDOR_SOURCE')
            require(sum(len(r) for r in (corridor.surface.exterior,)+corridor.surface.holes) <= 512,
                    'GUIDANCE_BOUNDARY_BUDGET_EXCEEDED')
        require(all(s.lane_type == 'road' and s.lane_id.prefab_token is None
                    for s in path.segments), 'SENSITIVE_TURN_REQUIRES_PHASE5_PLANNER')
        require(len({s.elevation_layer for s in path.segments}) == 1
                and (derived or all(abs(p.y-corridor.surface.y_m) < 1e-6
                                    for p in path.points)),
                'GUIDANCE_ELEVATION_MISMATCH')
        require(math.isfinite(speed_mps) and .5 <= speed_mps <= 25
                and math.isfinite(initial_trailer_heading), 'INVALID_GUIDANCE_MOTION')
        # Defaults are the conservative *offline simulation* plant, not live
        # tracking evidence. A live caller must supply measured timing.
        require(math.isfinite(actuator_response_s)
                and .1 <= actuator_response_s <= 1.
                and math.isfinite(actuator_delay_s)
                and 0. <= actuator_delay_s <= .5,
                'UNVALIDATED_ACTUATOR_TIMING')
        points = _with_kinematics(_resample_polyline(path.points, .5))
        ss = np.array([p.s for p in points])
        heads = np.unwrap([p.heading for p in points])
        ks = -np.gradient(heads, ss)
        require(max(abs(ks)) <= 1/35. and np.ptp(heads) < math.radians(75),
                'SHARP_TURN_REQUIRES_PHASE5_PLANNER')
        turns = ks[abs(ks) > .001]
        require(not (np.any(turns > 0) and np.any(turns < 0)),
                'COMPOUND_TURN_OUTSIDE_LIGHT_GUIDANCE_DOMAIN')
        timing_speed_cap = min(7., 7.*.75/max(.75,
                                 actuator_response_s+actuator_delay_s))
        design_speed = min(speed_mps, timing_speed_cap,
                           math.sqrt(.8/max(max(abs(ks)), 1e-9)))
        require(design_speed >= .5, 'GUIDANCE_SPEED_ABOVE_VALIDATED_DOMAIN')
        first_bend = next((float(s) for s, k in zip(ss, ks) if abs(k) > .001),
                          0.)
        speed_reduction_distance = (max(0., speed_mps**2-design_speed**2)
                                    / (2*.8)
                                    + speed_mps*(actuator_response_s
                                                 + actuator_delay_s) + 5.)
        require(speed_mps <= design_speed + 1e-6
                or first_bend > speed_reduction_distance,
                'INSUFFICIENT_APPROACH_FOR_DESIGN_SPEED')
        require(abs(wrap_angle(initial_trailer_heading-heads[0])) <= math.radians(5),
                'GUIDANCE_ENTRY_ARTICULATION')
        # Preserve full entry/exit settling support, not merely endpoint position.
        tail = max(12., 3*geometry.hitch_to_axle_m)
        require(ss[-1] >= 2*tail+10, 'INSUFFICIENT_GUIDANCE_SETTLING_DISTANCE')
        fixed = (ss <= 5.) | (ss >= ss[-1]-tail)
        require(max(abs(ks[fixed])) < .001, 'GUIDANCE_SEAMS_NOT_STRAIGHT')
        # Do not move a road/road gate. Prefab/merge/split were rejected above.
        for a, b in zip(path.points, path.points[1:]):
            if a.segment_index != b.segment_index:
                fixed |= abs(ss-a.s) < 3.
        xy = np.array([(p.x, p.z) for p in points])
        baseline = _predict(points, geometry, initial_trailer_heading)
        baseline_error = max(abs(_project(xy, np.array([(r[1].x, r[1].z) for r in baseline]))))
        require(baseline_error >= .05, 'NO_MEANINGFUL_TRAILER_OFFTRACKING')
        support = max(8., 1.5*geometry.hitch_to_axle_m)
        # Quintic taper has zero first/second derivative at unchanged seams.
        distance = np.minimum(np.maximum(ss-5., 0.), np.maximum(ss[-1]-tail-ss, 0.))
        for gate in ss[fixed]:
            distance = np.minimum(distance, abs(ss-gate))
        u = np.clip(distance/support, 0, 1)
        taper = u*u*u*(10-15*u+6*u*u)
        candidates = []
        for preview in (-support/2, 0., support/2):
            weights = np.maximum(0., 1-abs(ss[:, None]-ss[None, :]-preview)/support)**3
            smooth_k = weights @ ks / weights.sum(axis=1)
            for fraction in (.25,):
                require(clock() < deadline, 'GUIDANCE_DEADLINE_EXPIRED')
                offset = fraction*.5*(geometry.hitch_to_axle_m**2
                                      -geometry.hitch_ahead_m**2)*smooth_k*taper
                if max(abs(offset)) > (.15 if derived else .75):
                    continue
                candidate = _with_kinematics(tuple(replace(p,
                    x=p.x-offset[i]*math.cos(heads[i]),
                    z=p.z+offset[i]*math.sin(heads[i])) for i, p in enumerate(points)))
                # Route CTE normal is (-cos h, sin h), opposite right-positive
                # curvature. Positive compensation moves outside a right turn.
                ck = np.array([p.curvature for p in candidate])
                tyre = np.arctan(geometry.wheelbase_m*ck)
                times = np.array([p.s/design_speed for p in candidate])
                rate = np.gradient(tyre, times)
                if (max(abs(ck)) > 1/35. or max(abs(ck))*design_speed**2 > .8
                        or max(abs(rate)) > .12
                        or max(abs(np.gradient(rate, times))) > .20):
                    continue
                poses = _predict(candidate, geometry, initial_trailer_heading)
                error = max(abs(_project(xy, np.array([(r[1].x, r[1].z) for r in poses]))))
                if error >= .85*baseline_error:
                    continue
                candidates.append((error+.15*max(abs(offset)), candidate, poses,
                                   error, float(max(abs(offset)))))
        unavailable = ('NO_IMPROVING_REFERENCE_INSIDE_DERIVED_PLACEMENT_BUDGET'
                       if derived else 'NO_IMPROVING_REFERENCE_INSIDE_CONFIRMED_CORRIDOR')
        require(bool(candidates), unavailable)
        for _, candidate, poses, error, deviation in sorted(candidates, key=lambda row: row[0]):
            if derived:
                # Placement budget only: no assertion about body/curb clearance.
                axle_xy = np.array([(p.x, p.z) for row in poses for p in row])
                reserve = (derived_width/2 - max(abs(_project(xy, axle_xy)))
                           - derived_uncertainty - geometry.uncertainty_m - .75)
            else:
                reserve = _reserve(poses, corridor.surface,
                    .25+geometry.uncertainty_m+corridor.boundary_uncertainty_m,
                    .55, deadline, clock)
            if reserve > 0:
                break
        require(reserve > 0, unavailable)
        original = [(p.x, p.y, p.z) for p in path.points]
        xyz = [(p.x, p.y, p.z) for p in candidate]
        _seam(xyz, original, entry=True)
        _seam(xyz, original, entry=False)
        envelope = None
        if vehicle is not None:
            require(not derived, 'BODY_CLEARANCE_REQUIRES_CONFIRMED_SURFACE')
            vehicle.validate()
            require(len(vehicle.bodies) == 2
                    and vehicle.wheelbase_m == geometry.wheelbase_m
                    and vehicle.bodies[0].hitch_rear_m == geometry.hitch_ahead_m
                    and vehicle.bodies[1].hitch_front_m == geometry.hitch_to_axle_m,
                    'GUIDANCE_BODY_KINEMATICS_MISMATCH')
            # Low-speed whole-body validator remains optional and authoritative.
            require(design_speed <= vehicle.max_speed_mps, 'SWEPT_VALIDATOR_SPEED_DOMAIN')
            dense = _with_kinematics(_resample_polyline(candidate, design_speed*.02))
            dense_poses = _predict(dense, geometry, initial_trailer_heading)
            frames = tuple(Frame(p.s/design_speed, identity, row)
                           for p, row in zip(dense, dense_poses))
            # Kinematic calibration error is additional to body dimensions;
            # supplying a body model must not silently discard that reserve.
            envelope = evaluate_on_confirmed_surface(replace(vehicle,
                uncertainty_m=vehicle.uncertainty_m+geometry.uncertainty_m),
                frames, corridor, path, identity)
            require(envelope.accepted, envelope.failure_reason)
        require(clock() < deadline, 'GUIDANCE_DEADLINE_EXPIRED')
        path_hash = lane_path_fingerprint(path)
        corridor_token = digest((None if derived else corridor.token,
                                 lane_use_token))
        token = _reference_token(path_hash, geometry.configuration, corridor_token, identity, candidate)
        return GuidancePlan(True, '', identity, path_hash, geometry.configuration, token,
            tuple(candidate), poses, float(baseline_error), float(error), deviation,
            reserve, envelope, False, corridor_token, design_speed,
            'derived_lane_placement' if derived else 'confirmed_surface',
            speed_reduction_distance if design_speed < speed_mps else 0.)
    except EnvelopeError as exc:
        return GuidancePlan(False, str(exc), identity,
                            handoff_before_m=max(0., first_bend-10.))
    except (ValueError, TypeError, AttributeError, IndexError, OverflowError):
        return GuidancePlan(False, 'MALFORMED_GUIDANCE_INPUT', identity)


def reference_route(plan, path, identity, configuration):
    """Prepare a Route for offline/replay following by the existing controller.

    A Route object is not an execution packet. Only the unchanged 5D publisher
    and its complete live evidence may grant production local authority.
    """
    require(plan.accepted and plan.identity == identity
            and plan.path_fingerprint == lane_path_fingerprint(path)
            and plan.configuration == configuration, 'STALE_GUIDANCE_REFERENCE')
    require(plan.token == _reference_token(plan.path_fingerprint, plan.configuration,
        plan.corridor_token, identity, plan.points),
        'MUTATED_GUIDANCE_REFERENCE')
    layers = {s.lane_id: s.elevation_layer for s in path.segments}
    return Route([(p.x, p.y, p.z) for p in plan.points], name='trailer-guidance-candidate',
                 point_authorities=[(p.lane_id.sort_key(), layers[p.lane_id]) for p in plan.points])


def plan_sharp_turn(vehicle, start, path, surface, identity, **kwargs):
    """One explicit escalation to the retained 5B3 planner, never an offset."""
    from core.navigation.maneuver_planner import plan_maneuver
    return plan_maneuver(vehicle, start, path, surface, identity, **kwargs)


def plan_hybrid_reference(path, identity, geometry, corridor, *,
                          initial_trailer_heading, speed_mps,
                          vehicle=None, ground_frame=None,
                          sharp_surface=None, limits=None,
                          actuator_response_s=.60, actuator_delay_s=.15):
    """One offline trajectory result; sharp cases retain the 5B3 validator."""
    try:
        validate_path_identity(path, identity, identity)
        require(math.isfinite(speed_mps) and .5 <= speed_mps <= 25,
                'INVALID_GUIDANCE_MOTION')
        require(math.isfinite(actuator_response_s)
                and .1 <= actuator_response_s <= 1.
                and math.isfinite(actuator_delay_s)
                and 0. <= actuator_delay_s <= .5,
                'UNVALIDATED_ACTUATOR_TIMING')
        sensitive = any(s.lane_type != 'road' or s.lane_id.prefab_token is not None
                        for s in path.segments)
        heads = np.unwrap([p.heading for p in path.points])
        sharp = bool(np.ptp(heads) >= math.radians(75)
                     or max(abs(p.curvature) for p in path.points) > 1/35.)
        if not (sensitive or sharp):
            return plan_trailer_guidance(path, identity, geometry, corridor,
                initial_trailer_heading=initial_trailer_heading,
                speed_mps=speed_mps, vehicle=vehicle,
                actuator_response_s=actuator_response_s,
                actuator_delay_s=actuator_delay_s)
        first_turn = next((p.s for p in path.points
                           if abs(p.curvature) > .005), 0.)
        handoff = max(0., first_turn-10.)
        if vehicle is None or ground_frame is None or sharp_surface is None:
            return GuidancePlan(False,
                'SHARP_TURN_REQUIRES_CONFIRMED_BODY_SURFACE_AND_GROUND_FRAME',
                identity, handoff_before_m=handoff)
        from core.navigation.maneuver_planner import PlannerLimits
        selected_limits = limits or PlannerLimits()
        design_speed = min(speed_mps, selected_limits.speed_mps)
        required = (max(0., speed_mps**2-design_speed**2)/(2*.8)
                    + speed_mps*(actuator_response_s+actuator_delay_s) + 5.)
        if speed_mps > design_speed and handoff < required:
            return GuidancePlan(False,
                'INSUFFICIENT_APPROACH_FOR_SHARP_DESIGN_SPEED',
                identity, design_speed_mps=design_speed,
                speed_reduction_distance_m=required,
                handoff_before_m=handoff)
        full = plan_sharp_turn(vehicle, ground_frame, path, sharp_surface,
            identity, limits=selected_limits, entry_speed_mps=design_speed)
        if not full.accepted:
            return GuidancePlan(False, full.failure_reason, identity,
                                design_speed_mps=design_speed,
                                handoff_before_m=handoff)
        points = _with_kinematics(tuple(LanePoint(
            sample.frame.poses[0].x, sample.frame.poses[0].y,
            sample.frame.poses[0].z, lane_id=sample.source_lane_id,
            segment_index=sample.source_segment_index)
            for sample in full.samples))
        original = [(p.x, p.y, p.z) for p in path.points]
        xyz = [(p.x, p.y, p.z) for p in points]
        _seam(xyz, original, entry=True)
        _seam(xyz, original, entry=False)
        path_hash = lane_path_fingerprint(path)
        configuration = (geometry.configuration if geometry is not None else
                         digest(asdict(vehicle)))
        corridor_token = sharp_surface.token
        token = _reference_token(path_hash, configuration, corridor_token,
                                 identity, points)
        return GuidancePlan(True, '', identity, path_hash, configuration,
            token, points, (), 0., 0., 0.,
            full.envelope.minimum_clearance_m, full.envelope, False,
            corridor_token, full.speed_mps, 'confirmed_surface',
            required if design_speed < speed_mps else 0., handoff)
    except EnvelopeError as exc:
        return GuidancePlan(False, str(exc), identity)
    except (TypeError, ValueError, IndexError, AttributeError, OverflowError):
        return GuidancePlan(False, 'MALFORMED_HYBRID_INPUT', identity)


def propose_trailer_reference(path, identity, geometry, corridor, *,
                              initial_trailer_heading, speed_mps,
                              vehicle=None, ground_frame=None,
                              sharp_surface=None, limits=None):
    """Select one offline strategy. Sharp turns retain the full Phase 5 gate.

    Returns (strategy, proposal); neither result grants a live control lease.
    The caller must use 5C/5D for any sharp execution. The light proposal is
    currently for offline/replay only, not a substitute for their evidence.
    """
    from core.navigation.maneuver_planner import ManeuverPlan
    sensitive = any(s.lane_type != 'road' or s.lane_id.prefab_token is not None
                    for s in path.segments)
    heads = np.unwrap([p.heading for p in path.points])
    sharp = bool(len(heads) and (np.ptp(heads) >= math.radians(75)
                 or max(abs(p.curvature) for p in path.points) > 1/35.))
    if sensitive or sharp:
        if vehicle is None or ground_frame is None:
            return 'phase5_swept', ManeuverPlan(False,
                'SHARP_TURN_REQUIRES_CONFIRMED_BODY_AND_GROUND_FRAME', identity)
        return 'phase5_swept', plan_sharp_turn(vehicle, ground_frame, path,
            sharp_surface, identity, limits=limits, entry_speed_mps=speed_mps)
    return 'corridor_guidance', plan_trailer_guidance(path, identity, geometry,
        corridor, initial_trailer_heading=initial_trailer_heading,
        speed_mps=speed_mps, vehicle=vehicle)


class GuidanceWorker:
    """One in-flight offline job; callbacks cannot become runtime authority."""
    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='trailer-guidance')
        self._future = None
        self._key = None
        self._deadline = None

    def offer(self, key, *args, **kwargs):
        if self._future is not None:
            return False
        self._key = digest(key)
        self._deadline = kwargs.setdefault('deadline', time.monotonic()+10.)
        self._future = self._executor.submit(plan_trailer_guidance, *args, **kwargs)
        return True

    def harvest(self, current_key):
        if self._future is None or not self._future.done():
            return None
        future, key = self._future, self._key
        self._future = None
        result = future.result()
        return result if key == digest(current_key) and time.monotonic() < self._deadline else None

    def close(self):
        self._executor.shutdown(wait=False, cancel_futures=True)
