# Native traffic identity and constraint lifecycle — October 16 evening

**OFFLINE VERIFIED for the reproduced contract defects. Historical scene only
partially reconstructed. GAME NOT VERIFIED. No deployment.**

## Source and incident identity

Entry HEAD is `b6066ff` (ACC 1.3.5); the entry working tree was clean. No
repository/ancestor AGENTS.md was present. Plugin versioning and the preceding
ownership/crossing reports were read. All 33 installed receipt hashes match.
The installed Python runtime matched entry HEAD after LF/CRLF normalization;
DLLs are compared to their build receipts, not to a nonexistent Python source
path. The game plugin and packaged asset match the native candidate-c build
SHA-256 `ebe8af192bcd7c0955075d2869882d8c82804e855ba25a6b43fb47d8c7542bdb`.
The new source advances only ACC to 1.3.6 for its changed consumer contract.

Read-only reproduction:

```powershell
python -m tools.analyze_oct16_native_owner_contract --output docs/steering-audit/oct16-native-owner-contract/evidence-current.json
```
This checks existing replay hashes/immutable decoding and installed/native-source
receipts. Originals remain outside Git and unchanged. Derived evidence is ignored.

### First evening owner stop: 19:42:18 local / 17:42:18 UTC

Pedal incident `steering-replay-20261016T174218.227211Z-automatic_disable.json`
and dense `...174218.989155Z...` pass the existing integrity/codec inspection.
The screenshot is historical, not a new native read: generation 9371,
native frame 534631660, source time 24295.751 s, consumed ACC 25 and brake .350.
The later age displayed in that screenshot does not establish stale input at
the intervention.

| Field | Original evidence |
| --- | --- |
| Activation | 24283930823500 |
| Session / map / dataset | 1 / promods-1.59 / d6cc7936fce4e902761abb5d |
| Intent | 9de479c2644b49e09fcd999efe24f4bd |
| Revision / build | 9 / 8a37806749f94dbe926543e49c8b2ffe |
| Geometry | e6a5fec1da303e900a64b5997125b72ef205955e06c21d8ba03b8b824d6da30e |
| Rejected traffic SDK frame | 275788968 |
| Observation / computation / check | 24295.8807521 / 24295.9154258 / 24295.9342054 s |
| Observation / decision age | 53.4533 / 18.7796 ms |
| Remaining lease | 446.5467 ms |
| Envelope / context | valid=true; different_fields=[] |
| First intervention | Engine at 24295.9424645 s, vehicle frame 275838966 |
| First cause | ACC original native owner continuity unavailable |

Do not replace the rejected frame with the later intervention vehicle snapshot.

1. **Slowing:** ID 25's directed crossing ray generated a positive speed cap.
   At history time 24295.3727383, the actual cause retains native acquisition
   generation 9353/frame 534121405/time 24295.2402706, slot **4**, dimensions
   1.945376873 x 1.286008358 x 4.154852867 m, speed 10.168843 m/s. A hypothetical
   intersection was 53.708207 m ahead, actor arrival 5.511110 s, ego arrival
   4.963935 s, heuristic demand .0000812933 and resulting cap 6.961166 m/s.
   This is a model speed restriction, not an observed collision or lane claim.
2. **Acquisition:** ACC actually latched this crossing, not a lead. The immutable
   backend source retains `following_required=true`, `following_kind=crossing`,
   owner ID25/source moving/slot4/lifecycle70812498896944/acquired_generation9353.
   It commanded .350 service brake with zero throttle. At the screenshot's
   generation9371, ID25 is still recorded in slot4 with the same dimensions.
3. **Continuity loss:** generation9376/frame534771546/time24295.8914238 retains
   ID25 in slot **3**, same dimensions, speed10.685472 m/s, XYZ
   [34868.4609375,8.3155345917,45276.45703125], yaw-2.969049422 rad, still with a
   crossing cap5.774527 m/s. The native-source review proves such slot changes
   are ordinary sorting. The deployed guard necessarily rejects this slot
   transition if it compares the same acquired chain. The exact rejected
   full owner-witness list and all intervening actor arrays are not retained;
   an earlier omission/discontinuity cannot be excluded retrospectively.
4. **Full stop:** Engine treated failed ACC owner continuity as technical
   navigation-authority loss and applied its safety stop. It was not a lease
   expiry or a proved ID25 box collision. Recorded reference speed immediately
   after the fault is8.412336 m/s, not standstill at first rejection.

