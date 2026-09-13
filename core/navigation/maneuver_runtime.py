"""Phase 5D executable authority gate, with no actuator or shared-state writes.

Preparation and traffic evaluation belong to a worker, never the control tick.
The caller must consume a decision against its exact live frame/route binding.
No production caller currently supplies the required tracking/coverage proofs;
the gate must not be wired to the legacy display traffic list as a shortcut.
The original LanePath, 5C result and controller remain unchanged.
"""
from bisect import bisect_left
from dataclasses import asdict, dataclass, replace
from enum import Enum
import math
import time

import numpy as np

from core.navigation.drivable_surface import digest, lane_path_fingerprint
from core.navigation.lane_model import wrap_angle
from core.navigation.maneuver_integration import (
    GroundReferenceEvidence, _snapshot_hash,
    validate_integration_result,
)
from core.navigation.maneuver_planner import PlannerLimits, _exit, _limits
from core.navigation.maneuver_traffic import (
    OccupancyInterval, TrafficSnapshot, TrafficWindow, check_traffic_window,
    evidence,
)
from core.swept_envelope import (
    EnvelopeError, clearance, expand, finite, footprint, hull, require,
)
from core.vehicle_profile import bind_envelope_vehicle


REFERENCE_DECISION_MAX_COMPUTE_S = .1


class ManeuverState(str, Enum):
    NO_MANEUVER = 'NO_MANEUVER'
    PLAN_PENDING = 'PLAN_PENDING'
    GEOMETRY_REJECTED = 'GEOMETRY_REJECTED'
    WAITING_FOR_TRAFFIC = 'WAITING_FOR_TRAFFIC'
    READY_FOR_ENTRY = 'READY_FOR_ENTRY'
    EXECUTING = 'EXECUTING'
    EXIT_REVALIDATION = 'EXIT_REVALIDATION'
    COMPLETED = 'COMPLETED'
    CANCELLED_STALE = 'CANCELLED_STALE'
    EMERGENCY_ABORT = 'EMERGENCY_ABORT'


def _result_fingerprint(result):
    value = asdict(result)
    # LaneSegment includes frozenset diagnostic UID membership; its canonical
    # path fingerprint already covers the ordered, authoritative topology.
    value['context']['local_lane_path'] = lane_path_fingerprint(result.context.local_lane_path)
    return digest(value)


@dataclass(frozen=True)
class TrackingEvidence:
    """External validation of the existing controller and longitudinal executor.

    Bound includes *all* footprint corners, actuator lag/jitter and speed
    tracking for this exact vehicle/plan. A source label is not that validation.
    The production integration must verify the referenced artifact and bind
    the sole consumer to the local reference; this module cannot attest it.
    """
    source: str
    evidence_sha256: str
    confirmed: bool
    corner_error_m: float
    time_error_s: float
    speed_error_mps: float
    acceleration_mps2: float = 1.
    jerk_mps3: float = .5

    def validate(self):
        require(self.confirmed is True and evidence(self.source, self.evidence_sha256),
                'MISSING_VALIDATED_EXECUTION_TRACKING_BOUND')
        require(finite(self.corner_error_m, self.time_error_s, self.speed_error_mps,
                       self.acceleration_mps2, self.jerk_mps3)
                and 0 < self.corner_error_m <= .25
                and 0 < self.time_error_s <= .5
                and 0 < self.speed_error_mps <= .1
                and 0 < self.acceleration_mps2 <= 1.
                and 0 < self.jerk_mps3 <= .5,
                'INVALID_EXECUTION_TRACKING_BOUND')


@dataclass(frozen=True)
class RuntimeRequest:
    result: object
    network: object
    lane_path: object
    snapshot: dict
    target_segment_index: int
    surface_catalog: object
    profile: object
    ground: GroundReferenceEvidence
    tracking: TrackingEvidence
    limits: PlannerLimits = PlannerLimits()
    original_entry_speed_mps: float = 0.
    original_entry_tyre_rad: float = 0.


@dataclass(frozen=True)
class LiveManeuverState:
    now_s: float
    enabled: bool
    lane_path: object
    snapshot: dict
    profile: object
    ground: GroundReferenceEvidence
    speed_mps: float
    tyre_rad: float
    confirmed_profile_token: object
    configuration_confirmation_source: str
    navigation_computed_at_s: float
    map_heartbeat_s: float
    consumer_binding: str


