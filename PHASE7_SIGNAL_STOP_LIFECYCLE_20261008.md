# Directed signal stop lifecycle — 2026-10-08

## Verdict and build binding

**PASS for the reproduced production defects and supported offline lifecycle;
NOT VERIFIED for this candidate's ETS2 effect and the missing historical ACC
predicate.** No new drive, deployment, arming, commit or push was performed.
Steering, LanePath geometry, controller gains, scheduling, original observation
times and the 500 ms safety limits are unchanged.

Starting HEAD: `787d012a2a78ac917bb5506e0958c32d8d06575f`, with the existing
coast/signal-scope and automatic pedal-history work already present. All those
changes and the original incident files were preserved. Project/version rules
and the previous Phase 7 stop reports were read; no applicable AGENTS.md exists
in the checkout or its ancestors. This report describes the additional Oct 8
changes, not the entire accumulated diff.

At entry, Engine, transmission mode, arbitration, signal reader, pedal
diagnostics, Autopilot, ACC, DrivePolicy and visualization matched the installed
runtime bytes. Map matches after LF/CRLF normalization. The installed runtime
was used **read-only** for the baseline comparison; `commit.txt` was not used
as implementation evidence. Current core candidate changes now differ from
the installation; plugin source implementations are unchanged in this task.
Autopilot remains at its already pending **1.3.0**, ACC **1.1.4**, DrivePolicy
and Map **1.1.0**. Core/UI fixes do not release unchanged plugins.

Baseline SHA-256 identities:

| Installed file | SHA-256 |
| --- | --- |
| core/engine.py | `24d5cb6517bcf759e16663858a5d731a2fc6c40471696b4909ee532021d056ed` |
| core/service_brake_hold.py | `716495877917056a1a44fd1a9d7944d77ac0d3736e7efe8252aee9e7f40f9bf1` |
| core/sdk/signal_snapshot.py | `13100b7db2a073f5dcf013ca65b565b59da7efb68357ec2778607ed4c44b3ff3` |
| core/navigation/longitudinal_diagnostics.py | `3701d9aca3c80efc6cb2edbbd00beb351cabbff15bba20ab78d4d731c55745b4` |

The local ignored artifact `docs/steering-audit/oct8-stop/runtime-identity.json`
records source/install hashes and byte/normalized comparisons. It is not a
deployment receipt.

## Preserved incident evidence

All files below are under the installed `UltraPilot/route-diagnostics`, read
without modification. The full installed `ultrapilot.log` was matched to the
same session/activation and original monotonic times, not filename time alone.

| UTC filename suffix | Kind | SHA-256 | Integrity |
| --- | --- | --- | --- |
| 20261008T152856.137074Z-automatic_disable.json | pedal | `abdaee6fbc0ac125f8a3cced6694fef60d2e69ff9bbe45065d8b37e23be444a2` | valid |
| 20261008T152856.234394Z-automatic_disable.json | dense | `97c407e7debff116dfbc9a0da865d857dd6210805bb3e6a5f9ab5d2af1863e1e` | valid |
| 20261008T152900.816327Z-automatic_disable.json | pedal | `7e4689f50b5d0049d5f19696251249e748e0bb87aaf0ab567c17490e5e8948cf` | valid |
| 20261008T152951.404575Z-automatic_disable.json | pedal | `cdd043af64fa5f1e8812f77ec9fe4259d4956fdb3a3fe32cb066b2db468a29a5` | valid |
| 20261008T152951.514571Z-automatic_disable.json | dense, 899 samples | `e9c436a61d9575d6db86f82f6f99c6305343db27e33ace17bafab95ad99e8278` | valid |

Common context: game session **1**, map **promods-1.59**, dataset
**d6cc7936fce4e902761abb5d**, intent
**7b59e6e7e688414ca9cb19bf420dc8bf**, revision **9**, build
**92d6630f3af040d28cc19a5b79f75d67**. Geometry identity is
`[lane_path,0cb7fb288d13eaf63614114939a0e03ed719f2c20a7a375535501d0183444d05,true]`.
Activation epochs differ: **13902174745700**, **13914490702200** and
**13919234035900** respectively. They were not merged into one activation.

