# Combined pedal handoff — 26 October 2026

**Historical qualification, superseded by the 26 October daemon-host failure.**
The following original READY result used an insufficient process host. Do not
deploy build 10 as the correction. Current work and mandatory completeness
gates are in [PHASE7_DAEMON_STOP_EPISODES_20261026.md](PHASE7_DAEMON_STOP_EPISODES_20261026.md).

Original result: **READY FOR CONTROLLED CAPTURE — OFFLINE VERIFIED in the measured scope;
GAME NOT VERIFIED.** Final frozen-runtime regressions: **449 passed,
30 subtests passed**. Compileall and diff-check pass. The installation remains
unchanged. The single candidate ZIP and exact return backup are hash-verified;
see `combined10-release/release-receipt.json` and
`combined10-release/DEPLOYMENT_AND_CAPTURE.md` under the incident-assembly tree.

The current frozen diagnostic candidate is
`docs/steering-audit/oct25-incident-assembly/combined10-release/`.
Final readiness and archive hashes are recorded in its release receipt after
qualification. No deployment, game execution, arming, commit or push is
authorized or performed by preparing this build.

## Concrete correction

The old combined hook called `PedalJournal.snapshot(expanded=True)`, expanding
every retained source and deep-copying it on the Engine control thread. Capture
then converted the expanded tree to JSON-compatible values, and the combined
worker converted it again. The preceding baseline profile attributed 3.930 s
to snapshots and 4.916 s to capture preparation over 1,405 flushes; these are
inclusive instrumented totals, not per-tick acceptance times.

The Engine now requests the existing packed snapshot. Capture owns that small
primitive tree once through the already verified, bounded C codec. The private
read-only handoff contains only immutable bytes/header primitives; later source
mutations cannot affect it. The existing `EvidenceDiagnosticCollector._run`
worker expands and normalizes it once. Inspection returns detached values.
External JSON, schemas, hashes, original times, frame/activation/route identity
and pedal values remain unchanged. No SDK/IPC read or control command is added.

The existing queue remains **one slot**, with one in-progress item. The
transient producer copy is bounded by the same **512 KiB** record limit; it is
discarded immediately on rejected admission. No second queue or worker is
introduced. All fit the approved parent scratch allowance; no memory, disk or
safety-time budget is increased. Control never waits for worker progress.

A second directly related bug was reproduced: Engine advanced the pedal cursor
even when `offer` returned false. Cursor advancement now requires successful
admission, so the next snapshot retains unaccepted writes. Genuine journal
eviction remains explicitly reported; a bounded queue cannot promise unlimited
lossless service during an arbitrary permanent worker failure. The independent
full incident window remains unchanged and preserves its exact physical calls.

## Reproduction and worker proof

Against frozen 09, the five new tests produce **4 failures / 1 pass**:
control-thread expansion in both automatic modes, mutable/non-equivalent packed
handoff, and cursor advancement on rejection. The existing queue-overload
property was already correct. The corrected implementation passes these tests.
They use actual Engine/Controller calls and the existing collector thread;
source mutation after capture, chronological order, original clocks, full
queue rejection and worker-thread normalization are checked.

The representative same-input old/simple baseline normalizes only **1,967 of
2,913** physical calls under overload because of its premature cursor advance.
The enabled corrected capture normalizes **2,913 of 2,913** in **each** mode,
despite **438 / 439 rejected offers** (simple/real). Rejected capture offers are
not labeled accepted samples or zero loss; all pedal calls are independently
compared in order and recovered through the unchanged cursor. No reported
journal overwrite or normalization error occurs in the enabled runs.

The timing baseline without automatic incident capture ends with 2,911/2,913
combined normalized calls in real mode (603 rejected offers); it is explicitly
not a complete collected-evidence attestation. Its entire physical trace is
still used for the off/on control-equivalence comparison. Complete collected
evidence, like incident capacity/parts in the original criteria, is mandatory
for the **enabled** capture. The original automatic-enabled full trace and
warm incident completeness tests are not relaxed. Simple off normalizes all
2,913 calls. Full-run counts and scope remain visible in every JSON.

## Frozen timing and overload scenario

One runtime in both modes; 1,400 ticks/70 modeled seconds per variant; 40
moving + 40 parked records, three supported moving trailer slots, leader
change, crossing actor, red/wait/green/resume and overlapping incidents.
There are no ring/file sizing overrides. The actual existing one-slot worker
is active in both variants, executing production pedal expansion/normalization
concurrently. Its in-memory sink records original calls; full collector
geometry validation and actual combined export/readback are separate regression
tests. Deferred CPU work is not omitted from the timing load.

