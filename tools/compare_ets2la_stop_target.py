"""Read-only local ETS2LA Python stop reference comparison; no runtime patch."""
import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

from tests.signals.test_native_signal_direction import place
from core.longitudinal import stopping_speed_ceiling


def compare(source, workdir):
    body = source.read_text(encoding='utf-8'); tree = ast.parse(body)
    selected = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                and n.name in ('get_distance', 'calculate_traffic_light_constraint')]
    if len(selected) != 2: raise ValueError('expected ETS2LA Python methods unavailable')
    namespace = {'math': math}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), 'exec'), namespace)
    workdir.mkdir(parents=True, exist_ok=True)
    path, plan = place(workdir); record = plan['passages'][0]; first = path.points[0]
    entry_error = math.dist(record['entry_xyz'], (first.x, first.y, first.z))
    if entry_error > 1e-6: raise ValueError('different passage-entry reference')
    current_offset = record['front_allowance_m']+record['junction_standoff_m']
    rows = []
    # Original distance routine, exact placed passage endpoints. Explicit
    # straight approach poses; not recovered physical bumper positions.
    for distance in (50., 20., 10., 5.654666):
        xyz = [first.x+distance*math.sin(first.heading), first.y,
               first.z+distance*math.cos(first.heading)]
        ends = [namespace['get_distance'](None, xyz, [p.x,p.y,p.z]) for p in (path.points[0], path.points[-1])]
        ets_distance = min(ends)
        rows.append(dict(sdk_to_entry_m=distance, ets2la_nearest_endpoint='entry' if ends[0]<ends[1] else 'exit',
            ets2la_distance_minus_5_m=ets_distance-5.,
            # Preserve the Oct 12 comparison after the authorized Oct 13
            # change; do not label a freshly prepared 5 m target as 6+2 m.
            ultrapilot_entry_minus_6_plus_2_m=distance-8.,
            ultrapilot_current_remaining_m=distance-current_offset,
            endpoint_difference_m=ets_distance-distance,
            physical_line_or_bumper_measured=False))
    constraints = []
    for speed in (20./3.6,35./3.6,50./3.6,.5):
        self = SimpleNamespace(speed=speed, comfort_decel=-3., emergency_decel=-6., add_ar_text=lambda _:None)
        constraints.append(dict(speed_mps=speed, sdk_to_entry_m=20.,
            ets2la_target_acceleration_mps2=namespace['calculate_traffic_light_constraint'](self,20.),
            ultrapilot_target_speed_ceiling_mps=stopping_speed_ceiling(20.-8.,speed),
            ultrapilot_current_speed_ceiling_mps=stopping_speed_ceiling(20.-current_offset,speed),
            warning='Different control quantities, not directly comparable pedal values or physical trajectories.'))
    return dict(ets2la_source=str(source),ets2la_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        fixture='tests/fixtures/oct10-signal-place.json', passage=record['passage_key'],
        entry_xyz=record['entry_xyz'], entry_alignment_error_m=entry_error,
        ultrapilot_baseline_offset_m=8.,ultrapilot_current_offset_m=current_offset,
        modeled_straight_poses=rows,constraints=constraints,
        result=f'For these same-entry approaches, ETS2LA reserve is 5 m versus the UltraPilot 8 m baseline; current prepared offset is {current_offset:g} m. No painted line or truck front is measured.',
        runtime_changed=False,game_verified=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path(r'C:\ETS2LA\app\Plugins\AdaptiveCruiseControl\main.py'))
    parser.add_argument('--workdir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); result=compare(args.source,args.workdir)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))
