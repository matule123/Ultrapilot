# Phase 7: traffic acquisition, curve approach and locked signal continuation

Date: 2026-10-05. **Offline fixes verified; incident reconstruction remains
partially observed. This is not a claim of a corrected ETS2 drive.**

## Build and evidence boundaries

Input HEAD was `9350be73d256fd9e4a15c24254ad758222a7ac4e`; the tracked worktree
was clean. No `AGENTS.md` was found in the checkout or its parent directories.
`PLUGIN_VERSIONS.md`, `DEFERRED_WORK.md` and the preceding Phase 7 lifecycle,
signal and longitudinal-handoff reports were consulted. Existing records were
read only; no application/game was started, armed, deployed, committed or pushed.

The eleven runtime files checked against input HEAD were Engine, Controller,
longitudinal arbitration, ACC route selection, service-brake hold, signal reader,
Route, Map, Autopilot, ACC and DrivePolicy. Installed contents matched after
LF/CRLF normalization; Git blobs also matched installed bytes. Workspace newline
differences in Engine/Map/Autopilot were not different code. This confirms the
input implementation, **not the new uninstalled working changes**.

The existing installed `ets2la_plugin.dll` SHA-256 was
`53d8c54d2b71abb2f1d2de8cb68cd096f22f8385f750f46ce07af105295c3bcf`.
It is the previously prepared signal-sidecar candidate, not evidence that a
particular historical green was observed or consumed. No DLL change is made here.

Sources, under `C:\Users\PC\AppData\Local\Programs\UltraPilot`:

| Record | Samples / executions | SHA-256 |
| --- | --- | --- |
| `route-diagnostics/steering-replay-20261005T182758.414089Z-manual_disable.json` | 1,226 / 8,253 | `5961b1ba92ac3a9b5ef910efd30cf432bdfea451a6f23e435c9ed73cf31e625c` |
| `route-diagnostics/steering-replay-20261005T182906.053563Z-automatic_disable.json` | 726 / 3,907 | `8c7d41983f2d6acbc8de94c8851eba095437492db863bc646d7adc6b01d55d85` |
| `route-diagnostics/steering-timing-20261005T182925.634994Z-plugin_stop.json` | 435 | Timing evidence, not a physical pedal receipt |

Both replays have **zero immutable executor source packets**. No matching
October 5 combined export exists. Replay application SDK headers therefore
cannot establish the calculation-frame speed, actual pedal-write attribution,
signal colours, stop-line position or the historical ACC actor ID.

The relevant log is installed `ultrapilot.log`, supplemented by the user's
`49309d11-1b96-41aa-938e-d9c5e154b305/Vložený text.txt` attachment.
Binding: session `1`, map `promods-1.59`, dataset `d6cc7936fce4e902761abb5d`,
intent `0198eda713eb42e38a96f1537190396d`, revision `10`, build
`8f7d6fb339ad4d02a575fdea2ed1edd3`, geometry fingerprint
`12cdaa0c8765079b3c5a3e2988ae9e0db172cbbd80afebb0db2ea877f55c6fc7`.

## Historical sequence and what it proves

| Local time | Recorded event | Conclusion |
| --- | --- | --- |
| 20:26:52 | Simple-auto probe: frame 57014386, throttle 0.12, no D selector; handoff frame 57297708, gear 4, throttle 0.1408724 | Start/handoff occurred; no manual-input attribution beyond the records |
| 20:27:29 | Continuous service-brake hold logged | Hold occurred; the original brake source, locked ID and colour sequence were not retained in these replays |
| 20:27:58 | Manual N disable, followed by an N rejected for stale heartbeat | Old heartbeat age 775.94 ms, vehicle observation 793.10 ms, steering observation 810.95 ms at check 4330.808728. Rejection was correct; the exact scheduling cause is not established |
| 20:28:14–15 | Probe at 4346.8411448, then driver-held traffic wait | New activation is distinct from the previous continuous hold; it cannot inherit the old witness or signal lock |
| 20:28:23 | Cancellation at 4355.8122383, gear 4, forward speed 0.1149221 m/s | Recorded movement violated stationary pending wait. This is not evidence of a signal clearance or renewed brake ownership |
| 20:28:28 | New probe/handoff, activation epoch 4360769978400 | A new activation began |
| 20:29:05 | Engine first rejection: ACC target unavailable or unconfirmed departure | Traffic evidence was valid and identity matched; it was not an expired command |

At the first Engine rejection, checked time was `4396.8494313`, traffic frame
`188842446`, observation `4396.7296526`, computed time `4396.8378721`, deadline
`4397.2296526`. Observation age was **119.7787 ms**, decision age **11.5592 ms**,
remaining validity **380.2213 ms**, with no differing context fields.
The later Autopilot stop/hazards and release are consequences of this first
rejection. The user's observation of no car is retained as an observation,
not proof of which actor the producer selected. The historical target ID and
whether it had constrained driving were not recorded and cannot be recovered.

## Proven defects and implementation

### ACC candidate acquisition

