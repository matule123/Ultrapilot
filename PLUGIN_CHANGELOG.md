# Plugin changelog

Release history for individual plugins. See [PLUGIN_VERSIONS.md](PLUGIN_VERSIONS.md) for versioning rules.

## Core/application fixes — unreleased, 2026-10-05

- Retain the same fresh locked signal head across passage of the SDK reference within a bounded 20 m backward lookup, and preserve its lock through the existing bounded restart handoff. Keep ahead-only acquisition, authority, lifecycle, placement, ambiguity and green-generation checks.
- Label signal distance as SDK-reference-to-head with unverified stop-line geometry; preserve it in the existing compact diagnostic receipt. Do not invent a painted line or vehicle-front offset.
- Record the last protective ACC target ID, status and explicit unconfirmed flag in the existing first-fault details without replacing original identity/time evidence.
- Paired offline reproduction and remaining physical-entry/stop-line limitations: [PHASE7_TRAFFIC_APPROACH_AND_SIGNAL_20261005.md](PHASE7_TRAFFIC_APPROACH_AND_SIGNAL_20261005.md).

- Propagate the original limiting input's deadline provenance through effective longitudinal dependencies; do not let empty optional traffic or nonbinding higher limits expire unrelated fresh drive decisions.
- Use one activation/route-bound, finite zero-drive refresh transition in Autopilot and Engine. Retain the original evidence times and 500 ms limits, refuse expired pedals, and stop safely if a required producer does not recover within the fixed bound.
- Recheck identity and expiry after diagnostic binding and opposing-pedal release, immediately before positive backend I/O. Record actual write start/return and remaining validity without claiming game consumption.
- Preserve the existing acknowledged forward-started service-brake chain during refresh, including moving planned braking before stationary hold. Never seed a new stationary brake edge or manipulate parking brake.
- Retain compact original deadline receipts in the existing bounded pedal journal and first-fault details. Restore explicit fields on reading/export; keep the same allocation/event limits and quiet logging.
- Attribute route-candidate expiry to the actual consumed Map projection and an explicitly unverified receiver budget. Do not fabricate traffic producer acquisition time, generation or coverage.
- Offline reproduction, cadence comparison and remaining live limitations: [PHASE7_LONGITUDINAL_HANDOFF_20261005.md](PHASE7_LONGITUDINAL_HANDOFF_20261005.md). Core changes do not release unchanged Map or Controller components.

## Core/application fixes — unreleased, 2026-10-04

- Check the producer-timed red signal and longitudinal launch restrictions before a stationary propulsion probe. Keep a driver-held request explicitly pending with zero SDK pedals; this is not autonomous stationary holding or an active autopilot claim.
- Transfer a confirmed, moving launch handoff to the existing planned service-brake arbitration without a release-all gap. Preserve active continuous waiting, locked-head green clearance and bounded restart.
- Display active supported signal waiting as “Čakám na zelenú”; display stationary activation without a forward-started brake witness as requiring the driver to hold the vehicle. See [PHASE7_JOINT_LIFECYCLE_RELIABILITY_20261004.md](PHASE7_JOINT_LIFECYCLE_RELIABILITY_20261004.md) for the remaining stationary-hold blocker and reproduced lease budgets.
- Keep the planned service-stop witness independent of passive diagnostic truncation. Retain only fixed consumed fields; real joint ACC/DrivePolicy/signal inputs must not erase brake continuity evidence.
- Seed the existing continuous service-brake state from an actual positive planned brake write during the already validated, bounded moving zero-ratio transition. Do not authorize anonymous neutral, stationary re-press, reverse or expired launch.
- Compact identical metadata within an immutable pedal-journal decision, restoring explicit fields on reading/export. Account for shared provenance once while preserving the 64 KB/128-event limits and ordered paired writes.
- Preserve the current simple/real-automatic launch, signal clearance contract, steering behavior and 500 ms freshness checks. Core-only changes do not bump unchanged plugin versions.
- Verification and live limitations: [PHASE7_SIGNAL_LIFECYCLE_REGRESSION_20261004.md](PHASE7_SIGNAL_LIFECYCLE_REGRESSION_20261004.md).

