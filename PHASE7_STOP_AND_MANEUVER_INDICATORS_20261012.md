# Qualified stop approach and selected-exit indicators — 12 October 2026

## Verdict

**OFFLINE VERIFIED for the reproduced conflicting brake ownership, unused
positive integral and premature hold transition. GAME NOT VERIFIED.** The
unchanged planning target is approached more closely in the default and delayed
plants. Exact convergence and bumper-to-painted-line clearance are **not closed**.
An idle-drive sensitivity case does not meet the no-regression comparison; it
must not be presented as a universal improvement or readiness certification.

This continues the terminal-approach work rather than moving its target. The
existing 6 m front allowance plus 2 m stand-off remain unchanged. The stationary
comparison's +2.3377 m offset remains inactive. A vehicle already holding on red
is never released just to recover missing metres. No parking-brake operations,
steering changes, DLL changes or freshness-limit changes were made.

## Source, installation and retained evidence

Base HEAD is `787d012a2a78ac917bb5506e0958c32d8d06575f` plus preserved local
changes. Project versioning rules and the stop-line, stationary-comparison,
red-approach, joint-traffic and terminal-approach reports were read. No AGENTS.md
was found in the checkout or checked parent directories.

The installed `terminal-joint-20261012T124232464Z` receipt contains 22 runtime
files. Their installed SHA-256 values matched the receipt at entry; source and
installation matched after LF/CRLF normalization before this candidate. Commit
markers alone were not used as content evidence. The new candidate remains
uncommitted and undeployed. Earlier 2,401-test full-suite success belongs to the
installed preceding correction, not this candidate.

All five requested Oct 12 replay/incident files passed the existing immutable
codec integrity check. Originals were untouched. The main dense replay is
`steering-replay-20261012T132351.978039Z-automatic_disable.json`, SHA-256
`c374ca1c64fbee1b36178ccb5d108a1215d079679c5eedf495cb825b88f0fd36`.
Its approach identity is activation `2718943984800`, session `1`, intent
`e6beffbd839c4bb1834dbbba9bbea8d6`, revision `5`, build
`f63a8a59304e4171bc1b6e1b5d37620b`, dataset `d6cc7936fce4e902761abb5d`.
The relevant authored passage is
`45540e750098d8f1fc11bc8b76cd20b1ae161420a94ae48b90dad1891389062f`.

The Oct 11 2.5514 m residual alone does not prove a particular software fault.
The newer retained immutable summaries expose the following narrower chain:

| Monotonic time (s) | Speed (m/s) | Remaining planning distance (m) | Consumed/output evidence |
| --- | ---: | ---: | --- |
| 2763.3376 | 0.9861 | 3.2805 | Positive 1.898 m/s ACC ceiling; coast |
| 2763.6121 | 0.9885 | 3.0340 | Still approaching with positive ceiling |
| about 2763.689 | about 0.99 | response-band boundary | Separate Traffic brake commits braking phase |
| 2764.2726 | 0.621 | 2.4485 | light_brake 0.03434; external braking resets speed control |
| 2764.4247 | 0.4805 | 2.3568 | Traffic brake becomes zero; ACC requests drive, Engine retains brake |
| 2764.5018 | 0.4081, gear 0 | 2.3196 | Held brake prevents requested approach drive |
| 2764.912 | 0.0211 | 2.2309 | Holding; later retained brake 0.095447 |

100 held summary rows span 2764.9995–2780.8649 s with residual
2.23097–2.23170 m, zero throttle and the same locked signal. These summaries
retain consumed inputs and selected outputs, but are marked capture_incomplete.
The early individual pedal receipts have aged out of the short journal. They
are **not** reconstructed as exact historical write chronology or game input
consumption. Subsequent engine-off/launch failures are outside this change.

## Reproduced causes and corrections

1. Engine previously added a Traffic light brake inside `v*1.5 + 1.5 m` while
   the qualified stopping speed envelope remained positive. ACC treated that
   competing brake as external control; the service-hold state latched a brake
   before the planned approach was exhausted. Now a valid observed qualified
   signal with active ACC has one distance-profile owner until the envelope is
   exhausted. Missing qualification, other brake sources and emergencies remain
   protective; a map ID or missing head is not clearance.
