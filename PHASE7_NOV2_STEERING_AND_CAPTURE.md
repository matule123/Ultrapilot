# November 2 steering preparation and incident capture

**Final diagnostic/control candidate: OFFLINE VERIFIED / READY FOR CONTROLLED
CAPTURE under the conditions below. GAME NOT VERIFIED. Nothing deployed.**
The current installation separately requires verified archival before the next
32 MiB export; its free disk space alone is not a readiness verdict. Historical
timeout inner-phase attribution and six original AP failure causes remain
unknown; this is not a claim that every historical behavior is explained.

## Scope and evidence identity

Targeted correction of the 2026-11-02 15:57:52 local intervention. No deployment,
game operation, ACC/AEB tuning, signal rule, gearbox rule, geometry or timeout
change. Preserve all originals and unrelated dirty-tree changes.

The installed receipt SHA-256 is
`369468031ce54833f78bf9eda74d828ae4e3b984bd8813fa7cf82a1a0d228aa8`.
All 57 recorded files match their actual bytes. Its diagnostic overlay is
`UP-OCT29-REACTIVATION-02`, installed 2026-11-01 according to the receipt.
This supersedes the earlier handover's then-true NOT DEPLOYED description.
The candidate uses that complete installed Python base, not unrelated working
tree control changes. Exact hashes, derived read-only inventories and decoded
evidence are under `docs/steering-audit/nov2-sdk-preparation/`.

## First intervention and secondary ACC rejection

| Evidence | Original monotonic time / value |
| --- | --- |
| Last cited valid Map calculation | sequence 4018; SDK frame 369535218; observation 4814.1684307; computed 4814.2076927 |
| Its preparation | tick start 4814.1722717; lane update end 4814.1916586; reference end 4814.2066086; publish start 4814.2116374 |
| Engine comparison | checked 4814.4700406; observation age 301.6099 ms, below 500 ms |
| First recorded fault | Engine at 4814.5276741: `steering calculation rejected: SDK frame did not advance after steering preparation` |
| Later telemetry in that receipt | frame 369835206, observation 4814.4830887; not the original comparison snapshot |
| Secondary ACC fault | at 4814.5763573; target 79, crossing, original native owner witness unavailable |
| ACC timing | observation 4814.5329466, computed 4814.548469, checked 4814.5621294, expires 4815.0329466; 470.8172 ms remaining |

The recorded Engine comparison uses the previous Map packet. The separate
receipt telemetry was acquired later; it cannot prove which observation Map
could read at the rejected attempt. Passive timing confirms that telemetry and
subsequent Map calculations continued. The exact failed attempt's own reads,
CPU/wait breakdown and publication sequence were not stored. Therefore no
historical SDK outage, GC pause or exporter-induced Map stall is asserted.

### Proven code defect and repair

Map correctly refuses to compute new steering from an unconsumed frame whose
preparation age exceeds the existing dynamics budget. It incorrectly applied
that attempt's failure to the previous independently fresh calculation:
`_reject_steering_observation` copied the old packet, set `authority_valid=False`
and cleared `nav_active`. The packet's original clocks remained young, but its
new invalid bit immediately caused Engine to stop.

Map now defers that new calculation, preserving the predecessor only when its
original frame is the last accepted frame, identity matches and both original
observation/computation ages remain within the unchanged 500 ms limit. It does
not compute, publish or retimestamp a replacement command. Actual stale/future,
same-frame mutation, frame regression, revision/session changes and telemetry
failure still reject; consumers retain final physical-write checks and live
LaneId checks. No unbounded retry or new control regulator is introduced.
The existing completed-tick timing carries a small deferred-attempt record into
the next packet, retaining the original rejected attempt times and previous
sequence without altering the previous packet.

### ACC boundary

Engine `_route_lead_observation` requires a valid identified current Map packet
before projecting native actors. The invalidated packet makes it return
`route_unavailable_or_ambiguous` without an owner witness/source acquisition.
ACC then rejects its retained crossing owner. This exact secondary code path is
reproduced; preserving the still-valid original Map calculation allows actual
maximum-population native-model projection to continue. It does not prove that
actor 79 physically disappeared or that its historical path was clear. There
is no ID-79 exception, inferred clearance or relaxation of owner continuity.
The original first Engine reason and later AP reason remain distinct evidence.

## Capture failure and actual disk capacity

The current installed store contains 113,729,235 active bytes against 134,217,728
bytes (128 MiB), and 174,698,136 archived bytes against 536,870,912 (512 MiB).
The next Engine reserve is 33,554,432 bytes. Free filesystem space is ample;
the active diagnostic quota, not disk exhaustion, prevents the next export.

The active-counted standalone files are:

