# Original ACC owner, body-brake intervention and the separate signal stop

**OFFLINE VERIFIED for the reproduced ownership/display defects; GAME NOT VERIFIED. The historical reverse
engagement and the exact ID 26 collision classification remain open. This is
not a claim that the whole reported drive is fixed. Nothing is deployed.**

## Source and installed evidence

Starting HEAD: `5f96e07` (`fix: release ACC v1.3.4 and stabilize crossing and
signal braking`). The existing eight-line Engine change and untracked
`tests/test_oct16_brake_owner_handoff.py` were preserved and independently
extended. No applicable repository/ancestor AGENTS.md was found. Plugin version
rules, the preceding Oct16 report and deferred work were reviewed.

All **33 installed receipt hashes match** `manual-deployment.json`. Every
runtime payload in the previous 19-file candidate matches starting HEAD after
LF/CRLF normalization. The initial local Engine edit is a real source delta,
not line endings. This audit uses content, not `commit.txt`. Reproduce with
`tools/analyze_oct16_owner_incident.py`; derived audit files remain ignored in
`docs/steering-audit/oct16-owner-handoff/`. Original collections/logs are intact.

The source changes ACC **1.3.4 -> 1.3.5** for actual dependency behavior.
DrivePolicy 1.1.4, Autopilot 1.3.4, Map 1.1.2, HUD 1.0.2 and turn signals 1.0.2
are unchanged. Native traffic DLL `1.59.4-up-traffic-timed` remains unchanged;
no new ABI, sensor, lane classifier or native identity guarantee is claimed.

## 1. The 15:55:36 technical rejection

Both `steering-replay-20261016T135536.629376Z-automatic_disable.json` (pedals)
and `...135536.676051Z-automatic_disable.json` (dense) pass the existing replay
inspector and immutable-reference codec. The pedal history spans **30.0165168 s**,
290 stored rows / 260 unique decision times, zero capture failures and no
history incompleteness. This does not make the short detailed write ring complete.

| Original file suffix | SHA-256 |
| --- | --- |
| 135536.629376Z-automatic_disable.json | 8946fdc3aad7810c0f3aca3a1aa8a814a9011965e3cb68f227a1755bd92c4a2d |
| 135536.676051Z-automatic_disable.json | ed6361a5126b4d60d68d12e0f5a6a37888c85c43a997f3298464fd7c4b724ede |
| 135424.528163Z-automatic_disable.json | f01a2d860aa7ff5c6c818bb31c92bb0b3281246ddca06b5132bf1addb9762152 |
| 135424.791758Z-automatic_disable.json | 330ad281ea9a117793c054328540852f10abfca1b3d3539b3242a2ff17f4886d |

| Field | Original compared value |
| --- | --- |
| Activation | 10668711138600 |
| Session/map/dataset | 1 / promods-1.59 / d6cc7936fce4e902761abb5d |
| Intent | 3bac2c92f57e4d2d8dc5995c8985a1b4 |
| Revision/build | 8 / 0669f61a648a46869c49a8bd33d701e9 |
| Geometry fingerprint | 5680dbd0940163b73d6305631af6ea59e6d45eca7e1a41b71908d93202c772f1 |
| Rejected ACC frame | 201591936 |
| Observation/computation/check | 10694.3692425 / 10694.3770042 / 10694.3933597 s |
| Expiry / remaining lease | 10694.8692425 s / **475.8828 ms** |
| Observation/decision age | **24.1172 / 16.3555 ms** |
| Envelope/identity | valid=false; identical compared contexts, different_fields=[] |
| Inner cause | ACC target unavailable or unconfirmed departure; driver takeover required |

The intervention was recorded at 10694.3994921 s against a later vehicle frame
201625268. That later vehicle snapshot does not replace the rejected ACC frame.
The generic `acc: invalid longitudinal observation` is a wrapper, not an expiry.

### Three different events

1. At **10691.5968517 s**, ID 28 caused a directed crossing speed constraint:
   distance 43.9036519 m, actor arrival 4.8038089 s, ego constant-speed arrival
   5.5570251 s, heuristic brake .00240568 converted into a positive-speed cap.
   This is the start of this later slowing episode, not a proven box collision.
   An earlier independent ID 66 body-brake stop/restart exists in the same window.
