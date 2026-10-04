# Longitudinal leases and roundabout entry — 2026-10-04

## Build, scope and historical evidence

Entry HEAD: `e0be9ea155040b8d245c59802ab105a00b93bc29`; tracked tree clean.
This report covers the uncommitted candidate, not an installed release.
Previous joint lifecycle changes are preserved. No AGENTS.md was found in the
repository or checked ancestors; PLUGIN_VERSIONS.md and the previous lifecycle
report were read. No game, deployment, arm, commit or push was performed.

Read-only installed sources: ultrapilot.log, replay
`steering-replay-20261004T175124.240970Z-automatic_disable.json` and timing
`steering-timing-20261004T175230.628796Z-plugin_stop.json` in route-diagnostics.
Binding: session 1, map promods-1.59, dataset d6cc7936fce4e902761abb5d,
intent f46b0564aad04b5ab7aa67f9b12efb8a, revision 10,
build cef7e31f7dc0481a951fa3e012ece955, activation 11444765038700,
geometry 92fd7d7eaaabde1df4a4341427bfcd182172d9779b4de7d039448189fc8e9881.
Runtime times below are monotonic seconds; log wall time is UTC+2.

| Boundary | Time / budget |
| --- | --- |
| Inherited expiry | 11503.2997064; its 500 ms source-time origin is 11502.7997064 |
| AP vehicle observation | 11503.2246244 / frame 335819900; 424.918 ms after that origin |
| AP computation | 11503.2708851; 46.2607 ms after vehicle observation; only 28.8213 ms lease remains |
| First Engine rejection | 11503.3075058; decision age 36.6207 ms, observation age 82.8814 ms, lease exceeded by 7.7994 ms |
| Validity / context | valid=True, different_fields=[], all compared identities equal |
| Engine's newer vehicle read | Frame 335886564, time 11503.2954384; cannot renew an earlier consumed dependency |

Engine rejects first. Subsequent AP shutdown retains that reason. The failure
is an inherited input expiry, not proof of old vehicle telemetry or rerouting.
Replay calculation 1318 uses the exact source time 11502.7997064 / SDK 335403250:
Map start 11502.7730833, road preparation finish 11502.7892423, calculation start
11502.8055923, computation 11502.8063358, publication start 11502.8075101.
Sampled repeated reads persist through 11503.0481711. New calculations later
appear: 1324 observes 11503.2425709 and computes 11503.2544263.
Sampled reads are not first-delivery receipts; near the last tick, packet-read
RPC durations are submillisecond to a few milliseconds, not the entire chain.

**Historical uncertainty:** neither rejected command nor replay/timing retains
the consumed road/policy/ACC/traffic snapshots at the failing decision. No new
matching combined collection supplies them. The exact producer kind contributing
the minimum expiry cannot be uniquely identified, nor can the 46.2607 ms be split
into Policy, ACC, IPC and scheduling durations. Do not infer an OS lock stall.
The production defect below is independently reproduced with the exact budget;
it is not a fabricated retrospective identification of a road/traffic field.

## Installed-content audit

CRLF→LF normalization was applied; commit.txt was not used as implementation proof.

| File | Installed versus entry HEAD |
| --- | --- |
| core/engine.py | Real difference; matches cf25a97508aa1dfe4eb0917c5d6857583e45d87a |
| plugins/map/main.py | Real difference; matches that same earlier commit |
| plugins/autopilot/main.py | Same content; LF/CRLF only |
| core/longitudinal.py, plugins/drivepolicy/main.py, plugins/acc/main.py | Byte-identical before candidate edits |
| core/controller.py, core/service_brake_hold.py | Byte-identical |

The drive did **not** exercise the previous HEAD's Engine/Map joint repair.
Installed Engine SHA-256: 79c05b8325e87422043496923d06380289aa4d990553385ccf8aa11b5d5b752e.
Installed Map SHA-256: 570f0b930f0a63cecbe0759471121c2dc036e6b6c6f736b111a6af0f2630bc68.
All inspected hashes/matches are in the read-only receipt
docs/steering-audit/lease-runtime-audit-20261004.json. Its source hashes describe
the receipt-time candidate; subsequent edits are not installed hashes.

## Reproduced defect and repair

