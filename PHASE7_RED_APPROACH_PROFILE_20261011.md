# Qualified red approach: distance profile and terminal brake continuity

## Criteria fixed before modification

This is an offline software/model investigation, not measured ETS2 dynamics.
Preserve all local changes and the deployed packet-refresh/green restart path.

- A qualified far stop is a speed constraint for the existing speed controller,
  not an independent pedal controller. A below-profile moving vehicle must not
  be trapped by a tiny old signal brake. Preserve the locked head/authority.
- Near the derived target, retain forward-started uninterrupted positive
  service braking through standstill. Never seed a new brake edge at rest in
  simple automatic mode, write parking brake, or overlap positive pedals.
- Red model-front entry overruns must remain zero. Report reference stop gap
  separately from front gap; the prefab entry is not a measured painted line.
- Compare identical 20/35/50 km/h inputs, both gearbox modes, several approach
  distances, delayed actuators and irregular ticks. Report time/distance below
  5 km/h while more than 10 m from the derived target (an analysis band, not a
  new runtime speed floor), stopping gap, deceleration, jerk and pedal changes.
  No ETS2 comfort threshold is invented to label model measurements PASS.
- Fresh same-head green, including while moving, must still clear only after
  the existing two-acquisition confirmation. Other braking, missing/stale/foreign
  evidence, R, backend failure and cancellation remain protected.
- Do not change steering, geometry, gains, source timestamps or 500 ms limits.

## Verdict and evidence boundaries

**OFFLINE VERIFIED:** the moving signal-approach brake latch can trap a truck
well below its current stopping-speed envelope; competing far-signal pedal
requests reset the speed controller. Both defects have failing production-flow
counterexamples and are corrected. A late fresh red also inhibits a previously
validated positive throttle before physical I/O.

**NOT VERIFIED:** the exact source of the first harsh brake in the Oct 11 game
run. The retained record does not contain its consumed signal, countdown, stop
distance, first pedal decision or first backend write. The model is not a
reconstruction of those missing values. Neither uniformly better terminal jerk
nor new ETS2 behavior is established. This is not a complete game-comfort PASS.

## Build and read-only artifact audit

- HEAD: `787d012a2a78ac917bb5506e0958c32d8d06575f`, with inherited local
  uncommitted changes. No checkout, reset, commit, deployment or game operation.
- Installed receipt: `manual-deployment.json`, backup/build label
  `signal-timing-reactivation-20261010T200737Z`, base commit as above,
  `local_uncommitted_changes=true`, `game_verified=false`.
- All **20 installed receipt hashes match**. Before this task the corresponding
  source contents also matched after CRLF/LF normalization. The new coordinated
  five-file candidate below is now different; the installation was not modified.
- Installed Autopilot 1.3.3, Map 1.1.1, ACC 1.1.5, DrivePolicy 1.1.1,
  DLL `1.59.3-up-signal-scope`. Only ACC/DrivePolicy implementation versions
  change to **1.1.6 / 1.1.2**, respectively. Core changes do not release Map,
  Autopilot, HUD or the DLL.

Existing codec/integrity checks accept all seven Oct 11 exports, without changing
their bytes:

| UTC filename suffix | Type / retained scope |
| --- | --- |
| `052725.559870Z-automatic_disable` | Pedal incident, about 30 s summary |
| `052726.494167Z-automatic_disable` | Dense replay, earlier revision 8 |
| `052903.787999Z-manual_disable` | Dense replay, revision 11, separate activation |
| `053054.274558Z-automatic_disable` | Pedal incident, about 30 s summary |
| `053054.624800Z-automatic_disable` | Dense replay containing the slow approach |
| `052522.527336Z-plugin_stop`, `053106.968020Z-plugin_stop` | Passive timing |

The dense file is
`steering-replay-20261011T053054.624800Z-automatic_disable.json`: 2,190 samples
and 6,429 execution records. The low-speed band contains 379 original application
samples at monotonic **945.4952287–965.1591499 s**, lasting **19.6639212 s**,
progress **408.1454253–426.4943076 m**, a displacement of **18.3488824 m**,
speed **3.109–4.924 km/h**. Its application identity is session 1,
map `promods-1.59`, dataset `d6cc7936fce4e902761abb5d`, intent
`bb76e9f714ee4068b3e9217dfe92386a`, revision 11, build
`0fc616442368403b9f4dfb9ca468a5d8`, activation `938003511100`.
The preceding manual replay uses activation `887539537900`; it is not joined
across activation boundaries to invent a pedal chronology.

