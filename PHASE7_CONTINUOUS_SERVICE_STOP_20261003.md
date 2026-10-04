# Continuous service-brake planned waiting

**2026-10-04 follow-up:** [Producer-timed signal restart](PHASE7_SIGNAL_STOP_RESUME_20261004.md)
implements the user-authorized route/head relevance heuristic and a versioned
producer sidecar. The supported single-signal path now restarts offline without
another N. The BLOCKED clearance conclusion below records the earlier legacy
source contract; it is not the current implementation verdict. Live SDK brake
consumption, signal selection and restart remain unverified.

Date: 2026-10-03. HEAD: `3f11cb75362c6ba0e0d0e41f25fce16f7fb311b5`.
Built on the existing uncommitted standstill/logging corrections; all unrelated
changes and original evidence remain intact. No `AGENTS.md` was found at the
repository/ancestor locations. Reviewed the preceding safe-stop report, Phase 7
traffic/transmission contracts and plugin version rules. No deployment/game test.

**Verdict: planned continuous software braking and waiting implemented and tested
offline. Automatic traffic-cleared release/restart remains BLOCKED.** The present
signal/actor source cannot prove fresh clearance of every stop reason. This is
not an implemented green-light stop-and-go feature or a verified ETS2 hill hold.

## Evidence and corrected assumption

The user reports that manual service braking continuously from forward motion
through standstill does not select Reverse; a new positive brake edge after zero
at rest can select Reverse. This supersedes the previous blanket assumption that
any positive brake at rest selects R. It does not establish SDK input semantics.

The preceding report retains the incident hashes, identity and narrow measured
light-brake approach. The historical final backend brake stream was not recorded;
we cannot retrospectively prove a zero edge or the signal's actual red state.

Two unconditional code gates were reproduced: Autopilot/Engine rejected zero
ratio without forward motion; Engine's standstill guard then always relinquished
the service brake. The new real-Controller reproduction failed on baseline with
`simple automatic zero ratio lacks continuing forward motion`, then passes with
uninterrupted positive mapping writes and zero throttle at standstill.

| Writer/path | Actual effect | Continuity consequence |
| --- | --- | --- |
| Plugin SDK Controller | Writes intents to shared state, not hardware | Not proof of physical continuity; no real `Controller.flush` exists |
| Engine normal brake branch | Throttle zero, then positive brake | No intermediate brake zero between continuing positive demands |
| Engine drive/coast branch | Brake zero before throttle | Breaks chain; cannot seed a subsequent stationary brake hold |
| Real Controller `release_all`, SCS writer `reset` | Actual zero brake write | Invalidates chain even if a later positive write follows |
| Previous standstill guard | AP off and `release_all` | Unconditional termination of an otherwise continuous planned approach |
| Technical/selector/launch cancellation | Existing release/safety outputs | Never supplies automatic waiting or restart permission |

## Production contract

The SCS float writer maintains one O(1), fixed-size receipt: sequence, positive
chain, mapped value, return time and `game_consumption_verified=false`. Failure or
zero changes the chain; diagnostic recording need not be enabled. Other backends
without this receipt cannot authorize simple-auto holding. Successful mapping
write/flush is not proof of callback consumption or physical holding.

Engine seeds a witness only after positive, ordinary planned-stop braking has
actually been written while gear is forward and speed exceeds 0.05 m/s. It is
bound to the simple-auto activation token, mode generation/preference and full
longitudinal authority context, including activation/geometry identity. Light
braking and existing following-stop evidence qualify; emergency braking does not.
The first consumed stop evidence is immutable. A stationary demand cannot seed
the witness, and a witness from an earlier activation cannot be reused.

The shared transmission rule permits a zero ratio only with this current
Engine-owned witness; original SDK validity/time/frame checks remain. Engine
independently checks its actual receipt before the decision and again before
stationary pedal writes. Holding requires speed within the existing 0.05 m/s
standstill band. Motion/R, interrupted output, expired receipt, backend failure,
identity change or stale SDK/pedal/steering data revoke holding and use existing
safe takeover/cancellation. Technical failure while holding is terminal, never
automatic clearance or fault recovery. Zero outputs after takeover cannot
guarantee slope holding: the driver must take control.

