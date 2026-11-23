# Nov 3 — roundabout prediction, signed near-stop transition and AP continuation

This report distinguishes the original Nov 2 evidence from modeled output
tests. No deployment, game control, commit, push, original capture change or
whole pytest run is part of this task. Final qualification is recorded below.

## Original build and evidence

The installed `UP-NOV2-PREPARATION-02` receipt has SHA-256
`6307a14e3cccb06edf0eb2ecd2203219ae771e660cf1e4cf33aa30beb7524a20`.
All 57 receipt files were verified. Line-ending-only differences are normalized
when comparing source; package/receipt hashes always cover original bytes.
The installed observational Engine contains capture hooks absent from the
working-tree Engine. The delivered candidate must preserve those hooks and
apply only the selector metadata change to this installed file.

Original session: `acc09d754db347859ee0a83944db6d9a`, incidents 8703 and 11926.
See `PHASE7_NOV2_ROUNDABOUT_ACTOR61.md` for integrity and causal time stamps.
Original manifests remain incomplete. In particular AP11926 is absent;
AP8703 is a different part and cannot replace it. Its earlier immutable lane
snapshot supplies only static route information already available before the
decision (revision 11, build `a5b5353b69bc43e0856895bce4d3ba3d`).

## Cause → evidence → correction

### Actor motion

Both crossing and body prediction extended a native actor's current heading
as a straight constant-speed ray. Native history instead records actor 61
turning through the roundabout. At the first consumed crossing forecast the
nearest later observation was 15.243 m from the predicted reference point;
this is not bumper clearance, right of way or proof that no braking was needed.

The candidate prepares all authored directed curves of each route-touching
placed prefab once per LanePath. On this actual map the production preparation
reproduces **99 curves / 610 transformed XYZ points exactly**. Preparation took
4.0815 ms in the read-only map check; serialized metadata is 56,956 bytes.
It is immutable under the route/dataset/build identity, not calculated per actor
or tick. Fixed bounds: 256 curves, 4,096 points, eight simultaneous hypotheses
per actor, existing 80-actor limit. Incomplete/invalid/overflow topology falls
back to the original protective model, never a fabricated clear-road receipt.

Matching requires a qualified original native acquisition pair, same actor
lifecycle, an observed moving actor, <=1.2 m reference distance, <=1.5 m height
difference and <=30 degrees heading difference. The tight match selects
compatible hypotheses, **not confirmed lane membership**. Every authored
successor is retained, rather than choosing the closest exit. At missing map
support an explicitly labeled tangent assumption remains; exit intent and
physical road-envelope coverage remain unverified. No future replay point is
used by the runtime selector.

Crossing and body prediction use this same hypothesis set. Body protection
includes the measured tractor/trailer offsets with fixed articulation and a
conservative per-segment rotation enclosure. It takes the earliest contact
over all branches; crossing takes the strongest demand. The existing dev HUD
gets these actual poses and branch/model labels, not an independently drawn
curved line. Stationary/native-overlap protection and legacy unsupported-route
fallback remain. No steering, road geometry, PID, arbitration, AEB threshold,
signal, hold or freshness-timeout tuning.

### Signed stop speed

The first historical ACC technical rejection was not an expiry: approximately
474.266 ms remained. Actor 61 was still observed with a qualified native owner
chain. Native ego speed was -0.039795611 m/s and SDK speed -0.022485010 m/s.
The original decoder omitted ego boxes for any negative native speed and
crossing rejected any negative SDK speed. This destroyed decision-completion
inputs and was reported as an unavailable/unconfirmed departing target.

The candidate preserves signed speed and body availability independently of
drive permission. Small signed SDK speed uses the same -0.10 m/s boundary
already enforced by the drive guards. Body prediction models measured negative
displacement along the observed heading, including behind a rolling route's
left edge; it does not clamp speed to zero or extrapolate unknown road geometry.
Real R/backward drive is still rejected by the original independent gates.
Retained body/crossing evidence is not an empty-list clearance witness.

### Missing AP continuation

The previous part 8703 remained on traffic publications while its export was
busy; the later 11926 request arrived after the AP had become inactive. Both AP
completion paths discarded the retired input ring when no next case had yet
been accepted. The background completion path also omitted the bounded original
predecessor tail retained by the ordinary tick completion. That removes the
inactive AP's later compact-seal rendezvous and exact overlap inputs.

