# Phase 7 — systemic longitudinal reliability

18 October 2026. **Specific contract repairs are OFFLINE VERIFIED; overall
historical delay attribution remains INCOMPLETE. GAME NOT VERIFIED.**
No installation, original evidence, settings, commit marker or game was changed.
This is not a claim that every technical stop has been explained or eliminated.

## Build and evidence boundary

Entry HEAD is `7f1d5ee` and the entry tree was clean. The installation's
`manual-deployment.json` has SHA-256
`14fcce5243279be1c6732835f0d5120489a50089703bdb154b1d990778bd62ce`.
All36 receipt file hashes matched. Inspected runtime contents matched the entry
source after LF/CRLF normalization. Receipt legacy commit fields are not used
as proof of deployed implementation. The new candidate is uncommitted and does
not match the installation in its three changed core Python files.

ACC1.3.8, Autopilot1.3.4, Map1.1.2, DrivePolicy1.1.4 and Turn Signals1.0.2
remain unchanged: no plugin implementation was edited. Native
`1.59.5-up-parked-records` is unchanged; required DLL SHA-256 is
`fd06c12985fb67c48a7b9aaf5dd500d81e6ac23b928b79c95997bb8ed5d55d27`.
No DLL is added to the new package.

Read-only sources: `ultrapilot.log`, the already analyzed afternoon incidents
in [PHASE7_FOLLOWING_HOLD_AND_SIGNAL_EXECUTION_20261017.md](PHASE7_FOLLOWING_HOLD_AND_SIGNAL_EXECUTION_20261017.md),
and these late-session files under the installation's `route-diagnostics`:

* `steering-replay-20261017T191541.688670Z-automatic_disable.json`: immutable pedal incident;
* `steering-replay-20261017T191542.579910Z-automatic_disable.json`: dense replay,612samples;
* `steering-timing-20261017T191719.483704Z-plugin_stop.json`: passive timing,277samples.

All three late exports passed the existing integrity codec. Expanded immutable
copies, entry hashes/source snapshot, Git diffs, exact comparison and measurement
logs are retained outside tracked source under
`docs/steering-audit/oct17-systemic-longitudinal/`. Large original evidence is
not committed. `tools/audit_oct17_systemic.py` reproduces the read-only lineage
and sampled timeline. Original times are not replaced by decode/read times.

Late-session identity: activation10447815394300, session1,
map`promods-1.59`, dataset`d6cc7936fce4e902761abb5d`,
intent`699868b20c3047ceb868848c268cb6a0`, revision11,
build`9c2c5349ad3f48f2964ce93f73ba9a40`, geometry
`a36809c86c6f7f4794927611ca603fa3c3dc478908bc4f76c06bac1bbda48b5d`.
These are different from the afternoon identity; the journeys are not merged.

## Regression boundary, not an assumption of historical safety

Git pickaxe results and materialized source-only snapshots are in `history.json`
and `history-sources/`. Historical functions run in an isolated process/namespace;
no checkout reset or historical deployment is used. The pre-arbitration parent
is `1f592ce8`; the old221cc90 checkout remains untouched.

| Boundary | Concrete change | Assessment |
| --- | --- | --- |
| `7adf8c815309`,3October | Introduces `core/longitudinal.py` shared pedal arbitration, observation/input leases, shared identity and physical validation. Previously tick-order pedal mirrors were consumed without this complete lease chain. | Necessary safety contract; old absence of this fault does not prove old input freshness or safe behavior. |
| `0a75bf12701d`,11September → `7adf8c8` and entry | SDK and physical output gain independent workers, but traffic acquisition/projection/publication stays in the main loop alongside supervision, GPS/camera and other operations. The new longitudinal chain makes that source deadline necessary. | Old scheduling coupling becomes an observable authority failure. It is not proof of a newly slower traffic algorithm. A deliberate passive-loop stall reproduces this class with real components. |
| `9350be73d256`,5October | Bounded reread accepts any valid second packet, including an older same-activation result; refresh also rejects solely because the rejected original observation crosses500ms before the recovery check. | Concrete ordering and recovery-bound defects, reproduced with unchanged assertions. A valid fresh replacement can be available while an older command remains unexecutable. |
| `add9a190a6cb`,14October | Fixed-motion native body prediction can classify a parallel rear catch-up as a forward-brake stop owner. | Narrow case repaired in7f1d5ee; actual overlap/crossing/uncertainty still brakes. Not a general dismissal of rear hazards. |
| `5f96e07dab3a`,16October | Original crossing completion depends on global body-brake zero. | Repaired in7f1d5ee: unrelated actor73 must not keep completed owner57 alive. Actor73 independently retains braking priority. |
| `a5ca5c4b14a1`,12October | `profile_approach_allowed` can release an admitted terminal brake; ending-green decision can switch stop/go as actual speed changes. | Repaired in7f1d5ee. Earlier measured-speed reference rebound was separately repaired in5a82d0a. No target offset/PID tuning change here. |

