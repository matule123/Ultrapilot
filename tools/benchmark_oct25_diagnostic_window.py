"""Bounded journal tap costs. Explicit synthetic source; no live/game authority."""
import argparse
import gc
import json
from pathlib import Path
import time
import tracemalloc
from core.navigation.longitudinal_diagnostics import PedalJournal
from core.sdk.ets2la_data import _TRAFFIC_SIZE,_PARKED_SIZE


def distribution(values):
    values=sorted(values)
    return dict(samples=len(values),p50_ms=values[int((len(values)-1)*.5)]*1000,
        p95_ms=values[int((len(values)-1)*.95)]*1000,max_ms=max(values)*1000)


def run(enabled,*,heap=False):
    journal=PedalJournal();journal.enabled=True
    if enabled:journal.enable_incident_window()
    # Original ABI-sized moving/parked arrays are synthetic opaque bytes.
    moving=bytes((i%251 for i in range(_TRAFFIC_SIZE)))
    parked=bytes((i%239 for i in range(_PARKED_SIZE)))
    value=dict(moving=moving,parked=parked,source=dict(lifecycle=1,generation=1,
        frame_us=1,observed_at=100.),packet=dict(context=[7,'s','m','d','i',1,'b','g'],
        following=dict(status='candidate',actors=[dict(id=i,x=float(i),y=10.,z=30.+i,
        dimensions=[2.5,4.,6.],source='moving' if i<40 else 'parked') for i in range(80)])))
    costs=[];sealed=None
    if heap:gc.collect();tracemalloc.start()
    for i in range(3601):
        now=100.+i/60.
        value['source'].update(generation=i+1,frame_us=i+1,observed_at=now)
        start=time.perf_counter()
        journal.observe_incident('traffic',value,now)
        journal.observe_incident('ego',dict(speed=10.,gear=4,sdkFrameTimeUs=i+1),now)
        if i==3000:journal.incident_event('TECHNICAL_STOP',dict(reason='modeled fault'),now)
        if i>=3000 and sealed is None:sealed=journal.seal_incident(now)
        costs.append(time.perf_counter()-start)
    status=journal.incident_status()
    if heap:
        gc.collect();retained,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    else:retained=peak=None
    return dict(enabled=enabled,timing=distribution(costs),status=status,
        retained_tracemalloc_bytes=retained,peak_tracemalloc_bytes=peak,
        window=None if sealed is None else sealed['range_s'],
        incomplete=None if sealed is None else sealed['incomplete'],
        modeled_seconds=60.,new_sdk_reads=0,new_ipc_reads=0)


