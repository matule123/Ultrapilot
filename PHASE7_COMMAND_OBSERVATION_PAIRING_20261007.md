# Longitudinal command / vehicle observation pairing — 2026-10-07

## Verdict and build

**OFFLINE PASS for the reproduced publication race. NOT VERIFIED in ETS2.**
The starting tree was clean at `303627ced9052ea0e596272d79afbe62260f23ed`.
No project `AGENTS.md` was found in the checkout or its applicable ancestors.
Installed Engine, longitudinal arbitration, control timing, longitudinal
diagnostics and Autopilot were compared to that Git commit after LF/CRLF
normalization: all five matched. `commit.txt` was not used as code evidence.
The installed application remains unchanged; the four core files below now
differ from that baseline in the working tree.

No plugin implementation changed. Autopilot remains **1.2.2**, ACC **1.1.4**,
Map **1.1.0**, DrivePolicy **1.1.0**. No DLL/configuration update is needed.
No commit, push, deployment, diagnostic arming or game operation was performed.

## Incident evidence

Source log: installed `ultrapilot.log`, 2026-10-07 17:30:06–17:30:08.
Replay: installed `route-diagnostics/steering-replay-20261007T153007.640484Z-automatic_disable.json`,
schema 3, 16 samples; SHA-256
`4d49347cf8122b7243af1f0b6b07b184d54d32613cabdec0d1cdc7989c6892b4`.
The original files were only read.

Shared identity: activation/fault epoch `14355161432500`, session `1`,
map `promods-1.59`, dataset `d6cc7936fce4e902761abb5d`,
intent `78d0ba0a3bcb41388ac5b8dbbd0691ad`, revision `6`,
build `bf68a171786a4fef9050c98705ef8c75`, geometry
`718ca459227c72023bbaa2188dc045494c39c8d9c5c33dde2bf2ee29d37596a6`.

| Event | Clock/frame evidence | Interpretation |
| --- | --- | --- |
| Successful launch handoff, 17:30:06.759 | SDK `100012666`, gear 7, throttle 0.0647252, brake 0, active | Launch succeeded; this task does not change it. |
| Truck actually compared | SDK `100679306`, observation `14356.2386942`, valid true | Captured before the newer command was read. |
| Command actually rejected | SDK `100695972`, observation `14356.2569233`, computation `14356.282744` | One SDK frame (16,666 µs) ahead of the captured truck. |
| Engine check, 17:30:07.448 | `14356.2874754`; decision age 4.7314 ms; command observation age 30.5521 ms; expiry `14356.6315277` | 344.0523 ms of lease remained; identity equality and valid telemetry were recorded. This was neither expiry nor the 500 ms stale limit. |
| Old first-fault header | SDK `100712638`, observation `14356.2797499`, record time `14356.294992` | Diagnostic creation read a later truck; this header was not the comparison input. |
| Autopilot reaction, 17:30:07.470–.565 | Inherits Engine's first reason, controlled stop, hazards, eventual disable | A consequence of the Engine rejection, not an independent producer timestamp error. |

The historical rejection receipt does not retain every command/pedal and
truck field. It also cannot prove which replacement snapshot a single retry
would have returned at the original check. The later header establishes a
later read, not availability at an earlier instant. No missing historic
gear/speed or physical pedal write is reconstructed from unrelated replay
headers.

## Proven production cause and change

Before: Engine captured a truck after steering preparation, performed
drivetrain/hold checks, and then read `longitudinal_command`. An independent
Autopilot publication during that IPC read could legitimately reference a
newer SDK frame. Arbitration correctly refused an ahead command, but no
bounded observation pairing existed. Fault recording separately fetched
current telemetry, producing the misleading newer header.

Autopilot was audited: it reads navigation/history, captures its immutable
truck once, consumes producer snapshots and finalizes its command from that
same truck and embedded observation time. It did not originate the first
incident rejection. Its implementation and publication flow are unchanged.

Now:

1. After existing steering preparation, capture context and **one immutable
   command** before the drivetrain/hold checks.
2. If its SDK frame exceeds the captured truck's frame, make **at most one**
   actual `telemetry` IPC read. Do not reread/relabel the command, wait in a
   loop, change a frame, or retimestamp either observation.
3. Check the returned truck after the read. Use it consistently for forward
   ratio/history, service-hold checks, parking brake, motion gates,
   arbitration and final output/hold receipts. Full longitudinal validation
   still checks source/schema, original ages/deadlines, activation/route
   identity, current producer demands and the original ahead predicate.
4. Preserve the existing identity/expiry check immediately before positive
   physical I/O. If the single replacement is missing/invalid/stale or still
   behind, no positive drive is written. Existing controlled-stop or bounded
   zero-drive refresh behavior applies; this change does not grant recovery
   after a technical fault.
5. Record the exact comparison receipt instead of fetching later telemetry
   for its fault header. The receipt carries original and compared SDK frame,
   gear, signed speed, parking brake, bound observation metadata, command-read
   start/return, read completion time and `reread_count`. The compared command's
   identity, original times, source, validity, pedals and emergency flag remain
   explicit in fault details / the existing journal's requested packet.

