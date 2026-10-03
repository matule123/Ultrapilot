# Phase 7.3 — Route-aligned ACC following

Baseline: `9ffd5acba4b4a41fd77ad954cab0eb2aa1df88f8` (Phase 7.2),
2026-10-03. The tracked working tree was clean at entry. Results below apply
to the uncommitted Phase 7.3 changes, not to the installed application.
No game operation, deployment, sensor installation or raw-record alteration.

**Verdict:** PASS for the tested protective offline contracts; reliable live
ACC following is **NOT VERIFIED**. The legacy source cannot establish publisher
freshness, actor lane membership or complete coverage. This implementation
does not turn a projected candidate into a confirmed vehicle/free-road proof.

## Acceptance criteria fixed before implementation

1. Select the nearest unambiguous forward route projection, not the nearest
   Euclidean actor. Reject behind, opposite direction, adjacent centreline
   candidates and observed different heights. Projection does not certify a lane
   boundary, actor LaneId, bumper gap or bridge layer.
2. Determinism under actor-list permutations; retention only within a 2 m gap
   tie, never conceal a nearer cut-in outside that band. Duplicate IDs or
   ambiguous route occurrences cannot be confirmed targets.
3. Reference-point desired gap = 12 m + 2 s * ego speed. ACC speed ceiling is
   nonnegative and cannot increase any existing map/curve/safety ceiling.
   Existing speed PID and pedal arbitration remain sole control owners.
4. Loss of a previously observed target cannot silently restore drive from an
   unavailable, stale or empty/uncovered feed. Original 500 ms leases and route
   identity remain binding; no held old pedal command, stop-and-go or new sensor.
5. Emergency demand reaches the same Engine flush without comfort delay;
   disabling releases pedals and discards target memory.
6. Fixed closed-loop models: no reference-point collision; report minimum gap,
   headway, speed error and switches, including the safety-reaction delay.
   Models are not ETS2 clearance or sensor-coverage evidence.

## Source audit

`ETS2LAData` reads `Local\\ETS2LATraffic` (40 moving actors, three trailer
slots) and `Local\\ETS2LAParkedVehicles` (40 parked actors). The existing
`capture_traffic` double-reads bytes; agreement is receiver read stability,
not atomicity or proof of publisher progress. `LegacyTrafficProducer` explicitly
records no source timestamp, generation, range, coverage or dimension accuracy.
The source has numeric IDs, XYZ, quaternion, speed and acceleration slots;
IDs can be recycled and their lifetime is not documented. Actor LaneId and
elevation-layer identity are absent. XYZ height comparisons are geometric
screening, not bridge-layer certification. Missing dimensions must stay unknown.

Reliable live following remains NOT VERIFIED without publisher freshness and
lane/coverage evidence. Independent protective improvements will not promote
receiver timestamps or projected candidates into confirmed sensor evidence.

| Required data | Actual source / units | Evidence and limitation |
| --- | --- | --- |
| Actor identity | Numeric short ID in moving/parked buffers | Observable ID, undocumented lifetime/reuse; duplicate IDs reject the capture. Not a persistent vehicle identity. |
| Position / heading | World XYZ in metres, quaternion decoded by the existing SDK reader; yaw in radians | Finite/unit-quaternion checks. Publisher precision, chassis reference and uncertainty are not documented. |
| Lead speed | Moving-buffer speed channel, m/s | Retained as a source channel; a parked actor's zero is a classification, not an independent velocity measurement. Missing speed cannot become a measured zero. |
| Acceleration | Raw moving-buffer slot, m/s² according to the existing reader contract | Not used for predictive safety; accuracy and publisher timing are unproven. |
| Distance | Projection onto unchanged directed LanePath, metres | Derived along-route reference-point gap, not measured bumper distance. |
| Lane / direction | Ego's identity-bound LanePath, local tangent and actor heading | Candidate relevance only. Actor LaneId, occupancy of our lane and road-edge clearance are not provided. |
| Height | Actor and LanePath Y, metres | Rejects an observed large height difference; not a certified bridge/deck identifier. |
| Actor body | Raw width/height/length slots | Zero/unknown stays unknown. Legacy display defaults are not body evidence; no new body-clearance claim. |
| Timestamp / validity | Bounded receiver capture with two equal reads | Host monotonic receive time, not publisher time or an atomic snapshot. A frozen publisher can repeatedly yield equal bytes; the tests preserve this limitation. |
| Availability | Missing, changing, invalid, observed and empty states | Empty is explicitly `empty_unproven_coverage`; no documented sensing horizon, range or entry coverage. |

The existing ABI reads 6,960 bytes for 40 moving entries (three trailer slots
per entry) and 1,720 bytes for 40 parked entries. No new parser of game assets
or new traffic producer was introduced. The installed traffic plugin inspected
read-only was:

