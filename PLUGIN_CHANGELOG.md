# Plugin changelog

Release history for individual plugins. See [PLUGIN_VERSIONS.md](PLUGIN_VERSIONS.md) for versioning rules.

## Core bounded refresh response protocol — unreleased, 2026-10-15

- Bind each zero-drive renewal to its original deadline cause and deterministic activation/route token. Preserve the fixed 100 ms renewal bound and original 500 ms observation leases; repeated stale producer ticks cannot rearm a wait.
- At receipt or final write, allow one actual complete-owner response read and rerun the full Engine executor, including real SDK pairing, navigation, transmission, continuous hold, arbitration and final physical gates. Never execute the expired pedals or synthesize drive from newer ACC/Policy alone. Account for a complete response published just before the consumer creates its request.
- Acknowledge only successful application using a separate token slot, avoiding deletion of a concurrently published next request. A new causal renewal follows a qualified response; genuinely missing/late responses still stop and latch the first fault.
- Preserve the first actual timely response-publication witness across subsequent Autopilot ticks before Engine acknowledgement. A single bounded publisher-local receipt also covers publication just before the request exists. New commands still require their own complete validation; the witness never renews old pedals or observations.
- Preserve compact original cause/token, response comparison and exact final vehicle pairing through the existing bounded automatic pedal incident and immutable codec. Keep existing codec dictionaries, export hashes, byte budgets, workers, and quiet logging.
- Core-only change: no plugin implementation, version, regulator, geometry, native DLL, parking control or safety timeout change. The afternoon incident proves expiry of a zero-drive wait; historical availability of the complete AP response before its bound remains unrecorded. See PHASE7_REFRESH_RESPONSE_PROTOCOL_20261015.md. Offline evidence is not ETS2 verification.

## Core longitudinal execution handoff — unreleased, 2026-10-15

- Preserve the validated command envelope through final Engine arbitration, including validity and decision source. A recoverable late dependency expiry can now enter the existing bounded zero-drive handoff instead of being misclassified as unqualified evidence. The old command is never renewed or executed after expiry; a full new producer decision must take over.
- Keep the original producer reserve, 500 ms evidence deadline, fixed 100 ms handoff bound and final prewrite expiry check. Preserve physically acknowledged continuous service braking during qualified renewal. Reject an experimental extra prewrite reserve after it unnecessarily withdrew still-valid drive in the unchanged Map preparation regression.
- Retain already consumed inputs and the rejected decision alongside subsequent safety writes. Record bounded sampled producer-read times and refresh witnesses in the existing journal/export without additional SDK/IPC reads, new workers or per-tick INFO logs. Use the actual compared vehicle snapshot in final rejection evidence.
- Core-only implementation; ACC 1.3.2, DrivePolicy 1.1.4 and all other plugin versions/DLL remain unchanged. Historical traffic publication/first-delivery and the exact initiating delay were not captured; offline reproduction is not presented as historical scheduling proof or ETS2 verification.

## Core observed crossing and incident preservation — unreleased, 2026-10-14

- Use actual constant-speed ego arrival for acquisition-timed crossing candidates. Do not promote a guessed +2 m/s² departure from standstill into an imminent collision; actual observed overlap and swept-box AEB remain independently effective. Untimed legacy captures retain their conservative behavior.
- With a complete original timed actor acquisition and a full three-second no-contact body prediction, deliver the existing positive crossing-arrival cap to the authoritative speed PID instead of converting a tiny broad time-window brake into a terminal hold. Recompute the original owner's cap from each actual source frame until a same-body receding witness or a genuine contact/terminal requirement supersedes it. Missing/reassigned actors, incomplete bodies or source loss cannot clear ownership.
- Pair departure checks with the current native acquisition before evaluating them; reject discontinuous same-ID motion as clearance. Reproject retained ownership on validated same-authority geometry changes.
- Stop passive planner mode/voice oscillation after authority is revoked; retain and announce the first emergency once. A short AVOID presentation release delay does not delay pedal or emergency decisions.
- Preserve compact decisive actor/slot/source-time/contact evidence ahead of optional detail within existing bounded codecs and pedal history. On a full significant-event quota, retain one pending immutable receipt for automatic fault export and stop futile retries. Preserve all original files and existing memory/file budgets.
- See [PHASE7_ROUNDABOUT_TRAFFIC_INCIDENT_20261014.md](PHASE7_ROUNDABOUT_TRAFFIC_INCIDENT_20261014.md). Original initiating actor poses are missing and the exact first emergency input exceeded the old detail budget; reconstructed examples are not presented as historical poses or game verification. No DLL, geometry, steering, PID, 5 m signal offset, timeout, parking or other plugin release change.

## ACC

### 1.3.2 — unreleased, 2026-10-14

- Stop generating pedal requests and repeating emergency speech for an inactive strict-schema activation. Reset private control/following state while Engine observation continues; a later pending N resumes current validated producer processing without restoring old output. Retain immediate emergency priority during active or pending authority and the existing regulator/actuator mapping.

## Core stop ownership and destination handover — unreleased, 2026-10-14

- Distinguish a fresh native-source positive moving-actor speed constraint from a terminal conflict stop. Ordinary positive caps feed the existing speed PID; they no longer apply an independent legacy distance brake or create a terminal hold. Missing actors, legacy/unqualified records, source resets, crossing/body conflicts, red signals and other stop causes cannot authorize restart or clear a terminal receipt.
- Retain the physically admitted continuous service brake at a positive-distance destination planning stop until explicit driver handover. Show the takeover instruction without hazards; do not label standstill as confirmed native GPS completion or silently release unattended holding. Automatic arrival versus manual GPS removal remains blocked by the missing producer lifecycle contract.
- Preserve original acquisition/authority and moving-constraint ownership in the existing bounded export using literal codec extensions. DrivePolicy stays 1.1.4; the native DLL and other plugins remain unchanged. ACC's concrete consumer correction is versioned below. See the final continuation in [PHASE7_DESTINATION_STOP_AND_ACC_COMPLETION_20261014.md](PHASE7_DESTINATION_STOP_AND_ACC_COMPLETION_20261014.md).

