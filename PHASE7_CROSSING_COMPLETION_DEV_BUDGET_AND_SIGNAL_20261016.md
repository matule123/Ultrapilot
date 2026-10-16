# Oct 16: crossing completion, dense DEV geometry and signal braking phase

**OFFLINE VERIFIED for the corrected production counterexamples and defined
model safety criteria; GAME NOT VERIFIED. No deployment.** Dense-render hard
timing and missing historical branches remain NOT VERIFIED as listed below.
This report distinguishes the recorded incident from production counterexamples.
The existing XYZ/XZ Visualization repair and its tests are preserved.

## Build and evidence identity

Starting HEAD: `0ed435f9d05b499fc9ee2aad1d6d8638a4f2450f`.
Starting local changes: `ui/visualization.py` and
`tests/test_visualization_live_path.py`. Neither was reverted or rewritten.
Read-only inspection found all **33 installed deployment-receipt SHA-256 values
valid**, including the installed Visualization correction. After LF/CRLF
normalization, every runtime dependency in the candidate matched starting HEAD
except that pre-existing Visualization fix. `commit.txt` and the inherited
receipt source marker are not treated as proof of the installed Python content.
The installation was not modified.

The installed native binary remains `1.59.4-up-traffic-timed`, SHA-256
`ebe8af192bcd7c0955075d2869882d8c82804e855ba25a6b43fb47d8c7542bdb`.
No DLL, ABI, native traffic sensor or producer timestamp is added here.
ACC changes from **1.3.3 to 1.3.4**. DrivePolicy 1.1.4, Autopilot 1.3.4,
Map 1.1.2, HUD 1.0.2 and turn signals 1.0.2 remain unchanged.

Originals are under the installed `route-diagnostics` directory:

| Replay | SHA-256 | Stored evidence |
| --- | --- | --- |
| `steering-replay-20261016T052820.198925Z-manual_disable.json` | `35ba9ef5d0eacc11035e3d09ce30d411ef352a476f9b9f7bfd65411440990cd3` | 205 calculation / 4,452 execution rows |
| `steering-replay-20261016T115126.095989Z-manual_disable.json` | `a04f63cb9364ac98f8f3bcd5ea9c9ead73025b549ee717e3a942ccc1fee4b746` | 1,447 calculation / 8,473 execution rows |
| `steering-replay-20261016T115204.478872Z-automatic_disable.json` | `03f18f18c4d77da786f3e28c89d5e6683b8e48af96a25ee7aa490b4026da747c` | Immutable pedal incident and 29.9552861 s decision history |
| `steering-replay-20261016T115205.501673Z-automatic_disable.json` | `fbcc69498f0b5666532bb82f0bc8bfd572b62e64cec8c6d268c75787d88eda78` | 334 calculation / 2,235 execution rows |

All four pass `core.steering_replay.inspect_replay`, including expansion of
immutable references; `confirmed=false`, `runtime_authorized=false` remain.
The three Oct16 `steering-timing` exports also pass the same inspector
(130, 37 and 314 samples); they retain steering/Map phase times and identity,
not longitudinal decisions or signal/pedal inputs. Their hashes and exact field
inventories are in `evidence-summary-complete.json`.
The pedal history has 258 regular + 30 change rows, **zero capture failures**
and `history_incomplete=false`. The short detailed backend ring is separately
bounded/incomplete. Successful backend return is not game consumption.
The dense execution rows do not contain exact `executor.source_packet`
attribution; their current headers are not substituted for executed commands.
Read-only analysis is reproducible with `tools/analyze_oct16_joint_evidence.py`.
Derived JSON/logs are ignored under `docs/steering-audit/oct16-acc-dev-signal`;
original logs, replay/timing files and significant-event exports are unchanged.

## 1. Crossing target loss

### Recorded first fault, not a lease failure

| Field | Recorded value |
| --- | --- |
| First comparison / later intervention observation | 3282.1825367 / 3282.1887987 s |
| Reason | `ACC target unavailable or unconfirmed departure` |
| Compared traffic SDK frame | 162243510 |
| Original observation / computation | 3282.1133815 / 3282.1645526 s |
| Original expiry | 3282.6133815 s |
| Observation / decision age | 69.1552 / 17.9841 ms |
| Remaining validity | **430.8448 ms** |
| Identity | Matching activation/session/intent/revision/build/geometry; no differing field |
| Traffic | Valid, actors usable, `no_candidate_unproven_coverage`, zero traffic/light brake, no departure witness |

