"""Arm and inspect the fail-closed real-evidence diagnostic collector.

This tool changes only an explicit diagnostics setting and its control file.
It never writes maneuver evidence settings, installs artifacts or grants
runtime authority. Run ``arm`` while UltraPilot is stopped, then start the
application normally. ``finish`` and ``cancel`` are worker commands and may be
issued while collection is running.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.navigation.evidence_diagnostics import (
    COLLECTION_PURPOSES, SCHEMA_VERSION, atomic_json_write, inspect_collection,
    read_json,
)


def _output_root(value):
    root = Path(value).resolve()
    if root.name != "evidence-diagnostics":
        raise ValueError("OUTPUT_MUST_BE_DEDICATED_EVIDENCE_DIAGNOSTICS_DIRECTORY")
    return root


def _next_sequence(root):
    try:
        previous = read_json(root / "control.json", max_bytes=64 * 1024)
        old = int(previous.get("sequence", 0))
    except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
        old = 0
    return max(old + 1, time.time_ns())


def _control(root, action, collection_id=None, **values):
    document = {"schema_version": SCHEMA_VERSION,
                "sequence": _next_sequence(root), "action": action,
                "collection_id": collection_id, **values}
    atomic_json_write(root / "control.json", document)
    return document


def _settings(path):
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError("INVALID_SETTINGS_DOCUMENT")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    arm = commands.add_parser("arm")
    arm.add_argument("--settings", required=True)
    arm.add_argument("--output", required=True)
    arm.add_argument("--collection-id", required=True)
    arm.add_argument("--purpose", required=True, choices=COLLECTION_PURPOSES)
    arm.add_argument("--duration", type=float, default=180.0)
    arm.add_argument("--sample-period", type=float, default=0.1)
    arm.add_argument("--capacity", type=int, default=1800)
    arm.add_argument("--max-sessions", type=int, default=8)

    for name in ("finish", "cancel"):
        command = commands.add_parser(name)
        command.add_argument("--output", required=True)
        command.add_argument("--collection-id", required=True)

    disable = commands.add_parser("disable")
    disable.add_argument("--settings", required=True)
    disable.add_argument("--output", required=True)

    status = commands.add_parser("status")
    status.add_argument("--output", required=True)

    inspect = commands.add_parser("inspect")
    inspect.add_argument("collection")

    args = parser.parse_args(argv)
    if args.command == "inspect":
        print(json.dumps(inspect_collection(args.collection), indent=2))
        return 0
    root = _output_root(args.output)
    if args.command == "status":
        try:
            value = read_json(root / "status.json", max_bytes=64 * 1024)
        except FileNotFoundError:
            value = {"schema_version": 1, "state": "DISABLED",
                     "reason": "NO_DIAGNOSTIC_WORKER_STATUS",
                     "confirmed": False, "runtime_authorized": False}
        print(json.dumps(value, indent=2))
        return 0
    if args.command == "arm":
        if not 30 <= args.duration <= 600:
            raise ValueError("DURATION_MUST_BE_30_TO_600_SECONDS")
        if not 0.05 <= args.sample_period <= 0.5:
            raise ValueError("SAMPLE_PERIOD_MUST_BE_0.05_TO_0.5_SECONDS")
        if not 30 <= args.capacity <= 3600:
            raise ValueError("CAPACITY_MUST_BE_30_TO_3600")
        if not 1 <= args.max_sessions <= 32:
            raise ValueError("MAX_SESSIONS_MUST_BE_1_TO_32")
        settings_path = Path(args.settings).resolve()
        settings = _settings(settings_path)
        settings["maneuver_evidence_diagnostics"] = {
            "enabled": True, "output_directory": str(root),
            "capacity": args.capacity, "max_sessions": args.max_sessions,
        }
        atomic_json_write(settings_path, settings)
        command = _control(root, "arm", args.collection_id,
            purpose=args.purpose, max_duration_s=args.duration,
            sample_period_s=args.sample_period)
        print(json.dumps({"armed": True, "runtime_authorized": False,
                          "confirmed": False, "restart_required_if_running": True,
                          "control": command}, indent=2))
        return 0
    if args.command in ("finish", "cancel"):
        command = _control(root, args.command, args.collection_id)
        print(json.dumps({"command_written": command,
                          "runtime_authorized": False}, indent=2))
        return 0
    settings_path = Path(args.settings).resolve()
    settings = _settings(settings_path)
    config = dict(settings.get("maneuver_evidence_diagnostics", {}) or {})
    config["enabled"] = False
    settings["maneuver_evidence_diagnostics"] = config
    _control(root, "disable")
    atomic_json_write(settings_path, settings)
    print(json.dumps({"disabled": True, "runtime_authorized": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
