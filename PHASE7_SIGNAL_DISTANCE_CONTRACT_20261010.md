# Distance-aware signal uncertainty and continuous-stop flow

Follow-up: [PHASE7_SIGNAL_NATIVE_DIRECTION_20261010.md](PHASE7_SIGNAL_NATIVE_DIRECTION_20261010.md)
independently decodes the original PPD, matches the recorded head's pose to the
opposite group 3 and fixes the extra pi rotation of scoped native yaw. That
supersedes this earlier report's direction-compatible group-1 inference and
pending classification for this head; the distance measurements and historical
missing-owner limitations below remain the original audit record. No 3-to-1 ID
remap is used. The supported own-head lifecycle is verified offline, not in ETS2.

Date: 2026-10-10. **OFFLINE VERIFIED for the reproduced premature takeover
and the supported qualified-signal lifecycle. NOT GAME VERIFIED.** The live
ID/control-group correspondence at the reported place is not established.
No deployment, collection arm, game control, commit, push or full pytest run.

## Build and preserved evidence

Base HEAD: `787d012a2a78ac917bb5506e0958c32d8d06575f`, with preserved local
uncommitted changes. No AGENTS.md was found. Project versioning, deferred work
and the existing signal/traffic reports were consulted. The installed receipt
is `traffic-availability-20261010T161148Z`: all 18 installed receipt hashes
match. At task entry, their Python content matched source after LF/CRLF
normalization. They still match their receipt; new candidate edits are not
installed. Installed Autopilot 1.3.3, Map 1.1.1, ACC 1.1.4, DrivePolicy 1.1.0
and DLL `1.59.3-up-signal-scope` are the baseline, not this candidate.

Existing codec/integrity checks passed for these unchanged installed files:

- `route-diagnostics/steering-replay-20261010T164110.211564Z-automatic_disable.json`
  (pedal incident, including immutable first intervention and backend receipts);
- `route-diagnostics/steering-replay-20261010T164111.194118Z-automatic_disable.json`
  (dense replay: 703 packet samples and 10,800 execution samples);
- `route-diagnostics/steering-timing-20261010T164132.332988Z-plugin_stop.json`
  (1,668 timing samples).

No corresponding same-session significant-event export remains in the directory.
Morning and Oct 9 exports were not substituted for this evening incident.
Original files and log are unchanged. Decoded large data and benchmark outputs
remain ignored under `docs/steering-audit/oct10-signal/`.

Exact incident binding: activation `1137796149000`, session `1`, map
`promods-1.59`, dataset `d6cc7936fce4e902761abb5d`, intent
`697dbe31009c4d83b520092dbf158b7b`, revision **8**, build
`1f7b47966fa44d52ba3228d5f074fa92`, geometry
`b2d19b7499a1d553b12ac77e8a6d80f26eee06717145ea91c420eb09273237b0`.

## What caused the first intervention

The first recorded Engine intervention is **1167.9200405** monotonic seconds,
after its **1167.9134794** comparison. The actually rejected traffic envelope
was valid, SDK frame **157143714**, observation **1167.8641857**, computation
**1167.8923327**, expiration **1168.3641857**: observation age **49.294 ms**,
remaining lease **450.706 ms**, matching identities. Traffic and signal brake
requests were both **0**. This was not a stale-data or braking-source rejection.
Autopilot recorded the same coverage error later at **1167.9300744**.

The trigger was an **unassigned green head ID 3** at
`(34740.739685058594, 6.902343273162842, 45625.17125701904)`, yaw
`2.967770895079519`. Its original signal acquisition was **1167.8862009**,
frame **1007347294**, generation **6928**, lifecycle **18109188145067**.
Signal-source age at the first comparison was **27.279 ms**. SDK and native
sidecar frame counters are distinct; their numeric values are not equated.
The decoder accepts traffic-light kind 1; the original raw kind field was not
retained separately in the incident, so that is a source-path fact, not an
exported field.