The old ACC latched `following_required` for every geometric `candidate`, even
while passive and even when its cap could not affect the current cruise/road/
curve plan. An unrelated, far candidate disappearing could thus become loss of
required authority. This is reproduced through ABI traffic capture, the real
route selector, DrivePolicy, ACC, Autopilot, Engine, Controller and SCS float
mapping writes in both automatic modes.

ACC now acquires a protective dependency only within the current active/pending
activation when the cap lowers the existing effective target, is below actual
speed, or represents an emergency. Passive, disabled and changed-authority
states clear acquisition. A never-acquired, nonbinding candidate is not a reason
to stop on later valid empty observations. A previously acquired limiting or
hazardous candidate disappearing **still blocks drive**; legacy traffic cannot
prove clear coverage or a safe departure. Candidate geometry is not promoted to
confirmed same-lane sensing. Compact first-fault fields now preserve the acquired
target ID, status and explicit unconfirmed flag in the existing diagnostics.

This removes a proven code defect; the missing historical actor receipt prevents
claiming it fully explains the 20:29:05 acquisition.

### Curve preview ranking

The preview chose the largest curvature in its horizon without comparing the
distance-dependent approach envelope. A sharper, farther apex could hide a
nearer, gentler bend. Map now provides actual SDK speed to the existing query;
the query selects the smallest **existing** speed envelope across exactly the
same samples/horizon, with the nearer distance breaking ties. Geometric-only
callers retain the previous optional-speed-free query. No LanePath, lateral
preview, gains, geometry, safety constants or steering scheduling changes.

The existing 35 km/h cap remains restricted to identified roundabout turn
events, and tighter curvature may demand less. It is not applied globally.

The existing cache was inspected by exact recorded LaneId/placed prefab chain.
Two coherent chains were reconstructed; a 15.0038 m unrecorded gap across the
manual-disable/new-activation interval was **not bridged**. These are navigation
centreline chains, not physical boundaries or recovered complete LanePaths.

| Recorded bending region | Static evidence at recorded application pose | Interpretation |
| --- | --- | --- |
| s=0–175 m; first bend primarily s=65–174 m | 493 moving SDK rows; 247 lower envelopes. At s=46.84 m, road UID 5337536096517885871: 42.25 → 24.16 km/h, selected distance 80 → 28 m | Nearby restriction previously hidden by a farther apex |
| s=510–660 m | 349 rows; 131 lower envelopes. At s=621.39 m, prefab `blkw_2k00v`, UID 5337536178973708447: 24.47 → 22.30 km/h, distance 32 → 28 m | Same ranking defect has smaller effect in this region |

First-region assets include `dlc_blkw_48`, `dlc_blkw_51` and connecting roads;
second-region assets include `blkw_14051`, `dlc_blkw_57`, `blkw_2k00v`,
`dlc_blkw_46` and roads. None of the 22 recorded prefab asset paths independently
identifies the physical entry of the two user-described roundabouts. Therefore
**35 km/h before each actual entry is NOT VERIFIED**. These comparisons use
recorded application pose/speed, not an invented calculation-frame pairing or
counterfactual closed-loop replay. An approximately 20 km/h interior speed may
be justified by measured curvature; the old physical brake source is unrecorded.

### Signal continuation and stop location

The selector discarded a locked head when the SDK vehicle reference passed its
progress, even though the same head could still provide a fresh green. The
Engine then dropped the lock again when hold ownership transferred into the
bounded restart. Both defects are reproduced and corrected.

Acquisition is still strictly ahead. Only the already locked ID may be retained
up to 20 m behind current projected SDK progress, within the same approach,
height, authority and producer lifecycle and unchanged placement. This is a
bounded lookup, not permission to drive 20 m beyond a stop. Beyond this bound,
ambiguity, stale generation, moved/missing ID or changed authority remain
blocked. The lock survives the existing bounded restart handoff. Two original
fresh green generations spanning at least 0.1 s and clearance of all other stop
reasons remain necessary; no parking-brake operation is introduced.

The source provides head XYZ/yaw/colour, not a verified painted stop line or
SDK-reference-to-front-bumper offset. Distance is now explicitly labelled
`sdk_reference_to_signal_head`, with `stop_line_verified=false`, including the
existing compact receipt. **A guaranteed stop before the physical line remains
unsupported by these inputs.** No arbitrary front offset or fictional stop-line
geometry has been added. Historical failure to resume is consistent with the
reproduced lock loss but its exact colour/ID/other-brake history is absent.

## Paired closed-loop evidence

Same-input baseline `9350be7` versus candidate. The explicit along-path model
uses drive acceleration `(2.2*throttle-4*brake)/load`, drag `0.12+0.004*v²`,
120 ms output delay and 350 ms actuator response. Synthetic path pose is exact;
this is not a calibrated ETS2 brake, grip or lateral plant. Eight runs cover
both directions, load 1/1.4 and either 50 ms ticks or 25/40/50/80 ms jitter.
Real Policy/ACC/Autopilot/Engine/Controller/SCS mapping writes are exercised.