| File suffix / identity | Bytes |
| --- | ---: |
| AP d8f…-11495 | 7,959,886 |
| AP d8f…-14102 | 18,870,696 |
| AP 55bf…-15672 | 29,595,160 |
| Oct29 13:05:06 manual-disable devinputs | 16,338,674 |
| Oct29 17:09:56 manual-disable devinputs | 18,822,311 |
| Nov2 14:57:14 manual-disable devinputs | 22,142,508 |

All root main dossiers had already been archived. `_archive_incidents` only
iterated such mains, so the counted standalone files could not free capacity.
The new regression fails before and passes after a diagnostic-only repair:
hash-verified standalone `devinputs` replays without a live dossier reference
can be moved recoverably into the existing archive. Their original bytes/name
are preserved and read back by SHA-256. AP prerequisites are not moved or
deleted, no quota increases, and corrupt or over-budget evidence still blocks.

Read-only preflight `tools/preflight_nov2_capture.py` identifies one sufficient
candidate: the 16,338,674-byte Oct29 13:05 replay. Its outer hash is valid;
moving it would leave 97,390,561 active / 191,036,810 archived bytes, sufficient
for the unchanged next reserve. This is a plan, NOT a performed move or capture
authorization. The installed store is **not ready without archival**. Pending
AP parts and original logs remain untouched.

### Worker timeout: established versus unknown

The log records a busy one-job AP writer, a dropped ordinary replay request,
then `INCIDENT_EXPORT_WORKER_TIMEOUT`. That timeout covers child result
completion; the historical log does not name its internal phase, CPU time or
lock owner. It must not be relabeled as a disk-lock timeout or asserted to be
the cause of the Map stall.

Offline profiling uses the exact stored 1,359 AP records, reconstructed into
the same simple-record internal representation. Instrumented export is
25.6870 s wall / 25.5156 s process CPU; readback 11.478 s, typed-JSON packing
8.734 s, with substantial exact-record validation. These are inclusive
instrumented operation costs, not control-thread overhead, and do not reproduce
the 60 s timeout. An earlier expanded-record probe used a different legacy
path (20.3901 s); it is explicitly not a comparable simple-record baseline.
No arbitrary timeout increase or speculative codec replacement is made.

An additional profile reconstructs the actual archived Engine group plus its
exact AP part. One late assembly previously decoded both immutable replay
files twice: **15,188 exact records**, 39.920 s cumulative profiled operation
time. After correction it decodes **7,594 records**, 25.490 s cumulative
profiled time (25.6294 s wall / 25.2188 s process CPU). The final assembled
manifest bytes are identical before/after, SHA-256
`4ed29d240085a819d6ceb51a784ec5143faff8244eb07db85b63b79781f94cf2`.
This identifies real redundant work; it does not establish the historical
worker's exact phase or add separate profiled costs into a claimed live timeout.

The repair reuses at most two decoded replays during one assembly operation,
tracking at most 64 MiB of source-file bytes. EVERY access re-reads and hashes
current bytes; there is no mtime cache, process-global retention or mutable
producer reference. Requests, exact command lineage, failure counters and
manifest/attachment hashes are still checked. The cache uses only the existing
export child, under its unchanged 1,536 MiB RSS ceiling. Wire format and all
runtime/disk quotas are unchanged. A failing-before decode-count regression
now passes (four decodes → two). Corruption between attachment and final
readback, changed bytes, foreign requests and fixed cache bounds are tested.
The old dossier correctly remains incomplete with its original six failures.

### Six AP capture failures

The valid AP file `...-15672` belongs to the earlier 4723.6465704–4774.3781654
request. Actual rows span 4723.1696223–4770.2555086, with six aggregate capture
failures and zero capacity drops. Its per-row failure counts are empty; the
stored aggregate does not identify which producer/retention exception incremented
it. It is incomplete and cannot stand in for the fault at 4814.5. Neither the
six failures nor the missing tail is erased by integrity validation or a later
packet. Exact exception attribution is historically unavailable.

## Verification and candidate disposition

Two original preparation reproductions fail before repair; the expanded
both-mode reproduction also fails on the exact installed-base Map. Afterward
20 focused lifecycle/negative cases pass, including actual maximum native
traffic projection and Controller mapping outputs. The existing fresh-handoff
and post-localization suites produced 34 passes in the initial check. The
standalone quota reproduction fails before; its repair and neighboring
archive/late-assembly suites produced 38 passes. No whole pytest run.

The first newly written process test exposed a **test setup error**: its 510
ticks used the fixture's real 33.333 ms period (17 s), not the assumed 100 ms,
and its deliberately stale-input fault inserted an actual 501 ms evidence gap.
It correctly remained incomplete. The corrected model warms over 30 s and
uses a genuine reverse-gear fault for the continuity qualification; real stale
inputs remain separately tested. Completeness expectations are unchanged.

