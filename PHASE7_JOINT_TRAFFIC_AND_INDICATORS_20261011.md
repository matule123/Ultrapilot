# Phase 7: Oct 11 traffic, stop-distance and indicator regressions

Date: 2026-10-11. **OFFLINE VERIFIED for the specific corrections below;
GAME NOT VERIFIED. The complete roundabout collision and photographed stopping
gap are not resolved by these corrections.** No deployment, original-evidence
modification, commit, game operation or full pytest run was performed.

## Build and evidence boundary

Repository HEAD is `787d012a2a78ac917bb5506e0958c32d8d06575f`, with inherited
uncommitted red-approach, destination, traffic, signal and packet-refresh changes.
The installed baseline is the destination-lifecycle deployment
`20261011T095307684Z`, recorded in
`C:\Users\PC\AppData\Local\Programs\UltraPilot\manual-deployment.json`.
All **20 installed receipt hashes match**. At task entry the relevant installed
implementations matched the working tree after LF/CRLF normalization; this is
not inferred from `commit.txt`. The seven new candidate runtime files below now
intentionally differ. Installed files and the old `ets2la-old-221cc90` checkout
were only read.

Installed versions: ACC **1.1.7**, DrivePolicy **1.1.3**, Autopilot **1.3.4**,
Map **1.1.1**, scoped DLL **1.59.3-up-signal-scope**. TurnSignals was **1.0.0**.
This candidate changes ACC to **1.1.8** and TurnSignals to **1.0.1** only.
The previous user full-suite PASS belongs to the prior deployment, not this
candidate. No independent plugin update or DLL replacement is proposed.

All four artifacts were decoded with `core.steering_replay.inspect_replay`,
including its immutable codec, and passed their hash-integrity check. They are
in the installed `route-diagnostics` directory:

| Artifact | Retained rows | SHA-256 |
| --- | --- | --- |
| `steering-replay-20261011T104938.211656Z-automatic_disable.json` | 1,069 dense; 6,444 execution | `e17d17fb489aa3e881917151f763d9958f447c4076ae51bfcb74f439bdd3b15c` |
| `steering-replay-20261011T104936.895268Z-automatic_disable.json` | pedal incident, separate detail/history counts below | `09e3e6508d85c8cb0902171324bee3c5319755ec13edb7bc4a6c36ea76170e0a` |
| `steering-replay-20261011T104747.073445Z-manual_disable.json` | 1,070 dense; 8,553 execution | `b6441d20fab9a4e047a5c5728061b64890bc2d638f3de2c9e84b2340e9351d44` |
| `steering-timing-20261011T105004.392237Z-plugin_stop.json` | 455 timing | `0b94ed6569fc837f791ce12a57e9f98626aacafbd01828916cb152cfd2e98249` |

The relevant drive is **12:46–12:50 local time / 10:46–10:50 UTC** on Oct 11,
not the earlier Oct 9/10 recordings. The final active identity is activation
`5688400855600`, session `1`, map `promods-1.59`, dataset
`d6cc7936fce4e902761abb5d`, intent `a24f7a16112944b1a758a00989f2f268`, revision
`7`, build `c00e4335da75496facf8cab9a15c509c`, geometry
`lane_path/c9b44eacf4cf985f790208939220d1848a26ed0fc117d497480b45a16bd3e5de`.

Reproduce the read-only analysis with:

```powershell
$env:PYTHONCASEOK='1'
python tools/analyze_oct11_regressions.py --output docs/steering-audit/oct11-regressions
```

Its generated JSON and decoded raw data stay outside tracked Git content.

## Historical timeline and completeness

| Local time | Recorded event |
| --- | --- |
| 12:45:20 | TurnSignals skipped during discovery because settings disabled it. |
| 12:46:23 | UI saved `plugin_enabled.turnsignals=True`; no subsequent worker-start record. |
| 12:46:57 | N, simple-auto throttle probe 0.12, forward gear 4, handoff. |
| 12:47:03–22 | Significant-event export attempts failed the existing disk quota. |
| 12:47:46 | Manual disable and dense replay. |
| 12:48:26–39 | N accepted waiting before red; movement cancelled the unsupported stationary driver-hold wait. |
| 12:48:43 | New N, forward launch and handoff. |
| 12:49:00 | Continuous service-brake hold. |
| 12:49:13 | Fresh same-head green, hold release and existing simple-auto restart. |
| 12:49:36.768 | Engine's first technical intervention: `ACC target unavailable or unconfirmed departure`. |

