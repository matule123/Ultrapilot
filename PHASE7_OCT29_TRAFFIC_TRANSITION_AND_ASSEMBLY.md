# October 29 crossing-model transition and late diagnostic assembly

This report supplements `PHASE7_OCT29_FIRST_CAPTURE_ANALYSIS.md`; original
installed logs, replays, AP attachments and manifests remain unchanged. No
deployment, game operation, automatic reactivation, new traffic sensor or
controller is authorized. Qualification results below distinguish original
game evidence, exact-input replay and modeled integration.

## Original evidence and installed identity

The read-only receipt check verifies all 57 installed entries, including the
diagnostic26 payload. Original SHA-256 values and deployment-receipt hash are
in `docs/steering-audit/oct29-transition/audit.json`. The principal case is
`incident-d8f8382277da40c398b28c5fcf315a11-14102.json`, its Engine replay
`steering-replay-20261029T130620.051281Z-diagnostic_incident.json` and its
same-ID AP attachment. All three integrity checks pass. Integrity does not
mean assembled, complete, or a successful drive.

The original main case covers monotonic 22717.9108749--22783.6427569, but its
AP attachment has a large internal hole: retained stream 1 ends at
22742.7114375, stream 2 begins at 22771.7785167. The missing interval includes
the active decisions. A later packet cannot repair that original omission.

## 1. Physical write rejection: proven lifecycle mismatch

Exact pinned values are in `tests/fixtures/oct29-motion-transition.json`,
extracted from the existing immutable replay codec. Raw native acquisitions
are separately reconstructed by `tools/reconstruct_oct29_predictions.py`.

| Input | Original facts |
| --- | --- |
| Traffic record 16993 | Native generation 4250, lifecycle 104452067223580; positive-motion crossing scope for owner 66; cap 1.2598660036521165 m/s |
| ACC record 16994 | Valid; acquired crossing owner 66; original owner acquisition generation 4220 |
| Selected result 16999 | Throttle 0.24694000000017696, brake 0; moving/observed IDs [66]; original deadline 22771.8308795 |
| Traffic record 17004 | Valid; generation 4253; no motion scope or crossing/body conflicts; original native owner continuity remains present |
| Additional decisive field in 17004 | `constraint_completion` **and** `constraint_completions` explicitly include owner 66, status `observed_original_crossing_model_ended`, matching original acquisition lifecycle/current generation/frame/time |
| Last guard | Rejects `ACC moving constraint unavailable before write`; later binding references new traffic 17004 with older ACC 16994 |

The final guard ignored the explicit crossing-completion receipt that ACC and
the earlier Engine arbitration already understand. It treated its absence of
a cap as disappearance. This is a demonstrated scheduling/contract defect,
not lease expiration or proof that an unknown road is clear.

Correction: Engine arbitration carries a small owned copy of the exact acquired
ACC owner into its selected result. The final positive-write guard applies the
same existing owner-chain and crossing-completion validators. A matching new
completion **discards old positive drive for this tick**, retains original
command clocks and the minimum input deadline, and lets the next normal ACC
tick consume the new qualification. It never recomputes a second controller,
releases terminal hold, or asserts coverage. Fresh emergency demand takes
priority immediately. Missing/wrong owner, empty list alone, missing completion,
foreign identity, old/future source or absent source remain rejected.

Before: exact pair and production native/selector/Policy/ACC/AP/Engine/Controller
fixtures fail (4 failed / 6 passed, including emergency precedence and both
gearbox modes). After: 98 relevant transition/owner/traffic tests pass. The
isolated exact pair passes with throttle **0**, original computed/observation
times unchanged; modeled independent ACC update releases only the completed
owner and retains authority. This is not a replay of unrecorded future game
motion. Original 66 remained visible; no actor disappearance is asserted.

## 2. Earlier braking: reconstruction, not invented clearance

| Stage | Consumed prediction and selected behavior |
| --- | --- |
| Owners 39 / 51, near 22767.135 | Directed crossing points 34.94 / 30.44 m ahead; actor arrival 3.73 / 2.74 s; ego arrival 5.68 / 4.95 s; 2 s reserve plus half actor-body traversal time |
| Owner 66, near 22770.388 | Ego 4.3103 m/s; positive-motion cap 1.59567 m/s; no predicted 3 s body contact |
| ACC 16840 / output 16849 | Control target 5.6474873946 km/h, `speed service brake`; selected and written-request brake 0.35, ego 4.33067 m/s (15.5904 km/h) |
| Near 22771.57 | Vehicle has slowed enough for positive speed recovery under the old scope; guard then consumes the new completion and originally faults |