Normal same/older-frame commands incur no retry and add no bulky pairing
record to routine combined rows. Retry receipts use fixed-key lossless
packing inside existing diagnostic budgets, expanded back to named fields on
read/export. The 8 KB fault limit, 32 KB journal source limit, total journal
allocation and export integrity rules are unchanged. Packing was needed:
naively duplicating both receipts exhausted the existing diagnostic budget.
No separate collector, per-frame INFO logging or new authority was added.
Both genuinely different identities are also preserved: unchanged context
fields are shared only inside the immutable bounded receipt, with explicit
differences retained and both full contexts restored on reading. Tests cover
short and full-length identities with a foreign session; no identity check
or diagnostic limit is relaxed.

## Reproduction and verification

`tests/test_oct7_command_observation_pairing.py` uses the existing lifecycle
fixture: real SignalReader/selector, DrivePolicy, ACC, Autopilot, Engine,
Controller and SCSControlsWriter against an isolated byte mapping. A copying
IPC hook publishes the next real SDK/producer tick while Engine reads the
command. It records chronological backend writes and asserts there is no
pedal write before the replacement read/validation. This is a software model,
not confirmed ETS2 input consumption.

| Property | Baseline | Candidate |
| --- | --- | --- |
| Newer command + available replacement truck, simple automatic | False controlled stop; physical throttle 0 | Positive returned write, active authority, current frame in applied output/history |
| Same race, real automatic | False controlled stop; physical throttle 0 | Continues with confirmed forward ratio and paired truck |
| Later diagnostic publication | Header points at later frame instead of compared truck | Exact compared frame/time and pinned command retained |
| Still-future command after one read | Refused | Refused, no second retry or positive drive |
| SDK invalid/missing/stale/future time, R/backward motion | Protected | Protected, no positive drive |
| Expiry during replacement RPC | Protected | Pinned old drive refused; existing bounded zero-drive refresh remains available when its evidence is valid |
| Identity / activation / manual-off during replacement RPC | Protected | No positive drive; no identity or activation relabelling |
| Twenty consecutive publication races per automatic mode | Fails at first race | All continue on same activation, one retry per race |
| Combined round-trip | No pairing receipt | Receipt survives actual returned write → chunk/hash export → readback, confirmed=false, runtime_authorized=false |

Before production edits the initial counterexample set produced **3 failed,
9 passed**: both automatic-mode race reproductions and incorrect fault
header. After the fix and additional safety/round-trip coverage: **20 passed**.
Tests were also checked against existing controlled-stop semantics: at a
moving fault, revoking drive can preserve braking authority until standstill;
it is not required to erase the controlled-stop state immediately.

Relevant integration run: **359 passed, 7 subtests passed** (65.63 s). It
covered activation observation binding, arbitration, Oct 3/4/6 lifecycle
regressions, launch handoff, commit/preview, longitudinal evidence export,
independent cadence, control safety and timing. The final two additional
retry-time activation/future-time cases were included in the separate final
20-test run (1.45 s). The full pytest suite was **not** run.
After the final foreign-session receipt-budget check, the affected pairing,
evidence export, signal lifecycle and control-safety subset passed again:
**128 passed, 7 subtests passed** (5.89 s). This is overlapping targeted
coverage, not an additional 128 unique tests or a full-suite result.

Existing red → continuous forward-started braking → waiting → qualified
same-head green → release/restart tests passed for both automatic modes,
including repeated cycles and Engine-first scheduling. Actual mapping writes
retain positive brake continuity, zero throttle while held, no parking-brake
writes, no modeled reverse edges and no simultaneous positive pedals. These
are offline preservation results, not new game confirmation of brake semantics.

Benchmark comparisons against `303627c`:

| Existing benchmark | Cases | Result |
| --- | --- | --- |
| Steering | 16 | Case metrics numerically identical |
| Longitudinal comfort | 12 | Case metrics numerically identical |

Local ignored receipts: `docs/steering-audit/oct7-{steering,comfort}-{baseline,current}.json`.
No steering/controller/geometry/scheduler or freshness-limit change was made.
`compileall` for changed Python files and `git diff --check` passed.

## Changed files and remaining scope

Runtime: `core/engine.py`, `core/longitudinal.py`, `core/control_timing.py`,
`core/navigation/longitudinal_diagnostics.py`.
Regression: `tests/test_oct7_command_observation_pairing.py`.
Documentation: this report and `PLUGIN_CHANGELOG.md`.

The bounded retry cannot manufacture a new SDK sample. True SDK loss,
unsupported identity, stale packets, reverse motion and deadline expiry
still refuse propulsion. This fix does not complete the earlier unsupported
new stationary-red hold, prove traffic coverage, or guarantee all future
process scheduling. Installed runtime has not received the fix. User full
suite and separately authorized deployment/live confirmation remain open;
no new drive is requested in this task.

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python -m pytest tests -q
```
