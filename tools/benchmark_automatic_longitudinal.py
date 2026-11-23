"""Actual offline producers/Controller at modeled SDK/output 60 Hz, AP 20 Hz.

No sleep/game mapping/arming. Separate untraced timings from traced heap costs.
The private diagnostic opt-out is used only for a same-input comparison.
"""
import argparse
from collections import Counter
from contextlib import contextmanager
import json
import gc
from pathlib import Path
import sys
import time
import tracemalloc

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def scenario(enabled,samples=360,*,heap=False,events=False):
    from tests.test_activation_observation_binding import flow
    from tests.signals.test_signal_lifecycle import lifecycle
    from tests.test_signal_stop_resume import source_bytes
    from core.longitudinal import context,publish
    with contextmanager(flow.__wrapped__)() as raw:
        state,truck,engine,ap,tick,n,clock,writes,collected=lifecycle(raw)
        # The fixture owns restoration of its patched clock. A plain callable
        # avoids Mock retaining every clock call (not a runtime allocation).
        time.monotonic=lambda:clock[0]
        engine._maneuver_diagnostic_collector=None
        engine._automatic_longitudinal_diagnostics=enabled
        ap._longitudinal_diagnostics=enabled
        update=raw[4]
        counts=Counter(); state.hook=lambda key:counts.update([key])
        costs=[];producer=[];max_bytes=0;history_max_bytes=0;mapping_frames=[]
        capture_costs=[];seal_costs=[];last_braking=False
        initial_writes=len(writes)
        if heap:
            gc.collect()
            tracemalloc.start()
        for i in range(samples):
            update(4,.4+(i%17)*.002,dt=1/60)
            if i%3==0:
                current=state.get('telemetry')['truck']
                engine._signal_reader.buffer=source_bytes(clock[0],100+i,current['sdkFrameTimeUs'],color=8)
                signal=engine._signal_observation(current,context(state))
                braking=events and i>=1800 and 120<=i%600<240
                traffic=publish(state,current,'traffic',signal=signal,light=signal.get('candidate'),
                    traffic_brake=.35 if braking else 0.,light_brake=0.,following=None,
                    brake_basis=dict(kind='modeled_conflict',target_id=71,conflict_time_s=3.) if braking else None)
                if braking and not last_braking and enabled:
                    journal=engine.controller._pedal_journal
                    t=time.perf_counter();journal.significant('AVOID_OBSTACLE',traffic,clock[0])
                    capture_costs.append(time.perf_counter()-t)
                last_braking=braking
                tick.policy.on_tick(.05);tick.acc.on_tick(.05)
                t=time.perf_counter();ap.on_tick(.05);producer.append(time.perf_counter()-t)
            t=time.perf_counter();engine._flush_controls();costs.append(time.perf_counter()-t)
            # Compare every mapped control (including steering/selector), not
            # just the fixture's pedal edge assertion list. Exclude this test
            # recorder entirely from the retained-heap runs.
            if not heap:mapping_frames.append(engine.controller.scs._buf.getvalue())
            journal=engine.controller._pedal_journal
            if enabled and events and journal._pending_event is not None and journal._pending_event['after'] is None and clock[0]>=journal._pending_event['tail_until']:
                t=time.perf_counter();journal.ready_significant(clock[0]);seal_costs.append(time.perf_counter()-t)
            max_bytes=max(max_bytes,journal._bytes)
            history=journal._history
            history_max_bytes=max(history_max_bytes,sum(history.bytes.values())+history.identity_bytes)
            # The test backend keeps expanded source() copies in an unbounded
            # assertion list; production SCSControls keeps no such list. Do not
            # attribute the test recorder's history to runtime retained memory.
            if heap:writes.clear()
        if heap:gc.collect()
        usage=tracemalloc.get_traced_memory() if heap else None
        heap_top=[str(s) for s in tracemalloc.take_snapshot().statistics('lineno')[:8]] if heap else None
        if heap:tracemalloc.stop()
        state.hook=None
        snapshot=journal.snapshot(include_history=True)
        history=snapshot['decision_history']
        return dict(costs=costs,producer_costs=producer,ipc_gets=dict(counts),
            capture_costs=capture_costs,seal_costs=seal_costs,
            sealed_receipt_bytes=(journal._pending_event or {}).get('receipt_bytes'),
            sealed_history_bytes=(journal._pending_event or {}).get('before',{}).get('decision_history',{}).get('retained_bytes'),
            mapping_frames=mapping_frames,
            writes=[(c,v) for _,c,v,_ in writes[initial_writes:]],
            retained_bytes=max_bytes,retained_events=len(snapshot['events']),
            dropped_events=snapshot['dropped_events'],heap=usage,heap_top=heap_top,
            detail_duration_s=snapshot['detail_evidence']['duration_s'],
            history=dict(max_accounted_bytes=history_max_bytes,retained_bytes=history['retained_bytes'],
                byte_budget=history['byte_budget'],duration_s=history['observed_range_s']['duration'],
                regular_samples=len(history['regular_samples']),changes=len(history['changes']),
                regular_dropped_capacity=history['regular_dropped_capacity'],
                change_dropped_capacity=history['change_dropped_capacity'],
                capture_failures=history['capture_failures'],incomplete=history['incomplete']))


