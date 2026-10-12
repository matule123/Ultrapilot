# Thirty-second automatic pedal decision history

## Scope and verdict

**PASS: offline capture/export contract. ETS2 consumption NOT VERIFIED.**
Starting HEAD: `787d012a2a78ac917bb5506e0958c32d8d06575f`, plus the preserved
uncommitted automatic-evidence, export-regression, coast and signal-selection
changes. The user reported a successful full pytest run after the ten export
regression fixes, before this extension. No full suite was run here. No
AGENTS.md was found in the checkout; plugin-version rules were reviewed.

The proven problem was retention: the existing 64 KiB detailed journal covers
approximately 0.15–0.17 seconds at the measured write load, not several seconds
of pedal alternation. Two initial reproductions failed before adding the
history/export API. The extension changes diagnostics only. Regulators,
arbitration, transmission transitions, signal selection, steering cadence,
freshness limits and safety decisions remain unchanged.

## One existing journal, two independent evidence resolutions

`PedalJournal` owns the new history; it is not another collector or controller.
The existing Engine diagnostic wrapper binds already-consumed snapshots,
records existing Controller receipts and closes the diagnostic decision after
the physical calls. No new SDK or IPC reads are added.

| Evidence | Fixed live reservation | Resolution and retention |
| --- | ---: | --- |
| Existing detailed pedal calls | 64 KiB, 128 events, unchanged | Every retained physical call; actual start/return, result and immutable source; measured short duration, no thirty-second promise |
| Regular decision summaries | 512 KiB, at most 320 rows | At most 10 Hz, last 30 seconds plus one leading anchor |
| Ordered decision/state changes | 448 KiB, at most 2048 rows | Mode/source/reason, phase, gear, validity, identity, signal/lock, hold and first-fault changes; bounded separately from regular samples |
| Exact identity dictionary | 64 KiB | Owned session/map/dataset/intent/revision/build/publication-token context and route identity; exact immutable references, no guessed identity |

The summary's total live reservation is **1 MiB**, separate from the unchanged
64 KiB detail reservation. Each fixed-value row is at most 4096 bytes before
lossless compression; identities are at most 4096 encoded bytes. Retained
accounting charges compressed bytes plus row/identity metadata. Oversize,
identity-capacity and capture failures are explicit. No repeated whole producer
packets are kept. The bounded current projection and temporary encoding/export
allocations are measured separately from retained accounting.

A single existing export job seals immutable references. Initially it shares
the retained bytes; while the live window advances it can retain one additional
bounded history snapshot, never an unbounded waiting queue. Worker expansion
has temporary allocations; the 1 MiB figure is not a claim about the whole
application's RSS or dense steering replay memory.

## Recorded fields and meanings

Public path: `longitudinal.decision_history`. Its `regular_samples` and `changes`
use `sequence`, `monotonic_s` and `identity_reference`, resolved through the
owned `identities` dictionary. The two streams share one chronological sequence.

| Fields | Meaning |
| --- | --- |
| `sdk_frame_us`, `observation_timestamp`, `speed_mps`, `gear`, `observation_valid` | Original consumed Engine truck snapshot; timestamps are never refreshed |
| `activation`, `decision_sequence` | Actual activation and Engine decision; missing/unbound values remain null |
| `command_sequence`, `command_sdk_frame_us`, `command_observation_timestamp`, `command_computed_at`, `command_expires_at`, `command_valid` | Original received Autopilot command and its producer sequence, distinct from the later Engine snapshot |
| `requested_speed_kmh`, `constrained_speed_kmh`, `control_target_kmh`, `speed_ceiling_mps` | Available consumed targets/limits, with explicit units |
| `requested_throttle/brake`, `selected_throttle/brake`, `selected_source`, `reason`, `throttle`, `brake`, `pedal_mode` | Requested command, arbitration selection and final branch intent are separate |
| `brake_requests`, `acc_throttle/brake`, `traffic_brake`, `light_brake`, `policy_brake`, `curve_brake`, `curve_radius_m`, `curve_distance_m` | Available original producer requests and later Engine inputs; no invented traffic evidence |
| `acc_target_id`, `acc_status`, `acc_gap_m`, `acc_confirmed`, `speed_control_reason` | ACC's own consumed publication, including its production flat following fields; no inferred gap |
| `traffic_target_id`, `traffic_target_status`, `traffic_gap_m`, `traffic_target_confirmed` | Separate later traffic candidate; never substituted for ACC's earlier candidate |
| `signal_id`, `signal_color`, `signal_relevance`, `signal_valid`, `signal_reason`, `signal_observed_at`, `signal_frame_us`, `signal_generation`, `signal_lifecycle` | Qualified consumed control signal and original producer times; not HUD-only detection |
| `signal_lock`, `stop_target` | Actual hold lock and available passage key, distance/basis, entry progress/position, stop-target kind, front allowance and stop-line verification |
| `phase`, `control_state`, `forward_phase`, `coast_only`, `hold_phase`, `hold_chain`, `hold_brake`, `hold_reason` | Actual launch/coast/brake/wait/restart state and continuous-brake receipts |
| `write_first_sequence`, `write_last_sequence`, `write_count`, `write_success_count`, `write_error_count`, `write_unverified_count` | References/counts for physical calls; older detailed events may already have aged out |
| `write_first_started_at_s`, `write_last_returned_at_s`, `last_backend_status`, `last_backend_error`, `written_throttle`, `written_brake` | Existing physical receipts and held mapping values; failed/unverified channels are null |
| `backend_throttle_min/max`, `backend_brake_min/max`, `backend_pair_mode_changes`, `write_source_changes` | Successful physical values and transitions inside a decision, including intermediate writes that differ from the final intent |
| `sdk_game_throttle`, `sdk_game_brake` | Available SDK response from the original snapshot, not automatic attribution to these calls |
| `first_reason`, `first_reason_observed_at` | Original intervention, preserved through safety/release and reset only for a genuinely new activation |

