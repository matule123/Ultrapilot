# Bounded longitudinal refresh response protocol — 15 October 2026

## Verdict and scope

The deployed validity-envelope fix was necessary but incomplete. This continuation
reproduces a different failure: the **zero-drive refresh command itself expires**
while a complete replacement can be published during consumer IPC. Receipt-time
recovery and the final physical-write gate did not share a complete response/token
lifecycle. The new counterexample fails on the receipt-verified deployed source
and passes through real production components after the core changes below.

This is **offline verification of specified races**, not proof that every
historical deadline miss is eliminated. In particular, the original incident did
not retain the initial refresh token or the publication/first delivery of the
complete replacement Autopilot command. Its availability before the fixed bound
is **NOT VERIFIED**. A missing replacement still correctly ends in a safe stop.
ETS2 outcome remains **GAME NOT VERIFIED**. Nothing is deployed or operated.

## Source and original evidence

- Starting tree was clean at `eab0026` (`fix: preserve command validity during
  traffic lease refresh`). No `AGENTS.md` was found in the repository or checked
  parent rule locations. `PLUGIN_VERSIONS.md` and the preceding handoff report
  govern this core-only continuation.
- All **31** installed deployment receipt entries and all **16** previous
  candidate payloads match their exact SHA-256 content. The receipt identifies
  `oct15-traffic-lease-v1`, installed at `20261015T052213563Z`; its SHA-256 is
  `f4b3e21d51d8979c578c2f397b0cba1f684dc4a8d66715244e94b817d4065a95`.
  Its old source marker plus local changes is not substituted for content proof.
- Previous candidate SHA-256:
  `e1ba8f3dc633f724fb198dc8324edfdc476aa38ebe7eea52383042a6870044aa`.
  It is retained, superseded for candidate review only, and remains the historical
  deployed evidence. LF/CRLF normalization is used for source-content deltas;
  actual deployment verification remains byte/hash based.
- Pedal incident:
  `C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics\steering-replay-20261015T115402.250913Z-automatic_disable.json`.
  SHA-256 `6476250b6ed0c3d1d0ac5298dff5e0f306574e080a685699127a85929b271a8f`.
  Existing `inspect_replay`/immutable codec validates integrity. The bounded
  incident is incomplete, `confirmed=false`, `runtime_authorized=false`:
  seven retained physical boundary events (one before rejection, six safety
  writes afterward) and 30.0706086 s summary history.
- Dense replay:
  `steering-replay-20261015T115403.607836Z-automatic_disable.json`, same session;
  integrity verified with the same codec, not by trusting mutable headers.
  `steering-timing-20261015T115443.657979Z-plugin_stop.json` and the full installed
  `ultrapilot.log` provide surrounding lifecycle context. Originals are untouched.
- Read-only decoder/hash inventory: `tools/analyze_oct15_refresh_timeout.py`.
  Derived evidence, original file hashes and decoded copies stay ignored under
  `docs/steering-audit/oct15-refresh-protocol/`, outside runtime payloads.

Identity: activation `375700661800`, game session `1`, map `promods-1.59`, dataset
`d6cc7936fce4e902761abb5d`, intent `83b03546f0d242e7884e3b806cd90bf3`, revision `8`,
build `617a20d0acc7455d8079e8fa69bae810`, lane-path geometry fingerprint
`58b68450075538424d5cafaad7897e8d7a766929575ad14d51d84645b7c8689a`.

## First causal boundary, not subsequent release telemetry

