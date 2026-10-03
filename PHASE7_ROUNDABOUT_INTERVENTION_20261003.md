# Roundabout stopping and first-intervention evidence

Date: 2026-10-03. Source baseline: `8885bd92ff9665bde9bed1cd51e4302378c4821f`.
The tracked tree was clean when this task began. These changes are local,
uncommitted and not installed. Applicable project material reviewed: Phase 7
Stages 1–3/final, longitudinal diagnostics, commit/curve follow-up,
`PLUGIN_VERSIONS.md` and `DEFERRED_WORK.md`; no applicable `AGENTS.md` was found.

**Verdict: reproduced production defects repaired offline; exact historical
trigger NOT VERIFIED; predictive roundabout entry/wait/restart BLOCKED by
missing traffic and yield evidence.** This is not a live-game repair claim.

## 1. Incident evidence and limits

Console attachment:
`C:\Users\PC\.codex\attachments\f7484bd7-1998-4ca2-b45f-e93e7d6f0fde\Vložený text.txt`.
SHA-256: `9eb809e111e8ee0248a5d1da45605e83fbca58fefaa8dd37c6cfaf7d4909150b`.
Startup identifies `8885bd9`, Autopilot 1.0.2, ACC 1.1.1, Map/DrivePolicy 1.0.3.
This is logged version evidence, not a complete historical installed-file receipt.

Only the following identity is used for the 18:40 event: session `1`, map
`promods-1.59`, dataset `d6cc7936fce4e902761abb5d`, intent
`a0fd32f64f62454896017889684b0373`, revision `7`, build
`24800530a97d42abacc2e82b8f9ee33a`. Later 18:45–18:46 activation attempts and
their emergency/expiry messages are not assigned to the earlier event.

| Local time / monotonic s | SDK frame | Measured event | What it proves |
| --- | --- | --- | --- |
| 18:40:06 / 35237.5424371 | 60380918 | Simple-auto probe: throttle 0.12, brake 0, gear 0, no selector | One-N bounded launch request |
| 18:40:06 / 35237.7511595 | 60614242 | Gear 4, observation age 8.97 ms | Later forward-ratio observation, not selector-consumption proof |
| 18:40:07 / 35237.8735320 | 60714238 | Handoff: throttle 0.05258, steering -0.00905, brake 0, active | Launch handed to the existing controller |
| 18:40:37 / 35267.8535067 | 90646374 | Gear 12, signed speed 12.3409 m/s | Forward driving before the stop |
| 18:40:37–39 | — | `ADVANCED_PREFIX`, then `SAME_EXACT`; same intent/build/revision | A window advance is not proof of changed control authority |
| 18:40:40 | Not recorded for hazard edge | First warning: `Safety hazard lights: on` | First logged intervention symptom; cause/pedal command absent |
| 18:40:40 / 35270.9267300 | 93729584 | Gear 11, 9.6443 m/s, active, vehicle age 1.87 ms | Deceleration with a fresh drivetrain observation |
| 18:40:40 / 35271.7725308 | 94579550 | Gear 9, 2.2602 m/s, active, vehicle age 2.83 ms | Further deceleration; does not establish policy/command freshness |
| 18:40:41 / 35271.9903692 | 94796208 | Gear 0, 0.02743 m/s, inactive | Terminal stationary state, not the cause of initial braking |
| 18:40:41 / 35271.9970610 | 94796208 | Release: zero steering/throttle/brake; selector False | Release after authority loss, with no first reason in the old log |

Related installed replay:
`route-diagnostics/steering-replay-20261003T164041.279542Z-manual_disable.json`.
SHA-256: `03e6862a173f2a93d771f43450834bca7eae7c607fbc935a5a35fc29d33c531a`.
It contains 666 control samples and 3,984 executor samples, with **zero immutable
executor source packets**. The last control sample is at 35270.8575306;
later executor rows do not reconstruct longitudinal arbitration/writes.
`manual_disable` is the old exporter's classification, not independent proof
that the user pressed N to disengage.

Related timing export:
`steering-timing-20261003T164640.526899Z-plugin_stop.json`, SHA-256
`ebaed7073973d836d2cfc78bf4a7fddc5fa021c2696a95a8ee08f7d59ca2f040`.
It contains 853 sparse rows, 833 mentioning this build across several attempts.
For the narrow event, sequences 114–118 record steering ages 44.0, 238.1,
40.6, 30.2 and 79.1 ms, all with matching identity. These are sampled reads,
not all Engine commits. They do not exclude an unsampled expiry or identify
the first brake request. Sequence 119 is already inactive.

