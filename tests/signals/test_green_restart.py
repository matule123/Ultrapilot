"""Late Oct16 signal cadence/near-stop regressions, actual physical writer.

Scripted vehicle observations are not measured ETS2 input consumption.
"""
from unittest.mock import patch
import pytest
from tests.test_activation_observation_binding import flow  # noqa:F401
from tests.signals.test_signal_timing import timing_flow
from tests.test_roundabout_intervention_reporting import pedal


@pytest.mark.parametrize('mode',[0,3])
def test_slower_policy_cannot_take_away_same_signal_terminal_brake(flow,tmp_path,mode):
    values,step=timing_flow(flow,tmp_path,mode)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    step(30,'red',speed=1.,progress=40.3)  # 1.7 m to the existing target
    assert pedal(engine,'abackward')>0.
    with patch.object(tick.policy,'on_tick',lambda _:None):
        step(31,'red',speed=.3,progress=40.6)
    acc=state.get('longitudinal_acc')
    assert acc['signal_brake_selected'],acc
    assert pedal(engine,'abackward')>0. and pedal(engine,'aforward')==0.
    assert state.get('simple_auto_service_hold')['phase']=='braking'
    step(32,'red',speed=0.,gear=0 if mode==0 else 4,progress=40.65)
    assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
    assert pedal(engine,'abackward')>0.


@pytest.mark.parametrize('mode',[0,3])
def test_qualified_green_can_meet_zero_ratio_during_admitted_approach(flow,tmp_path,mode):
    values,step=timing_flow(flow,tmp_path,mode)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    step(30,'red',speed=10.,progress=0.)
    for gen in range(31,35):step(gen,'red',speed=.3,progress=3.)
    assert state.get('simple_auto_service_hold')['phase']=='approaching'
    assert pedal(engine,'abackward')==0.
    epoch=state.get('autopilot_failure_epoch')
    for gen in range(35,39):
        step(gen,'green',speed=0.,gear=0,progress=3.)
        assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
        if gen<37:
            assert pedal(engine,'aforward')==pedal(engine,'abackward')==0.
    for gen in range(39,44):step(gen,'green',speed=.4,gear=4,progress=3.1)
    assert state.get('autopilot_failure_epoch')==epoch
    assert pedal(engine,'aforward')>0. and pedal(engine,'abackward')==0.
    assert not state.get('safety_hazard_active')
    assert not any(ch=='parkingbrake' for _,ch,_,_ in writes)


@pytest.mark.parametrize('mode',[0,3])
@pytest.mark.parametrize('green_at',['moving','zero','holding'])
def test_terminal_chain_green_timing_and_repeated_cycles(flow,tmp_path,mode,green_at):
    values,step=timing_flow(flow,tmp_path,mode)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    gen=50
    for cycle in range(3):
        step(gen,'red',speed=1.,progress=40.3);gen+=1
        step(gen,'red',speed=.3,progress=40.6);gen+=1
        start=len(writes)
        if green_at=='holding':
            for _ in range(4):
                step(gen,'red',speed=0.,gear=0 if mode==0 else 4,progress=40.65);gen+=1
        for j in range(5):
            speed=.2 if green_at=='moving' else 0.
            step(gen,'green',speed=speed,gear=4 if speed else 0,progress=40.65);gen+=1
            assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
        for _ in range(4):
            step(gen,'green',speed=.4,gear=4,progress=40.7);gen+=1
        assert pedal(engine,'aforward')>0. and pedal(engine,'abackward')==0.
        assert not engine._service_brake_hold
        if green_at=='holding':
            red_end=clock[0]-.06*9
            assert all(v>0 for at,ch,v,_ in writes[start:] if ch=='abackward' and at<=red_end)
    assert not state.get('safety_hazard_active')
    pair={'aforward':0.,'abackward':0.}
    for at,ch,value,_ in writes:
        if ch in pair:
            pair[ch]=value
            assert not all(v>0 for v in pair.values()),(at,ch,pair)


