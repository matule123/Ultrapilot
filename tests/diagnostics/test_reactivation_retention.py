"""Busy export cannot silently age away the middle of a reactivation case."""
from types import SimpleNamespace
import pytest


def export_owner(state,directory,send,daemon):
    """Engine and AP shapes must both use the existing Manager admission."""
    import multiprocessing as mp
    import core.steering_replay as r
    from core.ipc.shared_state import SharedState
    try:
        r.configure_diagnostic_export(SharedState(state))
        def forbidden_local_child(*args,**kwargs):
            raise AssertionError('Engine bypassed shared Manager admission')
        r._run_admitted_diagnostic_export=forbidden_local_child
        buffer=r.SteeringReplayBuffer(2)
        buffer.append(dict(diagnostic_part_only=True,original_frame=42))
        path=r.export_replay_isolated(buffer,directory,dict(reason='daemon' if daemon else 'engine'))
        send.send(dict(path=path,daemon=mp.current_process().daemon,
            valid=r.inspect_replay(path)['integrity_valid']))
    except Exception as error:send.send(dict(error=type(error).__name__,detail=str(error)))
    finally:send.close()


def test_non_daemon_engine_and_daemon_ap_use_same_manager_admission(tmp_path,spawn_test_import_root):
    import multiprocessing as mp
    import core.ipc.shared_state as ipc
    context=mp.get_context('spawn')
    manager_class=getattr(ipc,'DiagnosticStateManager',None) or ipc.ControlStateManager
    with manager_class(ctx=context) as manager:
        state=manager.dict() if hasattr(ipc,'DiagnosticStateManager') else manager.control_dict()
        owners=[]
        try:
            for daemon in (False,True):
                receive,send=context.Pipe(duplex=False)
                process=context.Process(target=export_owner,args=(state,str(tmp_path),send,daemon),daemon=daemon)
                process.start();send.close();owners.append((process,receive))
            for process,receive in owners:
                assert receive.poll(30.),'shared export admission did not finish'
                result=receive.recv()
                assert not result.get('error'),result
                assert result['valid'] and result['daemon']==process.daemon
        finally:
            for process,receive in owners:
                process.join(3.)
                if process.is_alive():process.terminate();process.join(3.)
                receive.close();process.close()


def test_pending_episode_keeps_exact_middle_while_existing_writer_busy(monkeypatch,tmp_path):
    import core.navigation.longitudinal_diagnostics as d
    j=d.PedalJournal();j.enabled=True;j.enable_incident_window();ring=j._incident_window
    engine=SimpleNamespace(controller=SimpleNamespace(_pedal_journal=j),
        _automatic_replay_directory=str(tmp_path),_automatic_replay_writer=SimpleNamespace(status={'busy':True}))
    for i in range(1101):
        at=70.+i*.1
        ring.observe('traffic',{'generation':i,'raw':bytes([i%256])*32},at,force=True)
        ring.observe('ego',{'frame':i,'speed':5. if i<700 else 0.},at,force=True)
        if i==300:j.incident_event('BRAKING_STARTED',{'reason':'first brake'},at)
        if i==350:j.incident_event('AUTOPILOT_DISABLED',{'reason':'manual'},at)
        if i==370:j.incident_event('ACTIVATION_REQUESTED',{'reason':'new N'},at)
        if i==600:j.incident_event('TECHNICAL_STOP',{'reason':'modeled actual intervention'},at)
        monkeypatch.setattr(d.time,'monotonic',lambda at=at:at)
        d.finish_engine_incident(engine,j)
    window=j.seal_incident(180.,shutdown=True)
    times=[r['at_s'] for r in window['records'] if r['kind']=='traffic']
    assert len(times)==1101
    assert max(b-a for a,b in zip(times,times[1:]))<.101
    for i,row in enumerate(r for r in window['records'] if r['kind']=='traffic'):
        assert row['value']=={'generation':i,'raw':bytes([i%256])*32}
        assert row['at_s']==70.+i*.1
    assert not window['capacity_drops'] and not window['capture_failures']
    assert ring.retained_cost([(r,1024) for r in window['records']])<2*ring.limit


def test_admitted_export_child_never_waits_for_prerequisite(monkeypatch,tmp_path):
    import core.steering_replay as r
    from tests.diagnostics.test_late_assembly import full_case
    j,window,_=full_case();sent=[];seen=[]
    original=r._await_autopilot_part
    def no_reserved_wait(directory,window,wait_s=20.):
        seen.append(wait_s)
        assert wait_s==0.,'AP prerequisite waits while the sole child/admission slot is held'
        return original(directory,window,wait_s=0.)
    monkeypatch.setattr(r,'_await_autopilot_part',no_reserved_wait)
    r._incident_export_child(str(tmp_path),window,j.snapshot(),SimpleNamespace(send=sent.append,close=lambda:None))
    assert not sent[0].get('error'),sent
    assert seen and all(n==0. for n in seen)
    assert not r.inspect_incident(sent[0]['path'])['complete']