### 17:29:51 — loss of the brake chain, not lease expiry

The pedal history covers **30.0813975 s**, 248 regular samples and 72 changes.
Its exported history reports no capacity loss/incompleteness. This does not
establish completeness of nested signal fields: those were separately lost
to an input snapshot budget. Detailed writes retain only the short incident
tail. Summaries below refer to returned physical writes, not game consumption.

| Monotonic write-return time (s) | SDK frame | Signed speed (m/s) | Gear | Written throttle/brake | Recorded hold |
| --- | --- | --- | --- | --- | --- |
| 13964.6309519 | 176259616 | +2.917278 | 7 | 0 / 0.2368212 | braking |
| 13964.7544963 | 176359612 | +2.964804 | 7 | 0 / 0.5774952 | braking |
| 13964.8808845 | 176526272 | +2.489718 | 7 | 0 / 0.6945341 | braking |
| 13965.0085974 | 176626268 | +1.924356 | 7 | 0 / 0.4160041 | braking |
| 13965.1338818 | 176759596 | +0.6828014 | 7 | 0 / 0 | prior braking binding |
| 13965.1855577 | 176826260 | +0.1942281 | 7 | 0 / 0 | absent |
| 13965.2498059 | 176876258 | −0.0110887 | 0 | 0 / 0 | release |

There are **15 observed drive/brake transitions**, ignoring coast, in the
retained sampled history of this activation. This is not an exact count of
every physical edge in the ride.

The first Autopilot comparison used frame **176876258**, observation
**13965.1997171**, gear 0, speed −0.0110887, checked at **13965.2254018**.
The later intervention header contains frame **176909590**; it is not the
frame used for that comparison. Engine independently refused the same
zero-ratio lifecycle at **13965.2277751**. Its command was based on frame
**176826260**, observed **13965.1471476**, computed **13965.1893287**, expiring
**13965.5413804**: **313.6053 ms remained**, observation age **80.6275 ms**,
decision age **38.4464 ms**, identities equal. No expiry/frame-pairing fix was
needed here.

The reproduced production defect is the Engine continuation predicate: a
forward-started acknowledged planned brake was retained only at near-zero
speed, with a signal lock, or in a refresh transition. A temporarily unobserved
head had no signal lock. At positive approaching speed, a zero demand could
physically release the brake; `after_write` then correctly removed the broken
chain. A later stationary gear 0 consequently lacked a valid planned hold.
This is the first reproduced loss of stop priority, before the ratio error.

### 17:28:56 — measured movement during an existing hold

History: **30.0909724 s**, 265 regular samples, 18 changes. Engine compared
frame **121728464**, observed **13909.9335061**, checked **13909.9556096**:
gear 7, signed speed **+0.0612643994 m/s**, valid telemetry, parking brake false.
The existing holding threshold is **|speed| > 0.05 m/s**; it was exceeded.
The preceding returned brake was **0.118228793**, throttle zero, holding state.
The command still had **301.3724 ms** remaining, with matching identity.

The exact reason for that physical movement (hill, insufficient brake, input
mix, game consumption or another effect) is **NOT VERIFIED**. It is not
relabelled as noise and the threshold is not raised. Boundary reproductions
retain acceptance at ±0.049 and refusal at ±0.051 m/s; observed R is separately
refused. Software write continuity does not prove physical hill hold.

### 17:29:00 — precise ACC invalidity not recoverable

The first retained intervention says `acc: invalid longitudinal observation`
at **13914.5147855**, frame **126228284**, original observation
**13914.4750973**. Its details are
`UNVERIFIED_SNAPSHOT_BUDGET_EXCEEDED`. The Engine log separately compares a
**missing** command at **13914.5088861** after reading it at
13914.5028763–13914.5029629. The compared vehicle was valid, gear 10,
speed +9.411418915 m/s. Neither fact proves the discarded ACC packet valid.

