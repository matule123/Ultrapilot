# Phase 7 — following ownership, continuous hold and indicator execution

Date: 17 October 2026. **Core implementation; GAME NOT VERIFIED. Nothing deployed.**

## Build and evidence identity

Entry HEAD: `5a82d0a3861bd1fcec1f05582a6cbc4b26227604`. Entry tree was clean.
All 36 installed `manual-deployment.json` file hashes matched. The 28 inspected
runtime files also matched source after LF/CRLF normalization. Receipt SHA-256:
`02438dc44eb65392b92c0e9da8e6252048dea938fcdb8c5e414183d5afe8f670`.
The installed versions are ACC1.3.8, Autopilot1.3.4, Map1.1.2,
DrivePolicy1.1.4 and Turn Signals1.0.2. They are unchanged: this candidate changes
core implementations, not these plugin files. Native1.59.5-up-parked-records
is unchanged, SHA-256
`fd06c12985fb67c48a7b9aaf5dd500d81e6ac23b928b79c95997bb8ed5d55d27`.

Read-only sources are the installation's `ultrapilot.log` and nine integrity-valid
replays from 20261017T151712–152107 UTC. The two automatic pedal incidents end
151729.338663 and152107.223195; their dense partners end151729.443662
and152107.137422. The manual dense replay ends152056.713693. Four earlier
significant-event exports end151712.368794,151713.147486,151714.444828
and151714.885517. Existing immutable references were expanded with the existing
codec, not replaced with mutable current slots. Origin hashes, exact identities,
decoded copies, chronological writes and analysis are under
`docs/steering-audit/oct17-following-hold-signals/`. Reproduce using
`python -m tools.analyze_oct17_following_hold` (entry snapshot never overwritten).

The related `steering-timing-20261017T152120.377337Z-plugin_stop.json` was also
inspected with the existing codec: integrity valid, same session/intent/build,
576 calculation samples and0 execution samples. SHA-256:
`b74154c50d2727d4cdacf3c1f2ea87a1446c61910b47c7af7b3ba49b91406523`.
It contains no actor/following fields and cannot recover the missing original
actor lists or prove game consumption. `timing-inventory.json` records this check.

All three activations share session1, map `promods-1.59`, dataset
`d6cc7936fce4e902761abb5d`, intent `53d999f1460f42aca87cb26e8227d019`,
revision5, build `7a962573a0b14f12b7351bfd98562ac2`, geometry
`ea29f5c5b6208cb6f2dcd9cf9b7997f2f81ac056b9df9811dbf967c9a7e6d33d`.
Activation tokens differ:32845544831900,33042269180700,33082379034500.
The morning whole-suite PASS is evidence for its earlier build, not these new
afternoon behaviors or this uncommitted candidate.

## Causal findings and changes

| Area | Recorded evidence | Reproduced defect and correction | Limits |
| --- | --- | --- | --- |
| First roundabout | Original crossing owner57 at32865.789; independent body73 braking from32868.4505; first fault32869.1236469, `ACC target unavailable or unconfirmed departure`. Command observation45ms old,418ms lease left, identity unchanged. | Crossing completion incorrectly required **global** body brake zero. Completion now requires no crossing/body conflict for the original target, with the existing still-observed identity/acquisition witnesses. Actor73 continues to brake independently. Both-mode end-to-end regression verifies positive physical brake and no false owner57 fault. | The original complete actor lists/completion witness are not retained at the fault. The reproduced global defect is proven; its exact historical branch is not uniquely recoverable. Actor73's 2.49s model contact is not proof of physical collision or a proven false hazard. |
| Qualified green but continued hold | At33070.23785 actor52's body prediction creates another stop; at33071.197 ID1 is green/reserve-sufficient, yet B≈0.4367 continues. Actor52 is behind, moving approximately in our direction. | The fixed-motion model treated a rear catch-up as a forward-brake stop owner, whose clearance then required leaving the route. For fully-behind parallel native bodies on a complete straight/aligned prediction only, retain a bounded rear warning instead. Braking cannot avoid this particular catch-up. Current overlap, crossing, forward or uncertain geometry remain braking hazards. Native reader→selector→Policy/ACC→Autopilot→Engine→Controller red/hold/new-green/restart now passes both modes. | The exact recorded actor52/own-body acquisition is a tracked fixture, rigidly transformed into a known Map fixture. Original full route is absent; the transform is an offline reconstruction, not the historical route. Other genuine stop reasons still block release. |
| Native gear−1 | Raw signed SDK gear at offset504; first fault33086.9471966 compares frame542911616, observation33086.9328787, gear−1 and speed−0.00194796m/s. Earlier retained history shows B=0 at33086.1487, then B>0 at33086.2209; later SDK brake reaches0. | The admitted approach brake could be released in the last existing1.5m band while still above0.5m/s. The same ending-green countdown also changed stop→dilemma/go→stop as own speed changed. Preserve the already admitted positive chain in the terminal band, and commit the original ending-green stop until a genuinely new qualified phase. No new stationary brake edge, target shift or R exemption. | No driverR is assumed. Backend return and sampled SDK response do not certify continuous game consumption. These software edges can reproduce the user's gearbox model but are not definitive proof of the exact physical cause of historical R. True R remains rejected. |
| Invisible route indicator | Accepted right17:20:28/cancelled17:20:36; preceding safety hazard from17:17:29 remained latched. No Controller blinker command on this activation. Profile keys leftX/rightC. | Pending N/UI activation left `safety_hazard_active` true because immediate `new_state` was false during gear confirmation. Clear the preceding owned latch on **accepted pending activation** too. Existing Controller turns hazards off, writes one indicator pulse/release and receives a later stable SDK state in the modeled full path. | Historical focus and actual keyboard consumption are absent. Accepted request is not execution proof. Manual/still-observed hazard priority remains; no blind toggle retry or turn topology change. |