@dataclass(frozen=True)
class ApproachDemand:
    accepted: bool
    failure_reason: str
    target_speed_mps: float
    acceleration_mps2: float
    release_throttle: bool
    stopping_distance_m: float


def stopping_distance(speed, acceleration, max_deceleration=1., jerk=.5):
    """Exact integration of jerk-down to -D and subsequent constant braking.

    This is a conservative feasibility bound; brake calibration/grade must be
    supplied by the longitudinal executor. It is not an emergency brake command.
    """
    require(finite(speed, acceleration, max_deceleration, jerk)
            and speed >= 0 and 0 < max_deceleration <= 1. and 0 < jerk <= .5
            and -max_deceleration <= acceleration <= max_deceleration,
            'INVALID_APPROACH_DYNAMICS')
    ramp = (acceleration+max_deceleration)/jerk
    stop = (acceleration+math.sqrt(acceleration**2+2*jerk*speed))/jerk
    t = min(ramp, stop)
    distance = speed*t+.5*acceleration*t*t-jerk*t**3/6
    remaining = max(0., speed+acceleration*t-.5*jerk*t*t)
    # Reserve for replacing the hard stop's terminal acceleration discontinuity
    # with a jerk-limited release. This intentionally overbounds the release
    # area (rather than underestimating braking distance near standstill).
    return max(0., distance+remaining**2/(2*max_deceleration)
               + max_deceleration**3/(3*jerk**2))


def approach_demand(speed_mps, acceleration_mps2, distance_to_stop_m, dt_s,
                    blocked, entry_speed_mps=2., response_delay_s=.15):
    """Minimal approach demand; sole longitudinal executor owns brake output.

    Distance is to a confirmed axle stop point BEFORE the zone, accounting for
    front overhang and margin upstream. Every tick must use the measured state.
    Clear traffic targets entry speed, never a compulsory thirty-second stop.
    """
    try:
        require(type(blocked) is bool and finite(speed_mps, acceleration_mps2,
                distance_to_stop_m, dt_s, entry_speed_mps, response_delay_s)
                and 0 <= speed_mps <= 30 and distance_to_stop_m >= 0
                and 0 < dt_s <= .1 and 0 < entry_speed_mps <= 5
                and .15 <= response_delay_s <= 1., 'INVALID_APPROACH_STATE')
        stop = stopping_distance(speed_mps, acceleration_mps2)
        # During delay even a currently positive acceleration may persist.
        delay_speed = max(0., speed_mps+max(0., acceleration_mps2)*response_delay_s)
        delay_distance = (speed_mps*response_delay_s
                          + .5*max(0., acceleration_mps2)*response_delay_s**2)
        required = delay_distance+stopping_distance(
            delay_speed, acceleration_mps2)+.5
        if blocked and required > distance_to_stop_m:
            return ApproachDemand(False, 'INSUFFICIENT_CONFIRMED_STOPPING_DISTANCE',
                                  0., acceleration_mps2, True, required)
        target = 0. if blocked else entry_speed_mps
        desired = -1. if speed_mps > target else (1. if speed_mps < target else 0.)
        if (blocked and acceleration_mps2 >= 0
                and distance_to_stop_m > required+speed_mps*dt_s+.5*dt_s**2):
            desired = 0.  # coast until the bounded braking envelope is reached
        if acceleration_mps2 < 0 and speed_mps-target <= acceleration_mps2**2/(2*.5):
            desired = 0.  # release deceleration before reaching the stop speed
        acceleration = max(acceleration_mps2-.5*dt_s,
                           min(acceleration_mps2+.5*dt_s, desired))
        return ApproachDemand(True, '', target, acceleration,
                              blocked or speed_mps > target, max(stop, required))
    except (EnvelopeError, TypeError, ValueError, OverflowError) as error:
        return ApproachDemand(False, str(error), 0., 0., True, math.inf)


