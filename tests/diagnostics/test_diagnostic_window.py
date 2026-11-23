"""Diagnostic models; these do not reconstruct missing historical actors."""
from copy import deepcopy
import pytest
from core.navigation.longitudinal_diagnostics import PedalJournal


def decision(t, **changes):
    value=dict(context=[7,'session','map','dataset','intent',12,'build','geometry'],
        activation=7,sdk_frame_us=int(t*1e6),observation_timestamp=t-.01,
        actual_speed_mps=10.,observed_gear=4,phase='active',
        selected=dict(source='acc',reason='drive',throttle=.2,brake=0.),
        inputs=dict(traffic=dict(following=dict(target_id='42',status='candidate'))))
    value.update(changes)
    return value


def test_thirty_before_ten_after_and_first_reason_survive_new_activation():
    journal=PedalJournal();journal.enabled=True;journal.enable_incident_window()
    for i in range(601):
        t=100.+i*.1;value=decision(t)
        journal.observe_incident('decision',value,t)
        if i==400:journal.incident_event('TECHNICAL_STOP',dict(reason='original',epoch=7),t)
        if i==402:journal.incident_event('REACTIVATION',dict(epoch=8),t)
        if i==401:journal.incident_event('TECHNICAL_STOP',dict(reason='later',epoch=7),t)
        ready=journal.seal_incident(t)
        if ready:break
    assert ready['first_reason']=='original'
    assert ready['range_s']['pre_s']>=29.9
    assert ready['range_s']['post_s']>=10.
    assert [e['kind'] for e in ready['subevents']]==['TECHNICAL_STOP','TECHNICAL_STOP','REACTIVATION']
    assert not ready['runtime_authorized'] and not ready['confirmed']


def test_consumed_source_is_immutable_and_missing_is_not_zero():
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    source=decision(100.);original=deepcopy(source)
    j.observe_incident('decision',source,100.)
    source['selected']['brake']=1.
    j.incident_event('BRAKING',{},100.)
    result=j.seal_incident(101.,shutdown=True)
    assert result['records'][0]['value']==original
    assert result['range_s']['post_incomplete']
    assert result['unavailable']['physical_vehicle_color']=='unavailable'


def test_full_detail_budget_still_keeps_first_fault_frame_clock_and_identity():
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    details=dict(checked_at=100.05,sdk_frame_us=42,observation_timestamp=100.,
        computed_at=100.01,expires_at=100.5,actual_context=[7,'session'],expected_context=[7,'session'])
    j.incident_event('TECHNICAL_STOP',dict(reason='original',epoch=7,observed_at=100.05,
        producer='engine',details=details,huge=['x'*30000]*20),100.05)
    value=j.seal_incident(110.05)['first_intervention']['receipt']
    assert value['reason']=='original' and value['observed_at']==100.05
    assert value['priority_details']['sdk_frame_us']==42
    assert value['priority_details']['observation_timestamp']==100.
    assert value['priority_details']['actual_context']==[7,'session']


def test_malformed_optional_packet_fields_are_recorded_without_affecting_control():
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    value=dict(packet=dict(valid=False,following=['invalid'],signal='invalid',selected=['invalid']))
    j.observe_incident('consumer_traffic',value,100.)
    j.incident_event('TECHNICAL_STOP',dict(reason='original',summary=['invalid'],details='invalid'),100.)
    result=j.seal_incident(110.)
    assert result['records'][0]['value']==value
    assert result['first_reason']=='original'


def test_capacity_loss_and_two_simultaneous_events_are_explicit():
    j=PedalJournal();j.enabled=True;j.enable_incident_window(byte_limit=4096)
    for i in range(30):j.observe_incident('decision',decision(100.+i*.1),100.+i*.1)
    j.incident_event('AEB',{'reason':'danger'},103.)
    j.incident_event('TECHNICAL_STOP',{'reason':'technical'},103.)
    result=j.seal_incident(114.)
    assert result['first_reason']=='danger'
    assert len(result['subevents'])==2
    assert result['capacity_drops']>0 and result['incomplete']
    assert j.incident_status()['retained_bytes']<=4096


def test_short_consumer_rejection_between_periodic_samples_keeps_original_packet():
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    good=dict(context=[1,'s'],sdk_frame_us=1,observation_timestamp=100.,valid=True)
    rejected=dict(good,sdk_frame_us=2,valid=False)
    j.observe_incident('consumer_acc',dict(packet=good,reason=''),100.)
    j.observe_incident('consumer_acc',dict(packet=rejected,reason='original target unavailable'),100.02)
    j.observe_incident('consumer_acc',dict(packet=good,reason=''),100.04)
    j.incident_event('TECHNICAL_STOP',dict(reason='first'),100.04)
    result=j.seal_incident(110.04)
    assert [r['value']['packet']['valid'] for r in result['records']]==[True,False,True]
    assert result['records'][1]['value']['packet']==rejected