def test_independent_completeness_rejects_declared_complete_internal_hole(tmp_path):
    import json
    import core.steering_replay as r
    from tests.diagnostics.test_late_assembly import full_case
    j,window,part=full_case()
    window['records']=[row for row in window['records'] if row['kind']!='ego' or not 80.<row['at_s']<90.]
    # Model the old producer incorrectly declaring its endpoints sufficient.
    window['incomplete']=False
    r.export_autopilot_part(tmp_path,part)
    with pytest.raises(ValueError,match='READBACK|GAP'):
        r.export_incident(tmp_path,window,j.snapshot())


def test_busy_episode_pin_stays_bounded_and_marks_real_overload():
    import core.navigation.longitudinal_diagnostics as d
    import random
    ring=d._IncidentWindow(64*1024,deferred=True)
    ring.observe('ego',dict(frame=0),70.,force=True)
    ring.event('BRAKE',dict(reason='modeled stop'),100.)
    random_bytes=random.Random(17)
    for i in range(90):
        ring.observe('traffic',dict(frame=i,raw=random_bytes.randbytes(4096)),100.+i*.1,force=True)
        assert ring._pin_bytes<=ring.limit and ring.bytes<=ring.limit
    saved=ring.seal(120.,shutdown=True)
    assert saved['incomplete'] and saved['capacity_drops']>0


def test_pending_pin_does_not_prepare_allocating_input_sets_under_ring_lock(monkeypatch):
    import core.navigation.longitudinal_diagnostics as d
    ring=d._IncidentWindow(1024*1024,deferred=True,simple_records=True)
    ring.event('BRAKE',dict(reason='modeled stop'),100.)
    original=ring.row_inputs
    def prepare(row):
        assert ring.lock.acquire(False),'input-set preparation can trigger GC while the shared ring lock is held'
        ring.lock.release()
        return original(row)
    monkeypatch.setattr(ring,'row_inputs',prepare)
    ring.observe('traffic',dict(frame=42,raw=b'original'),100.1,force=True)
    saved=ring.seal(111.)
    assert saved['records'][0]['value']==dict(frame=42,raw=b'original')


def test_simple_prefix_pin_does_not_scan_nonexistent_shared_envelopes_under_lock(monkeypatch):
    import core.navigation.longitudinal_diagnostics as d
    ring=d._IncidentWindow(1024*1024,deferred=True,simple_records=True)
    for i in range(301):ring.observe('ego',dict(frame=i),70.+i*.1,force=True)
    original=ring.row_inputs
    def inspect(row):
        assert ring.lock.acquire(False),'simple prefix creates an empty shared-input set for every retained row under lock'
        ring.lock.release();return original(row)
    monkeypatch.setattr(ring,'row_inputs',inspect)
    ring.event('BRAKE',dict(reason='original'),100.)
    assert ring._pin_bytes==sum(e[1] for e in ring.pending['before'])
    assert not ring._pin_shared and len(ring.pending['before'])==301