## Map

### 1.0.7 — 2026-10-05

- Select the most restrictive existing distance/speed curve envelope over the unchanged preview samples, so a sharper distant apex cannot hide an earlier bend. Supply actual SDK speed at both Map production query sites; preserve geometric-only callers.
- Preserve LanePath, lateral controller, steering scheduling, freshness limits and the existing topology-specific 35 km/h roundabout ceiling. Ordinary roads receive no global roundabout cap.
- Earlier curve-entry restriction is verified offline; uniform jerk improvement and actual physical entry speeds remain unverified. See [PHASE7_TRAFFIC_APPROACH_AND_SIGNAL_20261005.md](PHASE7_TRAFFIC_APPROACH_AND_SIGNAL_20261005.md).

### 1.0.6 — 2026-10-04

- Add directed roundabout entry distance to the immutable longitudinal profile using existing LanePath turn events and calculation progress. Preserve curvature, geometry and original SDK times; ordinary prefabs receive no roundabout cap.
- Offline evidence and live limitations: [PHASE7_LEASE_AND_ROUNDABOUT_20261004.md](PHASE7_LEASE_AND_ROUNDABOUT_20261004.md).

### 1.0.5 — 2026-10-04

**Fixed**

- Classify and publish the road speed constraint from the actual SDK pose used after slow reference preparation, retaining its original frame and observation time. Prevent the initial road-input lease from prematurely expiring a newer longitudinal command.
- Reuse prepared classification only for the identical pose and RoadNetwork object; query the existing classifier again when the real pose changes. Publish this constraint after the steering packet so classification cannot delay that packet's delivery.
- Preserve the original minimum input-expiry propagation, 500 ms freshness checks, road-cap values, geometry and both controllers. No old input receives a new timestamp.

### 1.0.4 — 2026-10-04

**Fixed**

- Rebuild the validated trajectory when manual retreat leaves an inactive truck behind its previous trimmed start on the same uniquely confirmed first lane and elevation layer.
- Bind the new steering packet to the replacement build and actual SDK pose. Do not rebuild to bypass projection failures during active or pending driving, on another deck or on repeated lane occurrences.
- Preserve lane topology, the 2.4 m projection limit, the steering controller and the 500 ms freshness limit.

### 1.0.3 — 2026-10-03

**Fixed**

- Query the existing directed curve geometry over a braking-distance horizon instead of a fixed 60 m window. Retain the requested-speed horizon during deceleration, clip to available route geometry and bound the query to 400 m.
- Preserve steering geometry, lateral preview, packet timestamps and freshness limits.

### 1.0.2 — 2026-10-03

**Fixed**

- Bind the road-class speed constraint to the position, SDK frame and original observation time used for classification.
- Include the unchanged anticipatory curve profile in the immutable steering calculation for longitudinal consumers; prevent scalar radius/distance pairing across ticks.

**Preserved**

- Steering geometry, regulator, packet cadence and the 500 ms freshness limit.

### 1.0.1 — 2026-10-02

**Fixed**

- Recheck SDK observation freshness after localization.
- If the observation becomes stale during preparation, allow at most one fresh SDK read and localization retry.
- Reject control authority if no new valid observation is available.

**Preserved**

- Route identity checks and the 500 ms freshness limit.
- Existing steering controller behavior.

**Known limitation**

- This release does not establish or eliminate the internal cause of the long reference-preparation pause.
- Offline verification is not a live-game result.

Commit: `3ef65c7`.

### 1.0.0 — Versioning baseline

- Introduced independent version tracking for existing map dataset, localization and navigation-packet functionality.

## Autopilot

### 1.2.1 — 2026-10-05

- Compose the pedal command lease from inputs that actually constrain the decision, preserving each original limiting source/time/frame through speed-ceiling coast decisions.
- Request the shared bounded zero-drive transition when an otherwise valid decision has insufficient handoff reserve. Genuine stale/foreign/invalid evidence and a hung required producer retain controlled-stop behavior.
- Preserve existing launch, continuous signal waiting/restart, pedal ramps and lateral steering. Coordinated core/ACC/DrivePolicy changes are required; live behavior is not yet verified.

