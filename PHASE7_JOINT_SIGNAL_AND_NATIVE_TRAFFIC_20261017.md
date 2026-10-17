# Joint signal approach and native traffic evidence — 17 October 2026

## Current status: resumed signal completion

The resumed implementation supersedes the **partial proposal** recorded below.
Both original target-rebound assertions now pass unchanged and are collected
by the normal suite. A separate before/after production reproduction proves the
positive-approach-receipt/first-zero-observation phase bug in both automatic
modes. ACC1.3.8 implements the spatial-reference/PID correction; core shares the
continuous-receipt transition. Native candidate1.59.5 remains byte-identical.
See **Resumed completion evidence** at the end for criteria, same-clock model
results and final frozen verification. Historical missing inputs/contact are
not retroactively explained and nothing is GAME VERIFIED or deployed.

All sections up to that completion section describe the preceding investigation
and its preserved, superseded candidate/results. Their former OPEN verdicts
must not be read as the resumed implementation's current test result.

## Gate 1: immutable reconstruction before runtime edits

Entry HEAD `f93f67e`, clean working tree. No applicable AGENTS.md is present in
the workspace or inspected parent directories. PLUGIN_VERSIONS.md and the two
preceding signal/quota reports were read. All **34 installed receipt hashes**
and **27 runtime source comparisons after LF/CRLF normalization** match. ACC is
1.3.7. Entry source ZIP and hash report are preserved under
`docs/steering-audit/oct17-joint-lifecycle/`. No installation or recording changes.

Seven matching session exports (four significant events, pedal incident, dense
replay and timing) pass existing hash/codec integrity checks. The extractor is
`python -m tools.analyze_oct17_signal_lifecycle`; its `timeline.csv`, `rows.json`,
`writes.json`, `sources.json` and `summary.json` preserve original clocks and
separate immutable consumed packets from sampled history and dense telemetry.
The four event times are 10982, 10982.6, 10984.4 and 10995.6 monotonic seconds;
the final history covers 10993.4408–11023.5267 s. They are the same activation,
session 1, intent `edc6cd043b5e48ac861e4829064b0ea3`, revision 9,
build `72b56596668644c7a3c93e1155c698ed`, geometry fingerprint
`15ec4a77b2d27bc3b597ef7fb56e5d3e735b17ac528506fc82b6fc3d4e42d88a`.

| Original monotonic time | Recorded observation / decision |
| --- | --- |
| 10976.2235 | Own 0.12 launch; gear 0, later positive 4 and successful handoff |
| 10982–10995 | Model-independent SDK speed disturbances; detailed event windows retain their own consumed requests, not the whole journey's write sequence |
| 10996.060 | 6.72 m/s, signal green, target distance 166.13 m; selected speed brake 0.0789. This is not yet proof of red-stop braking. |
| 11003.052 | Same qualified head ID 1 is red, distance 124.82 m, speed 6.33 m/s |
| 11011.011 | Speed 10.70 m/s, distance 69.90 m; signal-distance brake 0.2477 |
| 11012.034 | Speed 7.31 m/s, distance 60.87 m; written drive 0.3248, zero brake |
| 11013.038 | Speed 7.35 m/s, distance 53.83 m; drive 1, signal-distance recovery |
| 11016.035 | Speed 4.90 m/s, distance 32.40 m; drive 0.3081 |
| 11018.025 | Speed 4.29 m/s, distance 21.78 m; written 0/0, SDK game brake 0.2237. The mixed game input is not automatically attributed to a driver or this same row's write. |
| 11020.064 | Speed 4.36 m/s, distance 14.82 m; brake 0.2779 |
| 11021.041 | Speed 1.36 m/s, distance 11.90 m; drive 0.4022 |
| 11023.1802 | Successful brake-zero backend return, previous drive about 0.3005; exact consumed traffic is still red, distance 7.526 m, ACC target 13.407 km/h, ACC drive 1, actual speed 0.344 m/s |
| 11023.3304 | Speed 0.1278 m/s, gear 4, distance 7.491 m; written drive 0.4651, SDK game drive 0.334, SDK brake 0. No confirmed continuous brake hold. |
| 11023.51097 | First Engine refusal, SDK frame 228990840, original observation 11023.5031681, gear 0, speed −0.0115278 m/s; fresh valid command from frame 228907510, computed 11023.470988, expires 11023.8262798, drive 0.6208733. Identity matches, remaining 315.31 ms. |

