# Oct 11 destination lifecycle and approach review

## Verdict

**PARTIAL OFFLINE CORRECTION.** Positive near-destination authority and the common
GPS stopping path are reproduced and corrected. Normal completion is verified
offline in both automatic modes, without hazards or parking-brake writes.

**NOT VERIFIED / NOT CHANGED:** the measured front/painted-line relation needed
to reduce the semaphore reserve, and the exact physical brake producer at the
second roundabout. Neither missing observation is replaced by an estimated value.
This report does not close all three requested issues or claim ETS2 success.

## Scope, criteria and build

The first tests, before runtime modification, require earlier distance-based
braking at 50 km/h / 60 m, no discard of a still-positive 20 m GPS destination,
and a physically admitted forward-stop chain followed by normal standstill
release. A zero/removal, stale/foreign observation, R, backend failure, manual
cancel or another stop must not become successful arrival. No new comfort
threshold or stop-coordinate offset is introduced to obtain PASS.

HEAD `787d012a2a78ac917bb5506e0958c32d8d06575f` plus existing local changes.
All inherited changes are preserved. At entry all **20 receipt hashes** and
normalized installed/source contents match. The installed receipt is the
Oct 11 `red-approach-20261011T070258194Z` deployment, with user-reported full
pytest PASS, local uncommitted content and `game_verified=false`.
Installed ACC 1.1.6 / DrivePolicy 1.1.2 / Autopilot 1.3.3 / Map 1.1.1 /
DLL `1.59.3-up-signal-scope`. No installation was changed in this task.

## Exact latest-drive evidence

Existing codecs verify all three supplied exports:

| Artifact in installed `route-diagnostics` | Retained content |
| --- | --- |
| `steering-replay-20261011T071453.485201Z-automatic_disable.json` | 3,358 steering samples, 10,800 execution records |
| `steering-replay-20261011T071453.034423Z-automatic_disable.json` | Immutable pedal incident and about 30 s decision history |
| `steering-timing-20261011T071505.960559Z-plugin_stop.json` | 409 passive timing samples |

Their SHA-256/integrity receipts are recorded by
`tools/analyze_oct11_lifecycle.py`. Dense calculation identity:
session 1 / `promods-1.59` / dataset `d6cc7936fce4e902761abb5d`,
intent `58c53f620a14460b8488d0cc7c6505fc`, revision 7, build
`6eb843e2ac1d457db50b3b855781c4f1`, activation `2638154663000`.
The final fault identity is revision 8 with no intent/build; it is not silently
joined to the earlier authority as a new successful route.

### Signal stop/front reserve

304 original speed samples below 0.2 km/h cover monotonic
2691.18516–2706.7366169 s and progress 317.49262–317.49576 m.
The log confirms planned hold at 09:13:10 and same-head ID 1 green release at
09:13:25, followed by the existing simple-auto handoff. The photograph shows
standstill, a green head and a visually apparent gap, but gives no surveyed
distance, capture-frame binding or truck body-front extent.

The existing control target subtracts **6 m unmeasured front allowance + 2 m
junction standoff** from an authored directed prefab entrance. The stopping
profile additionally reserves **speed * (1 s response + 0.5 s maximum transfer
age)**; this tends to zero with speed. Terminal software holding can stop before
that target (previous model gap about 1.34–1.39 m, not an ETS2 measurement).
These components must not be added to a visually guessed painted-line position
as if they were measured. SDK axle positions are not bumper dimensions.

**No reserve/coordinate reduction is made.** There is no saved controlling
stop target at the photographed stop and no measured front-to-painted-line
relation. Reducing 6 m to an axle distance or inventing a line offset would be
unsupported and could remove necessary entry protection. Ending-green prediction,
current-target approach, continuous terminal brake and green restart remain intact.

### Second-roundabout braking

The actual dense speed trace drops **40.720 -> 27.233 km/h** at
2734.5214307–2735.1936143 s over progress 624.84110–631.12092 m
(17 samples). The LaneId during this band is road UID
5337536214763748492, direction 1, lane 0, prefab `dlc_blkw_57`,
directed curve chain `[11,7,4,17]`. Build/revision do not change there.