## ACC

### 1.3.1 — unreleased, 2026-10-14

- Consume the qualified positive caps of still-observed native moving protective actors in the existing speed PID. Preserve the actual constraining target ID and traffic lease through the shared arbiter and final Engine gate. Do not classify geometric protective candidates as confirmed lane targets or infer departure from absence; unknown/legacy inputs, true terminal conflicts, emergency and signal braking retain protection. No PID gains, ramp rates, signal offset, timeout, steering or DLL changes.

### 1.3.0 — unreleased, 2026-10-14

- Run the existing authoritative speed PID in nominal acceleration units and estimate only its measurement derivative over 150 ms using genuine observation intervals. Preserve load integral, saturation/external-output anti-windup, hard-cap withdrawal, the existing asymmetric pedal recovery and immediate emergency paths. Seeded noise/jitter model comparisons improve; calibrated ETS2 acceleration or physical jerk is not claimed.
- Consume optional native acquisition-timed actor motion from Traffic v1. Anticipate only deceleration established by two new source frames of the same ID/source/slot, bounded to the existing 500 ms evidence horizon. Never predict positive drive, renew a repeated frame, or treat TMP placeholder speeds/acceleration as measured kinematics. Native lifecycle changes revoke acquired following.
- Coordinated core/DLL candidate: atomically publish moving and parked actor bytes, source lifecycle/generation/frame/QPC acquisition time, actual ego tractor/trailer boxes and a same-frame SCS speed/placement anchor. Preserve legacy traffic mappings and Semaphore v2/v3. Old DLL inputs remain explicitly unqualified; stale/torn/reset data do not silently fall back to fresh legacy evidence.
- Coordinated core: retain ownership of every qualified crossing stop and require two newer acquisitions of its still-observed bodies moving away from the reference before bounded restart. Absence, zero demand, another ID, discontinuity, unknown stops and ongoing conflicts cannot release hold. Preserve the uninterrupted physical service-brake chain and original activation through the existing restart owner.
- Coordinated core: add protective native-box contact prediction along the current directed route, including observed ego trailers; existing emergency arbitration has immediate precedence. Fixed-articulation/constant-motion prediction is not a verified complete swept envelope, lane/coverage certificate or bumper-distance measurement. No geometry, steering timing, signal offset or parking operation changes.
- Candidate review: protect against already-observed body overlap even when no complete future route segment remains. Include native parked bodies as explicitly static protective models, without inventing a measured parked speed or clearance. Add same-image revision-12 SDK pedal/load evidence to the existing journal and an offline operating-point estimator; estimates do not automatically alter actuator gains.
- Candidate safety review: a new incomplete traffic-stop cause cannot inherit qualification from an earlier complete owner set; overflow/reset incompleteness remains latched for the same hold. Report qualified restart capability separately from pending clearance, without relaxing brake ownership or stop release.
- Preserve the original times and compact ownership/prediction evidence in the existing bounded pedal export; do not reorder existing codec field tables. See [PHASE7_DESTINATION_STOP_AND_ACC_COMPLETION_20261014.md](PHASE7_DESTINATION_STOP_AND_ACC_COMPLETION_20261014.md) for measured scope and explicit unfinished arrival/load-calibration work. DrivePolicy remains 1.1.4; unchanged plugins are not released.

### 1.2.1 — unreleased, 2026-10-13

- Revoke private following/PID memory on a real activation/session/intent change before rejecting an invalid first acquisition. Do not clear a fault in the current activation or accept an invalid request; validated same-authority geometry updates preserve the existing departure witness.
- Expose a single signed nominal acceleration demand with an exclusive, numerically equivalent actuator mapping. Declare its offline-plant basis explicitly; do not present it as measured ETS2 acceleration, calibrated load compensation or physical jerk. Additional comfort slew candidates were rejected after paired steady-error/jerk regressions.
- Coordinated core: quarantine a zero, non-emergency invalid ACC result from a previous epoch only inside existing initialization, with original times and non-epoch authority checked. Await the current producer without executing or relabeling its old packet. Current-epoch, stale, future, foreign, nonzero and emergency failures still reject.
- Coordinated core: retain the first consumed compact traffic brake basis and decisive actor/conflict in the existing long-lived stop receipt/export. Do not infer clearance from zero demand or a heuristic type. A draft that skipped crossing hold was rejected after the unchanged native-crossing/zero-ratio regression failed; original continuous-brake and emergency behavior are preserved. These core changes do not release other plugins or the DLL; the separate DrivePolicy producer fix is recorded below.
- See [PHASE7_ARRIVAL_RETRY_AND_ACC_ACCELERATION_20261013.md](PHASE7_ARRIVAL_RETRY_AND_ACC_ACCELERATION_20261013.md). GPS disappearance/arrival classification, producer-timed leader anticipation and complete-body AEB remain explicitly blocked; no game verification is claimed.

### 1.2.0 — unreleased, 2026-10-13

- Keep the acquired lead dependency across validated geometry/revision publication within the same activation, session, map, dataset and navigation intent. Reproject the original receiver witness on the new reference; real authority changes still reset it and missing observations never prove departure.
- Coordinated core: after a real same-intent Map rebuild, a freshly observed positive forward ratio and current validated ACC packet start new gearbox observation history. Do not carry old route times, zero-ratio bridge, launch or hold receipts to the replacement identity; absent/stale/foreign inputs and ratio zero retain rejection.
- Qualify an observed departure using the minimum distance of every native oriented tractor/trailer box from the directed reference instead of an enclosing disk. Preserve unique ID/source/slot, changed-record, original receiver-time, height, bounded projection and 2.6 m caution requirements. This is receiver evidence, not certified traffic freshness or physical lane clearance.
- Retain the existing speed PID, pedal recovery, emergency demand and 5 m signal reference. A relative-closing-speed planning candidate inspired by MonoCruise was rejected after paired cut-in and steady-state regressions; no acceleration mapper, jerk filter, ghost target or unverified stop-and-go was adopted.