The next run identified a 303 ms ego gap caused by the test advancing Map's
fake clock without allowing independent Engine observations. The final model
instead performs actual Engine telemetry/native/pedal publication at 50 ms
steps while Map retains an earlier in-flight envelope. Both automatic modes
then produce complete Engine/AP dossiers, approximately 30 s pre / 11.07 s
post. The same full Windows daemon/Manager scenario fails on the original
installed runtime at prior-packet invalidation. The 250 ms gap criterion is
unchanged. These are declared models, not reconstructed actor-79 poses.

An intermediate runtime passed 160 neighboring tests / 984 subtests before
the assembly reuse fix. Its stage `release01/` is preserved, superseded and
has no ZIP. Final runtime is separately frozen as `UP-NOV2-PREPARATION-02`
under `release02/`, changing only Map 1.1.3, core replay diagnostics and the
temporary build identity. Engine, ACC, DrivePolicy, hold, controller and DLL
remain exact installed-base bytes.

The final selection produced 162 passes / 984 subtests and four test-order
failures. Detailed counters identify registration saturation, not an evidence
gap or a weakened integrity test: retired Plugin/assembler/mock cycles from
previous tests occupied all 16 weak compression slots. Test-boundary cyclic
collection changes 16 registrations to zero (81,713 unreachable objects), and
the same short order passes. A diagnostic-test fixture now collects unreachable
previous models before a new independent test, without clearing registries or
counters, changing runtime GC, changing limits or collecting inside measured
ticks. The full affected order plus the failing long-episode module passes:
**86 tests**. The runtime bytes did not change during this isolation correction.
This is not asserted to explain the six historical AP failures.

## Final frozen qualification

The unchanged existing maximum-load qualifier runs four independent Windows
spawn/daemon/Manager cases, 1,400 ticks / 70 modeled seconds each. Each uses
40 moving + 40 parked records, three supported moving trailer slots, leader
change/crossing, signal wait/resume, combined collection and overlapping export.
Model outcomes do not replace an ETS2 measurement. All original numeric gates
pass; `release02/load-qualification/assessment.json` has no failures. Criteria
SHA-256 remains
`7a74d5032dabb5264c5d13bd8a1895adf335768f6a8b3be45cda2f1c480567ff`.

| Mode / capture | Whole tick p50 / p95 / p99 / max (ms) | Engine flush p99 / max (ms) |
| --- | --- | --- |
| Simple off | 10.233 / 15.510 / 17.581 / 26.525 | 7.703 / 15.307 |
| Simple on | 12.980 / 17.989 / 20.197 / 39.275 | 8.460 / 23.538 |
| Real off | 10.823 / 15.541 / 17.232 / 25.512 | 7.385 / 10.428 |
| Real on | 13.266 / 16.718 / 18.653 / 31.522 | 7.277 / 18.031 |

Added whole-tick p99 is **2.616 / 1.420 ms**, below the unchanged 8.33 ms gate.
Whole p99/max remain below 50/100 ms; Engine p99/max below 16.67/50 ms. Ring
lock wait p99 is 0.0014 ms in both modes; maximum 0.400 / 0.3041 ms, below the
unchanged 1 / 5 ms gates. There is no control-thread export I/O/wait. Runtime
and exporter concurrency/memory are sampled at 20 ms by the existing monitors.

| Evidence/resource | Simple / real result | Verdict |
| --- | --- | --- |
| Actual warm window | Both 30.00 s pre + 15.55 s post, with complete exact AP attachment | PASS (model) |
| Full physical pedal detail | Both 1,927 exact calls across 45.55 s; no missing decision/input references or sequences | PASS (model) |
| Original native samples | Both 456 exact periodic captures checked, with original bytes/clocks/identity | PASS (model, original sampling contract) |
| Capacity/capture losses | Zero in both qualified windows and rings | PASS (model) |
| Outputs, decisions, reads | Identical off/on; 575,175 / 554,986 logical reads, no positive pedal overlap | PASS (model) |
| Ring held high-water | Engine 39,490,782 / 39,118,081 B; AP 7,700,550 / 7,548,662 B | PASS |
| Runtime parent conservative upper | 320.324 / 334.906 MiB; additional parent 179.977 / 194.742 MiB | PASS |
| Child / runtime family conservative upper | Child 1,083.863 / 1,066.211 MiB; family 1,404.188 / 1,401.117 MiB | PASS |
| Concurrent children | At most one; no exporter errors/timeouts in final runs | PASS |
| Output directory size | 38,037,649 / 37,366,698 bytes including component files | Measurement |

