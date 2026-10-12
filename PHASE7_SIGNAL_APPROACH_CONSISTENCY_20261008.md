# Phase 7 — signal admission, approach and holding consistency

Date: 2026-10-08. Scope: the evening Oct 8 incidents, existing producer →
signal selection → DrivePolicy/ACC → Autopilot → Engine → Controller flow.
No installation, game input, commit, new collector, controller tuning or
timeout increase was performed. Earlier local fixes are preserved.

**Verdict: reproduced software causes corrected and verified offline.
The historical driving result, physical stop-line accuracy and SDK hill-hold
effect are not certified. No additional drive is requested by this task.**

## Build and evidence binding

Repository HEAD is `787d012a2a78ac917bb5506e0958c32d8d06575f`, with existing
uncommitted work. Installed `manual-deployment.json` names that base commit,
local additions, Autopilot 1.3.0 and the user's full-suite PASS for the previous
stop-lifecycle candidate. All seven installed hashes in that receipt still
match. This is an incremental local deployment, not a claim that its files
equal pristine HEAD. At task entry the relevant installed/source contents
matched after LF/CRLF normalization, including Engine, Controller, longitudinal
flow, signal/hold modules, transmission observer, Map, ACC and DrivePolicy.

The installed baseline SHA-256 values used for comparison are:

| File | Installed SHA-256 |
| --- | --- |
| `core/engine.py` | `346e510f2395642bbbbaae0f6a8e5d7f696a2598bd121a983678c2804b09e8f9` |
| `core/longitudinal.py` | `7679f68fa210e733782a8fda012c5cacbccf4a884f53478654faff39473fa3fd` |
| `core/service_brake_hold.py` | `0ca5975066e5eedd3c5504add58ce1fc81313f0d253dec60de08be489ed68f3f` |
| `core/sdk/signal_snapshot.py` | `b3029704aba1c10944c7f8edc583345d7e876f1200174b61e117008d4fcebf8c` |

The candidate changes those four modules, `core/transmission_mode.py` and
`plugins/autopilot/main.py`; it has not replaced any installed file. Only
Autopilot's implementation changes among plugins: 1.3.0 → **1.3.1**. Map
1.1.0, ACC 1.1.4 and DrivePolicy 1.1.0 are not released again. No DLL changes.
The ignored `docs/steering-audit/oct8-common/runtime-identity.json` records
the full receipt, exact hashes and normalized comparisons.

Five specified replays were decoded with the existing `inspect_replay`.
All passed integrity validation; integrity does not prove complete evidence.

| Replay timestamp (UTC, 2026-10-08) | Evidence | Count / coverage |
| --- | --- | --- |
| 17:55:42.756248 automatic disable | Pedal incident | 281 regular + 16 change rows; 30.043 s; 18 detailed events |
| 17:55:42.842441 automatic disable | Dense steering | 119 calculation / 4,780 execution rows |
| 18:03:28.669987 manual disable | Dense steering | 1,337 / 10,800 rows |
| 18:06:32.932802 automatic disable | Pedal incident | 212 regular + 6 change rows; 30.002 s; 17 detailed events |
| 18:06:33.064412 automatic disable | Dense steering | 3,600 / 10,702 rows |

Both pedal histories report complete summary coverage but detailed-ring
capacity loss; each overall incident is incomplete. The last dense replay
does not contain immutable `executor.source_packet` receipts. Its headers
are not substituted for physical-write attribution. Full file hashes,
identity receipts and extracted events are in ignored `oct8-common/evidence.json`;
original captures/logs remain unchanged in the installation.

## Separate activations and first causes

| Local time | Proven observation / transition |
| --- | --- |
| 19:55:36.853 → 19:55:37.213 | One N, simple-auto 0.12 probe without D selector; handoff with gear 7. Revision 7, intent `fac89b73c5dc4d6caba8e1b35981d8b0`, build `e27e2992cf884ba88eb6b1fedef34b6c`. |
| 19:55:42.738 | Engine first fault: `vehicle motion observed during continuous service brake hold`. SDK 89013106, original observation 22716.5393337, checked 22716.5797246; speed −0.0523500293 m/s, gear 0. |
| 20:02:17 | Separate process/session activation succeeds. Integer session 1 is reused; intent, build and monotonic acquisition distinguish it from the first run. |
| 20:03:28.366 | Manual N disables; this is not an automatic failure. |
| 20:03:28.825 → .912 | Immediate subsequent N begins a probe then cancels with stale navigation-readiness confirmation. SDK age is about 5.38 ms; the rejected summary's original contents/time are not retained. |
| 20:03:34.930 → 20:03:35.345 | New N succeeds. Revision 8, intent `73b6e8a4096348caa2578318f7f7e49c`, build `ef0a5e4721de41b8ade8b3848e6aea21`. |
| 20:06:32.638 → .659 | Mode observer publishes unknown, `game log changed during read`; Autopilot then incorrectly reports `forward gear is no longer confirmed` while in continuous service holding. |
| 20:06:33.168 | Mode 0 returns with the previous generation/log identity. This does not restore the disabled activation. |

