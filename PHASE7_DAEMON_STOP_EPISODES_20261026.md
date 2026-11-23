# Daemon-host diagnostic export and stop episodes — 26 October 2026

This is a diagnostic-only continuation of combined10. **Frozen candidate 26 is
READY FOR CONTROLLED CAPTURE / OFFLINE VERIFIED; GAME NOT VERIFIED.** Final
handover completed 27 October 2026. The exact daemon-host runtime, both modes,
capacity and unchanged numeric timing gates passed. Nothing is deployed,
armed or started in the game. Combined10 and earlier candidates are superseded.

## Live evidence and first causes

The installed combined10 receipt/content check verifies all **55** recorded
files. Current receipt SHA-256:
`4e330af07e08345ad7ddcafae04da63c3ede157649044492e5680250471db79a`.
The read-only incident audit is
`docs/steering-audit/oct26-daemon-episode/live-incident-audit.json`.
Original logs/files in the installation and attachment are unchanged.

The original
`incident-fb1707f7fda74c538def96bb30a960a2-36250.json` hashes to
`c756538e3be443cb6dd6a8fde839c48a26ea87020cf522359a5d024acf5ada73`.
It is integrity-valid, **not complete**: AP part missing, five consumed-input
references missing, and retained streams have a >52 s internal gap. Nominal
range 4306.5795171–4429.7033036 does not prove continuous coverage.

The log records planned continuous holding at 14:56:27, ACC emergency target
51 at 14:56:39, and the export assertion at 14:56:41. This task does not judge
or change the control decision. First braking ownership/reason and later
disable/intervention remain separate timed subevents.

`core/plugin_manager.py` starts plugins with `daemon=True`. The existing AP
background exporter called `_run_admitted_diagnostic_export`, which attempted
`multiprocessing.Process.start()` from that daemon host. The independent
Windows-spawn reproduction fails before repair with the exact assertion
`daemonic processes are not allowed to have children`. A thread inside a
daemon process does not remove this Python restriction. The previous main-
process qualification missed the architectural boundary.

## Diagnostic-only implementation

- The application's existing non-daemon Manager hosts a narrow export service
  with three fixed production entry points. The diagnostic bootloader uses a
  normal dict-compatible Manager/proxy with only these added service methods;
  no new longitudinal publication/arbitration implementation is substituted.
  Plugins reserve its single slot before transmitting their owned payload.
  The existing background writer waits; control does not. Unknown export
  targets are rejected. A failed part releases the reservation. An abandoned
  pre-submission reservation expires; running work retains the existing child
  deadline/RSS cleanup. No internal multiprocessing daemon flag is modified.
- The same original codec, one admitted export child, 64/32 MiB Engine/AP
  rings, 32 MiB Engine file, 1,536 MiB child and 2,048 MiB additional diagnostic
  qualification budget remain. No unbounded payload queue, new collector or
  control-thread heavy I/O is introduced.
- Explicit observation edges cover braking/stop requests, zero-speed stops
  without a recognized reason, resume and active disable. Waiting extends its
  tail without emitting a stop every tick. Generic ego/traffic transitions are
  retained within an episode but no longer repeatedly create/extend unrelated
  episodes indefinitely. These are observational classifications, not new
  stop/gear rules or inferred clearance.
- Long pending episodes can seal bounded 20 s continuation parts. They share
  an episode ID and ordered part number, record the predecessor identity and
  exact manifest hash, and keep overlapping existing evidence. An open
  continuation is not a complete episode. Final completion requires the
  predecessor/attachment checks; unavailable evidence remains incomplete.
  Disk rotation remains bounded and recoverable. Very slow/missing export or
  finite-store exhaustion must not be reported as lossless completion.
- The Engine retains an extra 0.5 s of **existing diagnostic rows** inside its
  same byte budget, as AP already did, for binding dependencies just outside
  the left boundary. It does not extend command freshness or synthesize data.
  The live missing references were the actual rows immediately before the
  first retained pedal binding, not evidence that a later packet could replace
  those inputs.

## Frozen scope and tests

The current exact development snapshot is
`docs/steering-audit/oct25-incident-assembly/daemon26-release/`.
Its nine-file manifest includes the seven combined10 files plus diagnostic
Manager integration in `core/ipc/shared_state.py` and `bootloader.py`.
Each source and installed original has a SHA-256. No ACC/plugin VERSION or
DLL change; installed control functions are compared against the installed
baseline with only the documented observational hooks removed.

