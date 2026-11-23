"""Frozen deployed-method comparison through real native reader and writer.

No game, live SDK or deployment. The vehicle plant is the existing explicitly
uncalibrated run_prefab_signal_bench model. Baseline is the immutable entry ZIP,
not a guessed Git commit for the installed dirty build.
"""
import argparse
import ast
from contextlib import ExitStack,contextmanager
import hashlib
import importlib
import json
from pathlib import Path
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
ENTRY=ROOT/'docs/steering-audit/oct16-green-restart/entry-runtime.zip'


@contextmanager
def deployed_methods():
    targets={
        'core.longitudinal':(None,('stopping_brake_continuity_required',)),
        'core.service_brake_hold':(None,('after_write','real_auto_wait_allowed')),
        'core.transmission_mode':(None,('simple_auto_forward_transition',)),
        'core.navigation.longitudinal_diagnostics':(None,('bounded_input','hold_snapshot')),
        'plugins.acc.main':('Plugin',('on_tick','_reset_control')),
        'core.engine':('UltraPilotEngine',('_flush_auto_drive_engagement','_flush_controls_unlocked')),
    }
    with ExitStack() as stack,zipfile.ZipFile(ENTRY) as archive:
        for name,(owner,names) in targets.items():
            module=importlib.import_module(name)
            source=archive.read(name.replace('.','/')+'.py').decode('utf-8-sig')
            tree=ast.parse(source)
            body=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==owner).body if owner else tree.body
            for symbol in names:
                node=next(n for n in body if isinstance(n,ast.FunctionDef) and n.name==symbol)
                namespace={}
                exec(compile(ast.Module(body=[node],type_ignores=[]),'deployed-entry/'+name,'exec'),vars(module),namespace)
                original=namespace[symbol]
                stack.enter_context(patch.object(getattr(module,owner) if owner else module,symbol,original))
                if name=='core.transmission_mode':
                    for consumer in ('core.engine','plugins.autopilot.main'):
                        linked=importlib.import_module(consumer)
                        if hasattr(linked,symbol):stack.enter_context(patch.object(linked,symbol,original))
        yield