The first fault's pinned command uses SDK 88946442, observation
22716.4861939, computed 22716.5392583, expiry 22716.9685185; source
`traffic_light`, requested brake 0.0000074556. The actual held brake was
approximately **0.0001640716**. Identities agree and about 388.794 ms of
lease remains: this is not expiry. Earlier positive braking declined with
the distance/speed profile and the final tiny value became the hold floor.
The motion guard correctly rejected the observed rollback; it is unchanged.

In the second run, the admitted brake chain began at 23206.2382342 with
source **ACC**, not traffic light. The consumed signal was invalid/unknown,
ID 1, lock null, reason `prefab semaphore ID missing or spatially ambiguous`,
relevance `directed_prefab_control_unobserved`. Ordinary ACC speed braking
was promoted into a planned wait because a prospective unknown signal also
appeared in the input. Continuing positive signal demand subsequently
inhibited drive even well below the approach speed cap.

The longest identity-matched 3–4 km/h section has 2,860 rows, application
times 23214.0786476–23350.9216105 (**136.843 s**) and calculation progress
delta **132.799 m**. Calculation frames 585493246–722137780 and application
frames 585559910–722187778 differ. This is sampled speed and LanePath progress,
not contemporaneous bumper distance or an immutable physical-write trace.

The final fault uses SDK 737753822, observation 23366.4878531, speed
0.0000839 m/s and gear 0. Held brake is about 0.10944527. This stop was lost
because mode evidence became unavailable, not because zero gear proved a
selector change. Racing historical game-log bytes were not saved; ordinary
append versus rewrite cannot be proven from that historical receipt alone.

## Actual prefab classification and stop geometry

Read-only map data: `promods-1.59`, dataset `d6cc7936fce4e902761abb5d`;
descriptor `dlc_blkw_80`,
`prefab2/cross_temp/blkw/blkw_r2_x_r1_t_narrow_tmpl.ppd`.
Semaphore controls on curves are `(10,3), (16,1), (23,0), (25,3), (30,1)`.
The no-control sentinel is **−1**; ID 1 is an authored group, not that
sentinel. It does not establish that every placed template has a live head
or that an arbitrary nearby head governs this directed passage.

The tracked 39 KiB fixture contains the descriptor, two actual placements,
six nodes and source hashes, not a fabricated intersection. Real parser,
directed connectivity and coordinate transforms reconstruct chain
`(30,4,13,24)` with these entry positions:

| Incident | SDK/world XYZ of derived entry | Recorded final derived distance |
| --- | --- | --- |
| First | 34657.77564184687, 5.1015625, 45994.6097625493 | 19.761 m |
| Second | 34753.47350066377, 6.90234375, 45663.9580174013 | 2.084 m |

Positions match the recorded stop targets. Reconstruction validates these
real ID-1 groups, not an otherwise missing historical complete LanePath/head
list. The raw descriptor semaphore table alone cannot identify a physical
head's presence. Stop targets still subtract the existing **unmeasured** 6 m
front allowance and 2 m stand-off from entry progress. The SDK reference is
not the measured front and the curve entry is not the painted stop line.
No global offset or geometry was moved to accommodate the complaint.

## Repairs and baseline reproductions

Nine assertion failures were reproduced with the installed methods loaded
read-only into the same production-component harness. They are not fixture
exceptions: two actual-map false stops, two unrelated ACC stop admissions,
one nearer unobserved group masking a qualified head, two weak holds,
one ordinary-log append rejection and one immediate-N stale-summary rejection.

