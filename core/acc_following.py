"""Bounded protective ACC candidates; no clearance/coverage certification.

SDK world forward is (-sin yaw, -cos yaw); XYZ and gaps are metres,
speed is the legacy buffer's m/s channel, yaw radians. Receiver time is NOT
publisher freshness. Only lower speed demands are generated here, never pedals.
"""
import bisect
import math
import struct

from core.sdk.ets2la_data import _TRAFFIC_FMT, _PARKED_FMT, _yaw

MIN_GAP_M = 12.
HEADWAY_S = 2.
HORIZON_M = 120.
LATERAL_GATE_M = 1.2  # centreline relevance, NOT a physical corridor width
HEIGHT_GATE_M = 1.5  # uncertain chassis/path origins, NOT deck certification
RETENTION_M = 2.


def observation(capture, now):
    """Decode the very same bounded byte capture, without display fallbacks."""
    result = dict(status='unavailable', actors=[], receiver_time=capture.observed_at,
                  source_timestamp=None, source_sequence=None, complete=False,
                  atomic=False, confirmed=False)
    if not 0 <= now - capture.observed_at <= .1:
        result['status'] = 'stale_receiver_capture'
        return result
    if capture.moving is None or capture.parked is None:
        result['status'] = 'incomplete_buffers'
        return result
    if not capture.stable:
        result['status'] = 'changing_buffers'
        return result
    try:
        for source, data, stride in (
                ('moving', struct.unpack(_TRAFFIC_FMT, capture.moving), 46),
                ('parked', struct.unpack(_PARKED_FMT, capture.parked), 12)):
            for i in range(40):
                r = data[i*stride:(i+1)*stride]
                if r[0] == 0 and r[2] == 0:
                    continue
                q = r[3:7]
                if not all(math.isfinite(v) for v in r[:12]) or not .9 <= sum(v*v for v in q) <= 1.1:
                    result['status'] = 'invalid_actor'
                    return result
                result['actors'].append(dict(id=int(r[13] if source == 'moving' else r[10]),
                    x=r[0], y=r[1], z=r[2], yaw=_yaw(*q),
                    speed=r[10] if source == 'moving' else 0.,
                    speed_source='buffer' if source == 'moving' else 'parked_classification',
                    dimensions_whl=tuple(r[7:10]), source=source))
    except (ValueError, struct.error):
        result['status'] = 'invalid_buffer'
        return result
    ids = [a['id'] for a in result['actors']]
    # Moving/parked overlap is ambiguous, not resolved by list order.
    if len(ids) != len(set(ids)):
        result['status'] = 'ambiguous_actor_id'
        return result
    result['status'] = 'observed' if ids else 'empty_unproven_coverage'
    return result


