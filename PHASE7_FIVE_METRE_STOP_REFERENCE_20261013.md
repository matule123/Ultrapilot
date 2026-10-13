# Authorized five-metre signal stopping reference — 13 October 2026

## Full-suite follow-up: stale fixture coordinates

The user's complete run reported **5 failures, 2,455 passes and 1,592 subtests**.
All five failures were reproduced before the follow-up correction. No additional
runtime change was required: the missed tests still encoded the previous 8 m
reference or its fixture poses.

- `test_oct10_signal_approach.py`: 120 m to entry now leaves 115 m, not 112 m.
  The safety reserve remains 27 m. Retain progress 85 m as a negative case
  (30 m remaining) and test progress 88 m at the unchanged intervention boundary.
- `test_oct10_reactivation_traffic.py`: its helper deliberately shortened the
  synthetic approach by 3 m when the reference changed. The old fixed 48 m pose
  was now beyond the authored entrance, so there was no qualified signal. Derive
  the test pose from the actual prepared target minus 0.1 m; assert a valid
  signal and that exact positive remaining distance before forcing standstill.
- `test_oct6_joint_stop_flow.py`: old world Z=-138 is now 3 m before the target,
  not at it. Derive the target world Z from the authored entrance, current
  allowance sum and heading; move pose and Map progress together. Assert actual
  selected distance zero before checking the first zero-ratio brake/restart.

Brake continuity, no positive pedal overlap, manual cancellation, missing-source
rejection and green-release assertions were not weakened. No fake brake, fresh
history or signal authority was inserted. All three affected test files plus
the new five-metre reference tests passed: **87 tests in 30.00 s**. Compile checks
and `git diff --check` passed. Final full-suite revalidation: **2,460 tests and
1,592 subtests passed, zero failures, 587.16 s** (`PYTHONCASEOK=1 python -m pytest
tests -q -p no:cacheprovider --tb=short`). This follow-up changed only the three
test files and this report. Installed files, 5 m runtime reference and plugin
versions remain unchanged; no deployment was performed.

## Decision and scope

**OFFLINE VERIFIED: 5 m planning-reference implementation and supported
stop/hold/green/restart lifecycle. GAME NOT VERIFIED. Physical bumper-to-painted
line clearance NOT MEASURED.** No deployment, commit, push or game operation.

The user explicitly superseded the earlier requirement to retain 6+2 m:
“Áno, použi 5 m po offline overení.” The inspected local ETS2LA Python subtracts
5 m from its selected prefab endpoint. On this real directed passage that
endpoint equals UltraPilot's authored entry. This justifies a deliberate
planning-policy change; it does not prove that the previous conservative
allowance was a mathematical bug or that it explains every historical metre.
See the preceding source comparison for the exact ETS2LA commit/file hash.

Baseline: c7339a405542f55d2ac235161e99b019be4bf101 plus preserved uncommitted
Oct 12 moving-green and non-signal brake-ownership corrections. Both remain
intact. The installed `stop-indicators-20261012T175215479Z` receipt's **24 hashes
match**. Candidate/installed comparisons distinguish real changes from LF/CRLF.
The installation and original diagnostic collections were not modified.

## Concrete change

`core/navigation/prefab_signals.py` declares `STOP_REFERENCE_OFFSET_M=5`.
The existing compatible fields carry a 3 m planning component and the unchanged
2 m stand-off. The 3 m value is **not a measured body front**. Its explicit
status is `unmeasured_sdk_reference_policy`; `stop_line_verified` stays false.

The selector uses directed progress and subtracts the total once:

```
before: distance = entry_progress - sdk_progress - 6 - 2
after:  distance = entry_progress - sdk_progress - 3 - 2
```

Map geometry, head ownership/heading/layer qualification, lock identity, original
SDK times, 500 ms gates, speed envelope, PID, arbitration, continuous physical
brake ownership and confirmed-green release are unchanged. There is no minimum
creep speed, repositioning after a red stop, parking-brake actuation, additional
controller, new collector or new SDK/IPC read. Phase planning's conversion back
to entrance distance remains consistent: it adds the same transported components
that were subtracted. A lamp position is still not a stop target.

No plugin implementation or VERSION is changed. ACC remains **1.1.9**, with
this coordinated core correction documented under that existing changelog entry.
Map 1.1.2, Autopilot 1.3.4, DrivePolicy 1.1.3, TurnSignals 1.0.2 and DLL
1.59.3-up-signal-scope are not newly released.

