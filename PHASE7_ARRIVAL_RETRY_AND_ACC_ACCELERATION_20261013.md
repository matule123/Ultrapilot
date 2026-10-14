# Phase 7 — October 13 follow-up: arrival, reactivation and stop ownership

October 14 continuation: see
[PHASE7_DESTINATION_STOP_AND_ACC_COMPLETION_20261014.md](PHASE7_DESTINATION_STOP_AND_ACC_COMPLETION_20261014.md)
for the new source-timed native candidate, functional derivative/anticipation
changes and original-body stop clearance. The measurements and rejected drafts
below remain the historical 1.2.1/1.1.4 follow-up; they are not relabeled as
verification of the later ACC 1.3.0/DLL candidate. Destination disappearance
classification remains explicitly unfinished.

## Verdict and build identity

**PARTIALLY OFFLINE VERIFIED / GAME NOT VERIFIED. The complete request is not
closed.** GPS disappearance cannot yet be classified as successful arrival;
qualified leader acceleration prediction and complete-body AEB remain blocked.
No deployment, game operation, diagnostic arming, commit or push was performed.

Entry HEAD: `b3d82bb6d17a519f1efa1c1f2e96525f4d33f259`, clean working tree.
The installed receipt `manual-deployment.json`, scope `acc-departure-lifecycle`,
timestamp `20261013T174542792Z`, names source commit `d584ad6` and correctly
records uncommitted content. At entry, **24/24 installed hashes matched the
receipt and 24/24 contents matched the source after LF/CRLF normalization**.
The final read-only check confirms all 24 receipt hashes again: **22 versioned
Python/runtime entries match `b3d82bb`**, while two installed DLL entries refer
to the same ignored compiled workspace artifact. Those DLL bytes match the
receipt/artifact exactly; they are not falsely attributed to a Git object.
The later commit marker is not used to identify runtime content. Candidate
changes below are local and are not installed. ACC advances 1.2.0 -> 1.2.1;
DrivePolicy advances 1.1.3 -> 1.1.4 for its demonstrated producer fix.
Map 1.1.2, Autopilot 1.3.4 and TurnSignals 1.0.2 are unchanged.
DLL `1.59.3-up-signal-scope` is unchanged.

## Preserved evidence and causal limits

Read-only analysis: `tools/analyze_oct13_followup.py`; expanded immutable
references use `core.steering_replay.inspect_replay`, including integrity checks.
Derived large JSON/logs stay in ignored `docs/steering-audit/oct13-followup/`.
All original files remain in the installation's `route-diagnostics` directory.
Six completed replay/incident files passed integrity inspection. The unfinished
`steering-replay-20261013T175651.482499Z-plugin_stop.json.tmp-*` was not promoted,
deleted or treated as complete evidence. No older significant-event export was
substituted for this session; the latest ones are from October 10.

| Evidence (UTC file time; log uses local time) | What it proves |
| --- | --- |
| `steering-replay-20261013T175621.766498Z-automatic_disable.json` | At 19:56:21 the first AP intervention was `acc: invalid longitudinal observation`, activation 22232453365400, frame 252673226. Its observation was about 37 ms old. The rejected original ACC packet was not retained: the log's detail-budget marker cannot identify its invalid subcondition. |
| `steering-replay-20261013T175812.617248Z-manual_disable.json` (827 samples) | Manual disable of the second application session; not the subsequent unexpected stop. |
| `steering-replay-20261013T175945.736991Z-automatic_disable.json` and dense companion `...175945.900413Z...` (1793 samples) | A traffic brake demand established hold at monotonic 22404.3793202. The retained 30 s history starts at 22406.4573366; the original actor/conflict request is absent. Current traffic/light/ACC brake demands were already zero while the retained hold imposed about 0.212496 brake. The final first fault at 22436.4932254 was actual observed R, frame 456448408. |
| `steering-replay-20261013T180045.547978Z-automatic_disable.json` and dense companion `...180045.737986Z...` (1203 samples) | At 20:00:45 the GPS destination disappeared while speed was 10.5741596 m/s, gear 11, frame 516196018. The last detailed consumed GPS remainder was about 137.646 m, not zero. The context lost intent/build and revision became 9. First AP cause was no GPS authority; later token/identity cleanup was secondary. |

