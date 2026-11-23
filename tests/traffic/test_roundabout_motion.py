"""Original time-stamped native traffic, modeled activation/SDK transport."""
import copy
import json
from pathlib import Path
import math
from unittest.mock import patch
import pytest
from tests.lifecycle.test_joint_regressions import joint  # noqa: F401
from tests.test_activation_observation_binding import flow  # noqa: F401
from tools.reproduce_roundabout_prediction import apply_frame


def fixture():
    return json.loads((Path(__file__).resolve().parents[1]/'fixtures/nov2-roundabout-native.json').read_bytes())


def install(joint):
    from core.navigation.lane_model import LaneId
    state,engine,ap,acc,policy,tick,_,n,physical,writes,clock=joint
    n()  # Cancel the generic fixture activation before changing its route.
    data=fixture();lane=copy.deepcopy(data['lane']);lane['actor_motion']=data['graph']
    identity={k:lane[k] for k in ('source_game_session_id','source_map_key',
        'source_dataset_fingerprint','navigation_intent_id','revision','route_build_id')}
    state.update_batch(dict(lane_trajectory=lane,lane_trajectory_revision=lane['revision'],nav_trajectory_revision=lane['revision'],
        lane_trajectory_identity=identity,lane_trajectory_publication_token='original-map-offline',
        lane_trajectory_longitudinal_identity=dict(identity,geometry_token='original-map-offline'),
        game_session_id=lane['source_game_session_id'],active_map_key=lane['source_map_key'],
        active_dataset_fingerprint=lane['source_dataset_fingerprint'],
        navigation_intent_id=lane['navigation_intent_id'],nav_recalc_request=lane['request_id'],
        game_route_node_uids=lane['source_gps_uids'],lane_match=lane['lane_match'],
        navigation_unreliable=False,nav_active=True,system_state='CRUISE'))
    debug=state.get('nav_steering_debug')
    debug.update({k:lane[k] for k in identity if k!='revision'})
    debug.update(trajectory_identity=identity,authority_revision=lane['revision'],
        revision=lane['revision'],
        authority_lane_id=LaneId(**lane['active_lane_id']).sort_key(),authority_valid=True,
        lane_match_snapshot=lane['lane_match'])
    state.set('nav_steering_debug',debug)
    first=data['frames'][0];clock[0]=first['at_s']
    evidence=state.get('ets2_transmission_mode');evidence['observed_at']=clock[0]
    state.set('ets2_transmission_mode',evidence)
    return data


def test_original_roundabout_prediction_and_signed_stop_use_one_production_path(joint):
    from core.longitudinal import context
    state,engine,ap,acc,policy,tick,_,n,physical,writes,clock=joint
    data=install(joint)
    predicted=[];faults=[];native_signed=[]
    for index,frame in enumerate(data['frames']):
        clock[0]=frame['at_s']
        following,brake,capture=apply_frame(state,engine,frame,modeled_forward_gear=True)
        assert following['status'] in ('candidate','no_candidate_unproven_coverage'),following
        if index==0:
            state.set('autopilot_navigation_readiness',dict(ready=True,timestamp=clock[0],source='gps_lane',revision=11))
            n()
        signal=copy.deepcopy(frame['original_packet']['signal'])
        truck=state.get('telemetry')['truck']
        engine._publish_traffic_control(truck,truck['_control_observation']['observed_at'],
            context(state),[],capture,following,brake,signal,None)
        policy.on_tick(.05);acc.on_tick(.05);ap.on_tick(.05);engine._flush_controls()
        if not state.get('longitudinal_acc')['valid']:faults.append(state.get('longitudinal_acc')['invalid_reason'])
        if capture.source['ego_speed_mps']<0:
            native_signed.append(capture.source['ego_speed_mps'])
            assert following['body_prediction']['prediction_duration_s']==3.
        actor=next((a for a in engine._acc_selector._native_current[1].values() if a['id']==61),None)
        if actor:
            model=getattr(engine._acc_selector,'actor_motion',lambda actor:None)(actor)
            if model:predicted.append((clock[0],model))
    assert predicted,'the recorded turning actor must use authored directed branches'
    assert native_signed and not faults,faults
    assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
    assert not (physical('aforward')>0. and physical('abackward')>0.)


def test_directed_curve_hypotheses_are_not_a_straight_ray_through_the_roundabout(joint):
    state,engine,ap,acc,policy,tick,_,n,physical,writes,clock=joint
    data=install(joint);selected=None
    for frame in data['frames']:
        if frame['capture']['source']['observed_at']>8431.6835558:break
        clock[0]=frame['at_s'];following,brake,capture=apply_frame(state,engine,frame)
        assert following['status'] in ('candidate','no_candidate_unproven_coverage'),following
        actor=engine._acc_selector._native_current[1].get(61)
        if actor:
            model=getattr(engine._acc_selector,'actor_motion',lambda actor:None)(actor)
            if model:selected=(actor,model,following)
    assert selected,'must use causal original native history and authored PPD curves'
    actor,model,following=selected
    assert model['exit_intent_verified'] is False
    assert model['branches']
    # The graph, not a future replay point, causes a nonzero change of heading.
    assert any(abs(math.remainder(p[3]-actor['yaw'],2*math.pi))>.2
        for branch in model['branches'] for p in branch['poses'][:13])
    assert all(c['motion_model']==model['model'] for c in following['crossing']['conflicts'] if c['id']==61)