The first fault is **not** evidence expiration and not measured reverse gear.
It is `simple automatic zero ratio lacks continuing forward motion` after a
released nonterminal approach. The last recorded signal is **red**, not green:
ID 1, source lifecycle 90370547056636, passage
`45540e750098d8f1fc11bc8b76cd20b1ae161420a94ae48b90dad1891389062f`.
Entry progress 280.401436 m, XYZ (34753.4735,6.902344,45663.9580), reference
allowance 3+2=5 m. This is the existing derived curve-entry target, not a measured
painted line or bumper. No green is inserted to explain the historical fault.

## Exact evidence boundaries

Game/user pedal channels are present and kept separate from backend returns.
They show delayed/different values during gear changes and the final slowing;
the journals do not prove the owner of the game's mixed input. Motor brake is
false, retarder 0 in the retained terminal load observations. **Engine-running,
engine RPM/clutch, damage and concurrent external device writes are not retained
for the decisive 11020–11023 interval**. No claim that the driver, engine damage
or a particular input backend caused that slowing is supported. Replaying the
observed speeds is a command replay, not a closed vehicle-dynamics experiment.

The reported car contact has no exact confirmed time/object in these exports.
Dense pose can localize the roundabout traversal, but it cannot reconstruct an
unrecorded actor. Detailed traffic receipts do prove a separate code defect:
six duplicate parked IDs make the whole actor feed `ambiguous_actor_id`, before
selector/crossing/body-AEB evaluation. Examples include ID104 in parked slots
15/18 and ID123 in 17/19, identical decoded poses. Raw original native pointers
and the complete actor lists at contact are absent. Do not claim a particular
car was detected, missed, or hit solely from these examples.

## Source defect found before patching

The hash-bound native source matching the installed DLL is preserved at
`docs/steering-audit/oct14-completion/native-candidate-c`. In
`src/processing/traffic.cpp`, `process_traffic_object` walks a parked vehicle's
`slave_trailer` chain but appends **traffic_actor (the parent)** on every loop
iteration instead of **slave_trailer**. The later writer obtains both pose and
pointer-based ID from that wrong parent. Repeated parent IDs can therefore
invalidate an otherwise useful moving feed. This is a concrete source defect;
the exact original native pointers were not exported, so it is not labelled
the uniquely established cause of the reported collision.

Before any production change, reproduce the native pointer/record defect and
the signal profile's speed-dependent target rebound through real downstream
components. Candidate acceptance requires unchanged emergency/identity/freshness
guards, measured same-model improvement, no stop-target overrun and preserved
green/hold lifecycle. Failed candidates will be recorded as rejected, not hidden.

## Contact-time clarification and exhausted retained inputs

The user confirms that contact was **before** the right indicator at 11:13:02.
The corresponding earlier traversal includes prefab `dlc_blkw_48` UID
5337536180303306287 at 10988.4898–10993.2932 s, approximately progress
78.82–94.68 m. Speed falls to 0.908874 m/s at 10990.8394. This is a plausible
interval to inspect, not a confirmed collision timestamp. All **53** retained
history rows in 10988–10994 report `ambiguous_actor_id`. Four sealed source
receipts on either side also show that rejection and no decisive actor brake.
The actual moving actor array, original native pointers and contact/damage
event are not present. We cannot name the contacting actor or recreate its box.

## Accepted native correction and exact proof boundary

The actual three native methods (`get_uid_for_vehicle`,
`process_traffic_object`, `write_parked_vehicle_data`) are extracted from the
hash-bound deployed source and compiled with fake game-object discovery and
placement. Their actual output is the unchanged **1,720-byte** parked ABI. The
same record goes through the real timed TrafficReader, capture, selector, body
prediction, Policy, ACC, AP, Engine and actual Controller/test memory backend.

On the deployed source the parent-plus-two-trailer fixture and repeated source
enumeration emit the same parent several times, and the complete traffic path
rejects the entire actor set before evaluating a genuine modeled crossing.
The initial combined reproduction has **9 failures** (including both separate
signal-profile cases). Seven are the native/physical-path reproductions.

The corrected source:

- appends the actual `slave_trailer` pointer in the parked chain;
- serializes each identical parked native pointer once before the 40-record
  truncation, using a fixed **40-pointer / 320-byte** stack array on x64;
- never merges different pointers by position or short ID and does not weaken
  Python ambiguity, source-time, R, identity, stale or backend checks;
- leaves Signal schema 3, Traffic schema 1, every wire size and every other
  native source file unchanged apart from the implementation version string.

Final native version is **1.59.5-up-parked-records**, DLL SHA-256
`fd06c12985fb67c48a7b9aaf5dd500d81e6ac23b928b79c95997bb8ed5d55d27`.
The build receipt and compiled fixture bind that source. The earlier
unordered-set candidate is superseded by the fixed-array candidate B; neither
has been deployed. Telemetry init/shutdown exports load offline without game
initialization. This is a meaningful producer bug fix, not a version bump for
tests. **ACC remains 1.3.7 and all Python plugin versions remain unchanged.**