### 1.2.0 — 2026-10-04

**Added**

- Resume an existing continuous service-brake wait from two new producer-timed green acquisitions of the same route-selected, locked signal. Reuse the bounded simple-automatic launch and real-automatic Drive-confirmation paths without a new activation or parking-brake command.
- Reset the prior pedal-ramp state once at the validated restart transfer; current safety and other braking demands still take precedence.
- Permit a stationary zero ratio in real automatic only under the current Engine-owned brake witness or bounded restart confirmation.
- Expose waiting/restarting transitions and compact original signal provenance through the existing UI and combined journal.

**Requirements and limitations**

- Requires the coordinated core update and the version-2 signal sidecar from the separately built ETS2LA 1.59 plugin candidate. Legacy buffers cannot authorize restart.
- Route projection and head orientation are a relevance heuristic, not a proven signal-to-LaneId binding. Ambiguity, missing/stale data, another uncleared stop reason, or authority loss prevent restart.
- Isolated publication/load and backend-write tests do not confirm game memory patterns, uninterrupted SDK consumption, hill holding or live restart.

### 1.1.0 — 2026-10-03

**Added**

- Accept an Engine-owned continuous service-brake witness in the shared simple-automatic ratio transition. A planned approach that physically wrote positive brake during forward motion can wait at zero speed/ratio without the former false ratio disengagement.
- Keep current SDK/route/activation checks and reject interrupted write chains, reverse, motion during holding and technical faults. No parking-brake control or unverified automatic restart is introduced.
- Expose planned waiting and its missing clearance proof in the existing UI and bounded combined journal. Missing signals, unversioned green or disappeared traffic do not authorize resumption.

**Limitation**

- Software-write continuity and the user-observed manual-pedal model are not proof of uninterrupted DLL/game consumption. The current traffic buffers lack producer time/generation for safe automatic release and restart.

### 1.0.4 — 2026-10-03

**Fixed**

- Move routine per-second control/frame diagnostics from INFO to DEBUG. Keep shared diagnostic snapshots and replay recording independent of console verbosity.
- Preserve activation, disengagement and intervention events at their existing visible levels. No controller, pedal, transmission or steering-timing change in this plugin release.

### 1.0.3 — 2026-10-03

**Fixed**

- Consume emergency/obstacle braking from current immutable longitudinal requests instead of an unbound, slower planner state; retain the legacy pre-schema behavior and immediate current emergency response.
- Preserve the first control-intervention reason across controlled stopping, stationary simple-auto brake release and later activation/gear cleanup.
- Export an Engine-originated safety disengagement as automatic rather than manual, with the first decision record; keep explicit manual disengagement separate by activation epoch.
- Retain the actually rejected producer values for fault reporting instead of rereading a later packet. Steering, launch/handoff, transmission mode rules and freshness limits are unchanged.

**Known limitation**

- Predictive roundabout yield and automatic waiting/restart are not implemented: actor source timestamps, confirmed directed conflict paths, yield position and coverage are unavailable. Reactive traffic candidates are not proof of a safe entry gap.

### 1.0.2 — 2026-10-03

**Fixed**

- Pace ordinary throttle recovery at 0.8 input/s while withdrawing drive immediately.
- Interpret the existing EcoDrive rise preference in elapsed time rather than once per tick; never smooth zero drive or braking withdrawal.
- Preserve emergency brake bypass, paired-command arbitration, launch/handoff and unchanged steering.

**Known limitation**

- A pedal-rate bound is not a measured ETS2 acceleration or jerk limit; comfort is verified only in the documented offline model.

### 1.0.1 — 2026-10-03

**Fixed**

- Include ACC deceleration in the existing service-brake arbitration.
- Clear held throttle when any brake is applied; prevent EcoDrive from restoring it during braking.
- Publish one paired, identity-bound longitudinal command with its deciding source, reason and inherited expiry.
- Clear drive during stationary toll payment and clear the paired command on shutdown.

