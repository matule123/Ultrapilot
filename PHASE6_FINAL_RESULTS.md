# Phase 6 — final verification assessment (stage 3 of 3)

Date: 2026-10-02. Assessed source HEAD: **`0ed71aa32e64e79e38ff1ca4eccccb0b471d8fb1`**.

**Administrative closure: YES, within the evidence scope below. Universal
live-game validation of the current HEAD: NOT VERIFIED.** Phase 6 established
offline regression coverage and a measured roundabout entry, circulation,
complete navigated exit and following-road segment. It did not certify all
roads, all transmission modes, obstacle clearance or every physical output tick.
Historical failures remain failures; later offline repairs do not rewrite them.

## 1. Scope, builds and evidence provenance

This assessment consolidates [stage 1](PHASE6_STAGE1_RESULTS.md) and
[stage 2](PHASE6_STAGE2_RESULTS.md). Rules: [plugin versioning](PLUGIN_VERSIONS.md),
[plugin changelog](PLUGIN_CHANGELOG.md), [deferred work](DEFERRED_WORK.md), and
the existing benchmark and safety contracts referenced by those reports.
The tracked working tree was clean before this documentation task.
No controller, geometry, activation, transmission, scheduler or diagnostic
implementation changed in stage 3. No game run, deployment, pytest or benchmark
was performed. Existing analytical results were checked for consistency;
the latest collection was read-only inspected again.

| Evidence / change | Source baseline or commit | What the identity establishes |
| --- | --- | --- |
| Stage 1 offline tests and simulations | `e16e2a5eee6eb25b8c7d3d2227b6c28f83bb0116`; report/tool added in `77736d3` | Historical offline baseline, not a fresh run against current HEAD. |
| Stage 1 installation comparison / user full pytest result | Stage 1 runtime files unchanged between `e16e2a5` and `77736d3`; comparison documented in `daa57f5` | Engine, Map and Autopilot matched after CRLF-to-LF normalization. User reported a successful full suite for that state; no exact count supplied. This is not a full-suite result for `0ed71aa`. |
| Earlier game collection `164849` and stale-packet analysis | Analysis baseline `ea63a747832524eb74883c641a3935bd05cfffac` | Historical installed Map 1.0.0. Session 1, revision 8, build `1d544f9b8ccb4fe18fa51e902c4df508`. |
| Post-localization freshness repair | `3ef65c7`, Map **1.0.1** | A bounded fresh-SDK reread/relocalization when preparation consumes the budget. Verified offline; does not prove elimination of the internal long pause. |
| Latest game collection `185804` | Analysis baseline `c5cedbb78fd8881e98f07de735945039bed37061` | Session 1, revision 7, build `9aff982a062b496a83b14f8c7cfb7979`. A route build ID is not a Git commit or complete installation fingerprint. |
| Collector identity repair | Current HEAD `0ed71aa` | Diagnostics-only change, tested offline after the latest drive. It was not present in the collector that produced that drive. |

Current source plugin versions: Map **1.0.1**; the other eleven built-in
plugins **1.0.0**. No version bump is required for this documentation change.
There is no per-run historical hash inventory of every loaded module, DLL,
game input configuration and vehicle accessory. Timestamp proximity and
`commit.txt` alone cannot establish such an inventory.

### Current source versus installation

Read-only comparison: **2026-10-02 21:52 +02:00**, repository
`C:\Users\PC\Documents\GitHub\ets2la`, installation
`C:\Users\PC\AppData\Local\Programs\UltraPilot`. Only CRLF was converted to LF
for content comparison; whitespace, syntax and other characters were preserved.

