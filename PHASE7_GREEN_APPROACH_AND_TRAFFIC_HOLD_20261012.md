# Joint Oct 12 drive regressions: moving green and obstacle hold

## Verdict

**OFFLINE VERIFIED for two reproduced lifecycle defects. GAME NOT VERIFIED.**
The task is **not fully resolved**: exact physical line clearance remains
NOT MEASURED, and the validity of the crossing prediction behind the abrupt
speed drop cannot be decided from the retained actor data. No claimed repair
of those two open properties is substituted with a passing integration test.

No controller gains, geometry, signal selection, 6 m + 2 m reserves, timeout,
steering cadence, DLL or plugin VERSION changed. ACC remains **1.1.9**, explicitly
requested by the user. The coordinated core fixes are recorded under its current
changelog entry. Engine-off failures and MonoCruise are outside scope.

## Build and evidence identity

Working baseline HEAD: `c7339a405542f55d2ac235161e99b019be4bf101`. The existing
local edit to the preceding report's deployment section is preserved. The four
requested reports and project versioning rules were read; no AGENTS.md exists
in the checkout or checked parents.

Installation receipt: `stop-indicators-20261012T175215479Z`, ACC 1.1.9,
Map 1.1.2, TurnSignals 1.0.2. **All 24 target SHA-256 hashes match**, including
the recorded DLL targets. All corresponding source contents matched at entry
after normalizing LF/CRLF. At exit only Engine, service-brake hold and changelog
differ; unchanged dependencies still match. Receipt content, not commit.txt,
establishes the installed implementation. Nothing was installed by this task.

All five exports from the 19:55–20:00 session pass `inspect_replay`, including
immutable reference expansion, hashes, counts and sequence order. Originals and
the original log were not modified. Session is `1`, map `promods-1.59`, dataset
`d6cc7936fce4e902761abb5d`, intent `b733985d8e8f482e91e9912bb3f59470`, revision
`9`, build `c7deb1f7df2c4cc2b3782152542f9636`, geometry
`lane_path/c5a257e52ece6ff2dfec73ec25eefa57c4a7fa6c7ae183508b058e42cec08679`.

| File in installed route-diagnostics | SHA-256 | Dense / execution rows |
| --- | --- | ---: |
| steering-replay-20261012T175912.712989Z-automatic_disable.json | 8c11e8ef05c6459b7a1e12ef96d83b3574cac7e1f22b569aacfe57782ae2946e | 0 / 0; pedal incident |
| steering-replay-20261012T175913.020683Z-automatic_disable.json | 96d50bc3d747d71263c76b94be1531e1d8e2e5cc30626f65f6295b746eddd625 | 941 / 10800 |
| steering-replay-20261012T180012.182653Z-automatic_disable.json | 48a50905aa4aa855d0560da8cf067874768323a883d91ad98b0f664df2b801de | 0 / 0; pedal incident |
| steering-replay-20261012T180012.299925Z-automatic_disable.json | 00411590d961afb46858eebf7220dcab0e6e2ffd43b151430823ba56dc3e10dc | 784 / 3401 |
| steering-timing-20261012T180036.037599Z-plugin_stop.json | 3e4b9fd93785c939530d1624acf6c3ce90b80d2bd02ed8b8fc00e979febfadcd | 519 / 0 |

The pedal histories retain respectively 209 regular + 208 change rows over
19274.5365–19304.5592 s and 238 regular + 56 change rows over
19333.9629–19364.0274 s. Short detailed journals retain 12 and 17 events.
Historical early individual writes have aged out. The log explicitly reports
`SIGNIFICANT_EVENT_EXPORT_DISK_QUOTA`; no additional successful significant-event
file exists for this run. Earlier-run files are not substituted for missing data.

## 1. Green during deceleration: proved deadlock and repair