The fresh-source sorting failure is independently reproduced on entry code in
both automatic modes, through native packed capture, Engine selector, Policy,
ACC, Autopilot and actual Controller writes. Historical cause and production
counterexample are deliberately distinguished.

### Other failures in the same session are separate

- 19:44:56: `ACC moving constraint unavailable before write`. A positive
  protective-route forecast for ID53 (cap25.568820 m/s) appears while vehicle
  speed is5.900310 m/s; ACC has acquired no target. The final guard nevertheless
  required every auxiliary scope ID. Its exact concurrent missing packet is
  not retained, but that same ineffective-scope transition is reproduced.
- 19:45:15 and 19:45:24: actual model AEB/body requests concern ID40, with
  predicted contacts about1.448 and1.135 s. These are not silently reclassified
  as sorting failures. Their collision geometry/intent is not fully retained.
- 19:45:33: another owner-continuity rejection, with a fresh matching context.
- 19:45:36: explicit `STOP_HOLD_UNAVAILABLE` after reactivation at standstill;
  do not invent forward-started service-brake authority or a parking-brake act.
- 19:45:41: acquired owner69, projected candidate52 and decisive brake69 are
  explicitly different roles in the retained fault. Observation age19.8686 ms,
  remaining lease480.1314 ms, identical context; exact missing native chain
  input is again absent. It is not an observation-age failure.

## What the installed native producer actually guarantees

Pinned source is `docs/steering-audit/oct14-completion/native-candidate-c/`,
from source commit1f16156b9b37b70cf182c2bc09120fa1b234e129 plus the recorded
sidecar changes. `build-receipt.json` binds source hashes and the identical
installed binary. Relevant exact files are `src/processing/traffic.cpp`,
`traffic.hpp`, `src/core.cpp` and `src/up_traffic.hpp`.

- `get_uid_for_vehicle` maps a native **pointer** to a signed short, allocated
  from map size. The map persists while TrafficProcessor exists; `clear_data`
  clears per-acquisition vectors, not this pointer map. There is no exposed
  actor incarnation/destruction certificate. Pointer reuse/short exhaustion
  cannot be proved safe by Python merely seeing the same number.
- `write_active_traffic_data` combines game-spawned/player/TMP records, sorts
  by distance to the truck, writes at most **40** records into a zero-filled
  array. Removal/insertion/distance-order changes compact/reorder slots.
  `write_parked_vehicle_data` independently sorts/truncates40 parked records.
  Slot is the current array position, not a vehicle identifier.
- Game lists and classification determine inclusion; missing physics and
  capacity can omit objects. Moving/parked changes share a pointer-map ID but
  do not supply a trustworthy measured transition velocity. No declared range,
  complete coverage or traffic-lane membership exists. The top40 boundary is
  not a sensor-range certificate. Equal-distance tie order is not stable.
- The timed sidecar copies the same acquisition's moving/parked arrays plus
  available ego bodies/anchor/speed. Lifecycle/generation/source-frame/host
  monotonic observation time travel together under the seqlock. A read time
  never replaces the source timestamp. TMP speed/acceleration placeholders
  remain unusable for this motion qualification. No DLL/ABI change is needed
  to correct the consumer's false stable-slot requirement.

The preceding report's assertion that native slots do not compact was wrong.
Its preserved-slot fixtures covered one possible buffer shape, not the actual
producer guarantee. New tests restore permutation/compaction and separately
test truly ambiguous/reused/changed-shape records. Old reports/evidence are not
rewritten to conceal this correction.

## Authority and lifecycle contract

| Type | Acquisition / owner / validity | End / unavailable behavior |
| --- | --- | --- |
| Observed detection | Current immutable native record; no pedal authority | Disappearance is not clearance; no acquired lead merely from display |
| Ineffective auxiliary cap | Current route-projected positive forecast above the effective plan; no acquired ACC owner | Changing at write discards positive drive for that tick; next fresh decision, no permanent navigation fault |
| Effective positive lead/protective cap | Existing ACC binds actual limiting owner and acquisition; same route/activation and original <=500ms source leases | Current stricter requests always apply; own observed departure required to release an acquired owner; disappearance/ambiguity remains fail-closed |
| Effective crossing cap | Actual positive crossing urgency converted to a positive-speed cap; own bounded origin, not a confirmed lead/lane | Own fresh model completion, not another body's brake; incomplete/missing evidence cannot authorize drive |
| Body conflict | Current measured boxes plus existing directed constant-motion model; each decisive/source owner remains separate | Complete current no-contact/receding-body evidence of ORIGINAL chain, not any newly continuous pair |
| Full stop / continuous hold | Actual forward-started uninterrupted positive backend brake; explicit consumed stop reason/owner, not every slowdown | Same qualified signal green or original traffic clearance; all other causes must end; missing data cannot release hold |
| Completion witness | Exact original owner generation/lifecycle/authority, current native time/frame and model predicates | Fixed lease, never renewed by polling; cannot apply to reused ID/new acquisition |