## Core plugin lifecycle — unreleased, 2026-10-13

- Do not classify ordinary data KeyError as IPC shutdown. Preserve the first actual worker exception and revoke its producer packet immediately; stop after three consecutive failures with a nonzero exit and guaranteed cleanup. Required Policy/ACC inputs remain required during failure recovery, preventing old-limit cruise.
- Serialize spawn/supervision/stop, honor the UI shutdown request in parent and child, mark shutdown before Engine cleanup, and block restarting a disabled plugin. Allow at most three retries with 0.5/1/2 s backoff, with first failure and exit code published in bounded plugin health state; reset the budget only after 60 s healthy operation or explicit disable/re-enable.
- Core-only lifecycle changes do not release DrivePolicy, Map or other unchanged plugins. The historical DrivePolicy exception/exit code was not retained, so the reproduced worker defect is not presented as a proven historical stack trace.

## ACC

### 1.1.9 — unreleased, 2026-10-12

- Discard only positive PID integral accumulated for a qualified signal approach when its computed drive was not executed because the shared stop profile selected coast. Keep gains, derivative state, negative integral unwinding, other limits and emergency priority unchanged.
- Coordinated core follow-up: a freshly confirmed same-head green can transfer a still-moving qualified approach in simple-auto ratio zero to the existing bounded launch owner. Actual forward-started traffic/obstacle brake writes also retain continuous stop ownership without requiring a semaphore. Missing obstacle clearance remains a takeover limitation; disappearance is not permission to restart. ACC implementation and VERSION remain 1.1.9 at the user's request.
- Coordinated core follow-up, 2026-10-13: at the user's explicit request, change the directed prefab-entry SDK-reference offset from 8 m to 5 m, applied once through the existing target fields. Retain the stopping envelope, pedal controller, continuous brake, green confirmation and safety guards. The remaining 3 m planning component is not a measured truck front; painted-line clearance is still unverified. No ACC implementation or VERSION change. See [PHASE7_FIVE_METRE_STOP_REFERENCE_20261013.md](PHASE7_FIVE_METRE_STOP_REFERENCE_20261013.md).

## Map

### 1.1.2 — unreleased, 2026-10-12

- Publish a single selected-exit maneuver for a bounded, unambiguous directed cycle of placed one-way roads and three-port prefab connectors. Retain the preceding-exit progress gate and stable selected-exit identity; do not derive indicator direction from circulation curvature. Suppress unresolved connector arcs instead of inventing a maneuver.

## TurnSignals

### 1.0.2 — unreleased, 2026-10-12

- Apply the Map-owned entry/previous-exit progress gate before the existing roundabout warning window. Preserve manual, hazard and game self-cancellation priority.

## Core qualified signal approach — unreleased, 2026-10-12

- Delegate a positive qualified stopping envelope to ACC instead of issuing a second Traffic brake in the broad response band. Commit physical brake continuity only at an exhausted envelope or an acknowledged low-speed write in the existing terminal zone. Preserve standstill ownership, original timestamps, safety gates, 6 m + 2 m allowances and green release; no automatic repositioning after a red stop.
- These are offline corrections. Painted stop-line and truck-front geometry remain unmeasured; no calibration offset or parking-brake operation is introduced.

## Core terminal approach — unreleased, 2026-10-12

- Correct the first-brake regression exposed by the full suite: a slow qualified terminal approach still issues the calculated positive brake even before a continuous chain exists. At zero speed in the same terminal zone retain the brake request; Engine's unchanged authorization decides whether it may be written. No return to the moving full-pedal jump, no standstill repositioning, and no plugin version change.
- Remove the low-speed / fixed 1.5 m full-brake jump from the shared qualified-stop mapping when its stopping envelope is still positive. Retain full demand at exhausted envelope/target, actual continuous-brake holding, red standstill no-drive and original safety/identity checks. No target offset, 6 m + 2 m margin, PID gain, steering, DLL or plugin VERSION change.
- The paired production-path model improves the measured residual and terminal jerk without extra default-plant pedal reversals; it still stops before the planning target. Historical 2.5514 m causality and physical bumper-to-painted-line placement remain unverified. See [PHASE7_TERMINAL_APPROACH_20261012.md](PHASE7_TERMINAL_APPROACH_20261012.md).

## ACC

### 1.1.8 — unreleased, 2026-10-11

- Release only an acquired lead dependency after a same-ID/source-slot changed receiver record places every observed native body outside the existing route caution band. Preserve missing/ambiguous/stale/reassigned-record and already-latched loss protection; unknown traffic coverage remains unconfirmed. Existing speed controller, target recovery and emergency priority are unchanged.

## TurnSignals

### 1.0.1 — unreleased, 2026-10-11

- Release automatic ownership with `None`; request `off` only to cancel the plugin's own acknowledged side. Yield to game self-cancellation, a driver's side change and hazards, including live disable and a later Engine observation.
- Keep consumed semantic events across same-intent geometry republication, bounded to the current Map event window. Continue using the existing topology-owned turn/selected-roundabout-exit events and warning distances; ordinary curvature does not select an indicator.

## Core joint traffic and indicator fixes — unreleased, 2026-10-11

