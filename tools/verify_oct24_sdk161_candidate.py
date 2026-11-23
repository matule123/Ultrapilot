"""Compile/run own-process candidate tests; compare saved native data to map."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.verify_oct17_native_records import VCVARS,probe
AUDIT=ROOT/'docs/steering-audit/oct22-sdk161'
sys.path.insert(0,str(ROOT/'docs/steering-audit/mapconverter-159-work'))
from ultrapilot_map_converter.validation import iter_json_array

DATASET=Path(r'C:\Users\PC\Documents\GitHub\UltraPilot-MapConverter\build\UltraPilot-MapConverter-161-Progress-127-20261021\map-cache\promods-2.84')


def compare_map(layout,dataset):
    hypotheses=layout['snapshot']['hypotheses']
    native={format(row['uid'],'x'):row for row in hypotheses['prefabs']['items']}
    proof=[]
    for row in iter_json_array(dataset/'europe-prefabs.json'):
        if row['uid'] not in native:continue
        live=native[row['uid']];nodes=[format(n,'x') for n in live['nodes'] if n]
        proof.append(dict(uid=row['uid'],node_order_matches=nodes==row['nodeUids'],
            native_origin_118=live['origin_candidates'][0],native_origin_120=live['origin_candidates'][1],
            dataset_origin=row['originNodeIndex']))
    if len(proof)!=len(native) or not all(p['node_order_matches'] and p['native_origin_120']==p['dataset_origin'] for p in proof):
        raise ValueError('Native prefab ownership does not match dataset')
    wanted={format(row['uid'],'x'):row for row in hypotheses['gps']['first_items']};route=[]
    for row in iter_json_array(dataset/'europe-nodes.json'):
        if row['uid'] not in wanted:continue
        raw=wanted[row['uid']]['node_coords'];native_xyz=[raw[0]/256,raw[1]/256,raw[2]/256]
        mapped_xyz=[row['x'],row['z'],row['y']]
        route.append(dict(uid=row['uid'],native_world=native_xyz,dataset_world=mapped_xyz,
            error_m=math.dist(native_xyz,mapped_xyz)))
    if len(route)!=len(wanted) or any(row['error_m']>.01 for row in route):raise ValueError('Native GPS nodes do not match dataset')
    return dict(prefabs=proof,gps_nodes=route,all_sampled_match=True,
        full_world_verified=False,production_ready=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--dll-name',choices=('UltraPilot161ReadCandidate.dll','ets2la_plugin.dll'),
        default='UltraPilot161ReadCandidate.dll')
    args=parser.parse_args();candidate=args.candidate.resolve();dll_name=args.dll_name
    if candidate.parent!=AUDIT:raise ValueError('Only dedicated candidate is allowed')
    receipt=json.loads((candidate/'build-receipt.json').read_text())
    for name,digest in receipt['files'].items():
        if hashlib.sha256((candidate/name).read_bytes()).hexdigest()!=digest:raise ValueError('Candidate changed: '+name)
    output=candidate/'verification'
    output.mkdir(exist_ok=False)
    fmt=ROOT/'docs/steering-audit/signal-plugin-20261003/fmt'
    args=['cl','/nologo','/O2','/MT','/std:c++17','/EHsc','/utf-8','/DFMT_HEADER_ONLY',
        '/I'+str(candidate/'src'),'/I'+str(candidate/'vendor/scs_sdk/include'),'/I'+str(fmt/'include'),
        str(ROOT/'tools/sdk161_probe/test_candidate.cpp'),'/Fe:'+str(output/'candidate-host.exe')]
    command=output/'compile-host.cmd'
    command.write_text('@echo off\n'+f'call "{VCVARS}" >nul\nif errorlevel 1 exit /b 1\n'
        +subprocess.list2cmdline(args)+'\nexit /b %errorlevel%\n',encoding='utf-8')
    built=subprocess.run(['cmd','/d','/c',str(command)],cwd=output,capture_output=True)
    (output/'compile-host.log').write_bytes(built.stdout+built.stderr)
    if built.returncode:raise RuntimeError((built.stdout+built.stderr).decode(errors='replace'))
    native=subprocess.run([str(output/'candidate-host.exe'),str(candidate/dll_name)],
        capture_output=True,text=True,timeout=20)
    (output/'native-host.log').write_text(native.stdout+native.stderr,encoding='utf-8')
    if native.returncode:raise RuntimeError('Native host failed: '+str(native.returncode)+' '+native.stdout+native.stderr)
    probe(candidate,output/'parked-acquisition')
    layout_path=AUDIT/'layout-36720-1792779669310582700.json'
    result=dict(native_host=native.stdout.strip(),candidate_dll_sha256=receipt['dll_sha256'],
        source_layout_sha256=hashlib.sha256(layout_path.read_bytes()).hexdigest(),
        map_comparison=compare_map(json.loads(layout_path.read_text()),DATASET),
        deployed=False,game_verified=False,production_ready=False)
    (output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