Proofs preserved before final qualification:

- `daemon-before.log`: the real spawn/daemon reproduction fails with the live
  assertion. After repair the same daemon host exports a hash-valid replay.
- Earlier `live-warm.log` and `terminal-episodes.log` checked assembly only and
  could incorrectly count a startup dossier with missing prehistory. They do
  **not** prove full lifecycle completeness. Strict readback exposed this and
  its failing results are preserved in `daemon12-narrow.log` (5 failures,
  11 passes). No assertion was relaxed to accept those dossiers.
- `daemon16-narrow.log` and its immutable test outputs prove a fully complete
  manual-disable case in the real daemon host: 30 s prehistory, both exact
  parts and ordered physical calls. Long-wait continuation still exposed AP
  left-edge loss. The correction retains one exact predecessor tail and one
  next-case pin, each capped at the unchanged AP ring allowance. No previous
  input is replaced by a later read. `daemon17-narrow.log`: **7 passed**, with
  a fully verified three-part long-wait episode; startup's missing prehistory
  remains explicitly incomplete. Final full qualification runs against 19.
- Narrow tests cover bounded reservation, invalid exporter kind, malformed
  AP part/failure cleanup, stop edge deduplication, continuation identity,
  post-disable/resume tail and exact left-boundary consumed-input lineage.

Test-development failures are preserved, not production causes: the generic
lifecycle fixture initially bypassed Engine traffic publication (therefore no
join request); its first modeled green transition moved before the existing
hold contract permitted it. The corrected test uses the actual publisher and
the established supported zero-speed green handoff. Control assertions were
not weakened. A temporary Manager proxy was also retired before Windows spawn
in the new timing host; keeping its owner alive fixes that harness failure.
Those timing runs performed no real exports and cannot qualify export cost.

## Qualification boundary

Use the existing maximum-load scenario with `--daemon-host`, not a new
benchmark: same 1,400 ticks/70 modeled seconds, native 40+40 records and
trailers, concurrent combined normalization and exports, off/on in both modes.
The supervisor samples the daemon host, existing Manager broker and admitted
export descendants separately. Its own interpreter is excluded. Report baseline
and diagnostic contrasts separately; original timing gates and approved budget
are unchanged. No sizing overrides or real traffic mapping are permitted.

Final timing, capacity, failures, regression summary and exact identities will
be recorded under `docs/steering-audit/oct25-traffic-qualification/daemon26-release/`
and in the release qualification result. Until all mandatory gates pass there
is **no final ZIP or READY claim**. Missing history, pauses/source loss, shutdown
before the tail, delayed parts and hash failures are not successful captures.
Backend call return remains distinct from game consumption.

## Additional reproduced export boundaries

The child-crash test killed only the exporter owned by its test Manager. With
large ordinary Windows spawn arguments, the sender could block in
`Process.start()` before the old completion deadline even began. The correction
owns one capped **128 MiB internal transfer** in shared memory and starts the
child with a name/length/pipe only. The existing background exporter polls child
liveness and its original completion/RSS bounds, and always unlinks the mapping
and releases admission. This is internal transport of already owned primitive
data; the verified external typed-JSON/byte/hash format is unchanged. The real
crash reproduction passes after this correction. It does not prove a hard OS
memory reservation or survival of power loss.

After disable, control intentionally stops consuming traffic. Its old dense
ring is rotated. A seal riding only on later traffic therefore cannot complete
that AP part. The existing Engine background writer now publishes one compact
diagnostic seal slot. The AP's existing background writer reads only this slot,
retaining the original rotated ring. It exports those exact decisions plus
passive subsequent observations, not the newly read request as a control input.
The background rendezvous also handles a stop whose open request had not been consumed before
disable. If the ordinary replay writer was busy, its existing idle handoff is
used; no new thread/collector/queue or control-thread SDK/IPC read is introduced.
The original dense replay remains separate: its worker returns the original
path before the existing idle handoff begins AP attachment. A development
attempt to wait inside the original replay operation failed the unchanged
`test_combined_dense_and_automatic_history_exports_coexist` regression; that
attempt was removed. The superseded 18 run was stopped after reproducing this
known failure, rather than finishing an unnecessary old qualification.
`daemon19-narrow.log`: **8 passed**, including the unchanged coexistence test
and strict complete manual-disable case. Missing/delayed seals remain explicit incomplete
evidence, not completed cases.