Sixty-six native captures were decoded from their original moving/parked bytes,
ego tractor/trailer boxes and SDK observations. The same immutable 225-point
Map geometry/build/revision is recovered from AP inputs. It is matched by
geometry identity, not used as proof of original first delivery. Forty-six
common ray intersections reproduce distance with **0 m difference**. Original
and repeated 3 s box predictions both have zero contact rows. The body model
uses directed ego motion and fixed articulation, constant observed actor
speed/heading; the crossing model uses an up-to-8 s ray and 2 s reserve. Neither
is an actual measured future vehicle path or a certified right-of-way decision.

The 0.35 brake is therefore traced to the ordinary ACC reduction toward the
crossing speed ceiling, **not AEB contact, a semafor, or service-brake hold**.
The exact crossing inputs do not prove that this precaution was geometrically
unnecessary: future turning, priority and complete sensing coverage are not
recorded. No crossing protection, reserve, AEB geometry, speed regulator or
comfort parameter is changed to make the run pass. Unnecessary real-world
braking is **NOT PROVEN** by zero 3 s contacts alone. Numerical reconstruction
and all decoded bodies are in `prediction-reconstruction.json`.

## 3. Late AP assembly and lost diagnostic details

### Correct time domains and late delivery

- Engine replay `created_at`: 13:06:20.051281 UTC = **14:06:20.051281 local**.
- Original incident manifest file completed around **14:06:34 local**.
- AP replay `created_at`: **13:06:56 UTC = 14:06:56 local**; file written by
  **13:07:02 UTC = 14:07:02 local**. It arrived after the main case's decision.
- Prior AP part 11495 was written at 13:06:06 UTC / 14:06:06 local. The same
  single writer/export slot handles original safety replay and part work.

The original export closes an explicitly incomplete manifest after its bounded
AP-presence wait and never revisits it. Later valid AP arrival cannot attach
itself. The producer has no historical per-operation admission/start/finish
trace sufficient to assign every second of this delay to CPU versus admission,
IPC or retry scheduling. File creation is not first delivery. This report does
not fabricate that attribution or increase the assembly timeout.

Implemented supported late completion: the same admitted AP export child
checks the one exact existing case after writing its part. It emits a single
immutable `incident-<id>-assembled.json`, linked to the SHA-256 of the untouched
original. It verifies exact request/identity/range, all required consumed
commands and attachments, component counters and predecessor continuity.
It does not promote capture loss to completeness. Original and resolution
archive together inside the same active/archive disk quota. No control tick
waits, polls disk, spawns a process or performs this validation. An absent or
corrupt part stays incomplete; no newer packet may stand in for it.

Before: six late-attachment reproductions fail. After: correct, missing,
corrupt, wrong-range and capture-loss cases pass; real Windows-spawn daemon
uses the existing non-daemon Manager successfully. Corrupting the original
invalidates the resolution. A correct AP attachment can make assembly valid
while other original failures keep `complete=false`.

### Decision summary failures

Replaying exact original output summaries reproduces five of the original six
failures at 22767.2993955, 22767.4065936, 22767.5230544, 22767.7313853 and
22767.8418286. Expanded rows are 4,193--4,256 bytes. `_DecisionHistory._append`
rejects them at 4 KiB **before** its existing bounded compression; overlapping
traffic cause, departure, two-target scope and write aggregate cause the excess.
No capacity loss or bad input value is needed. The sixth original increment
has no saved exception/operation; replaying all available same-session earlier
exports does not identify it exactly. It remains an explicit historical gap.

Correction: retain the same exact compressed format, 4 KiB retained row bound
and 1 MiB history budget; separately bound expanded preparation to the existing
32 KiB source-envelope size. These actual rows fit losslessly after compression.
No fields or failure counters are erased. A compact eight-entry error-only
operation/reason ledger is charged within the original identity-pool budget;
real future capture errors no longer have only an unexplained total.

### AP capture failure and repeated disable