Milliseconds; baseline means automatic incident capture/export off, with the
existing combined workload still active. On includes incident retention AND
concurrent export, so the contrast is total diagnostic increment, not isolated
disk or compression cost. Quantile contrasts are not additive per-tick spans.

| Mode / automatic capture | Whole tick p50 | p95 | p99 | max | Engine p99 / max |
| --- | ---: | ---: | ---: | ---: | ---: |
| Simple / off | 10.222 | 17.433 | 19.634 | 28.875 | 10.734 / 15.367 |
| Simple / on | 15.695 | 21.345 | 25.319 | 41.639 | 13.155 / 25.420 |
| Real / off | 10.395 | 17.789 | 20.351 | 31.273 | 11.270 / 13.424 |
| Real / on | 15.475 | 20.932 | 25.689 | 37.901 | 13.232 / 28.565 |

Added whole-tick p99: **5.685 / 5.338 ms**, under **8.33 ms**. Both modes meet
the original whole-tick p99 <50/max <100 and Engine p99 <=16.67/max <50 gates.
The original timing criteria SHA is unchanged. Earlier baseline overruns remain
preserved; neither this run nor a negative contrast explains all historical
variability or guarantees future deadlines.

For comparable simple off inputs, Engine p99 decreases **13.097 → 10.734 ms**;
whole-tick p99 **20.986 → 19.634 ms**. Old/new and off/on physical-write,
decision, native-input hashes and logical SDK/IPC read counts match. No positive
pedal overlap, control fault or export I/O on the control thread. Five fixture
startup normalizations occur outside measured ticks; all 961/962 subsequent
normalizations run on the worker. Existing timers include those setup calls
under the control-thread label and must not be mistaken for timed tick work.

## Capacity, integrity and approved memory

| Mode | Actual pre / post | Exact incident calls | Required AP commands / missing | Dossier bytes |
| --- | --- | ---: | --- | ---: |
| Simple | 30.00 / 19.05 s | 2,067 | 982 / 0 | 41,023,798 |
| Real | 30.00 / 19.10 s | 2,069 | 976 / 0 | 40,414,878 |

Warm dossiers are hash-valid, assembled without AP disable, with zero incident
capacity/capture losses or missing call/binding/input references. Startup's
unavailable prehistory is explicitly incomplete. Backend return is not game
consumption confirmation. The old 64 KiB safety tail remains, alongside the
full-window precise backend detail.

Maximum child RSS **1,225,076,736 B**, parent peak contrast **93,347,840 B**,
simultaneous diagnostic-family peak contrast **1,304,043,520 B**. All fit the
approved 1,536/512/2,048 MiB bounds; one export child is observed at a time.
RSS is sampled every 20 ms and may miss shorter peaks. These are diagnostic
increments/model process RSS, not total installed-app/ETS2/Map memory promises.

## Scope, validation and remaining limitations

The installed-base receipt remains
`61d7bd251991e0933f9f598d80f3620f6f65e581fa68d6a1fb7d4faa59a38935`.
Seven runtime dependencies are listed with SHA-256 in the manifest. The combined
hook has only the exact packed-snapshot/accepted-cursor transformation; other
control AST comparisons remain equal. No controller, route geometry, steering
cadence, ACC/AEB, semaphore, hold or 500 ms limit changes. No plugin VERSION
increase; the temporary build identity records uncommitted diagnostic changes.

The first broad pass had 448 passes and one fixture-isolation failure: retired
cyclic Engine fixtures exhausted the existing 16-live-window registry. The
retention test now collects retired fixture cycles before constructing its
single test window. All original assertions remain; no production registry
limit was changed. The final frozen-runtime result and logs are in the release
directory. The three obsolete private nested-sharing graph tests remain
explicitly outside qualification of the already selected independent-record
format; semantic pedal, immutable-codec, control and full export tests remain.
No whole repository pytest claim is made.

This is readiness for one controlled **diagnostic** capture, not a fix or
certification of ACC/driving behavior. Models do not prove ETS2 consumption,
real IPC scheduling or all native traffic cases. An early shutdown, actual
worker failure, insufficient startup history or exhausted finite quotas must
remain explicitly incomplete. Do not request a drive before separately approved
deployment. See the accompanying deployment/capture instructions and receipt.

Some unchanged export banner strings still carry legacy diagnostic build
labels `20261025-07`/`04`. They must not be used as payload attribution: the
seven-file deployment receipt/hash set identifies build 10. Real route build
IDs, session identity and original SDK clocks are separately preserved. This
known label limitation does not grant authority or bypass integrity checks.
