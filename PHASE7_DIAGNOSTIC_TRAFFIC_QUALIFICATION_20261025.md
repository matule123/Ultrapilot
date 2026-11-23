# Populated-traffic qualification of the temporary diagnostic overlay

Latest export-only follow-up:
[PHASE7_DIAGNOSTIC_EXPORT_OVERHEAD_20261026.md](PHASE7_DIAGNOSTIC_EXPORT_OVERHEAD_20261026.md).
Current paired timing passes; the original capacity/RSS allowances remain
unapproved. Earlier results below are historical, not current readiness claims.

25 October 2026. **BLOCKED — not READY FOR CONTROLLED CAPTURE.**

Latest user-directed follow-up: [PHASE7_SIMPLE_RECORD_PROPOSAL_20261025.md](PHASE7_SIMPLE_RECORD_PROPOSAL_20261025.md).
It independently verifies a simple per-record format before integration and
delivers one full-window model/budget proposal. The user no longer requires
32 MiB to be an absolute design constraint, but no higher production limit is
approved or applied. The older sections below remain historical evidence.

## Latest continuation: complete consumer/pedal evidence, not a new handover

The sections below this continuation describe the historical build-04 result.
**No currently eligible final package exists.** The intermediate build-05 ZIP
was withdrawn before handover; its `SUPERSEDED.md` explains why. Build-06 and
build-07 directories are development/measurement evidence, not deployment
packages. No new BLOCKED ZIP is delivered. Nothing was installed or driven.

The installed receipt is still SHA-256
`61d7bd251991e0933f9f598d80f3620f6f65e581fa68d6a1fb7d4faa59a38935`.
Preparation rechecked all 53 receipt files and 141 control-function ASTs.
The latest exact installed-base overlay is inventoried in
`docs/steering-audit/oct25-incident-assembly/traffic07-evidence-only/candidate-manifest.json`.
It includes only diagnostic taps, storage and export changes; plugin VERSIONs,
DLL, control decisions, regulators, holds and timeouts are unchanged. The
unrelated dirty workspace Engine/AP controls are not its runtime baseline.

### Proven causes and retained changes

1. Large primitive snapshots were recursively copied repeatedly, then AP
   transactions were JSON-encoded/compressed in the tick. AP request/seal also
   expanded the whole rolling input ring. Ownership capture now uses bounded
   primitive bytes; JSON/archive/disk work stays in existing export children.
   Large retention compression uses one bounded passive worker per process,
   weak work references, at most 16 registered windows and batches of 32.
   No payload queue extends the 32 MiB ring. The legacy short-journal packing
   still executes its original small control-side compression; this was not
   falsely counted as removed or attributed to new large-export work.
2. The first worker prototype scanned the entire growing ring under its lock.
   At maximum load that raised p99 to 70.56 ms. The retained correction uses
   bounded weak work references, not a per-tick full-history scan. A narrow
   regression checks that large-input compression never runs on the caller.
3. The benchmark fixture retained all expanded combined samples indefinitely.
   Its history is now consumed/cleared outside the measured tick, as its write
   mock already was. Runtime evidence, input reads and GC remain enabled. This
   removes test-history growth, not a control-path safety rule. Older off
   maxima of 58--66 ms are preserved; they must not all be blamed on collection.
4. Every physical pedal callback now adds an exact ordered `backend_call` and
   immutable `decision_reference` to the existing window. `pedal_binding`
   preserves the bound input/identity and references the exact consumer reads.
   Calls retain original request/start/return times, values, backend status,
   error, pair-after and last-successful pair. The separate 64 KiB safety tail
   remains unchanged; its losses are reported as a separate component.
5. Read calls are now captured on every existing consumer invocation, without
   extra SDK/IPC reads. The inherited 10 Hz tap omitted intervening packets:
   its reproduction retained frame `[1]` instead of `[1,2,3]`. Silence during
   supported D confirmation is not a missing periodic sensor frame. Exact
   binding/input and physical sequence checks still reject genuinely missing
   records; completeness was not inferred from a time envelope alone.