2. At **10693.8197948 s**, a different native object **26**, moving slot 0,
   produced an actual body-prediction request .397004. Subsequent contact times
   2.47967 -> 2.26322 -> 2.09931 -> 2.07017 s accompany requests
   .397004 -> .468123 -> .525877 -> .536493. The write ring confirms throttle
   zero and brake .52587676, then .53649288, followed by safety/release zeros.
3. ACC still depended on original **28**, and rejected its unavailable or
   unconfirmed completion. Another object's brake is not its clearance proof.

### Proven software fault and correction

`selector.select()` mutates `selector.target_id` to the new projected lead.
The original scalar continuity field then describes that new candidate, while
ACC privately owns the old crossing constraint. Capturing `prior_target_id`
fixes one publication, but a second publication before ACC ticks has already
lost that original selector slot. ACC could also overwrite its dependency with
the new lead while another object's body brake was taking control.

Read-only loading of starting-HEAD production methods/classes reproduces **eight
failures** in both automatic modes (single and 2/4/8 independent publications).
This is a real production counterexample, not proof of the omitted historic
ID 28 array or its exact projection/slot transition.

The corrected selector retains at most **16 original native owner chains**.
Each is tied to source, slot, lifecycle and the acquisition generation when that
chain was first observed. This is a local witness origin, **not** a native vehicle
incarnation ID. Consecutive native frames, original times, finite kinematics and
unchanged body count/dimensions qualify continuity. Missing, temporary,
reassigned, regressing or discontinuously moved records break the chain; later
reuse cannot inherit it. Duplicate reads never advance its clock.

All current positive-scope owners are registered, rather than just the nearest
projection. The actual already-validated ACC owner is pinned from the existing
Engine decision, without another IPC/SDK read. Unused witnesses age out after
the existing 500 ms evidence horizon; completed witnesses likewise cannot form
an ever-growing cache. Capacity exhaustion is fail-closed. Repeated unrelated
body brakes cannot release/relabel the original dependency. Crossing completion
still requires its own complete current no-contact witness. Normal closer-lead
handoff is separate: **both** ordinary leads must be currently projected, and
the new owner gets its own native witness. This preserves the existing cut-in
simulation without treating disappearance as clear road.

ACC and the final Engine gate validate the same owner contract. Current urgent
braking is still applied, expired/foreign decisions are never renewed, and no
old drive is revived. Native/legacy capability is explicit: the new witness
schema is published only for a real native acquisition; a legacy receiver
capture is not falsely labelled as a native-generation proof.

An additional independent review reproduced a safety-ordering defect: original
lead 28 disappeared, reappeared, then moved outside the reference over several
new native frames before ACC ticked. Its *new* ordinary geometric departure
could pass even though the acquired owner's continuous chain was already broken.
ACC processed departure before validating that chain and cleared the dependency.
Both mode failures are retained in `reuse-departure-before.log`. The final fix
requires the same original owner-chain check **before release as well as before
continuation**, matching Engine. The geometric departure helper itself is not
disabled; its witness simply cannot authorize the wrong acquired lifetime.
The earlier complete-suite development run was deliberately interrupted after
this new counterexample was found and is not acceptance evidence.

An existing test double compacted native slots when removing an unused lead:
`[lead, crossing] -> [crossing]` moved the acquired object from slot 1 to slot 0.
It now clears the actual ABI slot 0 and preserves slot 1. All original outcome
assertions remain; separate slot-reassignment tests must still reject.

The first completed full run (`full-owner-final.log`) exposed four analogous
older fixture failures in `test_oct14_stop_completion.py`, not an accepted PASS:
**4 failed, 2849 passed, 1592 subtests passed in 670.34 s**. Its positive-motion
test moved a declared 10 m/s actor by 2 m in the first 33 ms, exceeding the
existing native motion coherence bound. The export test additionally reversed
the actual packed native array slots. Their inputs now preserve slots and move
the actor by `speed * dt`; all original recovery/export assertions remain. An
explicit witness-slot/chain assertion was added. Actual reassignment, missing
records and ID reuse still fail closed in separate tests. The focused rerun of
these two files passes **82 tests in 20.29 s**. No runtime guard was relaxed for
these failures. A new full run, `full-owner-native-fixtures.log`, is required.

