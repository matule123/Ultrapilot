"""Oct 11 production traffic and physical output regressions; no game proof."""
import math
import struct
from unittest.mock import patch
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from core.engine import UltraPilotEngine
from core.longitudinal import context
from core.navigation.traffic_producer import TrafficCapture, capture_traffic
from core.sdk.ets2la_data import _TRAFFIC_FMT
from tests.test_acc_following import capture
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_rolling_longitudinal_authority import rolling  # noqa: F401
from sdk.plugin_sdk import PluginSDK
from plugins.turnsignals.main import Plugin as TurnSignals
from core.acc_following import observation, RouteLeadSelector, observed_departure


@pytest.fixture(params=[0, 3], ids=['simple-auto', 'real-auto'])
def joint(flow, request):
    from tests import test_rolling_longitudinal_authority as module
    original = module.strict_flow
    with patch.object(module, 'strict_flow', lambda source: original(source, mode=request.param)):
        generator = module.rolling.__wrapped__(flow)
        value = next(generator)
    try:
        yield value
    finally:
        with pytest.raises(StopIteration):
            next(generator)


def traffic_step(rolling, actors, *, before_acc=False, trailer=None):
    state, engine, ap, acc, policy, tick, _, _, _, _, clock = rolling
    tick(speed=10., z=15., pedals=False)
    truck=state.get('telemetry')['truck']
    raw=capture(actors, clock[0])
    if trailer:
        fields=list(struct.unpack(_TRAFFIC_FMT,raw.moving))
        fields[12]=1
        fields[16:26]=trailer
        raw=TrafficCapture(raw.session,raw.observed_at,struct.pack(_TRAFFIC_FMT,*fields),raw.parked,True)
    reader=SimpleNamespace(_traffic_buf=raw.moving,_parked_buf=raw.parked)
    consumed=capture_traffic(reader, str(context(state)[1]), clock[0])
    following, brake=engine._traffic_control_observation(consumed,truck,context(state),[])
    engine._publish_traffic_control(truck,truck['_control_observation']['observed_at'],context(state),
        [],consumed,following,brake,dict(valid=False,candidate=None,reason='no head',coverage={}),None)
    if before_acc:
        engine._flush_controls()
        assert not state.get('autopilot_intervention'), state.get('autopilot_intervention')
        from tests.test_roundabout_intervention_reporting import pedal
        assert pedal(engine,'aforward') == 0.  # no old drive between producer ticks
    policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
    return following


@pytest.mark.parametrize('before_acc',[False,True])
def test_observed_lead_departure_continues_physical_drive(joint,before_acc):
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    lead=dict(id=29,x=2.25,y=10.,z=40.,yaw=math.pi,speed=5.)
    result=traffic_step(joint,[lead])
    assert result['target_id']=='29' and acc._followed_target
    result=traffic_step(joint,[dict(lead,x=10.,yaw=-math.pi/2)],before_acc=before_acc)
    assert state.get('autopilot_active') and not state.get('autopilot_intervention')
    assert state.get('autopilot_control_state') != 'controlled_stop'
    assert not state.get('safety_hazard_active')
    assert not acc._following_fault
    assert not (physical('aforward')>0 and physical('abackward')>0)
    assert result['departure']['target_id']=='29'


def test_changed_departure_receipt_survives_existing_integrity_export(joint,tmp_path):
    from core.navigation.longitudinal_diagnostics import PedalJournal
    from core.steering_replay import SteeringReplayBuffer,inspect_replay
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    journal=engine.controller._pedal_journal=PedalJournal();journal.enabled=True
    lead=dict(id=29,x=2.25,y=10.,z=40.,yaw=math.pi,speed=5.)
    traffic_step(joint,[lead])
    result=traffic_step(joint,[dict(lead,x=10.,yaw=-math.pi/2)])
    expected=result['departure']
    path=SteeringReplayBuffer(2).export(tmp_path,reason='manual_disable',
        longitudinal=journal.snapshot(expanded=False,include_history=True))
    inspected=inspect_replay(path)
    assert inspected['integrity_valid']
    block=inspected['replay']['longitudinal']
    rows=block['decision_history']['regular_samples']+block['decision_history']['changes']
    assert any(row.get('traffic_departure')==expected for row in rows),rows
    assert not block['game_consumption_verified']
    assert journal._bytes <= journal.MAX_BYTES