### Implemented correction

One selector-owned bounded pair validator now qualifies native continuity using
unique decoded ID, source class, lifecycle, source generation/frame/time,
unchanged body count/dimensions and the existing speed/displacement bounds.
Dimensions must be present, finite and positive for every body; two unknown
zero-size bodies cannot certify continuity just because their IDs agree.
The current slot is recorded but is not compared as identity. The existing
height gate rejects discontinuous vertical movement. The same check is reused
for acceleration anticipation, ordinary departure, crossing completion and
terminal body clearance. This is a qualified local witness, **not** a native
lifetime guarantee or proof of a free lane.

At most16 acquired owners remain. A complete but ambiguous acquisition breaks
their chain even if a slower ACC consumer only sees the next good publication.
A missing acquired owner stays broken on reappearance. Terminal body owners
are captured before applying a stop and pinned through the same hold identity;
`owner_generation` binds clearance to that original receipt. Two recent good
poses after disappearance may not clear the old stop. All owners of a combined
terminal conflict must qualify; ending one cannot clear the rest.

The final positive-write guard no longer promotes every passive forecast ID
into `moving_target_ids`. Acquired owners remain mandatory. Auxiliary IDs are
tracked separately as `observed_motion_ids`; a concurrent disappearance/change
discards old positive drive and awaits a newly calculated tick, retaining the
original lease and any brake. Stale/foreign inputs still reject. A current
emergency floor bypasses this zero-drive transition, and the actual Controller
receives the new brake as well as throttle zero at that same boundary. Emergency
cause is recorded in the existing first-intervention/export path.

DEV evidence now explicitly separates geometric candidate, consumed constraint
owner/type, decisive brake actor and specific continuity reason. Reasons include
missing, identity ambiguous/shape changed, source-class or lifecycle change,
invalid/discontinuous motion and stale/regressing source. The original slot and
current slot remain diagnostic facts. Technical stop stays distinct from AEB;
exact immutable history attribution is unchanged. No new SDK/IPC reads, collector,
disk I/O on the tick, memory budget, controller, geometry, 5m offset, freshness
limit, indicator behavior or native DLL change.

The historical card describes its exact saved successful write. Its continuity
line can therefore say `qualified` while the separate first-fault banner reports
a subsequent missing/ambiguous acquisition. The old receipt is not rewritten
with newer fault inputs or newly observed same-ID geometry. Unavailable fields
in an older receipt stay explicitly unknown.

## Geometry and limits of historical reconstruction

The first fault's exact steering calculation sequence5473 localizes to road UID
5337536093204383133, direction-1/lane0, progress639.634562m, projected XZ
[34859.18423983543,45366.03426757083], local tangent-.425173427 rad and
curvature.00000384594/m. It is a road segment with no prefab token at that
calculation, not proof of an instantaneous prefab switch. Its observation time
is24295.8807521/frame275788968; the immutable calculation identity matches
the incident, without using an unrelated newer header as pedal provenance.

ID25's recorded yaw at the last cause is-2.969049422 rad, broadly opposing the
local ego direction. The original directed crossing prediction was much farther
ahead on the curved reference. It may model a future turn incorrectly; neither
that heading nor the user's unobstructed view certifies a separate lane. Exact
full future directed XYZ reference and all actor bodies/arrays at every failed
native acquisition are not in these exports. The source array comes from a
capacity-limited sorted feed. Therefore the exact historical missing-vs-sorting
branch and truth of every forecast are not asserted as completely reconstructed.
The real route identity/localization, retained intersection point, measured
poses and model nature are preserved; no fictitious future vehicle path or
nearby-road dismissal is introduced. Existing curved/oncoming/elevation and
real-contact regressions remain necessary. AEB is not weakened to hide stops.

## Reproduction / verification

