# Phase 7.2 — Stable longitudinal speed control

Baseline: `7adf8c8` (Phase 7.1). Working tree clean at entry on 2026-10-03.
No game, deployment, commit or push is authorized by this implementation task.

## Acceptance criteria fixed before implementation

These are offline regression criteria for the explicitly documented plant,
not ETS2 comfort certification or a claim about actual stopping distance.

1. Phase 7.1 safety: exclusive pedals, original observation lease <= 500 ms,
   identity rejection, reverse protection, unchanged launch/parking ownership.
   Emergency brake and drive removal must occur on the same Engine flush;
   no comfort delay is allowed on these paths.
2. No target derivative kick; no integral accumulation while inactive or under
   external braking; bounded integral under saturation. A duplicate SDK frame
   must not advance controller state or renew the observation lease.
3. Equal elapsed-time Eco throttle-rise responses at 20/50/100 ms periods must
   match within 1e-6 when the separate slew limit is not binding. Throttle
   withdrawal is immediate, including an ordinary zero-drive request.
4. Closed-loop cruise cases (same target/plant/noise/dt before and after):
   settled speed RMS <= 1 km/h, maximum target overshoot <= 2 km/h;
   speed must enter and remain within +/-1 km/h for a 5 s window within 60 s
   of the last target change. Compare both error and drive/brake transitions:
   candidate steady RMS may not exceed baseline by more than 0.3 km/h and
   must not add drive/brake reversals in the steady window.
5. One-sided target handling: a lower current limit applies immediately; only
   increases may be paced. Regular throttle recovery is bounded to 0.8 input/s
   (at most 0.08 per accepted 100 ms ramp step). Service-brake ramp and all
   safety brake floors remain available; this is not a physical jerk limit.
6. Nonfinite/nonpositive dt or a scheduler gap beyond 500 ms resets dynamic
   memory and cannot authorize new drive. Steering behavior is unchanged.



## Scope and available evidence

**Verdict: PASS for the fixed offline criteria. Live ETS2 comfort: NOT VERIFIED.**
Phase 7.1's paired arbitration and final Engine ownership are unchanged. No
Engine, transmission, geometry, scheduler or steering-controller source was
modified. Baseline is the committed Phase 7.1 build, not an assumed historical
installation. All existing files and raw diagnostics were preserved.

The historical log/replay limitations in PHASE7_STAGE1_RESULTS.md still apply:
its Oct 2 steering replay contains no continuous throttle/brake channels. The
log establishes probe/handoff events, not the cause of perceived harshness.
No absent pedal data or physical acceleration was reconstructed from steering
headers. The following causes are production-code counterexamples, not claimed
causal explanations of an unmeasured game jerk.

## Original flow and repairs

User speed preference and existing road/posted/policy/traffic constraints ->
ACC speed PID -> Autopilot service/emergency arbitration and pedal stages ->
paired immutable command -> existing Engine identity/freshness/transmission
and exclusive-pedal guards -> physical Controller.

| Demonstrated defect | Before | Repair and proof |
| --- | --- | --- |
| Derivative on target error | 40 -> 40.1 km/h at constant speed requested 0.1605 drive | Derivative on measured speed; first/reset sample derivative is zero; no target kick |
| Integral charged without actuator ownership | 5 s inactive at rest charged integral to 10 | Reset while inactive; launch preference remains available without accumulating drive memory |
| External stop/brake or parking hold charged integral | Positive speed error accumulated during controlled stop/parking hold | Reset/inhibit during external traffic/policy/safety/parking braking; no stored drive is released afterwards |
| Output saturation windup | Large persistent error charged integral despite full drive | Conditional integration against signed output limits; opposite error may unwind |
| Every tiny target change erased load compensation | Integral 0.75 fell to 0.0155 after a 0.01 km/h target change | Preserve memory through small changes; reset deliberately on a >2 km/h downward target change |
| PID accepted invalid/nonpositive/long dt | NaN output or positive drive survived invalid intervals | Invalid dt or >500 ms interval resets memory and publishes invalid zero drive, still rejected by Engine |
| Per-tick Eco response | One-second rise endpoints differed by about 0.00983 input at 20/50/100 ms | `alpha(dt)=1-(1-alpha50)^(dt/0.05)` for drive increases only |
| Eco delayed drive withdrawal | 0.5 -> zero request still output 0.425 | Zero or reduced drive is not delayed by Eco or the upward slew limiter |
| Pure threshold braking could not compensate downhill load | 6% model descent settled at about +2.106 km/h, no +/-1 km/h settled window | Existing PID is signed; negative output requests ordinary brake through the same arbitration |
| Repeated frame/inconsistent interval | Controller had no duplicate/SDK-interval policy | Same unchanged frame does not integrate or republish; new frames use original SDK observation differences; incoherent/regressing frames reject |

