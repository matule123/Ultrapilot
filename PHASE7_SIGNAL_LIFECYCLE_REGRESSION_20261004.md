# Phase 7 — Continuous service-stop lifecycle regression, 2026-10-04

## Verdict and build scope

**PASS for the supported offline lifecycle; NOT VERIFIED in ETS2 after this
patch.** The existing launch, arbitration, controller, brake hold and signal
restart are retained. Two reproduced causes of losing the planned-stop witness
are fixed. The diagnostic journal is also repaired so the real joint-producer
flow can export the ordered paired writes and waiting/restarting state.

Starting Git state was clean, HEAD `cdea197`. No AGENTS.md was present in the
repository or its ancestors. PLUGIN_VERSIONS.md, DEFERRED_WORK.md and the existing
Phase 7 stop/transmission reports were consulted. This result applies to that
HEAD **plus the uncommitted changes listed below**, not to the installed build.
No commit, push, installation, arming, game launch or vehicle operation occurred.
Original logs, collections and replay files were not changed.

Plugin source files are unchanged: Autopilot **1.2.0**, ACC **1.1.1**, DrivePolicy
**1.0.3**, Map **1.0.4**. Per PLUGIN_VERSIONS.md, core-only fixes do not release
untouched plugins. The changelog records an application/core fix separately.

## Incident evidence and its limits

Source: installed `ultrapilot.log` and
`route-diagnostics/steering-replay-20261004T145743.933359Z-automatic_disable.json`.
Replay SHA-256:
`6DBF4BC619EC10D8F7D8E38E37291FF0123CBFA847D5386EE4D0F4DFBF21A979`.
It contains 83 sampled records and 4,159 execution records. Its termination
identity matches session `1`, map `promods-1.59`, dataset
`d6cc7936fce4e902761abb5d`, intent `44fa1cc1999f481892cbba00c928b8aa`, revision
`11`, build `d07082acabf84d9083eae872034230d9`, activation `1080820351700`.
The geometry identity is the `lane_path` fingerprint
`367f76af5b261192e3237d58c468146de126ff446a05475356f666bd68ac49dc`.

| Local time / monotonic seconds | SDK frame (us) | Measured event |
| --- | --- | --- |
| 16:57:39.975 | Not recorded on hotkey row | One N requests existing simple-auto launch |
| 16:57:40.011 / 1080.8573841 | 89696412 | Gear 0, speed -0.000152 m/s; throttle 0.12, brake/wheel 0, no D selector; observation age 30.693 ms |
| 16:57:40.220 / 1081.0672255 | 89913070 | Gear 4, speed 0.000209 m/s; handoff completes, throttle 0.146884, brake 0; observation age 25.720 ms |
| 16:57:43.849 / 1084.6975933 | 93546258 | **First causal fault is Engine:** TECHNICAL_CONTROL_STOP, zero ratio lacks continuing forward motion; original observation 1084.6872126, age **10.381 ms** |
| 16:57:43.859 / 1084.7062786 | 93546258 | Gear 0, speed **0.018660 m/s**, valid observation, age 19.066 ms; Engine reports zero outputs on revocation |
| 16:57:43.860 / 1084.7086238 | 93546258 | Plugin reports the same ratio fault after Engine |
| 16:57:43.881–.883 | Not recorded on these rows | Automatic disable, then hazard lights on |

The sampled replay rises to about 10.08 km/h, then decelerates; its last sample
has speed 0.242551 km/h (0.067375 m/s), progress about 5.15 m. Those values are
sampled telemetry, not proof of a particular pedal write. The last **logged**
positive ratio is gear 4 at handoff; intervening ratios are not saved in this
steering replay. The first brake producer, original stop witness and ordered
longitudinal backend writes are absent. No corresponding October 4 combined
export exists. Therefore **red is not a historically confirmed brake source**,
and no historical brake-zero edge, exact later positive gear or rejected witness
contents are invented. The timestamped evidence proves a fresh low-speed zero
ratio was classified as technical loss of drive, not a 500 ms expiry.

Installed commit.txt was `cdea197`. Before editing, Engine, transmission rules,
service hold, Autopilot, signal reader and longitudinal diagnostics matched the
repository after LF/CRLF normalization. This bounds the incident to the audited
code; it does not supply the missing runtime brake witness. The two causal code
defects below are reproduced with real production operations, independently of
the incomplete historical record.

## Reproduced defects and fixes

