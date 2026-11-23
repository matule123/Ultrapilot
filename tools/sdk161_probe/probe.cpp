// Passive SDK bring-up only. No Prism object casts, controller API, hooks or
// production mappings. Unknown/ambiguous signatures are counts, not pointers.
#include <Windows.h>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
#include "scssdk_telemetry.h"
#include "probe_patterns.hpp"

namespace probe {
constexpr size_t CAPACITY=16384;
struct Buffer { volatile LONG sequence; uint32_t bytes; char json[CAPACITY]; };
HANDLE handle=nullptr;Buffer* buffer=nullptr;
uint64_t frames=0,source_frame=0;bool paused=true,speed_valid=false,pose_valid=false;
float speed=0;double x=0,y=0,z=0;ULONGLONG last_emit=0;
std::array<unsigned,PROBE_PATTERN_COUNT> matches{};
const scs_telemetry_init_params_v101_t* api=nullptr;

std::vector<int> parse(const char* text) {
    std::vector<int> out;const char* p=text;
    while(*p){while(*p==' ')++p;if(!*p)break;
        if(*p=='?'){out.push_back(-1);++p;}else{char* end=nullptr;long v=strtol(p,&end,16);if(end==p||v<0||v>255)return {};out.push_back(int(v));p=end;}}
    return out;
}
void scan() {
    auto base=reinterpret_cast<const unsigned char*>(GetModuleHandleW(nullptr));
    auto dos=reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
    auto nt=reinterpret_cast<const IMAGE_NT_HEADERS64*>(base+dos->e_lfanew);
    auto section=IMAGE_FIRST_SECTION(nt);
    for(size_t index=0;index<PROBE_PATTERN_COUNT;++index){auto pattern=parse(PROBE_PATTERNS[index]);
        if(pattern.empty())continue;
        for(unsigned si=0;si<nt->FileHeader.NumberOfSections;++si){const auto& s=section[si];
            if(!(s.Characteristics&IMAGE_SCN_MEM_EXECUTE))continue;
            const auto* start=base+s.VirtualAddress;size_t length=s.Misc.VirtualSize;
            for(size_t at=0;at+pattern.size()<=length;++at){bool equal=true;
                for(size_t j=0;j<pattern.size();++j)if(pattern[j]>=0&&start[at+j]!=pattern[j]){equal=false;break;}
                if(equal)++matches[index];}
        }
    }
}
void publish(bool force=false) {
    if(!buffer)return;auto now=GetTickCount64();if(!force&&now-last_emit<500)return;last_emit=now;
    char text[8192];int count=snprintf(text,sizeof(text),
        "{\"schema\":1,\"read_only\":true,\"native_layouts_verified\":false,\"production_ready\":false,"
        "\"pid\":%lu,\"tick_ms\":%llu,\"frames\":%llu,\"sdk_frame_us\":%llu,\"paused\":%s,"
        "\"speed_valid\":%s,\"speed_mps\":%.8g,\"pose_valid\":%s,\"position\":[%.10g,%.10g,%.10g],\"pattern_counts\":[",
        GetCurrentProcessId(),now,frames,source_frame,paused?"true":"false",speed_valid?"true":"false",speed,
        pose_valid?"true":"false",x,y,z);
    for(size_t i=0;i<matches.size();++i)count+=snprintf(text+count,sizeof(text)-count,"%s%u",i?",":"",matches[i]);
    count+=snprintf(text+count,sizeof(text)-count,"]}");
    if(count<1||size_t(count)>=CAPACITY)return;
    InterlockedIncrement(&buffer->sequence);MemoryBarrier();buffer->bytes=uint32_t(count);
    memcpy(buffer->json,text,count);MemoryBarrier();InterlockedIncrement(&buffer->sequence);
}
SCSAPI_VOID channel(const scs_string_t name,const scs_u32_t,const scs_value_t* const value,const scs_context_t) {
    if(strcmp(name,"truck.speed")==0){speed_valid=value&&value->type==SCS_VALUE_TYPE_float&&std::isfinite(value->value_float.value);
        speed=speed_valid?value->value_float.value:0;}
    else{pose_valid=value&&value->type==SCS_VALUE_TYPE_dplacement;
        if(pose_valid){auto p=value->value_dplacement.position;x=p.x;y=p.y;z=p.z;pose_valid=std::isfinite(x)&&std::isfinite(y)&&std::isfinite(z);}
        if(!pose_valid)x=y=z=0;}
}
SCSAPI_VOID event(const scs_event_t kind,const void* const info,const scs_context_t) {
    if(kind==SCS_TELEMETRY_EVENT_paused){paused=true;speed_valid=pose_valid=false;publish(true);}
    if(kind==SCS_TELEMETRY_EVENT_started){paused=false;speed_valid=pose_valid=false;publish(true);}
    if(kind==SCS_TELEMETRY_EVENT_frame_start&&info){++frames;source_frame=static_cast<const scs_telemetry_frame_start_t*>(info)->render_time;}
    if(kind==SCS_TELEMETRY_EVENT_frame_end)publish();
}
void close(){paused=true;speed_valid=pose_valid=false;publish(true);if(buffer)UnmapViewOfFile(buffer);if(handle)CloseHandle(handle);buffer=nullptr;handle=nullptr;}
}

