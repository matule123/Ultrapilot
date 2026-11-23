# Diagnostic export overhead — 26 October 2026

**Superseding follow-up:** the user subsequently approved the proposed budget.
Implementation and exact no-override results are recorded in
[PHASE7_DIAGNOSTIC_APPROVED_BUDGET_20261026.md](PHASE7_DIAGNOSTIC_APPROVED_BUDGET_20261026.md).
The text below preserves the earlier pre-approval measurement and decision.

**Status: timing gates pass in the paired model; NOT READY FOR CONTROLLED CAPTURE.**
The exact lossless format is unchanged. Capacity/file sizing overrides remain
unapproved, and the export child exceeds the original 512 MiB RSS criterion.
No ZIP, installation, arming, game execution or plugin release is performed.
The earlier 4 GiB proposal is withdrawn as a current recommendation, not applied.

## Frozen scope and identity

- Installed-base receipt SHA-256:
  `61d7bd251991e0933f9f598d80f3620f6f65e581fa68d6a1fb7d4faa59a38935`.
- Source HEAD: `821dedcf1a9642a1f5767538a5daa9833c82d2d2` plus uncommitted work.
- Exact six-file development snapshot:
  `docs/steering-audit/oct25-incident-assembly/export-overhead-qualified/`.
  Its `candidate-manifest.json` contains every runtime SHA-256 and the installed
  originals. `control-baseline-proof.json` compares 141 installed control
  functions, excluding only the documented observational/export hooks.
- Evidence:
  `docs/steering-audit/oct25-traffic-qualification/export-overhead-qualified/`.
  `runtime-frozen.json` identifies the tested runtime and original criteria;
  `qualifier-used.py` preserves the exact benchmark bytes used by the four
  acceptance runs. Later changes to phase-only instrumentation are separately
  hashed in `phase-profile.tool-sha256` and did not change the runtime.
- The historical `-07` development label alone is not an identity. Earlier
  development directories are superseded by these hashes, not deployment
  alternatives. Original evidence and ZIPs remain preserved.

## Proven work and repair

1. Canonical hash calculation used the Python JSON iterator for each scalar.
   The original intrusive profile of the existing AP export attributed 8.345 s
   cumulative to three hash calls. This is profiler-attributed time, not an
   uninstrumented latency claim. Use the C encoder with identical canonical
   settings/bytes; regression tests compare the old digest for unicode, nested
   values, float/type cases and large inputs. External record/storage formats
   and integrity checks are unchanged.
2. Engine and AP could spawn two export children concurrently. Admit one child
   at a time for their common output directory, on the existing bounded
   background jobs. No control-thread admission, new payload queue or additional
   control/SDK read is introduced. Existing admission/export time bounds and
   explicit failure/retry handling remain; a failed admission is not success.
   Engine waits for the AP prerequisite before taking admission. A part that
   arrives while waiting for admission is fully validated, never falsely
   classified missing because an earlier presence wait expired.
3. `seal(packed=True)` performed full dependency/index/sort/gap assembly while
   holding the ring lock on the control thread. The prior measured maximum was
   92.991 ms. Seal now detaches bounded references to already-owned rows and
   remains explicitly incomplete until the existing export boundary completes
   the same assembly. No live-row repacking or rejected deduplication mechanism
   was added. The reproduction fails before this change and passes after it.

These reproduce concrete diagnostic costs. They do not prove that one isolated
operation alone caused the historical p99 contrast 23.649 → 42.412 ms. The
joint correction is measured below; no quantile subtraction is mislabeled as
an additive per-tick causal duration.

## Same-input qualification

Existing `tools/qualify_oct25_traffic_capture.py`, 1,400 production-flow ticks
per run, 70 modeled seconds, 40 moving + 40 parked records, three supported
trailer slots, lead/crossing actors, target change, signal wait/resume and
overlapping events. Each on/off pair uses the same scripted inputs. Runs are
sequential; pytest does not run concurrently with timing. These are models,
not ETS2 measurements or real Manager/RPC latency measurements.

All times below are milliseconds. Criteria are the unchanged
`docs/steering-audit/oct25-traffic-qualification/ACCEPTANCE.md`.

