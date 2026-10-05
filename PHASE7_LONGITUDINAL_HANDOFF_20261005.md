# Longitudinal evidence leases and executable handoff — 2026-10-05

## Verdict and build

**Offline PASS for the reproduced lease-composition and handoff defects.
The candidate's effect in ETS2 is NOT VERIFIED.** The full pytest suite is left
to the user. This is an uncommitted working-tree candidate; nothing was deployed,
armed, started in ETS2, committed or pushed. Original diagnostics are unchanged.

Entry HEAD: `b5a7aa323212bf1100633cbb6cb9907a7b92ee57`. The tracked tree was
clean at entry. No AGENTS.md was found in the repository or checked ancestors;
PLUGIN_VERSIONS.md, DEFERRED_WORK.md and the preceding Phase 7 reports were read.
Their launch, continuous braking, signal-clearance and 35 km/h entry work is
preserved. This report supersedes a claim that the preceding lease fixes alone
settled recurring handoff expiry; it does not rewrite their historical results.

Read-only comparison of Engine, longitudinal arbitration, control-fault storage,
pedal journal, Map, Autopilot, ACC and DrivePolicy found all eight installed files
equal to entry HEAD after CRLF/LF normalization. Thus the incident cannot be
explained by the earlier deployment mismatch. The local hash receipt is
`docs/steering-audit/handoff-build-identity-20261005.json`. Current candidate
changes are not installed. Controller, Map 1.0.6 and the DLL are unchanged.

Changed plugin declarations: Autopilot **1.2.1**, ACC **1.1.3**, DrivePolicy
**1.0.5**. Their prior versions were 1.2.0, 1.1.2 and 1.0.4 respectively.

## Incident reconstruction and attribution limits

Sources: installed ultrapilot.log and
`steering-replay-20261004T190242.344988Z-automatic_disable.json`.
The wall-clock event is 2026-10-04 21:02:40, UTC+2; below are original monotonic
seconds. Identity: activation 15769995551900, session 1, map promods-1.59,
dataset d6cc7936fce4e902761abb5d, intent ebea77f0a0bd446cbcbdad9ae13f4e22,
revision 7, build f5320dcad68e4cf2b331802977dc7cb4, geometry
f6e44b5a0a280f891ddcadaf2975d6a12dc7fd6a2dc58a166df6c0bbe895fff9.

| Compared object / boundary | Original times | Proven budget |
| --- | --- | --- |
| ACC observation and computation | 15781.6372786 → 15781.6612758 | 23.9972 ms processing; expiry 15781.6688093 leaves only 7.5335 ms |
| Autopilot check of ACC | 15781.6826799 | Observation age 45.4013 ms; inherited lease exceeded by 13.8706 ms |
| Earlier AP command consumed by Engine | Observation 15781.5838017; computation 15781.6455098 | Same expiry; only 23.2995 ms left at computation |
| Engine prewrite check | 15781.6916679 | Observation age 107.8662 ms; decision age 46.1581 ms; lease exceeded by 22.8586 ms |
| Compared identities | valid=True; actual_context=expected_context; different_fields=[] | No demonstrated activation/session/route mismatch |

The rejected lease is not a 500 ms vehicle-observation or steering expiry.
The displayed log order is not the order of the recorded checks: their log
capture times are later than the actual comparison times. A newer drivetrain
read does not renew the evidence used by either earlier decision.

The replay contains 183 samples and 10,800 retained executor records, with
42,814 dropped executor records. It shows a roughly 430 ms Map tick around
15781.2217095–15781.6522641: observation 15781.6014184, computation 15781.6485582,
publication 15781.6518134, and a sampled AP packet read finishing 15781.6649439.
Those sampled reads are not first-delivery receipts. Neither this replay nor a
matching combined export preserves the complete consumed input set that
created expiry 15781.6688093. Its implied 500 ms observation origin is
15781.1688093, but **the historical producer kind cannot be uniquely identified**.
The evidence also cannot allocate all delay to a particular IPC call, lock,
Policy operation or OS scheduling pause. No such retrospective claim is made.

## Reproduced common defects and production changes