At a supported stop, the existing regulator's last physically written positive
brake supplies the lower bound; a stronger current brake remains effective.
There is no arbitrary new hold-pedal constant or second regulator. Throttle is
zero. Source changes and unconfirmed clearance cannot accidentally release the
brake. Each application still requires a fresh accepted command and observation;
the stored reason/value does not refresh their timestamps or leases.

`planned_wait` is visible in Dynamic Island and logged once at the transition.
The combined journal includes compact `service_hold` provenance (phase, chain,
write sequence/time, start frame, original stop reason/ID, restart blocker and
unverified game consumption), selected hold decision and actual ordered pedal
events. Context already resides in the immutable envelope; duplicating it
initially exhausted the existing source budget and was corrected without raising
any limits. Chunk/hash/order validation and false authority flags remain.

## Clearance and manual-input limits

`read_traffic_lights()` provides ID, world XYZ/yaw, color and time-left, but no
producer timestamp/generation. The traffic/ACC source also lacks confirmed lane
membership/coverage and cannot prove that disappearance means departure. A
receiver/vehicle observation timestamp is not signal production time. Therefore:

| Situation | Result |
| --- | --- |
| Red approach with a continuous written brake chain | Keep authority, zero throttle, continuous brake, planned waiting |
| Unknown/missing/stale signal or unversioned green; missing actor | No automatic release or launch; original stop reason remains latched |
| Several reasons, or another source supplies brake | No release when one request disappears; retain hold while authority is valid |
| Technical input failure, R/backward motion, observed rolling, broken chain | Revoke; preserve first causal fault, no fresh brake re-press at unknown standstill |
| Manual N/UI disable | Release, destroy witness/token, driver takeover; another N cannot reuse hold |
| Real automatic | Existing brake/selector/activation behavior unchanged; no new stop-and-go claim |

`userBrake`/`userThrottle` do not establish who owns the mixed input; they are not
used as invented raw pedal axes. Explicit N/UI/manual cancellation is observed.
Independent physical pedal intervention and between-callback input mixing cannot
be fully identified by the present interface. Neither writer continuity nor the
historical isolated 276-channel DLL comparison proves live uninterrupted game
consumption. No parking-brake field, key or selector is toggled by this feature.

The one missing restart contract is a **producer-timed/generation-bound,
relevant, complete clearance observation for all latched stop reasons**. Until
the existing source can supply and validate it, implementing green->release->
launch would fabricate clearance. No new sensor/DLL/parser or synthetic green
permission was added. The requested automatic restart is explicitly unfinished.

## Verification

- Before: real AP -> arbitration -> Engine -> real Controller -> byte-buffer
  reproduction disengaged on stationary ratio zero. After: positive brake writes
  continue, throttle stays zero, authority enters `planned_wait`.
- Chronological writer model reproduces the user-observed zero->positive edge
  selecting Reverse at rest, and no such edge in a continuous approach. It is
  **manual-observation-based**, not an ETS2 SDK plant identification.
- Flat/+8%/-8% slope and 12/40 tonne model: observed held brake has sufficient
  static force in the declared 160 kN maximum-force model; zero modeled drift
  over 10 s. Assumptions: static friction, no slip/pneumatic delay, no game
  calibration. Insufficient force is not corrected with a guessed constant;
  detected actual motion revokes holding.
- Targeted integration covers interrupted/released brake, backend loss,
  unknown/unversioned signal, repeated fresh stationary frames, manual N/new N,
  source changes, real automatic, R/backward motion, stale data, identity races,
  emergency, current commands and immutable combined export/readback/tampering.
- Broad targeted result: **349 passed, 20 subtests passed**. After the final
  partial-write guard, the affected writer/holding/export subset passed
  **82 tests** (overlapping the broad run). The final after-IPC decision-clock
  correction passed its **104-test** targeted subset and an additional slow-read
  regression. Thirty-three new narrow cases cover the continuous-stop contract.
  `compileall` and `git diff --check` passed.
- A first sandbox run could not access pytest's temporary directory (WinError 5).
  Export tests were rerun with authorized access and a unique audit basetemp.
  One later run reported a generic export write failure without retaining its
  complete collector status; its exact cause is not proven. The same export
  passed alone and in the final broad/subset runs. Failure-only status printing
  was added to that test; no integrity expectation was weakened.
- Steering benchmark: 16 cases numerically identical to the immediately preceding
  local baseline. Speed-comfort benchmark: 12 cases numerically identical.