On entry ACC1.3.5, the first new native-format integration run yields **6 failed,
2 passed**: both lead/crossing sorted-owner cases and passive-scope write
dependency in both automatic modes. Additional counterexamples independently
failed before their fixes: complete ambiguous acquisition skipped between ACC
ticks (2 failures), and a reappearing body clearing its original terminal stop
(2 failures). The auxiliary emergency-at-write counterexample exposed a local
Engine variable still using the prior brake; it now consumes the fully selected
pedal pair and records the emergency. These are offline production-flow tests,
not a scripted claim of success in ETS2.

| Reproduced boundary | Before | After / required behavior |
| --- | --- | --- |
| Distance sort moves original lead/crossing slot | False loss of acquired authority | Qualified original owner continues; no technical stop in the valid fixture |
| Ineffective auxiliary forecast changes before positive write | Full navigation fault although ACC acquired no owner | Old positive drive discarded; next fresh decision required; authority retained |
| Complete ambiguous acquisition between slower ACC ticks | Next good list could skip the causal invalidity | Original owner remains invalid, with its first reason |
| Body disappears and later provides two new good poses | Fresh pair could clear the old terminal stop | Original acquisition chain required; no clearance after the gap |
| New emergency discovered at auxiliary write boundary | Prior local brake value could still be dispatched | Same-boundary throttle 0 / brake 1 reaches Controller, emergency recorded |
| Same ID with unchanged unknown dimensions | Incorrectly qualified | Missing/nonpositive shape cannot certify continuity |
| Successful write transitions into historical HUD | Five new fields were dropped | All five equal the original write's fields, including explicit nulls |

These are native-format in-process backend counterexamples, not proof that the
incomplete historical body forecast was a real collision or a false alarm.

Some older clearance fixtures teleported 23 m / 16 m in one 33 ms native frame and
accepted a later pair. They now advance at their declared speed through every
source acquisition; original stop/hold/restart outcome assertions remain.
Permutation fixtures are restored, with explicit unchanged original owner and
changed current-slot assertions. Duplicate-ID, gap/reuse, motion and lifecycle
negatives remain. No safety assertion is removed to obtain PASS.

The final frozen full suite passes **2881 tests and 1592 subtests in 945.27 s
(15 min 45 s)**, exit code 0 (`full-release-final.log`). Its `.verified.json`
binds the log SHA-256, entry HEAD and all 21 runtime/dependency file hashes;
before/after runtime hashes agree. This PASS applies to this dirty-tree
candidate, not merely to the earlier ACC1.3.5 build. `compileall` and
`git diff --check` also pass. The two interrupted development runs are not
included as successful verification.

### Targeted and numerical verification

Before the final unknown-shape qualification correction, the affected producer/
selector/Policy/ACC/Autopilot/Engine/Controller, signal/hold/restart and export
suites pass **301 tests in 78.51 s** (`targeted-complete.log`). The new contract
file, extended with the asynchronous-export/cadence scenes, passes **26 tests in 7.81 s**
(`contract-with-export.log`). Both modes and DEV off/on are exercised. In each
sorted-owner reproduction, the prior false technical stop becomes zero and the
original acquired target is retained; no positive pedal overlap occurs. Missing,
ambiguous/reused records and the original-chain clearance failures remain
protected. The stress scene has 80 packed acquisitions, ACC consumption every
four producer publications, .4 ms modelled IPC waits every 17 reads, and four
existing asynchronous immutable exports per mode/DEV combination. It is a
deterministic in-process scheduling model, not measured OS IPC performance.

A final negative case with unknown/zero body dimensions initially failed in
both automatic modes (`unknown-shape-before.log`): the original correction
wrongly called equal unknown shapes qualified. The shared validator now rejects
them as `identity_shape_unavailable`. After this last runtime change, **282 tests
pass in 90.19 s** (`targeted-shape-final.log`), including all 28 tests in the new
contract file and the existing ACC, completion, ownership, HUD and joint suites.
The earlier full run was explicitly interrupted before changing runtime and is
retained as `full-interrupted-before-shape-fix.log`, not reported as a PASS.

Final presentation-path review found one additional concrete omission: the
live receipt contained the new candidate/owner/brake/continuity fields, but its
historical compact whitelist dropped them. The existing release/history test,
strengthened to check every field against its original immutable write,
failed in both modes (`history-fields-before.log`). Those five compact fields
now survive history capture within the unchanged budget. **121 final targeted
tests pass in 35.26 s** (`targeted-release-final.log`), including the native
contract, ownership/HUD, real-evidence, longitudinal-evidence and pedal-history
suites. The second interrupted full run (`full-shape-final.log`) is also not
acceptance evidence. Runtime remained frozen during final full verification.

