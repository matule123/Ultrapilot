# Phase 7 — Oct 9 packet renewal and longitudinal refresh

Date: 2026-10-10. Continuation of the existing working tree; no new release.

**PARTIAL OFFLINE FIX; HISTORICAL LONG STALL NOT FULLY ATTRIBUTED.** Four
production counterexamples are fixed. The observed reference-region pauses
are identified, but the retained historical data do not separate the operations
inside that region. The throughput improvement below is not proof that the
657/514 ms gaps cannot recur. Game reliability and the requested 5 km acceptance
remain **NOT VERIFIED**. No drive is requested by this report.

No installation, diagnostic arming, game control, commit, push or full pytest
run occurred. Existing signal/traffic/approach/pedal-export changes are retained.
The controllers, LanePath geometry, scheduler, 35 km/h roundabout upper target,
500 ms freshness, 50 ms drive reserve and 100 ms zero-drive handoff bound remain
unchanged. In particular, an expired steering packet is still rejected during
a longitudinal refresh. No expired propulsion is written.

## Source and deployment binding

HEAD: `787d012a2a78ac917bb5506e0958c32d8d06575f`, plus the existing local work.
No `AGENTS.md` was present in the repository or checked parent directories.
`PLUGIN_VERSIONS.md` and the preceding signal/traffic report were read. The
explicit user instruction to avoid another plugin version takes precedence:
Autopilot remains **1.3.3**, Map **1.1.1**, ACC **1.1.4**, DrivePolicy **1.1.0**.
The implementation changes are marked unreleased in the changelog.

The Oct 9 `manual-deployment.json` declares that HEAD **with local changes**,
Autopilot 1.3.3 / Map 1.1.1 / DLL `1.59.3-up-signal-scope`. All **17 installed
target hashes** match the receipt. Before this task's runtime edits, their source
content matched too. Current LF/CRLF-normalized runtime differences introduced
here are `core/longitudinal.py`, `core/navigation/road_network.py`,
`core/navigation/evidence_worker.py`, `plugins/map/main.py` and observational
additions in `plugins/autopilot/main.py`. Engine, Controller, ACC and DrivePolicy still match
their installed content. The install is not silently presented as this candidate.

DLL SHA-256:
`0aba58549d2a7d008bc620424a43fa0f28c840e1688687d0ffd5effe6e434dab`.
No DLL/source-schema change is required by this task. `commit.txt` is not used
as a content certificate.

## Same-session evidence

Installed directory: `<UltraPilot>/route-diagnostics`. Existing hash/schema,
sample counts, chronological pedal references and history integrity were checked
with `inspect_replay`; original files were not edited.

| UTC suffix | Retained evidence |
| --- | --- |
| `194546.386635`, `.903409`, `194548.582905`, `.939919` | Four significant-event histories |
| `194550.677380-automatic_disable` | First pedal incident |
| `194551.726851-automatic_disable` | First dense replay; 261 rows, 4,803 executor rows |
| `194636.850094-manual_disable` | Intermediate activation/manual disable; 63 rows, 2,615 executor rows |
| `194657.272327-automatic_disable` | Second pedal incident |
| `194658.175301-automatic_disable` | Second dense replay; 133 rows, 1,237 executor rows |
| `194721.097080-plugin_stop` | Timing export; 288 sampled reads |

Common route binding: session `1`, map `promods-1.59`, dataset
`d6cc7936fce4e902761abb5d`, intent `3724b5710649430e9d8cc217adcff016`,
revision `7`, build `f367bcdac7ba43c1bd76a55de4c7980b`, geometry fingerprint
`1e19fec599b5c4c54a0a6d3adb0de78d19d0cefb7c1f3bda72d2b3e5f9a0f8a6`.
Reactivations have distinct activation tokens; these are not merged.

First dense file SHA-256:
`2cd540d9c3a53055eb7855cf758329821f1c26e3b63a4ccf4e606501c68aa84b`.

### First incident: Map reference region, not slow publication of packet 664

All times below are the recorded application monotonic clock in seconds.

| Boundary | Packet 664 | Next packet 665 |
| --- | ---: | ---: |
| Map tick start | 9659.8384908 | 9659.8899304 |
| Lane update end | 9659.8517951 | 9659.9051051 |
| Presentation end | 9659.8519365 | 9659.9054830 |
| Road type end | 9659.8584431 | 9659.9119698 |
| Reference end | 9659.8746086 | **9660.5320662** |
| Calculation start | 9659.8746390 | 9660.5320953 |
| Calculation complete | 9659.8758653 | 9660.5332376 |
| Publication complete | 9659.8797718 | 9660.5369549 |
| Original SDK observation | 9659.8576467 | 9660.5023695 |
| SDK frame | 169459888 | 170093196 |

