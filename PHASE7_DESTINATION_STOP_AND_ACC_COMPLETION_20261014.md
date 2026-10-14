# Phase 7 — destination, stop ownership and functional ACC completion attempt

## Status and exact build

**The complete request remains OPEN. Candidate implementation is not deployed;
GAME NOT VERIFIED.** Independent traffic/ACC mechanisms are implemented below.
Automatic GPS disappearance cannot safely become successful arrival with the
available destination contract. Measured load-adaptive acceleration and certified
complete-envelope AEB are not claimed.

Entry HEAD: `b11777d`; working tree was clean. Existing ACC 1.2.1 and DrivePolicy
1.1.4 fixes are retained. Candidate ACC is **1.3.0** for actual implementation
changes. DrivePolicy stays **1.1.4**; Map, Autopilot, indicators and other unchanged
plugins retain their versions. Native candidate is `1.59.4-up-traffic-timed`,
preserving legacy mappings and Semaphore schemas 2/3 while adding Traffic v1.
No commit, push, deployment, game operation or diagnostic arming took place.

Read-only installed audit: all **24/24** receipt hashes match. Compared with
`b11777d`, **19/24** contents match: 17 Git runtime entries and two exact DLL
workspace artifacts. Differences are `core/longitudinal.py`,
`core/service_brake_hold.py`, `plugins/acc/main.py`,
`plugins/drivepolicy/main.py` and the changelog. Python comparisons normalize
LF/CRLF; DLL comparisons are raw SHA-256. The installation does not contain the
previous source follow-up or this candidate merely because a commit marker says so.
Reproducible audit: `tools/analyze_oct13_followup.py --ref b11777d`.
All six completed October 13 exports passed the existing immutable codec/integrity
inspection; original files and the incomplete `.tmp` file were untouched.

## Completed earlier versus remaining work

The historical Policy `KeyError: 'speed'` exhausted its restart budget. The
previous repair keeps the same producer alive through missing startup telemetry
and recovers on a genuine valid frame. The retired-epoch invalid-zero ACC request
is quarantined only inside existing initialization; current/foreign/stale/nonzero
failures still reject. Private ACC ownership resets before invalid acquisition.
Those repairs, 5 m signal reference, distance stopping, green restart and indicators
are preserved. The nominal acceleration metadata alone was not accepted as a
functional ACC improvement.

## 1. Destination disappearance — BLOCKED, not reclassified

Actual source inspected (MIT 2024 Dario Wouters), pinned native commit
`1f16156b9b37b70cf182c2bc09120fa1b234e129`:

| Producer source | Available meaning | Missing meaning |
| --- | --- | --- |
| `src/core.cpp::get_navigation_data` | Physical route node UID, remaining distance/time rows; only republishes when row count changes | No completion/cancellation event; same-count changes can be missed; null task does not clear the old mapping |
| `prism/navigation/gps_manager.hpp` | `trip_distance`, next-checkpoint remainder, waypoint node pointers | A waypoint node is not the exact world point selected by the user; origin/lifecycle of target removal is not defined |
| `prism/navigation/route_task.hpp` | Physical route rows and raw `route_task_node_t` node | Four `unk*` fields have no arrival/cancellation semantics; `private_route_task_target_t` is undeclared/incomplete |
| Bundled SCS telemetry headers | Navigation distance/time, job destination city/company; `job.delivered` gameplay event | No GPS-waypoint completion/removal event or precise final waypoint position. Delivering a job is not arriving at a user GPS point |

We traced the actual producer instead of assuming the old Python mapping is the
only source. Its known fields still cannot distinguish the same sequence of
positive remainder -> missing target after manual cancellation from automatic
arrival. Publishing an assumed final node as the destination or inventing meanings
for unknown native flags would grant drive authority after manual cancellation.
No such contract or fake timestamp is implemented. The count-only publication
issue is recorded as a source limitation, not blamed for the historical removal
or presented as an arrival solution. This candidate leaves GPS ABI unchanged.

Historical clearing frame: speed **10.5741596 m/s**, gear 11,
frame **516196018**; last detailed positive remainder **137.646 m**.
The exact clearing-frame remainder and removal cause are absent. Existing
positive-distance completion tests are preserved; they do not prove this case.
Normal release still transfers standstill holding to the driver; unattended
hill hold after shutdown is not certified. No new stationary brake edge or
parking-brake operation was added to disguise that limitation.

