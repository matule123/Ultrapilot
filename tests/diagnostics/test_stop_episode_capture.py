"""Stop episodes are observational, irrespective of controller reason labels."""
import gc
import pytest


def journal():
    from core.navigation.longitudinal_diagnostics import PedalJournal
    gc.collect();j=PedalJournal();j.enabled=True;j.enable_incident_window()
    return j


def test_unknown_stop_and_disable_are_edges_not_repeated_tick_events():
    j=journal()
    j.observe_stop_episode(dict(active=True,speed_mps=5.,brake=0.,reason=None),100.)
    assert j._incident_window.pending is None
    j.observe_stop_episode(dict(active=True,speed_mps=0.,brake=0.,reason=None),101.)
    for t in (102.,103.,104.):j.observe_stop_episode(dict(active=True,speed_mps=0.,brake=0.),t)
    p=j._incident_window.pending
    assert [e['kind'] for e in p['subevents']].count('STOP_OBSERVED')==1
    j.observe_stop_episode(dict(active=False,speed_mps=0.,reason='manual N'),105.)
    assert p['tail_until_s']>=115.
    assert p['subevents'][-1]['kind']=='AUTOPILOT_DISABLED'


def test_braking_pins_before_wait_and_long_wait_splits_with_same_episode():
    j=journal();ring=j._incident_window
    for i in range(301):ring.observe('ego',{'frame':i},70+i*.1,force=True)
    j.observe_stop_episode(dict(active=True,speed_mps=10.,brake=.2,reason='red',source='signal'),100.)
    j.observe_stop_episode(dict(active=True,speed_mps=0.,brake=.2,reason='red'),102.)
    for i in range(201):
        ring.observe('ego',{'frame':301+i},100+i*.1,force=True)
        j.observe_stop_episode(dict(active=True,speed_mps=0.,brake=.2,reason='red'),100+i*.1)
    first=j.seal_incident(120.,packed=False)
    assert first and first['episode']['continues']
    assert first['range_s']['pre_s']>=29.9
    assert ring.pending and ring.pending['episode']['id']==first['episode']['id']
    assert ring.pending['episode']['part']==first['episode']['part']+1
    assert ring.pending['episode']['previous_incident_id']==first['incident_id']
    j.observe_stop_episode(dict(active=True,speed_mps=.4,brake=0.,reason='green'),125.)
    assert ring.pending['tail_until_s']>=135.
    assert j.seal_incident(134.) is None
    for i in range(151):ring.observe('ego',{'frame':502+i},120+i*.1,force=True)
    last=j.seal_incident(135.)
    assert last and not last['episode']['continues']
    assert last['episode']['id']==first['episode']['id']
    j.observe_stop_episode(dict(active=True,speed_mps=0.,brake=.2),140.)
    assert ring.pending['episode']['id']!=last['episode']['id']


def test_left_boundary_keeps_the_actual_inputs_referenced_by_pedal_binding():
    from unittest.mock import patch
    j=journal();ring=j._incident_window
    ring.observe('ego',dict(frame=1),100.,force=True)
    j.incident_event('BRAKE',dict(reason='original'),100.)
    j.begin_decision()
    reference=j.observe_incident('consumer_traffic',dict(packet=dict(frame=42)),150.099)
    with patch('time.monotonic',return_value=150.102):
        j.bind(dict(phase='active',actual_speed_mps=2.,inputs={},sdk_frame_us=42))
        j.record('brake',.2,150.105,150.11,'SCS_SDK',dict(status='MAPPING_WRITE_RETURNED',value=.2))
    ring.observe('ego',dict(frame=99),190.302,force=True)
    saved=j.seal_incident(190.302,shutdown=True)
    rows={(r['stream_id'],r['sequence']):r for r in saved['records']}
    assert tuple(reference) in rows
    assert rows[tuple(reference)]['value']['packet']['frame']==42
    for row in saved['records']:
        if row['kind']=='pedal_binding':
            assert all(tuple(ref) in rows for ref in row['value']['consumed_input_references'].values() if ref)