| Mode / capture and export | Tick p50 | p95 | p99 | max | Engine p99 / max |
| --- | ---: | ---: | ---: | ---: | ---: |
| Real / off | 12.569 | 20.493 | 22.192 | 75.777 | 13.292 / 19.377 |
| Real / on | 15.827 | 22.341 | 25.527 | 40.711 | 14.162 / 24.069 |
| Simple / off | 12.483 | 19.320 | 20.648 | 31.707 | 12.729 / 18.646 |
| Simple / on | 20.254 | 24.529 | 28.575 | 54.780 | 15.270 / 32.555 |

Added p99 is **3.335 / 7.927 ms** (real/simple), below the original 8.33 ms
gate. Both on runs meet tick p99 <50/max <100 and Engine p99 <=16.67/max <50.
The simple margin is only 0.403 ms; this is not a worst-case guarantee.
Baseline maxima and earlier baseline failures remain visible. In particular,
the earlier same-runtime measurement session had baseline p99 about 55 ms;
that failure cannot be attributed entirely to capture, nor used to excuse its
added cost. Host/session variation prevents treating historical quantiles as
paired causal measurements. The new paired baseline is the comparison above.

Control-thread seal maxima are **4.655 / 4.666 ms** (real/simple), versus
92.991 ms in the preceding measured candidate. Detailed p50/p95/p99/max lock,
GC, CPU and inclusive-operation results remain in each JSON. No export disk
I/O or completion wait is observed on the control thread. Windows quantized
thread CPU and wall-minus-CPU do not identify IPC/GIL wait.

Both pairs have identical decision, native-input and chronological physical
write digests, identical logical SDK/IPC GET counts, no simultaneous positive
pedals and no control fault. GET counts are in-process test mapping accesses,
not a real IPC transport benchmark.

## Window and pedal proof

| Mode | Actual pre / post | Exact physical calls | Required AP commands / missing | Dossier bytes |
| --- | --- | ---: | --- | ---: |
| Real | 30.00 / 19.10 s | 2,069 | 976 / 0 | 40,391,335 |
| Simple | 30.00 / 19.05 s | 2,067 | 982 / 0 | 40,898,728 |

Warm dossiers are integrity-valid and assembled complete without disabling AP;
zero capacity/capture losses or missing decision/consumed-input references.
The verifier compares every physical pedal call, original native bytes,
frame/time/context and types. Startup's unavailable prehistory is explicitly
incomplete and is not included as a successful warm window. The 64 KiB short
safety journal remains bounded; full individual calls live in the full-window
evidence and are not limited to that short tail. No game-consumption claim.

## Export phases and remaining memory operation

Separate lightweight phase instrumentation executes the same existing
maximum-load export. Its timings are attribution, not acceptance p99. For the
warm Engine dossier: 37.673 s child wall; initial expansion 0.659 s; AP
verification 7.186 s; exact packing 5.669 s; final dossier inspection 15.094 s.
Inclusive spans overlap and must not be summed. AP export is 12.751 s, of
which exact packing is 4.974 s and readback 5.576 s. Hash spans use the unchanged
canonical bytes. Archive preparation is 0.004 s. Child CPU is close to wall in
these phases: this is primarily materialization/encoding/verification work,
not waiting for a missing AP part.

Parent background process-start spans are 252–341 ms; argument-transfer spans
244–330 ms. Their measured CPU is 0–46.875 ms in Windows scheduler quanta.
Those are **background** waits, not measured uninterrupted GIL ownership or
control blocking. One child is observed at a time. No unbounded queue exists.

The remaining RSS peak occurs while the export child retains expanded Engine
evidence and materializes the Engine/AP trees again during full integrity and
coverage inspection. The phase probe reaches 1,057 MiB RSS at a verification
boundary, and its sampled child peak is 1,188,614,144 B. Verification has not
been removed to reduce that peak.

| Run | Parent peak | Parent on/off peak delta | Largest child | Simultaneous family peak |
| --- | ---: | ---: | ---: | ---: |
| Real on | 201,289,728 B | 78,503,936 B | 1,212,342,272 B | 1,411,457,024 B |
| Simple on | 202,223,616 B | 81,960,960 B | 1,229,299,712 B | 1,429,348,352 B |

The larger paired family-peak contrast is **1,309,085,696 B (1,248.44 MiB)**.
This is an observed peak contrast, not synchronized allocation accounting or
the memory of the whole installed application. The model co-locates Engine/AP
owners; Map, ETS2, other plugins and GPU allocations are outside these figures.
Sampling is every 20 ms and may miss shorter peaks.
One child is not proof of lower total RSS: the current largest family peak
1,429,348,352 B is above the older proposal's 1,318,678,528 B peak. The change
passes latency gates and bounds concurrency; it does not solve expanded-tree
memory amplification. That remaining cost is included in the approval request.