The new patch preserves these already committed ownership/reference/brake
corrections rather than reimplementing them or claiming they were new today.
The user's earlier reliability observation is consistent with exposing the old
producer scheduling coupling, but is not treated as a controlled old-build trial.

## Causal map: slowing, stopping and deactivation are separate

| Incident | First slowing/stop evidence | First wrong condition / deactivation | Repair and proof | Remaining historical limit |
| --- | --- | --- | --- | --- |
| Afternoon owner57 → body73 | Acquired crossing57, then independent body73 brake. | Completion of57 incorrectly gated by another body's brake; later `ACC target unavailable or unconfirmed departure`. Identity and original observation were valid. | Existing7f1d5ee per-owner completion; both-mode producer→AEB/arbitration→Controller counterexample preserves73 brake and does not falsely fault57. | Complete original actor lists at the comparison are absent. The reproduced global defect is proven; actor73 is not retrospectively called a false physical hazard. |
| Qualified green, brake remains | Body52 prediction creates a separate stop owner before the green. | Green cannot release a different still-owned stop; parallel rear catch-up was misclassified as a forward stop. | Existing narrow straight/fully-behind/aligned prediction correction, actual native boxes/trailers, both-mode red/hold/new-green integration. | Original complete route is missing; transformed real-body fixture is explicitly an offline reconstruction. |
| Zero/reapply before raw gear−1 | Retained software writes show brake0 then positive brake before subsequent signed SDK gear−1. | Terminal approach could release its admitted chain; true laterR causes the correct rejection. | Existing terminal continuity + same ending-green commitment; no fresh stationary brake edge. TrueR remains refused. | Software writes are not continuous game consumption; exact historical physical cause ofR remains unproved. Later release_all cannot explain earlierR. |
|21:15:41 | Qualified red was129.919m from a **derived** stop target; current traffic_brake/light_brake both0, no lead. No evidence that this distant red directly commanded the technical brake. | AP rejects old traffic at495.796ms observation age,66.408ms past a route-projection dependency deadline; Engine later echoes the latched reason and controlled braking. | New independent single traffic producer; bounded newer-source recovery; ordered reread. Same timed counterexample fails entry and passes current. | Exact main-loop blocking operation, CPU/GC/lock span and native acquisitions after the recorded generation are not stored. This portion is UNEXPLAINED, not closed by a synthetic stall. |

## Exact last-incident timing

First rejected traffic packet: frame126278282,
observation10477.838994, computed10477.9088135,
expiry10478.2683817. Deadline basis is **route_projection** with original
Map observation10477.7683817/frame126194952 plus the unchanged500ms lease.
This is not a changed activation, missing actor ID, stale steering timeout or
an arbitrary traffic deadline guess.

