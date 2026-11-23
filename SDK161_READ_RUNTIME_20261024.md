# ETS2 1.61 read-side runtime integration — 2026-10-24

## Status

Source integration and the separate SDK bundle are **deployed for testing**
after the user's explicit approval on 2026-10-24.
The candidate and deployed standard-name build passed stationary live reads.
Autonomous driving is not verified. This does not close
Phase 7 or certify earlier ACC/braking issues as fixed.

The game and UltraPilot stayed closed during deployment. No game input, app
startup, settings change, map selection, commit or push was performed.

## Authorized deployment result

Deployed at `2026-10-24T15:58:56Z`: five app source files and ten dedicated SDK
bundle files. All **53 entries** in the updated installed deployment receipt
were verified. The game producer matches the release hash below; both SCS
DLLs already matched and remained byte-identical.

Recoverable backup and exact deployment receipt:
`docs/steering-audit/oct22-sdk161/runtime-deploy-20261024T155856358095Z/receipt.json`.
The old producer and changed app files are saved there. The isolated diagnostic
candidate was copied/hash-verified into its `diagnostics/` directory and removed
from the game's plugin directory. This is archival, not loss of the original.
The separate passive `UltraPilot161ReadOnlyProbe.dll` is retained temporarily
to bind the first live read to the correct game PID; it writes no controls.

Settings, active map, root legacy SDK assets and unrelated game plugins were
hash-verified unchanged. No map dataset was copied or selected.

An isolated import of the **installed** Python modules confirmed detected game
version 1.61, `is_sdk_installed=True`, `ensure_installed=(True, already)`, and
zero copy calls when the installed boot helper checked this exact game. Thus
the deployed boot path does not revert the verified SDK to legacy root assets.

### First deployed standard-name live check — passed

User loaded ETS2 1.61.1.9s, PID 33960 (started 2026-10-24 18:59:55 local),
with UltraPilot off and the parked truck unpaused. The game log confirms
`1.61.0-up-scoped-read` initialized with matching game version. Candidate-e is
no longer loaded. The passive PID probe remains active without controls.

Read-only capture:
`docs/steering-audit/oct22-sdk161/runtime-a-live-33960-1792861650272184400.json`
(SHA-256 `5496ddc4cd190bec0e8bbcb9b3d6539bb3902e409385f444a09f137402afca17`).

All **20/20 traffic and 20/20 signal reads** were valid over ten seconds.
Both producer frames/generations advanced strictly. Traffic generation
4746 -> 5168; signal 4747 -> 5169. Both lifecycle IDs were
146180617554320. Maximum observed ages: traffic 25.760 ms, signal 25.705 ms.
Maximum absolute ego speed was 0.000270 km/h. Camera values were plausible.
All route counts were zero; no active GPS route is established by this capture.

Game stayed alive; crash log modification time remained the historical
candidate-d crash at 15:03:07, not a new incident. No controls were written and
the application was not started. This verifies stationary standard-buffer
acquisition, not autonomous driving or nonempty route behavior. The immutable
bundle manifest retains its build-time validation flags; this later live
evidence is recorded here without changing deployed binary/manifest hashes.

### Standard-name GPS route set — passed

User set a destination without restarting the game. Read-only capture:
`docs/steering-audit/oct22-sdk161/runtime-a-live-33960-1792861849638686300.json`
(SHA-256 `b1049ce93f5fa5d296fc71910653740e0cebbb17cd0c238d89f741baf07d8a07`).
All 16 samples contained the same 50-UID route with finite, nonnegative distance
and time fields. First remaining distance was 70383.234375 m, last 0 m. Route
UID sequence SHA-256:
`9bdd74c3ff00214bc692a6aa6e5b92781a40e7ccc6a74cd64274682b536dfe1e`.
Traffic/signal were valid 16/16 with strictly increasing frame/generation values.
Truck stayed stationary (maximum absolute ego speed 0.000199 km/h), game PID
remained 33960 and crash log remained unchanged. No controls/app startup.

This verifies a nonempty route on the standard buffers, not destination arrival
or driving. The installed app's map-cache still contains only `promods-1.59`;
using it for 1.61 driving would be wrong. The already-generated 1.61/ProMods
2.84 dataset must be installed/selected separately before application driving
validation. No map was copied or selected during these read-only checks.