At stationary simple automatic without a previously owned continuous brake,
the predicted conflict is required upstream but the physical guard may demand
driver takeover rather than seed a new brake edge that could select R. In real
automatic and during forward motion the actual brake write is checked. No
parking brake or hypothetical ego acceleration is used. Native body prediction
uses the actually observed stationary/constant-speed ego body, including an
incoming actor approaching that current body. This is an explicit motion model,
not certified gap acceptance, complete coverage or ETS2 consumption.

## Signal candidates: measured and REJECTED

The deployed envelope is `sqrt(2*a*max(0,d-v*1.5))`. Reducing the observed speed
can increase that target even at a closer point. A production repro in both
gearbox modes measures **26.2084 → 26.3907 km/h** while distance decreases
40→38 m and speed falls 9→7.42 m/s. Existing feed-forward switching can then
return to ordinary positive PID demand. This proves a mechanism, not that it
alone explains all observed slowing, especially the unobserved vehicle input.

Two experiments were tested against the exact entry runtime on the same real
placed prefab and existing explicit uncalibrated plant. Signal source clocks,
IPC sequencing, independent Policy every-third tick and jitter are retained.
The plant uses mass ratio 1.4, brake response 0.35/0.60 s and input delay
0.12/0.35 s. Criteria fixed before comparison: no target/entry overrun or pedal
overlap, stop gap 0–1.5 m, unchanged safety/hold, automatic green restart, no
extra pedal reversals or larger maximum modeled deceleration. Jerk and physical
stop/launch regressions are separately assessed, not hidden behind mean scores.

| Experiment / same model | Before | Candidate | Decision |
| --- | --- | --- | --- |
| Spatial fixed-envelope only, 20 km/h, simple, 0.12 s delay | 4 reversals, jerk 3.248 m/s³, target gap 0.951 m | 2 reversals, jerk 7.803 m/s³, gap 1.374 m | REJECTED: comfort regression |
| Same envelope, 35 km/h, both modes, 0.35 s delay | gap 0.562 m | gap 1.616 m | REJECTED: outside existing stop criterion |
| Same envelope, 50 km/h, simple, 0.12 s delay | 3 reversals, jerk 3.263 m/s³ | 1 reversal, jerk 2.580 m/s³ | Improvement in this case does not rescue the failed matrix |
| Envelope plus existing signed PID/feed-forward, 20 km/h, simple, 0.35 s delay | valid stop/restart | launch-expiry technical stop; jerk 48.572 m/s³ | REJECTED: new safety lifecycle regression |
| Same signed-PID experiment, 50 km/h, simple, 0.35 s delay | valid stop/restart | launch-expiry technical stop; 7 vs 1 reversals | REJECTED |

The first experiment ran 12 paired cases across both modes; the second ran six
simple-auto pairs and focused checks in both modes before rejection. One
baseline high-delay 35 km/h case also expires at launch; the baseline is not
called universally safe. Full rows/writes/model metrics and rejected source
are preserved in `paired-*`, `signed-pid-0` and
`rejected-signed-pid-runtime.zip`. The experiments were removed with exact
context patches; final `core/longitudinal.py` and `plugins/acc/main.py` match
entry content. No old expectations/gains/timeouts were weakened.

The **still-failing** desired-profile reproducer is retained explicitly as
`python -m pytest tools/reproduce_oct17_open_signal_profile.py -q` (2 failures).
It is not included in a claim that the accepted regression gate fixes signals,
and is not hidden by an xfail or changed assertion. Normal suite PASS cannot
turn this OPEN issue into a completed result.

## Minimum passive evidence gap

`engineEnabled` and `engineRpm` already exist in the same raw telemetry read but
were discarded by the journal. The accepted diagnostic-only extension carries
their original raw presence (missing/invalid values remain null) in
`powertrainObservation`, then immutable decision `powertrain_observation` and
the existing 30 s history. It adds no SDK/IPC read, control condition, queue or
collector. Original frame/time come from the same enclosing snapshot. Raw
clutch, damage and external device ownership remain explicitly unavailable;
no new offset or input-owner guess is introduced. Existing convenience
telemetry defaults are not used as evidence of engine-off/zero RPM.

This addition is not the signal fix and does not recreate the missing historical
powertrain state. The narrow remaining question is why the real vehicle reaches
zero/neutral on the still-red, nonterminal approach while the backend and later
game throttle are positive. A valid green cannot be invented; a blind brake at
standstill or launch on red cannot solve that missing causal proof safely.
The smallest next evidence is the original engine-enable/RPM and game-pedal
response through that exact final approach, and the native actor body snapshot
at the reported contact. These fields are to be observed passively through the
existing diagnostics when available; no general repeat drive is requested here.