- Start a discovered plugin skipped as disabled when the UI later enables it; do not duplicate workers or rescan folders every tick. Release TurnSignals ownership on live disable.
- Retain native trailer records from the same traffic capture in the existing protective crossing path. Share the bounded observed-lead-departure contract with the physical longitudinal boundary; between Traffic and ACC ticks, coast without old drive instead of requiring a departed target's missing speed cap. Retain original lease revalidation and other brake/emergency floors.
- Preserve manual/hazard indicator priority at the actual Controller boundary and store the compact immutable departure receipt in the existing decision/history codec without new reads or larger budgets.
- Historical collision actors and truck-front/physical-stop-line geometry remain unavailable; no guessed stop offset or safe-gap certification was added. Existing significant-event quota is full and originals are untouched. No DLL, steering, geometry, PID, timeout or unrelated plugin-version change. See [PHASE7_JOINT_TRAFFIC_AND_INDICATORS_20261011.md](PHASE7_JOINT_TRAFFIC_AND_INDICATORS_20261011.md) for before/after reproductions and partial offline scope; not game verified.

## ACC

### 1.1.7 — unreleased, 2026-10-11

- Constrain the existing speed controller with the positive GPS remainder from its actual SDK observation; reuse the qualified-stop distance envelope and pedal mapping without new PID gains or a second controller. Preserve lower signal/curve/following limits and emergency priority.

## DrivePolicy

### 1.1.4 — unreleased, 2026-10-14

- Validate the consumed vehicle speed and observation before planning. Expected missing startup telemetry publishes an invalid zero-brake/no-plan packet without throwing `KeyError: 'speed'`, exhausting bounded worker restart attempts or leaving every later N without a Policy producer.
- Keep Policy required while evidence is unavailable; revoke its previous plan and wait for a real valid SDK acquisition. Do not fabricate zero speed, renew old observations or clear a current control failure. Same-instance worker recovery and Map-to-Controller activation are verified offline for simple and real automatic modes.
- Retain the approved 5 m stop reference, distance stop profile, signal hold/restart, emergency priority and existing lane geometry. No DLL, Map, Autopilot or TurnSignals implementation change. See [PHASE7_ARRIVAL_RETRY_AND_ACC_ACCELERATION_20261013.md](PHASE7_ARRIVAL_RETRY_AND_ACC_ACCELERATION_20261013.md).

### 1.1.3 — unreleased, 2026-10-11

- Apply the current GPS stopping ceiling after non-stop preference smoothing; suppress only the duplicate auxiliary brake when ACC owns that ceiling.

## Autopilot

### 1.3.4 — unreleased, 2026-10-11

- Schema-1 arrival uses the common pedal/authority path instead of the legacy early-return brake branch; label a confirmed normal completion replay `destination_reached`.

## Core GPS destination lifecycle — unreleased, 2026-10-11

- Core: retain a positive <=25 m GPS route; distinguish moving destination approach from its physically acknowledged terminal brake chain. Normal release requires a fresh positive remainder within the existing arrival radius and acknowledged terminal reserve, standstill, current identity and no competing stop/fault. Zero/removal is never promoted to success; no automatic parking brake or unattended hill-hold promise.
- Existing diagnostic source captures the already-consumed GPS distance/time as additive immutable fields. Indexed codec tables, fixed budgets and source timestamps remain unchanged. Freeze the original red-approach test baseline from its hash-verified backup so later installations cannot silently replace the counterfactual.
- No steering/geometry/500 ms change or DLL replacement. The actual semaphore front/painted-line reserve and historical second-roundabout brake producer remain unproven; this is a partial offline correction, not complete game verification. See [PHASE7_DESTINATION_AND_APPROACH_REVIEW_20261011.md](PHASE7_DESTINATION_AND_APPROACH_REVIEW_20261011.md).

## ACC

### 1.1.6 — unreleased, 2026-10-11

- Own the qualified signal distance trajectory in the existing speed-control output, including its original required-deceleration mapping. Distinguish an active signal constraint from a signal-selected brake; a lower road/curve/vehicle limit still wins.
- Do not reset the speed controller on a duplicate independent far-signal pedal, or retain an obsolete signal ceiling after fresh green. Use existing pedal hysteresis and the declared response-sized planning reserve for coast/recovery, without a minimum approach speed, new gains or a second regulator. Same-head green remains Engine-confirmed.

## DrivePolicy

### 1.1.2 — unreleased, 2026-10-11

- Apply the current signal stopping ceiling after smoothing the non-signal speed preference; do not persist a lower ceiling belonging to an earlier position.
- Suppress only the duplicate auxiliary brake when ACC owns that qualified signal target. Lower independent constraints, unavailable coverage and their protective requests remain effective.

## Core qualified signal approach — unreleased, 2026-10-11

- Separate a locked moving approach from terminal continuous service-brake authority. Allow a fresh same-head/profile decision to coast or recover from excessive early slowing; only actual forward-started positive writes qualify terminal braking/holding. Preserve physical sequence, identity, green confirmation, cancellation and negative safety checks.
- Preserve the existing full terminal request, including when the response reserve exhausts the stopping envelope; do not let a squared-speed demand fade against idle load at a zero-speed target. The final Engine gate also enforces the current qualified signal ceiling between producer ticks.
- No parking writes, source retimestamping, 500 ms increase, steering/geometry change, DLL replacement or new collector. Read [PHASE7_RED_APPROACH_PROFILE_20261011.md](PHASE7_RED_APPROACH_PROFILE_20261011.md) for retained Oct 11 evidence, pre-fix failures, paired uncalibrated models, nonuniform jerk results and the missing first-brake historical inputs. Not game verified.

## Core prior-activation Traffic initialization — unreleased, 2026-10-10

