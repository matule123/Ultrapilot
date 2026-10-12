# Automatic pedal evidence — 2026-10-07

**Thirty-second extension:** [PHASE7_PEDAL_HISTORY_20261007.md](PHASE7_PEDAL_HISTORY_20261007.md)
supersedes the short-history limitation below. The original detailed journal,
measurements and export-regression fixes remain unchanged. Ordinary startup
now also retains a separately bounded, sampled decision history in the same
automatic incident; combined arming is unnecessary for that history.

## Scope and verdict

**Offline capture/export contract verified; ETS2 input consumption NOT VERIFIED.**
Starting HEAD: `787d012a2a78ac917bb5506e0958c32d8d06575f`. Existing uncommitted
coast confirmation, directed signal scope, HUD and reproduction changes were
preserved. No applicable AGENTS.md was found in the checkout/ancestors. Plugin
version rules and the existing longitudinal evidence report were reviewed.
Only Autopilot advances, from the in-progress 1.2.3 to **1.3.0**, for this
backward-compatible diagnostic addition. Controller/SCS write semantics,
regulators, geometry, freshness deadlines and activation guards are unchanged.
No deployment, arming, game control, commit or push was performed.

## Proven missing evidence and change

| Before | After | Evidence |
| --- | --- | --- |
| PedalJournal enabled only for armed combined collection | Existing journal retained on ordinary startup; combined reads use a nondestructive sequence cursor | Initial unarmed capture reproduction failed; actual producer/Engine/Controller writes now appear without arming |
| Engine inputs did not reconstruct what Autopilot had actually consumed earlier | Original producer trace travels with the same immutable command, separately from Engine's later inputs | Earlier traffic frame and later emergency frame remain distinct through export/readback |
| Dense steering export did not accept a pedal incident | Existing schema-3 replay writer accepts an additive longitudinal block, hash and exact immutable references | Initial export reproduction failed on unsupported longitudinal argument; hash-checked readback now passes |
| Arming/draining could erase the retained boundary history | Combined cursor and automatic incident snapshot share immutable rows | Snapshot mutation isolation and nondestructive cursor tests pass |
| Failure could obscure last successful pedal values | Unknown current channel plus separate last-successful pair | Closed mapping test retains failure status and prior successful float32 value |
| Disk replay export was synchronous | Sealed replay rotation and one background export job, no pending queue | Deliberately blocked disk worker does not block control cancellation; concurrent request is explicitly counted as dropped |

No claim is made that these new fields retrospectively explain historical pedal
alternation. Original logs/collections were neither modified nor supplemented.

## Fields and binding

Public `longitudinal.events` is the same existing PedalJournal schema. Both
combined collections and automatic replay readback expose:

| Field | Exact meaning |
| --- | --- |
| `sequence`, `channel`, `requested_value` | Chronological physical dispatch sequence, channel and clamped Controller argument |
| `call_started_at_s`, `call_returned_at_s`, `call_returned`, `error` | Monotonic dispatch interval and return/exception; never game acceptance |
| `backend` | Existing mapping-write evidence: status, actual float32 payload, write/flush times and error |
| `pair_after` | Last known successful values; a failed channel becomes unknown (`null`) |
| `last_successful_pair_after` | Previous successful pair remains explicit despite a later failed write |
| `source.context`, `activation`, `decision_sequence` | Exact activation/session/map/dataset/intent/revision/build/publication token and Engine flush sequence |
| `source.sdk_frame_us`, `observation_timestamp`, `sdk_observation`, `observed_gear`, `actual_speed_mps` | Same captured Engine truck; original acquisition metadata and signed speed |
| `source.sdk_response` | Existing `gameThrottle`/`gameBrake`, null if absent; no added SDK reads |
| `source.requested` | Original received command, pedals, winner, reason, expiry and deadline provenance |
| `source.requested.producer_trace` | Autopilot's own earlier immutable inputs, brake-source requests, input failure, original truck frame/time/gear/speed, producer decision sequence and consumed EcoDrive packet when available |
| `source.inputs`, `limits`, `speed_ceiling_mps` | Later Engine-consumed inputs and limits; never substituted for the producer trace |
| Speed fields under consumed ACC | Requested, constrained and control-target km/h, speed-control reason; null/missing bitmap when unavailable |
| Signal under consumed traffic | Controlling ID, normalized color, actual pose/yaw if supplied, original producer time/frame/generation/lifecycle, relevance/rejection and directed passage/stop-target receipt if supplied |
| `display_detection` | Separate optional HUD-only detection, explicitly untimed; cannot authorize braking/restart |
| `source.selected`, `output_intent` | Arbitration result versus actual branch's final intended pair; individual writes remain authoritative for the submitted channels |
| `forward_history`, `forward_coast_confirmation`, `service_hold`, `launch`, `phase` | Bounded existing forward/coast/continuous-brake history and lifecycle; no inferred game consumption |
| `command_observation_pairing` | Actual initial/replacement snapshots and read/check times when the existing single reread occurs |
| `intervention`, `first_intervention` | Original first fault receipt and exact already-recorded rejected comparisons; cleanup cannot replace its reason |

