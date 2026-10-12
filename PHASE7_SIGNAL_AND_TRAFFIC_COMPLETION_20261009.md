# Phase 7 — directed signal, traffic authority and event completion

Date: 2026-10-09. Continuation of the pending Autopilot 1.3.2 work.

**IMPLEMENTED AND OFFLINE VERIFIED** for the supported scoped-signal flow,
validated traffic demand, bounded hold ramp and significant-event export.
**NOT VERIFIED IN GAME** for this candidate. **BLOCKED** for attributing the
original missed red and early brake to an exact historical head/actor: those
consumed inputs were not retained. A driver takeover is not counted as a
successful automatic stop/resume implementation.

No deployment, game control, arming, commit, push or full pytest run occurred.
Existing local pedal/export, approach, launch and signal-selection changes
were preserved. The lateral controller, route centerline, speed controller,
35 km/h roundabout upper target and 500 ms limits are unchanged.

## Build and evidence separation

HEAD is `787d012a2a78ac917bb5506e0958c32d8d06575f`, with local additions.
The installed receipt declares Autopilot **1.3.1**, not this candidate.
All seven installed receipt hashes were rechecked and match. Controller,
ACC and DrivePolicy match the source after LF/CRLF normalization; the changed
core, signal, diagnostics, Map, Autopilot and UI files have real content
differences. `commit.txt` is not used as a deployment certificate.
Candidate declarations are **Autopilot 1.3.3**, **Map 1.1.1**. Core changes
do not create releases of unchanged ACC/DrivePolicy/Collision plugins.

The installed/repository-asset DLL has SHA-256
`53d8c54d2b71abb2f1d2de8cb68cd096f22f8385f750f46ce07af105295c3bcf`.
The preserved game log loads `1.59.2-up-signal`, ETS2 `1.59.1.3s`.
The new scoped DLL below was never loaded into ETS2.

The original Oct 8 captures and their integrity checks are documented fully in
[the preceding evidence report](PHASE7_SIGNAL_COVERAGE_AND_BRAKE_REVIEW_20261009.md).
Map key is `promods-1.59`, fingerprint `d6cc7936fce4e902761abb5d`, session 1.

| Capture, UTC suffix | Binding and usable coverage |
| --- | --- |
| `193225.467850Z-manual_disable` | 794 calculations / 4,547 executor rows; intent `ecd2369d7b15425d8d0a180384932eaf`, revision 6, build `ed103f70dca84da5a7275330e8d2137d` |
| `193401.934129Z-automatic_disable` | 17 detailed pedal rows; 280 summary/change rows; 30.057506 s, application clock 28585.721581–28615.7790871 |
| `193402.167118Z-automatic_disable` | 1,652 calculations / 5,633 executor rows; intent `2937eb3824c1475eba8aa5740b2b6653`, revision 9, build `dfc8e022187f494a9e8f786bb39cc136` |
| `193419.958526Z-plugin_stop` | 359 timing rows; 111 identity/Map/publication-matched observations |

Both dense files lack immutable execution source packets. Their headers are
not substituted for physical pedal receipts. The early slowdown at roughly
28559–28564 precedes the retained pedal window. `AVOID_OBSTACLE` is logged
near 21:33:05, but its original actor/TTC/traffic demand and posted speed limit
cannot be recovered. The 21:34:01 technical stop follows actual destination
removal; it is not attributed to the earlier light or brake impulse.

## Reproduced defects and changes

| Defect | Before | Change | After |
| --- | --- | --- | --- |
| Lamp height treated as road-deck height | Three real placed-prefab cases rejected a modeled owned head 4 m above the road | Add native owning-prefab/node/origin identity at acquisition; require exact ownership plus directed group/orientation | Three cases qualify; foreign owner/direction, torn/expired source and conflicting colors fail closed |
| Unknown scoped group silently loses uncertainty at lamp height | Three new real-prefab counterexamples failed | Use matching native owner to identify an unassigned directed-passage conflict, retaining the actual lamp pose | Takeover required; no synthesized red/green, ground pose or nearest-light control |
| Invalid display traffic can still brake | Six production counterexamples failed; malformed quaternion/duplicate ID produced an approximately 0.2696 brake | Only validated immutable capture and existing directed-route lead/crossing selection may produce traffic demand | Invalid capture cannot create a new phantom brake; missing data is not clearance |
| Straight cab extension overrides a curved route | Valid actor off the original curved route produced legacy braking with ACC disabled | Remove legacy display-list/cab-extension actuation override | No brake for that no-conflict route candidate; real directed conflicts/emergencies remain effective |
| Hold floor jumps directly from tiny approach brake to prior peak | Two 60 Hz cases failed the existing 2.5/s rise rule | Ramp the existing acknowledged floor using actual last write/time and the same rise rate | Continuous positive holding reaches its proven peak; drift/emergency protection bypasses the comfort ramp |
| Normal significant event ages out before automatic disable | Normal source-edge export test failed | Seal the existing history/ring in one bounded pending slot and use the existing replay worker | Normal brake-source event exports without arming/disabling; history survives later aging |
| Same-size game-log rewrite hidden by file metadata | Deterministic unchanged-stat reproduction confirmed an obsolete mode | Always compare one bounded immutable prefix on the existing off-tick observer | Rewrite/truncate/replace rejected; complete ordinary append remains supported |