- Publish the existing fixed activation/first-command bound with its exact authority; share initialization classification between Autopilot and the physical Engine. A still-valid prior-activation producer value is rejected without prematurely revoking the new request, only while all other identities match.
- Keep throttle zero before a current Traffic publication, never execute or relabel the old packet, and continue without another N after current validated data. Preserve supported continuous service braking, emergency priority and genuine missing/stale/future/foreign/R/backend rejection. Clear the bound on cancellation or first real accepted decision; never renew it per tick.
- Keep existing 0.5 s/2.5 s initialization and 500 ms evidence limits, original times, controllers, geometry and DLL. No plugin implementation/version change. Correct historical rejected epoch to 8145579392300; exact IPC ordering remains unrecorded. See [PHASE7_REACTIVATION_TRAFFIC_20261010.md](PHASE7_REACTIVATION_TRAFFIC_20261010.md) for the five pre-fix failures and final integration results. Not game verified.

## Core signal phase and moving clearance — unreleased, 2026-10-10

- Preserve original native countdown, yellow direction, acquisition/generation and phase plan through qualified selection and existing bounded pedal history/export. Append history fields without changing indexed source-codec keys or memory budgets.
- Forecast the qualified head's current green using directed extent, current speed, capped planning dynamics and explicit unmeasured clearance allowances. Use the existing shared stop envelope for insufficient green; distinguish preferred deceleration onset from the full-brake planning bound. A planning dilemma coasts without granting future-green clearance; emergencies and red remain effective.
- Clear a signal-only continuous braking commitment during forward motion after two fresh same-head green acquisitions and final source/identity/deadline validation. Restore the current decision and its diagnostic source; preserve other stop reasons and the existing bounded standstill restart.
- No controller gains, steering cadence, geometry, 500 ms limits, DLL or plugin implementation/version changes. Offline counterexamples, 48 paired plant cases, nonuniform jerk changes and the still-open manual-reactivation/initial-red evidence limits are documented in [PHASE7_SIGNAL_APPROACH_TIMING_20261010.md](PHASE7_SIGNAL_APPROACH_TIMING_20261010.md).

## Core scoped-native signal direction — unreleased, 2026-10-10

- Remove the extra 180-degree reversal from schema-3 actor-forward direction in binding and coverage. Original PPD 25 coordinates/quaternions and the native packing prove that the recorded ID 3 pose is opposite to our group-1 passage; do not remap its ID or treat its green as clearance.
- Preserve exact placed ownership, route/group/lifecycle, original producer times, distance-aware unknown approach, 500 ms freshness, continuous service hold and same-signal green confirmation. No new regulator, geometry, producer schema, DLL or plugin release.
- Verify the own-head stop/restart model through reader, Policy/ACC, Autopilot, Engine and physical test writes in both automatic modes. Unknown authored-object kinds remain uncertainty. See [PHASE7_SIGNAL_NATIVE_DIRECTION_20261010.md](PHASE7_SIGNAL_NATIVE_DIRECTION_20261010.md) for historical/model boundaries and the consistent runtime package.

## ACC

### 1.1.5 — 2026-10-10

- Consume the shared original-lease approach ceiling for an unresolved, native-owned directed signal entry. Preserve lower route/traffic limits, the existing speed regulator and immediate emergencies; detected green is not clearance.

## DrivePolicy

### 1.1.1 — 2026-10-10

- Include the same distance-based unresolved-entry ceiling in existing speed planning. The required dependency retains its producer time and 500 ms deadline instead of promoting an unassigned head into a red/green control.

## Core/UI signal-distance contract — unreleased, 2026-10-10

- Replace distance-independent takeover for proven owned entries with a bounded uncertain approach and the existing stopping reserve. Missing entry/speed evidence remains fail-closed; no nearest-head control or invented stop line is introduced.
- Prepare at most 128 fixed-field ownership scopes, reject proven foreign placement fallback only for complete metadata, retain one unresolved dependency on disappearance and invalidate it on authority/lifecycle change.
- Preserve already-compared LaneId/progress/publication and native head ownership/target/reserve in the existing bounded incident receipt, including priority evidence after optional detail overflow; keep historical schema-1 decoding and unchanged collector budgets.
- Label pending unassigned detection separately in the HUD. Qualified red/continuous service hold/fresh same-signal green/restart and other stop blockers remain unchanged. No new Autopilot/Map release, DLL change or game confirmation. See [PHASE7_SIGNAL_DISTANCE_CONTRACT_20261010.md](PHASE7_SIGNAL_DISTANCE_CONTRACT_20261010.md).

## Unreleased packet-renewal fix — 2026-10-10 (no new plugin release)

- Map keeps one private read-only geometry snapshot per exact publication token; public SDK copies, same-build invalidation and live identity/SDK checks remain intact.
- Core caches exact directed prefab topology enumeration within 128 entries, 16,384 curve indices and 1 MiB; equivalent iterative traversal removes recursive closure cycles without changing geometry or positional lane selection.
- Shared longitudinal handoff retains the exact expiring leaf only as a comparison witness for the existing bounded zero-drive transition when its IPC consumes the remaining milliseconds. No expired propulsion, timestamp renewal or increased timeout is permitted.
- Existing Map packets and Autopilot replay/timing rows retain fixed-size reference subphase times without additional SDK/IPC reads or per-tick INFO logs.
- Map checks the existing single-slot evidence worker before fetching profile/traffic arguments that would be discarded while it is occupied. The actual offer/harvest validation, worker count and queue bound are unchanged.
- Existing packets carry one explicitly sequenced previous completed Map tick, including CPU, publication completion, post-publication work and gap. Normal plugin-stop and combined exports retain this evidence on successful episodes with immutable executor/source binding; no separate collector or timestamp refresh.
- Autopilot 1.3.3 / Map 1.1.1 declarations are retained by explicit user instruction; not a new release or game reliability certificate. Historical 620/477 ms internal stalls are not fully attributed. See [PHASE7_PACKET_REFRESH_RELIABILITY_20261010.md](PHASE7_PACKET_REFRESH_RELIABILITY_20261010.md).