Original composition inherits the minimum expiry of every read map cap,
including a higher static road cap that does not constrain the desired speed.
A 60 km/h cap with 28.8213 ms remaining expires a fresh 50 km/h decision in transit.
The final Engine gate is correct to reject the resulting expired command.

Policy now includes valid requested cruise speed in its existing minimum
composition and retains leases of effective spatial constraints. ACC does not
inherit an irrelevant higher road cap's expiry; shared ceiling selection retains
the winning minimum and all tied winners. Static inputs are not made immortal:
reads still validate original frame/time/context, and effective lower caps retain
their original expiry. Previous actual-pose Map refresh is preserved.

Dynamic traffic evidence, required policy/ACC packets and curve evidence in ACC/AP
retain conservative leases. A missing target is not clear-road evidence. No
expired output is written, timestamp renewed, old throttle restored or continuous
brake interrupted to bridge a missing update. Engine's prewrite gate is unchanged.

| Reproduction through real producers and Controller/mapped backend | Before | Candidate |
| --- | --- | --- |
| Exact recorded delays, 60 road cap / 50 requested | Rejected: 82.8814 ms observation age / 7.7994 ms overrun | Original fresh observation; 417.1186 ms remaining lease, positive drive / zero brake |
| Same delays, effective road cap 35 | Expired lower constraint refused | Still refused, no throttle |
| Road cadence ≥520 ms, fresh SDK, 30 ms processing + 60 ms handoff/executor wait | False stop: 90 ms observation age / 10 ms inherited overrun | 1,300 iterations / 182 s continue; genuine 501 ms data loss still stops |
| Simple/real automatic, three red/wait/green/restart cycles >60 s each | Existing lifecycle retained | Continuous positive waiting brake, zero throttle, no additional N, no reverse edge or parking write |

## Roundabout ceiling and criteria

User criterion: at most 35 km/h at known entry, not a minimum or global ceiling.
Existing safety criteria: no paired positive pedals, immediate emergency
precedence, original leases and fail-closed identities. No physical jerk PASS
threshold is invented.

Map adds roundabout_entry_distance_m to the immutable longitudinal profile using
existing LanePath turn_events, kind=roundabout, directed start/end progress and
actual calculation progress. Only events within the real forward horizon qualify;
the cap persists through the event and ends after it. Ordinary prefabs and
untyped curves receive no roundabout label. No road edge or island is inferred.
This retains existing map semantic-classification limitations.

Policy and ACC combine the original curvature envelope with:

`usable=max(0, entry_distance -20 m -speed*1 s)`

`ceiling=sqrt((35/3.6)^2 +2*1 m/s²*usable)`

They also preserve lower road/posted/traffic/safety constraints. Curvature,
lateral controller, ramps, scheduler, original times and 500 ms limit do not
change. Progress is reused from the calculation; no extra projection or large
geometry IPC read is added.

Isolated additional Map metadata operation: 41 events, 3,000 calls, median
0.0026 ms / p95 0.0037 ms / maximum 0.0606 ms on this PC. This is operation cost,
not end-to-end cadence or a full live ProMods benchmark.

### Closed-loop same-input comparison

Command: `tools/run_curve_approach_bench.py --ref HEAD --roundabout` compares entry
HEAD with candidate. Real Policy/ACC/AP/Engine/Controller/mapped float writes;
R80 left/right path, 50 km/h initial speed, loads 1/1.4, 50 ms ticks or seeded
25/40/50/80 ms jitter. Explicit plant: 0.35 s actuator lag, 0.12 s command delay;
`a=(2.2*t-4*b)/load -0.12 -0.004*v²`; integration ≤10 ms. Entry progress s=200 m.
This is not calibrated ETS2 physics, clutch or grip proof. Semantic event is an
explicit offline fixture. Mean interval acceleration is Δv/dt; model jerk is the
consecutive mean-acceleration difference divided by actual dt.

| Load / tick (both directions) | Samples before→after | Entry km/h before→after | Brake begins, m before entry | First ≤35, m before entry | Max decel m/s² before→after | Max model jerk m/s³ before→after |
| --- | --- | --- | --- | --- | --- | --- |
| 1 / 50 ms | 325→364 | 46.495→33.569 | 7.427→68.040 | absent→24.000 | 0.890→1.073 | 2.994→2.207 |
| 1 / jitter | 328→366 | 48.207→33.552 | 20.464→66.721 | absent→23.906 | 1.162→1.074 | 4.217→3.268 |
| 1.4 / 50 ms | 327→364 | 45.860→32.988 | 13.506→67.211 | absent→19.377 | 0.907→0.952 | 2.099→2.569 |
| 1.4 / jitter | 330→367 | 46.282→32.926 | 22.545→68.544 | absent→19.479 | 0.890→0.971 | 3.642→3.361 |