### Authorized map installation and selection — completed

After the user explicitly requested transfer, the completed dataset was copied
to `<installed UltraPilot>/map-cache/promods-2.84` and selected in settings.
This supersedes the earlier statement that only the 1.59 map was installed.
Source output and the old `promods-1.59` directory were preserved.

Receipt and settings/metadata backups:
`docs/steering-audit/oct22-sdk161/map-install-20261024T171610428606Z/receipt.json`.
Copied 25 files, 1,898,886,311 bytes, through a separate staging directory.
All 21 manifest data hashes and all 25 destination/source hashes matched.
The actual **installed** RoadNetwork loader then read 1,284,486 nodes,
341,795 roads, 4,869 prefab descriptions and 450,311 graph nodes, matching the
generator counts. All 12 saved first/last GPS sample anchors were in this map.
No claim is made that these 12 anchors independently verify the whole route.

Only `selected_map` changed in settings, from `promods-1.59` to `promods-2.84`;
autopilot remains disabled and all other settings are unchanged. Installed
deployment metadata points to the map receipt. The game stayed running, the
UltraPilot UI was not started, and no controls were written. Map load/hash
verification passed; actual application startup and driving remain separate.

### Application running with the game — partial pass, route blocker found

The user started both applications. ETS2 PID 26848 and UltraPilot parent PID
29532 remained alive. App log on 2026-10-24 records the 1.61 session selecting
`promods-2.84`, loading 1,284,486 nodes / 341,795 roads / 4,869 prefab types,
and publishing a valid 232-point, 456.9 m local trajectory (confidence 0.838,
route build `d741d2e113104ee8b5c2fda6b5b3eb8f`, revision 12).

However, three preceding longer destination builds were rejected with
`TOPOLOGY_AMBIGUOUS` during `select_lane_sequence`: ambiguous prefab lane
connector for prefab 5337536198829569427 -> 5337536250146868729.
Build IDs: `44b4704b876f41fa837bab1c7bc0ba70`,
`0f6aff07cd744e21959703d6f6b5d86c`, `c10e0e2afb04420bbf8e6e22bf1cc996`.
The successful short build does not clear this route-construction blocker.
No bypass or data/routing change was made during inspection.

Independent standard-buffer read:
`docs/steering-audit/oct22-sdk161/runtime-a-live-26848-1792865274516356800.json`.
Traffic and signal valid 16/16, paused samples zero, route count six. The game
crash log still ends at the historical candidate-d crash. App also logged
`STALE_VEHICLE_OBSERVATION` at 20:06:48; this single log entry is retained as
an observation, not declared fixed by the separate native-buffer check.

Result: application/map startup and current native acquisition demonstrated;
whole-route navigation and driving qualification remain open. Autopilot must
not be enabled as a purported completed verification of these route failures.

## Scope and exact identity

`assets/sdk/1.61/manifest.json` pins ETS2 1.61.1.9s executable SHA-256:

`b70c2357cc56eb5834ee47fea3c60b2f2d4591383ff2ac479cfd3cd254301b8c`

| File | SHA-256 |
| --- | --- |
| `ets2la_plugin.dll` | `330c37eb5540cd23c84dba9a7b7824c1f791cd5aac7cd7c9bb5341db8ad5715c` |
| `scs-telemetry.dll` | `f361894a5434746933dab47ed8bc17a6f22f65802ce92256fc7cd7d4fc7fac3a` |
| `scs_sdk_controller.dll` | `d9fbd5ace5e76eed70b7e10b78c450b111566ad6aa814dff65d6244ad23e687e` |

Producer version: **1.61.0-up-scoped-read**. Only mapping names, log labels and
version text differ from live-tested candidate-e
(`cd5cabf8bbb55ee257c56ce9aa24442f14479bfe110207976911305e1dc5575c`).
The packager checks every candidate source hash and the exact source transform;
no acquisition/control logic changes are hidden in the rename.

Native input overrides stay disabled. The app's separate SCS controller backend
remains responsible for controls. The producer exports only telemetry init and
shutdown. A nonempty non-AI/multiplayer list remains explicitly unsupported,
not misreported as an empty road. Legacy GPS/camera buffers remain untimed.

## Integration defect fixed

Previously `install_game_dlls()` copied the same root assets into every detected
game during boot/install/repair. This could replace a 1.61 producer with a 1.59
layout after a subsequent app launch.

