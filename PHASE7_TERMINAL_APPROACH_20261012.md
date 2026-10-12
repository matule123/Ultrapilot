# Terminal signal approach: remove an unjustified full-brake discontinuity

## Continuation — qualified approach ownership, 12 October 2026

The later candidate and new retained approach evidence are documented in
[PHASE7_STOP_AND_MANEUVER_INDICATORS_20261012.md](PHASE7_STOP_AND_MANEUVER_INDICATORS_20261012.md).
It corrects competing Traffic/ACC braking and premature hold commitment without
moving the planning target. Its final targeted checks pass, but exact target
convergence, idle-drive sensitivity and painted-line/front clearance remain open.
The full-suite result below belongs to the earlier installed correction, not this
later candidate. No new deployment or game verification is claimed.

## Full-suite regression correction — 12 October 2026

The user's full suite exposed **30 failures, 2,368 passes and 1,592 subtests**.
This supersedes the earlier narrow-run claim that all stop/hold/restart
integration contracts remained preserved. The failure was reproduced locally
in both first-brake gear cases without modifying the existing safety tests.

Removing the moving full-pedal clause also let a first slow terminal approach
fall through `speed <= cap and not continuing`, returning zero brake. No
positive backend write meant no acknowledged service-brake chain; subsequent
gear-zero, hold-refresh, export and green-resume tests failed downstream.
At stationary speed the distance mapping could likewise fade to zero.

The correction retains the existing low-speed/1.5 m zone but uses the calculated
positive distance demand for a moving first brake as well as a continued brake.
It does not restore the moving full-pedal jump. At exactly zero speed in that
zone it retains full brake **request**; unchanged Engine/transmission ownership
still controls whether a new standstill write is authorized. No weaker identity,
freshness, reverse, backend, or manual-disengagement checks were introduced.

Three additional direct tests cover first positive requests at v=0.2/d=1 and
v=0.39/d=1.49, and the stationary request. Existing nonteminal ownership remains
unchanged. The seven files containing the reported failures plus terminal
approach tests passed together: **147 tests in 57.02 s**, including six paired
closed-plant comparisons. The original 30-failure tests were not relaxed.

Full-suite revalidation passed: **2,401 tests and 1,592 subtests, zero failures,
510.03 s**. Command: `PYTHONCASEOK=1 python -m pytest tests -q -p no:cacheprovider`.
Compile checks and `git diff --check` also passed. No deployment or
game result is implied. The earlier 54-pair matrix belongs to the prior candidate;
it is not presented as a fresh 54-pair rerun of this correction.

## Verdict and scope

**OFFLINE VERIFIED for the reproduced premature full-brake condition; GAME NOT
VERIFIED.** This is a limited approach correction, not proof that the complete
historical 2.5514 m stopping residual has been eliminated. The unchanged model
still stops roughly a metre before its planning target. Exact target convergence
and the physical bumper-to-painted-line gap remain separate open properties.

The existing 6 m front allowance and 2 m junction stand-off are unchanged. The
local stationary comparison's +2.3377 m offset is not activated. No stopped red
vehicle is released or automatically repositioned to improve its reported gap.

## Source and evidence identity

HEAD: `787d012a2a78ac917bb5506e0958c32d8d06575f`, plus preserved uncommitted
packet-refresh, signal, traffic, destination and indicator changes. No AGENTS.md
was found in this checkout or the previously checked parent directories. The
four requested reports and PLUGIN_VERSIONS.md were read. Work began on Oct 11;
verification/report completion follows on Oct 12 after an interrupted turn.

All 20 installed receipt hashes still match deployment
`20261011T095307684Z`. Actual source differences, after LF/CRLF normalization,
remain distinct from that deployment; its commit marker alone is not proof of
this candidate. Installed ACC is 1.1.7; inherited candidate ACC 1.1.8 and
TurnSignals 1.0.1 are preserved. This task changes only a core implementation,
so it does not release or increase any plugin VERSION. DLL is unchanged.

Both original replays pass the existing immutable codec/integrity check:

| Installed route-diagnostics file | SHA-256 |
| --- | --- |
| steering-replay-20261011T104936.895268Z-automatic_disable.json | 09e3e6508d85c8cb0902171324bee3c5319755ec13edb7bc4a6c36ea76170e0a |
| steering-replay-20261011T104938.211656Z-automatic_disable.json | e17d17fb489aa3e881917151f763d9958f447c4076ae51bfcb74f439bdd3b15c |

