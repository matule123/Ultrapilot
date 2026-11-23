"""Windows spawn, real daemon host, production export and Manager transport."""
import multiprocessing as mp
from pathlib import Path
import pytest


def daemon_export(state,directory,result):
    import core.steering_replay as replay
    from core.ipc.shared_state import SharedState
    configure=getattr(replay,'configure_diagnostic_export',None)
    if configure:configure(SharedState(state))
    try:
        buffer=replay.SteeringReplayBuffer(2)
        buffer.append(dict(diagnostic_part_only=True,original_frame=42))
        path=replay.export_replay_isolated(buffer,directory,dict(reason='daemon_reproduction'))
        result.send(dict(path=path,daemon=mp.current_process().daemon))
    except Exception as error:result.send(dict(error=type(error).__name__,detail=str(error)))
    finally:result.close()


def test_spawned_daemon_exports_through_existing_manager(tmp_path, spawn_test_import_root):
    import core.ipc.shared_state as transport
    from core.steering_replay import inspect_replay
    context=mp.get_context('spawn')
    cls=getattr(transport,'DiagnosticStateManager',None) or transport.ControlStateManager
    with cls(ctx=context) as manager:
        state=manager.control_dict() if hasattr(manager,'control_dict') else manager.dict()
        receive,send=context.Pipe(duplex=False)
        process=context.Process(target=daemon_export,args=(state,str(tmp_path),send),daemon=True)
        process.start();send.close()
        try:
            assert receive.poll(30.),'bounded export did not complete'
            result=receive.recv();assert 'error' not in result,result
            assert result['daemon'] is True
            assert inspect_replay(result['path'])['integrity_valid']
        finally:
            process.join(3.)
            if process.is_alive():process.terminate();process.join(3.)
            receive.close();process.close()


def test_manager_admission_is_bounded_and_failed_part_releases_ticket(tmp_path):
    import core.ipc.shared_state as transport
    cls=getattr(transport,'DiagnosticStateManager',None) or transport.ControlStateManager
    with cls(ctx=mp.get_context('spawn')) as manager:
        state=manager.dict() if hasattr(transport,'DiagnosticStateManager') else manager.control_dict()
        ticket=state.reserve_diagnostic_export()
        assert ticket and state.reserve_diagnostic_export() is None
        with pytest.raises(ValueError,match='DIAGNOSTIC_EXPORT_KIND'):
            state.diagnostic_export(ticket,'unapproved_callable',())
        next_ticket=state.reserve_diagnostic_export()
        assert next_ticket and next_ticket!=ticket
        with pytest.raises(RuntimeError):
            state.diagnostic_export(next_ticket,'_autopilot_part_child',(str(tmp_path),{}))
        final=state.reserve_diagnostic_export();assert final
        state.release_diagnostic_export(final)