Long-wait qualification uses 45 real seconds of stopped model time. Earlier
unpaced loops advanced tens of simulated seconds while the OS export process
had barely started; those overload runs are preserved as incomplete evidence,
not claimed live-cadence proofs. Test-host result deadlines include that real
waiting time; no control/SDK freshness or runtime export limit is increased.
Immutable manifests are inspected once per test poll rather than repeatedly
expanding the same large startup file. Final assertions require `complete=true`
and `incomplete=false`, not just attached parts.

## Retention and known limits

The existing 64 KiB journal remains a short safety tail; it does **not** provide
the full incident. Every physical call in the accepted full window is instead
retained in the existing incident ring with its exact decision/input references.
Each part reports these streams separately. The AP keeps one rolling ring, one
pending/next-case prehistory, one predecessor overlap and bounded frozen work;
these are exact shared row references, not whole repeated producer packets.
Pins and predecessor overlap are independently capped at 32 MiB. Overflow is
counted and prevents completeness. Final RSS qualification includes this actual
ownership and the Manager/export processes within the approved 2 GiB additional
budget; a nominal byte allowance alone is not a performance proof.

Files appear automatically under the installation's `route-diagnostics` after
normal startup of the approved diagnostic overlay. `incident-<id>.json` is the
manifest committed last; it names hashed Engine replay and `ap-inputs-<id>.json`
attachments. Long episodes link bounded parts by common episode ID, part index,
predecessor ID and exact manifest hash. Recoverable rotation uses `archive/`.
No arm command is needed. A valid hash does not imply a complete window, a
safe/successful drive, game consumption of a backend write, or runtime authority.

The original live incident is irrecoverably missing the recorded AP part and
five historical references in available files; this implementation cannot
manufacture them. Shutdown before the tail, paused/lost sources, permanent
worker failure or finite disk exhaustion remain explicit incomplete outcomes.
The original 53 s gap cannot be attributed to a particular internal operation
from the available historical timings alone.

## Regression and subsequent qualification boundary

Frozen 19: **464 passed, 30 subtests passed in 570.33 s**. Runtime hashes
remained unchanged before/after; the complete selection, preserved storage-only
legacy exclusions, test hashes and log hash are in `daemon19-release`.
This is the relevant targeted regression selection, **not** a claim that the
entire repository pytest suite ran. The three untouched legacy exclusions
assert the rejected nested-sharing private storage graph; the chosen simple
format has its independent exact values/types/bytes/immutability tests.

The same nine runtime sources pass compileall. `git diff --check` passes;
LF/CRLF warnings are not code errors. All **55 installed receipt hashes** still
match. Engine, longitudinal control and Autopilot payload hashes are identical
to that installed baseline; diagnostic changes are in the core storage/export,
Manager integration and temporary config. No plugin VERSION or DLL is changed.

Its later load did **not** qualify release: same final-frame refusal left the
finite combined test at 2,911/2,913 calls, one lock acquisition waited 6.336 ms,
and real-automatic Engine p99 was 18.392 ms against 16.67 ms. The same off
baseline had **18.428 ms** Engine p99: its whole cost cannot be attributed to
incident capture. These results remain under `daemon19-release`; no ZIP was
created from them and the timing gates were not changed.

Narrow attribution and correction (diagnostics only):

- `contention-before.log`: three reproducible failures. GC-capable record
  container creation occurred while owning the ring lock; primitive JSON leaves
  went through unnecessary dataclass reflection; and two pedal calls with the
  very same owned source expanded that source twice.
- Allocate record/entry/weak-reference containers and the compression batch
  before the lock. Preserve atomic sequence/capacity/accounting changes under
  it. This reproduces a possible allocation/collection blocker; without interval
  traces it does not prove the exact cause of the historical 6.336 ms outlier.
- Normalize exact builtin scalar types before reflection, preserving the old
  path for subclasses/dataclasses and all output values. Expand an identical
  owned pedal source once per call, using the already verified primitive codec
  for detached returned copies. The call-local cache is capped at **512 KiB**;
  no mutable shared-state lookup, new format, persistent cache or queue is used.
- A binding-cache experiment was rejected after attribution found **0 exact
  consecutive repeats / 496 calls**. No such speculative cache is implemented.