## Autopilot

### 1.3.3 — 2026-10-09

- Share the existing 2.5/s service-brake rise constant with the final acknowledged hold floor. Retain continuous positive braking, emergency/drift priority and the established red/green restart contract; controller gains and freshness limits are unchanged.
- Paired modeled stop tests reduce near-standstill jerk at 35/50 km/h without an entry overrun. This is not confirmation of loaded hill holding or SDK consumption in ETS2. See [PHASE7_SIGNAL_AND_TRAFFIC_COMPLETION_20261009.md](PHASE7_SIGNAL_AND_TRAFFIC_COMPLETION_20261009.md).

## Map

### 1.1.1 — 2026-10-09

- Preserve actual placed-prefab UID, native node UIDs and origin with the existing directed signal passages; use the controlled curve's existing transformed heading. Rebuild schema-14 caches which lack ownership metadata. No route-centerline, localization or steering-cadence change.

## Core/native signal and traffic fixes — unreleased, 2026-10-09

- Add coherent owner records in native signal schema 3 while preserving schema 2 acquisition times and ABI. Bind scoped heads to exact placed ownership and a directed group instead of treating lamp elevation as road-deck elevation. Keep foreign/ambiguous/torn/stale/lifecycle rejection and explicit unassigned takeover; no nearest-light control fallback.
- Make validated TrafficCapture and the existing directed-route candidate/crossing path own traffic demand. Legacy display defaults, duplicate IDs and straight-cab projection cannot override rejected source evidence or a no-conflict curved route. Preserve protective caution and emergency response; empty traffic is not clearance.
- Seal significant brake/source, AVOID_OBSTACLE, unassigned-signal and technical events in the existing bounded PedalJournal and replay worker without arming. Preserve original receipts, first faults and following writes; add explicit coalescing/loss, fixed disk quota and atomic integrity. No extra diagnostic SDK/IPC reads or new collector.
- Verify the bounded game-log prefix even when filesystem metadata appears unchanged; reject same-size rewrite without interrupting ordinary append. All file I/O remains on the existing observer worker.
- Scoped DLL 1.59.3-up-signal-scope is an uninstalled offline candidate. Live ownership/ID correspondence and original missing traffic inputs remain unverified; the historical incident is not declared resolved in ETS2. ACC, DrivePolicy and Collision plugin implementations/versions are unchanged.

## Autopilot

### 1.3.2 — 2026-10-09

- Treat an actually observed, forward route-aligned head with unproven directed assignment as a technical takeover requirement, not optional empty perception. Use the same coverage predicate as the final Engine boundary; inhibit propulsion, retain the first cause and do not resume automatically after technical loss.
- Preserve stronger fresh emergency demand when entering the existing safety stop. A coverage error cannot downgrade current emergency braking to the normal 0.70 safety floor. Regulators, steering cadence, launch and green-confirmation timings are unchanged.
- See [PHASE7_SIGNAL_COVERAGE_AND_BRAKE_REVIEW_20261009.md](PHASE7_SIGNAL_COVERAGE_AND_BRAKE_REVIEW_20261009.md): offline repairs do not establish live signal coverage or the historical brake source, so the complete incident task remains blocked.

## Core/UI signal coverage — unreleased, 2026-10-09

- Keep raw detection, qualified control and unknown coverage separate. Check the bounded original producer heads; preserve actual placed-ID selection and locked service braking. An earlier unassigned conflict cannot be silently cleared by a later qualified head. No nearest-head control fallback is restored.
- Show a fresh producer-timed detected color with an explicit unassigned label; keep untimed, expired and future-timed detection gray. Publish a clear Slovak takeover instruction. The HUD never promotes detection to control authority.
- Carry the original signal lease and exact rejected head through existing arbitration/fault/export paths. Compact fixed receipt fields within unchanged 8 KiB/64 KiB budgets and reject incomplete vectors. No new collector, DLL, timeout, map geometry or speed-planner change.
- Recover only uniquely determined planar route vertices from existing original projections/fractions for offline curve queries. Missing geometry, mixed identity and inconsistent constraints are refused; missing calculation speed remains an explicitly marked proxy. This analysis is not a measured historical pedal command.

## Autopilot

### 1.3.1 — 2026-10-08

- Reject unavailable confirmed transmission-mode evidence with its original cause before the zero-ratio fallback. A temporary observer failure is no longer reported as loss of forward gear; returning evidence does not automatically restore a technically disabled activation.
- Preserve the first intervention through Engine release/export. Lateral and speed regulators, steering cadence, launch commands, freshness limits and reverse protections are unchanged. See [PHASE7_SIGNAL_APPROACH_CONSISTENCY_20261008.md](PHASE7_SIGNAL_APPROACH_CONSISTENCY_20261008.md) for offline verification and unresolved historical evidence.

## Core signal/approach consistency — unreleased, 2026-10-08

- Require a uniquely placed, observed producer head before an authored prefab control group becomes a required signal stop. Retain an unknown stop dependency after losing that qualified head; an unobserved template group cannot manufacture red or hide a later qualified control.
- Bind planned-stop admission to the actual winning brake source. Ordinary ACC overspeed braking cannot latch a prospective distant red and repeatedly inhibit drive below the approach profile.
- At stationary continuous holding, retain the strongest successfully written deceleration brake from that same admitted chain instead of freezing the final tiny distance-profile value. Keep the unchanged motion/reverse guard and no-parking-brake ownership; returned software writes do not establish game consumption or hill holding.
- Read a bounded complete immutable game-log prefix, with at most one prefix-verification read on append. Reject rewrite, truncation, replacement and unconfirmed profile/mode changes; never renew previous observer evidence as a substitute for acquisition.
- Revalidate actual fresh GPS lane authority, steering packet and engagement alignment when a readiness summary is old. Preserve every packet/heartbeat/identity/alignment gate and the original summary timestamp.
- Keep exact compared mode evidence/vehicle metadata and first fault in the existing bounded incident path. ACC, Map and DrivePolicy implementations/versions are unchanged in this task. Model stop jerk near standstill can increase with stronger holding and is reported separately from unchanged moving deceleration and regulator benchmarks.