Twelve initial counterexample tests failed on baseline and two whole-flow safety
checks passed. Downhill and parking-integrator counterexamples were separately
run and failed before their corresponding repairs. Existing safety tests and
limits were not relaxed.

### Controller and comfort details

- The sole existing ACC PID gains (error in km/h, time in seconds) change from
  Kp=0.6, Ki=0.1, Kd=0.05 to Kp=0.15, Ki=0.06, Kd=0.015. Output bounds are
  [-1,1], with the existing integral bound +/-10 km/h*s. Negative output maps
  to ordinary brake at 0.35 times its magnitude; positive output maps to drive.
- Conditional anti-windup prevents accumulation into saturation. A valid paired
  Autopilot output can inhibit further positive integration while normal drive
  is being paced. This is request/output feedback, not proof of DLL/game response.
- Current lower target constraints apply immediately. Only recovery to a higher
  target is paced at 6 km/h/s; that is a target rate, not a vehicle acceleration
  guarantee. Published constrained speed remains the actual current minimum.
- Ordinary brake hysteresis enters above +0.5 km/h with a negative PID demand
  below -0.01, or above the existing +2 km/h overspeed safety threshold. It
  leaves when the signed demand becomes nonnegative. This allows sustained
  downhill braking without repeated drive/brake changes. Above +2 km/h the
  earlier overspeed/40 brake floor remains; ordinary ACC maximum remains 0.35.
- Posted/road/policy hard caps inhibit positive ACC drive when already exceeded;
  cruise hysteresis is not permission to drive through a lower safety cap.
- Ordinary drive recovery is limited to 0.8 input/s, with the existing maximum
  100 ms ramp integration step. Withdrawal is immediate. Ordinary brake ramp
  remains 2.5 input/s up and 4.0 input/s down. Emergency bypasses it.
- Immediate safety withdrawal, source/reason attribution, R/backward rejection,
  parking ownership, startup deadlines and the original 500 ms leases remain.
  No timestamp is renewed to compensate for delayed work. No repeated D/R pulse
  or automatic parking release was introduced.
- Source slots remain bounded single values. No new runtime geometry work,
  diagnostic serialization, input sensor or growing queue was added.

The same fixed matrix rejected the initial candidate that kept the old PID gains:
it produced excessive sustained oscillation with slower drive recovery. Another
candidate that forcibly coasted at every tiny positive cruise error also failed.
These candidates were not retained and criteria were not loosened to accept them.

## Explicit closed-loop model and methodology

`tools/run_longitudinal_comfort_bench.py` uses the real ACC class, Autopilot's
pedal stages, paired publication and Engine arbitration. It does not execute
full Map geometry, device I/O or a gearbox model. Complete hotkey/activation,
Autopilot tick and Engine physical-write ordering are tested separately.

Model: signed forward speed in m/s; normalized drive/brake; load multiplier
0.7/1.0/1.2/1.4; acceleration
`a=(2.2*throttle-4.0*brake)/load-0.12-0.004*v^2-9.81*grade` (m/s^2).
Actuators have a first-order 0.35 s response and 0.12 s transport delay, or
0.25 s in the jitter case. Plant integration uses substeps <=10 ms; a newly
computed command cannot act on the past interval that produced its observation.
Delay delivery is checked within substeps. Speed is constrained to nonnegative
values only in this forward-only comfort model; reverse safety is tested using
the actual production state flow instead.