The actual rejected **Traffic** packet is frame **298304734**,
observation **5741.5450319**, computation **5741.5782517**, expiry
**5742.0276161**, checked **5741.6071192**. Its observation age is **62.0873 ms**,
decision age **28.8675 ms**, remaining lease **420.4969 ms**; identities match.
It is valid and reports `no_candidate_unproven_coverage`, traffic/light brakes
zero and usable stable receiver buffers. The outer intervention separately has
frame **298371398**, observation **5741.601771**; it is not substituted for the
compared Traffic packet. The unqualified signal has `requires_takeover=false`
and was not the first cause.

The detailed PedalJournal retains **12 events / 0.2636325 s**, drops **4,353**,
uses **61,328 / 65,536 bytes**, and has **0 detail field-capture failures**.
The separate 30-second history retains **240 regular + 37 change rows** over
**30.0693017 s**, uses **371,895 / 1,048,576 bytes**, has **1,492 capture failures**
and **0 capacity drops**. Both are explicitly incomplete. Integrity does not
turn missing actor positions into evidence. Lead ID 29 is attributed in 82
history rows from **5733.4473844–5741.553086**, but its raw positions are absent.
The user's report that it turned is consistent with the sequence, not a
recorded trajectory proving the historical departure.

## Corrections and remaining limits

| Problem | Demonstrated defect / historical certainty | Candidate correction | Verdict |
| --- | --- | --- | --- |
| Roundabout crossing | The production protective decoder discarded native trailer records. A tractor can already have cleared the route while its trailer still crosses; before-fix physical outputs did not brake in this reproduced case. Original collision actors/tick are unavailable. | Decode the same captured tractor plus up to three native trailer boxes and evaluate each in the existing directed-route crossing predictor. Take all observed actors into account; removing car 1 never removes car 2's conflict. | Specific omission OFFLINE VERIFIED; the actual collision and reliable whole-body safe-gap entry NOT VERIFIED. |
| Lead turns off route | Selector had no explicit witnessed-departure receipt. Both ACC and the final boundary treated a non-candidate as loss. Exact ID 29 history ends without original actor poses. | Same acquired ID/source/slot, changed exact source-record fingerprint, valid kinematics, unambiguous projection and every observed body outside the existing caution band allow releasing only that lead dependency. ACC and Engine share the same matcher. | Supported observed departure OFFLINE VERIFIED; historical turning path and live effect NOT VERIFIED. |
| Departure between producer ticks | A new departure receipt can reach Engine before ACC updates. A second boundary branch still tried reading the departed target's missing speed cap, creating `invalid ACC following constraint`. This was exposed by asserting the actual first-intervention slot. | Do not fabricate a cap. Coast without old drive until ACC's next valid decision; keep the consumed Traffic receipt's original lease in final revalidation. Existing braking/emergency floors remain effective. | OFFLINE VERIFIED in both modes and both producer orders. |
| Excessive semaphore gap | No demonstrated duplicate reserve. The target is a derived curve entry with unmeasured front and stand-off allowances, not a surveyed stop line. | No guessed distance/offset change. Preserve the currently working approach and green restart. | Physical front-to-painted-line gap NOT VERIFIED. |
| Indicators absent | Historical log proves UI enable did not start the skipped worker. Code additionally used default `off` as an automatic cancellation even without route ownership, interfering with a driver's signal. | Start a discovered disabled plugin once upon UI enable; release its ownership when disabled. `None` means no automatic owner; `off` cancels only our acknowledged side. Preserve manual/hazard priority and consume self-cancelled semantic events. | Software path OFFLINE VERIFIED; live game consumption NOT VERIFIED. |

### Departure contract

