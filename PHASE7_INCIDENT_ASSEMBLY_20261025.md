# Non-disable incident assembly — 25 October 2026

**Historical build-02 handover, superseded by build 03.** Its measured Engine
capacity limitation was subsequently reproduced and corrected without increasing
the buffer budget. The only current package/results are documented in
[PHASE7_DIAGNOSTIC_CAPACITY_20261025.md](PHASE7_DIAGNOSTIC_CAPACITY_20261025.md).
The build-02 numbers and artifacts below remain preserved evidence, not the
current deployment recommendation.

## Verdict and scope

**OFFLINE VERIFIED for the missing Autopilot-part assembly blocker; GAME NOT VERIFIED.**
No driving decision, regulator, timeout, SDK timestamp/frame, parking-brake
behavior or native DLL was changed. Nothing was deployed, armed, committed,
pushed or operated in ETS2. This is the installed-base diagnostic overlay,
not deployment of the unrelated driving changes in the working tree.

This report supersedes the two complete-capture blockers in
[PHASE7_DIAGNOSTIC_BUILD_20261025.md](PHASE7_DIAGNOSTIC_BUILD_20261025.md).
That older candidate and all original evidence are preserved and superseded.

## Reproduced cause and correction

The previous Engine window could close a successful braking/waiting episode
while the corresponding Autopilot consumer inputs stayed only in its in-memory
dense replay. Their export depended on a later disable/stop. Window completeness
also did not aggregate the missing AP part or losses in the other streams.

The unchanged six-file old candidate was copied into an isolated verification
namespace. All six original hashes were checked. The four actual production-path
tests (short brake and red/wait/green, simple and real automatic transmission)
failed because the live dossier had no verified AP part. The AP remained active;
no disable was introduced to obtain the evidence. See
`docs/steering-audit/oct25-incident-assembly/baseline-isolated.log`.

The correction uses the existing PedalJournal, dense input ring and one-job
exporters:

1. Engine piggybacks a compact diagnostic open/seal request on its existing
   traffic publication. It identifies one incident, immutable time range and
   seal token. It grants no authority and adds no SDK/IPC reads.
2. Autopilot retains the original values returned by its existing longitudinal
   reads, actual `_control_tick` locals (including early wait/launch returns),
   captured truck/navigation inputs and exact finalized command. It does not
   query shared state again to reconstruct a historical decision.
3. Exact compressed transactions use the existing bounded AP input ring.
   Compression preserves the values; export expands them on the existing
   background worker, then uses the existing immutable-reference replay codec.
   One pending case, one frozen export and at most one compact next request are
   retained. There is no growing work queue or second collector.
4. The AP part is exported while AP stays active. Engine's export child waits
   at most 20 wall-clock seconds for it, outside the disk lock and control tick.
   This is an export-assembly bound, not a control freshness timeout.
5. The exact AP seal token/range, payload hash, record order and every retained
   Engine command's full immutable content are verified. A newer frame/command,
   different range or different activation cannot fill a missing command.
6. The main manifest is published last. `assembly_complete` requires the exact
   attached, verified AP part and matching commands. `complete` additionally
   requires all component loss/coverage checks to pass. Missing, failed, late,
   corrupt or shutdown-before-seal parts cannot certify a complete dossier.

Overlapping events join one existing episode with ordered subevents. An early
shutdown can export a partial/open AP part, but that cannot satisfy a later seal
request. A late file does not silently upgrade an already frozen incomplete
manifest. First causes and original timestamps remain unchanged.

## Verification of the frozen candidate