`tools/recover_steering_route.py` solves 571 observed edges / 573 measured
vertices with maximum projection residual **2.18e-11 m**. This is the observed
contiguous prefix, not unseen final vertices: the logged initial path was
580 points / 1121.5 m; reconstructed prefix length is 1108.353 m.
Lateral geometry is neither altered nor interpolated across missing data.

On those same recovered inputs, the current curve-only ceiling at the braking
band remains **at least 42.379 km/h**, without an abrupt 40 -> 30 ceiling jump.
The reconstructed calculation uses the explicitly labeled application-speed
proxy where calculation-frame speed is unavailable. It does not prove the exact
historical consumed curve packet, semantic roundabout cap or road classifier.
The roundabout upper bound remains 35 km/h, with tighter actual curves still
allowed to require less. No speed limit is raised to disguise the slowdown.

At 09:13:53–55 the log also records vehicle tracking and repeated
`AVOID_OBSTACLE` transitions overlapping the braking band. Corresponding
significant-event exports failed with `SIGNIFICANT_EVENT_EXPORT_DISK_QUOTA`.
Read-only inspection finds exactly eight earlier significant-event files (Oct 9/10),
6,614,998 bytes in total. The existing writer enforces eight files / 16 MiB;
the **file-count cap is already full**, not a demonstrated lack of disk space.
Nothing is deleted, moved or reconfigured here. Future event measurement is
blocked until separately approved archival preserves originals and receipts
outside the writer's active file set. Raising the limit is not this correction.
The retained pedal history begins at **2763.79717 s**, after the band, and ends
2793.88195 s. Thus the original selected/physical brake is **NOT RETAINED**.
Obstacle coincidence is a plausible competing explanation, not proof of the
winning producer or proof that its demand was wrong. No collision/curve brake
is suppressed and no fallback filter is introduced.

### Destination failure chronology

At 09:14:52.985 Engine declares the destination cleared and discards the route.
At 09:14:52.993 the intent tracker publishes `DESTINATION_REMOVED`, revision 8.
At 09:14:53.010 Autopilot reports missing GPS target and Engine reports an
incomplete steering packet. The last physical-boundary vehicle frame is
236940522, speed **11.07129 m/s (~39.86 km/h)**. Hazards turn on at 09:14:53.112.

The exact original `routeDistance` is not retained. The log's "destination
cleared" text runs for **both zero and any positive <=25 m**; it does not prove
which branch value occurred. The user reports automatic disappearance, which
is preserved as human evidence, not treated as a producer-level arrival event.

Two executable defects are established independently of that missing value:

1. `has_game_destination = routeDistance > 25 or dest_city` discards a still
   positive GPS destination at 20 m, even while `arrival_pending` says arrival.
2. The old 35 m arrival branch directly requests brake and returns before
   schema-1 common arbitration publishes its physical command. It also unwinds
   steering instead of continuing the validated route. There was no normal
   distance envelope above the threshold.

## Implementation

- Keep native route consumption/authority for **all positive GPS distance**;
  do not keep an old route when distance becomes zero or telemetry is missing.
- Plan a GPS distance ceiling from the actual immutable vehicle observation
  through existing Policy and ACC. Reuse the shared stopping mathematics and
  braking mapping, without inventing a red signal object, gains, actuator or
  second controller. Lower signal/curve/vehicle constraints still win.
- Apply the current stop ceiling after smoothing non-stop preferences; do not
  add a second Policy pedal when ACC owns that plan. Final Engine coast guards
  also respect the captured GPS ceiling.
- Schema-1 Autopilot follows the ordinary authority, R, freshness, arbitration
  and steering path during arrival. The unversioned legacy test path remains
  separate; it is not live schema-1 authorization.
- Reuse the existing Engine-owned service record for moving approach and actual
  terminal continuity. Destination clearance cannot resume a signal launch.
  A terminal receipt belongs to the original physical chain/frame and current
  activation/route; it is not a newly timestamped old demand.
- Normal completion requires actual standstill under the existing <0.05 m/s
  guard, a fresh **positive** GPS remainder no greater than the acknowledged
  terminal-entry distance and existing `ARRIVAL_RADIUS` (12 m), an admitted
  terminal brake chain, no signal lock/other stop/intervention, current identity
  and current write lease. The radius is existing completion semantics, not a
  new target shift; the model stops about 2 m short.
