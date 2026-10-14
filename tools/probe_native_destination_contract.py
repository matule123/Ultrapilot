"""Execute the unchanged native navigation publisher in an isolated C++ harness.

No game access or installation writes. Stubbed engine inputs exercise precisely
what the available function publishes; they do not prove private game events.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def function_source(text):
    start = text.index('    void CCore::get_navigation_data() const')
    body = text.index('{', start)
    depth = 1
    end = body + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def probe(source, output, vcvars):
    audit = ROOT / 'docs/steering-audit'
    if not output.is_relative_to(audit) or output.exists():
        raise ValueError('Use a new workspace audit directory')
    content = (source / 'src/core.cpp').read_bytes()
    method = function_source(content.decode('utf-8-sig'))
    output.mkdir(parents=True)
    harness = r'''
#include <array>
#include <vector>
#include <cstring>
#include <iostream>
#include <cstdint>
namespace ets2la_plugin {
struct RouteTaskObject { long long uid; float distance, time; };
struct RouteMemData { std::array<RouteTaskObject,6000> tasks; };
static_assert(sizeof(RouteMemData)==96000);
namespace prism {
struct node_item_t { long long uid; };
struct physical_route_item_t {
    node_item_t* node; float total_distance_till_end, total_time_till_end;
};
struct task_t { std::vector<physical_route_item_t> physical_route_items; };
struct source_t { task_t* route_task=nullptr; };
struct gps_manager_t {
    source_t simple_route_source;
    std::vector<int> waypoints, avoid_waypoints;
    static gps_manager_t* current;
    static gps_manager_t* get() { return current; }
};
gps_manager_t* gps_manager_t::current=nullptr;
}
struct Memory {
    RouteMemData data{}; unsigned writes=0;
    void write_route_mem(const RouteMemData value) { data=value; ++writes; }
};
struct CCore {
    Memory* memory_manager_; mutable size_t last_route_length_=0;
    void get_navigation_data() const;
};
__METHOD__
}
using namespace ets2la_plugin;
int main() {
    prism::node_item_t a{11}, b{22}, replacement{33};
    prism::task_t task{{{&a,100,10},{&b,0,0}}};
    prism::gps_manager_t gps;
    gps.simple_route_source.route_task=&task;
    prism::gps_manager_t::current=&gps;
    Memory memory; CCore core{&memory}; core.get_navigation_data();
    const auto initial=memory.data;
    if(memory.writes!=1 || initial.tasks[1].uid!=22) return 1;
    // A genuine target replacement with identical row count is not published.
    task.physical_route_items[1].node=&replacement;
    core.get_navigation_data();
    const bool replacement_missing=memory.writes==1 &&
        std::memcmp(&initial,&memory.data,sizeof(initial))==0;
    // No cause channel exists. Both removal scenarios offer the same null task.
    gps.simple_route_source.route_task=nullptr;
    gps.waypoints.clear(); core.get_navigation_data();
    const auto removal_first=memory.data;
    const auto count_first=memory.writes;
    core.get_navigation_data();
    const bool removals_identical=count_first==1 && memory.writes==1 &&
        std::memcmp(&removal_first,&memory.data,sizeof(initial))==0;
    const bool stale_mapping_retained=
        std::memcmp(&initial,&memory.data,sizeof(initial))==0;
    std::cout << "{\"replacement_same_count_unpublished\":"
        << (replacement_missing?"true":"false")
        << ",\"null_task_removal_has_no_cause_or_new_write\":"
        << (removals_identical?"true":"false")
        << ",\"old_mapping_retained\":"
        << (stale_mapping_retained?"true":"false")
        << ",\"mapping_bytes\":96000,\"writes\":" << memory.writes << "}";
    return replacement_missing && removals_identical && stale_mapping_retained ? 0:2;
}
'''.replace('__METHOD__', method)
    cpp = output / 'probe.cpp'
    cpp.write_text(harness, encoding='utf-8')
    exe = output / 'probe.exe'
    batch = output / 'compile.cmd'
    batch.write_text('@echo off\n'+f'call "{vcvars}" >nul\n'
        +'if errorlevel 1 exit /b 1\n'
        +f'cl /nologo /O2 /std:c++17 /EHsc /Fe:"{exe}" "{cpp}"\n'
        +'exit /b %errorlevel%\n', encoding='utf-8')
    build = subprocess.run(['cmd', '/d', '/c', str(batch)], cwd=output,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (output / 'compile.log').write_bytes(build.stdout)
    if build.returncode:
        raise RuntimeError(build.stdout.decode(errors='replace'))
    result = json.loads(subprocess.check_output([str(exe)], cwd=output))
    result.update(kind='available_publisher_information_loss_probe',
        source=str(source), source_sha256=hashlib.sha256(content).hexdigest(),
        extracted_method_sha256=hashlib.sha256(method.encode()).hexdigest(),
        game_event_semantics_verified=False,
        authentic_destination_completion_implemented=False)
    (output / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--vcvars', type=Path, required=True)
    args = parser.parse_args()
    probe(args.source.resolve(), args.output.resolve(), args.vcvars.resolve())
