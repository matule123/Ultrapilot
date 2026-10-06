# Phase 7 — joint braking, zero-ratio and traffic repairs

Date: 2026-10-06. Input HEAD: `77f7e31bb4d175cbe8a341f8097d54f263be456e`
(initially clean). No `AGENTS.md` was found in the checkout or its ancestors.
Plugin version rules, the current diff and preceding Phase 7 reports were read.

**Verdict: reproduced production defects repaired and verified offline.
The historical SDK interruption and collision are not fully explained.
Safe autonomous roundabout gap acceptance remains NOT VERIFIED, not fixed.**

No installation, commit, push, diagnostic arming or game operation occurred.
The original installed logs and collections were retained. The full pytest
suite is reserved for the user. This report does not close Phase 7 in ETS2.

## Build and evidence binding

Read-only comparison of 13 installed runtime files against the input HEAD
confirmed content equality after LF/CRLF normalization: Engine, transmission,
service hold, longitudinal contracts, telemetry, SCS SDK reader, signal reader,
Controller, ETS2LA reader, Map, ACC, Autopilot and DrivePolicy. Line endings are
not treated as code changes. Git-object bytes also matched the installed bytes
on the final read-only check. The working candidate now intentionally differs;
`commit.txt` was not used as proof of deployment.
The reused `core/sdk/vehicle_observation.py` decoder was also checked separately
against the installed content and matched after normalization.

The October 6 session is bound by:

| Field | Recorded value |
| --- | --- |
| Game session | `1` |
| Map / dataset | `promods-1.59` / `d6cc7936fce4e902761abb5d` |
| Navigation intent | `a8aa825fb9cc4e34b11d1008d8c5080e` |
| Revision / build | `10` / `430ff532edaa497f88fcdf6a147d33c7` |
| Geometry fingerprint | `4dc8f9b8f91966ec606d55a365cddff47719897c0fcd50ce7d8f91bc2c47400d` |

Artifacts are under the installed `route-diagnostics` directory:

| Artifact | Rows | SHA-256 |
| --- | --- | --- |
| `steering-replay-20261006T172619.199972Z-manual_disable.json` | 803 samples; 10,800 execution rows | `9c79adf2748cabda83c28c3efb029203280102ee008924d093c9b52a195f2173` |
| `steering-replay-20261006T172634.632597Z-automatic_disable.json` | 287 samples; 839 execution rows | `22074bbd884b370ac16fb8b77d0436e71e46f9e9a37033d97892e2e4a3ee4639` |
| `steering-replay-20261006T172654.355970Z-automatic_disable.json` | 228 samples; 1,144 execution rows | `32c1b2ee1eba787fafe8d4767b9cd55b7da0391a8667128f3b5a925e774b3490` |
| `steering-timing-20261006T172708.840212Z-plugin_stop.json` | 2,218 sampled reads | `d6362139e3e1b39527a65e24365f83e27a90f836ce2b27bcfcb86c85925e5fde` |

There is no October 6 combined collection containing the missing pedal/actor
history. These replay execution rows lack immutable `source_packet` binding;
they cannot establish historical throttle/brake edges, gear or actor identity.
Unbound replay headers are not substituted for that evidence.

## Recorded chronology

Wall clock below is local; all numerical ages use the recorded monotonic
clock. The full log was filtered by October 6, not merely by time of day.

| Local time | Recorded event | Interpretation |
| --- | --- | --- |
| 19:25:42.739 | N; simple-auto probe, throttle 0.12, gear 0 | Existing automatic launch used, no manual throttle proof required for this logged command |
| 19:25:43.176 | Handoff; frame 171043158, gear 4; SDK age 45.99 ms | Confirmed ratio and software handoff; backend return alone is not game consumption |
| 19:25:54.837–19:25:55.387 | Obstacle state entered then returned to cruise | Does not identify both roundabout vehicles or certify a clear gap |
| 19:26:18.918 | Manual N disable | Separate from later automatic faults |
| 19:26:21.143–21.514 | N, probe, gear 4, handoff | Next activation |
| 19:26:34.591 | First intervention from Autopilot at 16837.4370967; frame 222507766, observation 16837.4257061 | Zero-ratio history rejected with an 11.39 ms old observation; not stale SDK |
| 19:26:34.598 vicinity | Engine boundary: frame 222441102, gear 0, speed +0.5424093604 m/s, observation 16837.3728552 | Different fresh boundary frame; do not claim it is the Plugin's same snapshot |
| 19:26:43.239–43.631 | N, probe, gear 4, handoff | Third activation |
| 19:26:49.114 | Continuous planned service-brake hold logged | Software hold evidence; original brake source not recoverable from these rows |
| 19:26:54.315 | First Autopilot fault at 16857.1640084: stale Map heartbeat | Last SDK/steering frame had stopped advancing |
| 19:26:54.325 | Engine sees `telemetry_valid=false`, frame 0 | Failure publication, not a real SDK frame numbered zero |
| 19:26:54.338 | Automatic disable | First heartbeat reason retained |

