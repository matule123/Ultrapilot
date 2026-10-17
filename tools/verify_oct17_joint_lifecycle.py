"""Paired deployed/candidate production signal pipeline and explicit plant."""
import argparse
import ast
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import zipfile

from tools.verify_oct17_native_records import ROOT

OUT=ROOT/'docs/steering-audit/oct17-joint-lifecycle'


@contextmanager
def baseline():
    import core.longitudinal as module
    import plugins.acc.main as acc_module
    frozen=json.loads((ROOT/'tests/fixtures/oct17-signal-profile-original.json').read_text())
    def load(name,globals_):
        value=frozen['functions'][name]
        assert hashlib.sha256(value['source'].encode()).hexdigest()==value['sha256']
        env={};exec(compile(value['source'],'entry/'+name,'exec'),globals_,env)
        return env
    env=load('core/longitudinal.py',vars(module))
    acc_env=load('plugins/acc/main.py',vars(acc_module))
    with patch.object(module,'signal_stop_speed_limit',env['signal_stop_speed_limit']),patch.object(acc_module.Plugin,'on_tick',acc_env['on_tick']):yield


def run(directory,mode,speed,delay,before,*,phase_program=None,duration_s=60.):
    from contextlib import nullcontext
    from tools import run_prefab_signal_bench as bench
    from tools.audit_oct10_native_signal import placed_route
    from tools.run_oct10_signal_timing_bench import snapshot
    from plugins.drivepolicy.main import Plugin as Policy
    with baseline() if before else nullcontext():
        original=Policy.on_tick;count=[0]
        def independent(self,dt):
            count[0]+=1
            if count[0]%3==1:original(self,dt)
        with patch.object(Policy,'on_tick',independent),patch.object(bench,'plan_for',side_effect=lambda net,path:placed_route(directory)[2]):
            data=bench.run(directory,mode=mode,speed_kmh=speed,approach=100.,jitter=True,
                path_factory=placed_route,snapshot_factory=snapshot,observer_y=6.90234375,
                brake_response_s=.35 if delay==.12 else .6,input_delay_s=delay,mass_ratio=1.4,
                duration_limit_s=duration_s,phase_program=phase_program,
                allow_rejection=True,coherent_processing_clock=True)
    (directory/f'{mode}-{speed}-{delay}-{before}.json').write_text(json.dumps(data),encoding='utf-8')
    return {k:v for k,v in data.items() if k not in ('rows','writes','captures')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',type=int,choices=(0,3),default=0)
    parser.add_argument('--label',default='paired')
    parser.add_argument('--performance',action='store_true')
    args=parser.parse_args();directory=OUT/f'{args.label}-{args.mode}';directory.mkdir(exist_ok=True)
    if args.performance:
        import core.navigation.longitudinal_diagnostics as module
        from contextlib import ExitStack
        from tools.benchmark_oct15_crossing_dev_hud import run as measure
        with zipfile.ZipFile(OUT/'entry-runtime.zip') as archive:
            tree=ast.parse(archive.read('core/navigation/longitudinal_diagnostics.py').decode('utf-8-sig'))
        originals={}
        for name in ('_decision_summary','local_source_snapshot','source_snapshot'):
            node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
            env={};exec(compile(ast.Module(body=[node],type_ignores=[]),'entry/diagnostics.py','exec'),vars(module),env)
            originals[name]=env[name]
        fields=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='HISTORY_FIELDS' for t in n.targets))
        originals['HISTORY_FIELDS']=ast.literal_eval(fields.value)
        results=[]
        for repeat in range(3):
            row=dict(repeat=repeat,mode=args.mode)
            for name,before in (('before',True),('after',False)):
                with ExitStack() as stack:
                    if before:
                        for key,value in originals.items():stack.enter_context(patch.object(module,key,value))
                    row[name]=measure(False,args.mode,120)
            assert row['before']['control_output_sha256']==row['after']['control_output_sha256']
            assert row['before']['source_reads']==row['after']['source_reads']
            assert row['before']['faults'] is row['after']['faults'] is None
            results.append(row)
        (directory/'performance.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        print(json.dumps([{k:({m:v[m] for m in ('wall_ms','control_thread_cpu_ms','gc_ms')} if k in ('before','after') else v)
            for k,v in row.items()} for row in results],indent=2));return
    results=[]
    for delay in (.12,.35):
        for speed in (20.,35.,50.):
            row=dict(mode=args.mode,speed_kmh=speed,delay_s=delay)
            for name,before in (('before',True),('candidate',False)):
                row[name]=run(directory,args.mode,speed,delay,before)
            results.append(row)
            print(json.dumps(row),flush=True)
    (directory/'results.json').write_text(json.dumps(dict(cases=results,
        baseline_sha256=hashlib.sha256((OUT/'entry-runtime.zip').read_bytes()).hexdigest(),
        criteria=dict(no_target_overrun=True,no_pedal_overlap=True,stop_gap_m=[0,1.5],
            automatic_green_restart=True,unchanged_emergency_and_freshness=True,
            reversal_count_not_worse=True,maximum_deceleration_not_worse=True),
        limitation='Same explicit existing uncalibrated plant, no proof of ETS2 input consumption'),indent=2),encoding='utf-8')


if __name__=='__main__':main()
