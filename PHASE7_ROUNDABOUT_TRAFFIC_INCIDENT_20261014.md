# Roundabout traffic intervention — 14 October 2026

Reproduced code defects corrected; final verification recorded below.
**GAME NOT VERIFIED.** The original actor poses and first emergency input are
incomplete; the whole historical incident is not declared conclusively explained.
No deployment, game operation, commit, reset or evidence deletion. The cancelled
native GPS-arrival investigation is outside this task.

## Build and originals

Starting tree: clean at `ef8ea9dbab3d2750e4a596f8946fb293eca2d2e0`.
Installation receipt: `oct14-v4`, deployed `20261014T182749606Z`, source `ef8ea9d`.
All **30 receipt hashes** and all **17 ZIP payload hashes** match the installed
files. Normalize CRLF/LF only for code comparisons; deployed byte hashes are
exact. The receipt's inherited `base_commit=787d012` is not actual source identity.
Installed ACC 1.3.1, Policy 1.1.4, Map 1.1.2, Autopilot 1.3.4, TurnSignals 1.0.2,
DLL `1.59.4-up-traffic-timed`. Current changes are an uncommitted continuation.

V4 package SHA-256:
`106e0a97f4b1a276e468fd65aa93f2db6a6f1c73e4aae0fc84d2abe46e434b8f`.

Read-only originals under `C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics`:

| Replay | Integrity / retained evidence | SHA-256 |
| --- | --- | --- |
| `steering-replay-20261014T185321.654806Z-automatic_disable.json` | valid; 318 history rows, 13 detailed writes; 30.1007 s; incomplete, 1536 capture failures | `3beb61fb61f93135f843fb21ccb256f157690d645a44878d726df289e52bbe25` |
| `steering-replay-20261014T185321.886684Z-automatic_disable.json` | valid; 1477 calculation samples, 4880 executor rows | `677b49f9f6121cdf0bcd8e1ff482037b9c29b7ca4b1db6ae64e5e6c79f7ced9c` |
| `steering-replay-20261014T185156.878145Z-manual_disable.json` | valid; 560 calculation samples, 10800 executor rows | `8325a983cf36161145b05140c7078cf5cde0d83b2ad79cca377373ffd1f55264` |

Log: user attachment `e209f637-cec2-4349-99ec-cf5f41c4c18e`.
Session join: activation `22563081435900`, session `1`, map `promods-1.59`,
dataset `d6cc7936fce4e902761abb5d`, intent `6c68e05765ad44948a2cd03f8b6f137d`,
revision 7, build `a2ce1f38adf84104907c25c3acba2cab`, geometry
`e12678e1ca5a9c4a577706b66a5f7050de2be73cf23314ccb47cb977e32c1630`.
This join applies to the automatic incident pair; the preceding manual replay
is context only and is not merged across activations.
The analysis tool uses the existing immutable replay codec; derived large files
remain ignored in `docs/steering-audit/oct14-roundabout`. Dense executor
`source_packet` fields are absent: its row headers are not used to attribute
historical physical writes. Integrity does not make missing data complete.

## Historical chronology and limits

| Time | Preserved evidence | Conclusion |
| --- | --- | --- |
| 22619.717785 | Speed 11.3230 m/s, first history traffic brake 0.00027269 | Tiny geometric demand, not measured body collision |
| by 22619.8413904 | Original hold receipt: ID 42, directed crossing heuristic, distance 80.5283 m, actor arrival 5.31979 s, hypothetical ego 4.93395 s; native gen 11047 / frame 649103370 / observed 22619.666234 | Broad heuristic was promoted to terminal stop; original actor XYZ/bodies missing |
| 20:53:03 / 22623.0434666 | Speed 0.016675 m/s, gear 0, continuous brake hold | Stop occurred; ID 42 alone does not prove an obstruction |
| 20:53:07–08 | Same-owner traffic clearance ID 42, generation 11345, bounded restart/handoff | Existing qualified restart worked and is preserved |
| about 22635.9 | ID 23, brake 0.000127177, distance 50.9902 m, actor 7.87980 s versus hypothetical ego 4.95489 s | Same early heuristic/terminal-stop mechanism |
| 22641.4863105 / 20:53:21 | First Engine `EMERGENCY_BRAKE`, winner ACC; command frame 281255416 / observation 22641.3462479; compared vehicle 281372078 / 22641.4524758 | Exact first intervention/time, but decisive input replaced by old detail-budget marker |
| 22641.4975802, **later release input** | ID 7, distance 0.228867 m, actor 4.66815 s versus hypothetical ego 0.478383 s, brake 1; gen 11867 / frame 670789309 / observed 22641.4233202 | Reproduces stationary-ego false urgency; not substituted for the missing first emergency actor |