The final 16 ordinary steering cases are numerically identical to the previous
verified build, as are all 12 closed-loop ordinary longitudinal comfort cases.
These numerical runs preceded the final presentation-history-only correction;
no steering/PID/model/gain code changed afterward. The final complete suite and
paired pipeline benchmark cover the packaged runtime.
`steering-final.json` additionally contains 198 independent plant/calibration
matrix cases; the older stored comparison did not run that matrix, so no paired
198-case equality or new game claim is made. These are explicit models.

### Paired operation cost (not live packet cadence)

The command below loads starting-HEAD selector/display
classes and affected ACC/Engine methods read-only; remaining production guards
are shared:

```powershell
$env:PYTHONCASEOK='1'
python -m tools.benchmark_oct16_owner_handoff --baseline b6066ff --ticks 160 --repeat 3 --output docs/steering-audit/oct16-native-owner-contract/paired-release-final.json
```

Each state has 25 warm-up and 160 measured actual in-process pipeline
ticks per repeat, three repeats, both modes and DEV off/on. Control outputs'
SHA-256 and non-presentation source-read counts match across baseline/candidate
and DEV states. This measures native capture/selection/arbitration/backend
operations; it is not a complete historical multi-process runtime reconstruction.

| Mode / DEV | Version | p50 in the three runs, ms | p95, ms | p99, ms | Largest tick, ms |
| --- | --- | --- | --- | --- | --- |
| 0 / off | baseline | 9.948 / 10.791 / 10.456 | 13.107 / 14.349 / 12.412 | 14.680 / 15.872 / 14.435 | 16.003 |
| 0 / off | candidate | 9.031 / 9.470 / 11.216 | 10.767 / 11.154 / 13.820 | 11.861 / 11.661 / 15.296 | 15.514 |
| 0 / on | baseline | 9.779 / 10.946 / 11.319 | 12.317 / 13.821 / 15.037 | 13.648 / 15.192 / 15.748 | 16.458 |
| 0 / on | candidate | 10.330 / 9.990 / 10.724 | 14.166 / 12.100 / 13.948 | 16.010 / 14.653 / 14.528 | 18.330 |
| 3 / off | baseline | 8.603 / 11.760 / 10.542 | 10.088 / 13.851 / 14.633 | 10.878 / 14.785 / 18.859 | 19.282 |
| 3 / off | candidate | 8.212 / 9.033 / 8.775 | 9.000 / 10.382 / 10.160 | 9.923 / 11.426 / 11.763 | 12.708 |
| 3 / on | baseline | 9.032 / 10.211 / 9.483 | 11.318 / 13.395 / 12.015 | 12.669 / 15.053 / 12.412 | 16.855 |
| 3 / on | candidate | 8.410 / 13.267 / 9.747 | 10.510 / 18.256 / 12.957 | 11.018 / 20.169 / 15.579 | 20.515 |

There is no invented performance PASS threshold. In this final run, candidate
DEV-on maxima are worse (mode0: 16.458 to 18.330 ms; mode3: 16.855 to 20.515 ms),
while DEV-off maxima improve. CPU-time distributions are quantized at 15.625 ms
on this host. GC spans are separate and include preparation/warm-up. The prior
post-shape/pre-history run (`paired-shape-final.json`) recorded an unexplained
45.825 ms candidate mode0/on maximum, versus 26.010 ms baseline; its largest
GC span was .956 ms. That outlier is retained and not explained away by this
faster run. No proven recurring producer/IPC stall or general latency improvement
is inferred from the distributions.
The retained ordinary output hashes and fixed bounds do not prove worst-case
scheduling. The earlier development paired run overlapped targeted tests and
is retained separately as `paired.json`; `paired-final.json` predates the final
unknown-shape correction, and `paired-shape-final.json` predates the compact
history fix. None is substituted for the final measured run.

The dense snapshot in the final paired benchmark has **83,310 deep bytes**,
counting distinct owned objects once. Test/mock histories, worker/OS overhead,
selector/PID/journal caches and process RSS are excluded. The retained limits
remain 16 owner records, two 192 KiB geometry frames total and 64 KiB total receipts,
one presentation worker and one in-flight existing export. No queue or source
read was added. The source-bound before/after benchmark hashes are retained.

