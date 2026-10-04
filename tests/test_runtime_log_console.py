import logging

from core import logger


def test_console_line_matches_ets2la_tag_time_and_message_spacing():
    record = logging.LogRecord("Engine", logging.INFO, "engine.py", 42,
                               "Engine started", (), None)
    output = logger._ETS2LAFormatter().format(record)
    assert "\033[38;2;0;175;0m[INF]\033[0m " in output
    assert "  \033[38;2;204;204;204mEngine started\033[0m" in output
    assert "engine.py:42" in output


def test_reference_columns_colours_and_real_source_are_preserved():
    from io import StringIO
    from rich.console import Console
    stream = StringIO()
    console = Console(file=stream, width=120, force_terminal=True, color_system="truecolor",
                      no_color=False, legacy_windows=False)
    record = logging.LogRecord("Engine", logging.WARNING, "engine.py", 42,
                               "Freshness check rejected this packet", (), None)
    logger.ReferenceConsoleHandler(console).emit(record)
    output = stream.getvalue()
    assert "[WRN]" in output
    assert "engine.py:42" in output
    assert "38;2;215;175;0" in output
    plain = __import__('re').sub(r"\x1b\[[0-9;]*m", "", output).rstrip()
    assert plain.endswith("engine.py:42")
    assert plain.index("engine.py:42") > plain.index("rejected")


def test_plain_source_metadata_preserves_diagnostic_dictionary_tail():
    import ast
    value = {"action": "observe", "sdk_frame_us": 17}
    record = logging.LogRecord("Engine", logging.INFO, "engine.py", 42,
                               "Drive boundary: %s", (value,), None)
    formatted = logger._plain_formatter().format(record)
    assert "[source:engine.py:42] Drive boundary:" in formatted
    assert ast.literal_eval(formatted.split("Drive boundary: ", 1)[1]) == value
    assert "\033" not in formatted


def test_reference_exception_has_code_frame_without_local_values():
    from io import StringIO
    from rich.console import Console
    import sys
    stream = StringIO()
    console = Console(file=stream, width=100, force_terminal=True, color_system="truecolor",
                      no_color=False, legacy_windows=False)
    try:
        private_value = "".join(("DO_NOT_", "RENDER_LOCAL_VALUES"))
        raise ValueError("isolated rendering check")
    except ValueError:
        record = logging.LogRecord("test", logging.ERROR, __file__, 1,
                                   "Diagnostic failed", (), sys.exc_info())
        logger.ReferenceConsoleHandler(console).emit(record)
    output = stream.getvalue()
    assert "Traceback" in output
    assert "ValueError" in output
    assert "╭" in output and "╯" in output
    assert private_value not in output


def test_map_loading_receipts_are_measured_not_invented(monkeypatch):
    from core.map_load_log import MapLoadLog, MAP_WAIT_TEXT, hud_map_loading_text
    values = iter([0.0, 1.23, 1.5])
    ram = iter([100.0, 106.0, 105.0])
    calls = []
    monkeypatch.setattr(logging, "info", lambda *args, **kwargs: calls.append((args, kwargs)))
    receipt = MapLoadLog(clock=lambda: next(values), memory=lambda: next(ram))
    receipt.loaded("nodes", 24)
    receipt.loaded("roads", 12)
    assert calls[0][0] == (MAP_WAIT_TEXT,)
    assert calls[1][1]["extra"]["load_elapsed_cs"] == 123
    assert calls[1][1]["extra"]["load_ram_mb"] == 6
    assert calls[2][1]["extra"]["load_ram_mb"] == -1
    assert hud_map_loading_text({"active": True}) == MAP_WAIT_TEXT
    assert hud_map_loading_text({"active": False}) == ""


