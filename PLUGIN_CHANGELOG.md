# Plugin changelog

Release history for individual plugins. See [PLUGIN_VERSIONS.md](PLUGIN_VERSIONS.md) for versioning rules.

## Map

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

### 1.0.1 — 2026-10-03

**Fixed**

- Include ACC deceleration in the existing service-brake arbitration.
- Clear held throttle when any brake is applied; prevent EcoDrive from restoring it during braking.
- Publish one paired, identity-bound longitudinal command with its deciding source, reason and inherited expiry.
- Clear drive during stationary toll payment and clear the paired command on shutdown.

**Known limitations**

- Comfort gains and ordinary pedal ramps are unchanged. Offline arbitration verification is not a game-comfort result.

## ACC

### 1.0.1 — 2026-10-03

**Fixed**

- Keep traffic-induced reductions below already applicable speed constraints.
- Publish throttle/brake together with the original observation, route/activation identity and upstream expiry; clear the request on plugin shutdown.
- Consume current bound traffic and speed constraints without changing PID gains.

## DrivePolicy

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
