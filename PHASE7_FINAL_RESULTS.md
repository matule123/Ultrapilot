# Phase 7 — Final longitudinal verification

**2026-10-03 rolling-window follow-up:** [Rolling authority regression](PHASE7_ROLLING_AUTHORITY_REGRESSION_20261003.md)
documents the reproduced cache-publication/authority mismatch after a proven
GPS prefix rebase and its core-only fix. It preserves the previous activation
fixes. Verification is offline; the rejected historical context is unavailable
and the new changes have not been installed or game-confirmed.

**2026-10-03 activation follow-up:** [Activation regression fixes](PHASE7_ACTIVATION_REGRESSIONS_20261003.md)
documents reproduced IPC-clock and idle-cleanup races, their core-only fixes,
targeted verification and the unavailable historical policy/token evidence.
The new fixes are verified offline and have not been deployed or game-confirmed.

**2026-10-03 source-only follow-up:** the collector gap below describes the
original Stage 7.4 build. It is addressed offline by
[Combined longitudinal evidence](PHASE7_LONGITUDINAL_DIAGNOSTICS.md), based on
HEAD `0107430d57b2c96881ee39c9a27eccd2ea1ecf19`. Decisions and returned SCS pedal
writes are now retained with bounded provenance; game consumption and reliable
traffic remain unverified. The follow-up is not deployed and does not relabel
the original Stage 7.4 installation comparison or historical results.

Date: 2026-10-03. Stage 7.4 baseline and current runtime:
`84006376aa83592722eaa1d934471a78def3e3db`.

**Conclusion:** the tested offline pedal-arbitration, speed-control and
protective ACC contracts can be closed. ETS2 comfort and reliable traffic-based
following remain **NOT VERIFIED**. The existing combined collector is **not
ready for the requested longitudinal game measurement**. Its isolated export
works, but it does not preserve the pedal decision/write or ACC candidate.
No new drive is requested, and no runtime diagnostic feature was added.

## 1. Scope, rules and build identity

Reviewed: [Stage 7.1](PHASE7_STAGE1_RESULTS.md),
[Stage 7.2](PHASE7_STAGE2_RESULTS.md), [Stage 7.3](PHASE7_STAGE3_RESULTS.md),
[plugin versioning](PLUGIN_VERSIONS.md), changelog, README and
[deferred work](DEFERRED_WORK.md). The tracked tree was clean at entry.
Stage 7.4 changes only this report, the backlog and integration tests.
No controller, arbitration, geometry, steering timing, transmission logic,
500 ms limit or plugin behavior/version changed.

| Stage | Baseline | Resulting committed runtime | Evidence scope |
| --- | --- | --- | --- |
| 7.1 | `1f592ce8afca75c0a9ebfe9fbc60d9dcc052753c` | `7adf8c8153091ad500eb93d3366345d75e7e7359` | Paired command, producer/Engine guards and physical-write regressions; no live pedal-comfort result |
| 7.2 | `7adf8c8153091ad500eb93d3366345d75e7e7359` | `9ffd5acba4b4a41fd77ad954cab0eb2aa1df88f8` | Signed existing PID, reset/anti-windup and fixed longitudinal plant |
| 7.3 | `9ffd5acba4b4a41fd77ad954cab0eb2aa1df88f8` | `84006376aa83592722eaa1d934471a78def3e3db` | Protective route candidates, source-loss contract and fixed following plant |
| 7.4 | `84006376aa83592722eaa1d934471a78def3e3db` | Same runtime; only tests/docs added locally | Joint actual producer/Engine methods and isolated current collector export |

The stage reports describe their then-uncommitted candidates. Git history and
source comparison now bind those changes to the resulting commits above.
This does not retrospectively identify a historical installation from its
commit marker. Existing reports retain their original context and are not
silently relabelled as new runs.

### Read-only installation comparison

Installation: `C:\Users\PC\AppData\Local\Programs\UltraPilot`.
All twelve inspected files match HEAD after normalizing CRLF to LF:
Engine, longitudinal arbitration, PID, ACC following, Autopilot, ACC,
DrivePolicy, EcoDrive, Collision, Map, evidence collector and its management
tool. Raw Engine, Autopilot and Map bytes differ only by line endings.
Other inspected files match byte-for-byte. This is a present-file comparison,
not proof of the code loaded in an already running process or all files in
the installation. No installed file or setting was written.