Two ordered reproductions (ordinary and background completion) fail before the
change. The fix publishes one immutable completion tuple, retains the same
bounded original 30.5 s predecessor references and existing retired 32 MiB slot,
and permits the existing worker to accept the later seal. No newer packet fills
a historical hole. No new worker/queue, timeout or memory limit. Independent
completeness/integrity checks still reject missing ranges/references. This
reproduces a concrete delivery defect consistent with the observed ordering;
it cannot prove every historical missing subphase or recover AP11926.

The daemon long-wait qualification then exposed a second exact retention
gap: rows AFTER an in-flight seal could leave the current 30 s ring before the
next request existed. A frozen predecessor cannot contain that forward middle.
The existing retired slot now receives references to the original frozen AP
transaction after each tick while a case is pending. It has the same 32 MiB
limit, exact shared-input accounting, chronological keys and explicit overload
loss counts. On accepting an unrelated new request or completing a part, only
the provably out-of-range prefix is retired. No repacking, extra SDK/IPC reads,
unbounded incident list or new export worker is introduced.

A further ordered assembly test reproduced a correct late AP resolution being
ignored by the next Engine part: it linked the original incomplete predecessor.
Engine export now prefers and fully verifies the immutable `-assembled.json`
resolution, including its original lineage and all dependent hashes, and reuses
the existing bounded per-operation verification cache for final readback.
A corrupt resolution is rejected; no original is overwritten. This preserves
the original and successor completeness rules, rather than setting flags to
hide missing evidence.

The final daemon-host reproduction also exposed an active/inactive ownership
error: an ACTIVE AP with a retired slot started the compact-seal polling job
intended for a disabled AP, occupying its sole writer while current requests
arrived. The poll now uses the already-consumed local activation flag; it is
not launched while active. The real disable callback is unchanged. A newly
sealed case does not inherit the previous completed-case/poll retry deadline.
Existing failed-case retries, export admission and all safety limits remain.
Both ordered regressions fail on the prior candidate and pass after this fix.

## Reproductions and measurements

`tools/reproduce_roundabout_prediction.py` replays 32 exact native byte
captures with original source clocks/generations, SDK signed speeds and the
prior static route. It runs Engine traffic production, Policy, ACC, Autopilot
and the actual Controller into a memory backend in both supported modes.

**Transport model limitation:** activation and steering calculation transport
are explicit models, because the corresponding AP11926 inputs are missing.
The recorded prolonged gear=0 follows the OLD emergency output; the candidate
does not generate that emergency. Physical-output comparison therefore uses an
explicit confirmed forward-gear transport model for these frames, in both
modes. It does not relabel the historical gear, simulate vehicle physics, or
prove zero-ratio/hold behavior from this recording. Separate production lifecycle
regressions retain the actual zero-ratio, continuous-brake and R guards.

| Same captured input / metric | Installed baseline | Candidate |
| --- | ---: | ---: |
| New targeted reproductions | 10 failures | qualification below |
| Engine crossing brake at source generation 36660 | 0.7442873186 | 0 |
| First positive crossing brake in sampled 8429.017–8432.788 interval | 8431.7380422 | none |
| Native/SDK negative-stop body availability | unavailable | original signed motion retained |
| AP predecessor completed before late next seal, both completion paths | original references discarded | exact original references retained |

`prediction-comparison.json` compares the SAME first fully retained Engine
capture (source 8431.6835558), forecast horizon 3.4625738 s, with the nearest
later native position at 8435.1907916. Straight-reference error is **14.651 m**;
the candidate's one compatible branch at this instant has **6.652 m** error.
Earlier captures retain up to six branches; none is chosen using later data.
The original 15.243 m figure concerns the earlier consumer generation 36658,
whose complete Engine capture is not in the 10 Hz traffic series. Do not merge
these two forecasts. Remaining error includes unmodeled speed changes and exit
uncertainty; this is not a vehicle-dynamics or counterfactual safety proof.

Future actor samples are used **only for scoring**. The replayed ego speed
decline is the historical response to the old output, not the candidate's
predicted speed response. No closed-loop ETA/collision-free claim is made.

## Qualification and delivery

