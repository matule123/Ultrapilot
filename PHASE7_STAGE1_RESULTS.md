# Phase 7.1 — Unified longitudinal command ownership

Completed offline on 2026-10-03. Baseline:
`1f592ce8afca75c0a9ebfe9fbc60d9dcc052753c`.

**Verdict: PASS for the implemented offline arbitration contract. NOT VERIFIED
for live-game behavior or driving comfort.** No installation, game operation,
commit or push was performed. The user will run the full pytest suite.

## Scope and evidence

The tracked working tree was clean at entry. This change coordinates existing
longitudinal producers and the final Engine boundary. It does not introduce a
speed controller, traffic source, stop-and-go function or steering filter.
Steering geometry, controller/calibration, executor scheduling and its 500 ms
freshness limit are unchanged. Existing ordinary pedal ramps and ACC PID gains
are retained. Emergency braking bypasses the ordinary ramp.

Read-only historical evidence inspected:

| Artifact | Identity / observation | What it proves |
| --- | --- | --- |
| Installed `ultrapilot.log`, 2026-10-02 18:59:28–19:00:16 local time | Simple-auto probe: throttle 0.12, brake 0, gear 0, frame 259256296; handoff: throttle 0.1759542, brake 0, gear 4, frame 259539618 | Existing launch/handoff events, not the entire continuous pedal history |
| `steering-replay-20261002T170016.638031Z-manual_disable.json` | 1,648 sampled and 6,294 execution records; first sample: session 1, map `promods-1.59`, dataset `d6cc7936fce4e902761abb5d`, intent `84f81c0f88254c4a8d52dc3591257039`, revision 7, build `9aff982a062b496a83b14f8c7cfb7979` | Steering evidence; no throttle/brake fields in either record channel |

Replay SHA-256:
`d9aca4b8184389026f33c81bdcbf08ae6f013adbac2eed093ebf0bd1280d1e0e`.
Its final header has revision 8 and missing intent/build; that header is not
used to relabel earlier records. No historical pedal conflict or cause of the
user's perceived harshness is inferred from this steering-only replay. The
faults below are demonstrated by code and isolated production-flow tests.

## Producer audit and ownership

| Producer | Inputs | Request / units | Priority / contract | Application |
| --- | --- | --- | --- | --- |
| Autopilot | Bound truck observation, current navigation authority, producer requests | Paired throttle/brake, normalized 0–1 | Sole normal pedal composer; existing ramps | One `longitudinal_command`; Engine performs physical writes |
| ACC | User target (default 80 km/h), posted SDK limit, road/policy cap, current traffic | Requested/constrained speed km/h; throttle/brake 0–1 | Normal drive or service-brake target; emergency above existing ACC threshold 0.8 | One immutable `longitudinal_acc` |
| DrivePolicy | Same truck observation for plan/brake; bound road, curve and traffic | Planned speed m/s; auxiliary brake 0–1 | Minimum applicable speed constraints; service braking | `longitudinal_policy`; no direct physical controls |
| EcoDrive | Current truck/frame and existing optional preference | Existing smoothing coefficient 0.15 | Preference only; never defeats braking | `longitudinal_eco`, consumed by existing Autopilot throttle ramp |
| Curve slowdown | Existing Map curve profile and truck speed | Radius/distance m; derived speed m/s and service brake | Existing anticipatory law, then existing reactive fallback if unavailable | Curve profile travels with immutable Map calculation; same Autopilot |
| Collision | Existing lane-aligned traffic evidence | Traffic brake relay | Same evidence as traffic, not independent depth/coverage or another controller | Relay retains original lease; production arbitration does not count it twice |
| Engine traffic / lights | Existing buffers, captured truck pose/speed, nearest light | Lead gap m; traffic/light brake 0–1 | Ordinary service targets; existing planner emergency threshold >0.7 means full emergency brake | One `longitudinal_traffic`; latest emergency can override at Engine without another Autopilot tick |
| Toll | Existing planner `PAY_TOLL` state | Zero drive, existing stop target, payment action at rest | State-specific stop/payment contract, not an arbitrary competing brake scalar | Autopilot; toll plugin itself issues only payment action, unchanged |
| Safety / arrival / R | Navigation authority, heartbeat, original observations, ratio/motion, arrival | Zero drive; existing controlled stop/release | Overrides normal drive; current emergency is not downgraded during authority loss | Existing Autopilot/Engine state machine and final physical boundary |
| Launch owner | Mode, fresh observation/steering, activation token and absolute deadline | Existing bounded simple-auto probe/handoff; real-auto selector confirmation | Explicit temporary Engine ownership; live braking forbids launch | Existing Engine engagement/handoff, then paired Autopilot output |