Packet 664 was published at age **22.1251 ms**. Engine rejected it at
`9660.3822236`, age **524.5769 ms**, while SDK continued. Next-tick lane work
took 15.1747 ms; the road-type-to-reference interval then took **620.0964 ms**.
Calculation-to-calculation gap was **657.3723 ms**. Calculation and publication
themselves remained short. Packet 665 used a genuinely newer SDK pose, not a
renewed timestamp. Its sampled read was 4.8863 ms after publication; this is
**not** a measured first-delivery latency.

The reference interval contains existing maneuver-packet IPC, evidence harvest,
reference preparation, the new SDK read/localization and selection. Historical
timestamps do not distinguish these substeps, scheduling or GC pauses. It is
not valid to assign all 620 ms to DFS, IPC, diagnostics or GC.

### Following shutdown: exact refresh reason and the same renewal gap

The log's exact reason is **`longitudinal decision needs refresh`**, not the
user's approximate wording. At Engine check `9726.9683436`, command expiry
was `9726.9723052`: only **3.9616 ms** remained. The command was still valid,
normal drive, sourced from Autopilot/ACC, and its identities matched. Its
deadline was inherited from **curve / spatial_observation**, frame `235857232`,
observation `9726.4723052` plus the unchanged 0.5 s lease. Activation token was
`9720427175200`. New drivetrain data did not renew that separate Map evidence.

The command's own observation was `9726.8999626`, frame `236290548`, calculated
at `9726.9393888`. The compared vehicle was frame `236323880`, observation
`9726.9351842`, forward gear 9. This is not stale drivetrain telemetry or a
context mismatch.

Packet 2255 calculated at `9726.4920391` and published at `9726.4940347`.
Next tick started at `9726.4999168`, finished lane work at `9726.5160879`, road
type at `9726.5277945`, but reference only at `9727.0046458`:
**476.8513 ms** in that interval. Packet 2256 calculated at `9727.0058989`,
with a genuinely newer SDK observation `9726.9705283` / frame `236357212`.
Calculation gap: **513.8598 ms**. Its publication-start stamp exists; absent
completion in the sampled export is not proof that publication failed.

The zero-drive refresh bug below can consume the last milliseconds during its
own IPC. It is reproduced as code behavior, not presented as a measured
historical duration of that specific RPC. Fixing it alone cannot authorize the
old steering packet while Map is still stalled. That independent gate remains.

## Reproduced changes

| Defect | Before | Change | After |
| --- | --- | --- | --- |
| Re-decode Map's own unchanged full geometry | Six real Map/control ticks perform **18** full snapshot decodes | One privately owned read-only copy per exact publication token; public SDK reads still return independent copies | **0** repeat decodes after warming; same-build invalidation, publication races and legacy reads remain valid |
| Re-enumerate immutable prefab topology during localization | Real placed-prefab test repeats chain validation **127** times after warming to **22** | Exact-value LRU for directed enumeration only; replace self-referential recursive walkers with equivalent explicit stacks | Stays at **22**; no cached positional match/ranking/authority; damaged ports/nav identity and reverse queries remain separate |
| Still-valid zero-drive refresh loses its witness during IPC | At the incident's 3.9616 ms reserve, a modeled 4.5 ms read rejects refresh and becomes a technical stop | Pin the exact original curve leaf for comparison during the already bounded zero-drive transition | Zero physical propulsion while waiting, then a new real Map/Policy/ACC/AP decision resumes; no expired throttle or renewed timestamp |
| Fetch discarded evidence inputs after publishing steering | An occupied real one-slot evidence worker still causes two large SDK/Manager reads; injecting 260 ms into each creates a 520 ms renewal outage and a real controlled stop | Check the existing worker's local availability before evaluating its input arguments; offer keeps its own guard | No discarded input reads; real Map → Policy/ACC → AP → Engine → Controller continues; no expiry or timestamp change |

`tools/reproduce_oct9_baseline.py` restores only the relevant deployed functions
in memory: all **three counterexamples fail** against the installed baseline.
It never resets a checkout, edits the installation or runs the full suite.
The targeted candidate tests pass. The refresh witness must retain the exact
original SDK frame, observation timestamp, deadline and context. A late start,
wrong frame/leaf, changed identity, future data, evidence already stale at
transition entry or an exhausted wait cannot start this transition. Expiry
during its own read permits only the comparison witness described above, never
an executable stale constraint. The existing first-fault latch is preserved.