class RouteLeadSelector:
    """One cached unchanged LanePath, bounded local projections, one target ID."""
    def __init__(self):
        self.binding = None
        self.points = ()
        self.arcs = ()
        self.edges = ()
        self.target_id = None

    def reset(self):
        self.target_id = None

    def prepare(self, points, binding):
        if binding == self.binding:
            return
        self.binding = None
        self.reset()
        if not 2 <= len(points) <= 20000:
            raise ValueError('unsupported ACC route size')
        pts = tuple(tuple(float(v) for v in p) for p in points)
        if any(len(p) != 3 or not all(math.isfinite(v) for v in p) for p in pts):
            raise ValueError('ACC requires original finite XYZ route')
        arcs, edges = [0.], []
        for a, b in zip(pts, pts[1:]):
            length = math.hypot(b[0]-a[0], b[2]-a[2])
            if length <= 1e-6:
                raise ValueError('degenerate ACC route edge')
            edges.append((*a, b[0]-a[0], b[1]-a[1], b[2]-a[2], length,
                          1./length, 1./(length*length), arcs[-1]))
            arcs.append(arcs[-1]+length)
        self.points, self.arcs, self.edges, self.binding = pts, tuple(arcs), tuple(edges), binding

    def _project(self, actor, low, high):
        x, y, z, yaw = (float(actor[k]) for k in ('x', 'y', 'z', 'yaw'))
        if not all(math.isfinite(v) for v in (x, y, z, yaw)):
            return None
        first = max(0, bisect.bisect_right(self.arcs, low)-1)
        last = min(len(self.points)-1, bisect.bisect_left(self.arcs, high)+1)
        if last-first > 512:
            return None  # bounded work; never silently simplify dense geometry
        projections = []
        forward_x, forward_z = -math.sin(yaw), -math.cos(yaw)
        minimum_alignment = math.cos(math.radians(45.))
        for i in range(first, last):
            ax, ay, az, dx, dy, dz, length, inverse, inverse2, start = self.edges[i]
            alignment = (forward_x*dx+forward_z*dz)*inverse
            if alignment < minimum_alignment:
                continue
            offset_x, offset_z = x-ax, z-az
            raw_t = (offset_x*dx+offset_z*dz)*inverse2
            if raw_t*length < -.5 or (raw_t-1.)*length > .5:
                continue  # cannot clip a behind/end-of-horizon actor onto us
            t = max(0., min(1., raw_t))
            distance = math.hypot(offset_x-t*dx, offset_z-t*dz)
            height = abs(y-ay-t*dy)
            progress = start+t*length
            if height <= HEIGHT_GATE_M and low <= progress <= high:
                projections.append((distance, progress, height))
        if not projections:
            return None
        projections.sort()
        best = projections[0]
        if any(abs(p[1]-best[1]) > 8. and p[0] <= best[0]+.2 for p in projections[1:]):
            return None  # repeated loop/crossing occurrence cannot be resolved
        return best

    def select(self, actors, truck, progress):
        if not math.isfinite(progress) or not 0 <= progress <= self.arcs[-1]:
            return dict(status='invalid_route_progress', confirmed=False)
        if len(actors) > 80:
            return dict(status='unsupported_actor_count', confirmed=False)
        ego = self._project(dict(truck, yaw=truck['rotation']), max(0., progress-20.), progress+20.)
        if ego is None or ego[0] > LATERAL_GATE_M:
            return dict(status='route_localization_unavailable', confirmed=False)
        candidates = []
        ids = [a.get('id') for a in actors]
        if any(i is None for i in ids) or len(ids) != len(set(ids)):
            return dict(status='ambiguous_actor_id', confirmed=False)
        for actor in actors:
            try:
                speed = float(actor['speed'])
                if not math.isfinite(speed) or not 0 <= speed <= 70.:
                    continue
                projected = self._project(actor, max(0., ego[1]-5.), ego[1]+HORIZON_M)
                if projected is None or projected[0] > LATERAL_GATE_M:
                    continue
                gap = projected[1]-ego[1]
                if gap < 0.:
                    continue
                candidates.append((gap, str(actor['id']), speed))
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
        if not candidates:
            return dict(status='no_candidate_unproven_coverage', confirmed=False)
        candidates.sort()
        nearest = candidates[0]
        retained = next((c for c in candidates if c[1] == self.target_id), None)
        selected = retained if retained and retained[0] <= nearest[0]+RETENTION_M else nearest
        # Retention changes attribution only: all relevant candidates always cap
        # speed and emergency response, so a closer cut-in is never hidden.
        self.target_id = selected[1]
        constraints = [following_demand(c[0], c[2], float(truck['speed'])) for c in candidates]
        return dict(status='candidate', target_id=selected[1], gap_m=selected[0],
                    speed_mps=selected[2], confirmed=False,
                    gap_kind='route_reference_points',
                    speed_cap_mps=min(c['speed_cap_mps'] for c in constraints),
                    emergency=any(c['emergency'] for c in constraints),
                    reason='projected receiver observation; publisher freshness and lane membership unproven')


def following_demand(gap_m, lead_speed_mps, ego_speed_mps):
    """Time-gap speed constraint for the existing PID, not another controller."""
    if not all(math.isfinite(v) and v >= 0 for v in (gap_m, lead_speed_mps, ego_speed_mps)):
        raise ValueError('invalid following kinematics')
    desired = MIN_GAP_M + HEADWAY_S*ego_speed_mps
    closing = max(0., ego_speed_mps-lead_speed_mps)
    cap = max(0., lead_speed_mps + (gap_m-desired)/HEADWAY_S)
    # Preserve Engine's existing emergency boundary (>0.7 legacy TTC demand),
    # now measured along the route rather than the straight cab strip. Ordinary
    # distance braking is replaced by the existing speed PID, not safety floors.
    safety_gap = max(0., gap_m-(6.+.4*ego_speed_mps))
    if closing >= .5:
        ttc = safety_gap/closing
        legacy_demand = 1. if ttc <= 1. else ((5.-ttc)/4.)**2 if ttc < 5. else 0.
    else:
        legacy_demand = max(0., 1.-safety_gap/40.)
    emergency = legacy_demand > .7
    return dict(speed_cap_mps=cap, desired_gap_m=desired, emergency=emergency)
