"""Run counterexamples against preserved/deployed source in memory.

Never resets a checkout or writes an installed file. The default baseline run
expects three failures; --busy-only expects the fourth counterexample alone.
The ordinary targeted pytest run uses the candidate.
"""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import types
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.navigation.road_network import RoadNetwork
from plugins.map.main import Plugin as Map
import core.longitudinal as longitudinal


def load(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), module.__dict__)
    return module


def main(args):
    import pytest
    network_path = args.baseline/'core/navigation/road_network.py'
    command_path = args.baseline/'core/longitudinal.py'
    old_network = load(network_path, 'oct9_counterexample_network').RoadNetwork
    old_commands = load(command_path, 'oct9_counterexample_longitudinal')
    tests = ['test_map_does_not_deserialize_its_own_unchanged_geometry_each_tick',
        'test_warm_immutable_prefab_topology_does_not_repeat_search_on_map_control_ticks',
        'test_near_expiry_curve_refresh_survives_ipc_without_reusing_propulsion']
    captured = io.StringIO()
    files = (network_path, command_path)
    with contextlib.ExitStack() as stack:
        replacements = (
            (RoadNetwork, '_prefab_connector_options', old_network._prefab_connector_options),
            (RoadNetwork, '_prefab_parallel_lane_options', old_network._prefab_parallel_lane_options),
            (Map, '_read_control_lane_snapshot', lambda self: self.sdk.get('lane_trajectory', {}) or {}),
            (longitudinal, 'refresh_handoff', old_commands.refresh_handoff),
            (longitudinal, 'curve_input', old_commands.curve_input))
        if args.busy_only:
            map_path=args.baseline/'plugins/map/main.py'
            old_map=load(map_path, 'oct9_counterexample_map').Plugin
            replacements=((Map, 'on_tick', old_map.on_tick),)
            tests=['test_busy_evidence_worker_does_not_fetch_discarded_inputs_after_publication']
            files=(map_path,)
        for cls, attribute, replacement in replacements:
            stack.enter_context(patch.object(cls, attribute, replacement))
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            result = pytest.main(['-q', *[f'tests/test_oct9_packet_refresh.py::{name}' for name in tests]])
    result = dict(exit_code=int(result), tests=tests, transcript=captured.getvalue(),
        baseline_files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        scope=('Only deployed Map.on_tick restored in memory with actual one-slot pending evidence worker'
            if args.busy_only else 'Only deployed topology walkers, owned-snapshot reads and shared refresh functions restored in memory')+'; not a historical game replay.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(captured.getvalue())
    assert result['exit_code'] == 1 and f'{len(tests)} failed' in result['transcript'], result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--busy-only',action='store_true')
    args=parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT):parser.error('Output must stay in workspace')
    main(args)