First rejected traffic comparison: SDK frame333369998, observation32869.0745800,
computed32869.1066365, checked32869.1199550, expiry32869.5379364. The intervention
itself was recorded32869.1236469 using a newer current frame333403330; it must not
be substituted for the originally compared frame. Successful mapping returns
then record throttle0 at32869.1421219 (event790), brake0 at32869.1421674 (791),
followed by `release_all` throttle0/brake0 at32869.1687720/.1688082 (792/793).
The original first cause survives in events790/791; subsequent release records
are not a replacement first cause. `game_consumption_verified=false` throughout.

At nativeR, the retained subsequent release is event2031 throttle0, returned
33086.9714690, then2032 brake0, returned33086.9714996. Their consumed observation
is frame542911616 at33086.9328787, gear−1, speed−0.00194796m/s. These **later**
safety writes cannot explain the **earlier** transition toR. The earlier observed
zero/reapply chain is the separate software defect under reproduction.

### Rear-prediction classification boundaries

No nearest-object substitution or invented IDs are used. Only existing native
actor and ego tractor/trailer boxes participate; every predicted own heading and
actor heading must remain within10 degrees of the current tractor heading,
and the entire actor front must lie behind the rearmost ego body. A complete
13-sample/3-second prediction is required. Observed overlap is checked first and
always brakes. Up to16 non-braking rear warnings are retained; this list is not
an empty-road certificate. The existing crossing and lead selectors still run.
No sensor coverage, lane assignment or exact bumper separation is claimed.

### Brake/green ownership

The existing spatial stop reference, 5m derived offset, PID, limits and safety
timeouts are unchanged. Terminal continuity only preserves an already physically
admitted positive forward-started brake; it cannot authorize a new stationary
chain. The original green lock, authority/lifecycle/ID/passage and decreasing
producer countdown must match to retain the ending-green stop. A new green with
reset countdown uses the existing two-acquisition clearance proof. Red, unknown,
missing/stale/foreign data and other conflict owners never become clearance.

## Reproduction and acceptance

New tests use the real native traffic ABI reader and existing Map fixtures,
DrivePolicy, ACC, Autopilot, Engine, Controller and chronological test-backend
writes. Backend success is not game consumption. The fixture
`tests/fixtures/oct17-rear-body-receipt.json` preserves actor52's exact recorded
dimensions, pose, speed, own tractor/trailer boxes, source hash and acquisition.
Missing full original route and other actor records are explicitly marked.

The original behavior is loaded read-only from the receipt-matching entry ZIP
by `UP_OCT17_FOLLOW_BASELINE=1`; all new assertions stay unchanged. The final
before/after records are `final-contract-before.log` and `new-targeted.log`:
**16 defect cases fail on entry, six positive AEB controls already pass; all24
new cases pass after correction** (22 control cases plus two archive tests).
Earlier development records with corrected fixture contracts are preserved and
superseded; they are not counted as independent historical evidence.

Acceptance reuses existing stop-profile bounds rather than inventing new
thresholds. Mandatory checks: per-owner completion must not suppress another
hazard; no zero brake after terminal chain admission on red; new green releases
only after every real cause clears; true AEB writes positive brake; indicators
must emit one pulse/release and receive later stable feedback. Existing
both-mode20/35/50km/h closed scenarios and negative R/stale/identity/backend,
manual-off, crossing ambiguity/disappearance and asynchronous refresh tests
remain unchanged. Models are not ETS2 physical measurements.

Verification totals and final frozen hashes are recorded below after the single
whole-suite run. A preceding combined targeted run passed304 tests/7subtests;
the final expanded local set passed24 tests. No failed mandatory scenario is
being replaced with a general pytest PASS.