The topology cache has independent limits: **128 entries**, **16,384 retained
curve indices**, **1 MiB conservatively charged keys/results**. Measured charged
storage on the reconstructed real route is **229,025 bytes**. Oversized entries
are not retained; source geometry/topology is still validated. Each Map keeps
at most one owned full snapshot, replaced on publication, without a worker or
growing queue.

The existing packet, dense replay and timing rows now carry
`map_reference_phase_times`: reference read, harvest, preparation publication,
selection, and at most two actual observation attempts. Attempts retain route
snapshot read, identity check, SDK read, original frame/time, localization,
liveness publication and final-validation times. These fields add no SDK/IPC
reads, no log row per tick and no second collector. They are observational,
never used to change command validity. They cannot reconstruct the missing
historical substep.

## Measurements and their limits

### Read-only localization profile on the retained route

The original 38-UID window is reconstructed from logged directed LaneIds and
physical prefab ports, against the matching installed map cache. Cache source
files are read only. Three passes use 261 retained planar poses (783 calls).
Altitude is **map-derived**, not original SDK altitude. cProfile overhead is
included. All **783 matched LaneIds are identical** before/after.

| Warm localization, 782 calls, ms | Baseline | Candidate |
| --- | ---: | ---: |
| Median | 7.9763 | 6.5755 |
| p95 | 9.4001 | 7.4044 |
| p99 | 11.1767 | 10.1156 |
| Maximum | 13.5648 | 16.8370 |

Cold first lookup stays approximately **699.5 → 696.4 ms**, primarily building
the large road-pair index and accompanying GC. It is separated from warm
control work and **is not** attributed to the historical incident: that index
had already been used to build the route. Repeated topology search is removed,
not relocated into another repeated worker. The warm maximum did not improve.

### Actual Manager IPC, same retained planar route and workload

`tools/benchmark_oct9_control_flow.py` runs actual Map → Policy → ACC →
Autopilot → Engine → Controller → SCS float mapping writes in isolated memory.
It uses a real Manager process and an **independent SDK producer process**;
Map GC cannot freeze this producer's Python GIL. Each comparison has 240
control ticks/240 new packets, 239 adjacent intervals, active PedalJournal.
Cold loading/building is outside the measured active section.

SDK/vehicle physics are explicitly modeled: fixed 4 m/s, map-derived Y, 3.8 m
wheelbase/2.1 m reference. Control producers run serially at up to 50 Hz without
catch-up; the modeled SDK aims at 60 Hz. These are software wall-time samples,
not a 5 km drive, controller calibration or full parallel-runtime scheduling.
The baseline restores deployed Map and RoadNetwork; the other real components
are the same in both runs. One run per variant does not prove a tail bound.

| Metric, ms; median / p95 / p99 / max | Baseline | Candidate |
| --- | --- | --- |
| New calculation interval | 35.279 / 61.480 / 108.302 / 279.510 | 31.829 / 39.729 / 90.298 / 174.169 |
| Original steering observation age at mapping-write start | 42.897 / 57.041 / 76.623 / 122.818 | 42.608 / 53.479 / 60.000 / **173.887** |
| Steering calculation to mapping-write start | 21.311 / 28.483 / 46.135 / 106.016 | 20.549 / 24.888 / 43.718 / **149.884** |
| Pedal-source observation age at write | 33.030 / 45.357 / 62.189 / 124.551 | 32.384 / 45.857 / 61.583 / 144.276 |
| Minimum remaining pedal validity at write | 375.449 | 324.637 |
| Steering writes over 500 ms | 0 / 240 | 0 / 240 |
| Technical stops | 0 | 0 |

Steering mapping writes are captured synchronously with the immutable accepted
AP source, before Engine runs; no concurrent AP/Map changes that source. The
actual mapping-return time is retained. This synchronous benchmark does not
claim asynchronous executor/source pairing for historical replay headers or
game consumption. The interval and age are distinct metrics. Some tail ages
**worsened**, despite a lower median/p95 interval.

On Python 3.14, observed generation-1 GC events fall **734 → 258**; longest
callback **148.954 → 129.198 ms**. This proves GC can contribute material local
latency under this workload, not that GC caused all 620/477 ms historically.
No GC threshold/freeze/disable policy was introduced.

### Independently phased producers for more than one minute

Six 75 s modeled runs use actual producers/controllers with distinct periods:
SDK 33.333 ms, Map 360 ms, traffic 460 ms, Policy 59 ms, ACC 23 ms, Autopilot
26 ms, Engine 16.667 ms; copying RPC 60/120/200 µs with three phase offsets.
Diagnostics off/on have identical physical output/margin results.

