# Phase 7 — Combined longitudinal evidence

Date: 2026-10-03. Baseline HEAD: `0107430d57b2c96881ee39c9a27eccd2ea1ecf19`.
These are uncommitted source changes, not an installed or game-tested build.
The tracked working tree was clean at entry. No AGENTS.md was present in the
repository, its inspected parent directories, or the affected source directories.
Reviewed Phase 7 final results, deferred work and plugin-version rules.

**Result: PASS for the tested offline capture/export contracts.** The existing
combined collector can now preserve longitudinal decisions and SCS mapping
write evidence. ETS2 comfort, input consumption and reliable ACC remain
**NOT VERIFIED**. This work does not authorize a drive or arm a collection.

## 1. Actual data flow and scope

| Stage | Existing producer/consumer | New observation |
| --- | --- | --- |
| Speed demand/constraints | ACC target and PID; road/policy limits; traffic following candidate | Exact bounded producer packets consumed by Engine, including original observation times and rejection reasons |
| Normal arbitration | Autopilot `finalize()` publishes one immutable `longitudinal_command` | `source.requested`: the command received by Engine, already arbitrated by Autopilot; not a claim to reconstruct every earlier plugin intent |
| Last boundary | `engine_decision()` validates command and current ACC/policy/traffic/limits | `source.selected`: exact returned decision; later Engine guards are represented separately by `output_intent` and individual channel calls |
| Launch / fail-safe | Existing mode-specific launch and Engine controlled stop | Bounded owner, actual output intent, phase and reason; launch is not relabelled as an ACC decision |
| Physical dispatch | Single Controller, unchanged opposing-channel release order | Channel sequence, clamped requested value, call start/return and exception class |
| SCS mapping | Existing `aforward` / `abackward` packed float writes and flush | Actual float32 payload and successful write/flush return, or explicit disconnected/failed status |
| Observation | Existing SDK truck snapshot | Original frame/acquisition metadata and measured speed; optional pedal channels remain null when unavailable |
| Export | Existing one worker, sealed/chunked combined export | New `longitudinal` block in `automatic-observations` records; existing integrity and partial-export rules unchanged |

No regulator, ACC behavior, pedal priority, gearbox rule, steering geometry,
steering algorithm, scheduler or 500 ms limit changed. The optional diagnostic
argument of arbitration copies only its actual reads; it introduces no second
decision path. EcoDrive is not reread and falsely labelled a consumed Engine
input: its preference was already used upstream by Autopilot.

The original missing-field reproduction failed on absent `gameThrottle` and
an empty physical-call journal. After the addition both tests pass. The former
Phase 7.4 scope test now verifies that unrelated shared pedal mirrors cannot
be upgraded into bound writes merely because they are present.

## 2. Exact recorded fields

The top-level combined schema remains version 1; `longitudinal.schema_version=1`
is an additive block. Old sealed collections remain readable. No historical
collection is modified or retrospectively supplemented.