The same-identity hold has activation 5688400855600, session 1,
map promods-1.59, dataset d6cc7936fce4e902761abb5d, intent
a24f7a16112944b1a758a00989f2f268, revision 7, build
c00e4335da75496facf8cab9a15c509c. It retains 46 holding rows, head 1,
passage 45540e750098d8f1fc11bc8b76cd20b1ae161420a94ae48b90dad1891389062f,
and 2.5513871–2.5514364 m SDK-reference-to-derived-target gap. Its brake is
0.1174879596; the current positive speed ceiling is about 8.13 km/h while held.

The start of that stop's terminal transition and exact early backend writes
have aged out. Every retained hold row is marked capture_incomplete. Thus the
historical gap does **not** establish which early brake/hold/PID condition
caused it. In particular, the new counterexample below is not substituted for
unrecorded historical inputs. The subsequent ACC-departure fault is unrelated.

The stationary calibration has 737 accepted observations, but no current
selected destination or bound live stop target. Its projection is 4.8891 m
ahead of the old pose / 2.3377 m beyond the old target. Neither the projection
nor a photograph measures the painted line or truck front.

## Last-metres production chain and demonstrated defect

1. The scoped producer/reader preserves original acquisition time, SDK frame,
   generation, lifecycle and authored directed head qualification. Map's PPD
   passage entrance is projected onto LanePath, not replaced with lamp distance.
2. The selector computes `d = entry_progress - sdk_progress - 6 - 2` once.
   The shared ceiling is `sqrt(2 * 1 m/s² * max(0, d - v * 1.5 s))`.
   The speed-dependent response/evidence reserve is not a duplicate fixed gap.
3. Policy applies that current ceiling after non-stop preference smoothing.
   ACC uses the existing speed PID, hysteresis and distance/deceleration mapping.
   Its below-profile recovery/coast memory remains unchanged.
4. Engine's terminal zone can still reintroduce a protective Traffic pedal;
   that input resets ACC's PID as external braking. The zone and hold state
   are deliberately **not** retuned here: broad offline alternatives increased
   pedal reversals/jerk or produced unsupported standstill transitions.
5. The reproduced bug is in the shared `stopping_brake_request`: it returned
   full brake solely for `v < 0.5 m/s && d <= 1.5 m`, even with a positive
   stopping envelope. At `v=0.39, d=1.49`, the ceiling is about 1.345 m/s;
   the continued distance mapping calls for about 0.021 pedal, not 1.0.
   The same Traffic request wins arbitration and ramps the real Controller
   output upward despite the still-positive distance trajectory.
6. Remove only that low-speed/fixed-distance full-brake clause. Full terminal
   demand remains when the original envelope is exhausted or `d <= 0`.
   Actual acknowledged service-brake holding at standstill remains Engine-owned.
   Moving positive adjustments keep the same brake chain; standstill cannot
   seed a new brake edge or authorize red repositioning.

No PID gains, reference geometry, planner target, steering code, freshness
limit, timestamp, generation, identity guard or backend validation changes.
No competing controller, minimum approach speed or throttle-against-brake fix.

## Criteria and fail-first reproduction

Criteria were frozen in the regression tests before the retained production
modification and final paired matrix. Initial exploratory measurements precede
that selection; they are not historical reconstructions or accepted tuning.

- A nonzero stopping envelope must not create an unrelated full-brake jump.
- The paired default plant must reduce residual without crossing the unchanged
  target, increasing maximum model deceleration/jerk, or adding pedal reversals.
- Positive physical brake writes remain continuous from terminal braking through
  red standstill; no red standstill drive, parking writes or positive pedal overlap.
- Fresh green resumes through the existing bounded path without another N.
- Exhausted envelope, other stop sources, stale/foreign evidence, R, reverse,
  cancellation and backend failure retain their protections.

No absolute game comfort or placement threshold is invented. A measured smaller
residual does not certify exact target arrival or a 1–2 m physical line clearance.

All **8 initial regressions failed before** the production change: two real
qualified-reader → Traffic → Policy → ACC → Autopilot → Engine → Controller
cases requested 1.0 instead of the distance brake; six paired closed plants
had identical baseline/candidate residuals. After the single core change,
all eight passed (32.77 s). Additional cases explicitly prohibit red standstill
repositioning and preserve full brake at actual envelope exhaustion.