Selected normalized UTF-8 source SHA-256:

| Source | SHA-256 |
| --- | --- |
| `core/engine.py` | `bf6a16b878f90dfcf23cebc45cec99905e0c15aa17906c574df0dabf6d72f507` |
| `core/longitudinal.py` | `902abdfea3a51f73aef3fa0f0dcce00a84f9426aaceaa9972f5f3d204891f66f` |
| `core/pid.py` | `71add201dc618b65e9091923fa306323c91da0e4251f8ac300f1bad68ffb8fbf` |
| `plugins/acc/main.py` | `870be0fe619e267e4a8df6c56a378799b5ea43f3c3e8a8df854b1be8ea82e0db` |
| `plugins/autopilot/main.py` | `f8ec2fbecf5246593a7ce1fa16affcd6caf09859458164993fca2fa4dc89c2ff` |
| `core/navigation/evidence_diagnostics.py` | `ebdd19ed6e0fab57810c63ad8cb2f08ef12f90403b7878dcbfa6b4aee237f443` |

The full read-only hash receipt is ignored at
`docs/steering-audit/phase74-build-identity.json`. It includes raw/normalized
source and installation hashes and the three committed source comparisons.
Current affected-plugin declarations: ACC **1.1.0**, Autopilot **1.0.2**,
DrivePolicy **1.0.2**, Map **1.0.2**, EcoDrive **1.0.1**, Collision **1.0.1**.
Tests/docs alone do not release new plugin versions.

## 2. Implemented ownership and repaired causes

Existing traffic capture and identified road/curve limits → route candidate
and minimum speed ceilings → existing ACC speed PID → Autopilot pedal stages
and sole paired arbitration → Engine's identity/freshness/transmission/parking
guards → opposing pedal release → physical Controller backend.

Engine is the sole device writer. ACC, EcoDrive, DrivePolicy, collision and
traffic/light requests do not become independent physical controllers.
Normal lower limits apply immediately; ordinary upward recovery is paced.
Emergency drive removal/braking bypasses comfort pacing. Disabled/old-context
commands cannot regain authority. Backend-call return remains distinct from
DLL consumption and actual vehicle response.

| Stage | Reproduced cause and retained repair |
| --- | --- |
| 7.1 | Separate scalar pedal composition could leave positive drive and brake; paired decisions and final exclusive-pedal guards fix ownership. ACC braking, late safety requests and toll stopping are included; Eco cannot revive drive during braking. |
| 7.2 | Target derivative kick, inactive/external-brake integral accumulation, saturation windup and per-tick Eco behavior; the existing PID uses measured-speed derivative, conditional integration/reset and actual observation dt. Signed output permits downhill service braking. |
| 7.3 | Straight-strip lead selection missed curved-route actors; unknown speed became a stationary lead, observed other-height actors triggered braking, and target loss could restore drive. Route projection and explicit loss handling repair these counterexamples without certifying sensor coverage. |
| 7.4 | No production integration regression was found in the added scenarios. A test setup initially changed the LanePath publication token after composing a command: the real boundary correctly rejected it and used emergency fallback. The test was corrected to keep one context for the update-order experiment; no safety guard was changed. |

## 3. Criteria and joint integration results

No new acceptance thresholds were introduced. Stage 7.1 supplies exclusive
pedals, context/freshness rejection, immediate emergency and manual release.
Stage 7.2 supplies the fixed plant criteria: steady RMS ≤1 km/h, overshoot
≤2 km/h, a complete ±1 km/h five-second settling window within 60 s,
steady RMS non-regression allowance 0.3 km/h, no extra steady pedal reversals,
ordinary drive rise ≤0.8 input/s, invalid dt reset and original 500 ms leases.
Stage 7.3 supplies deterministic local candidates, no model reference-point
collision, inherited leases, no blind target-loss recovery and immediate
emergency. These criteria do not certify physical clearance or ETS2 comfort.

New tests: `tests/test_phase7_joint_validation.py`. Existing production
methods execute through PluginSDK to a simulated Controller that records each
physical pedal write. IPC-like fixtures return copies and use one monotonic
clock; they implement actual backend interfaces. They are not real DLL/game
measurements.

