# Phase 7 — deployed 1.3.1 signal coverage and second-approach review

Date: 2026-10-09. Incidents: the Oct 8 21:31–21:34 local-time session.

**Overall verdict: BLOCKED for complete resolution of both driving incidents.**
Two reproducible signal-path defects are corrected offline: silent propulsion
past an unassigned live head, and suppressing its actual fresh detected color
in the HUD. The historical first loss boundary and the original early braking
receipt are not available. No guessed geometry/profile correction is applied.
This report does not claim that the crossed red is now covered in ETS2.

Existing local changes are retained. No deployment, game input, commit,
new collector, timestamp renewal or timeout increase occurred. The full pytest
suite remains reserved for the user.

## Installed implementation and sources

HEAD: `787d012a2a78ac917bb5506e0958c32d8d06575f`, with existing local additions.
At task entry all seven files listed in `manual-deployment.json` matched both
the receipt and repository bytes. The receipt declares Autopilot **1.3.1**,
local uncommitted additions and the user's previous full-suite PASS. It is
not a pristine-HEAD deployment certificate.

Controller, Map, ACC, DrivePolicy, `ets2la_data.py`, `prefab_signals.py`,
`route.py` and `road_network.py` also match after LF/CRLF normalization.
The installed game DLL and repository asset both have SHA-256
`53d8c54d2b71abb2f1d2de8cb68cd096f22f8385f750f46ce07af105295c3bcf`,
matching the archived candidate-f build receipt. The preserved game log loads
`1.59.2-up-signal` against ETS2 `1.59.1.3s`.

The pinned producer source is commit
`1f16156b9b37b70cf182c2bc09120fa1b234e129`. Its semaphore writer obtains
nearby prefab `semaphore_instances`, carries the instance ID, actor placement
and quaternion, classifies a traffic-rule light as kind 1, and writes its
state. The existing sidecar attaches actual acquisition QPC time, generation,
render frame and lifecycle in one sequenced schema-2 snapshot. Python checks
that snapshot before kind/pose/color decoding. A successful read is not proof
of complete nearby coverage or live signal-to-lane ownership. No producer
source or DLL was changed in this task.

The one read-only check of the currently available producer mapping returned
`producer-timed signal plugin unavailable`. It was taken after the recorded
session and is explicitly **not** substituted for its historical snapshot.

Full runtime audit and original hashes are in ignored
`docs/steering-audit/oct8-deployed/runtime-audit.json`. Installed files remain
unchanged; the working-tree candidate is now Autopilot **1.3.2**. Other plugin
implementations/versions are unchanged by this continuation.

## Captures and separation of activations

Every capture below passed the existing `inspect_replay` integrity check.
Their session/map/dataset, original clocks, calculation identities and log
transitions identify this session; filenames alone were not used.

| UTC filename suffix, 2026-10-08 | Stored evidence | Binding / coverage |
| --- | --- | --- |
| `193225.467850Z-manual_disable` | 794 calculation / 4,547 execution rows | Intent `ecd2369d7b15425d8d0a180384932eaf`, revision 6, build `ed103f70dca84da5a7275330e8d2137d`; 28482.055–28519.134 application clock |
| `193401.934129Z-automatic_disable` | Pedal incident, 17 detailed events and 280 summary/change rows | Activation 28530315383000; history 28585.721581–28615.7790871, **30.057506 s**; summary complete, detailed ring incomplete |
| `193402.167118Z-automatic_disable` | 1,652 calculation / 5,633 execution rows | Calculation intent `2937eb3824c1475eba8aa5740b2b6653`, revision 9, build `dfc8e022187f494a9e8f786bb39cc136`; 28530.653–28615.722 |
| `193419.958526Z-plugin_stop` | 359 timing rows | 111 fully identity/Map/publication-matched rows |

Map is `promods-1.59`, fingerprint `d6cc7936fce4e902761abb5d`, integer
session 1. Separate activation epochs/intents/builds distinguish the two runs.
Both dense exports have **zero immutable execution source packets**. Their
steering headers are not used to fabricate longitudinal physical writes.
All four exports exist; the missing information is absent content/aged-out
coverage, not an unfinished export. Older 19:55/20:06 incidents are excluded.