The later intervention observes SDK frame **162293508**, observation
3282.1700921 s. It is not substituted for the compared frame.
Activation is `3265880373900`, session `1`, map `promods-1.59`, dataset
`d6cc7936fce4e902761abb5d`, intent `391b6dcfb41e4ceab52f23653a218bd7`,
revision 15, build `7eb58ee4fbaa4111afbd2e3a857f065d`, geometry
`7722dca46a5b3510d8214f466b49bf759ceeaad658bcca5ff0100f07ebb5cfd7`.

The history acquired **ID 102, moving slot 3**, WHL
2.0490732 × 1.6775467 × 4.3174973 m, speed 12.144537 m/s. At 3280.4818 s the
protective crossing had 77.9839 m reference distance, actor arrival 4.2684 s,
ego arrival 6.4246 s and selector brake 0.0334518. Subsequent caps caused real
ordinary braking before the technical fault. At 3281.2216 s the retained
crossing selector demand was zero; this alone did not prove clearance.
Later summarized throttle rose, reaching 0.724796; the detailed backend ring
retains brake zero at 3282.1225794 and throttle 0.724796 at 3282.12884.
After the fault it records throttle zero at 3282.2096174, then service brake
0.165062 at 3282.2096755 followed by increasing safety writes. Initial protective
slowing and the subsequent technical stop are different decisions.

**Historical boundary:** the rejected original actor array is absent. The
record cannot determine whether ID 102 disappeared, changed slot, turned or
failed a particular projection at that tick. The displayed vehicle-fault icon
does not establish a cause. No historical pose or lane assignment is invented.

### Proven defect and implemented contract

The same acquired-target latch was used for a crossing-arrival heuristic and
an ordinary lead. A still-observed crossing actor turning parallel could cease
to intersect the directed route while also failing the separate receding-body
departure test. The cap ended but both ACC and the final arbiter treated this
as lost lead evidence and stopped authority. The production reproduction fails
in both automatic modes on the starting implementation.

The corrected contract explicitly labels lead, protective-route and crossing
constraints. Only the **original still-observed crossing owner** can end that
heuristic, with same lifecycle/ID/source/slot/body count, advancing generation
and SDK frame, bounded observed displacement, no remaining directed crossing
ray, and a complete current three-second body prediction with zero demand and
no unsupported actor. This is **not** a lane, intent or empty-road certificate.
Ordinary lead loss still requires its original departure contract.

Up to **16 bounded original-owner completion witnesses** can be reproved on subsequent **new** consecutive
native acquisitions, so a slower ACC tick does not miss overlapping handoffs. Repeated reads keep
the original timestamp. Absence breaks the witness chain; later reappearance
cannot revive it. Cached completion rechecks current geometry/conflicts. Native
history survives a validated same-authority geometry rebase, but not a changed
activation/session/dataset/intent. No ID deduplication or invented incarnation.

ACC and the Engine use the same witness validator. Before ACC publishes a new
decision, Engine removes old drive rather than inventing a replacement cap or
executing expired pedals. Current positive brake/emergency floors remain.
The final guard now checks the actual acquired candidate ID, not merely the
presence of some other candidate. Original leases, 500 ms checks, first fault,
R protection, continuous hold and backend failure handling remain.
The single-completion field remains compatible; the optional multi-owner field
is published only when more than one current witness exists. Missing/reassigned
observations break their own chains. Capacity is fixed at the existing scope's
16-owner limit; this is bounded control evidence, not a new diagnostic collector
or an indefinitely queued event history.