| Property / scenario | Evidence and observed result | Existing criterion | Verdict |
| --- | --- | --- | --- |
| One-N simple-auto launch | Whole joint flow: probe 0.12, no D pulse; new frame/gear 8, Plugin takeover and positive drive | Existing bounded launch and zero unconfirmed unsafe drive | PASS offline |
| Real-auto activation | Whole joint flow: one D request, zero drive during wait; new frame/gear 8 before takeover | Existing selector/forward observation confirmation | PASS offline |
| Following plus road/curve limit | Actual raw decoder/selector, DrivePolicy, Eco, ACC, Autopilot and Engine; cap ≤30 km/h and candidate ceiling, positive service brake with zero drive | Lower applicable cap; exclusive pedals | PASS offline |
| Producer update order | Six road/traffic/Eco permutations after a composed positive command | Determinism and latest emergency precedence | PASS offline; all end at drive 0 / brake 1, `traffic_emergency` |
| Emergency between Plugin ticks | Both gearbox modes; no new Plugin tick needed | Same Engine flush, no comfort delay | PASS offline; drive 0 / brake 1 |
| Manual disable | Both modes after braking/emergency | Release ownership and clear paired command | PASS offline; both pedals 0 |
| Old activation completion | Cancel/reactivate with fresh producers, then inject prior-context result | Previous activation must not regain authority | PASS offline; zero drive |
| Stale source with new SDK/steering | New current observation after 501 ms; old source/command retained | No renewed old lease, 500 ms rejection | PASS offline; zero drive |
| Dataset change | All producers/command initially valid, then current dataset changes | Identity mismatch rejects authority | PASS offline; zero drive |
| No positive drive/brake overlap | Record intermediate and final physical calls in new launch/order cases | Exclusive channels at every write | PASS offline |
| Sustained speed, changes, descent, noise/jitter | Reused 12 same-input Stage 7.2 cases; criteria rechecked from metric artifacts | Original Stage 7.2 plant criteria | PASS in that model |
| Slower/braking lead, curve/roundabout, cut-in | Reused seven Stage 7.3 same-input cases, target absence/collision criteria rechecked | Original Stage 7.3 model criteria | PASS in that model |
| R, parking, invalid/future SDK, route loss, repeated frames | Existing stage regressions remain applicable; no relevant source change in 7.4 | Existing reverse/parking/freshness/authority guards | PASS in previously documented offline scope; not a new live result |
| Real ETS2 pedal comfort and complete stopping behavior | No qualifying longitudinal game record for this Phase 7 build | Requires measured bound writes and later SDK response | NOT VERIFIED |
| Reliable traffic-based following | Missing source-generation/lane/coverage/body reference evidence | Stage 7.3 explicitly requires evidence, not receiver time | NOT VERIFIED |

Stage 7.4 verification: **12 added tests passed** (nine joint/export cases,
then three late-authority cases). The first export attempt encountered Windows
sandbox `PermissionError` creating/accessing pytest basetemp, not an application
export failure. The nine cases subsequently passed outside that filesystem
restriction with a new ignored basetemp. The three non-filesystem cases passed
in the normal environment. No source check or tolerance was relaxed.

Previous targeted results are retained as historical runs, not summed into a
new current full-suite result: Stage 7.1 313 tests/17 subtests; Stage 7.2
351/17; Stage 7.3 347/17 plus 50/20 non-filesystem checks. Stage 7.3 still
documents two sandbox-blocked filesystem cases and the unexecuted elevated
retry in that session. Stage 7.4 did not rerun those unrelated checks.
The full `tests/` suite remains reserved for the user.

### Reused numerical results and provenance

No benchmark was rerun merely to repeat a passing measurement: runtime did not
change in Stage 7.4. The existing speed candidate artifacts from 7.2 and 7.3
are byte-identical, and all four steering benchmark production-source hashes
still match. There is no steering source diff from `7adf8c8` through HEAD.