The second session used intent `8141bcc7ee22442e99f4fbd37771e7f5`, revision 8,
build `2098289b133a410bb62f0b5322c5f803` before GPS clearing. The stop fault used
activation 22349956083000; the following activation used 22438663365800.
Session/dataset/intent are compared, not inferred from filenames.

**The restart-only activation problem has a direct historical stack trace.**
At 19:50:20.009 DrivePolicy entered `_compute_planned_speed` with no `speed`
in the startup truck dictionary, raising `KeyError` at installed main.py:181.
Attempts at 19:50:21.355, 19:50:23.099 and 19:50:26.074 failed at the same line.
The manager then exhausted its deliberately bounded three restart attempts.
N attempts at 19:55:35, 19:55:54, 19:56:18 and 19:56:27 reached their launch
bound without a Policy packet. Their recorded reason was
`policy: missing or unsupported longitudinal packet`; the intervening N
cancellations were manual. A new app startup at 19:56:59 produced a working
Policy. The manager guard was doing its intended job; missing initial telemetry
was incorrectly promoted into a worker crash by the producer.

The final detailed brake receipts before R remain positive; a brake-zero edge
is **not demonstrated** in that interval. Software continuity is not proof of
continuous game consumption. The manual-pedal gearbox observation is not
silently applied as an established SDK guarantee. R protection stays active.

## Stage 1: reproduced defects and repairs

| Production defect | Reproduction before | Repair / after |
| --- | --- | --- |
| DrivePolicy directly indexed startup `truck['speed']` after treating missing speed as zero elsewhere. Expected startup absence exhausted the crash restart budget and left subsequent N attempts without Policy. | Actual `plugin_worker` + real Policy: three KeyErrors terminate the worker before later telemetry. Missing/None/string speed also raises; NaN publishes an unverified default plan. | Validate the single consumed truck observation before planning. Publish an explicit invalid zero-brake/no-plan result, keep the required producer alive and discard previous dynamic plan. With a later genuine valid frame, the same instance publishes valid Policy. Full Map/Policy/ACC/AP/Engine/Controller recovery passes for both gear modes without a process restart. Nonfinite data, source freshness and invalid intervals remain rejected. |
| The original traffic cause is lost from the long-lived stop receipt after its beginning leaves the 30 s rolling history. The physical hold itself is NOT proved erroneous by the saved incident. | The first historical receipt names traffic, but lacks its decisive actor/conflict. New tests cannot retrieve the compact producer basis from `stop_reason`. | Preserve the FIRST compact consumed brake basis/decisive ID, route distance and prediction times in the existing stop receipt and export. Do not rewrite it when later demand is zero. Control behavior stays conservative. This improves future evidence; it does NOT fix the unexplained historical unexpected stop. |
| A zero invalid ACC packet from the previous activation was treated as a current technical failure before the independent ACC producer acknowledged a valid new N. | Both modes: N off/on, Policy ticks before ACC, AP/Engine enter `controlled_stop` with no drive. | Quarantine only the invalid **zero, non-emergency ACC result of another epoch** within the existing initialization bound. Check its original schema, frame, all original times and unchanged non-epoch authority. Never return it as usable or rewrite it. Await a new valid producer result; continue automatically without another N. |
| The invalid-startup early return preceded ACC private-target ownership cleanup. | A new epoch with invalid dt publishes invalid zero output but retains old private following fault/actor. | Revoke old private following/PID memory on real activation/session/intent change before validation. The invalid acquisition still publishes invalid zero output; a fault in the current epoch still stops. Valid same-authority geometry updates retain their existing departure witness behavior. |

The old invalid-ACC scheduling counterexample is a proved additional code defect, **not**
proof of the historical first invalid packet's source. A later valid tick could
already clear the private latch in the old code; that cleanup issue alone is not
presented as the primary cause of the historical restart-only failure. That
failure is explained by the retained DrivePolicy startup exception above.