| File | Checkout SHA-256 | Installed SHA-256 | Result |
| --- | --- | --- | --- |
| `core/engine.py` | `02ee602e6af0286d9a289378e52ccd767bcaa5b6b4b073745ddcc9c578380896` | `738e5a9315b6a97e8573a57dee046a5b08d61716807a473c5203f3a5713a57f8` | LF/CRLF only; installed content matches HEAD and `ea63a74` among checked revisions. |
| `plugins/map/main.py` | `24da8e3b381b07e39395a470ab4e04e0eee72b2de838ac9538684963c1e42c3e` | `7d75d7273710767a6c157f0fca2a6f5741f3061cea6ca3e167b3c494b7febb3a` | LF/CRLF only; installed content matches HEAD, `c5cedbb` and `3ef65c7`, not the earlier Map 1.0.0 baseline. |
| `plugins/autopilot/main.py` | `6564918f4a771b9a8ab0012bc56ae0d7b106d214a0c2f29fbd4dbfeba4c226db` | `fadad0fc5c30bc25508c3eb6b980424cd2bcf9e233e9c702916f8db1a84e61c3` | LF/CRLF only; installed content matches HEAD and the stage 1 baseline. |
| `core/navigation/evidence_diagnostics.py` | `ebdd19ed6e0fab57810c63ad8cb2f08ef12f90403b7878dcbfa6b4aee237f443` | `2997ee32cb432acf55ff179b3833552eb1828a01a6fbd2ce0bd6e693ee4c18eb` | **Real code difference**: installation matches `c5cedbb`/`3ef65c7`/`ea63a74`, and lacks the `0ed71aa` identity repair. |

Route, lateral controller, SteeringDynamics and SteeringExecutor were also
byte-identical to current source. Installed SHA-256 values respectively:

- `4654f6fc8360295534208056d440f38af539ba66901f2bb4ab0d81273d79d4ee`
- `39ab6a2cd3594b9b8d603dd816d76c92bcc69105981aceb99c4e22176eff05b8`
- `155838c3fbefe57d7994b461550f05d39432799442ec8687465c18a60f7ad730`
- `5741b3fa9f9f4b02a7e95cd1dcfec93377ba7b6936feca26b0d2e8cef2dc6a80`

Repository settings SHA-256:
`52e339d1996fe5d4f8f1f4991e19eb4990a1240607ffcfae477fce0ebd6992a8`,
transmission preference `0`. Current installed settings SHA-256:
`f53a8c03c2b7a6d21ac8b12a7712c8ff10f90c7eb6eb10b981bc373825b2a28f`,
preference `auto`. These configuration snapshots are not equivalent and do not
reconstruct historical settings. The latest drive's log identifies the simple
automatic branch (`g_trans=0`). Current on-disk equality does not retrospectively
prove which code was loaded in a historical process or certify the whole install.

### Latest game inputs

Collection root:
`C:\Users\PC\AppData\Local\Programs\UltraPilot\evidence-diagnostics\phase6-stage2-20261002-185804`.
Replay/timing root:
`C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics`.

| Input | SHA-256, rechecked in stage 3 |
| --- | --- |
| Collection `manifest.json` | `87b52ad60dd71d3c29f230f8079c823b715e3f3d7abd078bbddf8d129b5bf35e` |
| `steering-replay-20261002T170016.638031Z-manual_disable.json` | `d9aca4b8184389026f33c81bdcbf08ae6f013adbac2eed093ebf0bd1280d1e0e` |
| `steering-timing-20261002T170320.436567Z-plugin_stop.json` | `3338d7abf969c21aa7ed206bdb615a3aa336bce7ecd683c5c9bcb3778e9e98f9` |

Latest active identity: session **1**, intent
`84f81c0f88254c4a8d52dc3591257039`, revision **7**, build
`9aff982a062b496a83b14f8c7cfb7979`, map **`promods-1.59`**, dataset
**`d6cc7936fce4e902761abb5d`**. Read-only inspect confirms **964 samples,
47 files, integrity_valid=true, collection_complete=false**. The recorded
qualification remains `INCOMPLETE_REJECTED_COLLECTION`; `confirmed=false` and
`runtime_authorized=false`. Integrity is not collection completion or authority.

## 2. Summary of results and existing criteria

PASS below applies only to the named criterion, build and observed samples.
FAIL records an actual breach or incomplete required operation. NOT VERIFIED
means the needed evidence or acceptance criterion is absent. There is no new
RMS, comfort, cadence or stopping-distance threshold invented for this report.