- Isolated BytesIO brake-writer benchmark, 9 x 20,000 writes per version:
  median 0.400 us/write baseline versus 1.194 us/write candidate. This measures
  the receipt operation only, not IPC cadence, DLL consumption or game physics.
- Ignored receipts: `docs/steering-audit/continuous-hold-{steering,comfort,verification}-20261003.json`.
- Full pytest is reserved for the user. Deployment and any live SDK holding
  confirmation require separate approval; no new drive is requested here.

Autopilot advances from the existing local 1.0.4 to 1.1.0 because its shared
zero-ratio interpretation gains backward-compatible planned-wait behavior.
No unaffected plugin version changes. Lateral controller, geometry, steering
cadence, startup/handoff, 500 ms limit and reverse protection remain unchanged.

## Files changed in this follow-up

- `core/engine.py`: conditional planned hold, local receipt checks, fault/cancel
  lifecycle, truthful selected output and waiting state.
- `core/transmission_mode.py`, new `core/service_brake_hold.py`: shared zero-ratio
  evidence gate and Engine-owned continuous-stop state; decision clocks follow IPC.
- `core/sdk/scs_controller_writer.py`: bounded write receipts including partial
  write failure; existing public setter return contract unchanged.
- `core/navigation/longitudinal_diagnostics.py`, `ui/dynamic_island.py`: compact
  immutable hold provenance and waiting presentation, with emergency precedence.
- `plugins/autopilot/main.py`, `PLUGIN_CHANGELOG.md`: affected plugin version/release.
- New `tests/test_continuous_service_stop.py`; existing local
  `tests/test_stop_handover_and_quiet_logging.py` gains failure-only collector status.
- This report, `PHASE7_SAFE_STOP_AND_LOGGING_20261003.md`,
  `PHASE7_FINAL_RESULTS.md`, `DEFERRED_WORK.md`: superseded assumption and limits.

The other existing local changes in `core/control_timing.py`,
`core/longitudinal.py` and `core/telemetry.py` were retained; this follow-up does
not introduce additional changes to those files.

## Automatic signal resumption follow-up (2026-10-03)

**BLOCKED at the producer contract, not implemented green-light stop-and-go.**
The public producer source was found and its MIT license reviewed. This is not
an assumed private-source/licensing blocker. No additional runtime changes were
made; all preceding local changes remain. Tests/documentation do not require
another plugin version bump. The earlier local Autopilot 1.1.0 remains.

### Exact source and binary evidence

Installed file:
`C:\Program Files (x86)\Steam\steamapps\common\Euro Truck Simulator 2\bin\win_x64\plugins\ets2la_plugin.dll`.
SHA-256: `D07CF70A6F0810E22A028943380641CB1984304F8DD72265B09736CEAD89B61C`.
It is byte-identical to `assets/ets2la_plugin.dll` and the two local ETS2LA Python
distribution copies for 1.59. PE FileVersion/ProductVersion is 1.59.1.0. The
different 1.60 DLL was not substituted.

