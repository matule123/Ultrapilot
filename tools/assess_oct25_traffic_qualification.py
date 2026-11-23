"""Apply the predeclared acceptance gates; never deploys or alters runtime."""
import argparse
import hashlib
import json
from pathlib import Path


BASELINE_SCOPE_APPROVAL=dict(approval_date='2026-10-26',
    authority='Explicit user reply in this chat; no deployment approval',
    statement='Completeness required for enabled capture only; off baseline compares timing and control',
    unchanged_gates=['timing','memory','output_equivalence','input_identity','enabled_capture_completeness'])


def worker_contract_valid(worker,*,enabled,baseline_scope_approved=False):
    return bool(worker.get('queue_capacity')==1 and not worker.get('errors')
        and (worker.get('reported_missing_pedal_events')==0 or
            not enabled and baseline_scope_approved))


def assess(directory):
    root=Path(directory)
    failures=[];pairs=[]
    criteria_sha=hashlib.sha256((root/'ACCEPTANCE.md').read_bytes()).hexdigest()
    origin=root/'original03-identity.json'
    if not origin.exists():origin=root.parent/'original03-identity.json'
    if criteria_sha!=json.loads(origin.read_text(encoding='utf-8'))['criteria_sha256']:
        raise ValueError('PREDECLARED_CRITERIA_CHANGED')
    approval_path=root/'approved-budget.json';approval=None
    scope_path=root/'baseline-scope-approval.json';scope_approval=None
    if scope_path.exists():
        scope_approval=json.loads(scope_path.read_text(encoding='utf-8'))
        if scope_approval.get('approved_scope')!=BASELINE_SCOPE_APPROVAL:
            raise ValueError('UNRECOGNIZED_BASELINE_SCOPE_APPROVAL')
    if approval_path.exists():
        approval=json.loads(approval_path.read_text())
        if approval['approved_budget']!=dict(approval_date='2026-10-26',
                authority='Explicit user reply in this chat; no deployment approval',
                engine_ring_mib=64,autopilot_ring_mib=32,engine_file_mib=32,
                child_rss_mib=1536,parent_additional_rss_mib=512,family_additional_rss_mib=2048):
            raise ValueError('UNRECOGNIZED_BUDGET_APPROVAL')
    for mode,label in ((0,'simple'),(3,'real')):
        off=json.loads((root/f'final-max-{label}-off.json').read_text(encoding='utf-8'))
        on=json.loads((root/f'final-max-{label}-on.json').read_text(encoding='utf-8'))
        def check(ok,reason):
            if not ok:failures.append(dict(mode=mode,reason=reason))
        check(off.get('capacity_probe_mib') is None and on.get('capacity_probe_mib') is None,
            'capacity-sizing probe is not release qualification')
        check(off.get('file_probe_mib') is None and on.get('file_probe_mib') is None,
            'file-sizing probe is not release qualification')
        check(on.get('runtime_limits',{}).get('approved',False)==bool(approval),
            'approved runtime limits do not match the acceptance budget')
        for key in ('reads','physical_writes_sha256','decisions_sha256','native_input_sha256'):
            check(off[key]==on[key],key+' differs off/on')
        check(off['active'] and on['active'] and off['fault'] is None and on['fault'] is None,'unexpected control intervention')
        check(on['pedal_overlap']==off['pedal_overlap']==0,'overlapping positive pedals')
        for variant in (off,on):
            worker=variant.get('combined_worker') or {}
            check(worker_contract_valid(worker,enabled=variant is on,
                    baseline_scope_approved=scope_approval is not None),
                'existing combined worker exceeded its bound or reported pedal evidence loss')
        # As with incident capacity/parts below, complete collected evidence is
        # required of the ENABLED capture. The off run is the timing/control
        # baseline; its rejected offers are reported, not called complete.
        check(on.get('combined_worker',{}).get('exact_backend_trace') is True,
            'enabled combined worker lost or changed physical pedal evidence')
        check(on['count_per_buffer']==40 and on['trailers_per_moving']==3,'maximum native population not measured')
        check(on['targets']==['10','11'] and '12' in on['crossings'],'lead change/crossing scenario missing')
        check(bool(on['post_warm_dossiers']),'post-warm live dossier missing')
        for c in on['post_warm_dossiers']:
            check(c['range']['pre_s']>=29.9 and c['range']['post_s']>=10.,'30-before/10-after coverage missing')
            check(c['capacity_drops']==c['capture_failures']==0,'incident capacity/capture loss')
            check(c['assembly_complete'] and c['parts']['autopilot']['complete'],'exact AP part not complete')
            check(not c['incomplete'],'warm dossier reports incomplete evidence')
            check(c['subevents']>=2,'overlapping events not retained')
            detail=c.get('backend') or {}
            check(detail.get('storage')=='full_incident_window' and not detail.get('incomplete',True)
                and detail.get('missing_decision_references')==detail.get('missing_call_sequences')==0,
                'full exact pedal detail incomplete')
            check((detail.get('detail_evidence') or {}).get('duration_s',0)>=39.9
                and c.get('exact_physical_pedal_calls')==detail.get('event_count'),
                'pedal calls not equal actual backend trace throughout window')
        check(on['exact_native_records']>=400,'insufficient exact native byte/frame/time/identity checks')
        for name in ('engine_ring','ap_ring'):
            limit=(64 if approval and name=='engine_ring' else 32)*1024*1024
            check(on[name]['retained_bytes']<=limit and on[name]['byte_limit']==limit,'ring budget changed/exceeded')
            check(on[name]['capacity_drops']==on[name]['capture_failures']==0,name+' lost samples')
        check(on['whole_tick']['p99_ms']<50.,'whole tick p99 >=50 ms')
        check(on['whole_tick']['max_ms']<100.,'whole tick maximum >=100 ms')
        delta=on['whole_tick']['p99_ms']-off['whole_tick']['p99_ms']
        check(delta<=8.33,'added whole-tick p99 exceeds 8.33 ms')
        check(on['engine_flush']['p99_ms']<=16.67,'Engine flush p99 exceeds 16.67 ms')
        check(on['engine_flush']['max_ms']<50.,'Engine flush maximum >=50 ms')
        check(not on['control_thread_export_io'],'export file I/O on control thread')
        check(on['ring_lock_wait']['p99_ms']<=1. and on['ring_lock_wait']['max_ms']<=5.,'ring lock wait exceeds bound')
        runtime_parent_upper=None;runtime_family_upper=None
        if on.get('daemon_host'):
            # The external supervisor also sees the OFFLINE dossier inspector
            # after the run's original monitor has stopped. Do not call those
            # test readback allocations control/runtime diagnostic ownership.
            # Sum independent runtime-host + broker peaks conservatively,
            # without assuming they cannot overlap. Keep all raw RSS samples.
            runtime_parent_upper=on['host_local_memory']['parent_peak_rss']+on['memory']['broker_peak_rss']
            runtime_family_upper=runtime_parent_upper+on['memory']['children_combined_peak_rss']
            off_parent_upper=off['host_local_memory']['parent_peak_rss']+off['memory']['broker_peak_rss']
            peak_delta=runtime_parent_upper-off_parent_upper
            check(runtime_parent_upper<=512*1024*1024,'absolute runtime parents exceed additional-parent allowance')
            check(runtime_family_upper<=2048*1024*1024,'absolute runtime family exceeds additional-family allowance')
        else:peak_delta=on['memory']['parent_peak_rss']-off['memory']['parent_peak_rss']
        check(peak_delta<=(512 if approval else 272)*1024*1024,'parent peak RSS delta exceeds approved bound')
        check(on['memory']['children'] and max(on['memory']['children'].values())<=(1536 if approval else 512)*1024*1024,'export child exceeds approved bound or not sampled')
        if approval:
            check(on['memory']['simultaneous_children_max']==1,'more than one exporter process')
            family_delta=(runtime_family_upper if runtime_family_upper is not None else
                on['memory']['process_family_peak_rss']-off['memory']['process_family_peak_rss'])
            check(family_delta<=2048*1024*1024,'additional diagnostic family RSS exceeds 2048 MiB')
        pairs.append(dict(mode=mode,off=off,on=on,p99_delta_ms=delta,parent_peak_delta_bytes=peak_delta,
            runtime_parent_peak_upper_bytes=runtime_parent_upper,runtime_family_peak_upper_bytes=runtime_family_upper,
            rss_scope='runtime host monitor plus conservative broker/child peak sums; raw supervisor includes offline inspector'))
    representative_path=root/'representative-simple-on.json'
    representative=json.loads(representative_path.read_text(encoding='utf-8')) if representative_path.exists() else None
    if representative is not None and (not representative['post_warm_dossiers'] or
            representative['engine_ring']['capacity_drops'] or representative['engine_ring']['capture_failures'] or
            not representative['active'] or representative['fault']):
        failures.append(dict(mode=0,reason='representative traffic capture failed'))
    return dict(verdict='BLOCKED' if failures else 'READY FOR CONTROLLED CAPTURE',
        failures=failures,pairs=pairs,representative=representative,criteria_sha256=criteria_sha,
        criteria_changed=False,approved_budget=approval,
        baseline_scope_approval=scope_approval,
        baseline_scope_approval_sha256=hashlib.sha256(scope_path.read_bytes()).hexdigest() if scope_approval else None,
        baseline_completeness_scope_updated_by_explicit_approval=bool(scope_approval),
        budget_approval_sha256=hashlib.sha256(approval_path.read_bytes()).hexdigest() if approval else None,
        memory_capacity_criteria_updated_by_explicit_approval=bool(approval),
        model=True,game_verified=False,deployed=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);args=p.parse_args()
    output=args.directory/'assessment.json';assert not output.exists()
    result=assess(args.directory);output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('verdict','failures')},indent=2))