Coverage reported **119.7387647 m** with basis
`sdk_reference_to_unassigned_native_passage_entry`. This is along the directed
route to a prefab entrance, **not** aerial distance to the lamp or a measured
painted stop line. Before this fix `_coverage` unconditionally set
`requires_takeover=true` for a detected conflict inside its 120 m search
horizon, irrespective of distance or stopping reserve. That predicate passed
through shared traffic validation to Engine and Autopilot. It caused the
premature technical stop although no qualified red brake request existed.
The diagnostic budget marker is not its cause. The actor-ID ambiguity in the
same input is separate; the first refusal specifically names signal coverage.

The corresponding calculation-frame replay row has LaneId road UID
`5337536093762228338`, direction 1, lane 1; progress **207.3059871 m** and
SDK position `(34748.910064697266, 45779.80514526367)`. Its application speed
**21.28248 km/h** is explicitly a proxy, not a missing calculation-frame speed.
The fault's outer vehicle frame 157160380 is later than the rejected input and
was not used to replace its original observation.

The first fault's compact vector omitted native owner UID/nodes/origin and the
selected passage record. Those historical fields cannot be recovered by
assigning the reconstructed owner. The user's roughly 200 m observation is
not treated as a precise measurement or as a new distance threshold.

## Implementation and shared contract

1. Existing Map preparation retains up to **128 fixed-field route ownership
   scopes**, including unregulated route prefab placements. No centerline,
   transform, lane selection, controller or tracking geometry is changed.
   A proven foreign owner is excluded from geometric fallback only with a
   complete prepared scope; partial metadata does not certify foreign coverage.
2. An unassigned head with a proven native owner and directed entry may yield
   `UNASSIGNED_APPROACH_PENDING`. The entry is an existing map-derived planning
   target, explicitly `stop_line_verified=false`. Its offset uses the existing
   6 m front allowance and 2 m standoff; neither is newly measured body geometry.
3. Policy, ACC and the final shared Engine arbitration consume the **same**
   approach ceiling, using the existing signal stopping envelope. No extra PID,
   pedal filter, guessed red or nearest-head control is introduced. The command
   remains bounded by the original signal acquisition + **500 ms**.
4. Stopping reserve is the existing planning assumption
   `v²/(2*1 m/s²) + v*(1 s response + 0.5 s evidence budget)`.
   Unresolved regulation escalates when the remaining derived-target distance
   reaches that reserve. Missing speed or no proven entry remains fail-closed;
   a projected lamp is never invented into a stop line.
5. One private unresolved-entry record is retained per exact authority and
   producer lifecycle. Disappearance retains its original time/generation;
   repeated buffer reads cannot renew it or grant clearance. New session,
   activation or route authority invalidates it. Qualification of the same
   passage replaces uncertainty with the existing qualified-stop contract.
6. Qualified red/yellow, same-ID signal lock, continuous service braking,
   fresh multi-generation green confirmation and existing launch remain one
   unchanged lifecycle. Other braking reasons still block release. No parking
   brake action is added. Technical loss still cannot automatically resume.
7. HUD distinguishes detected/unassigned approach from qualified control.
   A visible detected green is labeled unconfirmed and is never green authority.
8. Within the existing **8 KiB fault receipt**, schema-2 fixed signal comparison
   preserves native ownership, target/reserve and the already-compared LaneId,
   progress and publication token. Schema-1 historical vectors remain readable.
   The priority fields survive unrelated detail overflow. Existing 64 KiB
   backend detail, 1 MiB summary history, hashes and incident worker are retained;
   no extra SDK/IPC reads, per-tick INFO output or new collector is added.

## Same-place reproduction: exact evidence vs model

`tools/reproduce_oct10_signal_place.py` reads the saved map cache, 40 logged
UIDs and 39 exact logged LaneIds, and rebuilds every directed connection with
production topology/trajectory functions. It uses the actual rejected lamp
pose, ID, color and acquisition values. The full reconstructed path has 565
points. Its origin differs from the rolling replay: reconstructed current
progress **178.5447259 m**, not 207.3059871 m. Its fingerprint differs; it is
**not** relabeled as the original geometry.

