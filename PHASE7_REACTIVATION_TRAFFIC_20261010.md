# Prior-activation Traffic handoff — 2026-10-10

**OFFLINE VERIFIED for the reproduced reactivation race. NOT GAME VERIFIED.**
Base HEAD: `787d012a2a78ac917bb5506e0958c32d8d06575f`, with existing local
packet-refresh, traffic, signal direction/distance, countdown anticipation and
moving-green release changes preserved. This task changes two core runtime
files, not plugin implementations, controller gains, geometry or the DLL.
No deployment, arm, game control, commit, push or full-suite pytest run.

## Recorded incident and limits of attribution

The original installed export
`C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics\steering-replay-20261010T183729.534607Z-automatic_disable.json`
passes `core.steering_replay.inspect_replay` integrity verification. The existing
codec resolves its immutable decision/storage references. It retains 15 detailed
pedal events and the first intervention; originals were not changed.

| Compared field | Recorded value |
| --- | --- |
| Rejected producer / slot | `traffic` / `longitudinal_traffic` |
| Previous activation in the rejected packet | **8145579392300** |
| New expected activation | **8147165030000** |
| Packet SDK frame | **201641934** |
| Original vehicle observation | **8147.0807591 s** |
| Computation | **8147.100905 s** |
| Autopilot comparison | **8147.1847974 s** |
| Expiry | **8147.5668177 s** |
| Observation / decision age at comparison | **104.0383 / 83.8924 ms** |
| Remaining lease | **382.0203 ms** |
| Valid / traffic brake / light brake | `true` / **0 / 0** |
| Changed authority fields | **activation only** |
| First fault record / intervention sequence | **8147.1954432 s / 8147195442500** |

The other authority fields match: session **1**, map `promods-1.59`, dataset
`d6cc7936fce4e902761abb5d`, intent `17d180e277514c08a4259f3d814c8fd6`, revision
**13**, build `91c5d0eb3ad54ff8953b2eb2b084e5fa`, geometry
`['lane_path', '47ed675412749ee2bb11ad2c6af45908fb77eb781ab48c9ff496700c258f19f8', true]`.
The rejected Traffic value has no retained command sequence; the intervention
sequence above is not presented as one. Frame, original times and full context
identify the compared value.

The first intervention headline frame **201758596**, observation **8147.1875543 s**,
is the subsequent vehicle snapshot captured for fault reporting. It is not the
Traffic observation actually rejected. Native signal acquisition is separately
**8147.0668177 s**, generation **7516**, native frame **225530223**; signal was
valid. Optional parked-actor ambiguity does not explain this activation-only
comparison. The optional-detail budget marker does not explain it either.

The log records manual disable at **20:37:22.281 local**, cancelled N attempts
at **20:37:24.915, 26.030, 26.488 and 27.762**, then the final request at
**20:37:29.315**. Autopilot rejects at **20:37:29.349**; Engine follows at
**20:37:29.387**, then controlled stop/disengagement. The rejected epoch belongs
to the last cancelled request, not the earlier creeping drive epoch
**8076403172500**. This corrects the attribution in the preceding timing report.

The packet computation predates the final N. The historical export does not
retain Traffic IPC publication-completion or all get/set ordering. Therefore it
proves that a still-fresh **old-activation slot was consumed after N**, not that
this particular packet was published after N. Concurrent publication while a
copied IPC return is in flight is separately reproduced offline, not asserted
as the exact historical interleaving.

## Production defect and minimal fix

Engine captures the Traffic binding before native traffic/signal acquisition,
then publishes one immutable producer value with the original SDK observation
and that binding. Publication checks the current context; it never relabels an
old value. A new N can precede the next independent producer tick.

Autopilot reads ACC, Traffic and Policy through the shared validator. Before
this fix, a qualified Traffic slot from the previous activation became a
permanent technical fault. The existing zero-drive refresh handoff understood
near-expiry **same-context** decisions but not this initialization transition.
Engine's neutral launch had a wait for ACC/Policy readiness, while Traffic
identity refusal cancelled it immediately. Its separate first-pedal wait could
not undo the already recorded prefixed Autopilot fault.

The shared longitudinal module now recognizes an initialization transition only
when:

- Engine has published an initialization receipt with the activation and exact
  session/map/dataset/intent/revision/build/geometry in the activation batch;
- the packet differs **only in activation**, matches its producer slot, and
  passes original validity, values, timestamp, frame, lease and Traffic-role
  checks against its own original context;
- current SDK observation and drivetrain remain valid, without R or backwards
  motion, and no technical stop has already revoked authority;
- the existing fixed first-command bound remains open: **0.5 s** for direct
  forward engagement, or the existing **2.5 s** neutral launch deadline.

