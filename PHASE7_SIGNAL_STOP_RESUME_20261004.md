# Producer-timed traffic-light waiting and restart

Date: 2026-10-04. Source baseline: `3f11cb75362c6ba0e0d0e41f25fce16f7fb311b5`
plus the preserved local continuous-service-stop and quiet-logging changes.
No commit, deployment, collection arm, game launch or game control occurred.
No AGENTS.md was found at the repository/ancestor locations. Plugin version
rules, previous service-stop and transmission/source reports were reviewed.

**Verdict: supported stop/wait/restart implemented and verified offline. ETS2
effect NOT VERIFIED.** The implementation reuses the existing lateral controller,
longitudinal arbitration, continuous brake witness and bounded gearbox launch.
It does not certify every intersection or a physical hill hold. The full Python
suite remains for the user; no new drive is requested by this task.

## 1. Reproduction and correction

The earlier legacy buffer exposes head ID, world XYZ, quaternion-derived yaw,
color and countdown. It has no acquisition time, generation or lifecycle.
Repeated reads and a newly observed color cannot prove fresh clearance. Existing
waiting consequently retained a positive brake indefinitely on legacy green.

With a valid new source contract, the initial real Controller reproduction
still failed: two new green acquisitions left actual throttle at zero and the
service brake positive. Engine had no validated transfer from the continuous
hold to its existing launch owner. This gap is now implemented for modes 0/3.
The fixture uses production reader/selector, arbitration, Autopilot, Engine,
Controller and chronological float32 SCS mapping writes. Its vehicle plant is
the user-observed manual-pedal gearbox model, not proof of SDK consumption.

| Reproduction | Before | Current offline result |
| --- | --- | --- |
| Locked red, forward braking, standstill, two new green frames | AP waits, throttle 0, positive brake | Same activation releases brake first, bounded launch, then current active command |
| Real automatic at zero ratio while waiting | No supported neutral hold/restart | Current witness permits waiting; one existing D request, no power until forward SDK gear |
| Full Map LaneId serialization and GPS prefix rebase | New reader initially compared dict to tuple | Canonical production LaneId comparison; ADVANCED_PREFIX/SAME_EXACT retain lock and authority |
| Combined wait/restart provenance | New signal evidence initially exceeded fixed journal budget | Missing-field bitmap preserves unknowns without repeated names; original signal and release writes survive export |
| Old/stale/ambiguous/missing green, other stop reason | Must not release | Positive continuous brake, zero throttle; precise blocker |
| R/backward/stale/identity loss/cancellation/backend error | Must revoke | No subsequent positive propulsion; existing takeover/cancellation |

Historical incident backend writes and rejected source snapshots were not saved
completely. These are reproduced implementation gaps, not retrospective proof
that the old incident was caused by a particular red head or physical zero edge.

## 2. Signal producer and reader contract

