"""Normal event export through the existing PedalJournal and physical path."""
import copy
import json
from pathlib import Path

import pytest

from core.longitudinal import context,publish
from core.steering_replay import inspect_replay
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct8_stop_lifecycle import directed_stop


def test_normal_brake_source_edge_exports_without_disabling_or_arming(flow,tmp_path):
    values,step=directed_stop(flow)
    state,truck,engine,ap,tick,n,clock,writes,collected=values
    engine._automatic_replay_directory=str(tmp_path)
    step(4,8.,color=8)
    state.set('longitudinal_acc_active',False)
    actual=state.get('telemetry')['truck']
    publish(state,actual,'traffic',traffic_brake=.35,light_brake=0.,light=None,
        following=None,brake_basis=dict(kind='test_directed_conflict',target_id=71,conflict_time_s=3.))
    ap.on_tick(.05);engine._flush_controls()
    for _ in range(10):
        flow[4](4,8.,dt=.025)
        actual=state.get('telemetry')['truck']
        publish(state,actual,'traffic',traffic_brake=.35,light_brake=0.,light=None,
            following=None,brake_basis=dict(kind='test_directed_conflict',target_id=71,conflict_time_s=3.))
        ap.on_tick(.025);engine._flush_controls()
    writer=getattr(engine,'_automatic_replay_writer',None)
    if writer:writer.wait(5.)
    paths=list(tmp_path.glob('*significant_event.json'))
    assert paths, 'Normal source edge did not preserve its evidence before the 30 s window ages out'
    checked=inspect_replay(paths[0])
    assert checked['integrity_valid'] and not checked['confirmed'] and not checked['runtime_authorized']
    assert checked['replay']['longitudinal']['significant_event']['kind']=='BRAKE_SOURCE_CHANGED'
    assert state.get('autopilot_active')


def test_event_receipt_is_immutable_bounded_and_keeps_following_writes(tmp_path):
    from core.navigation.longitudinal_diagnostics import PedalJournal
    from core.steering_replay import SteeringReplayBuffer
    journal=PedalJournal();journal.enabled=True
    receipt={'context':[1,'session','map','data','intent',7,'build','geometry'],
        'sdk_frame_us':100,'observation_timestamp':100.,'actor':{'id':71,'ttc_s':3.},
        'selected':{'source':'traffic','throttle':0.,'brake':.35}}
    original=copy.deepcopy(receipt)
    journal.significant('AVOID_OBSTACLE',receipt,100.)
    receipt['actor']['id']=99
    for _ in range(100):journal.significant('BRAKE_SOURCE_CHANGED',receipt,100.01)
    journal.bind(original)
    journal.record('brake',.35,100.05,100.051,'TEST',{'status':'MAPPING_WRITE_RETURNED'})
    pending=journal.ready_significant(100.2)
    snapshot=journal.expand_significant(pending)
    assert snapshot['significant_event']['receipt']['actor']['id']==71
    assert snapshot['significant_event']['coalesced']['BRAKE_SOURCE_CHANGED']==100
    assert len(snapshot['events'])==1 and snapshot['events'][0]['requested_value']==.35
    path=SteeringReplayBuffer(2).export(str(tmp_path),reason='significant_event',
        identity={'event_sequence':1},sample_kind='longitudinal_significant_event',longitudinal=snapshot)
    assert inspect_replay(path)['integrity_valid']
    journal.significant_submitted(pending['sequence'])
    for i in range(5):
        journal.significant('AVOID_OBSTACLE',original,100.3+i)
        p=journal.ready_significant(100.5+i)
        if p:journal.significant_submitted(p['sequence'])
    status=journal.snapshot()['event_capture_status']
    assert status['suppressed_events']>=2 and status['pending_capacity']==1


def test_unknown_event_names_cannot_grow_the_coalescing_dictionary():
    from core.navigation.longitudinal_diagnostics import PedalJournal
    journal=PedalJournal();journal.enabled=True
    for i in range(1000):journal.significant('unknown-'+str(i),{},100.)
    assert journal.ready_significant(101.) is None
    assert journal.snapshot()['event_capture_status']['suppressed_events']==1000


def test_pending_event_owns_nested_route_context():
    from core.navigation.longitudinal_diagnostics import PedalJournal
    journal=PedalJournal();journal.enabled=True
    receipt={'context':['a','session','map','data','intent',7,'build',['lane','original']]}
    journal.significant('AVOID_OBSTACLE',receipt,100.)
    receipt['context'][-1][-1]='mutated'
    pending=journal.ready_significant(100.2)
    assert pending['context'][-1][-1]=='original'
    assert pending['receipt_bytes']<=32768


