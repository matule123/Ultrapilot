# Joint ACC / Autopilot / Engine handoffs — 18 October 2026

Scope: four incidents A–D requested in attachment
`d0a3f0db-9449-4d15-9758-debabf577c98`. This is an implementation and
receipt-bound review, not a claim of complete-system/game reliability.
No installation, game, settings, map cache or original evidence was modified.

## Build and evidence identity

Entry HEAD: `821dedcf1a9642a1f5767538a5daa9833c82d2d2`; working tree was clean.
The installed `manual-deployment.json` was checked against **all 36 actual
target SHA-256 values**, including the external ETS2 DLL target. Relevant
installed Python runtime content matches entry source after LF/CRLF
normalization. Native assets/licenses that are not repository equivalents are
not mislabeled code differences. DLL remains
`1.59.5-up-parked-records`, SHA-256
`fd06c12985fb67c48a7b9aaf5dd500d81e6ac23b928b79c95997bb8ed5d55d27`.

Entry versions: ACC 1.3.8, Autopilot 1.3.4, Map 1.1.2, DrivePolicy 1.1.4,
Turn Signals 1.0.2. Candidate changes only Autopilot's implementation/version
to **1.3.5**; the other repairs are shared core/transport changes.

`tools/audit_oct18_joint_incidents.py` inspected the existing codec, not raw
immutable-reference headers. All **13 replay/timing envelopes pass integrity**:
the eight fault files listed in the request, significant-event files at
11:17:51.484761 / 53.846528 / 59.069515 / 59.780789 UTC, and timing
`11:19:43.809206Z-plugin_stop`. The original log and preserved attachment
`d2f31236-1f0c-4775-a7a4-29f98c2e8d7d` were compared. Names alone were not
used to join sessions. Decoded copies and entry runtime/hash snapshot remain
outside Git under `docs/steering-audit/oct18-joint-handoffs/`.

All four faults have session `1`, map `promods-1.59`, dataset
`d6cc7936fce4e902761abb5d`, intent `53d0969738df4767b82dc3dc656fde2f`,
revision **10**, build `56c950d80edb4415b40506fbb9bc74de`, geometry
`b552eaba54e7415bd08e3aff8026f983620d02c6b3432b2377ce5cf38c53391a`.
Activation epochs differ as specified below. Backend return confirms a mapping
write, not game consumption; subsequent SDK samples are separate observations.

## Original timelines, before production edits

Times below are the original monotonic seconds, not file-export UTC or first
delivery estimates. Brake demands before intervention are distinguished from
later Engine safety writes.

| Incident | Input → computation → consumption → first intervention |
| --- | --- |
| A / epoch 20391648715700 | ACC SDK frame **310087596**, observation **20402.9671814** → computed **20403.0075941**, expires **20403.4671814** → AP check **20403.0135872** → first fault **20403.0211919**. Remaining lease **453.594 ms**; matching route context. Owner **78**, kind **crossing**, acquired native generation **9533**, current **9550**, chain valid; current candidate **107**. |
| B / epoch 20456949539700 | Original traffic observation **20469.5671095**, SDK **376418276**, deadline **20470.0671095** → AP vehicle observation **20469.9939852**, SDK **376834926**, computed **20470.0352168** (**31.8927 ms** reserve) → Engine command read **20470.0645307–20470.0656395** → check **20470.07334** (**6.2305 ms** overrun) → first fault **20470.0840166**. Exact compared vehicle SDK **376884924**, observation **20470.0471166**, gear **8**, speed **5.1671 m/s**. |
| C / new epoch 20483389569400 | Retired actual epoch **20480588201900**, observation **20483.375842**, computed **20483.3933718**, expiry **20483.8018787** → check **20483.4234798** → first fault **20483.4409151**. Only activation differs; **378.399 ms** remains. The producer explicitly marks `identity changed during publication`, then writes that invalid old result into the common slot. |
| D / epoch 20493466209100 | AP compared SDK **443232270**, observation **20536.5238305**, gear **0**, speed **−0.00014745 m/s** → Engine admitted restart **20536.5340647** → brake write #2098 **20536.5374975–.5375192**, value **0** → throttle #2099 **20536.5522431–.5522606**, value **0.12** → AP check **20536.5532733**, still using `continuous_service_brake` history → first fault **20536.555411**. |

A's preceding history contains selected objects 106 and 107 and crossing
demands for 78 and 106; signal braking is zero. This does **not** establish that
every preceding brake demand was false. Original full actor geometry at the
first fault is not retained, so the counterexample poses are declared models.
Owner continuity and acquisition identity are retained and were not inferred
from a picture or a mutable slot.