def reactivation_host(service,directory,send,mode):
    """Modeled SDK, real controls/daemon/Manager/disk; no live mapping."""
    from contextlib import contextmanager
    from unittest.mock import patch
    import threading,time
    from pathlib import Path
    import core.steering_replay as replay
    from core.ipc.shared_state import SharedState
    from core.longitudinal import context
    from tests.test_activation_observation_binding import flow
    from tests.signals.test_signal_lifecycle import lifecycle
    import tests.signals.test_signal_lifecycle as scene
    gate=threading.Event();waiting=threading.Event()
    replay.configure_diagnostic_export(SharedState(service))
    original=replay._run_diagnostic_export
    def delayed(target,args):
        if not gate.is_set():
            waiting.set()
            assert gate.wait(15.),'test-controlled background export stalled'
        return original(target,args)
    replay._run_diagnostic_export=delayed
    try:
      with patch('core.sdk.traffic_snapshot.ExistingMapping',side_effect=OSError('model')):
       with contextmanager(flow.__wrapped__)() as raw:
        state,truck,engine,ap,tick,n,clock,writes,collected=lifecycle(raw,mode,start=False)
        engine._traffic_brake_basis=None
        def production_traffic(state,truck,source,**values):
            capture=SimpleNamespace(session='test-session',observed_at=clock[0],
                moving=b'',parked=b'',stable=True,source={})
            return engine._publish_traffic_control(truck,truck['_control_observation']['observed_at'],
                context(state),[],capture,dict(status='no_candidate_unproven_coverage'),0.,values['signal'],None)
        scene.publish=production_traffic
        engine._automatic_replay_directory=directory;ap._diagnostic_part_directory=directory
        for _ in range(355):
            tick(4,5.,dt=.1);writes.clear();collected.samples.clear()
        n()
        for _ in range(15):tick(4,5.,dt=.1)
        assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
        old_token=context(state)[0]
        manual_at=clock[0];n();tick(4,5.,dt=.1)
        assert not state.get('autopilot_active')
        n()
        for _ in range(15):tick(4,5.,dt=.1)
        assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
        assert context(state)[0]!=old_token
        # A genuinely invalid reverse observation supplies an automatic fault;
        # this is NOT a reconstruction of actor 85's missing pose.
        fault_at=clock[0];tick(-1,0.,dt=.1)
        assert state.get('autopilot_intervention')
        for _ in range(500):
            tick(4,0.,dt=.1);writes.clear();collected.samples.clear()
        assert waiting.wait(3.),'the export overlap was not exercised'
        gate.set()
        complete=[];deadline=time.perf_counter()+75.;inspected=set()
        while time.perf_counter()<deadline:
            for path in Path(directory).glob('incident-*.json'):
                if path in inspected:continue
                checked=replay.inspect_incident(path)
                inspected.add(path)
                if checked.get('complete') and not checked.get('incomplete'):
                    window=checked['replay']['longitudinal']['diagnostic_incident']
                    events=checked['dossier'].get('subevents')or[]
                    if any(e['at_s']>=fault_at for e in events):
                        complete.append((str(path),window,checked))
            if complete:break
            tick(4,0.,dt=.02);writes.clear();collected.samples.clear();time.sleep(.02)
        cases=[]
        for path,window,checked in complete:
            streams={}
            for row in window['records']:streams.setdefault(row['kind'],[]).append(row)
            gaps={kind:max([b['at_s']-a['at_s'] for a,b in zip(rows,rows[1:])],default=0.)
                for kind,rows in streams.items() if kind in ('ego','traffic','output_summary')}
            cases.append(dict(path=path,range=window['range_s'],gaps=gaps,
                backend=checked['dossier']['component_completeness']['backend_detail'],
                missing=checked['dossier']['component_completeness'].get('consumed_inputs')))
        send.send(dict(complete=cases,manual_at=manual_at,fault_at=fault_at,
            active=state.get('autopilot_active'),fault=state.get('autopilot_intervention'),
            engine_writer=getattr(getattr(engine,'_automatic_replay_writer',None),'status',None),
            ap_writer=getattr(getattr(ap,'_replay_export_writer',None),'status',None),
            assembler=dict(case=(ap._diagnostic_part_assembler.case or {}).get('request'),
                next=(ap._diagnostic_part_assembler.next_case or {}).get('request'),
                completed=ap._diagnostic_part_assembler.completed_id,
                retired=ap._diagnostic_part_assembler.retired_ring is not None,
                retry=ap._diagnostic_part_assembler.retry_at)))
    except Exception as error:
        import traceback
        send.send(dict(error=type(error).__name__,detail=str(error),traceback=traceback.format_exc()))
    finally:gate.set();send.close()


@pytest.mark.parametrize('mode',[0,3])
def test_actual_spawn_reactivation_and_fault_while_export_pending(tmp_path,mode,spawn_test_import_root):
    import multiprocessing as mp,json
    import core.ipc.shared_state as ipc
    context=mp.get_context('spawn')
    cls=getattr(ipc,'DiagnosticStateManager',None) or ipc.ControlStateManager
    with cls(ctx=context) as manager:
        service=manager.dict() if hasattr(ipc,'DiagnosticStateManager') else manager.control_dict()
        receive,send=context.Pipe(duplex=False)
        process=context.Process(target=reactivation_host,args=(service,str(tmp_path),send,mode),daemon=True)
        process.start();send.close()
        try:
            assert receive.poll(100.),'reactivation/export model did not finish'
            result=receive.recv();(tmp_path/'reactivation-result.json').write_text(json.dumps(result,indent=2))
            assert not result.get('error'),result
            assert result['complete'],result
            assert not result['active'] and result['fault']
            for case in result['complete']:
                assert all(gap<=.25 for gap in case['gaps'].values()),case
                assert not case['backend']['incomplete'],case
        finally:
            process.join(3.)
            if process.is_alive():process.terminate();process.join(3.)
            receive.close();process.close()