The rejected ACC packet's original valid flag, frame/time, preceding speed
sample and rejection reason were not retained. The code distinguishes an
invalid vehicle observation from regressing/coherence or >500 ms control
interval failures. Those alternatives cannot be historically selected from
this export. Engine-before-first-Plugin activation with the recorded forward
speed passes through the existing bounded zero-drive handoff; an actually
invalid ACC input still refuses propulsion. No speculative ACC change was
made. The exact rejected ACC input remains the missing historical evidence.

## Signal origin and production path

| Component | Actual contract and role |
| --- | --- |
| Existing 1.59 producer/sidecar | Local prefab semaphore ID, raw color/timer and placed pose; sidecar lifecycle, generation, frame and original QPC observation time. Python polling is not acquisition. |
| ETS2LAData / SignalReader | Decode signed tiles/quaternion and enum; equal envelope sequences, active flags, generation/frame, placement ambiguity and 500 ms age checks. No default controlling ID is invented. |
| Map preparation | Authored control IDs on the selected directed prefab curve and world/elevation transform. Known control entry is distinguished from a live observed head. |
| RouteSignalSelector | Match that local ID, placed bounds, height and direction to the prepared passage. Unassigned nearby heads are detection only. Ambiguity, lost lock or unsupported metadata cannot supply green. |
| Engine traffic publication | One consumed signal/stop target and brake request, with original times and the longitudinal identity. Raw HUD detection remains a different field. |
| DrivePolicy / ACC | Same distance-based stop envelope lowers target; external brake inhibits drive. Their zero demand does not prove clearance. |
| Autopilot / final Engine arbitration | One paired command and physical owner. Current identity/freshness validated before execution; acknowledged planned hold takes priority until confirmed clearance. |
| HUD | Qualified observed head, unobserved authored control entry, and unassigned detection have distinct labels. |

`signal_id=1` is not globally invalid: IDs are local to placed prefabs. The
parser copies the source ID and never converts a missing ID into 1. The raw
decoder emits red/yellow/green/off/sleep; the selector explicitly creates
**unknown** for a known authored control entry whose head cannot be qualified.
The first stop witness really records ID 1/color unknown, but the full consumed
signal was dropped. The particular acquisition/assignment failure and whether
the source had a red head nearby cannot be reconstructed. No claim is made that
the DLL emitted unknown, that ID 1 was foreign, or that every recorded brake
was caused by a false head.

The remaining `passages=None` geometric acquisition fallback was reproduced
and removed. Empty prepared metadata was already detection-only in the
preserved prior work. There is no replacement nearest-head authority. A known
authored control with missing observation remains a conservative unknown
approach constraint, never green clearance; this is different from braking
for an unassigned nearby object. Missing authored metadata cannot manufacture
a confirmed semaphore and may require driver takeover.

## Implemented lifecycle and diagnostic repairs

1. Continue the same acknowledged, activation/route-bound planned brake through
   **BRAKING → HOLDING**, including positive approaching speed without a live
   signal lock. Current command, SDK, receipt-chain and last-write checks remain
   required. A zero demand or a change of selected producer cannot clear it.
2. Use the existing distance/deceleration request for **positive** adjustment
   on the same unobserved authored entry while moving. No zero edge, arbitrary
   new holding constant, extra regulator or stationary brake seeding is added.
3. If that exact authored head recovers as an actual fresh red/yellow, bind its
   receipt to the original passage/ID and authority. Preserve the initial stop
   witness. Previously only the initial missing snapshot was considered, so
   later valid observations could never authorize eventual clearance.
