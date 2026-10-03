# Longitudinal commit and curve-approach regressions — 2026-10-03

## Scope and verdict

**Offline reproduced defects corrected; live correction NOT VERIFIED.** Engine
selected a leased pedal decision before potentially slow navigation/IPC work.
Curve discovery and the speed PID did not consistently use the existing
curve-entry braking envelope. These are reproduced production-code defects.
The exact rejected pedal packet and failed predicate were not retained in the
two historical incidents: this report cannot prove that both had the same cause.

Entry HEAD: `b9fb48419411bd74f2373dcf20c1b40f2f8bb30a`, clean tracked tree.
Project instructions were searched; no applicable AGENTS.md was available.
Phase 7 reports, deferred work and plugin-version rules were read. All changes
are local, uncommitted and undeployed. No game operation, arming, full pytest
run or original diagnostic modification occurred.

At entry, installed Engine, longitudinal core/diagnostics, Map and Autopilot
matched source after LF/CRLF normalization. Present files do not establish
every historical process's loaded modules. Versions now change only for Map
1.0.2→1.0.3, DrivePolicy 1.0.2→1.0.3 and ACC 1.1.0→1.1.1. Autopilot 1.0.2
retains its valid-input envelope numerics through delegation to shared code.

## 1. Evidence and historical limits

Source root: `C:\Users\PC\AppData\Local\Programs\UltraPilot`.

| Replay in route-diagnostics | SHA-256 | Samples / execution rows |
| --- | --- | --- |
| steering-replay-20261003T150356.244666Z-automatic_disable.json | `66d3ac28dcd1516bdf4637a5326c2f1535abd29521f1c45f5789a7eaa3c5c090` | 379 / 10,800 |
| steering-replay-20261003T150650.916049Z-automatic_disable.json | `815bd0719ba90294342cf7a0883b0c885a3293715c99ae83197ab8a09437fe01` | 417 / 3,247 |

| Identity / event | First incident | Second incident |
| --- | --- | --- |
| Intent | 94e2206ddb5541399f0ba653662649d5 | 3b417db84fbf48c5a823f2ce382abac4 |
| Revision | 10 | 8 |
| Build | 580f5496e61b4afe99e3471bdb9e0a45 | 38e00a599ba84695b35124daad8e2edc |
| Session / map / dataset | 1 / promods-1.59 / d6cc7936fce4e902761abb5d | Same values |
| First logged navigation-authority loss | 17:03:54.296 | 17:06:50.087 |
| Final automatic disable | 17:03:56.009 | 17:06:50.858 |
| Reason | longitudinal command expired or identity changed before write | Same generic reason |

The final disable time is not the first fault time. Both replays have **zero
immutable executor.source_packet objects** in execution rows. Current headers
cannot establish older physical-pedal provenance. The rejected decision's
observation, expiry, activation token, geometry fingerprint and comparison
context are NOT RECORDED. Historical longitudinal publication, ACC/arbitration
and lock-wait times are also NOT RECORDED. Expiry versus identity cannot be
resolved from the generic error text.

Collector phase7-longitudinal-20261003-152818 has status CANCELLED /
APPLICATION_STOPPED_BEFORE_FINISH: **0 samples**, 4 dropped, 1 skipped duplicate,
81 paused, 30 identity skips. No corresponding collection export exists.
Missing samples and rejected values were not reconstructed by invention.

### Same-identity sampled steering timing

Milliseconds, active identity-matching reads only. These are sampled Autopilot
reads, **not first delivery or longitudinal backend-write times**.

| Timing file / metric | n | Median | p95 | p99 | Max |
| --- | ---: | ---: | ---: | ---: | ---: |
| 150547.042108Z-plugin_stop: observation age at read | 40 | 45.777 | 78.381 | 224.110 | 224.110 |
| Same: observation→computation | 40 | 22.271 | 35.703 | 48.086 | 48.086 |
| Same: computation→sampled read | 40 | 19.724 | 51.571 | 204.141 | 204.141 |
| 150755.115488Z-plugin_stop: age at read | 42 | 42.375 | 76.125 | 133.558 | 133.558 |
| Same: observation→computation | 42 | 19.852 | 37.997 | 40.145 | 40.145 |
| Same: computation→sampled read | 42 | 20.293 | 48.853 | 115.565 | 115.565 |

Valid steering samples do not prove freshness of the separately rejected pedal
packet. Historical packet/writer age and contention remain unverified.

## 2. Physical-commit reproduction and correction