6. Version-4 marshal bytes include Python reference/intern flags; equal IPC
   copies could hash differently. A reproduction retained two allocations for
   equal values. The internal version-2 ownership representation avoids those
   flags, preserves primitive values/types/times, and passes the exact-copy
   regression. External evidence remains the existing hashed JSON/raw-byte
   codec. This improves sharing but does **not** finish nested sharing below.

### Final measured state of the current implementation

Same installed-base runtime, native 40 moving + 40 parked records, three trailer
slots, 1,400 ticks / 70 model seconds, real-automatic mode. Files:
`shared07-v2-real-off.json`, `shared07-v2-real-on.json` under
`docs/steering-audit/oct25-traffic-qualification/`. No concurrent pytest in
these measurements. The off result finished before the narrow regression log
was created. These are scripted models, not a closed-loop ETS2 measurement.

| Metric (ms unless stated) | Capture off | Capture on, required 32 MiB |
| --- | ---: | ---: |
| Whole tick p50 / p95 / p99 / max | 12.825 / 20.325 / 23.172 / 33.020 | 19.619 / 26.117 / 29.876 / 52.533 |
| Engine flush p50 / p95 / p99 / max | 4.899 / 12.139 / 13.270 / 17.590 | 6.301 / 13.358 / 16.569 / 44.960 |
| Whole-tick p99 increment | — | +6.704 (criterion <=8.33) |
| Parent peak RSS bytes | 120,954,880 | 236,535,808 |
| Largest export child RSS bytes | — | **674,865,152 (fails 536,870,912)** |
| Logical mapping GETs | 554,986 | 554,986 |
| Physical write / decision / native input hashes | Baseline | All identical |
| Positive pedal overlap / control-thread export file I/O | 0 / 0 | 0 / 0 |

During concurrent export the on tick p50/p95/p99/max was
21.764/28.029/30.544/49.547 ms. Lock acquisition p99/max was
0.0013/0.1553 ms. GC remained active: maximum 7.192 ms off, 38.337 ms on;
wall maxima are not proof that a particular historical game pause was GC.
Per-thread CPU is quantized on Windows (15.625 ms median here); it cannot
reliably separate scheduler wait from CPU at each individual short operation.
The mapping counts logical calls, **not actual Manager/RPC latency**.

The existing scenario now records inclusive phase timings. In this on run:
ownership-copy/digest total 2.371 s (103,590 nested calls, p99 0.136 ms),
capture/retention 1.901 s (25,299, p99 0.215 ms), AP finalize/handoff 0.214 s
(1,405, p99 0.280 ms), backend diagnostic callback 0.177 s (2,913, p99
0.127 ms). Legacy binding/packing p99 was 7.544/6.889 ms. Background
compression total was 3.745 s. Background process transport plus child export
and completion took up to 35.475 s; these are inclusive worker durations,
not control-thread waits. Nested totals must not be added as disjoint CPU.
The export/serialization/GC/RSS boundary still needs reduction; timing alone
does not make the current incomplete, over-budget evidence usable.

### Exact capacity blocker and sizing proof

The 32 MiB run dropped **12,659** records over the run; its warm event retained
only **27.90 s pre** instead of 30 s. This is FAIL, not an acceptable incomplete
capture. Whole-window physical sequence comparison cannot certify that run.

To size the existing representation, the **test model only** ran with an
explicit `--capacity-probe-mib 64`. The release gate rejects such probes. No
candidate source or installed runtime limit was changed. Its result is
`shared07-sizing64-real-on.json`:

- actual rolling retention: **48,542,312 B = 46.294 MiB**, 12,080 records;
  **14,987,880 B above** the required 33,554,432 B limit;
- zero capacity/capture losses; warm event **30.00 s pre + 19.10 s post**;
- **2,069** exact calls over **49.10 s**, all equal to the chronological test
  backend trace, zero missing decision/input references or call sequences;
- all **976** Engine-required command keys covered by the AP part, attached
  with AP active; warm dossier `complete=true`, verified hashes;