## 2. What ID 26 geometry establishes

The exact decisive receipt retains ID 26's pose, dimensions, speed, source/slot
and fingerprint, plus measured ego tractor/trailer boxes and anchor. For the
last retained prediction, actor WHL is **2.367208 x 2.553163 x 6.746131 m**,
position **[34875.605469, 9.074113, 45306.859375]**, yaw **3.038126 rad**,
speed **10.287645 m/s**. Ego speed is **.786763 m/s**; its measured tractor yaw
is **-.492786 rad**. These headings are broadly opposing; that is not proof of
an opposing lane or a separate branch. Native observation generation 7713,
frame 242399704, time 10694.1858636, and model source age .0150361 s remain
original. Contact 2.0852092 s from source minus that age gives 2.0701731 s.

The retained model is
`native_boxes_directed_reference_fixed_articulation_constant_actor_motion`.
It follows the directed ego reference, keeps trailer articulation and actor
heading/speed fixed, and expands rotating ego boxes conservatively per segment.
This can be conservative for turning/oncoming traffic. No retained observed
impact establishes that the future model contact actually occurred.

The available boxes were also exhausted in an explicitly separate SAT probe:
holding **both** ego and actor at their measured source headings/speeds predicts
tractor contact at **2.074445 s**, trailer at **2.293512 s**, compared with the
stored directed-model first contact **2.085209 s from source**. The measured
heading difference is **-2.752274 rad** (about -157.69 degrees). Thus a nominal
box-contact prediction can be reproduced from retained poses without inventing
a phantom actor; this is not evidence that its future motion was correct or
that the original directed reference was straight. Consecutive original native
pose changes and this labelled counterfactual are exported by the same read-only
analysis tool in `evidence-with-body-review.json`. No unobserved lane, turn
intention or complete body envelope is supplied to runtime.

**Missing historic inputs:** the complete original actor body array/body count
and the exact directed XYZ future reference/ego prediction samples at that
acquisition are absent. Dense steering rows contain local projections and
identity, not the consumed full future body path; headers are not substituted
for it. Actor 28's rejected original array and the historic DEV acquisition/frame
receipts are also absent. Therefore the exact branch/lane and false-positive
classification are **NOT VERIFIED**. AEB is not weakened or retuned. Current
real-contact and independent-hazard integration tests must keep braking.

## 3. Explanation and DEV HUD

The canonical first reason is unchanged. An additive bounded explanation carries
technical/emergency classification, producer, inner cause, original ACC owner
and decisive brake object. For this reproduction it reads:
`Technical stop [acc] / ACC target 28 (not confirmed clear) / brake object 26: ...`.
Both the log's first intervention and existing automatic incident export retain
it through `release_all`. Target evidence is compacted with the existing codec
inside the original budgets, not dropped to make the new test pass.

Two concrete presentation defects are reproduced separately from historical
visibility: (a) `continuous_service_hold` was excluded from orange attribution
even with an exact object/positive brake-channel receipt; (b) inactive authority
muted the display and there was no retained intervention scene. A normal safety
fallback's emergency flag also must not imply a proved object AEB.

The feed now retains the last **exactly matched** brake scene/receipt. It matches
native acquisition plus full route identity and full object record, not just ID;
geometry arriving after the write is qualified against the same immutable
receipt. On disable it is shown separately as **HISTORY**, with original source
time and dashed old geometry. Current same-ID detections never inherit it.
Orange means an actual successful object service-brake write; red requires an
attributed object emergency source. Technical loss has its own explanation
panel. Missing exact geometry is explicitly unavailable, including when an older
exact history scene is the only retained one. New activation/session/intent
clears old display ownership. Display toggling grants no authority.