4. Release only through the existing two advancing same-head green acquisitions
   at least 100 ms apart, unchanged lifecycle/authority, and no unresolved other
   stop reason. Then use the existing mode-0 throttle or mode-3 D-confirmation
   launch. Unknown/missing/stale/foreign green never releases the hold.
5. Preserve the original selected producer's reason at the final boundary
   instead of labelling a traffic-light request as generic `acc brake demand`.
6. Give optional crossing/display/following diagnostics their own sub-budget.
   Preserve the consumed signal inside the same fixed input allocation using
   the existing bounded lossless codec where needed. Mark omitted attribution
   with `capture_incomplete`; retain unobserved stop geometry/distance provenance
   as well. Summary capture failures now mark incomplete history explicitly.

No new collector, SDK/IPC read, INFO-per-tick event or unbounded queue was added.
The detailed ring stays **64 KiB**, history **1 MiB** with the same row/event
limits. Existing steering and combined exports, immutable pairing, hashes,
first intervention and subsequent safe writes are preserved.

## Reproductions and quantitative comparisons

Initial narrow run: **4 failures before the fixes** (unassigned red authority,
two transmission-mode brake-chain gaps, and discarded consumed signal fields).
A further recovered-head lock test failed before its lifecycle repair. The
unobserved-target export test separately failed because distance basis/entry
geometry was missing. The same expectations pass after the repairs.
An actual Map-prefix integration case also reproduced a missing original
ID/color when a valid producer carried the target only inside its signal
snapshot. A shared immutable target accessor now covers both representations
for the hold, profile and original reason; its new assertions pass.

Existing geometric-control fixtures were corrected to carry an explicit
authored passage. Safety, freshness and export assertions were retained; no
test was changed to accept a missing control binding. The old head-distance
benchmark is explicitly a counterfactual profile with authored selection, not
a restoration of the removed fallback.

`tools/run_oct8_stop_lifecycle_bench.py` loads only the baseline core methods
read-only. Both variants use actual SignalReader, policy, ACC, Autopilot,
Engine, Controller and chronological BytesIO backend calls.

| Same input/model | Before | After |
| --- | --- | --- |
| Supplied 52 approaching/standstill SDK inputs, mode 0 | 3 coast ticks, lost hold, automatic ratio rejection | 0 coast ticks; active holding, no unconfirmed drive |
| Same supplied inputs, mode 3 | 3 drive ticks without clearance, lost hold | 0 unconfirmed drive ticks; active holding |
| Closed-loop 35 km/h, head absent during approach then actual red/green, mode 0 | 13 drive/brake transitions; no restart in 103.054 s | 2 expected transitions; restart without N in 23.339 s |
| Same model, mode 3 | 13 transitions; no restart in 103.054 s | 2 transitions; restart without N in 23.339 s |
| Mode-0 missing-head model peak deceleration / peak absolute jerk | 1.693 m/s² / 24.639 m/s³ | 1.153 m/s² / 4.243 m/s³ |
| Mode-3 missing-head model peak deceleration / peak absolute jerk | 1.599 m/s² / 31.973 m/s³ | 1.153 m/s² / 4.243 m/s³ |
| Normal observed red, both modes | Brake starts 67.765 m before entry; stop at 90.422 m; model front 5.578 m before entry | **Numerically identical** |
| Normal observed red peak deceleration / peak jerk | 1.153 m/s² / 4.243 m/s³ | **Numerically identical** |

The closed model is the existing uncalibrated plant: command response 0.35 s,
transport 0.12 s, acceleration `(2.2*T−4*B)/1.4−0.12−0.004*v²`, integration
steps ≤10 ms, deterministic jitter 33/50/80 ms, model front extent 4 m. It
does not prove SDK input consumption, painted-line clearance or hill holding.
Before/after completion times differ because the baseline never resumed;
peak metrics include each model's available full run. The normal-red run and
candidate missing-head run have exactly the same physical trajectory and
brake profile. No post-hoc comfort threshold was introduced.

