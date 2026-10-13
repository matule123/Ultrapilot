# ACC departure and plugin lifecycle, 13 October 2026

## Scope and evidence boundary

The user confirmed stopping at the signal in the last drive. The approved 5 m
SDK-reference policy, signal selection, red approach, continuous service brake,
green restart, indicators, steering, geometry, PID and 500 ms gates are retained.
No installation, original record, old checkout, game, commit or push is changed.

Task-entry HEAD `d584ad6` contains the preceding joint lifecycle/5 m fix; the
working tree was clean. All **24 deployment receipt hashes match** and source
contents match after LF/CRLF normalization, including the scoped DLL. A commit
marker alone was not used. Candidate code now intentionally differs.

Original immutable exports pass `inspect_replay` integrity and were only read:

- `steering-replay-20261013T162000.938437Z-automatic_disable.json`: pedal incident.
- `steering-replay-20261013T162002.170123Z-automatic_disable.json`: 979 dense
  samples / 3,187 execution rows.

The first retained intervention is Engine, **16451.6558426 s**, not the later
Autopilot log. Rejected Traffic observation is **16451.6012671**, computation
**16451.6338128**, expiry **16452.0836119**, checked **16451.6499689**;
age **48.702 ms**, decision age **16.156 ms**, remaining lease **433.643 ms**.
SDK frame **171976454**. Vehicle/identity were valid; `different_fields=[]`.
Following status is `no_candidate_unproven_coverage`, departure absent,
traffic/light brakes zero. It is not a stale steering/Traffic timeout.

Activation 16400171135500, session 1, map `promods-1.59`, dataset
`d6cc7936fce4e902761abb5d`, intent `28905a70be224ce0b78b6d79f23d4ad8`,
revision 37, build `217bf3c5547a43268c87096bb8dc17d3`, geometry
`08a7502e89aa0cb4b610082bc527c0dd6ec88a6fdfa99166a4f774479bb74ab4`.
Lead **30** is attributed from 16443.6369466 through 16451.6007824.
The history retains 29.948 s but is incomplete; detail retains 12 events /
0.263 s and drops 2,958 earlier events. Original actor position/oriented boxes,
slot and changed receiver record at loss are **not retained**. The two specific
code defects below are reproduced, not falsely assigned as the exact historical
actor-loss branch. Successful physical write return does not prove game input
consumption. Exact historical departure geometry remains NOT VERIFIED.

## Stage 1: confirmed-departure software defects

**Before:** 4 integration cases fail / 2 protective trailer cases pass, in both
automatic modes. Actual native Traffic bytes, production Map fixture, Policy,
ACC, Autopilot, Engine, real Controller and chronological SCS test writes are
used. The initial missing-fixture import was a test setup error, not counted as
a production reproduction.

1. The old departure test subtracts a box's half-diagonal from center-to-route
   distance. A 2x4 m native car box turning perpendicular, center 4.75 m from
   the reference, is actually 2.75 m clear; its enclosing disk reports 2.514 m,
   below the unchanged 2.6 m caution band. Hence a genuinely outside modeled
   box cannot release the acquired dependency. The fix computes exact planar
   oriented-box/segment distance for **every tractor/trailer body**, bounded to
   512 local edges, after the existing projection/height/identity validation.
   No lane ownership, ego physical footprint or collision-free road is inferred.
2. `prepare()` reset target history on every geometry identity change. Preserve
   just the original one-target receiver witness across validated publication
   within the same activation/session/map/dataset/intent. Do not carry old
   projected progress or an old departure receipt; reproject the original actor
   on the new reference before deriving a new proof. A true authority change,
   invalid geometry, missing/ambiguous record, reassigned source slot or stale
   receiver time still cannot clear it. ACC's corresponding dependency is also
   retained, preventing a geometry refresh from becoming an empty-road bypass.

After this stage **150 targeted tests pass**. Subsequent additions cover a second
car after departure, immediate emergency demand, and a missing acquired target
across geometry refresh. Both modes keep zero drive for the missing case and
full emergency brake for the standing close leader. Source timestamps, original
fingerprints and first receipt time remain unchanged; no ID is invented.

An additional test forces a real Map rebuild through a fresh recovered-worker
build guard, using the unchanged actual directed network. It initially exposed
one more simple-auto conflict: the forward ratio history still belonged to the
preceding revision/build, although ACC's newly published packet was validated.
The shared transmission rule now starts **new history from the current positive
forward ratio** only with unchanged activation/mode/session/map/dataset/intent,
valid replacement geometry and current valid ACC. It does not rebind old ratio
times, coast, hold or launch receipts. Ratio zero and missing/current-invalid ACC
cannot use this transition. **76 targeted rebuild/lifecycle/ratio safety tests
pass**; both modes continue through the real Map rebuild and body departure.

## Stage 2: DrivePolicy worker and supervision

The session contains **108 DrivePolicy restart records**, including the
18:20:15–29 storm. UI requests complete shutdown at 18:20:32.418; a queued child
still reports successful startup at 18:20:34.809. The old manager has no retry
budget/backoff, live-disable restart check or shutdown guard in `_spawn`.