The final frozen runtime is `docs/steering-audit/nov2-roundabout/release11/`.
Internal stages `release01/` through `release10/` are superseded qualification
artifacts, not deployable packages; none has a candidate ZIP. In particular
release01's full working-tree Engine omitted installed capture hooks, so that
stage was rejected before delivery. The final installed-base overlay preserves
those hooks. DLL/ACC/Autopilot implementations and versions remain unchanged;
Map publishes new immutable metadata as 1.1.4. Final results are appended below.

### Performance scope (do not conflate these models)

The original 32 captured traffic frames contain the actual local native actor
population. A separate adversarial capacity model copies a uniquely identified
moving tractor into all 40 moving slots with three trailer slots, and adds 40
parked boxes. The clustered form contains physically overlapping vehicles;
the offset form uses distinct XZ/tractor/trailer positions but STILL contains
physically overlapping vehicles. It is not a representative spatial traffic
distribution. Neither is a second
historical drive or a counterfactual vehicle-dynamics simulation.

In the paced maximum-population run, the first refusal is **missing acquired
native owner witness**, with fresh data and unchanged identity. Forty competing
protective objects exceed the existing bounded 16-owner evidence contract.
That safe refusal is distinct from the recorded actor-61 signed-speed defect
and from stale telemetry. No owner limit or acceptance check is relaxed.
The exploratory earlier paced run also performed recursive test-only heap
inspection between acquisitions; that artificial replay delay was removed
from measurement, with memory inspection moved after the timed loop. Both
original results remain available and are not presented as historical faults.

Initial map-hypothesis implementation at maximum modeled population reached
**539.435 / 570.978 ms** projection maxima in modes 0/3. That is a demonstrated
implementation cost, not a historical cause, and that intermediate runtime is
not delivered. Profiling identified repeated hypothesis-segment/reference-edge
tests as its largest CPU operation. The final path indexes exact reference
edge bounds, batches only AABB candidate-pair admission (existing required
NumPy dependency; <=256 segments x 512 edges), retains scalar intersection/
arrival/brake decisions, shares identical geometric calculations without
merging actor identities, and prepares ego rotation enclosures once per frame.
Original hypotheses, times and all distinct branches/body/actor results remain.

The held geometry/index/query ownership is bounded: 256 authored curves,
4,096 points, eight branches x 33 samples per observed moving actor, <=80
actors, 65,536 edge-grid memberships and 1,024 local query entries. Sparse long
edges use full exact fallback, rather than vanishing from a point-only index.
Route replacement invalidates indices and their queries; invalid native
acquisition clears motion caches. Small signed speed also cannot subtract the
existing 12 m standstill headway or 6 m safety reserve; signed closing motion
is preserved.

Raw timing/CPU/whole-tick/memory results must be read from the final release
qualification, separately from earlier exploratory profiles. In particular,
meeting a 500 ms data-validity boundary is not equivalent to sustaining the
50 ms traffic-producer target period. The previous diagnostic-only capture
gates are not silently converted into PASS for a changed prediction algorithm.
Any maximum-population period overruns remain explicitly reported.

### Test isolation corrections

The legacy 64 KiB/significant-event export tests now explicitly select that
legacy mode when run under an enabled temporary diagnostic config. Their
existing safety/quota assertions are unchanged; diagnostic mode intentionally
uses multi-part incident export and its independent integrity/completeness
tests. The same legacy quota failure was reproduced on the unmodified installed
base before correcting the test setup.

Spawned hosts inherit the selected frozen runtime ahead of the checkout's test
package. Long-wait test polling reads only an immutable manifest's declared
incomplete state until it can be complete, then requires the SAME full hash,
coverage and lineage inspector before accepting it. Each remaining part is
fully checked once in the result. This removes test-only multi-second repeated
expansion from the modeled control loop; it does not relax any assertion,
runtime timeout or incomplete-evidence verdict. Original failed runs remain.

## Remaining boundaries

- This fixes demonstrated straight-ray and signed-input defects. It does not
  establish traffic priority, game consumption of backend calls, perfect exit
  prediction, all-map topology coverage or the necessity of every historical
  brake. Fixed-articulation, constant-speed hypothesis limits remain explicit.
- Original AP11926 and Engine observation gaps remain missing. Later successful
  diagnostic export cannot upgrade those originals. Retention beyond bounded
  capacity or unavailable observations still produces explicit incompleteness.
