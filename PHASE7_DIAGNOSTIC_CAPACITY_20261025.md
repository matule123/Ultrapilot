# Final diagnostic capacity correction — 25 October 2026

**Historical build-03 qualification; superseded for collection readiness.**
Populated-traffic testing found additional export failures and unmet timing
criteria. The current build-04 handover is **BLOCKED**, documented in
[PHASE7_DIAGNOSTIC_TRAFFIC_QUALIFICATION_20261025.md](PHASE7_DIAGNOSTIC_TRAFFIC_QUALIFICATION_20261025.md).
The zero-actor capacity results below remain valid in their measured scope;
they do not certify the later populated-traffic timing requirements.

**OFFLINE VERIFIED at the reproduced load. GAME NOT VERIFIED. Nothing deployed.**
Only the existing diagnostic window, assembly and export are changed. Control
decisions, regulators, original SDK clocks/frames, 500 ms freshness, sampling,
DLL and plugin VERSION declarations are unchanged. Existing workspace repairs,
installed files and original evidence are preserved.

This is the current handover. Build-01 and build-02 artifacts and
[PHASE7_INCIDENT_ASSEMBLY_20261025.md](PHASE7_INCIDENT_ASSEMBLY_20261025.md)
are superseded historical evidence, not installation alternatives.

## Capacity failure: load, evidence and required window

The exact previous production benchmark was repeated: **900 ticks at 50 ms,
45 s of modeled time**, Engine traffic publication **20 Hz**, original ring
period **100 ms plus state edges**, native moving/parked buffers **6,960 +
1,720 bytes**, **zero actors**. Both automatic gearbox modes run the same
scripted driving/braking/wait/green cycles, real Policy/ACC, AP, Engine,
Controller and test backend with diagnostic exports in flight.

This was not the separate synthetic 80-actor tap benchmark. Capacity failed
even at the zero-actor production load because large nested consumed decisions
and their producer inputs were retained repeatedly as expanded Python trees.
The original ring charged those owned copies against its fixed 32 MiB budget.

The old enabled simple-mode remeasurement retained only **17.0 s** of ego,
native signal, traffic, command-pair and producer-consumption streams; selected
summary streams spanned 17.1 s. Therefore **30 s before + 10 s after was violated**,
not merely conservatively labeled incomplete. Both old-mode regression tests
failed on actual capacity evictions: **3,634 / 3,491**. Evidence:
`docs/steering-audit/oct25-incident-assembly/capacity-before.log` and
`capacity-before-measurement.json`.

Acceptance was set before the fix: same load and original sampling; zero Engine
capacity/capture losses; at least 39.9 s of each continuously produced ego,
signal, traffic, command-pair, consumed-decision and output-summary stream;
same physical output and IPC reads. The 0.1 s tolerance reflects the existing
100 ms sampling phase, not a changed timeout or reduced retention request.

## Exact correction within the unchanged budget

Large owned window values (at least 8 KiB) now use lossless compressed internal
retention **only when it saves space**. Original bytes, missing values, field
values, identity, frame and times are preserved. The same 32 MiB ring and pinned
pre-window budgets, sample period and state-edge capture remain in force.
No record is omitted to obtain the result and no newer packet fills an older gap.

The internal primitive-tree encoding is verified by original length and SHA-256
before expansion. It is created from already owned runtime values, never read
from an external replay. Worker/public-inspection boundaries expand it back
to the original values. Engine transfers the packed immutable window to its
existing exporter; it does not expand the window on the control tick. Final
files still use the existing immutable-reference JSON/raw-byte codec, hashes,
atomic manifest and archive limits. No new collector, SDK/IPC read or queue.

Restored Engine retention exposed one AP boundary record formerly hidden by
Engine evictions: the AP ring could age it out before the next publication
delivered the seal request. The AP ring retains an additional **500 ms of
diagnostic receiver history within its same byte limit**, matching the unchanged
maximum input-age interval. This does not extend control validity or wait for
an expired command. The exact original command still must match the sealed part.
The intermediate failed assembly run is preserved in `final-capacity/` and is
not reported as successful qualification.