The later pedal history starts at **1016.061 s**, after the slow band. It also
reports **1,603 capture failures**, 2,635 regular / 224 change samples aged out.
The earlier incident history covers 807.348–837.369 s and has 153 capture
failures. Neither retained history provides the controlling signal at the slow
band. The short detailed backend journal near the later fault is not evidence
for the original approach. There is no matching newer combined collection.
Integrity proves the retained bytes, not completeness or causal pairing.

Today's earlier projection failure and later removed GPS target are separate
navigation events; they are not attributed to signal creep. The user's reported
successful route and green restart are preserved as that observed scope, not
generalized to every activation/export on this date.

## Reproduced causes and changes

| Reproduced original behavior | Corrected contract |
| --- | --- |
| At 42 m, Traffic supplies an independent positive signal pedal and Policy supplies an auxiliary brake; ACC treats this as external braking and resets its speed state. | Outside the terminal reserve, a qualified observed signal is one distance speed constraint owned by the existing ACC output. Policy keeps other lower constraints; Engine retains protection when ACC/qualification is unavailable. |
| After an acknowledged early signal brake, Engine latches `continuous_service_hold`, zeroes drive and retains a tiny positive brake even when fresh speed is far below the current distance envelope. | `approaching` locks the same head/authority but is **not** a stationary positive-brake-chain witness. A fresh same-head red profile can coast/recover while moving. Actual terminal braking/holding still requires the physical forward-started positive chain. |
| Policy smooths a stop ceiling belonging to the previous position; after disturbance the recovered profile can remain unnecessarily low. | Smooth the non-signal preference and then apply the current signal envelope. Separate `signal_stop_control` availability from `signal_brake_selected`; a lower independent speed limit remains effective. |
| A speed-squared request can fade at an exhausted zero-speed stopping envelope against modeled idle load. | Preserve the existing full terminal demand at zero envelope. No new arbitrary holding pedal, parking actuator or minimum driving speed. |
| A new red publication during steering I/O can arrive after the green throttle decision was checked. | One bounded Traffic-contract read immediately before positive drive I/O can only inhibit drive. Retain its original source deadline in the selected decision; recheck identity and time after reads/diagnostic binding. It cannot clear a hold, authorize drive or retimestamp an older command. |

The ACC PID gains, original SDK timestamps, 500 ms leases, route geometry,
steering implementation and native DLL are unchanged. Existing 2 km/h pedal
hysteresis is reused. Following a signal brake, normal response-sized profile
deficits coast; recovery is allowed for a deficit larger than the existing
planning acceleration times response-plus-lease reserve. This is not a new
minimum approach speed or a second controller. The existing terminal guard and
same-head two-acquisition green confirmation remain separate safety transitions.

Hold ownership is tied to activation/route and actual Controller receipt
sequence. A permitted moving zero-brake write ends the old positive chain; its
peak is not reused as a new stationary witness. Unknown/missing heads, another
latched stop, emergency, stale/foreign data, R, reverse motion, backend failure
and cancellation do not authorize recovery. Successful writes remain software
receipts, not proof that ETS2 consumed an uninterrupted input.

### Stop target and front reference

No stop coordinate or geometry offset is changed. The test uses real placed
PPD data and the existing `derived_directed_curve_entry` contract, not the
unrecorded Oct 11 head/position. Its reference distance is directed entry
progress minus truck reference progress minus existing 6 m front allowance and
2 m standoff. The plant's physical-front assumption is separately 4 m.
These allowances are not a measured painted line or a truck-specific calibrated
front. The actual Oct 11 target/front relationship is **NOT VERIFIED** because
the consumed historical target is missing.

## Reproduction before modification

The installed source is loaded read-only as AST functions in the same test
components; neither installed files nor original logs are modified.

- Seven production-flow regressions fail with the original installed methods:
  two gearbox modes for far-red creep, two for duplicate external braking,
  the exhausted-envelope brake, and two closed-plant disturbance/restart cases.