**Smallest required producer work:** identify/implement a proven complete
destination contract (which may use a computed route endpoint, not necessarily
a native exact world point) with stable destination identity and the actual
completion-versus-manual-removal event/hook in the game navigation lifecycle.
The currently incomplete private target type/unknown flags require independent
source/layout evidence before an ABI can truthfully publish them. Another ordinary
ride or photograph cannot supply that missing semantic contract. No ride is requested.

## 2. Unexpected traffic stop — qualified ownership and release IMPLEMENTED

The October 13 hold began at **22404.3793202**, from **traffic**;
the retained history starts **22406.4573366**. The initiating actor/conflict is
missing. The later current demands were zero but the receipt imposed about
**0.212496** brake; the first final fault was actual observed **R**, frame
456448408. No brake-zero edge is proved in the retained physical interval.
The new implementation does not assert that historical turn was a false conflict.

Reproduced code deficiency: every admitted traffic stop was conservatively
latched without an original-cause clearance contract. Even repeatedly observing
the same original crossing body move away could not end the wait. A zero request
or heuristic type cannot repair that contract, as the preserved October 12
crossing safety regression demonstrates.

Candidate contract:

- A new native acquisition atomically includes moving and parked bytes, lifecycle,
  generation, original QPC observation time and original render frame. Python
  receiver time does not create freshness. Repeated reads do not advance history.
- A qualified stop locks the complete bounded set (at most 16) of consumed conflict
  IDs and original authority/time/frame. New observed conflicts add owners; excess
  ownership, source reset or unknown reasons prevent automatic release.
- Clearance requires every original body still present in a unique ID/source/slot,
  changed records, plausible movement, actual dimensions and increasing distance
  outside the existing reference caution corridor; current crossing/body conflict
  demand must be zero. This is observed protective-reference clearance, not a lane
  or coverage certificate. Absence and unchanged buffers are not clearance.
- Engine confirms two newer native clearance acquisitions at least 100 ms apart,
  validates current Policy/ACC/signal restrictions and rechecks immediately before
  release. Only this traffic dependency is removed. Toll, ACC, unqualified traffic
  and a red/unknown signal retain their independent ownership.
- Moving release uses the current validated decision. Stationary release transfers
  to the existing bounded simple-auto or D restart owner, carrying the original
  lock through the handoff. It does not fabricate a new activation or renew a packet.
- Continuous brake remains positive while waiting; propulsion is zero. R, reverse
  movement, interrupted write chain, stale/foreign authority and backend failure
  preserve rejection. No parking operation or new regulator was introduced.

The new real Map/native reader/Policy/ACC/AP/Engine/Controller scenarios fail with
frozen `b11777d`: the same valid source frame has no producer-time qualification,
observed departure leaves hold latched, and native-body prediction is absent.
Candidate tests cover two full stopped cycles in both modes. The model emits
gear/motion only after an actual positive backend drive and zero brake; it cannot
script success while the output still holds. During stationary waiting no backend
brake-zero write occurs. This is software/backend evidence, not game consumption.

## 3. MonoCruise mechanisms — explicit individual verdicts

Reference: local `Downloads/MonoCruise-stable/MonoCruise-stable`, 1.1.2,
MIT copyright 2025 lukas deschryver. Reviewed longitudinal orchestrator/README,
IIDM/CAH, derivative/load mapping, acceleration envelope and ACC architecture.
No MonoCruise code or unqualified ghosts/constants were copied. Standard derivative
estimation and conservative finite-difference anticipation are implemented in the
existing single UltraPilot path.