| Check | Result |
| --- | --- |
| Previous candidate, live non-disable reproductions | 4 FAIL as expected: no verified AP part |
| Final installed-base targeted qualification | 180 PASS, 10 subtests PASS, 97.59 s |
| Supplemental actual AP worker failure and Engine/AP shutdown assembly | 2 PASS, 0.70 s |
| Red → hold → qualified green → launch, both gearbox modes | AP remains active; exact AP part attached; zero missing command matches |
| Short brake without stopping, both modes | Same live assembly, no later disable/stop needed |
| Overlapping events | One ID/dossier/part, both subevents preserved |
| Delayed delivery | No final manifest before the part is present and verified |
| Missing/failed/newer/wrong-range part | Explicitly incomplete; no false complete verdict |
| Part corruption/removal and forged complete flag | Inspector rejects the evidence |
| Shutdown during open assembly | Partial part retained; incomplete dossier with exact reason |
| Installed control functions | 141 AST-equivalent after removing only observational hooks |
| Physical writes and IPC reads, diagnostics off/on | Identical, both modes, including concurrent live export |
| `compileall`, `git diff --check` | PASS |
| Full workspace pytest | Not repeated; targeted candidate qualification only |

Tests use real publication, Policy/ACC, AP, Engine, Controller, mapped test backend,
codec and exporters with modeled SDK/signal observations. They are not ETS2
measurements or proof of game consumption. Verification-only package markers
prevent pytest or spawned export processes from accidentally resolving a module
from the unrelated dirty workspace. They are not shipped runtime files.

Qualification and supplemental logs are under
`docs/steering-audit/oct25-incident-assembly/final/`. The frozen six runtime hashes
are in `qualification-frozen.json`; qualification and ZIP creation rechecked them.
The extra failure tests changed no runtime file or previously frozen test.

## Measured overhead and retained memory

900 production ticks per run; synthetic ABI-sized native buffers; actual
publication/decision/output/export code. Off/on runs are separate, same scripted
inputs, not matched physical ETS2 trials. Costs below cover the whole modeled
tick, not only compression. No pytest ran concurrently with this measurement.

| Mode | Diagnostics | Tick p50 / p95 / max (ms) | While export busy p50 / p95 / max (ms) |
| --- | --- | --- | --- |
| Simple automatic | Off | 6.469 / 8.695 / 41.248 | Not applicable |
| Simple automatic | On | 9.324 / 11.220 / 79.707 | 9.436 / 11.573 / 79.707 |
| Real automatic | Off | 6.083 / 7.160 / 28.953 | Not applicable |
| Real automatic | On | 8.875 / 10.449 / 46.591 | 8.992 / 11.061 / 46.591 |

Median added whole-tick cost was 2.855 / 2.791 ms. The on-run GC maxima were
70.495 / 37.888 ms; these are observed concurrent pauses, not an attribution of
any historical game incident. Maxima are retained, not hidden behind medians.

Physical write SHA-256 values match off/on:

- Simple: `a05c40a0a9bd1402133d36ec7e375a885896895c05555902a0d288b20d347f32`
- Real: `63db751ec72936af6e8c3ba845f1a5bd687c63c01c2c38dadc1f75f0442893bc`

IPC read-count dictionaries also match exactly. One live dossier was assembled
in each enabled run while control remained active and fault-free. The AP ring
retained 5,095,937 / 4,668,947 accounted bytes, with zero AP capacity drops or
capture failures. The fixed AP ring ceiling remains 32 MiB. Exact compressed
transactions resolved the expanded-input capacity loss seen in the intermediate
test attempt; that failed attempt is preserved, not reported as PASS.

The stress run filled the existing Engine ring: 33,543,452 / 33,525,068 accounted
bytes, with 3,634 / 3,491 cumulative capacity evictions. These losses are explicit
and prevent a full-evidence verdict. Assembly success does not conceal them.
The original detailed backend ring is still 64 KiB and intentionally short;
its evictions independently keep `complete=false`. The 1 MiB summary is unchanged.

Ring accounting is not process RSS. Logical bounds: Engine ring 32 MiB plus one
pinned pre-window 32 MiB; AP ring 32 MiB plus at most one pinned pre-window 32 MiB;
one frozen/retry window per existing exporter, at most 64 MiB each (references may
share storage). Temporary transaction limit is 512 KiB, at most 16 input records.
Export-child/interpreter/codec transient memory is additional. No memory limit
was increased to conceal loss.

## One delivered package and required base

Build: **UP-DIAGNOSTIC-20261025-02**.
Only `docs/steering-audit/oct25-incident-assembly/final/` is the current handover.
Other preparation candidates are superseded, not alternatives for installation.

