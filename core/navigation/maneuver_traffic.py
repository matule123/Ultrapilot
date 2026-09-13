"""Phase 5D conservative, continuous traffic occupancy contracts.

The legacy display/ACC traffic list is deliberately NOT an input. Empty means
clear only inside a confirmed observation region, with a bound on unseen
entrants for the entire maneuver horizon. Evidence fields are trust contracts,
not certificates manufactured by this module. Production has no such producer
yet. All coordinates are world X/Z metres and all times share one monotonic
clock. No steering, map mutation, tracking filter or guessed dimensions.
"""
from dataclasses import dataclass
import math

from core.swept_envelope import (
    EnvelopeError, Identity, Surface, clearance, edges, expand, finite, hull,
    inside, intersects, point_segment, require, validate_ring,
)


def evidence(source, sha256):
    return (type(source) is str and bool(source.strip())
            and type(sha256) is str and len(sha256) == 64
            and all(c in '0123456789abcdef' for c in sha256))


@dataclass(frozen=True)
class TrafficObservation:
    observation_id: str
    time_s: float
    x_m: float
    z_m: float
    heading_rad: float
    speed_mps: float
    velocity_x_mps: float
    velocity_z_mps: float
    polygons_xz: tuple = ()


@dataclass(frozen=True)
class TrafficActor:
    """Whole vehicle, including each trailer, in the latest observed pose.

    Polygons contain ALL body points. Error bounds apply to every body point,
    including heading, dimensions, angular motion and articulated trailers.
    Corner acceleration is an absolute deviation bound from constant world
    velocity, not a guessed longitudinal acceleration. Unknown bounds reject.
    Elevation is not used to discard objects: absent a 3D separation proof,
    overlapping X/Z on another deck is conservatively treated as a conflict.
    """
    actor_id: str
    history: tuple[TrafficObservation, ...]
    polygons_xz: tuple
    source: str
    evidence_sha256: str
    dimensions_confirmed: bool
    confidence: float
    position_error_m: float
    corner_velocity_error_mps: float
    corner_acceleration_bound_mps2: float
    valid_until_s: float

    def validate(self, now):
        require(type(self.actor_id) is str and bool(self.actor_id.strip()),
                'MISSING_TRAFFIC_ACTOR_ID')
        require(self.dimensions_confirmed is True
                and evidence(self.source, self.evidence_sha256),
                'UNPROVEN_TRAFFIC_BODY_ENVELOPE')
        require(finite(self.confidence, self.position_error_m,
                       self.corner_velocity_error_mps,
                       self.corner_acceleration_bound_mps2, self.valid_until_s)
                and .99 <= self.confidence <= 1.
                and 0 < self.position_error_m <= 10.
                and 0 <= self.corner_velocity_error_mps <= 100.
                and 0 <= self.corner_acceleration_bound_mps2 <= 100.,
                'UNBOUNDED_TRAFFIC_PREDICTION')
        require(type(self.history) is tuple and 2 <= len(self.history) <= 128,
                'MISSING_TRAFFIC_MOTION_HISTORY')
        require(type(self.polygons_xz) is tuple
                and 1 <= len(self.polygons_xz) <= 5,
                'MISSING_TRAFFIC_BODY_ENVELOPE')
        for polygon in self.polygons_xz:
            validate_ring(polygon)
        seen = set()
        previous = None
        for obs in self.history:
            require(isinstance(obs, TrafficObservation)
                    and type(obs.observation_id) is str
                    and bool(obs.observation_id.strip())
                    and obs.observation_id not in seen,
                    'INVALID_TRAFFIC_OBSERVATION_ID')
            seen.add(obs.observation_id)
            require(type(obs.polygons_xz) is tuple
                    and len(obs.polygons_xz) == len(self.polygons_xz),
                    'MISSING_HISTORICAL_TRAFFIC_BODY_ENVELOPE')
            for poly in obs.polygons_xz:
                validate_ring(poly)
            require(finite(obs.time_s, obs.x_m, obs.z_m, obs.heading_rad,
                           obs.speed_mps, obs.velocity_x_mps, obs.velocity_z_mps)
                    and obs.time_s >= 0 and 0 <= obs.speed_mps <= 100
                    and abs(obs.x_m) <= 1_000_000
                    and abs(obs.z_m) <= 1_000_000
                    and abs(obs.heading_rad) <= 1000*math.tau,
                    'INVALID_TRAFFIC_KINEMATICS')
            require(abs(obs.speed_mps-math.hypot(
                obs.velocity_x_mps, obs.velocity_z_mps)) <= .001,
                'TRAFFIC_SPEED_VECTOR_MISMATCH')
            if previous:
                dt = obs.time_s-previous.time_s
                require(0 < dt <= .5, 'TRAFFIC_HISTORY_GAP')
                residual = math.hypot(
                    obs.x_m-previous.x_m-previous.velocity_x_mps*dt,
                    obs.z_m-previous.z_m-previous.velocity_z_mps*dt)
                require(residual <= 2*self.position_error_m
                        + self.corner_velocity_error_mps*dt
                        + .5*self.corner_acceleration_bound_mps2*dt*dt,
                        'TRAFFIC_HISTORY_EXCEEDS_MOTION_BOUND')
                for before, after in zip(previous.polygons_xz, obs.polygons_xz):
                    require(len(before) == len(after), 'TRAFFIC_BODY_HISTORY_TOPOLOGY_CHANGED')
                    require(all(math.hypot(b[0]-a[0]-previous.velocity_x_mps*dt,
                                           b[1]-a[1]-previous.velocity_z_mps*dt)
                        <= 2*self.position_error_m+self.corner_velocity_error_mps*dt
                        + .5*self.corner_acceleration_bound_mps2*dt*dt
                        for a,b in zip(before,after)), 'TRAFFIC_BODY_HISTORY_EXCEEDS_MOTION_BOUND')
                require(math.hypot(obs.velocity_x_mps-previous.velocity_x_mps,
                                   obs.velocity_z_mps-previous.velocity_z_mps)
                        <= 2*self.corner_velocity_error_mps
                        + self.corner_acceleration_bound_mps2*dt + 1e-9,
                        'TRAFFIC_VELOCITY_EXCEEDS_MOTION_BOUND')
                radius = max(math.hypot(x-self.history[-1].x_m, z-self.history[-1].z_m)
                             for poly in self.polygons_xz for x, z in poly)
                angle = abs((obs.heading_rad-previous.heading_rad+math.pi) % math.tau-math.pi)
                require(2*radius*math.sin(angle/2)
                        <= 2*self.position_error_m+self.corner_velocity_error_mps*dt
                        + .5*self.corner_acceleration_bound_mps2*dt*dt,
                        'TRAFFIC_ROTATION_EXCEEDS_CORNER_MOTION_BOUND')
            previous = obs
        require(0 <= now-previous.time_s <= .5,
                'STALE_TRAFFIC_OBSERVATION')
        require(previous.polygons_xz == self.polygons_xz,
                'TRAFFIC_BODY_OBSERVATION_MISMATCH')
        require(self.valid_until_s >= now, 'EXPIRED_TRAFFIC_PREDICTION')