- OFFLINE qualification is separate from GAME verification. No new game drive
  or deployment is requested in this task; user full pytest and explicit
  deployment approval remain prerequisites to any later controlled capture.

## Final verification — November 4

**Targeted incident corrections: OFFLINE VERIFIED. Overall release readiness:
BLOCKED by maximum-population throughput, not by an unexplained historical
lease. GAME NOT VERIFIED. No release ZIP or deployment is authorized by these
results.** The frozen nine-file runtime and exact installed-base hashes remain
under release11 for reproducibility; they are not a qualified deployment bundle.

| Check | Result / evidence |
| --- | --- |
| Original installed control reproductions | 10 failures, `installed-before.log`; original signed-reserve and subsequent AP regressions also fail before their fixes |
| Final frozen control regressions | **526 passed / 984 subtests**, `release11/control-regressions.log` |
| Diagnostic/daemon regressions | **39 passed**, `release10/diagnostic-regressions.log`; includes both real Windows spawn daemon long-wait modes, AP attachment and complete verified continuation without application shutdown |
| Diagnostic proof transferred to release11 | Diagnostic implementation, replay assembler, Engine and build config are byte-identical to release10; every selected diagnostic test file hash also matches. These 39 tests were not falsely reported as rerun on release11 |
| Actual captured source, repeated three times/mode | 96 samples/mode; 0 invalid ACC, 0 first interventions, ends active in every run |
| Paced original capture, actual processing elapsed | 32 samples/mode; 0 invalid ACC, 0 first interventions; both end active |
| HUD on/off, existing benchmark | 160 measured ticks/mode/setting; identical physical-output hashes and source-read counts, no faults |
| Existing longitudinal benchmark | 180 Engine samples; physical writes, mapping frames and IPC reads identical with diagnostics off/on |
| Existing steering benchmark | 16 cases completed; lateral/steering/route implementations remain identical to installed base |
| Static/integrity | Changed runtime compiles; normal `git diff --check`; 57 installed receipt files and 27 protected original evidence files unchanged |

The diagnostics transfer is component-level evidence, not a claim that every
release10 measurement was executed against release11. Latest batch admission
is separately regression-tested against the exact scalar transform and edge
comparisons, including distinct actor/trailer identities. The release11 control
suite and five benchmark jobs execute the frozen installed-base overlay.

All values below are milliseconds. p50 is the sample median; p95/p99 are
nearest-rank percentiles; with 32 or 96 samples p99 equals the maximum. The
whole modeled tick includes Engine traffic publication, Policy, ACC, Autopilot
and actual Controller dispatch into a memory backend. It serializes components
which run in separate application processes. It does not measure live IPC
scheduling, game response, or a closed-loop alternate vehicle trajectory.

| Load / mode | Samples | Traffic projection p50 / p95 / p99 / max | Whole modeled tick p50 / p95 / p99 / max |
| --- | ---: | --- | --- |
| Original captures, frozen receiver clock / simple | 96 | 8.57 / 9.81 / 11.38 / 11.38 | 20.17 / 27.93 / 31.12 / 31.12 |
| Original captures, frozen receiver clock / real auto | 96 | 8.71 / 10.19 / 10.96 / 10.96 | 18.70 / 26.33 / 28.85 / 28.85 |
| Original captures, paced wall clock / simple | 32 | 9.81 / 12.98 / 13.51 / 13.51 | 23.27 / 33.10 / 36.41 / 36.41 |
| Original captures, paced wall clock / real auto | 32 | 10.16 / 16.98 / 18.83 / 18.83 | 21.72 / 33.65 / 36.61 / 36.61 |
| 40 moving x 3 trailers + 40 parked, overlapping model / simple | 32 | 34.36 / 56.30 / 63.39 / 63.39 | 39.53 / 67.03 / 68.61 / 68.61 |
| Same overlapping model / real auto | 32 | 35.70 / 56.90 / 72.48 / 72.48 | 40.01 / 68.48 / 76.41 / 76.41 |

The nominal capture's projection ownership peaks at **408,526 bytes**; the
maximum-population graph/current-motion cache peaks at **2,548,630 bytes**.
These are recursively accounted retained objects, not whole-application RSS,
export-process RSS or retained test assertion history. CPU thread counters on
this host have a coarse 15.625 ms quantum, including zero results for short
sections; those readings cannot substantiate sub-millisecond CPU claims.

