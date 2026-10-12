# Signal approach, phase timing and moving clearance

**OFFLINE VERIFIED for countdown transport, anticipated stopping and moving
same-signal clearance. NOT GAME VERIFIED.** This is not closure of every observed
early-red creep, manual-reactivation fault, intersection or physical dilemma.
Base `787d012a2a78ac917bb5506e0958c32d8d06575f`; existing dirty packet-refresh,
native direction, traffic, hold, roundabout and distance changes preserved.
No deployment, arm, game control, commit, push or whole-suite pytest run.

## Criteria fixed before modification

These are offline software/model criteria, not ETS2 comfort thresholds.
For the same placed PPD and uncalibrated existing vehicle model:

- New, same-head green acquisitions at least 100 ms apart must release the
  signal-only braking commitment while moving, within the next valid Engine
  write; standstill must still use the existing bounded restart.
- Insufficient measured green must produce a stopping envelope before the
  color changes where stopping is feasible. Enough green must not invent red.
- No inferred future green, timer retimestamping, simultaneous positive pedals,
  parking writes, stale or foreign authority acceptance.
- An uninterrupted red approach must stop before the derived entry boundary;
  a comparison may not buy improvement by passing that boundary on red.
- Report physical-model deceleration/jerk and actual stop gap without pretending
  they are identified ETS2 dynamics or a painted stop line. Numerical steering
  and unrelated comfort benchmarks must remain identical.
- Missing/invalid timers cannot grant clearance. A model with no calibrated
  truck dimensions/grip cannot certify a physical dilemma-zone maneuver.

## Installed build and evidence identity

No AGENTS.md was found. Plugin versioning and the existing native-direction,
distance/continuous-stop reports were read. At task entry all **20** installed
`manual-deployment.json` hashes matched receipt
`signal-direction-20261010T182646Z` (identified by its backup directory). Source
and installed runtime content matched after LF/CRLF normalization. The six new
core edits below now differ; the installed files still match their receipt.
Commit markers alone were not used as proof. Autopilot **1.3.3**, Map **1.1.1**,
ACC **1.1.5**, DrivePolicy **1.1.1** declarations are unchanged: their plugin
implementations are not edited by this task. The DLL is unchanged
`1.59.3-up-signal-scope`.

The following seven original exports passed existing codec/hash/count checks:

| Original suffix, UTC 2026-10-10 | Kind | Packet/timing samples |
| --- | --- | ---: |
| 183457.854104Z-manual_disable | Dense steering | 781 |
| 183722.666709Z-manual_disable | Dense steering | 1,272 |
| 183729.534607Z-automatic_disable | Pedal incident + decision history | 1 |
| 183729.807720Z-automatic_disable | Dense fault | 1 |
| 183933.481281Z-manual_disable | Dense steering | 1,119 |
| 183748.351047Z-plugin_stop | Passive timing | 487 |
| 183939.747040Z-plugin_stop | Passive timing | 144 |

They remain under the installed `route-diagnostics` directory unchanged. Earlier
18:41 local evidence was not substituted for this 20:34–20:39 local episode.
`tools/analyze_oct10_signal_approach.py` reproduces receipt/integrity checks and
decodes actual history/immutable references. Large decoded/model output stays
ignored under `docs/steering-audit/oct10-approach/`.

The creeping episode binds activation **8076403172500**, session **1**, map
`promods-1.59`, dataset `d6cc7936fce4e902761abb5d`, intent
`17d180e277514c08a4259f3d814c8fd6`, revision **13**, build
`91c5d0eb3ad54ff8953b2eb2b084e5fa`, geometry
`47ed675412749ee2bb11ad2c6af45908fb77eb781ab48c9ff496700c258f19f8`.
Locked signal **1**, passage
`45540e750098d8f1fc11bc8b76cd20b1ae161420a94ae48b90dad1891389062f`,
derived entry progress **267.7427904 m**, entry XYZ
`[34753.4735007, 6.90234375, 45663.9580174]`.

## Proven moving-clearance defect, not a guessed ACC cause