The reference README points to [the producer repository](https://gitlab.com/ETS2LA/ets2la_plugin).
Current main `c925bd965a96c58b73eaea9ca033fe0f0dc623a7` targets 1.60.
Reviewed candidate [1.59 source](https://gitlab.com/ETS2LA/ets2la_plugin/-/tree/1f16156b9b37b70cf182c2bc09120fa1b234e129)
is `1f16156b9b37b70cf182c2bc09120fa1b234e129`, declaring CMake version 1.59.1.
Version correspondence is NOT proof that this commit built the installed binary;
no matching source/PDB or reproducible build receipt was found locally.
No upstream implementation was copied into production.

Eight small pinned source/license files and immutable URLs/hashes are retained
outside Git in `docs/steering-audit/semaphore-source-contract-20261003/receipt.json`.
`src/core.cpp`: SHA-256 `90129e7cc5db6a5381f37f9bc590f15a6e214fa047e7c098a57aaa7c62caf894`;
`src/processing/traffic.cpp`: `731048c04745f45f70a06919010a56cc1608f5d23315e8c47b2e3d71aa07055b`;
`src/prism/traffic/traffic_rule.hpp`: `bcf17f9570266dc1ac822659a836259df81579d5b3a606e533f5391989fd7cb7`.

### Actual acquisition/publication and missing interface

`CCore::init` registers `telemetry_tick` for SCS `frame_end`; its tick calls
`TrafficProcessor::tick`. Nearby prefab semaphore instances/traffic objects are
gathered; `write_semaphore_data` reads placement and traffic-rule color/timer,
sorts the closest forty and calls `CMemoryHandler::write_semaphore_mem`.
Publication is a plain memcpy to `Local\ETS2LASemaphore`, not an atomic envelope.

| Contract field | Actual interface | Release evidence |
| --- | --- | --- |
| ID, color, timer, tile-local pose/quaternion | Forty 48-byte records, 1,920 bytes; `fffhhffffifii` | Available candidate values |
| Source acquisition time/generation | No field/header | Missing; read time, timer or changed bytes do not replace them |
| Session / atomic generation binding | No lifecycle ID or seqlock marker | Missing; repeated equal reads do not prove acquisition |
| Controlled directed approach/stop-line | No decoded/exported LaneId or connector association | Missing |
| Python geometric relevance | Horizontal bearing/distance, lateral tolerance 32 m, facing tolerance 55 degrees | Heuristic only; no LanePath, connector or truck-height argument |

Precisely, `traffic_item_rule_source_t` contains arrays `N00007A8F` and
`N00007AA3`; `traffic_item_rule_link_t` is an otherwise undecoded wrapper.
The reviewed source does not identify fields linking a light to its controlled
directed approach. `semaphore_instance_t.id` is itself annotated "maybe".
Current UltraPilot navigation readers provide no independent signal-to-directed-
LaneId binding. A nearest facing green, even with the same numeric ID, cannot
be promoted to authoritative clearance on this evidence.

Source timestamp/generation instrumentation is possible at actual acquisition,
but would not create the missing controlled-approach relationship. Therefore no
guessed memory offsets, fabricated route relevance, timestamp-only replacement
DLL or optimistic automatic release were implemented. This follows the requested
STOP condition for a missing required producer interface.

### Reproduction, verification and before/after

New `tests/test_signal_clearance_source_contract.py` uses the actual legacy ABI,
real reader/selector, Engine's light-brake function and traffic publisher,
arbitration, real Autopilot/Engine and real Controller/SCS writer with an isolated
byte buffer. It does NOT execute the live C++ producer or prove game consumption.
After a moving red approach/continuous brake hold, decoded same-ID green removes
the ordinary light-brake request. Twelve fresh truck/control ticks over 1.2 s
still preserve `planned_wait`, positive physical brake writes and zero throttle.
The original stop reason remains latched. This reproduces the requested feature's
current refusal; it is NOT a correction of automatic resumption.

| Transition | Before / after this follow-up |
| --- | --- |
| Continuous approach -> stopped hold, gear zero | Preserved active AP, positive service brake, zero throttle |
| Legacy green -> release -> automatic launch | Still blocked; missing source clearance proof |
| Repeated/changed bytes, missing/unknown/other-ID light | No fabricated source timestamp, generation or permission |
| Session/reroute, stale data, R, broken chain or cancellation | Existing fail-closed behavior preserved |
| Driver parking brake | No writes, toggles or release |

Eight new cases passed. The selected holding/activation/arbitration/transmission
run passed **155 tests and 20 subtests**, including combined integrity export and
both transmission activation paths. A sandbox run failed accessing its temp
directory (WinError 5); the same tests passed with authorized access and a unique
audit basetemp. `compileall` and `git diff --check` passed. Full pytest was not run.
No closed steering/comfort benchmark was repeated because no runtime code changed.

### Single next step and runtime requirements

Obtain/verify the producer's controlled-approach/stop-line link definition
(`traffic_item_rule_link_t` and the two source arrays) for the 1.59 build, then
export the proven association with acquisition time, generation, session and
color as one versioned snapshot. No new drive is requested to guess these fields.

Completion requires a reproducibly built modified **`ets2la_plugin.dll`**, a
matching `core/sdk/ets2la_data.py` reader and Engine traffic publication, then
the existing hold/launch consumer transition. There is **no verified replacement
DLL, candidate hash or deployment manifest** for this feature yet. The current
Controller/SCS controller DLL and parking-brake fields must not be modified to
work around the gap. Offline continuous waiting is supported; automatic signal
resumption and live SDK holding remain NOT VERIFIED. No installation/game files
or original evidence were changed; nothing was deployed or armed.
