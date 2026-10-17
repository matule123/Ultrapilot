"""Reproducible private copy of the pinned native producer; NEVER installs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from tools.verify_oct17_native_records import BASE,ROOT,VCVARS,probe
from tools.build_signal_plugin import replace_once


def prepare(output):
    output=output.resolve()
    if not output.is_relative_to(ROOT/'docs/steering-audit/oct17-joint-lifecycle') or output.exists():
        raise ValueError('Use a NEW dedicated oct17 audit output directory')
    original=json.loads((BASE/'build-receipt.json').read_text())
    for name,digest in original['files'].items():
        if hashlib.sha256((BASE/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Native baseline source receipt mismatch: '+name)
    shutil.copytree(BASE,output,ignore=shutil.ignore_patterns('*.obj','*.lib','*.exp','*.dll','*.pdb','build-receipt.json'))
    source=output/'src/processing/traffic.cpp'
    replace_once(source,'slave_trailer->placement.get_distance_to(this->truck_pos),\n                        traffic_actor',
                       'slave_trailer->placement.get_distance_to(this->truck_pos),\n                        slave_trailer')
    replace_once(source,'        std::array<ParkedVehicle, 40> parked_vehicles_data = { 0 };',
        '        std::array<ParkedVehicle, 40> parked_vehicles_data = { 0 };\n'
        '        std::array<const prism::traffic_actor_t*, 40> emitted{};')
    replace_once(source,'            const auto position = get_center_coords(actor_data.traffic_actor->placement, actor_data.traffic_actor->aabox);',
        '            // Deduplicate only the identical native pointer before capacity truncation.\n'
        '            // Distinct pointers with equal positions/IDs are never merged.\n'
        '            if (std::find(emitted.begin(), emitted.begin()+count, actor_data.traffic_actor) != emitted.begin()+count) continue;\n'
        '            emitted[count] = actor_data.traffic_actor;\n'
        '            const auto position = get_center_coords(actor_data.traffic_actor->placement, actor_data.traffic_actor->aabox);')
    replace_once(output/'src/version.hpp','1.59.4-up-traffic-timed','1.59.5-up-parked-records')
    fmt=ROOT/'docs/steering-audit/signal-plugin-20261003/fmt'
    inputs=json.loads((ROOT/'tools/signal_plugin/inputs.json').read_text())
    for name,digest in inputs['fmt'].items():
        assert hashlib.sha256((fmt/name).read_bytes()).hexdigest()==digest
    sources=('core.cpp','main.cpp','memory/memory_utils.shared.cpp','memory/virtual/memory_handler.cpp',
        'prism/common.cpp','prism/game_actor.cpp','prism/camera/camera_manager.cpp',
        'prism/controllers/base_ctrl.cpp','prism/controllers/game_ctrl.cpp',
        'prism/navigation/gps_manager.cpp','prism/traffic/game_traffic.cpp',
        'prism/vehicles/game_trailer_actor.cpp','prism/vehicles/game_physics_vehicle.cpp',
        'prism/vehicles/vehicle_shared.cpp','processing/traffic.cpp','memory/memory_utils.win32.cpp')
    args=['cl','/nologo','/LD','/O2','/MT','/std:c++17','/EHsc','/utf-8','/Brepro',
        '/experimental:deterministic','/pathmap:'+str(output)+'=ETS2LA_SOURCE',
        '/DFMT_HEADER_ONLY','/DETS2LA_PLUGIN_EXPORTS','/DUNICODE','/D_UNICODE','/DUP_SIGNAL_SCOPE_V3',
        '/I'+str(output/'src'),'/I'+str(output/'vendor/scs_sdk/include'),'/I'+str(fmt/'include'),
        *[str(output/'src'/s) for s in sources],'/link','/DEF:'+str(output/'ets2la_plugin.def'),
        '/Brepro','/OUT:'+str(output/'ets2la_plugin.dll')]
    command=output/'compile.cmd'
    command.write_text('@echo off\n'+f'call "{VCVARS}" >nul\nif errorlevel 1 exit /b 1\n'
        +subprocess.list2cmdline(args)+'\nexit /b %errorlevel%\n',encoding='utf-8')
    build=subprocess.run(['cmd','/d','/c',str(command)],cwd=output,capture_output=True)
    (output/'compile.log').write_bytes(build.stdout+build.stderr)
    if build.returncode:raise RuntimeError((build.stdout+build.stderr).decode(errors='replace'))
    receipt=dict(source_commit=original['source_commit'],version='1.59.5-up-parked-records',
        schema=3,traffic_schema=1,abi_changed=False,base_receipt_sha256=hashlib.sha256((BASE/'build-receipt.json').read_bytes()).hexdigest(),
        files={str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in output.rglob('*') if p.suffix in ('.hpp','.cpp','.dll')},
        deployed=False,game_verified=False,runtime_authorized=False)
    receipt['dll_sha256']=receipt['files']['ets2la_plugin.dll']
    (output/'build-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    probe(output,output.parent/(output.name+'-probe'))
    print(json.dumps({k:v for k,v in receipt.items() if k!='files'},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    prepare(p.parse_args().output)