def test_short_native_brake_edge_keeps_exact_raw_acquisition_between_samples():
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    for i,brake in enumerate((0.,.4,0.)):
        j.observe_incident('traffic',dict(packet=dict(traffic_brake=brake,sdk_frame_us=i+1),
            capture=dict(moving=bytes([i]),source=dict(generation=i+1))),100.+i*.02)
    j.incident_event('BRAKING',{},100.04)
    records=j.seal_incident(110.04)['records']
    assert [r['value']['capture']['moving'] for r in records]==[b'\0',b'\1',b'\2']
    assert [r['value']['packet']['sdk_frame_us'] for r in records]==[1,2,3]


def test_long_related_braking_wait_and_green_remain_one_dossier():
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    for i in range(301):j.observe_incident('decision',decision(100.+i*.1),100.+i*.1)
    j.incident_event('BRAKING',{'reason':'red'},130.)
    for i in range(1,501):
        now=130.+i*.1
        j.observe_incident('decision',decision(now),now)
        j._incident_window.keep_activity(now)
        assert j.seal_incident(now) is None
    j.incident_event('GREEN_RESUME',{},180.)
    for i in range(1,102):
        now=180.+i*.1;j.observe_incident('decision',decision(now),now)
    result=j.seal_incident(190.1)
    assert result['first_reason']=='red' and result['range_s']['pre_s']>=29.9
    assert [e['kind'] for e in result['subevents']]==['BRAKING','GREEN_RESUME']
    # Busy/long episodes must retain the actual middle, not merely report the
    # prefix/tail loss this regression originally documented.
    rows=[r for r in result['records'] if r['kind']=='decision']
    assert len(rows)==902
    assert rows[0]['at_s']==pytest.approx(100.) and rows[-1]['at_s']==pytest.approx(190.1)
    assert all(r['value']==decision(r['at_s']) for r in rows)
    assert not result['sampling']['gaps']['decision']
    assert not result['incomplete']


@pytest.mark.parametrize('case',[('GPS_CHANGE',12,13),('ACC_LOST','42','lead'),
    ('HOLD_MOTION',.054094,'continuous_service_brake'),('ACC_LOST','39','crossing')])
def test_oct24_compact_cause_survives_without_inventing_scene(case):
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    j.observe_incident('decision',decision(100.),100.)
    j.incident_event(case[0],{'recorded_values':list(case[1:]),'actors':'unavailable'},100.)
    result=j.seal_incident(110.)
    assert result['subevents'][0]['receipt']['recorded_values']==list(case[1:])
    assert result['subevents'][0]['receipt']['actors']=='unavailable'


def test_existing_replay_export_owns_raw_capture_and_rejects_corruption(tmp_path):
    from core.steering_replay import export_incident,inspect_incident
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    j.observe_incident('traffic',dict(moving=b'original moving',parked=b'original parked'),100.)
    j.incident_event('AEB',{'reason':'original'},100.)
    window=j.seal_incident(110.)
    path=export_incident(tmp_path,window,j.snapshot(expanded=False,include_history=True))
    checked=inspect_incident(path)
    assert checked['integrity_valid'] and not checked['confirmed']
    raw=checked['replay']['longitudinal']['diagnostic_incident']['records'][0]['value']['moving']
    import base64,zlib
    # The simple exact-record codec restores original bytes; legacy exports
    # expose the older zlib wrapper. Both must preserve the SAME source bytes.
    restored=raw if isinstance(raw,bytes) else zlib.decompress(base64.b64decode(raw['data']))
    assert restored==b'original moving'
    from pathlib import Path
    part=tmp_path/checked['dossier']['replay']
    part.write_bytes(part.read_bytes()+b'corrupt')
    assert not inspect_incident(path)['integrity_valid']


def test_archive_closed_incidents_recovers_quota_without_deletion(tmp_path):
    from core.steering_replay import export_incident,inspect_incident
    paths=[]
    for i in range(9):
        j=PedalJournal();j.enabled=True;j.enable_incident_window()
        j.observe_incident('decision',decision(100.),100.)
        j.incident_event('TECHNICAL_STOP',{'reason':str(i)},100.)
        paths.append(export_incident(tmp_path,j.seal_incident(110.),j.snapshot()))
    active=list(tmp_path.glob('incident-*.json'))
    archived=list((tmp_path/'archive').rglob('incident-*.json'))
    assert len(active)==8 and len(archived)==1
    assert all(inspect_incident(p)['integrity_valid'] for p in active+archived)