The exact byte-row SHA-256 identifies a captured record, **not a generated
stable actor identity**. Slot reassignment, duplicate/missing ID, invalid speed,
invalid dimensions, unknown/ambiguous route projection, disappearance and
unchanged re-reading do not establish departure. The previous observed target
and the first changed outside-route receipt are single bounded slots, reset
with route binding. Re-reading the same departed record preserves its first
receiver time; the existing 0.5 s age is never renewed. A previously latched
actual loss cannot be cleared by a later geometric departure.

Pinned native source `1f16156b9b37b70cf182c2bc09120fa1b234e129`, inspected in
`docs/steering-audit/signal-plugin-20261009/scoped-candidate/src/processing/traffic.cpp`,
packs `get_center_coords(placement,aabox)` and absolute box dimensions for
tractor and trailers. The candidate uses each raw box's circumscribed
half-diagonal to avoid clearing a still-overlapping trailer. This establishes
the source's center convention, not independently measured physical accuracy.

The receipt remains `confirmed=false`, `coverage_confirmed=false` and explicitly
`changed_receiver_record_not_producer_timestamp`. The existing TrafficCapture
double-read provides stable receiver bytes, not a producer timestamp,
generation, joint atomicity or full traffic coverage. The receipt releases a
particular observed lead dependency; it never certifies an empty intersection,
safe maneuver gap or permission to release another stop reason.

### Crossing capability boundary

Read-only comparison with checkout `221cc90` found the earlier straight
relative-velocity closest-approach brake, including guessed fallback dimensions.
It is not evidence that it correctly handled this recorded entry. Current
protective prediction uses the directed local route, both arrival windows,
raw box length occupancy, all observed cars/trailers, and the pre-existing
2 s reserve / 8 s horizon / 0..2 m/s² nominal ego acceleration assumption.
Trailer motion uses tractor speed and the trailer's captured heading; it is
not a measured articulated-motion bound.

`core/navigation/maneuver_traffic.py` already contains the richer continuous
body/coverage contract, but the native legacy feed does not provide its needed
producer-timed frame progression, independently confirmed ego truck/trailer
envelopes, motion bounds and coverage/unseen-entry proof. No speculative ego
dimensions, new sensor or parallel predictor was added. A missing conflict is
still `no_conflict_unproven_coverage`, never a certified safe gap. These precise
missing capabilities block declaring autonomous roundabout entry reliable.

### Stop-distance finding

In 46 same-identity holding rows at **5711.6136629–5718.410371**, locked head ID
**1** and passage
`45540e750098d8f1fc11bc8b76cd20b1ae161420a94ae48b90dad1891389062f` have SDK
reference-to-derived-target distance **2.5513871–2.5514364 m**. Throttle is zero;
the retained brake is consistently **0.1174879596**. Authored entry progress is
**399.8333645 m**, XYZ **[34753.4735007, 6.90234375, 45663.9580174]**.

The selector subtracts the **6 m unmeasured front allowance + 2 m junction
stand-off once**. The planner then uses remaining target distance; its separate
speed-dependent response reserve vanishes at standstill. Thus the recorded
SDK reference was approximately **10.5514 m before the authored curve entry**,
not 10.5514 m before a measured painted line. The missing fields are the
truck-reference-to-front geometry and an authored/surveyed physical stop-line
location. No photo-derived bumper gap or arbitrary shortening is justified.

### Indicator ownership and evidence

Existing Map turn/roundabout/lane-change topology events remain the only source
of automatic direction. No instantaneous steering-sign or ordinary-road-curve
fallback was added. Existing 28–80 m / approximately four-second warning and
8 m completion margin are unchanged. Tests exercise left/right turns and the
chosen roundabout exit through Map's semantic-event publication, plugin,
Engine and real Controller toggle writes. A same-intent geometry republication
does not rearm a driver's cancelled event; consumed IDs are bounded to the
current Map event window.

SDK acknowledgement in these tests is an explicit game model, separate from
backend success. Engine checks its own current observed manual/hazard state
before toggling; it releases momentary button pulses without treating that as
a driver's switch cancellation. A safety hazard suppresses directional toggles.

## Diagnostics and significant-event quota

The optional departure receipt is retained by the existing immutable decision
codec and 30-second history. A fixed-field packed receipt avoids consuming the
existing attribution budget with repeated names. Deltas are restored before
receipt expansion, including an older producer trace beside a newer Engine
input. The original indexed codec tables remain unchanged; `traffic_departure`
is appended to history fields. Target/status changes are change events, so a
short departure cannot silently vanish between regular 10 Hz rows.