The old value is retained only as a rejected comparison witness. It is never
returned as accepted, executed, retimestamped or reidentified. Plugin and Engine
use their existing shared zero-drive handoff, with a new genuinely current SDK
zero-pedal decision. Neutral launch waits **before D selection or throttle
probe**. A current urgent Traffic demand still bypasses the wait. An already
acknowledged same-activation service-brake hold uses its existing continuity
path; this change introduces no release-all or new stationary brake edge in
the Traffic initialization branch.

First accepted non-refresh decision clears the initialization receipt. Manual
off/revocation clears it too; output ticks do not renew the deadline. A packet
from an earlier activation after that point is again rejected normally. If
fresh current Traffic does not arrive within the fixed bound, the reason is
`longitudinal initialization timed out waiting for traffic`. Missing required
producers, invalid/future/stale packets and changes to any other authority
field retain their established rejection behavior. No blanket missing-source
exception is added.

## Reproduction and verification

The initial five integration counterexamples fail on the pre-fix flow:
moving/stationary reactivation in both modes and copied old Traffic returned
while a current value is published. After the fix they pass without another N.
Tests use the real scoped signal reader/selector with the existing placed PPD,
Traffic publication, actual DrivePolicy/ACC/Autopilot, Engine and Controller,
and chronological SCS test-backend writes. Gear acknowledgment is modeled
after an actual D request in real automatic mode. It is not an ETS2 experiment.

| Scenario | Before | After / observed software condition |
| --- | --- | --- |
| Immediate N with otherwise valid old Traffic, both modes | Technical stop or launch cancellation | Fixed bounded wait; zero physical throttle; old packet unchanged |
| Delayed current publication / publication during copied read | Fault latched before next current tick | Automatic continuation on current validated inputs |
| Repeated N/off during wait | Included in old-slot failure | New epoch, cancelled receipt, zero outputs; no old drive revival |
| Current emergency with older Policy | Existing emergency contract | Physical throttle 0, brake 1; no comfort/init delay |
| No new Traffic by fixed deadline | Generic identity refusal | Exact initialization timeout, no probe/throttle |
| Session/dataset/intent/build/revision, invalid/future/stale, R, backend loss | Fail-closed contract | Retained; no positive physical throttle |
| Old activation after first real accepted output | Reject | Reject; controlled stop retained |
| Red → moving brake → stationary hold/gear 0 → green restart; repeated moving clearance | Earlier timing fix | Pass in both modes; continuous positive hold, no parking write |
| First fault → release_all → automatic immutable export | Existing evidence contract | Original first cause retained, hashes valid, `confirmed=false` |

Final targeted run: **330 passed, 10 subtests passed, 36.60 s** across twelve
modules: reactivation Traffic (35 cases), signal timing, signal stop/resume,
activation observation binding, longitudinal arbitration, packet refresh,
Traffic availability, joint stop flow, automatic longitudinal replay, drive
engagement safety, joint activation reliability and earlier activation races.
The earlier established missing-required-source tests exposed an overly broad
draft wait; that draft was removed. Their assertions were preserved, and the
final run includes them. Physical safety outputs and first-cause export checks
are asserted, not inferred from shared scalar mirrors.

`python -m compileall -q core plugins sdk ui tests tools` and
`git diff --check` pass. The initialization receipt is cleared once on the first
real accepted output, without a repeated IPC clear on every ordinary drive tick.

The closed timing plant and steering/comfort benchmarks from the preceding
report are not relabeled as new measurements here. This task does not tune
either controller. Full pytest remains the user's gate; offline passing does
not establish SDK consumption or game stop/restart behavior.

## Runtime and remaining gates

New runtime delta in this task:

- `core/engine.py`
- `core/longitudinal.py`

Deploying this delta alone to the older receipt is insufficient: retain the
preceding coordinated six-file timing package, including
`core/sdk/signal_snapshot.py`, `core/service_brake_hold.py`,
`core/navigation/prefab_signals.py` and
`core/navigation/longitudinal_diagnostics.py`, plus its already required
packet-refresh/native/Traffic baseline. No new DLL is needed. Plugin main
files and current VERSION declarations remain unchanged; this is a core fix.
Source-only changes: this report, prior timing report, backlog, changelog,
`tests/test_oct10_reactivation_traffic.py` and the timing fixture's optional
gear argument.

Exact historical IPC interleaving remains unknown, while the compared old
activation and the lifecycle defect are proved. The earlier initial far-red
creep, timer calibration, painted stop line/body dimensions, hill holding and
uninterrupted game consumption of SDK braking remain unverified. There is no
claim that stationary activation creates a safe new SDK brake hold or that all
intersections are supported. Next gates remain the user's full suite, separate
deployment approval and game corroboration. No additional drive is requested
now, and no existing evidence is modified.
