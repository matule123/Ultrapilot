"""Reproduce the REAL candidate-d method failure in an isolated native host.

The invalid empty-list sentinel mirrors the crash register vtable=5. Windows
SEH catches that expected test fault; neither DLL nor host is loaded into ETS2.
The patched method must return without inspecting the sentinel, and still
reject a nonempty unsupported list. No process injection or game controls.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.verify_oct17_native_records import method,VCVARS
AUDIT=ROOT/'docs/steering-audit/oct22-sdk161'


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--output-name',default='sentinel-regression')
    args=parser.parse_args();candidate=args.candidate.resolve()
    if candidate.parent!=AUDIT:raise ValueError('Use dedicated audit candidate')
    if not re.fullmatch(r'[a-z0-9-]+',args.output_name):raise ValueError('Use a simple unique output name')
    before_path=AUDIT/'read-candidate-d/src/processing/traffic.cpp'
    after_path=candidate/'src/processing/traffic.cpp'
    before=method(before_path.read_text(),'void TrafficProcessor::get_truckersmp_traffic_data()')
    after=method(after_path.read_text(),'void TrafficProcessor::get_truckersmp_traffic_data()')
    before=before.replace('TrafficProcessor::get_truckersmp_traffic_data()','TrafficProcessor::before()')
    after=after.replace('TrafficProcessor::get_truckersmp_traffic_data()','TrafficProcessor::after()')
    output=candidate/args.output_name;output.mkdir(exist_ok=False)
    code=r'''
#include <Windows.h>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <vector>
#include "up161_guard.hpp"
namespace ets2la_plugin {
namespace prism {
struct unit_descriptor_t {const char** p_class_name;};
struct vehicle_shared_u {
    virtual void f0(){} virtual void f1(){} virtual void f2(){}
    virtual void f3(){} virtual void f4(){}
    virtual unit_descriptor_t* get_unit_descriptor(){return nullptr;}
};
struct game_trailer_actor_u:vehicle_shared_u{};
struct game_physics_vehicle_u:vehicle_shared_u{};
struct Node {Node*next;Node*prev;vehicle_shared_u*item;};
struct List {uintptr_t vtable;uint64_t size;Node*begin;Node*end;
    void*allocator1;void*allocator2;vehicle_shared_u*empty_item;};
static_assert(offsetof(List,size)==8);static_assert(offsetof(List,begin)==0x10);
static_assert(offsetof(List,empty_item)==0x30);
struct game_ctrl_u {
    static game_ctrl_u* current;List*list=nullptr;
    static game_ctrl_u*get(){return current;}
    List*get_some_nearby_non_ai_vehicles_list(){return list;}
};
game_ctrl_u* game_ctrl_u::current=nullptr;
}
struct TrafficProcessor {
    std::vector<prism::game_physics_vehicle_u*>tmp_vehicles;
    std::vector<prism::game_trailer_actor_u*>tmp_trailers;
    void before();void after();
};
// REAL METHODS INSERTED BELOW
__METHODS__
}
using namespace ets2la_plugin;
static unsigned long call_before(TrafficProcessor*processor) {
    __try {processor->before();return 0;}
    __except(EXCEPTION_EXECUTE_HANDLER){return GetExceptionCode();}
}
static unsigned long call_after(TrafficProcessor*processor) {
    __try {processor->after();return 0;}
    __except(EXCEPTION_EXECUTE_HANDLER){return GetExceptionCode();}
}
int main() {
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
    TrafficProcessor processor;prism::game_ctrl_u ctrl;
    prism::game_ctrl_u::current=&ctrl;
    uintptr_t captured_bad_vtable=5;
    prism::Node sentinel{};sentinel.item=reinterpret_cast<prism::vehicle_shared_u*>(&captured_bad_vtable);
    prism::List list{};list.size=0;list.begin=&sentinel;list.end=&sentinel;
    ctrl.list=&list;
    unsigned long original_fault=call_before(&processor);
    assert(original_fault==EXCEPTION_ACCESS_VIOLATION);
    unsigned long patched_fault=call_after(&processor);assert(patched_fault==0);
    assert(processor.tmp_vehicles.empty()&&processor.tmp_trailers.empty());
    void* inaccessible=VirtualAlloc(nullptr,4096,MEM_RESERVE|MEM_COMMIT,PAGE_NOACCESS);
    assert(inaccessible);
    uintptr_t begin_values[]={0,5,0x10000,reinterpret_cast<uintptr_t>(&sentinel),reinterpret_cast<uintptr_t>(inaccessible)};
    uintptr_t empty_values[]={0,5,reinterpret_cast<uintptr_t>(&captured_bad_vtable)};
    unsigned empty_configurations=0;
    for(auto begin:begin_values)for(auto empty:empty_values) {
        list.begin=reinterpret_cast<prism::Node*>(begin);
        list.empty_item=reinterpret_cast<prism::vehicle_shared_u*>(empty);
        assert(call_after(&processor)==0);++empty_configurations;
    }
    assert(empty_configurations==15);
    unsigned nonempty_rejections=0;
    for(uint64_t count:{uint64_t(1),uint64_t(64),UINT64_MAX}) {
        list.size=count;bool rejected=false;
        try{processor.after();}catch(const std::runtime_error&){rejected=true;}
        assert(rejected);++nonempty_rejections;
    }
    unsigned invalid_header_rejections=0;
    for(uintptr_t header:{uintptr_t(5),reinterpret_cast<uintptr_t>(inaccessible)}) {
        ctrl.list=reinterpret_cast<prism::List*>(header);bool rejected=false;
        try{processor.after();}catch(const std::runtime_error&){rejected=true;}
        assert(rejected);++invalid_header_rejections;
    }
    assert(VirtualFree(inaccessible,0,MEM_RELEASE));
    ctrl.list=nullptr;processor.after();
    prism::game_ctrl_u::current=nullptr;processor.after();
    std::printf("PASS: real before method faults 0x%08lx; patched empty list does not dereference sentinel; nonempty remains rejected\n",original_fault);
    std::printf("MATRIX: empty=%u nonempty_rejected=%u invalid_headers_rejected=%u\n",empty_configurations,nonempty_rejections,invalid_header_rejections);
}
'''.replace('__METHODS__',before+'\n'+after)
    source=output/'sentinel.cpp';source.write_text(code,encoding='utf-8')
    command=output/'compile.cmd'
    argv=['cl','/nologo','/O2','/MT','/std:c++17','/EHsc','/utf-8','/I'+str(candidate/'src'),
        str(source),'/Fe:'+str(output/'sentinel.exe')]
    command.write_text('@echo off\n'+f'call "{VCVARS}" >nul\nif errorlevel 1 exit /b 1\n'
        +subprocess.list2cmdline(argv)+'\nexit /b %errorlevel%\n',encoding='utf-8')
    built=subprocess.run(['cmd','/d','/c',str(command)],cwd=output,capture_output=True)
    (output/'compile.log').write_bytes(built.stdout+built.stderr)
    if built.returncode:raise RuntimeError((built.stdout+built.stderr).decode(errors='replace'))
    run=subprocess.run([str(output/'sentinel.exe')],capture_output=True,text=True,timeout=20)
    (output/'run.log').write_text(run.stdout+run.stderr,encoding='utf-8')
    if run.returncode:raise RuntimeError('Sentinel regression failed: '+str(run.returncode)+' '+run.stdout+run.stderr)
    result=dict(before_method_sha256=hashlib.sha256(before.encode()).hexdigest(),
        after_method_sha256=hashlib.sha256(after.encode()).hexdigest(),
        before_exception='C0000005',after_exception=None,nonempty_rejected=True,
        empty_configurations=15,nonempty_rejections=3,invalid_header_rejections=2,
        original_source_sha256=hashlib.sha256(before_path.read_bytes()).hexdigest(),
        patched_source_sha256=hashlib.sha256(after_path.read_bytes()).hexdigest(),
        output=run.stdout.strip(),game_executed=False,deployed=False)
    (output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
