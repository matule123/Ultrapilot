"""Late original AP attachments cannot replace or bless missing evidence."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from tests.diagnostics.test_incident_assembly import sealed_case


def full_case():
    # The old sealed_case intentionally has no prehistory and cannot pass a
    # complete verdict. Populate real ring rows rather than clearing its flag.
    from core.navigation.longitudinal_diagnostics import PedalJournal
    _,_,part=sealed_case();command=part['records'][0]['value']['command']
    j=PedalJournal();j.enabled=True;j.enable_incident_window()
    for i in range(406):
        at=70.03+i*.1
        j.observe_incident('ego',dict(frame=i),at)
        if i==300:
            j.observe_incident('consumer_command_pair',dict(command=command),at)
            j.incident_event('BRAKE',dict(reason='red'),at)
    window=j.seal_incident(110.6)
    request=dict(schema=2,incident_id=window['incident_id'],phase='seal',
        start_s=70.03,end_s=110.53,trigger_at_s=100.03,shutdown=False)
    request['token']=request['incident_id']+'@70.03..110.53'
    window['required_autopilot_part']=request;part['request']=dict(request)
    assert not window['incomplete']
    return j,window,part


@pytest.mark.parametrize('damage',['none','hash','request','capture_loss','absent'])
def test_late_part_reconciles_only_verified_original_without_overwrite(tmp_path,damage):
    import core.steering_replay as r
    j,window,part=full_case()
    original=Path(r.export_incident(tmp_path,window,j.snapshot()))
    raw=original.read_bytes()
    assert not r.inspect_incident(original)['assembly_complete']
    if damage!='absent':
        if damage=='request':part['request']['end_s']+=1
        if damage=='capture_loss':part['capture_failures']=1
        ap=Path(r.export_autopilot_part(tmp_path,part))
        if damage=='hash':ap.write_bytes(ap.read_bytes()+b'broken')
    path=r.complete_incident_assembly(tmp_path,window['incident_id'])
    assert original.read_bytes()==raw
    if damage in ('hash','request','absent'):
        assert path is None
    else:
        checked=r.inspect_incident(path)
        assert checked['integrity_valid'],checked
        assert checked['assembly_complete']
        assert checked['complete'] is (damage=='none')
        assert not checked['confirmed'] and not checked['runtime_authorized']
        assert r.complete_incident_assembly(tmp_path,window['incident_id'])==path
        # The immutable original remains part of the chain of evidence.
        original.write_bytes(raw+b'broken')
        assert not r.inspect_incident(path)['integrity_valid']


def test_actual_ap_export_child_completes_late_case(tmp_path):
    import core.steering_replay as r
    j,window,part=full_case()
    original=Path(r.export_incident(tmp_path,window,j.snapshot()))
    sent=[]
    r._autopilot_part_child(str(tmp_path),part,SimpleNamespace(send=sent.append,close=lambda:None))
    assert 'error' not in sent[0],sent
    assert sent[0].get('assembled_incident')
    assert r.inspect_incident(sent[0]['assembled_incident'])['complete']
    assert not r.inspect_incident(original)['assembly_complete']


def daemon_late_part(state,directory,part,connection):
    import core.steering_replay as r
    from core.ipc.shared_state import SharedState
    try:
        r.configure_diagnostic_export(SharedState(state))
        path=r.export_autopilot_part_isolated(directory,part)
        assembled=Path(directory)/('incident-'+part['request']['incident_id']+'-assembled.json')
        connection.send(dict(path=path,assembled=str(assembled),daemon=__import__('multiprocessing').current_process().daemon,
            verified=r.inspect_incident(assembled)['complete']))
    except Exception as e:connection.send(dict(error=type(e).__name__,detail=str(e)))
    finally:connection.close()


def test_windows_spawn_daemon_late_attachment_through_existing_manager(tmp_path, spawn_test_import_root):
    import multiprocessing as mp
    import core.ipc.shared_state as transport
    import core.steering_replay as r
    j,window,part=full_case()
    original=Path(r.export_incident(tmp_path,window,j.snapshot()));raw=original.read_bytes()
    cls=getattr(transport,'DiagnosticStateManager',None) or transport.ControlStateManager
    context=mp.get_context('spawn')
    with cls(ctx=context) as manager:
        state=manager.dict() if hasattr(transport,'DiagnosticStateManager') else manager.control_dict()
        receive,send=context.Pipe(duplex=False)
        child=context.Process(target=daemon_late_part,args=(state,str(tmp_path),part,send),daemon=True)
        child.start();send.close()
        try:
            assert receive.poll(30.)
            result=receive.recv()
            assert 'error' not in result,result
            assert result['daemon'] and result['verified']
            assert original.read_bytes()==raw
        finally:
            child.join(3.)
            if child.is_alive():child.terminate();child.join(3.)
            receive.close();child.close()


def test_late_attachment_and_original_archive_as_one_verified_group(tmp_path,monkeypatch):
    import core.steering_replay as r
    j,window,part=full_case()
    original=Path(r.export_incident(tmp_path,window,j.snapshot()))
    r.export_autopilot_part(tmp_path,part)
    resolved=Path(r.complete_incident_assembly(tmp_path,window['incident_id']))
    budget=r.incident_diagnostic_budget
    def force_one_archive(directory):
        value=budget(directory)
        if original.exists():value['active_bytes']=value['active_limit_bytes']
        return value
    monkeypatch.setattr(r,'incident_diagnostic_budget',force_one_archive)
    r._archive_incidents(tmp_path,reserve_bytes=1)
    folder=tmp_path/'archive'/original.stem
    assert r.inspect_incident(folder/original.name)['integrity_valid']
    assert r.inspect_incident(folder/resolved.name)['complete']
