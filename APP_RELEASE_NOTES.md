# UltraPilot release announcements

The app version is still **0.4.2**. This feature does not publish 0.5.0.

## Publishing a future app release

1. Add an entry to `assets/app_release_notes.json` under `releases`, keyed by the new semantic version (without `v`).
2. Write a `changes` array of concise bullet strings for **UltraPilot application updates**. These strings appear verbatim in the dialog; use the desired UI language.
3. Add a `plugin_versions` object with every bundled plugin's version at that app release. Retain previous release entries and their plugin snapshots. This makes comparisons accurate even when users have installed commit-only updates in between app releases.
4. Keep each intermediate plugin release documented in `PLUGIN_CHANGELOG.md` (English). The dialog shows every release newer than the previous app-release baseline and no newer than the installed plugin.
5. Change `VERSION` in `core/update_check.py` only when actually releasing that app version.

Example structure (illustrative only, not a published release):

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

The shipped metadata currently has no release entries. First launch establishes a per-installation baseline without an announcement. Commit-only updates retain that baseline; the next app-version upgrade creates a persistent notice. Once dismissed, it is not shown on later launches. A pending notice survives an interrupted startup. Downgrades are not announced as new releases.

If no published plugin snapshot exists for the previous app release, the first-launch observed versions are used instead. This fallback does not reconstruct plugin changes made before this feature was installed. Missing app notes or plugin history are explicitly indicated rather than invented.

The Dynamic Island displays the app version separately from the commit. The scrollable, non-modal release dialog follows the light/dark theme and separates application bullets from plugin-by-plugin version history. Metadata and plugin changelog are included by the existing runtime updater; no network request is needed to display them.