| Area / scope | Evidence and measurement | Existing criterion / contract | Verdict |
| --- | --- | --- | --- |
| Lane tracking, offline baseline | 216 scenarios, 148,464 model samples; worst main-reference absolute CTE 1.304862 m; straight, both turn directions, S, roundabout, analytical 90-degree turns, noise/delay variants | Existing benchmark lane-loss indicator: absolute CTE >2.4 m. This is not a measured road edge. | **PASS — offline model scope** |
| Lane tracking, latest game segment | 1,465 immutable source observations; max absolute CTE 0.654234 m including complete navigated exit | Same stage 1 indicator, without claiming physical clearance | **PASS — measured segment only** |
| CTE RMS/p95 and heading quality | RMS 0.172367 m; weighted RMS 0.168096 m; heading RMS 0.021211 rad | No separate quantitative acceptance threshold established | **NOT VERIFIED as an acceptance verdict; measurements retained** |
| Steering smoothness | 246 confirmed sparse writes; step p95 0.027943/max 0.092132 input; rate max 0.350981 input/s | Existing controller regression benchmark remained numerically identical across its 16 reference cases. No full-rate game comfort/naturalness criterion | **PASS — recorded offline controller regression; NOT VERIFIED — full-rate game naturalness** |
| Packet renewal | 1,464 observed new-packet intervals: median 29.095, p95 56.682, max 436.595 ms | No independently specified cadence acceptance threshold; not all unsubmitted calculations are observable | **NOT VERIFIED as a cadence acceptance verdict; measurement only** |
| SDK age at confirmed game writes | 246 writes: median 73.739, max 443.063 ms; zero >500 ms | Unchanged 500 ms freshness lease plus source/route binding | **PASS — these confirmed writes only** |
| Earlier stale incident `164849` | Packet 2294 reached Engine with age 504.304 ms; uninterrupted run lost authority | 500 ms lease; continuous valid authority required for normal active driving | **FAIL — historical uninterrupted drive; safe rejection preserved** |
| Post-localization freshness repair | Reproduction max age 504.303 ->78.203 ms; exceedances 1 ->0; no timestamp renewal | Actual fresh SDK frame, identity revalidation, bounded retry, unchanged lease | **PASS — offline repair; NOT VERIFIED — exact historical-fault recurrence in game** |
| One N / simple automatic | Latest log: one request, 0.12 probe without D selector, fresh gear 4 after 212.646 ms, handoff about 290 ms after N | Bounded launch, forward observation before handoff, no R/reverse authority, safe cancellation | **PASS — 1 of 1 recorded activation; offline adverse cases PASS** |
| Launch without any manual accelerator | Engine-issued probe and subsequent forward motion are recorded; raw `userThrottle` is absent | Demonstrated absence of concurrent manual throttle would be required for this stronger claim | **NOT VERIFIED** |
| Real automatic (`g_trans=3`) | Stage 1 production-flow tests: one bounded D request, no positive throttle before fresh forward gear; timeout/R rejection | Separate real-auto activation contract | **PASS — offline; NOT VERIFIED — game** |
| Loss of navigation authority | Latest log: destination removed, revision 7 ->8; Engine throttle 0, AP false, steering 0, hazards on | Invalid route must remove propulsion/control authority, preserve causal reason | **PASS — observed output transition; NOT VERIFIED — full stopping distance** |
| Diagnostic export integrity | Latest collection: all 47 files/964 samples verify; chunk/hash/order/partial-write regressions documented | Atomic manifest exposure, hash/order checks, no overwrite, incomplete data cannot claim authority | **PASS — integrity and recorded offline regressions** |
| Diagnostic collection completion | Collector rejected `source_game_session_id` after GPS invalidation, although SDK age was 3.368 ms | Same game domain must not be rejected solely because route authority disappeared | **FAIL — recorded collection; repair PASS offline, NOT VERIFIED in game** |
| Session/map/dataset separation | Active selection has one complete domain/route identity; unknown rows excluded; current-domain reread repair rejects actual change and skips unknown/torn reads | Never merge domains or infer missing identity from an old route; diagnostics remain atomic=false | **PASS — selected-data separation and offline regressions; NOT VERIFIED — repaired live collection** |

Stage 1 recorded 506 targeted tests and separate analytical-method tests.
The post-localization repair recorded 226 targeted tests plus analytical/export
checks; the identity repair recorded 79 targeted tests. These counts describe
software checks, not independent physical experiments. The user's full-suite
PASS is retained for the earlier documented state; a full-suite result for
the current `0ed71aa` state is not supplied in the reports. No such run was
inferred or repeated here. Windows sandbox PermissionError was distinguished
from application failure in the earlier reports.