| RPC / phase | Physical writes | Remaining lease at physical write, ms: min / median / p95 / p99 / max |
| --- | ---: | --- |
| 60 µs / 0 | 3,084 | 34.940 / 212.273 / 385.900 / 402.340 / 478.220 |
| 120 µs / 3 ms | 1,795 | 38.640 / 216.760 / 380.680 / 380.680 / 450.440 |
| 200 µs / 7 ms | 1,202 | 21.200 / 146.000 / 321.600 / 375.000 / 413.000 |

Zero faults and expired physical drive writes in all six runs. Complete
publication, first consumer check, first Engine read, physical-write margins
and observation ages are in `independent-cadences.json`; a sampled read is not
labeled first arrival in historical data. Existing scoped-signal tests exercise
two stop/hold/green/resume cycles per real placed-prefab case in both automatic
modes, without another N or parking-brake writes.

## Verification

Targeted selections (overlap is not added as a unique total):

- **165 passed, 4 subtests passed**: rolling authority, handoff/cadence, native
  scoped signal cycles, geometry/route building, fresh SDK, snapshot transport.
- **93 passed** after observational additions: new counterexamples, cadence,
  automatic pedal export/history/significant event and longitudinal collector.
- **30 passed** after additional cache-invalidation cases: new tests, passive
  timing, actual worker scheduling and replay.
- **118 passed, 10 subtests passed**: activation, simple launch handoff,
  engagement safety, timing and joint producer/Engine regressions.

Sixteen steering benchmark cases and twelve longitudinal comfort cases are
**numerically identical** to the preserved Oct 8 benchmarks, including all
case metrics. No criterion/expectation was relaxed. `compileall` and
`git diff --check` are recorded in the final verification addendum below.
Full pytest remains the user's check.

Reproducible tools added here: `analyze_oct9_packet_flow.py`,
`profile_oct9_map.py`, `benchmark_oct9_control_flow.py`,
`reproduce_oct9_baseline.py`. Large JSON/profile outputs remain in the ignored
`docs/steering-audit/oct9-freshness/` directory, outside tracked evidence.
Quantiles use the sorted empirical sample at `floor(q*(n-1))` in the wall-time
analyzer; the established cadence benchmark uses its existing nearest-rank
definition. Missing times remain absent, never zero. Historical gaps with a
skipped calculation sequence are labeled observed gaps, not adjacent cadence.

## Remaining boundary and acceptance

**Unresolved:** which precise operation/scheduler pause occupied the historical
620.0964 and 476.8513 ms reference regions. The single missing channel is the
**per-operation reference-preparation timing for those exact Map ticks**. It
was not retained, so it cannot honestly be recovered from a sampled read or
the later SDK pose. Offline profiles identify removable work and GC cost but
do not uniquely reproduce the historical combination. The bounded phase field
above now preserves this channel in existing automatic exports if another
incident occurs; no separate collection or drive is requested.

The full user-requested problem is therefore **not declared completely solved**.
Expired GPS observations still cause a safety stop. The zero-drive handoff fix
does not conceal a genuine Map renewal outage. Any future deployment requires
the user's full pytest result and separate authorization; this task does not
approve installation or normal autonomous driving.

The agreed later game acceptance remains at least 5 km of controlled driving,
one N/no manual throttle, a supported red → continuous service hold → fresh
green → resume cycle and continued driving. Driver takeover on abnormal
steering, unexpected R/backwards movement, unqualified light/obstacle, stale
authority or brake failure terminates acceptance; genuine safety stopping is
never suppressed to reach the distance. This is a future acceptance definition,
not a request to perform it now, and is not met by any offline benchmark.

## Final verification addendum

- `python -m compileall -q core plugins tests tools`: exit 0.
- `git -c core.safecrlf=false diff --check`: exit 0. LF/CRLF normalization
  warnings are not source-code differences.
- These checks describe the earlier three-fix candidate. The continuation
  below adds the occupied-worker guard and completed-tick observation and has
  its own final targeted/static check result.
- Full pytest was not run. The user's existing whole-suite result applies to
  the earlier tree, not automatically to this candidate.

## Continuation: regression lineage, repeated profiles and successful export

### What changed since 221cc90

The old checkout is still at `221cc90d1132239ffbcb436e5eb68cf80d766dae`
(2026-09-11). Its checked tracked files match `git show 221cc90` after LF/CRLF
normalization. Its only status entry remains the pre-existing untracked
`route-diagnostics/`; no file there was changed. Neither this commit nor its
replay proves the exact contents of the historical installation.
`tools/audit_oct10_history.py` records normalized hashes and pickaxe history.

