"""Supplemental worker/shutdown checks against the same frozen runtime."""
from pathlib import Path
from types import SimpleNamespace

from tests.diagnostics.test_incident_assembly import sealed_case


def test_actual_ap_worker_failure_is_not_a_complete_incident(tmp_path,monkeypatch):
    import core.steering_replay as replay
    j,window,part=sealed_case()
    sent=[]
    connection=SimpleNamespace(send=sent.append,close=lambda:None)
    with monkeypatch.context() as patch:
        def disk_failure(*args,**kwargs):raise OSError('MODELED_AP_EXPORT_DISK_FAILURE')
        patch.setattr(replay,'_archive_incidents',disk_failure)
        # Actual export child operation, including its bounded failure record.
        replay._autopilot_part_child(str(tmp_path),part,connection)
    assert sent[0]['error']=='OSError'
    assert 'MODELED_AP_EXPORT_DISK_FAILURE' in sent[0]['detail']
    assert list(tmp_path.glob('ap-inputs-*.failed.json'))
    main=replay.export_incident(tmp_path,window,j.snapshot())
    checked=replay.inspect_incident(main)
    assert checked['integrity_valid'] and checked['incomplete']
    assert not checked['assembly_complete'] and not checked['complete']
    assert checked['dossier']['parts']['autopilot']['reason']=='AP_PART_EXPORT_FAILED'
    assert checked['dossier']['first_reason']=='red'


def test_engine_shutdown_rejects_ap_part_closed_before_seal_request(tmp_path,monkeypatch):
    import core.navigation.longitudinal_diagnostics as diagnostics
    from core.steering_replay import SteeringReplayBuffer,inspect_incident
    from tests.test_phase7_joint_validation import State
    j,_,part=sealed_case()
    command=part['records'][0]['value']['command']
    j.observe_incident('consumer_command_pair',dict(command=command),102.)
    j.incident_event('WAIT',dict(reason='preserved first shutdown cause'),102.)
    incident_id=j._incident_window.pending['incident_id']
    replay=SteeringReplayBuffer(2);replay._diagnostic_inputs=diagnostics._IncidentWindow(32*1024*1024)
    plugin=SimpleNamespace(_steering_replay=replay,_diagnostic_part_directory=str(tmp_path))
    assembler=diagnostics.AutopilotIncidentParts(plugin)
    assembler.begin()
    assembler.consume('consumer_traffic',dict(packet=dict(diagnostic_part_request=dict(
        schema=2,incident_id=incident_id,phase='open',start_s=72.,end_s=None,token=None))),102.)
    # AP has stopped before it can consume Engine's final seal request.
    assembler.close()
    engine=SimpleNamespace(controller=SimpleNamespace(_pedal_journal=j),
        shared_state=State({}),_automatic_replay_directory=str(tmp_path))
    monkeypatch.setattr(diagnostics.time,'monotonic',lambda:103.)
    assert diagnostics.finish_engine_incident(engine,j,shutdown=True)
    status=engine._automatic_replay_writer.wait(15.)
    assert status['path'] and not status['busy'],status
    checked=inspect_incident(Path(status['path']))
    assert checked['integrity_valid'] and checked['incomplete']
    assert not checked['complete'] and not checked['assembly_complete']
    assert checked['dossier']['first_reason']=='preserved first shutdown cause'
    assert checked['dossier']['parts']['autopilot']['reason']=='AP_PART_REQUEST_OR_RANGE_MISMATCH'
