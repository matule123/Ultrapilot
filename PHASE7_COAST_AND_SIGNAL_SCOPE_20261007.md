# Forward coasting and directed signal scope — 2026-10-07

## Verdict

**Reproduced production defects fixed offline; historical cause of pedal
alternation NOT VERIFIED. ETS2 effect of this candidate NOT VERIFIED.**
This report does not claim to have identified every cause of the 18:38 ride,
nor to have made every zero-ratio state safe for propulsion. No new drive is
requested. No control gains, geometry, scheduler, original observation times,
500 ms freshness limits or deadline checks were changed.

Starting commit: `787d012a2a78ac917bb5506e0958c32d8d06575f`. The working tree
was clean. Project rules/version declarations and the previous pairing/stop
reports were consulted; no applicable AGENTS.md exists in the checkout or
its ancestors. Installed Engine, transmission mode, longitudinal arbitration,
signal selector, Autopilot, ACC, DrivePolicy and 2D visualization matched this
Git commit after LF/CRLF normalization. No reliance on `commit.txt`.

## Preserved sources and timeline

Sources read only:

- User incident excerpt `C:/Users/PC/.codex/attachments/2f92bb73-fc5a-455e-b83e-dfdc263822d9/Vložený text.txt`.
- Installed `ultrapilot.log`, 2026-10-07 18:38:09–18:38:29.
- Installed `route-diagnostics/steering-replay-20261007T163828.552313Z-automatic_disable.json`.
  SHA-256 `a9d5860770f48c39b23d1bd6d8a8457c960a462e3475e5fbcfd229527b805f0b`;
  415 steering samples, 10,800 executor samples. Executor buffer capacity is
  not evidence that all those rows belong to this activation.

Authority: epoch `18438056458000`, session `1`, map `promods-1.59`,
dataset `d6cc7936fce4e902761abb5d`, intent `64e84fc7fcc1440b914745ff9f9e8377`,
revision `5`, build `de027bac61c7439b875e23f504dd9f77`, geometry
`80c42c66d2c74d1c78775bd622a8b8f6e7cf106b9c939a112b59d9757adc6ae8`.

| Event | Original evidence | What it proves |
| --- | --- | --- |
| 18:38:09 activation | Probe SDK 33931976, gear 0, speed +0.0000564 m/s, throttle 0.12; observation age 38.62 ms | A simple-auto launch request, no D selector pulse. |
| Successful handoff | SDK 34298628, gear 7, speed −0.01046 m/s, throttle 0.187298, brake 0, active | Existing bounded launch completed; does not establish every later physical pedal write. |
| Replay tick 18443.257076 | Smoothed speed 32.958 km/h, progress 19.746 m | The ride accelerated. |
| Replay tick 18448.001971 | Smoothed speed 17.027 km/h, progress 50.679 m | Substantial slowing occurred before the terminal ratio gate. |
| Replay tick 18452.5749835 | Smoothed speed 2.971 km/h, progress 66.200 m | Slowing is not explained solely by the final rejection. |
| Last replay tick 18457.1739681 | Smoothed speed 2.741 km/h, progress 72.704 m | Approximate progress/speed trend; not raw drivetrain confirmation. |
| First fault | Autopilot at 18457.2298586, reason `simple automatic zero ratio has no fresh forward confirmation`, details null | Plugin rejected first. Its top-level frame 53047878 was acquired by fault recording, not proven to be the actual ratio comparison. |
| Engine comparison | Truck SDK 53031212, original observation 18457.2011916, gear 0, signed speed +0.471773 m/s, parking brake false, valid | Not standstill, reverse or stale telemetry; 46.84 ms age at the later drive boundary. |
| Consumed command | SDK 52981214, observation 18457.1484112, computed 18457.1770668, checked 18457.2249984, expiry 18457.5381806; source ACC, reason normal drive, throttle/brake 0/0 | 313.1822 ms remained; identity matched. This was not lease expiry or the previous ahead-of-observation race. |

Replay speed is Autopilot's smoothed application speed, **not** raw SDK speed
from the controller calculation frame. Replay header SDK frame identifies a
steering calculation; it cannot supply a gear or longitudinal write for that
frame. Trend rows above are not causal pedal/vehicle-response pairs. The
current road LaneId in these rows is `5337536096337530399`, direction 1,
lane 0. Relevant local curvature is small, but that alone does not reveal the
future curve speed envelope or the winning longitudinal limit.

There are **no throttle, brake, target-speed, signal-selection or forward-history
fields** in this replay's sample rows. Steering executor source_packet proves
steering provenance, not pedals. The latest installed combined collections
are from October 2; none matches this October 7 activation. Thus no accepted
combined evidence can supply the missing historical source attribution.