Initial actuator/pedal memory is zero, even for the cases starting at speed.
This deliberately includes cold takeover underspeed; it is not calibrated from
ETS2 manual-throttle telemetry. No inertia, clutch, engine torque curve, gear
changes, brake fade or trailer mass distribution is claimed to be represented.

Each scenario lasts about 130 s, default 50 ms ticks. Jitter uses seeded
20/40/50/80/150 ms intervals (seed 7201), 0.12 km/h Gaussian speed-observation
noise, load 1.2 and 0.5% ascent. Uphill is load 1.4 / +2%; downhill light is
load 0.7 / -1.5%; braking descent is load 1.4 / -6%. Load-change case switches
0.7 -> 1.4 at 40 s. Target reductions/increases occur at 20/60 s; ordinary
traffic brake 0.2 is applied during 20-24 s; emergency during 10-12 s.
A road-cap scenario exercises the existing lower-boundary guard with the same
speed target schedule; it does not model lateral dynamics or a physical curve.

Metrics:
- Speed error is model speed minus target in km/h. RMS is sqrt(mean(error^2));
  time-weighted RMS uses each preceding actual observation interval dt as weight.
- Full-run max absolute error includes intentional target steps and initial
  acceleration. It must not be mislabeled overshoot caused by the controller.
- Overshoot is positive error after the last target change (an upward change
  in step cases). Downward steps have unavoidable inherited speed error, reported
  separately in the full max/error column.
- Steady RMS uses t >= max(80 s, last target change +20 s). Settling is the
  earliest complete 5 s window within +/-1 km/h after the last target change.
- Pedal reversals count switches between drive >0.02 and brake >0.02 after
  removing coast samples. Both whole-run and steady-window counts are retained.
- Pedal rate uses actual consecutive dt. Acceleration is model delta-v/dt;
  jerk is consecutive mean-acceleration difference / the actual observation dt.
  These are model quantities, not measured ETS2 acceleration or jerk.
- The simulated control pipeline has no IPC scheduling delay: original
  observation age at arbitration is 0 s. That is not a measured live latency.
  Lease rejection under delayed/stale inputs is verified in production-flow tests.

### Speed tracking: baseline -> candidate

All errors/overshoot are km/h. Displayed zeros are rounded, not missing values.
Duration is 130.05 s with 2,601 samples per normal case; jitter is 130.03 s with
1,921 samples. No invalid numeric sample is replaced with zero.

| Scenario | Full RMS before -> after | Full max absolute error before -> after | Steady RMS before -> after | Final-target overshoot before -> after | Settling s before -> after |
| --- | ---: | ---: | ---: | ---: | ---: |
| launch_flat | 7.543 -> 8.114 | 50.000 -> 50.000 | 0.000 -> 0.000 | 1.649 -> 0.000 | 9.500 -> 9.250 |
| steady_noise | 0.190 -> 0.366 | 1.339 -> 2.705 | 0.131 -> 0.070 | 0.529 -> 0.177 | 1.000 -> 3.950 |
| target_down_up | 3.533 -> 3.685 | 24.971 -> 25.000 | 0.015 -> 0.000 | 1.467 -> 0.309 | 5.450 -> 4.800 |
| curve_cap | 4.152 -> 4.337 | 25.005 -> 25.000 | 0.534 -> 0.000 | 0.773 -> 0.000 | 5.600 -> 6.150 |
| acc_slowdown | 2.284 -> 2.384 | 14.997 -> 15.000 | 0.014 -> 0.000 | 1.649 -> 0.616 | 4.450 -> 3.650 |
| uphill_heavy | 8.112 -> 8.602 | 45.000 -> 45.000 | 0.000 -> 0.000 | 0.947 -> 0.010 | 12.750 -> 13.850 |
| downhill_light | 0.057 -> 0.139 | 0.683 -> 1.291 | 0.000 -> 0.000 | 0.000 -> 0.000 | 0.050 -> 1.700 |
| downhill_braking | 2.092 -> 0.135 | 2.237 -> 0.887 | 2.106 -> 0.000 | 2.237 -> 0.887 | NOT SETTLED -> 0.050 |
| load_change | 0.115 -> 0.284 | 1.049 -> 1.928 | 0.000 -> 0.000 | 0.000 -> 0.018 | 0.550 -> 2.200 |
| jitter_delay | 8.982 -> 9.652 | 50.000 -> 50.000 | 0.408 -> 0.158 | 1.645 -> 0.397 | 21.250 -> 14.550 |
| eco | 7.732 -> 8.152 | 50.000 -> 50.000 | 0.507 -> 0.000 | 2.178 -> 0.000 | 13.950 -> 9.300 |
| emergency | 7.238 -> 7.996 | 35.301 -> 35.453 | 0.000 -> 0.000 | 1.236 -> 0.000 | 20.500 -> 21.000 |