## Performance (operations are not interchangeable)

Actual compiled parked acquisition/serialization, 40 objects, 25 warmup + 1,000
measured operations, microseconds:

| Version | p50 | p95 | p99 | Max | Aggregate process CPU |
| --- | ---: | ---: | ---: | ---: | ---: |
| Deployed | 1.0 | 1.2 | 1.2 | 56.3 | 0.001 s |
| Fixed-array candidate B | 0.8 | 1.4 | 1.5 | 109.7 | 0.001 s |

Retained vector capacity42 and pointer-ID entries40 are identical in this bounded
fixture. The new duplicate guard adds 320 stack bytes, no per-record heap nodes
or worker. Pointer-ID map lifetime/possible reuse is pre-existing and is not
silently declared solved by this patch. Measurements do not certify native
game callbacks or all historical pauses. A superseded heap-set trial had p50
4.1 µs / max214.4 µs and is retained separately, not mixed into final figures.

Separate Python full producer→physical-writer comparisons use 3 paired runs
per mode with 25 warmup + 120 measured ticks. Every output hash and consumed
source-read count matches baseline. Wall tails are variable (simple candidate
maximum40.367 ms, real candidate49.973 ms vs baseline32.300/38.717 ms). Host
load was uncontrolled and some trials overlapped native compilation. No hard
timing or universal speedup PASS is awarded. JSON records CPU, GC and full
p50/p95/p99/max independently. Test mock histories are excluded from retained
runtime display memory; these are copy-on-read test IPC counts, not OS Manager
latencies. The control laws, steering and signal geometry remain entry-identical.

The following are **ranges of per-run medians and worst per-run percentiles**
across the three 120-tick runs, not pooled quantiles. Wall times are milliseconds:

| Mode / version | p50 range | Largest p95 | Largest p99 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Simple / entry | 19.801–20.277 | 27.359 | 28.735 | 32.300 |
| Simple / accepted | 19.806–20.701 | 30.869 | 32.614 | 40.367 |
| Real / entry | 18.091–21.451 | 33.637 | 37.382 | 38.717 |
| Real / accepted | 18.015–23.371 | 39.904 | 45.786 | 49.973 |

Windows thread CPU is quantized to 15.625 ms in these measurements: medians are
15.625 ms, worst p95/p99 31.25 ms in all groups. Maxima are simple entry31.25 /
accepted46.875 ms and real46.875 /46.875 ms. This resolution and concurrent host
load do not support a sub-millisecond Python overhead conclusion. Source-read
counts are identical, but real OS IPC latency is **NOT MEASURED** by this fixture.
Its `runtime_snapshot_deep_bytes=16` is the disabled DEV-HUD's `None` snapshot,
**not journal memory**. Python journal retained memory is not measured by that
field; its existing allocation/count budgets are unchanged and existing bounded
history/export regressions pass. The native fixed guard's 320-byte stack size is
a separate explicit allocation, not a total application-memory measurement.

## Verification and handoff gates

### Why the earlier checks did not establish these outcomes

The ordinary Python traffic fixtures provide already serialized, unique actor
records. They cannot expose a C++ parent/trailer traversal that repeats the
parent pointer. The new compiled-source reproduction crosses that boundary
before using the unchanged native reader and downstream physical writer. Its
fake game-object discovery/placement is a test seam; it does not emulate the
game's object allocation or prove the historical contacting car was present.
The full DLL is separately compiled against the actual native headers and ABI
assertions, rather than treating the fake object's layout as a game ABI proof.

Scripted red/green and gearbox tests establish state transitions for their
supplied observations. They do not establish the vehicle's response to a
successful backend return. In this ride, positive written drive and later game
drive coexist with continued slowing, without the retained powertrain channels
needed to explain it. The wider delayed closed-model comparison also exposes
new comfort/launch failures in otherwise locally passing signal candidates.
Those candidates are rejected; the separate two-case open reproduction remains
an explicit failure, irrespective of the normal full-suite result.

The first accepted focused native/signal/hold/journal group passes **114 tests**.
The final gate, static checks, frozen hashes and one full-suite result are
recorded below after completion. Full suite runs once on the frozen accepted
code. No game/runtime authority is granted by a package, a successful backend
write or pytest.

| Requested area | Verdict |
| --- | --- |
| Smooth red approach without cycling | **REJECTED CANDIDATES / OPEN**. Rebound mechanism reproduced; attempted corrections fail wider criteria. |
| Green at last metres/zero ratio then launch | Existing supported handoff regressions pass; **BLOCKED for this incident** because first fault is still red after unexplained physical slowdown. No false-green/unsafe-standstill exemption added. |
| Roundabout actor protection | Native parked-parent/duplicate-record defect **FIXED / OFFLINE VERIFIED**; whole historical contact and unobserved coverage remain **BLOCKED** by the absent actor capture/contact time and no coverage guarantee. |