- Release automatic inputs once to the driver, set `arrived`, preserve a compact
  original-frame completion receipt, and label the dense replay
  `destination_reached`. No hazard or parking request. UI explicitly asks the
  driver to take over holding; no unattended hill hold is promised.
- Add original GPS distance/time to the existing bounded diagnostic source
  snapshot and an additive ACC destination-selection flag. No SDK/IPC diagnostic
  reads, indexed-codec renumbering, queue or memory-budget increase.

**Zero/removal remains a blocker:** the available SCS/native route interface
does not distinguish automatic arrival cancellation from manual removal or
navigation loss. A zero before confirmed stopping is still fail-closed, not
renamed successful arrival. The new positive-distance path reduces premature
authority deletion, but this task cannot certify every automatic GPS-clear event.

## Before -> after tests and closed plant

With the actual hash-verified installed runtime functions substituted read-only,
the five new positive-distance regressions fail; the zero-removal negative case
still passes. With the corrected runtime they pass. The actual Map/Policy/ACC/
Autopilot/Engine/Controller is used, including chronological physical writes.

The paired plant uses a 280 m validated Map route and explicit modeled GPS goal
at reference progress 240 m. Starting progress 20 m. Both automatic modes are
actually initialized, not merely labeled. At 30 Hz, four integration steps per
tick, 120 ms transport, 350 ms actuator response:
`a = (2.2*T - 4*B)/1.4 - 0.12 - 0.004*v²`, with velocity clamped at zero.
This is uncalibrated, flat-road modeled dynamics. It supplies physical jerk only
within the stated model. Completion uses the existing near-zero speed guard,
not an invented proof of exact zero/bumper position in ETS2.

| Initial speed, both modes | Before: speed crossing reference goal | After: reference gap / speed at completion | Brake onset distance | Max deceleration | Max jerk | Pedal changes |
| --- | --- | --- | --- | --- | --- | --- |
| 20 km/h | 19.780 km/h, no effective arrival brake | 2.007 m / 0.127 km/h | 23.791 m | 1.080 m/s² | 1.866 m/s³ | 1 |
| 35 km/h | 35.230 km/h, no effective arrival brake | 2.035 m / 0.079 km/h | 61.800 m | 1.127 m/s² | 2.120 m/s³ | 1 |
| 50 km/h | 49.435 km/h, no effective arrival brake | 2.246 m / 0.098 km/h | 117.106 m | 1.409 m/s² | 2.676 m/s³ | 1 |

After sample counts per mode: 1302 / 884 / 757; durations 43.400 / 29.467 /
25.233 s. All six reach `arrived`, zero positive pedal overlap, no reference-goal
crossing and no time below 5 km/h more than 10 m from the goal. Before runs do
not stop, so their lower peak jerk is **not** evidence of comfortable arrival.
These new metrics do not certify shorter semaphore gaps or fix the unrecorded
obstacle/roundabout impulse. Front-to-destination/painted-line clearance remains
NOT MEASURED; reference-point gap is not mislabeled bumper gap.

The first model exposed an overly narrow 1.5 m **completion** check: the declared
response reserve physically stopped the model about 2 m short and it kept
waiting. Completion now uses the acknowledged terminal spatial receipt and
existing arrival radius; the braking target is unchanged. This is not a new
minimum driving speed or an arbitrary approach offset.

Regression coverage includes ending green, red hold/green restart, GPS-window
movement, new/removed target, identity loss, stale data, R, cancellation and
backend failure. The original red regression functions are now a frozen
86 KiB code fixture from SHA-verified pre-deployment backup: installing the
fixed runtime had otherwise silently replaced their old counterfactual. Their
comparative expectations are unchanged.

## Verification and reproduction

- 370 targeted tests + 7 subtests passed, including joint stop/lifecycle,
  rolling authority, packet refresh, arbitration, safety and comfort modules.
- 80 targeted existing codec/export/pedal-history and new destination tests
  passed after the additive diagnostic fields.
- Final narrow runtime checks, compileall and diff-check are recorded below.
- **115 passed** after final missing/zero GPS and backend-release guards; includes
  destination, timing, stop/resume, physical commit and existing automatic replay.
