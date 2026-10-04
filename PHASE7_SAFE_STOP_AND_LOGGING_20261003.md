# Simple automatic standstill handover and quiet diagnostics

**Superseded standstill assumption:** the subsequent user manual-pedal observation
and [continuous-service-stop report](PHASE7_CONTINUOUS_SERVICE_STOP_20261003.md)
replace the blanket standstill disengagement with a proven software-write-chain
gate for planned waiting. The text below records the earlier local decision;
it is not proof that SDK braking continuously through standstill selects R.
Logging corrections remain. Automatic restart still lacks traffic-clearance proof.

Date: 2026-10-03. Source baseline: `3f11cb75362c6ba0e0d0e41f25fce16f7fb311b5`.
The tracked tree was clean at entry. No ancestor/root `AGENTS.md` was present;
reviewed Phase 7 reports, `DEFERRED_WORK.md` and `PLUGIN_VERSIONS.md`.
Changes remain local. No installation, game control, collection or deployment.

**Verdict:** explicit driver handover, first-cause preservation and log cleanup
are verified offline. **Automatic simple-auto holding/waiting/restart is BLOCKED**
by the absence of a verified state-setting hold actuator with execution feedback
and ownership. Releasing service brake is not a slope-holding solution. No
unverified parking-brake/neutral button sequence or optimistic restart was added.

## Incident evidence and identity

| Input | Identity / SHA-256 | Scope |
| --- | --- | --- |
| User incident text `d1b77384-7914-4b8f-adec-a1833b3becae/Vložený text.txt` | `98844c55600872c0403db3043bb77bb7078d2339f77c85410c7310832e3c26ed` | Protective standstill disable; no final selected pedal snapshot |
| Installed `steering-replay-20261003T181529.373609Z-automatic_disable.json` | `c71acdc9d459aec916cf7e9c1a412762807cfcb65b31a3e9c85b9af9114e03a5` | 217 control rows, 10,800 execution rows; 0 immutable executor `source_packet` records; no longitudinal pedal/light fields |
| Installed `ultrapilot.log`, strictly 2026-10-03 20:15 | Epoch `40950234457600`, session `1`, map `promods-1.59`, dataset `d6cc7936fce4e902761abb5d` | Additional periodic AP light-brake diagnostics, not backend-write confirmation |

Intent `7a0a8a59f0f34418a8fdcfff5a2a1720`, revision `7`, build
`a3099c951b2047f2b944e345c0daf8a4`, geometry fingerprint
`d96f7edc913ab979c6eecc6ed8d9a4a374d254f4632168a0ea1ffb9a065dffd4`.
Vehicle configuration fingerprint
`e412f13ad3fb22186614354fd724da0b3dfb1ebcde848323bd222677213d8bc1`.
Do not identify the historical installation solely by today's source HEAD.
The inspected combined status belonged to `phase7-longitudinal-20261003-152818`
and had **0 accepted samples**; it cannot supply the missing final pedal trace.
Original records were neither edited nor removed.

| Wall time | SDK frame / monotonic time | Measured event |
| --- | --- | --- |
| 20:15:19 | `334719944` / `40950.2797419` | Simple-auto launch, throttle 0.12, gear 0, no D selector |
| 20:15:19 | `334969934` / `40950.5073766` | SDK gear 4; not a selector acknowledgement |
| 20:15:19 | `335103262` / `40950.6751012` | Handoff complete; throttle 0.06444, brake 0, AP active |
| 20:15:26.819 | `342102982` | AP requested brake 0.050, light-brake 0.050, speed about 40 km/h |
| 20:15:27.841 | `343136274` | AP requested brake/light-brake 0.259, speed about 30 km/h |
| 20:15:28.874 | `344169566` | AP requested brake/light-brake 0.385, speed about 6 km/h |
| 20:15:29 | `344486220` / `40960.0182354` | Engine standstill R protection; observation `40960.0124992`, age 5.736 ms; historical details absent |
| 20:15:29.227 | `344536218` / `40960.0753405` | AP off; gear 0, signed speed +0.01552 m/s |

The contemporaneous AP rows report zero curve, collision, traffic, auxiliary and
vision brakes. This supports the **light-brake approach**, not the exact final
Engine winner or a measured red color. The user observed red; no raw light color,
producer generation or confirmed stop-line binding was retained. `_light_brake`
can request braking for both red and yellow. The final rejection was not caused
by stale vehicle telemetry. Prefix advancement retained the logged route identity.

## Available holding contract and supported behavior