The installed combined collector status is `CANCELLED` for
`phase7-longitudinal-20261003-152818`, with **0 accepted samples** and 4 dropped
samples. There is no usable longitudinal collection for this stop. The actual
first rejected policy/command values and traffic actor are unavailable. The
driver's circulating-car observation is recorded as an observation, not a
verified cause. No historical value, pedal trajectory or conflict gap is invented.

## 2. Reproduced defects and changes

| Defect | Before, actual isolated physical writes | Local correction / after |
| --- | --- | --- |
| Slow planner `EMERGENCY` overrides a fresh no-demand traffic packet | Brake 1.0 despite current traffic demand 0 | Schema-1 Autopilot/Engine use immutable current requests; brake 0 |
| Slow planner `AVOID_OBSTACLE` invents an additional braking floor | Brake 0.0825000033 after one 33 ms AP tick with no current brake request | Unbound floor retained only for legacy clients; brake 0 |
| Engine-only safety stop lacks first reason logging/terminal publication | Hazards and stationary disable can occur without an automatic-disable reason | Decision-edge fault record, first reason in log/state/UI/export; zero pedals at simple-auto rest |
| Engine-originated disable labelled manual in replay | Full producer/Engine stop exported as `manual_disable`, empty detail | Same activation's fault exports `automatic_disable` with original reason/record; explicit manual off remains manual |
| Newly received emergency checked against a pre-read clock in the stop path | Concurrent IPC publication is rejected as future; physical brake remains 0.25 instead of current emergency demand 1.0 | Validate after snapshot receipt; moving emergency writes 1.0 immediately, fresh mode-0 standstill still releases brake |

The first two are proven code defects, **not proven historical causes** of the
18:40 stop. The silent Engine path and wrong replay label are reproduced
production transitions consistent with the missing evidence; they do not
recover the historical rejection value. Raw planner state still serves its
other existing presentation/toll/PID-state roles. No claim is made that all
planner influence was removed; the unsafe unbound brake-authority paths were.

Current emergency requests still override propulsion in the same Engine
flush, even if they arrive after the AP tick. Technical producer loss uses the
existing controlled-stop ramp rather than a stale planner's full-brake override.
A genuinely current traffic emergency can still escalate that stop immediately.
The original 500 ms leases, final pre-write validation and timestamp identities
are unchanged. No brake filter, gain change, new regulator or steering change.
Emergency and standstill freshness checks use the time after receiving their
respective observations. No observation timestamp is changed. A future-dated
or expired packet remains rejected by the original validity checks.

For simple automatic mode 0, the existing stationary brake-to-R guard remains:
fresh confirmed standstill releases throttle/brake, cancels longitudinal
authority and leaves selector released. It now publishes the original reason.
Real automatic mode 3 keeps its existing safety-stop/manual-handover contract.
Neither mode gains automatic yield restart or automatic parking-brake release.

## 3. Reason contract, UI and export

Each first event includes `code`, `kind`, `reason`, `producer/source`,
`sequence`, `observed_at` (monotonic seconds), activation `epoch`, route
`context`, observed SDK frame and original observation time. Technical
longitudinal rejection details contain the **actually compared** source,
expected/actual contexts, differing activation/session/map/dataset/intent/
revision/build/geometry fields, observation/decision ages and lease overrun.
Navigation rejections retain the compared steering packet; heartbeat failures
retain its measured heartbeat age. Missing values stay null/unverified.
No reread of a newer packet is passed off as the rejected one.

`EMERGENCY_BRAKE` retains the selected source and consumed traffic evidence.
Existing reactive crossing/lead logic adds only provenance: actor ID/pose/speed,
relative conflict-time/closest-distance basis and any assumed envelope. It is
explicitly `confirmed_route_conflict=false`, `coverage_confirmed=false`, with
no producer timestamp. It does not change the heuristic's thresholds or paths.

First active emergency evidence survives the terminal brake-release/gear/token
transition; a recovered non-emergency output closes that episode. A new
activation cannot reuse an old epoch's record. Unchanged reasons are not logged
per tick; faults keep separate producer slots and the earliest record wins.

