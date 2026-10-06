# Phase 7 — directed prefab traffic-light binding and derived stop targets

Date: 2026-10-06. Input commit: `0aed9a0` (clean tracked tree).
Prior ACC, curve-preview, continuous service-brake and green-resume fixes are
preserved. No `AGENTS.md` was found at the checkout/ancestor locations; plugin
version rules and the preceding signal/lifecycle reports were read.

**Verdict: supported directed light binding and stop/wait/resume implemented
and verified offline. ETS2 effect NOT VERIFIED. Painted-line stopping is not
guaranteed. A physically insufficient approach remains a measured failure.**

## Reference and license

The pinned [Python ETS2LA ACC reference](https://github.com/ETS2LA/ETS2LA/blob/52f068dadfba84c6e10287add329dfe25ac40c69/Plugins/AdaptiveCruiseControl/main.py)
was read at `52f068dadfba84c6e10287add329dfe25ac40c69`, specifically
`get_next_prefab_traffic_light`, `get_traffic_light_from_prefab` and
`calculate_traffic_light_constraint`. It uses authored curve IDs, a placed
prefab scope check and a route endpoint. Its closest-endpoint choice and fixed
5 m deduction are not imported. [The pinned license](https://github.com/ETS2LA/ETS2LA/blob/52f068dadfba84c6e10287add329dfe25ac40c69/LICENSE)
is GPLv3. No upstream implementation is copied or imported into runtime code;
the new implementation uses UltraPilot's existing parser and control contracts.
The read-only reference SHA-256 is
`b6052b95adf2f98813ce6df6e63a2fcbfc3db83b3f5e51520ca7b95f49166ba3`.
Browser retrieval failed; the exact raw file and license were successfully read
through the approved read-only HTTP fallback.

## Actual data and identity

The existing ProMods 1.59 export has 4,838 prefab descriptions, 74,366 navigation
curves and 6,831 nonnegative `semaphoreId` entries. The original RoadNetwork
parser discarded this field. It now preserves the authored integer, preserving
the distinction between `-1` (no control) and `None` (missing/invalid metadata).
Cache version advances from 13 to 14 so old caches cannot silently omit it.

The existing pinned producer source at commit
`1f16156b9b37b70cf182c2bc09120fa1b234e129`,
`src/processing/traffic.cpp::get_traffic_objects_data/write_semaphore_data`,
iterates each nearby prefab segment's `semaphore_instances` and publishes its
instance ID. IDs therefore must be scoped to a placed prefab, not treated as
globally unique actor IDs. The sidecar already supplies original acquisition
time, render frame, generation and lifecycle; no DLL/schema change is needed.
The traffic command now inherits `observed_at + 500 ms` from that original
signal acquisition as a named `traffic_signal` deadline dependency. A fresh
truck snapshot cannot renew an old green. Deadline provenance explicitly marks
the signal render observation, separately from the outer truck SDK frame.
The decoder now permits identical IDs at distinct placements, but rejects exact
duplicate ID/placement rows. Pause/reset/torn/incomplete/stale checks remain.

Read-only reconstruction used the two October 5 replays identified in
[the preceding report](PHASE7_TRAFFIC_APPROACH_AND_SIGNAL_20261005.md) and the
same installed `map-cache/promods-1.59` JSON files. Session `1`, map
`promods-1.59`, dataset `d6cc7936fce4e902761abb5d`, intent
`0198eda713eb42e38a96f1537190396d`, revision `10`, build
`8f7d6fb339ad4d02a575fdea2ed1edd3` identify the recorded route.

| Recorded placed LaneId | Selected directed chain | Authored control | Directed entry world XYZ, metres |
| --- | --- | --- | --- |
| `dlc_blkw_80`, UID `5337536179686741705` | `[23,19,31,15,5,6]` | curve 23, ID 0 | `(34653.2401, 6.9023, 45907.1628)` |
| `dlc_blkw_80`, UID `5337536179342808338` | `[30,4,13,24]` | curve 30, ID 1 | `(34753.4735, 6.9023, 45663.9580)` |
| `dlc_blkw_57`, UID `5337536214763748492` | `[11,7,4,17]` | curve 11, ID 1 | `(34841.0606, 7.4453, 45406.0630)` |

The actual parser, descriptor ordering, reciprocal topology and existing world
transform/elevation code reconstructed these three placed chains. Their raw
world points equal the previously audited cached points exactly. This is a
standalone reconstitution of recorded prefab LaneIds, **not** the missing full
historical LanePath or a reconstruction of the old pedal response. Historical
live head IDs/colours and immutable pedal bindings are absent from those replays;
which head actually controlled the old red stop is not retrospectively proven.

No verified painted stop line was found in the consumed dataset contract. Map
points/display polygons and signal-head placement are not re-labelled as lines.
The exported semaphore-locator table is not used as an assumed physical line.

## Binding contract and incomplete data

`prepare_signal_passages` runs during validated LanePath construction, before
the existing fresh-SDK steering calculation. It uses the exact LaneSegment's
connector path and placed instance. It never chooses a nearer opposite endpoint.
Even when an ID occurs on an inner curve, the stop entry is the **first authored
curve of that complete selected directed passage**, not the inner curve start.

Each bounded record carries a qualified passage hash, prefab token, ordered
instance node UIDs, selected curve indices, controlling curve/ID, entry XYZ,
heading, horizontal route progress and placement scope. The same immutable
LanePath publication binds session/map/dataset/intent/revision/build/geometry;
Engine rechecks publication and context after reading/capture. Live selection
also requires current LaneId and fresh identified steering/SDK observations.

Selection uses the nearest regulated passage ahead by route progress, then its
authored ID. Live ID matching is additionally limited to the placed descriptor
node/selected-path scope plus 10 m, height within 1.5 m, approach orientation
within 45 degrees and head proximity within 40 m of entry. These are association
gates, **not physical road boundaries or universal signal-rule proof**. Multiple
matching placements or multiple distinct control groups at the same entry are
ambiguous; arbitrary nearest-green selection is refused. Repeated curves of the
same control group are deduplicated. A locked head retains its original placement
and passage hash; another closer head or adjacent prefab cannot replace it.

Missing authored ID with a known descriptor entrance produces an explicit
unknown-control stop target. It cannot be replaced by an unconfirmed geometric
green. Missing/stale/ambiguous live data likewise retains a derived approach
constraint with `head_observed=false`, `color=unknown`, `valid=false` for signal
clearance. These are map-derived stop requests, not new traffic observations.
`-1` remains explicitly uncontrolled. If a usable transform itself is missing,
the reason remains explicit and the existing lower-confidence geometric path is
not promoted to prefab confirmation. Prepared records are capped at 128.

Dedicated `/tollgate/` assets are delegated to the existing toll flow: their
semaphore IDs can represent SDK kind-2 barriers, not lights. This work does not
reinterpret gate-open states as green or replace toll/payment control. Other
unrecognized control types remain unsupported; no new gate system is added.

## Stop reference, planning and continuous braking

The runtime profile does not certify the complete tractor front extent. SDK
axle/hitch/camera/reference geometry is not a bumper measurement. The fallback
is explicitly `conservative_unmeasured_allowance`: **6 m front allowance plus
2 m junction stand-off**, deducted once:

`distance = directed_entry_progress - current_SDK_progress - 6 m - 2 m`.

Six metres is a planning allowance for unknown ordinary tractor-reference/body
placement, not a measured length or a guaranteed bound for arbitrary mods. The
model uses a 4 m front extent; a 6 m extent reduces the reported clearance by
2 m and remains ahead of entry in the adequate-distance cases. Larger bodies,
unknown SDK-reference semantics and grade hold are not certified. No false
precision or fixed upstream 5 m second deduction is introduced.

DrivePolicy consumes the derived target in the existing speed planner:
`v_cap = sqrt(2 * 1 m/s² * max(distance - speed * 1.5 s, 0))`.
The 1 m/s² approach and 1 s vehicle-response allowance reuse existing planning
assumptions; another 0.5 s reserves the unchanged maximum evidence/transfer age.
This is conservative planning, not measured ETS2 brake calibration. The existing
traffic request receives distance/deceleration feed-forward, normalized using
the existing yellow-light 4 m/s² nominal full-brake assumption. Common pedal
arbitration and Autopilot's comfort ramp still execute the result; no second PID,
steering filter or controller is introduced. Emergency/closer-vehicle demands
retain their priorities. Lower map/curve limits cannot be raised by this target.

The previous hold floor could ratchet a braking pedal upward throughout moving
approach. Only a **new positive**, same-passage, same-authority/lifecycle,
fresh planned request may now lower that pedal while speed exceeds 0.05 m/s.
It cannot produce a zero edge. Stationary, missing/unknown data or other safety
conditions retain the acknowledged positive hold. No parking-brake writes occur.

Green clearance preserves the existing two new acquisitions >=100 ms apart,
original timestamps, locked placement/ID/passage and all-other-stop-reasons
checks. Brake release precedes the existing bounded launch. R/backward motion,
stale data, backend loss and true authority changes retain safe rejection.
If the SDK reference actually passed the directed junction entry before stopping,
the overrun is latched and automatic green restart is refused with a driver
takeover reason. This is not permission to drive through an overshot entry.

Activation already at rest on red still has the previously documented standalone
holding limitation. This task does not create a new stationary positive brake
edge or claim to solve it. Neutral-start scenarios begin with green, encounter
red during forward movement, wait, then resume without a second N.

## Paired model results

Same geometry and plant for the legacy head-position path and the candidate.
100 m initial approach; straight, turning and reverse-authored passages;
20/35/50 km/h. Variable ticks 33/50/80 ms, 30 ms separately modelled IPC/
consumer work per tick, 120 ms output transport and 350 ms actuator response.
Along-path plant: `(2.2*throttle - 4*brake)/1.4 - 0.12 - 0.004*speed²`.
Synthetic path pose is exact; this is not a lateral or calibrated ETS2 model.
Real parser/LanePath/selector/reader, Policy, ACC, Autopilot, Engine, Controller
and float32 SCS mapping writes are exercised. The actual Map build/publication
path is also verified by a separate time-consistent SDK-stream integration test.

Criteria established by the first tests: correct directed ID/entry, model front
at least the 2 m stand-off before entry when stopping is feasible, continuous
positive physical brake from forward stopping through red wait, zero waiting
throttle, no simultaneous positive pedals, no parking writes, fresh same-head
green restart without N, and continued rejection of unproven clearance.
There is no newly invented numeric jerk PASS threshold.

| Approach | Model front gap to directed entry: legacy / candidate | Brake starts before entry: legacy / candidate | Maximum deceleration: legacy / candidate | Maximum absolute model jerk: legacy / candidate |
| --- | --- | --- | --- | --- |
| 20 km/h, 100 m | 18.57–38.56 / **5.44 m** | 43.94–63.42 / 31.72 m | 1.37–1.38 / 0.97 m/s² | 15.60–16.89 / 6.64 m/s³ |
| 35 km/h, 100 m | 2.39–21.86 / **5.58 m** | 43.98–63.37 / 67.77 m | 2.30–2.31 / 1.15 m/s² | 28.98–48.90 / 4.24 m/s³ |
| 50 km/h, 100 m | -13.47–7.59 / **5.64 m** | 43.47–63.56 / 99.31 m | 2.98–2.99 / 1.63 m/s² | 23.54–50.60 / 2.58 m/s³ |

Legacy turning-head placement differs from the straight-head placement; both
use the same controlled entry. Negative gap means the model front crossed it.
Candidate SDK reference stops 1.44–1.64 m before its derived target. Every
adequate-distance case resumes without N with active authority, zero concurrent
positive pedals, zero parking writes and zero red-wait brake gaps. At 20 km/h the
old flow brakes unnecessarily early; the new distance profile is intentionally
later but reaches the target safely and with less deceleration.

Both automatic modes also complete neutral start (no manual throttle), forward
approach, waiting and resume. The real-auto model only acknowledges an actually
written D selector in a later SDK frame; it does not confirm D from write return.
The simple-auto model uses throttle selection. Neither models proves DLL/game
consumption or manual-pedal/SDK equivalence.

Short 30 m approaches in both modes: 20/35 km/h stop with model front gaps
**5.43/5.44 m**, then resume. At 50 km/h, even the demanded full braking under
the declared load/delay model overshoots: front gap **-9.94 m**. This stopping
property is **FAIL in that model**, not disguised as PASS. The resulting entry
overrun blocks subsequent green restart; drive stays zero. No friction or
available distance is invented to make this case pass.

Acceleration is interval-average `(speed_n-speed_previous)/dt`; jerk is the
change of these averages divided by the following dt. Standstill clipping and
uncalibrated drag/load limit physical interpretation, especially at low speed.
The values are model outputs, not measurements of ETS2 acceleration/jerk.

## Runtime cost and regression evidence

Real placed-passage preparation was 0.161–0.203 ms per reconstructed chain;
the offline raw prefab-parser load was 1,916 ms. Geometry preparation is outside
the fresh-steering path, cached in the immutable LanePath publication. Only the
selected path/nodes define scope; unrelated sibling curves are not resampled
and cannot evict steering's bounded geometry cache. A 300-iteration, 40-head
decode plus cached selection benchmark measured median/p95/max
**0.129/0.192/0.316 ms**. This is operation cost, not full live packet cadence.

All 16 steering benchmark case dictionaries equal `0aed9a0` exactly. Eight
existing tagged roundabout approach cases are also numerically unchanged.
Neither steering calibration, geometry, cadence nor the 500 ms limit changed.

- Four initial new tests fail on the original parser/selector/planner contract.
- Inner-curve reproduction initially used s=130 m; correction uses the whole
  directed entrance at s=100 m.
- Missing-ID reproduction initially admitted geometric green; the correction
  retains an explicit unknown-control target and refuses clearance.
- Dedicated tollgate reproduction prevents a barrier from becoming a required
  traffic light.
- Signal-lease reproduction initially wrote positive drive at signal age
  501 ms despite a 201 ms truck observation; the corrected command refuses it
  at the physical boundary and retains the original signal deadline provenance.
- Broad targeted verification: **244 passed, 4 subtests passed**. Later affected
  missing-metadata/Map checks: **88 passed, 4 subtests passed**. These overlap.
- Final affected selection after the missing-ID/tollgate safeguards:
  **135 passed, 4 subtests passed**. This includes the real Map publication test
  and the qualified-target combined export; counts above are not added together.
- Original-signal deadline check plus waiting/lifecycle selection: **58 passed**.
  The wider lease/arbitration/export run had **114 passed** and one export
  assertion caused by a captured `PermissionError(13, 'Access is denied')`.
  That exact export passed unchanged in a new short system temporary directory
  (**1 passed**). This separates a measured Windows write-permission failure
  from a control/lease regression; no failed assertion or export check is removed.
- Combined round-trip retains qualified passage, derived target, original
  signal time/frame/generation, allowances and actual ordered pedal writes.
  Hashes/chunks/ordering remain valid; `confirmed=false`,
  `runtime_authorized=false` and `game_consumption_verified=false` remain.
- One initial default sandbox temp run failed with Windows `PermissionError`
  before assertions; it was rerun in a working isolated directory. Earlier
  isolated export attempts also returned `DIAGNOSTIC_EXPORT_WRITE_FAILED` without
  retaining the original exception. Later isolated and combined selections
  passed with unchanged export code and assertions. The historical OS/write
  cause of those earlier attempts is not claimed as proven; the later lease-run
  failure specifically records PermissionError. Error details are exposed by
  the test wrapper.
- Full pytest remains for the user. No production collection was armed or changed.
- `compileall` and `git diff --check` pass. No steering/controller benchmark is
  reclassified as a game measurement.

Reproducible tools:

```powershell
$env:PYTHONCASEOK='1'
python tools/analyze_prefab_signals.py --output docs/steering-audit/prefab-signals-real.json
python tools/run_prefab_signal_bench.py --workdir docs/steering-audit/prefab-signals-new-run --output docs/steering-audit/prefab-signals-model.json
```

Use a new work directory; the model tool refuses to overwrite an existing one.
Audit JSON stores input hashes, recorded identities and explicit reconstruction
limits. Original exports/caches/logs remain untouched; large generated evidence
and the read-only upstream reference stay in ignored audit storage.

## Runtime package and remaining limits

Changed runtime files: `core/engine.py`, `core/longitudinal.py`,
`core/navigation/road_network.py`, `core/navigation/prefab_signals.py`,
`core/sdk/signal_snapshot.py`, `core/service_brake_hold.py`,
`plugins/map/main.py`, `plugins/drivepolicy/main.py`.
Map **1.0.7 -> 1.1.0** and DrivePolicy **1.0.5 -> 1.1.0** add the coordinated
backward-compatible metadata/consumer feature. ACC **1.1.4**, Autopilot **1.2.1**,
Controller and the producer DLL remain unchanged. No DLL replacement is needed
for the already available version-2 sidecar; a legacy-only DLL cannot authorize
fresh green release. Core changes do not release unaffected plugins.

Other changed files: this report, `PLUGIN_CHANGELOG.md`, `DEFERRED_WORK.md`,
`tests/test_prefab_signal_binding.py`, `tools/analyze_prefab_signals.py`,
`tools/run_prefab_signal_bench.py`. Nothing has been installed, committed, pushed
or launched in ETS2. This list is not deployment authorization.

Remaining limits: no painted-line/front-body measurement; unknown/oversized
vehicles beyond the stated allowance; missing or ambiguous control groups;
unmeasured live sidecar-to-PPD compatibility and SDK brake consumption; actual
grade holding; physical braking insufficiency; and independent stationary-red
activation ownership. They block a universal or game-confirmed stop/resume
claim. The implemented supported offline path is complete; no new drive is
requested by this task.

## Full-suite regression follow-up

The user's full suite exposed two failures in
`test_refresh_preserves_existing_physical_signal_brake_chain` (automatic modes
0 and 3). The new `traffic_signal` deadline source was not recognized by the
shared bounded-refresh dispatcher. A valid near-expiry signal decision therefore
triggered a technical stop instead of preserving the established brake chain.

The dispatcher now reads the independent producer signal time from a valid
current traffic packet. It verifies authority, the locked head/lifecycle/passage,
frame progression and original-time freshness. It does not renew the old lease
or authorize expired throttle. The original two cases now pass; twenty added
negative cases cover missing/invalid evidence, changed identity/head/passage/
lifecycle, expired/future observations and regressing or retimestamped frames.
The contract test file has 36 passing cases. This is an offline regression fix,
not a new ETS2 verification. No plugin implementation or plugin version changed
in this follow-up.
