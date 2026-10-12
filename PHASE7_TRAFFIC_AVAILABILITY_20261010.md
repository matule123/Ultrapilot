# Oct 10 traffic validity, availability and first-fault preservation

Date: 2026-10-10. **OFFLINE VERIFIED for the reproduced contracts below;
the exact first rejected historical traffic snapshot/actor cause remains NOT
VERIFIED. Not GAME VERIFIED.** No deployment, game control, collection arm,
commit, push or whole pytest run. Existing packet-refresh, approach/signal and
pedal-export work is retained. No plugin implementation/version or DLL changed.

## Installed build and integrity

Before edits, all Python receipt targets matched repository content after CRLF/LF
normalization. All **18** installed receipt hashes match, including the five-file
packet-refresh payload and both DLL copies. Receipt: base
`787d012a2a78ac917bb5506e0958c32d8d06575f` with uncommitted changes,
`deployed_at_utc=20261010T063009Z`, payload content ID
`2f580acc989e632bfcd1993471b42f8011fa2449c682160fb772a908f11a1f29`,
`full_pytest=USER_REPORTED_PASS`. Autopilot **1.3.3**, Map **1.1.1**, ACC
**1.1.4**, DrivePolicy **1.1.0**, DLL **1.59.3-up-signal-scope** remain installed.
No AGENTS.md was found. Project version/deferred-work and current signal/traffic
reports were read; existing local changes were not reset or reclassified.

`tools/analyze_oct10_traffic_incident.py` uses **inspect_replay**, including its
existing immutable-reference codec, never indexes raw `$immutable` nodes as
public packets. All six relevant exports pass SHA/schema/count integrity:
four significant events at 06:35:15–18 UTC, pedal incident
`steering-replay-20261010T063538.233098Z-automatic_disable.json`, dense replay
`steering-replay-20261010T063539.235104Z-automatic_disable.json` (917 sampled
rows / 10,800 executor rows). Integrity is not complete evidence or game uptake.
Decoded copies/analysis/benchmark outputs are ignored under
`docs/steering-audit/oct10-traffic/`; originals are untouched.

Same binding: activation **7343709143800**, session **1**, map **promods-1.59**,
dataset **d6cc7936fce4e902761abb5d**, intent
**b94f980fca0d48e6a99423e7f4496f55**, revision **8**, build
**4c6f9a0edc9144b79aeeeb06e119520b**, LanePath fingerprint
**813f07575d26147642ce45cc680a3adc73c8878bb1ad598e2971158e7c9540f5**.

## Exact temporal boundary: the retained packet precedes the first fault

| Evidence | Monotonic time / SDK frame | Meaning |
| --- | --- | --- |
| Retained rejected optional traffic | original observation **7381.8043194**, calculation **7381.8203644**, expiry **7382.3043194**, frame **104112502** | `valid=false`, zero traffic/light brake, `following.status=ambiguous_actor_id`; invalid signal with reason `prefab semaphore ID missing or spatially ambiguous`, **coverage.requires_takeover=false** |
| Last successful bound physical write, journal sequence **1588** | start **7381.8987074**, mapping return **7381.8987196** | throttle **0.16121482849121094**, brake pair **0**; own comparison vehicle frame **104195832**, original time **7381.8738379**, gear **8**, speed **5.880532741546631 m/s** |
| Selected decision for that write | frame **104145834**, observation **7381.8217606**, calculation **7381.8550354** | ACC normal drive; curve deadline **7382.2687153**; traffic input rejection recorded, but optional traffic was **not consumed** and did **not stop this write** |
| First AP fault | **7381.9370333**, outer record vehicle frame **104245830**, original observation **7381.9266145** | `traffic: invalid longitudinal observation`; its compared input details are a budget marker, not the earlier source packet |
| First safety writes, sequences **1589 / 1590** | **7381.9575495 / 7381.9575873**, mapping returns **7381.9575585 / 7381.9575914** | throttle **0**, then brake **0.1253332495689392**; safety write's own vehicle frame **104212498**, original time **7381.8911572**, gear **8**, speed **5.8787841796875 m/s** |