| Mechanism | Status | Implementation / precise limit |
| --- | --- | --- |
| Desired acceleration/deceleration | IMPLEMENTED, nominal units | Existing speed PID computes nominal acceleration; measured-speed derivative uses a real-dt 150 ms exponential estimate. P, hard limits and emergency are not filtered. Pedal mapping remains exclusive in the shared arbiter. No second controller. |
| Stable mapper and anti-windup | IMPLEMENTED / retained | Same validated nominal 2.2/4.0 offline gains, existing saturation and actual external-output limitation prevent accumulation of unexecuted drive. Target/activation/source failures reset appropriately. |
| Load-adaptive physical acceleration mapper | BLOCKED | Same-frame ego speed and native boxes are now acquired; these do not identify available engine force, effective brake capacity, grade/road load, nor prove causal game consumption of each write. Existing `linear_acceleration` is a vector, TMP fields are placeholders, and summed XYZ is not longitudinal acceleration. No arbitrary truck-wide capacity fit is installed. |
| Asymmetric ordinary power/brake changes | IMPLEMENTED existing single stage, functional noise improvement | Existing AP drive rise 0.8/s, brake rise 2.5/s and release 4/s remain. The derivative estimate reduces unnecessary noisy demand without another recovery filter. Withdrawal/emergency bypass remains immediate. These pedal rates are not a physical jerk bound. |
| Gap/cut-in/confirmed departure | IMPLEMENTED existing guards preserved | All relevant route candidates constrain speed and emergencies despite retained target attribution; body/slot departure checks remain. Reference distances are not bumper distances; measured lane membership/coverage remains unverified. Missing lead still requires takeover. |
| Leader movement anticipation | IMPLEMENTED qualified negative anticipation | Two new same-lifecycle native frames, same unique ID/source/slot, plausible displacement and finite differences. Only negative acceleration (bounded to -2 m/s² over the 500 ms evidence horizon) lowers the existing cap; no positive forecast can add drive. Raw acceleration is retained as unverified, not substituted for measurement. Legacy/torn/paused/duplicate/TMP/reset data do not predict. |
| Predicted tractor/trailer contact AEB | IMPLEMENTED protective model / certification BLOCKED | Producer transports actual ego and actor boxes, source anchor, same-frame SCS speed and complete-enumeration flag up to three ego trailers. Swept oriented-box contact is evaluated along the existing directed route over 3 s / 250 ms segments, including conservative rotation expansion and source age. Predicted contact <=1 s triggers existing immediate emergency arbitration. Missing geometry/speed or horizon ends are not extrapolated. |
| Verified full swept envelope / reliable sensor ACC | BLOCKED | Traffic coverage and actor lifetime/error bounds remain unproved; future articulation/lane departure/braking and road-load identification are unavailable. Actual native boxes/time solve acquisition gaps, not these accuracy guarantees. More than three ego trailers disables the body channel. TMP placeholders are not forecast. |

Native actor short IDs originate from the existing pointer allocator. Neither a
short ID nor two samples certifies global actor lifetime. Slot/source/displacement
checks reject ambiguous/reassigned observations; no guessed IDs/deduplication or
empty-road certificate is created. Reset invalidates acquired following. Old DLL
continues its explicit legacy protective behavior and cannot authorize new
producer-qualified clearance/prediction.

## Fixed criteria and paired results

Before tuning: retain Phase 7.2 settled RMS <=1 km/h, overshoot <=2 km/h,
five-second +/-1 km/h settling window within 60 s, steady RMS regression <=0.3
km/h, no added steady pedal reversals, exclusive pedals and same-flush emergency
withdrawal. New seeded-noise criterion is >=20% reduction in p95 model jerk with
those existing speed/safety gates. It failed baseline **0.46123 <= 0.8*0.46123**.
No thresholds were changed after candidate evaluation.

The same 12 seeded 130 s plant cases use existing 2.2 m/s² drive, 4.0 brake,
0.35 s actuator response, 0.12 s delay (0.25 jitter), declared grade/load and
real integration intervals. Acceleration/jerk below are model quantities.

| Case | Steady RMS km/h, before -> after | p95 model jerk m/s³, before -> after | Settling s, before -> after |
| --- | --- | --- | --- |
| Launch | ~0 -> ~0 | 0.1242 -> 0.1242 | 9.25 -> 9.25 |
| Steady noise | 0.0704 -> 0.0339 | 0.4612 -> 0.2508 | 3.95 -> 3.30 |
| Target down/up | ~0 -> ~0 | 0.5963 -> 0.5919 | 4.80 -> 4.80 |
| Curve cap | ~0 -> ~0 | 0.5578 -> 0.5536 | 6.15 -> 6.20 |
| ACC ordinary slowdown | ~0 -> ~0 | 0.5282 -> 0.5102 | 3.65 -> 3.70 |
| Heavy uphill | ~0 -> ~0 | 0.0685 -> 0.0685 | 13.85 -> 13.85 |
| Light downhill | ~0 -> ~0 | 0.0037 -> 0.0050 | 1.70 -> 1.70 |
| Braking downhill | ~0 -> ~0 | 0.0124 -> 0.0123 | 0.05 -> 0.05 |
| Load change | ~0 -> ~0 | 0.0392 -> 0.0380 | 2.20 -> 2.20 |
| Jitter/delay | 0.1576 -> 0.0411 | 0.8433 -> 0.3570 | 14.55 -> 12.11 |
| Eco | ~0 -> ~0 | 0.1267 -> 0.1259 | 9.30 -> 9.30 |
| Emergency | ~0 -> ~0 | 0.4746 -> 0.4707 | 21.00 -> 21.05 |