def test_real_map_loader_receipts_and_cache_keep_geometry(tmp_path, caplog):
    import json
    from core.navigation.road_network import RoadNetwork
    files = {
        "nodes": [{"uid": 1, "x": 0, "y": 0, "z": 3},
                  {"uid": 2, "x": 10, "y": 0, "z": 3}],
        "roads": [{"uid": 3, "startNodeUid": 1, "endNodeUid": 2, "length": 10}],
        "graph": [[1, {"forward": [{"nodeId": 2}], "backward": []}],
                  [2, {"forward": [], "backward": [{"nodeId": 1}]}]],
    }
    for name, content in files.items():
        (tmp_path / (name + ".json")).write_text(json.dumps(content), encoding="utf-8")
    caplog.set_level(logging.INFO)
    cold = RoadNetwork()
    assert cold.load(str(tmp_path))
    receipts = [record for record in caplog.records
                if getattr(record, "map_load_receipt", False)]
    assert [(record.load_kind, record.load_count) for record in receipts[:3]] == [
        ("nodes", 2), ("roads", 1), ("forward navigation entries", 1)]
    warm = RoadNetwork()
    assert warm.load(str(tmp_path))
    assert warm.nodes == cold.nodes
    assert warm.segments == cold.segments
    assert warm.fwd == cold.fwd
    assert any(getattr(record, "load_kind", "") == "nodes (cached road network)"
               for record in caplog.records)


def test_plugin_summary_uses_only_identified_plugin_messages():
    lines = [
        "2026-08-08 12:00:00,000 INFO     PluginManager Loaded plugin: autopilot",
        "2026-08-08 12:00:01,000 WARNING  autopilot Camera confidence low",
        "2026-08-08 12:00:02,000 ERROR    Engine [plugin:map] worker crashed",
        "2026-08-08 12:00:03,000 CRITICAL Engine Plugin 'map' restart failed",
        "2026-08-08 12:00:04,000 WARNING  Engine unrelated runtime warning",
    ]

    issues = logger.collect_plugin_issues(lines=lines)

    assert issues["autopilot"]["warnings"] == 1
    assert issues["map"]["errors"] == 2
    assert "engine" not in issues


def test_plugin_summary_has_separate_warning_and_error_frames():
    issues = {
        "autopilot": {"warnings": 2, "errors": 0,
                      "warning_messages": ["confidence low"],
                      "error_messages": []},
        "map": {"warnings": 0, "errors": 1,
                "warning_messages": [], "error_messages": ["worker crashed"]},
    }

    output = logger.format_plugin_issue_summary(issues, colour=False)

    assert "autopilot" in output
    assert "map" in output
    assert "Errors: 1" in output
    assert "Warnings: 2" in output
    assert "PLUGINY S UPOZORNENÍM" not in output


def test_runtime_log_waits_for_enter_only_when_plugin_has_issue(monkeypatch):
    prompts = []
    monkeypatch.setattr(logger, "_SESSION_PROMPT_SHOWN", False)
    monkeypatch.setattr(logger, "collect_plugin_issues", lambda _offset: {
        "map": {"warnings": 1, "errors": 0,
                "warning_messages": ["missing optional field"],
                "error_messages": []},
    })

    logger.finish_session_log(10, input_fn=lambda prompt: prompts.append(prompt),
                              colour=False)
    assert len(prompts) == 1
    assert "Enter" in prompts[0]

    # A duplicate shutdown/finalizer call must not consume a second Enter.
    logger.finish_session_log(10, input_fn=lambda prompt: prompts.append(prompt),
                              colour=False)
    assert len(prompts) == 1

    prompts.clear()
    monkeypatch.setattr(logger, "collect_plugin_issues", lambda _offset: {})
    logger.finish_session_log(10, input_fn=lambda prompt: prompts.append(prompt),
                              colour=False)
    assert prompts == []


def test_startup_banner_is_not_a_regular_timestamped_log_line(capsys):
    logger.print_startup_banner("0.4.2", "abcdef123")
    output = capsys.readouterr().out
    assert "UltraPilot  v0.4.2  ·  abcdef1" in output
    assert "╭" not in output
    assert "INFO" not in output