def test_trailer_crossing_reaches_physical_brake(joint):
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    # Tractor already off the route; its articulated trailer is still crossing.
    actor=dict(id=9,x=8.,y=10.,z=20.,yaw=-math.pi/2,speed=5.)
    trailer=[-2.,10.,20.,math.cos(-math.pi/4),0.,math.sin(-math.pi/4),0.,2.5,4.,12.]
    following=traffic_step(joint,[actor],trailer=trailer)
    assert physical('aforward')==0. and physical('abackward')>0.
    assert following['crossing']['conflicts'], following
    assert engine.shared_state.get('traffic_brake')>0.


def test_ui_enable_starts_plugin_skipped_at_startup(monkeypatch):
    from core.plugin_manager import PluginManager
    from tests.test_control_safety_regressions import State
    from plugins.turnsignals.main import Plugin
    state=State({'plugin_enabled.turnsignals':False})
    engine=SimpleNamespace(shared_state=state,settings={'plugins':{'turnsignals':False}},running=True)
    manager=PluginManager(engine)
    monkeypatch.setattr('core.plugin_manager.os.path.isdir',lambda _:True)
    monkeypatch.setattr('core.plugin_manager.os.path.exists',lambda _:True)
    monkeypatch.setattr('core.plugin_manager.os.listdir',lambda _:['turnsignals'])
    manager._find_plugin_class=Mock(return_value=Plugin)
    manager._spawn=Mock()
    manager.discover_and_load()
    assert not manager.plugins
    state.set('plugin_enabled.turnsignals',True)
    manager.tick(.033)
    manager._spawn.assert_called_once_with('turnsignals')
    manager.tick(.033)
    manager._spawn.assert_called_once()


def test_no_route_turn_does_not_cancel_driver_indicator(joint,monkeypatch):
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    monkeypatch.setattr('core.controller._HAS_PDI',False)
    plugin=TurnSignals(PluginSDK(state.values,'turnsignals'));plugin.on_start()
    bool_writes=[]
    original=engine.controller.scs._write_bool
    def write(channel,value):
        bool_writes.append((channel,value));return original(channel,value)
    engine.controller.scs._write_bool=write
    truck=state.get('telemetry')['truck'];truck['blinkerLeft']=True;truck['blinkerRight']=False
    state.set('telemetry',{'truck':truck})
    plugin.on_tick(.033);engine._flush_controls()
    assert not any(ch=='lblinker' and value for ch,value in bool_writes),bool_writes


@pytest.mark.parametrize('loss', ['absent', 'turned_inside', 'duplicate', 'reassigned_slot'])
def test_unproven_departure_still_removes_physical_drive(joint, loss):
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    lead=dict(id=29,x=2.25,y=10.,z=40.,yaw=math.pi,speed=5.)
    traffic_step(joint,[lead])
    if loss == 'absent':
        actors=[]
    elif loss == 'turned_inside':
        actors=[dict(lead, yaw=-math.pi/2)]
    elif loss == 'duplicate':
        actors=[lead, dict(lead,x=10.,yaw=-math.pi/2)]
    else:
        actors=[dict(lead,id=7,x=20.),dict(lead,x=10.,yaw=-math.pi/2)]
    result=traffic_step(joint,actors)
    assert not result.get('departure'), result
    assert state.get('autopilot_intervention') or acc._following_fault
    assert physical('aforward') == 0.


def test_departure_does_not_restamp_unchanged_record_or_clear_actual_loss():
    selector=RouteLeadSelector();selector.prepare([[2.25,10.,float(z)] for z in range(121)],('route',))
    truck=dict(x=2.25,y=10.,z=15.,rotation=math.pi,speed=10.)
    lead=dict(id=29,x=2.25,y=10.,z=40.,yaw=math.pi,speed=5.)
    first=observation(capture([lead],1000.),1000.)
    selector.select(first['actors'],truck,15.,receiver_time=1000.)
    turned=observation(capture([dict(lead,x=10.,yaw=-math.pi/2)],1000.05),1000.05)
    proof=selector.select(turned['actors'],truck,15.,receiver_time=1000.05)
    repeated=selector.select(turned['actors'],truck,15.,receiver_time=1000.10)
    assert proof['departure']['receiver_time'] == repeated['departure']['receiver_time'] == 1000.05
    assert observed_departure(repeated,'29',1000.10)
    assert not observed_departure(repeated,'29',1000.56)
    assert not observed_departure(repeated,'other',1000.10)
    assert not selector.select([],truck,15.,receiver_time=1000.12).get('departure')
    assert not selector.select(turned['actors'],truck,15.,receiver_time=1000.51).get('departure')
    selector.prepare(selector.points,('different-route',))
    assert not selector.select(turned['actors'],truck,15.,receiver_time=1000.15).get('departure')