Baseline Engine selects engine_decision before navigation validation, IPC reads,
steering preparation and transmission checks. Producers may advance during
that work. The final write check then rejects the earlier captured command
even when a newer complete valid command is available.

The production-flow regression uses real Policy/ACC/Autopilot, Engine and
Controller with an isolated SCS float mapping. The initial command is 200 ms
old; navigation preparation takes **369 ms**, while producers process three
new SDK frames. Baseline attempts its old selection at **569 ms** and stops.
Candidate selects the latest actual command after preparation at **0 ms logical
selection age**, continuing with its embedded observation timestamp. This is
controlled scheduling, not a live latency measurement. A real RLock wait is
separately tested with continuing producers and selection after acquisition.

Engine now prepares navigation/steering first, reads one actual vehicle snapshot
and validates its original metadata, then selects current immutable pedals.
No timestamp, identity or lease is renewed; no retry loop is introduced.
The final identity, observation and upstream-expiry checks remain before pedal
writes, with clock sampling after the final context IPC read. Separate reasons
now identify identity/activation, observation age/coherence, or input lease.
A fault occurring after arbitration still fails closed.

The existing lock/single physical writer remain. No export/disk work or growing
queue was introduced under the lock. Genuine delays beyond a command lease
must still stop rather than authorize expired drive.

## 3. Braking evidence and planning mismatch

Second-session requests, not independently attributed physical backend brakes:

| Time 17:06 | Speed km/h | Radius m | Sampled curve distance m | Curve limit km/h | AP brake | Curve brake | Auxiliary brake |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 42.405 | 50 | 228.0 | 60 | 80.7 | 0 | 0 | 0 |
| 43.429 | 50 | 56.8 | 60 | 50.2 | .079 | 0 | .079 |
| 44.422 | 38 | 20.5 | 60 | 35.2 | .146 | .146 | 0 |
| 45.469 | 26 | 19.0 | 56 | 34.5 | 0 | 0 | 0 |
| 46.467 | 32 | 19.0 | 48 | 30.6 | .083 | .083 | 0 |
| 47.488 | 24 | 19.1 | 40 | 28.1 | 0 | 0 | 0 |
| 48.536 | 26 | 18.7 | 32 | 23.7 | .100 | .100 | 0 |
| 49.547 | 18 | 18.9 | 24 | 21.0 | 0 | 0 | 0 |

Traffic/light/collision demands were zero in this approach. Distance is to the
existing sampled directed curve, not a measured curb or free-space boundary.
Rejected target/winner/physical pedal values are not inferred from these rows.

Reproduced defects:

1. A fixed **60 m** Map query cannot discover R19 in time for the existing
   braking envelope at 50 km/h. Unchanged assumptions: 1.8 m/s² lateral speed,
   1 m/s² approach deceleration, 1 s response, 20 m setup. Required distance
   is **113.24 m**.
2. At R19 / 80 m / 50 km/h, Policy permits **61.33 km/h** while Autopilot's
   reserved-distance envelope permits **40.48 km/h**. ACC can power toward
   the higher target as the separate curve-brake demand releases.

Correction: Map queries existing directed geometry with a braking-distance
horizon (**134.34 m** at 50 km/h). Requested-speed retention prevents shrinkage
from dropping an upcoming curve while slowing. Query is capped at 400 m and
clipped to real remaining geometry. Policy and the existing ACC PID use the
same original Autopilot envelope; ACC inherits the curve lease. Safe curve
speed remains. No additional regulator/filter or emergency delay was added.
Planning assumptions are not measured adhesion or a vehicle brake model.

## 4. Same-input closed-loop comparison

Acceptance encoded before changing production behavior: fresh available commands
continue and genuinely stale/foreign commands reject; the query covers its own
existing braking envelope; curve targets agree; earlier braking with no faster
entry/no entry overspeed and lower modeled deceleration/jerk; exclusive pedals.
No new game-comfort PASS threshold is invented.

Reproduce with tools/run_curve_approach_bench.py, baseline classes loaded from
b9fb484 without modifying the checkout. Real producer/Engine/Controller pedal
operations use the isolated mapping. Production Route queries a 200 m straight,
R19 quarter-circle and exit; SDK/steering authority is a test harness.
Initial/requested speed 50 km/h. Plant:
`a=(2.2*throttle-4*brake)/load-0.12-0.004*v²`, actuator 0.35 s, delay 0.12 s,
integration at most 10 ms. Jitter decisions 25/40/50/80 ms, seed7103.
Lateral tracking is assumed perfect: no CTE, adhesion or physical-clearance
proof. Jerk uses interval-average model acceleration differences divided by dt.