The 1.61 path now uses `core/sdk/versioned_sdk.py` through `sdk_downloader`:

- distinct bundle; no 1.59 alias or unknown-version fallback;
- exact EXE, all three DLL hashes and manifest contract checked before writes;
- old DLL names alone cannot report a correct 1.61 SDK installation;
- full three-file bundle required, not a partial single-DLL legacy helper;
- cached/requested game version must agree with detected executable version;
- running game or an installed diagnostic candidate blocks replacement;
- changed files have content-addressed recoverable backups and same-directory
  staged replacements; a later failure rolls back prior replacements;
- onboarding's status checks use the game's version.

Legacy assets at `assets/*.dll` are not changed by this work. Unsupported or
unknown game versions are skipped instead of receiving legacy native layouts.

## Verification and evidence

145 targeted tests and 142 subtests passed across native candidate/profile,
map compatibility, SDK integration, onboarding installer and camera suites.
The complete offline suite subsequently passed: **3128 tests and 1725 subtests**
in 809.71 seconds (13:29), exit code 0. The log is
`docs/steering-audit/oct22-sdk161/oct24-runtime-full-suite.log`.
`compileall` and `git diff --check` also passed. The installer's runtime-payload
filter accepts all ten files in the new SDK directory; the source archive is
included without shipping the audit directory or native test executables.

Actual runtime DLL negative-host test passed: ABI offsets, wrong-EXE refusal,
API refusal and repeated shutdown after failed initialization. No game method
was executed. Runtime sentinel regression reproduced candidate-d's real method
fault `C0000005`; the patched method passed 15 empty-list configurations,
rejected all 3 nonempty cases and both unreadable headers.

`native-source.zip` includes modified source, dependency headers, licenses and
a portable x64 MSVC build command. A fresh extraction compiled successfully and
its DLL passed the negative-host test. Different build paths produce a different
binary hash; deployment uses only the manifest-pinned release DLL above.

Evidence (local audit directory, not packaged as runtime data):

- `docs/steering-audit/oct22-sdk161/read-runtime-a/build-receipt.json`
- `docs/steering-audit/oct22-sdk161/read-runtime-a/verification/result.json`
- `docs/steering-audit/oct22-sdk161/read-runtime-a/sentinel-regression/result.json`
- `docs/steering-audit/oct22-sdk161/packaged-source-rebuild/result.json`
- `docs/steering-audit/oct22-sdk161/oct24-runtime-full-suite.log`
- `docs/steering-audit/OCT24_SDK161_CANDIDATE_CRASH.md` (live candidate evidence)

The manifest records hashes of four real stationary captures: 20 valid samples,
destination change (16), destination cancellation (16), and same-profile reload
(20). Separate live pause/unpause checks invalidated paused acquisition as
expected. Those checks are **candidate-e**, not a standard-name live test.

Pre-deployment comparison with `candidate-e-install-receipt.json` confirmed all
eight recorded original plugin/settings hashes unchanged. At that preparation
stage the diagnostic candidate was still installed separately. The authorized
deployment above subsequently archived it and replaced the game producer.

## Deployment boundary / subsequent steps

Deployment required a separately authorized, game-closed operation, with a
receipt/backup of both app runtime and game plugins. Do not manually copy just
the new producer. Preserve/archive the diagnostic DLLs outside the game's
plugin directory before using the strict installer; do not delete original
plugins or overwrite the legacy SDK assets.

Application changes for this integration: `core/sdk/versioned_sdk.py`,
`core/sdk/sdk_downloader.py`, `core/sdk/game_utils.py`, `ui/onboarding.py`, plus
the prior `core/navigation/map_data.py` 1.61 compatibility work and this separate
`assets/sdk/1.61/` directory. Existing unrelated working-tree changes are not
implicitly part of this SDK deployment.

The generated ProMods 2.84 dataset remains at the generator's output location;
the user's active installed map/settings have not been changed. Any subsequent
map copy must verify its complete manifest/config and correct 1.61/2.84 identity.

After authorized deployment, first verify stationary standard mappings with
autopilot off; verify lifecycle, route change/clear and producer identities.
Only then plan a controlled driving validation. No timeout relaxation or
suppression of safety rejection is part of this integration.