`C:\Program Files (x86)\Steam\steamapps\common\Euro Truck Simulator 2\bin\win_x64\plugins\ets2la_plugin.dll`

SHA-256: `D07CF70A6F0810E22A028943380641CB1984304F8DD72265B09736CEAD89B61C`.
The adjacent source reference points to `https://gitlab.com/ETS2LA/ets2la_plugin`;
this is not proof that a public checkout built this exact binary. The audit
relies on the locally used reader contract, not a claim of source/binary equivalence.
Existing driving records do not supply the missing publisher generation,
actor LaneId or coverage. No historical replay is presented as proof of these.

## Proven counterexamples and changed production flow

Three narrow tests failed before the production changes:

| Counterexample | Before | After |
| --- | --- | --- |
| Actor 8 m above ego at the same XZ | Legacy lead calculation demanded full brake | Known height difference rejects the actor. This does not certify all elevation layers. |
| Actor without a speed field | Legacy default made it stationary and demanded full brake | No stationary measurement is invented. |
| A previously followed actor disappears | Physical Engine output restored throttle 0.0528 | Invalid ACC demand and last-boundary guard remove positive drive; driver takeover is required. |

Previously the straight cab-relative strip could miss a lead around a curve;
legacy lead braking, DrivePolicy's distance/3 ceiling and ACC speed control
also operated on overlapping interpretations of distance. In the fixed curved
model this produced target absences and repeated emergency interventions.
These are reproducible code/model counterexamples, not a reconstruction of
an unrecorded live traffic incident.

New flow:

1. The existing bounded raw capture feeds `core/acc_following.py`. No display
   dimension fallback, missing yaw or missing velocity is promoted to evidence.
2. Engine caches the unchanged XYZ LanePath under the full longitudinal context:
   activation epoch, game session, map, dataset, intent, revision, build and
   publication token. A new context rebuilds the cache and clears target memory.
3. Local projections use Map's validated progress, tangent and height. Metadata
   is rechecked after projection. The candidate expires at the earlier of the
   receiver capture lease and the original Map observation lease; a new
   calculation never makes an old observation fresh.
4. ACC consumes a speed ceiling using the existing Phase 7.2 speed PID. The
   lower of map, curve, policy, user and following limits wins. DrivePolicy
   omits its duplicate following ceiling only when this route-candidate path
   owns following. Legacy fallback remains when ACC is disabled/unavailable.
5. Original crossing protection remains. The existing Engine emergency
   threshold is preserved using the along-route gap. An emergency bypasses
   comfort pacing and also overrides a latched source-loss condition.
6. The Phase 7.1 paired arbitral command and Engine remain the only final pedal
   owners. The last boundary checks a latest required candidate independently
   of ACC tick order, so an old positive ACC command cannot survive source loss
   between plugin ticks.

No new steering reference, controller, physical limiter, selector pulse or
stop-and-go flow was added. Autopilot, Map, transmission control, geometry,
steering scheduler and the 500 ms limits are unchanged.

## Candidate selection and following contract

| Rule | Value / justification | What it does not prove |
| --- | --- | --- |
| Forward local horizon | 120 m, bounded to at most 512 original edges per projection | Completeness of the sensor or a free horizon |
| Centreline relevance gate | 1.2 m, conservative relevance screening | Usable lane width or physical edge |
| Heading gate | Within 45° of the local directed tangent | Authoritative actor LaneId |
| Height gate | 1.5 m, allowing uncertain origin offsets | Same certified deck in every case |
| Target retention | Within 2 m of the nearest gap; deterministic ID tie breaking | Permission to ignore another hazard: every candidate constrains speed/emergency |
| Ambiguous repeated occurrence | Reject competing near projections separated by more than 8 m progress | A fabricated connector through a loop/crossing |
| Reference-point desired gap | 12 m + 2 s × ego speed | Bumper clearance for unknown vehicle dimensions |
| Speed ceiling | max(0, lead speed + (gap − desired gap)/2 s) | A second pedal controller or calibrated collision prediction |
| Ordinary recovery | Existing Phase 7.2 upward target pacing, 6 km/h/s | Delay of a lower safety limit or emergency |
| Source/route lease | Original 500 ms limit; receiver capture must initially be no more than 100 ms old | Publisher freshness derived from receiver time |

The 12 m stand-off is an explicit reference-point model margin and 2 s a
time-gap design parameter; neither is a measured body bound. They were fixed
before closed-loop comparison and not adjusted to pass its outcomes.
The existing emergency law uses the original safety-gap allowance
`6 + 0.4 * ego_speed` and the original `> 0.7` emergency-demand boundary.
Tests cover both the closing-speed TTC branch and the low-closing-speed branch.

