# Signal near-stop handoff and second-roundabout oscillation

Incident date: 16 October 2026, Europe/Bratislava. Work continued on 17 October.
Status: **partial implementation; the second-roundabout cause is unresolved**.
No deployment, commit, push, game operation or request for another drive.

## Build and evidence boundary

The source parent is `b6066ff`, with the existing uncommitted native-owner,
brake-owner, HUD and export fixes preserved. A commit marker alone is not the
installed implementation. At entry all **34** files in the current installed
`manual-deployment.json` matched their SHA-256 receipt. All **25** inspected
runtime dependencies matched source after LF/CRLF normalization. The immutable
entry source is retained as `docs/steering-audit/oct16-green-restart/entry-runtime.zip`;
`installed.json` retains the original receipt and source checks. The deployed
ACC is **1.3.6**, Autopilot **1.3.4**, DrivePolicy **1.1.4**, Map **1.1.2**.
This candidate changes only ACC's plugin implementation/version, to **1.3.7**.
The native DLL remains **1.59.4-up-traffic-timed**; no DLL replacement is required.

The original attachment is
`C:\Users\PC\.codex\attachments\a7784b14-b8bc-4800-97ae-6157cc2f3af7\Vložený text.txt`.
The complete installed `ultrapilot.log` and the following original files were
read without modification. Existing `inspect_replay` and immutable codecs were
used; all six inspected exports passed integrity validation:

| Installed `route-diagnostics` file | Use |
| --- | --- |
| `steering-replay-20261016T193501.314781Z-automatic_disable.json` | Original signal fault, immutable pedal inputs, 13 detailed writes and 30 s decision history |
| `steering-replay-20261016T193501.530611Z-automatic_disable.json` | 1,129 dense samples, monotonic 31007.276–31059.068 s |
| `steering-replay-20261016T193659.223930Z-automatic_disable.json` | Later GPS-removal fault; its pedal history starts at 31147.020 s |
| `steering-replay-20261016T193700.658891Z-automatic_disable.json` | 1,682 dense samples, 31077.439–31176.900 s; contains the second-roundabout speed changes |
| `steering-timing-20261016T192826.174749Z-plugin_stop.json` | Earlier session boundary; not substituted for this incident |
| `steering-timing-20261016T193713.013590Z-plugin_stop.json` | Subsequent timing export; not longitudinal actor/constraint evidence |

Expanded workspace copies and original-file hashes are under the audit directory.
The read-only extractor is `tools/analyze_oct16_green_restart.py`. Where the
compact input has `light_reference=signal.candidate`, that exact immutable
reference must be resolved; absence of a repeated `light` dictionary is not a
recorded absence of a signal. Sparse replay headers are not substituted for
executed source packets. In particular, the later dense file's 6,910 execution
rows have no retained non-null `source_packet`; they cannot prove longitudinal
command/write ownership.

## 1. First signal fault: recorded ordering

First intervention: **21:35:01**, AP ratio gate, checked at **31059.0954289 s**.
The exact validated vehicle observation is SDK frame **173226404**, observed at
**31059.0816714 s**, gear **0**, speed **−0.0059080804 m/s**. This is within the
existing reverse-motion tolerance; no recorded R triggered this first fault.
Forward history was still `forward_confirmed`, confirmed frame **173193072**
at **31059.0467456 s**, with no zero-ratio deadline and neither brake-only nor
coast-only authority. The first reason is
`simple automatic zero ratio lacks continuing forward motion`.

The activation is **31006941084700**, session **1**, map **promods-1.59**, dataset
**d6cc7936fce4e902761abb5d**, intent **97be8db356a6463bbcd8df6aeaefb327**,
revision **9**, build **f3feb35d1b014c39a46d7e440bf3111e**. The qualified locked
signal is **ID 1**, passage **45540e750098d8f1fc11bc8b76cd20b1ae161420a94ae48b90dad1891389062f**.
The last retained signal is **red**, generation **6762**, source frame
**207254176**, observed at **31059.0413099 s**, countdown **15.89969 s**.
The original lock is generation **6212**, source frame **191009291**, observed
at **31042.8017807 s**. The reported immediate green is **not captured** before
the first rejection; it is tested separately as a timing variant, not inserted
into the historical record.