All 12 cases have zero steady pedal reversals; emergency reaction remains **0 s**.
Light-downhill jerk increases by 0.0013 m/s³: improvement is not universal. This
does not violate the existing speed/safety gates or suggest calibrated game comfort.
Sixteen steering benchmark case reports are **exactly identical** to `b11777d`.

Same-seed 70 s following cases with the frozen original selector/ACC/Engine versus
source-timed candidate (`tools/compare_oct14_completion.py`):

| Case | Minimum reference gap m, before -> after | Steady speed RMS km/h, before -> after |
| --- | --- | --- |
| Slower straight | 32.000002 -> 32.000002 | 0.000061 -> 0.000061 |
| Slower left/right | 31.999988 -> 31.999988 | 0.000061 -> 0.000061 |
| Roundabout | 32.000009 -> 32.000009 | 0.000061 -> 0.000061 |
| Braking lead | 22.000192 -> 22.000225 | 0.004522 -> 0.005339 |
| Cut-in | 18.373476 -> 18.373415 | 0.004104 -> 0.004097 |
| Jitter/heavy | 32.302797 -> 32.188792 | 0.518429 -> 0.523624 |

No model reference collision; target switch count and immediate emergency guards
remain. Cut-in minimum TTC **5.811605 -> 5.811577 s**, a tiny regression recorded
rather than hidden. Jitter gap decreases **0.114 m** while keeping the existing
speed criterion. These are reference-point quantities, not physical bumper safety.
The integration tests separately measure actual Controller channel writes.

## Native interface, performance and evidence

Traffic v1 mapping `Local\\UltraPilotTrafficV1` is **8928 bytes**, odd/even seqlock
with tail sequence, schema/magic/size checks, original QPC time/lifecycle/render
frame, atomic legacy traffic payloads, four ego bodies, world anchor and per-frame
SCS speed/time. Paused/configuration/shutdown invalidate; repeated frame cannot
republish as new. Reader rejects future/stale/torn/regressing/reused-generation
changed payload; stale new sidecar does not downgrade to legacy. Source motion
retains **two frames / at most 80 actors each**, stop owners **at most 16**, body
model **13 time samples / four bodies / 80 actors**. No unbounded worker or queue.
Existing journal detail **64 KiB** and 30 s history **1 MiB** limits are unchanged.
New codec fields are literal extensions; old numeric field tables stay unchanged.

Compiled C++ probe verifies original QPC domain, same bytes/generation for repeat,
new frame increment, lifecycle reset, pause invalidation and body-channel rejection
when the current SCS speed callback is missing. Candidate loads/unloads telemetry
entry points; game pattern scan/init is deliberately NOT run. Build used the
pinned hash-checked source and MSVC 17.14.41 toolchain; its inherited wchar/char
warning is recorded, not treated as a new ABI failure. Build receipt includes every
compiled source hash, schema and DLL hash. Installed equivalence is NOT CLAIMED.

Isolated body prediction: **200 samples**, 40 actors / two ego bodies:
p50 **1.890 ms**, p95 **2.311 ms**, p99 **2.750 ms**, max **3.148 ms**.
This is added operation cost, not whole packet cadence. Three paired legacy-path
pipeline runs of 180 ticks (same actual Policy/ACC/AP/Engine/Controller, copied IPC):

