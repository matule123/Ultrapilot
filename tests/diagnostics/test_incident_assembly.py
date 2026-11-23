"""The non-disable collection contract, not a game-behavior change."""
from contextlib import contextmanager
from pathlib import Path
import json
import pytest

try:
    from core.navigation.diagnostic_build_config import ENABLED as CANDIDATE_ENABLED
except ImportError:
    CANDIDATE_ENABLED=False


@pytest.mark.parametrize('mode',[0,3])
@pytest.mark.parametrize('stop',[False,True],ids=['short-brake','red-wait-green'])
@pytest.mark.skipif(not CANDIDATE_ENABLED,reason='Requires the isolated diagnostic runtime overlay; ordinary source has no AP instrumentation')
def test_live_episode_assembles_ap_inputs_without_any_disable(tmp_path,monkeypatch,mode,stop):
    from tests.test_activation_observation_binding import flow
    from tests.signals.test_signal_lifecycle import lifecycle
    from core.steering_replay import inspect_incident
    from types import SimpleNamespace
    import tests.signals.test_signal_lifecycle as scene
    with contextmanager(flow.__wrapped__)() as raw:
        state,truck,engine,ap,tick,n,clock,writes,_=lifecycle(raw,mode)
        journal=engine.controller._pedal_journal
        journal.enable_incident_window()
        engine._automatic_replay_directory=None
        ap._diagnostic_part_directory=str(tmp_path)
        engine._traffic_brake_basis=None  # No modeled actor brake request.
        # The scene provides modeled SDK/signal bytes. Use the actual Engine
        # publication, including the diagnostic request on that same packet.
        def publish_traffic(state,truck,source,**values):
            assert source=='traffic'
            capture=SimpleNamespace(session='test-session',observed_at=clock[0],
                moving=b'',parked=b'',stable=True,source={})
            return engine._publish_traffic_control(truck,truck['_control_observation']['observed_at'],
                __import__('core.longitudinal',fromlist=['context']).context(state),[],capture,
                dict(status='no_candidate_unproven_coverage'),0.,values['signal'],None)
        monkeypatch.setattr(scene,'publish',publish_traffic)
        for _ in range(310):tick(4,5.,color=8,dt=.1)
        engine._automatic_replay_directory=str(tmp_path)
        activation=state.get('autopilot_failure_epoch')
        tick(4,.2 if stop else 5.,color=2,dt=.1)
        pending=journal._incident_window.pending
        assert pending
        incident_id=pending['incident_id']
        for _ in range(12):tick(0 if stop else 4,0. if stop else 4.,color=2,dt=.1)
        if stop:
            tick(0 if mode==0 else 4,0.,color=8,dt=.1)
            tick(0 if mode==0 else 4,0.,color=8,dt=.12)
            for speed in (.001,.2,.3,.4):tick(4,speed,color=8,dt=.1)
        for _ in range(160):tick(4,.4 if stop else 5.,color=8,dt=.1)
        assert state.get('autopilot_active'),state.get('autopilot_intervention')
        assert not state.get('autopilot_intervention')
        assert state.get('autopilot_failure_epoch')==activation
        writer=getattr(ap,'_replay_export_writer',None)
        if writer:writer.wait(15.)
        writer=getattr(engine,'_automatic_replay_writer',None)
        if writer:writer.wait(15.)
        main=tmp_path/('incident-'+incident_id+'.json')
        assert main.exists(),list(tmp_path.iterdir())
        result=inspect_incident(main)
        assert result['integrity_valid'],result.get('reason')
        dossier=result['dossier']
        assert dossier.get('parts',{}).get('autopilot',{}).get('verified') is True, (
            'AP inputs must be exported and attached while AP stays active',dossier.get('parts'))
        assert dossier.get('assembly_complete') is True
        assert dossier['parts']['autopilot']['incident_id']==incident_id
        from core.steering_replay import inspect_replay
        ap_part=inspect_replay(tmp_path/dossier['parts']['autopilot']['name'])['replay']
        decisions=ap_part['diagnostic_consumed_inputs']['records']
        sources={v['source'] for row in decisions for v in row['value'].get('inputs',[])}
        assert {'consumer_acc','consumer_policy','consumer_traffic','consumer_control_locals'}<=sources
        assert dossier['parts']['autopilot']['missing_command_count']==0
        assert dossier['parts']['autopilot']['capacity_drops']==0
        detail=dossier['component_completeness']['backend_detail']
        assert detail['storage']=='full_incident_window'
        assert not detail['incomplete'],detail
        assert detail['missing_decision_references']==detail['missing_call_sequences']==0
        assert detail['detail_evidence']['duration_s']>=39.9
        assert not dossier['runtime_authorized'] and not dossier['confirmed']
        # Aggregate completeness never hides an intentionally bounded stream.
        if dossier.get('complete'):
            assert not dossier['incomplete']
        assert not any(ch=='parkingbrake' for _,ch,_,_ in writes)