| Defect / reproduction | Before repair | Candidate |
| --- | --- | --- |
| Exact incident intervals, fresh SDK but old nonbinding curve/higher policy/empty traffic | Full producer-to-backend reproduction fails; a nearly expired unrelated input expires the fresh execution | Only effective/tied constraints and required dynamic evidence contribute; original SDK time is retained and valid drive continues |
| Binding input with less than one handoff opportunity remaining | ACC can publish a command with a few milliseconds left; process phase causes a false technical stop | A producer marks insufficient execution reserve; common Plugin/Engine handling requests a new decision and issues zero drive in a fixed bounded transition |
| Required producer updates between consumer reads | A consumer can reject the value overtaken by publication | At most one complete immutable reread; validate after the read, using the returned original times and identity |
| Duplicate SDK frame, new effective input evidence, previous decision requires refresh | Unchanged-target early return can retain the old inherited expiry | Recompute the existing decision without another integral step or renewed SDK timestamp; the original frame still bounds its lifetime |
| 120 ms diagnostic binding after an earlier valid prewrite check | Positive physical throttle can be written after its input expiry; the narrow reproduction fails on HEAD | Repeat the boundary check after binding and opposing-channel release, immediately before positive I/O; refuse expired pedals |
| Refresh while forward-started planned braking is still moving, without a signal lock | Initial candidate wrote a brake zero in both modes 0 and 3 | Preserve the existing validated, acknowledged positive brake chain throughout the bounded transition, including the approach to rest |
| Original deadline in the existing bounded journal / first-fault receipt | Repeated full identities can exhaust the diagnostic budget; minimum scalar alone loses its source | Retain original deadline source/frame/time/kind; intern equal metadata within the same immutable row, restoring explicit fields at export |

The narrow exact-budget and delayed-positive-I/O tests were also run against
in-memory historical production modules from HEAD: both fail before and pass
with the candidate. No checkout was reset or copied. The moving brake-continuity
test was added before its fix and failed with physical brake write 0.0 in both
automatic modes; it passes after the repair. This independently reproduced
candidate defect is not asserted to be the historical incident's first cause.

### One evidence and handoff contract

- Actual telemetry remains one valid coherent SDK snapshot, with its original
  frame and observation time. All required frame/identity/freshness checks remain.
- Road and curve classifications are spatial observations, not indefinitely
  valid map facts. They retain the original 500 ms lease and complete identity;
  this patch has no verified spatial scope that would authorize permanent reuse.
- Dynamic traffic that actually constrains motion, a latched following target,
  red/yellow evidence, and effective/tied lower constraints retain their original
  leases. An empty/uncovered buffer authorizes no drive and is not a cruise lease
  owner. Missing data after a followed target still fail closed.
- Each decision records `deadline_basis` (source, kind, original SDK frame,
  original observation time and expiry), compact `lease_dependencies`, and
  `remaining_at_computation_s`. The winning leaf is propagated through Policy,
  ACC, Autopilot and Engine. An unattributed legacy expiry is explicitly unknown.
- Route-projected traffic records the actual consumed Map projection receipt.
  Its receiver-time bound is explicitly `receiver_budget_unverified`, with no
  fabricated producer timestamp or SDK frame. It is distinct from the Map
  spatial observation and from a measured traffic producer acquisition.
- ACC/AP decisions with less than **50 ms remaining at computation** request a
  fresh handoff instead of authorizing nearly expired ordinary drive. This is a
  scheduling reserve, not a new data-validity limit: approximately two 60 Hz
  opportunities plus a bounded producer/RPC allowance. The measured 13.9–22.9 ms
  consumer overruns and offline phase matrix justify avoiding single-digit
  budgets. It is not a guarantee under arbitrary CPU stalls.
- One shared `longitudinal_refresh_request` binds the original rejected decision
  to the current activation/context. Its absolute end is **original expiry +
  100 ms**, never now+100 ms on every tick. The interval bounds zero-drive
  transition handling, not the old pedal command's validity. Only still-valid
  expiring evidence or a demonstrably newer valid leaf/current SDK can start it.
  It cannot start on foreign, missing/invalid evidence, stale SDK, or a technical
  controlled stop. A hung required producer exhausts the bound and stops safely.
- The transition publishes a separate zero-drive decision using the actual SDK
  observation. It cannot execute the expired command. Engine preserves only an
  already acknowledged continuous planned brake chain with fresh physical-write
  evidence. It does not invent a stationary brake edge or release parking brake.
  Valid urgent traffic braking bypasses the ordinary execution-reserve wait.
- A real fresh nonpending physical decision completes the handoff. A zero-drive
  pending packet cannot clear or restart the timer. Manual/technical cancellation,
  foreign identity, R and reverse motion retain their existing safety behavior.
- The last identity/original-observation/expiry check remains at physical I/O.
  `longitudinal_applied` records original deadline basis, write start/return,
  remaining validity and `refresh_pending`. Backend return proves a software
  write, not ETS2 consumption. No steering timestamp, gain, cadence or 500 ms
  limit was changed.

## Independent-cadence end-to-end comparison

`tools/run_longitudinal_handoff_bench.py` loads the baseline's complete
Engine/arbitration/ACC/Policy/AP modules in memory. Both versions use the actual
Map publication, Controller and SCS memory-write code. Synthetic directed road
geometry and a coherent SDK pose moving at 3 m/s are explicit inputs; this is not
the original ProMods route or a calibrated vehicle/traffic plant.

