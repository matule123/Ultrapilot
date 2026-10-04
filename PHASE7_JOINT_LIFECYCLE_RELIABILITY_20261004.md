# Joint longitudinal lifecycle reliability

Date: 2026-10-04. Baseline: `cf25a97508aa1dfe4eb0917c5d6857583e45d87a`
plus the working changes described below. No commit, push, installation, collection
arm, game launch or game control. Original logs and collections are unchanged.
No AGENTS.md was found at repository/ancestor locations. Plugin version rules,
Phase 7 reports and deferred work were reviewed. The full pytest suite belongs
to the user and was not run.

**Offline verdict: reproduced input-lease and launch/braking transitions repaired.
Autonomous activation/holding from an already stationary simple-automatic truck
remains BLOCKED. New runtime behavior is NOT VERIFIED in ETS2.** A driver-held
pending request must not be described as the requested immediately active,
self-holding “Čakám na zelenú” state.

## Build and evidence identity

Read-only comparisons cover Engine, Map, Autopilot, longitudinal arbitration,
service-brake witness, transmission helpers, Controller/SCS writer, ACC,
DrivePolicy, combined collector and pedal journal. Installed contents match
the baseline after CRLF/LF normalization. At entry Engine and longitudinal
components were byte-identical; Map/Autopilot differed only in newline encoding.
After this task Engine, Map and Dynamic Island differ in code from installation;
unchanged Autopilot still differs only in newline encoding. `commit.txt` was not
used as proof. Full hashes are in the local source-identity receipt below.

Current declarations: Map **1.0.5** (from 1.0.4); Autopilot 1.2.0, ACC 1.1.1,
DrivePolicy 1.0.3 unchanged. Core/UI corrections do not release unaffected plugins.
Read-only game-plugin hash: `ets2la_plugin.dll`
`53D8C54D2B71ABB2F1D2DE8CB68CD096F22F8385F750F46CE07AF105295C3BCF`.
It matches the existing signal-sidecar candidate bytes; that alone does not prove
live acquisition correctness or SCS input consumption.

Primary incident attachment:
`C:\Users\PC\.codex\attachments\70a9f0d8-5c2c-4aa1-999c-b3508136be23\Vložený text.txt`.
Related replay names in the installed `route-diagnostics`:

- `steering-replay-20261004T161417.501397Z-automatic_disable.json`;
- `steering-replay-20261004T161429.625663Z-automatic_disable.json`;
- `steering-replay-20261004T161504.852702Z-automatic_disable.json`;
- `steering-timing-20261004T161529.194581Z-plugin_stop.json`.

Binding: session 1, map `promods-1.59`, dataset `d6cc7936fce4e902761abb5d`,
intent `58e0572a48094276b8eccdded87f5c03`, revision 8,
build `da98ccd9330f4947a10752a9385c836b`, geometry token
`lane_path3a4837076e8936de35b2e622249436ecd264bad85d196e37608d069e76d34198`.
Activation request/epoch changes between attempts and is not inferred from build.
Local log time is UTC+2; runtime comparisons use the original monotonic seconds.

## Causal reconstruction

| Event | Measured evidence | Conclusion / limitation |
| --- | --- | --- |
| 18:13:50, boundary 21 → 22 | Probe throttle 0.12 at 5651.2040474; cancellation at 5651.2430758, `traffic braking forbids launch` | Propulsion preceded the traffic rejection by 39.0284 ms. The existing source-check ordering is wrong; no stop-line distance is proven. |
| 18:14:16, activation 5674245479600 | ACC-derived selected command: frame 111712198, observation 5677.5213668, computation 5677.5606533, expiry 5677.5774154, checked 5677.5783973 | Observation age 57.0305 ms; decision age 17.7440 ms; inherited lease exceeded by 0.9819 ms. All compared identity fields match. |
| 18:14:29, activation 5686169337700 | Zero-ratio rejection, SDK 124545018, observation 5690.4327871; subsequent Engine observation speed −0.072845183 m/s | Not continuing forward motion. Historical final brake writes are absent: a valid continuous hold and a red-generated brake cannot be claimed retrospectively. |
| 18:15:03, activation 5717550576900 | AP command: frame 158277002, observation 5724.3295753, computation 5724.3844198, expiry 5724.3862163, checked 5724.4016594 | Observation age 72.0841 ms; decision age 17.2396 ms; inherited lease exceeded by 15.4431 ms. All compared identity fields match. |