- this is **not a qualifying result**: the limit is different, Engine p99/max
  **17.397/57.473 ms** also fails, and child RSS reaches **694,120,448 B**.

Sizing breakdown: row envelopes occupy **23,774,032 B** (see per-kind values in
the JSON); shared bodies still include **11,238,828 B** used by
`consumed_decision+pedal_binding` and **6,283,550 B** used by command pairing.
In particular the same large traffic evidence nested inside a bound decision
and a reader packet is allocated separately. A dedicated reproduction remains
**failing** and is not xfailed or adjusted to the current behavior.

46.294 MiB is the requirement of the **current representation**, not an
information-theoretic minimum and not a reason to silently raise the limit.
The smallest needed design change is bounded publication-time storage that
shares identical nested inputs/record metadata, preserving every original
sequence, time and field, before the existing worker serializes it. It must
remove at least 14,987,880 B at this load and reduce child expansion RSS.
Simply allowing 64 MiB does not meet the timing/RSS gates and is not proposed
as a ready fix. The 30+10 window and fields must not be reduced.

Automatic approval review rejected proposed live-row repacking, then the
pre-publication transactional variant, and nested path reconstruction because
their exactness/bounds were insufficiently demonstrated. **None of those
patches was applied.** Do not bypass that review. The next necessary step is
an approved, independently losslessness/bounds-tested storage representation;
there is no missing game drive or traffic sensor needed to explain this
capacity failure. The existing control implementation must remain unchanged.

### Verification and handover boundary

- Initial two narrow reproductions fail before the changes; full-window call
  references and off-thread large compression then pass. Additional exact IPC
  copy/read tests pass. Current targeted run: **18 passed, 1 failed**; the
  remaining test is the explicit nested-sharing/capacity reproduction above.
- Earlier frozen build 05: **413 passed, 30 subtests**, with identical control
  outputs/GETs. This **does not qualify the later all-consumer representation**.
  It was withdrawn after final inspection found incomplete real-auto evidence.
- No whole repository pytest was run. No repeated broad qualification is claimed
  for the unfinished current representation. Current compile/diff and identities
  are recorded beside the evidence; a final frozen qualification/package still
  has to follow the storage fix.

**BLOCKED: no deployment/capture approval is requested, no new final ZIP or
driving procedure is issued as ready.** Original candidates, rollback ZIPs and
raw evidence remain intact. The old 05 rollback is not authority to deploy 05.
The requested single final candidate and controlled-drive handover remain
undelivered until exact 32 MiB capacity **and** export RSS/timing all pass.
OFFLINE evidence above is not GAME VERIFIED and makes no ACC reliability claim.

---

Capacity and exact-part assembly pass at the tested maximum population after
the export corrections below. Timing does **not** pass the predeclared gates.
Passing regression tests does not override that result. Nothing was installed,
armed, committed, pushed or operated in ETS2. No ACC, AEB, signal/hold rule,
regulator, control timestamp/frame, 500 ms freshness or native DLL was changed.

This report supersedes the collection-readiness claim for build 03 in
[PHASE7_DIAGNOSTIC_CAPACITY_20261025.md](PHASE7_DIAGNOSTIC_CAPACITY_20261025.md).
Older artifacts and unsuccessful experiments remain preserved as evidence.

## Verified starting identity and fixed criteria

The requested build-03 ZIP SHA-256 was verified as
`41ea7f8fec40bd825962952089b77fea569df3e816d2f6ce9b49c56c6d7c0bb1`.
All six entries and all 53 installed-base receipt hashes matched. The installed
control implementations, not the unrelated dirty workspace controls, form the
isolated verification namespace. All 141 control-function AST comparisons pass
after removing only observational hooks.

Criteria were written and hashed **before** the populated-traffic benchmark in
`docs/steering-audit/oct25-traffic-qualification/ACCEPTANCE.md` and were not moved:

- >=29.9 s before + >=10 s after, zero capacity/capture losses, original 32 MiB
  per-ring limits, exact bytes/time/frame/identity and AP part without disable.
- Same chronological physical values, selected decisions and all logical
  shared-state backend GET counts off/on; no positive pedal overlap.