Periods: SDK 33.333 ms, Map 360 ms, traffic 460 ms, Policy 59 ms, ACC 23 ms,
AP 26 ms, Engine 16.667 ms. Independent phases, copying RPC costs and no catch-up
queue model normal cadence mismatch and conservative serialized contention.
Three phase/RPC settings are each tested with the existing pedal journal off/on.
The virtual clock does not turn journal CPU overhead into a measured zero cost.
No disk export, real OS-process scheduling or producer-timed traffic coverage is
simulated; export integrity is covered separately by the existing regressions.

| Phase / cost per RPC | Baseline time to first fault | Candidate duration per off/on run | Candidate physical decisions per run | Zero-drive refresh writes | Candidate faults / expired matched writes / paired positive pedals |
| --- | --- | --- | --- | --- | --- |
| 0 / 0.060 ms | 0.50436 s; observation/lease rejection | 75.01507 s | 3,093 | 151 | 0 / 0 / 0 |
| 3 ms / 0.120 ms | 0.99324 s; ACC lease rejection | 75.01172 s | 1,805 | 1 | 0 / 0 / 0 |
| 7 ms / 0.200 ms | 0.50940 s; input expiry before write | 75.00360 s | 1,214 | 209 | 0 / 0 / 0 |

Total candidate: six runs, approximately 450 simulated seconds and **12,224
physical decision receipts**. All remain active without a technical fault.
Historical baseline matched positive-write counts are only 20/23/7 per run;
they terminate early and are not a comparable full-duration population.
A later safety-stop brake is not attributed to an earlier rejected normal
command. The separate delayed-binding test, not this cadence table, proves the
baseline's expired positive-write window.

### Remaining validity and observation age

Values below are **milliseconds: minimum / median / p95 / maximum**, for the
candidate. Off/on runs have identical virtual-clock results. Publication is
measured at completion of actual ACC/AP slot assignments. First Engine read is
the first actual copied command lookup per distinct frame/computation/expiry
within Engine flush; it is not a claim of first delivery in the historical log.
Physical start is immediately before the paired synchronous mapped write.

| Phase / RPC | Completed publication (n) | First Engine read (n) | Physical write (n) | SDK observation age at write (n) |
| --- | --- | --- | --- | --- |
| 0 / 0.060 ms | 4.027 / 236.413 / 402.200 / 483.740 (4,174) | -1.193 / 215.993 / 389.493 / 480.920 (2,087) | 36.326 / 212.873 / 383.380 / 478.400 (3,093) | 7.214 / 44.793 / 60.007 / 69.153 (3,093) |
| 3 ms / 0.120 ms | 47.280 / 248.440 / 410.280 / 461.480 (3,608) | 43.880 / 223.360 / 386.440 / 455.840 (1,805) | 38.840 / 218.320 / 381.400 / 450.800 (1,805) | 25.200 / 33.800 / 38.120 / 49.200 (1,805) |
| 7 ms / 0.200 ms | 17.400 / 218.400 / 394.200 / 431.400 (2,429) | 0.800 / 206.000 / 380.800 / 422.000 (1,214) | 2.200 / 197.600 / 372.400 / 413.600 (1,214) | 42.000 / 42.600 / 63.600 / 70.800 (1,214) |

Publication/read populations include decisions marked as requiring refresh.
The negative read margin is explicitly rejected and replaced by a bounded
zero-drive transition; it is not a written expired command or repaired timestamp.
The 2.2 ms minimum physical margin shows finite reserve at this modeled load,
not a universal scheduling guarantee. Percentiles use sorted nearest-rank p95;
median is the middle sorted element. Missing values are not zeros.

Local receipts (ignored output, not raw data added to Git):
`longitudinal-handoff-cadence-20261005-complete-boundaries.json` and
`handoff-explicit-before-after-20261005.json` under docs/steering-audit.
The tool also retains computation-time and observer-read margins separately;
they must not be substituted for the completed-publication/Engine-read metrics.

## Regression and numerical evidence

- The consolidated selected run passed **514 tests and 10 subtests**. It covers
  arbitration, actual Controller outputs, the 75 s cadence matrix, original SDK
  binding, first N/handoff, zero-ratio transitions, route-window/identity races,
  brake hold, signals, producer loss, reverse, backend failure and diagnostic
  roundtrip. It is not the full pytest suite.
- Following the reproduced moving-brake gap fix, the directly affected
  handoff/continuous-stop/signal/lifecycle/commit/lease group passed **136 tests**.
  These overlap the consolidated selection and must not be added as a unique
  coverage count. The final boundary/emergency/arbitration/continuous-braking
  selection then passed **110 tests** after the last Engine change.
