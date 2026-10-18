"""Receipt-timed counterexamples; synthetic omissions are not historic facts."""
import math
from types import SimpleNamespace

import pytest

from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct11_joint_regressions import joint  # noqa: F401
from tests.test_oct14_completion import timed_step, native_bytes


@pytest.fixture(autouse=True)
def entry_contract():
    """Opt-in old methods, identical assertions; never changes a checkout."""
    import os
    from tools.benchmark_oct17_systemic import baseline
    with baseline(os.environ.get('UP_OCT18_SYSTEMIC_BASELINE')=='1'):
        yield


def test_projection_expiry_can_wait_for_new_traffic_without_reusing_drive(joint,monkeypatch):
    from core.longitudinal import context
    from core.navigation.traffic_producer import capture_traffic
    from core.sdk.traffic_snapshot import TrafficReader
    from tests.test_acc_following import capture
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    tick(speed=5.,pedals=False)
    origin=clock[0]
    truck=state.get('telemetry')['truck']
    debug=state.get('nav_steering_debug')
    debug.update(observation_timestamp=origin-.0706123,computed_at=origin-.0372301)
    state.set('nav_steering_debug',debug)
    clock[0]=origin+.0335753
    raw=capture([],clock[0]);reader=SimpleNamespace(_timed_traffic_reader=TrafficReader())
    reader._timed_traffic_reader.buffer=native_bytes(raw,clock[0],1,truck['sdkFrameTimeUs'])
    captured=capture_traffic(reader,str(context(state)[1]),clock[0])
    following,brake=engine._traffic_control_observation(captured,truck,context(state),[])
    clock[0]=origin+.0698195
    engine._publish_traffic_control(truck,origin,context(state),[],captured,following,brake,
        dict(valid=False,candidate=None,reason='no head',coverage={}),None)
    old=state.get('longitudinal_traffic')
    assert old['expires_at']==pytest.approx(origin+.4293877)
    # Same timed source is now required by a held crossing owner in a synthetic
    # variant. The historic required red is detailed in the receipt report.
    old['light']=dict(color='red',stop_target_kind='derived_directed_curve_entry',distance=130.)
    state.set('longitudinal_traffic',old)
    while clock[0]<origin+.40:
        tick(speed=5.)
        engine._flush_controls()
    target=origin+.4957955
    clock[0]=target-.033333
    tick(speed=5.,pedals=False)
    # ACC may have a fresher zero-drive/no-target decision before its next
    # dynamic read; keep its actual controller observation interval <500ms.
    acc.on_tick(.033);policy.on_tick(.033)
    from core.navigation import longitudinal_diagnostics as diagnostics
    original_compact=diagnostics.compact_decision
    delays=[]
    def processing(value):
        result=original_compact(value)
        if not delays and value.get('input_failure','').startswith('traffic:'):
            delays.append(True);clock[0]+=.008
        return result
    monkeypatch.setattr(diagnostics,'compact_decision',processing)
    ap.on_tick(.033);engine._flush_controls()
    assert delays==[True]
    assert state.get('autopilot_control_state')!='controlled_stop',state.get('autopilot_intervention')
    assert state.get('autopilot_active')
    assert physical('aforward')==0.
    request=state.get('longitudinal_refresh_request')
    assert request and request['expires_at']<=old['expires_at']+.1
    assert old['observation_timestamp']<clock[0]-.5
    token=request['token']
    # A genuinely new complete producer decision takes over, no second N.
    clock[0]+=.005  # next independent native producer, inside the ORIGINAL bound
    acquire=native_producer(joint);acquire(2)
    engine._traffic_tick()
    policy.on_tick(.005);acc.on_tick(.005);ap.on_tick(.005);engine._flush_controls()
    assert state.get('autopilot_active'),state.get('autopilot_intervention')
    assert not state.get('longitudinal_command')['refresh_pending']
    assert physical('aforward')>0. and physical('abackward')==0.
    assert state.get('longitudinal_refresh_completed')['token']==token


def test_older_reread_cannot_replace_newer_expiring_acc_decision(joint):
    from copy import deepcopy
    from core.longitudinal import context, read
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    tick(speed=5.)
    old=state.get('longitudinal_acc')
    tick(speed=5.)
    new=deepcopy(state.get('longitudinal_acc'))
    assert new['sdk_frame_us']>old['sdk_frame_us']
    # A newer complete decision has an expiring dependency. A delayed older
    # publication cannot replace it with its longer, unrelated prior lease.
    new['handoff_required']=True
    state.set('longitudinal_acc',new)
    count=[]
    def hook(key):
        if key=='longitudinal_acc':
            count.append(1)
            if len(count)==2:state.values[key]=old
    state.hook=hook
    value,reason=read(state,'acc',binding=context(state),required=True)
    state.hook=None
    assert value is None and reason=='acc: longitudinal decision needs refresh',(value,reason)