## One revised budget proposal — approval required

The 4 GiB family proposal is superseded. Proposed **additional diagnostic
budget: 2,048 MiB**, excluding the application's pre-existing baseline:

- One export child ceiling **1,536 MiB**. Measured maximum is 1,172.35 MiB;
  the proposed ceiling leaves about 31% over this sample. Original 512 MiB
  criterion fails; no claim of passing it is made.
- Parent diagnostic ownership: **384 MiB** logical upper allowance for Engine
  64 + AP 32 MiB rings, one pinned prehistory each (96 MiB), and one existing
  frozen/retry range each (192 MiB). Frozen retries share original owned
  references; no additional event queue is proposed.
- Parent copying/reference tables/receipts/scratch: **128 MiB** headroom.
  Measured parent peak contrast is 78.16 MiB. The 512 MiB combined parent
  allowance is deliberately above that measured increment.
- Engine file ceiling **32 MiB**, AP remains **32 MiB**. Existing active
  128 MiB/archive 512 MiB disk quotas remain; no disk increase is requested.

Engine retained high-water is about 37.1 MiB, above the unchanged production
32 MiB ring. The tested **64 MiB ring / 32 MiB Engine-file overrides are sizing
probes**, not approved production settings. Existing production constructor
and file limits remain unchanged. These are explicit qualification/operational
ceilings, not an OS-enforced RSS reservation or a proof for arbitrary load.

**Required decision:** approve or reject this one diagnostic-only budget and
the 64 MiB Engine ring/32 MiB Engine-file limits. Approval would permit encoding
those exact fixed limits in the candidate and qualifying that final runtime;
the present probe must not be installed as though approval already existed.
If rejected, the concrete alternative is an export-only redesign that avoids
simultaneous expanded verification trees while preserving every integrity and
coverage check. It is not a control change or a reason to weaken the checks.

## Verification and handover boundary

The focused export/codec suite passed **26 tests** after the fixes. Broad
frozen-runtime regressions returned **436 passed, 7 failed, 30 subtests**:

- Two original 32 MiB capacity tests still fail (3,054 / 2,570 evictions).
  They intentionally run without sizing overrides. This proves the unapproved
  candidate cannot be released as-is; the passing 64 MiB probe must not hide it.
- Four legacy-representation checks expect a zlib/base64 dictionary on readback
  or nested shared-input object identities. The unchanged simple-record
  proposal returns original bytes and owns independent records instead. Their
  expectations were preserved, not weakened or xfailed. Exact bytes/types and
  the replacement format's corruption rejection are tested independently.
- The new seal equivalence test encountered the existing 16-live-window gate
  after cyclic Engine fixtures from earlier tests had not been reclaimed. Its
  fixture now collects retired cycles before creating the test windows and
  asserts zero capture failures; production registration/overload handling is
  unchanged. The focused **26-test** run on the same frozen runtime passes.

The original broad log/frozen test hashes and later isolated test hash/log are
kept separately. The broad suite is **not** reported green and was not rerun
after this test-fixture-only correction. No whole repository pytest was run.
Compilation, content hashes and diff checks are recorded in the final
validation artifact.

No final ZIP or return ZIP is produced while budget/qualification gates are
open. The manifest already records the precise installed originals for the
eventual return backup. No installation changes require rollback now.
After approval and qualification, the deployment transaction must back up
those originals, copy only the six listed runtime dependencies, verify each
SHA-256 and write a receipt; preserve settings/cache/records/commit marker and
restore all originals on any error. Deployment itself needs separate consent.

Only after that consent: start normally without arming, allow >=30 s warm-up,
perform one safe red/wait/green/resume or short-braking episode, continue >=10 s
after the last event, then allow background assembly to finish (the measured
large Engine export takes about 38 s, not two seconds). Inspect the incident
and both required parts before shutting down. Take over for unsafe behavior;
do not deliberately provoke a collision/emergency. This is a future capture
procedure, **not authorization to drive or a current READY verdict**.

**OFFLINE timing/equivalence and warm evidence verified within this model;
budget not approved; GAME NOT VERIFIED.**