| Event / interval | Original monotonic time or duration | What is established |
| --- | --- | --- |
| Map source observation → packet computation |10477.7683817 →10477.8017639;33.382ms | Original spatial observation and calculation. |
| Map publication completed |10477.8057348 | Completed publication witness; not inferred first delivery. |
| Traffic SDK observation |10477.838994 | Exact traffic vehicle snapshot. |
| Native actor acquisition |10477.8725693, lifecycle38293688109949/gen4389/frame194088582 | Separate producer clock; not Python read time. |
| Native signal acquisition |10477.872642, gen4390/frame194088582 | Qualified red ID1; separate signal observation. |
| Receiver traffic capture |10477.884985 |12.416ms after actor acquisition. |
| Traffic computed |10477.9088135 |23.829ms after receiver capture; mixed operations/IPC, not measured CPU.69.820ms after its own SDK observation. |
| Remaining lease at computation |359.568ms | Producer was usable then; no near-zero initial lease. |
| Retained sampled physical receipt |10478.0442316 | Old traffic was still consumed; this sampled receipt is not first delivery. |
| AP comparison |10478.3347895 | Own observation495.796ms old, decision425.976ms old, dependency overrun66.408ms. Identities equal. |
| First intervention record |10478.3422378 |7.448ms after comparison, using a later vehicle frame126761596/observation10478.3262314. That later snapshot must not replace the compared packet's source. |

The last retained valid Engine decision starts10477.9860643. Its actual input
reads are traffic10478.0160928–10478.0163880 (0.295ms),
ACC10478.0165957–10478.0167815 (0.186ms),
road10478.0234951–10478.0241899 (0.695ms), and
Policy10478.0242135–10478.0246877 (0.474ms). Traffic validation at10478.016399
therefore still had251.983ms left; these recorded reads did not themselves
consume a66ms overrun. The corresponding AP command computed10477.9906003
uses original SDK observation10477.9333747, with the same final deadline
10478.2683817 through its curve/Policy/traffic dependencies. Actual writes1029/1030
return brake0 at10478.0378203 and throttle0.4618924 at10478.0442524.
At the throttle call,224.150ms of lease remained. No expired positive write
is inferred from this record.

First retained safety writes1031/1032 start10478.4161446/.4162035 and return
10478.4161637/.4162167: throttle0 then brake0.25, followed by the existing
controlled ramp. There is a **371.913ms gap between retained throttle calls**
and73.907ms from first fault record to the first retained safety throttle call.
Detail is a short bounded tail, so missing entries cannot alone prove no
intervening physical operation. The history finishes its prior source row at
10478.3549332, much later than that row's writes; its timestamp is not first
delivery or a new SDK sample. Exact control-lock wait, post-write diagnostics,
scheduling and Manager contention during this gap remain unrecorded. Moving
traffic alone is not claimed to explain or eliminate that separate uncertainty.

Map subsequently supplies sequences786–794, including observation10478.2547124,
computation10478.2897694, while this traffic decision remains old. SDK/Map
continuity does not establish that the native actor producer also kept acquiring.
No historical traffic publication-complete or first-consumer-delivery witness
exists for this packet. The source→capture→calculation durations above cannot
be split retrospectively into IPC, CPU, GC, logging and lock time.

The significant-event quota warning at21:15:19 is real, but does not prove it
blocked traffic. Existing export work is bounded/background. The accepted right
indicator request at21:15:41.136 and Controller command at.214 establish the
previous hazard-latch repair's software path; they do not prove game consumption.

## Contract corrections in this candidate

1. **One traffic owner with independent cadence.** Engine starts one traffic
   producer after the SDK worker. It reads the already captured local telemetry,
   native actor/signal seqlocks, projects/selects and publishes at a nominal50ms
   cadence. No task queue, catch-up backlog or controller-I/O lock is introduced.
   Overlap is skipped; shutdown is finite. Slow supervision/camera/GPS work cannot
   directly postpone that producer in the main loop. CPU/GIL contention or an
   actually blocked RPC can still delay it; no real-time maximum is promised.
2. **One coherent publication.** Packet and presentation metadata are published
   in one batch. Original authority is rechecked before publication. A route
   change invalidates old work instead of relabeling it. Native atomic/source
   timestamp/generation metadata now reflects the actual capture; legacy absence
   stays unknown and coverage stays unconfirmed. Control-worker activation uses
   the validated published signal rather than concurrently mutating the producer's
   signal reader/selection cache.
