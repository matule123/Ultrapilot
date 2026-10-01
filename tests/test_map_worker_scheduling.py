"""Exercise the actual plugin process loop, including overrun and shutdown."""
from unittest.mock import patch

import pytest

from core.plugin_manager import plugin_worker


@pytest.mark.parametrize('work_s', [.002, .027, .369])
@pytest.mark.parametrize('plugin_name', ['map', 'autopilot'])
def test_map_period_includes_work_without_catchup_or_added_sleep(work_s, plugin_name):
    clock = [10.]
    starts, waits = [], []
    stopped = []

    class Event:
        def is_set(self): return len(starts) >= 3
        def wait(self, seconds):
            waits.append(seconds)
            clock[0] += seconds

    class Worker:
        def __init__(self, sdk): self.enabled = True
        def on_start(self): pass
        def on_tick(self, dt):
            starts.append(clock[0])
            clock[0] += work_s
        def on_stop(self): stopped.append(True)

    def sleep(seconds):
        clock[0] += seconds

    with patch('core.plugin_manager.PluginSDK'), \
         patch('core.plugin_manager.logging.basicConfig'), \
         patch('core.plugin_manager.time.monotonic', side_effect=lambda: clock[0]), \
         patch('core.plugin_manager.time.sleep', side_effect=sleep):
        plugin_worker(Worker, plugin_name, {}, Event())
    expected = max(.01, work_s) if plugin_name == 'map' else work_s + .01
    assert [b-a for a,b in zip(starts,starts[1:])] == pytest.approx([expected]*2)
    assert stopped == [True]
    assert waits == pytest.approx([max(0., .01-work_s)]*3 if plugin_name == 'map' else [])