@pytest.mark.parametrize('mode',[0,3])
@pytest.mark.parametrize('fault',['stale','other_stop','reverse','backend','interrupted'])
def test_green_never_blesses_broken_terminal_chain(flow,tmp_path,mode,fault):
    values,step=timing_flow(flow,tmp_path,mode)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    step(50,'red',speed=1.,progress=40.3)
    step(51,'red',speed=.3,progress=40.6)
    assert state.get('simple_auto_service_hold')['phase']=='braking'
    if fault=='interrupted':engine.controller.set_brake(0.)
    if fault=='backend':engine.controller.scs.connected=False
    start=len(writes)
    for gen in range(52,57):
        step(gen,'green',speed=0.,gear=-1 if fault=='reverse' else 0,progress=40.65,
            other=.3 if fault=='other_stop' else 0.,age=.6 if fault=='stale' else 0.)
    assert not any(ch=='aforward' and v>0 for _,ch,v,_ in writes[start:])
    if fault in ('other_stop','stale'):
        # Old signal colour cannot release an established software hold.
        # Fresh vehicle telemetry still supports waiting, not an arbitrary
        # technical disable solely because green is unproven.
        assert state.get('autopilot_active')
        assert pedal(engine,'abackward')>0.
    else:
        assert not state.get('autopilot_active') or state.get('autopilot_control_state')=='controlled_stop'


def test_late_braking_does_not_relabel_own_probe_as_driver_motion(flow,tmp_path):
    values,step=timing_flow(flow,tmp_path,0)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    n()  # end the fixture's first activation
    step(40,'green',speed=0.,gear=0,progress=0.)
    n()
    step(41,'green',speed=0.,gear=0,progress=0.)
    assert engine._drive_engagement.get('probe_recorded')
    assert pedal(engine,'aforward')>0.
    step(42,'green',speed=.01,gear=0,progress=0.,other=.3)
    assert pedal(engine,'aforward')==0.
    assert engine._drive_engagement.get('phase')!='activation_wait'
    step(43,'green',speed=.2,gear=4,progress=.01,other=.3)
    assert state.get('autopilot_active'),state.get('navigation_status')
    assert engine._drive_engagement['phase']=='brake_handoff'
    assert pedal(engine,'aforward')==pedal(engine,'abackward')==0.
    step(44,'green',speed=.15,gear=4,progress=.02,other=.3)
    assert state.get('autopilot_active'),state.get('navigation_status')
    assert pedal(engine,'abackward')>0. and pedal(engine,'aforward')==0.


@pytest.mark.parametrize('mode',[0,3])
@pytest.mark.parametrize('fault',['manual','session','dataset','activation','reverse','future','backend'])
def test_zero_output_green_pairing_cannot_grant_foreign_or_invalid_drive(flow,tmp_path,mode,fault):
    values,step=timing_flow(flow,tmp_path,mode)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    step(30,'red',speed=10.,progress=0.)
    for gen in range(31,35):step(gen,'red',speed=.3,progress=3.)
    if fault=='manual':n()
    elif fault in ('session','dataset'):
        key='source_game_session_id' if fault=='session' else 'source_dataset_fingerprint'
        lane=state.get('lane_trajectory');lane[key]='foreign'
        state.set('lane_trajectory',lane)
        identity=state.get('lane_trajectory_identity');identity[key]='foreign'
        state.set('lane_trajectory_identity',identity)
    elif fault=='activation':state.set('simple_auto_activation_token',('foreign',1))
    elif fault=='backend':engine.controller.scs.connected=False
    start=len(writes)
    for gen in range(35,41):
        step(gen,'green',speed=0.,gear=-1 if fault=='reverse' else 0,progress=3.,
            age=-.1 if fault=='future' else 0.)
    assert not any(ch=='aforward' and v>0 for _,ch,v,_ in writes[start:])
    # No new standstill service brake in the previously released approach.
    assert not any(ch=='abackward' and v>0 for _,ch,v,_ in writes[start:])


@pytest.mark.parametrize('mode',[0,3])
def test_green_pairing_deadline_never_renews_with_new_ticks(flow,tmp_path,mode):
    values,step=timing_flow(flow,tmp_path,mode)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    step(30,'red',speed=10.,progress=0.)
    for gen in range(31,35):step(gen,'red',speed=.3,progress=3.)
    beginning=clock[0];deadlines=[]
    with patch('core.service_brake_hold.clearance',return_value=None):
        for gen in range(35,47):
            step(gen,'green',speed=0.,gear=0,progress=3.)
            held=state.get('simple_auto_service_hold') or {}
            if 'standstill_deadline_at' in held:deadlines.append(held['standstill_deadline_at'])
    assert deadlines and len(set(deadlines))==1 and deadlines[0]<=beginning+.5
    assert not state.get('autopilot_active')
    assert pedal(engine,'aforward')==pedal(engine,'abackward')==0.