The original AP part reports one aggregate failure, no transaction-level
failure. Its retained streams omit the intermediate active ring. Reproduction
shows `AutopilotIncidentParts.end()` retains the first retired ring but on the
second rotation increments the new ring's failure counter and discards the
second retired reference. This explains the demonstrated code defect and is
consistent with the two disables and original stream gap; the old scalar
counter alone cannot prove that exact branch was its historical origin.

Correction: merge exact owned row references into **one** replacement retired
slot, charging actual entries/shared ownership, bounded to the same 32 MiB.
Carry it through a pending successor case and include it in the normal seal.
Real overflow is still counted as lost capacity, never silently discarded or
called complete. No actor, timestamp, decision or backend result is replaced.

## Frozen runtime and qualification

Candidate `UP-OCT29-INCIDENT-01` uses the exact installed diagnostic26 base,
not unrelated dirty UI/SDK/control edits. Only four runtime files differ:

1. `core/longitudinal.py`: final guard and compact exact owner provenance;
2. `core/steering_replay.py`: verified late assembly and coherent archiving;
3. `core/navigation/longitudinal_diagnostics.py`: summary retention, bounded
   failure cause and exact repeated-rotation retention;
4. `core/navigation/diagnostic_build_config.py`: temporary build identity only.

Engine, ACC, DrivePolicy, Autopilot, service-hold implementation, DLL and plugin
VERSION declarations are unchanged. No plugin version is increased for core
fixes or documentation. Required installed hashes, dirty source provenance,
changed core functions and payload hashes are in `release01/candidate-manifest.json`.
Targets, frozen test hashes and final logs are stored beside it. No whole-repo
pytest claim is made: the user retains control of that separate run.

## Final frozen qualification and handover

### Additional original readback

Exact late-part validation finds 242 required commands, **118 missing**, 994
AP records, zero capacity drops and one aggregate failure. The original AP
file is integrity-valid, but fails coverage. Its late arrival alone cannot
make the original historical case complete.

Physical brake evidence: call 16848 at 22770.5606173 requests 0.35, returns
float32 0.3499999940395355 / `MAPPING_WRITE_RETURNED`, bound to `acc brake demand`.
Two preceding throttle writes return zero; call 16865 repeats that brake at
22770.6777938. These are backend confirmations, not game-consumption proof.

### Exact-runtime regressions

Main 581.73 s run: **619 passed, 30 subtests passed**, plus two publication-
contract mismatches. Both also fail on an unchanged installed-base copy,
independently of this patch. The test expected the dirty worktree's uninstalled
`publish_candidate` compare/commit API to leave its slot unchanged. Installed
diagnostic26 instead publishes the retired calculation as explicitly invalid;
the final output gate must reject it. That unrelated publication change is
not introduced or deployed here.

The test retains the stronger original assertion when that API exists. On the
installed plain-slot API it requires the **exact invalid retired result**,
original context and physically refused drive / safety intervention. All tests
in that adapted file and the new moving-transition suite rerun on the **same
four frozen runtime hashes**: **70 passed**, including both former mismatches.
Other test files are hash-unchanged. Original failing log, unchanged-baseline
failing log, old/new test hashes and supplemental log are preserved in
`qualification-completion.json`. Do not add 619 and 70 as unique tests or
claim a single all-green whole-repository run. All 621 selected scenario
outcomes are accounted for; a test-only compatibility correction does not
justify repeating the unchanged nine-minute runtime qualification.

Actual Windows-spawn daemon tests cover late AP assembly through the existing
Manager, active red/wait/green without disable, manual disable, long linked
wait in both modes, failed/late/corrupt parts, exporter crash and invalid
authority refusal. Compileall and `git diff --check` pass. The unchanged
steering benchmark has **16/16 identical case reports** baseline/candidate,
including CTE, heading, step/rate/acceleration, oscillation and completion.
No steering gains, geometry or packet cadence are changed.

### Same-input maximum-population measurement

Existing populated-traffic qualifier, actual Windows-spawn daemon, 40 moving
+ 40 parked records, three trailers per moving slot, lead switch, crossing,
signal wait/resume and overlapping events. Four 1,400-tick / 70-model-second
off/on runs; no sizing overrides. Original numerical criteria SHA-256 remains
`7a74d5032dabb5264c5d13bd8a1895adf335768f6a8b3be45cda2f1c480567ff`.
Earlier explicit memory and off-baseline-completeness approvals remain recorded;
no new waiver or timeout increase. All gates pass.