- With only the original Engine flush substituted, the new-red-during-steering
  regression fails: physical throttle **0.2479999959**, expected zero. The
  corrected path writes zero; the old command retains its original identity/time.
- These are executable code counterexamples. They do **not** prove the missing
  first-brake producer/countdown in the historical Oct 11 run.

## Closed-model comparison

Identical real reader -> directed selector -> Traffic -> Policy -> ACC ->
Autopilot -> Engine -> actual Controller -> BytesIO backend. Independent
producer phases add 12/8/10 ms between Traffic/Policy/ACC/AP. Seed 7610 produces
33/50/80 ms tick jitter; plant integration is 10 ms, transport delay 120 ms,
actuator response 350 ms, acceleration
`(2.2 * throttle - 4 * brake) / 1.4 - 0.12 - 0.004 * speed**2`.
Velocity is clamped at zero. No ETS2 mass/grade/idle/traction calibration is
claimed. Jerk is the difference of consecutive interval-average accelerations
divided by the actual next interval, not pedal slew rate.

Matrix: 18 paired red-stop runs (20/35/50 km/h, 40/60/100 m to entry, modes
0/3) and 18 candidate moving-green/ending-green/disturbance runs at 100 m.
Red stays until an observed model stop in the full-stop cases; new same-head
green then allows restart without N. A disturbance stress case explicitly
reduces speed to 0.92 m/s after initial braking and adds a stated low-speed idle
load. That disturbance is **assumed**, not an inferred cause of the game run.

### Direct creep counterexample, 35 km/h / 100 m, both modes

| Metric | Original installed methods | Candidate |
| --- | ---: | ---: |
| Time <5 km/h while target distance >10 m | 63.336 s within 70 s run | 1.194 s |
| Distance covered in that band | 49.753 m | 1.355 m |
| Actual stop / reference gap | No stop in 70 s | 0.495 m before derived target |
| Green -> positive drive, mode 0 / 3 | Not reached | 0.175 / 0.288 s |
| Positive pedal overlap / parking writes / zero brake while held | 0 / 0 / no completed hold | 0 / 0 / 0 |

The old disturbance output's earlier `resumed_without_n=true` field was a
benchmark limitation (it merely checked final speed). The tool is corrected to
require an observed stop, green and actual positive write. With no stop/green
the original case is **not** a successful restart. No production expectation
was removed to convert a failure into PASS.

### Normal red approach, 100 m, mode 0 (mode 3 has the same stopping dynamics)

| Initial speed | Brake onset, distance to entry before -> after | Reference stop gap before -> after | Peak deceleration before -> after | Peak jerk before -> after | Pedal source-mode changes before -> after |
| --- | --- | --- | --- | --- | --- |
| 20 km/h | 31.725 -> 31.725 m | 1.444 -> 1.388 m | 0.971 -> 1.244 m/s² | 6.638 -> 11.950 m/s³ | 2 -> 2 |
| 35 km/h | 67.765 -> 67.765 m | 1.579 -> 1.339 m | 1.153 -> 1.341 m/s² | 4.875 -> 11.881 m/s³ | 2 -> 2 |
| 50 km/h | 99.307 -> 99.307 m | 1.639 -> 1.378 m | 1.629 -> 1.629 m/s² | 4.218 -> 28.541 m/s³ | 1 -> 1 |

Candidate / baseline sample counts: 456/486, 373/440, 362/432;
durations 24.365/26.012, 20.090/23.419, 19.454/22.950 s.
Far-low-speed duration (>10 m) is zero for both versions in these ordinary
cases. Therefore the ordinary undisturbed plant **does not reproduce the user's
initial harsh slowdown**. Beyond 10 m, maximum jerk remains exactly 2.020,
4.243, 2.580 m/s³. The larger full-run peaks occur at terminal braking/standstill
and the model velocity clamp; they are reported, not removed from the result.
The candidate is **not** a uniformly better jerk/comfort result.

Example 50 km/h candidate trajectory, original sampled distance / actual / target:
50.212 m / 31.454 / 31.013 km/h;
30.075 m / 21.333 / 23.434 km/h;
9.983 m / 10.806 / 11.919 km/h;
3.004 m / 5.051 / 4.828 km/h.
These are model samples at the stated distances, not interpolated game evidence.

