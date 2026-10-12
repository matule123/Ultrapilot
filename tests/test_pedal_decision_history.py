"""Existing journal/production lifecycle; no installed files or game inputs."""
import pytest
from pathlib import Path

from core.navigation.longitudinal_diagnostics import PedalJournal
from core.steering_replay import SteeringReplayBuffer, inspect_replay
from tests.test_activation_observation_binding import flow  # noqa: F401
from tests.test_oct4_signal_lifecycle import lifecycle


def bound(journal,t,throttle,brake,*,identity='session',reason='drive',error=False):
    journal.begin_decision()
    journal.bind(dict(context=['a',identity,'map','data','intent',7,'build','token'],
        activation='a',sdk_frame_us=int(t*1e6),observation_timestamp=t-.01,
        sdk_observation=dict(valid=True),observed_gear=4,actual_speed_mps=10.,
        phase='active',decision_sequence=journal.next_decision(),
        selected=dict(throttle=throttle,brake=brake,source='acc',reason=reason),
        output_intent=dict(throttle=throttle,brake=brake),
        inputs=dict(acc=dict(requested_speed_kmh=50.,constrained_speed_kmh=40.,control_target_kmh=40.))))
    for channel,value in (('throttle',throttle),('brake',brake)):
        journal.record(channel,value,t,t+.001,'SCS_SDK',
            dict(status='MAPPING_WRITE_FAILED' if error else 'MAPPING_WRITE_RETURNED',
                 value=None if error else value),error='OSError' if error else None)
    journal.finish_decision(t+.001)


def test_history_preserves_short_changes_between_regular_samples(tmp_path):
    journal=PedalJournal();journal.enabled=True
    bound(journal,100.,.2,0.)
    bound(journal,100.02,0.,.3,reason='brake')
    bound(journal,100.04,.2,0.)
    bound(journal,100.11,.2,0.)
    saved=journal.snapshot(include_history=True)
    history=saved['decision_history']
    assert len(history['regular_samples']) == 2
    assert [r['pedal_mode'] for r in history['changes'][:3]] == ['drive','brake','drive']
    assert history['regular_samples'][-1]['aggregate']['pedal_mode_changes'] == 2
    assert history['regular_samples'][-1]['aggregate']['brake_max'] == .3
    path=SteeringReplayBuffer(2).export(tmp_path,reason='automatic_disable',longitudinal=saved)
    assert inspect_replay(path)['replay']['longitudinal']['decision_history'] == history
    from tools.analyze_longitudinal_evidence import load_rows
    rows,checked=load_rows(Path(path))
    assert checked['decision_history']==history and len(rows)==len(saved['events'])


def test_sixty_second_production_history_exports_last_thirty_seconds(flow,tmp_path,monkeypatch):
    import time
    state,truck,engine,ap,tick,n,clock,writes,collected=lifecycle(flow,full_identity=True)
    monkeypatch.setattr(time,'monotonic',lambda:clock[0])
    engine._maneuver_diagnostic_collector=None
    start=clock[0]
    for i in range(1200):
        t=i*.05
        red=(35<=t<42 or 52<=t<58)
        stopped=(37<=t<43 or 54<=t<59)
        tick(0 if stopped else 4,0. if stopped else 1. if red else 10.,color=2 if red else 8)
        assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
        writes.clear()
    saved=engine.controller._pedal_journal.snapshot(include_history=True)
    history=saved['decision_history']
    assert history['observed_range_s']['duration'] >= 29.9, (
        len(history['regular_samples']),history['regular_dropped_capacity'],
        history['capture_failures'],history['regular_samples'][-1])
    assert history['window_end_s']-start >= 59.9
    assert history['incomplete'] is False
    assert history['regular_dropped_capacity'] == history['change_dropped_capacity'] == 0
    assert any(r['pedal_mode']=='brake' and r['gear']>0 for r in history['changes'])
    assert any(r['hold_phase'] and r['gear']==0 for r in history['regular_samples'])
    assert any(r['signal_color']=='green' for r in history['changes'])
    # Actual automatic Engine incident, including original first rejection and
    # subsequent existing safe writes; no manual collection or export request.
    engine._automatic_replay_directory=str(tmp_path)
    command=state.get('longitudinal_command');command['sdk_frame_us']+=10000000
    state.set('longitudinal_command',command)
    engine._flush_controls()
    clock[0]+=.11
    engine._flush_controls()
    path=engine._automatic_replay_writer.wait(5.)['path']
    checked=inspect_replay(path)
    assert checked['integrity_valid']
    assert checked['replay']['longitudinal']['decision_history']['observed_range_s']['duration'] >= 29.9
    h=checked['replay']['longitudinal']['decision_history']
    assert any('ahead of vehicle observation' in (r['first_reason'] or '') for r in h['changes'])
    assert any(e['source']['phase']=='safety_stop' for e in checked['replay']['longitudinal']['events'])


