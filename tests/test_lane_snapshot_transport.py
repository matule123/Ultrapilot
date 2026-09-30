"""Immutable geometry must not be retransferred on every control tick."""
import copy

import pytest

from core.ipc.shared_state import SharedState
from sdk.plugin_sdk import PluginSDK
from plugins.autopilot.main import Plugin as Autopilot


class Transport(dict):
    def __init__(self):
        super().__init__()
        self.geometry_reads = 0
        self.on_geometry_read = None

    def get(self, key, default=None):
        if key == "lane_trajectory":
            self.geometry_reads += 1
            if self.on_geometry_read:
                self.on_geometry_read()
        return copy.deepcopy(super().get(key, default))


@pytest.mark.parametrize("consumer", [SharedState, PluginSDK])
def test_one_geometry_transfer_per_publication_not_per_control_tick(consumer):
    transport = Transport()
    writer = SharedState(transport)
    reader = consumer(transport)
    snapshot = {"valid": True, "revision": 7, "route_build_id": "build",
                "points": [[i, 10., i] for i in range(4128)]}
    writer.update_batch({"lane_trajectory": snapshot})
    for _ in range(12):
        assert reader.get("lane_trajectory") == snapshot
    assert transport.geometry_reads == 1


@pytest.mark.parametrize("writer_type", [SharedState, PluginSDK])
def test_same_revision_rebase_invalidation_and_returned_copy(writer_type):
    transport = Transport()
    writer, reader = writer_type(transport), SharedState(transport)
    publisher = writer.shared_state if isinstance(writer, PluginSDK) else writer
    snapshot = {"valid": True, "revision": 7, "source_gps_uids": [1, 2, 3],
                "points": [[0., 10., 0.], [0., 10., 3.]]}
    writer.set("lane_trajectory", snapshot)
    captured = reader.get("lane_trajectory")
    captured["points"][0][0] = 1000.
    assert reader.get("lane_trajectory")["points"][0][0] == 0.
    publisher.update_batch({"lane_trajectory": dict(snapshot, source_gps_uids=[2, 3])})
    assert reader.get("lane_trajectory")["source_gps_uids"] == [2, 3]
    writer.set("lane_trajectory", dict(snapshot, valid=False))
    assert not reader.get("lane_trajectory")["valid"]


def test_publication_during_geometry_read_cannot_cache_under_previous_token():
    transport = Transport()
    writer, reader = SharedState(transport), SharedState(transport)
    writer.set("lane_trajectory", {"revision": 7})

    def replace():
        transport.on_geometry_read = None
        writer.set("lane_trajectory", {"revision": 8})

    transport.on_geometry_read = replace
    assert reader.get("lane_trajectory")["revision"] == 8
    assert reader.get("lane_trajectory")["revision"] == 8


def test_legacy_transport_without_publication_token_never_caches():
    transport = Transport()
    reader = SharedState(transport)
    transport["lane_trajectory"] = {"revision": 7}
    assert reader.get("lane_trajectory")["revision"] == 7
    transport["lane_trajectory"] = {"revision": 8}
    assert reader.get("lane_trajectory")["revision"] == 8


def test_autopilot_cache_rejects_same_build_invalidated_snapshot():
    transport = Transport()
    sdk = PluginSDK(transport)
    identity = {key: key for key in ("navigation_intent_id", "route_build_id",
        "source_game_session_id", "source_map_key", "source_dataset_fingerprint",
        "lane_path_fingerprint")}
    sdk.set("lane_trajectory", dict(identity, revision=7, valid=True))
    sdk.set("nav_steering_debug", dict(identity, authority_revision=7))
    plugin = Autopilot(sdk)
    assert plugin._read_navigation_inputs()[0]["valid"]
    sdk.set("lane_trajectory", dict(identity, revision=7, valid=False))
    assert not plugin._read_navigation_inputs()[0]["valid"]
