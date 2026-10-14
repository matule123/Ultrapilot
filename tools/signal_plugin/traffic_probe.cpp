// Isolated publication test; does not call or load ETS2.
#include "up_traffic.hpp"
#include <fstream>
#include <filesystem>
int main(int argc,char** argv) {
    if(argc!=2)return 1;
    auto& life=up_signal::publisher();auto& p=up_traffic::publisher();
    const wchar_t* name=L"Local\\UltraPilotTrafficOfflineProbe";
    p.open(name);
    unsigned char moving[6960]{},parked[1720]{},ego[160]{};
    float anchor[3]{12,10,20};
    auto save=[&](const char* file){
        HANDLE h=OpenFileMappingW(FILE_MAP_READ,FALSE,name);if(!h)exit(2);
        auto* view=MapViewOfFile(h,FILE_MAP_READ,0,0,sizeof(up_traffic::Snapshot));if(!view)exit(3);
        std::ofstream out(std::filesystem::path(argv[1])/file,std::ios::binary);
        out.write(static_cast<const char*>(view),sizeof(up_traffic::Snapshot));
        UnmapViewOfFile(view);CloseHandle(h);
    };
    life.started();life.begin_frame(100000,false);p.speed_observation(10.f,true);
    p.observe(moving,parked,up_signal::clock_s(),true,ego,1,true,anchor);save("active.bin");
    p.observe(moving,parked,up_signal::clock_s(),true,ego,1,true,anchor);save("repeat.bin");
    life.begin_frame(116666,false);p.speed_observation(9.f,true);
    p.observe(moving,parked,up_signal::clock_s(),true,ego,1,true,anchor);save("next.bin");
    life.paused();p.invalidate();save("paused.bin");
    life.reset();life.started();life.begin_frame(1000,true);p.speed_observation(0.f,true);
    p.observe(moving,parked,up_signal::clock_s(),true,ego,1,true,anchor);save("reset.bin");
    life.begin_frame(17000,false); // no new per-frame SCS speed callback
    p.observe(moving,parked,up_signal::clock_s(),true,ego,1,true,anchor);save("missing_speed.bin");
}