Budgets remain **two 192 KiB frames total**, including the retained historical
frame, and **64 KiB total receipts**: 48 KiB current + at most 12 KiB historical
receipt + 4 KiB fault summary. The display uses one bounded publication worker,
10 Hz capture/write sampling, no extra source reads and no per-tick INFO output.
Frames are shared immutable references rather than extra full-scene copies.

## 4. The separate 15:54:24 red stop is not the ID 28 failure

`steering-replay-20261016T135424.528163Z-automatic_disable.json` and dense
`...135424.791758Z-automatic_disable.json` pass integrity inspection.
The 30.012544 s history has 479 rows / 359 unique times, no incompleteness or
capture failures. Activation **10575820227700** differs from the later failure;
session, intent, revision 8 and build are the same.

This history actually contains qualified **head 1, red**, the original signal
lock and derived target. Last reference target distances are 1.3923 -> 1.3464 ->
1.3077 -> 1.2912 m. They are **not** bumper/painted-line measurements; the 5 m
reference offset is unchanged. At .3054 m/s gear becomes 0 with continuous
braking chain 686. At .0016817 m/s the phase is holding. The first rejection is
**`reverse gear observed`**, in ACC frame **129744810**, observation
10622.3175186, checked 10622.3289436; age **11.425 ms**, lease remaining
**488.575 ms**, matching identities. The later Drive boundary confirms **gear -1**.
There is no basis to blame a GPS/refresh expiration or the later ID 28 ownership.

The exact final pre-fault brake writes are .00776223 at 10622.0567758,
.00233587 at 10622.1294291, then .03518075 at 10622.2025966 and
10622.2733117. All returned successfully. The retained interval has **no software
zero brake before the first R rejection**. The release zero at 10622.3538779
follows rejection; it is not its cause. SDK user/effective brake observations
lag these writes and retain small positive values. They do not identify every
game input callback, input mixing/deadzone semantics or the complete manual
input history. The isolated source available for the older standing steering
probe is not proof of the installed controller DLL's exact consumption here.

The session's Engine transmission record and current game log identify the same
active profile, `65726767726D617475736B727532`, with `g_trans=0`. Its on-disk
`controls.sii` has `c_brake_dz=0`, adds `semantical.abackward` after the physical
axis normalization, and maps `backward=dbackward+abackward`. This rules out
claiming a configured nonzero joystick brake deadzone as the established cause.
It still does not reveal the game's internal simple-auto direction threshold,
all physical/digital inputs, or each DLL callback. The read-only audit retains
the configuration's hash/mtime and only these relevant lines, without changing
game settings or substituting them for a recorded callback trace.

**OPEN:** why ETS2 selected R despite the retained positive software chain is
not established. It would be unsafe to remove R rejection or claim the red
cycle repaired on this evidence. The smallest missing proof is the controller
input callback's consumed brake values/input mixing at the first reverse
transition, tied to these original SDK frames; Python write success is not that
acknowledgement. No new drive or DLL installation is requested here. Current
offline red/hold/green regressions remain, but are not a game-semantic proof.

## Verification and package

Final targeted result after the last runtime edit: **341 passed in 47.12 s**
(`reuse-fixed-targeted.log`). The 40 tests in the new owner-handoff file include
both modes, 2/4/8 producer publications per ACC consumption, crossing/lead
ownership under another actual body brake, DEV off/on, missing/slot/teleport/
reuse/stale proofs, a longer pinned-owner sequence, automatic first-fault
export and historical exact geometry. Existing native/AEB/ordinary lead,
full Visualization XYZ/XZ opening, continuous hold, green resumption, export
integrity, safety and release-metadata assertions remain. The two added
reuse/departure tests failed before the final ordering fix and now pass.

The starting-HEAD comparison has eight expected failures. There are no false
technical stops in the corrected valid-owner scenarios, and current real body
hazards still write positive brake with zero throttle. The existing 30 repeated
crossing acquisition/completion cycles in **each** automatic mode produce 60
native acquisitions and 192 backend writes per mode, zero automatic disables
and zero positive pedal overlap. This is an uncalibrated synthetic input sequence,
not 60 real crossings or measured game physics.