Controller dispatch remains `SCS_SDK`, `VJOY` or `DIGITAL`. The plugin SDK
controller is an intent proxy, not a device writer. Engine alone calls the
physical Controller under its existing I/O lock. None of the new producers
writes a physical device.

### Original versus new flow

Previously, separately written scalar requests were combined incompletely.
Autopilot pedal mirrors could reflect different stages of a tick, and Engine
read throttle/brake individually. Brake ramping and the held throttle/Eco
preference could leave both channels positive. A completed backend write was
not itself a guarantee of exclusive pedals.

Now: user speed preference → minimum applicable constraints → existing ACC
speed control → existing Autopilot service/emergency arbitration and ramps →
one immutable paired command → Engine freshness/identity/transmission/parking
guards → opposing pedal release → physical write.

Engine rechecks current required producers and latest brake/coast constraints
before applying an older, otherwise valid Autopilot command. An ordinary new
brake target immediately inhibits drive but retains the existing Autopilot
brake ramp. An emergency applies directly, including during navigation loss.

## Decision contract

- Each producer has one replaceable IPC slot; no accumulating queue, file I/O
  or replay serialization was added to the control tick.
- Metadata: schema, source, original SDK frame/observation timestamp, computation
  time, expiry and activation/session/map/dataset/intent/revision/build binding.
  A LanePath publication token also invalidates same-revision replacements.
- Small identity metadata is published atomically with the existing LanePath;
  pedal arbitration does not copy or unpickle the full geometry per check.
- Source age is bounded by 0.5 s. Derived outputs inherit the earliest consumed
  source expiry; new computations cannot renew an old observation's lease.
- The final guard also validates the current truck observation, SDK binding and
  original timestamp. Future timestamps, missing required fields, invalid/nonfinite
  values, changed identity and expired observations are rejected. Decision source,
  reason and the boolean emergency flag are required; malformed decision metadata
  cannot be silently interpreted as a normal or emergency command.
- Final throttle/brake are finite normalized values in [0,1]. Any positive brake
  excludes positive throttle. Engine releases the opposing channel first.
- Each decision names a source and reason. One small `longitudinal_applied`
  record describes returned backend calls, their time, command/source frame and
  context. This is not evidence that ETS2 consumed a write.
- Manual disable clears the paired command, invalidates the activation and
  releases controls. An in-flight old-context result cannot regain authority.
  Current required-producer loss is rejected at Engine even before Autopilot's
  next tick; a new ACC zero-drive request cannot restore old positive drive.
- Existing simple-auto standstill brake release, R/backward-motion rejection,
  parking-brake ownership, launch deadlines and real-auto ratio confirmation
  remain authoritative. No automatic parking-brake release or new selector pulse
  was introduced.

| Class | Attribution priority | Pedal semantics |
| --- | ---: | --- |
| Emergency | 100 | Zero throttle, immediate emergency demand; existing simple-auto standstill/R protection still applies |
| Safety | 90 | Zero throttle, original producer-loss/authority stop behavior |
| Obstacle | 80 | Zero drive while braking; existing obstacle stop target |
| Traffic / light | 70 | Compatible service-brake targets through the existing ramp |
| Maneuver approach | 60 | Existing validated approach contract; no new maneuver authority |
| Curve / policy | 50 | Existing service-brake target and speed ceiling |
| ACC | 40 | Existing speed-controller drive/service target |
| Cruise | 10 | Existing fallback only if ACC is not enabled |
| EcoDrive | Preference only | Cannot generate independent drive/brake authority |