| Monotonic time (s) | Retained observation |
| --- | --- |
| 375.7539677 | One-N launch, simple-auto probe 0.12, frame 41515006, ratio 0 |
| 376.1138275 | Successful handoff, ratio 7, frame 41848326, throttle 0.14218488 |
| 408.8308673 | SDK observation used by the later zero-drive AP command, frame 74580350 |
| 408.9002076 | AP computes `decision_refresh`, throttle=brake=0; reason waiting for a new longitudinal decision |
| 408.9022674 | Actual compared vehicle observation, frame 74647014, ratio 9, speed 8.63824558 m/s, parking off |
| 408.9168766 | New ACC calculation, frame 74647014, expiry 409.3252566, throttle 1, brake 0 |
| 408.9203199 | New Policy calculation, same frame, expiry 409.3252566, brake 0 |
| 408.9413911–408.9417865 | Engine reads the older AP wait command |
| 408.9475395–408.9477668 | Engine reads that new ACC; validation after return 408.9477675 |
| 408.9537412–408.9543381 | Engine reads that new Policy; validation after return 408.9543387 |
| 408.9646251 | Wait command's fixed expiry, encoded as `unattributed_input/legacy_deadline` |
| 408.9661198 | First final-write check: wait expired by **1.4947 ms**, observation age **135.2525 ms**, decision age **65.9122 ms**, identical contexts, `valid=true` |
| 408.9690838 | Engine records the first technical intervention; immutable source retains the rejected zero command and actual consumed ACC/Policy |
| 409.0001025–409.0001156 | First retained safety throttle write, sequence 1199, acknowledged mapping value 0 |
| 409.0001844–409.0001945 | Safety brake sequence 1200, requested 0.21607575, mapping value 0.216075748 |
| 409.0438216–409.0438266 | Safety brake sequence 1202, mapping value 0.331294745; preceding throttle write remains zero |
| 409.0438608 | AP propagates the Engine cause, rather than independently proving another initial fault |
| 409.0847845–409.0847897 | Safety brake sequence 1204, mapping value 0.421362013; preceding throttle write remains zero |
| 410.2668478 | Later `release_all`, frame 75980294, observation 410.2336491; NOT evidence for the first comparison |

The last retained ordinary write at 408.8396495 used a decision computed at
408.4768118, expiry 408.8646251. The preceding summary write is at 408.3826:
there is an approximately 457 ms completion gap. The record does not isolate
CPU, IPC, scheduling or a particular worker as its historical cause.

The AP producer trace reports an ACC stale/incoherent input failure, but the
original rejected ACC packet and first request token were not retained. The
deadline arithmetic suggests an earlier dependency deadline; it does **not**
identify its original producer. New ACC/Policy are proven available during the
Engine read above; they are insufficient to invent a new complete AP decision.
The old final gate never attempted to obtain that complete owner response.
The acknowledged zero brake at 408.9631725–408.9631837 (sequence 1198) is the
opposing-channel release immediately before rejection, not proof of a continuous
service-hold failure. The subsequent mapping acknowledgements prove software
writes only; none is marked game consumption. Command-read RPC took 0.3954 ms,
ACC read 0.2273 ms and Policy read 0.5969 ms. The 24.3333 ms between command
return and final check includes other operations; it is not all IPC. Likewise,
the 30.8902 ms from ACC calculation to this sampled read is not first delivery.

## Implemented protocol and safety invariants

1. A request carries a deterministic bounded token derived from activation/route
   context and its exact original deadline basis. It retains the rejected
   decision, source, start and **original expiry + existing 100 ms** bound.
   Repeated stale candidates cannot restart that bound.
2. AP's existing shared finalizer attaches a compact pending/response receipt.
   Pending commands identify `bounded_refresh` when the request is the actual
   limiting deadline. Earlier vehicle or emergency evidence deadlines remain
   the real basis; the protocol receipt separately describes the fixed wait.
3. Both receipt and final-write recovery follow the original cause, rather than
   trying to refresh the zero command's synthetic legacy deadline. On expiry,
   Engine may read **one** actual complete AP command and pair it with at most
   one actual newer truck snapshot. It reruns the whole existing executor:
   navigation, SDK validity, activation/route, transmission, service hold,
   arbitration, opposing-channel release and the final physical gates.
4. A replacement must be a fully valid, newer complete owner decision that
   supersedes the original expiry and was computed within the fixed response
   bound. A response computed just before the consumer creates its request is
   validatable too; adding a request token retroactively is not necessary or
   allowed. The immutable source command is never rewritten. Receipt provenance
   identifies the observed association separately.
5. Only a successful current physical application acknowledges the token, in a
   separate single acknowledgement slot. It cannot erase a concurrently published
   next request. A subsequent distinct causal renewal can start; an unchanged old
   dependency cannot extend a wait. Context changes and manual cancellation
   cannot reuse prior authority. A full response genuinely missing the fixed
   computation bound fails explicitly and latches the first fault.
   The first actual timely full-response publication is retained in one small
   response slot across later AP ticks. One publisher-local qualified publication
   receipt covers the case where the request is created after publication.
   Neither is a control lease: a later current command must pass all its own
   input/identity/SDK/physical checks. Repeated publication never refreshes an
   observation or extends the original response bound.
6. During waiting there is no expired drive. Existing verified forward-started
   continuous service braking remains owned by its physical chain. R, backwards
   motion, invalid SDK, foreign identities, true lease loss and backend faults
   remain protected. Current urgent traffic still bypasses zero-drive renewal or
   the ordinary technical-loss brake ramp. No parking-brake controls are added.