The last two expirations do not demonstrate lost SDK telemetry. They are actual
expired *input leases* despite a newer valid vehicle observation. The final
Engine check correctly refuses them. The first failing comparison is retained;
later token cleanup does not supply an alternative cause.

The rejected snapshots do not include every original road/policy/ACC producer
packet. Their expiry cannot retrospectively be assigned to a recorded road field
with certainty. The code defect below is independently reproduced through real
production operations, with the exact observed age/overrun budgets. This is
stronger than attributing history to a nearby red light, but is not a claim that
all past/future expirations have the same cause.

## Repairs and unchanged contracts

### Source-observation lease

Map originally classified/published the road cap from the initial SDK pose,
before expensive reference preparation. Steering subsequently acquired a real
new SDK pose, but the road packet retained its earlier expiry. DrivePolicy,
ACC and Autopilot propagate the minimum consumed expiry; a fresh AP observation
therefore inherited a nearly exhausted road-input lease. This is not fixed by
retimestamping the old cap or enlarging the 500 ms limit.

Map now classifies the road at the actual post-preparation steering pose and
publishes with that pose's original frame/time. The old classification is reused
only for the identical position and RoadNetwork object. A changed position calls
the existing classifier. This operation follows steering publication and its
completion receipt; it cannot delay that packet's delivery. Road-cap values,
geometry, calibration, controller and original expiry propagation remain intact.
Live cost on the full ProMods network and future OS scheduling stalls are not
certified by the small operation benchmark.

| Handoff | Expiry rule |
| --- | --- |
| Map road classification | Actual classified pose observation + 500 ms, original SDK frame |
| DrivePolicy | Minimum of its observation and consumed road/traffic/curve leases |
| ACC | Minimum of its observation and consumed road/policy/traffic/curve leases |
| Autopilot | Minimum of its observation, chosen request and consumed speed limits |
| Engine arbitration / final physical write | Recheck original times, activation and full context after reads and immediately before write |

No downstream consumer extends a source lease by rereading. Missing/stale inputs
and changed identities continue to reject. Repeated old frames are not new data.

### Launch, planned braking and waiting

The physical owner checks current producer-timed red and accepted longitudinal
restrictions before the first probe, including when a forward ratio is already
engaged at standstill. It locks the same signal head/session/route while waiting.
No creeping toward a light is authorized without a demonstrated stop location.

A confirmed moving launch encountering an accepted ordinary planned-stop demand
now transfers to the existing arbitration/brake path without `release_all`.
The actual positive brake write can establish the current activation's forward-
started witness; a later gear=0 at rest uses that witness, rather than failing the
forward-motion rule before the hold is established. Brake stays positive and
throttle zero. This is the same state machine, not a second regulator.

Supported active waiting is `planned_wait`, displayed as **“Čakám na zelenú”**
when the locked signal is not green; it does not turn on technical-stop hazards.
Two genuinely new green acquisitions at least 100 ms apart, same lifecycle/head/
authority, and clearance of all other reasons permit brake release followed by
the existing bounded mode-specific restart. Head disappearance, old green,
unknown color, another latched stop or a newer direct red cannot authorize drive.
Manual cancellation, R/backward motion, broken brake chain, stale data, changed
identity or backend failure remain terminal safety branches. No parking-brake
control was added. Launch/handoff deadlines are not repeatedly renewed.

### Exact stationary-activation blocker

