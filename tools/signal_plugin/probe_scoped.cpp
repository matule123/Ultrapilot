// Isolated version-2/version-3 ABI and lifecycle probe. No game entrypoint.
#define UP_SIGNAL_SCOPE_V3
#include "snapshot.hpp"
#include <cassert>
#include <fstream>
#include <string>
int main(int argc,char**argv) {
    if(argc!=2)return 2;
    auto base=L"Local\\UltraPilotScopeProbe"+std::to_wstring(GetCurrentProcessId());
    up_signal::Publisher p;p.open((base+L"V2").c_str());p.open_scope((base+L"V3").c_str());
    HANDLE a=OpenFileMappingW(FILE_MAP_READ,FALSE,(base+L"V2").c_str());assert(a);
    HANDLE b=OpenFileMappingW(FILE_MAP_READ,FALSE,(base+L"V3").c_str());assert(b);
    auto*v2=static_cast<const up_signal::Snapshot*>(MapViewOfFile(a,FILE_MAP_READ,0,0,1980));
    auto*v3=static_cast<const up_signal::ScopedSnapshot*>(MapViewOfFile(b,FILE_MAP_READ,0,0,4860));
    assert(v2&&v3);
    auto save=[&](const char*name) {
        assert(v2->sequence==v2->end_sequence&&v3->sequence==v3->end_sequence&&v2->sequence==v3->sequence);
        assert(v2->generation==v3->generation&&v2->observed_at==v3->observed_at&&v2->lifecycle==v3->lifecycle);
        std::ofstream old(std::string(argv[1])+"/"+name+"-v2.bin",std::ios::binary);
        std::ofstream scoped(std::string(argv[1])+"/"+name+"-v3.bin",std::ios::binary);
        old.write(reinterpret_cast<const char*>(v2),1980);scoped.write(reinterpret_cast<const char*>(v3),4860);
        assert(old.good()&&scoped.good());
    };
#pragma pack(push,1)
    struct Light{float x,y,z;short tx,tz;float w,qx,qy,qz;int kind;float remaining;int color,id;};
#pragma pack(pop)
    static_assert(sizeof(Light)==48);
    unsigned char data[1920]{};up_signal::Owner owners[40]{};
    Light light{0,14,-5,0,0,0,0,1,0,1,10,2,19};memcpy(data,&light,48);
    owners[0]={900,{11,12,13,0,0,0},2,4,1};
    p.started();p.begin_frame(100,true);p.observe(data,1,up_signal::clock_s(),true,owners);save("red");
    p.observe(data,1,up_signal::clock_s(),true,owners);save("repeat");
    light.color=8;memcpy(data,&light,48);p.begin_frame(101,false);
    p.observe(data,1,up_signal::clock_s(),true,owners);save("green");
    p.paused();save("paused");p.started();p.begin_frame(2,true);
    p.observe(data,1,up_signal::clock_s(),true,owners);save("reset");
    UnmapViewOfFile(v2);UnmapViewOfFile(v3);CloseHandle(a);CloseHandle(b);
}