@dataclass(frozen=True)
class ExecutionTiming:
    start_s: float
    times_s: tuple[float, ...]
    initial_speed_mps: float
    cruise_speed_mps: float
    ramp_duration_s: float

    def speed_at(self, time_s):
        u = min(1., max(0., (time_s-self.start_s)/max(self.ramp_duration_s, 1e-12)))
        return self.initial_speed_mps+(self.cruise_speed_mps-self.initial_speed_mps)*(3*u*u-2*u**3)


def execution_timing(plan, now, speed, tracking):
    """Retime unchanged geometry. Speed change is confined to the straight entry.

    v=v0+dv*(3u^2-2u^3), so max acceleration=1.5*dv/T and
    max jerk=6*dv/T^2. The ramp ends before nonzero curvature; therefore the
    additional steering acceleration term a*d(delta)/ds is zero on the ramp.
    Slower traversal preserves the original *spatial* swept polygons.
    """
    tracking.validate()
    require(finite(now, speed) and now >= 0 and 0 <= speed <= plan.speed_mps,
            'ENTRY_SPEED_OUTSIDE_VALIDATED_TIMING_DOMAIN')
    dv = plan.speed_mps-speed
    duration = (max(1.5*dv/tracking.acceleration_mps2,
                    math.sqrt(6*dv/tracking.jerk_mps3)) if dv else 0.)
    ramp_distance = (speed+plan.speed_mps)*duration/2
    piece = plan.controls_xz[0]
    straight_length = math.dist(piece[0], piece[-1])
    direction = (piece[-1][0]-piece[0][0], piece[-1][1]-piece[0][1])
    require(straight_length > 0 and all(abs(
        (p[0]-piece[0][0])*direction[1]-(p[1]-piece[0][1])*direction[0])
        <= 1e-8 for p in piece), 'UNPROVEN_STRAIGHT_SPEED_TRANSITION')
    require(ramp_distance+tracking.corner_error_m < straight_length,
            'INSUFFICIENT_STRAIGHT_ENTRY_FOR_SPEED_TRANSITION')

    def distance_at(t):
        u = t/duration
        return speed*t+dv*duration*(u**3-.5*u**4)

    times = []
    for sample in plan.samples:
        s = sample.s_m
        if not duration or s >= ramp_distance:
            t = duration+(s-ramp_distance)/plan.speed_mps
        else:
            lo, hi = 0., duration
            for _ in range(50):
                mid = (lo+hi)/2
                if distance_at(mid) < s:
                    lo = mid
                else:
                    hi = mid
            t = (lo+hi)/2 if s else 0.
        times.append(now+t)
    require(all(a < b for a, b in zip(times, times[1:])), 'INVALID_RETIMED_MANEUVER')
    return ExecutionTiming(now, tuple(times), speed, plan.speed_mps, duration)


@dataclass(frozen=True)
class ManeuverDecision:
    state: ManeuverState
    failure_reason: str
    runtime_authorized: bool = False
    binding: str = ''
    computed_at_s: float | None = None
    valid_until_s: float | None = None
    sdk_frame_us: int | None = None
    traffic: TrafficWindow | None = None
    reference_plan_token: str = ''
    target_speed_mps: float = 0.