**Known limitations**

- Comfort gains and ordinary pedal ramps are unchanged. Offline arbitration verification is not a game-comfort result.

## ACC

### 1.1.4 — 2026-10-05

- Acquire a protective following dependency only within the current active/pending activation when a candidate constrains the effective plan, is slower than actual motion or is hazardous. A passive or nonbinding candidate must not create a later target-loss technical stop.
- Clear acquired target state across passive/disabled/changed-authority states; retain fail-closed handling for loss of an acquired limiting or hazardous target. Empty legacy traffic is not confirmed clear coverage.
- Preserve the acquired target ID in the existing command/fault receipt with explicit unconfirmed status; keep the speed controller and protective following law unchanged.

### 1.1.3 — 2026-10-05

- Retain original leases of effective speed constraints, required traffic and followed-target evidence without inheriting unrelated higher limits or empty uncovered traffic.
- Recompute a decision needing refresh on a repeated SDK frame when producer inputs advance, without repeating PID integration or renewing the frame's original observation time.
- Publish the limiting deadline provenance and handoff-reserve state. Preserve speed-controller gains, target-loss refusal and immediate urgent braking.

### 1.1.2 — 2026-10-04

- Apply the existing distance/deceleration envelope to a 35 km/h roundabout upper ceiling. Tighter curves and traffic retain precedence; lateral gains, pedal ramps and emergency limits remain unchanged.
- Retain leases of effective speed constraints without letting a higher nonbinding static map cap expire a fresh lower-speed decision. Preserve dynamic evidence leases and final Engine checks.

### 1.1.1 — 2026-10-03

**Fixed**

- Constrain the existing speed PID with the same identity-bound curve-entry envelope used by Autopilot, including its upstream expiry. Avoid powering toward a higher curve target when the separate curve-brake request releases.
- Preserve PID gains, traffic handling, emergency bypass and pedal ownership.

### 1.1.0 — 2026-10-03

**Added**

- Apply route-projected traffic candidate speed ceilings through the existing speed PID and paired pedal arbitration.
- Retain target attribution within a bounded gap tie while every nearer hazard still constrains speed and emergency response.
- Publish explicit unverified-candidate, unavailable-source and driver-takeover states; no bumper-clearance or complete-coverage claim.

**Fixed**

- Prevent missing, expired, ambiguous or empty/uncovered traffic after an observed target from restoring drive; require driver acknowledgement after target loss.
- Preserve original evidence expiry and immediate emergency demands, including while target-loss handling is latched.
- Hand low-speed following to the driver rather than introduce unverified stop-and-go.

**Known limitation**

- The installed legacy traffic ABI has no publisher timestamp/generation, actor LaneId or coverage certificate. Reliable live following remains unverified.

### 1.0.2 — 2026-10-03

**Fixed**

- Use the existing speed PID as one bounded signed drive/service-brake request, including downhill load compensation.
- Remove target derivative kick, condition integral accumulation on available authority/output, and reset memory on invalid timing, identity changes, inactive control and external braking.
- Use original SDK observation intervals; duplicate frames do not advance integration or renew packet validity.
- Pace only upward target recovery, apply lower constraints immediately and add service-brake hysteresis.
- Validate speed preferences and preserve immediate emergency demands and original evidence leases.

**Known limitation**

- New gains are evaluated across explicit offline noise, delay, grade and load cases; no live-game comfort certification or new ACC target-acquisition feature is claimed.

### 1.0.1 — 2026-10-03

**Fixed**

- Keep traffic-induced reductions below already applicable speed constraints.
- Publish throttle/brake together with the original observation, route/activation identity and upstream expiry; clear the request on plugin shutdown.
- Consume current bound traffic and speed constraints without changing PID gains.

## DrivePolicy

### 1.0.5 — 2026-10-05

- Publish original dependency receipts for effective/tied spatial constraints and required dynamic traffic instead of an unattributed scalar minimum lease.
- Avoid letting empty optional traffic become a speed-plan deadline owner. Preserve planning values, brake requests and original evidence freshness/identity checks.