An actor behind ego, opposing the directed tangent, outside the relevance gate
or on an observed different height is excluded. Unknown dimensions do not
become bumper measurements. Missing direction/height, duplicated IDs or
ambiguous route occurrences cannot become confirmed targets.

After a candidate has been observed, loss, stale input, invalid data or an
empty/uncovered buffer latches driver takeover for that activation context.
Merely seeing bytes again does not clear the fault. Disabling discards pending
pedals and target history; a new activation must satisfy the existing gates.
Before any candidate has been observed, optional unavailable traffic preserves
the existing cruise contract, labelled **cruise only / coverage unproven**;
this is not clear-road evidence. At low-speed following (speed below 1 m/s and
ceiling below 1 m/s), takeover is required: automatic stop/restart is not enabled.
An actual verified departure/clear corridor is unavailable in the current feed,
so automatic recovery after target disappearance is deliberately not claimed.

## Same-input closed-loop comparison

Reproducer: `tools/run_acc_following_bench.py`. Baseline classes/PID and lead
law are loaded from `9ffd5ac`; candidate uses the production raw-buffer decoder,
route selector, ACC, Autopilot pedal stages, paired arbitration and Engine
decision. Physical backend writes and activation gates are tested separately.

Plant: `acceleration = (2.2*throttle − 4*brake)/load − 0.12 − 0.004*speed²`,
SI units, actuator response 0.35 s and command transport 0.12 s. Integration
substeps are at most 0.01 s. Previous queued commands evolve the plant before
the next observation/control computation. Seed 7301; nominal tick 50 ms;
jitter case uses 20/50/80/120 ms ticks, speed noise 0.12 km/h and load 1.4.
Initial ego speed 15 m/s, lead speed 10 m/s, reference gap 55 m, requested
speed 70 km/h. Braking lead reaches 5 m/s; the cut-in introduces another actor
at 25 m gap travelling at 6 m/s. Left/right paths use R60, roundabout R35,
cut-in R83, then tangent straight. Exact synthetic XYZ pose is supplied.

Speed-error RMS is `sqrt(mean((ego_speed − relevant_lead_speed)²))`, converted
to km/h. It is not error against the unrestricted user speed. Minimum headway
is reference gap divided by ego speed (positive-speed samples). Steady RMS
uses t ≥ 50 s. No missing datum is replaced by zero. Results are unweighted
sample metrics; the irregular tick case intentionally includes its sampling
distribution. Bodies, road-edge clearance, lateral dynamics, sensor coverage
and real ETS2 acceleration/jerk are not modelled.

| Scenario | Samples / duration, each run | Speed RMS km/h, before → after | Minimum reference gap m, before → after | Minimum headway s, before → after | Target absent samples, before → after |
| --- | --- | --- | --- | --- | --- |
| Slower lead, straight | 1,401 / 70.05 s | 19.221 → 3.423 | 13.108 → 32.000 | 1.244 → 3.200 | 0 → 0 |
| Left R60 | 1,401 / 70.05 s | 20.269 → 3.423 | 6.006 → 32.000 | 0.534 → 3.200 | 280 → 0 |
| Right R60 | 1,401 / 70.05 s | 20.269 → 3.423 | 6.006 → 32.000 | 0.534 → 3.200 | 280 → 0 |
| Roundabout R35 | 1,401 / 70.05 s | 20.518 → 3.423 | 3.648 → 32.000 | 0.338 → 3.200 | 125 → 0 |
| Braking lead | 1,401 / 70.05 s | 16.442 → 3.680 | 10.455 → 22.000 | 1.244 → 3.201 | 0 → 0 |
| Cut-in R83 | 1,401 / 70.05 s | 17.099 → 5.101 | 9.775 → 18.373 | 0.819 → 2.308 | 402 → 0 |
| Jitter / noise / heavy load | 1,053 / 70.04 s | 18.396 → 3.534 | 7.858 → 32.303 | 0.699 → 3.161 | 216 → 0 |

No reference-point collision occurred in either baseline or candidate. After
repair, target switches are zero except the intended cut-in (one, versus two
baseline switches). Steady speed RMS after repair is below 0.005 km/h for the
six nominal cases and 0.518 km/h for the noisy heavy case. Cut-in triggers
21 immediate emergency samples: Engine decision delay is 0 s in model ticks;
the plant still has its explicit 120 ms transport delay. Other candidate
cases need no emergency, so their emergency latency is not measured, not zero.
Perfect synthetic source timing gives zero observation age in the plant;
this is **not a live packet-cadence/freshness benchmark**.

Raw benchmark JSON remains ignored in `docs/steering-audit/`:
`phase73-model-verified.json`, `phase73-speed-preserved.json`, and
`phase73-steering-final.json`.