B's command is only **38.123 ms** old, while its traffic dependency is
**506.2305 ms** old at rejection. `recovery_deadlines` are
`[20470.0671095, 20470.4225691]`. The vehicle age is **26.2234 ms**.
This is a dependency/publication handoff failure, not the steering timeout or
a foreign route. A still-newer complete traffic value at that exact check is
**NOT PROVEN** by sampled significant events.

The preceding traffic timing sequence **10312** has signal phase
**20468.9446555–20469.1528051** (**208.1496 ms**), native read ends
**.1528566**, projection **.1725454**, publish starts **.1728634**, finishes
**.1819801**. Whole wall time is **237.3487 ms** and quantized thread CPU
delta **15.625 ms**. Thus this particular recorded pause is localized to
the signal phase and is mostly not thread CPU. The exact inner IPC/scheduling
wait is **UNEXPLAINED**. Subsequent sequences 10313–10317 resume; the final
traffic acquisition used by B occurs after these retained phase details.
Do not assign sequence 10312 or 10317 to B's final receipt or invent its missing
publish/first-delivery times. The candidate does not claim to eliminate every
future producer scheduling pause.

D's first-fault outer snapshot has a newer SDK **443265602**, observation
**20536.5414623**. It is **not** the truck AP originally compared. The retained
history has confirmed frame/time **431149420 / 20524.4102352**, last observed
**20536.4690623**, and no launch deadline. Engine's actual request uses
qualified green generation **14178**. A preceding journal trace instead
contains generation **14176**; that old trace is not proof of the actual
release witness. Post-fault writes #2100 onward are safety/cancellation output,
not the cause of the initial wait release.

## Causes → implemented repairs → counterexamples

### A: acquired crossing scope lost when the primary lead changes

First faulty condition: `UltraPilotEngine._traffic_control_observation` used
only a crossing's current positive brake or the selector's **single primary**
crossing flag to retain the positive-motion trajectory. Selecting another lead
can remove owner 78 from this scope while its zero-urgency crossing ray still
prevents `RouteLeadSelector.crossing_completion`. ACC then correctly rejects
the missing old constraint; simply changing candidate does not prove departure.

Repair: include the bounded set of **already acquired, continuously observed,
uncompleted crossing owners** when constructing that same trajectory. Do not
acquire passive zero-urgency rays. Preserve each source/owner identity, current
positive cap and independent body/AEB path. Existing explicit per-owner model
completion still ends the constraint; absence/ambiguity/teleport does not.

Production counterexample: native timed owner 78, then new lead 107 with the
original continuous owner and zero-urgency ray. At modeled 10 and 11 m/s the
entry implementation faults in both gearbox modes. The candidate keeps the
original qualified cap and active authority. A 12 m/s control case, real lead,
missing/duplicate/teleported original owner and independent immediate actor 106
are separately covered. This reproduces the code defect, **not unrecorded
historical actor coordinates**.

### B: handoff required only after calculation, but publication did not start it

First faulty boundary: `core.longitudinal.finalize` can finish a calculation
with `handoff_required=true` after all producer reads have passed. The entry
code publishes the near-expired propulsion and relies on a later receiver to
start recovery. By then the original traffic source can already be expired;
starting an unqualified new wait is correctly refused.

Repair: at final construction, start the **existing** zero-drive handoff while
the original dependency still qualifies. Publish zero propulsion, preserve the
original command/input expiry and deadline basis, and retain the causal request.
Engine constructs its separate bounded zero transition from that request; only
a genuinely newer complete AP decision ends it. The original 50 ms reserve,
100 ms wait and 500 ms observation limits are unchanged. Emergency bypass,
all other receipt deadlines and uninterrupted admitted braking remain enforced.

The counterexample uses the recorded 31.8927 ms publication reserve and
6.2305 ms overrun with independent traffic/SDK cadence and a declared distant
required red (not a recovered native head). Entry fails to start a request;
candidate writes no propulsion during the gap, then accepts a new source and
completes the original token without another N. A real owner continuity loss
across a missing capture remains a rejection, not a benign renewal. An earlier
test variant incorrectly introduced such a loss; its failure is retained and
was not hidden by changing production identity checks.

**Limit:** this repairs the proven handoff defect. The exact historical final
producer/IPC delay remains OPEN; the older 208 ms phase is not a substitute.