Existing 64 KiB detail and 1 MiB history budgets, asynchronous export, steering
replay, combined collector, hash checks and first-fault preservation are retained.
No new collector, SDK/IPC acquisition or per-tick INFO logging was introduced.

**The significant-event quota remains full: 8 files / 6,614,998 bytes**, with an
8-file / 16 MiB cap. The files are from prior Oct 9/10 events; their existence
does not provide the missing Oct 11 collision evidence. Original files were
neither deleted nor moved. Explicitly authorized archival is needed before
future significant events can use that quota; ordinary automatic/manual replay
exports still exist. No new drive is requested here.

## Reproductions and checks

`tests/fixtures/oct11-joint-original-functions.json` freezes hash-identified
installed source/functions, including the actual unlocked Engine physical
flush body. The baseline tool substitutes these only in memory, with unchanged
test expectations. It is independent of a later mutable installation:

```powershell
$env:PYTHONCASEOK='1'
python tools/verify_oct11_joint_baseline.py
python -m pytest tests/test_oct11_joint_regressions.py -q
```

The baseline reproduces **9 failures, 0 passes, 0 setup errors**: four observed
departure/order cases, two omitted-trailer physical-brake cases, one live UI
start and two unwanted manual-indicator toggle cases. During review, four
invalid-departure-speed cases failed before the same kinematics guard was added;
they now remain safely rejected. The final tests also caught and fixed the two
between-ACC-tick missing-cap failures, without weakening expectations.

The integration fixture invokes the actual Map, Native TrafficCapture/decoder,
DrivePolicy, ACC, Autopilot, Engine and real SCS Controller over a chronological
BytesIO backend. It models SDK input and process scheduling; it is not ETS2.
The semantic-indicator fixture isolates topology events, not a physical
roundabout trajectory. The same-head red/hold/green fixture uses the existing
placed-prefab native-reader flow in both automatic modes. No parking writes
occur. Negative cases retain missing/duplicate/reassigned ID, invalid speed,
trailer still on route, unchanged/stale proof, foreign target and changed binding.
Existing suites cover stale packets, R/backwards, reroute/session/dataset loss,
backend failures, cancellation, independent cadence and export integrity.

Final targeted integration run after correcting the actual first-fault assertion
and between-tick branch: **373 passed + 7 subtests in 68.91 s**, including all
**48 new joint cases**. Earlier intermediate runs (413 + 7 subtests, followed
by 170 checks) are not substituted for this final result. The final run covers
the following files:

```text
tests/test_oct11_joint_regressions.py
tests/test_acc_following.py
tests/test_longitudinal_arbitration.py
tests/test_phase7_joint_validation.py
tests/test_oct10_traffic_availability.py
tests/test_control_safety_regressions.py
tests/test_rolling_longitudinal_authority.py
tests/test_automatic_longitudinal_replay.py
tests/test_pedal_decision_history.py
tests/test_longitudinal_evidence_diagnostics.py
tests/test_oct10_signal_timing.py
tests/test_oct11_destination_flow.py
tests/test_oct11_red_approach.py
```

The full pytest suite remains for the user. Compileall passes for the seven
runtime files, new joint test/tools and the two adjusted fixtures. Whole-tree
`git diff --check` passes; only Git's existing LF/CRLF conversion warnings appear.

## Performance and unchanged control metrics

Steering benchmark: **16 cases exactly equal** to the prior accepted
`docs/steering-audit/oct11-lifecycle/steering.json` metrics. Longitudinal comfort:
**12 cases exactly equal** to `oct11-lifecycle/comfort.json` metrics. No lateral
controller, route geometry, PID gains, safety timeout or 500 ms change.

The existing following benchmark's seven candidate scenarios have no synthetic
reference collision. Minimum reference gaps are 32.0000 m (straight/left/right/
roundabout), 22.0002 m (braking lead), 18.3735 m (cut-in) and 32.3028 m (noise/jitter).
Only cut-in switches target once. These are uncalibrated reference-point model
results, not bumper clearances or game/crossing safety proof. Its `before`
comparison is the tool's older `9ffd5ac`, **not this deployment's baseline**.