- Whole modeled tick p99 <50 ms, max <100 ms; added p99 <=8.33 ms. The model
  serializes work normally distributed between processes, hence the 50 ms
  traffic period, with a maximum of two such periods. The added budget is half
  a default 60 Hz output period, not a newly enlarged freshness limit.
- Actual Engine flush p99 <=16.67 ms, max <50 ms. Ring acquisition wait p99
  <=1 ms, max <=5 ms; no export I/O or completion wait on control ticks.
- Original retained budgets; parent peak RSS delta <=272 MiB (existing aggregate
  logical budgets plus scratch), each export child peak <=512 MiB. These are
  qualification gates, not increased runtime allowances.

## Load and methodology

Each maximum-load run has **1,400 ticks, 50 ms modeled step, 70 s modeled time**.
Native source: **40 moving + 40 parked records** in the actual 6,960/1,720-byte
ABI, **three trailer slots per moving vehicle**, or 200 modeled bodies total.
All IDs are distinct; native bytes change with generation. The real reader,
selector, Policy/ACC, AP, Engine, Controller and mapped test backend are used.
Lead 10 stays observed when closer lead 11 joins; actor 12 contributes a
crossing prediction. There is a qualified red/wait/green/resume episode and
15/17 overlapping subevents in the warm dossier, without disabling AP.

The first teleporting/turning lead scripts correctly triggered the unchanged
continuity/takeover guards. They are preserved as **invalid model-input probes**,
not evidence of a diagnostic or ACC defect. The accepted script uses bounded
position changes and an additional closer lead, not disappearance as clearance.

The 8+8 population and 0/1/3 trailer layouts are also tested through the real
reader/producer ABI. A separate 70 s production run at 8+8 with one trailer
retains 30.00 s before and 19.05 s after, zero Engine/AP losses, verified AP
attachment without disable, and 592 exact native rows (18,545,278 Engine bytes
and 7,972,015 AP bytes). All these are **synthetic models**, not recorded ETS2
traffic or a closed-loop vehicle-physics experiment.

Off/on runs use the same scripted inputs. Every SDK view and Engine access is
counted at the logical mapping boundary. This verifies added read count, **not
real Manager/RPC transport latency**: the test mapping is in-process. The sample
includes 5 ms real sleep between ticks to allow exporter progress; that sleep
is excluded from measured tick time. Export processes run concurrently. RSS is
sampled every 20 ms until workers finish, excluding later offline inspection.
No pytest ran concurrently with the accepted timing measurements.

Whole-tick wall time, per-thread CPU time, separate Engine flush, lock waits/
holds and GC are recorded. Windows thread CPU updates may be quantized; wall
minus CPU is **not** a measured lock or IPC wait. Parent RSS includes the
interpreter, fixtures, modeled input expectations and test collector history;
it is not exclusive diagnostic allocation. Ring accounting is reported apart.

## Proven export blockers and minimal fixes

| Failure on the prior candidate | Proof | Retained correction |
| --- | --- | --- |
| Native `ego_body_payload` bytes in an event made the final manifest fail JSON serialization | `binary-before.log`, exact TypeError; populated run's failure receipt | Apply the existing exact zlib/base64 raw-byte codec to manifest event fields; inspect inner length/hash as well |
| A dense owner witness exhausted the 16 KiB event receipt budget and lost fields | `owner-before.log`, capture failure reproduced | Compress the owned receipt only if it fits the **same** retained 16 KiB limit; expand/verify original values at export/inspection |
| Warm maximum-traffic Engine evidence exceeded the unchanged 16 MiB replay file quota | `max04-cutin-simple-on/incident-failure-*.txt`: `SIGNIFICANT_EVENT_EXPORT_DISK_QUOTA` | Losslessly compress the existing immutable JSON stream on the export worker, with original length/hash and bounded decode; no dropped rows or quota increase |
| The temporary grouped export suppressed the original immediate automatic-disable pedal replay | `legacy-automatic-before.log`: both unchanged full production/combined coexistence tests fail on original build 03 | Keep the installed automatic-export method intact; run grouped capture from the existing significant-event hook on that same one-job writer; both tests then pass |