Candidate time-weighted RMS equals full RMS for fixed-dt cases. Jitter:
9.120 km/h time-weighted versus 9.652 km/h sample RMS. These start-to-target
figures include the long initial acceleration interval, not merely cruise error.

**Tradeoffs are retained explicitly:** slower ordinary drive recovery increases
full-run RMS and initial underspeed in several cold-start/takeover cases. Heavy
uphill settles later (12.75 -> 13.85 s), and cold noisy takeover later
(1.00 -> 3.95 s). These remain within the criteria fixed above; this is not a
claim that every speed-error metric improves. All steady RMS values improve
or remain within the original non-regression allowance. No ordinary case adds
steady drive/brake reversals. Physical comfort in ETS2 still needs validation.

### Pedals and modeled motion

Candidate maximum ordinary drive rise is <=0.8 input/s in every case. Pedal
withdrawal and emergency brake can be faster: they are excluded from a comfort
restriction. Acceleration/jerk below are explicitly model outputs.

| Scenario | Whole-run pedal reversals before -> after | p95 absolute model jerk m/s^3 before -> after | Maximum absolute model jerk m/s^3 before -> after | Candidate max absolute model acceleration m/s^2 |
| --- | ---: | ---: | ---: | ---: |
| launch_flat | 0 -> 0 | 0.138 -> 0.124 | 3.803 -> 1.698 | 2.026 |
| steady_noise | 0 -> 0 | 1.509 -> 0.461 | 2.672 -> 1.157 | 0.890 |
| target_down_up | 2 -> 2 | 0.635 -> 0.596 | 5.393 -> 5.392 | 2.281 |
| curve_cap | 2 -> 2 | 4.474 -> 0.558 | 5.393 -> 5.392 | 2.281 |
| acc_slowdown | 4 -> 2 | 0.688 -> 0.528 | 4.827 -> 3.832 | 1.516 |
| uphill_heavy | 0 -> 0 | 0.067 -> 0.068 | 2.716 -> 1.216 | 1.233 |
| downhill_light | 0 -> 0 | 0.018 -> 0.004 | 2.393 -> 0.806 | 0.597 |
| downhill_braking | 0 -> 0 | 0.002 -> 0.012 | 0.345 -> 0.257 | 0.191 |
| load_change | 0 -> 0 | 0.097 -> 0.039 | 8.896 -> 8.896 | 0.890 |
| jitter_delay | 0 -> 0 | 3.354 -> 0.843 | 12.026 -> 3.871 | 1.626 |
| eco | 2 -> 0 | 1.953 -> 0.127 | 4.775 -> 1.640 | 2.014 |
| emergency | 2 -> 2 | 0.425 -> 0.475 | 12.696 -> 13.015 | 4.559 |

Steady-window pedal reversals are zero before/after in all cases. Requested ACC
slowdown and Eco reduce unnecessary whole-run reversals 4->2 and 2->0.
Emergency reaches brake 1.0/drive 0 on the same arbitration/Engine flush:
0 s modeled decision delay before and after. The model actuator still has its
transport/response delay; this is not zero physical stopping latency.