Untagged R40 then R15 scenario: 200 m approach, first 30 m bend, 70 m separation,
second 25 m bend. Entry metrics are the first sample at/after s=200/300 m;
braking starts at the first physical backend brake >0.02. This scenario models
the hidden-nearer-bend defect, not either physical roundabout's measured entry.

| Metric across eight paired runs | Baseline | Candidate |
| --- | --- | --- |
| First entry speed | 44.30–47.33 km/h | 28.30–28.48 km/h (R40 limit about 30.55, below 35) |
| Second entry speed | 16.93–17.46 km/h | 16.64–17.16 km/h (tighter R15 constraint) |
| First brake distance before entry | 57.23–62.85 m | 66.31–66.91 m |
| Maximum deceleration | 0.935–1.085 m/s² | 0.965–1.114 m/s² |
| Simultaneous positive backend pedals | 0 | 0 |

Model jerk is not uniformly improved. The maximum jitter/load-1 value increases
from up to 3.915 to 5.739 m/s³; jitter/load-1.4 increases from up to 2.753 to
3.481. Constant-tick/load-1 becomes 2.769 (baseline 2.742–3.130), while load-1.4
becomes 1.790 (baseline 1.593–2.475). Jerk uses differences of interval-average
accelerations divided by the following dt; irregular sampling and an
uncalibrated plant limit physical interpretation. **Earlier correct restriction
is verified; uniform comfort improvement is not.** No comfort threshold is
invented and no filter is added to hide this result.

Existing tagged R80 roundabout cases are unchanged: entry 32.93–33.57 km/h,
braking 66.72–68.54 m before entry, maximum deceleration 0.952–1.074 m/s².
Steering benchmark case results match input HEAD exactly. Seven established
ACC lead/braking/cut-in/curve/noise model scenarios also match input HEAD
numerically; the new benign-candidate lifecycle is exercised separately.

Preview-query operation cost (300 calls per implementation, 180 m two-bend
query) was median/p95 0.131/0.237 ms before and 0.186/0.259 ms after; maxima
0.580/0.391 ms. This modest operation increase is not a measured end-to-end
packet cadence or a guarantee of live scheduling. Steering is unchanged.

## Verification and reproducibility

- Seven narrow reproductions fail against the original production methods:
  benign candidate in both modes, passive/old activation acquisition, passed
  signal/head restart in both modes, and nearer-bend preview in both directions.
- Current 11 new tests pass, including two paired closed-loop entry tests, a
  malformed lost-target first-fault receipt and the 20 m lock lookup bound.
- Broad selected navigation/longitudinal/signal/export safety run: **293 passed,
  63 subtests passed**. After final receipt/tests changes, new tests plus existing
  ACC tests: **58 passed**. Counts overlap; they are not summed.
- An earlier sandbox temporary-directory `PermissionError` was an ACL/cleanup
  issue, not a test assertion. The broad run succeeded with a fresh permitted
  temporary directory. Existing directories were not deleted.
- `compileall` and `git diff --check` pass. Full pytest is left to the user.

Read-only audit:

```powershell
python tools/analyze_oct5_traffic_approach.py --baseline 9350be7 --geometry --output docs/steering-audit/oct5-approach-audit.json
python tools/run_curve_approach_bench.py --ref 9350be7 --two-bends --output docs/steering-audit/oct5-two-bends.json
python tools/run_curve_approach_bench.py --ref 9350be7 --roundabout --output docs/steering-audit/oct5-roundabout.json
```

Original data and generated large outputs remain outside tracked Git contents.
The audit requires the unchanged existing installation cache and listed records;
it neither opens game mappings nor generates new driving evidence.

## Changed files, versions and readiness

Runtime files required together for a future authorized deployment:
`core/engine.py`, `core/longitudinal.py`, `core/navigation/route.py`,
`core/sdk/signal_snapshot.py`, `plugins/acc/main.py`, `plugins/map/main.py`.
ACC is **1.1.4** (from 1.1.3); Map is **1.0.7** (from 1.0.6).
Autopilot 1.2.1 and DrivePolicy 1.0.5 are unchanged. Controller and DLL are
unchanged. No files have been copied to the application or game.

Other changes: `tests/test_oct5_traffic_approach.py`,
`tools/analyze_oct5_traffic_approach.py`, `tools/run_curve_approach_bench.py`,
this report, `PLUGIN_CHANGELOG.md`, `DEFERRED_WORK.md`.

**Offline implementation: PASS for the three reproduced code defects.
Complete requested game behaviour: NOT VERIFIED.** Remaining concrete blockers
are the missing verified stop-line/front-reference geometry, missing historical
ACC acquisition receipt, and unidentified actual roundabout-entry positions.
Autonomous holding when freshly activated from rest remains the prior explicit
limitation; an old continuous brake witness is not inherited after manual N.
Actual SDK brake consumption, hill hold, signal relevance and live comfort
remain separate game/interface questions. No further drive is requested here.
