"""Read-only existing-codec incident analysis and bounded operation benchmark."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import time
import tracemalloc
import ast
import subprocess
import sys
from unittest.mock import patch
import multiprocessing as mp
import threading
from types import SimpleNamespace

from core.steering_replay import inspect_replay


def analyze(installation):
    receipt=json.loads((installation/'manual-deployment.json').read_text(encoding='utf-8-sig'))
    files=[]
    for row in receipt['files']:
        target=Path(row['target']);source=Path(row['source'])
        files.append(dict(name=row.get('relative_path',target.name),
            installed_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            receipt_match=hashlib.sha256(target.read_bytes()).hexdigest()==row['sha256'].lower(),
            normalized_current_source_equal=target.read_bytes().replace(b'\r\n',b'\n')==
                source.read_bytes().replace(b'\r\n',b'\n')))
    if not all(f['receipt_match'] for f in files): raise ValueError('receipt mismatch')
    names=('steering-replay-20261013T162000.938437Z-automatic_disable.json',
           'steering-replay-20261013T162002.170123Z-automatic_disable.json')
    artifacts=[];history=None;incident=None
    for name in names:
        p=installation/'route-diagnostics'/name;r=inspect_replay(p)
        if not r['integrity_valid']:raise ValueError((name,'integrity rejected'))
        d=r['replay'];artifacts.append(dict(file=name,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
            samples=d['sample_count'],executions=d['execution_sample_count']))
        if d.get('longitudinal'):
            incident=d['longitudinal'];history=incident['decision_history']
    rows=sorted(history['regular_samples']+history['changes'],key=lambda x:x['monotonic_s'])
    acquired=[{k:r.get(k) for k in ('monotonic_s','acc_target_id','acc_status','identity_reference',
        'speed_mps','gear','acc_gap_m','traffic_departure','written_throttle','written_brake')}
        for r in rows if r.get('acc_target_id')]
    records=[];buffer=[]
    with (installation/'ultrapilot.log').open(encoding='utf-8',errors='replace') as log:
        for line in log:
            if line.startswith('2026-'):
                if buffer: records.append(''.join(buffer))
                buffer=[line] if line.startswith('2026-10-13 ') else []
            elif buffer:buffer.append(line)
    if buffer:records.append(''.join(buffer))
    errors=Counter();restarts=[];shutdown=[]
    for s in records:
        if ' ERROR ' in s:
            code=re.search(r'"failure_code"\s*:\s*"([^\"]+)"',s)
            errors[code.group(1) if code else s.split('[source:')[-1].split(']')[0]]+=1
        if "Plugin 'drivepolicy' died" in s:restarts.append(s.split(' WARNING ')[0])
        if 'shutdown request' in s.lower() or 'complete UltraPilot shutdown' in s:shutdown.append(s[:240])
    return dict(artifacts=artifacts,installation=files,first_intervention=incident['first_intervention'],
        detail_evidence=incident['detail_evidence'],history_incomplete=history['incomplete'],
        identity_table=history['identities'],lead_history=acquired,
        target_records_retained=False,source_slot_retained=False,
        historical_departure_geometry_cause='NOT VERIFIED: original actor boxes/slot/change record absent',
        drivepolicy_historical_exception='NOT RETAINED: former worker could classify KeyError as normal IPC shutdown',
        error_counts=dict(errors),drivepolicy_restart_count=len(restarts),restarts=restarts,shutdown=shutdown)


def operation_costs():
    from core.acc_following import RouteLeadSelector, observation
    from tests.test_acc_following import capture
    selector=RouteLeadSelector();selector.prepare([[2.25,10.,float(z)] for z in range(121)],('route',))
    truck=dict(x=2.25,y=10.,z=15.,rotation=math.pi,speed=10.)
    lead=dict(id=30,x=2.25,y=10.,z=40.,yaw=math.pi,speed=5.)
    incoming=observation(capture([lead],1000.),1000.)['actors']
    outgoing=observation(capture([dict(lead,x=7.,yaw=-math.pi/2)],1000.05),1000.05)['actors']
    source=subprocess.check_output(['git','show','d584ad6:core/acc_following.py'],text=True)
    tree=ast.parse(source)
    method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_departure')
    namespace={}
    exec(compile(ast.Module(body=[method],type_ignores=[]),'baseline-departure','exec'),
        RouteLeadSelector._departure.__globals__,namespace)
    paired={}
    current_method=RouteLeadSelector._departure
    for name,method in (('before',namespace['_departure']),('after',current_method)):
        durations=[]
        with patch.object(RouteLeadSelector,'_departure',method):
            for i in range(1000):
                at=1000.+i*.2;selector.reset();selector.select(incoming,truck,15.,receiver_time=at)
                start=time.perf_counter();selector.select(outgoing,truck,15.,receiver_time=at+.05)
                durations.append((time.perf_counter()-start)*1000.)
        durations.sort()
        paired[name]=dict(p50_ms=durations[499],p95_ms=durations[949],p99_ms=durations[989],maximum_ms=max(durations))
    times=[]
    tracemalloc.start()
    for i in range(1000):
        at=1000.+i*.2;selector.reset();selector.select(incoming,truck,15.,receiver_time=at)
        start=time.perf_counter();r=selector.select(outgoing,truck,15.,receiver_time=at+.05)
        times.append((time.perf_counter()-start)*1000.)
        assert r['departure']
    current,peak=tracemalloc.get_traced_memory();tracemalloc.stop();times.sort()
    seen=set()
    def retained(value):
        if id(value) in seen:return 0
        seen.add(id(value));size=sys.getsizeof(value)
        if isinstance(value,dict):size+=sum(retained(k)+retained(v) for k,v in value.items())
        elif isinstance(value,(list,tuple)):size+=sum(retained(v) for v in value)
        return size
    return dict(samples=1000,p50_ms=times[499],p95_ms=times[949],p99_ms=times[989],
        maximum_ms=max(times),traced_current_bytes=current,traced_peak_bytes=peak,
        limitation='in-process with tracing; times list is test overhead, not runtime retained history',
        bounded_route_points=len(selector.points),bounded_route_edges=len(selector.edges),
        retained_actor_count=1,retained_departure_count=1,
        retained_selector_bytes=retained(selector.__dict__),
        test_timing_history_bytes=sys.getsizeof(times)+sum(sys.getsizeof(v) for v in times),
        paired_untraced=paired,baseline_ref='d584ad6',no_new_sdk_or_ipc_reads=True)


def lifecycle_costs():
    from core.plugin_manager import PluginManager
    from core.ipc.shared_state import SharedState
    source=subprocess.check_output(['git','show','d584ad6:core/plugin_manager.py'],text=True)
    cls=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef) and n.name=='PluginManager')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='tick')
    namespace={}
    exec(compile(ast.Module(body=[method],type_ignores=[]),'baseline-supervision','exec'),
        PluginManager.tick.__globals__,namespace)
    with mp.Manager() as ipc:
        state=SharedState(ipc.dict())
        manager=PluginManager(SimpleNamespace(shared_state=state,settings={},running=True))
        for i in range(12):
            manager.plugins[str(i)]=dict(process=SimpleNamespace(pid=100+i,is_alive=lambda:True),
                stop_event=threading.Event(),started_at=time.monotonic())
        result={}
        for name,method in (('before',namespace['tick']),('after',PluginManager.tick)):
            durations=[]
            for i in range(1000):
                at=time.perf_counter();method(manager,.02)
                durations.append(1000*(time.perf_counter()-at))
            durations.sort()
            result[name]=dict(p50_ms=durations[499],p95_ms=durations[949],
                p99_ms=durations[989],maximum_ms=durations[-1])
        result['scope']='Real Manager IPC, 12 alive process doubles; no game workers, 1000 calls per variant.'
        return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--installation',type=Path,default=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--lifecycle-costs',action='store_true')
    args=p.parse_args()
    if not args.output.resolve().is_relative_to(Path.cwd()/'docs/steering-audit'):
        raise ValueError('write only workspace analysis')
    result=analyze(args.installation);result['costs']=operation_costs()
    if args.lifecycle_costs:result['lifecycle_costs']=lifecycle_costs()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(first=result['first_intervention']['reason'],
        restarts=result['drivepolicy_restart_count'],costs=result['costs']),indent=2))