A draft that classified a non-emergency crossing/route-candidate heuristic as
nonterminal was **REJECTED and removed**. Its initial new tests assumed the type
proved ordinary slowdown; that assumption was wrong. Existing unchanged
`test_native_crossing_demand_has_physical_hold_witness` reproduced a nearby
persistent native conflict: the draft lost hold and falsely disabled at zero
ratio. None of that test's expectations was relaxed. The final candidate
preserves the original planned-brake/continuous-hold admission and emergency
arbitration. Missing or zero traffic demand alone still does not clear a stop.
Correct release needs a qualified observation that the original reason ended;
the historical actor/conflict at hold start is absent. No new ride is requested.

### Arrival: blocked, not cosmetically fixed

`Local\\ETS2LARoute` supplies only UID, distance and route-time rows; the final
UID can be a truncated rolling horizon. SCS `routeDistance` is a remaining
distance, not a world target or a cancellation/completion event. City text is
not a physical endpoint. The available source provides no authenticated
destination lifecycle record that distinguishes **arrival** from **manual
waypoint removal** and pins the actual endpoint to that destination.

The last retained positive remainder was 137.646 m, outside the current stop
planning budget at its observed speed. The exact remainder/cancellation cause
at the clearing frame is not retained, so no physical 130 m endpoint or automatic
completion radius is inferred. Retaining that route merely
because a nearby final UID exists could continue after manual cancellation.
No such optimistic fallback was implemented. Existing fresh positive-distance
arrival braking/completion tests remain applicable; they do not verify this
disappearance case. The required interface is a producer-owned destination
record containing its stable target/position and explicit completion versus
cancellation lifecycle. More photographs or another identical drive cannot
create this missing contract. No new drive is requested.

## Stage 2: individual MonoCruise mechanisms

Reference inspected: local `Downloads/MonoCruise-stable/MonoCruise-stable`,
version 1.1.2, MIT copyright 2025 lukas deschryver. Reviewed ACC IIDM/CAH,
acceleration envelope and longitudinal architecture. No source code was copied;
its constants, ghost lead and body assumptions were not imported as ETS2 proof.

| Mechanism | Status | Actual scope / reason |
| --- | --- | --- |
| One requested signed acceleration/deceleration target | IMPLEMENTED, nominal representation only | Existing speed PID and selected pedal mapping expose `requested_acceleration_ms2` / `selected_acceleration_ms2`. `core/acc_acceleration.py` uses the explicit existing plant's 2.2 drive / 4.0 brake gains. The single arbitration and validated actuator path remain authoritative. These values are not measured acceleration or a new acceleration-feedback controller. |
| Stable mapping, anti-windup, pedal exclusivity | IMPLEMENTED / preserved | Signed demand has a deterministic exclusive mapping, numerically equivalent to the validated drive/brake requests. Existing saturation and external-output anti-windup, observation-dt and target hysteresis stay in place. Measured load-adaptive acceleration mapping is BLOCKED: no qualified actuator-capacity/road-load identification with causal game consumption is available. |
| Additional asymmetric acceleration recovery slew | REJECTED | Candidate 1 erased needed load compensation and failed steady error. Candidate 2 preserved integration and safety withdrawal but increased modeled jerk in target/curve/recovery cases. It is not in production. Existing ordinary Autopilot recovery and immediate safety paths remain. Smaller pedal steps were not mislabeled a physical jerk improvement. |
| Leader acceleration anticipation | BLOCKED | Raw acceleration slot exists, but traffic has no producer observation timestamp/generation or qualified acceleration accuracy. Receiver read time cannot qualify a new leader acceleration. Repeated unchanged buffers and disappearance must not become prediction or clearance. |
| Stable gap, cut-in and confirmed departure | IMPLEMENTED, existing 1.2.0 scope preserved | Existing speed-dependent protective gap and oriented tractor/trailer departure witness remain. Same-authority geometry republish, second lead, cut-in, actual loss and ambiguous source still use current production guards. Gaps are reference-point distances; reliable sensor following and stop-and-go are not claimed. |
| Predicted complete-body/trailer AEB | BLOCKED as a safety certification | Existing directed crossing prediction includes observed actor/trailer bodies and remains protective. It does not have a qualified producer clock/coverage nor a verified complete ego/trailer swept envelope. Arbitrary-object nearest distance and invented dimensions were not substituted. Emergency demands continue to override all ordinary comfort. |