The derived target is at passage entry progress **314.9294375 m**. It retains
the existing **3 + 2 = 5 m reference offset**. Neither this target nor its last
approximately **1.469 m** distance is a measurement of the painted line or bumper.

| Monotonic time (s) | Recorded speed (m/s) | Distance to same target (m) | Consumed/output evidence |
| --- | ---: | ---: | --- |
| 31058.532 | 1.004889 | 1.8170 | Written brake approximately 0.242337 |
| 31058.8076254 | 0.682817 | 1.555868 | ACC publishes drive approximately 0.24516, brake 0; Engine still retains brake approximately 0.199684; hold remains `approaching` |
| 31058.8787587 | 0.480993 | 1.511076 | ACC requests drive approximately 0.55436; the actual backend brake reaches 0 and drive approximately 0.043057 follows at 31058.884831 |
| 31058.9534 | 0.305997 | 1.511076 | Both written pedals are 0; no terminal continuous-hold witness |
| 31059.0203 | 0.155443 | 1.476420 | ACC requests approximately 0.84749 drive; actual pair remains 0/0 |
| 31059.0899346 | 0.005473 | 1.469109 | ACC drive reaches 1, brake 0; original approach remains non-terminal and actual pair is 0/0 |
| 31059.0954289 | −0.005908 | unchanged identity | AP sees the newer zero ratio and rejects before an Engine hold/restart transition |

The 480 retained regular/change rows cover **31029.0672003–31059.1487807 s**.
Detailed backend evidence covers only about **0.315 s**, not the full approach.
The last SDK observation in a row is not automatically the response to that
row's requested command. A successful backend return proves a software write,
not ETS2 consumption.

### Reproduced production defects and correction

1. **Independent stop-profile samples lose signal braking ownership.** The old
   ACC selected the distance brake only when its current signal cap equalled
   the effective minimum. A slower Policy retained a different lower sample
   of that same speed-dependent envelope, so the signal's required brake was
   dropped into ordinary speed tracking. The new failing reproduction holds
   Policy for one tick through the native reader, real selector, ACC, AP and
   physical writer. The historical `signal_brake_selected` flag was not retained,
   so that missing bit is not claimed as a directly recorded Boolean. The
   recorded red/zero-brake transition and the independently reproduced defect
   are distinguished. ACC now retains the current calculated signal brake as
   a floor while preserving stronger valid requests and their actor ownership.
   It does not raise the target or add a second speed regulator.
2. **Near-stop approach lacks a terminal brake commitment.** Releasing an
   admitted moving approach until raw distance crossed 1.5 m could lose the
   forward-started chain before the next observed zero ratio. The shared low-speed
   commitment now includes the existing response/transfer reserve:
   `distance <= 1.5 m + speed * (1.0 s + 0.5 s)`, only below 0.5 m/s. It still
   requires actual forward-started positive writes for a hold; it cannot create
   a stationary brake edge. The target, calculated braking law and 5 m offset
   are unchanged. The model's slightly earlier final stop is reported below.
3. **Qualified green and zero ratio can arrive before clearance pairing.** A
   previously admitted but released `approaching` state had neither a positive
   hold nor launch authority while Engine collected its second same-head green
   acquisition. Both gearbox validators now use the same bounded **zero-output**
   pairing contract. It checks original head/passage, lifecycle, authority,
   newer generation/frame/source time, current vehicle validity and fixed
   deadline. It cannot apply drive or a new stationary brake. Actual clearance,
   all other stop reasons, backend continuity and the existing bounded launch
   still precede drive. New ticks do not renew its 500 ms bound.
4. **Own probe was reclassified as a new stationary wait.** At 21:35:26 the log
   records the system's own 0.12 probe before the later traffic/ACC wait and
   ensuing motion cancellation. The earlier 21:35:23 attempt has no retained
   physical source history proving who initiated its motion. The production
   reproduction confirms the lifecycle defect. An already written probe now
   loses drive immediately on a later brake requirement but keeps its original
   launch deadline. Confirmed forward motion transfers through a bounded,
   zero-output Plugin acknowledgement and the normal final Engine gates. No
   drive may emerge from disappearance of that late brake alone; missing current
   braking or unconfirmed standstill ends in precise handover, not a blind brake.

