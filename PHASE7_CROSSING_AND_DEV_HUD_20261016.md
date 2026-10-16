# Crossing qualification, ACC brake ownership and the classic 3-D DEV HUD

Incident: **15 October 2026, 20:36:02 Europe/Bratislava**. Implementation/review:
16 October. **Not deployed; GAME NOT VERIFIED.** Final complete-suite result
and candidate identity are recorded in the verification section below.

## Scope and source identity

The starting working tree was clean at
`20b51c23c10fe0b56976716fbf5027f9da5dfea7`. The previous bounded-refresh protocol,
geometry/topology caches, continuous service brake, 5 m signal reference offset,
green release, departure handling and steering controller are preserved.

Read-only verification checked **all 31 installed receipt hashes**, including
both native DLL locations. All recorded Python/content dependencies matched the
starting source after LF/CRLF normalization. The installed native binary is the
receipt-bound **1.59.4-up-traffic-timed** candidate, SHA-256
`ebe8af192bcd7c0955075d2869882d8c82804e855ba25a6b43fb47d8c7542bdb`;
the raw repository DLL is a different historical asset and is not shipped here.
The installed receipt identifies source `20b51c2`, ACC 1.3.2, DrivePolicy 1.1.4,
Autopilot 1.3.4 and Map 1.1.2. No installation files were changed.

Evidence in the installed `route-diagnostics` directory:

| File | SHA-256 | Result |
| --- | --- | --- |
| `steering-replay-20261015T183602.361472Z-automatic_disable.json` | `48fbc3fe3b2a622cf01dac68dec83da4030dc0bb2e41096c2140394a2f292d26` | Valid integrity; incomplete bounded pedal incident |
| `steering-replay-20261015T183603.361416Z-automatic_disable.json` | `27e0c379e3f14cb378eeadb2e8c4850d130222ba1fc05e0acc724856d68903f4` | Valid dense-replay integrity; 1,431 samples |

Decoded using `core.steering_replay.inspect_replay`, including immutable journal
references. This does not certify correct historical attribution of unrelated
dense headers. The pedal detail retains six calls over **0.0825964 s**, after
**2,356** detail evictions. Its 30.013261 s decision history has **1,072 capture
failures** and is explicitly incomplete; neither missing values nor the
original rejected ACC branch are reconstructed as measured facts.

## What the historical incident proves

The first rejection was in Autopilot, not Engine expiry:

| Field | Exact recorded value |
| --- | --- |
| Reason | `acc: invalid longitudinal observation` |
| Rejected ACC SDK frame | 218424596 |
| Original observation | 5944.9819827 s |
| Calculation | 5945.0055096 s |
| Check | 5945.0187319 s |
| Observation / decision age | 36.7492 / 13.2223 ms |
| Remaining original lease | 463.2508 ms |
| Validity / identity differences | `false` / none |

The fault record subsequently observes SDK **218441262**, observation
5945.0175661 s. That newer vehicle observation is not substituted for the one
used in the failed ACC comparison. The full rejected ACC packet, including
`speed_control_reason`, is absent. **The exact historical reset branch remains
NOT VERIFIED.** This is not the earlier lease-expiration incident.

The history does preserve a specific crossing cap:

| Field | Recorded ID 83 value |
| --- | --- |
| Native source / slot | moving / 3 |
| Position XYZ | 34869.390625, 8.362007141113281, 45279.30078125 m |
| Yaw / speed | -3.004309609742633 rad / 6.520343780517578 m/s |
| Width, height, length | 1.856012225151062, 1.515342354774475, 4.688936710357666 m |
| Record fingerprint | `ec0896f0695991f9482ebd50163c728b7a1dfa55c8956e2fc6c6f971eec69094` |
| Native generation / frame / observation | 7297 / 291487739 / 5944.7521877 s |
| Traffic SDK frame / observation | 218157940 / 5944.7326679 s |
| Directed reference progress / distance | 654.9335090064556 / 56.59196661269402 m |
| Ego / actor extrapolated arrival | 7.430459760306165 / 7.972528745913883 s |
| Crossing selector brake | **0.0** |
| Contact time / contact basis | unavailable / unavailable |
| Promoted speed cap | **19.718281932414417 km/h** |