The traffic cases are **code counterexamples**, not reconstructed historical
actors. The signal-height cases are modeled lamp placements on real source
prefabs, not claimed original raw heads. This distinction remains necessary.

## Scoped signal producer and directed binding

Pinned native source: `1f16156b9b37b70cf182c2bc09120fa1b234e129`.
The existing semaphore loop obtains instance ID, actor type/state/pose, owning
prefab UID, native node UIDs, origin index and instance slot. The same actual
acquisition publishes those fields with QPC observation time, render frame,
generation and producer lifecycle. Python polling time is never substituted.

Native `semaphore_instance.id` is treated explicitly as a prefab-local segment
instance ID. Map `navCurves.semaphoreId` is an authored directed control group,
not a global actor ID. Group comparison requires the owning placed prefab,
node UID set and origin to match, then the controlled curve's transformed
heading. Equality of ID alone does not grant authority. The live relationship
of these namespaces on the crossed red is **not certified by existing data**.

Schema 2 remains 1,980 bytes. Additive schema 3 is 4,860 bytes: the original
1,920-byte actor payload and forty 72-byte owner records in one sequenced
snapshot. Both publish identical original acquisition, lifecycle/generation
and frame. Pause/reset invalidates both. Python prefers schema 3, accepts
schema 2 when absent, and does not fall back from a present invalid schema 3.
Kinds are decoded by the existing source parser: traffic-rule light (1) is
eligible; barriers/other objects do not become signals.

Legacy schema-2 pose/elevation/orientation gates remain unchanged. They cannot
prove an elevated lamp belongs to a road deck. Schema 3 avoids that mistaken
inference through actual native ownership rather than widening every height
gate. Same-owner/group lamps with one consistent color are one control;
conflicting colors are ambiguous. The locked physical head, passage and
lifecycle survive holding; another closer object cannot release the stop.

Map retains existing directed topology and geometry. Cache version 15 adds
native ownership metadata; version-14 caches are rebuilt rather than guessed.
The stop target is still an authored passage entrance minus the existing
6 m unmeasured front allowance and 2 m stand-off. It is not a measured painted
line, truck outline or physical-road boundary.

Tests use three real placed prefabs: two `dlc_blkw80` placements and one
`dlc_blkw57`, with their original transforms, selected connector chains,
descriptor metadata and native placement IDs. Six cases (three placements,
both automatic modes) each run two red/hold/green/resume cycles through actual
Policy, ACC, Autopilot, Engine, Controller and chronological mapping writes.
They preserve zero propulsion during holding, no brake-zero impulse, no
parking-brake writes and restart without another N. SDK/game response remains
an explicit model; software return is not game consumption.

DLL candidate:
`docs/steering-audit/signal-plugin-20261009/scoped-candidate/ets2la_plugin.dll`
(local ignored artifact), version **1.59.3-up-signal-scope**, SHA-256:
`0aba58549d2a7d008bc620424a43fa0f28c840e1688687d0ffd5effe6e434dab`.
The adjacent `build-receipt.json` pins source and produced files. Rebuild with
`tools/build_signal_plugin.py --scoped` and the verified source/fmt archives.
MSVC build, dual-schema probe, decoder/layout tests and DLL load/export/unload
passed offline. Neither SCS entrypoint was called; ETS2 was not started.

## Traffic/brake authority and original curve comparison

The legacy decoded list remains display data. It cannot restore a brake after
the coherent capture rejects duplicate identity or quaternion/kinematics.
Existing route selection and TTC protection remain the only traffic demand
path; a conservative 2.6 m reference caution band is retained from the old
behavior and labeled protective/unassigned, not confirmed lane membership.
Emergency demand overrides comfort immediately. Existing latched target-loss
handling still applies; invalid or empty traffic never certifies clearance.

`tests/fixtures/oct8-observed-route-prefix.json` retains 406 analytically
recovered original planar vertices over 785.217755 m. Reprojection residual
is below 2.3e-11 m; missing tail/elevation are not interpolated as evidence.
Actor test Y=10 m is an explicitly supplied model layer. Calculation speed is
missing in the historical curve records; application speeds are labeled
proxies, and requested-speed variants are scenario inputs.