A further mixed-scene reproduction identified a concrete owner mismatch:
the minimum cap belonged to lead **29**, and ACC acquired 29, but the selector
retained weaker crossing **83** for departure. `multiple-owner-before-valid.log`
records both mode failures. Retention now compares the complete actual scope's
caps first; a weaker crossing cannot overwrite the stronger ordinary lead's
departure history. This is a proven code defect, not asserted as the unrecorded
historical ID 102 branch.
The opposite priority exposed a second mismatch: ACC privately acquired crossing
83 but published projected lead 29 as `following_target_id`. The packet now
carries the **actual acquired winner**. Losing an unused projection cannot be
mistaken for losing this continuously observed owner. Independently scheduled
ACC could also miss completion when a new crossing replaced the selector's
single slot; the bounded witness handoff fixes this without changing IDs/times.
`handoff-owners-before-valid.log` and `published-owner-before.log` retain the
original mode failures. Tests include two completed originals before ACC ticks
and Engine consuming the publication first: no unvalidated drive is written.
The new-lead-at-completion reproduction additionally proved selector mutation
order: `select()` assigned the new lead before completion could inspect the
original crossing owner. Engine now snapshots that owner ID before projection,
then qualifies it against the exact same current native observation and body
prediction. It does not borrow an old pose, alter a packet identity or erase
the new lead's valid history. `projection-owner-before.log` has both original
failures; the full joint contracts include this case after the correction.
The final pipeline also completes **30 acquisition/completion cycles in each
automatic mode** (120 new native acquisitions, 192 backend writes per mode),
with zero technical disable, zero positive pedal overlap and no terminal hold.
This repeats the state transitions with synthetic poses; it is not a vehicle
physics simulation or reconstruction of ID 102's recorded maneuver.

## 2. Dense DEV HUD

The photograph's `omitted actors 65` is consistent with the reproduced budget
failure: after optional reduction, the old frame fallback returned only an
overflow marker and discarded all actual bodies. Correct ABI fixtures use
**40 moving slots plus up to 40 parked slots**, not an impossible 80 moving
records. The initial malformed fixture attempts are retained as test-development
logs, not counted as production counterexamples.

`dense-before-valid-abi.log` contains four valid failures (65/80 actors × both
automatic modes) using the exact starting-HEAD geometry function inside the
real native-reader/Engine pipeline. The old frame has zero bodies; the new one
retains actual identified objects and the relevant last-slot lead.

Admission now ranks actual AEB/emergency causes, selected brake owners,
ACC/positive-cap owners, then nearby actors with deterministic tie-breaking.
Actual boxes/trailers precede optional prediction samples and observed history.
The display uses exact subsets of existing samples, never a second predictor.
Omitted actors, bodies, priority actors, paths, prediction points, ego samples
and history are explicit. Pathological identity overflow is explicitly
unverified rather than an apparently clear scene.
Admission/path/history matching uses the complete native ID/source/slot/record
fingerprint. A further ambiguous-ID reproduction caught an off-by-one omission
count (20 reported bodies instead of 21); different source records are now
counted independently, not deduplicated or given control authority.

Fixed budgets remain **192 KiB per frame, two frames, one 64 KiB physical
receipt, 10 Hz admission/publication and one display worker with no queue**.
The already-decoded observation is captured after actual owner selection, with
no extra SDK or IPC read. Classic perspective roads, camera and normal HUD
remain. Fresh detections without active navigation are gray/passive; old data
and missing exact control attribution remain separately marked. Equal ID alone
does not transfer a brake color to another acquisition.

Dense priority/AEB and long-identity probes, disabled-authority presentation,
actual brake-color attribution, full Visualization opening with XYZ points,
render error containment and the original on/off control comparison pass.
The one modified previous test now expects fresh disabled-authority detections
to be passive, as explicitly requested; retired route/activation checks remain.

## 3. Red braking ownership

The retained 30 s incident history contains **zero qualified signal rows**.
The two earlier manual replay windows have no immutable pedal/signal chain.
The preceding significant receipt is an older curve-brake decision in another
activation, not evidence for this red approach. Available timing exports cannot
recover a missing longitudinal decision. Consequently the exact cause of the
user's earlier red oscillation is **historically NOT VERIFIED**.

A concrete production counterexample is independently proven: an ordinary
external Policy/traffic brake resets ACC's PID and also erases
`_signal_stop_started`. When that brake withdraws during the same red approach,
the still-responding vehicle is slightly below the distance envelope; ACC can
apply drive because it forgot that this same stop had already begun braking.
`red-physical-before.log` records **0.04 actual backend throttle** in both modes.
This is not diagnosed from a target field alone.