## Production defects and fixes

### 1. Unassigned signal promoted to control

The selector consulted prepared directed prefab passages. If there was no
regulated passage in the horizon, it fell back to geometric heads and could
return an unrelated nearby red as valid. Engine then additionally replaced
a failed directed selection with `nearest_light_ahead` (a 32 m lateral
heuristic, not a lane-control assignment). The same `traffic_light` reached
HUD and light_brake/DrivePolicy. This is a **reproduced unsafe attribution
path**, not proof that a particular historical head caused the ride.

Now an explicit prepared plan without a suitable regulated passage returns
`candidate=None`, `valid=False`, `relevance=detected_only_unassigned`.
Engine never substitutes a raw nearest head for a failed control selection.
The legacy raw detection is stored separately as `traffic_light_detected`;
its optional read failure cannot clear a qualified red. Failures/inactive
telemetry clear display detection and record unavailability as well.

The 2D HUD renders detection-only heads with inactive gray bulbs and
“Detegovaný – smer nepotvrdený”; scoped control uses “Semafor trasy”, legacy
geometric selection is labelled “Geometrický kandidát”. Existing 3D views
continue to render only the control-facing `traffic_light`, not a raw
detected head. A detected red/green cannot authorize brake release.

Authored same-ID placed-passage gates, orientation, elevation, ambiguity,
locked-head lifecycle, known missing-control approach constraints and
same-head fresh-green checks are retained. This does not create missing map
metadata, establish traffic coverage, or certify every intersection.
Legacy clients without a prepared passage schema still expose their existing
explicit geometric heuristic; that is not a confirmed prefab/prong binding.

### 2. Fresh forward observations absent from executor history during coast

The common ratio validator used Engine's committed positive-ratio timestamp.
Autopilot could validate newer actual positive-ratio SDK frames while Engine's
committed confirmation remained older than 500 ms. A subsequent current
zero-pedal, forward-moving zero-ratio frame then failed before normal
arbitration. Both Plugin-first and Engine-first scheduling reproduced it,
including real Map packet/route publication and copying IPC.

Autopilot now publishes a small **observation receipt** only after its common
ratio validator accepts a positive gear. Receipt frame/time are the original
bound SDK metadata, not publication time. Duplicate reads do not create a new
observation. Engine clears the slot with the activation history.

The shared transition can use that receipt only when its own confirmation
is old, the receipt is newer, fresh, no later than the consumed truck, and
has the same activation/transmission/route context. It also requires a valid
fresh **zero-pedal command and zero-pedal ACC request**. It rechecks vehicle
freshness and identity after IPC reads. This is a **coast-only bridge**:
Plugin and Engine both inhibit positive throttle; it is not another launch
exception or a replacement controller.

The first-zero observation starts the **existing fixed 500 ms transition**.
Repeated reads cannot renew it. Continued zero ratio expires safely; speed
at/below the existing standstill threshold still needs the acknowledged
forward-started continuous brake chain. A new actual positive gear restores
ordinary confirmed drive. R, backward motion, parking brake, missing/foreign/
future/stale receipts, stale commands and identity change remain refused.
The original no-stop/expired-stop tests still prohibit zero-ratio propulsion
from an old confirmation.

Supported planned braking remains separate from this zero-pedal coast. Its
existing actual positive-write receipt establishes continuous service hold;
fresh green of the same locked passage plus all-stop clearance releases it.
No brake constant, parking-brake toggle, pedal filter, PID gain, timeout or
stop-and-go sensor was added.

The existing pedal journal includes the immutable coast confirmation and
fixed zero deadline only when that transition is used. Autopilot's first
ratio fault now records the actual compared gear/speed/observation and compact
history rather than only a generic reason. No new collector or INFO flood.

## Reproductions and tests

Original `787d012` modules were loaded in memory; no old checkout, installation
or Git state was changed. **All 10 selected counterexamples failed** on the
baseline, including the real-Map foreign-red and independently scheduled
coasting cases. The initial eight-case run also failed before production edits.

| Scenario | Baseline | Candidate |
| --- | --- | --- |
| Prepared unregulated route + nearby foreign red | Geometric head promoted | No control candidate, detection only |
| Same case through real Map/Policy/ACC/AP/Engine/Controller | False signal admitted | No red brake demand, valid forward output |
| Positive observation, slow independent Engine history, gear 0 at +0.471773 m/s, zero pedals | Technical disable | Active bounded coast, actual zero pedal writes |
| Same case, Engine-first/Plugin-first | Both fail | Both continue without neutral propulsion |
| Repeated zero ratio | Fails at entry | Fixed bound expires; no renewal or drive |
| Missing/stale/future/foreign positive receipt | Not supported | Rejected, no positive throttle |
| Real stale data, identity change, R/backward motion, manual off | Protected | Protected |
| Yellow/red → forward braking → stop/hold → qualified green → restart | Existing support | Existing repeated cycles remain supported in both modes |
| Old Engine history + positive requested propulsion, no stop/expired stop | Refused | Still refused; receipt never grants propulsion |