The deliberately short 50 km/h / 40 m-entry case has a **3.945 m derived
reference-target overrun in both versions**. Full braking was already required;
the modeled front stops only about 0.055 m before the entry. It is not counted
as a successful stop before the target and does not certify a physical stop
line. The fix does not worsen that case or adjust its distance to hide it.
This insufficient modeled reserve remains a limitation. All other normal
matrix cases stop before their derived reference target.

All 36 candidate runs remain active with zero modeled front-entry overruns,
positive physical pedal overlaps, parking writes and interrupted stationary
holds. Full-stop and disturbance cases restart after green; moving/ending-green
cases continue while moving and are not mislabeled as completed stop/restart.
The new-red race and stale/foreign source/cancellation variants additionally
exercise the positive-write boundary.

## Regression and performance verification

- **312 passed**: Oct 11 approach, Oct 10 timing/reactivation/availability,
  stop/resume, Oct 8 lifecycle, hold comfort, longitudinal arbitration/commit/
  comfort, packet refresh, automatic replay and pedal-history modules.
- **69 passed**: additional Oct 6 joint stop, activation observation binding
  and Oct 4 signal lifecycle regressions.
- **43 passed** after the final bounded-write guard/diagnostic-binding optimization:
  Oct 11 approach, commit/preview and automatic longitudinal replay regressions.
- Steering benchmark: **16 cases numerically identical** to the Oct 10
  saved baseline. Non-signal longitudinal comfort: **12 cases identical**.
  The signal trajectory change is intentionally compared separately above.
- Three paired 360-tick in-process cruise measurements: Engine median
  0.507 -> 0.586, 0.514 -> 0.583, 0.523 -> 0.585 ms;
  p95 0.650 -> 0.831, 0.790 -> 0.787, 0.769 -> 0.823 ms;
  maximum 1.911 -> 2.696, 1.573 -> 1.894, 2.236 -> 1.692 ms.
  Physical writes and complete mapping bytes are identical. Traffic reads
  increase from 360 to 720: **one additional bounded control validation only
  for positive drive**, not diagnostic/SDK polling. These are copying IPC
  fixture timings, not live Manager latency or packet cadence measurements.
- No memory budget or diagnostic queue expansion; only fixed state/flags and
  one bounded consumed-source receipt. No synchronous disk I/O added.
- `compileall` and `git diff --check`: PASS after final edits.
  The full pytest suite was intentionally not run.

## Reproduction commands and local output

Run from the repository with `PYTHONCASEOK=1`:

```powershell
python -m tools.analyze_oct11_red_approach --output docs/steering-audit/oct11-approach/final-evidence.json
python -m tools.run_oct11_red_approach_bench --workdir docs/steering-audit/oct11-approach/baseline-reproduction --before
python -m tools.run_oct11_red_approach_bench --workdir docs/steering-audit/oct11-approach/candidate-reproduction
python -m tools.run_oct11_red_approach_bench --workdir docs/steering-audit/oct11-approach/lifecycle-reproduction --distances 100 --scenarios disturbance moving_green ending_green
python -m tools.run_oct11_red_approach_bench --workdir docs/steering-audit/oct11-approach --runtime-cost-output docs/steering-audit/oct11-approach/runtime-costs-final.json
```

Use a **new** work directory after code changes: the tool deliberately reuses
existing saved cases. `--before` requires the unchanged installed baseline
verified above; it is not reproducible by treating a later installation as old.
Current saved results are `baseline`, `disturbance-before`, `final4-red`,
`final4-lifecycle`, `paired-metrics.json`, `runtime-costs-final.json`, `steering.json`,
`comfort.json` and `final-evidence.json` under the ignored local output directory.
Original logs/collections remain outside Git and unchanged.

## Exact candidate runtime delta / changed files

Deploy **none** now. If separately approved later, these five files are a
consistent delta to the hash-verified installed baseline, not standalone plugin
mixes:

1. `core/engine.py`
2. `core/longitudinal.py`
3. `core/service_brake_hold.py`
4. `plugins/acc/main.py` (1.1.6)
5. `plugins/drivepolicy/main.py` (1.1.2)