## Core signal/stop lifecycle — unreleased, 2026-10-08

- Remove the remaining metadata-free geometric signal-control fallback. Keep unassigned head detection separate from an authored directed control entry and an actually observed qualified signal; label an unobserved entry explicitly in the HUD.
- Preserve an acknowledged forward-started planned service-brake chain while approaching without a signal lock, through producer changes and zero demands. Use the existing same-entry positive distance profile, then acquire a recovered actual red/yellow receipt for the same passage/ID before permitting confirmed green restart. Preserve current SDK/command/identity checks, reverse/motion rejection and the original first stop evidence.
- Keep the selected producer's causal reason at the final longitudinal boundary. Preserve consumed signal fields and missing-head stop geometry in the existing bounded journal; sub-budget optional crossing/display attribution and mark its loss instead of silently erasing the whole input.
- Verify actual producers/Controller writes, both automatic modes, repeat cycles, export integrity and read-only installed-runtime baseline comparisons. Normal-red braking, sixteen steering cases and twelve comfort cases remain numerically unchanged. No plugin implementation/version changes in this continuation. See [PHASE7_SIGNAL_STOP_LIFECYCLE_20261008.md](PHASE7_SIGNAL_STOP_LIFECYCLE_20261008.md) for measurements and separate unresolved historical incidents.

## Core diagnostics — unreleased, 2026-10-07

- Extend the existing automatic PedalJournal incident with a fixed-budget thirty-second decision history: at most 10 Hz regular samples, ordered state changes and explicit between-sample physical-edge aggregates. Preserve the detailed 64 KiB journal, original SDK/command times and exact owned identity references.
- Retain release provenance from actual Controller calls, including hotkey/shutdown calls outside a flush, and preserve the first intervention through subsequent safety writes. Keep requested/selected/physical/SDK evidence distinct; do not infer game consumption or fill missing measurements with zero.
- Export the owned history through the existing single-job background replay writer; retain independent coverage/loss metadata and reject malformed history references/order. Combined and dense steering exports remain available. No controller, arbitration, timeout or plugin implementation changes in this continuation; Autopilot remains at its already pending 1.3.0. See [PHASE7_PEDAL_HISTORY_20261007.md](PHASE7_PEDAL_HISTORY_20261007.md).

## Autopilot

### 1.3.0 — 2026-10-07

- Add bounded diagnostic provenance to the existing longitudinal command: the exact producer inputs, brake requests, original truck observation, decision sequence and consumed EcoDrive preference. Pedal arbitration, regulator outputs and validity checks are unchanged.
- Export sealed dense replay buffers through a single bounded background job; forward the existing first intervention receipt to Engine without additional diagnostic SDK reads. Ordinary startup also retains the existing PedalJournal and exports a hash-checked longitudinal boundary incident on automatic disable without manual arming.
- Keep actual write order/results, rejected inputs and post-fault safe writes separate from SDK response. Reuse combined export and its cursor without draining the incident ring. Explicitly report dropped events, unavailable fields and incomplete evidence. See [PHASE7_AUTOMATIC_PEDAL_EVIDENCE_20261007.md](PHASE7_AUTOMATIC_PEDAL_EVIDENCE_20261007.md).

## Autopilot

### 1.2.3 — 2026-10-07

- Publish the original bound SDK positive-ratio observation after validation, separately from Engine's committed output history. The common drivetrain transition can consume it only for a fresh zero-pedal forward coast with matching activation/route and the existing fixed zero-ratio bound; it never grants neutral propulsion or renews source time.
- Retain compact compared observation/history fields in the first ratio-fault receipt. Preserve launch, continuous service braking, qualified green restart and all reverse/freshness/identity controls. See [PHASE7_COAST_AND_SIGNAL_SCOPE_20261007.md](PHASE7_COAST_AND_SIGNAL_SCOPE_20261007.md) for offline evidence and unresolved historical brake-source attribution.

## Core/UI fixes — unreleased, 2026-10-07

- Preserve emergency and driver-handover intervention receipts in the automatic pedal journal before physical safety writes. Await background replay completion in export regressions rather than relying on thread scheduling; control decisions and memory limits are unchanged.

- Do not promote a geometric head when prepared directed-passage metadata has no relevant regulated passage. Remove the Engine nearest-head substitution from longitudinal control; separate optional raw detection from the qualified signal and keep its read failure from clearing a valid red.
- Label unassigned detected heads separately in the 2D HUD; unchanged 3D control views do not display raw detection as a controlling head. Keep locked passage, elevation/orientation, ambiguity and producer-timed green rules.
- Share the bounded coast-only observation receipt through Plugin and Engine; preserve the existing neutral-propulsion rejection, byte-mapping write safety and immutable diagnostic journal. Steering (16 cases) and comfort (12 cases) are unchanged. Historical pedal alternation and false-head identity are not reconstructed from steering-only replay headers.

## Core/application fixes — unreleased, 2026-10-07

- Pin the longitudinal command before drivetrain checks. If IPC publication overtakes the captured SDK frame, obtain at most one actual replacement truck observation and fully validate the pinned command against it. Reuse the same observation through forward-ratio, continuous-hold and physical output checks; preserve the ahead predicate, original times, identity checks and final write deadline.
- Keep exact compared command/truck receipts, original capture and retry timing in the existing bounded fault/journal export. Do not replace the fault header with later telemetry. Pack fixed-key receipts losslessly within unchanged memory budgets; normal commands add no routine retry payload.
- Verify both automatic modes, repeated races, stale/future/foreign inputs, expiry during reread and existing red/wait/green cycles through actual Controller mapping writes. Steering (16 cases) and longitudinal comfort (12 cases) are numerically unchanged. See [PHASE7_COMMAND_OBSERVATION_PAIRING_20261007.md](PHASE7_COMMAND_OBSERVATION_PAIRING_20261007.md). No plugin implementation or version changes; ETS2 confirmation remains open.