| Local time | Proven event |
| --- | --- |
| 21:31:47.838 → 21:31:48.270 | First N, simple-auto launch, gear 7, successful handoff on revision 6 |
| 21:32:25.293 | Manual N disables; no automatic failure is inferred |
| 21:32:32–33 | TRUE_REROUTE, then new SAME_EXACT build/revision 9 |
| 21:32:36.472 → .889 | Second N, 0.12 launch without D pulse, gear 4 and successful handoff |
| 21:33:05.173 / .687–.885 | TrafficAnalysis reports a tracked placeholder; planner enters AVOID_OBSTACLE briefly |
| 21:33:09.048 | Another TrafficAnalysis tracking event |
| 21:34:01.877 | Game destination is reported removed; route identity is cleared |
| 21:34:01.903 | First technical intervention: GPS steering packet incomplete against the cleared route |
| 21:34:19–21 | Normal UI shutdown and timing export |

TrafficAnalysis's “vehicle tracked” message is a placeholder generated from
positive obstacle level, not a measured actor identity. The AVOID_OBSTACLE
contract establishes a contemporaneous scalar traffic level **>0.3 and ≤0.7**;
it does not preserve the exact actor, TTC, packet or physical brake value.
The final destination-removal intervention is separate from the two reported
regressions. Its post-clear header is not used to identify the earlier route.

## A — missed red: evidence, reproduced defects and repair

Three actually traversed placements were reconstructed with the real parser,
directed curve validation, coordinate transform and signal preparation:

| Token / directed curves | Authored control | Entry XYZ |
| --- | --- | --- |
| `dlc_blkw_80`, `(10,12,6)` | curve 10 / ID 3 | 34677.958814, 6.902344, 45931.617787 |
| `dlc_blkw_80`, `(30,4,13,24)` | curve 30 / ID 1 | 34753.473501, 6.902344, 45663.958017 |
| `dlc_blkw_57`, `(11,7,4,17)` | curve 11 / ID 1 | 34841.060601, 7.445313, 45406.063039 |

The 70 KiB tracked fixture contains these three real placements, two real
descriptors, nine nodes and source hashes. The heads injected in tests are
**modeled producer inputs**, not recovered historical heads. The user did
not identify which particular head/crossing was the observed red.

Historical limitation: the first run exports steering only. The second run's
retained pedal window begins after the earlier crossings. Raw kind/ID/XYZ/yaw,
producer flags/color and the consumed `signal_passages` at the missed crossing
are not stored. It is therefore impossible to choose, from those exports,
between missing producer head, ID mismatch, missing passage, placement/yaw/
height rejection or identity loss as the **first historical boundary**.

Two software defects are nevertheless directly reproducible on 1.3.1:

1. A fresh actually observed forward route-aligned head that cannot be
   assigned becomes `candidate=None`, invalid selection and no brake demand.
   Optional traffic handling then continues propulsion without distinguishing
   unknown regulation from clear road. Eight baseline counterexamples fail
   across the real placements/both modes or missing metadata; an additional
   case shows a later qualified head hiding an earlier unassigned conflict.
2. The HUD explicitly chose `off` for **every** detected-only head, even when
   its real observed color was red. The production presentation-function
   reproduction failed before repair; it now retains fresh producer-timed
   color with the unassigned label. Untimed/expired/future data remain gray.

Candidate behavior:

- Keep actual placed-ID control selection. Do not restore nearest-head control
  fallback or create a red/stop target from a map ID alone.
- Check the existing bounded original heads for an unresolved forward approach
  conflict using the original directed route, orientation, elevation and
  corridor projection. This is an **uncertainty heuristic**, not proof that a
  head belongs to our lane. Foreign direction/deck/distant lateral heads do
  not become stops. At most 40 heads/512 edges per projection; no growing queue.
- A live unassigned approach conflict requires takeover. Carry its original
  signal deadline, exact head and rejection through the common longitudinal
  contract. Autopilot and final Engine both inhibit propulsion; the existing
  controlled-stop state publishes **“Prevezmite riadenie …”** before the
  diagnostic technical text can be truncated by UI layout. No automatic resume
  after technical loss and no parking writes.