Stopping-profile branches deliberately bypass the new nominal mapping and
report acceleration fields as unavailable. Original observations, 500 ms leases,
IDs and route geometry are unchanged. No new SDK/IPC reads are added.

## Fixed criteria and paired model evaluation

Use the pre-existing Phase 7.2 criteria, unchanged: settled RMS <= 1 km/h,
overshoot <= 2 km/h, a complete +/-1 km/h five-second settled window within
60 s, steady RMS regression <= 0.3 km/h and no extra steady pedal reversals;
same-flush emergency/drive withdrawal, exclusive pedals and original leases.
Do not retain a comfort candidate just because pedal steps shrink while model
jerk worsens. No newly invented game-comfort threshold is used.

`tools/run_longitudinal_comfort_bench.py` compares exact HEAD `b3d82bb` with
candidate over 12 identical 130 s seeded cases. Plant: 2.2 m/s² full drive,
4.0 m/s² full brake, 0.35 s actuator response, delay normally 0.12 s (0.25 s
jitter case), load/grade/drag/noise as declared by that tool. Each fixed-dt case
has 2601 rows; jitter case uses its actual dt. Jerk is the finite difference of
model acceleration using actual interval, **not ETS2 jerk**.

Rejected candidate 1 (0.8 nominal m/s³ drive rise, 1.6 brake release plus positive
integral deletion): launch steady RMS 0 -> 1.875 km/h; noisy steady 0.070 ->
2.73 km/h; jitter 0.158 -> 3.35 km/h. Candidate 2 (retained integral, immediate
brake release): noisy steady RMS 0.070 -> 0.095 km/h and launch drive step
0.040 -> 0.021, but p95 model jerk target-down/up 0.596 -> 0.713 m/s³,
curve 0.558 -> 0.787, ACC slowdown 0.528 -> 0.717. Neither was accepted as
the requested comfort improvement. The final candidate retains the old pedal
trajectory to floating-point rounding; final verification results below must
not be confused with either rejected candidate.

Final paired comfort matrix against `b3d82bb` has a maximum absolute numeric
metric difference of **4.31e-16**; all 12 cases retain their behavior. Selected
metrics (before -> final, original units):

| Scenario | Steady RMS km/h | Settling s | p95 model jerk m/s³ | Steady pedal reversals |
| --- | --- | --- | --- | --- |
| Launch 0 -> 50 | ~0 -> ~0 | 9.25 -> 9.25 | 0.12418 -> 0.12418 | 0 -> 0 |
| Steady noise | 0.07036 -> 0.07036 | 3.95 -> 3.95 | 0.46123 -> 0.46123 | 0 -> 0 |
| Target down/up | 0.000003 -> 0.000003 | 4.80 -> 4.80 | 0.59629 -> 0.59629 | 0 -> 0 |
| Curve cap | 0.000011 -> 0.000011 | 6.15 -> 6.15 | 0.55783 -> 0.55783 | 0 -> 0 |
| ACC ordinary slowdown | 0.000004 -> 0.000004 | 3.65 -> 3.65 | 0.52815 -> 0.52815 | 0 -> 0 |
| Heavy uphill | ~0 -> ~0 | 13.85 -> 13.85 | 0.06848 -> 0.06848 | 0 -> 0 |
| Braking downhill | ~0 -> ~0 | 0.05 -> 0.05 | 0.01239 -> 0.01239 | 0 -> 0 |
| Jitter/delay | 0.15758 -> 0.15758 | 14.55 -> 14.55 | 0.84331 -> 0.84331 | 0 -> 0 |