The cap is reproduced exactly by the old production formula:
`3.6 * 56.5919666 / (7.97252875 + 2 + 4.68893671/(2*6.52034378))`.
At history time **5944.8700593**, ACC requested brake 0.35 and the recorded
successful brake value was 0.1264835; at **5945.0035979**, the recorded brake
was 0.3489355. Another limiting actor was ID 54.

The native producer uses a pointer-to-short UID table, not a vehicle model ID or
actor-incarnation certificate. `get_center_coords` derives the measured AABB
centre from placement and rotated local bounds. The Python reader transports
body quaternions/dimensions and computes yaw; the body SAT and DEV rendering use
the same width axis `(cos(yaw), -sin(yaw))` and forward axis
`(-sin(yaw), -cos(yaw))`. No coordinate correction or DLL change was justified.

The receipt does **not** retain the complete original actor array, exact entire
route occurrence or future actor motion. It cannot establish that ID 83 was on
a side road, turning away, reused or a particular physical car. Extrapolating
its recorded pose yields approximately `(34876.5047, 8.3620, 45330.7953)`; this
is a model intersection, not an observed future position or collision.

A later safety summary preserves **ID 48**, body contact model time 2.865 s and
traffic brake 0.284888. This is a separate genuine model input and is not erased
because ID 83 was incorrectly promoted. It also cannot substitute for the
missing exact rejected ACC input. Null contact for ID 83 is not proof of an
empty road, and the user's observation is not a complete sensor/geometry record.

## Proven code faults and corrections

1. **Passive crossing became an active constraint.** Engine converted every
   broad crossing candidate to a positive speed constraint when the timed
   three-second body prediction reported no contact. This included candidates
   whose own selector demand was exactly zero. A new far-away eight-second
   straight-line possibility could therefore acquire ACC ownership and brake.
   The conversion now requires an actual positive crossing demand, or original
   continuously observed ownership of an already acquired crossing constraint.
   Potential crossings remain visible as diagnostic possibilities. Existing
   acquired protection, positive-urgency crossings, body overlap, swept contact,
   incomplete/legacy fallback and emergency demands remain effective. No new
   clearance certificate, prediction horizon or timeout is introduced.
2. **A stronger brake was mistaken for lost evidence.** Engine correctly removes
   a positive-motion speed scope when a stronger actual traffic/body brake must
   take over. ACC interpreted the absent scope as a missing acquired target,
   published a fresh invalid zero packet, and the final Engine guard independently
   made the same mistake. A shared `observed_braking_continuation` contract now
   recognizes the original target only when the same native lifecycle/ID/source/
   slot/body count and bounded motion are observed across consecutive acquisitions,
   with a current positive traffic brake and the original fresh source time.
   This only permits **continued braking**, never departure/clearance or old drive.
   Missing, reassigned, discontinuous, stale and foreign inputs still reject.
3. **Producer cause was lost.** ACC now identifies invalid control intervals,
   malformed/reverse observations and existing producer-reset reasons. Packet
   qualification records `invalid_reason`; the first compact rejection and
   existing automatic incident retain it ahead of optional large detail.
   The generic safety rejection remains in force. The existing 8/16/64 KiB
   diagnostic budgets and historical codec key/mask tables are unchanged.
   The complete-suite review caught a real export regression: two absent
   extension keys consumed enough conservative accounting space to erase an
   existing long-identity deadline receipt. Absent extensions are now omitted;
   populated producer causes first use the existing lossless bounded codec,
   before any optional-detail reduction. The original long-identity assertion
   and an additional populated-cause/deadline integration check both pass.

