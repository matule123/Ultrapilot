// Own-process tests only. Never opens ETS2 or invokes a game method.
#include <Windows.h>
#include <cassert>
#include <cstdio>
#include <cstddef>
#include <string>
#include "scssdk_telemetry.h"
#include "up161_guard.hpp"
#include "prism/management/item/prefab_item.hpp"
#include "prism/management/item/segment.hpp"
#include "prism/navigation/gps_manager.hpp"
#include "prism/camera/camera_manager.hpp"
#include "prism/traffic/traffic.hpp"
#include "prism/traffic/objects/traffic_ai_vehicle.hpp"
#include "prism/traffic/objects/traffic_light.hpp"
#include "prism/traffic/objects/traffic_semaphore_actor.hpp"
#include "core.hpp"
using namespace ets2la_plugin;
using namespace ets2la_plugin::prism;
static_assert(offsetof(prefab_item_t,nodes)==0x60);
static_assert(offsetof(prefab_item_t,origin_idx)==0x120);
static_assert(offsetof(prefab_item_t,prefab_payload)==0x128);
static_assert(offsetof(segment_t,semaphore_instances)==0x80);
static_assert(offsetof(gps_manager_t,simple_route_source)==8);
static_assert(offsetof(simple_route_source_t,route_task)==0x20);
static_assert(offsetof(route_task_t,physical_route_items)==0x50);
static_assert(offsetof(camera_manager_u,cameras)==0x30);
static_assert(offsetof(traffic_u,spawned_vehicles_1)==0xf0);
static_assert(offsetof(traffic_u,traffic_objects_1)==0x1e0);
static_assert(offsetof(traffic_ai_vehicle_t,physics)==0x238);
static_assert(offsetof(traffic_light_t,state)==0x70);
static_assert(offsetof(traffic_light_t,state_time_remaining)==0xb8);
static_assert(offsetof(traffic_semaphore_actor_t,traffic_rule)==0x100);
static_assert(sizeof(RouteMemData)==96000);
static_assert(sizeof(TrafficMemData)==6960);
static_assert(sizeof(ParkedVehiclesMemData)==1720);
static_assert(sizeof(SemaphoreMemData)==1920);

SCSAPI_VOID logger(scs_log_type_t,const scs_string_t) {}
int main(int argc,char** argv) {
    assert(argc==2);
    assert(!up161::image_matches()); // this host is NOT the pinned game
    assert(!up161::readable(nullptr,8));
    int local=42;assert(up161::readable(&local,sizeof(local)));
    struct {uint64_t size,capacity;int* value;} array{1,2,&local};
    assert(up161::bounded(array,2));array.size=3;assert(!up161::bounded(array,2));
    array.size=0;array.value=nullptr;assert(up161::bounded(array,2));
    HMODULE dll=LoadLibraryA(argv[1]);assert(dll);
    using Init=scs_result_t(__stdcall*)(scs_u32_t,const scs_telemetry_init_params_t*);
    using Stop=void(__stdcall*)();
    auto init=reinterpret_cast<Init>(GetProcAddress(dll,"scs_telemetry_init"));
    auto stop=reinterpret_cast<Stop>(GetProcAddress(dll,"scs_telemetry_shutdown"));assert(init&&stop);
    assert(init(SCS_TELEMETRY_VERSION_1_01,nullptr)==SCS_RESULT_unsupported);
    scs_telemetry_init_params_v101_t params{};params.common.log=logger;
    params.common.game_name="Euro Truck Simulator 2 1.59.2.0s";
    assert(init(SCS_TELEMETRY_VERSION_1_01,&params)!=SCS_RESULT_ok);stop();stop();
    params.common.game_name="Euro Truck Simulator 2 1.61.1.9s";
    assert(init(SCS_TELEMETRY_VERSION_1_01,&params)!=SCS_RESULT_ok); // exact EXE guard rejects test host
    stop();stop();FreeLibrary(dll);
    std::puts("PASS: compiled ABI offsets, exact-image rejection, API rejection, init-failure cleanup, no game execution");
}
