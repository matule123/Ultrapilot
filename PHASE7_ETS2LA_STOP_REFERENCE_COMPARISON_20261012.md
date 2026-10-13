# ETS2LA stopping reference versus UltraPilot — 12 October 2026

Follow-up, 13 October: the user explicitly authorized a 5 m planning reference
after offline comparison. The implementation and paired results are recorded
in [PHASE7_FIVE_METRE_STOP_REFERENCE_20261013.md](PHASE7_FIVE_METRE_STOP_REFERENCE_20261013.md).
The 8 m UltraPilot values below describe the inspected baseline, not the new
candidate. Neither report claims a measured bumper-to-painted-line distance.

## Concrete finding

The locally available ETS2LA Python implementation targets **5 m before a
selected prefab-route endpoint**. UltraPilot targets **8 m before the directed
entry** (6 m conservative front allowance + 2 m stand-off). On the same incoming
entry this is a proved **3 m difference in the planned SDK reference position**.
It is not a measured difference in bumper-to-painted-line clearance.

This is more specific than saying only that line geometry is missing: the
existing conservative target choice itself differs substantially from ETS2LA.
UltraPilot's additional controller stopping residual is a separate quantity.
This read-only comparison does not activate a global reduction of the existing
reserves, contrary to the preceding explicit task constraint.

## Exact inspected reference

- Source: `C:\ETS2LA\app\Plugins\AdaptiveCruiseControl\main.py`.
- Clean local Git checkout, remote `https://gitlab.com/ETS2LA/ETS2LA`.
- Commit `52f068dadfba84c6e10287add329dfe25ac40c69`, 22 June 2026,
  subject `Final update for ETS2LA Python.`
- File SHA-256 `b6052b95adf2f98813ce6df6e63a2fcbfc3db83b3f5e51520ca7b95f49166ba3`.
- This is the user's available local Python source, not a claim that it is the
  current official rewrite or proof of the exact build used in an earlier drive.
- UltraPilot baseline HEAD c7339a4 plus preserved uncommitted joint lifecycle
  fixes. Existing source and installed dependency verification is unchanged.

No ETS2LA files, installation, old UltraPilot checkout, game or original
diagnostic data were modified or run.

## Complete source path

1. Default `traffic_light_mode` is `Normal` in this source (an actual runtime
   override is not asserted). `get_next_prefab_traffic_light`, lines 880–968,
   reads the selected next intersection and lane, traverses its authored nav
   curves, matches live traffic lights to curve semaphore IDs, checks placement
   bounds, and chooses a candidate. It returns Euclidean distance from SDK truck
   position to the nearer of that route's first/last points. This is not a surveyed
   painted line. The nearer-endpoint behavior and ID/proximity qualification
   must not replace UltraPilot's stronger directed ownership/arc checks blindly.
2. `calculate_traffic_light_constraint`, lines 281–318, subtracts **5 m once**
   from that distance. It computes requested deceleration from `v²/(2*d)`,
   with a 1.2 multiplier and another 1.2 below 50 m, comfort/emergency bounds,
   and at least 1 m/s² demanded braking below 1 m/s. These are source rules,
   not measured ETS2 dynamics or proof of smoothness on every truck.
3. `calculate_target_acceleration`, lines 408–460, combines the most restrictive
   speed, lead, stop and light/gate acceleration constraint.
4. `run`, lines 1319–1381, derives signed acceleration feedback from SDK vectors
   and speed change, obtains objects around 15 Hz and calls an acceleration PID.
   `apply_pid`, lines 1178–1269, compares desired/current acceleration and maps a
   signed output to pedals via `set_accel_brake`. This differs from UltraPilot's
   speed PID plus qualified distance ceiling and actual physical hold ownership.
   Its signed-vector magnitude and smoothing are not adopted as calibrated
   vehicle physics, nor is a second controller added to UltraPilot.

## Same real passage comparison

The existing original-PPD fixture reconstructs the incident's placed directed
passage `45540e750098d8f1fc11bc8b76cd20b1ae161420a94ae48b90dad1891389062f`.
Entry XYZ is [34753.473500664, 6.90234375, 45663.958017401]. The first selected
curve point and UltraPilot prepared entry match with **0 m alignment error**.
Original ETS2LA distance/constraint method bodies are extracted without importing
or starting any app/game module. Straight approach poses are explicit models.
For those poses its nearer endpoint is indeed this entry, not the exit.

| SDK reference to same authored entry | ETS2LA remaining after 5 m | UltraPilot remaining after 8 m | Target offset difference |
| --- | ---: | ---: | ---: |
| 50 m | 45 m | 42 m | 3 m |
| 20 m | 15 m | 12 m | 3 m |
| 10 m | 5 m | 2 m | 3 m |
| Modeled pose at 5.654666 m | 0.654666 m | −2.345334 m | 3 m |

The last distance is a straight-pose comparison at the stationary collection's
scalar reference distance. It is **not** its complete actual lateral/height pose,
not its measured bumper and not a new calibration. The existing actual stationary
comparison remains −2.337669 m after arc projection with its lateral displacement.

No 1–2 m physical clearance is inferred. ETS2LA also uses a heuristic fixed
offset here rather than a measured truck-front/painted-line channel. Therefore
missing metrology does not explain away the clear 5-versus-8 target difference,
but it does prevent claiming that copying 5 m universally meets physical safety.
On curved approaches Euclidean distance is not the directed path distance.

## Result and next implementation boundary

**VERIFIED SOURCE DIFFERENCE:** same-entry planning target is 3 m earlier in
UltraPilot. This is a concrete candidate explanation for excessive stopping gap,
separate from terminal regulator residual. **NOT MEASURED:** ETS2LA's actual
stopping residual and either system's physical bumper-to-painted-line gap.
This comparison contains no claimed new runtime improvement or game PASS.

An implementation should separate the target convention from the stopping
residual, test a specifically scoped ETS2LA-equivalent target on the same actual
passage/vehicle, and retain directed assignment, conservative fallback, emergency
priority, continuous brake and the existing single regulator. It must not simply
replace all 6+2 m margins or copy nearest-head selection/acceleration control.
No new ride is requested by this analysis.

Reproduce with `PYTHONCASEOK=1`:

```powershell
python -m tools.compare_ets2la_stop_target --workdir docs/steering-audit/ets2la-stop-comparison --output docs/steering-audit/ets2la-stop-comparison/comparison.json
```

Only this report, the read-only comparison tool and a backlog note were added.
The tool verifies same-entry alignment and original method availability, and
the comparison ran successfully. Compile check and diff-check passed. Runtime,
ACC VERSION 1.1.9, changelog and all preceding lifecycle fixes are unchanged.
No full suite repetition is necessary for this source analysis; the preceding
runtime candidate's 2,449 tests / 1,592 subtests result remains its own evidence.