| Fixed plant result | Candidate measurement | Interpretation |
| --- | --- | --- |
| Noisy settled cruise | Steady RMS 0.070 km/h; overshoot 0.177 km/h; settling 3.95 s | Stage 7.2 model, not ETS2 |
| Target decrease/increase | Overshoot 0.309 km/h; settling 4.80 s | Lower limit immediate, paced recovery |
| Curve ceiling | Steady RMS about 0.000011 km/h; settling 6.15 s | Longitudinal cap scenario; no lateral/clearance proof |
| Heavy 6% descent | Steady RMS about 0; maximum final-target overshoot 0.887 km/h | Signed brake control in explicit model |
| Jitter/delay cruise | Steady RMS 0.158 km/h; settling 14.55 s | Seeded irregular timing/noise model |
| Following slower lead, straight | Speed RMS 19.221 →3.423 km/h; minimum reference gap 13.108 →32.000 m | Error relative to lead, not unrestricted user speed |
| Following braking lead | Speed RMS 16.442 →3.680 km/h; minimum reference gap 10.455 →22.000 m | Unknown body dimensions; not bumper gap |
| Cut-in | Minimum reference gap 9.775 →18.373 m; switches 2 →1; emergency decision delay 0 s model ticks | Plant still has 120 ms transport, not zero physical stopping latency |
| Existing steering | All 16 case metric dictionaries unchanged | Offline numerical non-regression, not new live comfort proof |

Speed model uses the same actual ACC/Autopilot/arbitration code, transport and
plant as Stage 7.2; following uses Stage 7.3's perfect synthetic route poses.
Detailed definitions, sample counts, durations, loads and limitations remain
in those reports. No missing physical acceleration, traffic freshness, body
clearance or game jerk was inferred from pedal slew.

Artifact SHA-256 (ignored JSON retained unchanged):

- `phase73-speed-preserved.json` and `phase72-speed-final-20261003.json`:
  `53b09f326082d3f5b8db613eda1d320d4edbd5b78a02ff21e9b85a985d6a0c2a`.
- `phase73-model-verified.json`:
  `a7b653edca3d98db16d89aaef1c059e3d8c56e2c22893c67e75aa70cc2af025a`.
- `phase73-steering-final.json`:
  `d983a439812d33b909882a311af41ddffff8fdb91585ed5d80aa14c3275cfa6b`.

`compileall` for core/plugins/sdk/tools/tests passed. Final tracked diff and
separate new-file whitespace/final-newline checks passed. These checks are not
substitutes for the user-run suite or live validation.

## 4. Explicit traffic evidence limits

| Missing / uncertain input | What is actually available | What it blocks |
| --- | --- | --- |
| Producer timestamp/generation | Two agreeing raw reads and host monotonic receive time | Detecting a frozen publisher and proving current actor kinematics. Read time is never labelled snapshot creation time. |
| Confirmed actor lane/deck | XYZ/quaternion projected onto the local directed LanePath, with relevance/height gates | Claiming a confirmed same-lane ACC target at adjacent/crossing/stacked roads. Candidate remains unconfirmed. |
| Documented sensing coverage | Up to 40 moving and 40 parked entries; no declared complete spatial/time horizon | Treating empty as a clear corridor, verified cut-out and automatic resumption after target loss. Unavailability is distinct from no projected candidate. |
| Body/reference accuracy | Raw dimensions, unknown zeros retained; chassis/path reference-point distance | Certified bumper distance, collision clearance or automatic stop-and-go. No legacy default body bound is promoted. |

After an observed target disappears or its evidence expires, the current
activation requires takeover; seeing bytes again does not silently clear the
fault. Before any target was observed, existing optional-sensor cruise remains
explicitly unqualified, not certified free space. A new sensor, DLL or broad
parser is not authorized or implemented by this closure.

## 5. Existing collector readiness: export passes, scope does not

The installed collector/management tool match current source byte-for-byte.
The isolated test supplies live-looking longitudinal state alongside the real
capture function, then exports 30 accepted samples through actual `finalize`
and `inspect_collection`. It checks collector status before inspecting files.
Source-packet mutation after capture cannot change the saved calculation ID.
The manifest passes integrity and remains `confirmed=false`,
`runtime_authorized=false`; this is not game qualification.

