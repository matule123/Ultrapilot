# Nov 2 evening roundabout — original evidence audit

Status: INCIDENT ANALYZED; PREDICTION / CONTROL NOT YET REPAIRED.
No runtime, settings, DLL, actuator output or installed version changed.

Follow-up (November 3): the above is the original audit verdict. The targeted
source correction, before/after reproductions and current qualification limits
are recorded in [PHASE7_NOV3_ROUNDABOUT_REPAIR.md](PHASE7_NOV3_ROUNDABOUT_REPAIR.md).
Original incident completeness and the missing AP11926 attachment remain
unchanged; follow-up tests do not create historical evidence or a game PASS.

## Sources and integrity

Installed build: UP-NOV2-PREPARATION-02. Session
`acc09d754db347859ee0a83944db6d9a`, incident parts `8703` and `11926`.
Both original manifests and referenced files pass `inspect_incident` integrity.
Neither dossier is complete. Part 8703 has its complete AP attachment; part
11926 explicitly reports `AP_PART_NOT_DELIVERED_WITHIN_ASSEMBLY_WINDOW`.
Engine windows also declare observation gaps. Do not call either a complete
reconstruction of all consumers. Near the incident, native actor positions,
traffic/ACC publications and physical pedal bindings are available.
Part 11926 contains 522 ordered pedal calls, zero missing decision/input links
and zero missing call sequences. These are backend calls, not proof of game
consumption. Original captures remain unchanged.

Derived audit: `tools/analyze_nov2_roundabout.py` and
`docs/steering-audit/nov2-roundabout/analysis-11926.json`.
The tool decodes original native byte captures using the existing observation
decoder; it does not substitute today's live traffic for historical frames.

## Proven intervention chain

1. At local 20:56:20.946, emergency brake uses `traffic_emergency`.
   Decisive actor **61**, moving, native lifecycle 87193271266866,
   generation 36660, frame 1013622620, source time 8431.6835558.
   Heading model: `constant_tractor_speed_raw_body_heading`.
   Crossing brake 0.7442873; predicted actor arrival 3.46257 s,
   ego arrival 1.54912 s; crossing point 11.34435 m along ego reference.
   This is the crossing heuristic, not a proven observed collision.
2. At 20:56:21.893/896, Engine/AP reject ACC as invalid because
   `ACC target unavailable or unconfirmed departure; driver takeover required`.
   At check 8432.7108725 the ACC observation is only 25.734 ms old,
   with about 474.266 ms remaining. This is **not a lease expiry**.
3. Actor 61 is still in native generation 36687. Owner witness is chain-valid,
   qualified, current slot 1 (acquired slot 2); retained continuity is present.
   This is **not evidence that the physical actor disappeared**.
4. At that acquisition, native ego speed is **-0.039795611 m/s** and the
   contemporaneous SDK vehicle speed is **-0.022485010 m/s**.
   `observation()` only produces ego bodies for nonnegative native speed;
   `crossing()` rejects negative SDK ego speed. Consequently the consumed
   traffic packet has no body prediction and no crossing conflicts/completion.
   ACC then sees neither a cap nor a braking continuation and latches the
   target-unavailable technical fault. The signed near-stop speed transition
   is a concrete reproduction target; it must not be hidden by falsifying speed
   or removing real reverse/missing-data protection.

## Prediction versus actual actor movement

The first consumed crossing claim is at 8431.6759662, using generation 36658,
source time 8431.6109708. It predicts actor 61 reaching
XYZ `(46071.9966495, 10.390625, 40228.7360086)` after 3.6467015 s.
At source time 8435.3217966 (64.1 ms after the forecast arrival), the original
native record places it at XZ `(46063.5859375, 40216.0234375)`:
**15.243 m horizontally from the predicted crossing point**.
The closest recorded actor reference to that point over the audited 8424–8447
window is **11.039 m**, at 8434.5646886. These are sampled reference-point
distances, not certified bumper/body clearance or counterfactual collision proof.

The actor's heading is not constant: yaw ~1.67080 at 8430.9367,
1.87293 at 8431.6836, 1.80457 at 8432.6411 and 1.39200 by 8434.9461.
The straight-ray model and body AEB both assume constant actor heading; neither
uses the actor's actual future turn. This supports the user's complaint about
an unrealistic straight predicted path, but does not prove which exit was
knowable in advance or that all roundabout yielding was unnecessary.

## Required repair and acceptance

- Reproduce the actual retained crossing owner + braking to near zero + signed
  negative native/SDK speed + missing body prediction + ACC rejection sequence.
  Distinguish valid bounded reverse motion from missing body transport; preserve
  collision protection and the independent real-reverse authority guards.
- Improve actor prediction using only information available before each decision:
  original motion history, unique identity continuity and compatible directed
  road/prefab paths. Do not snap to an arbitrary exit or use future recorded
  positions as runtime intent. Branch ambiguity must remain explicit.
- Compare straight-ray, body-contact and map-supported candidate results on this
  captured trajectory. Test real crossing danger, lead braking, stationary and
  reversing ego, ambiguous/lost actor, source restart and stale data as negatives.
  An empty heuristic is not automatically clearance or permission to accelerate.
- Repair/attribute the missing AP continuation separately. Do not erase evidence
  gaps or label the current episode complete because its hashes pass.
- Run targeted/neighbor tests, not the entire pytest suite. Do not deploy or
  increase versions merely to publish an unproven change. Preserve current
  originals and use this incident before requesting another game capture.

## Requested cleanup

485 older generated replay/incident/AP/timing files (2,450,532,147 bytes) were
removed from route-diagnostics only after every archived entry was read back
and SHA-256 verified. Recoverable ZIP:
`docs/cleanup-archives/old-replays-20261102T200405188457Z/older-diagnostic-replays.zip`
(473,270,660 bytes), with per-file `manifest.json` alongside it.
All 27 protected files, including the current session and route metadata/locks,
were verified unchanged afterward. No current incident or runtime file deleted.