The existing 16-case steering and 12-case ordinary longitudinal benchmark
metrics remain numerically equal to the previous verified build. No lateral
controller, PID gain, pedal calibration, stop geometry, 5 m offset, cadence or
timeout is changed here. The new owner scenarios separately exercise code that
the ordinary comfort matrix does not reach.

### Paired operation cost and retained memory

`tools/benchmark_oct16_owner_handoff.py` loads the original selector/display
classes and affected ACC/Engine methods read-only from `5f96e07`; remaining
production validation is shared. It is not a full historical multi-process
runtime reconstruction. Three sequential paired runs use 25 warm-up plus **160
measured actual in-process pipeline ticks per state**. Timings are wall ms of
the test's native acquisition/Policy/ACC/Autopilot/Engine/Controller step, not
live packet cadence or game latency. Test write/mock histories are cleared
outside measured ticks. The final `reuse-fixed-paired.json` binds all runtime
hashes before/after the run.

The table gives the three run-specific p50 / p95 / p99 values and largest single
tick of all three; percentiles are **not** fabricated from summary percentiles.

| Mode/state | p50 across three runs, ms | p95, ms | p99, ms | Largest tick, ms |
| --- | --- | --- | --- | --- |
| 0 baseline DEV off | 7.503 / 7.542 / 7.563 | 7.813 / 7.911 / 7.981 | 8.479 / 8.281 / 8.165 | 8.756 |
| 0 candidate DEV off | 7.489 / 7.509 / 7.571 | 8.004 / 7.779 / 7.959 | 8.402 / 8.676 / 8.103 | 9.187 |
| 0 baseline DEV on | 7.603 / 7.687 / 7.689 | 9.168 / 9.221 / 9.357 | 9.613 / 9.434 / 9.711 | 10.038 |
| 0 candidate DEV on | 7.641 / 7.692 / 7.698 | 9.220 / 9.227 / 9.301 | 9.594 / 10.156 / 9.958 | 10.158 |
| 3 baseline DEV off | 7.051 / 7.061 / 7.076 | 7.513 / 7.422 / 7.385 | 8.121 / 7.817 / 7.778 | 14.205 |
| 3 candidate DEV off | 7.043 / 7.097 / 7.096 | 7.423 / 7.623 / 7.591 | 8.068 / 8.409 / 8.413 | 9.136 |
| 3 baseline DEV on | 7.173 / 7.197 / 7.257 | 9.021 / 8.807 / 8.802 | 9.427 / 9.238 / 9.138 | 10.985 |
| 3 candidate DEV on | 7.220 / 7.240 / 7.215 | 8.735 / 9.027 / 8.811 | 9.684 / 9.253 / 8.997 | 10.791 |

All paired physical-output SHA-256 values and non-presentation source-read counts
match across DEV states and ordinary baseline/candidate scenes. No new SDK or
traffic IPC read. Small nonzero operation cost remains; lower maxima in a later
run do not establish a performance fix. CPU time is quantized at 15.625 ms on
this host. Raw GC spans are separate and may include preparation/warm-up; their
maxima are not attributed to a particular measured control tick or historical
pause. Earlier development runs retain maxima up to 128.309 ms; they are not
erased or claimed fixed by the lower final run.

The dense exported snapshot deep size is **82,888 bytes**. The separate actual
history/fault preview fixture retains **36,309 bytes** of adapter-owned Python
objects (distinct references counted once), two accounted geometry frames of
**32,342 / 32,982 bytes**, and **32,090 accounted receipt bytes** total. These
exclude test histories, PID/selector/journal caches, pending serialized IPC copy,
thread/executor/OS overhead and total process RSS. They are not a total RAM claim.
The maximum allocations remain the original two-frame/64 KiB receipt budgets.
`tools/preview_oct16_intervention_history.py` reproduces this memory audit and
the visually inspected offscreen `history-preview/history-TEST-DATA.png`; its
synthetic scene is explicitly HISTORY/NOT LIVE, not a game screenshot.