7. Fixed-size `refresh_protocol`, response-attempt and exact compared-pair
   evidence use the existing journal, immutable replay and bounded fault codecs.
   Historical codec key tables are unchanged. No new collector, worker, disk I/O
   in control, per-tick INFO logging or increased memory allowance is introduced.

The only runtime source changes are `core/longitudinal.py`, `core/engine.py` and
`core/navigation/longitudinal_diagnostics.py`. No plugin implementation changes:
ACC **1.3.2**, DrivePolicy **1.1.4**, AP **1.3.4**, Map **1.1.2**, TurnSignals
**1.0.2**, native **1.59.4-up-traffic-timed** remain unchanged. Steering geometry,
controllers, 5 m signal offset, original SDK metadata and 500 ms limits remain.

## Counterexamples and integration

`tests/test_oct15_refresh_protocol.py` uses real native bytes/TrafficReader,
directed selector, real Map publication, Policy, ACC, AP, Engine and SCS Controller
with a chronological byte-mapping backend. It is a modeled SDK/scheduler, not
measured game input consumption or vehicle physics.

- **Before runtime edits:** eight new counterexamples fail on the exact deployed
  source: receipt/steering/binding races in both modes and missing causal token.
  Evidence: `before.log`. These are different from the preceding ten fixes.
- The final test also covers repeated tokens/new causes, a response published
  before request creation, ack/publication race, fixed timeout, late reply,
  missing/old/future/foreign data, R, invalid SDK, cancellation, backend loss and
  original-cause automatic export/readback. No expectation is weakened.
- Final review reproduced two additional failures in the intermediate candidate:
  a timely complete reply could be overwritten by a subsequent AP tick before
  Engine acknowledged it, falsely becoming a timeout. The retained publication
  witness above fixes that lifecycle gap. `overwritten-response-before.log`
  records both failures; the input has a genuine timely publication, whereas the
  separate late-response rejection test deliberately withholds that publication.
  The obsolete partial `full-suite-v1.log` was stopped before changing runtime
  again. It is retained, has no successful verification receipt and cannot
  authorize packaging. Only the final complete run counts below.
- The disconnected-backend test explicitly does not claim a successful zero
  write to an unavailable mapping. It asserts no new positive write, revoked
  drive intent and the explicit fault; stale mock buffer bytes are not an ack.
- **309 targeted tests passed** in 61.12 s after the final runtime changes, including prior initialization,
  frame-ahead pairing, repeated launches, signal red/continuous hold/green,
  ACC/departure and immutable automatic/combined export regressions. The previous
  broad run found one over-budget full-identity receipt; additive absent `None`
  fields were removed and the exact bounded codec retained. Its safety/data
  expectations are unchanged.
- Independent cadence tests use SDK 33.333 ms, Map 360 ms, traffic 460 ms, Policy
  59 ms, ACC 23 ms, AP 26 ms and Engine 16.667 ms with copying RPC delays/phases.
  Their ordinary/nonbinding case is regression coverage, not proof of the newly
  discovered causal branch. The separately staggered renewal stress below covers
  that branch with actual timed native traffic.

Final complete-suite verification: **2,705 passed, 1,592 subtests passed in
645.83 s**. `full-suite-v2.log` is bound to before/after hashes of all **16**
candidate runtime/dependency payloads by `full-suite-v2.verified.json`.
Log SHA-256: `8b9296de77a78b1f6195ceb0d2a84e01faa127bcde6f2a80aa89e295bb971729`.
The interrupted v1 run is not a PASS and is never used for packaging.

Afterward, `python -m compileall -q core plugins sdk tests tools` passed with an
empty diagnostics log, and `git diff --check` passed. Final `steering-final.json`
and `comfort-final.json` again match all 16/12 preserved baseline case dictionaries
exactly after the last runtime change. No existing safety expectations were weakened.

## Paired repeated-renewal model and performance

`tools/benchmark_oct15_refresh_protocol.py`, `paired-stress-final.json`: frozen
`eab0026` versus candidate, two repeats per automatic mode and capture off/on.
Traffic, ACC, Policy and AP execute at separate causal phases; a complete AP
publication is delivered during steering IPC and the captured wait crosses its
fixed expiry by the incident's **1.4947 ms**. The observed speed is held at 3 m/s:
this is an execution/ownership test, not closed-loop physics or comfort evidence.