In the paced original runs the command's SDK age measured at **flush return**
has p50/max **89.80/120.86 ms** (simple) and **88.25/135.56 ms** (real auto).
Minimum original lease remaining at that point is **379.14/364.44 ms**.
These are not timestamps sampled at each physical write and are not game
consumption latency. Missing historical AP/write pairing is not filled with
these modeled values. The 500 ms freshness guards remain unchanged.

Longitudinal on/off Engine p99 is **1.284/2.344 ms**, max **1.967/2.478 ms**;
its measured diagnostic increment is reported separately in the benchmark.
That benchmark exercises the legacy short journal: its 358 evictions and
0.083 s retained detail are NOT a claim of a complete incident window. Complete
long-wait incident/continuation evidence comes from the separate daemon tests.

### Specific remaining release blocker

The maximum overlapping model still misses the existing **50 ms** modeled
traffic-period/p99 criterion, despite improving its initial 539/571 ms
projection maxima to 63/72 ms. The older diagnostic qualification's p99 <50 ms
and max <100 ms gates are not relaxed: maximum passes, p99 does not. A fresh
source and a sub-500 ms command age do not cure a missed producer period.
Consequently no general READY verdict, `all_gates_passed=true` or final ZIP is
issued. No user approval to weaken the criterion is requested.

`release11/profile-maximum.log` locates the remaining work in authored branch
enumeration/interpolation, per-actor crossing-pair admission and body prediction,
not in an export wait. On 64 profiled model ticks the cumulative times include
crossing 2.189 s, body prediction 1.411 s and hypotheses 1.766 s (nested times,
not additive); profiling itself adds overhead, so its wall maxima are not the
release timing values. Test-only recursive heap inspection is outside timed
acquisition. This profile does not identify a historical GC/scheduler pause.

The smallest remaining implementation step is to reduce repeated batch/body/
branch preparation under this same bounded maximum-population input while
preserving every original hypothesis, distinct identity and exact output; then
repeat that failed timing case and the affected frozen-runtime regressions.
Dropping actors, raising the 16-owner limit, changing safety timing or merely
exporting a ZIP would not resolve this blocker. The safe owner-cap refusal in
the adversarial model must also remain explicit, rather than be called a
successful cruise run.

### Exact prospective runtime overlay

`release11/candidate-manifest.json` contains SHA-256 and original installed
hashes for these nine prospective payloads:

- `core/actor_motion.py` (new);
- `core/acc_following.py`;
- `core/acc_body_prediction.py`;
- `core/engine.py` (installed observational base with only the selector metadata call changed);
- `core/steering_replay.py`;
- `core/navigation/longitudinal_diagnostics.py`;
- `core/traffic_dev_hud.py`;
- `plugins/map/main.py` (1.1.4);
- `core/navigation/diagnostic_build_config.py` (existing diagnostic config, truthful candidate build marker).

No DLL, settings, map cache, original evidence, commit marker, ACC or Autopilot
plugin implementation belongs to this overlay. After qualification only, the
existing builder can create one candidate plus exact installed-file rollback;
rollback removes only the newly introduced actor-motion module and restores
all overwritten originals together. No rollback archive is falsely advertised
as already delivered. Nothing has been installed or committed.

Machine-readable measurements, hash proofs and the failed release gate are in
`release11/qualification-summary.json` and `release11/qualification-result.json`.
The user's whole pytest suite was deliberately not run in this task.

## Performance follow-up — November 21

The performance comparison uses release11 as the repaired control reference.
The `perf21-offline/verification-runtime` snapshot carries exactly three new
Python payloads over that baseline. It is isolated for testing. The release
builder still verifies every installed dependency against the deployment
receipt before it can stage or package a release.

### Work removed from repeated ticks

- **Branch preparation.** A bounded index stores expanded bounds for individual
  authored segments. The grid only restricts which segments receive the
  existing exact position, height and heading tests. An exact fallback covers
  long segments and grid capacity overflow. Nearest-segment and branch order
  retain the original tie rules. Geometry preparation stores original join
  validity, headings and terminal poses once per route binding. Each forecast
  reuses rotation terms within the same seed and the same current actor.