The separate actual dense fixture audit (`held-memory-final.json`) counts both
retained frames and the latest/historical receipt by distinct owned object:
**127,519 to 127,917 bytes (+398 bytes)**. Snapshot-only size is 82,912 to
83,310 bytes. These are not process RSS or a complete application memory claim;
test histories, controller caches and OS/thread overhead are excluded.

The existing real Manager transport probe (`render-ipc-final.json`) uses a
configured 50 Hz telemetry/flag probe, nominal 60 Hz display reader and bounded
10 Hz publication, not real SDK/actuator timing. With DEV off/on respectively,
150 probe samples give p50 **.318/.343 ms**, p95 **.427/.475 ms**, p99
**.529/1.065 ms**, max **.533/1.128 ms**. The 102 actual display reads have p50
.745 ms, p95 .883 ms, p99 1.233 ms, max 1.345 ms. Both modes report zero skipped
publications and no unbounded queue; pickle payload is 17,057 bytes. Requested
reader cadence is not claimed as achieved sample cadence.

The same offscreen classic 3-D renderer shows 43 admitted records with explicit
37 omitted labels/actors; TEST DATA and unverified command attribution remain
visible. At 100 measured renders per state, DEV off/on p50 is 13.697/25.686 ms,
p95 15.828/31.215 ms and max 17.335/32.682 ms. This is UI paint cost, not an
Engine tick or proof of 60 FPS. The optional developer overlay has a real visual
cost. The generated current scene and the retained-history card were inspected;
the three new lines fit without clipping.

## Remaining boundary

GAME NOT VERIFIED. In particular, an actual capacity loss of a required lead
still requires safe intervention; this limited source cannot certify the actor
departed. Native pointer reuse with indistinguishable shape and plausible motion
cannot be ruled out as an incarnation guarantee. This correction fixes false
stable-slot assumptions and auxiliary-authority promotion; it does not create
complete traffic coverage or prove every body forecast. No new drive is requested.
The previous red-signal reverse-input-consumption investigation remains open and
is not silently marked repaired by passing native-slot tests.

## Changed files and candidate boundary

Runtime changes are limited to `core/acc_following.py`, `core/engine.py`,
`core/longitudinal.py`, `core/traffic_dev_hud.py` and `plugins/acc/main.py`.
Only ACC advances (1.3.5 to 1.3.6); DrivePolicy remains 1.1.4, Autopilot 1.3.4,
Map 1.1.2 and the native DLL 1.59.4-up-traffic-timed. `PLUGIN_CHANGELOG.md` and
`DEFERRED_WORK.md` record this scope and remaining limitations.

The new `tests/test_oct16_native_owner_contract.py` and the five affected older
completion/ownership/HUD test files cover the corrected native contract. Tools:
`analyze_oct16_native_owner_contract.py` (read-only incident extraction),
`benchmark_oct16_owner_handoff.py` (explicit baseline parameter), and
`prepare_oct16_native_owner_runtime.py` (hash-bound full verification/candidate).

The preparation tool freezes 21 files, including the unchanged physical-write
and immutable-export boundaries (`core/controller.py`, `core/steering_replay.py`).
Both additionally match the installation after LF/CRLF normalization. The
candidate includes those dependencies and the existing coherent runtime set;
tests, reports, raw recordings, caches/settings and DLLs are not payloads.
It verifies every payload hash on ZIP read-back and all 33 original deployment
receipt hashes before packaging, records dirty-tree status truthfully and grants
no runtime authority. Earlier ACC1.3.5 candidates are superseded as proposals
only; original evidence and the installation are unchanged.

Prepared candidate (not installed):
`docs/steering-audit/oct16-native-owner-contract/oct16-native-owner-acc136-candidate.zip`

SHA-256: `a2e425e2ea303d5377076c8215524d2b52af4d8ae4b747f836e12e5a22461671`.
The adjacent `.manifest.json` contains all 21 payload hashes, exact plugin
versions, original base receipt/files and the successful frozen verification.
Only five runtime implementations plus the changelog differ from the installed
base after LF/CRLF normalization; the other payloads are coherent dependencies.
Every ZIP payload was read back and hashed, and the archive hash was independently
checked with `Get-FileHash`. `runtime_authorized=false`, `game_verified=false`.