An already stationary simple-automatic truck has no current forward-started
software brake chain. `Controller.set_brake` writes the mixed `abackward` input;
there is no separate acknowledged service-only stationary hold that bypasses
Reverse selection. `gear` is an engaged ratio, not a selector acknowledgement.
The user's manual-pedal observation supports continuous braking from motion,
not a new SDK brake edge at rest. A returned mapping write does not prove
uninterrupted DLL/game consumption, ownership of a driver's mixed brake input,
or holding on a slope.

Consequently the new stationary request remains **pending**, not AP-active,
with zero SDK throttle/brake/selector and an explicit driver-hold instruction.
It can retain one N through valid red observations and use fresh confirmed green
for the existing bounded launch, but zero outputs do not hold a slope. It does
**not** implement the latest requested autonomous stationary activation. A prior
positive receipt from another activation cannot seed the missing witness.
Mode-3 tests also exercise this conservative pending path; they do not imply
that a new stationary hold was implemented there.

The single missing capability/proof is **a non-parking service-brake holding
transition from standstill through this exact SDK/backend that cannot select R,
with observable ownership/continuity**. No new pulse, invented timestamp, parking
toggle or cosmetic `autopilot_active=True` is used to conceal this gap. No extra
drive is requested to guess its semantics.

## Reproductions, metrics and validation

`tests/test_joint_activation_reliability.py` uses actual Map publication for lease
reproduction, real DrivePolicy/ACC/AP, Engine hotkey/flush, Controller and a
chronological float32 memory backend. Lifecycle fixtures use the existing versioned
signal reader/route selector with explicit generated acquisitions. SDK vehicle
motion and the user-observed gearbox semantics are declared test inputs/model;
they are not measured ETS2 effects.

The baseline Map methods were loaded from Git in an isolated test process without
overwriting source. Both recorded-budget reproductions wrote physical throttle
**0.0** and recorded a technical intervention before correction. They pass with
the refreshed, genuinely reclassified source. First red/probe and moving handoff
reproductions also failed before their correction; the original failing six-case
run is distinct from later sandbox permission errors.

| Same offline timeline | Baseline remaining lease at write | Corrected remaining lease at write | Physical result |
| --- | ---: | ---: | --- |
| First incident budget: Map refresh +354.5584 ms, newer AP vehicle observation +89.3930 ms, computation +39.2865 ms, write +17.7440 ms | −0.9819 ms | **353.5765 ms** | Before throttle 0 / technical stop; after current accepted propulsion, no brake |
| Third incident budget: Map refresh +53.0612 ms, newer AP vehicle observation +390.2978 ms, computation +54.8445 ms, write +17.2396 ms | −15.4431 ms | **37.6181 ms** | Before throttle 0 / technical stop; after current accepted propulsion, no brake |
| Separate slow preparation, 369 / 443.9514 ms, changed real pose | Old-frame road cap | Original time/frame of new actual pose, full 500 ms at immediate publication | No fake timestamp; old/stale source still refused |
| First N with red, both modes | Probe then braking rejection | No positive pedal/selector write, explicit driver-held pending state | Autonomous standstill holding **BLOCKED** |
| Moving confirmed launch → early planned brake → zero ratio | Launch cancellation before ordinary brake ownership | Continuous actual brake chain and active planned wait | Red → two fresh greens → bounded restart, same activation |
| Three consecutive active red/wait/green/restart cycles, both modes / either Engine tick order | Conflicting launch/hold edge | Existing joint production flow continues | No extra N, parking write, concurrent positive pedals or technical hazards |

Remaining-lease values are deterministic reproduction measurements, not a new
live timing result. In particular the third scenario has only 37.6181 ms left;
this repair does not promise unlimited scheduling slack or acceptance of actually
expired commands. At +501 ms old observations/constraints still reject and power
is removed. No expired command is rebranded with a later identity.

Validation:

- 394 targeted tests across 15 lifecycle, longitudinal, steering-freshness and
  evidence modules passed. After the detailed timing split, stationary-limit
  assertions and active-wait label change, the affected reliability/lifecycle/
  signal selection was rerun: **75 passed**, including all 18 reliability cases.
- Sandbox run hit Windows `PermissionError` on pytest temporary paths/cleanup;
  the same targeted selection passed outside the sandbox with a distinct temp
  directory. This was not treated as a product/test assertion failure.