| Change and commit | Relative to 221cc90 | Interpretation / reproduction |
| --- | --- | --- |
| Representative prefab DFS `d61b82e`; parallel prefab DFS `9043001` | Both predate 221cc90 | Old repeated work, **not a newly introduced Oct 9 algorithm**. Warming the real placed-prefab test did not stop repeated traversal on the deployed code. Exact directed enumeration caching fixes this latent cost without caching live localization. |
| Maneuver/reference evidence stages `d10829a`; Map evidence offer arguments `933f4ed` | Added after 221cc90 | New post-publication diagnostic/evidence reads. Python evaluates the profile/traffic arguments before `offer` can discard them. The pending-worker reproduction fails against the actual installed `Map.on_tick`, independent of ACC candidate presence. |
| Fresh SDK re-read plus localization `67f8661`; post-localization validation/retry `3ef65c7` | Added after 221cc90 | Necessary freshness corrections add real reads/localization. Removing them would revive old positions. Optimize the unchanged geometry/topology around them; keep both actual observations and all authority checks. |
| `LaneSnapshotReader` transport `2b6306f` | Added after 221cc90 | Reduces wire traffic but public full-snapshot readers still materialize owned copies. Map's private publication-bound copy removes repeated decoding. This is not evidence that the transport cache itself caused the historical stalls. |
| Map remainder-only scheduling `cbcfd8a` | Added after 221cc90 | A prior performance fix: old Map waited after work. Retained; no scheduler change in this task. |
| Engine final GPS boundary `eec165c`, later binding corrections `2b6306f` / `99c4ff7` | Added after 221cc90 | Stronger final output validation exposes actual stale packets. **Old Autopilot already checked both computed_at and observation_timestamp.** This is not explained away as just a newly strict timeout. A proven renewal outage remains a producer failure, even when a final guard correctly catches it. |
| Common longitudinal arbitration `7adf8c8`, bounded refresh/deadline propagation `9350be7` | Added after 221cc90; old `core/longitudinal.py` absent | The new refresh symptom and witness race belong to this newer contract. A fresh drivetrain frame cannot renew an older curve leaf. The shared bounded refresh correction fixes the reproduced read-crossing race, not a real steering outage. |

The fourth counterexample restores only the deployed `Map.on_tick` in memory:

```powershell
python tools/reproduce_oct9_baseline.py --baseline 'C:/Users/PC/AppData/Local/Programs/UltraPilot' --busy-only --output docs/steering-audit/oct9-freshness/busy-worker-before.json
```

The tool exits successfully only if this **one selected regression fails**.
It recorded `map plugin heartbeat is stale`, a controlled stop, and the two
discarded reads. With the candidate the same production-flow test passes.
The two 260 ms injected reads model a scheduling failure; they are **not**
claimed to be the historical 620/477 ms operation. A completed future also
remains unavailable until the existing `harvest` validates it. No queue,
second worker or waiting was added.

### Repeated same-input comparison with real IPC and concurrent exports

Three pairs, baseline then candidate per pair, use the identical saved route,
240 poses per run, an independent 60 Hz modeled SDK process, real Manager IPC,
actual Map/Policy/ACC/Autopilot/Engine/Controller and float-mapping writes.
Diagnostics are enabled. Another process runs the existing replay writer and
chunked combined export/inspect on separate explicitly synthetic evidence.
The actual one-slot evidence worker additionally has an explicitly modeled
80 ms job wait. Neither its delay nor the export fixture is live ETS2 evidence.

Control producers in this wall-time benchmark are serial. Thus the gap before
the next Map tick includes Policy, ACC, AP and Engine; it is **not** the native
parallel Map scheduler's wakeup latency. The independent-cadence tests above
cover different producer phases/RPC delays separately. These are complementary
software measurements, not a complete simulation of Windows game scheduling.

`tools/summarize_oct10_profiles.py` pools **only within-run adjacent intervals**
and individually bound mapping writes. It does not join runs, average p95s or
sum overlapping operation spans. 720 new packets and 720 bound steering writes
per variant; 717 adjacent intervals. Recorded monotonic times share the same
host clock; original SDK frame/time are not replaced by a read time.

