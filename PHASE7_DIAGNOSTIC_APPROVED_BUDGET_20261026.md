# Approved diagnostic budget and exact-runtime qualification

**Historical blocked snapshot.** The focused combined handoff correction is
now implemented and qualified in
[PHASE7_COMBINED_PEDAL_HANDOFF_20261026.md](PHASE7_COMBINED_PEDAL_HANDOFF_20261026.md).
The measurements and unresolved historical variation below remain preserved.

26 October 2026. **BLOCKED on the original absolute Engine timing gate.**
The user explicitly approved the 2 GiB additional diagnostic budget, Engine
64 MiB ring and 32 MiB Engine file, without deployment. Those limits are now
implemented in the isolated build; they are not test overrides. Nothing is
installed and no final ZIP is created while qualification is unsuccessful.

## Exact current development snapshot

`docs/steering-audit/oct25-incident-assembly/approved09-release/`

- Build `UP-DIAGNOSTIC-20261026-09`; six runtime hashes in
  `candidate-manifest.json`, frozen before testing.
- Installed-base receipt SHA-256:
  `61d7bd251991e0933f9f598d80f3620f6f65e581fa68d6a1fb7d4faa59a38935`.
- 141 installed control-function AST comparisons remain equal after removing
  the documented observational hooks. No ACC/AEB/signal/hold/steering rule,
  original SDK timestamp or safety timeout is changed. No plugin version bump.
- The flagless normal runtime retains the original 32 MiB ring / 16 MiB Engine
  file limits. The approved temporary configuration selects 64/32 MiB, while
  AP retains 32/32 MiB. One export child is admitted; its approved 1,536 MiB
  ceiling is sampled on the existing background export wait. Exceeding it
  terminates the child with an explicit retained/retry failure. This is a
  sampled operational ceiling, not an OS reservation or exact peak guarantee.
- Parent additional ownership/scratch allowance 512 MiB and additional family
  allowance 2,048 MiB are qualification bounds. Original active/archive disk
  quotas remain 128/512 MiB. The 4 GiB proposal is superseded.

## Repairs and qualification sequence

The previously verified exact record format is unchanged. Canonical C JSON
hashing, single-child admission and worker-side sealed-window assembly are
retained. A narrow test also reproduced overly eager passive compression
bookkeeping: notifications immediately restarted batches in the parent
process. The optional worker now coalesces them for one existing 60 Hz period,
outside the control thread. Raw records remain owned and charged in the same
ring, with the same bounded weak queue and 32-record batches. This is not a
control timeout, sampling loss, timestamp change or steering filter.

Build 08 passed 443 tests/30 subtests but failed added-p99 and Engine-p99
criteria. Its evidence is preserved. Build 09 adds the bounded coalescing
change; its before-test fails against frozen 08, and the final targeted suite
includes that regression. No further runtime variants are tried after the
remaining baseline timing failure described below.

## Maximum-load results, without capacity/file overrides

The existing scenario runs 1,400 ticks/70 modeled seconds per mode/variant:
40 moving + 40 parked native records, three supported trailer slots,
lead/crossing actors, target change, red/wait/green/resume and overlapping
events. It also continuously offers existing combined diagnostic samples.
This is modeled production flow, not an ETS2 measurement or real IPC latency.

All times are milliseconds. Original timing criteria are unchanged; only the
explicitly approved capacity/RSS criteria are extended in the separately
hashed `approved-budget.json`.

| Mode / automatic incident capture | Tick p50 | p95 | p99 | max | Engine p99 / max |
| --- | ---: | ---: | ---: | ---: | ---: |
| Real / off | 12.877 | 19.564 | 23.078 | 67.663 | 12.602 / 18.540 |
| Real / on | 19.801 | 24.941 | 27.092 | 32.805 | 14.591 / 18.994 |
| Simple / off | 19.289 | 34.399 | 53.002 | 112.021 | 22.138 / 69.167 |
| Simple / on | 23.034 | 32.508 | 40.417 | 71.073 | **19.708** / 36.524 |

Real mode passes all timing gates; added tick p99 is 4.013 ms. Simple mode
passes tick p99/max, added-p99 and Engine maximum, but **fails Engine p99
<=16.67 ms**. Its baseline already fails the same Engine gate and whole-tick
absolute gates. The negative paired p99 contrast (-12.585 ms) is not evidence
that adding diagnostics accelerates control, nor an excuse to waive the
absolute gate. The observed session variation is unresolved; no historical
pause is assigned to GC, IPC or scheduling without measurements proving it.