def distribution(values):
    values=sorted(values)
    def p(q):return values[min(len(values)-1,int(q*(len(values)-1)))]*1000
    return dict(samples=len(values),median_ms=p(.5),p95_ms=p(.95),p99_ms=p(.99),max_ms=p(1.))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=360)
    parser.add_argument('--events',action='store_true',help='Modeled brake-source edges and one sealed event slot; disk worker excluded')
    args=parser.parse_args()
    if args.events and args.samples<2400:parser.error('--events requires at least 2400 samples for a warmed 30 s history')
    if not args.output.resolve().is_relative_to(ROOT):parser.error('Output must stay in workspace')
    a=scenario(False,args.samples,events=args.events);b=scenario(True,args.samples,events=args.events)
    ma=scenario(False,args.samples,heap=True,events=args.events);mb=scenario(True,args.samples,heap=True,events=args.events)
    result=dict(model=dict(sdk_hz=60,engine_hz=60,producer_hz=20,combined_armed=False),
        simulated_duration_s=args.samples/60,
        physical_writes_identical=a['writes']==b['writes'],engine_ipc_reads_identical=a['ipc_gets']==b['ipc_gets'],
        all_control_mapping_frames_identical=a['mapping_frames']==b['mapping_frames'],
        timing={name:dict(engine=distribution(data['costs']),producer=distribution(data['producer_costs']))
                for name,data in (('off',a),('on',b))},
        retained_bytes=b['retained_bytes'],retained_events=b['retained_events'],dropped_events=b['dropped_events'],
        detail_duration_s=b['detail_duration_s'],history=b['history'],
        heap=dict(off_current=ma['heap'][0],off_peak=ma['heap'][1],on_current=mb['heap'][0],on_peak=mb['heap'][1]),
        heap_top=dict(off=ma['heap_top'],on=mb['heap_top']),
        limitation='Copying in-process IPC fixture; BytesIO backend; no ETS2 or process scheduling evidence. Heap excludes test-only unbounded backend assertion history, includes existing replay/PID data; retained heap after GC, peak before GC. Encoding measured on control path, disk/export on worker not included.')
    result['timing_increment_ms']={kind:{key:result['timing']['on'][kind][key]-result['timing']['off'][kind][key]
        for key in ('median_ms','p95_ms','max_ms')} for kind in ('engine','producer')}
    if args.events:
        result['significant_capture']=dict(capture=distribution(b['capture_costs']),
            tail_seal=distribution(b['seal_costs']),receipt_bytes=b['sealed_receipt_bytes'],
            history_bytes=b['sealed_history_bytes'],
            limitation='One pending sealed event; successive edges coalesced. No file worker in timing/heap. Capture already-consumed traffic packet, no extra source reads.')
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
    return 0 if (result['physical_writes_identical'] and result['engine_ipc_reads_identical']
        and result['all_control_mapping_frames_identical']) else 1


if __name__=='__main__':raise SystemExit(main())
