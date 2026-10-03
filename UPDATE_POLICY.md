# Application update payload

## Installed files

ZIP updates use an explicit runtime allow-list:

- `assets/`, `core/`, `languages/`, `plugins/`, `sdk/`, `ui/` (case-insensitive).
- `main.py`, `bootloader.py`, `requirements.txt`, `README.md`, license files
  and `PLUGIN_CHANGELOG.md`.

The plugin changelog is intentionally included as user-facing release history.
Phase results, audits, tests, tools, build output, hidden development folders
(including `.codex`) and compiled Python caches are excluded. A newly added
repository root is not installed automatically.

## User data

Settings, routes, map/model caches, logs, diagnostic collections, installer
metadata and the installer executable are protected from replacement.
Previously installed development files are left untouched: the updater does
not recursively delete folders that might contain user work. This filter
prevents new development payload from being installed; it is not a cleanup tool.

## Download and installation

The current server-side source is still the GitHub source ZIP for the selected
revision. The download therefore includes the repository, but installation
selects only runtime entries. A smaller download requires a separately built
runtime release artifact and is not claimed by this change.

Displayed unpacked size and file count describe the selected runtime payload,
including when an older staged ZIP is reused. Downloaded size describes the
actual complete transfer.

The archive is checked for corruption. Unsafe paths, duplicate case-insensitive
runtime destinations and archive links are rejected before installation.
Each installed file is written to a temporary sibling and atomically replaced.
The commit marker advances only after successful application.

This is not an all-files transaction or a full rollback system: an error after
several replacements may leave a partially updated installation. No automatic
full-installation backup is created. Existing explicitly obsolete modules are
still removed by their exact paths. Python dependencies and files inside ETS2
are not installed by this ZIP application step.

Source checkouts using `git pull` remain development checkouts and retain the
whole repository. The runtime filter applies to ZIP installation paths.