3. **Monotonic bounded reread.** The existing single reread cannot substitute a
   lower frame, earlier observation or earlier computation from the same source
   and authority for a newer expiring decision. Full ordinary validation still
   runs. No general stale-packet acceptance or unbounded retry is added.
4. **Separate unexecutable old command from a qualified zero-drive renewal.**
   After a dependency expiry, a genuinely newer qualified leaf can justify the
   existing100ms, original-deadline-anchored transition even if processing crosses
   the old observation's500ms boundary. The old pedals remain prohibited. All
   other recorded original dependency deadlines must remain valid, the actual
   current vehicle must pass every gate, and the original decision itself must
   not be older than500ms. The packet expiry must also match its original
   deadline-basis receipt; an inconsistent/edited expiry cannot start recovery.
   Missing receipts, real loss, foreign identity, R or
   late complete response still fail. The bound is never restarted or extended;
   a complete Autopilot response must pass Engine and final Controller gates.
   Existing admitted continuous brake is preserved by the same handoff path.
5. **Existing evidence, compact and bounded.** Current traffic phase wall times,
   threadCPU start/end, sequence and previous completed phase record travel in
   the existing packet/journal. A local current phase witness is attached to
   actual output records, separately from the immutable consumed packet. Exact
   compact dependency deadlines survive the existing fault budget/codec.
   These are not mutable references substituted for the rejected input. No new
   collector, SDK acquisition, queue, INFO-per-tick log or memory-budget increase.

The three changed runtime files are `core/engine.py`, `core/longitudinal.py` and
`core/navigation/longitudinal_diagnostics.py`. Lateral/speed controllers,
geometry,500ms source limits, signal5m reference, native producer, parking
actuation and plugin versions remain unchanged.

## Reproductions and acceptance

Acceptance uses existing gates, not thresholds chosen after measurements:
no expired positive drive; no old/foreign substitution; original100ms bound;
fresh complete-owner response before drive; R/stale/backend rejection; original
brake continuity; AEB priority; no positive pedal overlap. Finite performance
measurements below have no invented live PASS threshold.

`tests/test_oct17_systemic_longitudinal.py` uses actual Map, native ABI reader,
Policy, ACC, Autopilot, Engine, Controller and chronological test-backend writes.
Its final receipt-matching entry methods are loaded read-only with
`UP_OCT18_SYSTEMIC_BASELINE=1`. **Four assertions fail before and pass after**:
the timed expiry/recovery and older-reread counterexamples in both modes.
The clock reproduces AP comparison495.7955ms after the recorded observation;
an explicitly injected8ms processing span then crosses500ms before recovery.
The historical7.4483ms comparison→fault-record gap does not prove this exact
8ms inner operation. Source omissions/native actors in this model are marked
synthetic, not presented as an exact actor reconstruction.

The independent-owner test proves publication continues while a separate passive
operation is deliberately blocked. Single-flight/identity-race tests prove no
queued old work overwrites new authority. Newer source acquisition is required;
repeated buffer reads retain original source time. Real placed prefab signal
metadata and native signal bytes traverse the new owner through three repeated
red/hold/green cycles per automatic mode, preserving positive held brake and
automatic restart. Actual backend chronology has no positive pedal overlap or
parking writes. Negative telemetry/native-stale/R/identity/backend cases retain
no new positive physical drive; a disconnected backend is not claimed to have
successfully written zero.

New tests also inspect the existing automatic export for consumed producer phases,
current phase witness, first reason and subsequent safety writes. Both repaired
export-budget regressions preserve their original expectations. A broader
337-test/7-subtest joint run passes. The final focused set passes43 tests. The
initial exploratory failing logs are preserved, including fixture corrections;
only `final-contract-before.log` is the final four-case before proof.

The first whole-suite attempt found the existing
`test_output_boundary_still_rejects_real_faults[stale]` regression: an edited
old expiry disagreed with its original basis but could still request a wait.
The failed run was interrupted and retained (`interrupted-first-full.json`),
not called a full result. Requiring exact expiry/basis consistency fixes the
production guard; the unchanged test then passes with180 other focused cases
(`final-recovery-negative.log`). The final suite is newly frozen after that fix.

## Scheduling/load comparison

