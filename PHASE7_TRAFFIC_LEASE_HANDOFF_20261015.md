# Traffic dependency expiry and physical-boundary handoff — 15 October 2026

## Verdict and scope

**OFFLINE VERIFIED for the reproduced handoff/export defects; GAME NOT VERIFIED.** This is a core-only
correction to the existing renewal contract, not a new regulator or traffic
feature. It preserves the 500 ms evidence lease, 50 ms producer execution
reserve, original 100 ms renewal bound, steering, signal 5 m reference, gearbox
launch/continuous brake ownership, ACC departure and observed-body AEB.

The exact historical scheduling cause of the old traffic dependency is **not
proved**. A separate, reproducible defect prevented the existing safe recovery
at the final physical boundary even when newer qualified evidence existed.

## Installed build and evidence identity

- Initial working tree was clean at `3ee9786fff90a94ef75cbf3b5070e98867ecd603`.
  No AGENTS.md was present in the repository/parent search. Plugin versioning
  and deferred-work rules apply; previous repairs remain intact.
- Installation: `C:\Users\PC\AppData\Local\Programs\UltraPilot`.
  The actual deployment receipt and all 31 listed file hashes were checked.
  All 18 payloads also match the preserved v5 ZIP and its manifest, including
  the unchanged native artifacts. LF/CRLF differences are normalized for source
  comparisons; receipt and artifact integrity use exact bytes.
  HEAD matches the installed Python implementation. The repository's raw
  `assets/ets2la_plugin.dll` differs from the installed, receipt/v5-verified
  native build; it must not replace that staged native artifact. The candidate
  deliberately contains no DLL replacement. Final source deltas are the two
  core files and changelog, independent of that pre-existing native-asset delta.
- v5 ZIP SHA-256:
  `19d354b147b548a084d5160981cdb35724e7fb462a7fec800251d4f492a93f69`.
  Installed ACC 1.3.2, DrivePolicy 1.1.4, Autopilot 1.3.4, Map 1.1.2,
  TurnSignals 1.0.2, DLL 1.59.4-up-traffic-timed. No plugin implementation or
  native code is changed by this task, so no plugin version is advanced.
- Both original automatic exports pass `inspect_replay` hash/codec integrity:
  `steering-replay-20261015T043038.167087Z-automatic_disable.json` (pedals) and
  `steering-replay-20261015T043039.383315Z-automatic_disable.json` (dense).
  Originals are read-only; decoding and derived JSON stay in the ignored
  `docs/steering-audit/oct15-traffic-lease/` directory. Integrity is not proof of
  full capture or game input consumption.
  Original SHA-256, in the same order:
  `338a87de57b1f2a54b9e737863333402ee6a2a3896b872aa8700123ffe5a59f3`,
  `f5c1129447abcca47141ea5b3bad856bf2169a9f551597613d32b03e680cbee3`.
- Actual authority: activation `1208684946800`, session `1`, map `promods-1.59`,
  dataset `d6cc7936fce4e902761abb5d`, intent
  `dd31e6422753447eb472cb828fbd4ccb`, revision 6, build
  `b3dc0b8f50d446f3b24fe4135fc7041e`, geometry
  `ae9c92f914cfdb8588ab767cda028d0c60ccc5c716598555cd7b5a68cbf84708`.
  Neither a newer fault-time telemetry frame nor another session is substituted
  for the actual rejected command.

## First historical rejection and limits of reconstruction

All values below use the original monotonic clock, seconds.

| Stage | Original evidence | Time / interval |
| --- | --- | ---: |
| Traffic deadline owner | frame 108295668, dynamic evidence | observation 1240.3729019 |
| Command vehicle observation | frame 108662320 | 1240.7445940 |
| Command computation | selected source ACC, normal drive | 1240.8103433 |
| Traffic-limited deadline | original traffic observation + 0.5 s | 1240.8729019 |
| Final Engine check | same full authority, no differing identity fields | 1240.8740754 |
| Lease overrun | final check minus original deadline | 1.1735 ms |
| Own vehicle observation age | final check minus command observation | 129.4814 ms |
| Decision age | final check minus computation | 63.7321 ms |
| Budget at computation | deadline minus command computation | 62.5586 ms |
| First recorded intervention | Engine, TECHNICAL_CONTROL_STOP | 1240.8755883 |
| First retained safety write | journal 1165; later than initial rejection | about 1240.9026 |

