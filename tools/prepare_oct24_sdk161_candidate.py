"""Build isolated read-side SDK candidate. NEVER installs or enables controls.

All generated sources remain under a new audit folder. Public 1.60 layouts
are combined with our current timed/scoped publisher, with evidence-bound
1.61 differences. A compiled candidate is not a production readiness claim.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.build_signal_plugin import replace_once
from tools.verify_oct17_native_records import method, VCVARS, probe

AUDIT=ROOT/'docs/steering-audit/oct22-sdk161'
BASE=ROOT/'docs/steering-audit/oct17-joint-lifecycle/native-candidate-b'


def compile_source(output,dll_name='UltraPilot161ReadCandidate.dll'):
    sources=('core.cpp','main.cpp','memory/memory_utils.shared.cpp','memory/virtual/memory_handler.cpp',
        'prism/common.cpp','prism/game_actor.cpp','prism/camera/camera_manager.cpp',
        'prism/controllers/base_ctrl.cpp','prism/controllers/game_ctrl.cpp','prism/navigation/gps_manager.cpp',
        'prism/traffic/game_traffic.cpp','prism/vehicles/game_trailer_actor.cpp','prism/vehicles/game_physics_vehicle.cpp',
        'prism/vehicles/vehicle_shared.cpp','processing/traffic.cpp','memory/memory_utils.win32.cpp')
    fmt=ROOT/'docs/steering-audit/signal-plugin-20261003/fmt'
    args=['cl','/nologo','/LD','/O2','/MT','/std:c++17','/EHsc','/utf-8','/Brepro',
        '/DFMT_HEADER_ONLY','/DETS2LA_PLUGIN_EXPORTS','/DUNICODE','/D_UNICODE','/DUP_SIGNAL_SCOPE_V3',
        '/I'+str(output/'src'),'/I'+str(output/'vendor/scs_sdk/include'),'/I'+str(fmt/'include'),
        *[str(output/'src'/name) for name in sources],'/link','/DEF:'+str(output/'ets2la_plugin.def'),
        '/Brepro','/OUT:'+str(output/dll_name)]
    command=output/'compile.cmd'
    command.write_text('@echo off\n'+f'call "{VCVARS}" >nul\nif errorlevel 1 exit /b 1\n'
        +subprocess.list2cmdline(args)+'\nexit /b %errorlevel%\n',encoding='utf-8')
    result=subprocess.run(['cmd','/d','/c',str(command)],cwd=output,capture_output=True)
    (output/'compile.log').write_bytes(result.stdout+result.stderr)
    if result.returncode:raise RuntimeError((result.stdout+result.stderr).decode(errors='replace'))


def replace_method(path,name,replacement):
    text=path.read_text(encoding='utf-8-sig');old=method(text,name)
    replace_once(path,old,replacement)


def prepare(output):
    output=output.resolve()
    if output.parent!=AUDIT or output.exists():raise ValueError('Use a NEW direct child of SDK audit directory')
    receipt=json.loads((BASE/'build-receipt.json').read_text())
    for name,digest in receipt['files'].items():
        if hashlib.sha256((BASE/name).read_bytes()).hexdigest()!=digest:raise ValueError('Baseline changed: '+name)
    upstream=next((AUDIT/'inputs/upstream').iterdir())
    inputs=json.loads((AUDIT/'inputs/receipt.json').read_text())
    for name,digest in inputs['upstream_files'].items():
        if hashlib.sha256((AUDIT/'inputs'/name).read_bytes()).hexdigest()!=digest:raise ValueError('Public source changed: '+name)
    profile=json.loads((AUDIT/'static-profile-161.json').read_text())
    shutil.copytree(BASE,output,ignore=shutil.ignore_patterns('*.obj','*.lib','*.exp','*.dll','*.pdb','build-receipt.json','compile.*'))
    shutil.copytree(upstream/'src/prism',output/'src/prism',dirs_exist_ok=True)
    shutil.copy(ROOT/'tools/sdk161_probe/candidate_guard.hpp',output/'src/up161_guard.hpp')
    replace_once(output/'src/version.hpp','1.59.5-up-parked-records','1.61.0-up-read-candidate')
    replace_once(output/'src/version.hpp','1.59.x','1.61.x')
    # Preserve our owner nodes. The larger Windows array shifts origin by +8.
    prefab=output/'src/prism/management/item/prefab_item.hpp'
    replace_once(prefab,'char pad_WLA_0x0060[ 48 ];','class node_item_t* nodes[6];')
    replace_once(prefab,'char pad_W_0x00D0__LA_0x00C8[ 88 ];',
        'char pad_W_0x00D0__LA_0x00C8[ 80 ];\n        uint64_t origin_idx; // 0x120; compared with live/map evidence')
    # Use all already-decoded sites, not first-match signature guessing.
    bindings=profile['bindings']
    cpp=output/'src/prism/controllers/base_ctrl.cpp'
    replace_once(cpp,'#include "base_ctrl.hpp"','#include "base_ctrl.hpp"\n#include "up161_guard.hpp"')
    names={'instance_ptr_address':'base_ctrl_global','game_actor_offset':'game_actor_member',
        'some_nearby_kdop_items_offset':'nearby_kdop_items','some_nearby_non_ai_vehicles_offset':'nearby_non_ai_list'}
    assignments='\n'.join('        '+name+' = '+('up161::base() + ' if name=='instance_ptr_address' else '')
        +hex(bindings[key]['value'])+';' for name,key in names.items())
    replace_method(cpp,'bool base_ctrl_u::scan_patterns()',
        '    bool base_ctrl_u::scan_patterns() {\n        if(!up161::image_matches())return false;\n'+assignments+'\n        return true;\n    }')
    for relative,name,field,key,global_slot in (
        ('controllers/game_ctrl.cpp','game_ctrl_u','gps_manager_offset','gps_manager_member',False),
        ('camera/camera_manager.cpp','camera_manager_u','instance_ptr_address','camera_manager_global',True),
        ('traffic/game_traffic.cpp','game_traffic_u','instance_ptr_address','game_traffic_global',True),
        ('vehicles/game_physics_vehicle.cpp','game_physics_vehicle_u','trailer_offset','trailer_member',False),
        ('vehicles/game_trailer_actor.cpp','game_trailer_actor_u','slave_trailer_offset','slave_trailer_member',False),
        ('vehicles/vehicle_shared.cpp','vehicle_shared_u','steering_angle_offset','steering_member',False),
    ):
        path=output/'src/prism'/relative
        text=path.read_text(encoding='utf-8-sig');path.write_text('#include "up161_guard.hpp"\n'+text,encoding='utf-8')
        replace_method(path,f'bool {name}::scan_patterns()',f'    bool {name}::scan_patterns() {{ {field} = '
            +('up161::base() + ' if global_slot else '')+hex(bindings[key]['value'])+'; return true; }')
    # This candidate is a data producer only; the SCS control backend is separate.
    actor=output/'src/prism/game_actor.cpp'
    replace_method(actor,'bool game_actor_u::scan_patterns()','    bool game_actor_u::scan_patterns() { return true; }')
    replace_method(actor,'void game_actor_u::set_throttle_input','    void game_actor_u::set_throttle_input(float) {}')
    replace_method(actor,'void game_actor_u::set_brake_input','    void game_actor_u::set_brake_input(float) {}')
    vehicle=output/'src/prism/vehicles/vehicle_shared.cpp'
    replace_method(vehicle,'bool vehicle_shared_u::set_steering_angle','    bool vehicle_shared_u::set_steering_angle(float) { return false; }')
    core=output/'src/core.cpp'
    replace_once(core,'#include "core.hpp"','#include "core.hpp"\n#include "up161_guard.hpp"\n'
        '#include "prism/camera/core_camera.hpp"\n#include "prism/navigation/gps_manager.hpp"\n#include <stdexcept>')
    replace_method(core,'void CCore::override_inputs() const','    void CCore::override_inputs() const {} // NO GAME WRITES')
    replace_once(core,'        this->override_inputs();','        // Native controls deliberately absent in read-only candidate.')
    replace_once(core,'        this->info("Initializing {}", VERSION);',
        '        this->info("Initializing {} (isolated diagnostic, NO controls)", VERSION);')
    # Existing callers historically expected scanner exceptions and ignored a
    # false result. Make the exact-image gate explicit before any scanner.
    replace_once(core,'        if ( !this->scan_for_required_patterns() )',
        '        if ( !up161::image_matches() || !this->scan_for_required_patterns() )')
    replace_once(core,'            prism::base_ctrl_u::scan_patterns();',
        '            if(!prism::base_ctrl_u::scan_patterns())return false;')
    replace_once(core,'        g_instance = this;', '        this->traffic_processor_ = nullptr;\n        g_instance = this;')
    replace_once(core,'        delete this->memory_manager_;\n        delete this->traffic_processor_;',
        '        delete this->memory_manager_;this->memory_manager_=nullptr;\n'
        '        delete this->traffic_processor_;this->traffic_processor_=nullptr;\n'
        '        if(g_instance==this)g_instance=nullptr;')
    main=output/'src/main.cpp'
    replace_once(main,'    auto* init_params = static_cast< const scs_telemetry_init_params_v100_t* >( params );',
        '    if(version!=SCS_TELEMETRY_VERSION_1_01 || !params)return SCS_RESULT_unsupported;\n'
        '    auto* init_params = static_cast< const scs_telemetry_init_params_v101_t* >( params );')
    replace_once(main,'        return SCS_RESULT_generic_error;',
        '        g_core.reset();\n        return SCS_RESULT_generic_error;')
    # Enforce route capacity, publish empty when route disappears, and refresh
    # same-sized routes instead of silently reusing old IDs.
    replace_method(core,'void CCore::get_navigation_data() const','''    void CCore::get_navigation_data() const {
        auto* gps=prism::gps_manager_t::get();
        RouteMemData data{};
        if(!gps || !gps->simple_route_source.route_task) {
            memory_manager_->write_route_mem(data); return;
        }
        auto& route=gps->simple_route_source.route_task->physical_route_items;
        if(!up161::bounded(route,6000))return;
        for(size_t i=0;i<route.size;++i) {
            const auto& item=route.value[i];
            if(!up161::readable(item.node,sizeof(*item.node)))return;
            if(!std::isfinite(item.total_distance_till_end)||item.total_distance_till_end<0
               ||!std::isfinite(item.total_time_till_end)||item.total_time_till_end<0)return;
            data.tasks[i]={static_cast<long long>(item.node->uid),item.total_distance_till_end,item.total_time_till_end};
        }
        memory_manager_->write_route_mem(data);
    }''')
    # Pause never executes a Prism acquisition; existing publishers invalidate.
    replace_once(core,'    void CCore::tick() const\n    {',
        '    void CCore::tick() const\n    {\n        if(!up_signal::publisher().is_active())return;')
    # Release the constructor handler before replacing it (legacy leak).
    replace_once(core,'        this->memory_manager_ = new CMemoryHandler(scs_log_);',
        '        delete this->memory_manager_;\n        this->memory_manager_ = new CMemoryHandler(scs_log_);')
    # Public 1.60 removed the old acceleration field. Do not resurrect a stale
    # offset or fabricate zero for an unverified multiplayer vehicle. Reject
    # that acquisition explicitly; no complete frame is published.
    traffic=output/'src/processing/traffic.cpp'
    replace_once(traffic,'#include "traffic.hpp"','#include "traffic.hpp"\n#include "up161_guard.hpp"\n#include <stdexcept>\n#include <limits>')
    for owner in ('tmp_truck','tmp_trailer'):
        replace_once(traffic,f'{owner}->linear_acceleration.x + {owner}->linear_acceleration.y + {owner}->linear_acceleration.z',
            'std::numeric_limits<float>::quiet_NaN() /* unsupported candidate multiplayer motion */')
    # No sentinel traversal is valid here: the legacy while loop inspected a
    # sentinel even when size==0. A real candidate-d crash had vtable value 5.
    # Nonempty multiplayer acquisition remains explicitly unsupported rather
    # than inventing motion or silently publishing it as complete.
    replace_method(traffic,'void TrafficProcessor::get_truckersmp_traffic_data()', '''    void TrafficProcessor::get_truckersmp_traffic_data() {
        auto* ctrl=prism::game_ctrl_u::get();
        if(!ctrl)return;
        const auto* list=ctrl->get_some_nearby_non_ai_vehicles_list();
        if(!list)return;
        if(!up161::readable(list,sizeof(*list)))throw std::runtime_error("Candidate non-AI list header unreadable");
        if(list->size==0)return; // NEVER dereference an empty-list sentinel.
        throw std::runtime_error("Candidate multiplayer motion layout unverified");
    }''')
    # Catch acquisition exceptions at the telemetry boundary, invalidate instead
    # of allowing unsupported layouts to escape into the game callback.
    replace_once(core,'        CCore::g_instance->tick();','''        try { CCore::g_instance->tick(); }
        catch(const std::exception&) {
            up_signal::publisher().paused();up_traffic::publisher().invalidate();
        }''')
    # Prevent any collision with active app buffers. This is enforced in build tests.
    for path in (output/'src').rglob('*'):
        if path.suffix not in ('.hpp','.cpp'):continue
        text=path.read_text(encoding='utf-8-sig')
        updated=text.replace('Local\\\\UltraPilotSemaphore','Local\\\\UltraPilot161CandidateSemaphore')
        updated=updated.replace('Local\\\\UltraPilotTraffic','Local\\\\UltraPilot161CandidateTraffic')
        updated=updated.replace('L"ETS2LA','L"UltraPilot161CandidateETS2LA')
        if updated!=text:path.write_text(updated,encoding='utf-8')
    # Match the diagnostic DLL name so the linker emits no misleading name.
    replace_once(output/'ets2la_plugin.def','ets2la_plugin','UltraPilot161ReadCandidate')
    # Do not even create a control-input buffer.
    replace_once(output/'src/memory/virtual/memory_handler.cpp',
        '        this->initialize_memory_file(input_mmap_data, L"fbdfbd");','        // No input buffer in read-only candidate.')
    compile_source(output)
    result=dict(version='1.61.0-up-read-candidate',production_ready=False,deployed=False,game_verified=False,
        controls_enabled=False,isolated_mappings=True,game_sha256=profile['game_sha256'],
        baseline_dll_sha256=receipt['dll_sha256'],
        baseline_receipt_sha256=hashlib.sha256((BASE/'build-receipt.json').read_bytes()).hexdigest(),
        profile_sha256=hashlib.sha256((AUDIT/'static-profile-161.json').read_bytes()).hexdigest(),
        files={str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest() for p in output.rglob('*')
            if p.suffix in ('.hpp','.cpp','.dll')})
    result['dll_sha256']=result['files']['UltraPilot161ReadCandidate.dll']
    (output/'build-receipt.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='files'},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    prepare(parser.parse_args().output)
