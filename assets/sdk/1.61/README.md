# ETS2 1.61 scoped read-side bundle

This is **not** a full autonomous-driving qualification. `manifest.json` pins
the exact ETS2 1.61.1.9s EXE and every DLL. Other game patches are refused.

- `ets2la_plugin.dll`: UltraPilot scoped/timed traffic and signals, GPS and
  camera producer, version `1.61.0-up-scoped-read`. Native input overrides are
  disabled; only telemetry init/shutdown exports exist.
- `scs-telemetry.dll`, `scs_sdk_controller.dll`: pinned 1.61 upstream bundle;
  provenance and attributions are in the manifest and `upstream-sources.txt`.
- `native-source.zip`: modified producer source, headers, dependencies,
  licenses, build receipt and `build.cmd` (Visual Studio x64 Native Tools).

Candidate-e passed stationary live reads, pause/unpause, destination change,
destination cancellation and same-profile reload. The standard-name build
differs only by mapping/version/log labels and has offline ABI/negative-init
and sentinel-crash regression coverage. **Standard-name live operation and
autopilot driving remain unverified.**

Nonempty non-AI/multiplayer vehicle lists are unsupported and explicitly
invalidate acquisition; they are not silently treated as an empty road.
Legacy GPS/camera buffers have no producer timestamp. No safety timeout is
relaxed by this integration.

Use the version-aware installer, not a manual partial DLL copy. It verifies
the EXE and bundle before writing, refuses a running game or a still-installed
`UltraPilot161ReadCandidate.dll`, preserves originals in hash-named backups,
and rolls back earlier replacements if a later replacement fails. Diagnostic
DLLs must be archived separately as part of an authorized deployment.

This directory's presence does not itself deploy anything. The old 1.59
assets and the user's installed plugins, settings and active map are separate.