def production(mode,enabled,export_stress=False,isolated_export=False):
    from contextlib import contextmanager
    from collections import Counter
    import hashlib
    import tempfile
    worker=None;temporary=None;busy_costs=[]
    memory=None;monitor=None;monitor_stop=None
    if export_stress:
        from core.steering_replay import AsyncReplayExporter,export_incident,export_incident_isolated
        if isolated_export:export_incident=export_incident_isolated
        history=PedalJournal();history.enabled=True;history.enable_incident_window()
        for i in range(401):
            t=100.+i*.1
            history.observe_incident('traffic',dict(source=dict(generation=i+1,observed_at=t),
                moving=bytes(_TRAFFIC_SIZE),parked=bytes(_PARKED_SIZE),
                actors=[dict(id=a,x=a+.01*i,y=10.,z=30.+a,dimensions=[2.5,4.,6.]) for a in range(80)]),t)
            if i==300:history.incident_event('TECHNICAL_STOP',dict(reason='modeled worker stress'),t)
        sealed=history.seal_incident(140.)
        snapshot=history.snapshot()
        temporary=tempfile.TemporaryDirectory(prefix='ultrapilot-diagnostic-export-')
        worker=AsyncReplayExporter()
        import psutil,threading,os
        parent=psutil.Process(os.getpid())
        memory=dict(parent_initial_rss=parent.memory_info().rss,parent_peak_rss=0,
            child_peak_rss=0,sample_period_s=.02,child_includes_python_interpreter=True)
        monitor_stop=threading.Event()
        def observe_memory():
            while not monitor_stop.is_set():
                memory['parent_peak_rss']=max(memory['parent_peak_rss'],parent.memory_info().rss)
                rss=0
                for child in parent.children(recursive=True):
                    try:rss+=child.memory_info().rss
                    except psutil.Error:pass
                memory['child_peak_rss']=max(memory['child_peak_rss'],rss)
                monitor_stop.wait(.02)
        monitor=threading.Thread(target=observe_memory,name='Benchmark-RSS',daemon=True)
        monitor.start()
    from tests.test_activation_observation_binding import flow
    from tests.signals.test_signal_lifecycle import lifecycle
    with contextmanager(flow.__wrapped__)() as base:
        state,truck,engine,ap,tick,n,clock,writes,_=lifecycle(base,mode)
        journal=engine.controller._pedal_journal
        if enabled:journal.enable_incident_window()
        else:
            journal._incident_window=None
            ap._steering_replay._diagnostic_inputs=None
        counts=Counter();state.hook=lambda key:counts.update([key])
        engine._automatic_replay_directory=None
        costs=[];output=hashlib.sha256();gc_times=[];started=[];mock_calls=0
        def gc_tick(phase,info):
            if phase=='start':started.append(time.perf_counter())
            elif started:gc_times.append(time.perf_counter()-started.pop())
        gc.collect();gc.callbacks.append(gc_tick)
        if worker:worker.submit(lambda:export_incident(temporary.name,sealed,snapshot))
        try:
            for i in range(600):
                red=80<=i%200<130;stopped=100<=i%200<140
                busy=worker is not None and worker.status['busy']
                start=time.perf_counter()
                tick(0 if stopped else 4,0. if stopped else .4 if red else 5.,color=2 if red else 8)
                costs.append(time.perf_counter()-start)
                if busy:busy_costs.append(costs[-1])
                output.update(repr([(ch,v) for _,ch,v,_ in writes]).encode());writes.clear()
                if hasattr(time.monotonic,'reset_mock'):
                    mock_calls=max(mock_calls,time.monotonic.call_count)
                    time.monotonic.reset_mock()
        finally:gc.callbacks.remove(gc_tick)
        worker_result=worker.wait(30.) if worker else None
        if worker:
            assert not worker_result['busy'] and worker_result['path'],worker_result
            worker_result=dict(worker_result,bytes=sum(p.stat().st_size for p in Path(temporary.name).iterdir() if p.is_file()))
            temporary.cleanup()
            monitor_stop.set();monitor.join(2.)
        state.hook=None
        return dict(mode=mode,enabled=enabled,whole_model_tick=distribution(costs),
            writes_sha256=output.hexdigest(),reads=dict(counts),
            gc_ms=distribution(gc_times) if gc_times else None,maximum_mock_clock_calls_per_tick=mock_calls,
            concurrent_export=worker_result,concurrent_tick_ms=distribution(busy_costs) if busy_costs else None,
            sampled_process_memory=memory,
            fault=state.get('autopilot_intervention'),active=state.get('autopilot_active'),
            model='Actual installed-base producers/AP/Engine/Controller; modeled SDK and backend, no game')