The final source-bound full run `full-owner-native-fixtures.log` passes:
**2853 tests and 1592 subtests in 650.33 s (10 min 50 s)**, exit code 0.
Its `.verified.json` records identical before/after SHA-256 values for all 19
runtime payloads and the full log hash. Prior build's 2813-test PASS is not reused. The first
run `full-source-frozen.log` was interrupted at about 25% after the new safety
counterexample was independently found; it is not a PASS. Development failures
and fixes remain in the ignored audit directory; originals are not overwritten.

The intended runtime set reuses the existing **19-file** coherent candidate
manifest. Actual changes are `core/acc_following.py`, `core/engine.py`,
`core/longitudinal.py`, `core/control_timing.py`,
`core/navigation/longitudinal_diagnostics.py`, `core/traffic_dev_hud.py`,
`plugins/acc/main.py`, and `PLUGIN_CHANGELOG.md`. Unchanged dependencies and
required installed base hashes are explicit in that manifest. No DLL/settings,
cache, original evidence or commit marker is replaced. The new preparation tool
requires a successful complete-suite log bound to identical runtime hashes and
rechecks all installed base hashes before preparing the ZIP, never deploying.

`compileall -q` passes for every changed runtime Python file, all three changed
test files and all four new tools. `git diff --check` passes. No additional
whole-suite run is needed for the same unchanged candidate.

The single current proposal is:
`docs/steering-audit/oct16-owner-handoff/oct16-owner-handoff-acc135-candidate.zip`.
SHA-256: `37ede18aa5bdcf3478c0f746bbcc414295319ed5d135803a2c5bb6f3d5fa9008`.
Its sibling `.manifest.json` contains all 19 payload hashes, actual plugin
versions, the unchanged required native version, source HEAD, the explicit
uncommitted-working-tree flag and all 33 required installed base-file hashes.
All payloads were read back and hash-verified. `runtime_authorized=false`,
`game_verified=false`; this is not a deployment receipt. The older ACC 1.3.4
candidate is superseded only as a future proposal; its original evidence and
installed files remain untouched.

| Property | Verdict boundary |
| --- | --- |
| Original owner vs new candidate/other brake | OFFLINE VERIFIED; eight starting-HEAD failures corrected |
| Missing/reused/stale owner | OFFLINE VERIFIED rejection; two extra pre-fix reuse/departure failures corrected; continuity is not clearance |
| DEV hold attribution and historical display | OFFLINE VERIFIED; historic exact missing-frame branch not reconstructable |
| ID 26 true physical conflict/false positive | NOT VERIFIED; safety model retained |
| Red signal hold/green software lifecycle | Existing offline contracts preserved; first observed R remains OPEN |
| Actual input consumption and new game result | GAME NOT VERIFIED |

The whole requested incident is **not closed** merely because the reproduced
ownership defect and HUD behavior pass offline. No deployment, commit, push,
game operation, diagnostic arming or new-drive request is performed.

## Changed source and reproduction tools

- Ownership and validation: `core/acc_following.py`, `core/engine.py`,
  `core/longitudinal.py`, `plugins/acc/main.py`.
- Existing explanation/export/display: `core/control_timing.py`,
  `core/navigation/longitudinal_diagnostics.py`, `core/traffic_dev_hud.py`.
- Regressions: `tests/test_oct16_brake_owner_handoff.py`,
  `tests/test_oct16_joint_traffic_regressions.py`,
  `tests/test_oct14_stop_completion.py` (native fixtures, unchanged recovery
  and integrity expectations).
- Read-only incident analysis, paired cost, offscreen preview and preparation:
  `tools/analyze_oct16_owner_incident.py`,
  `tools/benchmark_oct16_owner_handoff.py`,
  `tools/preview_oct16_intervention_history.py`,
  `tools/prepare_oct16_owner_runtime.py`.
- Documentation: this report, `PLUGIN_CHANGELOG.md`, `DEFERRED_WORK.md`.

The candidate includes every one of the 19 runtime dependencies in its manifest,
not the test/tool/report files. Only ACC's implementation/version changes among
the plugins. An unchanged dependency in the candidate is not a new release of
that plugin. The complete ZIP remains a proposal for separate approval.