- The finite load had shut the normalizer down just after its final refused
  offer, despite keeping no further normal capture opportunity. It now drains
  that same immutable final offer through the existing one-slot worker before
  closing the test. The original frame, times, inputs and sequence are unchanged;
  no control/SDK read, physical write or production retry queue is added. Tail
  retries are reported separately. Full-window incident evidence was already
  exact in 19; missing the test's final two calls was not hidden by relabeling
  that evidence complete.
- Preserve legacy shared-value usage accounting: two fields pointing to the
  same owned input are charged/released once. The strict compatibility test
  rejects a negative usage count; no simple-record or external format changes.

`contention21-after.log`: **36 passed**. Frozen 21 runs the original maximum
load first, then its broader exact-runtime regressions if those gates pass.
Earlier 20 measurements were stopped after the compatibility mistake was
detected, before final regressions; they are not release evidence.

Final capacity/timing/RSS assessment is still required before packaging. No
development snapshot is a deployment alternative and no new ZIP is delivered
until that assessment passes the original gates.

## Last diagnostic-only blockers reproduced

Frozen 21 resolved capacity, exact combined trace and lock-wait gates, but
real-automatic Engine p99 **16.8127 ms** exceeded **16.67 ms** (off baseline
15.8249 ms). Whole-tick p99 increased 29.2016 → 33.7137 ms; this passed the
unchanged +8.33 ms criterion but did not waive the separate Engine gate.
The later cooperative-yield experiment (22) was **rejected**: Engine p99 was
19.5060/21.5997 ms; its off baselines already had 19.8214/18.7745 ms, and real
whole-tick increment 8.7752 ms also failed. All measurements remain preserved.
Yielding/extra normalization polling is removed from the candidate. The user
explicitly approved removal of only that new experimental test; its source
and failed/successful probe logs are retained in `rejected-cooperative-test.py.txt`
and `cooperative-*.log`. No established safety/export expectation was removed.

The next attribution found the old short journal still JSON-encoded and
compressed source trees in `PedalJournal.bind`. The temporary approved build
now freezes that already-consumed source with the **same existing verified
primitive codec**, under its **unchanged 32 KiB source / 64 KiB journal bounds**.
Legacy compaction and expansion happen at `unpack_source` on the existing
export/normalization path. Normal builds retain their original path. No new
external schema or serialization format is introduced; readers still receive
the same source fields. The full input window remains independently exact.
There is no new SDK/IPC read or deferred mutable pointer. Source oversize is
explicitly unavailable in the short tail, rather than increasing its budget.

`legacy-bind-before.log` fails the unchanged expected source values when JSON/
compression is prohibited. `legacy-bind25-after.log`: **56 passed**, including
the prohibition of control-side compaction itself, exact detached readback,
combined/dense coexistence, first fault and safe release history, AP overlap
and ancestor-chain completeness. The internal raw source can shorten the
legacy safety tail; the accepted full incident's every-call stream is the
required detail, not that tail. Existing source budget and loss flags remain.

Another negative assembly test found that a complete second/third part could
otherwise hide an incomplete first part. `chain-before.log` reproduces that
false-complete result. Each part now propagates verified predecessor-chain
completeness, and inspection rejects a complete claim with an incomplete
ancestor. The final positive long episode must still pass; a valid hash or
two good successor parts cannot repair absent original evidence.

Frozen 26 is the only current candidate. 11–25 are superseded development or
failed qualification snapshots; none is a new delivered ZIP. Final runtime
hashes, exact installed baseline and acceptance criteria are frozen before its
load/regression runs. No qualification result from 19/21/22/23 substitutes for
the final runtime's own checks.

Frozen 25's final regression run found one genuine compatibility error:
`test_oversized_snapshot_is_unverified_not_an_unbounded_allocation` expected
`UNVERIFIED_SNAPSHOT_BUDGET_EXCEEDED`, but the new internal source path used the
generic `UNVERIFIED_DIAGNOSTIC_CAPTURE_FAILURE` marker. **469 tests / 30
subtests passed, one failed**; this is not a passing candidate and no ZIP was
made. Frozen 26 supplies the original source-size bound to the verified codec
and preserves the original budget-exceeded marker for those exact errors.
Unsupported/corrupt capture errors remain distinct. The original test is
unchanged; `budget26-after.log`: **47 passed**. Final broad regression and load
qualification are performed over 26, with no reuse of 25 as its qualification.

