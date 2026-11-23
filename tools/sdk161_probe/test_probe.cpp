#include "probe.cpp"
#include <cassert>
#include <iostream>
#include <limits>

SCSAPI_RESULT register_event(const scs_event_t,const scs_telemetry_event_callback_t,const scs_context_t){return SCS_RESULT_ok;}
SCSAPI_RESULT register_channel(const scs_string_t,const scs_u32_t,const scs_value_type_t,const scs_u32_t,const scs_telemetry_channel_callback_t,const scs_context_t){return SCS_RESULT_ok;}
SCSAPI_VOID log_message(const scs_log_type_t,const scs_string_t){}
int main(){
    scs_telemetry_init_params_v101_t api{};api.common.game_name="Euro Truck Simulator 2 1.59.1.3s";
    api.common.log=log_message;api.register_for_event=register_event;api.register_for_channel=register_channel;
    assert(scs_telemetry_init(0,&api)==SCS_RESULT_unsupported);
    assert(scs_telemetry_init(SCS_TELEMETRY_VERSION_1_01,&api)==SCS_RESULT_unsupported);
    assert(!probe::buffer);
    api.common.game_name="Euro Truck Simulator 2 1.61.1.9s";
    assert(scs_telemetry_init(SCS_TELEMETRY_VERSION_1_01,&api)==SCS_RESULT_ok);
    assert(probe::buffer&&probe::buffer->bytes>0);
    auto text=std::string(probe::buffer->json,probe::buffer->bytes);
    assert(text.find("\"production_ready\":false")!=std::string::npos);
    assert(text.find("\"native_layouts_verified\":false")!=std::string::npos);
    assert(text.find("\"read_only\":true")!=std::string::npos);
    probe::event(SCS_TELEMETRY_EVENT_started,nullptr,nullptr);
    scs_value_t speed{};speed.type=SCS_VALUE_TYPE_float;speed.value_float.value=3.25f;
    probe::channel("truck.speed",SCS_U32_NIL,&speed,nullptr);assert(probe::speed_valid&&probe::speed==3.25f);
    speed.value_float.value=std::numeric_limits<float>::quiet_NaN();probe::channel("truck.speed",SCS_U32_NIL,&speed,nullptr);assert(!probe::speed_valid);
    scs_value_t pose{};pose.type=SCS_VALUE_TYPE_dplacement;pose.value_dplacement.position.x=42;
    probe::channel("truck.world.placement",SCS_U32_NIL,&pose,nullptr);assert(probe::pose_valid&&probe::x==42);
    scs_telemetry_frame_start_t frame{};frame.render_time=123;
    probe::event(SCS_TELEMETRY_EVENT_frame_start,&frame,nullptr);assert(probe::frames==1&&probe::source_frame==123);
    probe::event(SCS_TELEMETRY_EVENT_paused,nullptr,nullptr);assert(probe::paused&&!probe::pose_valid&&!probe::speed_valid);
    assert(probe::buffer->sequence>0&&probe::buffer->sequence%2==0);
    scs_telemetry_shutdown();assert(!probe::buffer&&!probe::handle);
    assert(scs_telemetry_init(SCS_TELEMETRY_VERSION_1_01,&api)==SCS_RESULT_ok);assert(probe::frames==0);scs_telemetry_shutdown();
    std::cout<<"PASS: wrong version; exact 1.61; dedicated mapping; not production; speed/pose; NaN; frame; pause; shutdown; restart\n";
}