| Run | p50 ms before -> after | p95 ms before -> after | p99 ms before -> after | max ms before -> after |
| --- | --- | --- | --- | --- |
| 1 | 9.218 -> 9.426 | 10.198 -> 12.522 | 14.878 -> 14.015 | 25.000 -> 20.036 |
| 2 | 9.406 -> 9.114 | 13.866 -> 10.286 | 16.221 -> 11.697 | 23.483 -> 23.280 |
| 3 | 9.300 -> 9.222 | 11.944 -> 12.874 | 15.446 -> 13.503 | 20.034 -> 20.840 |

Physical mappings and shared-state IPC read counts match in all three legacy
cases. Native sidecar replaces the old two-buffer capture with one coherent
producer acquisition; no extra SCS read is added by Python. Operation timing has
run-to-run variation and is not a live scheduling claim. Journal detail stays
<=65536 bytes; retained 9 s history about **99.6 KiB** remains below 1 MiB.
Reader retains one 8928-byte last wire image plus current bounded capture/history;
test mock histories are cleared from the pipeline memory measurement.

New native whole-path run: **180 ticks / 40 actors / two ego bodies**, 6 s modeled,
Map -> atomic native bytes -> Policy -> ACC -> AP -> Engine -> Controller:
p50 **9.910 ms**, p95 **10.716 ms**, p99 **14.506 ms**, max **17.352 ms**.
Retained two-frame actor-motion history is **100894 bytes** by recursive unique
object size (not RSS); detail journal **63062 / 65536 bytes**, rolling history
**48581 / 1048576 bytes**. The synthetic fixture includes publication/geometry
work and clears its assertion histories; this is operation latency, not a
measurement of real process scheduling, games or every maximum 80-actor topology.

## Verification and candidate package

Frozen production before: **7 failures / 15 passes** in the initial 22 new
scenarios; paired noisy model criterion also fails on baseline. Candidate new
scenarios pass, including observed-original stop clearance, actual native-box
emergency writes, source-time/repeat faults and original times surviving the
existing integrity export. Original safety expectations are not removed.

**Prior candidate full pytest: PASS — 2536 passed, 1592 subtests passed in 565.89 s
(9:25), 2026-10-14.** Final log:
`docs/steering-audit/oct14-completion/full-suite-final.log`.
All 29 newly added cases are included in that complete run; the earlier
2507-test result is not substituted for this candidate. Final `compileall` and
`git diff --check` also pass.

The first new full run found **35 failures / 2498 passes / 1592 subtests**:
34 shared one new adapter bug (`source` metadata was shadowed by the legacy
moving/parked loop label), and one read the release changelog before its new
ACC entry existed. The variable collision was repaired at the producer; tests
and original export expectations were unchanged. **185 targeted/new/export
regressions passed** afterward. Failed first-run output is preserved separately
as `full-suite-first.log`; the final complete run is not replaced with that result.
`compileall` and `git diff --check` pass; the runtime package is gated by the
final whole-suite PASS, checked before ZIP creation.

Runtime candidate contains only coherent application files and the optional new
native DLL; exact file hashes/build identity are listed in its manifest. The
manifest is a preparation receipt, never a deployment receipt. Source Python
depends on the new native sidecar for the new qualified mechanisms; deploying
only Python retains legacy limitations. No tests, reports, logs, settings or map
caches are runtime payload. The existing DrivePolicy 1.1.4 startup repair is
included because the installed version is older. No commit marker is rewritten.

Prepared/ZIP-readback-verified candidate:
`docs/steering-audit/oct14-completion/ultrapilot-oct14-candidate.zip`.
**Superseded by the follow-up working tree below; do not deploy this older ZIP
as if it contained the review fixes.** Its original bytes/receipt are preserved.
SHA-256: `600641742dc0f54f1158e430c4ff106539b5c6ac54071536692612cd02e7e5e3`.
Manifest: `ultrapilot-oct14-candidate.manifest.json` in the same directory.
**15 runtime payload files**, plus preparation manifest and native MIT/FMT legal
notices; every payload is rehashed after reading it from the ZIP. Native DLL
SHA-256: `ebe8af192bcd7c0955075d2869882d8c82804e855ba25a6b43fb47d8c7542bdb`.
All 24 existing installed receipt hashes were checked again immediately before
packaging. The candidate manifest binds that base receipt, exact source HEAD
`b11777d8285fb5e90557a223fd4640c38accd0a8`, uncommitted content, final test-log
hash and native source/build hashes. It does not modify the base receipt.