**The joint task is not complete. GAME NOT VERIFIED.** No deployment, commit,
push or game operation. A single hash-bound partial candidate will be prepared,
explicitly labelled with these open areas rather than sold as a completed fix.

## Final frozen verification and partial handoff

- Final focused group: **162 passed in 47.62 s** (`targeted-final.log`).
- Final normal full suite, run once after reverting rejected experiments:
  **2945 passed, 1592 subtests passed in 1288.60 s (21:28)** (`full-final.log`).
- All frozen Python runtime/test/tool files, runtime dependencies, changelog,
  candidate native DLL and build receipt remain byte-identical throughout that
  run and the subsequent package check (`final-frozen.json`,
  `final-verification.json`). Source HEAD is
  `f93f67e06427f2d958a8bffe02168340b152099b`, with these uncommitted changes.
- `python -m compileall -q core plugins sdk tests tools` and
  `git diff --check` pass. The separate desired-signal-profile reproduction
  still has **2 failures** (`open-signal-current.log`). It is deliberately not
  represented as one of the 2945 passing tests or a completed signal fix.

Candidate:
`docs/steering-audit/oct17-joint-lifecycle/ultrapilot-oct17-native-records-PARTIAL-candidate.zip`

SHA-256:
`0da2c00c0c4847904446e833a375bef16385877c252555c935ccc6b6f87e53e7`

All 27 entries were read back and hash-checked. The manifest has
`task_complete=false`, `game_verified=false`, `runtime_authorized=false`.
It contains 22 coherent runtime dependencies, one candidate DLL, two third-party
licences, the native build receipt and manifest. It contains no tests, reports,
settings, commit marker, map cache or original recordings. This is one **partial
proposal**, not authorization to install or a final three-outcome repair.

