# Native signal direction at the Oct 10 incident placement

Date: 2026-10-10. **OFFLINE VERIFIED for the scoped native direction defect
and the supported placed-prefab stop/restart model. NOT GAME VERIFIED.**
This completes the missing direction investigation in
[PHASE7_SIGNAL_DISTANCE_CONTRACT_20261010.md](PHASE7_SIGNAL_DISTANCE_CONTRACT_20261010.md).
It does not certify every head at this intersection or every traffic-light site.
No deployment, arm, game control, commit, push or full pytest run was performed.

## Evidence and build identity

Working tree base: `787d012a2a78ac917bb5506e0958c32d8d06575f`, with all preceding
uncommitted packet-refresh, traffic, distance, hold and export changes retained.
No AGENTS.md exists in the available project. PLUGIN_VERSIONS.md and the preceding
reports/deferred work were read. The installed receipt
`traffic-availability-20261010T161148Z` still matches all **18** target SHA-256
values. LF/CRLF-normalized comparison distinguishes eight actual runtime changes
from line-ending differences; the candidate is not installed.

The existing immutable codec again verified these untouched original exports:

| Original installed route-diagnostics file | Integrity | Samples |
| --- | --- | --- |
| steering-replay-20261010T164110.211564Z-automatic_disable.json | valid | pedal incident / original first intervention |
| steering-replay-20261010T164111.194118Z-automatic_disable.json | valid | 703 packets, 10,800 executions |
| steering-timing-20261010T164132.332988Z-plugin_stop.json | valid | 1,668 timing samples |

Exact incident authority: activation `1137796149000`, session `1`,
map `promods-1.59`, dataset `d6cc7936fce4e902761abb5d`, intent
`697dbe31009c4d83b520092dbf158b7b`, revision **8**, build
`1f7b47966fa44d52ba3228d5f074fa92`, geometry
`b2d19b7499a1d553b12ac77e8a6d80f26eee06717145ea91c420eb09273237b0`.
The original first comparison was **1167.9134794 s**, intervention
**1167.9200405 s**. Traffic envelope SDK frame **157143714**, original observation
**1167.8641857 s**, age **49.294 ms**, matching authority; requested traffic/light
brakes were both zero. The signal acquisition was **1167.8862009 s**, native frame
**1007347294**, generation **6928**, lifecycle **18109188145067**.
Native and SDK counters are separate domains. Later SDK data is not substituted
for the original comparison. Full incident details remain in the distance report.

## Concrete defect: reversing the native direction twice

The pinned producer source is commit
`1f16156b9b37b70cf182c2bc09120fa1b234e129`, including the unchanged scoped candidate
source in `docs/steering-audit/signal-plugin-20261009/scoped-candidate/`.

- `src/prism/common.hpp` defines quaternion components **w,x,y,z**.
- `src/processing/traffic.cpp` enumerates the actual prefab's
  `segment->semaphore_instances`; `semaphore_instance.id` is copied unchanged.
  Owner UID, native node UIDs, origin and enumeration slot travel beside that
  same object. The slot is not the control ID or a global actor allocator.
- The same file publishes `traffic_object->placement.rot.w/x/y/z` unchanged.
  A traffic-light rule produces kind 1; other semaphore actors produce kind 2.
- `SignalReader` schema 3 decodes that quaternion and owner row consistently.
  At this placement its resulting yaw already follows the regulated navCurve
  direction. It is not the visual face normal of the lamp.
- `RouteSignalSelector` nevertheless added **pi** before both owned binding and
  unknown-coverage projection. This reversed the directed passage. Correct
  heads were rejected; opposite heads could look compatible with our entrance.

The reverse-engineered native ID field is marked `maybe` in its source structure.
ID equality alone is therefore **not** the proof. The following independent
original-asset and placed-pose checks establish this site's correspondence.

## Original PPD and the recorded head

The existing cached TruckLib.Core **0.3.0**, HashFs **0.2.6**, Models **0.4.2**
and GisDeflate **1.0.2** read the exact asset from installed game `base.scs`:
`prefab2/cross_temp/blkw/blkw_r2_x_r1_t_narrow_tmpl.ppd`.
The same path was absent from dlc_balkan_w; the token name was not used to guess
its package. No converter, package installation or game was run.