All eight read-only-runtime comparison cases have zero simultaneous positive
pedals, no parking writes and no brake zero during modeled holding. The
existing 20/35/50 km/h straight/opposite-direction/turn matrix also completes
all nine current profiles with stop and green restart, without parking writes.
The new regression freezes recovery against the existing valid-red profile.

## Verification, overhead and limits

- **411 targeted tests passed in 136.98 s**: real producers, both automatic
  modes, repeated red/hold/green cycles, actual Map prefix/LaneId transitions,
  missing/foreign/ambiguous/stale signals, interruption, R/backward motion,
  backend failure, IPC pairing, emergency, manual disable, automatic/combined
  export integrity and the prior export regressions.
- Four additional full-producer unassigned-red cases passed in both modes
  (absent or empty prepared metadata); no traffic-light brake or hold is created.
- Final post-accessor stop/signal/export group: **164 passed in 39.42 s**;
  it includes the 20 Oct 8 cases, both closed recovery models and unchanged
  valid-red profiles. The intermediate Oct 8-only run was 20/20. Counts from
  overlapping runs are not added as unique tests.
- Steering: **16 cases exactly equal** to the prior `oct7-coast-steering-current`
  benchmark. Longitudinal comfort: **12 cases exactly equal**; emergency response
  remains immediate in the explicit model. These are offline results.
- Automatic diagnostic benchmark: 60 s, 3600 SDK/Engine steps at 60 Hz, 1200
  producer steps at 20 Hz. Every mapping frame, physical call and Engine IPC
  read count is identical with diagnostic capture on/off. Engine CPU median /
  p95 / maximum: off **0.480 / 0.778 / 1.636 ms**, on
  **1.404 / 1.673 / 3.528 ms**. Producer: off **0.301 / 0.469 / 0.899 ms**,
  on **0.491 / 0.590 / 1.205 ms**. These are separate distributions, not paired
  worst-case incremental latency and not Windows live scheduling evidence.
- History retains **30.1 s**, 302 regular rows, **356,704 accounted bytes**,
  maximum **359,070**, zero capacity drops/capture failures in that benchmark.
  Detailed ring retains 20 calls/0.15 s and reports 7190 evictions, as designed.
  On/off held-heap difference is about **386 KiB**, excluding the cleared
  test-only unbounded backend assertion list. Rich transient changes can have
  different costs and are covered by bounded export regressions.
- Final compileall and `git diff --check`: **PASS**. The full pytest suite is
  reserved for the user and was not run.

Artifacts are local ignored files under `docs/steering-audit/oct8-stop`:
`source-gap-closed.json`, `prefab-model.json`, `steering.json`, `comfort.json`,
`automatic-overhead.json`, and `runtime-identity.json`. Original captures remain
in the installation. No large raw captures were added to Git.

Remaining limitations: exact discarded ACC predicate at 17:29:00; physical
origin of motion at 17:28:56; historical live-head failure behind unknown ID 1;
SDK brake-consumption semantics, grip/slope/load behavior, signal-to-lane
coverage and real stop-line/body extent. Standstill activation without an
existing forward-started brake chain remains explicitly unsupported for safe
autonomous holding in simple automatic. Missing actor coverage cannot clear
another latched stop reason. No optimistic restart after a technical fault.

Supported offline lifecycle is ready for the user's full-suite review.
**This is not a claim that all three historical incidents are fixed in ETS2.**
No additional drive is requested in this task.

Changed in this task: `core/engine.py`, `core/service_brake_hold.py`,
`core/longitudinal.py`, `core/sdk/signal_snapshot.py`,
`core/navigation/longitudinal_diagnostics.py`, `ui/visualization.py`, directed
signal fixture/export tests, `tests/test_oct8_stop_lifecycle.py`,
`tools/run_prefab_signal_bench.py`, `tools/run_oct8_stop_lifecycle_bench.py`,
and documentation. Existing plugin changes from the prior task are preserved.

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python -m pytest tests -q
```