The incident retains **219 regular summaries + 21 changes** over
**30.1516513 s**, 8117.2298046–8147.3814559, and **15 detailed pedal events**.
It is incomplete: **1,621 capture failures** are explicitly reported. Full
backend detail covers the short later fault window, not the entire approach.

| Monotonic time | Original signal acquisition | Actual SDK speed | Derived target distance | Confirmed software pedal values | State |
| --- | --- | ---: | ---: | --- | --- |
| 8117.2298046 | red, generation 6549, 8117.1262401 | 3.455 km/h | 33.031 m | T=0, B=0.00363127 | braking |
| 8136.5813681 | green, generation 7188, 8136.5061868 | 3.321 km/h | 14.748 m | T=0, B=0.00792348 | braking |
| 8140.1282248 | same green/activation | 3.310 km/h | smaller target distance | T=0, B=0.00792348 | still braking |

The first green summary has SDK frame **191092356**, SDK observation
**8136.5383064**, backend sequences **3718–3720**. Its selected source is
`continuous_service_hold`, reason `waiting: stop clearance is not
producer-confirmed`. This is the existing write-summary witness; it does not
prove when the game consumed the values. Native sidecar and vehicle SDK frame
domains are not equated.

The consumed stop was initially yellow at decision **8109.5312067**; lock
acquisition **8109.5546244**, generation **6316**, native frame **188061211**,
lifecycle **108192130337703**. The prior Engine called green release only when
`abs(speed) < 0.05 m/s`. Thus a correctly refreshed green could never clear the
stop while still creeping. ACC's `external braking inhibits speed drive` is a
consequence of the continuing signal demand, not evidence that its PID invented
this hold. Reproducing the production order and physical writes proves this
branch independently of missing historical detail.

The later **20:37:29** technical fault is different: activation
**8147165030000** compared a traffic packet from **8145579392300**, the last
cancelled N request. The original creeping drive epoch **8076403172500** must
not be substituted for that rejected immutable packet. Same route build/revision
did not mean the same activation. The preceding N attempts also logged identity
refusal. The follow-up [PHASE7_REACTIVATION_TRAFFIC_20261010.md](PHASE7_REACTIVATION_TRAFFIC_20261010.md)
proves and fixes the bounded initialization defect offline; old commands remain
rejected. Exact historical IPC interleaving and game restart are not verified.

## Countdown origin and interpretation

Pinned native source `scoped-candidate/src/processing/traffic.cpp` copies
`traffic_light->state_time_remaining` into `return_object.time_remaining`.
`traffic_light.hpp` identifies a float at offset 0xA0. The existing Python
reader obtains that float at row byte 36 and state at byte 40; the existing HUD
renders it in seconds. **Seconds are that existing consumer contract**, not a
new calibrated countdown-rate measurement. Native states: 0 off, **1 orange to
red**, 2 red, **4 orange to green**, 8 green, 32 sleep. Both yellows still stop;
the new compact/history fields preserve their distinction.

The old compact signal discarded `time_left` and native `state`. The retained
historical summaries therefore cannot reconstruct the user's one-second green
or verify its rate/initial braking onset. No historical timer or owner was
filled from a model. Native acquisition timestamp/generation/lifecycle stay
original; reading the same buffer never renews a countdown.

## Implemented common path

1. Existing prefab preparation adds the directed arc extent and conservative
   curvature ceiling to its existing bounded passages. It does not edit
   LanePath/centerline, topology, route authority or the native ID namespace.
2. The existing selector computes a phase plan only for its already-qualified
   head. It deducts original acquisition age, estimates capped acceleration or
   deceleration from current SDK speed toward the authored/road ceiling and
   includes front/standoff, full directed prefab extent, **20 m unmeasured
   combination clearance** and **1.5 s planning reserve**. These are explicit
   planning assumptions, not measured body length, a conflict polygon or grip.
   No 1 km coverage or future cycle is inferred from one timer.
3. Insufficient current green requests the **same existing 1 m/s² distance
   stopping envelope** used for red by Engine, DrivePolicy and ACC. It keeps the
   actual color green; it never creates a red lamp/HUD identity. No additional
   speed controller, pedal filter, minimum creep speed or arbitrary brake
   floor is added. Invalid/missing timer cannot certify clearance. Scoped
   metadata missing its extent also cannot certify sufficient reserve; legacy
   unscoped color behavior is preserved, not promoted to timed forecast proof.