- A later separately qualified head remains separately identified/displayed,
  but cannot authorize propulsion through an earlier unresolved conflict.
  Preserve the locked actual control during waiting, its unknown dependency
  across producer reset/loss, continuous braking and qualified green restart.
- Current urgent traffic evidence remains available to safety handling;
  entering the safety state cannot reduce an actual emergency to 0.70.
- Reuse existing bounded first-fault/pedal/replay export. Fixed comparison
  fields and the fixed reason are interned within the unchanged 8 KiB receipt;
  original times/IDs/pose are restored explicitly, incomplete vectors rejected.

The old four unassigned-red integration expectations were changed explicitly:
they previously demanded continued positive drive past the unassigned head.
They now require no controlling-light assignment/no fabricated planned hold,
but a declared technical takeover and zero propulsion. Genuine locked-head,
reset, foreign-head and continuous-brake expectations remain enforced.

**Coverage verdict:** qualified modeled red → hold → fresh same-head green
passes on all three real placements and both modes. Historical red coverage
is **NOT VERIFIED**. Empty/unavailable detection is not a certification of
unregulated road. Producer coverage, live ID namespace/attachment, orientation
and physical head height remain limitations; the new projection cannot prove
coverage for a head which the producer does not provide or cannot localize.
This candidate must not be advertised as supporting all autonomous crossings.
Derived targets still use the existing unmeasured 6 m front allowance + 2 m
stand-off. They are not painted lines or measured bumper clearance.

## B — early speed dip and HUD transition

The user's locator is approximately 50 m before the second roundabout while
roads changed in the HUD. The revision-9 replay contains two early dips around
progress 333–378 m, with recovery before progress 394 m. These remain in the
same calculation identity; tracking progress does not regress. No build,
revision or reference-origin reset occurs at that interval.

Existing projection and fraction measurements uniquely determine **406
planar vertices over a 785.217755 m observed prefix**. 393 edges have two
independent fractions; adjoining known endpoints resolve remaining observed
edges algebraically. No missing vertex is interpolated. Maximum overlap
residual is **3.00e−11 m**, projection round-trip residual **2.30e−11 m**.
The final unobserved part of the published 800.859277 m path is not invented.

Production `Route.curve_profile_ahead` is rerun on that original geometry with
the original cached calculation projection. Calculation speed is absent,
so application speed is a **marked proxy**. Cruise targets 20/35/50/60/90/160
km/h are sensitivity inputs, not recovered driver settings. Missing turn-event
publication/posted speed limit cannot be reconstructed from those fields.

| Application clock | Original calculation / application SDK frame | Progress | Application speed proxy | Reconstructed curve-only target range | Radius / distance at 50 km/h requested |
| --- | --- | --- | --- | --- | --- |
| 28559.345 | 112795488 / 112828820 | 333.58 m | 42.99 km/h | 50.12–50.57 km/h | 18.729 m / 112 m |
| 28560.063 | 113462128 / 113545458 | 340.72 m | 31.63 km/h | 48.93–83.45 km/h | 19.062 m / 104 m |
| 28560.859 | 114278762 / 114345426 | 346.80 m | 23.67 km/h | 47.86–82.98 km/h | 21.063 m / 96 m |
| 28562.462 | 115895364 / 115945362 | 359.23 m | 33.38 km/h | 43.57–53.25 km/h | 20.559 m / 84 m |
| 28563.125 | 116562004 / 116595336 | 365.32 m | 31.22 km/h | 42.07–51.87 km/h | 18.823 m / 80 m |
| 28563.926 | 117361972 / 117411970 | 371.47 m | 20.39 km/h | 40.92–51.62 km/h | 20.293 m / 72 m |
| 28566.991 | 120411850 / 120445182 | 392.25 m | 33.23 km/h | 32.23 km/h | 19.223 m / 52 m |
| 28570.233 | 123661720 / 123711718 | 417.03 m | 22.29 km/h | 22.10 km/h | 18.936 m / 28 m |

This geometry query does not reproduce a zero-distance/fallback impulse at the
earlier road/prefab/road transition. The later tighter arc legitimately has
a roughly 21–22 km/h curvature ceiling; 35 km/h remains an upper bound, not
a minimum. No speed-planner, controller, geometry, gains or filtering changed.