All eight candidate entry cases meet ≤35 and have zero paired positive pedals.
The higher heavy-load regular-tick peak jerk is disclosed: not every comfort
quantity improves when enforcing a lower entry speed. The intentional benchmark
change is the semantic ceiling, not altered expectations to turn failures green.
Live entry speed, physical jerk and downhill/braking guarantees remain unverified.

Eight R19 comparisons preserve tighter curvature: entry 19.253–20.371 km/h,
largest entry difference <0.000001 km/h. Existing 16 steering benchmark cases
and 12 longitudinal-comfort cases are numerically identical to entry HEAD,
including model emergency reaction 0 s. They guard unchanged controller/model
behavior; they do not certify live CTE at the new lower roundabout speed.

## Validation, versions and verdict

- Before repair: exact-budget 60-cap production test fails; 35-cap refusal remains.
- Baseline Map profile fails the numerical 35 km/h producer criterion; candidate
  passes it, actual Map publication provenance and modeled physical entry.
- Targeted groups: 145 passed; 120 passed; focused final additions 13 passed.
  Groups overlap, so this is not a unique-test/full-suite coverage count.
- Final consolidated run: **283 passed**, selecting only the twelve relevant
  lease/lifecycle/arbitration/comfort/IPC/export/freshness regression files.
- Initial sandbox run hit Windows temp ACL PermissionError in fixture/cleanup.
  A targeted rerun with a new functional directory and permitted local IPC passed.
  The sandbox run is not presented as a passed run or a production defect.
- Full pytest is left to the user. `python -m compileall -q core plugins tools tests`
  and `git diff --check` both completed with exit code 0. The latter prints only
  Git's LF/CRLF conversion warnings, not whitespace failures.
- Changed versions: Map 1.0.6, DrivePolicy 1.0.4, ACC 1.1.2. AP 1.2.0 unchanged.

**Offline PASS: reproduced composition defect and modeled 35 km/h entry.
Live result and unique historical source attribution: NOT VERIFIED.**
The exact missing historical field is the immutable consumed input lease set
(producer kind, original time/frame, expiry) at that rejected AP decision.
Existing combined export already records it when enabled; no new system or
automatic extra collection/drive is requested.

## One future joint controlled verification (not executed)

After user's full suite and separately authorized consistent deployment, verify
content rather than commit.txt. Candidate runtime files: core/longitudinal.py,
plugins/map/main.py, plugins/drivepolicy/main.py, plugins/acc/main.py. Installed
older core/engine.py must also match the already committed lifecycle repair.
Preserve/verify rollback backups. Existing signal DLL/sidecar requirements are
unchanged; no DLL was modified here.

1. Prepare existing combined collection with UltraPilot off; start application
   and confirm increasing coherent SDK frames, identities and source-bound pedal
   writes before enabling control. Do not inject failures.
2. Clear level straight, valid route and transmission mode: one N, no manual
   throttle; verify forward gear and authority. Start before reaching red so
   the service-brake chain originates in forward motion.
3. Relevant red→continuous wait→fresh same locked-ID green→automatic restart,
   no parking brake. Already-stationary red activation remains driver-held/pending,
   not autonomous holding; do not count it as a successful selfholding test.
4. Approach a typed roundabout at ≤50 km/h; verify progressive reduction and
   ≤35 before entry (lower or stop is valid for tighter curves/traffic/yield).
   Include >60 s ordinary running and one short clear exit, without a hazard.
5. Immediately take over for R/backward movement, unexpected pedals, stale/foreign
   commands, loss of authority/backend or uncertain signal/hold. Do not force
   retries. Safely finish/export/inspect before shutdown; disable collection.

Review source leases, original SDK times, actual pedal writes, entry progress/speed,
first intervention, gear and later game observations. Returned writes are not
game-consumption acknowledgements. DLL brake semantics, slopes, signal direction
heuristics and traffic coverage retain existing limitations. No promise of
eliminating future genuine data/IPC/OS loss is made.
