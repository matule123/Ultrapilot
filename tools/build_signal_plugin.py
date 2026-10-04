"""Patch/build pinned 1.59 MIT source outside the installation; no deployment.

Input directories come from the source/download receipts in the audit report.
Only the private output copy is modified. Run with MSVC vcvars64 environment.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = '1f16156b9b37b70cf182c2bc09120fa1b234e129'


def replace_once(path, old, new):
    text = path.read_text(encoding='utf-8-sig')
    if text.count(old) != 1:
        raise ValueError(f'Pinned source anchor mismatch: {path.name}')
    path.write_text(text.replace(old, new), encoding='utf-8')


def prepare(source, fmt, output):
    audit_root = ROOT/'docs/steering-audit'
    if not output.is_relative_to(audit_root) or output.is_relative_to(source) or output.is_relative_to(fmt):
        raise ValueError('Output must be a separate repository audit directory')
    if output.exists():
        raise ValueError('Use a new output directory; no overwriting audit builds')
    receipt = json.loads((ROOT/'tools/signal_plugin/inputs.json').read_text())
    for folder, key in ((source, 'source'), (fmt, 'fmt')):
        for name, digest in receipt[key].items():
            if hashlib.sha256((folder/name).read_bytes()).hexdigest() != digest:
                raise ValueError('Pinned input receipt mismatch: '+name)
    shutil.copytree(source, output)
    shutil.copy(fmt/'LICENSE', output/'FMT_LICENSE')
    shutil.copy(ROOT/'tools/signal_plugin/snapshot.hpp', output/'src/up_signal.hpp')
    core = output/'src/core.cpp'
    replace_once(core, '#include "core.hpp"', '#include "core.hpp"\n#include "up_signal.hpp"\n#include "scssdk_telemetry_event.h"')
    replace_once(core, '    CCore *CCore::g_instance = nullptr;', '''    CCore *CCore::g_instance = nullptr;
    SCSAPI_VOID signal_lifecycle(const scs_event_t event, const void *const info, scs_context_t) {
        auto& p = up_signal::publisher();
        if(event == SCS_TELEMETRY_EVENT_paused) p.paused();
        else if(event == SCS_TELEMETRY_EVENT_started) p.started();
        else if(event == SCS_TELEMETRY_EVENT_configuration) p.reset(true);
        else if(event == SCS_TELEMETRY_EVENT_frame_start && info) {
            const auto* f=static_cast<const scs_telemetry_frame_start_t*>(info);
            p.begin_frame(f->render_time, (f->flags & SCS_TELEMETRY_FRAME_START_FLAG_timer_restart)!=0);
        }
    }''')
    replace_once(core, '        this->traffic_processor_ = new TrafficProcessor(scs_log_, this->memory_manager_);', '''        this->traffic_processor_ = new TrafficProcessor(scs_log_, this->memory_manager_);
        up_signal::publisher().open();
        for(auto event : {SCS_TELEMETRY_EVENT_paused, SCS_TELEMETRY_EVENT_started,
                          SCS_TELEMETRY_EVENT_configuration, SCS_TELEMETRY_EVENT_frame_start}) {
            if(this->init_params_->register_for_event(event, signal_lifecycle, nullptr)!=SCS_RESULT_ok)
                return false;
        }''')
    traffic = output/'src/processing/traffic.cpp'
    replace_once(core, '    void CCore::destroy()\n    {',
                 '    void CCore::destroy()\n    {\n        up_signal::publisher().paused();')
    replace_once(traffic, '#include "traffic.hpp"', '#include "traffic.hpp"\n#include "up_signal.hpp"')
    replace_once(traffic, '    void TrafficProcessor::write_semaphore_data()\n    {', '''    void TrafficProcessor::write_semaphore_data()
    {
        const double observed_at = up_signal::clock_s();''')
    replace_once(traffic, '''        this->memory_handler_->write_semaphore_mem(SemaphoreMemData{
            semaphore_objects_data
        });''', '''        this->memory_handler_->write_semaphore_mem(SemaphoreMemData{
            semaphore_objects_data
        });
        // Timestamp belongs to this actual actor/color read, never a receiver.
        // Missing game data is not an authoritative empty observation.
        const bool complete = prism::base_ctrl_u::get()!=nullptr &&
                              prism::base_ctrl_u::get()->get_nearby_kdop_items()!=nullptr;
        up_signal::publisher().observe(semaphore_objects_data.data(), count, observed_at, complete);''')
    version = (output/'version.hpp.in').read_text()
    for key, value in dict(PLUGIN_VERSION_MAJOR='1',PLUGIN_VERSION_MINOR='59',PLUGIN_VERSION_PATCH='2-up-signal',
                           GAME_VERSION_MAJOR='1',GAME_VERSION_MINOR='59',GAME_VERSION_PATCH='x').items():
        version = version.replace('@'+key+'@',value)
    (output/'src/version.hpp').write_text(version)
    sources = [
        'core.cpp','main.cpp','memory/memory_utils.shared.cpp','memory/virtual/memory_handler.cpp',
        'prism/common.cpp','prism/game_actor.cpp','prism/camera/camera_manager.cpp',
        'prism/controllers/base_ctrl.cpp','prism/controllers/game_ctrl.cpp',
        'prism/navigation/gps_manager.cpp','prism/traffic/game_traffic.cpp',
        'prism/vehicles/game_trailer_actor.cpp','prism/vehicles/game_physics_vehicle.cpp',
        'prism/vehicles/vehicle_shared.cpp','processing/traffic.cpp','memory/memory_utils.win32.cpp']
    subprocess.run(['cl', '/nologo','/LD','/O2','/MT','/std:c++17','/EHsc','/utf-8',
        '/Brepro', '/experimental:deterministic', '/pathmap:'+str(output)+'=ETS2LA_SOURCE',
        '/DFMT_HEADER_ONLY','/DETS2LA_PLUGIN_EXPORTS','/DUNICODE','/D_UNICODE',
        '/I'+str(output/'src'),'/I'+str(output/'vendor/scs_sdk/include'),'/I'+str(fmt/'include'),
        *[str(output/'src'/s) for s in sources],'/link','/DEF:'+str(output/'ets2la_plugin.def'),
        '/Brepro','/OUT:'+str(output/'ets2la_plugin.dll')], cwd=output, check=True)
    dll=output/'ets2la_plugin.dll'
    result={'source_commit':SOURCE_COMMIT,'dll_sha256':hashlib.sha256(dll.read_bytes()).hexdigest(),
            'installed_binary_equivalence':'NOT_CLAIMED','schema':2,
            'files':{str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in output.rglob('*') if p.is_file() and p.suffix in ('.hpp','.cpp','.dll')}}
    (output/'build-receipt.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='files'},indent=2))


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=Path,required=True);p.add_argument('--fmt',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prepare(a.source.resolve(),a.fmt.resolve(),a.output.resolve())