class ManeuverRuntime:
    """Explicit state machine. Terminal failures latch until a new instance.

    READY is a proposal, never permission. enter=True rechecks the entire live
    binding and traffic window, including a just-changed traffic situation.
    WAITING holds no old traffic lease and has no elapsed-wait timeout.
    """
    def __init__(self, request=None, *, clock=time.perf_counter):
        self.state = ManeuverState.NO_MANEUVER
        self.request = request
        self.binding = ''
        self.failure_reason = ''
        self.timing = None
        self.transitions = []
        self._last_now = None
        self._last_sdk = None
        self._traffic_sequence = None
        self._traffic_digest = None
        self._sdk_digest = None
        self._prepared_hash = None
        self._prepared_result = None
        self._prepared_model = None
        self._prepared_surface_catalog = None
        self._last_decision = None
        self._issued_live_stamp = None
        self._clock = clock
        if request is not None:
            self._transition(ManeuverState.PLAN_PENDING, 'GEOMETRY_VALIDATION_PENDING')
            try:
                r = request
                require(r.result.accepted, r.result.failure_reason)
                reason = validate_integration_result(r.result, r.network, r.lane_path,
                    r.snapshot, r.target_segment_index, r.surface_catalog,
                    r.profile, r.ground, r.ground.observed_at, r.limits,
                    r.original_entry_speed_mps, r.original_entry_tyre_rad)
                require(not reason, reason)
                r.tracking.validate()
                self.surface = r.surface_catalog.resolve(r.result.context.local_lane_path,
                    r.result.context.identity, r.result.context.identity)
                self.polygons = tuple(tuple(expand(poly, r.tracking.corner_error_m)
                    for poly in step.swept_polygons) for step in r.result.plan.envelope.steps)
                # Coverage with zero observed actors still has to contain the
                # complete maneuver plus unseen-entrant reach.  Precompute the
                # conservative whole-plan hull while preparing the maneuver so
                # immediate entry revalidation never rebuilds it in the lease.
                self._coverage_hulls = tuple(hull(tuple(
                    point for row in self.polygons for point in row[body]))
                    for body in range(len(self.polygons[0])))
                block_samples = max(1, int(round(
                    2.5 / r.limits.sample_dt_s)))
                self._occupancy_blocks = []
                for first in range(0, len(self.polygons)-1, block_samples):
                    last = min(first+block_samples, len(self.polygons)-1)
                    polygons = tuple(hull(tuple(
                        point for row in self.polygons[first:last+1]
                        for point in row[body]))
                        for body in range(len(self.polygons[0])))
                    self._occupancy_blocks.append((first, last, polygons))
                self._occupancy_blocks = tuple(self._occupancy_blocks)
                self.minimum_clearance_m = min(clearance(poly, self.surface.surface)
                    for row in self.polygons for poly in row)
                require(self.minimum_clearance_m > 0., 'TRACKING_RESERVE_EXCEEDS_SURFACE')
                k, ds, dss = _limits(np.asarray(r.result.plan.controls_xz), r.profile.model.wheelbase_m)
                speed = r.result.plan.speed_mps
                require(math.atan(k*r.profile.model.wheelbase_m) <= r.profile.model.max_tyre_rad
                        and speed*ds <= r.limits.tyre_rate_rad_s
                        and speed*speed*dss <= r.limits.tyre_accel_rad_s2,
                        'EXECUTION_STEERING_DYNAMICS_UNPROVEN')
                # The foremost point must remain on the confirmed approach side
                # of the first sensitive segment while waiting at the entry.
                gate = r.result.context.local_lane_path.segments[1].centerline[0]
                forward = (-math.sin(gate.heading), -math.cos(gate.heading))
                require(all((x-gate.x)*forward[0]+(z-gate.z)*forward[1] < 0
                    for poly in self.polygons[0] for x, z in poly),
                    'WAITING_POSE_ALREADY_INSIDE_MANEUVER_ZONE')
                self._prepared_hash = _result_fingerprint(r.result)
                self._prepared_result = r.result
                self._prepared_model = r.profile.model
                self._prepared_surface_catalog = r.surface_catalog
                self.binding = digest({'integration': self._prepared_hash,
                    'tracking': asdict(r.tracking), 'limits': asdict(r.limits)})
            except EnvelopeError as error:
                self._transition(ManeuverState.GEOMETRY_REJECTED, str(error))
            except (AttributeError, TypeError, ValueError, OverflowError, IndexError):
                self._transition(ManeuverState.GEOMETRY_REJECTED, 'MALFORMED_RUNTIME_REQUEST')

    def _transition(self, state, reason):
        if state != self.state or reason != self.failure_reason:
            self.transitions.append((self.state.value, state.value, reason))
        self.state, self.failure_reason = state, reason

    def _validate_live(self, live):
        r = self.request
        require(finite(live.now_s) and live.now_s >= 0 and
                (self._last_now is None or live.now_s >= self._last_now),
                'NONMONOTONIC_RUNTIME_CLOCK')
        require(type(live.enabled) is bool, 'INVALID_AUTOPILOT_STATE')
        require(live.enabled, 'MANUAL_AUTOPILOT_DISABLED')
        require(live.consumer_binding == self.binding, 'LOCAL_REFERENCE_CONSUMER_NOT_BOUND')
        for value, reason in ((live.navigation_computed_at_s, 'STALE_NAVIGATION_COMMAND'),
                              (live.map_heartbeat_s, 'STALE_MAP_HEARTBEAT')):
            require(finite(value) and 0 <= live.now_s-value <= .5, reason)
        path_hash = lane_path_fingerprint(live.lane_path)
        require(path_hash == r.result.context.full_lane_path_fingerprint
                and _snapshot_hash(live.snapshot, path_hash)
                    == r.result.context.snapshot_fingerprint,
                'STALE_MANEUVER_ROUTE_CONTEXT')
        current = r.result.context
        # The complete result graph is made of frozen dataclasses and tuples.
        # Retaining its exact root object proves it was not replaced without
        # serializing thousands of immutable samples on every live check.
        require(r.result is self._prepared_result,
                'MUTATED_PREPARED_MANEUVER')
        require(self.binding == digest({'integration': self._prepared_hash,
                'tracking': asdict(r.tracking), 'limits': asdict(r.limits)}),
                'MUTATED_EXECUTION_LIMITS_OR_TRACKING_PROOF')
        require(live.profile.token == r.result.vehicle_profile_token
                and live.profile.model == r.profile.model == self._prepared_model,
                'STALE_MANEUVER_VEHICLE_PROFILE')
        bind_envelope_vehicle(live.profile, live.profile, current.identity,
            current.identity, live.now_s, live.confirmed_profile_token,
            live.configuration_confirmation_source)
        live.ground.validate(live.profile, current.identity)
        require(0 <= live.now_s-live.ground.observed_at <= .1,
                'STALE_LIVE_GROUND_REFERENCE')
        require(live.ground.position_uncertainty_m <= r.ground.position_uncertainty_m,
                'GROUND_UNCERTAINTY_EXCEEDS_PLAN')
        live.ground.frame.validate(r.profile.model)
        require(finite(live.speed_mps, live.tyre_rad) and live.speed_mps >= 0
                and abs(live.tyre_rad) <= r.profile.model.max_tyre_rad,
                'INVALID_LIVE_ENTRY_DYNAMICS')
        require(all(abs(p.y-self.surface.surface.y_m) <= 1e-9
                    for p in live.ground.frame.poses), 'LIVE_GROUND_ELEVATION_MISMATCH')
        sdk = live.ground.sdk_frame_us
        frame_digest = digest(asdict(live.ground))
        require(self._last_sdk is None or sdk >= self._last_sdk, 'REGRESSING_GROUND_SDK_FRAME')
        require(sdk != self._last_sdk or frame_digest == self._sdk_digest,
                'REUSED_SDK_FRAME_WITH_CHANGED_GROUND')
        # RuntimeRequest is frozen and retains the exact catalog object and
        # resolved immutable surface. Re-resolving its thousands of vertices on
        # every lease cannot detect a change that object identity already
        # excludes; identity/path hashes above still detect live route changes.
        require(r.surface_catalog is self._prepared_surface_catalog
                and self.surface.token == r.result.surface_token,
                'STALE_MANEUVER_SURFACE')
        self._last_now, self._last_sdk, self._sdk_digest = live.now_s, sdk, frame_digest

    def _check_pose(self, live, indices, entry=False):
        r = self.request
        actual = live.ground.frame.poses
        budget = r.tracking.corner_error_m
        residual = min(max(math.dist(a, b)
            for body, pose, target in zip(r.profile.model.bodies, actual,
                                         r.result.plan.samples[i].frame.poses)
            for a, b in zip(footprint(body, pose), footprint(body, target)))
            for i in indices)
        require(residual <= budget, 'LIVE_BODY_OUTSIDE_TRACKING_RESERVE')
        if entry:
            target = r.result.plan.samples[0].frame.poses[0]
            pose = actual[0]
            require(math.dist((pose.x, pose.y, pose.z), (target.x, target.y, target.z))
                    <= r.limits.endpoint_position_m
                    and abs(wrap_angle(pose.heading-target.heading)) <= r.limits.endpoint_heading_rad,
                    'LIVE_STATE_NOT_AT_CONFIRMED_ENTRY')
            require(abs(live.tyre_rad) <= 1e-9, 'ENTRY_NOT_STRAIGHT')

    def _occupancy(self, timing, now, *, coverage_only=False):
        # Merge only for occupancy checking, never alter the driving geometry.
        # Nominal 2.5 s block hulls are prepared outside runtime revalidation.
        # A slower retimed entry only lengthens their time range, which is more
        # conservative. The first partial block is rebuilt from the current
        # sample; every complete future block reuses immutable geometry.
        if coverage_only:
            return (OccupancyInterval(
                now, max(now, timing.times_s[-1]), self._coverage_hulls),)
        intervals, start = [], now
        first_live = min(bisect_left(timing.times_s, now),
                         len(timing.times_s)-1)
        for first, last, cached in self._occupancy_blocks:
            if last < first_live:
                continue
            begin = max(first, first_live)
            polygons = cached if begin == first else tuple(hull(tuple(
                point for row in self.polygons[begin:last+1]
                for point in row[body]))
                for body in range(len(self.polygons[0])))
            end = max(start, timing.times_s[last])
            intervals.append(OccupancyInterval(start, end, polygons))
            start = end
        return tuple(intervals)

    def update(self, live, traffic, *, enter=False):
        revalidation_started = self._clock()
        terminal = {ManeuverState.NO_MANEUVER, ManeuverState.GEOMETRY_REJECTED,
                    ManeuverState.CANCELLED_STALE, ManeuverState.EMERGENCY_ABORT,
                    ManeuverState.COMPLETED}
        if self.state in terminal:
            return ManeuverDecision(self.state, self.failure_reason)
        executing = self.state in (ManeuverState.EXECUTING, ManeuverState.EXIT_REVALIDATION)
        window = None
        try:
            if executing:
                require(self._last_decision is not None
                        and finite(live.now_s)
                        and live.now_s <= self._last_decision.valid_until_s,
                        'EXECUTION_LEASE_EXPIRED_REVALIDATION_REQUIRED')
            self._validate_live(live)
            if isinstance(traffic, TrafficSnapshot):
                traffic_digest = digest(asdict(traffic))
                require(self._traffic_sequence is None or traffic.sequence >= self._traffic_sequence,
                        'REGRESSING_TRAFFIC_SEQUENCE')
                require(traffic.sequence != self._traffic_sequence
                        or traffic_digest == self._traffic_digest,
                        'REUSED_TRAFFIC_SEQUENCE_WITH_CHANGED_SNAPSHOT')
                self._traffic_sequence, self._traffic_digest = traffic.sequence, traffic_digest
            if executing:
                i = min(bisect_left(self.timing.times_s, live.ground.observed_at),
                        len(self.timing.times_s)-1)
                self._check_pose(live, (max(0, i-1), i))
                require(abs(live.speed_mps-self.timing.speed_at(live.ground.observed_at))
                        <= self.request.tracking.speed_error_mps,
                        'EXECUTION_SPEED_OUTSIDE_TIMING_BOUND')
                if live.now_s >= self.timing.times_s[-1]:
                    self._transition(ManeuverState.EXIT_REVALIDATION, 'FRESH_EXIT_CHECK_REQUIRED')
                    r = self.request
                    window = check_traffic_window((OccupancyInterval(live.now_s, live.now_s,
                        self.polygons[-1]),), traffic, r.result.context.identity, live.now_s,
                        temporal_margin_s=1.+r.tracking.time_error_s)
                    require(window.accepted, window.failure_reason)
                    _exit(replace(r.profile.model, uncertainty_m=r.profile.model.uncertainty_m
                        + r.tracking.corner_error_m + live.ground.position_uncertainty_m),
                        live.ground.frame, r.result.context.local_lane_path.points[-1],
                        r.result.context.local_lane_path, r.limits)
                    self._transition(ManeuverState.COMPLETED, 'EXIT_LANE_AND_ARTICLES_REVALIDATED')
                    return ManeuverDecision(self.state, self.failure_reason)
                timing = self.timing
            else:
                self._check_pose(live, (0,), entry=True)
                timing = execution_timing(self.request.result.plan, live.now_s,
                                           live.speed_mps, self.request.tracking)
            window = check_traffic_window(self._occupancy(
                timing, live.now_s,
                coverage_only=(isinstance(traffic, TrafficSnapshot)
                               and not traffic.actors)), traffic,
                self.request.result.context.identity, live.now_s,
                temporal_margin_s=1.+self.request.tracking.time_error_s)
            if not window.accepted:
                self._transition(ManeuverState.EMERGENCY_ABORT if executing
                                 else ManeuverState.WAITING_FOR_TRAFFIC, window.failure_reason)
                return ManeuverDecision(self.state, self.failure_reason, traffic=window,
                                        computed_at_s=live.now_s)
            if executing or enter is True:
                require(self._clock() - revalidation_started
                        < REFERENCE_DECISION_MAX_COMPUTE_S,
                        'REVALIDATION_DEADLINE_EXCEEDED')
                self.timing = timing
                self._transition(ManeuverState.EXECUTING, 'LIVE_ENTRY_AND_TRAFFIC_REVALIDATED')
                decision = ManeuverDecision(self.state, self.failure_reason, True, self.binding,
                    live.now_s, min(live.now_s+.1, live.ground.observed_at+.1),
                    live.ground.sdk_frame_us, window, self.request.result.plan.token,
                    timing.speed_at(live.now_s))
                self._last_decision = decision
                self._issued_live_stamp = _live_stamp(live)
                return decision
            self._transition(ManeuverState.READY_FOR_ENTRY, 'ENTRY_REVALIDATION_REQUIRED')
            return ManeuverDecision(self.state, self.failure_reason, traffic=window,
                                    computed_at_s=live.now_s)
        except EnvelopeError as error:
            state = (ManeuverState.CANCELLED_STALE
                     if str(error) == 'MANUAL_AUTOPILOT_DISABLED'
                     else ManeuverState.EMERGENCY_ABORT if executing
                     else ManeuverState.WAITING_FOR_TRAFFIC
                     if str(error) == 'REVALIDATION_DEADLINE_EXCEEDED'
                     else ManeuverState.CANCELLED_STALE)
            self._transition(state, str(error))
        except (AttributeError, TypeError, ValueError, OverflowError, IndexError):
            self._transition(ManeuverState.EMERGENCY_ABORT if executing
                             else ManeuverState.CANCELLED_STALE, 'MALFORMED_LIVE_MANEUVER_STATE')
        return ManeuverDecision(self.state, self.failure_reason, traffic=window)


