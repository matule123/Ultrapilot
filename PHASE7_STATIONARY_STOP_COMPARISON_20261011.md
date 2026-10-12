# Stationary desired-pose comparison — 11 October 2026

## Scope and verdict

The user's manually selected stationary position can be compared with retained
historical geometry without another game run. This is a local chassis-pose
comparison, **not a measured bumper-to-painted-line calibration**. No runtime,
installation, plugin version, safety margin, or original evidence was changed.

## Evidence

- Collection: `stop-calibration-20261011-stationary-01`, 737 samples, 32 files,
  existing integrity inspector PASS. Temporary collection was disabled after
  successful export. All poses valid; planar spread 0.00815 m.
- No GPS destination was selected. No current route build or stop target was
  captured. The preparatory check should have caught this before collection.
- Historical dense replay: `steering-replay-20261011T104938.211656Z-automatic_disable.json`.
- Historical pedal replay: `steering-replay-20261011T104936.895268Z-automatic_disable.json`.
  Both pass the existing integrity decoder. Original hold has 46 summary rows.
- Map `promods-1.59` and dataset `d6cc7936fce4e902761abb5d` match. Current
  configuration token `e412f13ad3fb22186614354fd724da0b3dfb1ebcde848323bd222677213d8bc1`
  matches the configuration recorded in the preceding geometry audit.
- Historical build `c00e4335da75496facf8cab9a15c509c`, passage
  `45540e750098d8f1fc11bc8b76cd20b1ae161420a94ae48b90dad1891389062f`.
  These are historical identifiers, not reassigned live authority.

## Method and results

Recover local segment endpoints from distinct original segment fractions and
projection coordinates. Validate original progress and coordinate residuals;
do not interpolate missing geometry. Project each measured new chassis pose
onto these retained segments. Twenty-one segments were reconstructed with
maximum residual 1.03e-11 m (numerical consistency, not physical map accuracy).

| Quantity | Result |
| --- | --- |
| Median new chassis XYZ | 34753.550449, 6.919367, 45669.719604 m |
| New frame range | 283122008–359818940 |
| New progress on historical route | 394.170668–394.178699 m |
| Lateral distance to historical centerline | 1.069972–1.070412 m |
| Maximum heading difference | 1.328 degrees |
| Authored entry progress | 399.833365 m |
| Historical held reference to entry | 10.551412 m |
| New reference to entry | 5.654666–5.662697 m |
| New desired pose forward of historical hold | 4.889081 m |
| New pose distance to unchanged derived target | -2.337669 m |

The historical target is entry minus 8 m (6 m estimated front allowance plus
2 m stand-off). The historical hold stopped approximately 2.5514 m **before**
that target. The new manually selected pose is approximately 2.3377 m **past**
that same target. Thus the observed 4.8891 m shift must not be substituted
directly for a planner offset; planning geometry and actuator stopping residual
are different quantities.

The new pose is laterally about 1.07 m from the historical route centerline.
The comparison is spatially compatible, but does not independently establish
current lane identity, painted line geometry, or longitudinal bumper extent.
Photo/user positioning provides desired-pose evidence with unmeasured error,
not a surveyed 1.5 m clearance. A local offset cannot be promoted to a universal
front allowance for all trucks or prefab placements.

## Next implementation boundary

No further drive is required for this comparison. Any proposed local calibration
must be explicit about vehicle/placement applicability and uncertainty, account
separately for stopping residual, and retain conservative fallback elsewhere.
General 1–2 m bumper clearance remains unverified until line/body geometry or
independent metric calibration is available. No guessed global reduction was
implemented. Existing joint ACC/indicator changes remain preserved and separate.

Reproduce read-only comparison:

```powershell
python -B -m tools.compare_oct11_stationary_stop
python -m pytest tests/test_oct11_stationary_stop_comparison.py -q
```

Only analytical tool, tests, and this report were added. Game control, deployment,
commit/push, and safety settings were not changed.