Emergency reaction remains **0 s in the model**; zero observation age in this
idealized plant is not a live IPC latency measurement. Independent full-path
integration tests cover actual identity/freshness/write gates. All **16 steering
benchmark case reports are exactly equal** against `b3d82bb`, including left/
right curves, S-curve, roundabout, straight and log-excited delayed cases. Neither
test is a claim of improved game comfort or completed destination stopping.

`tools/compare_oct13_followup.py` additionally uses the same actual traffic
decoder/selector and model with old versus final ACC/AP classes. The selector
is unchanged from entry HEAD. Seven paired following cases retain all metrics:

| Case | Minimum reference gap m, before -> after | Minimum model reference TTC s | Steady speed RMS km/h | Target switches |
| --- | --- | --- | --- | --- |
| Slower straight | 32.00000 -> 32.00000 | 11.06288 -> 11.06288 | 0.000061 -> 0.000061 | 0 -> 0 |
| Slower left/right | 31.99999 -> 31.99999 | 11.06275 -> 11.06275 | 0.000061 -> 0.000061 | 0 -> 0 |
| Roundabout | 32.00001 -> 32.00001 | 11.06250 -> 11.06250 | 0.000061 -> 0.000061 | 0 -> 0 |
| Braking lead | 22.00019 -> 22.00019 | 11.06288 -> 11.06288 | 0.004522 -> 0.004522 | 0 -> 0 |
| Cut-in | 18.37348 -> 18.37348 | 5.81161 -> 5.81161 | 0.004104 -> 0.004104 | 1 -> 1 |
| Jitter/heavy | 32.30280 -> 32.30280 | 11.13692 -> 11.13692 | 0.518429 -> 0.518429 | 0 -> 0 |

Fixed cases use 1401 samples over 70.05 s; seeded jitter uses 1053 samples over
70.04 s. TTC is positive candidate reference gap / positive closing speed from
the model's qualified synthetic observations, not bumper TTC. No reference-point
collision occurred in these models; that does not certify complete-body AEB.
Their 0.12 s backend queue models transport only; physical mapping is separately
covered by the integration tests.

## Verification and runtime bundle

Before repair: four initial integration reproductions failed; the subsequent
old-zero-invalid-ACC reactivation reproduction failed in both modes. After:
The 15 initial new regressions passed; after the historical Policy cause was
added, the Policy/lifecycle/arbitration/rebase/reactivation run passed 126 tests
and the new/comfort/destination/signal subset passed 105. After rejecting the
stop-ownership draft, **107 hold/lifecycle/reactivation regressions passed**.
The new real native-byte crossing scenario traverses Map/Traffic -> Policy ->
ACC -> AP -> Engine -> Controller and preserves the original protective hold,
with its decisive first cause available for export.
Negative tests cover current-epoch invalid ACC, stale/future observations,
foreign intent, nonzero old output and emergency; none receives positive drive.
Existing regressions cover manual off, real R, backend failure, signal wait/
green release, destination removal, leader loss and native trailers.

**Final full pytest: PASS — 2507 passed, 1592 subtests passed in 601.09 s**
(10:01), completed on 2026-10-14. Command: `python -m pytest tests -q` with
`PYTHONCASEOK=1`. Log:
`docs/steering-audit/oct13-followup/full-suite-after-hold-review.log`.
`compileall` and `git diff --check` pass for the final source. Tests are offline;
they do not establish game arrival, traffic clearance or physical comfort.
The first full-suite attempt was interrupted at 29%, without a summary; the
second was deliberately stopped when the historical Policy producer defect was
identified. Neither is counted as PASS or a test failure. A diagnostic full run with `-x`
failed on the rejected hold draft after **1107 passed, 159 subtests** in
307.27 s. That failure is recorded and the old safety regression is retained.

Three paired cost runs after the full suite use 360 SDK/output ticks each
(18 modeled seconds) and 40 native-byte traffic actors through actual
Policy/ACC/AP/Engine/Controller, copied in-process IPC and SCS BytesIO:

