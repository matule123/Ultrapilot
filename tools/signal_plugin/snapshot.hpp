// UltraPilot sidecar, independent of the legacy semaphore ABI. Windows only.
#pragma once
#include <Windows.h>
#include <cstdint>
#include <cstring>
namespace up_signal {
#pragma pack(push, 1)
struct Snapshot {
    uint32_t sequence, magic, version, size;
    uint64_t lifecycle, generation, frame;
    double observed_at;
    uint32_t flags, count;
    unsigned char payload[1920];
    uint32_t end_sequence;
};
#pragma pack(pop)
static_assert(sizeof(Snapshot) == 1980);
inline double clock_s() {
    LARGE_INTEGER q, f; QueryPerformanceCounter(&q); QueryPerformanceFrequency(&f);
    return double(q.QuadPart)/double(f.QuadPart);
}
class Publisher {
    HANDLE handle = nullptr;
    Snapshot* view = nullptr;
    uint64_t lifecycle = 0, generation = 0, frame = 0, last_frame = UINT64_MAX;
    uint32_t sequence = 0;
    bool active = false;
public:
    Publisher() { reset(); }
    ~Publisher() { paused(); if(view) UnmapViewOfFile(view); if(handle) CloseHandle(handle); }
    void open(const wchar_t* name = L"Local\\UltraPilotSemaphoreV2") {
        handle = CreateFileMappingW(INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE,
                                    0, sizeof(Snapshot), name);
        if(handle) view = static_cast<Snapshot*>(MapViewOfFile(handle, FILE_MAP_ALL_ACCESS,0,0,sizeof(Snapshot)));
    }
    void write(const void* data, uint32_t count, double observed_at, bool complete) {
        if(!view) return;
        Snapshot s{};
        s.magic=0x32535055; s.version=2; s.size=sizeof(Snapshot);
        s.lifecycle=lifecycle; s.generation=++generation; s.frame=frame;
        s.observed_at=observed_at; s.flags=(active?1:0)|(complete?2:0);
        s.count=count;
        if(data && complete) memcpy(s.payload,data,sizeof(s.payload));
        sequence += 2;
        InterlockedExchange(reinterpret_cast<volatile LONG*>(&view->sequence),sequence-1);
        MemoryBarrier();
        memcpy(reinterpret_cast<char*>(view)+4,reinterpret_cast<char*>(&s)+4,sizeof(s)-8);
        InterlockedExchange(reinterpret_cast<volatile LONG*>(&view->end_sequence),sequence);
        MemoryBarrier();
        InterlockedExchange(reinterpret_cast<volatile LONG*>(&view->sequence),sequence);
    }
    void reset(bool preserve_active = false) {
        LARGE_INTEGER q; QueryPerformanceCounter(&q);
        lifecycle = uint64_t(q.QuadPart) ^ (uint64_t(GetCurrentProcessId())<<32);
        ++lifecycle; last_frame=UINT64_MAX; active=preserve_active && active;
        write(nullptr,0,clock_s(),false);
    }
    void started() { active=true; }
    void paused() { active=false; write(nullptr,0,clock_s(),false); }
    void begin_frame(uint64_t next, bool restart) {
        if(restart || (last_frame!=UINT64_MAX && next<last_frame)) reset(true);
        frame=next;
    }
    bool can_observe() { return active && frame != last_frame; }
    void observe(const void* data, uint32_t count, double time, bool complete) {
        if(!can_observe()) return;
        last_frame=frame; write(data,count,time,complete);
    }
};
inline Publisher& publisher() { static Publisher p; return p; }
}
