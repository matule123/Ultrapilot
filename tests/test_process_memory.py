"""Process scope and startup receipts; no application or game is launched."""
from types import SimpleNamespace
from unittest.mock import Mock

from core import process_memory as memory
from core import logger


def test_memory_uses_published_root_and_exact_plugin_pids(monkeypatch):
    processes = {}
    for pid, rss in ((10, 20), (11, 30), (12, 40), (99, 900)):
        processes[pid] = SimpleNamespace(
            pid=pid, memory_info=lambda rss=rss: SimpleNamespace(rss=rss * 1_000_000))
    processes[10].children = lambda recursive: [processes[11], processes[12]]
    fake = SimpleNamespace(Process=lambda pid: processes[pid], Error=RuntimeError)
    monkeypatch.setattr(memory, "psutil", fake)
    monkeypatch.setattr(memory.os, "getpid", lambda: 11)
    state = {"runtime_root_pid": 10, "plugin_processes": {"map": 12}}
    total, cpu, plugins = memory.collect_memory(state)
    assert total == 90  # UI/plugin counted once, unrelated PID 99 excluded.
    assert cpu is None  # A fresh Process cannot yield a meaningful CPU sample.
    assert plugins == [("Map", 40, None)]
    assert memory.collect_memory({}) == (30, None, [])


def test_missing_memory_is_unknown_not_zero(monkeypatch):
    monkeypatch.setattr(memory, "psutil", None)
    assert memory.resident_mb() is None
    assert memory.collect_memory({}) == (None, None, [])


def test_startup_ram_is_pale_blue_in_console_plain_in_log(monkeypatch, capsys):
    info = Mock()
    monkeypatch.setattr(logger.logging, "info", info)
    monkeypatch.setattr(logger, "ensure_windows_console", lambda: None)
    logger.log_plugin_ready("map", 45.25)
    text = info.call_args.args[0]
    assert text == "Plugin Map started successfully. · RAM: 45.2 MB (RSS)"
    assert "\033" not in text
    record = logger.logging.LogRecord("map", 20, "main.py", 4, text, (), None)
    record.plugin_startup_memory = True
    assert "\033[38;2;186;230;253m · RAM: 45.2 MB (RSS)" in logger._ETS2LAFormatter().format(record)


def test_worker_reports_ram_after_start_once_outside_tick(monkeypatch):
    from core import plugin_manager as manager
    events = []
    class Plugin:
        def __init__(self, sdk):
            pass
        def on_start(self):
            events.append("start")
        def on_stop(self):
            events.append("stop")
    monkeypatch.setattr(manager, "PluginSDK", lambda *_: None)
    monkeypatch.setattr(manager.logging, "basicConfig", lambda **_: None)
    monkeypatch.setattr(logger, "setup", lambda **_: None)
    monkeypatch.setattr(memory, "resident_mb", lambda: 55)
    monkeypatch.setattr(logger, "log_plugin_ready",
                        lambda name, value: events.append((name, value)))
    manager.plugin_worker(Plugin, "map", {}, SimpleNamespace(is_set=lambda: True))
    assert events == ["start", ("map", 55), "stop"]