Signal evidence comes from the qualified consumed traffic input, not a HUD
header. Missing authored passage or yaw stays missing. Reference-point ACC
gap/relative-speed/coverage fields are stored only when their producer supplied
them; no bumper gap, source observation time or confirmed target is invented.
Old replay headers are never used to reconstruct pedal provenance.

Original source packets remain immutable. Exact context/time/subtree references
are resolved only inside their owned snapshot or sealed export; differences
between old producer and current Engine inputs remain explicit. The internal
bounded node codec uses fixed fields, immutable subtree references and lossless
in-memory compression. Export expands it on the worker, then interns equal
values in that one file. Missing fields use the existing schema-1 bitmap or
explicit null/status; overflow is `UNVERIFIED`, not a fabricated zero.

## Automatic incident and limits

After these source files are deployed, ordinary startup needs **no arm command**.
The existing Engine PedalJournal is active without combined collection. An
already-created first control-fault receipt triggers one finite diagnostic tail
(up to 100 ms of existing writes, or cancellation/shutdown release). The tail
does not authorize or send any control. The existing replay writer emits:

`<UltraPilot app directory>/route-diagnostics/steering-replay-<UTC>-automatic_disable.json`

The longitudinal incident has `sample_kind=longitudinal_boundary_incident`.
The normal Autopilot dense steering replay may also have the same event suffix;
distinguish files by sample kind and actual identity/time, not filename alone.
The boundary incident itself contains retained pre-fault decisions/writes,
first fault, rejected comparisons and retained safe/release calls in one
hash-checked file. No mutable shared-state pointer is used. No file I/O runs
inside the control tick. Shutdown waits at most five seconds for the worker;
a process crash/forced kill or failed disk operation cannot guarantee export.

Unchanged journal limits: **128 events, 64 KiB conservative retained accounting,
32 KiB per source and the existing bounded intervention receipts**. Payload size
usually reaches the byte bound first. Duration is **not guaranteed**: in this
60 Hz/two-channel fixture only the last 20 events (~0.17 s) fit. This is a short
incident window, not a full-drive recorder. Source history still includes its
original forward/hold start receipts. Older writes cannot be reconstructed.
This original limitation is superseded for sampled decisions by the linked
thirty-second extension. Combined collection remains necessary for a longer
full-resolution physical-write/SDK history; a sampled summary cannot reconstruct
every older physical call.

Every eviction is counted by `dropped_events`; capture-budget failures and
`snapshot_incomplete` are recorded. The inspector labels such a file
`INCOMPLETE_BOUNDED_INCIDENT` even when hashes are valid. `confirmed=false`,
`runtime_authorized=false`, `game_consumption_verified=false` always remain.
There is one in-flight job and no waiting queue per existing exporter owner;
busy requests have an explicit dropped-request count/warning. No per-tick INFO.
Combined chunking/hashes/partial export remain unchanged. This implementation
does not promise an unbounded causal history or reconstruct unavailable data.

## Analysis and reproducibility

`tools/analyze_longitudinal_evidence.py` accepts the existing combined collection
or a new integrity-checked automatic incident file. It expands owned references
and preserves channel/write order, speeds/targets/pedals/intervention reasons,
failed writes and simultaneous-positive-pair counts. A bad hash/schema/order
is refused. A valid partial file remains incomplete, not a successful drive.