| Property | Deployed baseline | Candidate |
| --- | --- | --- |
| Distinct renewal recoveries per run | 0; first case faults | 125 / 125 |
| Duration per run | 0.6348 s, stopped at first failure | 79.3535 s |
| Eight runs combined | 8 first-case technical failures | 1,000 recoveries, 0 technical failures |
| Invalid normal pedal writes / simultaneous positive pedals | No expired drive accepted | 0 / 0 |
| Background replay exports, capture on | Failure before scheduled export | 3 per run, integrity checked |
| Full new-decision publication lease, min/p50/p95/p99/max | No successful recovery | 498 / 498 / 498 / 498 / 498 ms |
| Response read and physical-write lease, min/p50/p95/p99/max | No successful recovery | 483.838 / 485.838 / 489.838 / 489.838 / 489.838 ms |
| Actual observation age at matched write, p50/p95/p99/max | No successful recovery | 14.162 / 16.162 / 16.162 / 16.162 ms |
| Detail journal retained payload | Separate failure evidence | At most 61,592 bytes; unchanged 65,536-byte limit |

Response-read samples are exported only with diagnostics on; off is explicitly
missing, not assigned zero. Final write receipts provide ages/margins in both
cases. No first-delivery time is inferred from sampled reads.

Candidate recovery flush wall time (ms), each row n=125:

| Mode/capture/repeat | p50 | p95 | p99 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Simple/off/1 | 3.3772 | 3.8470 | 6.0346 | 10.3946 |
| Simple/off/2 | 3.3291 | 3.6973 | 4.8075 | 9.8023 |
| Simple/on/1 | 6.1832 | 6.4621 | 6.7300 | 6.8487 |
| Simple/on/2 | 6.2039 | 6.5329 | 6.9256 | 7.1087 |
| Real/off/1 | 2.6732 | 2.9780 | 3.9099 | 9.1099 |
| Real/off/2 | 2.6994 | 3.0647 | 4.0472 | 9.6258 |
| Real/on/1 | 5.4725 | 5.7938 | 6.0955 | 6.2829 |
| Real/on/2 | 5.4599 | 5.6692 | 5.8684 | 6.2712 |

Do not compare one baseline failure flush against 125 candidate flushes as a
latency improvement. Equal-length ordinary comparisons (200 post-warmup flushes,
two pairs each) retain identical pedal-output hashes. Baseline/candidate p50
ranges are **0.8305–0.8461 / 0.8239–0.8304 ms** off and
**1.9319–1.9340 / 1.9332–1.9387 ms** on. Maximum ranges are
**9.0349–10.7323 / 1.0559–1.3954 ms** off and
**12.3123–19.4460 / 12.4266–12.9704 ms** on. Small median changes do not establish
an improved maximum. Raw p95/p99 and CPU distributions are retained in JSON.

CPU clocks on this Windows runtime quantize process time in 15.625 ms steps:
many flush p50 values are zero at that resolution, **not zero CPU work**.
Recovery flush CPU p95/p99/max are 15.625 ms in the controlled runs. Total process
CPU includes native-byte fixtures, deepcopy/RPC doubles and export workers.
Model IPC phase time is not measured OS blocked time; no subtraction of coarse
process CPU from wall is called pure wait.

An earlier intentionally untrimmed mock-history run is retained as
`paired-stress-v2.json`: it observed recovery maximum 114.864 ms and ordinary
maximum **121.9485 ms**. The refined repeat collects old fixtures before each
case and clears only the fake `unittest.Mock` monotonic call journal between
cycles, outside control; runtime GC is not disabled or changed. GC callbacks
record real spans in each final case's `slow_flushes`. The earlier v3 refined
repeat's slowest off recovery flush overlaps 7.524 ms GC within 11.0532 ms;
the final repeat's largest measured GC collection is 8.5557 ms (not necessarily
inside a measured flush), and its worst recovery flush is 10.3946 ms.
These measured harness facts are **not retroactive attribution** of the old
93/134 ms extremes or this game's 457 ms gap. Production scheduling tails remain
unproved by this model; maxima are retained rather than hidden by medians.

All **16 steering** and **12 longitudinal comfort** benchmark case dictionaries
are numerically identical before/after. This protects the unchanged controller
models, not ETS2 comfort, collision certification or physical jerk calibration.

### Actual Manager IPC operation check

`--manager-only`, `real-manager-final-v2.json` replaces all production SDK views
with a real `multiprocessing.Manager` process and meters actual proxy roundtrips.
It executes 20 repeated response races in each mode through the same reader,
producers and physical mapping. Baseline fails its first case in both modes;
candidate recovers **20/20** in each, with zero recorded invalid drive writes.