Memory remains inside the approved additional-parent 512 MiB, child 1,536 MiB
and additional-family 2 GiB limits, with unchanged Engine/AP 64/32 MiB rings and
32 MiB Engine-file bound. The supervisor's raw host peaks (968,228,864 /
956,813,312 B) include offline inspection; runtime in-host peaks are separately
229,031,936 / 226,807,808 B. They are not conflated or hidden. Source-file cache
accounting is not a claim that decoded Python trees occupy only 64 MiB; actual
child RSS is measured and constrained by the existing child gate.

Final proof: `release02/qualification-result.json`. All 57 installed receipt
entries, 124 unchanged installed Python dependencies and eight original
evidence files are verified. Compileall and `git diff --check` pass. Final
runtime's entire selected run has 162 passes / 984 subtests plus the four
explicit test-isolation failures above; all affected order tests pass in the
86-test recheck on the **same runtime hashes**. No safety assertion was removed,
no skip/xfail added, and no full pytest rerun. The actual full daemon episode,
red/wait/green, native owner/AEB and negative-control scenarios pass in the
selected run. Do not sum overlapping test counts into a fictitious suite total.

## One package and rollback

Directory: `docs/steering-audit/nov2-sdk-preparation/release02/`.

| Archive | Bytes | SHA-256 |
| --- | --- | --- |
| `ultrapilot-nov2-preparation-02-candidate.zip` | 65,526 | `c9a5f2b00aca22e109555d0ef119de1fbd22783070063910c7e6471c6c027376` |
| `rollback-installed-base.zip` | 62,728 | `1b10d46f69a3df8d87676336e7b790c0a655cb4304cc20db94e5f47a4272a661` |

Runtime payload is exactly:

- `plugins/map/main.py` — Map 1.1.3, preparation deferral;
- `core/steering_replay.py` — recoverable standalone archival and bounded
  exact-content assembly read reuse;
- `core/navigation/diagnostic_build_config.py` — temporary identity
  `UP-NOV2-PREPARATION-02`, same approved options/budgets.

The candidate includes its manifest and qualification; rollback includes exact
installed originals and the original receipt. No DLL, tests, raw data or dirty
unrelated runtime changes are bundled. `release01/` is a superseded unreleased
stage, preserved without a ZIP. The old installed diagnostic build remains
the current installation until separate explicit approval.

## Conditional deployment and capture procedure — not executed

1. Obtain separate deployment approval and confirm UltraPilot and ETS2 are
   stopped. Reverify the parent receipt and all 57 installed base files; stop
   on any drift. Verify both ZIP hashes and their internal payload hashes.
2. Keep rollback separately. Stage/extract the candidate and copy only its three
   runtime entries as one stopped-application transaction. Verify destination
   hashes and write a truthful receipt linking the parent receipt, exact payload
   and uncommitted-source provenance. Preserve settings, map cache, originals
   and commit marker. On any failure restore all three originals and original
   receipt before restarting; do not restore only the last copied file.
3. Before any capture, run the read-only preflight:

   ```powershell
   cd 'C:\Users\PC\Documents\GitHub\ets2la'
   $env:PYTHONCASEOK='1'
   python -m tools.preflight_nov2_capture --directory 'C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics'
   ```

   At this audit the required action is verified recoverable archival of the
   identified old standalone replay, not deletion or a quota increase. With
   applications stopped, the qualified candidate's `_archive_incidents`
   operation can perform this plan under its existing diagnostic disk lock;
   inspect/read back the archived hash and rerun preflight before proceeding.
   This preparation has NOT performed that move. A changed plan or full archive
   is a STOP condition; deleting unique originals needs explicit permission.
4. Only after approval, successful installation and capacity preflight, a future
   short user-operated capture uses normal startup, no arm command. Allow at
   least 30 s of live unpaused history, drive normally with a valid GPS route,
   include a safe manual disable/new N and a naturally encountered red/wait/
   green/resume when available. Do not provoke an emergency or collision.
   Wrong behavior requires driver takeover immediately.
5. Keep application and live telemetry running at least 10 s after the final
   disable; let the existing background export/assembly finish before shutdown.
   Inspect main/assembled manifests and every continuation with the matching
   runtime. Require actual Engine/AP coverage, original command/input/pedal
   links and zero unexplained losses, not just a valid hash. Pause, early exit,
   true loss/overload or an export failure remains explicitly incomplete.

No new driving attempt is requested now. This candidate repairs the reproduced
Map invalidation, quota dead-end and redundant assembly work. It does not
recover historical missing observations, prove actor 79's exact physical
situation, explain the six aggregate AP exceptions, or guarantee future
export latency in ETS2. OFFLINE VERIFIED is not GAME VERIFIED.