Previously the signal scenarios used effectively identical producer samples,
or an already established terminal brake chain/positive ratio. They missed the
slower Policy cap, the released approach reaching zero on the first green and
the probe already written before a slower brake publication.

The helper initially performed 19 unnecessary state reads when invoked on a
moving approach. A new failing read-count regression identified this before
release. The final helper returns from the already consumed local vehicle
snapshot before IPC in that case: **19 → 0 unnecessary reads**. Source clocks
are checked after the required reads at standstill. No SDK reads were added.

## 2. Second-roundabout speed oscillation: still unresolved

The exact earlier problem coordinate, approximately **(34859.18, 45366.03)**,
matches this ride at **31119.618603 s**, position **(34859.1745, 45366.0565)**,
progress **632.562867 m**, speed **37.6670 km/h**. It is not selected just by
prefab name. The same intent/revision/build persists through the affected interval.

| Approximate monotonic second | Speed (km/h) | Progress (m) | Directed path |
| --- | ---: | ---: | --- |
| 31121 | 17.118 | 643.696 | road UID 5337536093204383133, direction −1, lane 0 |
| 31122 | 12.635 | 647.702 | prefab `blkw_2k00v`, UID 5337536178973708447, connector 0 |
| 31124 | 18.301 | 655.752 | same prefab |
| 31126 | 2.855 | 663.830 | same prefab |
| 31128 | 13.435 | 668.205 | same prefab |
| 31129 | 23.175 | 673.419 | same prefab |
| 31130 | 17.604 | 679.071 | road UID 5337536093791584855 |
| 31134 | 15.380 | 700.604 | prefab `dlc_blkw_46`, UID 5337536180190062103, connector path [2,5,6] |

These are recorded SDK speed/pose samples, not inferred pedal outputs. At
31121–31126 the local reference curvature changes only approximately
0.000423→0.004219 /m. This does **not** prove the forward curve profile, nor rule
out traffic, braking ownership, PID state or a later sharper curve. No numerical
limit or predictor was tuned from these incomplete observations.

**Exact missing evidence:** the traffic actors and their original acquisition,
lead/crossing/body constraints, complete forward curve/roundabout profile,
Policy/ACC selected cap and state, AP decision and confirmed physical pedal
writes at **31119–31134 s**. The prior significant-event receipt ends at
**31116.0801245 s**; it shows only an earlier curve brake **0.0430856**, radius
**19.0311 m**, curve distance **108 m**, roundabout entry distance **107.4217 m**,
and Policy cap **13.50814 m/s**. Those values must not be assigned to later ticks.
The next detailed pedal history starts at **31147.0200995 s**. No combined
collection from this ride exists in the configured evidence directory; the
newest existing collection is the older stationary calibration on 11 October.

The log records **SIGNIFICANT_EVENT_EXPORT_DISK_QUOTA at 21:34:16**. This explains
why an expected evidence path is absent, not why the vehicle braked. The native
actors cannot be recovered from SDK pose/steering alone. This incident therefore
does not yet identify A/B/C/D/E/F as the first erroneous producer. The previous
native slot/identity fix remains intact and is not reverted.

No new drive is requested. The smallest missing item is an already-existing
longitudinal/scene export covering that interval, if one was archived elsewhere.
Otherwise the original cause cannot be reconstructed exactly from retained data.
Before any separately approved future measurement, the existing export quota
must be made usable through an explicit archive/retention decision; originals
are not deleted or overwritten by this task. Do not mark both issues resolved.

## Reproductions, acceptance and models

`tools/verify_oct16_green_restart.py --reproduce` loads the actual archived
deployed methods in memory; no checkout or installation is modified. The five
new targeted production cases fail on that baseline and pass on the candidate:
both-mode terminal ownership, both-mode qualified-green/zero pairing, and the
late-brake own probe. These are new failures, not reused old green tests.

The final new test module has **46 cases**. It covers three green timings and
three repeated red/hold/green cycles in each mode, slower Policy, stale/future
or foreign signals, session/dataset/activation changes, R, backend failure,
interrupted physical brake, concurrent stop, manual cancellation, fixed pairing
deadline, late-probe timeout/disappearance and original immutable export flags.
The auxiliary IPC read-count test also fails before its performance correction.
Targeted activation/gearbox regressions retain the existing protection criteria.