Actual constant-speed ego arrival for the first receipt is about **7.112 s**,
not the hypothetical 4.934 s. The old formula assumes +2 m/s² even at standstill.
It can turn a possible future crossing into full braking without observed ego
motion. A second defect converts arbitrarily small broad-window demand into
`observed_conflict_stop`, allowing downstream continuous-brake terminal hold.

Native ID/slot is not a lifetime or lane/coverage certificate. Missing original
poses prevent deciding whether each recorded actor was truly turning away,
on another road, reused or correctly located. Synthetic completed inputs and
the user's empty-road observation are not historical geometric measurements.
Specifically, native `TrafficProcessor::get_uid_for_vehicle` indexes a
`vehicle_ptr → short UID` table, assigning `size + 1`; it does not export an
actor-incarnation generation. Timed source lifecycle/generation describes the
acquisition, not guaranteed object lifetime. Python retains source class, slot,
record fingerprint and actual bodies; the new continuity check rejects observed
discontinuities but cannot certify pointer reuse that is itself indistinguishable.

## Corrections

1. Acquisition-timed crossings use actual ego speed, existing headway, directed
   reference and height gates. Standstill does not acquire a hypothetical
   accelerating crossing. Actual observed overlap/swept-box AEB remains active.
   Untimed legacy captures retain conservative behavior.
2. Complete original timed moving actors with a full three-second no-contact
   body prediction supply a **positive speed constraint** to the same ACC PID:
   `route distance / (actor arrival + existing headway + half-body passage time)`.
   This neither raises a lower cap nor clears actual contact. The existing
   1 m/s contract boundary, missing bodies, truncated horizon or emergency keeps
   terminal protection. No second pedal controller or comfort filter.
3. Recompute this cap from each actual new source frame for its original owner
   until current-body recession is demonstrated or a contact/terminal demand
   supersedes it. Time-window fluctuations, zero demand or actor disappearance
   do not certify departure. A positive cap cannot clear an existing stop receipt.
4. Evaluate departure against the current native frame pair before checking it;
   reject discontinuous same-ID motion as clearance. Same-authority geometry
   publication reprojects original ownership without relabeling old outputs.
5. Engine remains the single planner presentation owner. Inactive fluctuations
   cannot announce normal driving modes; first emergency stays pinned and is
   spoken once. A 0.5 s AVOID presentation release grace does not delay pedals or
   emergency. ACC also stops generating repeated emergency output/speech after
   active/pending authority is revoked.
6. Store compact decisive actor/slot/acquisition/time/contact fields before
   optional input accounting, using the existing immutable fault codec and pedal
   history. Indexed tables are unchanged; history fields append only. No new
   SDK/IPC read, collector, worker or synchronous control-tick disk I/O.
   The complete small brake basis also survives its original 2 KiB attribution
   sub-budget via exact bounded JSON/zlib round-trip: both decoded wire bytes
   and stored bytes must fit. Traversal is bounded by the existing input limit;
   long compressible strings cannot bypass it. This fixes the unchanged
   two-crossing export equality regression found by the first complete suite.
7. Acknowledge significant-event submission only after successful background
   export. Quota failure retains one immutable pending receipt, blocks futile
   retries and lets automatic fault export embed it beside first fault/safety writes.

The significant-event quota is actually **8 files / 6,614,998 bytes**: the
eight-file limit was reached before the unchanged 16 MiB byte limit. Originals
are preserved. New normal significant-event exports require separately approved
archival of old files. Existing automatic fault/dense paths remain available;
no silent overwrite, extra collector or unbounded queue.

## Reproduction and closed model

Pre-fix logs contain eight failed checks in both modes (tiny distant terminal
stop, stationary false emergency, inactive planner speech, lost first evidence),
plus two separate inactive-ACC speech failures. Intermediate failed candidates
are retained. A departure relaxation failed the **unchanged** native-crossing
hold safety regression; current-acquisition continuity fixed it without deleting
the expectation. A later intermediate model exposed ACC ownership loss; that
candidate is not presented as successful.