**Final frozen 26 regressions: 470 passed, 30 subtests passed in 562.36 s.**
Every frozen runtime SHA-256 remained unchanged before/after the run.
Qualification log SHA-256:
`bcf84f885e0bea15344655bb6a22f418e37a7f82922c481ace6a9d410640f7b5`.
The same original oversized-input test now passes with its original expected
budget marker. This is the complete relevant selection, not a claim to have
run the entire repository test suite. Existing private storage-graph exclusions
and the independent exact-codec replacement tests remain explicitly listed.

All six real-daemon lifecycle cases produced a fully verified final dossier:
red/wait/green while still active in both modes; manual disable with post-tail
in both modes; and long wait split into three linked episode parts then resume
in both modes. The startup dossier in each directory remains truthfully
incomplete when 30 s prehistory was unavailable. It cannot satisfy the test.
Final long-wait predecessors and the closed final part all pass complete-part
coverage. The compact original results/manifests and attachment hashes are
preserved under `daemon26-release/lifecycle-readback/`; primary raw maximum-
population model captures remain in the traffic-qualification directory.

The older generic `build` strings in some diagnostic envelopes are legacy
format labels, **not** sufficient runtime deployment identity. Keep the exact
deployment receipt and candidate/runtime SHA-256 manifest with the capture;
actual session/activation/navigation intent/revision/route-build fields are
preserved in the exact consumed inputs. This task does not relabel original
envelopes or manufacture a different route identity.

## Frozen 25 maximum-load result

The existing assessor returns **READY FOR CONTROLLED CAPTURE**, **zero failed
load gates**, for frozen 25. Broader regressions and archive readback must also
pass before final delivery. Original timing criteria SHA-256 remains
`7a74d5032dabb5264c5d13bd8a1895adf335768f6a8b3be45cda2f1c480567ff`.
Only the explicitly approved memory/file allowance differs from the original
25 October criteria. No capacity/file sizing override is used.

Each mode runs 1,400 ticks / 70 modeled seconds, maximum **40 moving + 40
parked**, three supported moving trailer slots, lead/crossing actors, target
change, signal stop/resume, overlapping subevents, the real one-slot combined
normalizer and concurrent admitted exports. The host is a real Windows-spawn
**daemon**; the existing non-daemon Manager owns the sole export child.
Vehicle/game physics and live traffic are modeled, not measured in ETS2.

All times below are milliseconds, in the order **p50 / p95 / p99 / maximum**:

| Measurement | Simple automatic | Real automatic |
| --- | --- | --- |
| Whole tick, incident capture off | 16.019 / 25.537 / 28.024 / 53.554 | 16.070 / 26.699 / 29.565 / 39.059 |
| Whole tick, capture/export on | 19.011 / 28.792 / 32.793 / 47.495 | 19.136 / 24.330 / 28.808 / 40.535 |
| Added whole-tick p99, on minus off | +4.769 | -0.757 |
| Engine flush, capture off | 3.625 / 12.232 / 15.585 / 18.876 | 3.479 / 12.455 / 15.382 / 20.470 |
| Engine flush, capture on | 3.921 / 13.945 / 16.232 / 21.266 | 3.347 / 12.663 / 14.621 / 26.239 |
| Whole tick while export busy, 188 samples | 23.084 / 30.387 / 33.574 / 47.495 | 19.957 / 24.788 / 26.600 / 34.700 |
| Ring lock acquisition, 57,035 / 56,687 samples | 0.0005 / 0.0012 / 0.0018 / 0.0914 | 0.0004 / 0.0010 / 0.0015 / 0.1210 |

The negative real-mode p99 contrast is ordinary run variability, **not** proof
that collecting evidence accelerates control. The off baseline already has
whole-tick maxima above a 16.67 ms control period; the existing 50 ms whole-
model p99 / 100 ms maximum gates account for serialized producer work. It is
not legitimate to attribute that whole baseline to the collector. The separate
Engine p99 <=16.67 ms / maximum <50 ms gates pass in both modes, as do added
p99 <=8.33 ms, lock p99 <=1 ms / maximum <=5 ms and no control-thread export I/O.
CPU, GC, inclusive operation durations, raw supervisor RSS and exporter spans
remain in the original JSON results; inclusive phases are not added together
or presented as isolated CPU/IPC waiting.