def daemon_lifecycle(state,directory,result,mode,manual=False,long_wait=False):
    """Real AP/Engine/Controller fixture hosted by the actual daemon shape."""
    from contextlib import contextmanager
    from unittest.mock import patch
    import time
    import core.steering_replay as replay
    from core.ipc.shared_state import SharedState
    from tests.test_activation_observation_binding import flow
    from tests.signals.test_signal_lifecycle import lifecycle
    import tests.signals.test_signal_lifecycle as scene
    from types import SimpleNamespace
    replay.configure_diagnostic_export(SharedState(state))
    try:
        with patch('core.sdk.traffic_snapshot.ExistingMapping',side_effect=OSError('isolated model')):
          with contextmanager(flow.__wrapped__)() as raw:
            shared,truck,engine,ap,tick,n,clock,writes,collected=lifecycle(raw,mode)
            engine._traffic_brake_basis=None  # No modeled actor conflict.
            def publish_traffic(state,truck,source,**values):
                assert source=='traffic'
                capture=SimpleNamespace(session='test-session',observed_at=clock[0],
                    moving=b'',parked=b'',stable=True,source={})
                from core.longitudinal import context
                return engine._publish_traffic_control(truck,truck['_control_observation']['observed_at'],
                    context(state),[],capture,dict(status='no_candidate_unproven_coverage'),0.,values['signal'],None)
            # The generic lifecycle fixture normally bypasses Engine traffic
            # publication. Use the real publisher/diagnostic join contract.
            scene.publish=publish_traffic
            engine._automatic_replay_directory=directory;ap._diagnostic_part_directory=directory
            for _ in range(310):
                tick(4,5.,color=8,dt=.1);writes.clear();collected.samples.clear();time.sleep(.005)
            engine._automatic_replay_directory=directory
            tick(4,.2,color=2,dt=.1)
            for _ in range(450 if long_wait else 12):
                tick(0 if mode==0 else 4,0.,color=2,dt=.1);writes.clear();collected.samples.clear();time.sleep(.1 if long_wait else .02)
            if manual:n()
            else:
                tick(0 if mode==0 else 4,0.,color=8,dt=.1)
                tick(0 if mode==0 else 4,0.,color=8,dt=.12)
                for speed in (.001,.2,.3,.4):tick(4,speed,color=8,dt=.1)
            # Give the OS export process time to run: an unpaced 16 model
            # seconds in a few ms is not a live producer cadence.
            for _ in range(160):
                tick(4,0. if manual else .4,color=8,dt=.1);writes.clear();collected.samples.clear();time.sleep(.02)
            deadline=time.perf_counter()+65.  # Existing 60 s exporter deadline plus result handoff.
            complete=[];inspected=set();verified_results={}
            while time.perf_counter()<deadline:
                for path in Path(directory).glob('incident-*.json'):
                    if path in inspected:continue
                    # A continuation explicitly declares complete=False.
                    # Expanding it for seconds on this SAME modeled control
                    # thread delays its next ticks/export handshake. Admit a
                    # possible complete result using metadata only, then run
                    # the unchanged FULL integrity/coverage inspector before
                    # accepting it. Every remaining part is inspected below.
                    import json
                    if json.loads(path.read_bytes()).get('complete') is not True:
                        inspected.add(path);continue
                    checked=replay.inspect_incident(path)
                    verified_results[path]=checked
                    inspected.add(path)  # Atomic immutable manifests cannot change.
                    if checked.get('complete') and not checked.get('incomplete'):complete.append(str(path))
                if complete:break
                tick(4,0. if manual else .4,color=8,dt=.02);writes.clear();collected.samples.clear();time.sleep(.02)
            # One full integrity expansion per immutable manifest for this
            # result. Repeating it three times per file adds tens of seconds
            # of test-only CPU after the actual live export has completed.
            dossiers=[]
            for path in Path(directory).glob('incident-*.json'):
                checked=verified_results.get(path)
                if checked is None:checked=replay.inspect_incident(path)
                dossiers.append({k:v for k,v in checked.items() if k not in ('replay','dossier')}
                    | {'name':path.name,'parts':checked.get('dossier',{}).get('parts')})
            result.send(dict(complete=complete,active=shared.get('autopilot_active'),
                fault=shared.get('autopilot_intervention'),daemon=mp.current_process().daemon,
                engine_writer=getattr(getattr(engine,'_automatic_replay_writer',None),'status',None),
                ap_writer=getattr(getattr(ap,'_replay_export_writer',None),'status',None),
                ap_assembly=dict(case=(ap._diagnostic_part_assembler.case or {}).get('request'),
                    next_case=(ap._diagnostic_part_assembler.next_case or {}).get('request'),
                    retired=ap._diagnostic_part_assembler.retired_ring is not None,
                    background_completed=getattr(ap._diagnostic_part_assembler,'background_completed_id',None),
                    completed=ap._diagnostic_part_assembler.completed_id,
                    rendezvous=ap._diagnostic_part_assembler.rendezvous_submitted),
                dossiers=dossiers))
    except Exception as error:result.send(dict(error=type(error).__name__,detail=str(error)))
    finally:result.close()


@pytest.mark.parametrize('mode',[0,3])
def test_live_red_wait_green_in_daemon_host(tmp_path,mode):
    import core.ipc.shared_state as transport
    try:
        from core.navigation.diagnostic_build_config import ENABLED
    except ImportError:ENABLED=False
    if not ENABLED:pytest.skip('Requires exact installed-base diagnostic candidate')
    cls=getattr(transport,'DiagnosticStateManager',None) or transport.ControlStateManager
    context=mp.get_context('spawn')
    with cls(ctx=context) as manager:
        state=manager.dict() if hasattr(transport,'DiagnosticStateManager') else manager.control_dict()
        receive,send=context.Pipe(duplex=False)
        process=context.Process(target=daemon_lifecycle,args=(state,str(tmp_path),send,mode),daemon=True)
        process.start();send.close()
        try:
            assert receive.poll(100.),'daemon-host lifecycle timed out'
            result=receive.recv()
            import json
            (tmp_path/'daemon-result.json').write_text(json.dumps(result,indent=2))
            assert not result.get('error'),result
            assert result['active'] and not result['fault'] and result['complete'],result
        finally:
            process.join(3.)
            if process.is_alive():process.terminate();process.join(3.)
            receive.close();process.close()


@pytest.mark.parametrize('manual,long_wait',[(True,False),(False,True)],ids=['manual-off','long-wait'])
@pytest.mark.parametrize('mode',[0,3])
def test_daemon_episode_finishes_without_application_shutdown(tmp_path,manual,long_wait,mode):
    import core.ipc.shared_state as transport
    if not hasattr(transport,'DiagnosticStateManager'):pytest.skip('Requires frozen installed-base candidate')
    context=mp.get_context('spawn')
    with transport.DiagnosticStateManager(ctx=context) as manager:
        state=manager.dict();receive,send=context.Pipe(duplex=False)
        process=context.Process(target=daemon_lifecycle,args=(state,str(tmp_path),send,mode,manual,long_wait),daemon=True)
        process.start();send.close()
        try:
            # Long-wait model now spends 45 REAL seconds stopped, in addition
            # to the unchanged 65 s result window and Windows spawn/readback.
            # This bounds the test host only, not any runtime safety deadline.
            assert receive.poll(170. if long_wait else 110.),'daemon episode timed out'
            result=receive.recv()
            import json
            (tmp_path/'daemon-result.json').write_text(json.dumps(result,indent=2))
            assert not result.get('error') and result['complete'],result
            assert result['active'] is (not manual) and not result['fault'],result
        finally:
            process.join(3.)
            if process.is_alive():process.terminate();process.join(3.)
            receive.close();process.close()