### C: retired ACC publication poisoned the new activation

First faulty boundary: `core.longitudinal.publish` writes the result even after
`packet()` has detected a changed publication context. Marking it invalid does
not prevent it from overwriting the current slot and aborting the new N.

Repair: one Manager-owned conditional publication compares current identity
and per-slot result order **with assignment**, under a short server-local lock.
Identity writes use that same lock. No calculation, disk I/O or proxy call occurs
under it. Bootloader, SharedState and PluginSDK use this one transport; it is not
a second controller/collector. Current faults still publish, foreign/stale data
still reject, and a failed RPC never falls back to an unchecked write.

Counterexamples cover an actual ACC tick interrupted by cancel/new N, a newer
epoch result already in the slot, and actual Windows Manager transport. Entry
overwrites the new result with `valid=false` old activation; candidate rejects
the retired commit and continues through fresh Policy/ACC/AP/physical output.
The server test also rejects a regressing current-epoch calculation and still
publishes a current-epoch producer fault. One producer slot remains one bounded
value; no result queue is introduced.

### D: old hold history combined with post-release state

First faulty boundary: AP captures history/launch early in `_control_tick`,
then `simple_auto_forward_transition` reads hold later. Engine can atomically
publish its release between these independent reads; AP has old history,
missing old hold and no launch deadline, so it produces the false zero-ratio
fault **after** the physical probe.

Repair: Engine publishes one immutable admitted transition (history, launch,
resume identity, original deadline and actual witness) together with release
state. The shared ratio rule recognizes only that matching transition. AP
then performs **at most one full input recapture and complete validation**,
instead of pairing the new history with an older truck/old hold ramp. This also
handles a genuinely newer SDK frame. No new launch authority is inferred from
a missing hold, and no deadline or SDK frame is rewritten. The actual history
and launch witness now bind the existing journal's release writes.

Counterexamples inject Engine release at the early launch read and at the late
hold read, with both same-frame and newer-SDK publication and both automatic
modes. Entry fails the original simple-auto scenario; the first partial repair
also failed the later newer-frame variant with `SDK frame regressed`, so it was
replaced by the complete bounded recapture. Qualified green now reaches brake
zero → probe → subsequent forward confirmation without another N. Red/green
flicker, another stop, engine-off, stale/foreign input, R, interrupted brake and
backend failure retain the existing refusal paths. No parking-brake actuation.

## Verification and measurements

New scenarios: `tests/test_oct18_joint_handoffs.py`, reusing real native ABI
reader, placed prefab/signal selection, Map, Policy/ACC, AP and the actual
Controller with chronological test backend writes. Five complete signal cycles
per mode retain one activation, no false intervention or simultaneous pedals.
The export test checks exact admitted release request/history after codec
round-trip; integrity is not game consumption.

The existing identity-change diagnostics test now examines the **local rejected
calculation** and asserts the IPC slot was not overwritten, plus zero physical
drive after actual session change. Its cause/freshness expectations remain;
expecting the poisoned slot itself would contradict C's required repair.
The existing `required_acc_expiry_is_not_restamped_by_new_autopilot_tick`
expectation is unchanged and passes after preserving the old command deadline.
The focused refresh-protocol run also retains the existing **125 distinct
responses over at least 75 simulated seconds**, in each gearbox mode with
diagnostics off/on (four parameter cases). Its unchanged assertions require all
125 recoveries, no failure and the original detail-memory bound. Separate
unchanged signal-hold tests require every subsequent brake write to stay
positive across a valid bounded refresh; no old pedal command is executed.

Entry reproduction before production edits: **9 FAIL / 3 PASS** in the initial
12-case matrix (`before2.log`). An additional newer-frame release variant
failed before the complete recapture repair (`newer-resume-reproduction.log`).
Subsequent targeted results and the final frozen whole-suite result are recorded
below; intermediate failing logs are preserved.

### Performance and numerical invariance

`tools/benchmark_oct18_joint_handoffs.py` compares saved entry methods against
candidate on identical modeled native records/route and physical dispatch.
Three paired repeats × two modes × 120 measured ticks, plus 25 warmups/run.
Outputs are numerically identical in this healthy non-handoff workload.
Some runs overlapped targeted tests; wall outliers are not historical attribution.
Thread CPU is quantized at 15.625 ms on this host and is not sub-ms profiling.

