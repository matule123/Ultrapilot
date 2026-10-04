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
              "changes": ["Better settings"], "plugins": [{"name": "map",
              "previous_version": "1.0.0", "version": "1.0.2", "releases": [
                  {"version": "1.0.1", "changes": ["First fix"]},
                  {"version": "1.0.2", "changes": ["Second fix"]}]}]}
    dialog = AppReleaseDialog(notice, {"ui_theme": theme})
    texts = [label.text() for label in dialog.findChildren(QLabel)]
    for text in ("v0.5.0 je tu!", "Aktualizácie UltraPilotu", "Zmeny pluginov",
                 "v1.0.1", "v1.0.2", "•  First fix", "•  Second fix"):
        assert text in texts
    assert not dialog.isModal()
    dialog.close()
    app.processEvents()


def test_release_assets_are_runtime_files_and_version_unchanged():
    assert update_check.VERSION == "0.4.2"
    # Assets are already shipped by the filtered updater.
    assert "assets" in update_check._RUNTIME_DIRS