The retained traffic observation was **132.714 ms** old at the AP fault time,
with **367.286 ms** lease remaining. It is not a stale observation, but it is
also not proven to be the packet compared by that AP fault. Later or earlier
vehicle reads are not substituted for that missing comparison.

The installed AP calls `read('traffic')` without explicit `required=True`.
In that installed read implementation only the signal coverage predicate
promotes it to required. Consequently, a terminal **traffic-prefixed** invalid
observation at that call implies the required-read branch (under this inspected
implementation); the retained earlier **coverage=false** optional packet cannot
alone reproduce it. The original first AP input and its required signal fields
are not recoverable from the budget marker. It would be incorrect to conclude
that the earlier ambiguous IDs alone caused the 08:35:38 shutdown, or that a
genuine unassigned-regulation takeover should be removed.

The detailed incident retains **13** pedal calls over **0.1819444 s**, with 1587
prior calls dropped from that short ring and explicit incompleteness. Its
separate summary history remains separately qualified. Neither history nor
significant-event receipts retain original TrafficCapture bytes/full actor rows.
No original missing/duplicated ID, source pointer, actor pose or cross-buffer
generation can therefore be assigned to this historical fault.

## Producer guarantees and code cause

Read-only native source inspected: pinned producer commit
`1f16156b9b37b70cf182c2bc09120fa1b234e129`, local scoped-candidate source/receipt.
Its DLL hash matches installation; this does not claim a bitwise rebuild from
source. `TrafficProcessor::get_uid_for_vehicle` allocates a **signed short** from
a pointer→UID map. Moving/parked publication are separate writes in `tick`;
neither buffer carries a producer timestamp or common generation. Short wrap,
pointer reuse, source enumeration overlap and cross-buffer transition are
possible code-level boundaries, **not historical explanations** established by
these exports. IDs are decoded from their original short fields, not converted
from a floating position value. The absent original rows prevent deciding among
same object twice, two objects sharing an ID, or a publication overlap.

TrafficCapture double-reads each bounded buffer and records receiver time/stable
bytes/session. It does **not** certify producer progression or joint atomicity.
The protective decoder rejects changing/missing/invalid rows and global duplicate
IDs before directed projection. That global rejection cannot reveal whether the
original ambiguous rows were on this route. LegacyTrafficProducer likewise
cannot certify coverage; CompleteTrafficProducer's separate authenticated
contract is not synthesized from this feed.

The reproduced production defect is at publication: Engine made the **whole
longitudinal packet's valid bit** depend on `traffic_available OR light != None`.
Thus a valid vehicle/route observation containing an unusable actor feed could
be labeled invalid. When regulation made that packet required, generic invalid
observation hid the real signal takeover cause. Meanwhile ACC's optional read
discarded it and displayed `traffic unavailable; cruise only`, because it had
neither a usable following candidate nor a previously acquired target. This is
different from a required regulation/target-loss decision; no ACC pedal itself
establishes navigation clearance.

## Implemented shared contract

Engine's existing inline producer publication was extracted without behavioral
change first, then tested and corrected in `_publish_traffic_control`. The real
route/perception loop calls it; tests call the same producer boundary with actual
TrafficCapture/decoder/selector/Policy/ACC/AP/Engine/Controller components.

- `valid` remains the exact vehicle observation + context envelope validity.
  SDK frame/time/expiry are original and still fully validated. It is **not**
  certification that actors or signal data are usable.
- `traffic_availability` schema 1 separately carries actors_usable, capture_status,
  original receiver_time, buffers_present, stable_read, atomic=false,
  coverage_confirmed=false and absent source timestamp/generation. `following`
  and qualified signal/coverage remain separate. An unstable/missing/stale
  optional capture yields no new traffic demand and **no clearance**.