Tests inspect chronological Controller/SCSControlsWriter writes against an
isolated byte mapping, not only shared scalar values. They retain no
simultaneous positive pedals, no brake-zero edge during qualified holding,
no parking-brake writes and no modeled reverse edges. The game model is based
on the user's manual-brake observation; software write continuity still does
not prove DLL/game consumption.

Two previous rolling-window tests used a SyntheticMap with **no authored
semaphore metadata**, yet expected a nearby geometric head to be controlling.
They now explicitly provide their synthetic placed directed passage (ID 19,
entry at z=64 m, head z=100 m, heading pi, y=10 m, real route projection).
Every hold, identity, prefix and physical-write assertion remains intact.
Parsed-map prefab tests independently verify genuine authored metadata;
these fixture changes do not certify synthetic metadata as game evidence.

Validation receipts:

- Focused coast/scope, signal, prefab and previous pairing runs passed;
  a 57-test signal/scope/prefab run and a 94-test activation/fault-detail run
  passed.
- Updated rolling/signal fixture regressions: **72 passed** (4.90 s).
- Final wider affected integration run: **381 passed, 7 subtests passed**
  (59.61 s), including all new counterexamples, preceding command-observation
  pairing, activation, real/legacy signal contracts, prefab binding, original
  neutral-propulsion protection, launch handoff, brake lifecycle, combined
  export, independent producer cadence and control-safety regressions.
- Existing steering benchmark: **16 cases numerically identical** to
  `787d012`; longitudinal comfort benchmark: **12 cases numerically identical**.
  Local ignored files: `docs/steering-audit/oct7-coast-{steering,comfort}-{baseline,current}.json`.
- Targeted compileall and final git diff --check passed.
- The full pytest suite was not run; the user owns that step.

An earlier prefab-export run encountered Windows `PermissionError` in an
isolated workspace temp path. It passed with a fresh short temporary path;
export protection/integrity was not relaxed. Earlier broad integration found
the second missing synthetic-passage fixture, which was corrected as above,
not by suppressing assertions or accepting arbitrary heads.

## Historical attribution and remaining blocker

**Confirmed:** successful launch; material speed reduction; first Plugin
ratio rejection; current forward motion/valid telemetry; zero consumed pedals;
matching identity and 313 ms remaining lease. The source deadline was traffic,
but an effective traffic dependency does not identify a signal or prove which
request created prior braking.

**Reproduced:** foreign-head control promotion and the missing asynchronous
positive-ratio observation/coast handoff. Both are implemented fixes.

**Not demonstrated historically:** original/new head ID and placement,
directed passage choice, locked-head changes, actual target/limits/ACC
candidate, earliest brake-producing request, chronology of physical pedal
alternation, and last actual positive gear/Engine history before rejection.
The historical first cause of slowing and the claimed false semaphore binding
are therefore **NOT VERIFIED**, not renamed as an ACC or traffic defect.

The exact missing evidence is the **time- and activation-bound longitudinal
decision/write receipt spanning the first braking transition**: requested/
selected pedals, limits and traffic light/passage ID, plus actual backend
edges and original SDK observations. Existing October 7 steering data cannot
recover it; unrelated October 2 collections are not substituted. No new ride
is requested and no 100% reliability or completed game repair is claimed.

## Changed scope

Runtime: `core/engine.py`, `core/transmission_mode.py`,
`core/sdk/signal_snapshot.py`, `plugins/autopilot/main.py`, `ui/visualization.py`.
Tests: `tests/test_oct7_coast_and_signal_scope.py`,
`tests/test_oct4_signal_lifecycle.py`, `tests/test_signal_stop_resume.py`.
Documentation: this report and `PLUGIN_CHANGELOG.md`.

Only Autopilot implementation changes its plugin release: **1.2.2 → 1.2.3**.
Map, ACC, DrivePolicy and HUD plugin versions are unchanged. Core selector/UI
changes do not release untouched plugins. No new DLL or configuration is
required. Nothing was committed, pushed, deployed, armed or run in ETS2.

```powershell
cd 'C:\Users\PC\Documents\GitHub\ets2la'
$env:PYTHONCASEOK='1'
python -m pytest tests -q
```
