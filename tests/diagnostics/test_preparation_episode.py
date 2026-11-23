"""Windows daemon + real Map/pedals + Manager exporter, modeled SDK only."""
import json
import multiprocessing as mp
from pathlib import Path
from types import SimpleNamespace
import pytest


def preparation_host(service, directory, connection, mode):
    from contextlib import contextmanager
    from unittest.mock import patch
    import time
    import threading
    import core.steering_replay as replay
    from core.ipc.shared_state import SharedState
    from core.longitudinal import context
    from tests.test_activation_observation_binding import flow
    from tests.test_rolling_longitudinal_authority import rolling
    from tests.test_longitudinal_arbitration import strict_flow
    from tools.qualify_oct25_traffic_capture import raw_capture
    gate=threading.Event();entered=threading.Event();gate.set()
    replay.configure_diagnostic_export(SharedState(service))
    export=replay._run_diagnostic_export
    def delay(target,args):
        if not gate.is_set():
            entered.set()
            assert gate.wait(25.),'bounded modeled overlap stalled'
        return export(target,args)
    replay._run_diagnostic_export=delay
    mapper=None
    try:
      with patch('core.sdk.traffic_snapshot.ExistingMapping',side_effect=OSError('offline model')):
       with contextmanager(flow.__wrapped__)() as raw:
        with patch('tests.test_rolling_longitudinal_authority.strict_flow',side_effect=lambda f:strict_flow(f,mode=mode)):
         with contextmanager(rolling.__wrapped__)(raw) as values:
          state,engine,ap,acc,policy,tick,observe,n,physical,writes,clock=values
          mapper=tick.publish_map.__self__
          engine._traffic_brake_basis=None
          engine._automatic_replay_directory=directory
          ap._diagnostic_part_directory=directory
          generation=0
          def drive_current_snapshot():
              nonlocal generation
              truck=state.get('telemetry')['truck'];generation+=1
              capture=raw_capture(40,3,clock[0],truck['sdkFrameTimeUs'],generation,str(context(state)[1]),truck['speed'])
              following,brake=engine._traffic_control_observation(capture,truck,context(state),[])
              assert following['status']!='route_unavailable_or_ambiguous',following
              engine._publish_traffic_control(truck,truck['_control_observation']['observed_at'],
                  context(state),[],capture,following,brake,dict(valid=False,candidate=None),None)
              policy.on_tick(.05);acc.on_tick(.05);ap.on_tick(.05);engine._flush_controls()
              writes.clear()
          def step(speed=4.,gear=4,delayed=False):
              # Fixture telemetry and actual Map first; retain all original
              # observations. 40+40 traffic records / three native trailers.
              tick(speed=speed,gear=gear,pedals=False)
              if delayed:
                  previous=state.get('nav_steering_debug')
                  value=state.get('vehicle_envelope_snapshot')
                  value.update(timestamp=clock[0]+.02,sdk_frame_us=value['sdk_frame_us']+16666)
                  clock[0]+=.02;state.set('vehicle_envelope_snapshot',value)
                  read=mapper.sdk.get
                  def map_read(key,default=None):
                      # An in-flight Map receiver still holds the preceding
                      # envelope; independent Engine/SDK publication continues.
                      return value if key=='vehicle_envelope_snapshot' else read(key,default)
                  def prepare(pos):
                      for _ in range(3):
                          clock[0]+=.05
                          source_truck=raw[1]
                          source_truck['sdkFrameTimeUs']+=50000
                          state.update_batch(engine._vehicle_telemetry_payload(
                              dict(truck=source_truck,raw=dict(sdkActive=True)),clock[0]))
                          drive_current_snapshot()
                  with patch.object(mapper,'_publish_road_type',side_effect=prepare),patch.object(mapper.sdk,'get',side_effect=map_read):
                      mapper.on_tick(.02)
                  assert state.get('nav_steering_debug')==previous
                  assert state.get('nav_active')
              drive_current_snapshot()
          # This fixture's true period is 33.333 ms, not 100 ms: 1,000 ticks
          # establish >30 s of real model history. Let its unavoidable cold
          # startup dossier finish before the explicitly tested overlap.
          for _ in range(1000):step()
          settle=time.perf_counter()+45.
          while time.perf_counter()<settle:
              ew=getattr(engine,'_automatic_replay_writer',None)
              aw=getattr(ap,'_replay_export_writer',None)
              if (not (ew and ew.status.get('busy')) and not (aw and aw.status.get('busy'))
                      and ap._diagnostic_part_assembler.completed_id):break
              step();time.sleep(.01)
          gate.clear();entered.clear()
          assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
          manual=clock[0];n();step()
          n()
          for _ in range(10):step()
          assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
          step(delayed=True)
          for _ in range(12):step()
          assert state.get('autopilot_active'),state.get('autopilot_disable_reason')
          # R remains a genuine safety fault without introducing a synthetic
          # half-second observation gap into the completeness test. True SDK
          # expiry is covered by the separate end-to-end negative cases.
          step(speed=0.,gear=-1);fault=clock[0]
          assert state.get('autopilot_intervention')
          assert physical('aforward')==0.
          for _ in range(500):step(speed=0.)
          assert entered.wait(3.)
          gate.set()
          completed=[];deadline=time.perf_counter()+80.;inspected=set()
          while time.perf_counter()<deadline:
              for path in Path(directory).glob('incident-*.json'):
                  if path in inspected:continue
                  checked=replay.inspect_incident(path);inspected.add(path)
                  if checked.get('complete'):
                      events=checked['dossier'].get('subevents',[])
                      if any(e['at_s']>=fault for e in events):
                          window=checked['replay']['longitudinal']['diagnostic_incident']
                          completed.append(dict(name=path.name,range=window['range_s'],
                              backend=checked['dossier']['component_completeness']['backend_detail']))
              if completed:break
              step(speed=0.);time.sleep(.02)
          connection.send(dict(complete=completed,manual_at=manual,fault_at=fault,
              daemon=mp.current_process().daemon,mode=mode,
              engine_writer=getattr(getattr(engine,'_automatic_replay_writer',None),'status',None),
              ap_writer=getattr(getattr(ap,'_replay_export_writer',None),'status',None),
              dossiers=[dict(name=p.name,**{k:v for k,v in replay.inspect_incident(p).items()
                  if k not in ('replay','dossier')}) for p in Path(directory).glob('incident-*.json')]))
    except Exception as error:
        import traceback
        connection.send(dict(error=type(error).__name__,detail=str(error),traceback=traceback.format_exc()))
    finally:gate.set();connection.close()


@pytest.mark.parametrize('mode',[0,3])
def test_actual_daemon_preparation_and_export_episode(tmp_path,mode,spawn_test_import_root):
    import core.ipc.shared_state as ipc
    cls=getattr(ipc,'DiagnosticStateManager',None) or ipc.ControlStateManager
    ctx=mp.get_context('spawn')
    with cls(ctx=ctx) as manager:
        state=manager.dict() if hasattr(ipc,'DiagnosticStateManager') else manager.control_dict()
        receive,send=ctx.Pipe(duplex=False)
        process=ctx.Process(target=preparation_host,args=(state,str(tmp_path),send,mode),daemon=True)
        process.start();send.close()
        try:
            assert receive.poll(130.),'process test deadline exceeded'
            value=receive.recv();(tmp_path/'result.json').write_text(json.dumps(value,indent=2))
            assert not value.get('error'),value
            assert value['daemon'] and value['complete'],value
            for part in value['complete']:
                assert not part['backend']['incomplete'],part
        finally:
            process.join(3.)
            if process.is_alive():process.terminate();process.join(3.)
            receive.close();process.close()