The braking-started phase is now owned by activation/session/map/dataset/intent,
qualified head and immutable directed passage/physical stop target. Ordinary
external braking and same-authority geometry publication reset PID state as
before but preserve this same-stop phase. No old integral is carried. Different
owners, green, emergency, technical stop or driver parking brake do not inherit
it. The existing response-sized coast allowance still permits drive recovery
after genuinely substantial underspeed. There is no new filter, speed floor,
brake constant, PID gain, 5 m offset, geometry or timeout change.

### Criteria fixed before the paired plant runs

- No red target overrun, positive pedal overlap, parking writes or brake-zero
  gap during established stationary hold; automatic green restart in both modes.
- Unchanged 5 m reference offset. Stop inside the existing modeled terminal
  zone, 0–1.5 m before that reference target; not a painted-line/bumper criterion.
- No positive drive pulse attributable to the lost same-stop phase for a normal
  response-sized deficit. Genuine large underspeed recovery remains supported.
- Report deceleration and jerk rather than manufacture a new comfort threshold.

The existing plant uses real signal reader/selector, Policy, ACC, Autopilot,
Engine, Controller and chronological SCS test-buffer writes. It models drive
2.2 m/s² and brake 4 m/s² divided by load ratio, drag `.12+.004*v²`, 120 ms
transport, actuator response 150/700 ms, load ratio .7/1.4, integration ≤10 ms
and jittered 33/50/80 ms ticks. It is **uncalibrated**, including a 4 m model
front extent, and is not an ETS2 physical measurement. Baseline methods are
loaded read-only from starting HEAD; candidate and baseline use identical
placed prefab geometry and external 0.12 brake for two ticks.

An early intervention (12 paired cases) does not excite the defect: stop and
pedal trajectories remain identical. A late intervention at the first coast
phase (another 12 paired cases) does. Each row below applies to **both modes**:

| Entry km/h; response/load | Red drive samples after braking, before → after | Red drive/brake reversals | Reference stop gap m | Max decel m/s² | Max absolute model jerk m/s³ |
| --- | --- | --- | --- | --- | --- |
| 20; .15/.7 | 16 → 0 | 2 → 0 | 1.003 → .513 | 1.747 → 1.632 | 9.897 → 10.534 |
| 20; .7/1.4 | 26 → 0 | 2 → 0 | 1.365 → .827 | 1.130 → 1.007 | 4.128 → 3.483 |
| 35; .15/.7 | 16 → 0 | 2 → 0 | 1.013 → .948 | 1.849 → 1.849 | 15.052 → 8.580 |
| 35; .7/1.4 | 24 → 0 | 2 → 0 | 1.241 → 1.023 | 1.144 → 1.144 | 2.991 → 2.991 |
| 50; .15/.7 | 17 → 0 | 2 → 0 | .596 → 1.153 | 2.516 → 2.516 | 10.707 → 10.641 |
| 50; .7/1.4 | 25 → 0 | 2 → 0 | 1.045 → 1.090 | 1.484 → 1.484 | 3.133 → 3.354 |

All 24 candidate stops in the 100 m early/late matrices satisfy the defined safety/terminal criteria and resume
on green without another N. There is zero physical positive overlap, zero
parking write, zero red overrun and zero established-hold brake gap. Maximum
jerk does **not** improve universally: two response/load combinations rise,
as shown, so this is not a universal comfort claim. Ordinary model and remaining
benchmarks are reported separately from the reset counterexample.

Pedal steps are normalized backend fractions, not physical jerk. For moving
red rows (`speed_mps > .1`) in the six 100 m late-intervention mode-0 cases,
maximum throttle steps before → after are .1123→.1123, .2643→.2643,
.1645→.1645, .4251→.4251, .0862→0 and .1410→0. Maximum brake steps are
.2000→.2000, .2000→.2000, .2147→.2102, .1907→.1907, .2289→.2289 and
.2000→.2000, in the table order. Earlier drive before braking can dominate a
whole-approach maximum even when the unwanted later drive pulse is removed.
The complete chronological setup/hold/release write stream separately includes
a maximum brake step of 1.0 in all six cases; it is not concealed as a moving
comfort sample. Fixture writes within one tick share a modeled timestamp, so
an intra-tick pedal rate is not inferred by division by zero. Physical model
acceleration/jerk uses actual integration/tick durations as described above.