Activation `19254283455700`. This was not the second incident's low-motion error.
The first recorded intervention is Engine at **19304.5399137 s**, reason
**simple automatic zero-ratio transition expired**. Compared vehicle frame
149677346 was valid, observed 19304.5185557 s, gear 0, speed 0.305847 m/s.
Command frame 149610682 was valid; computed 19304.5071718, expires
19304.87558, selected ACC drive 0.503130, brake 0. Identities matched. This is
not a telemetry or command freshness failure.

| Monotonic decision time | SDK speed | Signal / consumed target | Physical/selected evidence |
| --- | ---: | --- | --- |
| 19303.8432 | 2.588 km/h, gear 4 | yellow; distance 1.5728 m | approaching; brake 0 |
| 19303.9277 | 2.003 km/h, gear 4 | green; distance 1.5185 m | approaching hold override; both pedals 0 |
| 19304.0992 | 1.543 km/h, gear 0 | fresh green | zero-ratio transition, no drive |
| 19304.3916 | 1.244 km/h, gear 0 | valid same-head green, generation 5108 | ACC requests drive, actual pedals remain 0 |
| 19304.5378 | 1.101 km/h, gear 0 | fresh original observations | original zero-ratio deadline 19304.5372509 expired |

The locked head is 1, lifecycle 62554269612253, passage
`45540e750098d8f1fc11bc8b76cd20b1ae161420a94ae48b90dad1891389062f`.
Original red lock generation is 4607, observed 19289.0181503. Retained green
has sufficient phase reserve. No subsequent header is used as the initial check.

Engine's moving release branch required `gear > 0`. The approaching record
could retain a zero brake, so it was not a positive stationary hold witness.
Gear zero then needed propulsion to re-engage, but the hold override withheld
it: a closed-loop authority deadlock. The source condition and captured sequence
both support this causal explanation.

After same-head green confirmation, complete clearance/identity checks and no
other stop, a still-moving simple-auto gear-zero approach now transfers to
the **existing bounded signal launch owner**. Its standing-launch speed ceiling
does not misclassify this already-admitted moving approach. It retains the
existing absolute 2.5 s launch and 0.5 s receipt limits; neither renews each tick.
New commands and SDK snapshots retain their original times. Ordinary ratio-zero,
unconfirmed green, foreign identity, stale data and R gain no new authority.
Gear-positive moving release and the real-automatic D path are unchanged.

## 2. Second circle: proved missing physical stop ownership and repair

Activation `19323842336000`. Earliest intervention is Autopilot at
**19363.9948177 s**, checked 19363.989973, SDK 209008306, observation
19363.9732722, gear 0, speed **0.0392799 m/s**. Forward history was
`planned_brake_transition`, brake_only true, confirmed frame 208891644 at
19363.8495363; its deadline 19364.420478 had **not** expired.
Engine subsequently compared frame 209041638, speed -0.0154679 m/s, within the
existing reverse-motion noise boundary, against valid traffic-selected brake
0.504040. This later snapshot is not evidence for Autopilot's earlier check.

Actual returned brake writes before the fault:

| Backend start (s) | Journal sequence | Written brake |
| --- | ---: | ---: |
| 19363.6755617 | 2961 | 0.4804772 |
| 19363.7499111 | 2964 | 0.4804772 |
| 19363.8166414 | 2967 | 0.5414804 |
| 19363.8829744 | 2970 | 0.5318008 |
| 19363.9604532 | 2973 | 0.5318008 |
| 19364.021433 | 2975 | 0, after revocation |

There is no brake-zero interruption in this retained pre-fault detail. Yet no
service hold was recorded: `planned_stop()` admitted a Traffic stop only when
a qualified semaphore was also present. The actual crossing/obstacle demand had
no such semaphore. At speed <=0.05, the shared gearbox rule correctly required
a physical hold witness and could not find one. This producer/hold contract
mismatch is the repaired defect; the gearbox protection itself is not removed.

Now a validated positive Traffic/obstacle stop can acquire ownership **after an
actual positive write begun during forward motion**, without a signal dependency.
That same acknowledged chain survives ratio zero and standstill. An obstacle
disappearing or an unrelated green never authorizes release. Its missing clearance
contract remains explicit: automatic obstacle restart is unavailable, and the
driver must take over. New stationary brake edges, broken chain, backend loss,
identity change, stale data, reverse gear and backward motion remain protected.
Emergency priority is unchanged. The later EMERGENCY/voice messages do not prove
that emergency caused the earlier technical rejection.