The closed comparison uses the existing actual placed-prefab signal fixture,
native reader, Policy/ACC, AP, Engine and real Controller with chronological
BytesIO backend. Plant: 2.2 m/s² drive gain, 4 m/s² brake gain divided by mass
ratio 1.4, actuator time constant 0.35 s, transport 0.12 s, drag 0.12+0.004v²;
jittered 33/50/80 ms steps and Policy every third step. It is **not calibrated
ETS2 physics**. Criteria precede comparison: no red overrun, no positive pedal
overlap, no brake-zero during confirmed red hold, restart without N, unchanged
5 m reference and existing [0,1.5] m terminal gap zone. No painted-line/bumper
criterion is asserted from this model.

| Initial speed | Mode | Samples before→after | Gap to same planning target before→after (m) | Max deceleration before→after (m/s²) | Max model jerk before→after (m/s³) | Green-to-drive before→after (s) |
| --- | --- | --- | --- | --- | --- | --- |
| 20 km/h | simple | 506→497 | 0.300→0.951 | 1.012→1.012 | 4.224→3.248 | 0.122→0.095 |
| 35 km/h | simple | 432→411 | 0.251→1.065 | 1.154→1.154 | 4.454→4.454 | 0.100→0.108 |
| 50 km/h | simple | 414→417 | 0.317→0.591 | 1.592→1.592 | 4.324→3.263 | 0.098→0.158 |
| 20 km/h | real | 506→497 | 0.300→0.951 | 1.012→1.012 | 4.224→3.282 | 0.222→0.255 |
| 35 km/h | real | 432→411 | 0.251→1.065 | 1.154→1.154 | 4.454→4.454 | 0.230→0.208 |
| 50 km/h | real | 414→417 | 0.317→0.591 | 1.592→1.592 | 4.324→3.245 | 0.258→0.258 |

All six candidate comparisons satisfy those pre-existing safety/terminal criteria;
all have zero positive physical overlap, red overrun, parking writes and brake
zeros during established red hold. The stop is **0.274–0.813 m earlier in this
model**, not falsely advertised as improved stop-line precision. Brake onset is
unchanged: approximately 28.224/65.426/99.307 m to the derived entry for
20/35/50 km/h. Pedal-mode transitions remain respectively 4/4/3. The ordinary
closed approach also passed on baseline: it is not the failing race reproduction.
The five specific scheduling/state reproductions provide that evidence.

## Performance and unchanged control

Three paired repeats, 120 measured ticks after 25 warm-up ticks per mode and
DEV setting, use the existing production pipeline/test IPC benchmark. Ordinary
control outputs and source-read counts are exactly equal before/after and with
DEV off/on. No new worker, queue or history budget is introduced. The final
performance data is `performance-exact-combined.json` (three sequential single-
repeat jobs under `exact-performance-0/1/2`). The archived baseline includes
the original diagnostic compaction methods as well as control methods; the
earlier shared-compactor trial is retained separately, not merged into this table.

Table cells are range of per-repeat medians; worst p95 / worst p99 / maximum
across repeats, **wall milliseconds**. They are not percentiles of percentiles.

| Mode / DEV | Before | Candidate |
| --- | --- | --- |
| simple / off | 7.719–8.601; 10.390 / 10.759 / 10.817 | 7.924–8.704; 10.685 / 12.191 / 13.506 |
| simple / on | 8.507–9.169; 11.470 / 14.020 / 16.048 | 8.472–9.915; 15.330 / 18.872 / 20.748 |
| real / off | 7.567–8.803; 11.635 / 12.524 / 12.536 | 7.758–9.227; 11.419 / 13.197 / 13.342 |
| real / on | 7.901–9.610; 12.513 / 13.520 / 13.658 | 7.656–8.752; 11.236 / 11.873 / 13.141 |

Some tails worsen; this is not a claim of universal speedup or a hard-real-time
guarantee. Thread CPU samples on this Windows runtime are quantized at 15.625 ms
and cannot resolve these individual ticks. GC is recorded separately: the final
comparison's maximum is approximately **2.061 ms**. An earlier retained trial
had a 14.87 ms pause; neither is labelled the cause of historical braking.
The owned display snapshot remains **41,959 deep bytes**
with DEV on in both versions; off is `None` (16-byte Python object accounting,
not process RSS). Test mock histories, worker/OS memory and the existing journal
budgets are not concealed inside that figure. This task's interrupted full-suite
processes had ended before the final paired measurement; unrelated host load
was not controlled, and these are not isolated OS-IPC latency measurements.