| Path under `longitudinal` | Meaning / unit |
| --- | --- |
| `events[].sequence` | Monotonic physical pedal-call sequence, shared by throttle/brake; not an SDK or callback sequence |
| `events[].channel` | `throttle` or `brake` |
| `events[].requested_value` | Actual clamped Controller argument, normalized 0–1 |
| `events[].backend_mode` | Dispatch backend (SCS_SDK, VJOY, DIGITAL, NONE) |
| `events[].call_started_at_s`, `call_returned_at_s` | Python monotonic seconds around the dispatch; latter is the time of return or exception observation |
| `events[].call_returned`, `error` | Return versus propagated exception; safe class name only |
| `events[].backend.status` | `MAPPING_WRITE_RETURNED`, `MAPPING_NOT_CONNECTED`, `MAPPING_WRITE_FAILED`, or `BACKEND_RESULT_UNVERIFIED` |
| `events[].backend.value` | Float32 actually submitted to the SCS mapping; null for failed/unverified writes |
| `events[].backend.started_at_s`, `returned_at_s`, `error` | Actual SCS float-write/flush interval and failure class |
| `events[].pair_after` | Last verified mapping value for each held pedal after this channel call; unknown channels are null, not zero |
| `events[].source.decision_sequence` | Engine flush decision sequence |
| `events[].source.activation` | Existing `autopilot_failure_epoch`; not a newly invented activation token |
| `events[].source.context` | Failure/activation epoch, game session, map key, dataset fingerprint, intent, revision, build, publication token (in that order) |
| `events[].source.sdk_frame_us`, `observation_timestamp`, `observation_valid` | Exact Engine truck frame and original acquisition time/validity; no timestamp refresh |
| `events[].source.decision_started_at_s` | Time capture began for that flush |
| `events[].source.actual_speed_mps`, `observed_gear` | Same Engine observation's signed m/s and engaged gear |
| `events[].source.phase`, `autopilot_active`, `control_state` | Launch/handoff, active, controlled stop, release or inactive state at decision/call binding |
| `events[].source.launch` | Existing mode, request ID, start/deadline/frame, phase and handoff deadline if available |
| `events[].source.requested` | Original Engine-consumed `longitudinal_command`, including pedals, original timestamps, lease, identity, winning upstream source and reason |
| `events[].source.selected` | Engine arbitration result: pedals, winning source, reason, emergency flag and original command identity/times/expiry |
| `events[].source.output_intent` | Final intended pair for that physical branch (after additional Engine guards); release and launch have their own owners/reasons |
| `events[].source.inputs` | Accepted Engine-consumed traffic, ACC and policy packets |
| `events[].source.limits`, `speed_ceiling_mps` | Exact consumed road/policy ceilings and minimum, in m/s |
| `events[].source.input_rejections`, `rejected_inputs` | Exact read-validation reasons and bounded rejected packets, without treating them as accepted requirements |
| `events[].source.inputs.acc.requested_speed_kmh` | Requested ACC speed, km/h |
| `events[].source.inputs.acc.constrained_speed_kmh`, `control_target_kmh` | Constrained and controller target speeds, km/h |
| `events[].source.regulator_mode`, `regulator_mode_status` | Existing producer's `speed_control_reason` (e.g. speed tracking/service brake); `PRODUCER_SPEED_CONTROL_REASON` identifies its origin. Internal PID state is not reconstructed |
| `events[].source.inputs.traffic.following` | Available candidate status, ID, reference-point gap_m, speed_mps, speed_cap_mps, emergency/reason, receiver/source time, sequence, coverage/atomic/confirmed flags and expiry |
| `events[].source.disable_reason`, `safety_reason` | Existing reason at capture; controlled stop also preserves the first causal fault |
| `sampled_state` | Separately sampled active/pending/control state, activation and disable/safety reasons; not the source of an earlier physical write |
| `dropped_events`, `capacity`, `byte_budget` | Losses due to the bounded pedal journal and its configured limits |
| `game_consumption_verified` | Always false, at block and event level |

Each source is copied before the corresponding calls. A source published
during or after the call cannot relabel that call. Separate writes retain
their own source even when combined into a later collector sample. Calls
outside the bound Engine flush remain unbound; release has its own phase.

SDK fields retained under `truck`: `gear`, `parkBrake`, `_control_observation`,
`userThrottle`, `gameThrottle`, `userBrake`, `gameBrake`, plus existing speed,
frame, pose and steering fields. The current SDK normalizer/reader does **not**
publish the four SDK pedal channels. They therefore remain **null** in current
live captures; this change does not add or guess raw SDK offsets. Engine
mapping writes plus subsequent SDK speed are sufficient to measure submitted
pedals and observed motion, but not exact in-game pedal consumption.

VJOY/DIGITAL/NONE have returned-call/error observations but no independent
actual-value result in the existing backend contract; their value stays null
and `BACKEND_RESULT_UNVERIFIED`. Exact submitted float evidence is currently
SCS-specific. A successful mapping write is **not** DLL callback consumption,
input-mix output, gear confirmation or measured acceleration.

## 3. Bounds, concurrency and export