Times in ms: **p50 / p95 / p99 / maximum**.

| Measurement | Simple automatic | Real automatic |
| --- | --- | --- |
| Whole modeled tick, capture off | 13.243 / 19.211 / 22.279 / 35.129 | 14.344 / 23.827 / 30.106 / 37.335 |
| Whole modeled tick, on | 17.138 / 24.137 / 27.866 / 35.859 | 18.697 / 24.493 / 27.733 / 37.348 |
| p99 on minus off | +5.587 | -2.373 |
| Engine flush, on | 3.566 / 11.122 / 13.558 / 25.153 | 3.580 / 11.966 / 14.350 / 28.805 |
| Whole tick during export, 188 samples | 17.395 / 23.403 / 25.798 / 35.859 | 19.430 / 26.788 / 31.339 / 37.348 |
| Ring lock wait p99 / maximum | 0.0014 / 1.8075 | 0.0016 / 0.2345 |
| Runtime parent + Manager peak upper sum | 320.039 MiB | 317.156 MiB |
| Sole export child maximum | 1,081.996 MiB | 1,068.336 MiB |
| Conservative runtime family peak upper sum | 1,402.035 MiB | 1,385.492 MiB |
| Output footprint | 36.22 MiB | 35.65 MiB |

Negative real-mode p99 contrast is run variability, not proof of faster control
with diagnostics. Whole serialized baseline already exceeds the nominal
16.67 ms period; this is not attributed to diagnostics. Separate Engine p99
<=16.67 ms / maximum <50 ms, whole tick p99 <50 ms / maximum <100 ms, added
p99 <=8.33 ms and lock p99 <=1 ms / maximum <=5 ms all pass. Inclusive phases
are not added as independent CPU/IPC costs.

Enabled runs retain **30.000 s pre + 15.550 s post**, all **1,927/1,927**
incident physical calls and **2,913/2,913** combined normalized calls. Zero
missing decision/input references, sequence gaps, capture losses or capacity
drops. AP commands 912 / 905, all present; 922 AP records each. Physical-write,
decision and native-input digests match off/on; logical gets match (575,175 /
554,986); no positive pedal overlap or unexpected control fault. The finite
fixture's final refused offer is explicitly retried at quiescence in simple
mode without new SDK reads or retimestamping, not a new production queue.

RSS scope: runtime monitor before offline inspection plus conservative separate
Manager/child peak sums, excluding later inspector/test assertion history.
Absolute measured family <2 GiB even before baseline subtraction, parents
<512 MiB, child <1,536 MiB, one child only. Engine/AP ring/file limits remain
64/32/32 MiB. This does not promise an OS reservation or bound all Map/UI
application RSS. Logical gets are not distributed IPC latency; modeled physics
are not ETS2 verification.

### One current package, not deployed

Directory `docs/steering-audit/oct29-transition/release01/`:

- `ultrapilot-oct29-incident-01-candidate.zip` — SHA-256
  `82c1b3b358ea4bf5cb6b76a4f56dd408570dfbcf12808d8d4dbe1c90284edaf5`.
- `rollback-installed-base.zip` — SHA-256
  `4ac95c96e43146e339f192904ed6d8645902f99d2adf8c582ef956a6a3db0879`.

Candidate: only four runtime entries plus hash manifest. Return ZIP: their
four exact installed originals plus original deployment receipt. Every archive
member is read back; all 57 installed receipt entries remain unchanged.
`DEPLOYMENT.md` specifies the conditional transaction/rollback. Settings/cache,
original evidence, commit marker and DLL remain unchanged. Older diagnostic26
archives remain original baseline evidence; this patch is not installed yet.

**OFFLINE VERIFIED**: the exact crossing-completion write race, summary-overflow
mechanism, repeated retired-ring loss and supported late attachment handling.
**GAME NOT VERIFIED**: this build's live effect. Unnecessary real crossing
braking, the sixth historical summary error, exact AP aggregate-error branch
and every internal second of original delay remain unproven as explained
above. Original 118 absent commands cannot be recovered. This is not a general
ACC completion claim or a repaired complete original incident. No new drive is
requested as part of this task; deployment needs separate user approval.