- 16 steering cases and 12 non-destination comfort cases are numerically
  identical to the saved Oct 11 baseline. The separate 198-case steering matrix
  is exploratory: the earlier saved baseline has no matrix to compare.
- Six-second diagnostic on/off benchmark: actual control mappings/writes and
  IPC-read counts identical. Engine median 0.577 / 1.597 ms, p95 0.706 / 1.853 ms,
  maximum 1.648 / 3.186 ms. This measures copying IPC/BytesIO with the existing
  journal, not additional live latency caused solely by the two GPS fields.
- No full pytest, game run, deployment, commit or push.

Reproduce from repository (`PYTHONCASEOK=1`):

```powershell
python -m tools.analyze_oct11_lifecycle --output docs/steering-audit/oct11-lifecycle/analysis.json
python -m tools.run_oct11_destination_bench --output docs/steering-audit/oct11-lifecycle/arrival-reproduction
python -m tools.run_oct11_destination_bench --before --output docs/steering-audit/oct11-lifecycle/before-reproduction
```

`--before` uses the verified current installed Oct 11 1.1.6/1.1.2/1.3.3 runtime,
so do not use a future deployment as that baseline. Saved accepted comparison:
`arrival-before` / `arrival-final2` under the ignored output directory. Older
`arrival-after` / `arrival-final` are explicitly rejected intermediate models
which still remained waiting and are not accepted results. Original exports,
photo, log, installation and old checkout were not modified.

## Exact runtime delta and remaining acceptance

Seven coordinated files relative to the verified installed payload:

1. `core/engine.py`
2. `core/longitudinal.py`
3. `core/service_brake_hold.py`
4. `core/navigation/longitudinal_diagnostics.py`
5. `plugins/acc/main.py` **1.1.7**
6. `plugins/drivepolicy/main.py` **1.1.3**
7. `plugins/autopilot/main.py` **1.3.4**

No DLL, Map/steering/geometry change, settings or cache replacement. Source hash
manifest can be regenerated before a separately approved deployment; tests,
tools, fixture and reports do not belong in the runtime delta.

Other task files: this report, changelog, new destination tests/analytical and
model tools, the original-function fixture, and the two historical benchmark
helpers corrected to preserve their counterfactuals. All prior work remains.

Final `compileall` and `git diff --check`: PASS. Full pytest was not run.

After the user's full pytest PASS and explicit deployment approval, one future
user-controlled check can cover ending-green braking, red wait, same-head green
restart, both roundabouts and a positive-distance destination stop. The driver
must take over for unexpected braking, red/target uncertainty, rolling or a
technical fault; do not create emergency traffic or suppress protections. Check
the same-build export and first fault before considering any repeat.
**STOP before that check if the existing significant-event quota is still full**;
otherwise the lost roundabout producer would remain unmeasurable again. Archival
requires separate authorization and is not performed by this task.

This is a prepared procedure, **not a request for another drive now**. A painted
stop target/body-front binding and the lost selected/physical roundabout brake
remain the exact missing evidence. Normal zero-GPS disappearance additionally
requires a producer-level arrival-versus-removal discriminator; it cannot be
solved by refreshing/relabeling an old route. MonoCruise remains out of scope.

## Authorized deployment — 2026-10-11

The user reported the corrected full pytest suite PASS and explicitly approved
deployment. Seven runtime files listed above and the corrected changelog were
installed while UltraPilot and ETS2 were stopped. All 20 prior receipt hashes
matched before copying; all 20 final receipt hashes and all eight source hashes
matched afterward. Installed versions: ACC 1.1.7, DrivePolicy 1.1.3,
Autopilot 1.3.4. DLL, settings, map-cache and commit marker were not changed.

Verified backup of the previous receipted payload:
`C:\Users\PC\AppData\Local\UltraPilotBackups\destination-lifecycle-20261011T095307684Z`.
Ignored local receipt:
`docs/steering-audit/manual-deployment-destination-lifecycle-20261011T095307684Z.json`.
The installation receipt was replaced atomically with rollback protection.
No application, game or diagnostic collection was started. Old diagnostic
files were not moved or deleted; event archival still requires authorization.
**DEPLOYED / HASH VERIFIED; GAME VERIFIED remains false.**