## 3. Confirmed game measurement

The following values match both stage 2 and its saved analysis
`docs/steering-audit/stage2-185804-analysis.json`. They cover **47.6389802 s /
419.7735728 m**, not an entire route or all operating conditions.
The active window is handoff **19910.3489547 s** to first Engine rejection
**19958.0769194 s**; the measured span uses source observation times.

CTE is **SDK chassis-origin LaneMatch CTE**, not a confirmed tractor axle,
trailer axle or trailer body clearance. Heading is immutable calculation
`body_tracking_error_rad`. Source speed comes from that calculation frame.
Route-domain identity, sequence and SDK frame are preserved. The 527 inactive
standing records are excluded; of 437 active combined records, 191 without
complete source-bound write confirmation are excluded from physical derivatives.
The dense source series contributes 1,465 distinct active calculation/frame pairs.
No missing numeric data are replaced with zero.

| Metric | Samples / differences | Result |
| --- | ---: | --- |
| CTE RMS / time-weighted RMS | 1,465 | **0.172 / 0.168 m** (0.172367 / 0.168096 unrounded) |
| Mean / p95 / p99 / max absolute CTE | 1,465 | 0.119133 / **0.372447** / 0.595911 / **0.654234 m** |
| Heading RMS / max absolute | 1,465 | 0.021211 / 0.083498 rad (maximum about 4.784 degrees) |
| New source-packet interval median / p95 / p99 / max | 1,464 | **29.1 / 56.7 / 65.4 / 436.6 ms** |
| SDK age at confirmed write median / p95 / p99 / max | 246 | **73.7 / 108.8 / 236.8 / 443.1 ms** |
| Confirmed writes exceeding 500 ms | 246 | **0** |
| Calculation to confirmed write median / p95 / p99 / max | 246 | 57.3 / 98.1 / 225.3 / 429.7 ms |
| Absolute steering step p95 / p99 / max | 235 | 0.027943 / 0.059936 / 0.092132 normalized input |
| Absolute steering rate p95 / p99 / max | 235 | 0.173520 / 0.266234 / 0.350981 input/s |
| Absolute steering acceleration p95 / p99 / max | 224 | 0.577990 / 1.083722 / 1.838691 input/s² |

| Navigated phase | n / observed seconds / progress metres | CTE RMS / weighted RMS / p95 / max [m] |
| --- | --- | --- |
| Approach including early launch | 144 / 4.886 / 20.622 | 0.1681 / 0.1647 / 0.2216 / 0.2596 |
| Entry | 84 / 2.579 / 16.175 | 0.2744 / 0.2710 / 0.4280 / 0.4801 |
| Circulation | 426 / 13.868 / 103.352 | 0.1832 / 0.1785 / 0.3584 / 0.5441 |
| Complete navigated exit to following road | 240 / 7.598 / 49.862 | 0.2577 / 0.2518 / 0.6130 / 0.6542 |
| Following road | 571 / 18.637 / 227.563 | 0.0714 / 0.0716 / 0.1515 / 0.1777 |

Phase durations/progress omit inter-phase intervals; the whole same-identity
series includes them. The exit is proven by directed LaneIds through
`dlc_blkw_46` UID `5337536179565107919`, connector `(3,0,6)`, road
`5337536096979258520`, `dlc_blkw_51` UID `5337536179162457633`, connector
`(4,6,2,5)`, and following road `5337536093846112063`, direction 1/lane 1.
This is navigation evidence, not an obstacle-boundary survey.

RMS is sqrt(mean(CTE²)). Time-weighted RMS uses left-held CTE² multiplied
by actual time to the next valid sample, divided by total included time,
then square-rooted. There is no terminal artificial weight or bridge across
identity changes, invalid samples or gaps >500 ms. Percentiles use linear
interpolation. Steering rate uses actual backend-return time differences;
acceleration uses the separation of interval midpoints. The 246 confirmed
writes span 11 separate sparse segments, 41.722 s /373.586 m. Derivatives do
not establish maxima of every physical 60 Hz write. A later SDK response is
not automatically attributed to a command in the same diagnostic row.

