"""Transport reuse must leave the one actuator's physical outputs identical."""
from contextlib import contextmanager
from unittest.mock import patch
import math

from core.ipc.shared_state import LaneSnapshotReader, SharedState
from tests.test_activation_observation_binding import flow
from tests.test_lane_snapshot_transport import Transport


@contextmanager
def production_flow():
    generator = flow.__wrapped__()
    try:
        yield next(generator)
    finally:
        generator.close()


def execute(cached):
    with production_flow() as (state, truck, engine, plugin, publish, n, clock):
        transport = Transport()
        transport.update(state.values)
        state.values = transport
        engine.shared_state = SharedState(transport)
        plugin.sdk.shared_state._state = transport
        plugin.sdk.telemetry._state = transport
        plugin.sdk.controller._state = transport
        engine.shared_state.set("lane_trajectory", state.get("lane_trajectory"))
        transport.geometry_reads = 0
        original = LaneSnapshotReader.read
        read = original if cached else lambda self, data, default: data.get("lane_trajectory", default)
        with patch.object(LaneSnapshotReader, "read", read):
            publish(8, 7.)
            n()
            outputs = []
            # Straight, both signs and a gradual S transition. These are
            # prevalidated packet inputs, not a claim of measured free space.
            for index in range(80):
                dt = publish(8, 7., dt=.02)
                target = 0.0 if index < 10 else .12 * math.sin((index-10)*.09)
                packet = state.get("nav_steering_debug")
                packet.update(output=target, local_curvature=target*.04)
                state.set("nav_steering_debug", packet)
                state.set("nav_steering", target)
                plugin.on_tick(dt)
                engine._flush_controls()
                assert state.get("autopilot_active"), state.get("autopilot_disable_reason")
                outputs.append((engine.controller.steering, engine.controller.throttle,
                                engine.controller.brake))
            n()
            engine._flush_controls()
            assert engine.controller.steering == engine.controller.throttle == engine.controller.brake == 0
            return outputs, transport.geometry_reads


def test_cached_geometry_preserves_every_applied_output_and_reduces_transfers():
    before, old_reads = execute(False)
    after, new_reads = execute(True)
    assert after == before
    assert old_reads > 80
    assert new_reads == 2  # One for Engine and one for the Plugin process.