def assembly(mode,enabled):
    """Whole output path with actual non-disable two-part export in flight."""
    from contextlib import contextmanager
    from collections import Counter
    from types import SimpleNamespace
    from unittest.mock import patch
    import tempfile,hashlib
    from tests.test_activation_observation_binding import flow
    import tests.signals.test_signal_lifecycle as scene
    from core.longitudinal import context
    from core.steering_replay import inspect_incident
    with tempfile.TemporaryDirectory(prefix='up-assembly-benchmark-') as directory:
      with contextmanager(flow.__wrapped__)() as base:
        state,truck,engine,ap,tick,n,clock,writes,_=scene.lifecycle(base,mode)
        journal=engine.controller._pedal_journal
        if enabled:journal.enable_incident_window()
        else:
            journal._incident_window=None;ap._steering_replay._diagnostic_inputs=None
        engine._automatic_replay_directory=directory
        ap._diagnostic_part_directory=directory
        engine._traffic_brake_basis=None
        moving=bytes(_TRAFFIC_SIZE);parked=bytes(_PARKED_SIZE)
        def publish_traffic(state,truck,source,**values):
            capture=SimpleNamespace(session='benchmark',observed_at=clock[0],
                moving=moving,parked=parked,stable=True,source={})
            return engine._publish_traffic_control(truck,truck['_control_observation']['observed_at'],
                context(state),[],capture,dict(status='no_candidate_unproven_coverage'),0.,values['signal'],None)
        counts=Counter();state.hook=lambda key:counts.update([key])
        costs=[];busy_costs=[];digest=hashlib.sha256();gc_times=[];gc_start=[]
        def observe_gc(phase,info):
            if phase=='start':gc_start.append(time.perf_counter())
            elif gc_start:gc_times.append(time.perf_counter()-gc_start.pop())
        gc.collect();gc.callbacks.append(observe_gc)
        with patch.object(scene,'publish',publish_traffic):
          try:
            for i in range(900):
                phase=i%300
                red=80<=phase<130;stopped=100<=phase<140
                # Allow the existing qualified two-observation green release.
                speed=0. if stopped else .4 if red else 5.
                writer=getattr(engine,'_automatic_replay_writer',None)
                ap_writer=getattr(ap,'_replay_export_writer',None)
                busy=any(w is not None and w.status['busy'] for w in (writer,ap_writer))
                start=time.perf_counter();tick(0 if stopped else 4,speed,color=2 if red else 8)
                cost=time.perf_counter()-start;costs.append(cost)
                if busy:busy_costs.append(cost)
                digest.update(repr([(ch,v) for _,ch,v,_ in writes]).encode());writes.clear()
                if hasattr(time.monotonic,'reset_mock'):time.monotonic.reset_mock()
          finally:gc.callbacks.remove(observe_gc)
        state.hook=None
        for writer in (getattr(ap,'_replay_export_writer',None),getattr(engine,'_automatic_replay_writer',None)):
            if writer:writer.wait(40.)
        cases=[inspect_incident(path) for path in Path(directory).glob('incident-*.json')]
        assert all(c['integrity_valid'] for c in cases)
        status=journal.incident_status()
        ap_ring=ap._steering_replay._diagnostic_inputs
        ap_status=ap_ring.status() if ap_ring is not None else None
        retained=journal._incident_window.rolling_snapshot()['records'] if enabled else []
        streams={}
        for row in retained:streams.setdefault(row['kind'],[]).append(row['at_s'])
        retention={kind:dict(samples=len(times),start_s=min(times),end_s=max(times),
            span_s=max(times)-min(times),max_gap_s=max((b-a for a,b in zip(times,times[1:])),default=0.))
            for kind,times in streams.items()}
        windows=[dict(range_s=(c['replay'].get('longitudinal') or {}).get('diagnostic_incident',{}).get('range_s'),
            capacity_drops=(c['replay'].get('longitudinal') or {}).get('diagnostic_incident',{}).get('capacity_drops'),
            assembly_complete=c['assembly_complete'],incomplete=c['incomplete']) for c in cases]
        return dict(mode=mode,enabled=enabled,whole_model_tick=distribution(costs),
            concurrent_export_tick=distribution(busy_costs) if busy_costs else None,
            gc_ms=distribution(gc_times) if gc_times else None,reads=dict(counts),
            writes_sha256=digest.hexdigest(),active=state.get('autopilot_active'),
            fault=state.get('autopilot_intervention'),engine_ring=status,autopilot_ring=ap_status,
            assembled=sum(c['assembly_complete'] for c in cases),dossiers=len(cases),
            retained_streams=retention,exported_windows=windows,
            load=dict(ticks=900,dt_s=.05,modeled_duration_s=45.,traffic_bytes=len(moving),
                parked_bytes=len(parked),actor_count=0,traffic_publication_hz=20.,
                ring_period_s=.1,ring_limit_bytes=32*1024*1024),
            model='900 production ticks; ABI-sized synthetic native buffers; modeled SDK/backend, not ETS2')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--production',action='store_true')
    parser.add_argument('--export-stress',action='store_true')
    parser.add_argument('--isolated-export',action='store_true')
    parser.add_argument('--assembly',action='store_true')
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Never overwrite measurements')
    if args.assembly:
        rows=[assembly(mode,enabled) for mode in (0,3) for enabled in (False,True)]
        for a,b in zip(rows[::2],rows[1::2]):
            assert a['writes_sha256']==b['writes_sha256'] and a['reads']==b['reads']
            assert a['active'] and b['active'] and a['fault']==b['fault'] is None
            assert b['assembled']>0
        result=dict(assembly=rows,game_verified=False)
    elif args.export_stress:
        result=dict(rows=[production(mode,True,export_stress=True,isolated_export=args.isolated_export)
            for mode in (0,3)],game_verified=False)
    elif args.production:
        rows=[production(mode,enabled) for mode in (0,3) for enabled in (False,True)]
        result=dict(production=rows,game_verified=False)
        for a,b in zip(rows[::2],rows[1::2]):
            assert a['writes_sha256']==b['writes_sha256'] and a['reads']==b['reads']
            assert a['fault']==b['fault'] is None and a['active'] and b['active']
    else:result=dict(timing=[run(False),run(True)],heap=[run(False,heap=True),run(True,heap=True)],
        limitation='Synthetic 80 actor records, 60 Hz caller/10 Hz retained input; tap only, not whole Engine or worker serialization. No mock-call histories retained. Worker/output equivalence measured separately.')
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