No DLL, settings, cache, commit marker, steering file, geometry file or collector
replacement is required. Source/installed SHA-256 values are emitted by the
read-only analyzer; recheck them before any future approved deployment.

Other task changes: `tests/test_oct11_red_approach.py`,
`tools/analyze_oct11_red_approach.py`, `tools/run_oct11_red_approach_bench.py`,
`tools/run_prefab_signal_bench.py` (optional explicit disturbance model),
`tools/run_oct10_signal_timing_bench.py` (preserve the old counterfactual after
the new approach contract), this report and `PLUGIN_CHANGELOG.md`.
All inherited local work is preserved.

## Remaining limits

The initial Oct 11 braking source, consumed distance/countdown and true painted
stop-line/front relation remain unavailable. Existing data were exhausted;
no further drive is requested here. Terminal jerk and short stopping reserve
are explicitly not certified as comfortable/safe for all ETS2 vehicles. The
software removes the proven creep trap but does not prove the entire reported
harsh-braking incident resolved in ETS2. A future user-authorized deployment and
evaluation must retain this distinction; a new full pytest run is pending after
the test-harness corrections below.

## Full-suite follow-up: four test-harness failures

The user ran the full suite: **4 failed, 2,296 passed, 1,592 subtests passed**.
All four failures were reproduced before changing the harness. No production
file, safety limit, plugin version or installed file was changed in this follow-up.

- The combined-export test used the real executor's constructor-bound clock for
  submissions but the fixture clock for execution. Its target therefore appeared
  expired (about 131 seconds old in the isolated reproduction). Bind both to
  the same simulated clock. `command_binding_proven` must still be true for
  every exported row; neither freshness nor the collector gate is relaxed.
- Two gearbox-mode tests required positive brake from the first approach
  correction. That predates the moving approach phase described above and
  would require the very latch that traps a below-profile vehicle. The tests
  now require moving releases to remain in `approaching` above 0.05 m/s, then
  require every actual brake write and sampled pedal pair to remain positive
  brake / zero throttle from terminal braking through red standstill.
- The head-distance comparison mixed a metadata-free legacy brake with today's
  qualified distance controller. It is now explicitly a **geometry-only
  counterfactual**, with the same consumed target for all producers. Its wrong
  distance crosses the actual entry and eventually fails route qualification;
  it is not labeled a completed historical stop or successful restart. The
  derived target must have zero red entry overruns, a stop front gap of at
  least 2 m, active authority and a real green restart. The standalone benchmark
  uses distinct `head_distance_counterfactual` / `derived_target` labels.
- The benchmark's restart flag now requires an observed stop, subsequent green,
  actual positive throttle, continuing authority and modeled forward movement;
  final speed alone cannot imply a successful restart.

Verification: **145 targeted tests passed** across packet refresh, prefab signal
binding, Oct 11 red approach, signal restart, continuous stop and Oct 4 lifecycle.
After the final stricter approach/restart assertions, **3 affected cases passed**.
These results do not replace a fresh full-suite run or certify ETS2 behavior.

Follow-up files: `tests/test_oct9_packet_refresh.py`,
`tests/test_prefab_signal_binding.py`, `tools/run_prefab_signal_bench.py`, this report.

## Authorized deployment, 2026-10-11

After the user reported the corrected full suite PASS and explicitly requested
deployment, the five candidate runtime files above and `PLUGIN_CHANGELOG.md`
were copied to the installation. UltraPilot and ETS2 were not running. All 20
previous receipt hashes matched before deployment and all 20 final receipt
hashes matched afterward; the six copied files also match their source hashes.
Installed ACC is 1.1.6 and DrivePolicy is 1.1.2. DLL, settings, map-cache,
application version and commit marker were not changed. No application, game
or collection was started.

Backup: `C:\Users\PC\AppData\Local\UltraPilotBackups\red-approach-20261011T070258194Z`.
It contains the prior receipt, the full 20-file receipted payload and individual
copies of the six replaced files. The receipt was published atomically with
rollback protection. Local deployment receipt:
`docs/steering-audit/manual-deployment-red-approach-20261011T070258194Z.json`.
The deployment helper and receipt are ignored audit artifacts, not Git payload.
**DEPLOYED / HASH VERIFIED; GAME VERIFIED remains false.**
