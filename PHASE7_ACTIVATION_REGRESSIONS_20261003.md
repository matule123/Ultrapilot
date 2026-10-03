# Phase 7 activation regressions — 3 October 2026

## Build and incident evidence

Baseline: `826cc86a852dbe616bf51b81b8e9ad14de8162e5` (HEAD = origin/main,
clean tracked tree). Installed Engine, longitudinal arbitration, Autopilot and
DrivePolicy match that baseline after LF/CRLF normalization. No installation
was changed. AGENTS.md is absent in the repository and inspected parents;
PLUGIN_VERSIONS.md was read.

Incident: session `1`, map `promods-1.59`, dataset `d6cc7936fce4e902761abb5d`,
intent `b9c5877cb12748b193ae024b1887119a`, revision `8`, build
`90f3fa69c2a04ea089a444480b30fa50`. Loaded versions: ACC 1.1.0,
Autopilot 1.0.2, DrivePolicy 1.0.2, Map 1.0.2.

| Artifact | SHA-256 |
| --- | --- |
| Supplied incident log attachment | `3f39d0ce67f9530f1754cb7fe41aa7df68d2877bc34083584ee36bf9059381d3` |
| `steering-replay-20261003T132902.499730Z-automatic_disable.json` | `2549eef06b7f9e03156845cba4b15554c672dc9404f4ec6714d134408eb807e6` |
| `steering-replay-20261003T132926.684089Z-automatic_disable.json` | `350a11e3344e274f98bba0ba8d9de44c0b8789ae259d55dd061fcb7a352269a6` |
| Diagnostic status read during audit | `1ae6e40b6626bef1cfc7b91262c077e35ebe6f9e6e75f651cf79bd1a923f9686` |

The collection `phase7-longitudinal-20261003-152818` ended as CANCELLED /
APPLICATION_STOPPED_BEFORE_FINISH. No exported directory or manifest exists;
its cleared accepted rows cannot be recovered. Replays match the incident but
do not retain the rejected policy packet or the second activation's token.
`longitudinal_curve_profile` in a steering packet is not policy provenance.

| Attempt | Directly recorded sequence | Missing historical evidence |
| --- | --- | --- |
| 15:29:01–02 | Probe 0.12 at frame 135294588; gear 4 at 135527912; handoff at 135561244 with throttle 0.13618944; policy stale/incoherent rejection | Rejected policy SDK frame, observation/computation/expiry timestamps |
| 15:29:13–14 | Activation with gear 4; release at 147677426 and +0.99515849 m/s; activation/route identity rejection | Old/new token and history context |
| 15:29:25–26 | Probe 0.12 at 159610282; gear 4 at 159810274; handoff at 159860272 with throttle 0.13872440; same policy rejection | Same missing policy provenance |

At the first/third release boundaries the drivetrain ages were 19.6834 and
15.8873 ms. They are NOT policy ages. Recent accepted steering packets likewise
do not establish policy freshness.

## Proven defects and production fixes

| Defect | Before | Fix | After |
| --- | --- | --- | --- |
| Engine captured its clock before IPC reads | A real Policy tick publishes during the read, computed_at 5 ms later than the cached decision clock; `computed_at <= now` falsely fails | Read each complete immutable packet before checking its time. Recheck the SAME consumed snapshots after arbitration | Fresh output survives; true future timestamps, expired observations/leases and slow IPC still fail closed |
| Idle output races re-engagement | After a new token/history is seeded but before activation publication, the idle output thread clears it | Serialize hotkey/UI activation and physical output using the existing I/O mutex, made reentrant for nested cancel/release helpers | Token/history survive both entry points and subsequent producer/Plugin/Engine ticks |
| First current pedal command may not exist immediately | After serialization the output thread can see activation before the Plugin's first command | A fixed, at-most-500-ms zero-output wait only for an absent or previous-activation command; no deadline renewal; discard wait on cancellation | A valid current command takes over; actual faults and emergency requests retain the safety path |

The exact historical policy predicate is NOT recoverable. Its message covers
future computation time, observation expiry, inherited constraint expiry and
incoherent ordering. The historical second token is also unavailable. These
production reproductions prove real defects capable of causing the reported
failure classes; they do not reconstruct missing historical values.

Before arbitration (`7adf8c8^`), policy advice was scalar and had no typed
timestamp inequality. The pre-read clock originated in `7adf8c8`. Forward-history
seeding/idle cleanup already existed before Phase 7 (`cce61a4` and later fixes).
It is not attributed to ACC or diagnostics merely by chronology. The old
untyped/no-freshness path was not restored.

Original timestamps, SDK-frame binding, route/activation context, validity,
500-ms leases, parking brake, Reverse/backward-motion protection and backend
checks remain enforced. The existing simple-auto probe/handoff owns launch.
The new zero-output wait is only for activation in confirmed forward gear.
No regulator, geometry, steering cadence, gear-selection semantics or comfort
parameters changed.

## Verification

- Four primary counterexamples fail with the HEAD arbitration and original
  activation bodies; all pass with the fixes. Source files were not reverted.
- Final targeted activation/arbitration/joint/simple-auto suite: **172 passed**.
- Additional drivetrain, control-thread, safety, diagnostic, ACC and comfort
  suite: **221 passed, 17 subtests passed**.
- New tests exercise actual Controller -> SCSControlsWriter -> in-memory mapping
  writes, stationary launch without driver throttle, short stationary zero
  ratio, forward continuation, first-command delay, fixed deadline, cancellation,
  Reverse/backward motion, future/stale/invalid policy, command ahead of vehicle
  frame, backend loss, emergency, session/route changes and pedal exclusivity.
- Mapping write return is NOT DLL consumption or proof of ETS2 motion.
- Windows sandbox PermissionError affected pytest temporary files and Manager
  IPC. Those targeted operations passed outside that restriction; this was not
  classified as an application failure.
- Controller benchmark: all **16 case result dictionaries numerically identical**
  to HEAD. `compileall` and `git diff --check` passed. Full pytest is left to user.

Existing operation benchmark, 500 samples and a 10,000-point route:

| Manager IPC operation | Before median / p95 / max, ms | After median / p95 / max, ms |
| --- | --- | --- |
| Engine arbitration | 1.3311 / 1.7107 / 1.9717 | 1.7108 / 2.0985 / 2.6603 |
| Combined publication/arbitration | 3.5759 / 4.3669 / 4.9734 | 3.9674 / 4.6065 / 5.3957 |

The additional final validity checks cost approximately 0.38 ms here. This is
not end-to-end cadence, a worst-case scheduling bound or a game measurement.
Raw benchmark JSON remains in ignored `docs/steering-audit/oct3-activation-*`.

## Verdict and changed files

**OFFLINE FIXES VERIFIED; GAME RESULT NOT VERIFIED.** No new drive is requested.
The missing historical raw policy packet still limits the causal verdict for
the incident. Full-suite review and separately approved deployment precede any
game verification. No installed files, settings or original data were changed.

Runtime: `core/engine.py`, `core/longitudinal.py`.
Regression: `tests/test_oct3_longitudinal_activation_races.py`.
Documentation: this report and PHASE7_FINAL_RESULTS.md.
Plugin files/behavior were not changed; core-only fixes do not increment plugin
versions or create plugin changelog entries under PLUGIN_VERSIONS.md.

Suggested commit: `fix(control): serialize re-engagement and validate pedals after IPC`.
Description: protect new activation history from idle cleanup, bound the first
pedal handover to zero output, and validate original timestamps after IPC reads
while retaining stale and identity rejection.