Tests reject damaged compressed data even after an outer hash is recomputed.
The old raw/internal record checks, part hashes, ordering, archive limits and
atomic final manifest remain enforced. The decoder reads the old representation
as well as this bounded optional representation. Use the matching new inspector;
an older reader is not a completeness certificate for the new encoded window.

A further exact-copy/marshal optimization was tried because the timing gate
failed. It did not demonstrate improvement: the tested simple-mode p99 was
36.329 ms and Engine maximum 63.236 ms. It was **REJECTED and removed**, including
its experiment-only tests. The final runtime matches the minimally corrected
`traffic04-storage` retention/codec implementation. The final remeasurement
additionally includes the immediate-safety-export restoration. Original behavior
expectations and safety regressions were not weakened. Interim failed broad
qualification (407 pass / 2 fail) is preserved separately; it is not presented
as the final qualification.

## Maximum-load capacity and exact evidence

| Metric | Simple automatic | Real automatic |
| --- | --- | --- |
| Warm event pre / post | 30.00 / 19.05 s | 30.00 / 19.10 s |
| Engine retained bytes / limit | 19,027,803 / 33,554,432 | 18,904,630 / 33,554,432 |
| AP retained bytes / limit | 7,973,043 / 33,554,432 | 7,797,793 / 33,554,432 |
| Engine/AP capacity losses | 0 / 0 | 0 / 0 |
| Engine/AP capture failures | 0 / 0 | 0 / 0 |
| Exact native records verified | 592 | 593 |
| Exact AP commands required / missing | 491 / 0 | 488 / 0 |
| AP part delivery | Verified while AP active | Verified while AP active |
| Warm dossier bytes, all attached files | 24,416,830 | 23,917,796 |
| Warm subevents | 15 | 17 |
| Positive pedal overlaps | 0 | 0 |

For every retained traffic row checked, moving/parked bytes are compared against
the exact original generation, along with native observation time, SDK frame and
full activation/session/map/dataset/intent/revision/build/geometry context.
Full immutable command contents pair Engine use to the AP decision; a newer
packet is not substituted. Startup cases remain correctly incomplete because
history before startup does not exist.

**Assembly is verified, but these dossiers are not globally complete.** The
64 KiB detailed backend ring retains only **14 writes over approximately 0.30 s**
at warm export, after 2,523/2,525 earlier write evictions. The separate decision
window and summary preserve consumed decisions, state/source changes and write
sequence/count/outcome summaries. They cannot reconstruct every individual
pre-event physical pedal edge, its exact start/return time or game consumption.
Thus the detail limit **does restrict causal proof** of several-seconds pedal
alternation or per-write latency before the short retained tail. It does not
invalidate the captured producer/AP input chain. `complete=false` is preserved;
the limitation is not concealed or filled with later headers/packets. No claim
of a universally complete incident is made, and that ring was not enlarged.
The Engine window also retains its existing per-source-gap incomplete flag
despite zero capacity losses. Neither that flag nor backend-detail loss is
cleared to obtain an overall complete verdict. A 30+10 time envelope alone
is not proof that every source produced a continuous stream.

## Whole-tick and output latency — criteria not met

All values are milliseconds; 1,400 whole-tick samples per row.

| Mode / collection | p50 | p95 | p99 | max |
| --- | ---: | ---: | ---: | ---: |
| Simple / off | 13.534 | 22.690 | 27.892 | 73.386 |
| Simple / on | 23.474 | 33.479 | 36.144 | 82.028 |
| Real / off | 12.354 | 20.682 | 25.879 | 74.515 |
| Real / on | 23.340 | 33.642 | 36.075 | 89.182 |

Added p99: **8.252 / 10.196 ms**. The simple run passes the 8.33 ms gate narrowly;
the real run fails it. The separate Engine gates below still fail in both modes.