SCSAPI_RESULT scs_telemetry_init(const scs_u32_t version,const scs_telemetry_init_params_t* const params) {
    if(version!=SCS_TELEMETRY_VERSION_1_01||!params)return SCS_RESULT_unsupported;
    probe::api=static_cast<const scs_telemetry_init_params_v101_t*>(params);
    const char* game=probe::api->common.game_name;
    const char* prefix="Euro Truck Simulator 2 1.61.";
    if(!game||strncmp(game,prefix,strlen(prefix))!=0)return SCS_RESULT_unsupported;
    probe::close();probe::frames=probe::source_frame=0;probe::matches.fill(0);
    auto name=std::wstring(L"Local\\UltraPilot161ReadOnlyProbe-")+std::to_wstring(GetCurrentProcessId());
    probe::handle=CreateFileMappingW(INVALID_HANDLE_VALUE,nullptr,PAGE_READWRITE,0,sizeof(probe::Buffer),name.c_str());
    if(!probe::handle)return SCS_RESULT_generic_error;
    probe::buffer=static_cast<probe::Buffer*>(MapViewOfFile(probe::handle,FILE_MAP_WRITE,0,0,sizeof(probe::Buffer)));
    if(!probe::buffer){probe::close();return SCS_RESULT_generic_error;}
    memset(probe::buffer,0,sizeof(probe::Buffer));probe::scan();
    for(auto kind:{SCS_TELEMETRY_EVENT_started,SCS_TELEMETRY_EVENT_paused,SCS_TELEMETRY_EVENT_frame_start,SCS_TELEMETRY_EVENT_frame_end})
        if(probe::api->register_for_event(kind,probe::event,nullptr)!=SCS_RESULT_ok){probe::close();return SCS_RESULT_generic_error;}
    if(probe::api->register_for_channel("truck.speed",SCS_U32_NIL,SCS_VALUE_TYPE_float,0,probe::channel,nullptr)!=SCS_RESULT_ok
        ||probe::api->register_for_channel("truck.world.placement",SCS_U32_NIL,SCS_VALUE_TYPE_dplacement,0,probe::channel,nullptr)!=SCS_RESULT_ok){probe::close();return SCS_RESULT_generic_error;}
    probe::publish(true);probe::api->common.log(SCS_LOG_TYPE_message,"[UltraPilot161ReadOnlyProbe] Read-only diagnostics active; native layouts NOT verified; NO controls.");
    return SCS_RESULT_ok;
}
SCSAPI_VOID scs_telemetry_shutdown(){probe::close();}
