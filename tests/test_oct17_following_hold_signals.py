"""New deployed-1.3.8 counterexamples; backend output is not ETS2 consumption."""
import math
import os
from unittest.mock import patch

import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct11_joint_regressions import joint  # noqa: F401
from tests.test_oct14_completion import timed_step
from tests.test_oct15_crossing_dev_hud import step, crossing


@pytest.fixture(autouse=True)
def entry_runtime(monkeypatch):
    """Unchanged new assertions against the receipt-matching entry methods."""
    if os.environ.get('UP_OCT17_FOLLOW_BASELINE')!='1':return
    import ast
    import importlib
    from pathlib import Path
    import zipfile
    root=Path(__file__).resolve().parents[1]
    archive=root/'docs/steering-audit/oct17-following-hold-signals/entry-runtime.zip'
    methods={'core.acc_following':('RouteLeadSelector',['crossing_completion']),
        'core.sdk.signal_snapshot':('RouteSignalSelector',['select']),
        'core.engine':('UltraPilotEngine',['_check_hotkey_unlocked','_process_autopilot_command_unlocked'])}
    functions={'core.acc_body_prediction':['predict'],
        'core.longitudinal':['stopping_brake_continuity_required'],
        'core.service_brake_hold':['profile_approach_allowed']}
    with zipfile.ZipFile(archive) as saved:
        for name in functions.keys()|methods.keys():
            module=importlib.import_module(name)
            tree=ast.parse(saved.read(name.replace('.','/')+'.py').decode('utf-8-sig'))
            owner=module;body=tree.body
            wanted=functions.get(name)
            if wanted is None:
                cls,wanted=methods[name];owner=getattr(module,cls)
                body=next(n.body for n in body if isinstance(n,ast.ClassDef) and n.name==cls)
            assert set(wanted)<=set(n.name for n in body if isinstance(n,ast.FunctionDef))
            for node in body:
                if isinstance(node,ast.FunctionDef) and node.name in wanted:
                    env={};exec(compile(ast.Module(body=[node],type_ignores=[]),'entry/'+name,'exec'),vars(module),env)
                    monkeypatch.setattr(owner,node.name,env[node.name])