No stale-steering event is documented in this latest active window. Its
termination is GPS destination removal followed by revision invalidation,
not diagnostic completion. The replay's `manual_disable` filename does not
replace the first causal log event. Last replay execution is 19958.080375 s,
79.038 ms before collector rejection; it cannot establish post-rejection driving.

## 4. Remaining limitations and verdict impact

| Open item | Exact limitation | Verdict impact |
| --- | --- | --- |
| Section described as “after toll” | End prefab `dlc_blkw_94`/UID `5337536182924768567` is not identified as a toll passage; no bound continuation after rejection | **NOT VERIFIED** for that section. Does not invalidate the measured complete roundabout exit. |
| Current collector repair (`0ed71aa`) | Installed collector remains older; rejected historical new identity value was not saved. Old value 1 is recorded; absent-value failure is demonstrated by production reproduction, not an invented historical value | Blocks a live PASS for corrected collection completion and whole-current-HEAD certification. |
| Post-localization repair (`3ef65c7`) | Current installed Map matches repaired code; latest drive has no recorded stale event. Historical internal pause and identical-fault live before/after reproduction are not established | Offline repair PASS; no claim that future stalls are eliminated. Does not negate measured freshness PASS. |
| Long reference pauses / latency tails | Latest reference-phase max 419.953 ms; earlier 456.155 ms pause. Exact suboperation/OS cause is unproven. Offline age improvement did not shorten forced packet gaps | Blocks a guarantee of continuous future cadence. Backlog item, not a failure of all latest measured writes. |
| Smoothness and naturalness | Sparse physical writes, no full-rate comfort criterion, no demonstrated acceptable replacement for original preview | Blocks a universal naturalness PASS. Measured derivatives remain usable; original controller is retained. |
| Simple-auto manual-input exclusion | Raw accelerator input absent | Blocks “no possible manual throttle” proof, not the recorded Engine probe/forward-gear/handoff sequence. |
| Real automatic and complete controlled stop | Real-auto launch only offline; post-invalidation full stopping trajectory absent | Game verification **NOT VERIFIED** for these specific contracts; no new drive required to close this assessment. |
| Broader identity and environment coverage | GameWatcher counter identifies observed process session, not a complete game-profile identity; historical whole-install/DLL/settings inventories incomplete | Blocks generalization to all profiles, devices, modes and installed builds. Selected samples are not merged across unknown identity. |
| Overswing, swept-envelope clearance, trailer tracking, AR rendering | No universal confirmed physical surface/profile; no measured full-trailer clearance in Phase 6; AR flicker remains deferred | Out of this verification scope. Blocks any claim of safe autonomous overswing or resolved AR rendering. Existing code is preserved. |

The historical `164849` stale failure and the `185804` collector completion
failure remain visible alongside offline repairs. No integrity-valid collection
is promoted to a confirmed physical profile, complete run or runtime authority.

## 5. Closure and next development

**Close Phase 6 administratively as a bounded verification exercise.** Retain
the offline baseline PASS, latest observed lane-indicator/freshness/activation
and authority-removal PASS, historical failures, and all NOT VERIFIED items.
Do not label the complete current release “game certified” or universally safe.
No new drive is requested by this stage; evidence already supports the measured
roundabout exit and following-road results.

Move to the backlog: live confirmation of the collector identity repair;
unresolved long-pause cause; real-auto live activation; full stopping trajectory;
missing raw manual-input channel; deferred steering naturalness, AR and overswing.
Future verification should address a named gap rather than repeat the whole
route or treat another pytest result as a game experiment.

**Proposed next independent task: throttle/brake and ACC arbitration under
existing evidence limits.** First document ownership/priority of manual override,
navigation safe stop, collision braking and ACC intents. Reproduce stale/missing
lead-vehicle observations and simultaneous brake/throttle demands offline through
the existing Engine output boundary. Acceptance must retain zero positive drive
under lost authority or reverse conditions, avoid simultaneous positive throttle
and braking, and preserve simple-auto protection against braking into reverse.
Define longitudinal tracking/comfort criteria before tuning; do not assume
unobserved traffic is clear. No ACC implementation or tuning is part of this task.

Stage 3 validation is documentation consistency, read-only hash/integrity checks
and `git diff --check`. No additional pytest or repeated controller benchmark is
needed for these documentation-only edits. This does not fill the separately
unreported full-suite status of the latest runtime repair.
