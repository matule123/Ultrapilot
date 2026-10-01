"""Exercise actual Map calculations through PluginSDK to physical Engine writes."""
import math
from dataclasses import replace

import pytest

from plugins.map.main import Plugin as MapPlugin
from sdk.plugin_sdk import PluginSDK
from tests.test_cached_control_output import production_flow
from tests.test_lane_authority_integration import build_map_plugin, Tags
from tests.test_stage5b1_vehicle_profile import observation
from core.vehicle_profile import VehicleProfileProvider


@pytest.mark.parametrize("lateral_sign", [-1, 1])
@pytest.mark.parametrize("profile_observer", [False, True])
def test_fresh_map_packets_reach_physical_output_without_sparse_targets(lateral_sign, profile_observer):
    with production_flow() as (state, truck, engine, autopilot, _, n, clock):
        source, _, point = build_map_plugin()
        state.set("game_route_node_uids", [1, 2, 3])
        truck.update(x=point.x, y=point.y, z=point.z, rotation=point.heading,
                     referenceGeometry={"valid": True, "source": "fixture",
                                        "wheelbase_m": 3.8, "reference_ahead_m": 2.1},
                     roadWheelAnglesRad=[0.0])
        map_plugin = MapPlugin(PluginSDK(state.values, "map"))
        map_plugin.on_start()
        map_plugin.tags = Tags()
        map_plugin.road_net = source.road_net
        map_plugin._net_attempted = True
        profiles = VehicleProfileProvider()
        writes = []
        writer = engine.controller.set_steering

        def physical_write(value):
            writes.append((clock[0], value))
            writer(value)

        engine.controller.set_steering = physical_write

        def observe(index):
            clock[0] += .02
            truck.update(gear=8, speed=7., sdkFrameTimeUs=1_000_000+index*20_000,
                         x=point.x+lateral_sign*.06*math.sin(index*.06),
                         z=point.z+index*.14)
            state.update_batch(engine._vehicle_telemetry_payload(
                {"truck": truck, "raw": {"sdkActive": True}}, clock[0]))
            if profile_observer:
                # The real telemetry producer publishes this dataclass, not a
                # dictionary with no observation.frame (which hides repeated
                # evidence jobs behind the worker's duplicate-frame gate).
                o = replace(observation(now=clock[0]),
                            sdk_frame_us=truck["sdkFrameTimeUs"])
                state.set("vehicle_profile_snapshot", profiles.update(o, clock[0]))
            mode = state.get("ets2_transmission_mode")
            mode["observed_at"] = clock[0]
            state.set("ets2_transmission_mode", mode)

        try:
            observe(0)
            map_plugin.on_tick(.02)
            assert state.get("nav_active"), state.get("navigation_failure_reason")
            autopilot.on_tick(.02)  # Publish readiness for this newly built route.
            n()
            packets = []
            for index in range(1, 101):
                observe(index)
                map_plugin.on_tick(.02)
                packet = state.get("nav_steering_debug")
                assert packet["authority_valid"], packet.get("control_failure")
                assert packet["sdk_frame_us"] == truck["sdkFrameTimeUs"]
                assert packet["observation_timestamp"] == clock[0]
                autopilot.on_tick(.02)
                engine._flush_controls()
                assert state.get("autopilot_active"), state.get("autopilot_disable_reason")
                assert engine.controller.throttle > 0
                packets.append(packet)
            assert len(writes) == 100
            assert all(b["calculation_sequence"] == a["calculation_sequence"]+1
                       for a, b in zip(packets, packets[1:]))
            assert all(b["computed_at"]-a["computed_at"] == pytest.approx(.02)
                       for a, b in zip(packets, packets[1:]))
            # This is a deterministic unblocked-flow check, not a wall-clock
            # performance assertion or proof that live scheduling is fixed.
            assert max(abs(b[1]-a[1]) for a, b in zip(writes, writes[1:])) < .0035
            original_time = packets[-1]["observation_timestamp"]
            clock[0] += .501
            map_plugin.on_tick(.02)
            autopilot.on_tick(.02)
            engine._flush_controls()
            assert state.get("vehicle_envelope_snapshot")["timestamp"] == original_time
            assert not state.get("nav_active")
            assert engine.controller.throttle == 0
            n() if state.get("autopilot_active") else None
            engine._flush_controls()
            assert engine.controller.steering == engine.controller.throttle == 0
        finally:
            map_plugin._maneuver_evidence_worker.close()
            map_plugin._maneuver_reference_mux.close()
            source._maneuver_evidence_worker.close()
            source._maneuver_reference_mux.close()