def native_producer(joint, *, actors=()):
    """Actual local telemetry publication + native ABI capture; no extra clock."""
    import threading
    from core.sdk.traffic_snapshot import TrafficReader
    from tests.test_acc_following import capture
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    engine._telemetry_lock=threading.Lock()
    engine._latest_telemetry_success=True
    engine._latest_telemetry_data=state.get('telemetry')
    engine._latest_telemetry_timestamp=clock[0]
    engine._telemetry_sequence=1
    reader=SimpleNamespace(_timed_traffic_reader=TrafficReader(),traffic_available=True,
        read_traffic=lambda:[],read_traffic_lights=lambda:[])
    engine.ets2la=reader
    engine._signal_observation=lambda truck,binding:dict(valid=False,candidate=None,reason='no signal in this fixture',coverage={})
    def acquire(generation):
        truck=state.get('telemetry')['truck']
        engine._store_telemetry_sample(True,state.get('telemetry'),clock[0])
        raw=capture(actors,clock[0])
        reader._timed_traffic_reader.buffer=native_bytes(raw,clock[0],generation,truck['sdkFrameTimeUs'],
            ego=[(truck['x'],truck['y'],truck['z'],0.,1.,0.,0.,2.5,4.,6.)],
            anchor=(truck['x'],truck['y'],truck['z']),ego_speed=abs(truck['speed']))
    return acquire


def test_one_traffic_owner_publishes_atomic_envelope_and_original_times(joint):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    acquire=native_producer(joint,actors=[dict(id=i+100,x=40.+i,y=10.,z=80.,yaw=math.pi,speed=3.) for i in range(35)])
    acquire(1)
    batches=[];original=state.update_batch
    def publish(values):
        if 'longitudinal_traffic' in values:batches.append(values)
        original(values)
    state.update_batch=publish
    packet=engine._traffic_tick()
    assert packet['valid'] and packet['following']['source_acquisition']['generation']==1
    assert packet['traffic_availability']['atomic'] is True
    assert packet['traffic_availability']['source_timestamp']==packet['following']['source_acquisition']['observed_at']
    assert len(batches)==1 and batches[0]['traffic_brake']==packet['traffic_brake']
    assert packet['producer_timing']['sequence']==1
    original_at=packet['following']['source_acquisition']['observed_at']
    for index in range(1,6):
        tick(speed=5.,pedals=False)
        engine._store_telemetry_sample(True,state.get('telemetry'),clock[0])
        repeated=engine._traffic_tick()
        assert repeated['following']['source_acquisition']['observed_at']==original_at
        assert repeated['expires_at']<=original_at+.5
        assert repeated['producer_timing']['previous']['sequence']==index
        policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
    assert state.get('autopilot_active'),state.get('autopilot_intervention')


def test_single_flight_never_queues_or_overwrites_after_identity_change(joint):
    import threading
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    acquire=native_producer(joint);acquire(1)
    first=engine._traffic_tick()
    engine._traffic_production_lock.acquire()
    try:
        assert engine._traffic_tick() is None
        assert state.get('longitudinal_traffic')==first
    finally:engine._traffic_production_lock.release()
    original=engine._traffic_control_observation
    def changed(*args):
        result=original(*args)
        state.set('navigation_intent_id','new-intent')
        return result
    engine._traffic_control_observation=changed
    assert engine._traffic_tick() is None
    assert state.get('longitudinal_traffic')==first
    ap.on_tick(.033);engine._flush_controls()
    assert physical('aforward')==0.


def test_blocked_passive_work_cannot_block_traffic_worker(joint):
    import threading
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    acquire=native_producer(joint);acquire(1)
    engine.running=True;engine._realtime_stop=threading.Event()
    entered=threading.Event();release=threading.Event();published=threading.Event()
    original=engine._traffic_tick
    def observe():
        value=original()
        if value:published.set()
        return value
    engine._traffic_tick=observe
    # A deliberately blocked passive operation represents any main-loop I/O.
    # Its historic exact operation is absent; do not call this a GC proof.
    passive=threading.Thread(target=lambda:(entered.set(),release.wait(2.)))
    passive.start();assert entered.wait(1.)
    engine._start_traffic_worker()
    try:
        owner=engine._traffic_thread
        engine._start_traffic_worker();assert engine._traffic_thread is owner
        assert published.wait(1.)
        assert not release.is_set() and passive.is_alive()
        assert state.get('longitudinal_traffic')['valid']
        policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
        assert state.get('autopilot_active'),state.get('autopilot_intervention')
    finally:
        engine.running=False;engine._realtime_stop.set();release.set()
        owner.join(2.);passive.join(2.)
    assert not owner.is_alive()