| Mode | Entry worst repeat p95 / p99 / max wall ms | Candidate p95 / p99 / max ms |
| --- | --- | --- |
| Simple automatic | 13.744 / 14.039 / 14.179 | 13.772 / 13.942 / 14.183 |
| Real automatic | 12.880 / 13.038 / 13.466 | 13.085 / 13.178 / 13.440 |

Separate 490 warm actual Manager publication RPCs: entry p50/p95/p99/max
**0.0718 / 0.1029 / 0.1227 / 0.1436 ms**; compare-and-commit
**0.0773 / 0.0952 / 0.1602 / 0.1846 ms**. First guarded RPC costs
**3.5824 ms** (imports/cold path), compared with **0.0940 ms** simple set.
No unbounded queue or cross-process calculation lock. The new transition stores
one value per current activation, cleared on cancellation. Existing journal
64 KiB and summary-history budgets are unchanged.

Independent-cadence model: 65 simulated seconds per mode/variant, 35 actors,
SDK 27 ms, Map 41 ms, Traffic 50 ms, Policy 61 ms, ACC 31 ms, AP 38 ms,
Engine 21 ms, jitter and 50 µs copied-RPC cost. Existing bounded journal and
exports are active. This is **not** an ETS2 latency distribution or a faithful
recreation of missing historical native actors.

| Measurement (candidate) | Simple automatic | Real automatic |
| --- | --- | --- |
| Traffic intervals p50 / p95 / p99 / max ms | 52.795 / 62.800 / 67.200 / 73.250 | 52.450 / 62.820 / 66.900 / 71.390 |
| Age at confirmed writes p50 / p95 / p99 / max ms | 42.010 / 68.520 / 75.850 / 81.520 | 41.250 / 67.420 / 74.370 / 83.620 |
| Minimum remaining lease at confirmed write ms | 235.730 | 244.070 |
| Confirmed write samples | 2,863 | 2,879 |
| False interventions / >500 ms writes / expired-lease writes | 0 / 0 / 0 | 0 / 0 / 0 |

The same entry runs also have zero faults in this ordinary cadence workload;
it does not replace the separate failing deadline/ownership/race tests. Candidate
simple-auto maximum age 81.520 ms versus entry 81.690 ms; real-auto values and
full distributions remain in `cadence.json`, not omitted because of tails.
Traffic packet cadence and age at write are separate metrics. Runtime retained
detail is ≤64 KiB and model summary history 327,631–334,211 accounted bytes;
test Mock histories are excluded. A measured 29.781 ms GC outlier remains in
the real-mode run; it is not assigned to any historical incident.

Steering and longitudinal-comfort benchmark **case results are exactly equal**
between entry 821dedc and candidate. Controller gains, lane geometry and
pedal calibration were not tuned to pass these repairs. Model comfort remains
distinct from real vehicle acceleration/jerk or unobserved game consumption.

## Release gates and remaining limits

Changed implementation files: `bootloader.py`, `core/ipc/shared_state.py`,
`sdk/plugin_sdk.py`, `core/engine.py`, `core/longitudinal.py`,
`core/transmission_mode.py`, `plugins/autopilot/main.py`.
Test changes: `tests/test_oct18_joint_handoffs.py`,
`tests/test_oct15_crossing_dev_hud.py`, `tests/conftest.py`.
Reproduction/evidence tools: `tools/audit_oct18_joint_incidents.py`,
`tools/benchmark_oct18_joint_handoffs.py`, `tools/verify_oct18_joint_candidate.py`.
Documentation: this report, `DEFERRED_WORK.md`, `PLUGIN_CHANGELOG.md`.
The package also carries unchanged runtime dependencies; the read-back-verified
manifest, not a filename guess or commit marker, is the definitive content list.

| Area | Verdict |
| --- | --- |
| A reproduced crossing-scope defect | FIXED / OFFLINE VERIFIED; exact historical full actor poses unavailable |
| B near-expiry publication/handoff defect | FIXED / OFFLINE VERIFIED; final historical production delay attribution OPEN |
| C old-activation overwrite | FIXED / OFFLINE VERIFIED |
| D split hold/restart capture | FIXED / OFFLINE VERIFIED |
| Original historical brake necessity for all 78/106 actions | NOT VERIFIED; no invented clear-road certificate |
| Whole-system / ETS2 behavior of candidate | GAME NOT VERIFIED; not declared complete |

Final package and whole-suite hashes are appended after the final passing run;
failed frozen attempts remain evidence, never PASS receipts.
Preparation is not deployment authorization. A consistent release must include
**bootloader.py, core/ipc/shared_state.py and sdk/plugin_sdk.py** together with
the core/AP dependencies; mixing the new SDK with the old Manager provides no
atomic runtime guarantee. No new DLL is required. Keep existing settings, cache,
logs, map data and commit marker unchanged.