Not every jerk metric decreases: abrupt load changes retain the same peak,
and emergency peak jerk is slightly larger in the candidate because safety
braking is not comfort-limited. Descent p95 jerk increases from an almost
constant overspeed plateau to active regulation while peak jerk decreases.
No physical jerk acceptance threshold or ETS2 stopping-distance certification
has been invented from these model numbers.

## Verification and build identity

Final targeted run: **351 passed, 17 subtests passed in 33.99 s**.
`compileall` (core/plugins/sdk/tools/tests), `git diff --check`, and separate
new-file whitespace/final-newline checks passed.
The selection covers comfort/closed-loop matrix, Phase 7.1 arbitration, complete
activation observation binding, simple-auto handoff, control safety, activation
braking/stopping, real-auto selection, policy/traffic/light, diagnostic physical
boundary/export, post-localization freshness, steering handoff, tick stability,
cache and plugin metadata. The full pytest suite was not run.

Complete production-flow tests inspect real Engine method calls to a simulated
physical Controller via PluginSDK, not just Plugin flags. They cover both
transmission modes, initial N, parking, release/recovery after service braking,
manual disable/reactivation, emergency between Plugin ticks, stale and
incoherent observations and changed identity. Duplicate frames do not renew
leases and actual SDK elapsed time overrides a differing Plugin period.

A Windows filesystem sandbox PermissionError prevented temporary-file setup in
one broad run. The same targeted selection succeeded outside that restriction;
this environment failure was not treated as an application regression.

Steering benchmark: all 16 case dictionaries are exactly equal between HEAD
and candidate, including straight, both turn directions, S, roundabout and
logged-speed cases. Steering sources, geometry and 500 ms checks are unchanged.

Reproduce speed comparison (requires the local baseline commit):

```powershell
$env:PYTHONCASEOK='1'
python tools/run_longitudinal_comfort_bench.py --ref 7adf8c8 --output docs/steering-audit/phase72-speed-baseline-final-20261003.json
python tools/run_longitudinal_comfort_bench.py --output docs/steering-audit/phase72-speed-final-20261003.json
```

Metric JSONs remain ignored under docs/steering-audit. Raw game recordings were
not edited. Candidate runtime source SHA-256 below hashes UTF-8 source after
LF/CRLF normalization so line endings are not mistaken for code changes.

| Runtime source | Candidate normalized SHA-256 |
| --- | --- |
| `core/pid.py` | `71add201dc618b65e9091923fa306323c91da0e4251f8ac300f1bad68ffb8fbf` |
| `plugins/acc/main.py` | `328fa8221b4f72f5e0e9db8b1e17ce9b6d2f687b38dc5c5355de1e734fa4a125` |
| `plugins/autopilot/main.py` | `f8ec2fbecf5246593a7ce1fa16affcd6caf09859458164993fca2fa4dc89c2ff` |

## Changed files and next boundary

- Runtime: core/pid.py, plugins/acc/main.py, plugins/autopilot/main.py.
- Regression: tests/test_longitudinal_comfort.py.
- Offline model/tool: tools/run_longitudinal_comfort_bench.py.
- Documentation: this report, PLUGIN_CHANGELOG.md, PLUGIN_VERSIONS.md,
  DEFERRED_WORK.md.
- ACC and Autopilot advance 1.0.1 -> 1.0.2. No unaffected plugin was bumped.
  EcoDrive producer behavior is unchanged; only its existing preference consumer
  changes in Autopilot. Core PID changes do not release other plugins.

Phase 7.2 is implemented in its verified offline scope. Full suite and authorized
later live validation remain pending; no new drive is requested here. The
simulation does not verify clutch/gear dynamics, every hill/load, comfort in
ETS2, obstacle clearance or ACC traffic coverage. ACC must be enabled for this
closed-loop speed behavior; the disabled-ACC conservative fallback remains.

For 7.3: evaluate existing lead-target selection/continuity, headway error and
its evidence quality independently of this speed/PID change. No new traffic
sensor, stop-and-go, obstacle model or overtaking authority was added. Do not
attribute unmeasured live harshness to ACC alone.