| Warm metric, ms: p50 / p95 / p99 / maximum | Deployed baseline, 3 runs | Candidate, 3 runs |
| --- | --- | --- |
| New packet interval | 35.911 / 57.118 / 125.938 / 174.712 | 34.140 / 47.273 / 107.662 / **183.365** |
| Original observation age at mapping-write start | 42.572 / 55.041 / 107.647 / 179.808 | 41.829 / **55.127** / 90.121 / **192.427** |
| Calculation to mapping-write start | 21.968 / 24.475 / 79.280 / 155.239 | 21.980 / **26.681** / **83.209** / **171.130** |
| Whole Map tick | 12.167 / 17.977 / 76.627 / 135.726 | 10.364 / 14.408 / 61.515 / 105.438 |
| Tick start through lane update | 5.707 / 6.623 / 8.785 / 125.650 | 4.775 / 5.594 / 6.175 / 7.197 |
| Lane update end through reference end (includes road-type work) | 3.893 / 8.398 / 56.185 / 99.729 | 3.102 / 6.754 / 54.440 / 98.348 |
| Steering IPC publication | 0.179 / 0.246 / 0.336 / 0.391 | 0.190 / 0.267 / 0.360 / 0.567 |
| Work after publication | 1.333 / 1.790 / 1.986 / 2.970 | 1.203 / 1.587 / 1.776 / **3.624** |
| Gap before next Map tick, serial-model boundary | 23.546 / 26.204 / 81.046 / 156.726 | 23.668 / **29.153** / **85.252** / **172.908** |
| Writes older than 500 ms | 0 / 720 | 0 / 720 |
| Technical stops / producer failures | 0 / 0 | 0 / 0 |

Per-run maximum packet interval: baseline **174.712 / 164.049 / 158.982** ms;
candidate **183.365 / 159.186 / 162.472** ms. Exact raw values are retained in
`repeated-flow-summary.json`; the table's pooled maxima are not a guarantee.
Minimum remaining pedal validity at physical write by run: baseline
**318.539 / 340.025 / 320.730** ms; candidate **306.010 / 353.206 / 335.450** ms.
No expired physical propulsion was accepted. The earlier 122.818 → 173.887 ms
age result is retained above; these additional runs do **not** erase that
regression or demonstrate an improved global maximum.

Inclusive operation profiles separate client CPU accounting and Manager calls:

| Operation | Baseline p50 wall range, ms / maximum wall, ms | Candidate p50 wall range, ms / maximum wall, ms | Typical RPC count / p50 RPC wall, ms |
| --- | --- | --- | --- |
| Warm localization call | 3.531–3.556 / 123.276 | 3.020–3.062 / 5.995 | 0 / 0 |
| Actual fresh-SDK/localization/validation stage | 1.611–1.671 / 69.480 | 1.088–1.215 / 7.694 | 21 / baseline 1.092–1.142; candidate 0.977–1.096 |
| Policy | 2.195–2.277 / 4.004 | 2.193–2.299 / 3.520 | 36 / 1.999–2.102 |
| ACC | 2.488–2.560 / 4.261 | 2.480–2.549 / 4.054 | 38 / 2.224–2.304 |
| Autopilot | 8.597–8.838 / 13.694 | 8.519–8.831 / 12.620 | 116 / 6.393–6.649 |
| Engine output | 8.409–8.731 / 141.102 | 8.712–8.852 / **156.386** | 105 / 5.914–5.996 |

RPC wall time includes server CPU, serialization, scheduling and transport;
it is not exclusively network/lock wait. `time.thread_time` isolates the
caller, but Windows CPU accounting is coarse (observed 15.625 ms steps), so
zero CPU for a short call does not mean no computation. The stored profiles
retain p50/p95/p99/max CPU and RPC distributions separately. Map's warm maximum
accounted thread CPU falls **140.625 → 31.250 ms**; Engine's maximum is
**140.625 → 156.250 ms**. Inclusive substeps overlap and must not be summed.

Worst bound write: candidate run 1, calculation **118**, original observation
age **192.427 ms**. Its source Map tick published promptly; the following
consumer/output region overlaps a **146.708 ms generation-1 GC** on the main
control-model thread. The other candidate runs' worst ages also occur at
sequence 118: **177.300 / 162.980 ms**, with **125.295 / 128.981 ms** GC overlaps.
Baseline run 1's worst age, sequence **232**, overlaps **131.392 ms** GC.
This proves GC is a material cost in **these measured software runs**, not the
exclusive source of the historical Map outage. It also explains why optimizing
Map alone does not guarantee a lower end-to-end tail. No GC thresholds,
disable/freeze policy or steering smoothing was changed. Unbounded live
scheduling/GC-tail reliability remains unproven.

Cold cache load is CPU work: baseline wall **8.310–8.447 s**, candidate
**8.321–8.386 s**; thread CPU **8.266–8.438 s** / **8.266–8.313 s**. It is measured
before activation. First Map tick wall **291.234–319.123 ms** / **297.489–312.662 ms**;
its genuinely refreshed packet observation age is **14.663–41.047 ms** /
**36.351–41.627 ms**. Startup index construction is not assigned to the already
warm historical incidents.