`tools/benchmark_oct17_systemic.py` executes actual production components on
independent synthetic cadences: SDK27ms, Map41ms, traffic50ms, Policy61ms,
ACC31ms, AP38ms, Engine21ms; fixed phase offsets and+17%/−8% jitter. It includes
35 native actors, enabled bounded pedal/history diagnostics and background
exports. The baseline loads the actual entry main-loop traffic block and its
old read/refresh methods while retaining the common current publisher/helper
contract. This isolates scheduling/recovery; it is not a byte-for-byte run of
the entire historical application. A declared
440ms passive-loop stall repeats every5s. Candidate source production is
independent. Mock RPC cost is50µs per operation. These clocks model scheduling;
they are not measured Manager delivery or a calibrated ETS2 vehicle plant.
A qualified distant red is an explicit synthetic dependency, not a recovered
native signal association. Full real-prefab red/green tests are separate.

Initial65s comparison (`scheduling-65s.json`): entry mode0 faults at22.481s,
mode3 at2.580s; candidate completes65s in both modes without a false intervention.
Different baseline stopping times mean the following distributions have different
sample counts. Candidate results do not depend on executing an expired command.

| Metric, milliseconds | Simple entry → candidate | Real-auto entry → candidate |
| --- | --- | --- |
| New **traffic** packet intervals, n |377 →1216|40 →1221|
| Interval p50 / p95 |52.45 /63.05 →51.62 /62.87|52.20 /63.40 →51.72 /62.47|
| Interval p99 / max |477.91 /529.01 →67.97 /72.34|475.24 /475.24 →66.36 /70.42|
| Minimum remaining traffic lease at **sampled** AP read |−34.80 →368.50|33.24 →370.55|
| Confirmed-write command observation age, n |1014 →2934|116 →2943|
| Write age p50 / p95 |40.49 /65.03 →41.54 /66.60|41.25 /68.72 →41.25 /65.82|
| Write age p99 / max |72.95 /81.42 →73.59 /81.69|72.87 /75.72 →72.10 /81.02|
| Minimum remaining command lease at write |24.24 →252.59|8.07 →248.24|
| Maximum remaining command lease at write |477.30 →477.40|477.95 →478.05|
| Writes beyond500ms / with negative lease |0/0 →0/0|0/0 →0/0|

Do not claim every tail improved: simple-auto write-age max increases0.27ms,
real-auto max5.30ms in these finite runs. Packet interval is a different metric
from observation age at use. These are longitudinal/traffic intervals, not a
claim about a measured change in steering cadence. Source SDK age at the final
write comes from the actual applied-command witness, not the current shared slot.

Runtime retained source bytes are65,159/64,741 (modes0/3, budget65,536), history
337,567/332,163 (budget1,048,576). Test/mock write histories are cleared outside
measurement. No budget was raised. Candidate producer p50/p95/max wall time is
4.562/5.648/5.915ms in mode0 and5.378/5.846/6.313ms in mode3. The scheduling run
overlapped other tests; those wall values are loaded-host overhead, not isolated
CPU speed-up. GC maxima17.481/9.278ms are observed, not historical causal proof.

A second complete comparison on the final frozen code is retained as
`scheduling-frozen.json`. All synthetic cadence counts, interval/age/lease
distributions, stopping times and fault outcomes are exactly equal to the first
run. Retained bytes vary with current timing witnesses: source65,400/65,039,
history337,778/332,456, still within the same budgets. Loaded-host candidate
producer wall p50/p95/p99/max is3.340/3.968/5.325/6.740ms (mode0) and
3.340/3.911/5.556/6.492ms (mode3). The entire suite was running concurrently;
this repeat proves the final contracts under that finite load and does not
support an isolated CPU speed-up claim.

### Actual IPC profiling, cold and warm

`tools/profile_oct18_traffic.py` additionally uses an actual local Manager proxy,
the same35 native actors and production projection/publication. Three alternating
entry/current repeats have65 calls each, first10 excluded from warm statistics.
Producer RPCs are timed separately from following consumers; transport timings
overlap phase wall time and must not be added to it. Source acquisition is a
synthetic ABI buffer; signal computation here is the explicit no-signal fixture.