`Controller` exposes steering, throttle, service brake, momentary Drive selection
and release. It has **no acknowledged set-held/set-released parking-brake API**.
`SCSControlsWriter._FIELDS` contains a boolean `parkingbrake`; that is not evidence
of idempotent brake state, DLL consumption or ownership. SDK `parkBrake` reports
an applied flag, not who owns it or an acknowledgement of our command. `gear` is
the engaged ratio, not the selector state. No new controller/DLL method was added.

| Mode / condition | Supported result | Explicit limitation |
| --- | --- | --- |
| Simple auto (`g_trans=0`), valid braking at standstill | Existing R guard releases automated inputs and revokes activation. New `STOP_HOLD_UNAVAILABLE` handover explicitly asks the driver to take the brake and apply parking brake. | No automatic hill hold or auto restart; driver must prevent rolling |
| Driver parking brake already observed | Do not toggle or release it; report observed flag and external/driver ownership, with `holding_verified=false`. | The flag alone does not certify physical slope hold |
| Real auto (`g_trans=3`) | Retain existing valid service-brake output at standstill; no new selector or parking-brake behavior. | This change does not certify autonomous wait/resume or hill hold |
| Emergency, technical loss, R/backward motion | Existing immediate drive inhibition/safe-stop remains. Preserve the first emergency/technical cause rather than relabel it as a planned stop. | No automatic fault recovery/resume |
| Missing/stale/foreign traffic, disappeared candidate, or green after handover | No new waiting/restart authority. Invalid optional traffic is excluded from evidence; an existing valid brake still requires takeover. | Missing traffic is not clear-road evidence |
| Manual disable / new activation | Existing explicit N lifecycle remains; handover clears pending Drive intent, simple-auto token/history and the active pedal command. | No old launch lease can restart the vehicle |

The one missing actuator capability must be established before implementing
automated simple-auto holding: **an acknowledged, owned, idempotent hold command**
whose safe release does not release a driver's brake. Traffic timestamp/coverage
limits documented in Stage 7.3 also block claims of reliable all-reasons-clear
restart. No new sensor, parser or DLL work is authorized by this change.

## Local corrections

- Classify ordinary standstill inability to hold as **driver handover**, rather
  than a generic technical defect. Preserve the earlier emergency/technical cause.
- Store a bounded copy of the **consumed** brake decision and its traffic/light,
  ACC and policy evidence. Later green/candidate publications cannot be assigned
  to the earlier decision. This metadata never grants authority.
- Carry the first intervention through nested `Controller.release_all` journal
  binding. Previously its separate journal allocation was lost when the release
  copied only the command source. Actual zero writes now retain the same event.
- Show takeover instructions in Dynamic Island, including the transition after
  an already displayed emergency, without replacing its original cause.
- INFO profile logs contain a compact configuration/model change. Full wheel
  JSON is generated only when existing DEBUG logging is enabled, still at most
  once per 10 seconds and only for changed diagnostic signatures. Expected SDK
  overlap/read mismatch is DEBUG; distinct unexpected observation errors remain
  WARNING. The same unexpected warning is not repeated after normal reads.
- Routine SDK gear edges, normal GPS `SAME_EXACT`/`ADVANCED_PREFIX`, route trims
  and periodic AP control dumps are DEBUG. Their shared-state diagnostics/replays
  are unchanged. Camera publishes readiness every existing one-second interval;
  INFO/WARNING reports only changed readiness/reason, details are DEBUG.
- Routine gear diagnostics no longer consume the 240/minute INFO budget for
  activation/selector/rejection records. No new global log filter or log setting.

Plugin version: Autopilot **1.0.3 → 1.0.4**, for its changed diagnostic log level.
Other plugins are unchanged. Core/UI changes do not release unrelated plugins.
No lateral controller, geometry, scheduler, steering cadence, launch parameters,
500 ms freshness limits, service/emergency brake strength or transmission-mode
selection was changed. No authority is created by UI or log messages.

## Reproduction and verification

Tests use production Plugin/Engine methods, real `Controller` and
`SCSControlsWriter` offsets with an isolated byte-buffer backend. A mapping write
is not DLL consumption or ETS2 execution. Pitch inputs `0`, `-0.08`, `+0.08` rad
exercise identical no-hold/handover contracts; **they do not simulate or prove
physical holding on a slope**. A released zero-pedal vehicle can roll under gravity.