The frozen baseline in `tests/fixtures/oct11-terminal-original.json` is the
current dirty-tree helper before this modification, with its source hash.
It is **not** HEAD-only, an older red-approach baseline or the installed file.
All other production components, geometry, input sequence, random dt, actuator
parameters and Controller write interfaces are identical between paired runs.

## Closed model and results

Real placed `dlc_blkw_80` PPD metadata and native-layout signal bytes feed the
actual reader/selector and control path. The approach is straight or a synthetic
radius-60 m left/right arc tangent to that same authored entrance. Curved tests
verify along-route distance plumbing; they do not claim those arcs were driven.

The uncalibrated plant integrates at <=10 ms, with 2.2 m/s² nominal throttle
and 4 m/s² nominal brake divided by mass_ratio, rolling deceleration 0.12 m/s²,
drag 0.004*v², transport delay and first-order actuator response. Default:
delay 0.12 s / response 0.35 s / mass_ratio 1.4. Quick: 0.05 / 0.20 / 1.4;
slow-loaded: 0.22 / 0.60 / 1.8. Tick jitter is seeded (0.033/0.05/0.08 s).
Source times remain original; producer operations add the existing 12/8/10 ms.
This is not a fitted ETS2 mass, brake efficiency, clutch, idle or input model.

Default straight plant, same result in both automatic modes:

| Entry speed | SDK gap before → after (m) | Max deceleration before → after (m/s²) | Max absolute model jerk before → after (m/s³) |
| --- | ---: | ---: | ---: |
| 20 km/h | 1.3882 → 1.2093 | 1.2443 → 0.9715 | 11.9504 → 3.6198 |
| 35 km/h | 1.3389 → 1.0773 | 1.3410 → 1.1530 | 11.8808 → 4.2432 |
| 50 km/h | 1.3785 → 1.1941 | 1.6288 → 1.6288 | 28.5413 → 3.9548 |

These maxima include clamped model standstill/restart and are not measured
physical jerk. No far creep (<5 km/h with >10 m remaining) occurs. The final
low-speed portion can take longer after removing the premature hard stop;
duration is reported rather than automatically labeled comfort PASS.

The full **54-pair matrix** (3 speeds × 2 modes × 3 approaches × 3 plants)
completed: 21,492 baseline observations / 22,974 candidate observations.
Individual modeled runs last 19.341–25.000 s before and 20.792–25.899 s after.
Residual range is **1.3378–1.3882 m before / 0.9749–1.2864 m after**. Every
paired case has a smaller nonnegative residual, no increased maximum
deceleration/jerk or pedal reversals, zero red target overruns, zero red
standstill drive writes, zero interrupted terminal/holding brake writes,
zero positive physical pedal overlap, zero parking writes, continuing authority
and confirmed modeled green restart. Missing physical-line data remain null.

For the default straight approach, sample counts before → after are
456 → 478 (20 km/h), 373 → 404 (35), 362 → 388 (50). Time below 5 km/h while
still moving increases 2.691 → 3.866 s, 2.478 → 4.016 s, 2.659 → 3.883 s,
respectively. These are the final few metres, not the old >10 m far-creep trap;
no claim that all low-speed duration improved. Initial brake onset is unchanged
at 31.7248 / 67.7652 / 99.3069 m SDK reference distance to the authored entry.
The planning target is 8 m before that entry, not a painted-line measurement.
Pedal reversals remain 2 / 2 / 1. Fresh-green drive return is 0.132 / 0.152 /
0.155 s after the modeled green; producer acquisition and confirmation still
gate that transition.

## Final verification

**379 targeted tests + 7 subtests passed in 145.30 s**. The interrupted earlier
large run had no retained final result and is not counted; it was repeated with
a workspace log. This is the required targeted selection, not the full suite:

```text
tests/test_oct11_terminal_approach.py
tests/test_oct11_stop_geometry_audit.py
tests/test_oct11_stationary_stop_comparison.py
tests/test_oct11_red_approach.py
tests/test_oct11_destination_flow.py
tests/test_oct10_signal_timing.py
tests/test_signal_stop_resume.py
tests/test_continuous_service_stop.py
tests/test_service_hold_comfort.py
tests/test_acc_following.py
tests/test_longitudinal_arbitration.py
tests/test_control_safety_regressions.py
tests/test_oct11_joint_regressions.py
```