Reproduce with `tools/verify_oct16_joint_traffic.py` (normal and
`--late-intervention`). Full rows and ordered writes are retained outside Git.

An additional **12 paired 60 m approaches** use the same fixed criteria,
speeds, modes and plant parameters. All candidates pass: reference stop gaps
are .406–1.384 m, zero red drive samples after braking, zero hold-brake gaps,
zero overlap/parking/overrun, and green restart in every case. Baselines have
15–52 red drive samples and 2–4 red pedal reversals. The 50 km/h, .7 s response,
1.4 load baseline fails the original terminal/hold criteria in both modes:
1.866 m reference gap and 21 zero-brake hold samples; the candidate has 1.283 m
gap and zero hold gaps. This is model evidence, not an observed ETS2 stop.
The tight 50 km/h, fast/light 60 m approach still peaks at **4.662 m/s²**
deceleration and **20.035 m/s³** modeled jerk, unchanged by the phase fix.
The correction removes reset-driven pedal reversals; it does not promise
comfortable emergency-limited stops from every short initial distance.

## Verification, performance and candidate

Targeted final-runtime result: **179 passed**, including full Visualization
XYZ/XZ tests, release metadata, automatic exports, ACC following and 38 new joint regressions. Additional existing lifecycle,
native/body/AEB/stop contracts previously passed in the 174-test development run;
the final complete suite below is authoritative for the delivered runtime.

The initial full run exposed a release-changelog heading error. The existing
release-reader assertion was preserved; the changelog format was corrected and
its test passes. Interrupted/failed development runs are not acceptance evidence.

### Numerical preservation and display overhead

The existing steering benchmark's **16 cases are numerically identical** to
starting HEAD. The ordinary longitudinal comfort benchmark's **12 cases are
also numerically identical**. Neither changes the lateral controller, target
geometry, pedal calibration, steering cadence or timeout. These unchanged
scenarios do not replace the separately excited signal reset counterexample.

`tools/benchmark_oct16_dense_hud.py` uses actual ABI decoding, selectors,
producers, Autopilot/Engine/Controller and chronological physical test writes.
Each row has 25 warm-up + **160 measured ticks**, with mock call/write histories
cleared outside measured ticks. The final run was isolated from pytest and
the paired plant runs. These are wall times of the complete in-process test
step, **not live multi-process packet cadence or game physics**.

| Actors/mode | Starting geometry DEV on p50/p95/p99/max ms | Candidate DEV off ms | Candidate DEV on ms |
| --- | --- | --- | --- |
| 65/0 | 10.648 / 12.764 / 13.089 / 13.224 | 10.551 / 10.982 / 11.843 / 12.505 | 10.680 / 14.177 / 14.526 / 14.852 |
| 65/3 | 10.161 / 12.043 / 12.234 / 13.825 | 10.114 / 10.623 / 13.684 / 16.956 | 10.237 / 13.833 / 15.244 / 16.942 |
| 80/0 | 11.052 / 12.995 / 13.518 / 15.512 | 10.952 / 11.440 / 12.172 / 14.512 | 11.057 / 14.860 / 15.351 / 15.371 |
| 80/3 | 10.699 / 12.600 / 12.981 / 13.099 | 10.540 / 10.897 / 12.335 / 13.440 | 10.639 / 14.363 / 14.614 / 14.693 |

