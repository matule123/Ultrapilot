import json

import pytest
from PyQt6.QtWidgets import QApplication, QLabel

from core.app_release import acknowledge_release, plugin_history, release_notice
from core import update_check
from UI.update_widget import AppReleaseDialog


def prepare(tmp_path):
    root = tmp_path / "install"
    (root / "plugins" / "map").mkdir(parents=True)
    (root / "assets").mkdir()
    (root / "plugins" / "map" / "main.py").write_text(
        'class Plugin:\n    VERSION = "1.0.0"\n', encoding="utf-8")
    (root / "assets" / "app_release_notes.json").write_text(
        json.dumps({"releases": {"0.5.0": {"changes": ["New settings"]}}}),
        encoding="utf-8")
    (root / "PLUGIN_CHANGELOG.md").write_text(
        '## Map\n### 1.0.2\n- Second fix\n### 1.0.1\n- First fix\n'
        '### 1.0.0\n- Baseline\n', encoding="utf-8")
    return root, tmp_path / "cache"


def test_commit_updates_preserve_baseline_and_all_plugin_releases(tmp_path):
    root, cache = prepare(tmp_path)
    assert release_notice(root, cache, "0.4.2", "first") is None
    (root / "plugins" / "map" / "main.py").write_text(
        'class Plugin:\n    VERSION = "1.0.2"\n', encoding="utf-8")
    assert release_notice(root, cache, "0.4.2", "second") is None
    notice = release_notice(root, cache, "0.5.0", "third")
    assert notice["changes"] == ["New settings"]
    assert [r["version"] for r in notice["plugins"][0]["releases"]] == ["1.0.1", "1.0.2"]
    assert release_notice(root, cache, "0.5.0", "third") == notice
    acknowledge_release(notice)
    acknowledge_release(notice)  # idempotent
    assert release_notice(root, cache, "0.5.0", "fourth") is None
    assert release_notice(root, cache, "0.4.2", "old") is None


def test_installs_are_independent_and_corrupt_state_cannot_break_startup(tmp_path):
    root, cache = prepare(tmp_path)
    release_notice(root, cache, "0.4.2", "a")
    path = next(cache.glob("app-release-*.json"))
    path.write_text("broken", encoding="utf-8")
    assert release_notice(root, cache, "0.5.0", "b") is None
    other, _ = prepare(tmp_path / "other")
    assert release_notice(other, cache, "0.5.0", "b") is None


def test_missing_history_and_unchanged_plugins_are_honest():
    result = plugin_history("", {"map": "1.0.0", "acc": "1.0.0"},
                            {"map": "1.0.2", "acc": "1.0.0"})
    assert len(result) == 1
    assert result[0]["releases"] == []


def test_published_baseline_and_skipped_app_versions(tmp_path):
    root, cache = prepare(tmp_path)
    (root / "plugins" / "map" / "main.py").write_text(
        'VERSION = "1.0.2"\n', encoding="utf-8")
    release_notice(root, cache, "0.4.2", "a")
    metadata = {"releases": {
        "0.4.2": {"plugin_versions": {"map": "1.0.0"}},
        "0.5.0": {"changes": ["First"]}, "0.6.0": {"changes": ["Second"]}}}
    (root / "assets" / "app_release_notes.json").write_text(json.dumps(metadata))
    notice = release_notice(root, cache, "0.6.0", "c")
    assert notice["changes"] == ["First", "Second"]
    assert len(notice["plugins"][0]["releases"]) == 2


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_dialog_sections_plain_text_and_versions(theme):
    app = QApplication.instance() or QApplication([])
    notice = {"version": "0.5.0", "previous_version": "0.4.2", "commit": "abc123",
              "intro": "Welcome to UltraPilot", "limitations": ["Requires compatible DLL"],
              "changes": ["Better settings"], "plugins": [{"name": "map",
              "previous_version": "1.0.0", "version": "1.0.2", "releases": [
                  {"version": "1.0.1", "changes": ["First fix"]},
                  {"version": "1.0.2", "changes": ["Second fix"]}]}]}
    dialog = AppReleaseDialog(notice, {"ui_theme": theme})
    texts = [label.text() for label in dialog.findChildren(QLabel)]
    for text in ("v0.5.0 je tu!", "Aktualizácie UltraPilotu", "Zmeny pluginov",
                 "v1.0.1", "v1.0.2", "•  First fix", "•  Second fix",
                 "Welcome to UltraPilot", "Dôležité vedieť", "•  Requires compatible DLL"):
        assert text in texts
    assert not dialog.isModal()
    dialog.close()
    app.processEvents()


def test_release_assets_are_runtime_files_and_version_is_current():
    assert update_check.VERSION == "0.5.0"
    # Assets are already shipped by the filtered updater.
    assert "assets" in update_check._RUNTIME_DIRS


def test_first_launch_with_published_predecessor_shows_welcome_once(tmp_path):
    root, cache = prepare(tmp_path)
    metadata = {"releases": {
        "0.4.2": {"plugin_versions": {}},
        "0.5.0": {"previous_version": "0.4.2", "intro": "Welcome",
                  "changes": ["Changed"], "limitations": ["Scope"]}}}
    (root / "assets" / "app_release_notes.json").write_text(json.dumps(metadata))
    notice = release_notice(root, cache, "0.5.0", "c")
    assert notice["previous_version"] == "0.4.2"
    assert notice["intro"] == "Welcome"
    assert notice["limitations"] == ["Scope"]
    acknowledge_release(notice)
    assert release_notice(root, cache, "0.5.0", "c") is None


def test_unversioned_baseline_includes_shared_plugin_table():
    text = '## Other plugins — 1.0.0 baseline\n| acc | 1.0.0 | Existing ACC. |\n'
    result = plugin_history(text, {}, {"acc": "1.0.0"})
    assert result[0]["releases"] == [{"version": "1.0.0", "changes": ["Existing ACC."]}]


def test_shipped_release_snapshot_matches_all_plugins():
    from pathlib import Path
    from core.app_release import plugin_versions
    root = Path(__file__).resolve().parents[1]
    metadata = json.loads((root / "assets" / "app_release_notes.json").read_text(encoding="utf-8"))
    # A published app-release snapshot is historical: later commit-only plugin
    # fixes must not rewrite the baseline used by the next app release.
    snapshot = metadata["releases"]["0.5.0"]["plugin_versions"]
    current = plugin_versions(root)
    assert set(snapshot) == set(current)
    for name, version in snapshot.items():
        assert tuple(map(int, version.split('.'))) <= tuple(map(int, current[name].split('.')))
    history = plugin_history((root / "PLUGIN_CHANGELOG.md").read_text(encoding="utf-8"),
                             {}, plugin_versions(root))
    assert len(history) == 12
    assert all(plugin["releases"] for plugin in history)
    # Every current plugin release must be readable by the welcome dialog,
    # including Autopilot; combined plugin/version headings are not its schema.
    assert all(plugin["releases"][-1]["version"] == current[plugin["name"]]
               for plugin in history)
    map_history = [entry["version"] for entry in next(
        p for p in history if p["name"] == "map")["releases"]]
    assert map_history[:4] == ["1.0.0", "1.0.1", "1.0.2", "1.0.3"]
    assert map_history[-1] == current["map"]