- `read` validates these roles together. A positive traffic brake cannot use an
  unusable actor observation; a positive signal brake needs the consumed
  qualified candidate or already acquired unknown stop candidate. Usable actor
  evidence needs stable/present buffers, consistent projection status and its
  original receiver deadline. Relevant demand/coverage is required evidence;
  malformed roles cannot bypass validation or crash its diagnostic path.
- Required signal coverage retains its specific takeover cause despite unrelated
  actor ambiguity. Existing ACC acquired-target loss remains latched and blocks
  cruise restoration. Signal hold/clearance continues to require the same
  producer-timed head, current identity and other stop reasons. Invalid or absent
  actors never authorize a conflict gap or release a signal/vehicle stop.
- ID **0**, native invalid sentinel **-1**, absent/noninteger/out-of-short-range
  IDs and duplicates are explicitly unusable. Other signed-short values remain
  representable; no optimistic stable ID is invented. Up to **four** compact
  problem examples retain actual IDs, moving/parked slots, positions and equal
  decoded-value status, with omitted counts. **No rows are deduplicated**: equal
  contents do not prove the same native source object.
- Required traffic rejection retains compact `traffic_comparison`, exact original
  frame/time, checked time, contexts/differences and `rejection_cause`. Optional
  verbose details may be lost explicitly, but this priority receipt survives
  the existing **8 KiB** fault / **16 KiB** outer incident allocations through the
  existing exact immutable codec. No additional collector, SDK/IPC read or
  per-tick INFO output. PedalJournal's **64 KiB** detail / **1 MiB** history limits
  are unchanged; corrupt/incomplete evidence remains unconfirmed.
- A separate negative reproduction discovered SCS disconnect during the physical
  output could leave active state and publish applied pedals. Existing final
  output now checks connection before and after pedal I/O, revokes authority and
  skips applied publication on failure. This is a reproduced code defect, **not
  attributed to the historical traffic incident**. It adds no SDK/IPC read.

No controller gains, geometry, LaneId identity, packet cadence, 500 ms freshness,
bounded refresh, D selection or parking-brake behavior changed.

## Before/after evidence

| Reproduction | Before | After |
| --- | --- | --- |
| Valid vehicle + unusable optional duplicate/missing/changing/stale traffic | Whole packet marked invalid (or ID 0 accepted); no explicit role contract | Valid vehicle envelope, actors unusable, zero invented brake/clearance, ordinary optional cruise remains active |
| Required unassigned regulation + ambiguous actors | Generic `traffic: invalid longitudinal observation` | Specific signal coverage takeover; propulsion remains inhibited |
| Missing ID 0 / duplicate same or different content / moving–parked overlap | 0 accepted or ambiguity only as generic status | Explicit bounded original-ID/slot examples; no guessed deduplication |
| Oversized first rejection → safety writes/release → normal incident exporter | Required reason lost; outer first-fault export also overflowed during reproduction | Original cause/frame/time/IDs survive hash-checked automatic export |
| SCS disconnect during real output | Active flag remained; reproduced negative failed | Revoked before/after pedal boundary; no success publication |
| Retained preincident optional packet alone | Does **not** reproduce terminal fault | Same nonterminal rejection demonstrated; not misrepresented as recovered historical cause |

Initial **13 new tests failed** before the contract corrections (after a semantic-
preserving extraction of the original publication block). The backend negative
then also failed before its correction. Fixtures initially used a nonexistent
journal method and omitted the normal Engine incident envelope; corrected to
the actual `_automatic_safety_stop`/background export interface without removing
the original preservation assertion.

Final targeted selection: **329 passed**, including **30** new tests, actual
controller/backend output, both transmissions, two same-head red/hold/green cycles
with unusable unrelated actors, target loss, malformed roles, changing source
bytes, stale/identity/R/backend rejection, manual reactivation, rolling GPS
windows, packet-refresh cadence/worker regressions and existing combined/dense/
pedal export/first-fault integrity tests. Whole suite remains the user's check.

All **16 steering** and **12 longitudinal comfort** case metrics are exactly
equal to `oct9-freshness/*-continuation.json`. Comfort's first invocation lacked
the Windows PYTHONCASEOK setting and failed at SDK import before running; the
correctly configured run passed. `compileall` and `git diff --check` passed.