def run(directory,before,mode,speed,slow_policy):
    from tools import run_prefab_signal_bench as bench
    from tools.audit_oct10_native_signal import placed_route
    from tools.run_oct10_signal_timing_bench import snapshot
    from plugins.drivepolicy.main import Plugin as Policy
    with ExitStack() as stack:
        if before:stack.enter_context(deployed_methods())
        stack.enter_context(patch.object(bench,'plan_for',side_effect=lambda net,path:placed_route(directory)[2]))
        policy_tick=Policy.on_tick;count=[0]
        def independent(self,dt):
            count[0]+=1
            if count[0]%3==1 or not slow_policy:policy_tick(self,dt)
        stack.enter_context(patch.object(Policy,'on_tick',independent))
        result=bench.run(directory,mode=mode,speed_kmh=speed,approach=100.,jitter=True,
            path_factory=placed_route,snapshot_factory=snapshot,observer_y=6.90234375,
            brake_response_s=.35,input_delay_s=.12,mass_ratio=1.4,
            duration_limit_s=45.,allow_rejection=True)
    path=directory/f'{speed:g}-{mode}-{slow_policy}-{before}.json'
    path.write_text(json.dumps(result),encoding='utf-8')
    return {k:v for k,v in result.items() if k not in ('rows','writes','captures')}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reproduce',action='store_true')
    p.add_argument('--performance',action='store_true')
    p.add_argument('--repeats',type=int,choices=(1,2,3),default=3)
    p.add_argument('--retained-memory',action='store_true')
    p.add_argument('--workdir',type=Path,required=True)
    a=p.parse_args();a.workdir.mkdir(parents=True,exist_ok=True)
    if a.reproduce:
        import pytest
        with deployed_methods():
            raise SystemExit(pytest.main(['tests/signals/test_green_restart.py','-q','-k',
                'slower_policy or qualified_green or late_braking']))
    if a.retained_memory:
        from tests.test_activation_observation_binding import flow
        from tests.signals.test_signal_timing import timing_flow
        from tools.benchmark_oct15_crossing_dev_hud import deep_size
        results=[]
        for mode in (0,3):
            fixture=flow.__wrapped__();values=next(fixture)
            try:
                state,step=timing_flow(values,a.workdir,mode)
                shared,truck,engine,ap,tick,n,clock,writes,collector=state
                for generation,color,speed,gear,progress in (
                    (30,'red',10.,4,0.),(31,'red',.3,4,3.),(32,'red',.3,4,3.),
                    (33,'green',0.,0,3.),(34,'green',0.,0,3.),(35,'green',0.,0,3.),
                    (36,'green',.4,4,3.1),(37,'green',.4,4,3.2)):
                    step(generation,color,speed=speed,gear=gear,progress=progress)
                    journal=engine.controller._pedal_journal
                    saved=journal.snapshot(include_history=True)
                    owned=dict(events=journal._events,sizes=journal._sizes,source_uses=journal._source_uses,
                        history=vars(journal._history),pending_event=journal._pending_event)
                    results.append(dict(mode=mode,generation=generation,
                        hold_phase=(engine._service_brake_hold or {}).get('phase'),
                        hold_deep_bytes=deep_size(engine._service_brake_hold),
                        engagement_deep_bytes=deep_size(engine._drive_engagement),
                        journal_owned_containers_deep_bytes=deep_size(owned),
                        detail_accounted_bytes=saved['retained_bytes'],
                        history_accounted_bytes=saved['decision_history']['retained_bytes']))
            finally:fixture.close()
        output=dict(rows=results,excluded='Mock call histories, collector.samples assertion list, controller caches, workers, Python allocator/OS and process RSS; short lifecycle, not a full 30s retention stress')
        (a.workdir/'retained-memory.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
        print(json.dumps(output,indent=2));return
    if a.performance:
        from tools import benchmark_oct15_crossing_dev_hud as bench
        results=[]
        for repeat in range(a.repeats):
            for mode in (0,3):
                row=dict(repeat=repeat,mode=mode)
                for label,before in (('before',True),('after',False)):
                    with ExitStack() as stack:
                        if before:stack.enter_context(deployed_methods())
                        row[label]={str(flag):bench.run(flag,mode,120) for flag in (False,True)}
                baseline=row['before']['False']
                for stage in ('before','after'):
                    for data in row[stage].values():
                        assert data['control_output_sha256']==baseline['control_output_sha256']
                        assert data['source_reads']==baseline['source_reads']
                        assert data['faults'] is None
                results.append(row)
                print(repeat,mode,{label:{flag:v['wall_ms'] for flag,v in row[label].items()}
                    for label in ('before','after')},flush=True)
        (a.workdir/'performance.json').write_text(json.dumps(dict(rows=results,
            limitation='Actual producer/policy/ACC/AP/Controller pipeline with copy-on-read test IPC, not OS Manager or ETS2'),indent=2),encoding='utf-8')
        return
    results={}
    for mode in (0,3):
        for speed in (20.,35.,50.):
            name=f'{speed:g}-{mode}'
            pair={label:run(a.workdir,old,mode,speed,True)
                  for label,old in (('before',True),('after',False))}
            results[name]=pair
            print(name,json.dumps(pair),flush=True)
    output=dict(baseline_zip_sha256=hashlib.sha256(ENTRY.read_bytes()).hexdigest(),
        criteria=dict(existing_reference_stop_zone_m=[0.,1.5],no_red_overrun=True,
            no_positive_pedal_overlap=True,green_restart_without_n=True,
            no_zero_brake_during_confirmed_red_hold=True),
        plant='Existing explicit, uncalibrated plant; .35s actuator, .12s delay, mass ratio 1.4; not ETS2',
        policy_cadence='Every third independent tick; jitter .033/.05/.08s; original source clocks',cases=results)
    (a.workdir/'comparison.json').write_text(json.dumps(output,indent=2),encoding='utf-8')


if __name__=='__main__':main()