Dynamic Island shows **technical controlled handover**, **emergency braking**,
or **yield waiting** from typed records, without creating control authority.
Yield formatting is tested but no yield-wait producer is enabled. Structured
debug dictionaries stay out of the user banner. The first stop remains readable
through stationary disengagement; normal driving is not displayed during a
controlled stop.

The existing journal/combined collector is extended, not replaced:
`longitudinal.events[].intervention` contains the immutable first event beside
`source.requested`, `source.selected`, consumed inputs and returned backend writes.
The analyzer exposes the same field in `write_series`. The intervention is
separately bounded to 16 KiB; producer source remains capped at 32 KiB. Both
count against the **unchanged 64 KiB / 128-event journal**. No background queue,
per-tick disk export, chunk/hash/overwrite change or authority promotion.
Dense replay identity also retains `control_intervention` and the first detail.
Mapping-write return remains distinct from game/DLL consumption.

## 4. Predictive yield: unavailable inputs and explicit restriction

| Required input | Existing source / proof | Limitation / verdict |
| --- | --- | --- |
| Actor ID and XYZ | `Local\\ETS2LATraffic` decoded by `core/sdk/ets2la_data.py` | Numeric ID and pose exist; ID lifetime/publisher freshness unproven |
| Speed/heading | Legacy speed channel and quaternion yaw; invalid fields rejected | Measured instant velocity, not a known future circular route/turn intention |
| Original actor timestamp/generation | `TrafficCapture.observed_at` is receiver time | Missing producer timestamp/generation; double read proves stability only |
| Confirmed actor lane, directed roundabout path, priority | RouteLeadSelector projects onto our LanePath | Geometric candidate, not actor LaneId, turn choice or priority proof |
| Own planned entry | Identified directed GPS LanePath | Navigation path exists; no consumed verified yield line/priority/conflict-zone contract in current Map snapshot |
| Coverage / hidden or missing actor | Up to 40 moving and 40 parked legacy entries | Empty/missing buffer is not a clear conflict zone; no coverage/range certificate |
| Trailer clearance duration and launch uncertainty | Existing SDK articles/wheels and bounded drivetrain launch | No confirmed full active body/coverage model for guaranteed interval occupancy |

Code inspected: `core/navigation/traffic_producer.py`, `core/acc_following.py`,
Engine traffic/lead production, planner, current Map/LanePath/road-network
contracts and Phase 7.3 evidence. No new sensor, DLL, map extraction or inferred
actor route was added. Straight velocity extrapolation is a retained reactive
heuristic, not a proven roundabout trajectory or safe-gap calculator.

**Automatic predictive entry, waiting and restart remain unsupported.** Loss
of a previously tracked following candidate still invokes the existing
handover contract; unknown direction/absence is not promoted to a safe gap.
Normal lane following and speed control remain available, but do not guarantee
roundabout right-of-way. The driver must retain responsibility for entry.
There is no autonomous-game-test recommendation here.

No honest before/after safe-gap, yield-point speed, conflict occupancy or
trailer-clearance metric can be calculated from the missing data. Those are
NOT MEASURED, rather than synthetic successful yield cases. The minimum input
work needed before implementing this feature is one authenticated traffic
snapshot contract with publisher generation/time, actor directed path and
coverage at a verified yield/conflict location. That is separately scoped work,
not another requested drive or an implementation in this task.

## 5. Verification and measurements

Acceptance retains Stage 7.1–7.3 contracts: exclusive pedals, immediate fresh
emergency action, unchanged lease/identity rejection, no old-activation command,
same steering outputs, safe mode-0 stopped release and first-cause preservation.

- Before: original two regressions failed (false full brake, silent Engine stop).
  A further AVOID_OBSTACLE reproduction failed at brake 0.0825000033.
  Engine-only replay classification also failed before its fix.
- 412 targeted tests and 17 subtests passed across joint arbitration, real
  Controller/SCS float mapping, activation/launch/ratio, GPS rolling identity,
  current ACC and UI. After the final replay/reporting changes, 113 focused
  tests and 7 subtests passed, including all 16 new intervention cases.
- Final review added two malformed-packet regressions: rejection reporting must
  not throw before the physical safe stop. Both failed before the type guard.
  The final focused run passed 145 tests and 7 subtests, including all 18 new
  intervention cases and the final UI/replay/collector changes. These runs
  overlap; their counts are not a total unique test count.
