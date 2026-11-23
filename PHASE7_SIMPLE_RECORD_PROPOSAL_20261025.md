# Simple exact-record diagnostic proposal — 25 October 2026

**Historical proposal.** The export-only correction and revised, unapproved
budget are in [PHASE7_DIAGNOSTIC_EXPORT_OVERHEAD_20261026.md](PHASE7_DIAGNOSTIC_EXPORT_OVERHEAD_20261026.md).
The 4 GiB recommendation below is superseded; it was never approved/applied.
Both original and current measured results remain preserved.

**LOSSLESS MODEL PROPOSAL VERIFIED; NOT READY FOR CONTROLLED CAPTURE.**
No production budget was increased, no ZIP was created, nothing was installed,
and no game/AP was operated. This is the single proposed storage/budget design,
not another release or a claim that ACC/game behavior is fixed.

## Identity and independent proof before integration

The exact installed-base overlay is frozen in
`docs/steering-audit/oct25-incident-assembly/simple-record-proposal/candidate-manifest.json`.
All six runtime hashes and all 53 installed receipt files were rechecked.
The installed receipt remains SHA-256
`61d7bd251991e0933f9f598d80f3620f6f65e581fa68d6a1fb7d4faa59a38935`.
Control-function comparison remains 141 AST-equal functions after removing only
observational hooks. Unrelated workspace controls were not deployed or used
as this baseline. No plugin VERSION, DLL, regulator or safety timeout changed.

1. `exact-codec-standalone.log`: **13 independent tests passed before wiring**.
   They compare original types and dictionary order, arbitrary IEEE float bits,
   NaN payloads, negative zero, tuples/lists, bool/int distinctions, clocks,
   frame/identity fields, Unicode and native bytes. Unsupported/coerced types,
   cycles/oversize, truncated/corrupt frames and trailing bytes are rejected.
2. A bounded C ownership copy was then independently tested: a custom producer
   object's reducer cannot run, and the restricted internal reader cannot load
   classes. The source remains an owned primitive snapshot, never a mutable IPC
   reference. Internal pickle frames are **not accepted from external files**.
3. External files use a self-contained, whitelisted primitive-type JSON tree
   per record, compressed and hashed on the existing export worker. No field
   paths, cross-record reconstruction or invented timestamps are used. Existing
   outer file hashes, part hashes, sequence checks and final manifest remain.
   **18 codec/file tests passed**, including real JSON and Engine/AP file
   round-trips and original native 40+40/three-trailer ABI bytes.
4. Only after the independent tests was `SIMPLE_RECORDS=True` added to the
   isolated proposal configuration. Normal source/configuration defaults keep
   it disabled. No rejected transaction, live-row repacking or recursive
   ownership/deduplication patch was applied.

Every record is independent. It owns original values; it does not depend on a
later packet. Original physical calls keep decision/read references, request,
start/return times, values, results/errors and pair evidence. The 64 KiB safety
tail stays separate and may remain short without erasing the full-window call
component. A backend return is not game-consumption confirmation.

## Full production-model window and exact calls

Existing `tools/qualify_oct25_traffic_capture.py`, unchanged scenario family:
1,400 ticks at 50 ms model step (70 s), native **40 moving + 40 parked** records,
three moving trailer slots, lead/crossing actors, a target change, overlapping
subevents and red/wait/green/resume. Both supported automatic modes stay active
without a technical fault. These are scripted inputs, not ETS2 measurements or
a closed-loop vehicle-physics test.

Measurements and frozen runtime/tool identities:
`docs/steering-audit/oct25-traffic-qualification/simple-record-proposal/`.
`proposal-results.json` hashes the evidence and verifies the following:

| Property | Simple automatic | Real automatic |
| --- | ---: | ---: |
| Actual pre / post range | 30.00 / 19.05 s | 30.00 / 19.10 s |
| Exact physical pedal calls / duration | 2,067 / 49.05 s | 2,069 / 49.10 s |
| Missing call sequences / decision / consumed-input references | 0 / 0 / 0 | 0 / 0 / 0 |
| Capacity / capture loss | 0 / 0 | 0 / 0 |
| Engine commands covered by attached AP part | 982; missing 0 | 976; missing 0 |
| Warm dossier completeness and integrity | Complete, verified | Complete, verified |
| Overlapping subevents | 15 | 17 |
| Complete dossier bytes | 41,040,913 | 40,452,569 |
| Sampled high-water Engine ring bytes | 39,141,498 | 38,959,971 |
| Sampled high-water AP ring bytes | 7,673,847 | 7,528,046 |

Native bytes/frame/time/identity are checked against the original capture.
The exact original publisher context **type** is checked too: the new format
preserves tuples where historical JSON converted them to lists. This is a
stronger producer-contract assertion, not removal of an expected identity.
All eight off/on/export/probe runs have identical selected decision, physical
write and native input hashes and identical GET counts (575,175 simple;
554,986 real). No positive pedal overlap or control-thread export file I/O.

The full-window tests used **model-only** Engine ring 64 MiB and Engine file
32 MiB probes. Application source limits are still 32 MiB and 16 MiB. Probe
results cannot pass the release gate. The earlier 16 MiB file run failed the
quota and is preserved, not reported as a complete export.

## Timing: baseline, capture increment and export separately

1,400 whole-tick/Engine samples per row. Values below are milliseconds.
The scenarios ran sequentially, without concurrent pytest. GC stayed enabled.
The original criteria were not relaxed: tick p99 <50/max <100, added p99
<=8.33, Engine p99 <=16.67/max <50. Memory probes are not timing approval.

| Mode / operation | tick p50 | p95 | p99 | max | Engine p99 / max |
| --- | ---: | ---: | ---: | ---: | ---: |
| Simple / no capture | 12.791 | 20.056 | 21.807 | 69.304 | 13.343 / 20.330 |
| Simple / capture, no export | 20.905 | 23.341 | 27.250 | 41.870 | 14.946 / 28.330 |
| Simple / complete export, file-budget probe | 21.349 | 24.752 | 28.278 | 66.755 | 16.446 / **58.556** |
| Real / no capture | 12.346 | 19.432 | 23.649 | 32.306 | 12.950 / 16.275 |
| Real / capture, no export | 20.699 | 23.775 | 26.070 | 37.589 | 15.380 / 21.923 |
| Real / complete export, file-budget probe | 21.240 | 28.213 | 42.412 | 95.284 | **20.145** / 49.908 |

Capture-only p99 increment: **+5.443 / +2.421 ms**. Complete-export contrast
versus capture-only: **+1.028 / +16.342 ms**. Total versus baseline:
**+6.471 / +18.762 ms**. These are quantile contrasts between identical-input
runs, not additive per-tick causal measurements. Complete-export timing is
**NOT QUALIFIED**: simple Engine maximum and real Engine p99/added p99 fail.
Changing memory allowances would not turn those failures into PASS.

**Baseline limits must not be hidden:** earlier baseline-without-capture Engine
maxima were **65.815/58.437 ms**, already above the original <50 ms gate.
The current paired baseline did not reproduce that absolute Engine overrun;
that does not erase the older evidence or prove a deadline guarantee. The
69.304 ms current simple whole-tick maximum exceeds a 50 ms traffic period,
but the predeclared whole-tick maximum gate is 100 ms, not 50 ms.

GC, per-thread CPU, lock and inclusive operation timings remain in the JSON.
Wall minus Windows quantized thread CPU is not measured IPC/GIL wait. GETs use
the in-process test mapping; real Manager/RPC latency is **not measured**.
The mock's unbounded sample history is cleared outside timed ticks; runtime
rings, controller/backend callbacks and export work are retained.

## One proposed fixed budget — approval required, not applied