## Performance and preserved behavior

`tools/benchmark_oct17_following_hold.py` alternates entry/current order over
three repeats, both transmissions, DEV display off/on, 25 warm-up +80 measured
ticks per run. Each tick executes the existing production pipeline with nine
synthetic native actors. Output hashes and source-read counts must match across
entry/current for these unchanged scenes. It measures wall and threadCPU
separately and records GC; mocked IPC is not real transport/scheduling latency.
The host threadCPU clock is quantized at15.625ms, so its per-tick values cannot
support sub-millisecond CPU claims.

The exploratory `performance.json` is preserved. The final repeat after the
whole suite, without concurrent tests, is `performance-frozen.json`: identical
benchmark logic with only its no-overwrite output filename changed in memory;
no production instrumentation or source edit. Per-run worst reported percentile,
entry→candidate, wall milliseconds: **p50 7.942→7.999; p95 9.709→10.124;
p99/max 12.700→14.381**. Paired per-run median deltas span−0.274…+0.187ms;
p95 deltas−0.735…+0.649ms; p99/max deltas−3.178…+5.900ms. Do not hide the tail
increase behind the median or claim this repair is a proven speed-up.
GC callbacks record maxima1.531ms entry and7.589ms candidate, but this aggregation
does not uniquely pair a GC span with the slowest tick or prove a historical
cause. Retained DEV snapshot deep memory is at most41,931bytes in both builds;
fixture/mock histories are excluded. All paired output hashes and source-read
counts match. These finite synthetic host runs measure overhead/jitter, not a
promise of live maxima or calibrated native timing. Steering/comfort comparisons use
the same HEAD inputs and analytical plants: **all16 steering and12 ordinary
comfort result dictionaries are exactly equal**. This preserves these finite
models, not all possible live vehicle response. The ordinary comfort benchmark
does not exercise the new rear classification or ending-green commitment;
those have separate production-path regressions above.

### Paired full red/hold/green model, installed entry versus this candidate

`paired-red/results.json` contains six additional paired runs with the same
existing explicit plant: 0.35s input delay, 0.6s brake response, mass ratio1.4,
jitter and a slower independently scheduled Policy. The original entry methods
come from the deployment-matching snapshot, **not** the earlier morning broken
reference equation. All runs resume withoutN in both modes, with zero red target
overruns, zero far crawl, zero simultaneous positive physical pedals, no parking
writes and one drive→brake transition on red. This ordinary red scenario passes
before too; it is a preservation check, not the new fault reproducer.

| Initial speed | SDK-reference gap to derived target, entry→candidate (m) | Maximum model deceleration, entry→candidate (m/s²) | Maximum absolute model jerk, entry→candidate (m/s³) |
| --- | --- | --- | --- |
| 20km/h |0.595→0.725|1.053→1.053|1.887→1.960|
| 35km/h |0.606→0.760|1.185→1.185|1.902→1.902|
| 50km/h |0.609→0.748|1.512→1.512|1.587→1.866|

These stop/deceleration/jerk values are identical for modes0 and3 in this plant.
Candidate green-to-positive-drive delay is0.159/0.222/0.187s in simple auto and
0.349/0.365/0.347s in real auto, for20/35/50km/h respectively. Entry values are
0.282/0.126/0.142s and0.472/0.286/0.302s. Deceleration and pedal reversal counts
are preserved. Retaining the terminal brake stops about0.13–0.15m earlier and
increases model peak jerk by0.073m/s³ at20km/h and0.279m/s³ at50km/h. This tradeoff
is explicitly recorded; no new comfort PASS threshold is invented. Existing
closed-model acceptance against the prior broken-reference baseline remains
unchanged. Real comfort is GAME NOT VERIFIED.

These gaps are **not bumper-to-painted-line measurements**. The plant's fixed
modeled front offset and prefab entry are declared assumptions; source target
offset stays5m. No physical calibration is inferred from this table.

## Significant-event quota: PREPARED, not applied

The installation still has eight significant-event files and is **NOT READY**
for another such file. Original logs/replays were not deleted or moved.
`tools/prepare_event_archive.py` validates each original with the codec and
SHA-256, makes a read-back-verified ZIP copy, and emits an exact-file reversible
PowerShell script. Default execution is a dry run. `-Apply` requires closed
applications, unchanged source hashes and no destination collision; no recursive
deletion or quota increase. Rollback restores moved originals on error.

Prepared artifacts:
`docs/steering-audit/oct17-following-hold-signals/event-archive-preparation/`.
ZIP SHA-256:
`a64c78ef0c1aa088ac63f855260de195e59a319ff885e1cc2d3e1cdf50c70bad`.
The dry run and PowerShell parse passed. Actual archival is a separate explicit
operation, not performed by this task. After it, run the existing read-only
`python -m tools.check_event_export_readiness --directory <installation>/route-diagnostics`.
Readiness does not certify that an unknown future payload will fit.