## 3. Abrupt speed drop: attributed, not proven spurious

Retained history shows separate episodes. Before the second circle, curve distance
decreases progressively from 268 m; its radius is roughly 19–23 m. At
19346.5032 s, actual speed is 45.14 km/h and the constrained curve target remains
45.66 km/h, but **Traffic** selects about 0.111 brake. At 19347.569 s speed is
31.70 km/h with cap 43.24 and Traffic demand 0.224. Later the truck drops below
20 km/h and then below 5. This rapid portion is not explained by a 20 km/h Map
target jump. Afterwards, the ordinary curve target progressively decreases to
roughly 21 km/h; a later crossing demand produces the complete stop above.

The final detailed input attributes that later demand to
`directed_crossing_heuristic`, actor **91**, reference conflict progress
705.6711 m, distance 11.2045 m, actor arrival 5.56254 s, ego arrival window
2.22734–3.99718 s, 2 s reserve, raw dimensions
[1.63439, 1.20280, 4.03987] m. The source declares no confirmed route conflict,
no producer timestamp and no confirmed ego envelope. Actor coordinates/yaw/speed
at the early onset are **not retained**; the later actor 91 receipt must not be
assigned retrospectively to that earlier event.

A reproducible measured-speed band contains 19 distinct valid SDK observations:
**47.209 → 17.236 km/h**, timestamps 19346.1289365–19348.2579022, **2.129 s**.
Trapezoidal integration of SDK forward speed gives **20.981 m** (an estimate,
not original route-progress displacement). Peak sampled deceleration is
6.653 m/s² and peak sampled jerk 20.055 m/s³ over retained adjacent 20–200 ms
intervals. SDK noise, shifting and irregular samples limit these derivatives;
they are not certified physical comfort measurements.

**Before → after for this braking algorithm: unchanged.** No legitimate conflict
was removed just to reduce a graph's peak, and no unsupported comfort filter was
added. Proving whether it is false requires the original crossing actor body
pose, yaw/speed and receiver-record identity at the first positive demand. Those
fields are absent from existing early detail and failed significant-event exports.
No new ride or sensor is requested here. This part remains unresolved.

## 4. Excessive physical stopping gap: still NOT MEASURED

The existing stationary collection again passes integrity: 737 samples / 32 files,
configuration `e412f13ad3fb22186614354fd724da0b3dfb1ebcde848323bd222677213d8bc1`.
It lacks current GPS/route identity. Its desired chassis pose is 4.8891 m forward
of the historical hold, 2.3377 m past the old derived target and about 1.07 m
lateral from that historical centerline. It contains neither painted-line
endpoints nor confirmed front-bumper geometry. It cannot justify a universal
offset or certify a local bumper clearance; no such offset was activated.

The new incident histories retain no red stationary rows. Moving residuals at
the green change are not reclassified as a new completed red stop. The historical
2.5514 m residual and user-selected pose remain distinct from this session.

On the exact same closed plant and inputs as deployed HEAD, before → after is:

| Entry speed, both gearbox modes | SDK reference gap to unchanged planning target (m) | Difference (m) |
| --- | ---: | ---: |
| 20 km/h | 0.871572 → 0.871572 | 0.000000 |
| 35 km/h | 1.013040 → 1.013040 | 0.000000 |
| 50 km/h | 0.843077 → 0.843077 | 0.000000 |

Deceleration, jerk, pedal reversals, stop time and green return match baseline
exactly in these six paired cases. Zero red overrun, held brake-zero, positive
pedal overlap, red standstill drive or parking writes; all resume without N.
This proves preservation, **not closer physical stopping**. That reported problem
is not repaired by this task. The minimum missing geometry remains one bound
line/front measurement with vehicle configuration, placement/dataset/direction,
SDK-local front transform, world line coordinates and uncertainty. Existing
photographs/desired pose do not supply it. No after-stop metre-chasing is added.