The first two production reproductions failed in both automatic modes before
the changes: **four failures** in `before.log`. Afterward the same scenarios
continue through actual Map, native timed TrafficCapture/reader, selector,
DrivePolicy/ACC, Autopilot, Engine, Controller and the memory-mapped test backend.
The stronger brake physically withdraws drive and applies service braking without
a false technical stop. The passive crossing no longer creates that cap/brake.
These are offline code counterexamples; fault 2 is not presented as the uniquely
identified reset branch of the incomplete historical recording.

| Same production-flow reproduction, both modes | Before | After |
| --- | --- | --- |
| New passive crossing at 60 m, 7.97 s extrapolated arrival | Acquires a 21.103 km/h cap despite zero crossing and body demand | No acquired cap, ACC brake zero, physical brake zero, authority continues |
| Acquired crossing followed by a stronger actual body brake | Fresh invalid ACC packet and false technical stop | ACC stays valid; physical throttle zero and positive service brake; authority continues |
| Existing full-identity deadline receipt after diagnostic extensions | `deadline_basis` lost to budget marker | Exact original deadline, identity and vehicle fields retained within unchanged limit |

The first synthetic crossing is not the exact historical geometry; the
historical 19.718 km/h value is independently reconstructed above. No missing
historical physical writes are filled from the model.

## Classic 3-D developer HUD

On **Visualization**, select **DEV traffic**. It is default-off and session-local.
No arming, extra collector or game action is required. The ordinary HUD remains
unchanged when off. When on, the exact existing perspective renderer continues
to draw the road network, selected route, ego truck and camera orbit. Developer
geometry overlays that scene; it is not a separate top-down replacement.

The Engine copies already decoded native actor bodies and the actual local
reference. The existing body predictor optionally exposes the very ego samples
and actor positions it evaluates, including its early termination/unsupported
cases. The crossing selector exposes its actual reference intersection. There
is no second predictor or guessed turning intent. Observed two-acquisition
history is dashed, extrapolation is labelled by model/time, and absent paths are
unavailable rather than fabricated. Native boxes are occupancy geometry, not
an exact visual vehicle/model or physical road-edge survey.

The panel retains original native lifecycle/generation/frame/time, consumed SDK
frame/time, activation/session/route identity, selected ACC/other limiting IDs,
source/reason, desired/capped speed, defined reference gap/contact time, actual
backend pair/write sequence/status, refresh and first fault. Unknown values use
`?`, never a manufactured zero. Reference-point gaps are not bumper gaps; parked
classification is a static model, not a measured speed. Backend return does not
prove game consumption or tie a subsequent SDK response to the same row's write.

| Colour | Meaning and required attribution |
| --- | --- |
| Gray | Fresh detection, no consumed intervention attributed |
| Blue | Current ACC target, no attributed physical braking |
| Yellow | Actually consumed protective positive speed constraint |
| Orange | Actual selected service brake, exact consumed owner/acquisition and a successful positive brake-channel write in this decision |
| Red | Actual selected emergency/AEB cause with that same physical-write evidence |
| Muted/dashed | Old/invalid data or retired activation/route; not a current fact |

Priority is invalid/retired → red → orange → yellow → blue → gray. Full source,
slot and record fingerprint must match the consumed acquisition; equal ID alone
does not bind old geometry to a new record. Changed route/activation or disabled
authority mutes old control attribution. Missing exact geometry is explicitly
`CONSUMED_GEOMETRY_UNAVAILABLE`. A throttle-only write cannot colour an object
as the cause of a successfully written brake.
Fresh detection without a matched consumed native acquisition stays gray; it
does not inherit the unmatched decision's brake colour. Stale source data and
unverified current control are labelled separately. An absent fault receipt is
shown as **not captured**, rather than asserting that no fault occurred.

Capture/output sampling and publication are at most **10 Hz**. Fixed limits:
two owned frames, **192 KiB accounted/frame**, **64 KiB accounted output receipt**,
80 actors, four bodies/actor, 64 sampled body paths, 64 crossing markers and 256
local reference points. Optional predictions are omitted before priority actor
identity/pose on budget exhaustion; remaining loss is explicit. One in-flight
presentation RPC, no pending queue, one reusable display worker across toggles;
off stops geometry/path work. Runtime source objects are owned snapshots, not
mutable shared-slot references. Control-tick sensor/traffic reads are unchanged;
presentation flag/snapshot RPCs are classified separately. No synchronous disk
I/O or per-tick INFO logging is added.