- Three red/continuous-wait/green/restart cycles exceeding one minute in both
  automatic modes retain positive brake at every waiting write, zero throttle,
  no extra N, no reverse edge and no parking-brake write. Refresh is tested both
  during stationary signal holding and the moving braking phase. The gearbox
  behavior remains an explicitly user-observation-based model, not SDK proof.
- Original-leaf expiry, permanently stalled producer, genuinely stale SDK,
  different identity, manual cancellation and previous activation remain
  fail-closed. Valid urgent braking uses the immediate physical output path.
- All **16 steering benchmark cases** and **12 speed-comfort benchmark cases**
  are numerically identical to the entry baseline on the same modeled inputs.
  Steering controller/route/dynamics files are unchanged. Comfort comparison
  verifies controller numerics; the full historical handoff comparison is the
  independent-cadence tool above.
- All **eight roundabout approach cases** retain the already implemented upper
  ceiling: entry 32.926–33.569 km/h, identical baseline/candidate results.
  Modeled maximum deceleration is 0.952–1.074 m/s² and maximum absolute jerk
  2.207–3.361 m/s³. For the regular light-load case braking starts 68.040 m before
  entry and reaches 35 km/h 24.000 m before it. These are modeled metrics, not
  measured physical jerk or universal live roundabout guarantees.
- A sandbox run hit Windows temp-directory `PermissionError` during fixtures
  and cleanup; it is not counted as a passing run or a production assertion
  defect. The selected rerun with a new functional directory and permitted local
  IPC produced the successful consolidated result. A mistyped nonexistent test
  filename also aborted collection without running tests; it is not a test failure.
- Final `python -m compileall -q core plugins tools tests` and `git diff --check`
  completed with exit code 0. New untracked source/report files were also checked
  for trailing whitespace and a final newline. Git's LF/CRLF warnings are not
  whitespace failures. The existing .pytest_cache access warning was preserved;
  no existing directory or diagnostic was deleted.

## Remaining limitations and next gate

**No new drive is requested now.** First obtain the user's full-suite result;
any coordinated deployment needs separate authorization. A future single
controlled verification can inspect launch, normal drive, braking, continuous
signal waiting and fresh-green restart using the existing combined journal.
Do not deliberately provoke failures, release a driver-owned parking brake or
treat missing traffic as clearance. The driver must remain able to take over.

Autonomous holding when activated at an already stationary red remains
**BLOCKED** in simple automatic: no verified non-reverse new service-brake edge
or alternative permitted holding interface exists. The current driver-held
pending state is not an active self-holding feature. No parking-brake workaround
was introduced. The live DLL consumption of continuous SDK brake, hill holding,
signal memory patterns and effect of this repair are NOT VERIFIED.

Legacy traffic still lacks producer timestamp/generation, coverage and a proven
actor-to-lane link. Receiver time is not producer acquisition time. A geometric
following candidate is not a confirmed reliable ACC target, and reference-point
gap is not a bumper measurement. These limitations block broad ACC/live-safety
claims but do not excuse inheriting irrelevant deadlines or executing expired
pedals. Original historical deadline attribution remains unavailable; new
compact provenance enables attribution in the existing journal/fault export.

## Changed files and reproduction

Coordinated runtime files: core/engine.py, core/longitudinal.py,
core/control_timing.py, core/navigation/longitudinal_diagnostics.py,
plugins/acc/main.py, plugins/autopilot/main.py, plugins/drivepolicy/main.py.
No Map, Controller, SDK/DLL, steering controller or settings file is changed.

Tests: test_longitudinal_handoff_contract.py, test_longitudinal_handoff_cadence.py,
test_longitudinal_lease_budget.py, test_oct4_signal_lifecycle.py,
test_phase7_joint_validation.py and test_rolling_longitudinal_authority.py.
Existing fixtures expose their actual producer ticks; they do not manufacture
success. The old lower-cap test now asserts original consumed expiry, zero drive
and a bounded separate refresh command, rather than expecting immediate technical
shutdown on a valid handoff. The ACC simulation now supplies actual Map
calculation/frame fields required by production projection validation; no
production freshness check was removed to accommodate an incomplete double.

Tools: run_longitudinal_handoff_bench.py (new reproducible historical comparison)
and run_acc_following_bench.py (complete fixture/projection dependency contract).
Documentation: this report, PLUGIN_CHANGELOG.md and DEFERRED_WORK.md.

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python tools/run_longitudinal_handoff_bench.py --ref b5a7aa3 --output docs/steering-audit/handoff-rerun.json
```

Full suite, to be run by the user:

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python -m pytest tests -q
```