Exact runtime payload (relative to the application root, except the last game copy):

- `core/acc_acceleration.py` (preserved prior nominal mapping dependency)
- `core/acc_body_prediction.py`
- `core/acc_following.py`
- `core/engine.py`
- `core/longitudinal.py`
- `core/pid.py`
- `core/service_brake_hold.py`
- `core/navigation/traffic_producer.py`
- `core/navigation/longitudinal_diagnostics.py`
- `core/sdk/traffic_snapshot.py`
- `plugins/acc/main.py`
- `plugins/drivepolicy/main.py` (preserved prior startup repair, 1.1.4)
- `PLUGIN_CHANGELOG.md` (runtime release-dialog metadata)
- `assets/ets2la_plugin.dll`
- the identical `game-plugin/ets2la_plugin.dll` candidate for the previously
  receipt-identified ETS2 `bin/win_x64/plugins` directory.

Tracked additional files are the two new regression modules,
`tools/compare_oct14_completion.py`, `tools/prepare_oct14_runtime.py`, the native
build recipe and Traffic/probe headers/sources under `tools/signal_plugin`, this
report, the prior-report continuation link and `DEFERRED_WORK.md`. Generated
native builds, logs, metrics and ZIP remain ignored audit artifacts. Installation,
original logs/replays, settings, map caches, old checkout and commit marker are
untouched. The prior extra-slew/heuristic-hold-bypass experiments remain REJECTED;
they are not silently reintroduced or relabeled as completed mechanisms.

**OFFLINE VERIFIED** applies only to completed regressions/model/ABI scope;
**GAME NOT VERIFIED** applies to every new mechanism. Arrival after GPS removal,
unattended holding after normal completion, load-calibrated physical mapping and
certified full-body/traffic coverage remain open. No new ride is requested now.
Smallest next work is the producer navigation lifecycle interface identified
above; deployment and any game verification require separate approval.

## October 14 follow-up: endpoint proof, AEB review and passive calibration

The user's proposed computed endpoint is valid in principle as a planning target.
The earlier statement that only a native precise world point could suffice was
too broad. Actual current GPS LanePath does not yet carry that proof:

- Map `_runtime_gps_window` limits the resolved route to 8 km / 768 UIDs.
  `route_horizon_complete` compares that window with the currently exposed SDK
  UID list; it is not a whole-destination completion declaration.
- `road_network` resolves directed lane centerlines between those nodes;
  `lane_trajectory.validate` preserves the last source centerline point. Neither
  crops the terminal road to the exact in-road user waypoint.
- The new production Map regression uses the same full UID window and identical
  pose with positive GPS remainders of 100 m and 200 m. Both modes produce the
  **same computed endpoint**, while the existing destination profile consumes
  different original live remainders. Hence that endpoint does not uniquely
  encode the user goal. This is an explicit synthetic contract counterexample,
  not an invented endpoint from the historical 137.646 m clearing frame.
- The native route publication is count-only and supplies node remainders, not
  a removal cause. A computed target still needs independent whole-route/goal
  identity and removal semantics. Positive-distance stopping remains supported;
  disappearance is not reclassified as successful arrival. No guessed point,
  cached distance renewal, new drive authority or stationary brake edge is added.

### Review fixes with failing-before production evidence

| Issue | Before | After / scope |
| --- | --- | --- |
| Native parked actors omitted from the new body AEB | Real reader/Engine/Policy/ACC/AP/Controller scenario in both modes yields body brake 0 despite measured trailer-box conflict | Parked classification supplies an explicit static protective model; physical output is throttle 0 / emergency brake 1. No measured parked speed or clearance is invented. |
| Existing overlap depends on future route samples | A valid one-metre remaining reference has fewer than two future poses; an already-overlapping observed body yields brake 0 | Check original same-frame oriented-box overlap independently of future segment availability; contact basis is exported. No reference extrapolation. |
| Incomplete stop owners inherit old qualification | Add 17 actual crossing candidates after an admitted one-owner stop: the unqualified new basis still leaves only a qualified `traffic` cause | New unqualified cause is independently latched; overflow/reset incompleteness cannot recover merely because a later list is smaller. Both real transmission flows retain zero propulsion. |
| Missing pedal/load response in the existing diagnostic path | SDK -> normalize -> original codec regression raises `KeyError: gameThrottle` | Decode optional response/load fields from the same copied SDK image, transport them with the exact paired frame and retain them in the existing detail/history. No control decision or extra SDK/IPC read. |