| Reproduction | Before | After |
| --- | --- | --- |
| New initial 23 cases against Git HEAD source loaded in process memory, no worktree replacement | 15 failed / 8 passed: missing takeover type/evidence/UI, release evidence loss, noisy logs | Initial targeted changes passed; final expanded file has 31 cases |
| Camera repeated unchanged fault for 80 s, then a different fault | 4 normal-level messages | 2; new fault remains visible |
| 260 routine gear edges then important handoff | Routine rows exhaust INFO budget and hide handoff | One INFO handoff; event state still advances |
| Full profile at INFO | Attempts wheel JSON serialization | No log JSON serialization; profile/wheels remain accessible; DEBUG test retains detailed JSON |
| Nested physical release | First intervention omitted from release events | Same event in returned zero-write records; 128-event/64 KiB journal limits unchanged |
| Emergency shown before standstill handover | Banner never refreshes to brake takeover | Original cause retained plus takeover instruction; reproduction failed before the UI fix |
| Quiet combined handover export | Missing release intervention | Candidate export/inspect verifies integrity and retained first event; `confirmed=false`, `runtime_authorized=false` |
| Failed mapping release at standstill | No confirmed hold capability | Revoked authority; only zero intents; failed writes not promoted to a hold/game acknowledgement |

Targeted runs: **495 passed / 99 subtests**, including activation, both
transmissions, ratio transitions, safety, rolling identity, longitudinal stages,
profile, camera and version checks. Additional collector/ACC/new-case run:
**93 passed**. Final expanded handover/UI/export/version run: **83 passed**. These runs overlap;
they are not added into a unique total. No full pytest suite was run.
The initial export run hit Windows sandbox `PermissionError` in pytest basetemp;
the same targeted checks passed using a new ignored audit basetemp outside that
filesystem sandbox. This was an environment failure, not an application defect.

Benchmarks: **16 steering cases numerically identical**, with unchanged production
controller/dynamics hashes, to the preceding guard benchmark. **12 longitudinal
comfort cases numerically identical** to this task's Git HEAD baseline. These
explicit, unvalidated plants are regression evidence, not game-holding or comfort
measurements. Receipts are ignored under `docs/steering-audit/stop-handover-*`.

`compileall` and `git diff --check`: **PASS**, including whitespace validation
of the new untracked Python/report files. Original
diagnostics, settings and the installed application were not changed. Complete
pytest and any installation approval remain with the user. No new drive requested.

## Disable command (verified syntax; not executed)

From the repository, the existing tool accepts:

```powershell
python tools/manage_maneuver_diagnostics.py disable --settings 'C:\Users\PC\AppData\Local\Programs\UltraPilot\settings.json' --output 'C:\Users\PC\AppData\Local\Programs\UltraPilot\evidence-diagnostics'
```

This disables only the existing diagnostic collector; it does not enable or
disable autopilot authority. Finish/inspect a collection before disabling it if
its in-memory accepted samples must be retained. No command was run on the user's
installation in this task, and no original log was deleted.

## Changed files

- `core/engine.py`: explicit handover/cleanup and quieter routine frame/camera/navigation logs.
- `core/longitudinal.py`: bounded consumed stopping evidence; command values unchanged.
- `core/control_timing.py`: retain the first terminal handover alongside emergency/technical causes.
- `core/navigation/longitudinal_diagnostics.py`: preserve separately budgeted intervention through nested release binding.
- `core/telemetry.py`: compact profile-change logs; opt-in full DEBUG record.
- `plugins/autopilot/main.py`: routine periodic diagnostics DEBUG, version 1.0.4.
- `ui/dynamic_island.py`: truthful brake takeover banner, refresh without replacing the causal event.
- `tests/test_stop_handover_and_quiet_logging.py`: real Controller/mapping regressions and quiet combined export.
- This report, `PHASE7_FINAL_RESULTS.md`, `DEFERRED_WORK.md`, `PLUGIN_CHANGELOG.md`.

Suggested commit, not executed: `fix(safety): make simple-auto standstill handover explicit and quiet routine diagnostics`.
Description: Preserve brake-decision/first-cause evidence through physical release,
clear launch authority on handover, report the missing hold capability, and move
routine diagnostics to DEBUG without changing normal control or export integrity.

## Remaining result

The specific protective disable is not removed by allowing service brake to
select R or by releasing into an assumed safe hold. The fallback is now explicit,
auditable and does not promise autonomous waiting. The only next capability work
for simple-auto holding is the verified owned hold actuator described above;
it needs separate authorization if it involves a DLL/backend or live validation.
Newly observed green or an absent ACC candidate cannot resume this activation.
This task does not claim a successful ETS2 stop/wait/restart.