## Reproduction and verification

New tests use the real native signal reader and actual placed prefab, Policy,
ACC, Autopilot, Engine and Controller with chronological physical test writes.
Additional crossing cases use the original TrafficCapture ABI, directed selector
and actual Map publication. Actor/SDK response is an explicit model; backend
return does not prove ETS2 consumption.

Before correction: **4 failed / 2 passed** in six primary cases (moving green
at 2 km/h and 0.08 m/s in simple auto, plus obstacle hold in both modes).
An intermediate implementation still rejected 2 km/h through the standing-launch
speed ceiling; the complete moving transfer above resolves that path too.
After correction: **18 new tests passed**, including 25 ms delayed write boundary,
R, backward motion, stale signal, backend loss, cancellation, identity change and
TrafficCapture-to-physical hold. The unexpected technical-disable count is
**3 technical-disable cases → 0** in supported final cases; the fourth original
failure was missing real-auto hold ownership, not an automatic disable. All four
primary failures pass now. Deliberate negative tests remain rejecting.
Existing signal hold/green/other-stop, manual, indicator
and first-brake suites also pass their targeted run (92 tests before adding the
four delayed variants). No original safety test expectation was weakened.

The 16 existing steering and 12 longitudinal comfort case outputs match the
preceding deployed benchmark exactly. Paired stop comparison has six cases.
The complete requested suite passed: **2,449 tests and 1,592 subtests, zero
failures, 542.22 s** (`PYTHONCASEOK=1 python -m pytest tests -q`). This is a
whole-suite result for the final lifecycle code, not a claim of game acceptance.
`compileall` passed for both runtime files, new tests and both tools;
`git diff --check` passed. Existing LF/CRLF warnings were kept separate from
code differences. Full suite log: `docs/steering-audit/oct12-joint-regressions/full-suite.log`.

Reproduce in the repository with PYTHONCASEOK=1:

```powershell
python -m tools.analyze_oct12_joint_lifecycle --output docs/steering-audit/oct12-joint-regressions/analysis.json
python -m tools.run_oct12_joint_lifecycle_bench --output docs/steering-audit/oct12-joint-regressions/stop-bench.json
python -m pytest tests/test_oct12_joint_lifecycle.py -q
```

Benchmark baseline is pinned to c7339a4, not whichever HEAD exists in a later
checkout. Large decoded evidence and results remain in ignored
`docs/steering-audit/oct12-joint-regressions/`; original records remain untouched.

## Exact changes and coherent runtime delta

- `core/engine.py`: same-green moving ratio-zero handoff; standing versus moving
  launch distinction using the existing signal-resume witness/deadlines.
- `core/service_brake_hold.py`: non-signal Traffic stop acquires actual physical
  brake ownership; no false clearance or arbitrary stationary brake.
- `tests/test_oct12_joint_lifecycle.py`: full flow regressions and negative cases.
- `tools/analyze_oct12_joint_lifecycle.py`: read-only immutable incident analysis.
- `tools/run_oct12_joint_lifecycle_bench.py`: pinned same-input model comparison.
- `PLUGIN_CHANGELOG.md`: coordinated core follow-up under current ACC 1.1.9.
- This report and a backlog reference; preceding local report edit is preserved.

Only **core/engine.py + core/service_brake_hold.py**, with changelog metadata,
are new runtime delta. All 24 installed receipt dependencies remain required:
ACC 1.1.9, AP 1.3.4, Map 1.1.2, TurnSignals 1.0.2, existing PID/turn-maneuver,
traffic, signal reader, packet-refresh and export code, and unchanged DLL.
Their exact target hashes and candidate delta hashes are in
`runtime-candidate.json`. Do not copy tests/reports/tools, replace settings/cache,
or mix this delta with an older installation. No deployment, commit, push,
arming or game operation occurred. Whole-task GAME VERIFIED is not claimed.