### 1.0.4 — 2026-10-04

- Include the valid requested cruise ceiling in minimum-speed composition so a higher nonbinding static map cap does not shorten the lower-speed decision's lease. Effective lower limits and dynamic evidence retain their original leases.
- Apply the existing anticipatory deceleration envelope to the 35 km/h roundabout upper ceiling, preserving tighter curve and traffic constraints.

### 1.0.3 — 2026-10-03

**Fixed**

- Apply the existing Autopilot curve-entry envelope, including response and setup distance reserves, to the planned speed ceiling. Remove disagreement between speed planning and curve braking.
- Preserve route identity, evidence leases, traffic constraints and lateral advice.

### 1.0.2 — 2026-10-03

**Fixed**

- Avoid applying the legacy lead-distance/3 speed cap on top of ACC's route-candidate time-gap ceiling when ACC owns following. Preserve the fallback when ACC is disabled or route following is unavailable.

### 1.0.1 — 2026-10-03

**Fixed**

- Prevent the smoothed speed preference from overriding a lower current constraint.
- Use one truck observation for the speed plan and its brake request.
- Bind speed/brake constraints to current producer evidence and inherited expiry; clear them on shutdown.

**Preserved**

- Existing lateral advice is unchanged; this release grants no new maneuver authority.

## EcoDrive

### 1.0.1 — 2026-10-03

**Fixed**

- Publish the existing throttle-smoothing preference as a bounded, identity-bound request and clear it on shutdown.
- Leave pedal ownership with Autopilot and Engine; stale preferences are ignored.

## Collision

### 1.0.1 — 2026-10-03

**Fixed**

- Relay the original traffic request without renewing its observation lease or creating a second independent brake authority.
- Label unavailable/stale traffic explicitly instead of presenting it as clear.

## HUD

### 1.0.2 — 2026-10-04

**Changed**

- Report actual HUD element initialization and the discovered element count in the reference console style. Do not label normal element discovery as a warning.
- Driving controls, HUD element behavior and navigation authority are unchanged.

### 1.0.1 — 2026-10-04

**Fixed**

- Prefer the current SDK dashboard gear for the gear element instead of inferring neutral from the physical transmission ratio at standstill.
- Show D for positive displayed gear in automatic modes, preserve numbered manual gears, R and explicit dashboard neutral. Do not infer a selector state from an activation request or retain an old D value.
- The coordinated core telemetry reader now exposes gearDashboard separately. Gearbox safety checks continue using the original physical gear.

## Other plugins — 1.0.0 baseline

Version 1.0.0 marks the start of independent versioning of existing code.
These are baseline capabilities, not claims that the features were newly
implemented or fully completed in that release. Older unversioned changes
are not retrospectively assigned to releases.

| Plugin | Version | Baseline capability |
| --- | --- | --- |
| acc | 1.0.0 | Adaptive cruise control and following-distance requests. |
| autopilot | 1.0.0 | Coordination of steering, throttle and braking. |
| collision | 1.0.0 | Collision-risk assessment and braking requests. |
| discord | 1.0.0 | Discord Rich Presence. |
| drivepolicy | 1.0.0 | Shared driving-assistance decisions. |
| ecodrive | 1.0.0 | Throttle-request adjustments for economical driving. |
| hud | 1.0.0 | In-game information overlay. |
| lanecontrol | 1.0.0 | Steering based on a validated trajectory. |
| toll | 1.0.0 | Toll-gate assistance. |
| tts | 1.0.0 | Spoken notifications. |
| turnsignals | 1.0.0 | Route-based turn signals. |

## Adding a release

Under the relevant plugin heading, add `### VERSION — YYYY-MM-DD`, newest first.
Use **Added**, **Fixed**, **Changed** and **Known limitations** as applicable.
Describe actual changes and include the commit when available.

Updating the version display changes the application UI, not plugin behavior,
so it does not itself increase plugin versions. Independent plugin distribution
and dependency compatibility checks remain planned, not implemented.