def test_history_identity_backend_failure_and_capacity_are_explicit(tmp_path):
    journal=PedalJournal();journal.enabled=True
    bound(journal,100.,.2,0.)
    bound(journal,100.02,0.,.3,identity='new-session',reason='brake',error=True)
    h=journal.snapshot(include_history=True)['decision_history']
    assert len(h['identities']) == 2
    last=h['changes'][-1]
    assert last['write_error_count']==2 and last['written_throttle'] is None
    assert h['identities'][last['identity_reference']]['context'][1]=='new-session'
    # Burst beyond the fixed event reservation; 10 Hz samples still record the
    # changes/min/max. Ordered event loss cannot masquerade as complete proof.
    journal._history.CHANGE_CAPACITY=2
    for i in range(15):bound(journal,100.04+i*.02,.2 if i%2 else 0.,0. if i%2 else .3,reason=str(i))
    saved=journal.snapshot(include_history=True)
    assert saved['decision_history']['change_dropped_capacity'] > 0
    assert saved['decision_history']['incomplete']
    assert any(r['aggregate']['state_changes']>=4 for r in saved['decision_history']['regular_samples'])
    path=SteeringReplayBuffer(2).export(tmp_path,reason='automatic_disable',longitudinal=saved)
    checked=inspect_replay(path)
    assert checked['integrity_valid'] and checked['history_incomplete']


def test_summary_does_not_turn_missing_values_into_zero():
    j=PedalJournal();j.enabled=True;j.begin_decision()
    j.bind(dict(phase='inactive',sdk_frame_us=1,observation_timestamp=1.))
    j.finish_decision(1.1)
    h=j.snapshot(include_history=True)['decision_history'];r=h['regular_samples'][0]
    assert r['speed_mps'] is r['gear'] is r['throttle'] is r['signal_id'] is None
    assert r['pedal_mode']=='unknown' and h['warmup']


def test_publication_reread_and_manual_activation_stay_bound(flow):
    state,truck,engine,ap,tick,n,clock,writes,collected=lifecycle(flow)
    engine._maneuver_diagnostic_collector=None
    epoch=state.get('autopilot_failure_epoch')
    original=state.get('telemetry')['truck']['sdkFrameTimeUs']
    fired=[]
    def publish_during_read(key):
        if key=='longitudinal_command' and not fired:
            fired.append(True);state.hook=None;tick(4,.6,flush=False)
    state.hook=publish_during_read
    engine._flush_controls()
    saved=engine.controller._pedal_journal.snapshot(include_history=True)
    # Snapshot sequence is not falsely overwritten with the initial vehicle.
    bound_source=saved['events'][-1]['source']
    assert bound_source['sdk_frame_us']>original
    assert bound_source['command_observation_pairing']['reread_count']==1
    # Force only diagnostic sampling time to advance via an actual next tick.
    tick(4,.6,dt=.11)
    rows=engine.controller._pedal_journal.snapshot(include_history=True)['decision_history']['regular_samples']
    assert rows[-1]['command_sdk_frame_us']>original
    assert rows[-1]['activation']==epoch
    n();engine._flush_controls()
    n();tick(4,.6)
    h=engine.controller._pedal_journal.snapshot(include_history=True)['decision_history']
    assert any(r['phase']=='release' for r in h['changes'])
    releases=[r for r in h['changes'] if r['phase']=='release']
    assert releases[-1]['written_throttle']==releases[-1]['written_brake']==0.
    assert any(r['activation'] not in (None,epoch) for r in h['changes'])