2. `signal_speed_control.terminal` used the same broad band. It now describes
   actual exhausted-envelope authority. A separate shared `brake_chain_required`
   flag retains the existing slow-speed/1.5 m terminal write contract. Only an
   acknowledged positive physical write can commit continuity there. This avoids
   both premature broad-band holding and a newly exposed gear-zero rejection
   after a legitimate first slow brake. No new standstill brake authority exists.
3. PID positive integral accumulated for throttle that a qualified signal coast
   never executed. ACC discards only that unused positive integral; negative
   unwinding, derivative memory and ordinary cruise operation remain. An attempted
   broader coast-band change was discarded because it added reversals/jerk.

Before correction, full production-flow counterexamples fail on independent
Traffic brake, premature hold and positive integral despite zero executed drive.
After correction they pass through actual reader, Policy, ACC, Autopilot, Engine,
Controller and recorded backend writes in both gearbox modes. A subsequent suite
run exposed a genuine slow-brake phase regression; the shared acknowledged-write
correction above fixed it without removing the original safety expectations.

Some earlier terminal fixtures forced standstill without moving the SDK pose:
50 m prelude minus progress 35 m minus the unchanged 8 m allowance means a vehicle
7 m before its target. Terminal hold fixtures now use matching pose/progress 41 m
(1 m remaining). Far approach/coverage cases are unchanged. Positive hold, no
zero edge, unknown-head retention, green restart and other safety assertions were
retained. Other corrections preserve actual same-prefab ownership in a fixture
and coherent captured producer implementations in historical counterfactual tools.

## Paired closed-model comparison

Criteria retained from the preceding terminal report: no red target overrun,
no holding brake-zero write, no red standstill drive, no simultaneous positive
pedals, no parking write, and green restart without N. Default-plant comparison
also requires a reduced nonnegative residual, no increased maximum deceleration
or jerk and no additional pedal reversals. No new physical-line acceptance threshold
was invented.

`tools/run_oct12_stop_indicators_bench.py` restores captured installed Engine,
ACC, stop-control and hold implementation bodies for baseline, then runs identical
inputs for the candidate. Thirty pairs: 20/35/50 km/h, both automatic modes,
straight and +/-1/60 m curvature, delayed loaded plant and an idle sensitivity.
The authored placed prefab/reader and complete pedal path are used. Curved
approaches and vehicle dynamics are explicit models, not recovered ETS2 physics.
Default lag is 0.35 s, input delay 0.12 s, mass ratio 1.4; delayed case uses
0.60 s, 0.22 s, 1.8. The idle case adds an uncalibrated drive term towards
0.92 m/s. SDK observations, physical test writes and response remain separate.

| Straight approach | Planning residual before → after (m) | Maximum deceleration (m/s²) | Maximum jerk before → after (m/s³) | Pedal reversals |
| --- | ---: | ---: | ---: | ---: |
| 20 km/h | 1.209 → 0.872 | 0.971 → 0.971 | 3.620 → 2.746 | 2 → 2 |
| 35 km/h | 1.077 → 1.013 | 1.153 → 1.153 | 4.243 → 4.243 | 2 → 2 |
| 50 km/h | 1.194 → 0.843 | 1.629 → 1.629 | 3.955 → 3.268 | 1 → 1 |
| Delayed loaded, 50 km/h | 1.206 → 0.315 | 1.377 → 1.377 | 2.133 → 2.002 | 1 → 1 |
| Idle stress, 20 km/h | 0.529 → 0.636 | 1.346 → 1.482 | 30.244 → 21.464 | 2 → 2 |

Modes have equal results on this explicit plant. Left/right outcomes are similar.
All 30 candidate cases retain the six safety/green invariants above, with zero
far creep (<5 km/h and >10 m remaining). Slow moving time below 5 km/h is not
eliminated: e.g. 20 km/h default 3.866 → 4.564 s and delayed 50 km/h
4.680 → 6.025 s, nearer the target. Braking starts at unchanged authored-entry
distances 31.725/67.765/99.307 m for 20/35/50 km/h. These are not painted lines.
The idle sensitivity fails the relative residual/deceleration criterion; all
plant conditions must not be called PASS. No post-stop repositioning is used.

## Preserved indicator work from the joint task

The historical Map classified separate three-port arc connectors using net/arc
heading; this produced multiple left/right events inside one circulation. Actual
placed PPDs `dlc_blkw_48` and `dlc_blkw_51` are merge/split templates, not named
roundabouts. A bounded static directed topology now identifies an unambiguous
16-node circulation with four exits and publishes only the chosen right exit.
For later exits, indication is gated until the preceding exit has passed; manual,
hazard and self-cancellation priorities are preserved. Generic ambiguous cycles
are not promoted. This is maneuver metadata, not legal-priority or lane coverage
certification. The geometry and lateral controller are unchanged.