This is not a blind maximum over unrelated requests. Speed limits are combined
as a minimum in consistent speed units. Service brake targets are compatible
minimum deceleration demands at the arbitration input; their strongest target
must be retained, with existing transient ramp semantics. Emergency/safety wins
attribution, and does not lower a stronger compatible target. Ties are broken
deterministically by class priority and source name. Toll/arrival/parking/R are
state transitions, not ordinary numeric competitors.

### Unavailable inputs

Enabled ACC or DrivePolicy with missing/invalid/expired evidence causes zero
drive and controlled stopping; during pending activation, Engine can wait with
zero drive inside the original absolute deadline for their new-epoch packet.
It does not renew the deadline or ask for another N.

Disabled ACC keeps the existing conservative fallback. Missing Eco preference
is ignored. Missing road classification supplies no invented road-class cap;
posted SDK limits and remaining validated constraints still apply. Missing
anticipatory geometry supplies no invented curve profile: the existing reactive
fallback and navigation-authority guards remain. Optional legacy traffic loss
supplies no new observation/request and is explicitly unavailable, not free
space. An independently observed light can still contribute without an available
traffic buffer. Existing traffic does not prove complete sensor coverage, static
obstacle clearance, accurate body geometry or a physically confirmed road edge.
No such authority is added here.

## Reproductions and repairs

| Proven fault | Before | After / regression |
| --- | --- | --- |
| ACC brake omitted by Autopilot | `acc_brake=0.3` did not produce service braking | Included in arbitration; positive brake and zero drive |
| Held throttle / Eco revival during braking | Existing throttle could remain positive as brake ramp increased | Any brake clears held throttle; Eco cannot revive it |
| Conflicting physical scalar output | Engine wrote throttle 0.7 and brake 0.4 | Engine writes throttle 0, brake 0.4; opposing channel released first |
| Traffic reduction raised an existing ACC cap | Danger branch overwrote the earlier constrained target | Every reduction remains below existing speed limits |
| Smoothed policy overrode a lower constraint | Plan remained 19 m/s after a 5 m/s constraint | Returned plan 5 m/s; gains and lag coefficients unchanged |
| Stationary toll left old drive latched | Existing throttle 0.5 survived payment branch | Zero held and published throttle before stop/payment logic |
| Producer-loss ramp downgraded current emergency | Simultaneous expired navigation/current emergency produced brake about 0.05 in reproduction | Immediate brake 1.0, zero drive; standstill/R protection retained |
| New ACC brake/coast or required-producer loss between ticks | Earlier paired drive 0.099 could still be written | Latest service/coast cuts drive; emergency is immediate; required-source loss enters controlled stop without waiting for Plugin |
| Simple-auto safety stop retained brake at rest when R was observed | Brake remained about 0.05 despite fresh zero speed | Fresh standstill releases both pedals and removes authority, including observed R; moving safety braking is preserved |
| Missing constraint fields accepted as a valid producer | Road cap / policy speed absent despite valid wrapper | Shape/range validation rejects the malformed request before use |
| Incoherent scalar inputs | Separate radius/distance and second truck reads could straddle updates | Bound curve profile; one captured truck for speed planning; traffic relative-speed calculation uses its captured truck speed |

Initial conflict tests were run before the fixes and failed. The policy 19→5
case was independently executed against `git show HEAD:plugins/drivepolicy/main.py`.
Emergency downgrade and final between-tick boundary tests were separately run
before their respective repairs and failed. The fresh simple-auto standstill/R test also failed before the brake-release repair. No old test threshold was lowered.
The speed-cap test explicitly cancels preceding ACC/policy braking before testing
the independent cap, because current braking now correctly has precedence.

## Verification

Final targeted run: **313 passed, 17 subtests passed**, 14.19 s. The full suite
was not run. Selection: longitudinal arbitration; activation observation binding;
simple-auto handoff; control safety; activation braking/stopping; real-auto drive
engagement; policy/signal/light; evidence export/physical boundary; post-localization
freshness; steering handoff; activation tick stability; cached control output;
plugin version metadata.

