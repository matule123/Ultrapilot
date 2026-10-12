"""Read-only source lineage; snapshot exports stay in the workspace, never the old checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FILES = ('plugins/map/main.py','core/navigation/road_network.py','core/ipc/shared_state.py',
         'core/plugin_manager.py','plugins/autopilot/main.py','plugins/acc/main.py',
         'plugins/drivepolicy/main.py','core/engine.py','core/longitudinal.py')


def git(*args, cwd=ROOT):
    return subprocess.check_output(['git',*args],cwd=cwd,stderr=subprocess.PIPE)


def normalize(value):
    return value.replace(b'\r\n',b'\n')


def main(args):
    revision=git('rev-parse','221cc90').decode().strip()
    assert git('rev-parse','HEAD',cwd=args.old).decode().strip()==revision
    assert not git('diff','--name-only','HEAD',cwd=args.old).strip(), 'Old tracked worktree differs'
    rows=[]
    for name in FILES:
        try: historic=git('show',f'221cc90:{name}')
        except subprocess.CalledProcessError: historic=None
        old=args.old/name
        current=(ROOT/name).read_bytes()
        rows.append(dict(path=name, existed_at_221cc90=historic is not None,
            old_checkout_matches_git=(normalize(old.read_bytes())==normalize(historic)
                if historic is not None and old.is_file() else None),
            historic_sha256=hashlib.sha256(normalize(historic)).hexdigest() if historic else None,
            candidate_sha256=hashlib.sha256(normalize(current)).hexdigest()))
    searches=(('extra SDK/localization refresh','_refresh_steering_observation', 'plugins/map/main.py'),
              ('evidence arguments on Map tick','evidence_worker.offer', 'plugins/map/main.py'),
              ('snapshot transport copy cache','LaneSnapshotReader','core/ipc/shared_state.py'),
              ('final Engine GPS rejection','_gps_output_packet_rejection_reason','core/engine.py'),
              ('bounded longitudinal refresh','def refresh_handoff','core/longitudinal.py'),
              ('parallel prefab DFS','_prefab_parallel_lane_options','core/navigation/road_network.py'),
              ('Map remainder-only scheduling','if plugin_name == "map"','core/plugin_manager.py'))
    lineage=[dict(feature=label,path=path,git_pickaxe=git('log','-S',term,
        '--format=%H %ad %s','--date=iso','--',path).decode().splitlines()) for label,term,path in searches]
    destination=args.output.parent/'historic-map-221cc90'
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'main.py').write_bytes(git('show','221cc90:plugins/map/main.py'))
    # Explicit compatibility boundary: historical Map logic, deployed modern
    # network/schema/SharedState and current producers. Not the old full app.
    network=(ROOT/'docs/steering-audit/oct9-freshness/before/road_network.py').read_bytes()
    (destination/'road_network.py').write_bytes(network)
    result=dict(historic_commit=revision,head=git('rev-parse','HEAD').decode().strip(),
        old_status=git('status','--short',cwd=args.old).decode(),files=rows,lineage=lineage,
        historical_probe_boundary='221cc90 Map only; modern deployed schema-15 RoadNetwork, current IPC/producers. Not a 221cc90 installation or physics result.',
        historic_probe_directory=str(destination))
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('files','lineage')},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--old',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if not args.output.resolve().is_relative_to(ROOT):p.error('Output must stay in workspace')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    main(args)