def test_replay_rejects_damaged_history_even_when_outer_hash_is_recomputed(tmp_path):
    import json
    from pathlib import Path
    from core.steering_replay import _payload_hash,_intern_values
    j=PedalJournal();j.enabled=True;bound(j,100.,.2,0.)
    path=SteeringReplayBuffer(2).export(tmp_path,reason='automatic_disable',longitudinal=j.snapshot(include_history=True))
    checked=inspect_replay(path)
    block=checked['replay']['longitudinal']
    block['decision_history']['changes'][0]['identity_reference']='missing'
    payload=json.loads(Path(path).read_text(encoding='utf-8'))
    payload['longitudinal_storage']=_intern_values(block)
    payload['integrity']['payload_sha256']=_payload_hash(payload)
    Path(path).write_text(json.dumps(payload),encoding='utf-8')
    assert inspect_replay(path)['integrity_valid'] is False


def test_controller_failure_and_first_fault_survive_release_in_history():
    from tests.test_longitudinal_evidence_diagnostics import memory_controller
    ctl=memory_controller();j=ctl._pedal_journal=PedalJournal();j.enabled=True
    source=dict(context=['epoch','session','map','data','intent',7,'build','token'],
        activation='epoch',sdk_frame_us=100,observation_timestamp=10.,
        sdk_observation=dict(valid=True),output_intent=dict(throttle=.2,brake=0.),
        phase='active',actual_speed_mps=1.,observed_gear=4)
    j.bind(source);ctl.set_throttle(.2);ctl.set_brake(0.)
    fault=dict(epoch='epoch',reason='original backend failure',observed_at=10.1,
        context=source['context'],sdk_frame_us=100,observation_timestamp=10.)
    j.history_intervention(fault)
    ctl.scs._buf.close();ctl.set_throttle(.3);ctl.release_all()
    h=j.snapshot(include_history=True)['decision_history']
    assert any(r['write_error_count'] and r['last_backend_status']=='MAPPING_WRITE_FAILED' for r in h['changes'])
    assert h['changes'][-1]['first_reason']=='original backend failure'
    assert h['changes'][-1]['written_throttle'] is None
    assert h['changes'][-1]['phase']=='release'
    assert h['changes'][-1]['observation_timestamp']==10.


def test_summary_keeps_flat_acc_contract_separate_from_current_traffic_candidate():
    j=PedalJournal();j.enabled=True;j.begin_decision()
    j.bind(dict(phase='active',output_intent=dict(throttle=.2,brake=0.),
        inputs=dict(acc=dict(following_target_id='acc-old',following_status='protective_candidate',
            following_confirmed=False,speed_control_reason='speed tracking'),
            traffic=dict(following=dict(target_id='traffic-new',gap_m=25.,confirmed=False)))))
    j.finish_decision(100.)
    r=j.snapshot(include_history=True)['decision_history']['regular_samples'][0]
    assert r['acc_target_id']=='acc-old' and r['acc_confirmed'] is False
    assert r['acc_status']=='protective_candidate' and r['acc_gap_m'] is None
    assert r['traffic_target_id']=='traffic-new' and r['traffic_gap_m']==25.


def test_history_snapshot_is_owned_and_clock_regression_is_explicit():
    j=PedalJournal();j.enabled=True;bound(j,100.,.2,0.)
    a=j.snapshot(expanded=False,include_history=True)
    bound(j,100.2,0.,.3,identity='new-session',reason='brake')
    from core.navigation.longitudinal_diagnostics import expand_journal
    saved=expand_journal(a)['decision_history']
    assert len(saved['identities'])==1
    assert saved['changes'][-1]['observation_timestamp']==99.99
    saved['identities']['1']['context'][1]='mutated'
    current=j.snapshot(include_history=True)['decision_history']
    assert all(v['context'][1]!='mutated' for v in current['identities'].values())
    bound(j,99.,.1,0.)
    current=j.snapshot(include_history=True)['decision_history']
    assert current['time_regressions']==1 and current['incomplete']