| Completeness / ownership | Simple | Real |
| --- | --- | --- |
| Actual warm event coverage | 30.000 s pre + 15.550 s post | 30.000 s pre + 15.550 s post |
| Exact full-window physical pedal calls | 1,927 / 1,927 | 1,927 / 1,927 |
| Required AP commands / missing | 912 / 0 | 905 / 0 |
| Missing decision/input references; sequence gaps | 0 / 0 / 0 | 0 / 0 / 0 |
| Capacity drops / capture failures | 0 / 0 | 0 / 0 |
| Exact native-byte/frame/time/identity readbacks | 456 | 456 |
| All combined normalized physical calls | 2,913 / 2,913 | 2,913 / 2,913 |
| Combined rejected offers (reported, not accepted) | 632 | 691 |
| Logical backend gets, identical off/on | 575,175 | 554,986 |
| Dossier including both attached parts | 36.197 MiB | 35.636 MiB |
| Runtime host + Manager conservative peak sum | 318.059 MiB | 315.289 MiB |
| Maximum one export child | 1,080.520 MiB | 1,065.082 MiB |
| Runtime family conservative peak sum | 1,398.578 MiB | 1,380.371 MiB |

Physical-write, decision and native-input digests are identical off/on; no
positive pedal overlap or control fault occurs. Rejected combined offers are
not evidence samples, but accepted cursor recovery preserves the calls. The
simple run needed one explicitly reported quiescent final-offer retry at the
finite test boundary; real needed none. This is not a hidden production queue.
No additional control-thread get/SDK read is introduced. Background-only seal
rendezvous reads on manual disable are separately tested, not counted as fresh
control observations or first-delivery measurements. The coupled model's
logical get counts are **not measurements of distributed Manager IPC latency**.

Peak memory scope is the runtime host's original monitor before offline
inspection, plus independent broker/child peaks conservatively summed. The
supervisor also observes later offline inspector allocations; those raw values
are retained, but are not mislabeled runtime ownership. All measured parents
are below 512 MiB and the whole measured family below 2,048 MiB **even before
subtracting their baseline**; child <1,536 MiB, at most one child at a time.
This is stronger than the approved incremental allowance in this model, not
an OS hard reservation or a claim about the application's total Map/UI RSS.
Engine/AP retained high-water bytes remain within their 64/32 MiB ceilings.

Machine-readable result: `daemon25-release/MEASURED_SUMMARY.json`; full raw
load results and unchanged assessor are under the traffic-qualification tree.
These are diagnostic-build readiness proofs, not repaired ACC or GAME VERIFIED.

## Final frozen 26 handover — 27 October 2026

This section supersedes the frozen-25 table above; its original measurements
remain historical evidence. No runtime changed after the final 26 regression
and maximum-load runs. All four raw off/on result files remain byte-identical.
The original strict BLOCKED assessment is preserved separately. The user
explicitly approved requiring complete evidence from **enabled capture**, with
capture-off serving only as a timing/control baseline. The simple off run lost
two calls in its old short journal (2,911 retained); this is **not complete**.
Both enabled runs retain all 2,913 calls. This approval changes no numerical
timing, memory, safety, output-equivalence or enabled-completeness gate.
`scope-reassessment.json` records the approval, old/new assessor hashes and
unchanged raw measurement hashes. No measurements or runtime regressions were
repeated merely to apply that approved scope.

All times are milliseconds, **p50 / p95 / p99 / maximum**, 1,400 ticks per
mode, 70 modeled seconds. Maximum traffic is 40 moving + 40 parked records,
three supported moving trailer slots, with lead/crossing traffic, target
change, signal waiting/resume, overlapping events and concurrent export.

| Final 26 measurement | Simple automatic | Real automatic |
| --- | --- | --- |
| Whole tick, incident capture off | 12.304 / 21.568 / 23.250 / 53.203 | 12.010 / 20.657 / 22.537 / 31.403 |
| Whole tick, capture/export on | 18.816 / 24.174 / 28.453 / 37.832 | 15.369 / 23.207 / 24.998 / 35.205 |
| Added whole-tick p99 | +5.203 | +2.461 |
| Engine flush, off | 3.002 / 11.361 / 13.405 / 17.427 | 2.880 / 11.112 / 12.774 / 16.763 |
| Engine flush, on | 3.486 / 12.434 / 14.680 / 28.124 | 3.299 / 12.653 / 14.415 / 24.986 |
| Whole tick during export, 188 samples | 19.458 / 24.119 / 25.602 / 36.633 | 18.237 / 24.166 / 26.204 / 35.205 |
| Ring lock wait | 0.0004 / 0.0011 / 0.0015 / 0.0133 | 0.0004 / 0.0010 / 0.0014 / 0.0446 |
| Runtime parents, conservative peak sum | 330.395 MiB | 321.906 MiB |
| One export child peak | 1,080.266 MiB | 1,065.055 MiB |
| Runtime family, conservative peak sum | 1,410.660 MiB | 1,386.961 MiB |
| Dossier size, both parts | 36.211 MiB | 35.656 MiB |
| Logical gets, identical off/on | 575,175 | 554,986 |