An initial ownership fixture accidentally exercised immediate emergency rather
than planned crossing hold; it was corrected to the existing non-emergency
crossing geometry, preserving emergency precedence. No safety expectation was
removed. Supported traffic restart is now displayed separately from its pending
clearance blocker; incomplete/unknown causes remain unsupported.

### Load calibration: concrete implementation and remaining gate

`tools/analyze_actuator_calibration.py` consumes integrity-checked existing replay
history. It never controls the game, changes gains or creates a collector. New
optional fields use the official [RenCloud revision-12 layout](https://github.com/RenCloud/scs-sdk-plugin/blob/master/scs-telemetry/inc/scs-telemetry-common.hpp):
game throttle/brake 976/980, user throttle/brake 960/964, cargo mass 748, unit mass
944, retarder step 108, motor-brake flag 1567 and chassis pitch 2232 (turns -> rad).
Unsupported revisions/nonfinite/out-of-range values stay unavailable. Cargo/unit
mass is not inferred total mass; chassis pitch is not measured road grade.

The offline estimator groups original observations by authority, activation,
gear, cargo/unit mass, 5 m/s speed bin and 0.01-rad pitch bin. It requires exclusive
SDK/backend pedal agreement within 0.02, no observed manual input/retarder/motor
brake, the previous bound successful write preceding the subsequent observation,
fresh command/frame/lease and no unresolved intervening pedal pulse, original frame
advancement, dt 50–250 ms and a 700 ms pedal plateau. At least 30 intervals / 8 s
and full-rank excitation are required. Weighted least squares uses interval dt
to fit `a = drive_gain*T - brake_gain*B + drift`; speed finite differences supply
observed/model acceleration, not a made-up native acceleration channel. The
drift includes grade/drag and is not labeled a measured slope.

Explicit model response tests recover drive/brake gains **2.2/4.0** and **1.2/3.0
m/s² per full pedal**, with drift **-0.1 m/s²**, in their qualified operating bins.
Missing fields, unknown ABI, human/retarder intervention, an unreturned prior
write, expired/foreign-frame command, hidden pedal transitions and rank-deficient
input cannot produce a calibrated gain. This is
**IMPLEMENTED passive identification / BLOCKED automatic mapper application**:
operating-domain validation and real response evidence are absent. It is not
safe to install a global mass multiplier from these two synthetic plants.

The existing Oct 13 pedal export `20261013T175621.766498Z` is integrity-checked:
**310 retained history rows, 310 unqualified, 0 fit rows / NOT MEASURED**. All six
completed exports were checked: history row counts 310 / 0 / 228 / 0 / 291 / 0,
all NOT MEASURED for response/load identification. Original
SDK pedal/load channels are absent there. No zero filling or retroactive data
repair is performed. Result is `load-evidence-followup.json` in the ignored audit
directory. Future existing automatic exports can retain the new fields without
arming; no new game attempt is requested in this task. The 64 KiB detail and
1 MiB history budgets and append-only codec indices are unchanged.

### Current verification and packaging gate

Initial AEB reproduction: **3 failed / 4 passed**; missing SDK response reproduction:
**1 failed**; non-emergency ownership reproduction: **2 failed**. Follow-up module:
**25 passed** after fixes, including both transmission variants and calibration
rejection cases. Related existing integration/native/export checks: **144 passed**
before the final additions. The earlier 2536-case PASS remains evidence for the
earlier candidate, not the new runtime.

`tools/verify_oct14_candidate.py` runs the explicitly user-authorized complete
suite and records before/after SHA-256 for every runtime payload. Packaging now
requires that receipt, its exact PASS log hash and unchanged current runtime
hashes. A stale successful log alone cannot approve a changed candidate. The
new runtime additionally needs `core/sdk/scs_sdk.py` and `core/telemetry.py`;
the native DLL remains the same hash-checked 1.59.4 candidate (no rebuild/deployment
is needed for these Python review fixes). No plugin implementation changed after
the already prepared ACC 1.3.0 / DrivePolicy 1.1.4 candidate, so another arbitrary
plugin version bump is not applied for coordinated core/tests/tools changes.

Final follow-up verification: **2561 passed, 1592 subtests passed in 580.21 s
(9:40)**, `full-suite-completion-v2.log`, with matching
`full-suite-completion-v2.verified.json` before/after runtime hashes. This run
includes the final preceding-write analytical pairing, three added expiry/frame/
hidden-pulse rejection cases, and all unchanged original safety/export tests.
The intermediate 2558-case runtime PASS predates those analytical additions and
is preserved as `full-suite-followup.log`; it is not substituted for the final run.
`compileall core plugins tools tests` and `git diff --check`: PASS.

All **16 steering** and **12 comfort** case reports exactly match the prior
candidate's numerical results. Repeated following gap/TTC/error results match
the earlier native paired benchmark, including its recorded tiny regressions;
they are not repackaged as improved bumper safety.

Performance review (same 40 actors / two ego bodies, no concurrent pytest):

| Measurement | p50 ms | p95 ms | p99 ms | Maximum ms |
| --- | --- | --- | --- | --- |
| Initial reviewed whole-path run, 180 ticks | 10.566 | 11.234 | 22.815 | **93.236** |
| Instrumented repeat 1, 180 ticks | 10.931 | 11.924 | 16.366 | 19.468 |
| Instrumented repeat 2, 180 ticks | 10.748 | 11.668 | 13.957 | 20.905 |
| Instrumented repeat 3, 180 ticks | 10.643 | 11.427 | 12.218 | 21.047 |

The 93 ms maximum is retained as unexplained, not hidden behind warm medians or
declared solved by GC. Tracked repeat tails overlap GC in Engine (~8.5–10.1 ms)
and Map (~6.2 ms). Full 50–58 ms collections also occur in fixture teardown,
outside timed control iterations. These observations do not identify the earlier
93 ms pause or any historical game pause. Windows `thread_time` quantizes to
15.625 ms here, so per-phase sub-millisecond CPU/wait separation is NOT VERIFIED;
wall-minus-CPU cannot honestly be labeled IPC waiting. Existing real game packet
cadence/freshness still requires the approved future runtime measurement.

Three exact ZIP-frozen prior-body comparisons on 200 same-input calls each:
median **1.826 -> 2.012**, **1.807 -> 2.016**, **1.814 -> 2.056 ms**.
The new overlap check costs about **0.19–0.24 ms** in this body-heavy case;
maxima before **2.16–3.34 ms**, after **2.78–3.72 ms**. This is a justified extra
protective check, not a packet-refresh optimization. Copied SDK decode (500
samples each): median **0.0224 -> 0.0262 ms**, max **0.0487 -> 0.0615 ms**,
original control fields equal and **zero additional live acquisitions**.
Whole-path retained motion state **100894 bytes**, detail **63823 / 65536 bytes**,
history **48604 / 1048576 bytes** for the six-second explicit fixture. Actual
budget limits, drop reporting and the existing collector remain unchanged.
Raw profile artifact: `profile_followup.json`; it is ignored, not deployed.

Current prepared candidate:
`docs/steering-audit/oct14-completion/ultrapilot-oct14-candidate-v2.zip`.
SHA-256 **5014edfc3499fface84a1f280f5585d2cd25586e1d271a3db53e5c9f6df13fe7**.
**17 runtime files**: the prior coherent list plus `core/sdk/scs_sdk.py` and
`core/telemetry.py`. The same native DLL appears twice for the two existing
installation destinations; its exact hash is unchanged. All ZIP payloads passed
readback SHA verification; all 24 installed base-receipt hashes still match.
The preparation manifest binds the final full-suite log and exact runtime bytes.
It is not a deployment receipt. Reports/tests/calibration tools/profiling logs
are not runtime payload. No file in either installation was changed.

**Final boundary: OFFLINE VERIFIED for the implemented AEB/ownership/evidence
changes and modeled identification; GAME NOT VERIFIED.** Arrival after ambiguous
GPS disappearance and automatic calibrated load-mapper application remain OPEN.
Protective AEB is implemented for qualified measured boxes; complete coverage,
future articulation and collision-free behavior are not certified. There is no
new game request, deployment, automatic gain application or false whole-task
completion claim.