At progress 333.58/340.72/346.80/365.32/371.47 m the reconstructed curve-only
targets are approximately 50.12/48.93/47.86/42.07/40.92 km/h or higher.
They do not demonstrate an early reset to 20 km/h. The later tight curve near
417 m legitimately requests about 21–22 km/h (radius about 18.9 m). No guessed
planner or geometry correction is applied to suppress that real constraint.

## Hold comfort: same-input closed model

Unvalidated plant: acceleration = `(2.2*T - 4*B)/1.4 - .12 - .004*v²`,
0.12 s transport, 0.35 s pedal response, integration <=0.01 s; tick jitter
33/50/80 ms. Modeled front reference is 4 m. This is not measured ETS2 jerk,
traction or loaded hill holding. Baseline is the preserved installed 1.3.1
runtime; candidate changes only the near-stationary acknowledged hold floor.

| Approach, both modes | Maximum absolute model jerk before → after (m/s³) | Front gap before → after (m) | Stop time before → after (s) |
| --- | --- | --- | --- |
| 20 km/h | 6.6385 → 6.6385 | 5.443991 → 5.443991 | 23.339 → 23.339 |
| 35 km/h | 5.7774 → 4.8753 | 5.579190 → 5.579081 | 20.792 → 20.792 |
| 50 km/h | 5.5529 → 4.2179 | 5.639667 → 5.639102 | 20.316 → 20.349 |

The largest modeled stopping-position difference is 0.57 mm closer, with no
entry overrun; it is reported rather than called identical stopping distance.
Moving deceleration and jerk above 0.5 m/s remain unchanged. Each run stays
active, resumes without N, has zero positive-pedal overlap and zero parking or
hold-brake-zero writes. Crawl remains 3.35–3.84 s / 2.22–2.64 m in this model;
the task does not claim elimination of all live creeping. Drift/emergency
checks retain their safety priority and existing limits.

## Existing diagnostic event capture

No new collector, source read or control command is added. PedalJournal uses
the already consumed immutable source, existing 30 s/10 Hz history and 64 KiB
physical write ring. Four event types are supported: `AVOID_OBSTACLE`,
`BRAKE_SOURCE_CHANGED`, `UNASSIGNED_SIGNAL`, `TECHNICAL_AUTHORITY_LOSS`.
Each stores original input/context/time, actor/TTC or signal receipt when
available, selected source and subsequent physical calls. Missing input fields
remain missing. AVOID_OBSTACLE uses the actual locally returned traffic packet.

One pending event slot, maximum four submissions/minute; busy edges coalesce
into counts for the fixed four kinds, not an unbounded dictionary/queue.
Receipt budget is 32 KiB, sealed history <=1 MiB, each pre/post detail snapshot
<=64 KiB. Immutable rows are shared until expansion. Existing live history,
one sealed slot and one worker-owned job can coexist; those bounded snapshots
are separate from the live ring's budget. These are accounted byte limits,
not a claimed process-RSS ceiling. Counts and loss/incompleteness are explicit.

The existing single-job background replay worker writes:
`<UltraPilot>/route-diagnostics/steering-replay-<UTC>-significant_event.json`.
No arming is needed after an authorized deployment; ordinary startup enables
the existing automatic diagnostics. Pre-event history is sealed at the event;
up to 0.1 s of following writes are included, or shutdown seals available tail.
An automatic-disable incident takes priority over a pending normal event and
retains its compact receipt; superseded event history is explicitly marked.
It cannot replace the original first fault. Steering/combined export survives.

Disk quota is eight significant-event files / 16 MiB across that directory.
The worker checks before export and verifies the new temporary file fits the
remaining budget before atomic publication. It never deletes/overwrites old
evidence. A full quota reports `SIGNIFICANT_EVENT_EXPORT_DISK_QUOTA`; no file
is falsely labeled saved. Automatic-disable export is independent of this
normal-event quota. Further events require separately authorized archiving or
removal of old files; no cleanup was performed here. Hash/order/reference
checks remain, and `confirmed=false`, `runtime_authorized=false` always remain.

A 60 s test seals a warmed 30 s history, continues collecting, then verifies
the sealed earlier interval still exists. Other tests cover source mutation,
fault while the worker is busy, post-fault safety writes, capacity, oversized
receipt, disk byte/file quota and corrupt export. No expectations were removed.

### Measured overhead

Offline production components: SDK/Engine 60 Hz, producer 20 Hz, 60 s,
3,600 Engine ticks and 1,200 producer ticks, multiple modeled brake edges.
All mapping frames, chronological physical calls and IPC read counts match
with diagnostics off/on. Test-only unbounded backend assertions are excluded
from retained-heap measurement. Disk worker is excluded from tick timing.