Rollback, only after separately approved deployment: stop UltraPilot and ETS2,
restore **all** package-listed originals from the separate rollback ZIP, restore
the saved deployment receipt, verify every recorded original SHA-256, then
restart normally. Do not mix individual old/new handoff modules. No rollback or
deployment was executed in this task.

### First frozen whole-suite attempt — FAILED, retained

The first immutable run (`final-frozen.json` / `final-full-suite.log` /
`final-verification.json`) completed **47 failed, 3,019 passed, 1,592 subtests
passed in 841.70 s**, with all frozen hashes unchanged. It is not a PASS receipt
and cannot authorize packaging.

46 failures report `inactive_or_incomplete_source_capture`: legacy-buffer test
fixtures accidentally attached an existing process-global Windows native
sidecar, which has precedence over their supplied legacy actor bytes. The first
failed test, the whole ACC file and the same test with full collection each
passed in separate processes. The original creator/lifetime of that external
mapping is not recorded, so no user game/process is blamed. `tests/conftest.py`
now isolates only implicit live TrafficReader mapping opens in offline tests;
native ABI tests still supply actual source bytes and can explicitly override
the factory. The new negative asserts that an explicitly supplied inactive
native source STILL rejects, even with readable legacy actor bytes underneath.
No production validity/fallback rule was weakened. This is test input isolation,
not a claimed additional runtime repair.

The remaining failure was the release-history parser: a combined top-level core
entry did not satisfy its `## Autopilot` / `### 1.3.5` schema. The proper English
release entry was added, without rewriting the published 0.5.0 snapshot or test
expectations. A new final frozen run is justified by these concrete changes;
the failed run and original hashes remain preserved under their original names.

Targeted verification after those corrections: **221 PASS in 36.75 s**,
including all formerly failing files, the release parser, joint regressions and
the new explicit inactive-native rejection. Earlier completed focused runs:
**123 PASS in 101.43 s** for joint restart/native signal/activation coverage and
**103 PASS in 29.71 s** for dependency/refresh protocol and unchanged expiry
expectation. `compileall` and `git diff --check` passed. The second final record
uses the separate immutable `completion-*` names; no failed receipt is replaced.

Additional baseline checks: installed `bootloader.py`,
`core/ipc/shared_state.py` and `sdk/plugin_sdk.py` also match entry HEAD after
LF/CRLF normalization. Their exact installed hashes are respectively
`b578b4dd13fabf2c9f2f06ae814e8f462a9eabde11921e12a373919d70be744c`,
`f56992e5db54ea97f52d322c48dbf4c0104bf00a1778844cb80b53fe19878974`,
`a875a2a9bc37a9a17d4618ad2acb5c43a64e64e0c8f71d30f36f153aae65b315`.
The original deployment receipt hash is
`3dd9a59fd126fe14991ec2f5a71bee4dff3b4ef79f782a818d0bf813fa964d64`.

For the independent-cadence comparison, real-auto entry write-age
p50/p95/p99/max was **41.250 / 65.820 / 72.100 / 81.020 ms**, versus candidate
**41.250 / 67.420 / 74.370 / 83.620 ms**. Minimum write lease was
**248.240 → 244.070 ms**. These tails are retained, not called a freshness
improvement; the repairs address bounded causal handoff defects, and ordinary
cadence remains a separate workload.

### Second frozen attempt — FAILED; test-clock lifetime reproduced and fixed

`completion-full-suite.log` records **4 failed, 3,063 passed, 1,592 subtests
passed in 796.27 s**. Its frozen hashes remained unchanged. The failures were
stationary diagnostic preflight, native QPC agreement, extractor timeout and
trailer-guidance deadline. They must not be dismissed as four random flakes.

The new implicit-native-mapping isolation originally depended on pytest's shared
`monkeypatch` fixture. That instantiated the fixture before a flow fixture's
clock patch. A test's own later clock replacement was then undone AFTER the
flow had restored the real clock, reinstating the retired model clock globally.
The minimal ordered pair (60 s history test, then compiled native clock probe)
reproduces **1 PASS / 1 FAIL**, with native QPC **27910.7914399** versus the
leaked model time **1060.3933329999452**. This is test-fixture lifetime pollution,
not evidence of a production timestamp-domain defect or a reason to change any
deadline assertion.