def sealed_case():
    from core.navigation.longitudinal_diagnostics import PedalJournal
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    command=dict(context=[1,'session','map','dataset','intent',7,'build','geometry'],
        sdk_frame_us=42,observation_timestamp=100.,computed_at=100.02,throttle=0.,brake=.2)
    j.observe_incident('consumer_command_pair',dict(command=command,truck=dict(gear=4,speed=5.)),100.03)
    j.incident_event('BRAKE',dict(reason='red'),100.03)
    # A second source/event joins this exact case, rather than replacing it.
    j.incident_event('WAIT',dict(reason='same signal'),100.5)
    window=j.seal_incident(111.)
    request=dict(schema=2,incident_id=window['incident_id'],phase='seal',start_s=70.03,
        end_s=110.5,trigger_at_s=100.03,shutdown=False)
    request['token']=request['incident_id']+'@70.03..110.5'
    window['required_autopilot_part']=request
    part=dict(request=dict(request),records=[dict(stream_id='ap-stream',sequence=1,
        kind='ap_decision',at_s=100.02,value=dict(command=command,
        inputs=[dict(source='consumer_traffic',at_s=100.01,value=dict(packet=dict(
            sdk_frame_us=42,observation_timestamp=100.,light_brake=.2)))],capture_failures=0))],
        capacity_drops=0,capture_failures=0,shutdown_before_seal=False)
    return j,window,part


@pytest.mark.parametrize('fault',['missing','failed','newer','wrong-range','shutdown','capture-loss'])
def test_missing_or_wrong_exact_part_never_certifies_complete(tmp_path,fault):
    from core.steering_replay import export_incident,export_autopilot_part,inspect_incident
    j,window,part=sealed_case()
    if fault=='failed':
        (tmp_path/('ap-inputs-'+window['incident_id']+'.failed.json')).write_text('{}')
    elif fault!='missing':
        if fault=='newer':part['records'][0]['value']['command']=dict(part['records'][0]['value']['command'],sdk_frame_us=43)
        if fault=='wrong-range':part['request']['end_s']+=1
        if fault=='shutdown':part['shutdown_before_seal']=True
        if fault=='capture-loss':part['capture_failures']=1
        export_autopilot_part(tmp_path,part)
    checked=inspect_incident(export_incident(tmp_path,window,j.snapshot(include_history=True)))
    assert checked['integrity_valid'],checked
    assert checked['incomplete'] and not checked['complete']
    if fault in ('missing','failed','newer','wrong-range'):
        assert not checked['assembly_complete']
    assert checked['dossier']['first_reason']=='red'
    assert not checked['runtime_authorized'] and not checked['confirmed']


def test_delayed_part_is_verified_before_main_becomes_visible(tmp_path):
    import threading,time
    from core.steering_replay import export_incident,export_autopilot_part,inspect_incident,_await_autopilot_part
    j,window,part=sealed_case();arrived=threading.Event();errors=[]
    def assemble():
        try:
            result=_await_autopilot_part(tmp_path,window,wait_s=2.)
            arrived.set()
            export_incident(tmp_path,dict(window,autopilot_part_result=result),j.snapshot())
        except Exception as e:errors.append(e)
    thread=threading.Thread(target=assemble);thread.start()
    time.sleep(.1)
    assert not arrived.is_set() and not list(tmp_path.glob('incident-*.json'))
    export_autopilot_part(tmp_path,part)
    thread.join(5.)
    assert not thread.is_alive() and not errors
    checked=inspect_incident(next(tmp_path.glob('incident-*.json')))
    assert checked['integrity_valid'] and checked['assembly_complete']
    assert len(checked['dossier']['subevents'])==2
    assert len(list(tmp_path.glob('incident-*.json')))==1
    assert len(list(tmp_path.glob('ap-inputs-*.json')))==1


@pytest.mark.parametrize('damage',['missing','corrupt','false-complete'])
def test_attached_parts_and_completeness_are_rechecked(tmp_path,damage):
    import core.steering_replay as replay
    j,window,part=sealed_case()
    ap=Path(replay.export_autopilot_part(tmp_path,part))
    main=Path(replay.export_incident(tmp_path,window,j.snapshot()))
    if damage=='missing':ap.rename(ap.with_suffix('.preserved'))
    elif damage=='corrupt':ap.write_bytes(ap.read_bytes()+b'corrupt')
    else:
        value=json.loads(main.read_text());value['complete']=True;value['incomplete']=False
        # The warm-up is incomplete; a new envelope hash cannot bless that loss.
        value['integrity']['payload_sha256']=replay._payload_hash(value)
        main.write_text(json.dumps(value))
    assert not replay.inspect_incident(main)['integrity_valid']


def test_shutdown_during_open_case_exports_only_explicit_partial(tmp_path):
    from types import SimpleNamespace
    from core.navigation.longitudinal_diagnostics import AutopilotIncidentParts,_IncidentWindow
    from core.steering_replay import SteeringReplayBuffer,inspect_replay
    j,window,part=sealed_case()
    buffer=SteeringReplayBuffer(2);buffer._diagnostic_inputs=_IncidentWindow(32*1024*1024)
    plugin=SimpleNamespace(_steering_replay=buffer,_diagnostic_part_directory=str(tmp_path))
    assembler=AutopilotIncidentParts(plugin)
    assembler.begin()
    assembler.consume('consumer_traffic',dict(packet=dict(diagnostic_part_request=dict(
        part['request'],phase='open',end_s=None,token=None))),100.)
    assembler.close()
    status=plugin._replay_export_writer.wait(10.)
    assert status['path'] and not status['busy'],status
    checked=inspect_replay(status['path'])
    assert checked['integrity_valid']
    assert checked['replay']['diagnostic_consumed_inputs']['shutdown_before_seal']
    # A partial/open token cannot satisfy a later closed window request.
    from core.steering_replay import inspect_autopilot_part
    assert not inspect_autopilot_part(status['path'],part['request'],window)['verified']