| Defect | Before | Fix | After |
| --- | --- | --- | --- |
| Runtime stop evidence used a lossy **passive diagnostic** copy with an 8,192-byte conservative budget | Joint real ACC + DrivePolicy + traffic inputs replace the entire witness with `UNVERIFIED_SNAPSHOT_BUDGET_EXCEEDED`. `planned_stop` cannot recognize red, so an actual positive brake write does not seed holding. At the existing 0.05 m/s boundary, zero gear then disables both Engine and Plugin | Fixed-field, owned runtime witness retains consumed source/frame/time, brake demands, following status, signal receipt and light ID/color/distance. No actor arrays/display geometry/verbose speed-controller text. Runtime authority no longer depends on diagnostic truncation | Same throttle/brake selection and leases; stop witness remains available with both real producers |
| First positive planned brake at an already admitted moving zero-ratio transition was ignored | `after_write` required gear > 0 even though the common bounded ratio rule had just admitted gear 0 and forward motion | Engine passes its validated history. Seeding also requires exact context and SDK frame, fresh original observation, phase `zero_ratio_transition`, unexpired absolute deadline, no launch deadline, speed > existing 0.05 m/s and released driver parking brake | Actual positive write can seed continuity; anonymous/stationary/expired zero ratio cannot do so |
| Joint-producer journal snapshot exceeded 32,768 bytes; charging the same immutable source twice could evict one paired write | Export may have valid hashes but lose waiting/restarting provenance or a throttle write | Internally reference only **exactly equal** metadata of the same immutable decision; expand explicit fields before external reading/export. Differing frames/times/identities are retained. Charge one shared source per bind, 2,048 bytes per event; reclaim it on last-use eviction | Explicit original field contract preserved, both ordered pedal writes exported with zero journal drops in the supported lifecycle reproduction |

No timestamps are refreshed. No timeout, gear-0 permission duration, brake
strength, regulator gain, lane geometry, steering cadence or safety threshold
changes. The shared ratio evaluator itself is unchanged: the fixed Engine-owned
witness supplies its existing planned-stop branch to Plugin and Engine together.
No parking-brake write or repeated D pulse is added.

## Whole-flow regression evidence

`tests/test_oct4_signal_lifecycle.py` uses actual DrivePolicy and ACC plugins,
Autopilot, Engine hotkey/telemetry processing, immutable producer publication,
signal V2 binary reader/route selector, real Controller/SCS writer and a
chronological in-memory mapping. The navigation-window case additionally uses
actual Map, directed LanePath building and NavigationIntentTracker. Existing
tests supply stale/identity/selector/export coverage and the explicit slope/load
model. No backend is programmed to automatically report success: gear and speed
are declared SDK inputs, and every intermediate pedal write is recorded.

Before tests were also run against original `cdea197` modules loaded only into
memory; no checkout/reset or working-file replacement was used:

- Seven selected lifecycle/witness cases fail on original modules.
- Keeping the runtime-witness fix but restoring only the old hold-seeding rule
  gives **1 failure / 1 pass**: first-brake gear 0 fails, gear 4 passes.
- Restoring only the original journal makes the full-producer export fail
  because waiting/restarting provenance is unavailable.
- Final targeted selection: **366 passed, 20 subtests passed**, 14 selected
  files. Earlier runs overlap and must not be added to this count.

| Production scenario | Result |
| --- | --- |
| One N, no manual throttle; simple-auto probe, actual gear confirmation and active pedal takeover | PASS offline |
| First planned positive brake at gear 4 or admitted moving gear 0; incident speeds 0.067375 → 0.018660 → 0 m/s | PASS: continuous positive brake, zero throttle, active planned wait, no technical hazards |
| Three consecutive red/wait/green/restart cycles, both modes, Engine-before/after-Plugin ordering | PASS: same activation, no extra N, no overlapping positive pedals, no parking writes |
| Two new green acquisitions of the same locked ID, >=100 ms separation | PASS: ordered release then existing bounded launch; real-auto Drive confirmation retained |
| Stale/future/repeated/torn/inactive signal, reset, missing/wrong/ambiguous head, another uncleared following/brake reason | PASS: no unproven restart; unknown is not clear-road evidence |
| Actual Map ADVANCED_PREFIX/SAME_EXACT with both real pedal producers | PASS: valid locked stop and same activation survive the window rebase |
| R, backward motion, stale SDK/command, authority change, manual cancellation, broken/failed brake write, driver parking brake | PASS: revocation and no automatic recovery; no blind new positive brake edge at rest |
| Backend release interrupted by reverse or identity/clearance change | PASS: existing rechecks prevent positive launch |
| Combined export with realistic-length route identities and all producers | PASS: hash/order round-trip, stop source/lock, gear/speed/frame/original time, wait/resume phase, selected source, returned pedal writes; confirmed=false, runtime_authorized=false |
| Journal capacity/byte eviction and original source timing during concurrent publication | PASS: bounded storage, exact original data, no relabeling to a later packet |

The manual-pedal gearbox model counts a new positive brake edge at rest as a
possible reverse request. It reports zero such edges during supported cycles.
It is based on the user's manual-pedal observation, **not measured SDK/DLL
consumption**. Existing 12/40-tonne and ±8% grade tests use explicit service-brake
force/static-friction assumptions, not ETS2-calibrated hill holding.

## Numerical preservation and operation costs

All **16 steering** benchmark case dictionaries are numerically equal to HEAD;
all **12 longitudinal comfort** case dictionaries are equal. The modeled
emergency reaction remains **0.0 s**. These preserve the existing model results;
they do not prove vehicle comfort, stopping distance or live cadence.

