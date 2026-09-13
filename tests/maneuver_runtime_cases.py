"""Explicit synthetic evidence for Phase 5D; never production certificates."""
from dataclasses import replace
from functools import lru_cache
import math

from core.navigation.maneuver_integration import build_maneuver_route_context, prepare_maneuver
from core.navigation.maneuver_planner import PlannerLimits
from core.navigation.lane_model import LaneConnection, LaneId, LanePath
from core.navigation.lane_trajectory import build_lane_trajectory
from core.navigation.road_network import RoadNetwork
from core.navigation.maneuver_runtime import LiveManeuverState, RuntimeRequest, TrackingEvidence
from core.navigation.maneuver_traffic import TrafficActor, TrafficObservation, TrafficSnapshot
from tests.maneuver_cases import junction
from tests.test_stage5c_maneuver_integration import (
    ground, profile, snapshot, surface_catalog, synthetic_network,
)


@lru_cache(maxsize=16)
def runtime_request(right=False, trailers=1, lane_type='prefab'):
    vehicle, start, path, source_surface, _ = junction(
        right=right, trailers=trailers, half_width=3.5)
    middle = replace(path.segments[1], lane_type=lane_type,
                     connector_curve_indices=path.segments[1].lane_id.connector_path)
    path = replace(path, segments=(path.segments[0], middle, path.segments[2]))
    if lane_type in ('merge','split'):
        middle_id=LaneId(102,1,0)
        first=replace(path.segments[0],successors=(LaneConnection(middle_id,lane_type),))
        middle=replace(path.segments[1],lane_id=middle_id,connector_curve_indices=(),
                       successors=(LaneConnection(path.segments[2].lane_id,lane_type),))
        path=build_lane_trajectory(LanePath((first,middle,path.segments[2]),(),
            path.source_gps_uids,confidence=path.confidence,valid=True,revision=path.revision))
    snap = snapshot(path)
    network = RoadNetwork() if lane_type in ('merge','split') else synthetic_network(path)
    context = build_maneuver_route_context(network, path, snap, 1)
    catalog = surface_catalog(context, source_surface)
    prof = profile(vehicle)
    ref = ground(start, context.identity, prof.token)
    limits = PlannerLimits(max_candidates=9)
    result = prepare_maneuver(network, path, snap, 1, catalog, prof, prof, ref,
        10., prof.token, 'synthetic accessory confirmation', limits)
    assert result.accepted, result.failure_reason
    tracking = TrackingEvidence('synthetic exact executor', 'a'*64, True, .05, .05, .05)
    return RuntimeRequest(result, network, path, snap, 1, catalog, prof, ref, tracking, limits)


def live_state(runtime, now=10., speed=0., sample_index=0, enabled=True):
    r = runtime.request
    sdk = 1_000_000+int(round((now-10.)*1_000_000))
    prof = replace(r.profile, observed_at=now,
                   observation=replace(r.profile.observation, sdk_frame_us=sdk,
                                       captured_at=now))
    frame = replace(r.result.plan.samples[sample_index].frame, time_s=now)
    ref = replace(r.ground, sdk_frame_us=sdk, observed_at=now, frame=frame)
    return LiveManeuverState(now, enabled, r.lane_path, dict(r.snapshot), prof, ref,
        speed, r.original_entry_tyre_rad, prof.token, 'synthetic confirmed configuration',
        now, now, runtime.binding)


def clear_traffic(identity, now=10., actors=(), sequence=None, horizon=180.):
    return TrafficSnapshot(identity, f'synthetic-{now}',
        int(round(now*1_000_000)) if sequence is None else sequence, now, now+horizon,
        tuple(actors), ((-20000.,-20000.), (20000.,-20000.),
                        (20000.,20000.), (-20000.,20000.)),
        True, 50., 'synthetic complete coverage', 'b'*64, now-2.)


def actor(actor_id='car', x=0., z=0., vx=0., vz=0., now=10., width=2., length=4.):
    speed = math.hypot(vx, vz)
    heading = math.atan2(-vx,-vz) if speed else 0.
    polygon=((x-width/2,z-length/2),(x+width/2,z-length/2),
             (x+width/2,z+length/2),(x-width/2,z+length/2))
    history = tuple(TrafficObservation(f'{actor_id}-{now-dt}', now-dt,
        x-vx*dt,z-vz*dt,heading,speed,vx,vz,
        (tuple((px-vx*dt,pz-vz*dt) for px,pz in polygon),))
        for dt in (2.,1.8,1.6,1.4,1.2,1.,.8,.6,.4,.2,0.))
    return TrafficActor(actor_id, history,(polygon,),
        'synthetic complete body bounds', 'c'*64, True, 1., .01, 0., 0., now+180.)
