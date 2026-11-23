# Temporary diagnostic build — 25 October 2026

**Superseded handover:** the non-disable AP-part/completeness blockers below
are addressed by the current diagnostic build 03, documented in
[PHASE7_DIAGNOSTIC_CAPACITY_20261025.md](PHASE7_DIAGNOSTIC_CAPACITY_20261025.md).
This build-01 report and its evidence remain historical; its ZIP is not the
current deployment candidate. Bounded stream-loss and game-verification limits
still apply to the documented limits of the current build.

**Final handover: REVIEW ONLY / BLOCKED for the complete requested collection.**
The user requested closure of the current verification without more features.
The implemented subset has offline evidence below. The gaps listed here remain;
this report does not certify complete capture, ACC, Phase 7 or driving behavior.
Nothing was installed, armed, committed, pushed or operated in ETS2.

## Single delivered artifact

Build identifier: **UP-DIAGNOSTIC-20261025-01**.
Directory: `docs/steering-audit/oct25-diagnostic-build/release-approved-scope/`.
The directory name is historical preparation terminology, NOT deployment approval.

| Artifact | SHA-256 |
| --- | --- |
| `ultrapilot-diagnostic-20261025-01-candidate.zip` | `d6a750b5de08b34eec2d4a34b875bb6cafc3a0b41d961b75c9a2a48c510a2d84` |
| `rollback-installed-base.zip` | `f168162082f0aab4a23fa78672dbd306f2ead7f76be91cf788f21c4d6e9a99ff` |

Every archive member was read back and hash-checked. The candidate manifest
contains the six exact runtime hashes, their previous installed hashes, the
53-file required base receipt and the qualification hash. This is an
uncommitted installed-base overlay, not a release of the current repository HEAD.
Earlier preparation directories are superseded; their evidence is preserved.
Only this candidate ZIP is the handover. The other ZIP is rollback, not another candidate.

Runtime payload:

1. `core/engine.py` — installed baseline plus observational taps, diagnostic
   readiness/export integration and shutdown-only export waits.
2. `core/longitudinal.py` — installed baseline plus local callbacks observing
   the exact values already read, before diagnostic compaction.
3. `plugins/autopilot/main.py` — installed baseline plus the existing dense
   replay's exact-consumer callback; no driving fix or gain change.
4. `core/navigation/longitudinal_diagnostics.py` — optional window in PedalJournal.
5. `core/steering_replay.py` — existing codec/export extension, grouped dossiers,
   recoverable archive and bounded export children.
6. `core/navigation/diagnostic_build_config.py` — diagnostic-build opt-in.

No DLL, SDK bundle, settings, map cache, test, report or commit marker is in the
runtime payload. No plugin version is increased for this diagnostic overlay.

## Installed identity and excluded workspace changes

All **53** targets in the installed deployment receipt were checked again.
Receipt SHA-256:
`61d7bd251991e0933f9f598d80f3620f6f65e581fa68d6a1fb7d4faa59a38935`.
The preserved evidence inventory's **20 raw file hashes** and **13 replay/timing
envelopes** pass verification. Originals are unchanged.

LF/CRLF were normalized before comparing code. The four differences are real:

| File | Workspace changes excluded from the diagnostic payload |
| --- | --- |
| `core/engine.py` | Oct18 acquired-crossing scope and coordinated green restart/history changes |
| `core/longitudinal.py` | Atomic publication and near-expiry finalization/handoff repairs |
| `core/transmission_mode.py` | The newer hold/restart input-refresh rule; installed file is retained unchanged and is not shipped |
| `plugins/autopilot/main.py` | Workspace 1.3.5 and bounded resume recapture; candidate retains installed 1.3.4 behavior/version |

`installed-workspace.diff` and `entry-audit.json` in the Oct25 audit directory
preserve the comparison. **141 installed control functions have identical ASTs**
after removing the newly inserted diagnostic calls/imports. Only diagnostic
initialization, preflight, export and shutdown-wait methods are excluded from
that comparison. Physical-output equivalence is tested separately.

The SDK 1.61 bundle, executable pin and installer guards are unchanged:

| Item | SHA-256 |
| --- | --- |
| ETS2 executable pin | `b70c2357cc56eb5834ee47fea3c60b2f2d4591383ff2ac479cfd3cd254301b8c` |
| 1.61 producer DLL | `330c37eb5540cd23c84dba9a7b7824c1f791cd5aac7cd7c9bb5341db8ad5715c` |
| SCS telemetry DLL | `f361894a5434746933dab47ed8bc17a6f22f65802ce92256fc7cd7d4fc7fac3a` |
| SCS controller DLL | `d9fbd5ace5e76eed70b7e10b78c450b111566ad6aa814dff65d6244ad23e687e` |

## What is retained

The existing PedalJournal owns the new optional window. Existing dense replay
owns Autopilot consumer inputs. Existing background export jobs own the output;
there is no second authority/controller and no additional SDK or IPC read.

