"""Compile the ACTUAL native parked acquisition/writer methods with fake objects.

Only native object discovery/placement is stubbed. Methods, packed output,
reader and downstream Python decisions are real; not an ETS2 execution proof.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'docs/steering-audit/oct14-completion/native-candidate-c'
VCVARS=Path(r'C:\DevTools\VS2022BuildTools\VC\Auxiliary\Build\vcvars64.bat')


def method(text,name):
    start=text.index('    '+name)
    opening=text.index('{',start);level=1;at=opening+1
    while level:
        level+=(text[at]=='{')-(text[at]=='}');at+=1
    return text[start:at]


def probe(source,output):
    output.mkdir(parents=True,exist_ok=False)
    raw=(source/'src/processing/traffic.cpp').read_bytes();text=raw.decode('utf-8-sig')
    methods='\n'.join(method(text,n) for n in (
        'short TrafficProcessor::get_uid_for_vehicle',
        'void TrafficProcessor::process_traffic_object',
        'void TrafficProcessor::write_parked_vehicle_data'))
    harness=r'''
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <map>
#include <unordered_set>
#include <vector>
#include <chrono>
#include <ctime>
#include <iostream>
using std::abs;
namespace up_signal {struct Owner {};}
namespace ets2la_plugin {
namespace prism {
enum class ETrafficObjectType { traffic_ai_vehicle,traffic_ai_trailer,traffic_parked_vehicle,traffic_parked_trailer,traffic_semaphore_actor };
struct Point{float x=0,y=0,z=0;};
struct Placement { Point pos;struct {float w=1,x=0,y=0,z=0;}rot;
float get_distance_to(Point p)const{return std::hypot(pos.x-p.x,pos.z-p.z);} };
struct Box {Point start,end;};
struct traffic_object_t {ETrafficObjectType kind;Placement placement;Box aabox;ETrafficObjectType get_type()const{return kind;}};
struct traffic_actor_t:traffic_object_t{};
struct traffic_ai_vehicle_t:traffic_actor_t{struct Physics{float speed,acceleration;}*physics;};
struct traffic_parked_actor_t:traffic_actor_t{traffic_parked_actor_t*slave_trailer=nullptr;};
struct traffic_semaphore_actor_t:traffic_actor_t{};
}
#pragma pack(push,1)
struct ParkedVehicle {float x,y,z,w,qx,qy,qz,width,height,length;short id;bool trailer;};
#pragma pack(pop)
static_assert(sizeof(ParkedVehicle)==43);
struct ParkedVehiclesMemData{std::array<ParkedVehicle,40> data;};
struct Memory{ParkedVehiclesMemData saved{};void write_parked_vehicles_mem(ParkedVehiclesMemData v){saved=v;}};
struct processor_actor_object_t{bool is_trailer;float distance;const prism::traffic_actor_t*traffic_actor;};
struct processor_active_actor_object_t:processor_actor_object_t{float speed,acceleration;};
struct processor_semaphore_object_t{uint32_t id;float distance;const prism::traffic_semaphore_actor_t*traffic_object;up_signal::Owner owner;};
class TrafficProcessor{public:
mutable std::map<uintptr_t,short>vehicle_uids;prism::Point truck_pos;
std::vector<processor_actor_object_t>parked_actors;
std::vector<processor_active_actor_object_t>active_actors;
std::vector<processor_semaphore_object_t>semaphore_objects;
std::array<unsigned char,1720>acquired_parked{};Memory*memory_handler_;
prism::Point get_center_coords(const prism::Placement&p,const prism::Box&)const{return p.pos;}
short get_uid_for_vehicle(uintptr_t)const;
void process_traffic_object(const prism::traffic_object_t*,uint32_t id=0,up_signal::Owner owner={});
void write_parked_vehicle_data();
};
__METHODS__
}
int main(int argc,char**argv){using namespace ets2la_plugin;Memory memory;TrafficProcessor p;p.memory_handler_=&memory;
prism::traffic_parked_actor_t parent,a,b;parent.kind=prism::ETrafficObjectType::traffic_parked_vehicle;
a.kind=b.kind=prism::ETrafficObjectType::traffic_parked_trailer;
int i=0;for(auto* o:{&parent,&a,&b}){o->placement.pos={30.f,10.f,120.f+5.f*i++};o->aabox.end={2,2,4};}
parent.slave_trailer=&a;a.slave_trailer=&b;
p.process_traffic_object(&parent);
// The same native pointer may also occur in another discovered list. It is
// exactly the same source object, unlike matching ID/pose in Python.
p.process_traffic_object(&a);
p.write_parked_vehicle_data();
std::ofstream out(argv[1],std::ios::binary);out.write(reinterpret_cast<const char*>(p.acquired_parked.data()),1720);
out.close();
TrafficProcessor perf;perf.memory_handler_=&memory;
std::array<prism::traffic_parked_actor_t,40> objects;
for(size_t j=0;j<objects.size();++j){objects[j].kind=prism::ETrafficObjectType::traffic_parked_vehicle;
objects[j].placement.pos={float(j+10),10,120};objects[j].aabox.end={2,2,4};}
std::vector<double> durations;durations.reserve(1000);const auto cpu=std::clock();
for(int n=0;n<1025;++n){const auto start=std::chrono::steady_clock::now();perf.parked_actors.clear();
for(auto& actor:objects)perf.process_traffic_object(&actor);perf.write_parked_vehicle_data();
if(n>=25)durations.push_back(std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count());}
const auto cpu_s=double(std::clock()-cpu)/CLOCKS_PER_SEC;std::sort(durations.begin(),durations.end());
std::cout<<"{\"samples\":1000,\"warmup\":25,\"actors\":40,\"p50_us\":"<<durations[499]
<<",\"p95_us\":"<<durations[949]<<",\"p99_us\":"<<durations[989]<<",\"max_us\":"<<durations.back()
<<",\"aggregate_process_cpu_s\":"<<cpu_s<<",\"retained_vector_capacity\":"<<perf.parked_actors.capacity()
<<",\"retained_pointer_ids\":"<<perf.vehicle_uids.size()<<"}";
return 0;
}
'''.replace('__METHODS__',methods)
    cpp=output/'probe.cpp';cpp.write_text(harness,encoding='utf-8');exe=output/'probe.exe'
    batch=output/'compile.cmd';batch.write_text('@echo off\n'+f'call "{VCVARS}" >nul\nif errorlevel 1 exit /b 1\n'
        +f'cl /nologo /O2 /std:c++17 /EHsc /Fe:"{exe}" "{cpp}"\nexit /b %errorlevel%\n',encoding='utf-8')
    built=subprocess.run(['cmd','/d','/c',str(batch)],cwd=output,capture_output=True)
    (output/'compile.log').write_bytes(built.stdout+built.stderr)
    if built.returncode:raise RuntimeError((built.stdout+built.stderr).decode(errors='replace'))
    measured=json.loads(subprocess.check_output([str(exe),str(output/'parked.bin')],timeout=10))
    receipt=dict(source_sha256=hashlib.sha256(raw).hexdigest(),source=str(source),
        probe_sha256=hashlib.sha256(cpp.read_bytes()).hexdigest(),
        parked_sha256=hashlib.sha256((output/'parked.bin').read_bytes()).hexdigest(),
        native_operation_benchmark=measured,
        boundary='Actual acquisition/serialization methods; fake game pointers/placements, no game process')
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,default=BASE)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(probe(a.source.resolve(),a.output.resolve()),indent=2))
