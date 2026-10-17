# Existing event export: quota visibility, bounded recovery and sealed evidence

## Verdict and scope

The diagnostic defects below are reproduced and corrected offline. This is
**not** a diagnosis or correction of the second-roundabout braking oscillation.
Its missing original consumed inputs cannot be reconstructed from later samples.
No control law, plugin implementation/version, source clock, evidence freshness,
5 m signal offset, parking brake or physical control decision changes here.
The existing uncommitted ACC 1.3.7 signal candidate is preserved.

No installation, original recording, settings, DLL or game operation is changed.
The user will run the full suite manually; no whole-suite PASS is claimed.

## Exact existing limit and current read-only inventory

The existing significant-event writer counts all top-level
`steering-replay-*-significant_event.json` files in `route-diagnostics`, across
application runs. Its limits remain **8 files / 16,777,216 bytes**. They are not
the 500 ms control freshness limit, the 64 KiB detail ring or free disk space.

Read-only inventory of the installation on 17 October:

| Property | Measured result |
| --- | --- |
| Significant-event files | 8 |
| Total bytes | 6,614,998 (6.31 MiB) |
| Unused bytes within the quota | 10,162,218 |
| Actual blocker | `FILE_COUNT_LIMIT` |

The exact filenames and SHA-256 values are retained in
`docs/steering-audit/oct16-green-restart/event-export-readiness.json` (local
evidence, outside the runtime payload). No historical payload is edited.
The 16 October log's quota exception establishes a failed export path, not
which producer commanded the vehicle to brake.

## Reproduced defects and correction

1. Once an export failed, Engine latched `_significant_export_blocked` for the
   entire process. Even explicit external archival freeing the quota did not
   allow the same original sealed event to export. The existing single worker
   now permits one recheck after a **30 s diagnostic retry cooldown**. This is
   not a control timeout or new command lease. There is still no queue, no
   disk check in the actuator tick and no automatic deletion/archival.
2. The existing one-slot journal retained the first event's sealed detail and
   history after a quota failure, but the later automatic fault transferred
   only a small receipt. The automatic incident now includes the full already
   sealed `preceding_significant_event` alongside the existing compatibility
   receipt. Expansion and immutable interning occur in the existing background
   writer. Original event observation times and history windows stay unchanged.
   The fault's own recent history, first intervention and safety writes remain
   separate. No additional SDK/IPC acquisition or history ring is introduced.
3. Quota readiness was not reported at normal startup. A single metadata-only
   preflight now uses that same exporter and emits one `NOT READY` warning
   showing the precise file/byte limits when blocked. This warning cannot grant
   or remove control authority. A read-only preparation tool exposes the same
   calculation and hashes the existing files without arming anything.

The journal's `event_capture_status.export_failure` includes the original
failure reason, first/last failure monotonic time, attempts and incompleteness.
The automatic fault includes `event_export_status` and explicitly says that
coalesced events do **not** each have individual snapshots. Replay inspection
checks ordering, identity references and incompleteness in both the current and
the retained preceding event. The original fixed codec key dictionary and
export schema version remain compatible; additions use explicit string keys.

The original compatibility field `sealed_history_superseded_by_fault` denotes
that the standalone event export is superseded by the fault export; the added
`sealed_history_included=true` identifies the now-preserved full evidence.

## Reproduction and verification

`tests/test_oct17_evidence_quota.py` initially reproduced **2 failures**:
no recovery after external archival and missing sealed event history after
35 s of rolling-history aging followed by an actual Engine safety intervention.
The latter uses the existing activation/physical Controller fixture and real
fault/export path; journal aging is driven explicitly to avoid pretending it is
a second measured vehicle journey.

Coverage includes original file/byte quota rejection, unchanged source file
hashes, no partially published event, recovery with the original timestamp and
receipt, first fault/safety writes, a background-only one-shot startup check,
read-only readiness/hash inspection, old replay compatibility and rejection of
structurally corrupted nested evidence even with a recomputed outer hash.

The first focused run passes **27 tests**. The final focused export, signal,
replay and release gate passes **105 tests in 27.99 s**
(`quota-regressions.log`). Full pytest remains the user's manual gate. No new candidate is labelled verified using
the preceding `verification-pending.json`: these later core/test changes
supersede that hash snapshot.

`compileall` for changed runtime/tests/tools and `git diff --check` pass.
The fresh pending snapshot is `verification-pending-oct17.json`; it records
hashes only, not a successful full-suite execution. Original evidence files
still match the read-only inventory SHA-256 values after the checks.

## Bounds and remaining limits

No quota is raised. The detailed ring remains 64 KiB, the rolling decision
history remains 1 MiB / 30 s and the journal retains one pending event with the
existing bounded receipt/pre/post snapshots. The added failure record is one
fixed-shape record, and the retry retains no additional queue. The automatic
fault reuses existing sealed references until the background worker expands
them; it does not allocate a second rolling history in the control tick.

This **does not** guarantee a complete continuous recording during a full quota:
later changes can still be coalesced, and the lost 16 October inputs do not
exist in the new field retroactively. A readiness result with a free slot also
does not prove that an unknown next payload fits the remaining byte quota.

Before a future collection, the existing eight files must be archived with
user approval, retaining verified original bytes. Proposed reversible action:
move exactly the eight inventoried event files into a dated archive directory,
verify SHA-256 at the destination, and rerun the read-only check. Do not remove
other replay types, logs, settings or receipts. No such move has been executed.
While the directory remains saturated, event export is explicitly **NOT READY**.
The safety-fault export remains a distinct path with its existing behavior.

## Read-only command

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
python tools/check_event_export_readiness.py --directory 'C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics'
```

Exit 2 means blocked, 0 means a slot and some bytes are available. Neither is
game verification, proof of traffic coverage or proof of command consumption.

Runtime changes for this correction: `core/engine.py`,
`core/steering_replay.py`, `core/navigation/longitudinal_diagnostics.py`.
The existing consistent candidate already includes these dependencies. The
preparation/readiness tool and tests are not installed as control runtime.

**Second-roundabout cause remains OPEN / GAME NOT VERIFIED.** Correcting evidence
retention must not be presented as fixing the vehicle's unexplained braking.