A separate 90-tick probe uses the exact **221cc90 Map only**, modern deployed
schema-15 network/cache and current consumers, versus today's Map. This is
an explicit compatibility boundary, **not the full old application**. No
concurrent exports or artificial evidence wait in either probe. First packet
age: **279.673 → 30.696 ms**, demonstrating why the true post-preparation SDK
read must remain. Warm intervals p50/p95/p99/max:
**33.425 / 42.175 / 144.571 / 170.448 → 34.808 / 53.394 / 94.795 / 112.060 ms**.
Bound write age: **49.469 / 63.199 / 172.168 / 181.504 →
45.164 / 57.691 / 75.017 / 92.976 ms**. One run each is insufficient for a
tail-reliability claim; p50/p95 interval did not universally improve.

### Successful-drive evidence using the existing exports

No new collector, SDK read, IPC read, disk operation or per-tick INFO message
was added for this continuation. Map retains **one** completed-tick record
and carries it in the **next immutable calculation packet** as
`previous_map_tick_timing`. It contains local tick sequence, start/end,
thread CPU, the interval since the previous finish, post-publication work,
and the original publication receipt (packet sequence, SDK frame/time and
complete route identity). It explicitly belongs to the prior tick, not the
current SDK observation. The first tick has no prior record; the very last
completed tick needs a subsequent publication to be carried. No zero or
invented timestamp fills that absence.

`map_reference_phase_times` identifies current reference-read/harvest/
preparation/selection and actual SDK/localization attempts. The two fields
are retained by the existing passive trace, dense replay and immutable
`executor.source_packet` in combined samples. Normal `plugin_stop` therefore
exports them even when no automatic disable occurs. Existing replay rings
remain bounded; they do not promise the entire start of a >5 km drive.

The isolated successful-export test uses the **actual sole SteeringExecutor**
submit/step/observer path, actual Engine capture **after** real Controller
mapping return, then existing collector finish and integrity-checked reading.
All **40** combined samples retain exactly the original submitted packet,
its completed prior-tick record and acknowledged write time. No latest replay
header is substituted. Export stays `confirmed=false`,
`runtime_authorized=false`; backend return is not game consumption.
A separate uninterrupted episode calls normal Autopilot `on_stop` and proves
the ordinary existing passive/dense files retain the same frame-bound times.
The test's original missing source was a fixture limitation: synchronous AP
mode bypasses the worker submit/observer, so it cannot supply a real
`source_packet`. The production test now invokes that real executor path;
no production validation or expectation was removed to make it pass.

Future acceptance preparation, **only after user full-suite success and
separately approved coordinated deployment**:

1. Keep UltraPilot stopped while preparing the existing combined collection.
   Use a new collection ID, `combined`, **600 s**, **0.2 s period**, capacity
   **3600** (the existing supported maximum). This covers approximately 3000
   samples, including preparation within ten minutes; it cannot certify an
   arbitrarily long drive. The passive/dense exports supplement finer timing.
2. Start normally, verify increasing accepted SDK frames/counts, valid current
   route identity, no rejection and no control fault before enabling. No
   diagnostic command grants driving authority. If this precheck fails, stop
   the procedure and preserve the export; do not begin the acceptance drive.
3. Driver performs the agreed ≥5 km controlled route including the supported
   red → continuous service hold → fresh same-signal green → resume cycle.
   Use one N, no manual throttle for the launch under test. Do not manufacture
   an emergency. Driver takes over for R/backwards movement, abnormal steering,
   stale authority, unqualified signal/obstacle, hold failure or unexpected
   propulsion. A real safety stop terminates acceptance; it is not suppressed.
4. Safely finish driving. Issue existing `finish` while the app/worker still
   run; wait for export completion/status, then successful `inspect` rather
   than assuming two seconds is enough. Normal app shutdown also creates the
   passive/dense `plugin_stop` timing exports. Disable diagnostics afterward.
5. Bind the result to **new content hashes/deployment receipt**, not the old
   commit/version alone. Analyze the first failing tick if it fails, preserving
   its current subphases plus previous completed tick/actual executor binding.
   Do not request a repetition before explaining which specific evidence, if
   any, is missing. No arm/deploy/drive has been executed or requested here.