Exact runtime entries (unchanged dependencies are included to avoid a mixed
proposal):

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
core/controller.py
core/steering_replay.py
core/transmission_mode.py
assets/ets2la_plugin.dll
```

Any later approved DLL deployment would need matching copies in application
assets and `ETS2/bin/win_x64/plugins/ets2la_plugin.dll`; neither was written.
The native source/build/probe remain in `native-candidate-b/` and
`native-candidate-b-probe/`, reproducible via
`tools/prepare_oct17_native_candidate.py`. Superseded experimental artifacts
remain evidence, not alternative current deployment proposals.

Only `core/telemetry.py` and `core/navigation/longitudinal_diagnostics.py` change
Python runtime behavior here, passively. The native build tool applies the
two source corrections and version string in a separate candidate tree. The
new test and analysis/build/verification tools, this report, changelog and
DEFERRED_WORK.md make the evidence and unfinished scope reproducible. All Python
plugin versions and pre-existing control implementations remain unchanged.

No further full pytest run is needed for the same frozen source. This does not
close the red-profile failure. Its next implementation requirement is one
coherent distance/deceleration trajectory that passes the **entire existing
paired delay/speed/mode matrix**, including launch and terminal hold; the two
rejected local changes must not be deployed as a shortcut. Historical
still-red physical slowing and the contacting actor cannot be reconstructed
from absent channels. The smallest missing evidence is the already acquired
engine enable/RPM with the exact game-pedal response over 11020–11023, and the
actual native actor/body acquisition at contact; the passive extension cannot
recover them retrospectively. No general repeat journey is requested here.

## Resumed completion evidence

### Proved defects and coherent implementation

1. The old target subtracts measured `speed*1.5` before taking its square root.
   Slowing therefore relaxes the same red target. The original pair of
   assertions fails on the entry source (`resume-profile-before.log`) and passes
   on the corrected source. No assertion, skip or xfail was added. The shared
   signal reference is now the positive spatial solution of
   `d = v_ref*T + v_ref²/(2*a)`, with unchanged `a=1 m/s²`, `T=1.5 s` and derived
   target/5 m allowance. This reference depends on distance, not its feedback
   speed. Actual speed still determines the independent required-stop demand.
2. Merely changing the square root was insufficient. Ordinary cruise integral
   memory plus an independently switched distance brake produced alternating
   control and could compound the new deceleration. The existing signed PID now
   tracks the spatial reference with analytic feed-forward
   `-a*v/(v_ref+a*T)`. Entry/exit ownership resets old cruise memory; integration
   is inhibited only while this moving signal reference owns the plan. Ordinary
   cruise/ACC integration is unchanged. Normal negative demand is bounded by
   the larger of the declared planning deceleration and **current required-stop
   deceleration**. Exhausted actual stopping reserve, another winning brake and
   emergency can still require more immediately. The old terminal brake floor
   and original actuator ramp remain; no throttle ban or extra regulator/filter
   is introduced. Large real underspeed may still legitimately recover drive.
   `terminal` and Engine's independent Traffic safety brake explicitly retain
   the **actual-speed exhausted-reserve** test. A positive spatial reference
   must not erase that original safety condition or its hold commitment.
3. A real positive brake receipt could still be labelled `approaching` when the
   next SDK observation first reported zero speed/ratio. Plugin's ratio gate ran
   before Engine's `after_write` could relabel it as `holding`. The new red
   production reproduction failed in **both modes** (`resume-zero-before.log`).
   The same helper now recognizes only a positive, forward-admitted receipt
   with its chain/sequence at this stopped transition. Engine still verifies
   the actual local backend receipt, freshness and identity before writing.
   Interrupted/released approaches do not qualify, and no new stationary brake
   edge is manufactured. Red can retain its chain; new same-head green uses the
   existing two-acquisition clearance and bounded restart.
4. Explicit engine-off evidence is not an ordinary ratio transition. The
   existing raw-presence powertrain observation can veto a restart, initially
   and on the final already-required truck read. The existing engine-running
   threshold150 RPM is reused; missing legacy fields are never called measured
   engine-off/healthy. The original frame/time and decisive health values are
   retained in the existing first-fault record before cancellation. This is
   driver handover on a real known fault, not automatic engine starting or a
   certified unattended hold after a technical fault. Both engine-off cases
   fail before that guard (`resume-engine-before.log`); final-read publication
   races are also tested with a genuinely newer SDK observation.

The historical last refusal is still on **red**, after a released brake and
unexplained slowing with positive backend/later game throttle. It lacks the
positive uninterrupted receipt required by fix3, and is not retrospectively
called a green bug. The reproduced phase bug is a concrete additional code
defect, not proof that the unrecorded powertrain caused the original event.

### Model clock correction and acceptance

The earlier plant integrated only each scheduler `dt` but the simulated process
clock also advanced12+8+10 ms for publication/IPC. Thus leases advanced while
the vehicle did not move during those30 ms; the candidate's earlier launch
expiry could not be treated as a fair whole-loop timing result. The existing
benchmark now has explicit `coherent_processing_clock=True`: it integrates the
previous processing interval, dates a write after processing and applies input
delay from that write. Every consecutive model timestamp difference is asserted
equal to the actual mocked control-clock difference. Legacy mode is retained
and labelled solely for reproducing old reports, not current acceptance.
No runtime clock, lease or timeout was changed to fix this test limitation.

Criteria retain the preceding declared requirements: same target, stop gap
0–1.5 m with no target overrun, no positive pedal overlap or parking operation,
continuous terminal brake, green restart, no extra pedal reversals, and no
larger maximum modeled deceleration/jerk against the same-clock baseline. The
new tests additionally require at most one drive→brake transition on red and
zero time below5 km/h while still more than10 m from the target. These directly
measure the reported repeated cycling/far crawl; neither is a minimum-speed
command. Both original assertions are part of the regular test suite now.

The baseline is the exact hash-checked entry functions, retained in
`tests/fixtures/oct17-signal-profile-original.json`; no ignored source ZIP is
needed to recreate those two functions. The paired benchmark substitutes these
two original functions to isolate the approach change; shared physical/receipt
guards are current in both runs. Original pre-fix phase reproduction is logged
separately. The native reader/real placed PPD fixture is the existing Oct10
offline fixture, not an invented capture of the unrecorded contacting actor.

The12 paired full production-flow cases use both gearbox modes, speeds20/35/50
km/h, transport delays120/350 ms, responses350/600 ms, mass ratio1.4,
independent Policy every third tick and jitter33/50/80 ms. The model is explicitly
uncalibrated, with its existing drag/gravity terms and nonnegative-speed clamp.
Max jerk is a finite difference of modeled acceleration using actual elapsed
model time; it includes stopping-clamp effects and is not measured ETS2 jerk.

Both modes have the following approach metrics (restart selector timing differs):

| Speed km/h / delay ms | Stop gap before→after m | Full-cycle pedal reversals before→after | Max deceleration before→after m/s² | Max absolute model jerk before→after m/s³ |
| --- | ---: | ---: | ---: | ---: |
| 20 /120 | 1.225→0.436 | 4→2 | 1.049→1.018 | 2.247→2.234 |
| 35 /120 | 1.067→0.437 | 4→2 | 1.155→1.077 | 2.888→2.589 |
| 50 /120 | 0.868→0.438 | 3→1 | 1.592→1.592 | 2.325→2.325 |
| 20 /350 | 0.641→0.595 | 2→2 | 1.079→1.053 | 3.035→1.887 |
| 35 /350 | 0.442→0.606 | 4→2 | 1.831→1.185 | 9.067→1.902 |
| 50 /350 | 0.677→0.609 | 1→1 | 1.681→1.512 | 25.874→1.587 |

All12 candidates stop before the same target and restart, with zero observed
technical terminations, overlaps, parking writes, target overruns or terminal
brake-zero samples. The regular regression repeats these comparisons and checks
the red-only reversal/far-crawl criteria. Four additional closed scenarios pass
green while moving /200 ms before the modeled red stop, both modes, and recover
drive within the existing2.5 s bound. Scripted SDK cases exercise green exactly
at gear0, repeated stop/hold/restart cycles, other brake ownership, stale/foreign
inputs, backend interruption, R, engine-off and final-read races. They establish
software/actuation behavior, not consumption by ETS2.

### Existing test contract and preserved behavior

The old geometry test duplicated the **defective measured-speed formula**. It
now independently checks the defining distance equation and independence from
measured speed, retaining the once-only5 m subtraction and all geometry checks.
The exhausted-reserve test still demands full positive braking; its reference
target no longer collapses simply because measured speed consumes the reserve.
No safety assertion is removed.

Two clearance fixtures manually published ACC brakes without the real
producer's `signal_stop_control` / `signal_brake_selected` fields. A separate
Traffic brake under the former zero target masked that missing ownership.
The fixtures now explicitly carry their intended ACC-owned signal-stop
contract. All original physical continuity, identity, green relevance and
negative assertions remain. An unrelated ACC/curve brake beside a red is still
not automatically a signal-stop commitment.

The16 steering benchmark cases and12 ordinary longitudinal comfort cases are
**numerically identical** to entry HEADf93f67e. The native candidate, source
receipt and packed ABI remain unchanged and its downstream AEB/physical-write
tests are rerun. Actual ambiguous IDs are still rejected. Missing/empty traffic
never receives a coverage certificate; historical contact and full sensor
coverage remain unverified, independent of these signal fixes.

Final targeted/static/frozen full-suite result and the new coherent candidate
receipt are appended after completion. The earlier `full-final.log` / partial
ZIP attest only their earlier source and are retained as superseded evidence.

The completed targeted evidence before freezing includes169 passing lifecycle,
native, signal and negative cases (`completion-targeted.log`);92 passing
terminal-reserve/traffic/real-reference cases after the safety-branch correction
(`resume-terminal-contract.log`); and25 passing original-reproducer/last-read/
incomplete-receipt cases after the final fail-closed handling
(`completion-last-negative.log`). These groups overlap and are **not summed**
into a unique test count. The separately preserved same-clock matrices are
`completion-matrix-0/results.json` and `completion-matrix-3/results.json`.

| Scope | Current offline verdict | Boundary |
| --- | --- | --- |
| Original two red target-rebound cases | FIXED / OFFLINE VERIFIED | Both unchanged assertions also collected by the full suite. |
| Paired20/35/50 km/h red stop / hold / green restart, both modes | OFFLINE VERIFIED in declared model | Twelve paired cases, no target overrun or repeated red reversals; uncalibrated physical response. |
| Positive approaching receipt → first gear0 → red wait / green launch | FIXED / OFFLINE VERIFIED | Previously failed in both modes; never admits a released/interrupted brake or seeds a new brake at rest. |
| Genuine R, stale/foreign data, backend loss, explicit engine-off | Rejection preserved / targeted verified | Fault does not automatically restore propulsion; no claim of certified unattended hill hold after failure. |
| Correct native tractor/trailer records → downstream AEB/write | Preserved FIXED / OFFLINE VERIFIED | Same DLL/source hashes; actual actor ambiguity still rejects. |
| Original actual contact / unexplained slowing with positive game drive | NOT RETROSPECTIVELY VERIFIED | Missing original actor capture and powertrain/input-owner channels remain missing. |
| ETS2 consumption and comfort after this change | GAME NOT VERIFIED | No installation or game operation performed. |

### Complete-suite follow-up and final source freeze

The first resumed whole-suite run is preserved as `full-completion.log` with
its matching `completion-frozen.json` / `completion-verification.json`:
**6 failed, 2978 passed, 1592 subtests passed in 782.39 s**. The files were
unchanged during that run. This failed build is not a verified candidate.

Four failures were real integration regressions in the new signed mapping:
it overwrote the existing response-sized coast phase with a small positive
PID recovery after the same red approach had already braked, including an
intervening independent Policy brake. The mapping now preserves that existing
phase within its original `a*T` underspeed allowance. Substantially larger
underspeed can still recover drive; this is neither a permanent throttle ban
nor an extra filter/controller. The four original physical-output and integral
expectations in `test_oct12_stop_and_indicators.py` and
`test_oct16_joint_traffic_regressions.py` are **unchanged**.

One remaining failure was the uncertainty-reference fixture duplicating the
superseded measured-speed formula. Its new independent distance equation checks
the common spatial reference, while the original actual-speed **27 m takeover
reserve**, takeover positions, target identity/distance and absence of clearance
remain unchanged. The sixth failure exposed a real release-document schema
error: the combined heading was not recognized by the existing welcome parser.
ACC1.3.8 is now recorded under the existing `## ACC` / `### 1.3.8` schema;
no parser/runtime workaround or extra version increase was used.