PPD version **25**, SHA-256
`1d1112d31434d552656c469f65863c01f9f9d43fef4963e5a6d38bac52327409`.
All **36** curve start/end positions and control IDs agree with the saved map
descriptor. All **16** authored semaphore positions/quaternions/IDs/profile/type
agree with the tracked fixture. The cached `semaphores` display array contains
malformed records after its first row; runtime binding does not consume it.
The correct original PPD was parsed independently rather than trusting that array.
Current asset identity is verified; a historical full-package hash was not logged.

Placed prefab `dlc_blkw_80`, UID **5337536095150555635**, origin **0**, native nodes:
`[5337536179342808338,5337536181041520511,5337536182308200131]`.
The existing production transform and elevation offset were reused unchanged.

| Directed relation | Original PPD | Transformed heading / position |
| --- | --- | --- |
| Our route `[30,4,13,24]` | controlled curve 30, group **1** | heading **-0.173821748 rad** |
| Own vehicle head | authored slot **3**, group **1**; local `(11.499997,0,18)`, quaternion `(1,0,0,0)` | same directed heading as our controlled curve |
| Opposite route `[10,12,6]` | group **3** | heading **2.967770906 rad** |
| Opposite head | authored slot **1**, group **3**; local `(-11.499999,0,-18)`, quaternion `(1.8375893e-15,0,1,0)` | `(34740.7397008285,6.90234375,45625.1712567315)` |
| Actually recorded green ID **3** | `(34740.7396850586,6.9023432732,45625.1712570190)`, yaw **2.967770895 rad** | position residual **0.01578 mm**, yaw residual **-2.834e-8 rad** from opposite authored head |

Thus the reconstructed recorded head belongs to the opposite group's pose,
not our group's pose. **No 3-to-1 namespace remapping is justified.** The selector
must not bind it to our route or use its green as clearance. The original fault
omitted native owner/node/origin/slot, so the reconstructed owner is explicitly
a model witness, not recovered historical ownership. Head 1's live existence,
color and complete contemporaneous native array were not retained in that fault.

The entire saved route is also rebuilt: **40** logged GPS UIDs, **39** exact
directed LaneIds, **565** points, **3** prepared passages. The entry distance
remains **119.4428053 m**, versus recorded **119.7387647 m**; difference **-0.296 m**.
This is distance to a prefab entrance, not proof of a stop line. The reconstructed
arc origin/fingerprint differ from the rolling replay and are not relabeled.

## Narrow production change and compatibility

`core/sdk/signal_snapshot.py` now shares the correct scoped-native forward
heading across candidate binding, owned uncertainty and fallback projection.
Exact prefab UID/node/origin/group, directed heading, current route authority,
producer lifecycle/generation/time, 500 ms freshness and signal lock remain.
Missing ownership or a genuinely unknown forward group cannot manufacture green.
Distance-aware pending approach and stopping reserve remain in place.

No producer/schema/ABI/DLL change is needed. Schema-3 owned rows use the existing
1.59.3-up-signal-scope DLL. The pre-existing unscoped schema-2 geometric heuristic
is left separate and unchanged; it is not certified by this scoped repair.
This result requires the verified installed scoped reader/producer path.
There is no new plugin implementation/release in this delta. Existing candidate
ACC **1.1.5** / DrivePolicy **1.1.1** from the distance repair remain; installed
ACC **1.1.4** / DrivePolicy **1.1.0**, Autopilot **1.3.3** / Map **1.1.1** are unchanged.

The authored object list is not a list of proven kind-1 vehicle lights. IDs
5/14/15/16/17/20 have no vehicle curve here. The source obtains actual kind from
the runtime rule; PPD type/profile alone cannot replace it. When these objects
are deliberately modeled as forward kind-1 heads, the selector retains an
unverified approach dependency. They are not silently excluded for a PASS.

## Reproductions, real interfaces and measurements

With only the previous native `yaw+pi` rule restored inside an isolated process,
the new same-place expectations fail (**10 failed, 3 passed**). The initial test
run before editing production also failed own-head, foreign-head and both backend
flows. No installed files or original evidence were modified for the comparison.

Corrected tests acquire genuine schema-3 packed rows through SignalReader and
use real placed PPD preparation â†’ selector â†’ DrivePolicy â†’ ACC â†’ Autopilot â†’
Engine â†’ real Controller/test mapping. Modes **0 and 3** run initial N/launch,
foreign green, own red, continuous brake/zero throttle through gear 0, missing
locked head, two new green-acquisition confirmations, release and restart, two
cycles, same-geometry republication, another stop dependency and manual cancel.
Chronological backend writes are checked; no parking command is used.