| Candidate mode | Flush p50/p95/p99/max (ms), n=20 | RPC p50/p95/p99/max (ms) | RPC operations |
| --- | --- | --- | ---: |
| Simple | 20.9326 / 22.5264 / 22.6812 / 22.6812 | 0.0459 / 0.1254 / 0.2076 / 0.8402 | 23,273 |
| Real | 18.6636 / 19.6944 / 20.2109 / 20.2109 | 0.0456 / 0.1232 / 0.2006 / 0.9472 | 22,713 |

The first baseline's cold proxy includes a **52.4896 ms** maximum roundtrip;
the second baseline maximum is 0.5120 ms. These are retained, not silently
discarded, and unequal run lengths/cold states prohibit a throughput improvement
claim. RPC wall includes transport, server work and scheduling, not pure blocked
time. The server is real; the source/scheduler clock is still modeled. This
check does not prove game scheduling or locate the historical completion gap.
An initial harness attempt failed to spawn a picklable Manager after fixture
Pool stubs; the successful run starts the real server before fixture imports.
No production IPC/scheduler change was made to accommodate that harness issue.

## Candidate and remaining gate

The candidate preparer is `tools/prepare_oct15_refresh_protocol.py`; it refuses
nonzero/mismatched complete-suite receipts or source content changed after that
verification. It rechecks the installed base and every ZIP payload after readback.
The payload is the consistent existing 16-file runtime dependency set plus
manifest; the content delta is the three core files and English changelog.
There is no DLL, test, report, settings/cache, commit marker or raw-data payload.
Every installed base hash and unchanged native dependency is bound in the manifest.

Deployment still requires separate approval, both applications stopped and a
whole-set rollback backup. Existing records are never overwritten. The existing
eight-file significant-event quota remains full; that separate archival issue
does not suppress the priority automatic fault incident or authorize deletion.

No new drive is requested here. The precise remaining historical evidence gap is
the original first refresh request and the complete AP response publication/
receipt relative to its bound. New existing automatic incidents now preserve
that compact protocol/attempt, both compared command and SDK pairing, first
cause and subsequent safety writes. A future separately approved game check can
evaluate the deployed candidate; this report makes no game success claim.

## Final candidate and changed files

**OFFLINE VERIFIED:** the described bounded response protocol, its negative
cases, current integration/simulation scope, actual Manager operation check and
complete suite. **GAME NOT VERIFIED:** all new behavior in this candidate.
The first historical response availability and initiating scheduling operation
remain **NOT VERIFIED**, not silently relabelled resolved by offline success.

Candidate (prepared only, not installed):
`docs/steering-audit/oct15-refresh-protocol/ultrapilot-oct15-refresh-protocol-candidate-v1.zip`,
**187,212 bytes**, 16 payloads plus manifest. Every payload was SHA-256 checked
against the successful complete-suite receipt and rechecked after ZIP readback.
ZIP SHA-256: `fe2163404bb7d49f481cdc57732a3c2da054eec3cbb87a6824cd8eda3c98500b`.
Sidecar: `ultrapilot-oct15-refresh-protocol-candidate-v1.manifest.json`.

Content changes versus the installed normalized source are exactly:
`core/engine.py`, `core/longitudinal.py`,
`core/navigation/longitudinal_diagnostics.py`, `PLUGIN_CHANGELOG.md`.
The complete dependency payload also retains unchanged core `acc_acceleration`,
`acc_body_prediction`, `acc_following`, `control_timing`, `pid`,
`service_brake_hold`, navigation `traffic_producer`, SDK `traffic_snapshot` /
`scs_sdk`, `telemetry`, and ACC/DrivePolicy entry points. Unshipped plugin/native
dependencies are bound to the 31 exact required base hashes. DLL and commit
marker are not replaced; local uncommitted status is explicit in the manifest.

Workspace changes:

- Runtime: the three core files above.
- Regressions: `tests/test_oct15_refresh_protocol.py` (42 new parametrized cases).
- Tools: `tools/analyze_oct15_refresh_timeout.py`,
  `tools/benchmark_oct15_refresh_protocol.py`, `tools/prepare_oct15_refresh_protocol.py`.
- Documentation: this report, `PLUGIN_CHANGELOG.md`, `DEFERRED_WORK.md`.

No commit, push, installation, game control, diagnostic arming or original-data
change occurred. No further drive is requested. Candidate review and any future
deployment remain separate from this offline verification.