- Steering benchmark: **16 cases, zero numeric differences against HEAD**.
- Longitudinal comfort benchmark: **12 cases, zero numeric differences against
  HEAD**; modeled emergency response remains 0.0 s. This benchmark does not
  certify gearbox or hill-hold effects.
- IPC operation benchmark, 150 samples: Manager combined median 3.5712 ms,
  p95 4.3616 ms, p99 4.7984 ms, maximum 5.1118 ms. These are publication/
  arbitration costs, not live end-to-end cadence or lock-wait measurements.
- Actual classifier/publication on the two-road synthetic network, 500 samples:
  identical-pose reuse median 0.0051 ms / p95 0.0068 ms; changed-pose query median
  0.0104 ms / p95 0.0131 ms, maximum 0.0377 ms. Direct dictionary transport;
  no extrapolation to the full live map.
- Existing combined roundtrip covers original SDK frame/time/context, selected
  brake source, actual ordered writes, holding/restart phases, immutable packet
  provenance, chunk/hash integrity and `game_consumption_verified=false`.
  No second collector, raw-log flood or enlarged memory limit was added.
- `compileall` (core, plugins, SDK, UI, tests, tools) and `git diff --check`: **PASS**.

Local ignored receipts under `docs/steering-audit/`:
`joint-reliability-source-identity-20261004.json`,
`joint-reliability-steering-{before,after}-20261004.json`,
`joint-reliability-comfort-{before,after}-20261004.json`,
`joint-reliability-longitudinal-cost-20261004.json`,
`joint-reliability-road-cost-20261004.json`.

## Subsequent single controlled verification (prepared, not requested or armed)

Prerequisites: user full-suite PASS and separate deployment approval with backup/
hash verification. The installation currently contains baseline runtime files.
Use the existing combined collector; never arm it as part of this repair task.

For the supported continuous-stop cycle: on a clear level road, valid directed
GPS route and fresh unique relevant producer-timed signal, driver stays ready to
take over. With no parking brake and no manual throttle, one N on a permissive
approach → bounded automatic launch → stable driving → natural red → continuous
service braking → active “Čakám na zelenú” → naturally confirmed green → coordinated
release/restart without another N. Do not manufacture emergency traffic or use
an ambiguous junction to establish clearance. One collection can capture the
cycle and repeated wait/restart, if they naturally occur.

STOP immediately for R, backward/rolling motion, inability to hold, lost identity,
stale/invalid command, backend failure, unexpected pedal/selector edge, technical
hazards during ordinary waiting or need for manual intervention. Driver takes
over; no automatic recovery after a technical stop. End/export/inspect before
application shutdown, using the existing documented combined procedure.

Required evidence: activation token, full session/map/dataset/intent/revision/
build/geometry context, original SDK frames/times and signed speed/gear; locked
signal ID/lifecycle/generation/color/original acquisition time; each producer's
expiry and winning source; launch/hold/resume state; ordered brake/throttle writes
and return status; later SDK response. A write return is not game consumption.

**Do not use this procedure to claim or test unsupported self-holding activation
from an already stationary simple-automatic truck.** That remains the concrete
blocker described above, not an invitation to repeat a whole route.

## Changed files / proposed commit

Runtime: `core/engine.py`, `plugins/map/main.py`, `ui/dynamic_island.py`.
Tests: `tests/test_oct4_signal_lifecycle.py`,
`tests/test_joint_activation_reliability.py`.
Documentation: this report, `DEFERRED_WORK.md`, `PLUGIN_CHANGELOG.md`.

Suggested title: `fix: refresh road input leases and preserve planned-stop handoff`.
Description: Reclassify longitudinal road limits from the real post-preparation
SDK pose; reject red-light propulsion before launch and transfer valid moving
handoff into continuous service braking. Preserve source expiry and all safety
checks; explicitly retain the unsupported stationary self-hold boundary.

Full suite, for the user:

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python -m pytest tests -q
```