| Proven software cause | Candidate correction | Safety retained |
| --- | --- | --- |
| Prospective map ID creates unknown required stop without head corroboration | Admit only a unique live producer head matching directed placed ID/XYZ/height/orientation; bound retained admissions to 128 passage records and authority/lifecycle. Unobserved nearer groups cannot mask later qualified heads. | Losing a previously qualified head retains an unknown stop dependency. No inferred green, lane association or clearance. |
| Unrelated ordinary ACC brake latches future signal wait | Bind stop admission to winning source and its actual stop contract; ordinary overspeed/curve braking is not following or a signal stop. | Genuine following/toll/signal stops remain latched; disappearance does not prove clearance. |
| Tiny last deceleration request is frozen as hold | Save the strongest **successfully written** brake within this same admitted chain; use it once holding/stationary. Moving positive approach adjustment is unchanged. | No fresh stationary brake edge, arbitrary holding constant or parking writes; rollback guard and backend checks remain. |
| Append changes game-log stat during observer read | Bounded raw-byte acquisition; at most one prefix-verification read. Parse only complete lines of the captured immutable prefix. | Rewrite/truncate/replacement, disagreement and unconfirmed mode/profile remain rejected; no previous result retimestamping. |
| Old readiness summary blocks current valid navigation after manual N | For GPS only, fully revalidate actual lane authority, packet freshness/identity and current engagement alignment rather than treating summary time as decisive. | Original summary untouched; stale packet/heartbeat, misalignment, revision changes still reject. |
| Unknown mode is misreported through zero-ratio branch | Autopilot/Engine preserve the actual mode-evidence failure before ratio fallback and retain exact compared snapshot in the existing first-fault export. | Real loss still disables safely and cannot automatically reactivate when evidence returns. |

Recovered actual same-passage red/yellow evidence remains available to acquire
the release lock even when its current distance-profile brake is zero.
Green restart still requires the same locked ID, authority/lifecycle, newer
producer acquisitions and existing confirmation interval; other latched
reasons cannot be cleared by a missing actor or signal.

HUD uses the same qualified signal slot: an unobserved map ID has no fabricated
red candidate. Previously observed but now unavailable control remains clearly
unknown. Existing detection-only display and bounded diagnostics are preserved.

## Same-input before/after measurements

Both modes 0 and 3, supplied 120 fresh SDK ticks over 5.95 s at 0.97222 m/s,
red 102 m ahead, following an ordinary ACC overspeed request:

| Measurement | Installed baseline | Candidate |
| --- | --- | --- |
| Positive drive / brake ticks | 0 / 120 | 120 / 0 |
| Falsely admitted planned hold | braking | absent |
| Active / simultaneous positive physical pedal pairs | true / 0 | true / 0 |
| Actual-map ID-1 required stops with no corroborating head, two placements | 2 | 0 |
| Stationary hold after actual 0.125 deceleration write | 0.0002356021 | 0.125 |

Speed in that test is supplied, not simulated progress or an ETS2 outcome.
It proves removal of the false inhibition, not that historical 133 m creep
has been measured again after repair.

Separate closed-loop model: existing uncalibrated plant
`a=(2.2*T−4*B)/1.4−0.12−0.004*v²`, 0.12 s transport, 0.35 s actuator,
integration ≤10 ms, deterministic 33/50/80 ms jitter, 4 m modeled front.
Identical model runs in both automatic modes produce:

| Initial speed | Brake onset before entry, both | Stop time before → after | Modeled front gap before → after | Crawl time / distance, both | Peak deceleration, both | Peak model jerk before → after |
| --- | --- | --- | --- | --- | --- | --- |
| 20 km/h | 31.725 m | 23.339 → 23.339 s | 5.444 → 5.444 m | 3.345 s / 2.220 m | 0.971 m/s² | 6.638 → 6.638 m/s³ |
| 35 km/h | 67.765 m | 20.842 → 20.792 s | 5.578 → 5.579 m | 3.723 s / 2.524 m | 1.153 m/s² | 4.243 → 5.777 m/s³ |
| 50 km/h | 99.307 m | 20.449 → 20.316 s | 5.637 → 5.640 m | 3.843 s / 2.638 m | 1.629 m/s² | 2.580 → 5.553 m/s³ |

Crawl is the red interval with speed 0.3–1.2 m/s, integrated over actual
adjacent sample dt/progress. It is unchanged for a normally qualified red.
Drive/brake changes are two at 20/35 km/h and one at 50 km/h (starts braking),
unchanged. All six candidate runs stay active, resume without another N,
have zero brake-zero edges while holding, zero pedal overlap and no parking
writes. Above 0.5 m/s, peak model jerk is unchanged (2.020 / 4.243 / 2.580
m/s³ respectively). **Peak jerk near standstill increases at 35/50 km/h**
with stronger holding. This is a disclosed safety/hold tradeoff, not a comfort
PASS or measured physical jerk. No acceptance threshold was invented.