@pytest.mark.parametrize('fault',['telemetry','native_stale','R','identity','backend'])
def test_independent_producer_does_not_authorize_invalid_drive(joint,fault):
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    acquire=native_producer(joint);acquire(1)
    first=engine._traffic_tick()
    # Make this source required without inferring clearance from disappearance.
    first['light']=dict(color='red',stop_target_kind='derived_directed_curve_entry',distance=130.)
    state.set('longitudinal_traffic',first)
    if fault=='telemetry':
        engine._latest_telemetry_success=False
        engine._traffic_tick()
        state.set('telemetry_valid',False)
    elif fault=='native_stale':
        for _ in range(17):tick(speed=5.,pedals=False)
        engine._store_telemetry_sample(True,state.get('telemetry'),clock[0])
        # A repeated source has not observed another vehicle frame. Keep the
        # original required red dependency rather than replacing it with empty.
    elif fault=='R':
        tick(gear=-1,speed=-.01,pedals=False)
    elif fault=='identity':state.set('game_session_id','other-session')
    else:engine.controller.scs.connected=False
    start=len(writes)
    ap.on_tick(.033);engine._flush_controls()
    assert not any(ch=='aforward' and v>0 for _,ch,v in writes[start:])
    if fault=='backend':
        # Disconnected mapping cannot acknowledge even a zero write. Do not
        # interpret its last retained float as a successful new drive command.
        assert state.get('autopilot_control_state')=='controlled_stop' or not state.get('autopilot_active')
        assert 'backend' in state.get('autopilot_intervention')['reason']
    else:assert physical('aforward')==0.


def test_timing_and_consistent_rejection_survive_existing_export(joint,tmp_path):
    from core.steering_replay import inspect_replay
    from core.navigation.longitudinal_diagnostics import PedalJournal
    state,engine,ap,acc,policy,tick,_,_,physical,writes,clock=joint
    acquire=native_producer(joint);acquire(1)
    engine._automatic_replay_directory=str(tmp_path)
    journal=engine.controller._pedal_journal=PedalJournal();journal.enabled=True
    packet=engine._traffic_tick()
    policy.on_tick(.033);acc.on_tick(.033);ap.on_tick(.033);engine._flush_controls()
    captured=journal.snapshot()['events']
    timing=next(e['source']['inputs']['traffic']['producer_timing'] for e in captured
        if ((e.get('source') or {}).get('inputs') or {}).get('traffic'))
    assert timing==packet['producer_timing']
    assert any(e['source'].get('traffic_producer_runtime',{}).get('active_stage')=='finished' for e in captured)
    tick(gear=-1,speed=-.01,pedals=False)
    ap.on_tick(.033);engine._flush_controls()
    first=state.get('autopilot_intervention')
    engine._request_automatic_longitudinal_incident(first)  # actual main-loop relay
    engine._finish_automatic_longitudinal_incident(journal,shutdown=True)
    result=engine._automatic_replay_writer.wait(5.)
    checked=inspect_replay(result['path'])
    assert checked['integrity_valid'] and not checked['confirmed']
    block=checked['replay']['longitudinal']
    assert block['first_intervention']['reason']==first['reason']
    assert any((e.get('source') or {}).get('traffic_producer_runtime') for e in block['events'])


@pytest.mark.parametrize('mode',[0,3])
def test_independent_native_producer_preserves_repeated_real_signal_cycles(flow,tmp_path,monkeypatch,mode):
    import threading
    from core.sdk.traffic_snapshot import TrafficReader
    from tests.test_acc_following import capture
    from tests.test_oct10_signal_timing import timing_flow
    from tests.test_roundabout_intervention_reporting import pedal
    values,step=timing_flow(flow,tmp_path,mode)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    engine._telemetry_lock=threading.Lock()
    engine._latest_telemetry_success=True
    engine._telemetry_sequence=0
    engine.ets2la=SimpleNamespace(_timed_traffic_reader=TrafficReader(),traffic_available=True,
        read_traffic=lambda:[],read_traffic_lights=lambda:[])
    consumed=[]
    def publish_through_owner(state,actual,source,**requested):
        assert source=='traffic'
        engine._store_telemetry_sample(True,state.get('telemetry'),clock[0])
        gen=requested['signal']['generation']
        raw=capture([],clock[0])
        engine.ets2la._timed_traffic_reader.buffer=native_bytes(raw,clock[0],gen,actual['sdkFrameTimeUs'])
        result=engine._traffic_tick()
        assert result['signal']['candidate']['id']==requested['signal']['candidate']['id']
        assert result['signal']['observed_at']==requested['signal']['observed_at']
        consumed.append(result)
    monkeypatch.setattr('tests.test_oct10_signal_timing.publish',publish_through_owner)
    generation=200
    for cycle in range(3):
        generation+=1;step(generation,'red',speed=3.)
        for _ in range(25):
            generation+=1;step(generation,'red',speed=0.,gear=0)
            assert pedal(engine,'aforward')==0. and pedal(engine,'abackward')>0.
            assert state.get('autopilot_active') and not state.get('safety_hazard_active')
        for _ in range(10):
            generation+=1;step(generation,'green',speed=0.,gear=0)
        for _ in range(6):
            generation+=1;step(generation,'green',speed=.4,gear=4)
        assert pedal(engine,'aforward')>0. and pedal(engine,'abackward')==0.
        assert not state.get('autopilot_intervention')
    assert len(consumed)==126
    assert not any(ch=='parkingbrake' for _,ch,_,_ in writes)
    pair={'aforward':0.,'abackward':0.}
    for _,channel,value,_ in writes:
        if channel in pair:pair[channel]=value
        assert not (pair['aforward']>0. and pair['abackward']>0.)