The mapping isolation now owns a separate `pytest.MonkeyPatch.context()` and
does not change the test's clock-patch teardown order. The same history test
followed by all four exact failed tests gives **5 PASS in 15.98 s**. Native QPC
must still match Python QPC, actual extractor timeout must still reap its child,
and the original diagnostic/guidance assertions remain unchanged. Those four
failures require no production change. A replacement final run is warranted by
this reproduced test-isolation fix; both failed logs/hashes are preserved.

Final review also found the malformed-pedal early-return branch in `finalize`
still directly assigned an invalid AP result without its activation. Its own
counterexample failed in **both gearbox modes** on the preceding candidate:
an old malformed calculation overwrote the new activation's valid slot. It now
uses the SAME context-bound atomic commit as all other AP results. An invalid
result of the CURRENT activation still reaches the physical boundary and cuts
propulsion; the fault is not suppressed. This is the remaining branch of C,
not an additional controller or unrelated feature. Focused publication,
arbitration, handoff and joint tests: **164 PASS in 24.14 s**. Additional clock,
export, release-history and joint isolation checks: **144 PASS in 30.36 s**.

## Final frozen verification and review package

Final label **`accepted`** is a test-record name, not user deployment approval.
After the final implementation/test changes, the complete suite finished:
**3,069 passed, 1,592 subtests passed in 916.83 s (15:16)**, exit code **0**.
Every frozen source/runtime/test/tool hash remained unchanged during the run.
`compileall` passed before the freeze and `git diff --check` passed after the
documentation update. Earlier failed runs remain under `final-*` and
`completion-*`; neither is replaced or treated as acceptance evidence.

Evidence under `docs/steering-audit/oct18-joint-handoffs/`:

| File | SHA-256 |
| --- | --- |
| `accepted-frozen.json` | `9ceedb8aa61b0c1b95dbef4598da29dbac4f79b833a946b4d0038e22a911ebe1` |
| `accepted-verification.json` | `88dbcac34d919eeff0f8d8c47508fc136f17a19eebdc4c6b72c836df5255ed26` |
| `accepted-full-suite.log` | `d5b406d622cf0a317943ced476da921225a92aabf022b4391960f5560da6b65b` |
| `ultrapilot-oct18-joint-handoffs-candidate.zip` | `0e811a638e701e8aa295332739ff99dcae6a69565d63d28d7f948197a5de1c7f` |
| `rollback-runtime.zip` | `6c256fde703445f1057c838ec3eb1355c314359ea8b520dc756a18ae3747f039` |
| `candidate-manifest.json` | `0e4aa8e9ea6f31182f36328823d17a36a124246a81aef648483d14fd49e6d035` |

Preparation command: `python -m tools.verify_oct18_joint_candidate --package
--label accepted`. The candidate contains **28 listed runtime/release files**
(27 Python files and the changelog), plus its manifest. Each archive member was
read back and compared with its recorded SHA-256. The separate rollback ZIP
contains all 28 installed originals and the deployment receipt; its originals
were also read back and checked. All 36 installed receipt targets were verified
again before packaging. The base receipt still has hash
`3dd9a59fd126fe14991ec2f5a71bee4dff3b4ef79f782a818d0bf813fa964d64`.

The seven changed implementation files listed above and the changelog differ
from installation; the other 20 included runtime dependencies match exactly.
The manifest lists every path, new hash, previous hash and required base target.
No tests, raw evidence, reports, settings, cache or DLL are in the runtime ZIP.
Autopilot is **1.3.5**; ACC **1.3.8**, DrivePolicy **1.1.4**, Map **1.1.2**,
Turn Signals **1.0.2** and native **1.59.5-up-parked-records** remain unchanged.
The source HEAD is still `821dedcf1a9642a1f5767538a5daa9833c82d2d2`; the manifest
explicitly identifies this candidate as an **uncommitted working-tree build**.

**Final scope verdict:** the reproduced A/C/D defects and B's publication/handoff
defect are FIXED / OFFLINE VERIFIED. B's exact historical final production delay
and the inner cause of the separate 208.150 ms signal wait remain **OPEN**.
Missing actor poses do not prove that all earlier A braking was unnecessary.
There is no failing mandatory collected test remaining, but these historical
attribution gaps prevent a whole-system completion claim. The ZIP is a coherent
review candidate, not a recommendation to deploy it as a definitive cure.
**GAME NOT VERIFIED.** No commit, push, deployment, arming or game control took
place, and no additional drive is requested by this report.