## Same-load before/after

All memory figures below are accounted retained ring bytes, not process RSS.

| Property | Before, simple / real | After, simple / real |
| --- | --- | --- |
| Engine byte ceiling | 33,554,432 / 33,554,432 | **unchanged** |
| Engine retained bytes | 33,543,452 / 33,525,068 | **15,967,540 / 15,789,127** |
| Engine retained MiB | 31.99 / 31.97 | **15.23 / 15.06** |
| Capacity evictions | 3,634 / 3,491 | **0 / 0** |
| Capture failures | 0 / 0 | **0 / 0** |
| Continuous ego/signal/traffic retention | approximately 17.0 s in the measured old simple run | **40.1 s / 40.1 s** |
| Command-pair span | 17.0 s in the measured old simple run | **40.1 s / 40.15 s** |
| Consumed-decision span | 17.1 s in the measured old simple run | **40.2 s / 40.2 s** |
| AP retained bytes | 5,095,937 / 4,668,947 in prior build-02 comparison | **5,140,552 / 4,678,075** |
| AP capacity/capture losses | 0 / 0 | **0 / 0** |

The post-fix periodic ego/signal/traffic streams each contain 402 retained rows
with maximum interval 100 ms. Summary/consumption state edges remain captured.
Some consumer-only streams have no read in certain modeled handoffs (real-mode
command-pair maximum interval 450 ms); no synthetic sample fills that absence.
The byte-capacity defect is corrected; these original consumption gaps remain
visible and completeness remains conservative.

The early startup dossier in this benchmark is still incomplete because there
was no 30 s pre-start history. Its parts are assembled and capacity loss is zero.
This is not presented as a complete cold-start recording. The subsequent rolling
window after warm-up is the capacity test: all required continuous streams retain
40.1–40.2 s. A new observation cannot manufacture history before startup.

Raw results: `delivered/assembly-overhead.json` under
`docs/steering-audit/oct25-incident-assembly/`.

## Outputs, overhead and final verification

Same script, separate off/on runs; no pytest ran concurrently with the final
benchmark. These are modeled SDK/backend results, not physical ETS2 measurements.

| Mode | Off tick p50 / p95 / max (ms) | On tick p50 / p95 / max (ms) | On, export busy p95 / max (ms) |
| --- | --- | --- | --- |
| Simple automatic | 6.401 / 7.966 / 41.521 | 9.670 / 11.580 / 53.516 | 11.784 / 53.516 |
| Real automatic | 6.300 / 7.566 / 30.104 | 9.288 / 10.755 / 58.549 | 10.758 / 58.549 |

Whole-tick median overhead is **3.269 / 2.987 ms** versus diagnostics off.
Measured enabled-run GC maxima were 42.930 / 49.341 ms. No historical game pause
is attributed to these model GC observations. Maxima are not hidden by medians.
Physical pedal-write hashes and every IPC read count are identical off/on in
both modes; both stay active without an intervention while export runs.
This is not a universal performance improvement: the real-mode maximum exceeds
the prior build-02 run's 46.591 ms. Separate-run scheduling/GC variability and
the full retained-input workload prevent a stronger latency claim.

Final frozen qualification: **186 tests PASS, 10 subtests PASS, 131.04 s**.
This includes the unchanged old export regressions; successful short braking
and red/wait/green/restart without disable in both modes; exact AP matching;
overlap, delayed/failed/missing/corrupt parts; shutdown during assembly; original
capacity load; original-byte/clock retention and internal corruption rejection.
All **141 installed control-function AST comparisons** pass after removing only
observational hooks. `compileall` and `git diff --check` pass. Full workspace
pytest was not rerun.