The paired operation benchmark runs 1,200 samples / 60 s of modeled 20 Hz flow,
40 native-layout actors, actual decoder/selector/publication/Autopilot/Engine/
Controller, copied in-process IPC and BytesIO writes. It compares this task's
frozen installed baseline, with unchanged physical outputs and IPC read counts.
This is wall operation cost, not live packet cadence or native input consumption.
Its final measured results are:

| Complete operation wall time | Frozen installed baseline | Candidate | Difference |
| --- | ---: | ---: | ---: |
| p50 | 8.5479 ms | 8.7331 ms | +0.1852 ms |
| p95 | 9.7842 ms | 10.0129 ms | +0.2287 ms |
| p99 | 11.6038 ms | 11.7819 ms | +0.1781 ms |
| maximum | 51.4576 ms | 60.2460 ms | +8.7884 ms |

An earlier paired run measured 9.2609/9.4793 ms medians and 62.9399/64.1420 ms
maxima. Neither run establishes improved tail scheduling; the final maximum is
explicitly worse. Physical mappings and IPC read counts match exactly in both
runs. Candidate retained detail is **62,020 / 65,536 bytes**, summary
**297,611 / 1,048,576 bytes**, versus baseline 62,032 and 298,206 bytes. These
are charged serialized runtime buffers, not mock write-history heap or process
RSS. Native trailer decoding and fingerprinting add bounded work; no end-to-end
live cadence, scheduling or 500 ms headroom guarantee follows from this fixture.

```powershell
$env:PYTHONCASEOK='1'
python tools/benchmark_oct11_joint.py --samples 1200 --output docs/steering-audit/oct11-regressions/operation-bench-final.json
python tools/run_steering_bench.py --output docs/steering-audit/oct11-regressions/steering.json --quiet
python tools/run_longitudinal_comfort_bench.py --output docs/steering-audit/oct11-regressions/comfort.json
python tools/run_acc_following_bench.py --output docs/steering-audit/oct11-regressions/following.json
```

## Consistent candidate runtime bundle

Only these seven files differ from the installed task baseline and belong to
this correction together:

```text
core/acc_following.py
core/engine.py
core/longitudinal.py
core/navigation/longitudinal_diagnostics.py
core/plugin_manager.py
plugins/acc/main.py
plugins/turnsignals/main.py
```

`tools/analyze_oct11_regressions.py` writes exact raw and normalized source/
installed SHA-256 values to `docs/steering-audit/oct11-regressions/runtime-candidate.json`.
These files depend on the already receipt-matched destination/red-approach/
signal-scope/packet-refresh runtime. They must not be deployed onto an older
mixed installation. **DLL unchanged**. Preserve settings, map cache, commit
marker and original diagnostics. New tests, baseline fixture, tools and this
report are development artifacts, not installation files.

Other changed development files for this task: the new joint test, narrow
ownership/mock-ack adjustments in `test_policy_signal_light_regressions.py` and
`test_control_safety_regressions.py`, frozen baseline fixture, analysis/baseline/
operation-benchmark tools, changelog and `DEFERRED_WORK.md`. The acknowledgement
fixture now explicitly reports the side whose cancellation it expects; backend
success alone is never promoted to a received SDK acknowledgement. Existing
unrelated local changes are retained.

## Final scope

Supported observed departure, omitted native trailer protection, indicator
live-enabling/ownership and receipt preservation can be closed **offline** after
the targeted checks. The complete historical collision and actual front/painted
line gap remain **NOT VERIFIED**, with the precise missing data stated above.
All new game effects remain **GAME NOT VERIFIED**. The next release gate is the
user's full suite and separate deployment authorization, not another automatic
drive request. No claim of universal collision avoidance, traffic coverage,
perfect stop placement or uninterrupted game consumption is made.

Suggested commit title: `Fix witnessed ACC departure and topology indicator ownership`.
Description: preserve acquired-lead loss protection while handling changed
outside-route observations, include native trailers in protective crossing
checks, repair live indicator ownership and retain bounded departure evidence.
This is a proposed description only; no commit was created.