| Operation | Off median / p95 / max (ms) | On median / p95 / max (ms) |
| --- | --- | --- |
| Engine flush | 0.5170 / 1.0602 / 16.1834 | 1.5001 / 1.9785 / 4.0229 |
| Producer tick | 0.3228 / 0.6113 / 2.2847 | 0.5190 / 0.7368 / 1.3886 |

These are separate run distributions, not paired per-tick differences. The
off-run scheduling outlier does not establish a negative maximum overhead.
Engine p99 is 1.6727 ms off / 2.4557 ms on; producer p99 is 0.9342 / 0.8523 ms.
The first warmed event seal takes 0.2926 ms; two later coalesced calls take
about 0.0026 ms each. One post-tail seal takes 0.0159 ms. These three calls are
not a robust latency percentile sample. Held diagnostic heap increment is
805,814 bytes (about 787 KiB), including the warmed sealed slot. Live summary
is 368,438 accounted bytes (maximum 368,440) / 302 regular + 9 change rows /
30.10 s, zero summary capacity loss/capture failures. The sealed event retains
355,485 history bytes plus a 2,382-byte receipt. Detailed ring is 65,110 bytes /
0.15 s and 7,560 evicted calls; that short detailed resolution remains
explicitly partial. Test mock history is excluded; no RSS ceiling is inferred.

The bounded legacy signal decode/selection operation (40 heads, 10,000 points,
500 cached calls) costs median 0.1370 → 0.3305 ms, p95 0.2177 → 0.6560 ms,
maximum 0.3269 → 6.2266 ms. Added all-head coverage validation has a cost;
these operation timings are not end-to-end cadence or a live jitter guarantee.
Geometry preparation remains about 12.2 ms and is cached. No scheduler,
steering cadence or timeout is changed to conceal this overhead.

## Checks and release boundary

Sixteen steering cases and twelve existing longitudinal comfort cases are
numerically identical to the preceding preserved benchmark, including all
CTE/heading/step/rate metrics. Near-stop differences are separately shown
above. Targeted native/signal, traffic, hold, mode-observer, arbitration,
launch, reverse, stale/identity, release, combined and replay regressions were
run; final aggregate result is recorded in the verification addendum below.
`compileall` and `git diff --check` are required final checks. Full pytest is
reserved for the user.

Verification addendum: **532 passed, 20 subtests passed** in the explicit
27-file targeted integration selection (64.94 s); no full-suite run. The final
additional nested-context ownership test and original pedal export/history
regressions passed together: **35 passed** (6.44 s). Targeted native/event
checks after adding unassigned-head ownership to the immutable receipt passed
with the original automatic/history regressions: **54 passed** (8.00 s).
These overlapping selections are not added to the 532-test count. Native
checks also passed the Windows isolated producer probe and DLL entrypoint
load/unload (without initialization). `compileall` passed. Final diff check
has no whitespace errors; normal Git LF/CRLF notices are not code failures.
One earlier broad run exposed a real unchanged-metadata observer race and an
incorrect foreign-head fixture; both were corrected before this final run.
The fixture now explicitly faces the opposite direction, and its original
same-facing geometry is retained as a separate required-takeover regression.

Runtime content differences requiring a coherent later deployment are:
`core/engine.py`, `core/acc_following.py`, `core/longitudinal.py`,
`core/navigation/longitudinal_diagnostics.py`, `core/navigation/prefab_signals.py`,
`core/navigation/road_network.py`, `core/sdk/ets2la_data.py`,
`core/sdk/signal_snapshot.py`, `core/service_brake_hold.py`,
`core/steering_replay.py`, `core/transmission_mode.py`,
`plugins/autopilot/main.py`, `plugins/map/main.py`, `ui/visualization.py`,
plus changelog and the scoped DLL candidate at the existing game-plugin
location. This is a **preparation list**, not permission or a deployment
command. Settings, commit marker, controls and original captures were not
changed. Controller/ACC/DrivePolicy plugin files are content-equal and require
no replacement for this delta.

**Remaining boundary:** actual producer prefab UID/node/origin/group values
and source coverage at the missed live red have not been captured. Offline
source/ABI tests establish consistent transport and the supported selector,
not live namespace agreement or coverage of all intersections. Likewise the
original short brake actor/TTC is absent. Automatic event capture now closes
that retention gap for future data but cannot restore lost history. Effects
of uninterrupted SDK braking, loaded hill holding and stop-front geometry
remain unconfirmed in ETS2. No further drive is requested here. The immediate
next gate is the user's full suite; game confirmation requires separately
authorized coherent deployment, not mixing this candidate with the old DLL.

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python -m pytest tests -q
```