@dataclass(frozen=True)
class TrafficSnapshot:
    """Complete actor history in coverage_xz since coverage_since_s.

    Completeness includes recently departed actors for the temporal reserve,
    not just objects visible in the latest frame. No legacy reader attests this.
    """
    identity: Identity
    snapshot_id: str
    sequence: int
    observed_at_s: float
    valid_until_s: float
    actors: tuple[TrafficActor, ...]
    coverage_xz: tuple
    complete: bool
    unseen_speed_bound_mps: float
    source: str
    evidence_sha256: str
    coverage_since_s: float | None = None

    def validate(self, expected_identity, now):
        require(isinstance(self.identity, Identity), 'MISSING_TRAFFIC_IDENTITY')
        self.identity.validate()
        require(self.identity == expected_identity, 'STALE_TRAFFIC_IDENTITY')
        require(type(self.snapshot_id) is str and bool(self.snapshot_id.strip())
                and type(self.sequence) is int and self.sequence >= 0,
                'INVALID_TRAFFIC_SNAPSHOT_ID')
        require(self.complete is True and evidence(self.source, self.evidence_sha256),
                'UNPROVEN_TRAFFIC_COVERAGE')
        require(finite(self.coverage_since_s)
                and 0 <= self.coverage_since_s <= self.observed_at_s,
                'MISSING_HISTORICAL_TRAFFIC_COVERAGE')
        require(finite(now, self.observed_at_s, self.valid_until_s,
                       self.unseen_speed_bound_mps)
                and 0 <= now-self.observed_at_s <= .5
                and self.valid_until_s >= now,
                'STALE_TRAFFIC_SNAPSHOT')
        require(0 < self.unseen_speed_bound_mps <= 100.,
                'UNPROVEN_UNSEEN_TRAFFIC_MOTION_BOUND')
        validate_ring(self.coverage_xz)
        require(type(self.actors) is tuple and len(self.actors) <= 256,
                'INVALID_TRAFFIC_ACTOR_SET')
        ids = set()
        for actor in self.actors:
            require(isinstance(actor, TrafficActor), 'INVALID_TRAFFIC_ACTOR')
            actor.validate(now)
            require(actor.actor_id not in ids, 'AMBIGUOUS_TRAFFIC_ACTOR_ID')
            require(actor.history[-1].time_s <= self.observed_at_s,
                    'TRAFFIC_OBSERVATION_AFTER_SNAPSHOT')
            ids.add(actor.actor_id)