The unique direction-compatible reconstructed entry is prefab `dlc_blkw_80`,
curves `[30,4,13,24]`, authored group **1**, placed UID
`5337536095150555635`, nodes
`[5337536179342808338,5337536181041520511,5337536182308200131]`, origin **0**;
entrance `(34753.47350066377,6.90234375,45663.9580174013)`.
Reconstructed distance to entry is **119.4428053 m**, residual **−0.2959594 m**
from the incident's 119.7387647 m. Altitude is map-derived and speed is the
application proxy. Owner fields injected for the supplemental reproduction
are explicitly **model inputs**, not recovered historical values.

| Same saved head / reconstructed place | Installed selector | Candidate |
| --- | --- | --- |
| Classification at 119.443 m to entry / 111.443 m to derived target | Immediate takeover | Pending approach; no clearance |
| Proxy-speed stopping reserve | Not consulted | 26.342 m |
| Actual Policy → ACC → Autopilot → Engine → Controller/test mapping | Controlled stop, throttle 0, brake 0.0500 | Normal authority, throttle 0.0160, brake 0 |

The physical-flow experiment uses the immutable original signal at the reader
boundary and modeled fresh SDK inputs; it does not run DLL/game code. Separate
integration tests acquire actual schema-3 bytes through SignalReader and use
real placed PPD fixtures before Policy/ACC/AP/Engine/Controller. It is not a
claim that the real head is qualified or that ETS2 consumed those writes.

Native source publishes `semaphore_instance.id`; the reverse-engineered
structure even marks that field `maybe`. The current interface has no separately
verified control-group correspondence. Original native ID **3** is not remapped
to authored group **1** merely because poses/directions are close. If it never
qualifies, this candidate still requires takeover before that conflict.

## Decision distances and regression evidence

At modeled speed **6 m/s**, the reserve is **27 m**. Each row is a genuinely
new producer observation; unavailable-source tests separately retain old times.

| Progress toward modeled entrance | Entry distance | Derived target distance | Candidate state |
| --- | --- | --- | --- |
| 0 m | 120 m | 112 m | Pending, no immediate stop |
| 50 m | 70 m | 62 m | Pending |
| 75 m | 45 m | 37 m | Pending |
| 85 m | 35 m | 27 m | Takeover; no unknown-color restart |

Four new unchanged candidate expectations **fail** with only the offending
installed selector restored in an isolated process, including the full flow
in both automatic modes. After correction, the final explicit 19-file targeted
run is **393 passed**. It covers native acquisition/binding, foreign/opposite/
deck and conflicting heads, missing/stale signals, real-prefab red/hold/green,
two automatic modes, multiple cycles, pending-source disappearance, reroute,
manual cancel, required ACC loss, R/backend faults, immutable export and the
previous packet-refresh regressions. No old test assertion was weakened.

An intermediate run exposed a tuple-versus-JSON-list mismatch in newly exported
LaneId; production now uses the canonical JSON representation and the original
export assertion passes. That run also had one 1,800-sample finalization failure
with a complete staged manifest. Isolated export reached READY and final serial
targeted run passed; its original OSError detail was not retained, so no causal
claim or speculative collector change is made. Test-spy stdout pollution in a
temporary diagnosis was removed; it is not counted as a production regression.

### Same closed-loop qualified-stop inputs, before and after

Existing explicit model: irregular ticks, transport delay, production planner,
ACC, arbitration, Autopilot, Engine and real Controller with test mapping.
Installed/candidate selector results are identical in all four paired runs.

| Approach speed / modes | Brake starts before entry | Stop-front gap | Maximum deceleration | Maximum modeled jerk | Green restart |
| --- | --- | --- | --- | --- | --- |
| 35 km/h, 0 and 3 | 67.765 m → same | 5.579 m → same | 1.153 m/s² → same | 4.875 m/s³ → same | Yes → yes |
| 50 km/h, 0 and 3 | 99.307 m → same | 5.639 m → same | 1.629 m/s² → same | 4.218 m/s³ → same | Yes → yes |

All runs have zero concurrent positive pedals, zero parking-brake writes and
zero brake-zero writes during the modeled red hold. This uncalibrated plant
does not establish SDK brake consumption, grade/load holding or painted-line
accuracy. All **16 steering** and **12 comfort** case metrics are numerically
identical to the preserved preceding outputs (`oct10-traffic/steering.json`
and `comfort.json`). No steering timing or 35 km/h roundabout target is changed.