| Artifact | SHA-256 |
| --- | --- |
| `ultrapilot-diagnostic-20261025-02-candidate.zip` | `04511baebea8dda2323fbd157f66ad74bd097b9869ac21e875d62a2d02a8b729` |
| `rollback-installed-base.zip` | `ba3b34eef1f8049f5a761de49e90601964a861c87555312ee994a55d669f8c11` |

ZIP contents were read back and hashed. The release manifest includes six runtime
hashes, prior hashes, qualification and overhead-result hashes, and all 53 required
installed-base hashes. Base deployment receipt SHA-256:
`61d7bd251991e0933f9f598d80f3620f6f65e581fa68d6a1fb7d4faa59a38935`.
The receipt and installed contents were rechecked during packaging. Repository
HEAD is `821dedcf1a9642a1f5767538a5daa9833c82d2d2`; this is truthfully an
uncommitted diagnostic overlay on the installed base, not that HEAD alone.

Exact runtime payload:

- `core/engine.py`: installed control baseline plus passive input/export hooks
  and the diagnostic request on the existing traffic publication.
- `core/longitudinal.py`: installed baseline plus existing-read/finalization taps.
- `plugins/autopilot/main.py`: installed baseline plus passive tick-local capture
  and part assembly on the existing exporter.
- `core/navigation/longitudinal_diagnostics.py`: existing diagnostic module extension.
- `core/steering_replay.py`: existing codec/export/inspection and exact-part join.
- `core/navigation/diagnostic_build_config.py`: temporary diagnostic-build opt-in.

No DLL, settings, map cache, tests, reports or verification package markers are
in the runtime ZIP. Plugin declarations are unchanged (installed AP 1.3.4);
the temporary instrumented build has its separate explicit identifier and is not
a normal plugin release. Unrelated workspace AP 1.3.5 and driving/SDK changes
were preserved and not substituted into the installed control baseline.

## Export location and operator steps

After separately approved installation, normal startup enables this temporary
build. **No arm command or additional collector is needed.** Files go to:

`C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics\`

- `incident-<ID>.json`: final integrity-checked dossier manifest and component verdicts.
- `incident-<ID>.md`: human-readable overview; it defers completeness to the manifest.
- `ap-inputs-<ID>.json`: exact AP input/command part for that sealed incident.
- Manifest-listed `steering-replay-...-diagnostic_incident.json`: Engine window,
  journal, backend returns, first cause and summary. Existing steering replay
  and combined export continue independently.

While safe, allow the existing 10 s post-event tail and background completion
before closing. App shutdown is not necessary to obtain the AP part. Early or
forced termination can only produce explicitly incomplete evidence. Backend
return is not confirmation of game consumption. Integrity is not completeness,
traffic coverage, a successful drive or runtime authority.

Read-only inspection from the repository:

```powershell
python -m tools.prepare_oct25_diagnostic_build --inspect 'C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics\incident-<ID>.json'
```

## Conditional installation and rollback — not executed

Deployment requires separate explicit approval. Close UltraPilot AND ETS2 first.
Verify ZIP hashes and all 53 base hashes; STOP on any drift. Create a fresh
timestamped backup of all six target paths and the deployment receipt, including
the absence of the new configuration. Copy all six files as one consistent
overlay, recheck every SHA-256 and save a receipt marking the uncommitted build.
Preserve DLL, settings, map cache, original evidence and commit marker.

On any failure restore all five prior files and the original receipt; quarantine
the newly introduced configuration file. Verify all prior hashes. The separate
rollback ZIP is not a second runtime candidate. Do not delete evidence for rollback.

## Remaining limits

The AP-attachment blocker is corrected offline. A universal complete-capture
guarantee is not made: bounded Engine/backend losses, insufficient warm-up,
arbitrarily long holds, missing/failed/late parts, low disk, forced kill and power
loss remain explicitly partial/failing cases. The measured Engine capacity loss
is a concrete retained-evidence limitation, not a steering or longitudinal fix.
The exporter never upgrades such evidence merely because a later packet exists.
Installed driving regressions are outside this task. No game reliability or
pedal-consumption result is claimed, and no new drive is requested here.
