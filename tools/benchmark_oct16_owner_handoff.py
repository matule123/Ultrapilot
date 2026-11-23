"""Paired HEAD/candidate actual pipeline; synthetic native input, no game."""
import argparse
import ast
from contextlib import contextmanager,ExitStack
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from tools import benchmark_oct15_crossing_dev_hud as bench


@contextmanager
def baseline(ref='5f96e07'):
    import core.acc_following as following
    import core.engine as engine
    import core.traffic_dev_hud as hud
    import plugins.acc.main as acc
    def nodes(path,kind,names):
        raw=subprocess.check_output(['git','show',ref+':'+path]).decode()
        return [n for n in ast.parse(raw).body if isinstance(n,kind) and n.name in names]
    with ExitStack() as stack:
        for path,module,names in (
            ('core/acc_following.py',following,('RouteLeadSelector',)),
            ('core/traffic_dev_hud.py',hud,('DevHUDFeed',))):
            namespace=dict(vars(module))
            exec(compile(ast.Module(body=nodes(path,ast.ClassDef,names),type_ignores=[]),path,'exec'),namespace)
            for name in names:stack.enter_context(patch.object(module,name,namespace[name]))
        for path,module,clsname,names in (
            ('core/engine.py',engine,'UltraPilotEngine',('_route_lead_observation','_traffic_control_observation')),
            ('plugins/acc/main.py',acc,'Plugin',('on_start','on_stop','on_tick','_publish_pedals'))):
            cls=nodes(path,ast.ClassDef,(clsname,))[0]
            for method in cls.body:
                if isinstance(method,ast.FunctionDef) and method.name in names:
                    namespace=dict(vars(module))
                    exec(compile(ast.Module(body=[method],type_ignores=[]),path,'exec'),namespace)
                    stack.enter_context(patch.object(getattr(module,clsname),method.name,namespace[method.name]))
        yield


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--ticks',type=int,default=160);p.add_argument('--repeat',type=int,default=3)
    p.add_argument('--baseline',default='5f96e07')
    p.add_argument('--reproduce-baseline',action='store_true');a=p.parse_args()
    if a.reproduce_baseline:
        import pytest
        with baseline(a.baseline):
            raise SystemExit(pytest.main(['tests/traffic/test_brake_owner_handoff.py','-q','-k',
                'current_crossing_continuity or original_owner_survives']))
    from tools.prepare_oct16_crossing_hud import hashes
    before_hashes=hashes()
    rows=[]
    for repeat in range(a.repeat):
        for mode in (0,3):
            pair={}
            for label,old in (('baseline',True),('candidate',False)):
                if old:
                    with baseline(a.baseline):pair[label]={str(flag):bench.run(flag,mode,a.ticks) for flag in (False,True)}
                else:pair[label]={str(flag):bench.run(flag,mode,a.ticks) for flag in (False,True)}
            for label in pair:
                assert pair[label]['False']['control_output_sha256']==pair[label]['True']['control_output_sha256']
                assert pair[label]['False']['source_reads']==pair[label]['True']['source_reads']
                assert pair[label]['False']['faults'] is pair[label]['True']['faults'] is None
            assert pair['baseline']['False']['control_output_sha256']==pair['candidate']['False']['control_output_sha256']
            rows.append(dict(repeat=repeat,mode=mode,**pair))
    from tools.benchmark_oct16_dense_hud import native_dense_snapshot
    snapshot=native_dense_snapshot()
    # Distinct owned scene objects are counted once, including history. Test
    # mock call histories, Controller caches and worker/OS memory are excluded.
    if hashes()!=before_hashes:raise ValueError('Runtime changed during paired benchmark')
    result=dict(basis=__doc__,runtime_sha256=before_hashes,baseline=a.baseline+' read-only AST methods/classes',rows=rows,
        snapshot_deep_bytes=bench.deep_size(snapshot),snapshot=snapshot,
        game_verified=False,limits='two geometry frames total incl history; 64 KiB total receipts incl history/fault')
    a.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows','snapshot')},indent=2))
    for row in rows:
        print(row['repeat'],row['mode'],{k:{flag:v['wall_ms'] for flag,v in row[k].items()}
            for k in ('baseline','candidate')},flush=True)


if __name__=='__main__':main()