- **Crossing.** Exact route-edge bounds remove impossible candidate pairs.
  The parallel and segment-intersection tests reject more pairs before they
  become Python objects. Surviving pairs follow the original intersection,
  height, arrival and brake rules in original order. A native ego speed at
  or below 0.1 m/s already excludes a future crossing-arrival demand. The
  shortened path retains input validation and leaves body protection active.
- **Body prediction and HUD.** One read-only array shares current actor body
  poses between crossing and body prediction. Body prediction reuses ego
  box axes, circumscribed radii and identical per-body branch prefixes. The
  original scalar contact test and sequence select the exact same result.
  Paths are still attributed to their original actor, body and hypothesis.
- **Invalidation and bounds.** Actor caches are discarded on each new source
  acquisition, invalid source and route change. The current acquisition can
  retain up to 80 keys. Body arrays contain at most 4 bodies × 8 branches × 33
  samples × 4 float64 values per actor. The static grid has at most 65,536
  memberships. The body contact cache has at most 8 × 12 entries and lives
  within a single body prediction. There is no new worker or dependency.

Exploratory stages 12–18 are retained for comparison. Batching very short
curves and running separating-axis arithmetic over dense body arrays added
allocation and computation. Those experiments were discarded. No candidate
lowers the time or spatial coverage required of a protective forecast.

### Installed dependency preflight

The original receipt still has SHA-256 `6307a14e3cccb06edf0eb2ecd2203219ae771e660cf1e4cf33aa30beb7524a20`.
56 of its 57 files match. The game's installed `ets2la_plugin.dll` is now
`41335023cc84487d3c38d9f497d06f54cb501e142267ff51d5ff1ea714849811`.
The receipt and bundled SDK manifest require
`330c37eb5540cd23c84dba9a7b7824c1f791cd5aac7cd7c9bb5341db8ad5715c`.
The updated file and the last game log declare `1.61.0-up-scoped-read`.
That shared version label does not establish binary identity or qualify the
new DLL's traffic ABI and original-clock behavior. The release preparation
stopped at the dependency check. The installation and the receipt were left
as found.

### Exact output comparison

The paired replay executes the same 32 native acquisitions per automatic mode
through Engine, Policy, ACC, Autopilot and Controller. The tolerance was zero
for numeric output. All branch poses, crossing and body conflicts, owner
witnesses, active state, speed caps, selected brake and throttle, intervention
reasons and ordered Controller writes matched release11. The earlier technical
refusal in the adversarial overlap model remained the same missing owner
witness. Both paced runs over the original actor-61 recording stayed active
with zero invalid ACC inputs. The real-auto run still had a 79.43 ms total
tick, with a 57.42 ms projection stage, despite retaining authority.

The final offline runtime passed **131 focused tests**. The immediately
preceding offline snapshot passed **522 adjacent tests** before the final
reference projection and SAT-axis reuse changes. The final focused suite
reran the affected geometry, ACC, signed stop, reverse, signal, HUD and
continuation coverage. The qualification's SHA-256 verification confirms that
the other six files in the overlay, including Engine, replay assembly and AP
continuation, match release11 byte for byte. Original daemon long-wait evidence is retained
with its original build scope. The 27 protected incident files all match.

### Timing and capture gates

Phase probes use the identical overlapping 40-moving / 40-parked workload in
both modes. Values are in milliseconds. The rows are inclusive and can
overlap, so they cannot be added. Cold preparation is counted only when the
selector rebuilds its graph and reference. The other rows have 64 samples.

| Phase | Release11 p50 / p95 / max | perf21 p50 / p95 / max |
| --- | ---: | ---: |
| Cold selector preparation (4 calls) | 2.39 / 2.61 / 2.61 | 2.98 / 3.11 / 3.11 |
| Branch selection and forecast | 10.90 / 18.99 / 23.53 | 5.81 / 12.29 / 18.31 |
| Crossing pair admission | 11.49 / 23.95 / 53.84 | 5.89 / 10.79 / 47.61 |
| Crossing inclusive | 25.73 / 48.47 / 67.31 | 17.90 / 32.76 / 66.15 |
| Body prediction | 7.09 / 15.54 / 18.66 | 4.69 / 9.88 / 12.14 |
| Engine traffic projection inclusive | 36.74 / 63.44 / 81.83 | 22.33 / 43.64 / 69.52 |