These preserve moving-green recovery, ending-green anticipation, competing
stop priority, destination release, missing/foreign signal qualification,
freshness/identity/R/backend rejection, brake receipts and manual cancellation.
The unchanged production steering benchmark's **16 cases match exactly** and
the longitudinal comfort benchmark's **12 cases match exactly** the retained
`oct11-lifecycle` baseline metrics. No baseline expectation was relaxed to pass.

Compileall passes for the changed core, tests and model tools; whole-tree
`git diff --check` passes with only existing LF/CRLF conversion warnings.
The generated `summary.json` explicitly checks all 54 pairs, and
`runtime-candidate.json` records source/installed hashes for the seven-file
coordinated candidate below. All seven are real content differences after
LF/CRLF normalization; none is deployed here.
The preserved 120-file runtime snapshot confirms this task changed only
`core/longitudinal.py`; every other previously modified runtime file is intact.

Changed in this task: `core/longitudinal.py`, the new terminal regression test
and frozen baseline fixture, `tools/run_oct11_terminal_stop_bench.py`, optional
offline plant parameters in `tools/run_prefab_signal_bench.py` and
`tools/audit_oct11_stop_geometry.py`, this report, `PLUGIN_CHANGELOG.md` and
`DEFERRED_WORK.md`. All inherited work remains.

## Reproduction and consistent runtime bundle

```powershell
$env:PYTHONCASEOK='1'
python tools/run_oct11_terminal_stop_bench.py --output docs/steering-audit/oct11-terminal-approach/comparison.json
python -m pytest tests/test_oct11_terminal_approach.py -q
```

Generated models, write summaries and verification logs remain ignored in
`docs/steering-audit/oct11-terminal-approach`. No original collection is modified.

**This task's runtime delta: `core/longitudinal.py` only.** To preserve the
uninstalled joint correction, a consistent candidate relative to the currently
receipt-matched destination installation contains these seven runtime files:

```text
core/acc_following.py
core/engine.py
core/longitudinal.py
core/navigation/longitudinal_diagnostics.py
core/plugin_manager.py
plugins/acc/main.py
plugins/turnsignals/main.py
```

Include PLUGIN_CHANGELOG.md as release metadata. Tests, fixtures, analytical
tools, reports and temporary data are not runtime payload. No DLL replacement,
settings, map-cache or commit-marker change. Inherited versions remain ACC
1.1.8 / TurnSignals 1.0.1; this core-only correction adds no plugin release.
User full-suite PASS and separate explicit deployment approval are still gates.

## Remaining limitations

The original 2.5514 m residual is not causally explained by the retained export.
The tested narrow fix leaves a model stopping residual; exact convergence to
the unchanged planning target is **not declared complete**. The terminal-zone
handoff, PID reset/coast interaction and vehicle brake/rolling/idle response
remain relevant to that residual. Broad experimental changes were discarded
because their closed-loop results worsened, not hidden with new acceptance limits.

There is no trustworthy physical painted-line/front channel in the existing
map/SDK data. The separate line-position task remains blocked by bound metric
line and truck-front geometry. That limitation does not negate this software
counterexample and is not used to claim the unchanged fallback repaired.

No new drive is requested. No game, deployment, commit or push. Full pytest was
subsequently run for the regression correction documented at the top.
**OFFLINE VERIFIED narrow correction / full target convergence still open /
GAME NOT VERIFIED.**

## Authorized manual deployment — 12 October 2026

After full-suite PASS and the user's explicit `nasad` request, the seven runtime
files listed above plus PLUGIN_CHANGELOG.md were deployed. UltraPilot and ETS2
were verified stopped. All 20 previous receipt hashes matched before copying;
the new receipt covers 22 payload files (PluginManager and TurnSignals are now
included). All eight changed source/installed hashes and all 22 final receipt
hashes match. No DLL, settings, cache, application-version or commit-marker change.

Backup: `C:\Users\PC\AppData\Local\UltraPilotBackups\terminal-joint-20261012T124232464Z`.
Receipt: `docs/steering-audit/manual-deployment-terminal-joint-20261012T124232464Z.json`.
Includes inherited ACC 1.1.8 and TurnSignals 1.0.1; Autopilot 1.3.4 and DrivePolicy
1.1.3 remain unchanged. The backup contains the previous receipted payload,
individual changed files and previous receipt. No game was started.
**DEPLOYED / GAME NOT VERIFIED; physical stop-line placement still open.**