Intervention-only rows carry fields actually present in the first-fault receipt;
other values remain null. Exact rejected comparisons remain in the existing
`first_intervention` and detailed call sources. Backend return is never treated
as confirmation that ETS2 consumed an input.

Short drive/brake/drive changes between regular samples are retained as ordered
change rows. Each regular row additionally has an `aggregate` for intervening
decisions: counts, requested-pedal and signed-speed min/max, successful physical
pedal min/max, write/error counts, physical-mode and write-source changes.
`aggregate.exact_write_timing=false`: these aggregates preserve evidence of
short changes but cannot reconstruct their exact order/timing after detailed
or change-event eviction. `aggregate_tail` covers the unsampled tail.

## Automatic export and coverage

After deployment, ordinary startup is sufficient: **no arm command or new
setting is required**. Existing automatic-disable handling captures the first
fault and the existing finite safety/release tail, then uses the existing
background replay writer:

`C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics\steering-replay-<UTC>-automatic_disable.json`

The pedal incident has `sample_kind=longitudinal_boundary_incident`. A separate
dense steering replay can share the event suffix; distinguish it by sample
kind and actual identity/time. Combined export remains nondestructive and
chunked; it does not repeat the entire thirty-second ring in every sample.
There is no synchronous disk I/O or extra control command in the capture path.

Coverage is separate:

- `detail_evidence`: start/end/duration, call count, dropped count and incomplete
  flag for the 64 KiB detail ring.
- `decision_history`: observed range, requested window, period, capacities,
  retained bytes, capacity evictions per stream, normal window aging, capture
  failures, time regressions, warmup, unsampled tail and independent incomplete
  flag. Capacity counts are cumulative for this journal lifetime; ordinary
  aging beyond the window is not counted as capacity loss.
- Existing steering sample/count/overflow metadata remains independent.

Hash validity does not establish completeness or game consumption. A history
with loss remains incomplete even when SHA-256 is valid. Invalid references,
duplicate/regressing sequences, nonfinite/regressing row times and altered
payloads are rejected. `confirmed=false`, `runtime_authorized=false` and
`game_consumption_verified=false` remain unchanged. Forced termination or disk
failure cannot guarantee a completed file.

The existing `tools/analyze_longitudinal_evidence.py` exposes the long history
separately from physical `write_series`. It never reconstructs older exact
writes or causal SDK response from summaries. Full-resolution longer capture
still requires the existing combined collection.

## Reproductions and validation

| Scenario | Before / after |
| --- | --- |
| Thirty-second history and incident roundtrip | Missing API/history failed before; actual sixty-second production loop now exports at least 29.9 seconds, long real-format identities, two red/wait/green cycles, deceleration, standstill and first intervention |
| Brief switches between 10 Hz samples | Drive/brake/drive events retain their order; regular aggregates retain counts and min/max |
| Intermediate physical writes inside one flush | Launch throttle then zero is visible in physical min/max/mode/source counts, even when the final intent is release |
| Manual release | Temporary Controller release source was initially replaced before summary closure; actual write binding and out-of-flush release capture now retain zero writes and new-activation separation |
| Backend failure | Actual closed BytesIO mapping produces failure, unknown current pair and original first reason through release; no false game-consumption claim |
| IPC publication race | Actual bounded reread uses the newer consumed snapshot; summary preserves its frame and original command frame rather than the stale initial capture |
| Sixty-second 50 Hz change storm | Last thirty-second regular window survives; event capacity loss is explicit and aggregates retain short-switch evidence |
| Identity/clock/missing fields | Immutable snapshots preserve different identities; time regression is incomplete; absent gear/pedals stay null |
| Combined + dense + automatic incident | Existing combined export, Autopilot dense worker and Engine pedal-history worker all read back with valid integrity; first cause survives cleanup |
| Corruption | Missing identity reference is rejected even with recomputed outer hash |