- Original consumed native moving/parked bytes, source metadata and original
  frame/time/lifecycle/generation; the published traffic packet and selected
  signal/actor/prediction data already computed by production.
- Raw available ego fields and subsequent SDK observations, separately from
  backend writes. Missing geometry, physical vehicle color/type and game
  consumption are not invented.
- Original packets actually read by longitudinal consumers, read/return/check
  times and original observation/compute/deadline/identity fields. Autopilot's
  full consumer stream is in its dense replay when that stream is exported.
- Selected command and existing source/request/hold/launch provenance, ordered
  backend calls/results and the existing short detailed ring/summary history.
- Activation rejection/request and driver cancellation from already available
  locals; an absent rejected-activation truck snapshot remains absent.
- First intervention, including compact original frame/time/context even when
  optional detail exceeds the receipt budget; later cancellation does not replace it.

Ordinary sampling is at most 10 Hz per stream. Target/status/light/pedal-mode,
traffic/light brake edges and invalid/rejected inputs can retain intervening
samples. This is NOT a claim to retain every original control tick for 40 s.
Per-stream gaps, loss counters and actual time ranges are exported.

One pending episode groups related braking, waiting and restart transitions.
Its pre-event references are pinned and its rolling tail is bounded. A long
episode can have an explicitly missing middle; it does not become fictitious
continuous coverage. After disable the observer can retain passive data, never
issue new control commands. Shutdown may produce an incomplete post-window.

## Dossier and disk behavior

Output: `<UltraPilot>/route-diagnostics/incident-<session UUID>-<sequence>.json`,
a matching `.md`, and hash-referenced replay parts. Engine/AP automatic-disable
exports are correlated using the original intervention epoch and observation
time; qualifying new dense parts are members of that dossier. A mapping write
return is never game-consumption confirmation. `confirmed` and
`runtime_authorized` remain false.

Active new diagnostic files have a **128 MiB** budget, at most eight closed
dossiers; the recoverable closed archive has **512 MiB**. A dossier replay is
capped at 16 MiB, a diagnostic dense replay at 32 MiB. Failure notes have a
separate 64 KiB/eight-note ceiling. Original legacy significant-event files
are not silently deleted or rewritten; the old three quota failures remain evidence.

Closed dossiers are verified before being moved as a whole under
`route-diagnostics/archive/<incident ID>/`, then verified there. Failure rolls
back the move. Export processes share a disk-only lock, never a control lock.
The main JSON is exposed last. Partial/orphan files consume budget and may
require explicit review; they are not silently removed to fake readiness.

Large serialization, compression and readback run in bounded export child
processes under the existing one-job exporters. Failure retains one retry
window with a 30 s retry interval, an explicit worker error/status and, where
disk permits, a compact failure note. No unbounded queue is introduced.

The startup log and `diagnostic_capture_status` report disk capacity/readiness.
**Disk `ready=true` is not complete evidence readiness or navigation authority.**

## Verification results

Frozen installed-base qualification: **165 tests and 10 subtests PASS in
29.08 s**, exit 0, all six frozen runtime hashes unchanged. Log:
`release-approved-scope/qualification-tests.log`; result:
`release-approved-scope/qualification-result.json`.

This ran isolated installed-baseline Engine/Autopilot/longitudinal modules, not
the different workspace driving fixes. The whole pytest suite was NOT rerun.
Normal-build legacy codec/quota expectations were also retained in separate
targeted runs; their assertions were not weakened for the diagnostic contract.

Coverage includes original Oct24 first receipts, a model 60 s stream,
30 s pre/10 s post retention, short inter-sample brake/rejection edges, long
episode gaps, duplicate/changed native identities preserved verbatim, both
gearbox modes, red/green and cancellation, immutable consumer pairing,
backend outcomes, corrupt/missing parts, full/low disk, failure/retry, partial
manifest recovery, and Engine/AP dossier correlation.

The four Oct24 scenes are NOT reconstructed from missing actors. In particular
ACC 42 and 39 still had fresh receipts; their stored reasons remain original
target-unavailable refusals, not fabricated timeout diagnoses.

## Measurements and limits of the measurements

| Measurement | Result |
| --- | --- |
| Synthetic 80 actors / 60 s / 3601 offers | 30.0 s before + 10.0 s after; zero capacity drops/capture failures |
| Tap off p50 / p95 / max | 0.0003 / 0.0004 / 0.0213 ms |
| Tap on p50 / p95 / max | 0.0034 / 0.4470 / 3.2014 ms |
| Accounted ring / fixed ring cap | 25,951,588 / 33,554,432 bytes |
| Traced retained / peak window memory | 12,776,758 / 13,181,206 bytes, without mock-call histories |
| Simple-auto whole model tick off → on p50 / p95 / max | 5.16 / 6.63 / 32.16 → 5.82 / 7.14 / 31.03 ms |
| Real-auto whole model tick off → on p50 / p95 / max | 4.87 / 5.91 / 25.25 → 5.49 / 6.69 / 41.41 ms |
| Whole-model output and read comparison | Physical write hashes identical; IPC read counts identical, both modes |
| Original threaded large-export concurrent tick maxima | 112.50 / 120.89 ms, simple / real |
| Isolated-process export, unmonitored comparison maxima | 36.93 / 54.98 ms, simple / real |
| Separate 20 ms RSS-sampled export run | Parent peak 173,146,112 / 171,798,528 bytes; child peak 89,366,528 / 85,463,040 bytes |