def test_sixty_second_change_storm_keeps_regular_window_and_reports_order_loss():
    j=PedalJournal();j.enabled=True
    for i in range(3000):
        bound(j,100.+i*.02,.2 if i%2 else 0.,0. if i%2 else .3,reason='drive' if i%2 else 'brake')
    h=j.snapshot(include_history=True)['decision_history']
    assert h['observed_range_s']['duration']>=29.9
    assert h['retained_bytes']<=h['byte_budget']==1048576
    assert h['regular_dropped_capacity']==0
    assert h['change_dropped_capacity']>0 and h['incomplete']
    assert any(r['aggregate']['pedal_mode_changes']>=4 and r['aggregate']['brake_max']==.3
        and r['aggregate']['throttle_max']==.2 for r in h['regular_samples'])


def test_multiple_physical_edges_inside_one_flush_are_aggregated_without_fake_order():
    j=PedalJournal();j.enabled=True;j.begin_decision()
    j.bind(dict(phase='launch',output_intent=dict(throttle=.12,brake=0.)))
    for c,v in (('brake',0.),('throttle',.12)):
        j.record(c,v,100.,100.,'SCS_SDK',dict(status='MAPPING_WRITE_RETURNED',value=v))
    j.bind(dict(phase='release',output_intent=dict(throttle=0.,brake=0.)))
    j.record('throttle',0.,100.001,100.001,'SCS_SDK',dict(status='MAPPING_WRITE_RETURNED',value=0.))
    j.finish_decision(100.002)
    r=j.snapshot(include_history=True)['decision_history']['regular_samples'][0]
    assert r['backend_throttle_min']==0. and r['backend_throttle_max']==.12
    assert r['backend_pair_mode_changes']>=2 and r['write_source_changes']==1
    assert r['aggregate']['backend_throttle_max']==.12
    assert r['aggregate']['exact_write_timing'] is False


def test_combined_dense_and_automatic_history_exports_coexist(flow,tmp_path,monkeypatch):
    import copy
    from dataclasses import replace
    from core.navigation.evidence_diagnostics import EvidenceDiagnosticCollector
    from tests.test_real_evidence_diagnostics import capture,command
    from tools.analyze_longitudinal_evidence import load_rows
    import plugins.autopilot.main as module
    monkeypatch.setattr(module,'app_dir',lambda:str(tmp_path))
    state,truck,engine,ap,tick,n,clock,writes,collected=lifecycle(flow)
    engine._automatic_replay_directory=str(tmp_path/'route-diagnostics')
    for i in range(40):tick(4,.4+i*.01)
    # Existing combined capture is nondestructive; it does not replicate the
    # entire thirty-second ring into every sample/chunk.
    assert all('decision_history' not in r.longitudinal for r in collected.samples)
    exporter=EvidenceDiagnosticCollector(tmp_path/'evidence-diagnostics',capacity=120)
    exporter.apply_command(command(1,collection_id='history-coexist'))
    for i,saved in enumerate(collected.samples):
        profile=copy.deepcopy(capture(i,when=1000.).profile)
        profile['observation'].update(sdk_frame_us=saved.truck['sdkFrameTimeUs'],captured_at=saved.captured_at_s)
        profile['observation']['articles'][0]['position_m']=[saved.truck[k] for k in ('x','y','z')]
        exporter._ingest(replace(saved,profile=profile))
    p=state.get('longitudinal_command');p['sdk_frame_us']+=10000000
    state.set('longitudinal_command',p);engine._flush_controls()
    ap._publish_automatic_disable('later cleanup');engine._flush_controls()
    exporter.finalize()
    assert exporter.status()['state']=='READY_FOR_OFFLINE_REVIEW',exporter.status()
    rows,checked=load_rows(tmp_path/'evidence-diagnostics'/'history-coexist')
    assert checked['integrity_valid'] and rows
    dense=ap._replay_export_writer.wait(5.)
    incident=engine._automatic_replay_writer.wait(5.)
    assert dense['path']!=incident['path'] and not dense['error'] and not incident['error']
    assert inspect_replay(dense['path'])['replay']['sample_count']>0
    checked=inspect_replay(incident['path'])
    assert checked['integrity_valid']
    assert checked['replay']['longitudinal']['decision_history']['regular_samples']
    assert 'ahead of vehicle observation' in checked['replay']['longitudinal']['first_intervention']['reason']