The raw output also retains control-thread CPU and GC distributions. Windows
thread CPU measurements are quantized in roughly 15.625 ms increments and
cannot support sub-millisecond CPU claims. Candidate on/off physical-output
SHA-256 values and all non-presentation source-read counts are **identical** in
all four rows, with no technical fault. There is no claim of zero overhead.
The table uses **dense-delivery.json**, after the final projection-order repair.
Its geometry-only counterfactual uses starting-HEAD admission, while control
logic is held identical; it is not a complete historical runtime comparison.
Earlier isolated dense runs are retained, not silently replaced: the mode-3
80-actor candidate maximum was 32.558 ms (`dense-isolated-complete.json`) and
**81.178 ms** (`dense-release.json`), versus 14.693 ms in the final run.
The 81.178 ms run's CPU maximum is 46.875 ms and recorded GC maximum .0037 ms
in that row; neither identifies its unexplained wall-time extreme. The final
run's thread CPU samples are quantized at 0/15.625 ms. Lower final values do
not prove that the projection-order repair caused a performance improvement.
No claim that GC explains this or the historical incident. Runtime display cost is bounded
in work/memory, not demonstrated to meet a hard real-time bound on this host.

For both 65 and 80 actors, baseline admission retains **0** actors. Candidate
admission retains **43**, including every priority owner in these scenes,
with 22/37 actors and bodies explicitly omitted, zero omitted priority actors,
zero omitted prediction paths and nine omitted path samples. Its accounted
frame size is **183,518 bytes**, below the unchanged 196,608-byte limit.
Final snapshot deep size is about 80.6 kB. A separate direct measurement of two
owned frames plus the receipt is **127,495 bytes** (snapshot 80,524 bytes).
This excludes test histories, control caches, Python worker/executor overhead
and OS stack/RSS; it is not total application RAM. Fixed accounted maxima remain
384 KiB geometry plus 64 KiB receipt, with one publication in flight.

Actual classic 3-D QPainter, 25 warm-up + **100 measured draws**, with 43 dense
admitted records and registered Windows fonts:

| Render | p50 / p95 / p99 / max ms |
| --- | --- |
| DEV off | 9.809 / 10.276 / 10.625 / 10.625 |
| DEV on | 17.907 / 18.616 / 18.970 / 18.970 |

The earlier `dense-release.json` **261.781 ms** DEV draw maximum is retained as
an unresolved performance extreme, not hidden behind the final lower median.
Its off p50/p95/p99/max was 31.204 / 48.434 / 57.897 / 57.897 ms and on was
53.569 / 136.477 / 261.781 / 261.781 ms. A separate prior same-scene
render/transport run measured off 21.602 / 45.028 / 63.986 / 63.986 ms and on
33.625 / 41.649 / 47.404 / 47.404 ms. These runs show substantial wall-time
variability; no internal paint-phase measurement proves a unique cause.
This blocks a claim of validated dense-HUD smoothness, not the demonstrated
admission/control-output equivalence. Earlier headless output without
registered fonts is superseded for visual/readability evidence, not used to
claim the final render performance. The checked preview is
`docs/steering-audit/oct16-acc-dev-signal/dense-delivery.png` (also the separate
`dense-render-ipc.png` transport-run preview), explicitly
**TEST DATA**, not a game screenshot.

A **separate** real multiprocessing Manager probe uses the dense 16,425-byte
pickled snapshot, 50 Hz source probes, 60 Hz display reads and bounded 10 Hz
publication. At 150 measured probes per state, off p50/p95/p99/max is
**.543 / 1.307 / 1.849 / 2.274 ms**; on is
**.493 / 1.265 / 1.923 / 4.270 ms**. The 102 display reads are
1.062 / 2.155 / 2.651 / 3.933 ms. No unbounded queue or failed publication.
This isolates transport/display contention; it is not end-to-end SDK-to-write
latency and does not explain a historical steering stall.

The final complete suite is **2,813 passed and 1,592 subtests passed in
676.45 s (11:16)**, exit code zero. Log:
`docs/steering-audit/oct16-acc-dev-signal/final-source-bound.log`; receipt:
`final-source-bound.verified.json`. All 19 runtime payload SHA-256 values are
identical before and after this complete run. The earlier 2,811-pass run is
not the candidate's acceptance proof: its runtime changed during verification
and the existing hash guard correctly refused it. No test expectation or
safety threshold was weakened to obtain the final PASS.

`compileall` and `git diff --check` pass. No installation, game action, arm
command, commit or push is performed.

## Verdict boundaries