The publication test first exposed an incomplete test double: plain IPCState
omitted production's compact geometry authority and changed authority with every
token. The fixture now calls actual `lane_publication_batch`, with a fingerprint
computed by `lane_path_fingerprint` from the complete modeled LanePath. Assertions
remain unchanged; genuine unknown/new geometry still invalidates authority.
No production hold/identity gate was relaxed to make this test pass.

| Same input / before â†’ after | Result |
| --- | --- |
| Saved opposite green head on complete saved route | controlled stop, throttle 0 / brake 0.0500 â†’ normal authority, throttle 0.0160 / brake 0; foreign head grants no clearance |
| Own original PPD head through native reader, both directions | unassigned â†’ qualified exact directed group |
| Placed red/hold/green closed model, modes 0/3 | before: no qualified stop/restart cycle; after: completed, active, no further N |
| Other stop disappears while locked green is fresh | still waits, zero throttle; disappearance is not clearance |
| Conflicting colors, wrong owner/nodes/origin/direction/deck, unknown group | no qualified green; safety remains |

Existing unvalidated longitudinal plant: force demand `(2.2*throttle-4*brake)/1.4`,
drag `0.12+0.004*vÂ˛`, 350 ms actuator lag, 120 ms transport; 10 ms integration,
seeded ticks 33/50/80 ms and 30 ms producer/IPC separation. It is not an ETS2
vehicle/loaded-grade model. The actual prefab chain is used with an explicitly
synthetic 100 m straight prelude. Original vehicle groups 0/1/3 are model inputs;
their colors, native owner rows and subsequent SDK responses are not historical.

| Initial speed, both modes | Samples / modeled duration | Braking starts before entry | Model front gap at stop | Max deceleration | Max absolute jerk | Restart |
| --- | --- | --- | --- | --- | --- | --- |
| 35 km/h | 440 / 23.419 s | 67.765 m | 5.579 m | 1.153 m/sÂ˛ | 4.875 m/sÂł | yes |
| 50 km/h | 432 / 22.950 s | 99.307 m | 5.639 m | 1.629 m/sÂ˛ | 4.218 m/sÂł | yes |

All four runs: **0** simultaneous positive pedals, **0** parking writes,
**0** brake-zero samples during red holding. Physical writes are software
receipts, not confirmed game consumption or painted-stop-line/body geometry.
Baseline fails qualification, so comparable baseline deceleration/jerk metrics
do not exist; they are not replaced with zeros.

1,000 warm selector operations with identical placed vehicle-group inputs:
p50/p95/p99/max **0.0457/0.0570/0.0888/0.2174 ms â†’
0.0368/0.0408/0.0637/0.1306 ms**. An earlier repeated run had a worse candidate
maximum (0.4305 ms vs 0.1857 ms); these microbenchmarks do not prove improved
live cadence. No cache, worker, queue or memory budget is enlarged. Only the
heading interpretation changes; no SDK/IPC/diagnostic reads are added.
All **16 steering** and **12 longitudinal comfort** metrics are numerically
identical to preserved `oct10-traffic/steering.json` and `comfort.json`.

## Reproducibility and remaining game boundary

- `tools/extract_oct10_signal_ppd.ps1 -OutputPath <new ignored JSON>` reads the
  existing game archive with pinned cached packages, hashes PPD/parser DLLs and
  refuses overwrite. Its output contains all original heads/curves.
- `tools/audit_oct10_native_signal.py --output <JSON> --workdir <new directory>
  --ppd-audit <extracted JSON>` checks all 36 cached curves/16 authored objects,
  reproduces the prior rule and runs the same placed closed-loop model.
- `tools/reproduce_oct10_signal_place.py` uses the exact logged route and
  independently matched original PPD pose. Ownership is never inferred from
  entry distance or the reversed direction.
- `tools/analyze_oct10_signal_flow.py` uses the existing immutable codec and
  installed receipt. Raw/decoded artifacts remain ignored under
  `docs/steering-audit/oct10-signal/`; originals are preserved.

**Offline conclusion:** a concrete direction-interpretation defect is fixed;
the observed ID 3 pose is reconstructed as opposite, while the own group 1
stop/restart flow passes through production interfaces. This is more than moving
the old takeover closer to the entrance. The 500 ms, R/backward/backend/identity
checks and continuous-brake ownership are preserved.