The feed's two frames/receipt, one in-flight reference snapshot and the one IPC
display slot are all bounded. Accounted codec budgets are not exact allocator or
cross-process RSS limits. Raw fixture mock histories are excluded from measured
retained runtime memory below. The preview canvas is a reusable 2,860,000-byte
QImage, not a growing image queue.

## Criteria, verification and performance

Criteria follow the existing selector urgency/owner and safety contracts, rather
than introducing a new numerical collision or comfort threshold: a new passive
zero-demand crossing cannot actuate; actual stronger braking cannot manufacture
loss of a continuously observed owner; invalid data remain rejected; no positive
pedal overlap; DEV mode must not change controls or sensor/producer reads.

Targeted results before the final complete suite:

- **60 new cases** pass, including both modes, passive/active crossings,
  stronger-brake transition, missing/slot-reused/teleported/lifecycle/stale owners,
  all reproduced invalid ACC branches, identity changes during publication,
  first-cause automatic export, exact rendered box axes, actual ACC/AEB colours,
  old route/activation, failed writes and throttle-only non-attribution.
- The older two-owner fixture included a **zero-demand** second crossing
  (`x=-25`, arrival 5.45 s). Its expectation that this object acquired a new cap
  contradicts the corrected passive-crossing contract. All original two-owner
  and lost-original-owner assertions are retained: the second fixture now has
  actual positive urgency (`x=-21.5`, arrival 4.75 s, demand 0.00390625), with an
  additional assertion that both demands are positive. A separate new regression
  preserves the **original geometry** and verifies that only the active ID 42
  acquires a cap, while passive ID 43 does not inherit its demand. No timeout,
  threshold or safety assertion was weakened.
- Final combined new/handoff/roundabout regression selection: **126 passed** in
  15.76 s. The two final display-qualification cases independently reproduce a
  fresh unmatched detection incorrectly called invalid (1 failed / 1 passed
  before correction); they pass after correction. They cannot acquire any brake
  colour without exact consumed geometry. These are presentation-only checks.
- Final targeted new/regression selection: **92 passed** in 4.44 s, including
  the unchanged full-identity deadline assertion from the existing handoff suite.
- Existing production/native/diagnostic regression selection: **180 passed**.
  Refresh/signal/classic-HUD selection: **146 passed**. These overlap and are not
  added as a unique test count. Earlier supporting selection: 198 passed.
- All **16 steering** and **12 ordinary longitudinal comfort** benchmark case
  results are numerically identical to `20b51c2`. The historical crossing-cap
  correction is an intentional constraint-selection change, not retuned PID or
  steering. Emergency/body predictor numeric output is identical with/without
  its passive geometry capture.

Warm actual pipeline, nine native actors, 500 measured ticks/mode/configuration
after 25 warmup ticks; same poses and real production operations, synthetic SDK:

| Mode / DEV | Wall p50 / p95 / p99 / max, ms | Retained display snapshot |
| --- | --- | --- |
| Simple / off | 7.626 / 8.296 / 8.983 / 11.039 | none |
| Simple / on | 8.060 / 9.867 / 10.480 / 15.993 | 66,227 bytes |
| Real / off | 7.271 / 8.058 / 8.739 / 15.298 | none |
| Real / on | 7.688 / 9.672 / 10.687 / 12.338 | 66,227 bytes |

On/off physical-output hashes and non-presentation read counts are identical,
with no faults. Median incremental pipeline cost was approximately **0.434 ms**
and **0.417 ms**; tails are reported rather than hidden. Independent Windows
thread-CPU readings have 15.625 ms granularity here and cannot resolve these
small increments. GC is recorded separately; no historical pause is attributed
to it. These are wall-time harness measurements, not game latency/physics.