## Fail-first and acceptance definitions

Before the change, two real-PPD/native-reader directional tests received 42 m
remaining instead of the newly required 45 m at the same 50 m approach. Two
35 km/h production-path/physical-write tests observed the original **8 m**
offset instead of **5 m**. These four checks failed before implementation.
Afterward all 11 new regressions passed, including both modes, 20/35/50 km/h,
curved approaches, other stop priority, source time preservation and actual
ordered SCS test-backend writes.

Before retained runtime modification, the paired experiment fixed these
criteria: 5 m SDK-reference target, nonnegative target residual, no target
crossing, continuous terminal brake, zero red standstill drive, no parking
writes or positive pedal overlap, authority retained and fresh-green restart
without another N. Far creep means speed <5 km/h with >10 m remaining to the
derived target. No new measured-game comfort threshold is invented.

The earlier tests' **>=2 m model-front gap** belonged to the old 8 m policy.
The explicit 4 m model front and authorized 5 m reference target imply a
**>=1 m model-front-to-authored-entry** bound, additionally requiring a
nonnegative reference residual. That intentional criterion change is stated,
not disguised as an unchanged safety guarantee. It is not physical metrology.
Other safety assertions were not removed. Old near-stop lifecycle fixtures
keep their original 42 m initial distance to the target by moving the synthetic
approach from 50 to 47 m; pose and published progress change together. The
actual authored prefab stays unchanged. The independent paired plant keeps
its original **100 m approach to the entrance**, proving the real target shift.

## Same-input closed-plant comparison

Real placed `dlc_blkw_80` PPD, directed passage
`45540e750098d8f1fc11bc8b76cd20b1ae161420a94ae48b90dad1891389062f`,
entry XYZ [34753.473500664, 6.90234375, 45663.958017401]. Native source layouts
feed reader -> selector -> Traffic -> DrivePolicy -> ACC -> Autopilot ->
Engine -> real Controller -> chronological BytesIO SCS writes. Producer times
remain original. This is not a reconstruction of missing historical writes.

54 pairs: three speeds, two transmission modes, straight/left/right radius-60 m
synthetic approaches tangent to the same entrance, and three explicit plants.
Before substitutes only the original 6 m planning component; after substitutes
3 m. Every other production component, geometry, random tick sequence and plant
parameter is identical. 23,828 baseline / 24,212 candidate observations.

Uncalibrated plant: `a=(2.2*T-4*B)/mass_ratio-0.12-0.004*v²`, integrated at
<=10 ms with zero-speed clamp, delayed first-order pedal response. Default:
120 ms transport / 350 ms response / mass_ratio 1.4; quick: 50/200 ms / 1.4;
slow-loaded: 220/600 ms / 1.8. Seeded tick intervals 33/50/80 ms and existing
12/8/10 ms producer operations. Model jerk is adjacent acceleration difference
divided by actual elapsed dt, including terminal clamp/restart. It is not
measured ETS2 jerk, input consumption or calibrated transmission physics.

Default straight plant (identical in both automatic modes):

| Speed | SDK point -> authored entry before/after (m) | Residual before/after (m) | Peak deceleration before/after (m/s²) | Peak model jerk before/after (m/s³) |
| --- | ---: | ---: | ---: | ---: |
| 20 km/h | 8.872 / 5.912 | 0.872 / 0.912 | 0.971 / 1.001 | 2.746 / 3.133 |
| 35 km/h | 9.013 / 6.006 | 1.013 / 1.006 | 1.153 / 1.154 | 4.243 / 4.459 |
| 50 km/h | 8.843 / 5.612 | 0.843 / 0.612 | 1.629 / 1.592 | 3.268 / 3.150 |

Brake onset SDK distance to entry: 31.725 -> 28.198 m, 67.765 -> 65.428 m,
99.307 -> 99.307 m. At 50 km/h braking is already needed at the initial pose.
Pedal reversals remain 2/2/1. Green drive return is 0.112 -> 0.125 s,
0.152 -> 0.098 s and 0.122 -> 0.128 s.

Across all pairs, candidate SDK-entry gap is **5.281–6.006 m** versus
**8.284–9.013 m**; target residual remains **0.281–1.006 m** versus
0.284–1.013 m. Candidate duration is 21.496–27.442 s versus 21.546–26.983 s.
All pairs have zero red target/4 m model-front entry overruns, interrupted
terminal/holding brake writes, red standstill drive, pedal overlap, parking
writes and far-creep time. All retain authority and restart without N.