### Bounded operation cost (not live cadence)

1,000 warm selector calls at the same placed unknown entry:

| Wall time | Installed | Candidate |
| --- | --- | --- |
| p50 | 0.0192 ms | 0.0252 ms |
| p95 | 0.0228 ms | 0.0257 ms |
| p99 | 0.0376 ms | 0.0315 ms |
| maximum | 0.0783 ms | 0.0942 ms |

Only one unresolved record is held, with a fixed-field target/head/source and
the existing maximum 40 native heads. No curve-index list is repeated in scope
metadata. A separate 600-tick traffic-flow operation comparison yielded
p50/p95/p99/max **8.058/8.608/11.080/29.928 ms →
8.197/8.888/12.363/38.340 ms**, identical mapping bytes and IPC-read counts.
It uses the existing equivalent inline publisher model for these valid-actor
inputs, not a live scheduler measurement. The maximum increased; it is not
reported as an end-to-end performance improvement. Existing detail/history
storage remained below 64 KiB / 1 MiB. These costs were measured with concurrent
offline checks and cannot predict live OS jitter. Static check results follow
in the final verification addendum.

## Candidate runtime package and remaining boundary

Only these content-changed runtime files relative to the installed baseline
belong to this delta, as one coherent package:

- `core/engine.py` (already-consumed signal/map evidence only);
- `core/longitudinal.py`;
- `core/navigation/longitudinal_diagnostics.py`;
- `core/navigation/prefab_signals.py`;
- `core/sdk/signal_snapshot.py`;
- `plugins/acc/main.py` (**1.1.4 → 1.1.5**);
- `plugins/drivepolicy/main.py` (**1.1.0 → 1.1.1**);
- `ui/visualization.py`.

Core-only changes do not release Autopilot or Map. Their implementations in
this delta, the DLL and Controller are unchanged. No tests, reports, tools,
settings, map-cache, controls, original evidence or commit marker are deployment
payload. Nothing has been copied to the installation.

**Offline PASS:** distance-independent premature takeover removed, qualified
red/continuous hold/same-signal fresh green/restart preserved, bounded evidence
retains the actual comparison, and freshness/reverse/identity guards remain.
**NOT VERIFIED:** native instance-ID/control-group correspondence and complete
signal coverage at this actual place; SDK continuous-brake consumption/loaded
hill holding; game result of this candidate. Historical owner fields/full native
array and calculation-frame speed/Y are missing. The new compact receipt covers
the ownership/target gap on future ordinary incidents without arming.

The supported qualified flow is ready for the user's full suite. The entire
reported place is **not declared resolved** merely because the early stop moved:
ID 3 is still unqualified. No new drive is requested. Game acceptance requires
a separately approved coherent deployment and qualified coverage at the place;
no guessed mapping or safety suppression is used to obtain a successful run.

Reproduction tools: `analyze_oct10_signal_flow.py`,
`reproduce_oct10_signal_place.py`, `verify_oct10_signal_baseline.py`,
`benchmark_oct10_signal_flow.py`. These are offline tools, not runtime collectors.

## Final verification addendum

- The final 19-file run passed **393 tests** in 63.25 s. After extending the
  same compact priority receipt to pending-approach faults as well, the four
  affected integration/export files passed **64 tests** in 5.85 s, including
  the new distant-entry budget-overflow case. Counts overlap; they are not added.
- `compileall` passed for core/plugins/sdk/ui/tests/tools. `git diff --check`
  and trailing-whitespace checks of new files passed; LF/CRLF notices are not
  content failures.
- Final historical export inspection passed through the backward-compatible
  codec, and all 18 installed receipt hashes still match. A content-normalized
  scan of tracked core/plugins/sdk/ui Python files confirms exactly the eight
  runtime differences listed above, including both actually changed plugin
  implementations. Raw source/installed SHA-256 values are saved in the ignored
  `docs/steering-audit/oct10-signal/candidate-package.json`; this is a candidate
  inventory with `deployed=false`, not a deployment receipt.
- Full pytest and game verification remain pending. No source diagnostic file
  was armed and no runtime/DLL file was installed.