The traffic observation preceded the command's own observation by **371.6921 ms**;
another **65.7493 ms** elapsed to computation. AP's later report repeats Engine's
first cause; it is not a separate initiating fault. The selected result stored
`valid=null`, `decision_source=null`, despite the command having passed the
qualification checks. These missing fields match the production defect below.

The original full traffic capture/packet, its producer generation, native
acquisition, publication-return and first delivery are **not retained for this
fault**. The significant receipt near 1219.8 s is about 21 seconds earlier and
cannot fill those fields. The summary row at 1240.7562 s is completion-time
sampling of an earlier command, not proof of a post-expiry positive write.
The first rejected longitudinal sequence itself is not present in this fault
receipt; the comparison is identified by its complete authority, SDK frame,
original observation/computation and deadline, not a guessed later sequence.
Its approximately 367 ms gap does not isolate CPU, IPC, scheduling or GC.
Only seven detailed safety writes remain; they cannot reconstruct the preceding
pedal chronology. No initiating actor pose or signal state is invented.

The retained summary covers 29.9094 seconds but explicitly marks itself
incomplete: 536 summary capture failures, zero capacity drops in its regular and
change rings. Detail reports 1,164 aged/dropped events. These losses are not
zero-valued measurements or evidence of no braking. Their missing data cannot
be recovered from an unrelated export.

The dense recording shows Map continuing nearby: publication 2464 completed
at 1240.6948083 from original observation 1240.6738958; publication 2466
completed at 1240.7709358 from observation 1240.7445940. Actual preceding
Map tick records include their start/end, CPU, post-publication and next-tick
gap. They refute a steering 500 ms outage at this rejection; they do not identify
the traffic producer's missing internal timing. Sampled packet observations
are not misrepresented as first delivery or a complete cadence trace.

## Proven defects and correction

1. **Validated envelope lost during Engine selection.** `_engine_decision`
   reduced a qualified executable packet to pedals/context/times and omitted
   `valid` and `decision_source`. If it expired later during steering I/O or
   diagnostic binding, `handoff_decision` called the shared refresh validator,
   which correctly requires `valid is True`. It therefore rejected every such
   selected result before checking for new evidence. The final gate turned a
   potentially recoverable boundary race into a technical control stop.

   Selection now retains the original validated schema, validity and decision
   source. All dependency, identity, time, drivetrain and final write checks
   still apply. No old expiry/frame/observation is changed. The existing
   handoff may emit only a **new zero-drive transition**, or the current urgent
   brake; the whole Policy/ACC/AP decision must be recomputed before drive
   resumes. Its deadline remains original expiry + 100 ms, never now + 100 ms.

2. **First prewrite failure lost consumed diagnostic inputs.** Safety writes
   copied the initial unbound journal source instead of the current immutable
   arbitration trace. The original selected result and consumed producer
   inputs could disappear before the first active output bind. Safety binding
   now uses that already consumed trace, retaining the rejected selected result
   as `rejected_decision` separately from the original Autopilot `requested`
   packet and newly selected safety pedals. Final
   rejection stores the actual `CommandObservation` pairing, not later SDK data.

