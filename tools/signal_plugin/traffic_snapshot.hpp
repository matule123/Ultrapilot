// UltraPilot native acquisition sidecar. Legacy traffic/signal ABI unchanged.
#pragma once
#include "up_signal.hpp"
#include <cstring>
#pragma pack(push, 1)
namespace up_traffic {
struct Snapshot {
    uint32_t sequence, magic, version, size;
    uint64_t lifecycle, generation, frame;
    double observed_at;
    uint32_t flags;
    unsigned char moving[6960], parked[1720];
    uint32_t ego_count, ego_flags;
    unsigned char ego[160]; // same 10-float centre/quaternion/box format as trailers
    float ego_anchor[3], ego_speed;
    double ego_speed_observed_at;
    uint32_t end_sequence;
};
static_assert(sizeof(Snapshot)==8928, "Traffic v1 wire size");
class Publisher {
    HANDLE handle=nullptr;
    Snapshot* view=nullptr;
    uint32_t sequence=0;
    uint64_t generation=0,last_frame=UINT64_MAX,last_life=0;
    float speed=0;
    double speed_at=0;
    uint64_t speed_frame=UINT64_MAX;
public:
    void speed_observation(float value,bool valid) {
        speed=value;speed_at=up_signal::clock_s();
        speed_frame=valid?up_signal::publisher().frame_id():UINT64_MAX;
    }
    void open(const wchar_t* name=L"Local\\UltraPilotTrafficV1") {
        handle=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(Snapshot),name);
        if(handle)view=static_cast<Snapshot*>(MapViewOfFile(handle,FILE_MAP_ALL_ACCESS,0,0,sizeof(Snapshot)));
    }
    ~Publisher() {if(view)UnmapViewOfFile(view);if(handle)CloseHandle(handle);}
    void write(const void* moving,const void* parked,double at,bool complete,
               const void* ego=nullptr,uint32_t count=0,bool all_bodies=false,const float* anchor=nullptr) {
        if(!view)return;
        const auto& source=up_signal::publisher();
        Snapshot s{};s.magic=0x31545055;s.version=1;s.size=sizeof(s);
        s.lifecycle=source.lifecycle_id();s.generation=++generation;s.frame=source.frame_id();
        s.observed_at=at;s.flags=(source.is_active()?1:0)|(complete?2:0);
        if(complete){memcpy(s.moving,moving,sizeof(s.moving));memcpy(s.parked,parked,sizeof(s.parked));}
        s.ego_count=count;s.ego_flags=all_bodies&&speed_frame==source.frame_id()?1:0;
        s.ego_speed=speed;s.ego_speed_observed_at=speed_at;
        if(anchor)memcpy(s.ego_anchor,anchor,sizeof(s.ego_anchor));
        if(complete&&ego)memcpy(s.ego,ego,sizeof(s.ego));
        sequence+=2;
        InterlockedExchange(reinterpret_cast<volatile LONG*>(&view->sequence),sequence-1);
        MemoryBarrier();memcpy(reinterpret_cast<char*>(view)+4,reinterpret_cast<char*>(&s)+4,sizeof(s)-8);
        InterlockedExchange(reinterpret_cast<volatile LONG*>(&view->end_sequence),sequence);
        MemoryBarrier();InterlockedExchange(reinterpret_cast<volatile LONG*>(&view->sequence),sequence);
    }
    void invalidate(){last_frame=UINT64_MAX;write(nullptr,nullptr,up_signal::clock_s(),false);}
    void observe(const void* moving,const void* parked,double at,bool complete,
                 const void* ego=nullptr,uint32_t count=0,bool all_bodies=false,const float* anchor=nullptr) {
        const auto& source=up_signal::publisher();
        if(!source.is_active() || (source.lifecycle_id()==last_life && source.frame_id()==last_frame))return;
        last_life=source.lifecycle_id();last_frame=source.frame_id();
        write(moving,parked,at,complete,ego,count,all_bodies,anchor);
    }
};
inline Publisher& publisher(){static Publisher p;return p;}
}
#pragma pack(pop)