4. Preferred deceleration reserve is distinct from the existing yellow-light
   **4 m/s² full-brake planning bound**. Treating the preferred onset as an
   impossible-stop boundary suppressed useful anticipation, so the candidate
   does not make that mistake. Inside the latter bound, `green_dilemma` is an
   explicit **zero-drive coast** in the existing arbiter; it cannot release a
   hold. Red/emergency demand still wins immediately. This is not certification
   of an unavoidable physical dilemma or permission to pass a later red.
5. Two fresh acquisitions of the same locked green, >=100 ms apart, can clear
   the signal commitment while moving. Engine first preserves its positive
   hold through steering/IPC, then rechecks current signal/authority and the
   exact already-validated fresh longitudinal decision before restoring that
   decision. It does not substitute a launch probe or pre-stop throttle. Other
   stop evidence remains latched. At standstill it still uses the established
   bounded simple-auto throttle/D restart. Gear/R/backend/identity/freshness
   guards and the 500 ms limits remain.
6. Existing journal/history append `signal_native_state`, `signal_time_left_s`
   and `signal_phase_plan`; original signal frame/time/generation and actual
   write ranges already exist. History field indices are append-only. The
   indexed source-codec key table is not changed, preserving old incident
   decoding. The final restored source is recorded instead of falsely leaving
   `continuous_service_hold` attached to an applied drive command. No new
   SDK/IPC read, collector, worker or synchronous export is introduced.

## Before/after proof and closed model

At entry the four new regressions failed (lost countdown, moving green in
both modes, ending-green envelope). Rechecking with the **installed Engine
method and compact function**, plus the former color-only selector behavior,
again gives **4 failed**. Candidate gives PASS. Those counterfactual methods
are isolated in the test process; installed sources and original evidence are
not changed. Paired model `before` isolates the same former two behaviors; it
is not a reconstructed live physics run.

`tools/run_oct10_signal_timing_bench.py` runs **48 paired cases**: 20/35/50 km/h,
both automatic modes, red-stop/green restart, moving green, ending green and
enough green. It uses the original placed PPD/own scoped head from the
native-direction fixture, an explicit 100 m straight model prelude (60 m for
ending green), real reader → Policy → ACC → Autopilot → Engine → Controller →
chronological SCS BytesIO writes. Plant: 120 ms transport, 350 ms actuator lag,
10 ms integration, dt jitter 33/50/80 ms, seed 7610, acceleration
`(2.2*T - 4*B)/1.4 - 0.12 - 0.004*v²`, no calibrated slope/idle/gear dynamics.
Gear acknowledgments follow modeled actual writes. This is not ETS2 evidence.

| Scenario at 35 km/h | Before → after, simple auto | Before → after, real auto |
| --- | --- | --- |
| Moving green: first positive drive after green | 9.359 → **0.283 s** | 9.472 → **0.233 s** |
| Moving green: max deceleration | 1.162 → **1.082 m/s²** | 1.162 → **1.082 m/s²** |
| Moving green: max absolute model jerk | 25.730 → **4.243 m/s³** | 25.730 → **4.243 m/s³** |
| Ending green: brake onset distance before entry | 50.118 → **59.515 m** | 50.118 → **59.515 m** |
| Ending green: max deceleration | 1.539 → **1.304 m/s²** | 1.539 → **1.304 m/s²** |
| Ending green: max absolute model jerk | 3.686 → **3.873 m/s³** | 3.691 → **2.701 m/s³** |
| Ending green: first drive after next actual green | 2.059 → **0.133 s** | 2.172 → **0.083 s** |
| Red until full stop: actual model-front gap to entry | **5.579 m, unchanged** | **5.579 m, unchanged** |
| Full stop: green restart delay | **0.146 s, unchanged** | **0.259 s, unchanged** |

For ending green at 50 km/h, onset moves **45.966 → 59.307 m**, max modeled
deceleration **3.267 → 3.003 m/s²**, jerk **6.712 → 6.490 m/s³**. At 20 km/h
braking is not needed within the first green second, so onset is unchanged at
**31.202 m**. Green release still improves; simple-auto max jerk **3.482 →
3.728 m/s³** is disclosed. No uniform jerk/comfort improvement is claimed, and
no acceptance threshold was retrofitted to label these measurements PASS.