def test_original_crossing_completion_is_not_blocked_by_another_body(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    original=crossing(at=32.,arrival=4.1,aid=57)
    step(joint,[original],1)
    assert acc._following_target_id=='57'
    turned=dict(original,x=original['x']+1.1,yaw=math.pi)
    # Current observed original 57 has ended its crossing model. A separate
    # crossing hazard 73 still must brake; it cannot keep 57's model alive.
    hazard=dict(id=73,x=-3.,y=10.,z=18.,yaw=-math.pi/2,speed=4.)
    following=timed_step(joint,[turned,hazard],generation=2,
        ego=[(2.25,10.,15.,0.,0.,1.,0.,2.5,4.,6.)])
    assert any(c['id']==73 for c in following['body_prediction']['conflicts'])
    assert any(p['target_id']=='57' for p in following.get('constraint_completions',
        [following.get('constraint_completion')]) if p)
    assert state.get('autopilot_active'),state.get('autopilot_intervention')
    assert not acc._following_fault and not acc._followed_target
    assert physical('aforward')==0. and physical('abackward')>0.


@pytest.mark.parametrize('mode',[0,3])
def test_reactivation_clears_owned_hazards_before_route_indicator(flow,mode):
    state,truck,engine,ap,publish,n,clock=flow
    evidence=state.get('ets2_transmission_mode');evidence.update(mode=mode,generation=f'profile:{mode}')
    state.set('ets2_transmission_mode',evidence)
    state.set('safety_hazard_active',True)  # previous technical intervention
    n()
    assert state.get('auto_drive_pending')
    assert state.get('safety_hazard_active') is False
    publish();engine._flush_controls()  # actual D/probe precedes confirmation
    publish(4,.3);engine._flush_controls()
    assert state.get('autopilot_active')


@pytest.mark.parametrize('mode',[0,3])
def test_slow_zero_ratio_stop_never_releases_admitted_terminal_brake(flow,tmp_path,mode):
    from tests.test_oct10_signal_timing import timing_flow
    from tests.test_roundabout_intervention_reporting import pedal
    values,signal_step=timing_flow(flow,tmp_path,mode)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    signal_step(30,'red',speed=1.775,progress=39.17)
    assert pedal(engine,'abackward')>0.
    start=len(writes)
    for gen,speed,distance in ((31,.6689,1.4),(32,.5685,1.24),(33,.476,1.1),
            (34,.454,.98),(35,.325,.8),(36,.071,.66),(37,.004,.65),(38,0.,.65)):
        signal_step(gen,'red',speed=speed,gear=0 if (gen>=34 and mode==0) or gen>=37 else 4,progress=42.-distance)
        assert state.get('autopilot_active'),state.get('autopilot_intervention')
    brakes=[v for _,ch,v,_ in writes[start:] if ch=='abackward']
    assert brakes and all(v>0. for v in brakes),brakes
    assert pedal(engine,'aforward')==0.


def test_rear_closing_body_does_not_create_forward_stop(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    rear=dict(id=52,x=2.25,y=10.,z=0.,yaw=math.pi,speed=8.)
    following=timed_step(joint,[rear],generation=1,speed=1.,z=15.,
        ego=[(2.25,10.,15.,0.,1.,0.,0.,2.5,4.,6.),(2.25,10.,7.,0.,1.,0.,0.,2.5,4.,8.)])
    assert following['body_prediction']['brake']==0.,following['body_prediction']
    assert not engine._service_brake_hold
    assert state.get('autopilot_active') and physical('abackward')==0.


@pytest.mark.parametrize('mode',[0,3])
def test_ending_green_cannot_alternate_dilemma_and_stop_in_last_metres(flow,tmp_path,mode):
    from tests.test_oct10_signal_timing import timing_flow
    values,signal_step=timing_flow(flow,tmp_path,mode)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    signal_step(30,'green',speed=1.775,progress=38.5,remaining=3.)
    signal_step(31,'green',speed=1.775,progress=39.17,remaining=2.)
    hold=state.get('simple_auto_service_hold')
    assert hold and hold['brake']>0.
    start=len(writes)
    for gen,speed,distance,remaining in ((32,.6013,1.94,1.),(33,.5685,1.24,.1),
            (34,.476,1.1,.05),(35,.454,.98,.01),(36,.071,.66,0.),(37,.004,.65,0.)):
        signal_step(gen,'green' if gen<35 else 'red',speed=speed,
            gear=0 if mode==0 and gen>=35 or gen>=37 else 4,
            progress=42.-distance,remaining=remaining)
        assert state.get('autopilot_active'),state.get('autopilot_intervention')
    brakes=[v for _,ch,v,_ in writes[start:] if ch=='abackward']
    assert all(v>0. for v in brakes),brakes
    for gen in range(38,47):signal_step(gen,'green',speed=0.,gear=0,progress=41.35,remaining=60.)
    assert state.get('autopilot_active'),state.get('autopilot_intervention')
    assert state.get('simple_auto_service_hold') is None


@pytest.mark.parametrize('mode',[0,3])
def test_actual_rear_capture_cannot_latch_red_hold_after_new_green(flow,tmp_path,mode):
    from types import SimpleNamespace
    from core.longitudinal import context
    from core.sdk.traffic_snapshot import TrafficReader
    from core.navigation.traffic_producer import capture_traffic
    from tests.test_acc_following import capture
    from tests.test_oct14_completion import native_bytes
    from tests.test_oct10_signal_timing import timing_flow
    from tests.test_roundabout_intervention_reporting import pedal
    values,signal_step=timing_flow(flow,tmp_path,mode)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    original_publish=__import__('tests.test_oct10_signal_timing',fromlist=['publish']).publish
    def publish_with_actual_capture(state_,actual,source,**kwargs):
        if source!='traffic':return original_publish(state_,actual,source,**kwargs)
        fw=(-math.sin(actual['rotation']),-math.cos(actual['rotation']))
        def pos(distance):return actual['x']+distance*fw[0],actual['z']+distance*fw[1]
        x,z=pos(-18.)
        actor=dict(id=52,x=x,y=actual['y']+1.,z=z,yaw=actual['rotation'],speed=2.)
        raw=capture([actor],clock[0]);reader=SimpleNamespace(_timed_traffic_reader=TrafficReader())
        bodies=[]
        for distance,length in ((0.,6.),(-7.,14.)):
            x,z=pos(distance);bodies.append((x,actual['y']+2.,z,
                math.cos(actual['rotation']/2),0.,math.sin(actual['rotation']/2),0.,2.5,4.,length))
        reader._timed_traffic_reader.buffer=native_bytes(raw,clock[0],kwargs['signal']['generation'],
            actual['sdkFrameTimeUs'],ego=bodies,anchor=(actual['x'],actual['y'],actual['z']),ego_speed=abs(actual['speed']))
        used=capture_traffic(reader,str(context(state)[1]),clock[0])
        identity=state.get('lane_trajectory_identity')
        debug=state.get('nav_steering_debug');debug.update(trajectory_identity=identity,authority_valid=True)
        state.set('nav_steering_debug',debug)
        following,brake=engine._traffic_control_observation(used,actual,context(state),[])
        assert 'body_prediction' in following,following
        assert following['body_prediction']['status']=='protective_observed_body_prediction',following
        if actual['speed']==0.:
            assert (following['body_prediction'].get('non_braking_rear_contacts')
                or any(c['id']==52 for c in following['body_prediction']['conflicts']))
        engine._publish_traffic_control(actual,actual['_control_observation']['observed_at'],context(state),
            [],used,following,brake,kwargs['signal'],None)
    with patch('tests.test_oct10_signal_timing.publish',publish_with_actual_capture):
        signal_step(30,'red',speed=3.,progress=35.)
        for gen in range(31,36):signal_step(gen,'red',speed=0.,gear=0,progress=35.)
        assert state.get('autopilot_active') and pedal(engine,'abackward')>0.
        for gen in range(36,46):signal_step(gen,'green',speed=0.,gear=0,progress=35.)
        # A real-auto D request is only a request; confirm the actual forward
        # observation before expecting its speed regulator to apply drive.
        for gen in range(46,50):signal_step(gen,'green',speed=.2,gear=4,progress=35.)
    assert state.get('autopilot_active'),state.get('autopilot_intervention')
    assert state.get('simple_auto_service_hold') is None
    assert pedal(engine,'abackward')==0. and pedal(engine,'aforward')>0.


@pytest.mark.parametrize('kind',['forward','crossing','overlap'])
def test_nonmitigating_rear_classification_never_hides_real_aeb(joint,kind):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    actor=(dict(id=73,x=2.25,y=10.,z=25.,yaw=math.pi,speed=0.) if kind=='forward' else
        dict(id=73,x=-3.,y=10.,z=18.,yaw=-math.pi/2,speed=4.) if kind=='crossing' else
        dict(id=73,x=2.25,y=10.,z=15.,yaw=math.pi,speed=12.))
    following=timed_step(joint,[actor],generation=1,speed=10.,
        ego=[(2.25,10.,15.,0.,1.,0.,0.,2.5,4.,6.)])
    assert following['body_prediction']['brake']>0.
    assert not following['body_prediction'].get('non_braking_rear_contacts')
    assert physical('aforward')==0. and physical('abackward')>0.


def test_reactivated_indicator_reaches_button_and_subsequent_stable_feedback(joint,monkeypatch):
    from sdk.plugin_sdk import PluginSDK
    from plugins.turnsignals.main import Plugin as Signals
    from tests.test_oct11_joint_regressions import topology_events
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    monkeypatch.setattr('core.controller._HAS_PDI',False)
    n();tick(gear=0,speed=0.,pedals=False);engine._flush_controls()
    state.set('safety_hazard_active',True)
    engine.controller.current_hazard=True  # the preceding owned intervention
    edges=[];game=dict(hazard=True,right=False,left=False)
    original=engine.controller.scs._write_bool
    def write(channel,value):
        result=original(channel,value);edges.append((clock[0],channel,value))
        if value and result:
            if channel=='flasher4way':game['hazard']=not game['hazard']
            elif channel=='rblinker':game['right']=not game['right']
            elif channel=='lblinker':game['left']=not game['left']
        return result
    engine.controller.scs._write_bool=write
    n()
    plugin=Signals(PluginSDK(state.values,'turnsignals'));plugin.on_start()
    for gear,speed in ((0,0.),(4,0.),(4,.2),(4,.4),(4,4.)):
        tick(gear=gear,speed=speed);engine._flush_controls()
    assert state.get('autopilot_active'),state.get('autopilot_intervention')
    for _ in range(6):
        tick(speed=10.,pedals=False)
        truck=state.get('telemetry')['truck']
        truck.update(blinkerLeft=game['left'] or game['hazard'],blinkerRight=game['right'] or game['hazard'])
        state.set('telemetry',{'truck':truck})
        lane=state.get('lane_trajectory');lane['turn_events']=topology_events('prefab','right')
        state.set('lane_trajectory',lane)
        policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033);plugin.on_tick(.033);engine._flush_controls()
    assert game==dict(hazard=False,right=True,left=False)
    assert engine.controller._observed_blinker=='right' and plugin._observed_active
    assert len([e for e in edges if e[1]=='rblinker' and e[2]])==1
    assert any(e[1]=='rblinker' and not e[2] for e in edges)
    # The backend toggle/feedback model is explicit, not a native consumption
    # certificate. A stale lamp-flash bit is never used as stable feedback.


def test_exact_recorded_rear_actor_boxes_through_native_reader_and_backend(joint):
    import json
    import struct
    from pathlib import Path
    from types import SimpleNamespace
    from core.longitudinal import context
    from core.sdk.ets2la_data import _TRAFFIC_FMT
    from core.sdk.traffic_snapshot import TrafficReader
    from core.navigation.traffic_producer import capture_traffic
    from tests.test_acc_following import capture
    from tests.test_oct14_completion import native_bytes
    record=json.loads((Path(__file__).parent/'fixtures/oct17-rear-body-receipt.json').read_text())
    cause=record['decisive'];anchor=cause['ego_anchor_xyz'];root=cause['ego_bodies'][0]
    # Exact rigid transform into the existing straight Map fixture; actual
    # incident boxes/angles/speed preserved. The full original route is absent.
    delta=math.pi-root['yaw'];c,s=math.cos(delta),math.sin(delta)
    def transform(body):
        x,z=body['x']-anchor[0],body['z']-anchor[2]
        return dict(body,x=2.25+c*x+s*z,z=15.-s*x+c*z,y=10.+body['y']-anchor[1],yaw=body['yaw']+delta)
    actor=transform(cause['actor']);bodies=[transform(b) for b in cause['ego_bodies']]
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    speed=cause['ego_observed_speed_mps'];tick(speed=speed,pedals=False)
    actual=state.get('telemetry')['truck'];raw=capture([actor],clock[0])
    fields=list(struct.unpack(_TRAFFIC_FMT,raw.moving));fields[7:10]=actor['dimensions_whl']
    raw=type(raw)(raw.session,raw.observed_at,struct.pack(_TRAFFIC_FMT,*fields),raw.parked,True)
    reader=SimpleNamespace(_timed_traffic_reader=TrafficReader())
    packed=[(b['x'],b['y'],b['z'],math.cos(b['yaw']/2),0.,math.sin(b['yaw']/2),0.,*b['dimensions_whl']) for b in bodies]
    reader._timed_traffic_reader.buffer=native_bytes(raw,clock[0],1,actual['sdkFrameTimeUs'],
        ego=packed,anchor=(2.25,10.,15.),ego_speed=speed)
    used=capture_traffic(reader,str(context(state)[1]),clock[0])
    following,brake=engine._traffic_control_observation(used,actual,context(state),[])
    assert brake==0.
    assert following['body_prediction']['non_braking_rear_contacts']
    engine._publish_traffic_control(actual,actual['_control_observation']['observed_at'],context(state),
        [],used,following,brake,dict(valid=False,candidate=None,reason='no head',coverage={}),None)
    policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
    assert state.get('autopilot_active') and not engine._service_brake_hold
    assert physical('abackward')==0.