The baseline already exceeds the nominal 16.67 ms period in whole-model
ticks. That serialized producer workload is not attributed to diagnostics.
Original separate gates still pass: whole-tick p99 <50 ms / maximum <100 ms,
added p99 <=8.33 ms, Engine p99 <=16.67 ms / maximum <50 ms, lock p99 <=1 ms /
maximum <=5 ms. These inclusive phases are not summed as separate CPU costs;
logical gets are not a distributed IPC-latency measurement. Memory scope is
the runtime monitor plus conservative independent broker/child peak sums,
excluding later offline-inspector allocations. Absolute measured runtime
family <2,048 MiB even before baseline subtraction; parents <512 MiB and
child <1,536 MiB. This does not promise an OS reservation or cap total Map/UI
application memory. Approved ring/file ceilings remain unchanged.

Enabled captures in both modes preserve **30.000 s before + 15.550 s after**,
all **1,927/1,927 exact physical pedal calls** in the event window, zero missing
decision/input references or sequence gaps, and zero capacity/capture loss.
Required AP commands: 912 simple / 905 real, none missing. Each mode verifies
456 native byte/frame/time/identity readbacks. Off/on physical-write, decision,
input digests and read counts match; no positive pedal overlap or control
fault occurs. The 64 KiB legacy journal is still short, but is not the sole
detail: every full-window call and immutable binding is in the incident ring.

Exact frozen-runtime regressions: **470 passed, 30 subtests passed** in 562.36 s.
This is the full relevant selected regression set, **not the whole repository
pytest suite**. The preserved selection documents three old private storage-
layout exclusions; exact codec and completeness tests run independently.
Six actual Windows-spawn daemon lifecycle cases pass full dossier checks,
including active wait/resume, manual disable and long linked continuations in
both modes. Crash, missing/late part, overload and incomplete ancestry remain
explicit failures, never promoted to complete. Eight assessment-tool tests
also pass; enabled loss/error/queue gates remain mandatory after the approved
off-baseline scope change. Compileall and `git diff --check` pass.

### Single frozen package and return archive

Directory: `docs/steering-audit/oct25-incident-assembly/daemon26-release/`.

- `ultrapilot-diagnostic-20261026-26-candidate.zip`, SHA-256
  `b34abd71747a2b71f0ee4ab58e508bc908eb9362952418dd83a3cdc83fdf3291`.
- `rollback-installed-base.zip`, SHA-256
  `ab7a5cbf3489d9c8633942d23a488fce23d80e7ce409f1fbcc2a3cbe73496339`.

The candidate contains nine installed-base runtime files plus the exact
manifest. The return archive contains all nine installed originals and the
original deployment receipt. All entries are read back and hash-checked;
all 55 installed receipt files remain unchanged. Engine, longitudinal control
and Autopilot payloads equal the installed baseline; the isolated diagnostic
Manager/bootloader overlay does not substitute dirty working-tree control
changes. No DLL or plugin VERSION change. Source provenance is uncommitted
and recorded truthfully, not presented as a clean released Git commit.

`DEPLOYMENT_AND_CAPTURE.md` gives the conditional transaction/rollback and one
short capture procedure. Nothing is authorized to deploy yet. After approval,
normal startup enables this existing automatic capture without arming. Output
is `C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics\incident-<id>.json`
with its named Engine replay, AP attachment and continuation lineage. Wait
35 s of live telemetry for prehistory, then retain at least 10 s live telemetry
after resume/disable and allow background export to finish before app exit.

**READY FOR CONTROLLED CAPTURE is diagnostic-build readiness only.** Original
missing AP/five references cannot be recovered; the historical >52 s gap is
not explained by these tests. Startup without prehistory, pauses/source loss,
early shutdown and finite-storage exhaustion remain explicitly incomplete.
No backend return proves game consumption. Driving behavior, repaired ACC,
and this build's live effect remain **GAME NOT VERIFIED**.