All 48 cases retain authority with **0 red-entry-overrun samples, 0 positive
physical pedal overlaps and 0 parking writes**. Entire red-stop and enough-green
result metrics are identical before/after at all three speeds in both modes.
Red stop model-front gaps range **5.444–5.639 m**; reference gaps to the derived
target range **1.444–1.639 m**, not painted-line accuracy. Pedal transitions in
the 35 km/h moving case remain 2; ending-green case falls 2 → 1. Jerk uses the
actual irregular dt between consecutive model acceleration samples. Detailed
rows preserve phase, SDK frame/original time, context and physical writes.

Verification: **372 targeted tests passed** across 18 relevant modules; one
additional 60-second real-component countdown-history test passed afterward.
It preserves >=29.9 s within the existing 1 MiB history and 64 KiB detail
budgets, with no capture failures and original signal frame/time pairing.
The final timing-module rerun passed **30 tests in 18.90 s**, including that
60-second history case. The 10 Hz summary tail is tested as a tail, not
mislabeled the last SDK frame.
This includes reader identity/foreign/torn/stale cases, flicker, duplicate
generation, both yellows, invalid timer, another stop reason, green lost during
steering/IPC, repeated red/green cycles, manual cancellation, technical faults,
packet refresh and integrity/partial exports. Controller/steering **16 cases**
and unrelated longitudinal comfort **12 cases** are numerically identical to
the retained pre-task native benchmarks. Final `compileall -q core plugins sdk
ui tests tools` and `git diff --check` passed. The first unprivileged Python
launch was blocked by the Windows app-alias sandbox; the authorized isolated
Python rerun completed successfully. Whole-suite pytest was not run.

Isolated phase forecast CPU overhead, 10,000 calls: median **2.2 us**, p95
**2.7 us**, p99 **2.9 us**, max **37.1 us**. This is the operation, not total
tick/scheduling/IPC latency. No freshness-budget increase or memory-budget
increase is used.

Reproduce the paired model:

```powershell
$env:PYTHONCASEOK='1'
python -m tools.run_oct10_signal_timing_bench --output docs/steering-audit/oct10-approach/matrix.json --workdir docs/steering-audit/oct10-approach/new-matrix-runs
python -m pytest tests/test_oct10_signal_timing.py -q
```

## Runtime package and remaining gates

Exact delta against the checked installed receipt (deploy together, after
user's whole pytest and separate approval):

- `core/engine.py`
- `core/longitudinal.py`
- `core/sdk/signal_snapshot.py`
- `core/service_brake_hold.py`
- `core/navigation/prefab_signals.py`
- `core/navigation/longitudinal_diagnostics.py`

No new DLL, plugin main file, settings, map-cache, test, tool or report belongs
to that runtime delta. The preceding coordinated packet-refresh/native/traffic
runtime must remain installed. Restarting Map prepares the extra passage
metadata; stale old metadata cannot manufacture a verified phase reserve.
Version declarations/historical release snapshot are not advanced for core
edits. New tools/test helper contracts and reports/changelog are source-only.

Still open: the initial far-red speed collapse is not fully reconstructable
because its first physical writes, countdown/native yellow direction and SDK
response are outside the retained detail window. The retained tiny positive
brake and zero throttle show why forward creep can persist, but they do not
identify an ETS2 idle/clutch or early-onset physical cause. The model cannot
certify that behavior, hill holding, measured vehicle length, a real stop line,
intersection coverage or a physical dilemma-zone maneuver. The separate
manual-reactivation traffic-activation race above is now fixed offline in the
linked follow-up, but lacks game confirmation. Source timer rates also need
live corroboration, not inference from a float alone.

**Ready for the user's full suite and review of this scoped candidate; not yet
approved for deployment or declared game-ready as a complete lifecycle.** No
additional drive is requested now. Existing automatic significant/fault and
manual dense/timing exports remain, with added original countdown/phase data
to resolve a future missing first-brake/phase boundary without another collector.