The six runtime hashes were frozen before qualification, unchanged afterward
and rechecked when packaging. Packaging refuses capacity evictions, capture
failures, less than 39.9 s on the same continuous streams, changed outputs/reads
or unsuccessful qualification. No acceptance threshold was relaxed for PASS.

The six production-overlay tests explicitly require the temporary instrumented
configuration. They all run in candidate qualification. Ordinary workspace
testing has no such overlay: the direct diagnostic tests pass (15), while those
six candidate-only tests skip explicitly. This avoids importing or installing
the candidate implicitly into ordinary source testing. The benchmark was not
rerun after these test-environment declarations: all six runtime hashes stayed
identical, recorded in `benchmark-runtime-equivalence.json`.

Fixed logical budgets remain: Engine ring 32 MiB + pinned pre-window up to
32 MiB; AP ring 32 MiB + pinned pre-window up to 32 MiB; one frozen/retry window
per existing exporter, up to 64 MiB each, with shared immutable references.
The detailed backend ring remains 64 KiB and decision summary 1 MiB. Per-value
capture is bounded at 512 KiB. Export-child/codec/interpreter temporaries are
additional; accounted retention is not a hard process-RSS guarantee.

## The single current runtime package

Build **UP-DIAGNOSTIC-20261025-03**, directory:
`docs/steering-audit/oct25-incident-assembly/delivered/`.

| Artifact | SHA-256 |
| --- | --- |
| `ultrapilot-diagnostic-20261025-03-candidate.zip` | `41ea7f8fec40bd825962952089b77fea569df3e816d2f6ce9b49c56c6d7c0bb1` |
| `rollback-installed-base.zip` | `2b263aae776b31c5f485accf6b614978a49c45aae9b696dfedb1b0b19de4d272` |

The rollback is not a second candidate. Every ZIP member was read back and
hash-checked. All 53 required installed-base hashes and receipt were rechecked.
Base receipt SHA-256:
`61d7bd251991e0933f9f598d80f3620f6f65e581fa68d6a1fb7d4faa59a38935`.
HEAD: `821dedcf1a9642a1f5767538a5daa9833c82d2d2`, with uncommitted changes,
truthfully recorded. The overlay uses installed control implementations, not
the unrelated unfinished driving changes in this workspace.

Exactly six runtime files: `core/engine.py`, `core/longitudinal.py`,
`plugins/autopilot/main.py`, `core/navigation/longitudinal_diagnostics.py`,
`core/steering_replay.py`, `core/navigation/diagnostic_build_config.py`.
No DLL, settings, map cache, tests, reports or verification namespace markers
are shipped. The temporary diagnostic build identifier changes; plugin VERSION
declarations do not change for this diagnostic-only development overlay.

## Use, assembly and rollback — no action performed

After separate installation approval: normal startup, **no arm command**.
Existing automatic export location:
`C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics\`.
The sealed `incident-<ID>.json` manifest attaches exact `ap-inputs-<ID>.json`,
the Engine/journal replay and overview with hashes. It is published only after
required parts have been checked. Missing/failed/late parts or real loss remain
incomplete; a later packet or later application shutdown cannot substitute.
Allow the 10 s tail and background export completion where safe.

Before any separately approved deployment, close UltraPilot and ETS2. Verify
archive and all base hashes, take a fresh timestamped six-path/receipt backup,
apply all six files together and verify their new hashes. Save an accurate
uncommitted-build receipt. Preserve DLL, settings, map cache, evidence and commit
marker. On any failure restore all five previous files and receipt, quarantine
the newly added diagnostic configuration, and verify every original hash.

The reproduced 30+10 s capacity blocker is corrected, not merely relabeled.
This does not guarantee arbitrary actor/input volume, arbitrarily long holds,
power-loss recovery, complete high-rate 64 KiB backend history, traffic coverage
or game consumption. Such limits remain explicit and never grant authority.
No new driving feature, deployment or game test was performed or requested.