## Bounded operation cost and unchanged baselines

The cache stores the original points/edge transforms, without resampling or
simplifying geometry. Maximum route size is 20,000 points, actor count 80 and
local scan 512 edges. Unsupported density or ambiguous geometry is rejected.
There is no growing task queue, disk access or raw-geometry serialization on
each traffic sample. Initial route preparation occurs once per context in the
existing slow traffic loop; the critical 60 Hz steering executor is unchanged.

| In-process operation | Measurement |
| --- | --- |
| Prepare 1,801 unchanged points | 4.085 ms, one measured preparation |
| Decode and project 40 actors, 100 samples | median 2.151 ms; p95 3.341 ms; maximum 5.113 ms |

Precomputing edge invariants removed repeated work (earlier measured median
8.729 ms). This is a local-operation result, not a guarantee of whole Engine
cadence, live IPC throughput or game-publisher freshness.

The 16 steering benchmark case results are numerically identical to the
Phase 7.2 benchmark. All 12 existing longitudinal-comfort benchmark case
results are also identical. Original PID gains, geometry, actuator calibration,
emergency thresholds and safety freshness limits were not relaxed.

## Regression verification

| Check | Final result |
| --- | --- |
| ACC following, arbitration, comfort, activation binding, signals, real-incident regressions, engagement safety, simple-auto transitions/handoff and control safety | 347 passed, 17 subtests passed |
| Non-filesystem transmission-mode activation and plugin-version metadata checks | 50 passed, 20 subtests passed; 8 filesystem-dependent cases deselected |
| Same-input following benchmark | Seven cases completed; table above |
| Existing steering and speed benchmarks | 16 and 12 case results unchanged, respectively |
| Compileall for core, plugins, SDK, tools and tests | Passed |
| `git diff --check`, including separate whitespace/newline checks of new files | Passed |
| Full `tests/` suite | Not run; reserved for the user |

The production-path regressions exercise the existing Engine physical-write
boundary, both supported transmission modes, loss between plugin ticks,
emergency precedence, multiple caps, list permutations, close cut-in,
opposite/adjacent/other-height actors, repeated route occurrences, missing
fields, stale captures, context change during projection, expired Map progress,
manual disable and reactivation. Frozen equal buffers explicitly remain
unconfirmed; no test fabricates publisher freshness.

An earlier broader targeted run had 373 passing tests and 37 passing subtests,
with two `ProfileModeEvidenceTests` failing solely on Windows sandbox
`PermissionError` while creating hard-coded temporary directories. The
out-of-sandbox retry was not executed: automatic approval review was unavailable
because of its usage limit. These are unresolved environment checks, not
application failures; the subsequent permitted checks above passed. No full
suite or previously required safety tolerance was weakened to hide them.

## Changed files and versions

| File | Change |
| --- | --- |
| `core/acc_following.py` | Bounded decode, cached route candidates and speed/headway constraint; no pedals |
| `core/engine.py` | Source-to-route candidate publication, height/missing-speed counterexamples and preserved crossing/emergency protection |
| `core/longitudinal.py` | Last-boundary target-loss/ceiling guard |
| `plugins/acc/main.py` | Existing PID consumes following cap; takeover latch and explicit unverified status; version 1.1.0 |
| `plugins/drivepolicy/main.py` | Avoid duplicate distance law while route following is owned by ACC; version 1.0.2 |
| `tests/test_acc_following.py` | Narrow counterexamples and physical-output/closed-loop regressions |
| `tools/run_acc_following_bench.py` | Reproducible same-input model and operation-cost comparison |
| `PLUGIN_VERSIONS.md`, `PLUGIN_CHANGELOG.md` | Release only changed ACC and DrivePolicy plugins |
| `DEFERRED_WORK.md`, this report | Results, source limitations and joint-validation backlog |

## What remains for Phase 7.4

Protective route-based constraints and their loss behavior are implemented
offline. This is not complete, verified ACC following for arbitrary roads.
Required source evidence still includes publisher timestamp/generation,
documented actor identity lifetime and speed/position accuracy, lane/elevation
membership or demonstrably adequate disambiguation, and documented sensing
coverage. A receiver double-read cannot supply those fields. The smallest
source-side change for freshness is a timestamp/generation attached to the
same traffic snapshot; coverage and membership remain separate requirements.
No new DLL/sensor was built or installed for this task.

Phase 7.4 should jointly verify the existing longitudinal contracts, producer
loss, emergency response, supported transmissions and actual source limitations.
Stop-and-go, certified bumper gaps, verified cut-out/free-road recovery and
live comfort remain outside the completed evidence. No new drive is requested
until the current user-run suite and the input limitations have been assessed.