## Final candidate and remaining gate

The coherent core/runtime dependency list is taken from the prior verified
bundle and bound to all36 installed base receipt hashes; no whole-repository
copy. `tools.verify_oct17_following_candidate.py --verify` freezes code/tests/
fixtures/tools/changelog, runs the affected integration set, then the whole
suite once. `--package` refuses a changed hash or failed run and verifies ZIP
read-back. The unchanged required DLL is hash-bound, not included for replacement.

Exact payload and final ZIP hash are in `candidate-manifest.json` inside
`ultrapilot-oct17-following-hold-candidate.zip` and `candidate-receipt.json`.
This is a **candidate, not permission to install**. Settings, map cache, commit
marker and original records are not payload. Earlier proposals/evidence remain.
The earlier morning ZIP is superseded only as a future candidate proposal.

### Final immutable verification and package

- Frozen420 source/test/fixture/tool/changelog files. `frozen.json` SHA-256:
  `34dee7312a95fa25fb13f5303de4f4fef451095cfe96cc1d9eae34343a37f5a4`.
- Frozen affected integration group: **244 passed in105.78s**. Groups overlap
  earlier measurements and must not be summed.
- The single full run on this final build: **3008 passed,1592 subtests passed
  in791.31s (13:11)**. Exit0 and all420 hashes unchanged. Full log SHA-256:
  `a4ba6702d295e285360a24c0861a387bb33bc546a588bcf9da675b7afd35570a`.
- `verification.json` SHA-256:
  `7ccb22f3f08414f01b6ec887ac8a64fb34c63b96f0182fb019466f9996bed874`.
- `compileall` and `git diff --check` pass. No existing safety expectation was
  removed to obtain this result. The ordinary AEB controls pass both before/after.
- Prepared ZIP, **26 entries**, all read back and SHA-256 checked:
  `docs/steering-audit/oct17-following-hold-signals/ultrapilot-oct17-following-hold-candidate.zip`.
  SHA-256: `c03e6e5f4bdb1b68771522f2072d7a66d22fe47e9e7f106cd0f1823e3d629a79`.
  Receipt: `candidate-receipt.json`. All36 installed base files were rechecked
  during preparation. Native DLL unchanged and not packaged for replacement.

Another whole-suite run is unnecessary for these unchanged hashes. The
verification record deliberately has `game_verified=false` and `deployed=false`.
Archive application and installation still require separate approval.

Exact coherent payload (24 Python runtime dependencies and the changelog):

```text
core/acc_acceleration.py
core/acc_body_prediction.py
core/acc_following.py
core/engine.py
core/control_timing.py
core/longitudinal.py
core/pid.py
core/service_brake_hold.py
core/navigation/traffic_producer.py
core/navigation/longitudinal_diagnostics.py
core/sdk/traffic_snapshot.py
core/sdk/scs_sdk.py
core/telemetry.py
plugins/acc/main.py
plugins/drivepolicy/main.py
PLUGIN_CHANGELOG.md
core/hud.py
core/traffic_dev_hud.py
ui/visualization.py
core/controller.py
core/steering_replay.py
core/transmission_mode.py
plugins/autopilot/main.py
plugins/map/main.py
core/sdk/signal_snapshot.py
```

Only six runtime files differ from the installed base: `acc_body_prediction`,
`acc_following`, `engine`, `longitudinal`, `service_brake_hold` and
`sdk/signal_snapshot`. Other runtime entries are identical pinned dependencies.
No DLL, settings, tests, reports, map cache or original evidence is installed
by preparation. The manifest is the additional ZIP metadata entry.

Changed non-runtime files: this report, `DEFERRED_WORK.md`,
`tests/test_oct17_following_hold_signals.py`,
`tests/test_event_archive_preparation.py`,
`tests/fixtures/oct17-rear-body-receipt.json`,
`tools/analyze_oct17_following_hold.py`, `tools/benchmark_oct17_following_hold.py`,
`tools/prepare_event_archive.py` and `tools/verify_oct17_following_candidate.py`.
The release notes are the changed `PLUGIN_CHANGELOG.md` payload entry above.

OFFLINE VERIFIED applies only to the passing reproduced contracts and frozen
test/model scope. GAME NOT VERIFIED applies to this new core build, indicator
input consumption, uninterrupted SDK brake consumption, full route coverage and
the exact historical physical cause ofR. Actor73's physical conflict and missing
complete fault-time actor lists remain unresolved historical evidence limits.
No new drive is requested to replace those available offline reproductions.