The journal is part of the existing collector path, not another collector.
It has at most 128 events and a conservative 64 KiB payload budget. Bounded
snapshots have depth/node/string budgets (16 KiB per input; 32 KiB per complete
source). Oversize data becomes `UNVERIFIED_SNAPSHOT_BUDGET_EXCEEDED`, never a
truncated identity presented as valid. The budget accounts conservatively for
JSON escaping without serializing on the control tick. Overflow drops oldest
events and records their count. Suspending capture clears held-value knowledge.

No disk writes, hashing, large geometry serialization, growing queue or log
payloads were added to the control tick. Existing capture still performs its
bounded in-memory reads; the new copies have finite budgets. The existing
collector keeps one queued capture, <=3600 accepted rows, <=8 MiB/128-record
chunks and the 32 MiB standalone file ceiling. Manifest publication remains
last and atomic; duplicate collection IDs cannot overwrite data. Hash/order,
missing/tampered chunks, old exports and rejected partial exports are tested.

This is retained diagnostic evidence, **not a guaranteed complete 60 Hz trace**.
Collector queue losses, duplicate-frame skips, rejection, finish and journal
overflow can omit calls. Journal overflow is counted, but a skipped whole
capture does not provide a count of every omitted physical call. The analyzer
always reports `complete_write_coverage=false`; zero retained overlapping
pedals is not a universal claim about unrecorded calls. No new frame is invented
to preserve an otherwise inadmissible geometry sample.

## 4. Reproducible analysis

`tools/analyze_longitudinal_evidence.py` first uses the existing inspector to
verify the manifest and every part. It reads raw automatic observations, not
the known unreliable steering replay headers. Output includes:

- speed and target speed series; requested, selected and backend pedal values;
- write/decision sequences, identity, phase, winning source and reasons;
- available candidate and explicit rejection/unverified data;
- failed/unbound writes, retained simultaneous-positive pair observations,
  dropped journal events and excluded samples;
- subsequent SDK **candidates**, matched only to a later frame and later
  acquisition time in the same activation/session/map/dataset/intent/revision/build;
- finite-difference acceleration and jerk series/distributions with sample counts.

`simultaneous_positive_pair_observations` counts retained verified mapping
states after individual channel calls with both known values >0. It is not a
count of game-consumed pairs, and unknown opposite channels are not counted as
zero. A later speed sample is not automatically attributed to the last write:
intervening writes, drivetrain dynamics and input mixing remain possible.

Acceleration: `(v[i]-v[i-1])/(t[i]-t[i-1])`, positioned at the interval midpoint.
Jerk: difference of adjacent interval accelerations divided by midpoint time
difference. Use only original bound SDK observation times, valid finite speed,
increasing frames and times, matching full identity and phase, and gaps <=0.5 s.
Missing/invalid metadata, duplicates/regression, identity/activation/phase changes
and gaps split differentiation. Units are m/s² and m/s³. No smoothing or zero
replacement is applied; quantization/noise can dominate jerk. These are
kinematic estimates from speed, not direct accelerometer measurements or proof
that pedal slew limits bound physical jerk. Existing exports without original
metadata return empty/unverified derivative metrics.

Example after a separately authorized collection:

```powershell
python tools/analyze_longitudinal_evidence.py '<collection-directory>' --output docs/steering-audit/phase7-longitudinal.json
```

The JSON includes source manifest SHA-256 and inspector result. It assigns no
new PASS threshold and never upgrades `confirmed` or `runtime_authorized`.

## 5. Verification and measured overhead

| Verification | Before / after |
| --- | --- |
| Missing SDK pedal export | Reproduced KeyError before addition; preserved value or explicit null after |
| Actual Controller pedal record | Empty journal before addition; returned mapping write/value/time after |
| Simple and real automatic launch | Actual unchanged mode-specific Engine calls captured; no inferred selector confirmation |
| ACC braking / immediate emergency | Zero drive and exclusive pair preserved; candidate and selected source recorded |
| Old command / changed identity | Existing fail-safe remains; rejected original source is retained separately from safety output |
| Packet changes during physical call | Original consumed command/target remains attached to older write |
| Manual release / backend disconnect and exception | Zero release is identified; failure cannot reuse preceding success; original exception behavior remains |
| Export → inspector → analyzer | Real Engine calls survive combined serialization/readback, chunks and partial rejection; tampering/missing part refused |
| Unknown/oversize data | Explicit unverified/null; bounded loss; no manufactured distance, relative velocity or game response |
| Disabled/failed observation | Backend bytes and method return contract unchanged |