**Not established:** the original complete native kind/owner array, live head 1
at that acquisition, actual SDK continuous-brake consumption/grade holding,
accurate physical stop-line/front offset, legacy unscoped signal authority, or
the game's response to this candidate. Missing original fields are not synthesized
into historical evidence. The existing scoped sidecar and bounded signal receipt
are the smallest means to obtain that live binding; no additional sensor/collector
or new ride is requested now. GAME VERIFIED requires full-suite approval, a
separately approved coherent deployment and the user's passage at this place.

## Verification and exact runtime candidate

Verification counts and content hashes are appended below after final checks.

- Final explicit 17-file targeted run: **312 passed in 54.55 s**, including
  original native ABI/probe, full same-place flows, actual Map prefix rebasing,
  traffic/emergency/R/backend/identity/stale cases, refresh and immutable exports.
- Earlier run: 310 passed / 2 new republication tests failed because the test
  double omitted production metadata. After supplying the actual publication
  contract, the affected three files passed 43 tests and the final run above
  passed. Existing safety expectations were retained.
- `compileall` passed for core/plugins/sdk/ui/tests/tools; `git diff --check`
  passed. LF/CRLF warnings are line-ending notices, not code mismatches.
- Both compiled signal-probe/ABI tests ran in the targeted suite; DLL source,
  binary and receipt are unchanged. No replacement DLL belongs to this delta.
- Full pytest remains for the user. Game behavior remains NOT VERIFIED.

The coherent candidate payload relative to the verified installation is:

| Runtime path | Candidate source SHA-256 |
| --- | --- |
| `core/engine.py` | `10aacb33abe427e35bb2d082256e2ea2fd82a433658fd8dfc5b60e7321e1236c` |
| `core/longitudinal.py` | `27a5041b25fb23e425a12e2d068b99102f70ff2d46d7bb317710bcc3afa907a8` |
| `core/navigation/longitudinal_diagnostics.py` | `82239ecc6cda348e3bdb5aff0575b1600a45fe5359e760b32f50b26d66a52df6` |
| `core/navigation/prefab_signals.py` | `1197a5957a1eee2ae230204e8f3a3bb971dea160e24b804cb2f59995f48089e0` |
| `core/sdk/signal_snapshot.py` | `fd87714309f7a0bf17c642056bb1ce6e76d58c2de4a285916090c61b13f19066` |
| `plugins/acc/main.py` | `a10093e043113cb32eb0e7061c3a99894e3feff2f76897a8ad77b0d8649881c8` |
| `plugins/drivepolicy/main.py` | `3c8d7c9e28f93032edb987e39202064297c24832ad4ed4d36fe65170fc5099df` |
| `ui/visualization.py` | `9cb945235d534afc637a322dce0c288251cf742f62db85e63802c25312c53d89` |

These are raw source hashes; normalized comparisons determine actual content
differences. The preceding eight-file distance package is retained, with this
additional selector correction in `core/sdk/signal_snapshot.py`. No other
tracked core/plugins/sdk/ui Python file differs after LF/CRLF normalization.
Existing Controller, scoped DLL and SDK interfaces remain dependencies, not new
payload. The verified DLL is `1.59.3-up-signal-scope`, SHA-256
`0aba58549d2a7d008bc620424a43fa0f28c840e1688687d0ffd5effe6e434dab`; it is not rebuilt
or copied. Settings, map-cache, commit marker, old evidence, tools, fixtures and
reports are excluded from deployment. Nothing was installed.

Files changed in this continuation: `core/sdk/signal_snapshot.py`; scoped
fixture helpers in `tests/test_scoped_signal_binding.py`,
`tests/test_oct10_signal_approach.py`, `tests/test_oct8_signal_coverage.py`; new
`tests/test_oct10_native_signal_direction.py` and
`tests/fixtures/oct10-signal-place.json`; `tools/run_prefab_signal_bench.py`,
`tools/reproduce_oct10_signal_place.py`; new `tools/audit_oct10_native_signal.py`
and `tools/extract_oct10_signal_ppd.ps1`; this report, the distance report
follow-up, `DEFERRED_WORK.md` and `PLUGIN_CHANGELOG.md`. Existing unrelated
local changes are preserved.