The worker also treats the text `KeyError` as IPC shutdown and silently leaves
its loop. A real `KeyError` therefore becomes an unexplained normal process
exit followed by repeated restart. **Historical originating exception and exit
code were not saved**, so that mechanism is a proven reproduction, not a
claimed original stack trace. There are no separate current-session Map or
DrivePolicy log files; workers append to the common `ultrapilot.log`.

**Before:** all six initial lifecycle reproductions fail. **After:** 85 targeted
tests / 50 subtests pass, including existing worker cadence and UI discovery.
Final new integration/negative checks pass as recorded in the verification log.

- Ordinary data `KeyError` is no longer normal IPC shutdown. Log/store the first
  actual error, invalidate the worker's Policy/ACC packet immediately and retain
  required-producer status on failed exit. Three consecutive tick failures exit
  nonzero with cleanup; a transient error can recover on a later successful tick.
- Store bounded `plugin_exit.<name>` / `plugin_health.<name>` with first failure,
  exit code, retry count and next retry, using the existing shared state. No new
  collector, per-tick INFO output or unbounded error history.
- At most **three retries**, delays **0.5 / 1 / 2 s**; reset after 60 s healthy
  operation or explicit disable/re-enable. Data disappearance does not renew
  old Policy limits. The actual arbitration/output gate rejects unavailable
  required Policy instead of issuing drive from its old packet.
- Serialize spawn/supervision/stop with one lifecycle RLock. Publish the closing
  flag before Engine cleanup/joins; parent checks the UI shutdown request and
  child checks it before initialization. A disabled worker is stopped and never
  crash-restarted. New N does not automatically restore drive after a technical
  safety intervention. Steady worker loops retain their original local stop
  event and live-enable read; no new per-control-tick shutdown IPC polling.

Final lifecycle selection: **39 tests + 50 subtests pass**. Initial profiling
found redundant parent live-enable RPC reads for healthy workers (median
1.590 ms for 12 processes). Remove those duplicate reads; each worker already
observes its live flag, and the parent checks it after exit before any restart.
One global parent shutdown check remains. Actual Manager IPC benchmark, 1,000
calls per variant: median **0.0039 -> 0.0536 ms**, p95 **0.0041 -> 0.0920 ms**,
p99 **0.0045 -> 0.1348 ms**, maximum **0.5344 -> 0.2820 ms**. Process doubles are
alive handles, not real game workers. This is supervision cost, not packet
cadence or an end-to-end live timing guarantee.

The 32 Map ERROR records comprise localization failures, insufficient lane-change
approach and stale revision/horizon build failures, plus duplicate phase/result
reports. They occur before this ACC intervention and retain prior-route behavior
where applicable. They are not proved to cause DrivePolicy exit or be an ACC
consequence. No localization safety rule is removed to hide that summary.

## Stage 3: MonoCruise comparison and rejected candidate

Read-only local reference: nested `MonoCruise-stable`, source declaration
**1.1.2**, MIT license, copyright 2025 lukas deschryver. It is an unpacked archive
without a Git checkout; no exact upstream commit is asserted. Source module
hashes are recorded with the runtime candidate. Read its root agent guide,
ACC/cruise-control/longitudinal documentation and actual controller sources.

No source code was transplanted. Native oriented-body geometry and separation
of dependency, controller and safety state are independently implemented here.
MonoCruise's acceleration-cap/one-mapper architecture, stable in-lane tracking,
relative closing reserve, asymmetric recovery and anti-windup were compared
against our existing single PID/arbitration flow. Its tuned gains, calibrated
pedal capacity, lead acceleration, ghost target/anticipation, inferred ego
overhangs and stop-and-go cannot be imported as measured UltraPilot capabilities.

A candidate added relative closing reserve `closing²/(2*1 m/s²)` to the existing
reference-point headway law. Three pre-change kinematic tests fail, two existing
equal/opening/emergency invariants pass. It then passes 106 targeted tests, but
the **seven paired 70 s closed-plant cases do not justify retaining it**:

| Case | Speed RMS before/after (km/h) | Minimum reference gap before/after (m) | Steady RMS before/after (km/h) |
| --- | ---: | ---: | ---: |
| Straight slower lead | 3.423 / 3.014 | 32.000 / 32.104 | 0.00006 / 0.468 |
| Left/right R60 and R35 circulation | ~3.423 / ~3.014 | ~32.000 / ~32.104 | ~0.00006 / ~0.468 |
| Braking lead | 3.680 / 3.269 | 22.000 / 22.000 | 0.00452 / 0.00525 |
| Cut-in | 5.101 / 5.089 | **18.373 / 17.865** | 0.00410 / 0.00622 |
| Heavy/noisy/jitter | 3.534 / 3.090 | 32.303 / 32.233 | 0.518 / 0.503 |

Cut-in minimum reference headway drops 2.308 -> 2.251 s; emergency samples
21 -> 23; Engine emergency response remains same-tick. No reference-point
collision occurs. The gain in aggregate tracking error is not enough to accept
the worsened cut-in gap/steady convergence, so the candidate is **removed**.
The original gap law, PID, gain, setpoint recovery and emergency mapping remain.
Tests explicitly assert the retained law and document the rejected alternative;
they do not label its old fail-first tests a successful production fix.