204 targeted regressions passed (diagnostics, identity/timing/rejected export,
pedal arbitration/comfort, joint producer/Engine flow, activation and steering
boundary). A final five-test follow-up checked the tightened unknown-identity
analysis, export/concurrent publication and final overhead measurement. Full
pytest was **not** run. `compileall -q core tools tests plugins` passed;
`git diff --check` and the separate tracked/new-file whitespace check passed.
The first temporary-directory run hit Windows filesystem-sandbox PermissionError;
rerunning only the targeted tests in an approved fresh temporary directory worked.
This was not classified as an application/export failure.

Measured on this PC: 500 paired identical-input Engine flushes, in-process
copying state fixture, actual arbitration/Controller/capture and BytesIO in place
of the SCS mapping. Capture offered on **every** flush to a bounded one-element
sink, intentionally heavier than a normal 0.05 s sample period. Backend bytes
were identical with diagnostics enabled/disabled.

| Duration, ms | Median | p95 | p99 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Disabled complete fixture flush | 0.2770 | 0.4663 | 0.5585 | 0.6491 |
| Enabled complete fixture flush | 0.8021 | 1.2988 | 1.7881 | 14.7542 |
| Paired added overhead | 0.5046 | 0.8615 | 1.5351 | 14.4919 |

The maximum includes host scheduling/GC effects and is not attributed to one
operation. This does not measure ETS2, OS IPC, real mmap I/O, worker contention
or disk/export latency and does not prove a real-time worst-case bound. The
measurement is reproducible in
`test_engine_output_matches_without_diagnostics_and_measure_overhead`; its
`overhead.json` remains in ignored pytest audit output. Capture is not free,
and game evidence is still needed to assess live overhead.

## 6. Readiness and remaining limits

**Source-side SCS longitudinal collection: ready for full-suite review and a
separate coordinated deployment decision. Not armed, deployed or game-tested.**
The installed old collector cannot obtain these fields until the changed core
files and new helper are deployed together after approval. No plugin file or
control behavior changed, so plugin VERSION and PLUGIN_CHANGELOG remain unchanged.

Traffic producer timestamp/generation, confirmed actor lane/elevation/coverage,
exact bumper gap and trustworthy relative velocity are still unavailable where
the existing producer lacks them. Keeping a candidate snapshot does not cure
these source limitations or make stop-and-go safe. Internal PID components and
four missing live SDK pedal channels are not reconstructed. The optional
regulator mode is the producer's reported reason, not fabricated internal state.

Next smallest step: user full suite, then review the coordinated source changes
for a separately approved deployment. Do not request another drive on the old
installed schema. Comfort/following conclusions remain pending actual retained
game measurements, and no original collection is changed.

Changed files: `core/controller.py`, `core/engine.py`, `core/longitudinal.py`,
`core/navigation/evidence_diagnostics.py`, `core/navigation/longitudinal_diagnostics.py`,
`core/sdk/scs_controller_writer.py`, `tools/analyze_longitudinal_evidence.py`,
`tests/test_longitudinal_evidence_diagnostics.py`, `tests/test_phase7_joint_validation.py`,
this report, `PHASE7_FINAL_RESULTS.md` and `DEFERRED_WORK.md`.

Proposed commit: **feat(diagnostics): capture source-bound longitudinal writes**.
Description: add bounded pedal/ACC decision and SCS write provenance to the
existing combined export; analyze retained speed/target/pedal/intervention data
without upgrading traffic evidence or changing control behavior.

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python -m pytest tests -q
```