An additional short actual signal lifecycle measures owned containers separately
from test histories (`retained-memory/retained-memory.json`). The single hold
record peaks at **13,157 deep bytes**, versus **12,716** at its immediately
preceding moving/coast stage in that simple-auto fixture (**+441 bytes** during
green pairing). The bounded engagement record peaks at **9,907 bytes** and is
removed after handoff. Journal-owned event/source/history containers peak at
**83,962 deep bytes** in these 16 phase samples across two modes; accounted
detailed storage peaks at **65,499 / 65,536 bytes**, and short-history storage at
**24,572 / 1,048,576 bytes**. These are short lifecycle samples, not a claim of
whole-process peak RAM or a substitute for the existing 30-second capacity
stress. Mock call histories, the test collector's sample assertion list,
controller caches, workers and OS/Python allocator overhead are excluded.

The **16** ordinary steering scenarios and **198** independent steering matrix
results are numerically identical to the preceding verified build when run
with the **same provisional calibration**. The separate matched-calibration
run is not compared as if inputs were identical. All **12** ordinary longitudinal
comfort scenarios are numerically identical. No lateral/PID/gain/geometry change.

## Final verification and candidate

Update, 17 October: the later core-only evidence correction is documented in
[PHASE7_EVENT_EXPORT_QUOTA_RECOVERY_20261017.md](PHASE7_EVENT_EXPORT_QUOTA_RECOVERY_20261017.md).
It adds readiness, bounded retry and full sealed-event inclusion in an automatic
fault without recreating the missing second-roundabout inputs. The old pending
hash snapshot is superseded by `verification-pending-oct17.json`; no old test
result is treated as verification of those later runtime changes.

**The final complete suite has not completed.** Interrupted runs are retained
as such, not counted as PASS. The `full-frozen.log` run reached approximately
94%; a later detached run also ended when the chat was interrupted. Detached
process startup did not survive cancellation in this environment. After the
user explicitly chose to run the whole suite manually, no further full run is
started by this task. The last previously completed 2,881-test result belongs
to the preceding ACC 1.3.6 build and is not claimed for this candidate.

A full-run failure in the new combined changelog heading
was reproduced by `test_app_release_notice.py`; the heading was corrected to
the existing `## ACC` / `### 1.3.7` parser schema, without weakening the test.
The focused release gate passes **56 tests**, including all **46** new cases.
The final focused activation/signal/continuous-brake group passes **178 tests
and 10 subtests**. An earlier broader group passes **252 tests**; the final
new-module and activation guards cover subsequent narrow changes. `compileall`
and `git diff --check` pass. No existing safety expectations are weakened.
The final user-run gate remains pending; targeted OFFLINE VERIFIED is not a
complete-suite PASS or GAME VERIFIED.

New runtime changes relative to the deployed entry: `plugins/acc/main.py`,
`core/longitudinal.py`, `core/service_brake_hold.py`, `core/transmission_mode.py`,
`core/engine.py`, and additive evidence fields in
`core/navigation/longitudinal_diagnostics.py`. The unchanged native-owner and
HUD fixes already in the working tree remain included. Supporting files:
`tests/test_oct16_green_restart.py`, the read-only analysis tool, paired
verification tool, hash-bound preparation tool, this report, changelog and
`DEFERRED_WORK.md`.

The hash-only `verification-pending.json` freezes **22** coherent runtime/release
dependencies and Python sources for comparison with the user's forthcoming
manual result. It explicitly records `full_suite_passed=null`; it is not a PASS
receipt. The preparation tool
requires the successful full-suite receipt and unchanged deployed base hashes.
No final ZIP has been produced under a false PASS. After the user's result is
recorded truthfully and the frozen hashes are checked, the consistent candidate
can be prepared without changing runtime or rerunning an already successful
suite. No tests, reports, raw recordings, cache/settings or DLL are candidate payloads.
`task_complete=false`, `runtime_authorized=false`, `game_verified=false`:
the second incident remains open even if the signal candidate passes offline.