After these corrections all **89** tests in the four affected files pass
(`completion-six-regressions.log`), as do **186** targeted production-flow,
closed-model, native/ABI/AEB, stop/green and negative cases
(`completion-final-targeted.log`). These groups overlap and are not summed.
The final twelve paired model results were copied from that targeted run,
without another simulation run, into `completion-final-matrix.json` and its
mode-specific raw-result directories. All numbers in the table above are
unchanged. The final16 steering and12 ordinary comfort benchmark cases also
remain exactly equal to entry HEAD (`completion-final-benchmark-comparison.json`).

The corrected sources are frozen in `completion-final-frozen.json`. The
single complete run on **this corrected build** writes
`full-completion-final.log` and `completion-final-verification.json`:
**2984 passed, 1592 subtests passed in 831.33 s (13:51)**. All frozen Python,
test, tool, changelog and native source/artifact hashes remain unchanged.
The log SHA-256 is
`faa4cf905c5f240ee83ba0284cb08fa643b4562a4d93642e2e6441d3419756f4`.
`compileall` and `git diff --check` pass. The packaging tool refuses a failed,
modified or mismatched full-suite receipt and preserves the earlier failed
records and partial package. Another whole-suite run is unnecessary unless
these sources change.

### Coherent completion candidate — prepared, never installed