| Property | Offline verdict | Historical/game boundary |
| --- | --- | --- |
| Observed crossing ends without false lost-lead technical stop | Targeted PASS | Exact original rejection actor array missing; GAME NOT VERIFIED |
| Missing/reassigned/stale owner cannot certify completion | Targeted PASS | Native ID is not a certified vehicle incarnation |
| Dense DEV admission keeps priority bodies in original budget | Targeted PASS | Optional predictions can be omitted explicitly; no road-clearance claim |
| DEV preserves control output and source-read count | Paired benchmark PASS | Display has measurable nonzero overhead |
| Dense HUD render smoothness / hard timing bound | NOT VERIFIED | Final offscreen draw max 18.970 ms; earlier 261.781 ms extreme unexplained, not diagnosed as a game stall |
| Same-red phase survives an ordinary external brake | Integration + paired-plant PASS | Historical red reset branch not retained; GAME NOT VERIFIED |
| 5 m reference, continuous hold and green restart | Paired-plant PASS | Physical painted stop line/front-bumper offset remains unmeasured |
| Universal comfort/reliability | NOT VERIFIED | No promise of all roads, all actor intent or zero future faults |

No new drive is requested. A prepared candidate requires separate approval and
deployment before any game conclusion. This report does not call the entire
historical incident uniquely explained or the new behavior GAME VERIFIED.

## Changed files and coherent runtime scope

Actual runtime changes: `core/acc_following.py`, `core/engine.py`,
`core/longitudinal.py`, `core/navigation/longitudinal_diagnostics.py`,
`core/traffic_dev_hud.py`, `plugins/acc/main.py`. The separately existing
`ui/visualization.py` fix remains in the candidate unchanged from task start.
`PLUGIN_CHANGELOG.md` describes the actual ACC 1.3.4 behavior; no unrelated
plugin version is increased. New joint tests and the adjusted passive-detection
test are in `tests/test_oct16_joint_traffic_regressions.py` and
`tests/test_oct15_crossing_dev_hud.py`; the existing
`tests/test_visualization_live_path.py` is preserved.

Tracked analytical/preparation tools are `tools/analyze_oct16_joint_evidence.py`,
`tools/verify_oct16_joint_traffic.py`, `tools/benchmark_oct16_dense_hud.py` and
`tools/prepare_oct16_joint_runtime.py`. This report and `DEFERRED_WORK.md` record
the scope and limitations. Raw traces, logs, previews and candidates remain
outside tracked source under the ignored audit directory.

The single candidate reuses the existing source-bound verification/preparation
mechanism and carries these **19 files**, including unchanged dependencies:

```text
core/acc_acceleration.py
core/acc_body_prediction.py
core/acc_following.py
core/engine.py
core/control_timing.py
core/longitudinal.py
core/pid.py
core/service_brake_hold.py
core/navigation/traffic_producer.py
core/navigation/longitudinal_diagnostics.py
core/sdk/traffic_snapshot.py
core/sdk/scs_sdk.py
core/telemetry.py
plugins/acc/main.py
plugins/drivepolicy/main.py
PLUGIN_CHANGELOG.md
core/hud.py
core/traffic_dev_hud.py
ui/visualization.py
```

Unchanged Map, Autopilot, other plugins and native dependencies are bound by
the required installed 33-file base receipt/hashes; mixed deployment is not
authorized. No DLL, settings, cache, original diagnostic or commit marker is
overwritten. Older candidate/evidence files remain intact and are superseded
only as future deployment proposals. Separate explicit user approval and a
whole-set rollback backup are still required before any deployment.

Prepared candidate (one ZIP, not a deployment):
`docs/steering-audit/oct16-acc-dev-signal/oct16-joint-traffic-acc134-candidate.zip`.
SHA-256:
`fdf3175e171af3b399977305c06d122fa7ac02cd1c1033736e13bcd9098ee84a`.
Its sibling `.manifest.json` and embedded `candidate-manifest.json` bind all
19 payload hashes, complete-suite receipt, starting HEAD, actual uncommitted
working-tree state, plugin versions and required installed base. Every archive
payload was read back and rehashed; no DLL is included. Tools, tests, reports,
raw data and temporary files are not runtime payloads. Earlier candidates remain
historical originals and are superseded as deployment proposals by this ZIP.
