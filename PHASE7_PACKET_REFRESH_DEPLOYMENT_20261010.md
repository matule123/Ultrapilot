# Packet renewal — prepared deployment and controlled acceptance

Prepared on 2026-10-10. **PREPARED ONLY: no installation write, diagnostic arm,
application/game launch, commit or push. Full user pytest and explicit deployment
approval are pending. GAME VERIFIED: NOT VERIFIED.**

The complete implementation/profile report is
[PHASE7_PACKET_REFRESH_RELIABILITY_20261010.md](PHASE7_PACKET_REFRESH_RELIABILITY_20261010.md).
It retains the mixed end-to-end tails and the unexplained historical 620/477 ms
reference-region pauses. This preparation does not claim to resolve those pauses.

## Exact frozen payload

Base HEAD: `787d012a2a78ac917bb5506e0958c32d8d06575f`, **with uncommitted local
changes**. This is not a clean or newly pushed release. The prepared files are
byte-for-byte copies of the working tree; existing unrelated changes are retained.

Workspace-only prepared directory:
`docs/steering-audit/oct9-freshness/deployment-prepared-20261010T060704Z/`.
Its ignored `payload/` contains exactly five Python files. No tests, reports,
tools, settings, cache, diagnostics, commit marker or DLL belong in the payload.
`review/` retains their actual LF/CRLF-normalized diffs against installation.

Manifest: `manifest.json`, SHA-256
`b2c3416c3ff235ede3e73d903c3b518a388b46a1cd30104fafa7c9708b260a21`.
Payload content ID:
`2f580acc989e632bfcd1993471b42f8011fa2449c682160fb772a908f11a1f29`.
The manifest records raw and normalized source/installed hashes, original hashes,
sizes, imports, plugin versions, full working-tree status and tracked-diff hash.
The bundle is not a backup of the installation; backup is a prerequisite of the
later approved transaction.

| Runtime file | Reason for coordinated replacement | Candidate SHA-256 |
| --- | --- | --- |
| `core/navigation/road_network.py` | Bounded exact directed prefab topology cache and equivalent iterative enumeration | `373bdd07043a77c0332932a1a3b1127c93ae535029218bc8209c97da21020399` |
| `core/navigation/evidence_worker.py` | Local one-slot availability check; Map must deploy with this method | `66b4a085fb6ad4fbd48324489350012a4009efd87ae94cfbef06ce3e6b6a9d54` |
| `core/longitudinal.py` | Preserve exact comparison witness across bounded zero-propulsion refresh IPC; never execute expired propulsion | `e0b65ebc1425abb2ab1ddd7426d4af28994d82153809a67649304535bda0d572` |
| `plugins/map/main.py` | Publication-bound private geometry cache, occupied-worker argument skip, current reference phases and prior completed-tick timing | `0ca3d89f9e39934fd66d99d5b917392c44795999c60ad163ee4e8a4ca3911fc6` |
| `plugins/autopilot/main.py` | Preserve these timing fields in existing successful/manual-disable/passive exports | `50d093899e3e299d37d759f58bbfa3386e2d5724c93503ac4f87ed34640fcfdc` |

## Installed compatibility and preflight

All **17** targets in installed `manual-deployment.json` match their raw receipt
SHA-256, including the application DLL asset and actual ETS2 plugin DLL. Both DLL
copies remain `0aba58549d2a7d008bc620424a43fa0f28c840e1688687d0ffd5effe6e434dab`;
no binary/schema replacement is needed.

An entire **106-file** installed/source Python inventory over `core/`, `plugins/`
and `sdk/` finds exactly these **five code differences** and **101 exact byte
matches**, with no missing source counterpart. CRLF/LF normalization was used
before classifying differences; it does not conceal code changes. Engine,
Controller, SDK/IPC snapshot transport, ACC, DrivePolicy, service-brake hold,
SteeringExecutor, replay exporter and combined collector need no replacement.
The visualization and diagnostics CLI also match exactly. Map's new worker call
requires coordinated Map/evidence_worker deployment; all other project imports
resolve against the compatible installed inventory. New imports are Python
standard library `sys` and `functools.wraps`; no new dependency install is needed.

Versions remain Autopilot **1.3.3**, Map **1.1.1**, ACC **1.1.4**, DrivePolicy
**1.1.0**. No versions were changed in preparation.

Read-only process enumeration found neither UltraPilot nor ETS2 running. The
initial sandbox CIM query lacked permission; the permitted read-only retry
succeeded. This is only a point-in-time precheck, not permission to write or
proof of the state at a later deployment.