def test_signal_selection_flags_survive_existing_immutable_export(flow,tmp_path):
    from core.steering_replay import SteeringReplayBuffer,inspect_replay
    values,step=timing_flow(flow,tmp_path,0)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    step(30,'red',speed=1.,progress=40.3)
    with patch.object(tick.policy,'on_tick',lambda _:None):
        step(31,'red',speed=.3,progress=40.6)
    snapshot=engine.controller._pedal_journal.snapshot(include_history=True)
    path=SteeringReplayBuffer(2).export(tmp_path,reason='significant_event',longitudinal=snapshot)
    checked=inspect_replay(path)
    assert checked['integrity_valid'] and checked['confirmed'] is False
    events=checked['replay']['longitudinal']['events']
    sources=[e.get('source') or {} for e in events]
    acc=[s['inputs']['acc'] for s in sources if (s.get('inputs') or {}).get('acc')]
    assert acc and acc[-1]['signal_stop_control'] and acc[-1]['signal_brake_selected']


@pytest.mark.parametrize('fault',['timeout','cancel','identity','reverse','backend'])
def test_interrupted_own_probe_never_renews_or_writes_standstill_brake(flow,tmp_path,fault):
    values,step=timing_flow(flow,tmp_path,0)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    n();step(40,'green',speed=0.,gear=0,progress=0.);n()
    step(41,'green',speed=0.,gear=0,progress=0.)
    original_deadline=engine._drive_engagement['deadline_at']
    step(42,'green',speed=.01,gear=0,progress=0.,other=.3)
    start=len(writes)
    if fault=='cancel':n()
    elif fault=='identity':state.set('autopilot_failure_epoch','foreign')
    elif fault=='backend':engine.controller.scs.connected=False
    for gen in range(43,90):
        step(gen,'green',speed=0.,gear=-1 if fault=='reverse' else 0,progress=0.,other=.3)
        pending=engine._drive_engagement
        if pending:assert pending['deadline_at']==original_deadline
    assert not state.get('autopilot_active') and not engine._drive_engagement
    assert not any(ch in ('aforward','abackward') and v>0 for _,ch,v,_ in writes[start:])


def test_green_pairing_reads_identity_and_clock_after_ipc(flow,tmp_path):
    values,step=timing_flow(flow,tmp_path,0)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    step(30,'red',speed=10.,progress=0.)
    for gen in range(31,35):step(gen,'red',speed=.3,progress=3.)
    policy=tick.policy.on_tick
    def acquire_then_delay(dt):
        policy(dt)
        def hook(key):
            if key=='longitudinal_traffic':
                state.hook=None
                clock[0]+=.51
        state.hook=hook
    start=len(writes)
    with patch.object(tick.policy,'on_tick',acquire_then_delay):
        step(35,'green',speed=0.,gear=0,progress=3.)
    assert not any(ch in ('aforward','abackward') and v>0 for _,ch,v,_ in writes[start:])
    assert not state.get('autopilot_active') or state.get('autopilot_control_state')=='controlled_stop'


def test_late_probe_brake_disappearance_is_not_clearance(flow,tmp_path):
    values,step=timing_flow(flow,tmp_path,0)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    n();step(40,'green',speed=0.,gear=0,progress=0.);n()
    step(41,'green',speed=0.,gear=0,progress=0.)
    step(42,'green',speed=.01,gear=0,progress=0.,other=.3)
    start=len(writes)
    for gen in range(43,58):step(gen,'green',speed=.2,gear=4,progress=.01,other=0.)
    assert not any(ch=='aforward' and v>0 for _,ch,v,_ in writes[start:])
    assert not state.get('autopilot_active') and not engine._drive_engagement


def test_standstill_pairing_never_reads_ipc_for_moving_approach(flow,tmp_path):
    from core.service_brake_hold import approach_green_wait_allowed
    values,step=timing_flow(flow,tmp_path,0)
    state,truck,engine,ap,tick,n,clock,writes,collector=values
    step(30,'red',speed=10.,progress=0.)
    for gen in range(31,35):step(gen,'red',speed=.3,progress=3.)
    actual=state.get('telemetry')['truck']
    held=state.get('simple_auto_service_hold')
    assert held['phase']=='approaching'
    reads=[];state.hook=reads.append
    try:assert approach_green_wait_allowed(held,state,actual) is False
    finally:state.hook=None
    assert reads==[]