Eight paired cases / 16 runs; left and right have identical longitudinal metrics.
408–453 samples, approximately 20.4–22.1 s per run.

| Load / jitter | n before/after | Brake start distance before/after m | Entry km/h before/after | Peak decel m/s² before/after | Peak modeled jerk m/s³ before/after |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 / no | 413/441 | 60.90/86.43 | 20.83/19.25 | 2.713/1.147 | 5.367/1.184 |
| 1 / yes | 423/453 | 61.25/83.91 | 20.78/19.27 | 2.711/1.126 | 7.114/1.505 |
| 1.4 / no | 408/435 | 60.97/84.04 | 21.05/20.37 | 2.174/.968 | 4.149/1.337 |
| 1.4 / yes | 419/447 | 60.62/78.43 | 21.06/20.14 | 2.172/1.011 | 5.069/1.767 |

Candidate entry overspeed and simultaneous positive pedals: **zero in all cases**.
Baseline maximum entry excess .0093 km/h in this model. A gentler approach can
increase travel time and undershoot entry target slightly; no universal comfort
claim follows from the simplified plant.

## 5. Diagnostic integrity, cost and verification

A joint producer diagnostic source exceeded the fixed 32 KiB accounting budget
(34,752 bytes), retaining only an unverified marker. Missing fields now appear
explicitly in an `unavailable_fields` comma-separated list instead of repeated
null entries; scalar ceiling metadata no longer duplicates producer bodies
already stored under inputs. Byte/node/depth limits remain unchanged.
The regression retains the selected SDK frame/time and actual mapping-write
result. Mapping-write return is not confirmation of game consumption.

| Isolated operation | n | Median ms | p95 | p99 | Max |
| --- | ---: | ---: | ---: | ---: | ---: |
| Route query: baseline60 m | 300 | .0464 | .0536 | .0864 | .4264 |
| Route query: candidate134.34 m | 300 | .0993 | .1155 | .1749 | .2117 |
| Manager producer publication | 100 | 1.4977 | 1.8945 | 1.9563 | 1.9568 |
| Manager paired publication | 100 | .3864 | .6207 | .6408 | .8924 |
| Manager Engine arbitration | 100 | 1.5150 | 1.8835 | 1.9898 | 2.0091 |
| Combined measured Manager operations | 100 | 3.6061 | 3.9077 | 4.2967 | 4.5471 |

Operation cost is not live end-to-end cadence or historical lock-wait time.
Corrected live packet intervals/consumption ages remain NOT VERIFIED.

- Baseline methods: **3 failures before correction**, late selection, wrong
  curve target and insufficient horizon.
- Targeted integration: **333 passed, 17 subtests passed**. Four subsequent
  final-check/closed-loop additions bring the new test file to **17 passed**
  on its separate final run. No full suite was run.
- Cases include both automatic modes, launch/stop, ACC/emergency, rolling
  windows, stale/R/backwards/manual/identity, delayed producer delivery,
  lock wait, final-write expiry and diagnostics on/off.
- Steering benchmark: all **16 cases numerically identical** to entry HEAD.
- compileall and git diff --check passed. Initial pytest temp PermissionError
  and Manager pipe WinError5 were environmental; targeted runs passed outside
  those restrictions with an ignored unique basetemp.
- Raw JSON and temporary outputs remain ignored under docs/steering-audit.

## 6. Files, remaining evidence and next gate

Runtime: core/engine.py, core/longitudinal.py,
core/navigation/longitudinal_diagnostics.py, plugins/map/main.py,
plugins/drivepolicy/main.py, plugins/acc/main.py, plugins/autopilot/main.py.
Reproduction: tests/test_longitudinal_commit_and_preview.py,
tools/run_curve_approach_bench.py. Documentation: this report,
PLUGIN_CHANGELOG.md, PHASE7_FINAL_RESULTS.md, DEFERRED_WORK.md.
No lateral controller, Route geometry, steering calibration, limiter or
freshness threshold changed. Transmission launch and R protections remain.

Historical missing proof: **the rejected immutable longitudinal decision with
its final context and comparison time**. Absent samples/null replay sources
cannot supply it. No further drive is requested. User full-suite verification
precedes any separately authorized deployment. Live behavior remains unverified.

Proposed commit: `fix: commit fresh pedal decisions and anticipate curve braking`.

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python -m pytest tests -q
```