@dataclass(frozen=True)
class OccupancyInterval:
    start_s: float
    end_s: float
    polygons_xz: tuple


@dataclass(frozen=True)
class TrafficConflict:
    actor_id: str
    start_s: float
    end_s: float
    minimum_clearance_m: float
    time_to_conflict_s: float
    confidence: float


@dataclass(frozen=True)
class TrafficWindow:
    accepted: bool
    failure_reason: str
    snapshot_id: str = ''
    conflicts: tuple[TrafficConflict, ...] = ()
    minimum_clearance_m: float | None = None
    spatial_margin_m: float = .5
    temporal_margin_s: float = 1.
    checked_start_s: float | None = None
    checked_end_s: float | None = None


def polygon_distance(a, b):
    """Whole polygon distance, including containment and edge crossings."""
    if inside(a[0], b) or inside(b[0], a):
        return 0.
    best = math.inf
    for p, q in edges(a):
        for r, s in edges(b):
            if intersects(p, q, r, s):
                return 0.
            best = min(best, point_segment(p, r, s), point_segment(q, r, s),
                       point_segment(r, p, q), point_segment(s, p, q))
    return best


def polygon_distance_with_margin(a, b, margin):
    """Conservative fast path for spatially separate polygon bounds."""
    aminx = min(p[0] for p in a); amaxx = max(p[0] for p in a)
    aminz = min(p[1] for p in a); amaxz = max(p[1] for p in a)
    bminx = min(p[0] for p in b) - margin
    bmaxx = max(p[0] for p in b) + margin
    bminz = min(p[1] for p in b) - margin
    bmaxz = max(p[1] for p in b) + margin
    dx = max(0., aminx-bmaxx, bminx-amaxx)
    dz = max(0., aminz-bmaxz, bminz-amaxz)
    if dx > 0. or dz > 0.:
        # AABB separation is a lower bound on polygon separation. Reporting
        # the lower value is conservative and a positive value proves no hit.
        return math.hypot(dx, dz)
    return polygon_distance(a, expand(b, margin))


def _validate_convex_ring(ring):
    """Linear validation for ego hulls; rejects every non-convex input."""
    require(isinstance(ring, tuple) and 3 <= len(ring) <= 2048,
            'INVALID_BOUNDARY_RING')
    require(all(isinstance(p, tuple) and len(p) == 2 and finite(*p)
                and max(abs(v) for v in p) <= 1_000_000 for p in ring),
            'NONFINITE_BOUNDARY')
    require(len(set(ring)) == len(ring), 'DUPLICATE_BOUNDARY_VERTEX')
    turns = [((b[0]-a[0])*(c[1]-b[1])
              - (b[1]-a[1])*(c[0]-b[0]))
             for a, b, c in zip(ring, ring[1:]+ring[:1],
                                ring[2:]+ring[:2])]
    require(all(math.dist(a, b) > 1e-12
                for a, b in zip(ring, ring[1:]+ring[:1])),
            'DEGENERATE_BOUNDARY_EDGE')
    significant = [turn for turn in turns if abs(turn) > 1e-12]
    require(significant
            and (all(turn > 0 for turn in significant)
                 or all(turn < 0 for turn in significant)),
            'NONCONVEX_EGO_OCCUPANCY')


def predicted_polygons(actor, start_s, end_s):
    """Continuous reachability tube; no missed crossing between two samples.

    p(t)=p0+v*t+error, |error| <= ep+ev*t+0.5*ac*t^2.
    Endpoint hull contains the entire nominal translation. Square expansion
    contains the error ball for every intervening time and every body point.
    """
    require(actor.history[0].time_s <= start_s <= end_s
            and end_s <= actor.valid_until_s,
            'TRAFFIC_PREDICTION_HORIZON_INCOMPLETE')
    result = []
    for index, obs in enumerate(actor.history):
        next_time = (actor.history[index+1].time_s
                     if index+1 < len(actor.history) else actor.valid_until_s)
        begin, end = max(start_s, obs.time_s), min(end_s, next_time)
        if begin > end:
            continue
        lo, hi = begin-obs.time_s, end-obs.time_s
        pad = (actor.position_error_m + actor.corner_velocity_error_mps*hi
               + .5*actor.corner_acceleration_bound_mps2*hi*hi)
        result.extend(expand(hull(tuple(
            (x+obs.velocity_x_mps*t, z+obs.velocity_z_mps*t)
            for t in (lo, hi) for x, z in poly)), pad)
            for poly in obs.polygons_xz)
    require(all(finite(*p) and max(abs(v) for v in p) <= 1_000_000
                for poly in result for p in poly), 'UNBOUNDED_TRAFFIC_POLYGON')
    return tuple(result)