The later `UNSUPPORTED_SDK_ABI` message is not proof of what interrupted the
earlier frame. There is no later recorded N in the inspected green/reactivation
window; the observation that the truck stayed stationary cannot be attributed
to an accepted subsequent activation.

## Concrete causes, changes and counterexamples

| Problem | Proven code defect | Implemented change | Before / after |
| --- | --- | --- | --- |
| Fresh gear 0 during first planned braking | Both gates could reject before the first brake receipt because Engine's last committed positive-ratio confirmation was older than 500 ms | One shared rule admits a bounded **brake-only** transition from same-activation forward history, fresh positive forward motion and valid identified stop input. Plugin and Engine both forbid propulsion in it. The actual first brake write seeds the existing continuous hold | Original gate disables with the exact incident reason; candidate reaches positive brake, then stationary hold, without hazards or a new N |
| Existing hold rejected by old zero window | The expired transitional zero deadline was checked before the current acknowledged brake chain | Validate the current activation/route-bound hold before the obsolete transition deadline; no deadline renewal for unacknowledged zero-ratio driving | Original disables; candidate continues the real positive brake chain |
| Stop color flicker / restart blocked after yellow | A stop begun on yellow did not lock its valid signal head, unlike a red-started stop | Lock red **or yellow** when the acknowledged stop begins. Preserve the existing same-head, passage, lifecycle and two-new-green-acquisition clearance checks | Original hold has no signal lock; candidate retains brake through an isolated green/red flicker and supports the existing qualified resume |
| Missed later crossing vehicle on a directed turn | Legacy ahead-axis/straight-velocity gate misses an observed actor which crosses a future turn rather than the current heading ray | Test all valid captured actors against bounded directed XYZ reference edges; preserve the strongest existing brake demand. These are protective heuristic candidates only | Original production path writes positive throttle in the reproduction; candidate writes zero throttle and positive brake before/after removing the first actor and after reordering |
| Mixed SDK control fields | Independent live field reads could combine an old frame with newer gear/speed; a partial decode could return a nonempty incomplete dictionary | Decode one immutable byte image after bounded equal-copy checks; reject the whole incomplete/nonfinite image. Preserve acquisition time through publication | Original reproduction returns frame 100 with later fields, and accepts partial input; candidate returns frame 200 with its own fields or rejects the whole read |
| Transient overlapping read erases valid telemetry | Detected read failure could replace the last accepted observation with a synthetic loss immediately | Only the specific detected-copy-change failure may retain the previously accepted sample with its **original age**, up to the unchanged 500 ms limit. Missing/invalid reads, pause/inactive game and true expiry still revoke authority | Original publishes frame 0 during a short overlap; candidate retains the original frame/time and revokes it at real expiry |

The common brake-only transition has a fixed first-zero bound, is not extended
by polling, and never permits an arbitrary neutral throttle. Invalid stop
values, expired stop evidence, wrong identity, R and backward motion fail closed.
An actual returned positive brake receipt must establish the holding chain.

The five historical pedal alternations are a user observation. Without paired
pedal receipts and signal acquisitions their exact cause is NOT VERIFIED. The
yellow-start/flicker defect is reproduced in production components, not claimed
as the uniquely established historical explanation for all five alternations.

## Heartbeat and SDK evidence

The last advancing packet is calculation sequence 2327, SDK frame 241673666.
Its original SDK observation is 16856.649146. The recorded Map tick is:

| Phase | Monotonic time | Duration from preceding phase |
| --- | --- | --- |
| Tick starts | 16856.6536714 | — |
| Lane update ends | 16856.6678945 | 14.2231 ms |
| Presentation ends | 16856.6680327 | 0.1382 ms |
| Road type ends | 16856.6704950 | 2.4623 ms |
| Reference ends | 16856.6768030 | 6.3080 ms |
| Controller begins | 16856.6768275 | 0.0245 ms |
| Calculation ends | 16856.6778246 | 0.9971 ms |
| Publication starts | 16856.6804099 | 2.5853 ms |
| Publication completes | 16856.6807348 | 0.3249 ms |
| First retained sampled Autopilot read | 16856.7507393 | 70.0045 ms after publication |

Total tick-to-publication: **27.0634 ms**. Observation-to-calculation-start:
**27.6815 ms**. Calculation-to-publication-complete: **2.9102 ms**.
The sampled read is not proof of first delivery. At the first fault, the last
observation is **514.8624 ms** old and publication completion is 483.2736 ms ago.
Publication completion is not substituted for the separate heartbeat field.
The replay repeats the last SDK frame without advancement across the gap.

This does **not** demonstrate a blocking Map operation. The exact reason the
upstream frame stopped advancing is not preserved: contemporaneous raw
`sdkActive`, `pause` and SDK read-failure status are missing. No timeout was
raised and no heartbeat/timestamp was manufactured. A genuine frozen SDK must
still stop the autopilot. Equal byte copies detect overlap but do not provide
atomic publisher proof; the legacy SCS ABI has no seqlock. Trailer/job reads are
not newly certified as atomic with the truck control image.

## Crossing contract and limits

The existing buffer provides actor ID, XYZ, yaw, scalar speed and raw dimension
fields. It has no producer timestamp/generation, complete coverage guarantee,
verified lane membership or certified full-body outline. Receiver capture time
remains explicitly separate from unknown producer time.

The new protective calculation uses the existing local directed reference,
at most 80 actors and 512 edges within 120 m; linear actor motion up to 8 s;
a nominal ego-arrival window assuming 0–2 m/s²; the existing 2 s ACC reserve;
and raw length only when finite and positive. These are stated assumptions,
not a calibrated physics bound or measured bumper clearance. Parallel directed
lead candidates remain in ACC; known other elevations, invalid/ambiguous data
and unsupported dense references are not certified as crossing/clearance.

All actors affect selection. The existing bounded journal receives at most 16
listed IDs, total/omitted counts and the decisive candidate. Existing emergency
braking cannot be weakened. All results keep `clearance_confirmed=false`,
`coverage_confirmed=false` and unknown producer time. Removing the first actor
does not authorize entry or release a latched traffic stop. A traffic stop with
unconfirmed clearance still blocks automatic resume even if a light turns green.

**The collision-prevention claim remains blocked by producer freshness,
coverage and conflict-history evidence.** No DLL/sensor/parser was added.
Stationary activation at red without an acknowledged forward-started service
brake remains the previously documented holding limitation; no new stationary
brake edge or parking-brake control is introduced.

## Offline verification and performance

`tools/reproduce_oct6_joint_flow.py` compiles the selected original modules from
Git in memory, preserving both checkouts and the installation. Fixtures use the
real Controller/SCSControls writer with byte buffers, not the game's mapping.
The synthetic SDK motion/brake model is not proof of ETS2 input consumption.

The new regressions include actual RoadNetwork/Map parsing and publication,
DrivePolicy, ACC, Autopilot, Engine and chronological physical mapping writes.
Three red–hold–qualified-green–launch cycles preserve the activation without
another N, throttle during waiting, a brake-zero edge during holding, parking
brake writes or ordinary-wait hazards. Tests also cover an independently delayed
first Engine brake, wrong identity, R/backward motion, stale input, malformed SDK
images, actual loss/pause, and existing manual/backend/emergency refusals.