Both modes preserve identical physical-write, decision, native-input digests
and logical SDK/IPC read counts on the same inputs. Zero pedal overlap,
control faults or control-thread export I/O. Maximum ring-lock wait is
0.148/0.260 ms (real/simple), below the original 5 ms maximum.

| Mode | Actual pre / post | Exact pedal calls | Required AP commands / missing | Dossier bytes |
| --- | --- | ---: | --- | ---: |
| Real | 30.00 / 19.10 s | 2,069 | 976 / 0 | 40,384,850 |
| Simple | 30.00 / 19.05 s | 2,067 | 982 / 0 | 40,988,558 |

Both warm dossiers are complete and integrity-valid without disabling AP;
zero capacity/capture loss or missing decision/input references. Original
native bytes, clocks, types, identities and every physical pedal call are
checked. Startup's unavailable prehistory remains explicitly incomplete.

Maximum measured child RSS: **1,229,131,776 B**, below 1,536 MiB. Parent
on/off peak contrast is at most **80,527,360 B**, below 512 MiB. Simultaneous
family peak contrast is at most **1,307,566,080 B**, below 2,048 MiB. One
child at a time. These exclude the application's unrelated existing baseline
and are sampled every 20 ms; they are not a whole-application RAM promise.
Engine/AP retained high-water is 39,123,865 / 7,681,488 B, within 64/32 MiB.

## Precise remaining operation and smallest design change

An attribution-only run profiles the **same existing baseline** with automatic
incident capture off. It does not replace the acceptance measurements.
`baseline-engine-attribution.txt` attributes 20.602 s cumulative to 1,405
Engine flushes. Of that, the pre-existing combined hook
`_offer_maneuver_evidence_diagnostic` accounts for 8.957 s; its
`capture_diagnostic_application` accounts for 4.916 s and
`PedalJournal.snapshot(expanded=True)` for 3.930 s. Inclusive spans overlap.
The latter expands retained sources and deep-copies the result; capture then
recursively converts the expanded tree again for JSON. This work exists in
the measured baseline too. Mock copy/clock overhead is separately visible in
the profile; instrumented times are not uninstrumented per-tick deadlines.

The smallest targeted next design change is to pass the already-owned packed
pedal snapshot through the existing combined collector's bounded handoff and
expand/normalize it on its existing worker. Final file format and exact source
binding must remain unchanged. The present mock collector retains captures
without running that worker; a fair concurrency qualification must execute
the deferred work too. Merely removing the baseline combined work, disabling
that stress case, or excluding its time would hide the failure. None was done.
This change has **not** been implemented or declared verified in this build.
The measurements do not prove that all baseline tail variability is caused
by this operation; they identify a concrete remaining control-thread cost.

Do not waive the 16.67 ms gate, change controls, or create another final
BLOCKED ZIP. The choice is to implement and qualify that focused existing-
collector handoff correction, or explicitly retain the current BLOCKED verdict.
Memory approval alone cannot turn this timing failure into readiness.

## Regressions and artifact integrity

The exact frozen 09 runtime returned **444 passed, 30 subtests passed** in
180.57 s. `test-selection.json` records all selected test hashes. Three old
private nested/shared-storage graph tests remain unchanged and explicitly
outside qualification of the independent-record format; all semantic pedal
tests and independent exact-codec tests are included. The byte readback test
accepts either original bytes or the legacy wrapper and verifies the same
source bytes. The capacity assertion uses the explicitly approved bound and
still requires zero loss and full coverage. No safety expectation was removed.
No entire repository pytest run is claimed.

After pytest completed, its wrapper failed while hashing a Path rather than
its bytes when persisting qualification metadata. That wrapper bug is fixed;
the complete original test log and frozen hashes are preserved, and the
broad tests are not rerun for a metadata-only fix. The final validation records
the wrapper error separately and does not invent an observed pytest exit code.
Packaging now also rejects a missing/unknown qualification exit code.

Compileall, installed receipt/content checks, frozen runtime/test hashes and
`git diff --check` are recorded in `final-validation.json`. Original records,
installation, settings/cache, commit marker and unrelated workspace changes
remain untouched. No game, autopilot, arming, commit, push or deployment.

No final ZIP/return ZIP is produced because the acceptance conjunction fails.
The candidate manifest retains exact installed original hashes for a later
transactional return backup. No rollback is needed now. The future controlled
capture procedure remains in the preceding export-overhead report, conditional
on a genuinely qualified build and separate deployment approval.

**Capacity, exact evidence, budget and functional regressions: OFFLINE VERIFIED
within this model. Timing qualification: BLOCKED. GAME NOT VERIFIED.**