| Isolated operation (200 calls) | Median ms | p95 ms | p99 ms | Maximum ms |
| --- | --- | --- | --- | --- |
| Original arbitration at the same all-producer stop | 0.191 | 0.213 | 0.288 | 0.309 |
| Corrected arbitration | 0.160 | 0.178 | 0.297 | 0.338 |
| Corrected Engine flush, diagnostics enabled | 1.369 | 1.639 | 1.800 | 1.864 |
| Corrected Engine flush, diagnostics disabled | 0.587 | 0.654 | 0.830 | 7.943 |

The original arbitration loses the runtime stop witness in **200/200** calls;
the corrected operation loses it in **0/200**, with identical selected pedal
values/source/identity/leases. Realistic-identity snapshot conservative accounting
falls from **43,674** to **31,710** bytes, below the unchanged source budget.
Journal remains **65,536 bytes / 128 events**, and collector/chunk/hash limits
are unchanged. Outliers are retained, not discarded. These are isolated frozen
SDK-input operation costs with real Controller memory writes; they are **not**
end-to-end Map cadence, a live load test, vehicle physics or game consumption.

Compileall of core/plugins/SDK/ui/tests/tools and `git diff --check` pass.
Sandbox temporary-directory PermissionErrors were separate from assertions;
export tests were rerun in unique working audit directories with the permitted
offline-test execution scope. The full pytest suite was not run.

Ignored receipts remain in `docs/steering-audit/oct4-service-lifecycle-20261004/`:
baseline-reproduction.txt, baseline-zero-seed.txt, baseline-export.txt,
operation-costs.json, steering-head/after.json and comfort-head/after.json.
Reproduction commands:

```powershell
$env:PYTHONCASEOK='1'
python -m pytest tests/test_oct4_signal_lifecycle.py tests/test_continuous_service_stop.py tests/test_signal_stop_resume.py tests/test_signal_clearance_source_contract.py tests/test_stop_handover_and_quiet_logging.py tests/test_longitudinal_evidence_diagnostics.py tests/test_longitudinal_arbitration.py tests/test_longitudinal_commit_and_preview.py tests/test_oct3_longitudinal_activation_races.py tests/test_rolling_longitudinal_authority.py tests/test_simple_auto_launch_handoff.py tests/test_activation_observation_binding.py tests/test_transmission_mode_activation.py tests/test_policy_signal_light_regressions.py -q -p no:cacheprovider --basetemp docs/steering-audit/pytest-oct4-user-recheck
python tools/run_steering_bench.py --ref cdea197 --output docs/steering-audit/oct4-service-lifecycle-20261004/steering-head.json --quiet
python tools/run_steering_bench.py --output docs/steering-audit/oct4-service-lifecycle-20261004/steering-after.json --quiet
python tools/run_longitudinal_comfort_bench.py --ref cdea197 --output docs/steering-audit/oct4-service-lifecycle-20261004/comfort-head.json
python tools/run_longitudinal_comfort_bench.py --output docs/steering-audit/oct4-service-lifecycle-20261004/comfort-after.json
```

## Runtime scope and remaining game gate

Changed runtime files: **core/engine.py**, **core/longitudinal.py**,
**core/service_brake_hold.py**, **core/navigation/longitudinal_diagnostics.py**.
Additional changes: the lifecycle regression test, this report, changelog and
the linked stop-report addendum. No new DLL or plugin-source change is required
by this patch. Deploying partial core versions would be an invalid combination.

Read-only disk checks found the existing candidate hash
`53D8C54D2B71ABB2F1D2DE8CB68CD096F22F8385F750F46CE07AF105295C3BCF` both in installed
`assets/ets2la_plugin.dll` and
`C:\Program Files (x86)\Steam\steamapps\common\Euro Truck Simulator 2\bin\win_x64\plugins\ets2la_plugin.dll`.
It matches the already built candidate-e from the prior signal report. Disk
identity does not prove that an existing game process loaded it or that its
live hooks/head selection work. No DLL was rebuilt or replaced here.

After the user's full suite and separately approved coordinated deployment,
the supported single-head lifecycle is ready for a short controlled game check.
There is **no need for another speculative drive to diagnose the fixed code**.
The one remaining live capability to establish is uninterrupted consumption of
the held SDK service brake across a stationary zero ratio, followed by a new
locked green and the existing restart. It has not been demonstrated by this
offline task. Phase 7's live stop/comfort verdict remains NOT VERIFIED.

For that later check, first inspect producer V2 validity, advancing generations,
session/route identity and unique locked head while stationary. Do not proceed
with missing/stale/ambiguous signal evidence. On a safe level approach, the user
may then perform one supported red-wait-green cycle with one initial N and no
manual throttle, ready to take control. Abort for R/backward motion, unexpected
brake release/rolling, power while holding, wrong head, stale authority, backend
failure or a technical stop. Record the existing combined source/selected pedal
decision, gear/speed/frame/original time, hold chain/lock, ordered backend writes
and later SDK observations. Do not manufacture an emergency or promise coverage
of every intersection, grade, mod or ACC target.