Worst per-repeat warm statistics, entry→candidate (ms):

| Phase | p50 | p95 | p99 / max |
| --- | --- | --- | --- |
| Whole traffic operation |7.891 →8.045|9.889 →11.266|10.777 →12.263|
| Embedded Manager RPC wall sum |4.100 →3.898|4.712 →5.361|5.068 →5.747|
| Native buffer capture |0.023 →0.024|0.032 →0.037|0.082 →0.167|
| Projection/control observation |5.564 →5.558|7.408 →8.302|8.197 →9.354|
| Publication helper, including optional HUD handoff |1.508 →1.502|1.937 →2.195|2.026 →2.552|

Cold first operations are51.968/8.023/8.198ms entry and
10.344/7.860/8.324ms candidate. The first entry import/cold path is not a fair
steady-state speed-up claim. Producer RPC counts53→52 include the corrected
single-batch publication. ThreadCPU totals across65 calls are421.875/343.750/
375.000ms entry and468.750/390.625/296.875ms candidate; the host CPU clock is
quantized15.625ms, precluding sub-ms per-call CPU attribution. GC maxima11.337ms
entry and8.030ms candidate are not uniquely paired with slowest ticks. Earlier
`actual-manager-profile.json` includes consumer RPCs in its column and is
superseded by `actual-manager-final.json`, not silently relabeled.

This is a decoupling/ordering correction, not a demonstrated reduction of all CPU
cost. It does not identify a620/477ms historical pause or promise future maxima.

## Verification, packaging and limits

Final verification, frozen SHA-256 and package receipts are recorded below after
the one authorized whole-suite run. The steering/ordinary comfort comparisons
use the existing16/12 finite analytical scenarios, identical entry/current
inputs and unchanged controllers; they are not game measurements.

The candidate includes the existing25-file coordinated dependency set plus a
manifest, not the whole repository. Only the three core files above change
implementation. The required native DLL is hash-bound, not copied. Existing
old candidates remain preserved and are superseded only as proposals.

Prepared rollback is a separately hash-verified ZIP of exactly those25 installed
runtime files plus the original receipt. No backup content is restored now.
On a separately approved future deployment: close both applications, verify the
unchanged base receipt and every original hash, take a new per-deployment backup,
copy the entire candidate set, verify all candidate hashes, then atomically
publish its deployment receipt. On any failure restore **all25 files** from that
backup, verify every original hash and restore the original receipt; do not
restore only the failed file. `settings.json`, map caches, evidence, commit marker
and native DLL stay untouched. A changed installation requires a new backup,
not blind restoration of today's snapshot. Exact payload paths are in the
candidate manifest/receipt. Preparation does not authorize deployment.

**Overall status remains incomplete.** The exact inner Engine operation behind
the last source delay, complete afternoon actor lists/route and continuous game
input consumption are unavailable. Specific reproduced contracts can be marked
OFFLINE VERIFIED; the complete historical system cannot. Future investigation
needs the now bounded producer phase/CPU witness from the same build's existing
export, not a newly invented timestamp or another collector. No new journey is
requested here, and this package is not proposed as a definitive cure.

Existing significant-event storage still has its original quota restriction.
The previously prepared reversible archival step is not applied. Automatic
fault/pedal export and manual steering replay retain their existing paths and
budgets; quota exhaustion/incomplete evidence must remain explicit. A new export
is not automatically a complete record or GAME VERIFIED.

### Frozen identity

The final verification seals425 source/fixture hashes in `final-frozen.json`.
Changed implementation SHA-256:

| File | SHA-256 |
| --- | --- |
| `core/engine.py` |`c1d9b932c80374134106232a763ad314d8d2c55e697684ed81d5897d19c5f46b`|
| `core/longitudinal.py` |`1967fa4cd3cdf257048d7f18b836c145c0f6a5f84069da3bff31130b555cbbfc`|
| `core/navigation/longitudinal_diagnostics.py` |`c4afe653a46c733e14dd4dc9ef1ef7e01fe06021f90fc346a0fc16cbd8ac1cd3`|