| Run | Median ms before -> after | p95 ms | Maximum ms |
| --- | --- | --- | --- |
| 1 | 8.8545 -> 8.8422 | 9.9233 -> 9.6235 | 25.6303 -> 28.0259 |
| 2 | 8.9096 -> 8.9303 | 10.2011 -> 10.0044 | 28.7163 -> 28.0600 |
| 3 | 8.6925 -> 8.6875 | 9.5110 -> 9.1958 | 28.3781 -> 26.1192 |

All physical backend mappings and IPC read counts matched exactly. Median
increment ranges -0.0123..+0.0207 ms; tail costs fluctuate and no tail-speedup
claim is made. This measures whole operation cost, not live scheduling,
first-packet delivery or game consumption. Retained history is 188234..188240
bytes before and 188237..188242 after, within its unchanged 1 MiB budget;
detail stays within 64 KiB. Test mock histories are cleared/excluded. This
cruise-cost scenario does not measure memory of every possible stop cause.
Reproduce with `python tools/compare_oct13_followup.py --cost-samples 360
--output docs/steering-audit/oct13-followup/pipeline-cost.json`.

Exact consistent runtime candidate (no tests/reports/data/DLL):

- `core/longitudinal.py`
- `core/service_brake_hold.py`
- `core/acc_acceleration.py` (new dependency)
- `plugins/acc/main.py`
- `plugins/drivepolicy/main.py`

The final package is `docs/steering-audit/oct13-followup/oct13-followup-runtime.zip`
with a per-file SHA-256 manifest `runtime-candidate.json`. Archive SHA-256:
`709a1c994c5889ad0fe216911ebc4b2b1d10c69416ab8a9d0ba0e0fe751e4452`.
All five archived files match the final working-tree hashes. The manifest
truthfully says `local_uncommitted_changes=true`, `NOT_DEPLOYED` and
`game_verified=false`; this is not an installation receipt.

Other changed files: `tests/test_oct13_followup.py` (21 parameterized regressions),
`tools/analyze_oct13_followup.py`, `tools/compare_oct13_followup.py`, this report,
`PLUGIN_CHANGELOG.md` and `DEFERRED_WORK.md`. Large derived evidence, benchmark
JSON/logs and the ZIP remain ignored. Originals, settings and map-cache are untouched.

Candidate package is not a deployment receipt. It must be separately approved,
backed up and content-verified before installation. No game success or complete
arrival support is claimed. Unchanged steering controller, geometry, packet
cadence, 5 m signal reference, service-brake chain, signal restart, indicators,
parking ownership and safety timeout behavior remain acceptance requirements.

## Explicit remaining work

1. **Arrival after GPS disappearance: BLOCKED.** Obtain a producer-owned stable
   destination point and completion/cancellation lifecycle. Do not treat a
   truncated UID endpoint, city name or driver waypoint removal as arrival.
2. **Historical unexpected traffic stop: NOT RESOLVED.** Its initiating actor/
   conflict is outside retained history and no qualified stop clearance exists.
   The rejected heuristic-type shortcut is not part of the package. The existing
   stop receipt now preserves its first compact cause without an extra collector.
3. **First current-epoch invalid ACC packet at 19:56:21: subcondition NOT
   VERIFIED.** Its exact packet was not retained. This is distinct from the
   historically proved Policy startup crash and the reproduced retired-epoch race.
4. **Physical acceleration mapping, producer-timed lead anticipation and
   complete-body AEB: BLOCKED** by the qualified channels stated above. The
   nominal demand metadata is not a claim that these mechanisms are completed.
5. **New fixes in ETS2: GAME NOT VERIFIED.** No installation changed and no new
   drive is requested. The present task is not declared completely solved.

Suggested commit (not created): `fix: recover Policy startup and quarantine retired ACC requests`.
Description: validate genuine startup telemetry before Policy planning, preserve
bounded activation ownership, expose nominal acceleration provenance and retain
the first traffic stop cause; document rejected comfort/hold drafts and precise
remaining source-contract limitations.