The full tick improves in its typical duration, but repeated samples fail the
unchanged **p99 < 50 ms**, **maximum < 100 ms** and **Engine flush p99 ≤ 16.67 ms**
gates. These short runs use the existing replay driver and copying IPC fixture.
There are three 32-frame runs per mode for perf21. Nearest-rank p99 is the
maximum at this sample size. The release11 row shows the prior 32-frame
qualification from November 4. A same-day rerun of release11 also failed
with p99 75.00 / 99.67 ms. The results do not establish an improvement in
worst-case latency.

| Overlapping roundabout model | p50 / p95 / p99 / max whole tick | Engine flush p99 |
| --- | ---: | ---: |
| Release11, simple | 39.53 / 67.03 / 68.61 / 68.61 | unrecorded |
| Release11, real auto | 40.01 / 68.48 / 76.41 / 76.41 | unrecorded |
| perf21, simple | 38.91 / 66.27 / 107.57 / 107.57 | 44.50 |
| perf21, real auto | 41.81 / 86.38 / 136.55 / 136.55 | 21.38 |

GC contributes up to 34.44 / 48.36 ms in the timed perf21 loops. The observed
pauses do not explain all overruns. Earlier paired samples also exceeded the
gate during crossing and physical flush with negligible GC in those ticks.
The profiler's wall times include scheduling and contention. They do not
identify either as a historical root cause. Bounded graph and current actor
cache ownership peaked at 3,370,716 bytes, including array storage. This is
separate from application RSS and export children.

The existing, separate **1400-tick 40+40 capture qualification** ran on the
same perf21 Python snapshot in both automatic modes, with and without enabled
incident capture. It exercises a lead change, a crossing actor, a red/green
episode, the combined worker, Windows spawn daemon host and actual admitted
export child. Its scene does not contain the overlapping prefab approaches.
Every unchanged gate in that qualification passed.

| Mode | Full tick off p50 / p95 / p99 / max | Full tick on p50 / p95 / p99 / max | During export p99 / max | Flush on p99 / max |
| --- | ---: | ---: | ---: | ---: |
| Simple | 11.18 / 14.52 / 16.33 / 40.45 | 15.06 / 19.81 / 24.38 / 35.36 | 22.96 / 29.33 | 8.47 / 16.39 |
| Real auto | 12.19 / 16.26 / 19.16 / 27.77 | 12.51 / 16.86 / 18.66 / 31.17 | 18.27 / 28.51 | 7.03 / 20.67 |

Each enabled mode exported a verified ledger with **30.00 s pre / 15.55 s
post**, **1,927 exact pedal calls**, zero capacity drops or capture failures,
and complete Engine and AP parts. Both active states and all ordered writes,
inputs, decisions and read counts matched capture off/on. One export child
was admitted at a time. Its maximum RSS was 1,137,209,344 bytes in simple and
1,119,961,088 bytes in real auto. The conservative runtime parent upper bounds
were 341,061,632 and 335,347,712 bytes. Upper family totals were 1,478,270,976
and 1,455,308,800 bytes. The peak Engine/AP ring ownership was 39,513,996 /
7,691,183 bytes and 39,145,963 / 7,538,158 bytes, respectively. The original
approved limits and lock-wait gates pass. That scope excludes the offline
readback checker's additional allocations and is not a full overlapping-prefab
run during export.

**BLOCKED.** The concentrated roundabout model exceeds the time gates and the
game's current native DLL differs from the qualified dependency. The full
capture qualification for its own scene and the preserved control behavior
provide partial offline verification. No deployable ZIP or rollback was
created. The current DLL needs a verified build/ABI receipt or a separately
authorized restoration of the already qualified dependency before packaging.
The roundabout needs a passing repeated profile at maximum load, including
an export-active run on that same workload, before controlled capture can be
authorized. GAME NOT VERIFIED.

Evidence and the nine-file runtime hashes are in
`docs/steering-audit/nov2-roundabout/perf21-offline/qualification-summary.json`.
The exact capture gate evaluation is in `perf21-offline/load/assessment.json`.
Compilation and `git diff --check` passed. No whole pytest run, deployment,
game start, commit or push was performed.