Original late-session raw-file hashes, distinct from expanded working copies:

| Original file ending | SHA-256 |
| --- | --- |
| `191541.688670Z-automatic_disable.json` |`baea1b269ce6dc68f1c9aebff6afec0f7f7efb4bf07558bdd3ae0b5ba07a6301`|
| `191542.579910Z-automatic_disable.json` |`309626b638bcc9cc964538846744e645b5e763fd8034740da39aa998efe72771`|
| `191719.483704Z-plugin_stop.json` |`48b0b2a5df17d214c4099caa10616d591fbea47bf1649a48f71a97058e60bb14`|

### Final verification and candidate

The final frozen whole suite passes **3032 tests and1592 subtests in745.03s
(12:25)**, exit0, all425 hashes unchanged. Full log SHA-256:
`2c5d54dc776c554a670985f4c8e432aa11efed64478a95c5ae86717b9f00a6e5`.
`compileall` and `git diff --check` pass. LF→CRLF Git notices are not content
errors. All16 steering and12 ordinary comfort result dictionaries are exactly
equal to HEAD7f1d5ee under the same analytical inputs. The four new defect cases
fail the old methods; all24 new cases and181 final focused cases pass current.
The interrupted earlier full attempt remains a failed/incomplete record.

| Property | Verdict / scope |
| --- | --- |
| Independent source renewal under the declared passive-loop stall | OFFLINE VERIFIED in both65s scheduling runs/modes; no live real-time guarantee. |
| Ordered reread and fixed bounded replacement | OFFLINE VERIFIED; no expired positive drive, renewed old timestamp or rearmed original bound. |
| Genuine stale/incoherent/foreign/R/backend refusal and AEB | OFFLINE VERIFIED by unchanged negative/integration tests; backend failure is not successful zero consumption. |
| Per-owner completion, terminal continuous brake, red/green restart, indicators | Existing repairs preserved; new worker red/green cycles plus the final full suite pass. Game effect remains unconfirmed. |
| Exact operation causing the historical late traffic/control gap | NOT VERIFIED / unresolved; source scheduling coupling is proven, unique historical CPU/IPC/GC/lock attribution is not. |
| Complete-system/game reliability | NOT VERIFIED. No new drive or deployment requested here. |

One current candidate, prepared only:
`docs/steering-audit/oct17-systemic-longitudinal/ultrapilot-oct18-systemic-candidate.zip`,
**25 coordinated files plus manifest**, SHA-256
`e5891d4b688f2a09cd43aeb74ad35a504db3a02c0388b2c3fd9839bb5b268597`.
The25-file set includes the release changelog; it contains no tests, audit
report, raw evidence, settings, map cache, commit marker or DLL.

Prepared return snapshot:
`docs/steering-audit/oct17-systemic-longitudinal/rollback-runtime.zip`,
SHA-256`9bef7fd2c54a16594820a572883a4e31475185e414e470683271ee36736a9c17`.
It contains those25 original installed files and the original deployment receipt.
Both ZIPs were read back; every entry hash matches. Post-package verification
again confirms all36 installed receipt hashes, original receipt, original backup
bytes and all425 source hashes unchanged. Normalized content differences are
exactly the three core implementations and the changelog. Nothing was deployed.
The manifest retains `system_complete=false`, `runtime_authorized=false`,
`historical_inner_delay_resolved=false`, `game_verified=false`.

Changed source files: the three core implementations above;
`tests/test_oct17_systemic_longitudinal.py`; read-only audit/benchmark helpers
`tools/audit_oct17_systemic.py`, `tools/benchmark_oct17_systemic.py`,
`tools/profile_oct18_traffic.py`; candidate verifier
`tools/verify_oct18_systemic_candidate.py`; this report, `DEFERRED_WORK.md` and
`PLUGIN_CHANGELOG.md`. Suggested commit title only:
`fix(core): decouple traffic renewal and validate bounded recovery`.
No commit or push was made. Do not repeat the completed whole suite without
another code change; its manual command is:

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python -m pytest tests -q
```