Installed combined settings are `enabled=false`, capacity 3600, max_sessions 16.
The retained status belongs to the old `phase7-longitudinal-20261003-152818`
collection: CANCELLED / APPLICATION_STOPPED_BEFORE_FINISH, zero accepted samples,
`accepting_samples=false`. It is not a current armed collector or new evidence.
These files were only read and remain unchanged.

## Required deployment transaction — only after approval

1. Obtain the user's full pytest result for this exact runtime candidate, then
   explicit approval to install this five-file bundle. Recheck source/payload
   hashes and compatible installed inventory. Any relevant source or installation
   change invalidates this frozen plan and requires review; never silently copy
   a changed working tree under the same approval.
2. Immediately verify both UltraPilot and ETS2 processes are stopped, including
   Python-hosted UltraPilot. If either is running, write nothing and ask the
   user to close it. Neither application is started or controlled by deployment.
3. Create a unique separate backup under
   `C:\Users\PC\AppData\Local\UltraPilotBackups\packet-refresh-<UTC timestamp>\`.
   Copy all five installed originals preserving relative paths and the previous
   `manual-deployment.json`; verify every backup SHA-256 against its source and
   this preparation's original hashes **before the first runtime replacement**.
   Record backup integrity and the original receipt hash in its manifest.
4. With both processes still stopped, copy only the five frozen payload files.
   Verify every installed SHA-256 against the manifest and actual staged bytes.
   This is a consistent stopped-process transaction, not an atomic five-file
   filesystem operation. No process may observe a mixed running bundle.
5. Write the new `manual-deployment.json` only after all five verifies succeed,
   using a same-directory temporary file and atomic rename. Preserve prior receipt
   provenance, record exact new five-file hashes, unchanged dependency/DLL hashes,
   base commit, `local_uncommitted_changes=true`, payload content ID, versions,
   UTC time, prior receipt hash and verified rollback directory. Mark
   `game_verified=false`. Keep the previous receipt in the rollback backup;
   `commit.txt` stays unchanged and is not treated as a content certificate.
6. On any copy/hash/receipt error after replacement begins, restore **all five**
   originals and the previous receipt from the verified backup, then hash-verify
   the complete restoration. If restoration cannot be verified, leave both
   applications stopped and report the exact failure; never announce success.

Preserve `settings.json`, map-cache, original evidence/replays/logs, DLL files
and commit marker throughout deployment. Diagnostics setup below is a separate,
later driver action, not part of the runtime replacement.

## Existing successful-drive evidence and its limits

The prior targeted checks already exercised an ordinary successful `plugin_stop`
export and the actual sole SteeringExecutor → Engine → Controller mapping return
→ combined export/inspect path with **40** immutable source-bound samples.
They retained original SDK frame/time, calculation/submission sequence, route
identity, `map_reference_phase_times`, `previous_map_tick_timing` and acknowledged
write-return times. They are offline checks, not new game evidence. No test or
benchmark was repeated in this preparation.

Manual N after a sufficiently sampled episode creates the existing dense
`manual_disable` export. Normal application shutdown also creates passive/dense
`plugin_stop` files in `<UltraPilot>/route-diagnostics`. Timing data do not require
an automatic failure. Prior completed-tick information belongs to the **previous**
tick and is carried by the next immutable packet; the first has none, and the last
needs a later publication. Do not misassign it to the current observation.

For ordinary global-lane execution, immutable `executor.source_packet` is retained
when the **existing combined diagnostic mode** is active (local-maneuver execution
has its own existing condition). Without it, latest dense row headers are not a
valid substitute for the older physically written executor target. Automatic
rings also cover only a bounded tail of a long drive. Therefore one combined arm
is necessary for this acceptance's exact write binding and broad coverage; no
second collector is needed. It is **not armed now**.

## One future driver-controlled acceptance run

Prerequisites: user's full-suite PASS, separately approved completed deployment,
verified new receipt, both applications stopped during setup. Prepare a GPS route
of at least **5 km** on which the driver can safely encounter a supported relevant
traffic light and roundabout. Start from a safe open location before the approach;
do not test an unverified new stationary brake press in simple automatic mode.
Do not manufacture a red light, obstacle or emergency.

1. With UltraPilot stopped, prepare the existing collector using these commands:

   ```powershell
   cd 'C:\Users\PC\Documents\GitHub\ets2la'
   $runtimeRoot = 'C:\Users\PC\AppData\Local\Programs\UltraPilot'
   $collectionId = 'packet-refresh-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
   $evidenceRoot = Join-Path $runtimeRoot 'evidence-diagnostics'
   python tools/manage_maneuver_diagnostics.py arm --settings "$runtimeRoot\settings.json" --output "$evidenceRoot" --collection-id "$collectionId" --purpose combined --duration 600 --sample-period 0.2 --capacity 3600
   ```

   STOP if paths/collection ID are wrong, another collection is active, or arm
   fails. Arming only diagnostics grants no actuator authority.
2. Driver starts ETS2 and UltraPilot normally. While stationary, use
   `python tools/manage_maneuver_diagnostics.py status --output "$evidenceRoot"`.
   Verify the **new ID**, accepted sample count and SDK frames advance, no
   rejection, correct current GPS identity, connected backend and no control
   fault. STOP without driving if the precheck fails; preserve partial export.
3. Driver enables with **one N**, no manual launch throttle. After a safe launch,
   drive the ≥5 km route: normal driving, roundabout, supported red → continuous
   service-brake stop/hold → fresh relevant same-signal green → resume, then
   continued driving. No parking-brake automation. Stop acceptance and take over
   for abnormal steering, unexpected propulsion/R/backwards movement, rolling
   while waiting, missed/unqualified signal, authority loss or a technical stop.
   A real safety stop remains valid and must not be suppressed to reach 5 km.
4. Finish in a safe place under the driver's control and manually disable with N.
   Keep UltraPilot running for export, then issue:

   ```powershell
   python tools/manage_maneuver_diagnostics.py finish --output "$evidenceRoot" --collection-id "$collectionId"
   python tools/manage_maneuver_diagnostics.py status --output "$evidenceRoot"
   python tools/manage_maneuver_diagnostics.py inspect "$evidenceRoot\$collectionId"
   ```

   Finish acknowledgement alone is not completion. Recheck status at reasonable
   intervals until READY_FOR_OFFLINE_REVIEW and manifest is available; do not
   assume a two-second export. Inspect must report `integrity_valid=true` for the
   same ID, with no rejected/incomplete collection. STOP the success claim if
   export fails, counts stop unexpectedly, capacity is exceeded or samples are
   missing; preserve the files. `confirmed=false` and `runtime_authorized=false`
   are expected diagnostic properties, not authority to drive.
5. Close UltraPilot normally to retain passive/dense `plugin_stop` timing, then:

   ```powershell
   python tools/manage_maneuver_diagnostics.py disable --settings "$runtimeRoot\settings.json" --output "$evidenceRoot"
   ```

   Finish/disable diagnostic commands do not change autopilot authority. Driver
   takeover/manual N is a separate control action. This 600 s / 0.2 s / 3600
   setup allows ~3000 periodic samples within ten minutes including startup and
   waits. A drive longer than that is not wholly measured; report its actual
   coverage rather than claiming the entire 5 km. Sampled reads are not first
   IPC arrival; combined witnesses are not every physical write.

## Evaluation after the driver supplies this run

Bind by new receipt hashes/content ID, then session, activation, intent, revision,
build, dataset/map key, calculation sequence and original SDK frame. Inspect
integrity before metric computation. Split identity changes/gaps and separate
launch, active driving, waiting, controlled stop and manual intervals.

Report within-segment new packet intervals and original observation ages at
**acknowledged source-bound writes** separately: p50/p95/p99/max, counts and >500 ms
cases. Do not infer every write or first arrival from sampled reads. Report
CTE RMS/time-weighted RMS, mean/p95/p99/max |CTE| and heading error only where
reference point and source binding are valid; missing values remain missing.
Use existing phase-6 and longitudinal analysis tools/methods and retained current
and completed-prior Map subphases for the worst ticks. Examine first technical
cause and physical pedal chain, qualified signal ID/time/generation, brake hold
and restart without replacing the first cause with later cleanup.

If a fault occurs, explain its first faulty tick from this same deployed bundle
before suggesting any repetition. Historical 620/477 ms attribution remains
unknown unless evidence actually establishes it. A successful run grants GAME
VERIFIED only for its measured route/situations, not universal reliability.

## Preparation validation

Content/inventory/receipt hashes and CLI/source contracts checked. All five staged
files equal their working-tree originals. No runtime/test code changed, no pytest,
benchmark or game was run in this preparation. The recorded earlier targeted
260 tests / 10 subtests and unchanged 16 steering / 12 comfort cases remain the
offline implementation checks, not a current full-suite result. Required next
gate: **await user full pytest result; then explicit deployment approval**.
