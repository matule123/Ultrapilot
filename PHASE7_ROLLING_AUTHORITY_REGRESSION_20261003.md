# Phase 7 — Rolling-window longitudinal authority regression

## Scope and baseline

Baseline: `99c4ff7c5ca66d539e838dc8d41960b167e5b308`, following the
activation-race fixes. The tracked working tree was clean at entry. AGENTS.md
was absent at the inspected project locations; PLUGIN_VERSIONS.md was read.
No game, installation, original diagnostic record, or existing controller was
modified. This report describes an offline core fix, not a confirmed game fix.

The installed Engine, longitudinal module, SharedState, PluginSDK, Map and
Autopilot were byte-identical to this baseline during the read-only check.
The new local changes have **not** been installed.

## Incident evidence

Session `1`; map `promods-1.59`; dataset `d6cc7936fce4e902761abb5d`;
intent `b0eb388edc3b4f5ebca029b54e87d4d0`; revision `7`; build
`b9304119de9e44f49d29607c74eebb33`.

| Artifact | SHA-256 | Evidence and limitation |
| --- | --- | --- |
| Supplied log attachment `46bd6991-5368-4f53-af4a-c401e8f58601/Vložený text.txt` | `7532b94ae4068a7d23a33503b1754ce31f9396503e904e4840e4956dbdb301f7` | One N at 16:21:05, probe 0.12, gear 4, handoff 0.13971752; prefix trim and identity rejection at 16:21:10 |
| `steering-replay-20261003T142110.612707Z-automatic_disable.json` | `9b3ff8bb5670b0177367e1632f22de67e52795f4e43ec38407c5d52f59fdcfad` | 106 control rows, 5,029 execution rows, matching incident identity/reason; **zero** immutable execution source packets; rejected longitudinal context absent |
| `steering-timing-20261003T142124.250125Z-plugin_stop.json` | `62545a1409eaf727569a15a905c607e315d498c9c588f151109ba2ae60b32ac0` | 132 passive timing rows with the matching route identity; no pedal activation/publication token evidence |

Accepted control rows cover monotonic 26896.5507535–26901.1795117 and SDK
frames 15316054–19982534. All sampled LaneIds are road UID
`5337536096111037309`, direction 1, lane index 1. They do not prove that the
rejected command's context was unchanged. The attachment records release at
frame 20232524 and the generic identity rejection. No new combined collection
for this session exists in the diagnostic directory. Its status still refers
to the older cancelled 15:28 collection; those sessions were not merged.

**Historical uncertainty:** the old/new longitudinal contexts and activation
epochs at rejection were not retained. Their exact historical values cannot be
reconstructed. ADVANCED_PREFIX is correlation in the log. The production code
defect below is independently reproduced with the same transition and error;
it is not presented as a measured historical token comparison.

## Proven cause and narrow fix

The eight context components were: activation failure epoch, game session,
map, dataset, navigation intent, trajectory revision, build, and **publication
UUID**. The last component was added in `7adf8c8`. SharedState generates a new
UUID for every LanePath publication, including Map's proven rolling rebase.
`_rebase_rolling_snapshot` retains the validated points and path fingerprint
while changing only the source/covered GPS UID metadata. Existing producer
packets consequently fail `rejection()` even though authority is unchanged.
Engine enters controlled stop and removes propulsion; Autopilot can then
complete the disable. This is not a gearbox or steering-regulator defect.

| Boundary | Before | After |
| --- | --- | --- |
| Navigation tracker | ADVANCED_PREFIX preserves intent; SAME_EXACT preserves intent | Unchanged |
| Map rebase / SharedState | Same geometry, new cache UUID | Unchanged cache UUID invalidation; additionally publish compact longitudinal geometry identity in the same update |
| Pedal producers / Autopilot | Bind to cache UUID, which may change before their next tick | Bind to the existing validated LanePath SHA-256 plus validity, build and the original authority/activation fields |
| Engine arbitration / final write | A still-fresh unchanged-authority packet triggers identity rejection | Such a packet remains valid only within its **original** lease; real geometry/activation changes still reject it |

The existing Map fingerprint covers XYZ samples, headings, curvature,
directed LaneIds, elevation, segments and revision. No geometry hashing or
geometry transfer was added to pedal ticks. The compact build/geometry value
is fetched together, avoiding pairing a build read with a later transport UUID.
Unknown or malformed fingerprints retain publication-based invalidation.
Invalid snapshots change the geometry validity component. Normal progression
to another LaneId inside the same validated LanePath does not redefine the
path; independent live LaneMatch/steering checks remain mandatory.