@pytest.mark.parametrize('speed',[-1.,71.])
def test_invalid_departed_actor_speed_cannot_release_acquired_lead(joint,speed):
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    lead=dict(id=29,x=2.25,y=10.,z=40.,yaw=math.pi,speed=5.)
    traffic_step(joint,[lead])
    result=traffic_step(joint,[dict(lead,x=10.,yaw=-math.pi/2,speed=speed)])
    assert not result.get('departure'), result
    assert state.get('autopilot_intervention') or acc._following_fault
    assert physical('aforward') == 0.


def test_departed_tractor_with_trailer_on_route_cannot_release_acquired_lead(joint):
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    lead=dict(id=29,x=2.25,y=10.,z=40.,yaw=math.pi,speed=5.)
    traffic_step(joint,[lead])
    trailer=[2.25,10.,35.,math.cos(math.pi/2),0.,math.sin(math.pi/2),0.,2.5,4.,12.]
    result=traffic_step(joint,[dict(lead,x=10.,yaw=-math.pi/2)],trailer=trailer)
    assert not result.get('departure'), result
    assert state.get('autopilot_intervention') or acc._following_fault
    assert physical('aforward') == 0.


def test_two_crossing_actors_and_empty_buffer_never_certify_gap(joint):
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    actors=[dict(id=1,x=-8.,y=10.,z=25.,yaw=-math.pi/2,speed=5.),
            dict(id=2,x=-13.,y=10.,z=25.,yaw=-math.pi/2,speed=6.)]
    following=traffic_step(joint,actors)
    assert {c['id'] for c in following['crossing']['conflicts']} == {1,2}
    assert not following['crossing']['clearance_confirmed']
    assert physical('aforward') == 0 and physical('abackward') > 0
    following=traffic_step(joint,[actors[1]])
    assert {c['id'] for c in following['crossing']['conflicts']} == {2}
    assert physical('aforward') == 0 and physical('abackward') > 0
    following=traffic_step(joint,[])
    assert not following['crossing']['clearance_confirmed']
    assert not state.get('longitudinal_traffic')['traffic_availability']['coverage_confirmed']


@pytest.mark.parametrize('mode', [0, 3])
def test_departure_fix_preserves_same_head_red_hold_green_restart(flow,tmp_path,mode):
    from tests.test_oct10_signal_timing import timing_flow
    from tests.test_roundabout_intervention_reporting import pedal
    values,step=timing_flow(flow,tmp_path,mode)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    step(20,'red',speed=3.)
    for generation in range(21,25):
        step(generation,'red',speed=0.)
        assert state.get('autopilot_active')
        assert pedal(engine,'aforward') == 0 and pedal(engine,'abackward') > 0
    for generation in range(25,33):
        step(generation,'green',speed=0.)
    assert state.get('simple_auto_service_hold') is None
    assert state.get('autopilot_active')
    assert pedal(engine,'aforward') > 0 and pedal(engine,'abackward') == 0
    assert not any(channel=='parkingbrake' for _,channel,_,_ in writes)


def indicator_loop(joint,monkeypatch,events):
    state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=joint
    monkeypatch.setattr('core.controller._HAS_PDI',False)
    plugin=TurnSignals(PluginSDK(state.values,'turnsignals'));plugin.on_start()
    edges=[];original=engine.controller.scs._write_bool
    def write(channel,value):
        edges.append((clock[0],channel,value));return original(channel,value)
    engine.controller.scs._write_bool=write
    def pump(z=15.,observed='off'):
        tick(speed=10.,z=z,pedals=False)
        truck=state.get('telemetry')['truck']
        truck.update(blinkerLeft=observed in ('left','hazard'),blinkerRight=observed in ('right','hazard'))
        state.set('telemetry',{'truck':truck})
        lane=state.get('lane_trajectory');lane['turn_events']=events
        state.set('lane_trajectory',lane)
        policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033)
        plugin.on_tick(.033);engine._flush_controls()
        assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
    return plugin,pump,edges


def topology_events(kind,side):
    # Use Map's actual topology publication, not a steering-sign shortcut.
    from plugins.map.main import Plugin as Map
    from core.navigation.lane_model import LaneId,LanePath,LanePoint,LaneSegment
    lane=LaneId(21,1,0,prefab_token=kind,connector_index=0,connector_path=(1,))
    change=.6 if side=='left' or kind=='roundabout' else -.6
    points=tuple(LanePoint(2.25,10.,s,s,math.pi+change*i/3,lane_id=lane,segment_index=0)
        for i,s in enumerate((35.,43.,51.,60.)))
    segment=LaneSegment(lane,1,2,1,0,1,4.,'synthetic',0,'look',kind,points)
    return Map.__new__(Map)._turn_events_payload(LanePath((segment,),points,(1,2),60.,.95,True))