## Measured overhead — operation cost, not live packet latency

`tools/benchmark_oct10_traffic_contract.py`: 1,200 model ticks per variant, **60 s
modeled duration**, 20 Hz, 40 native-layout off-route actors. Actual decoder and
selector plus installed read/traffic-required/arbitration functions restored for
baseline; original inline publication reproduced explicitly. Real current
Policy/ACC/AP/Engine/Controller execute in both. Predetermined SDK speed/pose,
copying in-process IPC and BytesIO mapping are models; native scheduling/game
physics and disk export are **not** measured. No test-only unbounded write or
capture recorder contributes to retained runtime journal accounting.

| Complete modeled traffic → producer → physical boundary wall cost, ms | Baseline | Candidate |
| --- | ---: | ---: |
| p50 | 8.3151 | 8.4124 |
| p95 | 8.9427 | 9.0168 |
| p99 | 11.3834 | 11.3089 |
| maximum | 52.0414 | 54.8097 |

Difference: p50 **+0.0973 ms**, p95 **+0.0741 ms**, maximum **+2.7683 ms**.
One wall-time pair is not a bound or proof of improved tails. All control mapping
frames and IPC-read counts are **identical** for these valid inputs.
Retained journal detail: **63,895 → 60,951 bytes** / 65,536-byte budget;
summary history **297,109 → 297,110 bytes** / 1,048,576-byte budget.
Source-role/ID diagnostics use bounded fields, not full actor arrays per tick.

## Remaining uncertainty and deployment scope

Missing historical channel: the **exact required traffic input/coverage snapshot
compared at the first AP fault**, with original actor rows for its ambiguous IDs.
Do not ask for another drive merely to guess it; current exports and production
reproductions are exhausted. The priority receipt now preserves the compared
source fields in the existing automatic export. No new collection or drive is
requested or armed.

The source/native feed still lacks producer traffic timestamp/generation, joint
atomicity, certified actor LaneId/coverage and bumper distances. Reliable complete
ACC and universal autonomous junction passage remain NOT VERIFIED. An unassigned
real signal must still cause takeover, not silently authorize passage.

Changed runtime: `core/engine.py`, `core/acc_following.py`, `core/longitudinal.py`,
`core/navigation/longitudinal_diagnostics.py`. No plugin implementation/version
changed; changelog records a core unreleased correction only. The installed
packet-refresh five-file bundle remains intact, but any later deployment of this
new correction must coordinate **these four** source differences, after the
user's whole suite and separate approval. The old frozen bundle does not include
this traffic correction and must not be reused as its deployment plan.

**Conclusion:** shared availability/demand/fault-export defects are reproduced
and corrected offline. The original invalid-bit refusal is explained as a
required-read branch, but the precise first historical producer snapshot and
native ID cause are not recovered. No promise that this route now passes in
ETS2, or that all technical stops disappear, is made.

## Full-suite follow-up — 2026-10-10

The user's full run reported 3 failures, 2,196 passed and 1,592 subtests.
One failure exposed loss of the rejected unassigned signal's physical ID in
the priority fallback. The fallback now retains its fixed-field signal receipt
inside the unchanged 8 KiB budget; matching identities remain accounted once.
The existing full-flow emergency/coverage test again preserves head ID 999.

Two legacy stop tests expected driver handover after an expired or foreign
positive light-brake request. Positive demand is now required evidence; its
invalid lease is a technical rejection, not optional perception. The tests now
assert the exact source/cause and preserved positive demand, while retaining
inactive authority, zero propulsion and no pedal overlap checks. No control
decision or safety limit was weakened for these expectations.

Follow-up checks: 86 coverage/handover/traffic tests and 84 pairing/replay/history/
signal-cycle tests passed. Compile checks and diff whitespace checks passed.
The initial sandbox run failed at ViGEm import before test execution; checks
were repeated with permitted bus access. No deployment or game operation occurred.
