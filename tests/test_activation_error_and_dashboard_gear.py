import logging
import struct
from types import SimpleNamespace

import pytest

from core.gear_display import gear_text
from core.hud import _gear_text
from core.sdk.scs_sdk import SCSTelemetry
from core.telemetry import Telemetry
from plugins.hud.elements.gear import Widget
from sdk.plugin_sdk import PluginSDK
from tests.test_activation_observation_binding import flow  # noqa: F401


def test_rejected_lane_activation_is_error_not_info(flow, caplog):
    state, truck, engine, plugin, publish, n, clock = flow
    packet = state.get('nav_steering_debug')
    packet.update(authority_valid=False, control_failure=(
        'live LaneId has no reachable projection on the validated trajectory'))
    state.set('nav_steering_debug', packet)
    with caplog.at_level(logging.INFO):
        n()
    records = [r for r in caplog.records if r.getMessage().startswith('Hotkey N ->')]
    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert 'live LaneId' in records[0].getMessage()
    assert not state.get('autopilot_active')
    assert engine.controller.throttle == 0


def test_successful_launch_request_remains_info(flow, caplog):
    state, truck, engine, plugin, publish, n, clock = flow
    with caplog.at_level(logging.INFO):
        n()
    records = [r for r in caplog.records if r.getMessage().startswith('Hotkey N ->')]
    assert records and records[-1].levelno == logging.INFO


@pytest.mark.parametrize('gear,dashboard,automatic,expected', [
    (0, 8, True, 'D'), (0, -1, True, 'R'), (8, 0, True, 'N'),
    (3, 5, False, '5'), (4, None, False, '4'), (0, None, True, 'N'),
    (None, None, True, '—'), (0, float('nan'), True, '—'),
])
def test_display_uses_current_dashboard_without_selector_inference(gear, dashboard, automatic, expected):
    assert gear_text({'gear': gear, 'gearDashboard': dashboard}, automatic) == expected
    assert _gear_text(gear, dashboard, automatic) == expected


def test_real_sdk_reader_normalization_and_plugin_element_keep_physical_gear():
    reader = SCSTelemetry()
    reader.mm = bytearray(reader.mmap_size)
    struct.pack_into('i', reader.mm, 504, 0)
    struct.pack_into('i', reader.mm, 508, 8)
    raw = reader.update()
    telemetry = Telemetry.__new__(Telemetry)
    normalized = telemetry._normalize_sdk(raw)
    truck = normalized['truck']
    assert truck['gear'] == 0
    assert truck['gearDashboard'] == 8
    sdk = PluginSDK({'telemetry': normalized, 'ets2_transmission_mode': {'mode': 0}}, 'hud')
    widget = Widget(SimpleNamespace(sdk=sdk))
    widget.draw(0, 100, 50)
    assert widget.data[-1]['text'] == 'D'
    sdk.set('telemetry', {'truck': {'gear': 0, 'gearDashboard': 0}})
    widget.data.clear()
    widget.draw(0, 100, 50)
    assert widget.data[-1]['text'] == 'N'