- A concurrent-publication stop-path test then failed before its clock-order
  correction (physical brake 0.25 instead of 1.0). Its moving and stationary
  variants now preserve immediate emergency action and the brake-to-R guard.
  **Definitive targeted run: 428 passed, 17 subtests passed**, across 15 relevant
  test modules, including all 20 new intervention cases. Reporting's malformed
  packet type guard was corrected during final review, before delivery.
- New cases cover same-flush emergency after AP, nonconflicting/moving-away
  crossing, unknown direction and other height, expired policy versus foreign
  context, technical stop escalation, changing publication after arbitration,
  manual off/new activation, first-cause UI, combined export/inspect/analyzer
  and automatic/manual replay classification. Existing ACC tests retain
  candidate-loss/no-free-gap, deterministic selection and reverse/stale guards.
- Isolated combined export retains first reason with valid hashes and
  `confirmed=false`, `runtime_authorized=false`; failed/changing input is not
  relabelled as valid SDK evidence. No original collection is modified.
- Windows sandbox blocked pytest temporary-directory access in one run.
  Targeted runs used unique ignored basetemps outside that filesystem restriction;
  this PermissionError is not classified as an application defect.
- All 16 steering benchmark cases are numerically **exactly equal** to `8885bd9`.
  This checks offline controller/dynamics preservation, not game cadence.
- The 8 existing curve-approach plant cases are **exactly equal** to the prior
  ignored receipt `curve-approach-20261003.json`. Brake onset remains
  78.43–86.43 m before entry, entry speed 19.25–20.37 km/h, maximum model
  deceleration 0.968–1.147 m/s², maximum absolute model jerk 1.184–1.767 m/s³,
  zero simultaneous positive pedals. These gains came from the preceding
  committed curve fix; they are not new yield improvements or ETS2 measurements.

Ignored receipts: `roundabout-guard-steering-before.json`,
`roundabout-guard-steering-after.json`, `roundabout-guard-curve-model.json` under
`docs/steering-audit`. Static checks: compileall and git diff/whitespace checks
passed, including the new untracked report and test file.
Full pytest remains for the user. Autopilot version 1.0.2 → 1.0.3;
unchanged Map, ACC, DrivePolicy and Collision versions are not advanced.

## Changed files

| File | Change |
| --- | --- |
| `core/control_timing.py` | Bounded first-cause records and decision-edge logging |
| `core/longitudinal.py` | Current brake authority and actually consumed rejection/emergency evidence |
| `core/engine.py` | Physical-boundary first-cause handling, traffic provenance and stationary release reporting |
| `core/navigation/longitudinal_diagnostics.py` | Immutable intervention alongside the bounded pedal journal source |
| `plugins/autopilot/main.py` | Schema-1 brake authority, rejection details and automatic/manual replay classification; version 1.0.3 |
| `ui/dynamic_island.py` | Concise intervention state and first-cause banner persistence |
| `tools/analyze_longitudinal_evidence.py` | Exported intervention in analyzed write series |
| `tests/test_roundabout_intervention_reporting.py` | Production-flow intervention, provenance, UI and export regressions |
| `PHASE7_ROUNDABOUT_INTERVENTION_20261003.md` | This evidence and limitation report |
| `PHASE7_FINAL_RESULTS.md` | Link to this follow-up and its limited verdict |
| `DEFERRED_WORK.md` | Missing historical cause and unsupported predictive yield backlog |
| `PLUGIN_CHANGELOG.md` | Autopilot 1.0.3 fixes |

## 6. Outcome

The reproduced false brake authority and missing/misclassified first reason are
repaired offline. Historical traffic versus longitudinal expiry/identity at the
first 18:40:40 intervention remains undecidable because its selected pedal
command was not recorded. Existing data are exhausted; no further drive is
requested. Predictive roundabout yield is not implemented on insufficient
inputs, and the live result of these local changes is NOT VERIFIED.

Suggested commit: `fix(control): bind brake interventions and preserve the first stop cause`.
Description: consume current longitudinal brake authority, preserve intervention
provenance across Engine stopping and UI/combined/replay export, and distinguish
automatic disengagement from manual release. No commit or deployment performed.