| Verification | Result |
| --- | --- |
| Initial original-module reproduction (18-case version) | 12 failed, 6 passed; includes exact zero-ratio reason and positive-throttle crossing counterexample |
| Final original-module reproduction (30 cases) | 24 failed, 6 passed; some failures deliberately identify absent new contracts rather than additional historical incidents |
| New candidate regressions plus narrow export retry | 31 passed (30 new cases and the export case) |
| Broader affected regression matrix before the final attribution/test additions | 528 passed, 70 subtests passed |
| Final traffic/SDK/combined-export matrix after all attribution assertions | 118 passed; includes all 30 new cases and full JSON-wire brake-source attribution |
| Steering benchmark | All 16 cases and the independent matrix exactly equal to input HEAD |
| Longitudinal comfort benchmark | All 12 cases exactly equal; emergency reaction remains 0 s in the model |
| Independent-cadence handoff benchmark | Six 75 s cases, diagnostics on/off, identical baseline/candidate outputs; no faults or expired physical writes |

One subsequent export attempt returned `DIAGNOSTIC_EXPORT_WRITE_FAILED`; the
sandbox separately denied access to its test directory. The isolated export
retry passed. Earlier sandbox `PermissionError`/WinError 5 failures are
environmental access results, not evidence that a safety assertion passed or
failed. No collector invariant or test expectation was relaxed.
The full attribution equality uses the actual JSON-wire contract (dimension
tuples become arrays), without omitting fields or substituting a later packet.
`compileall` and `git diff --check` pass. No full-suite run was performed.

Handoff cadence model uses SDK 33.3 ms, Map 360 ms, traffic 460 ms, policy 59 ms,
ACC 23 ms, Autopilot 26 ms, Engine 16.7 ms, no catch-up and copying RPC:

| Phase offset / RPC cost | Physical writes, per diagnostic setting | Minimum remaining validity at write | Maximum observation age at write |
| --- | --- | --- | --- |
| 0 / 0.06 ms | 3,093 | 34.1667 ms | 69.3333 ms |
| 3 / 0.12 ms | 1,804 | 40.5200 ms | 49.3200 ms |
| 7 / 0.20 ms | 1,211 | 2.6000 ms | 72.8000 ms |

Operation microbenchmark, same 500 SDK images: baseline median/p95/max
0.1054/0.2075/0.3889 ms; candidate 0.1083/0.2100/0.5175 ms. Protective crossing
stress (80 actors, 240 edges, 100 runs): 8.7639/9.5318/10.3798 ms. This is a
bounded traffic operation, not an end-to-end Map/steering cadence measurement.
The lateral controller, geometry, scheduler and 500 ms checks are unchanged.

Ignored local benchmark receipts are `docs/steering-audit/oct6-{steering,
comfort}-{baseline,candidate}.json`, `oct6-handoff.json`,
`oct6-operation-cost.json` and `oct6-install-audit.json`. Large original data
remain outside Git. Reproduction commands use `PYTHONCASEOK=1`:

```powershell
python tools/reproduce_oct6_joint_flow.py --baseline-ref 77f7e31 --basetemp docs/steering-audit/oct6-original-reproduction-new
python tools/reproduce_oct6_joint_flow.py --basetemp docs/steering-audit/oct6-candidate-reproduction-new
```

## Versions, runtime scope and remaining confirmation

Only Autopilot changes plugin behavior: **1.2.1 → 1.2.2**. ACC remains 1.1.4,
Map 1.1.0 and DrivePolicy 1.1.0. Core fixes do not release unchanged plugins.

Coordinated runtime scope: `core/acc_following.py`, `core/engine.py`,
`core/longitudinal.py`, `core/sdk/scs_sdk.py`, `core/service_brake_hold.py`,
`core/telemetry.py`, `core/transmission_mode.py`, `plugins/autopilot/main.py`.
No new DLL or configuration change is required. Test/tool/document files are
not runtime deployment files. Nothing has been deployed.

After the user's full suite and separately authorized consistent deployment,
remaining game confirmation is one supported forward-started red stop, continuous
brake waiting and same-head qualified green resume, with the existing combined
receipt export. It must show actual SDK gear/motion response, intact brake chain,
matching activation/route identity and fresh frame cadence. It must not be used
to provoke crossing traffic, collision or a stationary neutral re-press. This
task does not request another ride. The existing producer/coverage limitations
must be resolved before claiming reliable autonomous roundabout gap acceptance.