Acceleration uses original increasing SDK frames with the same identity and
phase and gaps <=500 ms: delta signed speed / delta observation time, located
at the interval midpoint. Jerk is delta interval acceleration / midpoint-time
delta. Duplicate observations are not extra dynamics samples. Raw derivative
noise can dominate. A later SDK frame within the matching identity/window is
only a subsequent-response candidate, not proof of game consumption or causality.

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python tools/benchmark_automatic_longitudinal.py --output docs/steering-audit/automatic-longitudinal-overhead-20261007-final.json
python tools/analyze_longitudinal_evidence.py '<automatic incident JSON>' --output docs/steering-audit/pedal-incident-analysis.json
```

Large generated evidence/benchmark JSON stays ignored outside tracked reports.

## Measured overhead

Same fixture/model: six seconds, 360 Engine/SDK steps at 60 Hz, 120 producer
steps at 20 Hz, unarmed combined, copying IPC stand-in, real Controller and
BytesIO mapping. Plain simulated clock avoids counting unittest Mock's growing
call history as runtime memory. Backend test-history storage is excluded from
heap measurement; existing replay/PID data are included. Timing and traced
heap are separate runs; heap is retained after GC plus peak before GC.

| Measurement | Diagnostic off | Diagnostic on |
| --- | ---: | ---: |
| Engine median / p95 / p99 / max, ms | 0.3783 / 0.4412 / 0.5206 / 1.3168 | 1.1564 / 1.8397 / 4.2767 / 4.6947 |
| Autopilot median / p95 / p99 / max, ms | 0.2519 / 0.2988 / 0.3265 / 0.5646 | 0.4339 / 0.6719 / 1.5804 / 1.7385 |
| Retained traced heap, bytes | 846030 | 893600 |
| Peak traced heap, bytes | 877185 | 1128431 |

Median increments: Engine **0.7781 ms**, Autopilot **0.1820 ms**. Retained
heap difference **47570 bytes (46.46 KiB)**; peak difference 251246 bytes
(245.36 KiB), including temporary codec/copy allocations. Journal reserved
maximum 64631 bytes; 20 events remained, 710 earlier calls explicitly dropped.
These are operation/fixture measurements, not live end-to-end IPC/game latency
or a worst-case scheduling guarantee. Actual physical channel/value sequences
and Engine IPC-read counts are identical with diagnostics on/off.

## Validation

Initial narrow reproductions: **3 failed before implementation** (unarmed
retention, pedal replay support and snapshot/cursor contract). New automatic
evidence tests cover both transmission modes, failed mapping and last success,
immutable snapshots/producer versus later Engine frame, first fault through
safety/release, blocked export, full-length identities and original signal
fields, corruption/drop reporting, analyzer order and observation timestamps,
and diagnostic failure without changed physical control. Existing combined
roundtrip includes actual prepared prefab passage receipts and green restart.

Final targeted run: **192 passed in 26.32 s** across automatic longitudinal
replay, combined longitudinal evidence, Oct-7 command/observation pairing,
Oct-4 signal lifecycle, steering replay, coast/signal scope, prefab signal
binding, activation observation binding and longitudinal arbitration. The 14
new automatic evidence tests pass. `compileall` over core/plugins/sdk/tools/
tests/ui and `git diff --check` pass. No full pytest suite was run. The same-input
diagnostic on/off benchmark confirms identical recorded physical pedal controls
and identical Engine IPC-read counts. Steering packet/regulator code is untouched;
the listed steering/activation regressions pass. No live evidence has yet been
produced by this diagnostic extension.

## Files changed by this extension

- `core/engine.py`: reuse local consumed snapshots, nondestructive combined
  journal cursor, first-fault/tail export on the existing replay worker.
- `core/longitudinal.py`: attach bounded producer evidence to the same command.
- `core/navigation/longitudinal_diagnostics.py`: immutable input deltas/codec,
  missing fields, last successful pair and nondestructive snapshots.
- `core/sdk/signal_snapshot.py`: additive compact diagnostic head position/yaw.
- `core/steering_replay.py`: additive hash-checked pedal incidents and one-job
  asynchronous export/readback; unchanged controller packet validity.
- `plugins/autopilot/main.py`: exact consumed producer inputs and first fault,
  asynchronous sealed replay; VERSION 1.3.0.
- `tools/analyze_longitudinal_evidence.py`: same analyzer reads incident files
  as well as combined collections, with original observations and write order.
- `tools/benchmark_automatic_longitudinal.py`: same-input timing/heap comparison.
- `tests/test_automatic_longitudinal_replay.py`: 14 narrow integration regressions.
- `PHASE7_LONGITUDINAL_DIAGNOSTICS.md`, this report and `PLUGIN_CHANGELOG.md`:
  additive contract, measurements, version and limitations.

Prior coast/transmission/HUD changes and their tests/report remain in the
working tree; they are not new controller changes made by this extension.
