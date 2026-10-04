# UltraPilot release announcements

The current app and installer application version is **0.5.0**. The installer tool's own version is separate and unchanged.

## Publishing a future app release

1. Add an entry to `assets/app_release_notes.json` under `releases`, keyed by the new semantic version (without `v`).
2. Write a `changes` array of concise bullet strings for **UltraPilot application updates**. These strings appear verbatim in the dialog; use the desired UI language.
3. Add a `plugin_versions` object with every bundled plugin's version at that app release. Retain previous release entries and their plugin snapshots. This makes comparisons accurate even when users have installed commit-only updates in between app releases.
4. Keep each intermediate plugin release documented in `PLUGIN_CHANGELOG.md` (English). The dialog shows every release newer than the previous app-release baseline and no newer than the installed plugin.
5. Change `VERSION` in `core/update_check.py` only when actually releasing that app version.

Minimal illustrative structure (the shipped file contains the complete release):

```json
{
  "schema_version": 1,
  "releases": {
    "0.5.0": {
      "changes": ["A concise application change"],
      "plugin_versions": {"map": "1.0.3", "autopilot": "1.2.0"}
    }
  }
}
```

The shipped metadata contains the 0.4.2 source baseline and the 0.5.0 announcement. Version 0.4.2 had no independent plugin versions, so its `plugin_versions` is deliberately empty, not an invented 1.0.0 snapshot. The complete 1.0.0 versioning baseline and subsequent plugin releases are shown for this upgrade.

An optional `previous_version` in the current release entry allows first launch to show its announcement even if the user skipped the commit that introduced announcement tracking. This also shows the release welcome on a fresh installation. Otherwise first launch establishes a baseline silently. Commit-only updates retain the baseline. Once dismissed, the notice is not shown on later launches. A pending notice survives an interrupted startup. Downgrades are not announced as new releases.

Optional `intro` provides the opening paragraph and `limitations` provides a separate honest scope/compatibility card. Notes describe the shipped implementation, not universal live-game certification. The 0.4.2 GitHub commit date is known; its original push time is not verified. See [RELEASE_NOTES_0.5.0.md](RELEASE_NOTES_0.5.0.md) for provenance and the full commit inventory.

If no published plugin snapshot exists for the previous app release, the first-launch observed versions are used instead. This fallback does not reconstruct plugin changes made before this feature was installed. Missing app notes or plugin history are explicitly indicated rather than invented.

The Dynamic Island displays the app version separately from the commit. The scrollable, non-modal release dialog follows the light/dark theme and separates application bullets from plugin-by-plugin version history. Metadata and plugin changelog are included by the existing runtime updater; no network request is needed to display them.