def test_oversized_event_receipt_is_explicitly_incomplete(tmp_path):
    from core.navigation.longitudinal_diagnostics import PedalJournal
    from core.steering_replay import SteeringReplayBuffer
    journal=PedalJournal();journal.enabled=True
    journal.significant('AVOID_OBSTACLE',{'actor':'x'*40000},100.)
    snapshot=journal.expand_significant(journal.ready_significant(100.2))
    path=SteeringReplayBuffer(2).export(tmp_path,reason='significant_event',longitudinal=snapshot)
    result=inspect_replay(path)
    assert result['integrity_valid'] and result['incomplete'] and not result['confirmed']
    assert result['replay']['longitudinal']['significant_event']['receipt_incomplete']


def test_sealed_event_survives_history_aging_and_identity_mutation(tmp_path):
    from core.navigation.longitudinal_diagnostics import PedalJournal
    from core.steering_replay import SteeringReplayBuffer
    from tests.test_pedal_decision_history import bound
    journal=PedalJournal();journal.enabled=True
    receipt={'context':['a','original','map','data','intent',7,'build','geometry']}
    sealed=None
    for i in range(1200):
        t=100.+i*.05
        braking=35.<=i*.05<42.
        bound(journal,t,0. if braking else .2,.3 if braking else 0.,reason='brake' if braking else 'drive')
        if i==700:
            journal.significant('AVOID_OBSTACLE',receipt,t)
            receipt['context'][1]='later-mutation'
        if i==703:
            sealed=journal.ready_significant(t)
            journal.significant_submitted(sealed['sequence'])
    assert sealed['context'][1]=='original'
    event=journal.expand_significant(sealed)
    history=event['decision_history']
    assert history['observed_range_s']['duration']>=29.9
    assert history['window_end_s']<136.
    assert journal.snapshot(include_history=True)['decision_history']['window_end_s']>159.
    path=SteeringReplayBuffer(2).export(tmp_path,reason='significant_event',longitudinal=event)
    checked=inspect_replay(path)
    assert checked['integrity_valid'] and not checked['confirmed']
    payload=json.loads(Path(path).read_text())
    payload['identity']['tampered']=True
    Path(path).write_text(json.dumps(payload))
    assert not inspect_replay(path)['integrity_valid']


@pytest.mark.parametrize('quota',['files','bytes'])
def test_background_event_quota_does_not_overwrite_evidence_or_publish_partial(tmp_path,quota):
    from core.engine import UltraPilotEngine
    from core.navigation.longitudinal_diagnostics import PedalJournal
    engine=UltraPilotEngine.__new__(UltraPilotEngine);engine._automatic_replay_directory=str(tmp_path)
    journal=PedalJournal();journal.enabled=True
    journal.significant('AVOID_OBSTACLE',{'context':[1,'session','map','data','intent',7,'build','geometry']},100.)
    if quota=='files':
        for i in range(8):(tmp_path/f'steering-replay-{i}-significant_event.json').write_bytes(b'original')
    else:
        with (tmp_path/'steering-replay-original-significant_event.json').open('wb') as stream:
            stream.seek(16*1024*1024-2);stream.write(b'x')  # One byte of quota remains.
    original={p.name:p.stat().st_size for p in tmp_path.iterdir()}
    engine._finish_significant_longitudinal_event(journal,shutdown=True)
    result=engine._automatic_replay_writer.wait(5.)
    assert result['error_detail']=='SIGNIFICANT_EVENT_EXPORT_DISK_QUOTA'
    assert {p.name:p.stat().st_size for p in tmp_path.iterdir()}==original


def test_automatic_fault_waits_for_single_job_and_keeps_preceding_receipt(flow,tmp_path):
    import threading
    from core.steering_replay import AsyncReplayExporter
    values,step=directed_stop(flow)
    state,truck,engine,ap,tick,n,clock,writes,collected=values
    engine._automatic_replay_directory=str(tmp_path)
    step(4,8.,color=8)  # Publish after the fixture's geometry-token change.
    journal=engine.controller._pedal_journal
    journal.significant('AVOID_OBSTACLE',{'context':list(context(state)),
        'actor':{'id':71,'ttc_s':3.}},clock[0])
    gate=threading.Event();entered=threading.Event()
    writer=engine._automatic_replay_writer=AsyncReplayExporter()
    def slow():entered.set();gate.wait(5.);return 'earlier-job'
    writer.submit(slow);assert entered.wait(1.)
    command=state.get('longitudinal_command');command['sdk_frame_us']+=10000000
    state.set('longitudinal_command',command);engine._flush_controls()
    fault=engine._automatic_longitudinal_fault
    assert 'ahead of vehicle observation' in fault['reason']
    assert getattr(engine,'_automatic_longitudinal_export_epoch',None)!=fault['epoch']
    gate.set();writer.wait(5.)
    clock[0]+=.11;engine._flush_controls()
    path=writer.wait(5.)['path'];checked=inspect_replay(path)
    assert checked['integrity_valid']
    block=checked['replay']['longitudinal']
    assert block['first_intervention']['reason']==fault['reason']
    preceding=block['preceding_significant_event_receipt']
    assert preceding['receipt']['actor']['id']==71 and preceding['sealed_history_superseded_by_fault']
    assert any(e['source'].get('phase')=='safety_stop' for e in block['events'])