The first complete run produced **7 failed / 2626 passed / 1592 subtests**.
One was the real added-attribution budget regression above; its unchanged
expectation passes after correction. The other six failed launching `git` or
native probe EXEs with Windows `0xC0000142`, before their assertions; the exact
loader/resource cause is not established. All **15 tests** in the affected
subprocess files/scenarios then passed unchanged in isolation. The corrected
codec, new cases and surrounding flow gave **79 passed**. A new complete
hash-bound run is required and is not replaced by these isolated passes.

Criteria declared before final comparison: no terminal hold, emergency,
intervention/disengagement or simultaneous positive pedals in the specified
non-contact crossing model; actual contact and unknown-data safeguards must
remain in negative tests. No post-hoc global gap/comfort PASS threshold.

Model: actual reader → Map/Policy/ACC → Autopilot → Engine → Controller/test
backend, two automatic modes, 540 samples / 18 s per case at 30 Hz. Pedal delay
0.10 s, actuator 0.35 s, nominal drive/brake 2.2/4 m/s², drag 0.12 + 0.004*v²,
120 Hz plant integration, constant actor motion. These are declared unvalidated
plant parameters, **not ETS2 calibration**. Pre-fix selector/body/traffic methods
load from `ef8ea9d` in memory; the old checkout is untouched.
The fixture executes actual producer/controller ticks but not the entire outer
application event pump; its inactive-row count is not a game-disengagement metric.

| Same inputs; identical results in modes 0 and 3 | Before | After |
| --- | ---: | ---: |
| Terminal hold samples / time | 110 / 3.667 s | 0 / 0 s |
| Emergency decision samples | 2 | 0 |
| Inactive samples | 0 | 0 |
| Minimum speed | 5.871 m/s | 9.890 m/s |
| Maximum model deceleration | 2.857 m/s² | 0.968 m/s² |
| Maximum model jerk | 5.784 m/s³ | 2.782 m/s³ |
| Drive↔brake reversals (>0.01; coast excluded) | 1 | 1 |
| All drive/coast/brake transitions | 11 | 13 |
| Observed model box-overlap samples | 0 | 0 |
| Minimum reference-centre separation | 18.406 m | 11.789 m |
| Minimum model box-boundary distance at sampled poses | 13.678 m | 7.057 m |
| Simultaneous positive physical pedals | 0 | 0 |

The two extra coast transitions and smaller model separation are disclosed,
not described as universal comfort/safety improvement. Discrete overlap counts
are not a continuous-game collision certificate or a bumper gap.
For these orthogonal model rectangles the last distance is
`hypot(max(0, abs(car_x-2.25)-3.25), max(0, abs(95.52834-ego_z)-4))`.
Those half-extents belong to the declared 2.5×6 m ego / 2×4 m car model only.

Reproduce using `PYTHONCASEOK=1` and
`python tools/compare_oct14_roundabout_incident.py --output docs/steering-audit/oct14-roundabout/another-closed-model.json`.
The tool refuses to overwrite an existing result.

## Verification and performance

New scenarios: **30 passed**. Earlier broader targeted run: **275 passed**;
subsequent added summary/model cases are included in the final full suite.
Coverage includes true contact, empty/side/far/opposite/departing actors, two
owners/owner loss, native continuity, legacy stop safety, saturated quota and
first-fault export. Existing signal hold/green/restart, R/stale/identity/backend
and launch regressions remain unchanged.

Steering: **16/16 benchmark cases numerically identical** to `ef8ea9d`.
Longitudinal comfort: **12/12 numerically identical**. Neither certifies the game.

Three alternating paired pipeline runs: 180 ticks each, 40 actors, two ego
bodies, about 6 s modeled; assertion/mock histories cleared:

| Run | Before p50 / p95 / p99 / max, ms | Candidate p50 / p95 / p99 / max, ms |
| --- | --- | --- |
| 1 | 10.179 / 10.942 / 15.441 / 19.063 | 10.212 / 10.679 / 12.046 / 19.699 |
| 2 | 10.147 / 10.608 / 11.877 / 20.786 | 10.281 / 10.815 / 12.850 / 27.158 |
| 3 | 10.361 / 12.132 / 14.414 / 36.092 | 11.015 / 11.773 / 15.674 / 36.053 |

These isolate changed route/body/traffic operations under the common current
diagnostic infrastructure, not clean-process historical-v4 runtime. They include
synthetic copied IPC and producer/backend work; no other benchmark/full suite
ran during timing. Tails fluctuate; no general speedup is claimed.
Selector motion deep size: **100,894 bytes**; detail at most **64,135 / 65,536
bytes**; six-second retained history about **47.5 KiB / 1 MiB**. These are retained
structures, not RSS or worst-case 30-second coverage. Fixed limits/loss counts remain.

