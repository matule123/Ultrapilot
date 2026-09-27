"""Authored simulation lanes, never production survey evidence."""
from collections import deque
from dataclasses import replace
import math
import numpy as np

from core.navigation.drivable_surface import build_confirmed_surface
from core.navigation.lane_model import LaneId, LanePoint, LaneSegment, LanePath
from core.navigation.lane_trajectory import _with_kinematics
from core.navigation.route import Route
from core.navigation.trailer_guidance import TrailerGeometry, UsableLaneCorridor
from core.steering_dynamics import SteeringDynamics
from core.swept_envelope import Identity
from tests.steering_bench import path as bench_path
from tests.test_stage5b2_drivable_surface import record


def case(radius=80., sign=1., length=8., half_width=2.75,
         sections=None):
    sections = (sections if sections is not None else
                ((0., 40.), (sign/radius, radius*.6+10.), (0., 75.)))
    data = bench_path(sections, transition=12.)
    lane = LaneId(101, 1, 0)
    points = _with_kinematics(tuple(LanePoint(x, 0., z, lane_id=lane, segment_index=0)
                                    for x, z in data['points']))
    segment = LaneSegment(lane, 1, 2, 1, 0, 1, 2*half_width, 'derived', 6,
                          'fixture', 'road', points, gps_pair_index=0)
    path = LanePath((segment,), points, (1, 2), points[-1].s, .99, True, revision=8)
    identity = Identity('synthetic', 8, 'build', 'session', 'fixture-map', 'fixture-data',
                        'elevation:6', (lane,), ((1, 2),))
    # Independently authored lane boundary with entry/exit support for the rig.
    side = []
    sample = list(points[::12])
    if sample[-1] != points[-1]:
        sample.append(points[-1])
    for direction in (-1, 1):
        row = [(p.x-direction*half_width*math.cos(p.heading), 0.,
                p.z+direction*half_width*math.sin(p.heading)) for p in sample]
        h0, h1 = points[0].heading, points[-1].heading
        row.insert(0, (row[0][0]+30*math.sin(h0), 0., row[0][2]+30*math.cos(h0)))
        row.append((row[-1][0]-20*math.sin(h1), 0., row[-1][2]-20*math.cos(h1)))
        side.append(row)
    raw = record(path, identity, y=0., uncertainty=.03)
    raw['exterior_xyz'] = side[0]+side[1][::-1]
    surface = build_confirmed_surface(raw, path, identity, identity)
    assert not surface.failure_reason, surface.failure_reason
    model = TrailerGeometry(3.8, 0., length, 'c'*64, 'synthetic calibrated single axle', True)
    corridor = UsableLaneCorridor(surface, identity.lanes,
        'synthetic authored same-lane edges; not ETS2 evidence', 'a'*64, True)
    return path, identity, model, corridor


