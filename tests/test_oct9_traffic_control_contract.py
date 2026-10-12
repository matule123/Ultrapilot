"""Original route prefix, modeled actors/SDK, actual producer/Controller calls.

Actor injections are code counterexamples, NOT recovered historical traffic.
The supplied constant Y is a model input; the stored original route is X/Z.
"""
import json
import math
import struct
from dataclasses import replace
from pathlib import Path

import pytest

from core.acc_following import observation
from core.longitudinal import context,publish
from core.sdk.ets2la_data import ETS2LAData,_TRAFFIC_FMT
from tests.test_acc_following import capture
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct8_stop_lifecycle import directed_stop
from tests.test_roundabout_intervention_reporting import pedal


def setup_route(flow,mode,progress=0.):
    values,step=directed_stop(flow,mode)
    state,truck,engine,ap,tick,n,clock,writes,collected=values
    raw=json.loads((Path(__file__).parent/'fixtures/oct8-observed-route-prefix.json').read_text())
    points=[[x,10.,z] for x,z in raw['points_xz']]
    lane=state.get('lane_trajectory');lane['points']=points
    state.set('lane_trajectory',lane);state.set('lane_trajectory_publication_token','original-oct8-prefix')
    identity={k:lane[k] for k in ('source_game_session_id','source_map_key',
        'source_dataset_fingerprint','navigation_intent_id','revision','route_build_id')}
    state.set('lane_trajectory_identity',identity)
    packet=state.get('nav_steering_debug');packet['trajectory_identity']=identity
    state.set('nav_steering_debug',packet)
    from core.navigation.route import Route
    route=Route(raw['points_xz']);a=route._point_at_progress(progress);b=route._point_at_progress(progress+1.)
    truck.update(x=a[0],y=10.,z=a[1],rotation=math.atan2(-(b[0]-a[0]),-(b[1]-a[1])))
    packet=state.get('nav_steering_debug');packet['tracking_progress_m']=progress
    state.set('nav_steering_debug',packet)
    flow[4](4,40/3.6,dt=.05);state.set('truck_speed_ms',40/3.6)
    return values


def produce(values,actors,*,invalid=False,duplicate=False):
    state,truck,engine,ap,tick,n,clock,writes,collected=values
    binding=context(state)
    cap=replace(capture(actors,clock[0]),session=str(binding[1]))
    if invalid:
        fields=list(struct.unpack(_TRAFFIC_FMT,cap.moving));fields[3:7]=[0.,0.,0.,0.]
        cap=replace(cap,moving=struct.pack(_TRAFFIC_FMT,*fields))
    reader=ETS2LAData();reader._ensure=lambda:None
    reader._traffic_buf=cap.moving;reader._parked_buf=cap.parked
    # Real legacy decoder currently accepts/defaults this phantom; current
    # production then keeps its brake even though the source validator rejects.
    displayed=reader.read_traffic()
    actual=state.get('telemetry')['truck']
    following,brake=engine._traffic_control_observation(cap,actual,binding,displayed)
    publish(state,actual,'traffic',traffic_brake=brake,light_brake=0.,light=None,
        following=following,brake_basis=engine._traffic_brake_basis,
        dependencies=following.get('deadline_dependencies',()),
        expires_at=following.get('expires_at',float('inf')))
    tick.policy.on_tick(.05);tick.acc.on_tick(.05);ap.on_tick(.05);engine._flush_controls()
    return observation(cap,clock[0]),following,brake


def forward_actor(values,lateral=0.,actor_id=71):
    t=values[1];h=t['rotation']
    return dict(id=actor_id,x=t['x']-40.*math.sin(h)+lateral*math.cos(h),
        y=10.,z=t['z']-40.*math.cos(h)-lateral*math.sin(h),yaw=h,speed=1.)


@pytest.mark.parametrize('mode',[0,3])
@pytest.mark.parametrize('fault',['quaternion','duplicate'])
def test_invalid_capture_cannot_create_a_phantom_brake(flow,mode,fault):
    values=setup_route(flow,mode);actors=[forward_actor(values)]
    if fault=='duplicate':actors.append(forward_actor(values,lateral=2.,actor_id=71))
    observed,following,brake=produce(values,actors,invalid=fault=='quaternion')
    assert observed['status'] in ('invalid_actor','ambiguous_actor_id')
    assert brake == 0.
    assert pedal(values[2],'abackward') == 0.


@pytest.mark.parametrize('mode',[0,3])
def test_tangent_vehicle_off_actual_curved_route_is_not_a_legacy_lane_brake(flow,mode):
    values=setup_route(flow,mode,progress=520.);values[0].set('longitudinal_acc_active',False)
    actor=forward_actor(values,lateral=2.)
    legacy=values[2]._lead_brake([actor],(values[1]['x'],values[1]['z']),values[1]['rotation'],40/3.6)
    assert legacy>0.2  # Before path: positive floor on imaginary cab extension.
    observed,following,brake=produce(values,[actor])
    assert observed['status'] == 'observed'
    assert following['status']=='no_candidate_unproven_coverage'
    assert brake == 0. and pedal(values[2],'abackward') == 0.


def test_empty_observation_is_not_clearance_and_does_not_brake(flow):
    values=setup_route(flow,0)
    observed,following,brake=produce(values,[])
    assert observed['status']=='empty_unproven_coverage'
    assert following['status']=='no_candidate_unproven_coverage'
    assert brake == 0.
    assert following['confirmed'] is False
