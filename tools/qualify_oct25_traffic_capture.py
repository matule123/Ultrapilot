"""Populated native ABI qualification of the existing diagnostic overlay.

Modeled SDK/traffic only. Never attaches a live mapping or installs anything.
Run with the isolated candidate namespace first on sys.path.
"""
import argparse
from collections import Counter
from collections import UserDict
from contextlib import contextmanager
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch


def stats(values):
    if not values:return None
    v=sorted(values)
    return dict(n=len(v),p50_ms=v[int((len(v)-1)*.5)]*1000,
        p95_ms=v[int((len(v)-1)*.95)]*1000,p99_ms=v[int((len(v)-1)*.99)]*1000,
        max_ms=v[-1]*1000)


def raw_capture(count,trailers,at,frame,generation,session,speed):
    """40 fixed ABI slots each; changing nonzero poses, distinct source IDs."""
    from core.sdk.ets2la_data import _TRAFFIC_FMT,_PARKED_FMT
    from core.navigation.traffic_producer import TrafficCapture
    moving=[0.]*(46*40);parked=[0.]*(12*40)
    for i in range(40):
        moving[i*46+12:i*46+16]=[0,0,0,0]
        parked[i*12+10:i*12+12]=[0,0]
    for i in range(count):
        # Two possible route leads and a crossing actor. Remaining trucks and
        # parked objects are adjacent/further traffic, not invented clear-road
        # coverage. Target switch keeps the original actor observed off-route.
        x=15.+(i%8)*4.1;z=-65.-(i//8)*17.2;v=7.+(i%7)*.2;yaw=0.
        if i==0:
            x,z=0.,-36.  # Original owner remains observed when a closer lead joins.
        if i==1:x,z=0.,-46.+15.*min(1.,max(0.,(generation-750)/100.))
        if i==2:
            x,z,v,yaw=23.+.2*math.sin(generation*.03),-32.,1.,math.pi/2
            if 650<=generation<=950:x,v=23.-7.*math.sin(math.pi*(generation-650)/300.),2.5
        x+=.001*math.sin(generation*.13+i);z+=.002*math.cos(generation*.07+i)
        q=(math.cos(yaw/2),0.,math.sin(yaw/2),0.)
        b=i*46
        moving[b:b+16]=[x,10.,z,*q,2.45,3.7,6.3,v,.01*math.sin(generation*.1),trailers,10+i,0,0]
        for j in range(trailers):
            t=b+16+j*10
            moving[t:t+10]=[x+math.sin(yaw)*(j+1)*8.,10.,z+math.cos(yaw)*(j+1)*8.,*q,2.45,3.5,7.2]
        b=i*12
        parked[b:b+12]=[-12.-(i%8)*4.3,10.,-60.-(i//8)*19.-generation*.0001,
            1.,0.,0.,0.,2.2,2.8,4.8,100+i,0]
    raw=TrafficCapture(session,at,struct.pack(_TRAFFIC_FMT,*moving),struct.pack(_PARKED_FMT,*parked),True)
    from tests.lifecycle.test_longitudinal_completion import native_bytes
    from core.sdk.traffic_snapshot import TrafficReader
    from core.navigation.traffic_producer import capture_traffic
    reader=TrafficReader()
    reader.buffer=native_bytes(raw,at,generation=generation,frame=frame,
        ego=[(0.,10.,0.,1.,0.,0.,0.,2.5,3.8,6.)],anchor=(0.,10.,0.),ego_speed=speed)
    return capture_traffic(SimpleNamespace(_timed_traffic_reader=reader),session,at)


class TimedLock:
    def __init__(self,lock,waits,held):self.lock=lock;self.waits=waits;self.held=held;self.local=threading.local()
    def acquire(self,blocking=True,timeout=-1):
        # Materialize this thread's probe storage before taking the measured
        # lock; thread-local dict creation can itself schedule cyclic GC.
        self.local.start=0.
        start=time.perf_counter();ok=self.lock.acquire(blocking,timeout)
        if ok:self.waits.append(time.perf_counter()-start);self.local.start=time.perf_counter()
        return ok
    def release(self):
        self.held.append(time.perf_counter()-self.local.start);self.lock.release()
    def __enter__(self):self.acquire();return self
    def __exit__(self,exc_type,exc_value,traceback):self.release()


class CountedMapping(UserDict):
    """Count logical backend GETs across Engine AND every SDK view, not truck fields."""
    def __init__(self,data):self.data=data;self.reads=Counter()
    def __getitem__(self,key):self.reads[key]+=1;return self.data[key]
    def get(self,key,default=None):self.reads[key]+=1;return self.data.get(key,default)


def _sizing_incident_child(directory,window,journal,connection):
    """Offline budget proposal ONLY; never imported by the application.

    Spawn a real existing exporter with a 32 MiB *model* file bound. No runtime
    source/configuration/installed limit is changed. The result is explicitly
    ineligible for release, just like the existing ring-capacity sizing probe.
    """
    import core.steering_replay as replay
    original=replay.SteeringReplayBuffer.export
    def export(self,*args,**kwargs):
        if kwargs.get('maximum_output_bytes')==16*1024*1024 and kwargs.get('reason')=='diagnostic_incident':
            kwargs=dict(kwargs,maximum_output_bytes=32*1024*1024)
        return original(self,*args,**kwargs)
    replay.SteeringReplayBuffer.export=export
    try:replay._incident_export_child(directory,window,journal,connection)
    finally:replay.SteeringReplayBuffer.export=original


def _profile_export_child(target,args,connection):
    """Time existing export phases without per-Python-call profiler distortion."""
    import psutil
    import core.steering_replay as replay
    import core.navigation.longitudinal_diagnostics as diagnostics
    import core.navigation.evidence_diagnostics as combined_module
    directory=Path(args[0] if isinstance(args[0],(str,os.PathLike)) else args[1])
    spans=[];originals=[];process=psutil.Process()
    def wrap(owner,name):
        original=getattr(owner,name)
        def measured(*a,**kw):
            start=time.perf_counter();cpu=time.thread_time();rss=process.memory_info().rss
            try:return original(*a,**kw)
            finally:spans.append(dict(operation=name,start_s=start,end_s=time.perf_counter(),
                cpu_s=time.thread_time()-cpu,rss_before=rss,rss_after=process.memory_info().rss))
        setattr(owner,name,measured);originals.append((owner,name,original))
    for owner,name in ((diagnostics,'expand_incident_window'),(diagnostics,'pack_exact_window'),
            (replay,'_payload_hash'),(replay,'_archive_incidents'),
            (replay,'_await_autopilot_part'),(replay,'export_incident'),(replay,'export_autopilot_part'),
            (replay,'inspect_incident'),(replay,'inspect_replay')):wrap(owner,name)
    start=time.perf_counter()
    try:return target(*args,connection)
    finally:
        for owner,name,original in reversed(originals):setattr(owner,name,original)
        stem='export-profile-'+str(os.getpid())
        (directory/(stem+'.json')).write_text(json.dumps(dict(target=target.__name__,
            pid=os.getpid(),started_at_s=start,finished_at_s=time.perf_counter(),spans=spans),indent=2))


def run(mode,enabled,count,trailers,ticks,directory,pace=0.,capacity_probe_mib=None,export_enabled=True,file_probe_mib=None,profile_export=False,child_memory_external=False):
    from tests.test_activation_observation_binding import flow
    import tests.signals.test_signal_lifecycle as scene
    from core.longitudinal import context
    from core.steering_replay import inspect_incident
    import psutil
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    if child_memory_external:
        import multiprocessing as mp
        assert mp.current_process().daemon,'External child observer requires the supervised daemon host'
    process=psutil.Process();memory=dict(parent_initial_rss=process.memory_info().rss,
        parent_peak_rss=0,children={},sample_period_s=.02,children_combined_peak_rss=0,
        process_family_peak_rss=0,simultaneous_children_max=0,
        export_children_observed_by='external Manager-family supervisor' if child_memory_external else 'local process-family monitor')
    stop=threading.Event()
    def monitor():
        while not stop.is_set():
            parent_rss=process.memory_info().rss;child_rss=0;child_count=0
            memory['parent_peak_rss']=max(memory['parent_peak_rss'],parent_rss)
            # A daemon host cannot own export processes. Its exports run under
            # the existing Manager, whose complete child family is sampled by
            # run_daemon_host at the SAME 20 ms cadence. Enumerating Windows'
            # entire PID map here was redundant and stalled this host's GIL.
            # Keep local host RSS sampling; retain both monitors for standalone
            # runs which have no external Manager-family observer.
            for p in (() if child_memory_external else process.children(recursive=True)):
                try:
                    key=str(p.pid);rss=p.memory_info().rss
                    memory['children'][key]=max(memory['children'].get(key,0),rss)
                    child_rss+=rss;child_count+=1
                except psutil.Error:pass
            memory['children_combined_peak_rss']=max(memory['children_combined_peak_rss'],child_rss)
            memory['process_family_peak_rss']=max(memory['process_family_peak_rss'],parent_rss+child_rss)
            memory['simultaneous_children_max']=max(memory['simultaneous_children_max'],child_count)
            stop.wait(.02)
    monitor_thread=threading.Thread(target=monitor,daemon=True);monitor_thread.start()
    waits=[];holds=[];cost=[];cpus=[];flush=[];busy_cost=[];gc_cost=[];gc_started=[]
    expected={};physical_trace=[];raw_hash=hashlib.sha256();decision_hash=hashlib.sha256();write_hash=hashlib.sha256()
    phase_counts=Counter();target_ids=set();crossing_ids=set();capture_statuses=Counter()
    held_peaks={'engine':0,'autopilot':0}
    # This is instrumentation of the existing scenario, not a second runtime
    # collector. Inclusive durations can nest; they must not be summed as CPU.
    import core.navigation.longitudinal_diagnostics as diagnostics
    import core.steering_replay as replay_module
    measured={};restores=[];control_thread=threading.get_ident()
    import core.navigation.evidence_diagnostics as combined_module
    def instrument(owner,name,label):
        original=getattr(owner,name)
        def timed(*args,**kwargs):
            start=time.perf_counter()
            try:return original(*args,**kwargs)
            finally:
                suffix='control' if threading.get_ident()==control_thread else 'background'
                measured.setdefault(label+':'+suffix,[]).append(time.perf_counter()-start)
        setattr(owner,name,timed);restores.append((owner,name,original))
    for name,label in (('_freeze_input','snapshot_C_copy_and_digest'),('bounded_copy','legacy_short_journal_copy'),
            ('pack_source','legacy_short_journal_pack'),('finish_engine_incident','incident_seal_and_submit'),
            ('expand_journal','pedal_journal_expansion')):
        instrument(diagnostics,name,label)
    instrument(diagnostics.zlib,'compress','compression')
    instrument(replay_module,'_run_diagnostic_export','export_process_transport_and_completion')
    export_parent_spans=[]
    if profile_export:
        import multiprocessing.reduction as reduction
        from multiprocessing.process import BaseProcess
        for owner,name in ((reduction,'dump'),(BaseProcess,'start')):
            original=getattr(owner,name)
            def measured_parent(*a,_original=original,_name=name,**kw):
                start=time.perf_counter();cpu=time.thread_time()
                try:return _original(*a,**kw)
                finally:export_parent_spans.append(dict(operation=_name,start_s=start,
                    end_s=time.perf_counter(),cpu_s=time.thread_time()-cpu))
            setattr(owner,name,measured_parent);restores.append((owner,name,original))
        # Admission still sees the original directory/arguments. Instrument
        # only the admitted child; do not wrap a function in the directory slot.
        original=replay_module._run_admitted_diagnostic_export
        from tools.qualify_oct25_traffic_capture import _profile_export_child as profile_child
        def profiled(target,args):return original(profile_child,(target,args))
        replay_module._run_admitted_diagnostic_export=profiled
        restores.append((replay_module,'_run_admitted_diagnostic_export',original))
    if file_probe_mib is not None:
        assert enabled and export_enabled and file_probe_mib==32
        # Import by module name so Windows spawn can load this test-only target.
        from tools.qualify_oct25_traffic_capture import _sizing_incident_child as sizing_child
        restores.append((replay_module,'_incident_export_child',replay_module._incident_export_child))
        replay_module._incident_export_child=sizing_child
    for owner,name,label in (
            (diagnostics._IncidentWindow,'observe','capture_retention'),
            (diagnostics._IncidentWindow,'seal','incident_window_assembly'),
            (diagnostics.PedalJournal,'bind','decision_binding_and_legacy_copy'),
            (diagnostics.PedalJournal,'record','backend_diagnostic_callback'),
            (diagnostics.AutopilotIncidentParts,'consume','AP_consumed_input_capture'),
            (diagnostics.AutopilotIncidentParts,'end','AP_tick_finalize_and_handoff')):
        instrument(owner,name,label)
    if hasattr(combined_module,'_DeferredLongitudinal'):
        instrument(combined_module._DeferredLongitudinal,'materialize','combined_pedal_normalization')
    main_thread=threading.get_ident();in_tick=[False];io_violations=[];generation=[0]
    with contextmanager(flow.__wrapped__)() as base:
      state,truck,engine,ap,tick,n,clock,writes,combined_sink=scene.lifecycle(base,mode)
      combined_sink_count=0
      # Exercise the EXISTING one-slot collector worker, not a sink that omits
      # deferred CPU work. Geometry/export validation is covered separately;
      # this sink executes the actual changed normalization and records calls.
      combined_worker=combined_module.EvidenceDiagnosticCollector(directory/'evidence-diagnostics')
      combined_worker._state='COLLECTING';combined_worker._sample_period_s=.05
      # Startup calls were captured by the fixture before installing the real
      # worker. Keep those exact existing captures, not invented replacement
      # packets, when comparing against the complete physical trace.
      combined_calls=[(e['call_started_at_s'],e['channel'],(e.get('backend') or {}).get('value'))
          for c in combined_sink.samples for e in combined_module._jsonable(c.longitudinal).get('events',[])]
      combined_errors=[];combined_busy=threading.Event()
      combined_processed=[0];combined_lost=[0]
      def normalize_capture(capture):
          combined_busy.set()
          try:
              pedals=combined_module._jsonable(capture.longitudinal)
              combined_lost[0]+=pedals.get('dropped_events',0)
              combined_calls.extend((e['call_started_at_s'],e['channel'],(e.get('backend') or {}).get('value'))
                  for e in pedals.get('events',[]))
              combined_processed[0]+=1
          except Exception as error:combined_errors.append(type(error).__name__+':'+str(error))
          finally:combined_busy.clear()
      combined_worker._ingest=normalize_capture
      engine._maneuver_diagnostic_collector=combined_worker;combined_worker.start()
      # Remember only the last refused IMMUTABLE offer at the model boundary.
      # A real still-running application has subsequent capture opportunities;
      # this finite test must not shut its worker down before handing off that
      # already captured final frame. No SDK/control read or new time is used.
      original_offer=combined_worker.offer;refused_tail=[None]
      def observed_offer(capture):
          accepted=original_offer(capture)
          refused_tail[0]=None if accepted else capture
          return accepted
      combined_worker.offer=observed_offer
      lane=state.get('lane_trajectory')
      identity={k:lane[k] for k in ('source_game_session_id','source_map_key','source_dataset_fingerprint',
          'navigation_intent_id','revision','route_build_id')}
      state.set('lane_trajectory_identity',identity)
      debug=state.get('nav_steering_debug');debug['trajectory_identity']=identity;state.set('nav_steering_debug',debug)
      journal=engine.controller._pedal_journal
      if enabled:journal.enable_incident_window()
      else:journal._incident_window=None;ap._steering_replay._diagnostic_inputs=None
      if capacity_probe_mib is not None:
          # Design-sizing experiment ONLY in this in-memory model. This is not
          # a runtime allowance: the release gate requires exactly 32 MiB and
          # explicitly rejects every capacity-probe result. No installed file
          # or candidate source is edited by this measurement.
          assert enabled and capacity_probe_mib in (64,128)
          journal._incident_window.limit=capacity_probe_mib*1024*1024
      engine._automatic_replay_directory=str(directory) if export_enabled else None
      ap._diagnostic_part_directory=str(directory)
      for ring in (journal._incident_window,ap._steering_replay._diagnostic_inputs):
          if ring is not None:ring.lock=TimedLock(ring.lock,waits,holds)
      underlying=state.values;mapping=CountedMapping(underlying);state.values=mapping
      for plugin in (ap,tick.acc,tick.policy):
          for view in (plugin.sdk,*vars(plugin.sdk).values()):
              if getattr(view,'__dict__',{}).get('_state') is underlying:
                  object.__setattr__(view,'_state',mapping)
      reads=mapping.reads
      original_flush=engine._flush_controls
      def timed_flush(*args,**kwargs):
          start=time.perf_counter()
          try:return original_flush(*args,**kwargs)
          finally:flush.append(time.perf_counter()-start)
      engine._flush_controls=timed_flush
      paired=dict(aforward=0.,abackward=0.);pedal_overlap=0
      def publish_traffic(state,truck,source,**values):
          generation[0]+=1
          binding=context(state)
          capture=raw_capture(count,trailers,clock[0],truck['sdkFrameTimeUs'],generation[0],str(binding[1]),truck['speed'])
          capture_statuses['valid_native']+=int(capture.source['valid'])
          following,brake=engine._traffic_control_observation(capture,truck,binding,[])
          capture_statuses['following:'+following['status']]+=1
          if following.get('target_id'):target_ids.add(str(following['target_id']))
          crossing_ids.update(str(c['id']) for c in (following.get('crossing') or {}).get('conflicts',[]))
          published=engine._publish_traffic_control(truck,truck['_control_observation']['observed_at'],
              binding,[],capture,following,brake,values['signal'],None)
          digest=hashlib.sha256(capture.moving+capture.parked).hexdigest()
          expected[generation[0]]=dict(hash=digest,at=clock[0],frame=truck['sdkFrameTimeUs'],
              context=published['context'],moving=capture.moving,parked=capture.parked)
          raw_hash.update(digest.encode())
          return published
      def gc_observer(phase,info):
          if phase=='start':gc_started.append(time.perf_counter())
          elif gc_started:gc_cost.append(time.perf_counter()-gc_started.pop())
      import builtins
      original_open=builtins.open
      def audit_open(file,*args,**kwargs):
          if in_tick[0] and threading.get_ident()==main_thread:
              try:
                  if Path(file).is_relative_to(directory):io_violations.append(str(file))
              except TypeError:pass
          return original_open(file,*args,**kwargs)
      gc.collect();gc.callbacks.append(gc_observer)
      with patch.object(scene,'publish',publish_traffic),patch.object(builtins,'open',audit_open):
       try:
        for i in range(ticks):
          # First 35 seconds warm up naturally; the later red creates an actual
          # post-warm event, with overlapping native target-change/state edges.
          red=900<=i<1000;stopped=930<=i<1010
          v=0. if stopped else .4 if red else 5.
          busy=any(w is not None and w.status['busy'] for w in (
              getattr(engine,'_automatic_replay_writer',None),getattr(ap,'_replay_export_writer',None)))
          start=time.perf_counter();cpu=time.thread_time();in_tick[0]=True
          try:tick(0 if stopped else 4,v,color=2 if red else 8)
          finally:in_tick[0]=False
          cost.append(time.perf_counter()-start);cpus.append(time.thread_time()-cpu)
          if enabled:
              # Local integer observations, outside the measured tick; no
              # snapshot expansion, locking scan or SDK/IPC access.
              for label,ring in (('engine',journal._incident_window),('autopilot',ap._steering_replay._diagnostic_inputs)):
                  if ring is not None:held_peaks[label]=max(held_peaks[label],ring.bytes)
          if busy:busy_cost.append(cost[-1])
          phase_counts[underlying.get('autopilot_control_state')]+=1
          for _,ch,value,_ in writes:
              if ch in paired:
                  paired[ch]=value
                  if paired['aforward']>0. and paired['abackward']>0.:pedal_overlap+=1
          physical_trace.extend((t,'throttle' if ch=='aforward' else 'brake',value)
              for t,ch,value,_ in writes if ch in ('aforward','abackward'))
          write_hash.update(repr([(ch,value) for _,ch,value,_ in writes]).encode());writes.clear()
          # Captures is the fixture's unbounded *test history*, not the runtime
          # combined collector. It previously retained every expanded sample
          # for the whole 70 s and its GC dominated even the off baseline.
          # Consume/clear only this mock history outside the timed tick, just
          # like the existing backend-write mock. Runtime rings/GC stay enabled.
          combined_sink_count+=len(combined_sink.samples);combined_sink.samples.clear()
          command=underlying.get('longitudinal_command') or {}
          decision_hash.update(json.dumps({k:command.get(k) for k in ('source','throttle','brake','decision_source','reason','valid','emergency')},sort_keys=True).encode())
          if hasattr(time.monotonic,'reset_mock'):time.monotonic.reset_mock()
          if pace:time.sleep(pace)
       finally:gc.callbacks.remove(gc_observer)
      reads=dict(reads)
      drain_deadline=time.perf_counter()+10.
      while (combined_worker._queue.qsize() or combined_busy.is_set()) and time.perf_counter()<drain_deadline:
          time.sleep(.005)
      tail_retry=False
      if refused_tail[0] is not None and not combined_busy.is_set() and not combined_worker._queue.qsize():
          retained=refused_tail[0]
          tail_retry=original_offer(retained)
          if tail_retry:
              refused_tail[0]=None
              while (combined_worker._queue.qsize() or combined_busy.is_set()) and time.perf_counter()<drain_deadline:
                  time.sleep(.005)
      combined_status=combined_worker.status()
      combined_worker.close(3.)
      combined_result=dict(worker='existing EvidenceDiagnosticCollector._run',queue_capacity=1,
          normalized_samples=combined_processed[0],rejected_offers=combined_status['dropped_samples'],
          reported_missing_pedal_events=combined_lost[0],errors=combined_errors,
          exact_backend_trace=combined_calls==physical_trace,
          normalized_backend_calls=len(combined_calls),physical_backend_calls=len(physical_trace),
          quiescent_tail_retry=tail_retry,
          tail_retry_scope='Test boundary only; same last refused immutable frame, unchanged original time/input/sequence; no extra control or SDK read',
          scope='Actual bounded handoff and worker normalization; full geometry/collection export tested in regression suite')
      for w in (getattr(ap,'_replay_export_writer',None),getattr(engine,'_automatic_replay_writer',None)):
          if w:w.wait(60.)
      stop.set();monitor_thread.join(2.)  # Exclude offline inspector allocations.
      # Original values are checked AFTER the measured control path, never by
      # extra SDK/IPC reads. Full native bytes come from the existing export.
      cases=[];exact=0;post_warm=[];files=list(directory.glob('incident-*.json'))
      for path in files:
          checked=inspect_incident(path)
          if not checked['integrity_valid']:raise ValueError(checked['reason'])
          window=checked['replay']['longitudinal']['diagnostic_incident']
          import base64,zlib
          for row in window['records']:
              if row['kind']!='traffic':continue
              capture=row['value']['capture'];src=capture['source'];g=src['generation'];e=expected[g]
              def raw(v):
                  return zlib.decompress(base64.b64decode(v['data'])) if isinstance(v,dict) and v.get('encoding')=='zlib-base64' else v
              assert raw(capture['moving'])==e['moving'] and raw(capture['parked'])==e['parked']
              assert src['observed_at']==e['at'] and src['frame_us']==e['frame']
              observed_context=row['value']['packet']['context']
              if window.get('record_format')=='simple-exact-record':
                  assert type(observed_context) is type(e['context'])
                  assert observed_context==e['context']
              else:
                  # Legacy JSON converted tuples to lists. The simple proposal
                  # now proves the actual publisher's type as well as identity.
                  assert tuple(observed_context)==tuple(e['context'])
              exact+=1
          entry=dict(name=path.name,range=window['range_s'],trigger=window['trigger_at_s'],
              capacity_drops=window['capacity_drops'],capture_failures=window['capture_failures'],
              assembly_complete=checked['assembly_complete'],incomplete=checked['incomplete'],
              parts=checked['dossier'].get('parts'),subevents=len(window['subevents']),
              bytes=sum((directory/f['name']).stat().st_size for f in checked['dossier']['files'])+path.stat().st_size,
              backend=checked['dossier'].get('component_completeness',{}).get('backend_detail'))
          call_rows=[r['value'] for r in window['records'] if r['kind']=='backend_call']
          if call_rows:
              actual=[(c['call_started_at_s'],c['channel'],c['backend'].get('value')) for c in call_rows]
              start,end=call_rows[0]['call_started_at_s'],call_rows[-1]['call_returned_at_s']
              expected_calls=[c for c in physical_trace if start<=c[0]<=end]
              if actual!=expected_calls:raise ValueError('EXACT_PHYSICAL_PEDAL_TRACE_MISMATCH')
              entry['exact_physical_pedal_calls']=len(actual)
          cases.append(entry)
          if window['range_s']['pre_s']>=29.9:post_warm.append(entry)
      status=journal.incident_status();ap_status=ap._steering_replay._diagnostic_inputs.status() if enabled else None
      storage=None
      if enabled:
          window=journal._incident_window
          with window.lock:
              rows=list(window.rows)
              kinds=Counter();bodies={}
              for row,size in rows:
                  kinds[row['kind']]+=size
                  for body in window.row_inputs(row):
                      key=id(body)
                      if key not in bodies:bodies[key]=dict(bytes=body.size,kinds=set())
                      bodies[key]['kinds'].add(row['kind'])
              shared=Counter()
              for body in bodies.values():shared['+'.join(sorted(body['kinds']))]+=body['bytes']
              storage=dict(row_bytes_by_kind=dict(kinds),unique_body_bytes_by_use=dict(shared),
                  unique_bodies=len(bodies),accounted_bytes=sum(kinds.values())+sum(b['bytes'] for b in bodies.values()))
      active=state.values.get('autopilot_active');fault=state.values.get('autopilot_intervention')
    stop.set();monitor_thread.join(2.)
    # Histories of mock telemetry expectations are excluded from ring accounting.
    for owner,name,original in reversed(restores):setattr(owner,name,original)
    return dict(mode=mode,enabled=enabled,count_per_buffer=count,trailers_per_moving=trailers,
        runtime_limits=diagnostics.diagnostic_build_limits(),
        capacity_probe_mib=capacity_probe_mib,file_probe_mib=file_probe_mib,
        eligible_for_release=capacity_probe_mib is None and file_probe_mib is None,
        export_enabled=bool(export_enabled),
        export_profile=bool(profile_export),export_parent_spans=export_parent_spans,
        ticks=ticks,modeled_seconds=ticks*.05,whole_tick=stats(cost),cpu_tick=stats(cpus),
        total_wall_tick_s=sum(cost),total_thread_cpu_s=sum(cpus),
        cpu_note='Windows per-thread CPU can update in scheduler quanta; wall-minus-thread-CPU is NOT a measurement of lock/IPC blocking. Lock acquisition waits are measured separately.',
        non_cpu_wall=stats([max(0.,w-c) for w,c in zip(cost,cpus)]),engine_flush=stats(flush),
        concurrent_export_tick=stats(busy_cost),ring_lock_wait=stats(waits),ring_lock_hold=stats(holds),
        diagnostic_operations={k:dict(stats(v),total_s=sum(v)) for k,v in measured.items()},
        operation_note='Inclusive wall durations; nested phases are not additive. Background export includes bounded transport/child completion. In-process mapping is not measured Manager IPC.',
        combined_test_sink=dict(samples=combined_sink_count,retention='one tick; cleared outside measured tick; runtime evidence rings unchanged'),
        combined_worker=combined_result,
        gc=stats(gc_cost),memory=memory,dossiers=cases,post_warm_dossiers=post_warm,
        exact_native_records=exact,engine_ring=status,ap_ring=ap_status,
        retained_byte_high_water_sampled_each_tick=held_peaks,
        engine_storage=storage,
        reads=reads,logical_backend_gets=sum(reads.values()),pedal_overlap=pedal_overlap,
        physical_writes_sha256=write_hash.hexdigest(),decisions_sha256=decision_hash.hexdigest(),
        native_input_sha256=raw_hash.hexdigest(),phase_counts=dict(phase_counts),targets=sorted(target_ids),
        crossings=sorted(crossing_ids),capture_statuses=dict(capture_statuses),
        control_thread_export_io=io_violations,active=active,fault=fault,
        files_bytes=sum(p.stat().st_size for p in directory.rglob('*') if p.is_file()),
        model=True,game_verified=False)


def _daemon_qualification(arguments,state,connection):
    try:
        from core.steering_replay import configure_diagnostic_export
        from core.ipc.shared_state import SharedState
        configure_diagnostic_export(SharedState(state))
        connection.send(dict(result=run(**arguments,child_memory_external=True)))
    except Exception as error:connection.send(dict(error=type(error).__name__,detail=str(error)))
    finally:connection.close()


def run_daemon_host(arguments):
    """Same scenario in real spawn/daemon shape; include broker/child memory."""
    import multiprocessing as mp,psutil
    from core.ipc.shared_state import DiagnosticStateManager
    context=mp.get_context('spawn');memory=dict(parent_initial_rss=0,parent_peak_rss=0,
        broker_peak_rss=0,host_peak_rss=0,children={},sample_period_s=.02,
        children_combined_peak_rss=0,process_family_peak_rss=0,simultaneous_children_max=0)
    with DiagnosticStateManager(ctx=context) as manager:
        receive,send=context.Pipe(duplex=False)
        # Keep the owner proxy alive until the child has finished. Passing a
        # temporary manager.dict() lets its decref retire the service before
        # Windows spawn has unpickled/incref'd the child proxy.
        service_state=manager.dict()
        process=context.Process(target=_daemon_qualification,args=(arguments,service_state,send),daemon=True)
        process.start();send.close();deadline=time.perf_counter()+400.
        host=psutil.Process(process.pid);broker=psutil.Process(manager._process.pid)
        try:
            while True:
                try:
                    h=host.memory_info().rss;b=broker.memory_info().rss
                    children=broker.children(recursive=True);child_rss=0
                    for child in children:
                        try:rss=child.memory_info().rss
                        except psutil.Error:continue
                        memory['children'][str(child.pid)]=max(memory['children'].get(str(child.pid),0),rss)
                        child_rss+=rss
                    memory['host_peak_rss']=max(memory['host_peak_rss'],h)
                    memory['broker_peak_rss']=max(memory['broker_peak_rss'],b)
                    memory['parent_peak_rss']=max(memory['parent_peak_rss'],h+b)
                    memory['children_combined_peak_rss']=max(memory['children_combined_peak_rss'],child_rss)
                    memory['process_family_peak_rss']=max(memory['process_family_peak_rss'],h+b+child_rss)
                    memory['simultaneous_children_max']=max(memory['simultaneous_children_max'],len(children))
                except psutil.Error:pass
                if receive.poll(.02):break
                if time.perf_counter()>=deadline:raise TimeoutError('DAEMON_QUALIFICATION_TEST_DEADLINE')
            envelope=receive.recv()
            if envelope.get('error'):raise RuntimeError(str(envelope))
            value=envelope['result'];value['host_local_memory']=value['memory'];value['memory']=memory
            value['daemon_host']=True
            value['process_scope']='daemon host + existing Manager broker + admitted export child; supervisor excluded'
            return value
        finally:
            process.join(3.)
            if process.is_alive():process.terminate();process.join(3.)
            receive.close();process.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mode',type=int,choices=[0,3],default=0);p.add_argument('--enabled',type=int,choices=[0,1],default=1)
    p.add_argument('--count',type=int,choices=[8,40],default=40);p.add_argument('--trailers',type=int,choices=[0,1,3],default=3)
    p.add_argument('--ticks',type=int,default=1400);p.add_argument('--pace',type=float,default=0.)
    p.add_argument('--capacity-probe-mib',type=int,choices=[64,128],default=None)
    p.add_argument('--export-enabled',type=int,choices=[0,1],default=1)
    p.add_argument('--file-probe-mib',type=int,choices=[32],default=None)
    p.add_argument('--profile-export',action='store_true')
    p.add_argument('--daemon-host',action='store_true')
    args=p.parse_args();assert not args.output.exists()
    arguments=dict(mode=args.mode,enabled=bool(args.enabled),count=args.count,trailers=args.trailers,
        ticks=args.ticks,directory=args.output.with_suffix(''),pace=args.pace,
        capacity_probe_mib=args.capacity_probe_mib,export_enabled=bool(args.export_enabled),
        file_probe_mib=args.file_probe_mib,profile_export=args.profile_export)
    value=run_daemon_host(arguments) if args.daemon_host else run(**arguments)
    args.output.write_text(json.dumps(value,indent=2),encoding='utf-8');print(json.dumps({k:value[k] for k in ('active','fault','engine_ring','whole_tick','targets','crossings')},indent=2))
