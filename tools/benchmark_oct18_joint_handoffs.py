"""Paired entry/candidate operations. No live scheduling or game proof."""
import argparse
import ast
from contextlib import contextmanager
import json
import logging
import multiprocessing as mp
from pathlib import Path
import time
import zipfile

from pytest import MonkeyPatch
from tools.benchmark_oct15_crossing_dev_hud import run, percentiles

OUT=Path(__file__).resolve().parents[1]/'docs/steering-audit/oct18-joint-handoffs'


@contextmanager
def entry_runtime(enabled):
    import core.engine as engine
    import core.longitudinal as longitudinal
    import core.transmission_mode as transmission
    import plugins.autopilot.main as autopilot
    import plugins.acc.main as acc
    import plugins.drivepolicy.main as policy
    with MonkeyPatch.context() as patches:
        if enabled:
            with zipfile.ZipFile(OUT/'entry-runtime.zip') as archive:
                for module,names in ((longitudinal,('publish','finalize')),
                                     (transmission,('simple_auto_forward_transition',))):
                    source=archive.read(module.__name__.replace('.','/')+'.py').decode('utf-8-sig')
                    for node in ast.parse(source).body:
                        if isinstance(node,ast.FunctionDef) and node.name in names:
                            namespace=dict(vars(module))
                            exec(compile(ast.Module(body=[node],type_ignores=[]),'entry/'+module.__name__,'exec'),namespace)
                            patches.setattr(module,node.name,namespace[node.name])
                cls=next(n for n in ast.parse(archive.read('core/engine.py').decode('utf-8-sig')).body
                    if isinstance(n,ast.ClassDef) and n.name=='UltraPilotEngine')
                for node in cls.body:
                    if isinstance(node,ast.FunctionDef) and node.name in (
                            '_traffic_control_observation','_resume_signal_wait','_clear_simple_auto_forward_history'):
                        namespace=dict(vars(engine))
                        exec(compile(ast.Module(body=[node],type_ignores=[]),'entry/Engine','exec'),namespace)
                        patches.setattr(engine.UltraPilotEngine,node.name,namespace[node.name])
            patches.setattr(engine,'simple_auto_forward_transition',transmission.simple_auto_forward_transition)
            patches.setattr(autopilot,'simple_auto_forward_transition',transmission.simple_auto_forward_transition)
            for module in (acc,policy):patches.setattr(module,'publish',longitudinal.publish)
        yield


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--ticks',type=int,default=100)
    parser.add_argument('--cadence-seconds',type=float,default=0.,
        help='Independent Map/traffic/Policy/ACC/AP/Engine periods, copied RPC delays, 35 actors and bounded journal')
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Never overwrite measurements')
    logging.disable(logging.WARNING)
    if args.cadence_seconds:
        from tools.benchmark_oct17_systemic import run as cadence
        rows=[]
        for entry in (True,False):
            with entry_runtime(entry):
                for mode in (0,3):
                    row=dict(entry=entry,**cadence(mode,False,args.cadence_seconds))
                    rows.append(row);print(json.dumps(row),flush=True)
        args.output.write_text(json.dumps(dict(rows=rows,
            historical_actor_inputs_reconstructed=False,game_verified=False),indent=2),encoding='utf-8')
        assert all(not r['fault'] and r['over_500ms_writes']==r['negative_lease_writes']==0 for r in rows)
        return
    rows=[]
    for repeat in range(3):
        for entry in ((True,False) if repeat%2==0 else (False,True)):
            with entry_runtime(entry):
                for mode in (0,3):
                    row=dict(entry=entry,repeat=repeat,mode=mode,**run(False,mode,args.ticks))
                    rows.append(row)
                    print(json.dumps({k:v for k,v in row.items() if k not in ('source_reads','presentation_reads')}),flush=True)
    for mode in (0,3):
        selected=[r for r in rows if r['mode']==mode]
        assert len({r['control_output_sha256'] for r in selected})==1
        assert all(r['faults'] is None for r in selected)
    # Separate actual Windows Manager RPC. Does not claim whole-tick latency.
    from core.ipc.shared_state import ControlStateManager, SharedState
    from core.longitudinal import context, packet
    from tests.test_activation_observation_binding import flow
    generator=flow.__wrapped__();state,truck,*rest=next(generator)
    costs={}
    try:
        with mp.Manager() as plain, ControlStateManager() as guarded:
            for label,raw in (('entry_single_set',plain.dict(state.values)),('guarded_compare_commit',guarded.control_dict(state.values))):
                view=SharedState(raw)
                value=packet(view,truck,'acc',binding=context(view),throttle=0.,brake=0.,emergency=False)
                samples=[]
                for _ in range(500):
                    start=time.perf_counter()
                    if label=='entry_single_set':raw['longitudinal_acc']=value
                    else:assert view.publish_longitudinal('longitudinal_acc',value)
                    samples.append((time.perf_counter()-start)*1000)
                costs[label]=dict(cold_ms=samples[0],warm_ms=percentiles(samples[10:]))
    finally:generator.close()
    result=dict(rows=rows,manager_publication_ms=costs,
        identical_model_outputs=True,
        limitation='Synthetic source/route, fixed poses, mocked scheduler; full ticks use copied in-process state. Manager numbers measure only actual publication RPC. No historical pause attribution or ETS2 consumption proof.')
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(costs),flush=True)


if __name__=='__main__':
    mp.freeze_support();main()