def test_failed_worker_retains_window_for_bounded_retry_and_records_failure(tmp_path,monkeypatch):
    import core.steering_replay as replay
    from core.navigation.longitudinal_diagnostics import finish_engine_incident
    from types import SimpleNamespace
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    j.observe_incident('decision',decision(100.),100.)
    j.incident_event('TECHNICAL_STOP',dict(reason='first fault'),100.)
    engine=SimpleNamespace(_automatic_replay_directory=str(tmp_path))
    original=replay.export_incident_isolated
    def fail(*args):raise OSError('MODELED_DISK_FULL')
    monkeypatch.setattr(replay,'export_incident_isolated',fail)
    assert finish_engine_incident(engine,j,shutdown=True)
    engine._automatic_replay_writer.wait(5.)
    assert engine._diagnostic_export_retry['window']['first_reason']=='first fault'
    assert engine._diagnostic_incident_failure['complete'] is False
    assert len(list(tmp_path.glob('incident-failure-*.txt')))==1
    monkeypatch.setattr(replay,'export_incident_isolated',original)
    finish_engine_incident(engine,j,shutdown=True)
    result=engine._automatic_replay_writer.wait(5.)
    assert result['path'] and engine._diagnostic_export_retry is None
    assert replay.inspect_incident(result['path'])['integrity_valid']


def test_disk_preflight_never_claims_ready_on_low_space(tmp_path,monkeypatch):
    import shutil
    from core.steering_replay import incident_diagnostic_budget
    monkeypatch.setattr(shutil,'disk_usage',lambda path:type('Space',(),{'free':1024})())
    assert incident_diagnostic_budget(tmp_path)['ready'] is False


def test_partial_manifest_failure_can_retry_without_overwriting_evidence(tmp_path,monkeypatch):
    import core.steering_replay as replay
    from pathlib import Path
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    j.observe_incident('decision',decision(100.),100.)
    j.incident_event('TECHNICAL_STOP',dict(reason='original'),100.)
    window=j.seal_incident(110.)
    original=replay.os.replace
    def fail(source,target):
        if Path(target).name.startswith('incident-'):raise OSError('MODELED_MANIFEST_COMMIT_FAILURE')
        return original(source,target)
    monkeypatch.setattr(replay.os,'replace',fail)
    with pytest.raises(OSError):replay.export_incident(tmp_path,window,j.snapshot())
    overview=next(tmp_path.glob('incident-*.md'));before=overview.read_bytes()
    monkeypatch.setattr(replay.os,'replace',original)
    path=replay.export_incident(tmp_path,window,j.snapshot())
    assert replay.inspect_incident(path)['integrity_valid']
    assert overview.read_bytes()==before


def test_exact_consumer_inputs_survive_existing_dense_replay(tmp_path):
    from core.steering_replay import SteeringReplayBuffer,inspect_replay
    from core.navigation.longitudinal_diagnostics import _IncidentWindow,diagnostic_consume
    from types import SimpleNamespace
    replay=SteeringReplayBuffer(2)
    replay._diagnostic_inputs=_IncidentWindow(32*1024*1024)
    state=SimpleNamespace(_diagnostic_consumer=replay.append_consumer_input)
    first=dict(valid=True,context=[1,'original'],sdk_frame_us=42,observation_timestamp=100.)
    expected=deepcopy(first)
    diagnostic_consume(state,'traffic',dict(packet=first,read_returned_at=100.02),100.02)
    first.update(sdk_frame_us=99,observation_timestamp=101.)
    replay.append(dict(sdk_frame_us=99))
    path=replay.export(tmp_path,reason='automatic_disable')
    checked=inspect_replay(path)
    assert checked['integrity_valid']
    row=checked['replay']['diagnostic_consumed_inputs']['records'][0]
    assert row['value']['packet']==expected
    assert row['value']['read_returned_at']==100.02


def test_source_id_slot_lifecycle_and_invalid_values_are_preserved_not_repaired():
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    sources=[dict(lifecycle=1,generation=7,id=42,slot=3,valid=True),
        dict(lifecycle=1,generation=8,id=42,slot=5,valid=False),
        dict(lifecycle=2,generation=1,id=39,slot=0,valid=True)]
    for i,source in enumerate(sources):
        j.observe_incident('native',dict(source=source,actors=[dict(id=42),dict(id=42)]),100.+i*.2)
    j.incident_event('TECHNICAL_STOP',dict(reason='original'),100.5)
    result=j.seal_incident(111.)
    assert [r['value']['source'] for r in result['records']]==sources
    assert all(len(r['value']['actors'])==2 for r in result['records'])


def test_full_archive_budget_fails_before_writing_new_parts(tmp_path,monkeypatch):
    import core.steering_replay as replay
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    j.incident_event('TECHNICAL_STOP',dict(reason='original'),100.)
    original=replay.incident_diagnostic_budget
    def full(path):return dict(original(path),ready=False,archive_bytes=512*1024*1024)
    monkeypatch.setattr(replay,'incident_diagnostic_budget',full)
    with pytest.raises(ValueError,match='BUDGET'):
        replay.export_incident(tmp_path,j.seal_incident(110.),j.snapshot())
    assert not list(tmp_path.iterdir())