The test vehicle/SDK frames are explicit modeled inputs; the real producers,
Autopilot, Engine and Controller use an in-memory test backend. This proves
software ordering and evidence retention, not ETS2 physical response.

Final targeted regression group: **193 passed in 37.86 s**, including the
existing automatic-pedal, combined, dense replay and original export-regression
files; Oct-7 command pairing/coast scope, prefab binding and Oct-4 signal
lifecycle/green restart are included. The twelve history regressions also check
analyzer readback of the separate summary block. Python `compileall` over
core/plugins/sdk/tools/tests/ui and `git diff --check` pass. The full pytest
suite remains for the user; no original regression expectations were removed.

Completion after the interrupted check, 2026-10-08: all **12 history tests
passed in 6.03 s**, including the analyzer's actual `Path` input contract.
The previously passing 193-test targeted group and benchmark were not rerun
without a new runtime change. No user installation or original evidence changed.

## Measurements

Final sixty-second benchmark: SDK/Engine 60 Hz (3600 steps), producers 20 Hz
(1200 steps), copying in-process IPC and real Controller/BytesIO backend.
The original six-second measurements in the earlier report are historical.

| Operation, ms | Diagnostics off: median / p95 / max | Diagnostics on: median / p95 / max |
| --- | ---: | ---: |
| Engine flush | 0.3966 / 0.5710 / 1.3861 | 1.3291 / 1.5901 / 2.3823 |
| Autopilot producer | 0.2630 / 0.4253 / 0.6576 | 0.4611 / 0.5948 / 0.9696 |

Engine statistic increments are **0.9325 / 1.0191 / 0.9962 ms**; producer
increments **0.1981 / 0.1695 / 0.3120 ms**. These are differences between
whole-operation distributions, not isolated history-only costs or guarantees
about an individual tick. The comparison enables/disables the complete existing
automatic provenance capture, including this extension. No additional plugin
implementation was introduced by this continuation.

The summary retained **30.100 s, 302 regular rows**, with **zero capacity
evictions and zero capture failures**. Its accounted maximum was **338630 B**,
final **336147 B**, against the fixed 1048576 B limit. Normal unchanged state
left no change events in the final thirty-second window; the separate production
cycle and rapid-alternation tests exercise those events.

The unchanged detail ring retained **20 calls / 0.150 s**, maximum **64706 B**,
with **7190 earlier calls explicitly evicted**. Detail is incomplete; summary
is not. This separation is intentional, not a claim that thirty seconds of
individual physical writes were retained.

Traced retained heap after GC: off **8144695 B**, on **8518892 B**; increment
**374197 B (365.43 KiB)**. Traced peak: off **8176890 B**, on **8953747 B**;
increment **776857 B (758.65 KiB)**. These include existing application/replay
allocations and temporary diagnostic work, while excluding the test-only
backend write recorder and mapped-output history. Exact physical pedal/channel
sequences, **all 3600 mapped control frames** (including steering/selector) and
Engine IPC-read counts were identical on/off.

Reproduce the sixty-second on/off comparison:

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python tools/benchmark_automatic_longitudinal.py --samples 3600 --output docs/steering-audit/automatic-longitudinal-history-20261007.json
```

The benchmark separates untraced CPU runs from traced heap runs, clears the
unbounded test-only backend assertion list during heap measurement and replaces
the mock clock recorder with a plain function. Mapping-frame recording is
excluded from heap runs. Existing steering replay/IPC/PID allocations are still
included, and operation timings are not a live process-scheduling guarantee.

## Files and versions

This continuation changes `core/navigation/longitudinal_diagnostics.py`,
`core/engine.py`, `core/steering_replay.py`,
`tools/analyze_longitudinal_evidence.py`,
`tools/benchmark_automatic_longitudinal.py`,
`tests/test_pedal_decision_history.py`, this report,
`PHASE7_AUTOMATIC_PEDAL_EVIDENCE_20261007.md`,
`PHASE7_LONGITUDINAL_DIAGNOSTICS.md` and `PLUGIN_CHANGELOG.md`.

No plugin implementation changes in this continuation: Autopilot retains the
already pending **1.3.0** from the previous diagnostic addition; no other
plugin version is increased. The earlier export, coast, signal and HUD edits
remain in the working tree. No deployment, arming, game input, commit or push.