Pinned MIT source: [ETS2LA plugin](https://gitlab.com/ETS2LA/ets2la_plugin), commit
`1f16156b9b37b70cf182c2bc09120fa1b234e129` (1.59). fmt MIT input commit:
`9ff9c695db8aeadf70eb26498a0e1cdceeeb849a`. The tracked
`tools/signal_plugin/inputs.json` checks every required source/header/license
input before building. The build changes only a separate ignored audit copy.
Source archives and receipts remain under `docs/steering-audit`; no originals
or previous candidates were deleted.

| Binary/input | SHA-256 |
| --- | --- |
| Installed `ets2la_plugin.dll` (unchanged) | `D07CF70A6F0810E22A028943380641CB1984304F8DD72265B09736CEAD89B61C` |
| Candidate-e and independent candidate-f | `53D8C54D2B71ABB2F1D2DE8CB68CD096F22F8385F750F46CE07AF105295C3BCF` |
| Pinned producer archive | `BB2DDB10853BEF0C4F936FDFE2C8BE4CD043EF135DC66625849480E23100010B` |
| Pinned fmt archive | `409FD26F96E6E7756EE83CA8738BC58D30326132525E65625BB3B6D38287E1A7` |

Installed path:
`C:\Program Files (x86)\Steam\steamapps\common\Euro Truck Simulator 2\bin\win_x64\plugins\ets2la_plugin.dll`.
Candidate path:
`C:\Users\PC\Documents\GitHub\ets2la\docs\steering-audit\signal-plugin-20261003\candidate-e\ets2la_plugin.dll`.
This is the traffic/telemetry plugin, **not** `scs_sdk_controller.dll`.
Exact source-to-installed-binary equivalence is **NOT PROVEN**. Candidate build
version is `1.59.2-up-signal`, expected game version 1.59.x. Unchanged memory
patterns from the pinned source still require live compatibility verification.

Build: MSVC 14.44.35207, x64, `/O2 /MT /std:c++17 /utf-8 /Brepro`, deterministic
path mapping. Two separate output directories yield identical bytes. Exported
entry points: `scs_telemetry_init`, `scs_telemetry_shutdown`; dependency:
`KERNEL32.dll`. Isolated WinDLL load, entry-point resolution and unload pass.
We deliberately did not invoke game pattern-scanning initialization outside ETS2.
Upstream wchar-to-char C4244 warning remains, unrelated to the added sidecar.
MIT source and fmt licenses accompany the private build.

`tools/build_signal_plugin.py` patches acquisition in
`src/processing/traffic.cpp::write_semaphore_data`; SDK lifecycle callbacks in
`src/core.cpp` handle started, paused, configuration and frame_start/timer reset.
Definitions come from the pinned vendor SDK `scssdk_telemetry_event.h`.
Only telemetry publication is added; controller input channels are untouched.

New mapping: `Local\UltraPilotSemaphoreV2`, packed 1980 bytes. Fields:
`sequence`, magic `UPS2`, version 2, size, `lifecycle`, `generation`, `frame`,
`observed_at`, active/complete flags, count (0..40), unchanged 1920-byte legacy
head payload, `end_sequence`. QPC time is sampled before the actual color/pose
reads. Generation advances once per new SDK render frame. Repeated frame reads
cannot advance generation or acquisition time. Pause/shutdown publishes invalid;
configuration/timer restart creates a new lifecycle. Missing source pointers do
not publish an authoritative empty observation.

The reader checks version, bounded count, even matching sequence before/after
copy, finite poses/quaternions, unique IDs, lifecycle/generation/frame, original
time in [0, 500 ms], regression and changed-in-place generation. The compiled
publisher probe proves red/green publication, unchanged repeat, pause/reset/
incomplete/shutdown and QPC agreement with Python monotonic. It is an isolated
mapping test, not a real memory-pattern or signal-ownership test.

`frame_us` is this producer's SDK **render_time**. It is retained separately
from truck `sdkFrameTimeUs`; their equality is not assumed. Lifecycle is a local
producer/reset identifier, not a decoded game session ID. The immutable Python
receipt binds it to the current SDK/navigation session and full route authority.
Seqlock consistency does not imply an atomic game-world snapshot.

## 3. Route relevance and locked clearance

The nearest head is selected by forward progress on the existing directed XYZ
LanePath, not Euclidean distance. The original source yaw faces the approach:
head yaw + pi is compared with the route tangent. Height difference must be
within the existing 1.5 m projection gate; ego projection within 1.2 m.
Signal lateral gate is 6 m, horizon 120 m, angular agreement 45 degrees.
These are conservative selection **heuristics**, not physical road boundaries.
Distinct candidate IDs within 3 m progress are ambiguous. Duplicate IDs,
loop/crossing ambiguity, missing live LaneMatch, old packet or changed route
publication during geometry read cannot authorize clearance.

First physical planned brake receipt locks head ID/position, producer lifecycle,
red acquisition and full activation/session/map/dataset/intent/revision/build/
geometry authority. A different closer signal or list order cannot replace it.
Placement drift >1 m, loss of the head, wrong direction/layer, or true reroute
blocks release. Normal GPS prefix rebasing preserves the same proven authority.
The upstream ID field is annotated as uncertain; ID plus position/lifecycle
reduces accidental reuse but does not establish authoritative signal-to-lane
membership or complete visibility of all heads.

Release requires two distinct new green acquisitions >=100 ms apart, both later
than the locked red. A sampled yellow/red/unknown resets confirmation. This
rejects a one-frame green flicker; it is not proof of an unseen continuous color
between acquisitions. Engine rechecks the original leases, identity and physical
brake chain after IPC/steering and before release, then again before power.

ACC following/source-loss, independent traffic braking and toll waits are
latched as lacking proven clearance. Disappearance does not clear them. Current
fresh safety/ACC/policy demands also veto launch. No new traffic predictor,
collision parser or gap planner was added.

## 4. Physical ownership and bounded restart

During supported waiting AP stays active with `planned_wait`; Engine is the
only physical pedal owner. Throttle is zero and the existing last acknowledged
positive planned brake is a lower bound while waiting. No new arbitrary hold
constant is introduced. Missing green cannot create a zero/positive brake edge.
An emergency or technical loss remains a terminal takeover, not clearance.

At confirmed green and standstill: `resuming` -> brake zero **first** -> reuse
bounded gearbox launch. Mode 0 uses the existing 0.12 launch and fixed 0.5 s
handoff/2.5 s launch window; current Plugin output takes over. Old ramp brake is
reset once for this validated transfer; fresh safety brakes still cancel it.
Mode 3 reuses one D-confirmation request when needed, zero power until a new
forward gear observation. An already-forward gear uses the existing confirmation
tick without a new D pulse. Deadlines are not renewed. Mode changes, R, backward
motion, parking brake, stale SDK/steering/traffic, identity change, manual N or
backend failure cancel. After cancellation the old request cannot restart.

Supported restart currently completes a standstill wait; green during approach
does not initiate rolling release. Driver-owned parking brake is never written,
toggled or released. Manual input mix cannot identify pedal ownership; explicit
N/UI cancellation, R/motion/parking observations and physical-chain loss revoke
the wait. No promise of autonomous holding/resumption on every grade is made.

## 5. Diagnostics, cost and verification

Existing immutable traffic input includes compact signal fields:
`valid`, `reason`, lifecycle, generation, render frame, original time, relevance,
candidate ID/XYZ/color. Existing `service_hold` exports original stop reason and
lock ID/acquisition/chain/actual write sequence/time. `signal_resume`/`launch`/
`active` events retain ordered backend values and times; readback/write success
is not DLL/game consumption. Missing input fields use schema-1 bitmap in the
fixed `INPUT_KEYS` order excluding `following`, not zeros or a repeated long
name string. No journal, snapshot or chunk budget was increased. Combined
round-trip verifies hashes/order, original provenance and exclusive known pedal
pairs; `confirmed=false`, `runtime_authorized=false` remain.

| Isolated operation | Median | p95 | Maximum | Scope |
| --- | --- | --- | --- | --- |
| Prepare 10,000-point route (10 runs) | 12.201 ms | 13.731 ms | 13.731 ms | Once per geometry/publication cache change |
| Decode/project 40 heads with cached route (500 runs) | 1.419 ms | 2.092 ms | 3.486 ms | Worst supported head count, synthetic ABI input |
| Existing Manager IPC longitudinal publication + arbitration (100 runs) | 3.630 ms | 4.081 ms | 4.277 ms | Operation benchmark, not end-to-end tick |

Route projection work is bounded to 512 edges per local query, 40 heads and one
cached geometry; unsupported density rejects relevance rather than simplifying
the route. No worker queue or unbounded extraction is added. The legacy plugin
still performs its existing nearby-actor acquisition. Live producer acquisition,
whole Engine cadence and loaded-game cost are **NOT MEASURED**. Benchmarks do not
promise a live deadline or prove coverage of modded intersections.

Targeted final run: **349 passed, 10 subtests passed** (14 selected files,
including compiled C++ probe/load). Source tests cover both automatic modes,
red/wait/new green, stale/future/repeat/torn/pause/reset, closer side head/order,
ambiguity/elevation/opposite direction, other stop reasons, slow IPC, route
publication race, real Map ADVANCED_PREFIX/SAME_EXACT, R/backward/backend failure,
manual disable, neutral/launch handoff and combined export. Standalone earlier
test runs remain historical; this total is the final targeted selection only.

Windows sandbox temporary-file/named-pipe PermissionErrors were distinguished
from assertions and rerun with a working repository audit temporary directory.
The new export reproduction also caught fixed-budget source loss and then passed
after compacting unavailable-field metadata, without weakening integrity.

After the final UI blocker-deduplication change, the affected signal/hold/logging
selection also passed: **102 tests**. This overlaps the 349-test selection; the
counts must not be added as independent cases. Dynamic Island updates a changed
waiting reason once and suppresses repeated identical messages.

Steering benchmark: all 16 case dictionaries match `--ref HEAD` numerically.
Lateral controller, route geometry and SteeringDynamics are unchanged. Relevant
compileall and git diff --check pass. Full suite not run.

Reproduction/build/benchmark artifacts:
`docs/steering-audit/signal-plugin-20261003/` (ignored), including input/build
receipts, candidates e/f, compiled publisher probe, signal-cost.json,
longitudinal-cost.json and steering-after/head.json. No existing data was removed.

## 6. Coordinated runtime package and remaining gates

Feature runtime files:
`core/engine.py`, `core/longitudinal.py`, `core/service_brake_hold.py`,
`core/sdk/signal_snapshot.py`, `core/navigation/longitudinal_diagnostics.py`,
`plugins/autopilot/main.py` (1.2.0), `ui/dynamic_island.py`, plus the candidate
`ets2la_plugin.dll` and upstream/fmt license notices.
The prior continuous-hold prerequisites `core/transmission_mode.py` and
`core/sdk/scs_controller_writer.py` must also be present at this working-tree
version. Previous quiet-log changes in `core/control_timing.py`/`core/telemetry.py`
remain preserved, but are not newly required by signal clearance itself.

This is a coordinated source package, not permission to mix individual files
with unknown installed versions. Before any future deployment compare all
dependencies and hashes, preserve rollback copies, obtain separate approval and
keep ETS2/UltraPilot closed for DLL exchange. Nothing is installed now.
`scs_sdk_controller.dll`, controls.sii, settings and game input configuration do
not change. Map/ACC plugin versions do not change for core-only consumption.

Next gate: user's complete pytest result. After that, separate deployment
approval and a controlled live confirmation are still needed. Required game
evidence is the same selected head/lifecycle and fresh acquisitions, positive
service-brake consumption through standstill, no R/rolling, brake release before
power, current steering/route authority and stable restart without N. This task
does not authorize or request that live test now.

Unresolved applicability limits: source memory-pattern compatibility; heuristic
head-to-approach membership and 40-head coverage; SDK-versus-manual pedal
semantics; driver-input mix and grade hold/release; all following/toll clearance.
They block universal stop-and-go certification, not the tested supported offline
single-signal implementation. Legacy or ambiguous sources remain waiting with
an explicit reason. Technical takeover requires the driver; zero outputs cannot
guarantee slope holding.