def test_damaged_earlier_continuation_cannot_hide_behind_valid_last_manifest(tmp_path):
    import json,hashlib
    from core.steering_replay import export_incident,inspect_incident,_payload_hash
    j=journal();j.observe_incident('ego',dict(frame=42),100.)
    j.incident_event('BRAKE',dict(reason='modeled red'),100.)
    original=export_incident(tmp_path,j.seal_incident(110.),j.snapshot())
    base=json.loads(__import__('pathlib').Path(original).read_text())
    previous=None;paths=[]
    for part in range(3):
        value=dict(base,incident_id='a'*32+'-'+str(part),complete=False,incomplete=True,
            assembly_complete=False,episode_complete=False,part_complete=False,
            episode=dict(id='modeled-episode',part=part,continues=part<2,
                previous_incident_id=None if part==0 else 'a'*32+'-'+str(part-1)),
            previous_part=previous)
        value['integrity']=dict(algorithm='sha256',payload_sha256=_payload_hash(value))
        path=tmp_path/('incident-chain-'+str(part)+'.json')
        path.write_text(json.dumps(value))
        previous=dict(name=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        paths.append(path)
    assert inspect_incident(paths[-1])['integrity_valid']
    paths[0].write_bytes(b'corrupted model manifest')
    checked=inspect_incident(paths[-1])
    assert not checked['integrity_valid'] and not checked['complete']


def test_next_ap_case_pins_original_history_while_previous_part_is_busy():
    from types import SimpleNamespace
    from core.steering_replay import SteeringReplayBuffer
    from core.navigation.longitudinal_diagnostics import AutopilotIncidentParts,_IncidentWindow
    replay=SteeringReplayBuffer(2)
    replay._diagnostic_inputs=ring=_IncidentWindow(32*1024*1024,deferred=True)
    ring.observe('ap_decision',dict(original_frame=42),100.,force=True)
    assembler=AutopilotIncidentParts(SimpleNamespace(_steering_replay=replay))
    def request(number):return dict(schema=2,incident_id='a'*32+'-'+str(number),phase='open',start_s=70.)
    assembler.accept(request(1));assembler.accept(request(2))
    pinned=assembler.next_case
    ring.observe('ap_decision',dict(original_frame=99),200.,force=True)
    assert ring.rolling_snapshot()['records'][0]['value']['original_frame']==99
    assert _IncidentWindow.expanded_row(pinned['before'][0])['value']['original_frame']==42
    assembler.accept(dict(request(2),phase='seal',end_s=210.))
    assert assembler.next_case is pinned and pinned['request']['phase']=='seal'
    failures=ring.failures
    assembler.accept(request(3))
    assert assembler.next_case is pinned and ring.failures==failures+1


def test_disabled_ap_seal_uses_rotated_exact_inputs_even_without_prior_open(monkeypatch,tmp_path):
    import threading
    from types import SimpleNamespace
    import core.steering_replay as exports
    from core.navigation.longitudinal_diagnostics import AutopilotIncidentParts,_IncidentWindow
    old=exports.SteeringReplayBuffer(2)
    old._diagnostic_inputs=_IncidentWindow(32*1024*1024,deferred=True)
    command=dict(context={'activation':'original'},sdk_frame_us=42,
        observation_timestamp=100.,computed_at=100.01,throttle=0.,brake=.2)
    old._diagnostic_inputs.observe('ap_decision',dict(command=command,raw=b'\x00\xff'),101.,force=True)
    request=dict(schema=2,incident_id='b'*32+'-2',phase='seal',start_s=71.,end_s=112.,token='original-seal')
    reads=[]
    class State:
        def get(self,key):reads.append((threading.get_ident(),key));return request
    plugin=SimpleNamespace(_steering_replay=old,sdk=SimpleNamespace(shared_state=State()),
        _diagnostic_part_directory=str(tmp_path))
    assembler=AutopilotIncidentParts(plugin)
    current=exports.SteeringReplayBuffer(2)
    current._diagnostic_inputs=_IncidentWindow(32*1024*1024,deferred=True)
    current._diagnostic_inputs.observe('ap_decision',dict(command=None),112.,force=True)
    plugin._steering_replay=current
    captured=[];caller=threading.get_ident()
    def save(directory,snapshot):captured.append((directory,snapshot));return 'verified-part'
    monkeypatch.setattr(exports,'export_autopilot_part_isolated',save)
    worker=threading.Thread(target=lambda:assembler.after_disabled_replay(old,'unused-dense-directory'))
    worker.start();worker.join(2.)
    assert not worker.is_alive() and len(captured)==1
    assert all(t!=caller and key=='diagnostic_incident_seal_request' for t,key in reads)
    directory,snapshot=captured[0]
    assert directory==str(tmp_path) and snapshot['request']==request
    rows=[_IncidentWindow.expanded_row(r)['value'] for r in snapshot['records']]
    assert any(r.get('command')==command and r.get('raw')==b'\x00\xff' for r in rows)
    assert assembler.background_completed_id==request['incident_id']


def test_incomplete_first_part_cannot_be_blessed_by_two_complete_successors(tmp_path):
    """Model the assembly metadata, not three successful physical drives."""
    from tests.diagnostics.test_incident_assembly import sealed_case
    from core.steering_replay import export_autopilot_part,export_incident,inspect_incident
    previous=None;episode_id='c'*32+'-0'
    for index in range(3):
        j,window,part=sealed_case()
        ident='c'*32+'-'+str(index)
        request=dict(part['request'],incident_id=ident,token='modeled-'+str(index))
        window.update(incident_id=ident,required_autopilot_part=request,incomplete=index==0,
            episode=dict(id=episode_id,part=index,continues=index<2,previous_incident_id=previous))
        part['request']=request
        export_autopilot_part(tmp_path,part)
        checked=inspect_incident(export_incident(tmp_path,window,j.snapshot()))
        assert checked['integrity_valid']
        if index==2:
            assert checked['dossier']['part_complete'] is True
            assert not checked['complete'] and checked['incomplete']
        previous=ident