def test_engine_and_autopilot_exports_share_one_hash_checked_dossier(tmp_path):
    from core.steering_replay import SteeringReplayBuffer,export_incident_isolated,inspect_incident
    from core.navigation.longitudinal_diagnostics import _IncidentWindow
    replay=SteeringReplayBuffer(2);replay._diagnostic_inputs=_IncidentWindow(32*1024*1024)
    fault=dict(epoch=7,observed_at=130.,reason='same original',kind='technical')
    replay.append_consumer_input('consumer_traffic',dict(packet=dict(valid=False,sdk_frame_us=42)),130.)
    replay.append(dict(sdk_frame_us=42))
    dense=replay.export(tmp_path,reason='automatic_disable',identity=dict(control_intervention=fault))
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    j.observe_incident('ego',dict(speed=0.,gear=4),130.)
    j.incident_event('TECHNICAL_STOP',fault,130.)
    main=export_incident_isolated(tmp_path,j.seal_incident(140.),j.snapshot())
    checked=inspect_incident(main)
    assert checked['integrity_valid']
    related=checked['dossier']['related_original_exports']
    from pathlib import Path
    assert len(related)==1 and related[0]['name']==Path(dense).name
    assert related[0]['incident_id']==checked['dossier']['incident_id']
    assert len(list(tmp_path.glob('incident-*.json')))==1
    assert Path(dense).name in [r['name'] for r in checked['dossier']['files']]


@pytest.mark.parametrize('name',['01-201154-gps','02-201351-acc42','03-201435-hold','04-201522-acc39'])
def test_preserved_oct24_first_intervention_is_not_reclassified_as_timeout(name):
    import json
    from pathlib import Path
    path=Path(__file__).resolve().parents[2]/'docs/steering-audit/oct24-driving-incidents'/ (name+'.json')
    case=json.loads(path.read_text(encoding='utf-8'))
    original=case['first_interventions'][0]
    # Historical receipt, not a synthetic reconstruction of absent actors.
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    j.incident_event('TECHNICAL_STOP',original,case['monotonic_s'])
    result=j.seal_incident(case['monotonic_s']+10.)
    assert result['first_reason']==original['reason']
    assert result['first_intervention']['receipt']['observed_at']==original['observed_at']
    assert result['range_s']['pre_incomplete'] and result['incomplete']
    if name.endswith(('acc42','acc39')):
        assert 'stale' not in original['reason'] and 'expired' not in original['reason']


def test_diagnostic_activation_receipt_preserves_unavailable_snapshot_explicitly():
    from types import SimpleNamespace
    from core.navigation.longitudinal_diagnostics import observe_engine_incident
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    engine=SimpleNamespace(controller=SimpleNamespace(_pedal_journal=j))
    observe_engine_incident(engine,'activation',dict(source='hotkey',enabled=False,
        pending_started=False,reason='original rejection',request_id=None,ego=None))
    result=j.seal_incident(10**12,shutdown=True)
    assert result['subevents'][0]['kind']=='ACTIVATION_REJECTED'
    assert result['subevents'][0]['receipt']['ego'] is None
    assert result['first_reason']=='original rejection'


@pytest.mark.parametrize('mode',[0,3])
def test_installed_base_production_outputs_and_ipc_reads_are_identical(tmp_path,mode):
    """Run this also in the staged installed-base interpreter, not just HEAD."""
    from contextlib import contextmanager
    from collections import Counter
    from tests.test_activation_observation_binding import flow
    from tests.signals.test_signal_lifecycle import lifecycle
    results=[]
    for enabled in (False,True):
        with contextmanager(flow.__wrapped__)() as base:
            state,truck,engine,ap,tick,n,clock,writes,_=lifecycle(base,mode)
            journal=engine.controller._pedal_journal
            if enabled:journal.enable_incident_window()
            else:journal._incident_window=None
            counts=Counter();state.hook=lambda key:counts.update([key])
            # Disk worker is covered separately; this comparison includes the
            # actual Controller, full source tap and byte accounting.
            engine._automatic_replay_directory=None
            for i in range(180):
                red=40<=i<95
                stopped=60<=i<105
                tick(0 if stopped else 4,0. if stopped else .4 if red else 5.,color=2 if red else 8)
            results.append(dict(writes=[(ch,v) for _,ch,v,_ in writes],reads=dict(counts),
                active=state.get('autopilot_active'),fault=state.get('autopilot_intervention')))
            state.hook=None
    assert results[0]==results[1]
    assert results[1]['active'] and not results[1]['fault']