`docs/steering-audit/oct17-joint-lifecycle/ultrapilot-oct17-signal-completion-candidate.zip`

SHA-256:
`010e50026d9f8d8d2072790ca1dabe1cf05e365d0fdba619a1d258a116d2b197`

All **30 entries** were read back and byte/hash-checked: the25 entries below,
one candidate DLL, two MIT licence texts, the native build receipt and candidate
manifest. `completion-final-candidate-receipt.json` records that ZIP. Native
DLL1.59.5 retains SHA-256
`fd06c12985fb67c48a7b9aaf5dd500d81e6ac23b928b79c95997bb8ed5d55d27`.
When separately approved, the same DLL must be used for the app asset and game
plugin targets; preparation itself grants no installation/game authority.

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
core/controller.py
core/steering_replay.py
core/transmission_mode.py
plugins/autopilot/main.py
plugins/map/main.py
core/sdk/signal_snapshot.py
```

The receipt-bound installed base still matches all34 deployed files. Normalized
LF/CRLF comparison of this payload finds **seven changed Python files**:
Engine, longitudinal, service-brake hold, longitudinal diagnostics, telemetry,
ACC and transmission mode; the changelog also changes. Other payload files are
unchanged consistent dependencies. The native DLL change is additional and
explicit. Only ACC's Python implementation version advances to1.3.8; Autopilot
remains1.3.4, DrivePolicy1.1.4 and Map1.1.2. No settings, map cache, commit marker,
tests or original recordings are included or changed in the installation.

The native compiled-record regression explicitly checks positive physical
braking at1 and10 m/s in both modes. At standstill it requires the modeled
conflict and zero drive, allowing the simple-auto guard to demand takeover
instead of seeding a fresh stationary brake. It does not certify stationary
game input semantics, sensor coverage or collision avoidance in all situations.

**OFFLINE VERIFIED:** the two original signal target-rebound assertions,
the independently reproduced positive-approach/first-zero phase defect,
declared closed-cycle acceptance, negative guards and native-record correction.
**Historically unresolved:** exact contacting actor and unexplained still-red
slowing under positive game drive; the missing source channels are not invented.
**GAME NOT VERIFIED:** SDK consumption, real-vehicle response/comfort and the
new DLL in ETS2. The manifest deliberately keeps `task_complete=false`,
`game_verified=false` and `runtime_authorized=false`; it is an offline-verified
candidate for separate approval, not a claim that every historical event is
explained. No new journey is requested here and no deployment occurred.