Coverage includes both supported transmission modes, one-N startup and moving
activation, temporary zero ratio, required-producer readiness without a second N,
disable during pedal application, current/stale/future/incoherent SDK observations,
packet/context/frame faults, inherited lease expiry, multiple simultaneous caps,
request permutation, cancellation, Eco interaction, toll and latest emergency.
Tests inspect actual simulated Controller writes through Engine/PluginSDK, not
only internal Plugin flags. No simulated backend result is called a game result.

The filesystem sandbox blocked pytest temporary export directories and a local
Manager pipe with Windows `PermissionError`. These were environment failures;
the same targeted selection and IPC benchmark succeeded outside that filesystem
restriction using a unique ignored audit basetemp. No application integrity check
was relaxed.

### Unchanged steering benchmark

`tools/run_steering_bench.py` against HEAD and candidate: **all 16 case metric
dictionaries exactly equal**. Cases include both directions R18/R35/R83/R250,
S35, roundabout, straight 10/30/60/90 km/h and logged-speed R22 with response
0.32/0.5 s. Controller, Route, Dynamics and benchmark source hashes are unchanged.
This demonstrates no mathematical steering regression in those offline cases;
it is not a live IPC cadence or comfort measurement.

### New arbitration operation cost

Reproduction: `python tools/benchmark_longitudinal.py --samples 500`.
500 samples per direct/Manager mode, 10,000-point LanePath; percentiles use
nearest rank over elapsed `perf_counter` intervals. Values below use actual
local `multiprocessing.Manager` IPC.

| Operation | Median ms | p95 ms | p99 ms | Maximum ms |
| --- | ---: | ---: | ---: | ---: |
| Three producer publications + context | 1.802 | 2.352 | 2.564 | 2.903 |
| Paired Autopilot publication | 0.437 | 0.726 | 0.868 | 0.979 |
| Final Engine arbitration | 1.331 | 1.867 | 2.102 | 2.633 |
| Combined operations | 3.703 | 4.367 | 4.794 | 5.744 |

Direct in-process combined median: 0.035 ms. These are costs of the new operations,
not an end-to-end Map/Plugin/Engine scheduler or physical backend benchmark. They
do not prove game jerk reduction or the absence of future scheduling pauses.
Large output JSONs remain in ignored `docs/steering-audit`.

`compileall` for core/plugins/sdk/tools/tests passed. `git diff --check` and
separate whitespace/final-newline checks for new untracked text files passed.
Benchmark dictionaries use different path separators and the candidate includes
the benchmark's own hash; common production hashes match after matching paths.
All four steering/benchmark source files also match HEAD after LF/CRLF normalization.

## Changed files and deployment boundary

- Core: `core/longitudinal.py`, `core/engine.py`, `core/ipc/shared_state.py`.
- Changed plugins: Autopilot, ACC, DrivePolicy, EcoDrive, Collision → 1.0.1;
  Map → 1.0.2. Unaffected plugins, including toll, retain their versions.
- Regression: `tests/test_longitudinal_arbitration.py`.
- Reproducible cost tool: `tools/benchmark_longitudinal.py`.
- Documentation: this report, `PLUGIN_CHANGELOG.md`, `PLUGIN_VERSIONS.md`,
  `DEFERRED_WORK.md`.

These runtime changes form one coordinated application build. Old and new
producer/consumer files must not be independently mixed during installation.
The pre-schema scalar adapter exists only for isolated legacy clients/fixtures;
the live Engine initializes and requires longitudinal schema 1.

## Phase 7.2 questions and verdict

1. Establish comfort criteria before changing ACC gains/ordinary ramps: speed
   error, longitudinal acceleration/jerk, gap error and drive/coast/brake transitions.
2. Evaluate how often ordinary requests overlap or switch in a real run with
   properly time-bound pedal channels; the historical steering replay cannot
   answer that question.
3. Keep the legacy sensor-coverage limitations explicit. No new traffic source,
   obstacle model, stop-and-go, or overtaking authority is part of this release.
4. Full pytest and later authorized deployment/game verification remain pending.
   No additional drive is requested as part of this offline implementation.

Phase 7.1 implementation is complete in the verified offline scope. Reliable
comfort improvement in ETS2 remains **NOT VERIFIED**, not inferred from passing
unit tests or faster publication.