No previous packet is relabelled, republished, or timestamp-refreshed. There
is no new waiting state: first-command handover retains the existing fixed
500 ms zero-output bound; real authority loss retains controlled stop. Old
activation packets, R, backwards movement, stale SDK/packets and changed
intent/session/dataset/build/geometry remain rejected. Regulators, launch
handoff, gear semantics, cache behavior and geometry are unchanged.

## Reproduction and verification

The integration fixture uses NavigationIntentTracker, a directed synthetic
RoadNetwork, actual Map localization/rebase/packet publication, Policy/ACC,
Autopilot, Engine and **the real Controller/SCSControlsWriter**, with an
in-memory test mapping and recorded float32 writes. It is not an ETS2 plant.
Progress advances in 0.5 m steps at 15 m/s with 33.333 ms ticks; no teleport
or fabricated connector is required.

| Scenario | Baseline / fixed result |
| --- | --- |
| One N, neutral launch, confirmed forward gear, normal ticks, first prefix trim between pedal ticks | Baseline enters `controlled_stop` and loses physical throttle despite unchanged geometry; fixed retains authority, positive mapped throttle and zero brake |
| Three ADVANCED_PREFIX updates, SAME_EXACT, normal directed LaneId transitions | Fixed passes; publication UUID changes, geometry/context remain stable, old command dictionary/timestamps unchanged until a genuine producer tick |
| True reroute, session/dataset change, destination removal, different geometry fingerprint | Fixed rejects propulsion; original failure remains after the next output tick |
| Manual disable, new N, previous-activation command | Zero mapped controls on disable; old command cannot drive during first-command wait; a newly calculated current command takes over |
| Prefix/reroute publication during command IPC | Same-authority prefix continues; true reroute removes propulsion |
| Stale observations, R, backwards movement | Fail closed with zero propulsion |
| SharedState and PluginSDK publishing; unknown geometry; invalid snapshot | Both writers publish the same compact contract; cache refresh remains independent; unknown/invalid geometry invalidates old authority |
| Backend write failure and diagnostic provenance | Existing real-writer regressions pass; failed/unavailable mapping writes remain explicitly unsuccessful/unverified, never evidence of game consumption |

The final prefix test was also executed against the baseline functions loaded
directly from HEAD, without reverting files: one expected failure at
`controlled_stop`. The same test passes with the fix.

Targeted verification: **316 tests and 36 subtests passed** across rolling
authority, activation races, arbitration, snapshot transport, intent, Map
authority, joint Phase 7 flow, launch/gear transitions, ACC and longitudinal
diagnostic export/provenance. After strengthening the assertions to preserve
the entire original command and moving before the concurrent prefix update,
all **14 new cases** passed again. An earlier sandbox run encountered Windows
PermissionError in pytest's temporary directory; the targeted run with a new
ignored basetemp outside that restriction passed. This was not an application
regression. The full test suite was not run.

Steering benchmark: all **16 case dictionaries are numerically identical**
between HEAD and the fix. Artifacts remain ignored under `docs/steering-audit/`:
`oct3-rolling-steering-before.json` and `oct3-rolling-steering-after.json`.
This is controller evidence, not a new live cadence or ride-comfort measurement.
Compileall and diff/whitespace checks passed.

## Result and changed files

**Proven code regression fixed offline. Game confirmation: NOT VERIFIED.**
The historical rejected context is still unavailable; no further drive is
requested here. Existing incident data was preserved. No timeout, safety
threshold, first-fault behavior, regulator, steering limiter or GPS geometry
was weakened.

Changed: `core/ipc/shared_state.py`, `core/longitudinal.py`,
`tests/test_rolling_longitudinal_authority.py`, this report and the link in
`PHASE7_FINAL_RESULTS.md`. No plugin source or VERSION changed: this is a
core-only fix under PLUGIN_VERSIONS.md, so unchanged plugins are not released
and no plugin changelog entry is warranted.

Suggested commit: `fix(control): preserve pedal authority across rolling GPS windows`.
Description: Separate LanePath cache publication from longitudinal geometry
identity; retain fresh same-authority commands across proven prefix rebases,
while rejecting changed geometry, route identities and prior activations.
Add production-flow and physical-write regressions. No commit or deployment
was performed.