The simple format needs about **37.33 MiB** of measured Engine-ring retention,
so 32 MiB is not adequate for this representation/load. Proposed bounds:

| Component | Proposed ceiling / rationale |
| --- | --- |
| Engine input ring | **64 MiB**; about 1.7x measured 37.33 MiB high-water |
| AP input ring | **32 MiB**; measured high-water about 7.32 MiB |
| Pinned prehistory | At most one additional Engine/AP ring each: **96 MiB combined** |
| Frozen/retry payloads | One existing job/retry per owner, at most two ring ranges: **192 MiB combined** |
| Engine parent RSS | **512 MiB**, including owned windows, normal interpreter and scratch |
| AP parent RSS | **256 MiB**, including its owned windows and scratch |
| Export children | **At most 2**, one per existing owner, **1,536 MiB each** |
| Diagnostic process-family RSS | **4,096 MiB (4 GiB)**: 512 + 256 + 2x1,536 + 256 shared headroom |
| Engine / AP file | **32 / 32 MiB**, immutable/hash checked |
| Active dossiers / archive | **256 / 512 MiB**, with existing rotation, never source-evidence deletion |

Current complete exports measured parent peaks **216,997,888 / 214,413,312 B**,
largest child **1,118,101,504 / 1,104,646,144 B**, and simultaneous family peak
**1,318,678,528 / 1,302,728,704 B**. Maximum observed children was 2. Per-child
1,536 MiB leaves about 44% over the larger measured child. The family proposal
does not assume their individual peaks cannot overlap: two full child ceilings
are included. Overlapping events coalesce; no extra event queue/process is added.

RSS numbers include interpreter/test-runtime allocations. They are proposed
qualification/operational ceilings, **not OS-enforced memory reservations**.
The family budget covers these diagnostic owners/children; ETS2, Map/other
plugin processes and GPU memory are outside it. This scenario proves 20 Hz
consumption, not arbitrary producer rates or unbounded waits.

This is **one** budget proposal, not permission to apply it. The current
constructor/file quotas, installed config and receipt remain unchanged. The
builder marks `memory_budget_approved=false` and refuses ZIP packaging for
this proposal, regardless of passing codec tests.

## Reproduction and remaining boundary

Use the frozen verification runtime, not the dirty workspace controls:

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python -m pytest tests/test_oct25_exact_record_codec.py -q
python -c "import sys,runpy;sys.path.insert(0,r'docs/steering-audit/oct25-incident-assembly/simple-record-proposal/verification-runtime');sys.argv=['tools/qualify_oct25_traffic_capture.py','--output',r'docs/steering-audit/oct25-traffic-qualification/simple-record-proposal/reproduce-new-real.json','--mode','3','--enabled','1','--export-enabled','1','--capacity-probe-mib','64','--file-probe-mib','32','--ticks','1400','--pace','.005'];runpy.run_path(sys.argv[0],run_name='__main__')"
```

Output paths must be new; prior evidence is never overwritten. For the full
matrix, modes are `0,3`; variants are off (`--enabled 0 --export-enabled 0`),
capture-only (`1,0`, with the capacity probe), and complete capture/export
(`1,1`, with both explicitly labeled model-only probes). The preserved failed
16 MiB export runs stay in the result directory too.

The old nested-sharing optimization reproduction remains red on the legacy
shared-envelope path. It was not weakened, xfailed or reused as proof of this
independent-record proposal. The earlier 413-test result belongs to build 05,
not this design. Six smaller episode/failure tests passed on the intermediate
typed-record candidate; the final eight maximum-load runs and codec/file tests
have their own exact identities. No full repository pytest was repeated.

The standalone/simple-record design and full-window/pedal proof are delivered.
The next decisions are explicit approval of this memory/disk budget and a
separate resolution/acceptance of the measured timing failures. Neither is
assumed. **No final ZIP, deployment or controlled drive is authorized.**
OFFLINE LOSSLESS VERIFIED is not GAME VERIFIED.