## Core/application changes — unreleased, 2026-10-06

- Admit the first fresh identified planned brake at a moving zero ratio as a bounded brake-only transition. Let its actual returned brake write establish the existing service hold; validate that current chain before an obsolete zero-transition deadline. Do not permit anonymous neutral propulsion or renew old observations.
- Lock the qualified signal head when continuous braking starts on yellow as well as red. Preserve same-head/passage/lifecycle green confirmation and other-stop clearance checks through repeated supported wait/restart cycles.
- Evaluate all observed protective crossing candidates on the unchanged directed local reference, retaining the stronger existing brake. Bound actor/edge work and compact diagnostic attribution; missing producer freshness and coverage remain explicit and cannot authorize entry or stop release.
- Decode truck control fields from one bounded immutable SDK image after equal-copy checks, rejecting partial/nonfinite reads. Preserve its original acquisition time; retain an accepted sample only during a detected copy overlap within its existing age limit. Pause, inactive game and true loss still revoke authority.
- Production counterexamples, unchanged steering/comfort benchmarks and unproven historical SDK/collision causes: [PHASE7_JOINT_STOP_TRAFFIC_20261006.md](PHASE7_JOINT_STOP_TRAFFIC_20261006.md).

- Support the producer-timed `traffic_signal` leaf in the bounded decision-refresh contract. Preserve continuous service braking while waiting for replacement decisions; reject missing, expired, foreign-head/lifecycle/passage and retimestamped-frame evidence without extending the original signal lease.
- Retain authored prefab-curve semaphore IDs and invalidate schema-13 caches which lack them. Prepare qualified control entries from the unchanged directed LanePath and existing world/elevation transform.
- Scope live signal IDs to the selected placed passage with position, approach, height and ambiguity checks; allow repeated IDs in distinct prefabs without admitting duplicate ID/placement rows.
- Carry the original producer-timed signal deadline through traffic publication, arbitration and the last physical boundary. Fresh vehicle telemetry cannot renew old red/green evidence; render-frame provenance remains separate from the truck SDK frame.
- Derive a stop target before the complete directed passage, labelled as unverified painted-line geometry with a 6 m unmeasured front allowance and 2 m stand-off deducted once. Missing known-entry control data constrains approach as unknown and cannot be replaced by geometric green.
- Feed the existing longitudinal flow a distance/response-aware stop constraint. Permit a fresh positive same-passage brake request to decrease while moving without interrupting the acknowledged chain; retain stationary/unknown hold and all safety checks.
- Preserve the qualified passage through green confirmation and bounded restart. Latch actual directed-entry overrun to refuse automatic restart; preserve the prior stationary-red holding limitation and existing toll ownership.
- Preserve derived-target fields in the existing bounded combined export without changing journal/chunk limits or granting runtime authority. Offline evidence and limitations: [PHASE7_PREFAB_SIGNAL_BINDING_20261006.md](PHASE7_PREFAB_SIGNAL_BINDING_20261006.md).

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

### 1.1.0 — 2026-10-06

- Add bounded prefab traffic-control metadata to the immutable validated LanePath publication, using selected directed curve IDs and placed-instance geometry. Prepare it during route construction, outside the fresh steering calculation.
- Preserve lateral geometry, regulator, steering scheduling, 500 ms checks and existing roundabout profile. Missing metadata remains explicit; dedicated tollgate assets retain their existing control flow.

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

### 1.2.2 — 2026-10-06

- Use the common bounded zero-ratio planned-braking and acknowledged service-hold transition before rejecting lost forward confirmation. Suppress propulsion in its brake-only phases; preserve existing launch, reverse, freshness and route-identity guards.
- Keep supported continuous waiting active without ordinary-wait hazards, using the existing Engine-owned hold and qualified green restart rather than a separate gearbox exception.

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

### 1.1.0 — 2026-10-06

- Consume the derived directed-entry stop target in the existing speed plan with response/transfer allowance; avoid braking solely from the light-head position or deducting stand-off twice.
- Treat an unobserved known-entry control as an unknown stopping constraint, never green clearance. Preserve lower map/curve/traffic limits and existing arbitration/controller ownership.

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

## Core traffic availability and fault export — unreleased, 2026-10-10

- Separate vehicle/identity envelope validity from optional actor capture usability and qualified signal coverage. Validate coherent evidence roles and reject unsupported positive demands; preserve acquired-target loss and same-head signal hold/clearance. No weakened freshness/identity checks or new traffic sensor.
- Reject absent/zero/sentinel and duplicated actor IDs with four bounded original source-slot/pose examples; equal values never authorize content-based deduplication. Preserve receiver time as receiver time, not producer freshness.
- Keep the exact required traffic cause/frame/time/context in existing fault and automatic incident exports using priority immutable receipts inside unchanged budgets. No extra SDK/IPC reads, new collector or per-tick INFO output.
- Revoke longitudinal authority when the SCS connection fails during physical output; do not publish failed writes as applied commands. This separate backend defect was reproduced offline, not attributed to the historical traffic refusal.
- See [PHASE7_TRAFFIC_AVAILABILITY_20261010.md](PHASE7_TRAFFIC_AVAILABILITY_20261010.md): the retained earlier optional traffic packet is not the missing first rejected AP snapshot. The historical native actor cause and game outcome remain unverified. Plugin implementations/versions and DLL are unchanged.