| Required channel | Current capture/export | Verdict for requested game measurement |
| --- | --- | --- |
| Actual speed | `truck.speed` / `speed_mps`, original SDK frame | Available |
| User/constrained/control target | Exists in `longitudinal_acc`, omitted from DiagnosticCapture and rows | Missing |
| Actual pedal writes and time | Engine maintains `longitudinal_applied` after returned backend calls; collector omits it | Missing; CTL mirrors are not sufficient |
| Paired pedal source/identity/lease | Exists in `longitudinal_command`, omitted | Missing |
| Activation and intervention | `autopilot_active` boolean retained; launch/pending/safety state and first reason omitted | Partial; cannot fairly split/attribute all phases |
| ACC candidate / reference gap / validity | `longitudinal_traffic.following` omitted; raw legacy traffic exported separately | Missing; raw traffic is not a saved selection decision |
| Immutable steering execution | `executor.source_packet`, submission sequence, backend steering and return time retained | Available, but not longitudinal binding |
| Subsequent SDK response | Captured speed, steering/tyre channels; pedal response and SDK gear not in bounded truck pick | Partial; later frames must be paired by time, never by same row alone |

Consequently **COLLECTION NOT READY** for the combined comfort/following
validation. A successful current `inspect` would prove file integrity, not
the absent pedal/candidate channels. No arm command or new drive is requested.

### Minimum proposed collector-only addition — not implemented

One small immutable longitudinal capture beside the existing steering capture:

1. The paired source decision with full context, source SDK frame, original
   observation/computation/expiry times, throttle/brake, source and reason.
2. The physically returned pedal-write record, backend mode, a monotonic
   pedal-write sequence and return time, retaining the exact source decision
   that produced that write. Never substitute the newest shared decision.
3. Requested/constrained/control speed and the actually consumed candidate ID,
   reference gap, lead speed, relevance status, original leases and explicit
   unknown publisher timestamp/generation/coverage flags.
4. Pending launch/active/safety/manual phase, gearbox mode, first intervention
   reason and subsequent original SDK speed/gear/pedal-response channels when
   genuinely available. Missing channels remain null/unknown.

This would reuse the bounded worker, current chunked export/integrity/finish
contract and existing authority=false qualification. It needs a narrow isolated
binding/export regression before arming. It would not solve the traffic
producer's missing freshness/membership/coverage, or prove that ETS2 consumed
a returned backend call. No broad replay data belongs in the normal log.

### Conditional future minimum game verification

Only after that explicit diagnostic addition/export verification, the user-run
suite and a separate deployment decision: use one short collection with enough
startup/preflight time, on a known wide route at moderate legal speed. Verify
increasing SDK frames and complete bound pedal records while standing before
activating. Then one N without manual throttle, a settled-speed segment and a
normal lower-target deceleration; following is observed only if ordinary traffic
happens to be present. Do not create an emergency, cut-in or brake failure.
The driver remains ready to take over; unexpected reverse, authority loss,
invalid frames, unexplained pedal behavior or unsafe gap ends the test.

Finish and wait for actual export completion, inspect every chunk/hash and
disable diagnostics. Separate launch, active, manual and controlled-stop phases;
pair writes to later SDK frames, not the SDK sample in the same row. This tests
pedal behavior/comfort on that run; it cannot certify the traffic source.
No fixed time-to-export promise or current ready-to-arm instruction is given.

## 6. Closure, backlog and proposed commit

| Scope | Closure |
| --- | --- |
| Phase 7.1 common ownership/safety | Closed in the documented offline contracts |
| Phase 7.2 fixed-model speed/pedal stability | Closed offline; cold-start RMS/settling tradeoffs remain documented |
| Phase 7.3 protective following improvements | Closed offline; reliable live ACC is NOT VERIFIED |
| Phase 7.4 joint integration/export-scope check | Completed; no new production bug demonstrated |
| Entire Phase 7 in ETS2 | NOT VERIFIED; do not label complete live validation |
| Combined comfort collection | Blocked by omitted longitudinal decision/write/candidate fields |

The next smallest independent task is the collector-only addition above,
not another controller or a new drive. Source-side traffic evidence and game
comfort remain separate backlog items. Overtaking, steering naturalness,
new sensors and stop-and-go are outside this phase.

Changed files: this report, `DEFERRED_WORK.md`, and
`tests/test_phase7_joint_validation.py`. No plugin version/changelog update is
needed for tests/documentation. No commit, push, deployment, installation,
game operation, arming or original-record modification was performed.

Proposed commit: **test: close offline Phase 7 longitudinal integration**.
Description: verify joint gearbox/ACC/policy/Eco pedal ownership, latest
emergency and old-authority rejection; document build-bound results and the
combined collector's missing longitudinal measurement scope.

The user runs the full suite:

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python -m pytest tests -q
```