The **first actual braking packet cannot be recovered**: the pedal window
starts at 28585.721581, well after clocks 28559–28564. The required consumed
traffic `brake_basis` (actor/TTC/crossing), ACC/policy requests, original posted
SDK limit and backend writes at those frames have aged out or were not
exported. AVOID_OBSTACLE proves a brief traffic demand, not its exact value or
full physical effect. Later history begins with actual returned brake
0.0342484638 and source `traffic`; it is not attributed to the earlier dip.
The earlier dense run belongs to another activation and cannot fill this gap.
The actual HUD path/zoom publication was not captured either.

**B verdict: cause NOT PROVEN; no random continuity patch.** The supplied
recovered curve values pass through real Policy/ACC/Autopilot/Engine/Controller
in both modes with zero brake impulses. That counterexample is an offline
input scenario, not proof that the same curve packet reached the game.

## Timing and verification

111 matched timing rows, original monotonic clock; sampled read is not first
delivery. Median / p95 / maximum:

- SDK age at sampled read: **36.358 / 223.256 / 235.928 ms**.
- Lane-update completion → calculation: **18.772 / 199.401 / 309.560 ms**.
- Publication completion → sampled read: **9.615 / 200.280 / 217.811 ms**.

No matched observation exceeds 500 ms. This is not evidence that steering
staleness caused either reported incident. The scheduler and limit are intact.

- **299 targeted tests and 20 subtests passed in 48.78 s**, including real PPD
  cases, both automatic modes, head loss/reset, red/hold/green restart,
  foreign head/ID-only refusal, emergency priority, backend/identity/stale
  regressions, HUD, geometry recovery and automatic/combined export checks.
- Steering: **16 cases numerically identical** to the previous candidate.
  General longitudinal comfort: **12 cases numerically identical**. These
  do not certify signal coverage or comfort of the historical dip in ETS2.
- Cached decode/selection operation, 500 samples, 40 heads, 10,000 points:
  final baseline median / p95 / max **0.1339 / 0.1459 / 0.2725 ms**;
  final candidate **0.3166 / 0.3400 / 0.4827 ms**. This measures the operation,
  not live end-to-end scheduling. No additional diagnostic SDK/IPC reads,
  live storage limit or synchronous tick disk export was added.
- Compileall, added-file whitespace and `git diff --check`: **PASS**.

Candidate runtime files: `core/engine.py`, `core/longitudinal.py`,
`core/sdk/signal_snapshot.py`, `core/navigation/longitudinal_diagnostics.py`,
`plugins/autopilot/main.py`, `ui/visualization.py`. New/updated narrow tests,
real fixture, analysis/operation tools, changelog and backlog accompany them.
All earlier stop/coast/diagnostic work is preserved. No DLL change or deployment.

## Reproduce and remaining evidence

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python tools/analyze_oct8_signal_stop.py --record steering-replay-20261008T193225.467850Z-manual_disable.json steering-replay-20261008T193401.934129Z-automatic_disable.json steering-replay-20261008T193402.167118Z-automatic_disable.json steering-timing-20261008T193419.958526Z-plugin_stop.json --log-from '2026-10-08 21:31:00' --output docs/steering-audit/oct8-deployed/evidence.json
python tools/recover_steering_route.py 'C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics\steering-replay-20261008T193402.167118Z-automatic_disable.json' --build dfc8e022187f494a9e8f786bb39cc136 --output docs/steering-audit/oct8-deployed/curve-recovery.json
```

Remaining precise evidence: **A**, the original producer head/snapshot and
consumed passage selection at the crossed light; **B**, the original bound
longitudinal receipt and physical writes around SDK 112795488–117411970,
including traffic actor/TTC, posted limit and HUD publication. The existing
exports cannot recreate those fields. No additional drive is requested here.
New unassigned-head intervention export now retains the exact rejected head
and original timing; it does not recover the missing historical data.

**Offline signal-path repairs are verified; full incident resolution and live
coverage remain BLOCKED.** Do not deploy this as a declaration that the crossed
red and the speed dip are both fixed. Full-suite review is the user's gate:

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python -m pytest tests -q
```