@pytest.mark.parametrize('kind,side',[('prefab','left'),('prefab','right'),('roundabout','right')])
def test_topology_indicator_has_one_physical_edge_and_owned_cancellation(joint,monkeypatch,kind,side):
    events=topology_events(kind,side)
    assert events[0]['direction'] == side
    plugin,pump,edges=indicator_loop(joint,monkeypatch,events)
    channel='lblinker' if side=='left' else 'rblinker'
    # The selected roundabout exit is 45 m away; a 10 m/s approach is 40 m.
    pump()
    if kind=='roundabout':
        assert not any(value for _,ch,value in edges if ch==channel)
        # Progress starts at the Map-trimmed route origin, not world Z=0.
        # Advance at the actual 10 m/s / 33 ms fixture cadence, no teleport.
        # The new roundabout gate forbids indicating before the proven entry
        # at route progress 35 m (world Z=50 in this trimmed fixture).
        for index in range(1,121):
            acknowledged=any(ch==channel and value for _,ch,value in edges)
            pump(z=15.+index/3.,observed=side if acknowledged else 'off')
        position=55.
    else:
        position=15.
    assert len([1 for _,ch,value in edges if ch==channel and value]) == 1
    for index in range(1,9):pump(z=position+index/3.,observed=side)
    position+=8/3.
    assert len([1 for _,ch,value in edges if ch==channel and value]) == 1
    for index in range(1,int((91.-position)*3)+1):pump(z=position+index/3.,observed=side)
    assert len([1 for _,ch,value in edges if ch==channel and value]) == 2
    pump(z=91.,observed='off')
    assert joint[0].get('route_blinker') is None
    assert len([1 for _,ch,value in edges if ch==channel and value]) == 2


@pytest.mark.parametrize('driver',['off','left','hazard'])
def test_self_cancel_manual_side_and_hazards_do_not_rearm_event(joint,monkeypatch,driver):
    plugin,pump,edges=indicator_loop(joint,monkeypatch,topology_events('prefab','right'))
    pump();pump(observed='right')
    before=len([1 for _,_,value in edges if value])
    for _ in range(12):pump(observed=driver)
    assert joint[0].get('route_blinker') is None
    assert len([1 for _,_,value in edges if value]) == before


def test_disabling_worker_after_driver_changed_side_cannot_send_blind_off(joint,monkeypatch):
    plugin,pump,edges=indicator_loop(joint,monkeypatch,topology_events('prefab','right'))
    pump();pump(observed='right')
    plugin.on_stop()
    assert joint[0].get('ctl_blinker') is None
    before=len([1 for _,_,value in edges if value])
    truck=joint[0].get('telemetry')['truck']
    truck.update(blinkerLeft=True,blinkerRight=False)
    joint[0].set('telemetry',{'truck':truck})
    joint[1]._flush_controls()
    assert len([1 for _,_,value in edges if value]) == before


def test_safety_hazards_suppress_directional_toggle(joint,monkeypatch):
    plugin,pump,edges=indicator_loop(joint,monkeypatch,topology_events('prefab','right'))
    pump();pump(observed='right')
    before=len([1 for _,ch,value in edges if ch in ('lblinker','rblinker') and value])
    joint[0].set('safety_hazard_active',True)
    joint[1]._flush_controls()
    assert joint[0].get('active_blinker') == 'hazard'
    assert len([1 for _,ch,value in edges if ch in ('lblinker','rblinker') and value]) == before


def test_geometry_republication_does_not_rearm_cancelled_semantic_event(joint,monkeypatch):
    events=topology_events('prefab','right')
    plugin,pump,edges=indicator_loop(joint,monkeypatch,events)
    pump();pump(observed='right');pump(observed='off')
    state=joint[0]
    # Publish a coherent new version of the same semantic instruction. This
    # isolated ownership edge does not flush pedals under a fabricated new
    # route identity; the separate topology tests exercise physical toggles.
    snapshot=state.get('lane_trajectory')
    snapshot['route_build_id']='new-indicator-geometry'
    snapshot['revision']+=1
    state.set('lane_trajectory_revision',snapshot['revision'])
    state.set('lane_trajectory',snapshot)
    plugin.on_tick(.033)
    assert state.get('route_blinker') is None
    assert plugin._event_id(events[0]) in plugin._consumed_event_ids