The reproducible rejected-law tool also retains the unfavorable comfort data:
braking-lead peak sampled model deceleration **1.389 -> 2.096 m/s²**, sampled
jerk **1.576 -> 3.222 m/s³**, pedal mode changes **4 -> 5**. Cut-in values are
**4.008 -> 4.036 m/s²**, **7.764 -> 7.802 m/s³**, mode changes **6 -> 7**,
reference-point TTC **5.812 -> 5.600 s**. Noisy-case acceleration/jerk are null,
explicitly NOT MEASURED, rather than noise derivatives presented as physical
jerk. These are results of the rejected experiment, not the retained runtime.

This explicit model uses perfect synthetic route poses, 120 ms delayed output,
350 ms actuator response and an uncalibrated longitudinal plant, not real game
input or bumper separation. Existing following tests exercise actual physical
writes separately. Measured lead acceleration, trusted producer generation,
coverage and lane membership are absent from the native ABI. Asymmetric physical
jerk control/lead acceleration feed-forward and certified whole-vehicle collision
prediction therefore remain **NOT IMPLEMENTED / NOT VERIFIED**. A pedestrian
or crossing actor is not replaced by the ACC headway law. Semaphore/other-stop
priority remains separate. This task is not “MonoCruise-equivalent ACC”.

## Verification, performance and handoff

Steering **16/16** and ordinary longitudinal comfort **12/12** benchmark metrics
match the preceding 5 m candidate exactly. Departure operation has bounded
extra geometry work, with the real before/after CPU timings and retained memory
recorded in `analysis.json`; tracing time is reported separately from untraced
timing and test timing-list storage. No SDK/Traffic IPC reads are added.

The retained 121-point/120-edge selector occupies **54,830 bytes** by recursive
object accounting, including the existing route cache; exactly one target and
one departure receipt are kept. Its old bounding-disk operation versus new
oriented-box operation (1,000 untraced changed-record checks) measures median
**0.1012 -> 0.9304 ms**, p95 **0.2456 -> 2.4868 ms**, p99 **0.8389 -> 3.6852 ms**,
maximum **2.0723 -> 6.8848 ms**. This is a deliberately difficult departure case,
not ordinary following cadence. Tracemalloc greatly increases operation time;
its current/peak allocations and the **32,856-byte test timing list** are
separate in `analysis.json`, never claimed as retained runtime history. Native
body/route accuracy and producer freshness remain unverified.

The complete suite required by this task finished in **678.19 s (11m18s)**:
**2,485 passed, 1 failed, 1,592 subtests passed**. The sole failure was
`test_worker_reports_ram_after_start_once_outside_tick`: its stop event was
already set before entering the worker, while it expected initialization and a
RAM report. That contradicts the newly required cancellation-before-start
contract. The test now uses a real initially clear event and sets it in
`on_start`, allowing the unchanged expected sequence `start -> RAM -> stop`.
The shutdown regression still requires no initialization for a pre-set event.
No runtime code, RAM assertion or safety gate was changed to fix this test.

The final memory/lifecycle/cadence/version selection passes **30 tests in
3.23 s**. Compileall of all affected Python files and `git diff --check` pass.
The full suite was not repeated after this test-only correction; its recorded
result is not relabeled as an all-green final full-suite run. Targeted safety
tests were not weakened; earlier fixture/metadata errors and discarded
candidate results remain in ignored logs.

Runtime candidate relative to the verified 24-file installation:

```
core/acc_following.py
core/engine.py
core/plugin_manager.py
core/transmission_mode.py
plugins/acc/main.py
PLUGIN_CHANGELOG.md
```

ACC **1.2.0**, updated for its dependency behavior and supported oriented-body
departure feature. DrivePolicy implementation remains **1.1.3**; core lifecycle
does not release that unchanged plugin. Map, Autopilot, TurnSignals and DLL
remain unchanged. Keep the receipt-matched signal, packet-refresh, policy,
controller and diagnostic dependencies. No DLL/settings/cache/marker change.
Tests, tools and reports are not installation payload.

Reproduction:

```powershell
$env:PYTHONCASEOK='1'
python -m tools.analyze_oct13_acc_lifecycle --output docs/steering-audit/oct13-acc-lifecycle/analysis.json
python -m tools.compare_oct13_following_candidate --output docs/steering-audit/oct13-acc-lifecycle/rejected-candidate.json
python -m pytest tests/test_oct13_acc_departure.py tests/test_oct13_plugin_lifecycle.py tests/test_oct13_acc_anticipation.py -q
python -m pytest tests -q
```

Report/tools/targeted regressions, changelog and backlog are included in the
source work. Original incident and MonoCruise source are untouched.
**OFFLINE corrections only / GAME NOT VERIFIED**. Exact historical actor/exit
causes remain open; no 100% reliability or future game outcome is promised.
No new drive is requested. Deployment requires the user's explicit approval.