Actual classic 3-D QPainter, 25 warmup + 200 measured renders/configuration:

| DEV | p50 / p95 / p99 / max, ms |
| --- | --- |
| Off | 10.309 / 10.855 / 11.168 / 11.403 |
| On | 12.404 / 13.109 / 13.357 / 15.063 |

Median incremental rendering: **2.095 ms**, separate from the control pipeline.
The synthetic rendered snapshot occupied 46,253 deep Python bytes. Real scenes,
hardware, source gaps and crowded labels can differ. Limits remain fixed.
Live/stale previews were rendered by the real classic HUD and visually inspected;
they are explicitly **TEST DATA**, not an ETS2 screenshot or game verification.

Final timings are in `overhead-final-v3.json`; earlier repeated runs remain
preserved and are not silently substituted for the final numbers. The production
pipeline uses fixture IPC and synthetic SDK observations. A separate **real
Manager IPC** probe (`--ipc-only`, `ipc-final.json`) therefore tests transport
under the optional display load: two scalar/telemetry gets per nominal 50 Hz
probe, nominal 60 Hz display reads, at most 10 Hz publication, 9,953-byte pickled
test snapshot. Each probe row contains 150 measured samples after 10 warmups;
the enabled run received 134 nonempty display reads. It is not an end-to-end
control or producer-freshness measurement.

| Real Manager operation | p50 / p95 / p99 / max, ms |
| --- | --- |
| Probe, DEV off | 0.251 / 0.338 / 0.373 / 0.398 |
| Probe, DEV on | 0.213 / 0.368 / 0.678 / 0.713 |
| Display snapshot read | 0.451 / 0.558 / 0.618 / 1.127 |

Exact geometry survived serialization, no queued backlog or publication skips
occurred in this bounded probe. This moderate synthetic payload does not prove
the worst-case latency of every 80-actor scene or eliminate OS scheduling stalls.

The first complete-suite attempt was deliberately interrupted after a final
review found the throttle-only colour-attribution gap; it is not a PASS. The
second was stopped after its deadline-receipt failure was independently
reproduced and corrected. Neither partial run is counted as a successful suite.
The third exposed the legacy fixture's passive-owner assumption above; it is
not counted as a PASS either: **2 failed, 2,759 passed, 1,592 subtests passed**
in 681.97 s. Both failures were that fixture in the two automatic modes; no
additional failures were hidden. It preceded the two display-qualification cases.
The final hash-bound complete-suite receipt is
`docs/steering-audit/oct15-crossing-dev-hud/full-suite-v4.verified.json`.
Final result: **2,765 passed, 1,592 subtests passed**, no failures, in **693.09 s**
(11 min 33 s). The receipt has exit code zero and hashes the final log and all
19 runtime payloads before/after the complete run. No runtime content changed
during that successful run or before candidate creation. `compileall` for
`core plugins ui tools tests` and `git diff --check` pass. Git's LF/CRLF notices
are not content or whitespace errors.

| Property / criterion | Verdict | Evidence boundary |
| --- | --- | --- |
| New passive zero-demand crossing cannot acquire drive/brake authority | OFFLINE VERIFIED | Failing baseline in both modes; final native/producer/backend regressions pass |
| Actual stronger braking with continuously observed original target cannot manufacture target loss | OFFLINE VERIFIED | Shared ACC/final-arbiter contract; actual zero throttle and positive test-backend brake |
| Invalid, stale, foreign, reused or missing evidence stays protected | OFFLINE VERIFIED for covered cases | New negative tests and complete existing suite; no timeout/identity guard removed |
| DEV changes no control outputs or sensor-read count | OFFLINE VERIFIED for measured workload | Identical on/off physical-output hashes and non-presentation reads |
| DEV is a classic 3-D road view with attributable geometry | OFFLINE VERIFIED | Actual classic renderer, visually inspected TEST DATA previews; owner/write/transform regressions |
| Exact historical ACC reset branch / ID 83 lane or future intent | NOT VERIFIED | Required original branch/full actor scene absent from bounded record |
| New behavior and display in ETS2 | GAME NOT VERIFIED | No installation or game action performed |