Actual cropped placed topology, original PPD connector directions and existing
baked road centerlines are retained in the fixture. Four exit paths previously
produced 2/4/6/8 events; now each produces one. Physical indicator tests use that
Map metadata with an explicit progress ruler, not a reconstructed game trajectory.
Budget exhaustion, two-port curves, entry suppression and driver override are
covered. Ordinary road paths return before graph construction. Graph limits are
256 nodes, 768 edges and 1,024 pending items; existing prefab cache remains capped
at 128 entries/1 MiB. No new worker, SDK reads or IPC reads are introduced.

Measured event publication on the cropped route: cold 1.222 ms, untraced warm
p50 1.089 ms, p95 1.227 ms, maximum 7.367 ms (200 calls). Traced loops perturb
timing; after GC the repeated-call retained increase was 32 bytes, temporary
peak 2.25 MB, existing topology cache charge 254,762 bytes. This is publication
work, not a claim about live end-to-end packet cadence.

## Verification and reproducibility

- Final targeted integration/safety run: **279 passed in 130.84 s**.
- Actual placed terminal signal/native scope tests: **68 passed in 6.89 s**.
- Final 30-pair stop comparison completed; assertions/metrics above are distinct
  from a universal game verdict.
- Existing 16-case steering and 12-case longitudinal comfort benchmark results
  match the prior baseline exactly; the changed signal branch is covered by the
  paired stop comparison instead.
- `compileall` passed for core/plugins and the new regression/benchmark.
- `git diff --check` passed; LF/CRLF warnings are not code differences.
- An earlier full candidate run had 39 failures before these follow-up corrections.
  All affected test files were targeted again. The final complete suite was **not
  rerun** under the user's latest instruction to run it personally; no full-suite
  PASS for this final candidate is claimed.

Ignored analytical outputs live in `docs/steering-audit/oct12-stop-indicators/`:
`stop-comparison-final.json`, final test logs, immutable decoded evidence and
`runtime-candidate.json`. Reproduce the paired comparison with:
`python tools/run_oct12_stop_indicators_bench.py --output docs/steering-audit/oct12-stop-indicators/stop-comparison-final.json`.

## Exact runtime candidate and open acceptance

Deploy only as a coherent candidate after user full-suite PASS and explicit
approval. Required files relative to installation:

1. `core/engine.py`
2. `core/longitudinal.py`
3. `core/service_brake_hold.py`
4. `core/pid.py`
5. `core/navigation/turn_maneuvers.py` (new)
6. `plugins/acc/main.py` — 1.1.9
7. `plugins/map/main.py` — 1.1.2
8. `plugins/turnsignals/main.py` — 1.0.2

Changelog is release metadata. All preceding installed receipt dependencies
remain required unchanged; no reports, tests, fixtures, tools, DLL or user
settings belong in the runtime copy. No deployment occurred.

The remaining physical geometry evidence is a common-frame surveyed painted
stop-line position and confirmed truck-front transform relative to the SDK
reference. Stationary GPS/destination absence and photographs cannot supply it.
Neither the 2.34 m local offset nor a generic truck overhang is activated.
Existing model residual and idle sensitivity remain open separately from that
geometry. No new journey is requested here. Offline corrections do not certify
game consumption, exact painted-line placement or all intersections.

## Authorized deployment — 12 October 2026

After user-reported final full-suite PASS and explicit deployment approval,
eight runtime files above plus changelog were copied with both UltraPilot and
ETS2 verified stopped. All 22 prior receipt hashes matched; the expanded receipt
covers 24 files, adding PID and the new turn-maneuver module. All nine changed
source/installed hashes and all 24 final receipt hashes match.

Backup: `C:\Users\PC\AppData\Local\UltraPilotBackups\stop-indicators-20261012T175215479Z`.
Receipt: `docs/steering-audit/manual-deployment-stop-indicators-20261012T175215479Z.json`.
Installed ACC 1.1.9, Map 1.1.2, TurnSignals 1.0.2. DLL, settings, caches and app
version/commit marker were unchanged. No application or game was launched.
DEPLOYED / GAME NOT VERIFIED; physical stop-line placement remains open.