The existing verified CLI accepts the following parameters (do not execute
until the above prerequisites/authorization):

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$runtimeRoot = 'C:\Users\PC\AppData\Local\Programs\UltraPilot'
$collectionId = 'packet-refresh-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$evidenceRoot = Join-Path $runtimeRoot 'evidence-diagnostics'
python tools/manage_maneuver_diagnostics.py arm --settings "$runtimeRoot\settings.json" --output "$evidenceRoot" --collection-id "$collectionId" --purpose combined --duration 600 --sample-period 0.2 --capacity 3600
python tools/manage_maneuver_diagnostics.py status --output "$evidenceRoot"
# After driving, still with UltraPilot running:
python tools/manage_maneuver_diagnostics.py finish --output "$evidenceRoot" --collection-id "$collectionId"
python tools/manage_maneuver_diagnostics.py status --output "$evidenceRoot"
python tools/manage_maneuver_diagnostics.py inspect "$evidenceRoot\$collectionId"
# After successful inspect and normal app shutdown:
python tools/manage_maneuver_diagnostics.py disable --settings "$runtimeRoot\settings.json" --output "$evidenceRoot"
```

### Two separate gates

| Gate / property | Result | Meaning |
| --- | --- | --- |
| **OFFLINE VERIFIED**, four concrete code counterexamples | PASS within their stated scenarios | Repeat geometry decoding, immutable topology re-enumeration, refresh witness lost across IPC, discarded occupied-worker input reads reproduced before and fixed after. Full identity, R/backend/freshness guards remain. |
| Full historical explanation of 620/477 ms | **NOT VERIFIED** | Per-operation reference timing for those exact historical ticks is missing. New timing preserves it for future successful/failed exports; no historical operation or GC event is invented. |
| End-to-end maximum age improvement / absence of all future outages | **NOT VERIFIED** | Repeated tails are mixed and some worsen. Zero >500 ms writes in these runs is not a bound for Windows/ETS2. |
| Successful existing export | OFFLINE VERIFIED | Real executor/source and mapping return retained, integrity checked, no automatic disable required. |
| **GAME VERIFIED**, ≥5 km and signal restart on this candidate | **NOT VERIFIED — awaiting verification** | Requires user's full pytest, explicit deployment approval/content verification, then their controlled acceptance result. Nothing has been deployed or driven. |

The implementation work fixes four demonstrated defects. The complete repeated
shutdown problem is **not declared definitively solved**; historical attribution
and live tail behavior remain open. The final source check confirms all **17**
installed receipt files are unchanged; candidate runtime differences are the
five files listed above (plus unreleased documentation), not LF/CRLF alone.

### Continuation verification

- **260 passed, 10 subtests passed**, one targeted selection: counterexamples,
  real Map cadence, independently phased long-running pedal producers,
  rolling GPS authority, actual evidence-worker qualification, native scoped
  signal cycles, traffic coverage, combined export, dense replay, snapshot
  transport, activation and both automatic transmission/handoff safety paths.
  It is not the whole test suite and overlapping previous selections are not
  added to this count.
- All **16** established steering cases and **12** longitudinal comfort cases
  are numerically identical to the preserved Oct 8 results and the earlier
  three-fix benchmark. No regulator, plant criterion or expectation was tuned.
- New reproducible tools: `audit_oct10_history.py` (read-only source lineage)
  and `summarize_oct10_profiles.py` (within-run paired-profile analysis).
  The existing real-flow benchmark now separates CPU/RPC/stages, cold start,
  bounded worker load and concurrent existing export. Large generated profiles,
  before-source copies and isolated collections remain ignored, outside Git.
- Full pytest is deliberately reserved for the user. Prior whole-suite success
  does not apply automatically to the current runtime additions.
- Final `python -m compileall -q core plugins tests tools` and
  `git -c core.safecrlf=false diff --check`: both exit 0 after the continuation.
  Only documentation/tool cleanup followed the passing runtime tests; no
  production edits followed the 260-test selection.

Changed implementation inventory for this packet-renewal task (other existing
working-tree modifications are preserved, not reclassified as these fixes):

- Runtime: `core/navigation/road_network.py`, `core/navigation/evidence_worker.py`,
  `core/longitudinal.py`, `plugins/map/main.py`, `plugins/autopilot/main.py`.
- Regression: `tests/test_oct9_packet_refresh.py`.
- Reproducible tools: `tools/analyze_oct9_packet_flow.py`,
  `tools/profile_oct9_map.py`, `tools/benchmark_oct9_control_flow.py`,
  `tools/reproduce_oct9_baseline.py`, `tools/audit_oct10_history.py`,
  `tools/summarize_oct10_profiles.py`.
- Documentation: this report, `PLUGIN_CHANGELOG.md`, `DEFERRED_WORK.md`.

## Deployment preparation (no installation performed)

The exact five-file frozen payload, content/receipt compatibility checks,
rollback transaction and one future driver-controlled acceptance procedure are
recorded in [PHASE7_PACKET_REFRESH_DEPLOYMENT_20261010.md](PHASE7_PACKET_REFRESH_DEPLOYMENT_20261010.md).
Full user pytest confirmation and subsequent explicit deployment approval remain
pending. No runtime file, version, settings, diagnostic arm or DLL was changed
by that preparation; it is not GAME VERIFIED.