## Prepared candidate, not a deployment

- Path: `docs/steering-audit/oct15-crossing-dev-hud/ultrapilot-oct16-crossing-dev-hud-candidate-v1.zip`.
- SHA-256: `07c3eab2aebb286c8fc9246994e472f2fbaf9eb1f49cf2c1023cc3d5cbf7ae92`.
- Size: **235,077 bytes**; **19 runtime payloads**, plus the candidate manifest.
  Ten payloads differ in content from the installed base, including the new
  display module and changelog; other files are unchanged required dependencies.
- The archive was reopened and every payload SHA-256 checked against its
  manifest. The manifest retains the successful verification receipt, base
  deployment-receipt hash, all 31 required installed hashes, source commit plus
  truthful uncommitted-worktree status, plugin versions and explicit
  `runtime_authorized=false`, `game_verified=false`.
- Existing `oct15-refresh-protocol-v1` is superseded **for future candidate
  review**; its archive, deployed files, receipt and original evidence remain
  untouched. No DLL replacement is included or required for this change.
- No additional pytest repeat is needed for this unchanged candidate. Any later
  runtime modification invalidates its bound verification and requires a newly
  verified candidate. Installation still requires separate user approval and a
  whole-set rollback backup.

## Reproduction, runtime set and remaining limits

Tools: `tools/analyze_oct15_crossing_incident.py`,
`tools/preview_traffic_dev_hud.py`, `tools/benchmark_oct15_crossing_dev_hud.py`,
`tools/prepare_oct16_crossing_hud.py`. Derived raw evidence, benchmark JSON/logs,
previews and candidate ZIP remain outside tracked source under
`docs/steering-audit/oct15-crossing-dev-hud/`.

The candidate preparer verifies the successful full-suite log/hash and unchanged
runtime hashes, rechecks the 31-file installed base, packages exactly the existing
16-file dependency set plus `core/hud.py`, `core/traffic_dev_hud.py` and
`ui/visualization.py`, and rehashes all 19 payloads after ZIP readback. No DLL,
tests, report, temporary data, settings/cache or commit-marker payload is included.

Exact payloads, relative to the installation, applied only as one coherent set:

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

Source changes in this task: `core/acc_body_prediction.py`,
`core/acc_following.py`, `core/engine.py`, `core/longitudinal.py`,
`core/navigation/longitudinal_diagnostics.py`, `plugins/acc/main.py`,
`core/hud.py`, new `core/traffic_dev_hud.py`, `ui/visualization.py`,
new `tests/test_oct15_crossing_dev_hud.py`, the two-owner fixture in
`tests/test_oct14_roundabout_incident.py`, the four tools listed above,
`PLUGIN_CHANGELOG.md`, `DEFERRED_WORK.md` and this report. Other payloads are
unchanged dependencies inherited from the receipt-verified installed base.

ACC is **1.3.3** because its implementation changes. DrivePolicy remains **1.1.4**;
HUD plugin **1.0.2**, Autopilot **1.3.4**, Map **1.1.2**, TurnSignals **1.0.2** and
the native DLL remain unchanged. The developer renderer is a core/UI feature,
not a release of the untouched `plugins/hud/main.py` implementation.

**Remaining historical uncertainty:** the precise rejected ACC reset branch and
the original complete actor/route scene. A proof of foreign-road membership,
pointer incarnation or observed future intent is not recoverable from these
records. The code reproductions repair concrete defects without claiming that
every observed brake was unjustified. Existing actual conflict/traffic-source
loss remains protected. The significant-event quota/original files are preserved.

**GAME NOT VERIFIED:** the new crossing/ownership correction and DEV presentation.
No new drive is requested here. Any deployment requires separate approval and a
rollback backup. A future already-planned controlled check can evaluate this
specific package; successful offline tests do not establish universal reliability.
