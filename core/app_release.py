"""Version-change announcements, independent of commit-only updates."""
import ast
import hashlib
import json
import logging
import os
from pathlib import Path
import re


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError("Invalid release version")
    return tuple(map(int, value.split(".")))


def plugin_versions(root):
    """Read declarations without importing or starting any plugin."""
    result = {}
    for path in sorted((Path(root) / "plugins").glob("*/main.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "VERSION" for t in node.targets):
                value = ast.literal_eval(node.value)
                _version(value)
                result[path.parent.name] = value
                break
    return result


def plugin_history(text, previous, current):
    """Keep every intermediate plugin release, not just the newest bullets."""
    history = {}
    plugin = release = None
    for line in text.splitlines():
        if line.startswith("## "):
            plugin = line[3:].strip().casefold()
            release = None
        elif line.startswith("### "):
            match = re.match(r"### (\d+\.\d+\.\d+)\b", line)
            release = match[1] if match else None
            if plugin and release:
                history.setdefault(plugin, {}).setdefault(release, [])
        elif line.startswith("- ") and plugin and release:
            history[plugin][release].append(line[2:].strip())
    result = []
    for name, end in sorted(current.items()):
        start = previous.get(name)
        if start == end:
            continue
        releases = []
        for version, changes in sorted(history.get(name.casefold(), {}).items(),
                                       key=lambda item: _version(item[0])):
            if _version(version) <= _version(end) and (
                    start is None or _version(version) > _version(start)):
                releases.append({"version": version, "changes": changes})
        result.append({"name": name, "previous_version": start,
                       "version": end, "releases": releases})
    return result


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def release_notice(root, cache_dir, version, commit):
    """Baseline first launch; retain a notice until the user dismisses it.

    Same-version commits never advance the plugin baseline. State is scoped to
    the installation so an old worktree cannot consume another install's notice.
    """
    _version(version)
    root = Path(root).resolve()
    key = hashlib.sha256(os.path.normcase(str(root)).encode()).hexdigest()[:20]
    path = Path(cache_dir) / ("app-release-" + key + ".json")
    try:
        current = plugin_versions(root)
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        if state is None:
            _write(path, {"version": version, "plugins": current, "pending": None})
            return None
        _version(state["version"])
        if state["version"] == version:
            return state.get("pending")
        if _version(version) < _version(state["version"]):
            return None  # Downgrades are not new releases; retain the baseline.
        metadata_path = root / "assets" / "app_release_notes.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        entries = metadata.get("releases", {})
        changes = []
        for number, entry in sorted(entries.items(), key=lambda item: _version(item[0])):
            if _version(state["version"]) < _version(number) <= _version(version):
                changes.extend(entry.get("changes", []))
        # A published baseline can override observed versions for commit-updated installs.
        baseline = entries.get(state["version"], {}).get("plugin_versions", state["plugins"])
        history = (root / "PLUGIN_CHANGELOG.md").read_text(encoding="utf-8")
        notice = {"version": version, "previous_version": state["version"],
                  "commit": commit, "changes": changes,
                  "plugins": plugin_history(history, baseline, current),
                  "ack_path": str(path)}
        _write(path, {"version": version, "plugins": current, "pending": notice})
        return notice
    except Exception:
        logging.getLogger(__name__).exception("App release announcement unavailable")
        return None  # Release notes must never prevent application startup.


def acknowledge_release(notice):
    path = Path(notice["ack_path"])
    state = json.loads(path.read_text(encoding="utf-8"))
    if (state.get("pending") or {}).get("version") == notice["version"]:
        state["pending"] = None
        _write(path, state)
