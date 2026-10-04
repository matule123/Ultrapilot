// Isolated producer/mapping lifecycle test; never loads game memory or controls.
#include "snapshot.hpp"
#include <cassert>
#include <fstream>
#include <string>
int main(int argc, char** argv) {
    if(argc != 2) return 2;
    std::wstring name=L"Local\\UltraPilotSignalProbe"+std::to_wstring(GetCurrentProcessId());
    up_signal::Publisher p; p.open(name.c_str());
    HANDLE h=OpenFileMappingW(FILE_MAP_READ,FALSE,name.c_str()); assert(h);
    auto* v=static_cast<const up_signal::Snapshot*>(MapViewOfFile(h,FILE_MAP_READ,0,0,1980)); assert(v);
    auto save=[&](const char* label) {
        assert(v->sequence && v->sequence%2==0 && v->sequence==v->end_sequence);
        std::ofstream f(std::string(argv[1])+"/"+label+".bin",std::ios::binary);
        f.write(reinterpret_cast<const char*>(v),1980); assert(f.good());
    };
    unsigned char payload[1920]{};
#pragma pack(push,1)
    struct Light { float x,y,z; short tx,tz; float qw,qx,qy,qz; int kind; float left; int state,id; };
#pragma pack(pop)
    static_assert(sizeof(Light)==48);
    Light light{0,10,-5,0,0,0,0,1,0,1,10,2,19};
    memcpy(payload,&light,sizeof(light));
    double observed=up_signal::clock_s();
    p.started(); p.begin_frame(100,true); p.observe(payload,1,observed,true);
    assert(v->flags==3 && v->frame==100 && v->observed_at==observed); save("active");
    auto generation=v->generation; auto lifecycle=v->lifecycle;
    p.observe(payload,1,up_signal::clock_s(),true); assert(v->generation==generation); save("repeat");
    light.state=8; memcpy(payload,&light,sizeof(light));
    p.begin_frame(101,false); p.observe(payload,1,up_signal::clock_s(),true);
    assert(v->generation>generation && v->frame==101); save("next");
    p.paused(); assert(v->flags==0); save("paused");
    generation=v->generation; p.begin_frame(102,false); p.observe(payload,0,up_signal::clock_s(),true);
    assert(v->generation==generation);
    p.started(); p.begin_frame(2,true); p.observe(payload,1,up_signal::clock_s(),true);
    assert(v->flags==3 && v->lifecycle!=lifecycle); save("reset");
    p.reset(true); p.begin_frame(3,false); p.observe(payload,0,up_signal::clock_s(),false);
    assert(v->flags==1); save("incomplete");
    p.paused(); save("shutdown");
    UnmapViewOfFile(v); CloseHandle(h);
}