| Engine flush | p50 | p95 | p99 | max |
| --- | ---: | ---: | ---: | ---: |
| Simple / off | 4.959 | 13.291 | 16.357 | 65.815 |
| Simple / on | 6.203 | 14.347 | **17.622** | 22.899 |
| Real / off | 4.799 | 12.552 | 14.381 | 58.437 |
| Real / on | 6.073 | 14.360 | **16.948** | **57.894** |

Base off runs also show occasional long pauses. This prevents attributing every
maximum solely to collection, but **does not excuse** the measured on-run gate
failures or authorize changing the threshold.

During active export/assembly, 405 simple / 402 real ticks:

| Mode | p50 | p95 | p99 | max |
| --- | ---: | ---: | ---: | ---: |
| Simple | 24.441 | 35.070 | 36.394 | 82.028 |
| Real | 25.328 | 34.626 | 36.102 | 89.182 |

Maximum parent GC duration: 64.802 / 64.665 ms. The preserved interim real run
had a 302.156 ms tick and 254.481 ms GC maximum; they are not overwritten by
the shorter final-run maximum and are not labeled solved. Profile evidence identifies
repeated diagnostic ownership/copying as CPU work (`copy`: 3,702 calls / 220-tick
profile, 2.094 s under profiler). The profiler perturbs execution and its export
wait/inspection totals are not control-tick latency. Aggregate GC data does not
prove the exact stack of each accepted-run worst tick or any historical game
pause. Precise attribution of the remaining worst tick/GIL pause is **unresolved**.

## Blocking, memory and output equivalence

Ring acquisition wait p50/p95/p99/max (ms):

- Simple: 0.0005 / 0.0009 / 0.0014 / 2.0574.
- Real: 0.0005 / 0.0009 / 0.0014 / 1.5929.

Acquisition gates pass. Recorded hold maxima were 53.431 / 7.680 ms; these
wall-time holds can include GC/scheduling and are not proof of that much CPU
inside a lock. Traffic and flush are serialized in this model, so this is not a
certificate of concurrent Engine-thread waiting bounds. No export file I/O or
export-completion wait was observed on the measured control thread; disk locks
and large file/codec work remain in the existing export workers/children.

| RSS metric, bytes (20 ms sampling) | Simple | Real |
| --- | ---: | ---: |
| Parent off peak | 233,025,536 | 230,920,192 |
| Parent on peak | 292,298,752 | 290,066,432 |
| Largest sampled export child | 421,576,704 | 416,956,416 |

Memory gates pass on observed peaks. Sampling can miss brief peaks; values
include interpreter/codec/test memory and are not hard RSS guarantees. There is
one job per existing exporter, no growing queue, and original retained budgets.

All logical shared-state backend GET counts match: **575,175 / 575,175** simple,
**554,986 / 554,986** real, off/on. Physical-write hashes and selected-decision
hashes match exactly, as do native input hashes. No safety guard was weakened.
These counts are not a measurement of actual Windows Manager IPC latency.

## Final frozen artifact and verification

The final development overlay identifier is **UP-DIAGNOSTIC-20261025-04** because
build 03 had reproduced export failures. It is **not a new ACC/plugin release**.
Only one current candidate is handed over; earlier ZIPs are superseded, not deleted.
The final receipt, runtime hashes, qualification, traffic assessment and rollback
are in `docs/steering-audit/oct25-incident-assembly/traffic04-release/`.

Six runtime paths only: `core/engine.py`, `core/longitudinal.py`,
`plugins/autopilot/main.py`, `core/navigation/longitudinal_diagnostics.py`,
`core/steering_replay.py`, `core/navigation/diagnostic_build_config.py`.
No DLL, settings, map cache, reports/tests, unrelated driving fixes or verification
namespace markers are shipped. The release truthfully records uncommitted
changes on the required installed base; commit.txt is not used as content proof.

Task-owned source changes are limited to
`core/navigation/longitudinal_diagnostics.py`, `core/steering_replay.py`,
`tools/prepare_oct25_diagnostic_build.py`,
`tools/qualify_oct25_traffic_capture.py`,
`tools/assess_oct25_traffic_qualification.py`,
`tests/test_oct25_populated_capture.py`, this report, the older report's
supersession notice, `PLUGIN_CHANGELOG.md` and `DEFERRED_WORK.md`.
The generated Engine overlay restores only its diagnostic export method;
unrelated pre-existing workspace control changes were not reset or installed.