This is **not uniformly better comfort**: peak deceleration increases in 26/54
cases (largest increase 0.03884 m/s²); peak model jerk increases in 22/54
(largest increase 1.15145 m/s³). Overall maxima are 1.695 -> 1.658 m/s² and
8.896 -> 6.037 m/s³, but those aggregate improvements do not erase individual
increases. No gains/filter were tuned to hide them. The fixed trajectory has
shifted relative to the seeded tick phases; game comfort remains open.

## Physical clearance limits

The model front is explicit, not inferred from SDK axles. Sensitivity of the
same candidate stopped poses to assumed fronts of 3/4/6 m gives respective
entry gaps 2.281–3.006 / 1.281–2.006 / **-0.719–0.006 m**. Thus 5 m is not a
certified universal reserve for a truck with a 6 m SDK-to-front extent.
No claim of physical 1–2 m clearance or suitability for every truck is made.

The historic 10.5514 m SDK-entry gap and manually desired 5.655–5.663 m pose
belong to recorded geometry, not this plant. Their painted-line/front channels
remain missing. The stationary +2.3377 m local calibration is not activated.
Historical terminal residual 2.5514 m is separate from the proved 3 m target
difference and is not causally explained by these simulations.

## Checks, reproducibility and runtime bundle

Targeted selection: 165 cases passed after coordinate/reference updates;
five old-policy >=2 m assertions then passed after the intentional documented
5-minus-4 m criterion update. A separate **348 tests + 7 subtests passed** for
arbitration, launch, hold/green release, emergency, R/backward, stale/foreign
inputs, cancellation, backend errors and combined evidence integrity.
Total distinct selected cases: **518 tests + 7 subtests passed**. All 11 new
tests are included. The first old-fixture run's 37 failures and the subsequent
five old-policy failures are retained in logs, not claimed as successful runs.
The full suite is reserved for the user.

Unchanged steering benchmark **16/16** and longitudinal comfort benchmark
**12/12** case metrics match the preceding Oct 12 candidate exactly. Static
checks (`compileall`, `git diff --check`) pass; the final source/installed
manifest is stored with the artifacts.

```powershell
$env:PYTHONCASEOK='1'
python -m tools.compare_oct13_stop_reference --output docs/steering-audit/oct13-stop-reference/comparison.json
python -m pytest tests/test_oct13_stop_reference.py -q
```

Large outputs remain ignored under `docs/steering-audit/oct13-stop-reference/`.
The analytical harness now reads the actual prepared offset instead of reporting
a hard-coded 8 m target. The ETS2LA source comparison explicitly distinguishes
the frozen 8 m baseline from the current prepared 5 m policy; rerunning it cannot
silently mislabel a new target as the old one. No original collection or old
checkout was edited.

Changed in this task: `core/navigation/prefab_signals.py`; new
`tests/test_oct13_stop_reference.py`; reference expectations / consistent modeled
poses in `tests/test_prefab_signal_binding.py`, `tests/test_oct11_stop_geometry_audit.py`,
`tests/test_oct8_signal_coverage.py`, `tests/test_oct10_signal_timing.py` and
`tests/test_oct10_native_signal_direction.py`; new
`tools/compare_oct13_stop_reference.py`; actual-offset reporting in
`tools/run_prefab_signal_bench.py`, `tools/audit_oct11_stop_geometry.py` and
`tools/compare_ets2la_stop_target.py`; this report, the comparison follow-up,
`DEFERRED_WORK.md` and the current-version `PLUGIN_CHANGELOG.md` entry.
All inherited runtime, reports and untracked lifecycle tests/tools are retained.

**New runtime delta:** `core/navigation/prefab_signals.py` only.
**Consistent pending runtime bundle relative to the receipt-matched install:**

```
core/navigation/prefab_signals.py
core/engine.py
core/service_brake_hold.py
PLUGIN_CHANGELOG.md (release metadata)
```

The latter two core files preserve the preceding joint lifecycle fix. Keep all
24 receipt-matched dependencies; no DLL replacement, settings/cache/marker
change or copying of tests/tools/reports. Candidate hashes are recorded in
`runtime-candidate.json`. User full-suite PASS and explicit deployment approval
are required before installation changes. After approved deployment, a single
controlled red approach -> hold -> green -> restart can check the joint candidate
with existing automatic export; the user controls the game and takes over on
unsafe behavior. No new game run is requested now.