The light-slope/load test models 0.12 m/s² grade with 1.4/2.2 load factors,
using actual written brake and the same modeled full-pedal deceleration.
It stays stationary in that model. Supplying the real −0.0523500293 m/s
still triggers the unchanged 0.05 m/s motion guard.

## Timing, regression verification and reproducibility

The two timing captures pass integrity validation. Only identity/Map/publish
matched rows are included below. Samples lacking that complete binding are
excluded, not treated as zero latency. Read time is sampled consumption,
**not first delivery**.

| Timing UTC | Total / matched | SDK age at sampled read median / p95 / max | Lane update → calculation median / p95 / max | Publish → sampled read median / p95 / max |
| --- | --- | --- | --- | --- |
| 17:57:45.836124 | 409 / 293 | 38.427 / 131.964 / 241.112 ms | 13.980 / 199.428 / 242.741 ms | 13.887 / 119.120 / 212.472 ms |
| 18:07:08.035308 | 1,087 / 590 | 35.484 / 220.886 / 262.738 ms | 16.401 / 30.886 / 262.433 ms | 10.686 / 200.515 / 235.881 ms |

No matched SDK age exceeds 500 ms. These timings do not establish a stale
steering cause for either first intervention. Scheduler, steering cadence,
geometry, lateral calibration/regulator and the 500 ms limit are unchanged.

- Baseline targeted counterexamples: **9 failed** (20 deselected); same
  assertions pass on the candidate. Existing real-head-loss fixtures now first
  establish actual producer corroboration. The missing-ID test still rejects
  control/green; it no longer assumes an unobserved template means required red.
- Final candidate: **267 targeted tests and 20 subtests passed in 48.73 s**.
  They cover both automatic modes, actual-prefab admission, multiple wait/green
  cycles, source changes, lost/stale/ambiguous heads, observer append/rewrite,
  immediate N, stale SDK/packets, R, identity changes, backend faults and the
  existing automatic/combined export regressions. Earlier overlapping runs
  are not added as unique tests. The full suite was not run.
- A malformed-key counterexample discovered in the new bounded admission
  code initially raised `TypeError`; the same identity rejection now runs
  inside the selector's fail-closed path. This is not attributed to the
  user's historically unrecorded crash. Its regression passes.
- `compileall` and `git diff --check`: **PASS**.
- Steering benchmark: all **16 cases exactly equal** to the previous candidate.
  General longitudinal comfort benchmark: all **12 cases exactly equal**;
  modeled emergency response remains 0 s. The separate near-stop change above
  is not hidden by those unchanged regulator benchmarks.
- No new diagnostic memory budget, SDK/IPC reads for diagnostics, synchronous
  export I/O, or new traffic/DLL interface was introduced.

Reproduce the read-only evidence analysis and installed-method comparison:

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python tools/analyze_oct8_signal_stop.py --output docs/steering-audit/oct8-common/evidence.json
python tools/run_oct8_signal_approach_bench.py --baseline-runtime 'C:\Users\PC\AppData\Local\Programs\UltraPilot' --workdir docs/steering-audit/oct8-common/reproduce-model --output docs/steering-audit/oct8-common/reproduce.json
```

The model work directory must be new; the tool refuses to overwrite it.
Raw measurements remain ignored under `docs/steering-audit/oct8-common`.
Repository additions are the small real-prefab fixture, narrow regressions,
analysis/benchmark tools and this report.

## Remaining limits and runtime scope

No Oct 8 traceback/fatal/crash entry was found in the preserved log or crash
files. Older failures are not evidence for this reported crash. It is **not
claimed repaired**. The original rejected navigation summary and historical
racing game-log bytes were not exported: the corresponding code defects are
reproduced, but their precise historical trigger cannot be reconstructed.

Painted stop line, real vehicle-front extent, installed head/lane coverage,
SDK input consumption and holding under actual slope/load remain unmeasured.
Never-qualified map groups are detection metadata; this does not prove that
no physical light exists. The map/producer cannot guarantee all intersections.
New standstill activation without an existing forward-started brake chain
still cannot promise autonomous holding in simple automatic. Genuine unknown
clearance or technical loss cannot automatically restart.

Candidate runtime scope for a separately approved deployment: six Python
files listed above; no DLL, settings, controls or map-geometry replacement.
Documentation/changelog and existing pending diagnostic fixes must be retained
as one coherent working tree. This task neither deploys nor requests a drive.
The user's full pytest suite remains the next verification gate:

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python -m pytest tests -q
```