These are separate offline runs, not matched ETS2 trials. RSS includes the
interpreter, model fixtures and allocator retention; it is not the ring's
exclusive allocation. The memory-sampled run had concurrent tick maxima
21.62 / 19.79 ms, illustrating run/monitoring variability rather than a stronger
latency guarantee. GC was measured, not disabled; the real-mode ordinary
on-run includes a 35.49 ms GC maximum. No historical pause is attributed to it.

Logical retained upper budgets are 32 MiB Engine ring + 32 MiB pinned pre-window,
32 MiB AP consumer ring and up to 64 MiB for one retained retry window. Shared
references may reduce actual storage. This is not a hard RSS cap; export child
and JSON/codec transient allocations are additional. The original 64 KiB detail
ring and 1 MiB decision-summary budget are unchanged. Larger/unusual scenes
may exhaust the budget and MUST be interpreted via the loss flags.

## Blocking point and remaining risks

**BLOCKER FOR THE ORIGINAL COMPLETE-COLLECTION GOAL:** on a successful slowdown
or wait without disable, the exact Autopilot consumer stream can still be only
in its in-memory dense replay until a later disable/manual stop. The Engine
dossier may close earlier without that part. The new inputs are retained and
immutable, but the full cross-process evidence is not guaranteed to be delivered
with every successful event. This is NOT solved by the passing unit tests.

**Related completeness limitation:** the top-level dossier `incomplete` field
currently describes the window. Backend-detail loss and AP stream loss must be
read from their own counters. A false window-incomplete flag must not be read
as a certificate of complete backend/AP evidence. These two points are included
in the delivered manifest's OPEN gates and prevent a ready-for-collection claim.

Other limits: no game verification; no recovery guarantee for forced process kill
or power loss; no guaranteed full middle of arbitrarily long holds; no invented
lane coverage, physical color, exact stop line or native geometry not supplied
by the consumed data. Existing installed driving regressions deliberately remain.

No further runtime feature was added after the user's closure instruction.
The manifest is truthfully **REVIEW_ONLY_BLOCKED_COMPLETE_CAPTURE**,
`ready_for_drive=false`, `ready_for_separate_collection_approval=false`.

## Conditional deployment and rollback procedure — NOT EXECUTED

Do not apply this candidate as the finished reliable collector. Review the
blocking scope first. Any later experimental installation requires separate
explicit approval; this report is not that approval.

1. Close UltraPilot AND ETS2; verify their processes have exited. Do not copy
   files into an active control session.
2. Verify the candidate/rollback archive SHA-256 and all 53 required base hashes.
   If the installed base differs, STOP; do not mix this overlay with another build.
3. Make a fresh timestamped backup of the six target paths and deployment receipt.
   Record that `diagnostic_build_config.py` did not previously exist.
4. Apply all six manifest-listed files as one operation, verify each new hash,
   and save a deployment receipt identifying this uncommitted diagnostic build.
   Preserve SDK 1.61, settings, map cache, original logs and commit marker.
5. On any copy/hash failure, restore all five existing originals and the receipt;
   quarantine the newly added configuration file. Do not restore selected files only.
6. For rollback later, repeat the application/game-closed checks, restore the
   entire recorded base, quarantine the new configuration, and verify every
   original SHA-256. Never remove diagnostic evidence to perform rollback.

## Future one-drive collection procedure — conditional, not requested now

Only after the blocking capture scope is resolved/reviewed and deployment is
separately approved: normal startup enables this diagnostic build, no arm command.
Check startup capacity status, correct 1.61/map identity and valid GPS authority;
STOP on an export/readiness error or invalid route. Allow at least 30 s of warmup.
Choose one short ordinary route with launch, steady driving, a bend and a natural
signal/traffic encounter. Do not manufacture AEB or dangerous traffic.

The driver remains ready to take control. On an unexpected event take control,
allow at least 10 s of passive aftermath where safe, and wait for the export
completion before closing the app. Early shutdown is explicitly incomplete.
Inspect the main dossier and all component loss counters; integrity alone is
not completeness or a successful drive. No new drive is requested in this task.

Read-only commands from the repository:

```powershell
python -m tools.prepare_oct25_diagnostic_build --status 'C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics'
python -m tools.prepare_oct25_diagnostic_build --inspect 'C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics\incident-<ID>.json'
```

`compileall` and `git diff --check` complete the final static checks. The exact
delivered verification is targeted installed-base verification, not a new whole
workspace-suite PASS. No ACC or Phase 7 driving-completion claim is made.