def _live_stamp(live):
    return (live.ground, live.profile, live.speed_mps, live.tyre_rad,
            live.navigation_computed_at_s, live.map_heartbeat_s)


def decision_rejection_reason(decision, runtime, live, traffic):
    """Worker result is not a reusable command: consume against this exact frame.

    A production consumer must additionally retain the ordinary command packet
    checks, sole controller and sole SteeringDynamics. This function sends none.
    """
    try:
        require(isinstance(decision, ManeuverDecision) and decision.runtime_authorized
                and decision.state == runtime.state == ManeuverState.EXECUTING,
                'NO_MANEUVER_EXECUTION_AUTHORITY')
        require(decision == runtime._last_decision, 'SUPERSEDED_OR_MUTATED_MANEUVER_DECISION')
        require(decision.binding == runtime.binding
                and decision.reference_plan_token == runtime.request.result.plan.token,
                'STALE_LOCAL_REFERENCE_BINDING')
        require(finite(live.now_s, decision.computed_at_s, decision.valid_until_s)
                and decision.computed_at_s <= live.now_s < decision.valid_until_s,
                'EXPIRED_MANEUVER_DECISION')
        runtime._validate_live(live)
        require(decision.sdk_frame_us == live.ground.sdk_frame_us,
                'STALE_MANEUVER_DECISION_SDK_FRAME')
        require(_live_stamp(live) == runtime._issued_live_stamp,
                'CHANGED_MANEUVER_DECISION_LIVE_STATE')
        require(isinstance(traffic, TrafficSnapshot)
                and digest(asdict(traffic)) == runtime._traffic_digest,
                'STALE_MANEUVER_DECISION_TRAFFIC')
        traffic.validate(runtime.request.result.context.identity, live.now_s)
        return ''
    except EnvelopeError as error:
        return str(error)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return 'MALFORMED_MANEUVER_DECISION'