The final attribution fix is measured separately on the exact same real-selector
two-crossing input, 1000 calls after 20 warmups, after the complete suite ended:
old helper p50/p95/max **0.0527 / 0.0549 / 0.1075 ms**, final helper
**0.1528 / 0.3183 / 1.0717 ms**. The old helper loses the basis; the new one
preserves it. This costs about **0.1001 ms median** on that overflow branch,
not a whole-pipeline latency measurement. Traced transient peak is **385,638
bytes** versus 2,800, including zlib scratch; discarded-result retained tracing
is 24 bytes on both sides, not the size of a retained journal/returned result.
The scratch allocation is bounded and released; fixed journal/history storage
budgets are unchanged. The earlier paired pipeline table predates this final
small-attribution fallback and must not be presented as its complete cost.
Reproducer/results remain in the ignored audit directory as
`measure-diagnostic-cost.py` / `diagnostic-cost.json`.

Final complete run: **2633 passed, 1592 subtests passed, 604.83 s**, exit 0.
`full-suite-v6.verified.json` binds all 16 runtime/changelog hashes before and
after the run; no runtime changed during it. Log SHA-256:
`d7df61f9f07d452ce199f53391426f1bedd37a121a893f2899552ad814d264d3`.
`compileall -q core plugins tools tests` and `git diff --check` pass. No safety
test expectation was weakened or removed.

Candidate: `docs/steering-audit/oct14-roundabout/ultrapilot-oct14-roundabout-candidate-v5.zip`,
619,902 bytes, **18 payload files** plus manifest/licenses, every payload
SHA-256 verified by ZIP readback against the successful runtime receipt.
ZIP SHA-256: `19d354b147b548a084d5160981cdb35724e7fb462a7fec800251d4f492a93f69`.
Sidecar: `ultrapilot-oct14-roundabout-candidate-v5.manifest.json`.
The unchanged DLL also matches its original native build receipt and source
artifact hashes. The installation's 30 receipt hashes were rechecked while
preparing the candidate. V4 remains untouched and is superseded only as the
candidate for this review. The installation is still v4.

## Runtime and remaining limits

Only ACC advances **1.3.1 → 1.3.2** for its changed inactive-authority behavior.
Policy remains 1.1.4; Map, Autopilot and TurnSignals versions are unchanged.
The same receipt-verified v4 DLL is retained as a dependency, not a new native
release. PID, geometry, steering timing, 5 m signal offset, source timestamps,
500 ms limits, parking controls and emergency arbitration are preserved.

One coherent package contains runtime dependencies, changelog, unchanged native
artifact/licenses and a manifest. It excludes tests/reports/raw evidence,
settings/cache/commit marker. V4 remains the installed historical baseline; the
new package supersedes it only as a review candidate, never deployment approval.

Exact payload (the two DLL entries contain identical unchanged bytes):

```text
runtime/core/acc_acceleration.py
runtime/core/acc_body_prediction.py
runtime/core/acc_following.py
runtime/core/engine.py
runtime/core/control_timing.py
runtime/core/longitudinal.py
runtime/core/pid.py
runtime/core/service_brake_hold.py
runtime/core/navigation/traffic_producer.py
runtime/core/navigation/longitudinal_diagnostics.py
runtime/core/sdk/traffic_snapshot.py
runtime/core/sdk/scs_sdk.py
runtime/core/telemetry.py
runtime/plugins/acc/main.py
runtime/plugins/drivepolicy/main.py
runtime/PLUGIN_CHANGELOG.md
runtime/assets/ets2la_plugin.dll
game-plugin/ets2la_plugin.dll
```

Of these, six core Python files and ACC change relative to v4; other runtime
entries preserve the coordinated dependencies. Added/updated non-runtime files:
this report, `DEFERRED_WORK.md`, `tests/test_oct14_roundabout_incident.py`,
`tools/analyze_oct14_roundabout_incident.py`,
`tools/compare_oct14_roundabout_incident.py`, `tools/prepare_oct14_runtime.py`
and `tools/verify_oct14_candidate.py`. Changelog is included explicitly.

**OFFLINE VERIFIED** is limited to reproduced defects/declared models after the
final complete suite. **GAME NOT VERIFIED** applies to new behavior. The missing
first actor pose/body record cannot be recovered from a later ID; the existing
decision boundary now preserves it without new reads. No new drive is requested
here. Separately approved deployment and a controlled passage are still needed
for game acceptance; neither can certify every junction or future actor motion.