3. **Receiver timing was absent.** Existing diagnostic traces now include a
   fixed-size `input_read_timing[source]` array:
   `[read_started_at, accepted_read_returned_at, accepted_check_at, reread_count,
   sdk_frame_us, original_observation_timestamp, computed_at, expires_at]`.
   Reads are sampled receiver events, not producer time or first delivery. A
   bounded `refresh_evidence` records the refresh check and qualified source-read
   return (including that reader's validation, not first delivery),
   original deadline, replacement deadline and whether newer live evidence was
   observed. There are no new SDK/IPC reads, queues, workers or per-tick INFO
   messages; existing snapshot limits and codec/atomic hash export apply.

An experimental extra 50 ms reserve check at physical I/O was **REJECTED**:
it withdrew still-valid drive in the unchanged Map-preparation regression
`test_preparation_lease_through_real_map_policy_acc_ap_engine_backend`.
The original safety expectation was preserved; the experiment was removed.
The final check remains actual original expiry, not an invented earlier timeout.

## Reproduction and verification

`tools/reproduce_oct15_baseline.py` loads `3ee9786` modules in memory, without
editing any checkout. The same new tests run real native reader/selector or
signal producer, Policy, ACC, AP, Engine and the actual Controller/SCS writer
with an isolated byte mapping. These are software-operation/SDK models, not
proof of game consumption or truck dynamics.

Final complete suite: **2,663 passed, 1,592 subtests passed**, 724.94 s.
`full-suite-v3.verified.json` binds all 16 runtime/changelog hashes before and
after that run. No runtime changed afterward. Log SHA-256:
`8b160f53e28f3439d2b98de0215663c4224a4f6ba9188c45960134fdd1c7b0db`.
The earlier selected integration run passed 265 tests; the final export/hold
selection passed 74. Counts overlap and are not summed. The final frozen
baseline run produces **10 failures / 20 deselected** on unchanged `3ee9786`,
while all 30 new tests pass in the complete candidate suite. `compileall` and
`git diff --check` pass. No original safety expectation was weakened.

The rejected reserve experiment and two interrupted full runs remain preserved
as evidence, not reported as PASS. The first was stopped after reproducing its
Map-regression failure; the second was stopped to finish the exact original
versus rejected export binding and receiver timing. Only v3 is the final full
verification. Benchmarks ran outside that final suite.

### Paired results on the declared models

Criteria were the existing contracts: no expired positive write, no positive
throttle/brake overlap, unchanged authority during a qualified bounded renewal,
no renewed wait deadline, preserved emergency/true loss rejection and physically
continuous service brake during waiting. Existing tests were not weakened.
The extra reserve experiment failed an existing criterion and was removed.

| Property / scenario | Baseline `3ee9786` | Candidate | Evidence / verdict |
| --- | --- | --- | --- |
| New late-boundary/snapshot counterexamples | 10 failures | pass in targeted run | same assertions, both automatics; OFFLINE VERIFIED |
| Repeated boundary renewal | technical stop at first induced race (0.7512 s from fixture start) | 125 renewals and 5 red/hold/green cycles, 78.4968 s, 0 technical stops | each mode, actual automatic capture on/off; OFFLINE VERIFIED |
| Still-valid short remaining lease | original expectation retained | positive write remains allowed only before its original expiry | no artificial extra timeout |
| Newer native actor source, same content | false technical stop | zero-drive handoff; later fully recomputed drive | actual native reader/selector + Map fixture |
| Newer native actor source, urgent danger | technical fault even though safety subsequently brakes | immediate brake 1, throttle 0, no spurious technical stop | current content re-evaluated; not old command relabeling |
| Missing/stale/future/invalid/foreign input, R | protected | protected | negative flow and unchanged safety regressions |
| Unrecoverable final fault | initial binding lost consumed inputs | original AP packet, rejected Engine result and actual safety output retained separately | automatic background export + codec/hash readback, full-sized identities |
| Steering benchmark | 16 established cases | all case metrics exactly equal | no lateral/geometry/dynamics edits |
| Longitudinal comfort benchmark | 12 established cases | all case metrics exactly equal | no PID/acceleration/mapping tuning |

The long renewal model starts from the actual N/launch producer path, varies
the content during I/O, and verifies chronological physical byte-mapping
pedals. Its speed/gear are controlled SDK inputs, not an ETS2 dynamics plant.
Signal cycling exercises red braking, ratio zero, continuous physical brake,
same-head fresh green and existing restart without another N. It does not prove
the game's continuous consumption or real brake/gear semantics.

### Independent cadence and IPC

The separate 75.016 s run uses actual Map, Policy, ACC, AP, Engine, Controller
and copying Manager-like RPC semantics: SDK 33.333 ms, Map 360 ms, traffic
460 ms, Policy 59 ms, ACC 23 ms, AP 26 ms, Engine nominal 60 Hz. Jobs do not
catch up in an unbounded queue. Every get/set costs 0.2 ms and initial phase
is 7 ms; all phases/other RPC costs are additionally exercised by existing
cadence regressions. This models timing, not measured process scheduling.

Baseline and candidate distributions below are **identical**, with actual
automatic capture off and on separately. This ordinary cadence scenario already
worked on baseline; the corrected failure is the independently injected final
boundary race above. It would be incorrect to claim every row improved.

| Metric (ms) | n per case | min | p50 | p95 | p99 | max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Remaining lease at ACC/AP publication completion | 2,337 | 2.600 | 207.600 | 389.400 | 425.200 | 430.600 |
| Remaining lease at first sampled Engine receipt | 1,168 | -5.200 | 198.800 | 381.200 | 384.800 | 422.800 |
| Remaining lease at actual pedal-write receipt start | 1,168 | 48.000 | 187.200 | 369.600 | 373.200 | 411.200 |
| Original observation age at write | 1,168 | 44.000 | 47.200 | 65.000 | 66.200 | 68.600 |

An expired received candidate is not an executed candidate: existing bounded
renewal can withdraw drive and await a new complete producer decision.
Neither run has expired write receipts or technical stops. Job counts per
case are identical: SDK/ACC/AP 1,169 each, Map 185, traffic 152, Policy 800,
Engine 1,168. Diagnostic timing additions perform no extra SDK/IPC reads.

In the explicit late-race candidate, minimum write reserve is **98.8255 ms**;
maximum observation age is **101.1745 ms**, p50 zero, p95/p99 101.1745 ms.
This includes new zero-drive transition receipts as well as normal writes;
it is not a claim that an old positive command was given 100 ms extra life.
Every actual positive output is validated against its own original deadline.

### Runtime overhead and memory limits

Equal-length ordinary-flow comparisons run 200 measured flushes after 20 warmup
ticks, twice per variant, outside the full suite. The unbounded test combined
sink is excluded. Automatic capture is genuinely disabled through its wrapper
switch for the off case, not just `journal.enabled=False` (the wrapper resets
that field). That old test-model mistake is corrected in the cadence fixture.
The 64 KiB detail ring is unchanged; no new ring/queue/worker is allocated.

| Capture / repeat | Baseline p50 / p95 / p99 / max (ms) | Candidate p50 / p95 / p99 / max (ms) |
| --- | --- | --- |
| off / 1 | 0.7800 / 0.9048 / 1.0775 / 13.4079 | 0.8724 / 1.1193 / 2.5842 / 13.1617 |
| off / 2 | 0.7914 / 0.9490 / 1.1977 / 1.4794 | 0.8478 / 1.0819 / 6.5241 / 22.7422 |
| automatic / 1 | 1.9023 / 2.4002 / 3.1986 / 10.3499 | 1.9833 / 2.2921 / 4.5913 / 34.0210 |
| automatic / 2 | 1.8386 / 2.0537 / 3.2877 / 11.4416 | 1.9522 / 2.0848 / 3.8817 / 24.9210 |

All eight output traces have identical pedal SHA-256
`aaffd8d73100a35d3c4b02a05419112278c272794b385844a7408dc5b3c6d2c2`.
Candidate retained detail reaches 65,535 / 65,536 bytes; off is zero. Capacity
eviction remains explicit; this is ring accounting, not total Python RSS or
the test framework's history. Existing 1 MiB summary and pending-receipt limits
remain unchanged. No claim of lower tail latency is made: ordinary maxima are
up to 34.021 ms, and the separate long recovery run observes **134.4257 ms**
in one automatic-capture flush (p99 5.0117 ms). That outlier is retained and is
not attributed to historical IPC/GC without a matching trace. Process CPU clock
resolution is 15.625 ms in these samples and cannot isolate sub-ms CPU cost.
The wall measurements include test doubles and OS scheduling; their tails are
an explicit performance limitation, not a hidden PASS or a new 500 ms timeout.

## Related incidents and remaining uncertainty

- This correction covers late dependency expiry **after successful Engine
  selection**, regardless of which qualified leaf owns the deadline. It does
  not assert that every historical stale/needs-refresh fault had this cause.
- Earlier command-ahead observation pairing, initialization identity, Map
  geometry/topology caches and evidence-worker fixes remain in place and are
  regression-tested. Steering loss and genuine 500 ms evidence loss still stop.
- Eight significant-event originals occupy 6,614,998 bytes. The existing
  eight-file quota is reached even though the 16 MiB byte ceiling is not.
  Nothing is deleted/archived or overwritten. Existing one-pending-receipt and
  priority automatic fault export remain available; normal significant export
  needs separately authorized archival, not a raised limit.
- No calibrated physical jerk, certified traffic coverage, native GPS arrival
  completion or universal reliability claim is made. Those are outside this fix.

## Deployment status

Nothing is installed, committed, pushed, armed or operated in ETS2. The final
candidate is hash-bound to the successful complete suite, retaining the
receipt-verified unchanged DLL rather than distributing a replacement. Prior
v5 and all original evidence remain intact. New game behavior remains
**GAME NOT VERIFIED**; no further drive is requested in this task.

Candidate:
`docs/steering-audit/oct15-traffic-lease/ultrapilot-oct15-traffic-lease-candidate-v1.zip`,
183,736 bytes, 16 payloads plus manifest, every payload SHA-256 rechecked after
ZIP readback. ZIP SHA-256:
`e1ba8f3dc633f724fb198dc8324edfdc476aa38ebe7eea52383042a6870044aa`.
Sidecar: `ultrapilot-oct15-traffic-lease-candidate-v1.manifest.json`.

The coherent payload contains Engine/longitudinal plus the existing
`acc_acceleration`, `acc_body_prediction`, `acc_following`, `control_timing`,
`pid`, `service_brake_hold`, navigation `traffic_producer` /
`longitudinal_diagnostics`, SDK `traffic_snapshot` / `scs_sdk`, `telemetry`,
ACC and DrivePolicy runtime dependencies, and changelog. Only
`core/engine.py`, `core/longitudinal.py`, `PLUGIN_CHANGELOG.md` differ from the
installation. The manifest binds all 31 required base file hashes, versions,
source HEAD and uncommitted status. There are **no DLL payloads**, tests,
reports, settings, cache, commit marker or raw evidence in this ZIP.

V5 is retained as the installed baseline and original evidence. This candidate
supersedes it only for review. Any later deployment requires separate approval,
both applications off, a whole-set rollback backup, unchanged base checks and
per-file verification. No deployment is authorized by a candidate manifest.

## Reproducible files

- Runtime changes: `core/longitudinal.py`, `core/engine.py`.
- New production-flow/automatic-export counterexamples:
  `tests/test_oct15_traffic_refresh.py`. Corrected off/on test-model switches
  and added p99 reporting: `tests/test_longitudinal_handoff_cadence.py`.
- Read-only original decoding/hash/timeline analysis:
  `tools/analyze_oct15_traffic_lease.py`.
- Frozen baseline counterexamples: `tools/reproduce_oct15_baseline.py`
  (an expected nonzero result on `3ee9786`, not a candidate PASS).
- Paired recovery, ordinary overhead and cadence:
  `tools/benchmark_oct15_refresh.py`, with default, `--steady` and `--cadence`.
- Existing unchanged benchmark tools: `tools/run_steering_bench.py`,
  `tools/run_longitudinal_comfort_bench.py`.
- Hash-bound ZIP preparation only: `tools/prepare_oct15_runtime.py`, after
  `tools/verify_oct14_candidate.py` has completed the explicitly authorized
  full suite against before/after runtime hashes. Its historical filename does
  not identify the new build; the new receipt carries the actual source hashes.
- Documentation: this report, `DEFERRED_WORK.md`, `PLUGIN_CHANGELOG.md`.

All generated traces, benchmark JSON, logs, verification receipts and candidate
artifacts remain ignored under `docs/steering-audit/oct15-traffic-lease/`.
Neither tests nor raw evidence are shipped as runtime files.