def check_traffic_window(intervals, snapshot, identity, now,
                         spatial_margin_m=.5, temporal_margin_s=1.):
    """Check a complete, explicitly timed ego sweep; never authorize controls.

    Time padding checks other traffic over [ego.start-margin, ego.end+margin].
    Historical full-body observations cover the leading edge before now;
    missing history rejects instead of clipping the temporal margin. Clear intervals are not
    merged across a conflict. Diagnostics retain each actor's conflict range.
    """
    try:
        require(isinstance(snapshot, TrafficSnapshot), 'MISSING_TRAFFIC_SNAPSHOT')
        snapshot.validate(identity, now)
        require(finite(spatial_margin_m, temporal_margin_s)
                and spatial_margin_m >= .5 and temporal_margin_s >= 1.,
                'INVALID_TRAFFIC_SAFETY_MARGIN')
        require(type(intervals) is tuple and 1 <= len(intervals) <= 20000,
                'MISSING_TIMED_EGO_ENVELOPE')
        coverage = Surface(identity, snapshot.coverage_xz, (), 0.,
                           snapshot.source, True, True)
        previous = None
        conflicts, minimum = [], math.inf
        coverage_polygons = []
        maximum_unseen_reach = 0.
        for interval in intervals:
            require(isinstance(interval, OccupancyInterval)
                    and finite(interval.start_s, interval.end_s)
                    and now <= interval.start_s <= interval.end_s
                    and interval.end_s-now <= 180., 'INVALID_EGO_OCCUPANCY_TIME')
            require(previous is None or abs(interval.start_s-previous) <= 1e-7,
                    'EGO_OCCUPANCY_TIME_GAP')
            previous = interval.end_s
            require(type(interval.polygons_xz) is tuple
                    and 1 <= len(interval.polygons_xz) <= 5,
                    'MISSING_EGO_BODY_ENVELOPE')
            end = interval.end_s+temporal_margin_s
            start = interval.start_s-temporal_margin_s
            require(snapshot.coverage_since_s <= start,
                    'TRAFFIC_TEMPORAL_HISTORY_INCOMPLETE')
            require(end <= snapshot.valid_until_s,
                    'TRAFFIC_PREDICTION_HORIZON_INCOMPLETE')
            unseen_reach = snapshot.unseen_speed_bound_mps*(end-snapshot.observed_at_s)
            for poly in interval.polygons_xz:
                _validate_convex_ring(poly)
                coverage_polygons.extend(poly)
            maximum_unseen_reach = max(maximum_unseen_reach, unseen_reach)
            for actor in snapshot.actors:
                predicted = predicted_polygons(actor, start, end)
                distance = min(polygon_distance_with_margin(
                                   ego, other, spatial_margin_m)
                                for ego in interval.polygons_xz for other in predicted)
                minimum = min(minimum, distance)
                if distance <= 1e-9:
                    conflicts.append(TrafficConflict(actor.actor_id, interval.start_s,
                        interval.end_s, distance, max(0., interval.start_s-now),
                        actor.confidence))
        # One convex superset is stricter than checking the cells separately:
        # if it fits, every timed ego polygon plus the maximum unseen-entrant
        # reach fits.  It avoids repeating the same polygon/surface search in
        # the worker and cannot create coverage that was absent.
        coverage_envelope = expand(
            hull(tuple(coverage_polygons)),
            maximum_unseen_reach + spatial_margin_m)
        require(clearance(coverage_envelope, coverage) > 0.,
                'TRAFFIC_COVERAGE_HORIZON_INCOMPLETE')
        # Merge only contiguous conflicts for the same actor, preserving gaps.
        merged = []
        for actor_id in sorted({c.actor_id for c in conflicts}):
            for conflict in (c for c in conflicts if c.actor_id == actor_id):
                if (merged and merged[-1].actor_id == actor_id
                        and abs(merged[-1].end_s-conflict.start_s) <= 1e-7):
                    old = merged.pop()
                    conflict = TrafficConflict(actor_id, old.start_s, conflict.end_s,
                        min(old.minimum_clearance_m, conflict.minimum_clearance_m),
                        old.time_to_conflict_s, min(old.confidence, conflict.confidence))
                merged.append(conflict)
        return TrafficWindow(not merged, 'TRAFFIC_CONFLICT' if merged else '',
            snapshot.snapshot_id, tuple(merged),
            None if math.isinf(minimum) else minimum,
            spatial_margin_m, temporal_margin_s,
            intervals[0].start_s, intervals[-1].end_s)
    except EnvelopeError as error:
        return TrafficWindow(False, str(error))
    except (AttributeError, TypeError, ValueError, OverflowError, IndexError):
        return TrafficWindow(False, 'MALFORMED_TRAFFIC_INPUT')