The current package is for **offline review/return backup**, with collection
approval disabled because timing qualification failed. Hashes and final suite
results are recorded beside this report in the final receipt, not inferred from
the earlier build-03 test result. Whole-workspace pytest is not claimed.

Final frozen qualification: **409 passed, 30 subtests passed in 146.82 s**.
All original expectations were retained, including the two immediate safety/
combined coexistence tests that previously failed. The nine populated-ABI/export
regressions, original window/assembly/failure/capacity suites, complete following,
arbitration, service-stop, transmission, signal-contract, journal-history and
steering replay suites run against the exact packaged installed-base runtime.
`compileall` and `git diff --check` pass. No complete workspace pytest run is
reported or inferred from these selected complete regression suites.
The direct new source regression file also passes **9 tests in 1.74 s** with
the project's required `PYTHONCASEOK=1`. A prior unconfigured source invocation
failed on the repository's SDK import casing; it is not reported as a source
code defect or as PASS. `final-check.json` records the actual parsed successful
test summary and verifies the log hash, rather than pre-filling a result.

| Final artifact | SHA-256 |
| --- | --- |
| `ultrapilot-diagnostic-20261025-04-candidate.zip` | `59e7639c69cd308377a7ed4be2950894b9a5d89f37499c3565a3599488b84a36` |
| `rollback-installed-base.zip` | `541425a37201c1a4cd6b6dab2a644fbf633a58ca19c58272f7206f8e28f999ab` |

ZIP members were read back and checked against the qualification and traffic
measurement's frozen runtime hashes. Packaging verifies the original acceptance
hash and the exact traffic-tested runtime before recording
`BLOCKED_TIMING_QUALIFICATION`, `ready_for_separate_collection_approval=false`.
All 53 installed-base hashes and the original receipt are unchanged. The
parent/worker measurement and assessment files are under
`docs/steering-audit/oct25-traffic-qualification/release04/`.

## Deployment and one-drive procedure — conditional, not executed

**STOP now: timing qualification is BLOCKED. Do not install or start a capture
from this handover.** The following is the exact operational sequence only
after the blocker is resolved/requalified and the user separately approves it:

1. Close UltraPilot and ETS2 and verify their processes exited. Verify the
   candidate/rollback SHA-256 and every required installed-base hash. Any drift:
   STOP; do not mix overlays.
2. Create a fresh timestamped backup of all six target paths and original
   `manual-deployment.json`. Record the diagnostic config's original absence.
   Apply only the six manifest paths together; verify every new SHA-256; save an
   accurate diagnostic/uncommitted-build deployment receipt. Preserve DLL,
   settings, map cache, original evidence and commit marker.
3. On any copy/hash failure, restore **all five previous files** and the receipt;
   quarantine the newly added config; verify all original hashes. Do not remove
   evidence. The supplied rollback is not a second candidate for normal use.
4. Following separate approval of an eligible build: normal application start,
   **no arm command**. Valid GPS route and at least 30 s safe warm-up. One short
   familiar route: launch, steady section, ordinary bend, naturally encountered
   red/wait/green/resume, then at least 10 s subsequent driving. Do not create a
   dangerous traffic/AEB situation. Driver remains ready to take over; STOP on
   unsafe behavior or export readiness failure. Game control belongs to user.
5. Safely stop/disable AP, allow tail and background completion before closing.
   Inspect `route-diagnostics\incident-<ID>.json` using the matching inspector;
   require exact AP attachment and read every component loss flag. A successful
   backend return is not confirmed game consumption; missing detail remains
   NOT VERIFIED. Analyze the same receipt/build, not the next newest filename.

No new drive is requested now. The smallest remaining step is offline
worst-tick/allocation/GC attribution and reduction in this existing diagnostic
path, followed by the **same unchanged timing gates**. It is not a control fix,
larger timeout, new sensor or another ordinary game attempt.