def simulate(path, model, reference=None, *, speed=5., lag=.32, delay=.10,
             noise=False, jitter=False, corridor=None):
    """Independent time-domain bicycle+trailer plant with <=5 ms substeps.

    Calls production Route.steering and one SteeringDynamics. No production
    spatial predictor is used to evolve or measure the plant.
    """
    points = np.array([(p.x, p.z) for p in path.points])
    edges = np.diff(points, axis=0)
    lens = np.sum(edges*edges, axis=1)
    ss = np.array([p.s for p in path.points])

    def project(pos):
        u = np.clip(np.sum((pos-points[:-1])*edges, axis=1)/lens, 0., 1.)
        r = pos-points[:-1]-u[:, None]*edges
        i = int(np.argmin(np.sum(r*r, axis=1)))
        return ((r[i, 0]*edges[i, 1]-r[i, 1]*edges[i, 0])/math.sqrt(lens[i]),
                ss[i]+u[i]*(ss[i+1]-ss[i]))

    route = reference or Route([(p.x, p.y, p.z) for p in path.points])
    dynamics = SteeringDynamics()
    pos = points[0].copy()
    h = path.points[0].heading
    trailer_h = h
    game = target = t = 0.
    queue = deque()
    rows = []
    while t < (ss[-1]+10)/speed:
        i = len(rows)
        dt = .05+(.007*math.sin(i*.7) if jitter else 0.)
        measured = pos + (np.array((.04*math.sin(7*t), .02*math.sin(11*t))) if noise else 0.)
        mh = h+(math.radians(.25)*math.sin(9*t) if noise else 0.)
        raw = route.steering(tuple(measured), mh, speed, control_dt_s=dt,
                vehicle_curvature_per_m=math.tan(.78*game)/model.wheelbase_m,
                reference_geometry={'valid': True, 'source': 'plant',
                    'wheelbase_m': model.wheelbase_m, 'reference_ahead_m': 0.})
        assert route.last_steering_debug['authority_valid']
        out = dynamics.update(raw, dt, speed_ms=speed,
                             curvature_per_m=route.last_steering_debug['local_curvature'])
        queue.append((t+delay, out))
        cte, progress = project(pos)
        hitch = pos-model.hitch_ahead_m*np.array((math.sin(h), math.cos(h)))
        axle = hitch+model.hitch_to_axle_m*np.array((math.sin(trailer_h), math.cos(trailer_h)))
        tr_cte, _ = project(axle)
        j = min(len(path.points)-1, int(np.searchsorted(ss, progress)))
        heading_error = (h-path.points[j].heading+math.pi) % math.tau-math.pi
        rows.append((progress, cte, tr_cte, out, *pos, *axle,
                     heading_error, t, game))
        if progress >= ss[-1]-2:
            break
        sub = math.ceil(dt/.005)
        ds = dt/sub
        for j in range(sub):
            while queue and queue[0][0] <= t+j*ds:
                _, target = queue.popleft()
            game += (target-game)*(1-math.exp(-ds/lag))
            yaw = -speed*math.tan(.78*game)/model.wheelbase_m
            vx, vz = -speed*math.sin(h), -speed*math.cos(h)
            hx = vx-model.hitch_ahead_m*yaw*math.cos(h)
            hz = vz+model.hitch_ahead_m*yaw*math.sin(h)
            tr_yaw = (-hx*math.cos(trailer_h)+hz*math.sin(trailer_h))/model.hitch_to_axle_m
            pos += ds*np.array((-speed*math.sin(h+yaw*ds/2), -speed*math.cos(h+yaw*ds/2)))
            h += yaw*ds
            trailer_h += tr_yaw*ds
        t += dt
    rows = np.asarray(rows)
    tail = rows[rows[:, 0] > ss[-1]-15]
    turn_end = max((p.s for p in path.points if abs(p.curvature) > .001),
                   default=0.)
    exit_rows = rows[rows[:, 0] >= turn_end]
    settling_time = None
    for i, row in enumerate(exit_rows):
        if (max(abs(exit_rows[i:, 1])) <= .1
                and max(abs(exit_rows[i:, 2])) <= .1
                and max(abs(exit_rows[i:, 8])) <= math.radians(1.)):
            settling_time = float(row[9]-exit_rows[0, 9])
            break
    result = {'cab_max_cte_m': float(max(abs(rows[:, 1]))),
            'trailer_max_cte_m': float(max(abs(rows[:, 2]))),
            'steering_step': float(max(abs(np.diff(rows[:, 3])))),
            'steering_rate_per_s': float(max(abs(np.diff(rows[:, 3])
                                             / np.diff(rows[:, 9])))),
            'heading_max_error_rad': float(max(abs(rows[:, 8]))),
            'settling_time_s': settling_time,
            'placement_width_used_m': float(2*(max(abs(rows[:, 1]).max(),
                                               abs(rows[:, 2]).max())+.75)),
            'exit_cab_cte_m': float(max(abs(tail[:, 1]))),
            'exit_trailer_cte_m': float(max(abs(tail[:, 2]))),
            'completed': bool(rows[-1, 0] >= ss[-1]-2)}
    if corridor is not None:
        # Independent point-to-boundary calculation on the ACTUAL plant poses.
        # The radius encloses the planner's square uncertainty/motion budget.
        from core.swept_envelope import inside
        surface = corridor.boundary.surface
        minimum = math.inf
        for ring in (surface.exterior,)+surface.holes:
            a = np.asarray(ring)
            d = np.roll(a, -1, axis=0)-a
            q = np.sum(d*d, axis=1)
            for pos in np.concatenate((rows[:, 4:6], rows[:, 6:8])):
                u = np.clip(np.sum((pos-a)*d, axis=1)/q, 0., 1.)
                distance = float(np.sqrt(np.min(np.sum((pos-a-u[:, None]*d)**2, axis=1))))
                if not inside(tuple(pos), surface.exterior) or any(inside(tuple(pos), hole) for hole in surface.holes):
                    distance = -distance
                minimum = min(minimum, distance)
        result['minimum_axle_corridor_reserve_m'] = minimum-math.sqrt(2)*(
            .25+model.uncertainty_m+corridor.boundary.boundary_uncertainty_m+.55)
    return result, rows
