# October 29 evening reactivation: recording retention and export admission

**Final handover: READY FOR CONTROLLED CAPTURE — diagnostic build only.**
Build `UP-OCT29-REACTIVATION-02` passes the unchanged offline qualification
gates on its exact frozen installed-base runtime. Nothing is deployed.
GAME NOT VERIFIED; the historical actor-85 braking cause remains unproven.
Earlier failed measurements below are preserved and explicitly superseded by
the final `prefix-load-qualification` run, not erased or relabeled as passes.

## Scope and identity

Diagnostic-only correction of the 18:10–18:11 local incident. No deployment,
game operation, ACC/traffic policy, AEB, gearbox, controller, safety-timeout or
DLL change. The installed receipt SHA-256 is
`7064a5073aa2642d5e41a9bb4e3c7950096b3c90ab7b543d067d7bbc54f1c64c`;
all 57 receipt entries matched their installed bytes. Line endings are included
in this exact installed-base check. The three preceding deployed diagnostic
files also match the earlier frozen `oct29-transition/release01` runtime byte
for byte. Candidate 02 uses that installed base, not unrelated dirty source.

Original incident/replay files, including archived predecessors, remain intact.
Read-only reconstruction: `tools/analyze_reactivation_capture.py`, outputs in
`docs/steering-audit/oct29-reactivation/stream-audit.json`. The local binary
analysis caches are trusted-local derived data, not a new runtime file format.

## Historical evidence and boundaries

| Boundary | Evidence |
| --- | --- |
| New activation | 18:10:00.448 request, activation 37440264293800; forward handoff gear 4 at monotonic 37441.0499755 |
| First recorded slowing | 37447.1251392, curve brake demand 0.1335791, speed 9.74038 m/s; this is distinct from the later ACC rejection |
| ACC brake edge | 37460.4748422, brake 0.35, speed 6.82698 m/s; original full consumed input and physical call at this edge are missing |
| Rejected ACC command | computed 37460.7601609; SDK frame 311070890; observation 37460.7437808; expires 37461.2437808; checked 37460.7873178 |
| Rejection | `ACC target unavailable or unconfirmed departure; driver takeover required`; identity equal; observation age 43.537 ms; remaining lease 456.463 ms |
| First intervention | Autopilot 37460.8122901; stored producer acquisition generation 7732, lifecycle 99550537144601, original crossing owner 85 acquired at generation 7717 |
| Late zero writes | Safety replay retains ten exact backend calls 37461.4476743–37461.7234054; these do not replace the missing initial safety/braking writes |
| Disk failure | 18:11:08.840, `DIAGNOSTIC_DISK_LOCK_TIMEOUT`; historical message does not identify lock name/owner PID or lock-entry time |

Main incident `def0be9809114e53a55e959d11361ae9-43934` has valid file integrity,
but incomplete evidence and no delivered AP part. Its native traffic gap is
37436.4137844–37473.6487207 = **37.2349363 s**. Ego and output-summary gaps
are 37.181509 s and 37.191219 s. The declared endpoints span
37406.5083919–37514.3003441; those endpoints do not establish coverage.
Its 259 full-window backend calls only span 37416.4999743–37432.1464492.
Zero missing references inside those retained calls does not establish that
the later calls were captured. No original missing snapshot is reconstructed.

## Proven diagnostic defects and correction

1. **Busy-writer retention hole.** `finish_engine_incident` waits for the
   existing one-job writer before sealing. The old window only pinned the
   original 30-second prefix; its rolling tail expired intermediate rows while
   the writer remained busy. The same mechanism reproduces a prefix/tail hole
   without any disk error, proving that a disk timeout need not cause the hole.
   Pending episodes now retain each exact subsequent entry in the existing
   single pinned-window allowance, with original size accounting updated by
   background compression. No new queue or byte allowance. Real overload is
   counted and marks the dossier incomplete.
2. **Different Engine/AP export admission.** The non-daemon Engine bypassed the
   Manager export service used by the daemon plugin. An AP service ticket could
   therefore be occupied while waiting for an independently admitted Engine
   child at the directory admission lock. Both now use the same existing
   Manager reservation. Prerequisite AP waiting remains outside admission;
   an admitted Engine child performs only a nonwaiting AP readback. No daemon
   flag manipulation, additional exporter or timeout increase.
3. **Independent completeness check.** The inspector now recomputes gaps in
   actually stored periodic ego, traffic, native-signal and output-summary
   streams before accepting a complete part. It rejects an internal gap over
   the existing 250 ms capture-gap criterion even if a producer claims complete
   endpoint coverage. Event-driven backend/consumer streams are not incorrectly
   required to produce periodic calls.

The historical lock owner and exact time spent holding each lock were not
recorded. The two admission/prerequisite defects above are code/reproduction
findings, not proof of a particular historical lock-holder PID. OS file locks
release on exporter death; the existing Manager failure path releases its
ticket. Retried sealed input remains immutable; no failed export is blessed.

## Actor 85 identity audit

Native `TrafficProcessor::get_uid_for_vehicle` in
`docs/steering-audit/oct22-sdk161/read-runtime-a/src/processing/traffic.cpp`
maps an actor pointer to a short ID. The pointer map survives `clear_data`.
It provides no per-actor incarnation token; pointer reuse can reuse that ID.
The array is distance-sorted and truncated to 40 moving records. A slot change
is not an identity change. The capture lifecycle identifies the producer,
not each physical vehicle. The reader preserves those meanings.

Before the missing interval, ID 85 is in slot 29 with WHL approximately
(2.00836, 1.61401, 4.95951). Afterwards it is in slot 0 with WHL approximately
(2.15642, 1.51575, 4.85840), behind the truck. Neither the later pose nor the
changed shape proves the original fault-time pose or pointer reuse. The compact
rejection witness says the locally retained acquisition chain was qualified,
but candidate/completion evidence was absent. Generations 7717–7732 and their
full original actor records are not present in the stored periodic or consumed
streams. No new packet may fill that historical hole.

The installed selector already requires unique ID, source/lifecycle continuity,
an increasing real acquisition, exact body-count/dimensions and bounded motion.
Missing/ambiguous/changed-shape observations break the acquired chain; slot
sorting alone does not. Tests use the recorded dimension pairs with explicitly
MODELED poses to verify that a reassigned short ID cannot inherit ownership.
A fresh rear noncolliding actor creates no traffic brake; genuine predicted
contacts remain protected. No new identity tolerance, fabricated ID, ID-85
exception or speculative traffic-policy correction is included.

## Qualification status

The four diagnostic reproductions fail on the exact preceding installed runtime
and pass with the correction. Real Windows spawn tests exercise a non-daemon
Engine export owner and daemon plugin through the same Manager/disk admission.
A production-component lifecycle model in both automatic modes exercises warmed
recording, active motion, manual N, immediate reactivation, a genuine reverse
observation fault during pending export, passive tail and AP/Engine assembly.
The reverse fault is an explicit safety model, **not** a reconstruction of the
missing actor-85 acquisition. Candidate runtime hashes are fixed before the
selected regression and existing maximum-population qualification runs.

The selected frozen-runtime run produced **630 passes / 30 subtests** and two
test-contract failures. The long-episode test explicitly expected the very
middle loss being repaired; it now requires all 902 original values/times,
no gaps and a complete window. The export-validator double lacked the real
`wait_s` keyword; it now accepts it and additionally requires zero, preserving
the original verified-part assertion. Neither change weakens a safety test.
Both entire affected test modules plus the new retention/identity tests pass:
**48 passes**. No runtime bytes changed between those runs. No whole suite,
renames, skips or xfails were added.

The complete reactivation/automatic-fault scenario also fails on the exact
preceding installed runtime in a real Windows daemon host (79.06 s bounded
test), then passes in both modes on candidate 02. The initial four narrower
reproductions likewise fail before (4 failures / 1.44 s) and pass after.
The candidate's modeled joined dossier spans 30 s pre-event plus approximately
54 s post-event, retains the manual-off/new-N/automatic-stop subevents, has
100 ms maximum periodic-stream gaps and complete exact AP/backend links.
This is model cadence, not a measured game packet interval.

The first load run exposed input-set/list preparation inside the new pin's
shared lock. A new critical-section reproduction failed before correction.
That refinement reuses the exact already-prepared set outside the lock;
it neither copies a new packet nor changes its accounting. **72 affected tests
pass on those intermediate runtime bytes**, including both red/wait/green daemon hosts,
both reactivation/fault modes, overload, exporter death and exact lineage.
The broader 630-pass run preceded this small diagnostic refinement and is not
misreported as a complete final-version suite run.

## Earlier load qualification: BLOCKED (superseded measurements)

Hashes for that earlier measurement: the preserved manifests and
`release02/final-load-qualification/runtime-identity.json` under the output
directory above. Previous unreleased manifest/load data is preserved as
`candidate-manifest-before-pin-allocation.json` / `load-qualification`; it is
superseded for final-version measurements. No candidate ZIP or deployment was
created at that point. The package builder refuses `all_gates_passed=false`.

Existing maximum-load scenario: 1,400 ticks / 70 modeled seconds per run,
40 moving + 40 parked slots and three supported moving trailer slots, leader
change, crossing, signal wait/resume, combined worker and overlapping exports.
Same predeclared criteria SHA-256
`7a74d5032dabb5264c5d13bd8a1895adf335768f6a8b3be45cda2f1c480567ff`.
No thresholds, safety limits or quota changes.

| Automatic mode / capture | Whole tick p50 / p95 / p99 / max (ms) | Engine flush p99 / max (ms) |
| --- | --- | --- |
| Simple, off | 18.30 / 32.35 / 35.64 / 48.75 | 20.48 / 26.13 |
| Simple, on | 29.95 / 49.85 / 70.70 / 136.38 | 30.10 / 93.65 |
| Real, off | 27.59 / 47.94 / 68.40 / 103.47 | 28.71 / 47.69 |
| Real, on | 37.57 / 49.96 / 65.04 / 105.39 | 33.08 / 75.83 |

Whole-tick criteria remain p99 <50 ms, max <100 ms, added p99 <=8.33 ms;
Engine p99 <=16.67 ms and max <50 ms. The simple-mode added p99 is **35.06 ms**,
which fails independently of baseline overruns. The real-mode baseline itself
fails the whole-tick p99/max criteria; the enabled run's lower p99 does not
excuse its absolute failure. Both off baselines exceed the Engine p99 gate.

A same-current-host run of the exact *preceding installed* runtime with capture
enabled gives whole p99/max 36.22/64.22 ms and Engine 20.62/31.41 ms. Thus an
Engine p99 overrun already exists without the new retention change. This does
not explain away the candidate's added overhead. Initial load profiling also
recorded large inclusive control-side legacy source-pack spans and background
normalization spans; these aggregates cannot prove a historical GC/lock cause.
Instrumented baseline Engine CPU attribution is kept separately, never used as
release timing evidence.

Two earlier load runs also reported `INCIDENT_EXPORT_WORKER_TIMEOUT` at the
existing 60-second child-result boundary. This is not a reproduced disk-lock
timeout, and the exact serialization/readback subphase responsible is not
established by the existing aggregate timer. The successful warmed dossiers
below do not make those failed export attempts successful.

| Property | Earlier maximum-load result (superseded) | Verdict |
| --- | --- | --- |
| Warm exact Engine/AP window | 30.00 s before + 15.55 s after, both modes; complete AP attachment and original input links | PASS (model) |
| Full physical pedal detail | 1,927 exact calls in each warmed window, equal to chronological backend trace; no missing links/sequences | PASS (model) |
| Capacity/raw identity | Zero capacity/capture losses; raw bytes, original types/frames/times/context checked | PASS (model) |
| Physical output/decision/reads | Off/on hashes and reads identical within each mode; 575,175 simple / 554,986 real logical reads; no mixed positive pedals | PASS (model) |
| Ring ownership | Engine peak 39,483,627 B / 39,114,120 B; AP 7,682,186 B / 7,511,797 B, within unchanged 64/32 MiB bounds | PASS |
| Export concurrency/memory | One child maximum; child peaks 892.61 / 797.82 MiB; conservative runtime parent upper 321.87 / 334.80 MiB | PASS |
| RSS accounting scope | External host peaks 979,406,848 / 966,787,072 B include offline inspector allocations; runtime-host monitor peaks 231,075,840 / 226,582,528 B are reported separately, not hidden | Measurement |
| Ring acquisition wait | p99 0.0029 / 0.0035 ms; max 0.3802 / 2.7603 ms, below existing 1/5 ms gates | PASS |
| Whole-tick/Engine time and export completion | Absolute gates and simple-mode added p99 fail; export-child timeout observed | FAIL — release blocker |

Static checks at that point: compileall and `git diff --check` pass. All 57 installed
receipt entries and all eight original incident manifests still match. Runtime
control hashes are unchanged. No plugin VERSION/DLL update. Full pytest was not
rerun. Detailed proof is `release02/qualification-result.json`, with
the explicit failed gates (preserved as `qualification-result-before-observer.json`).

**Disposition at that measurement:** retention/admission/completeness passed,
but timing blocked release. The subsequent observer investigation below
supersedes that timing assessment, not the preserved raw measurements.

## Qualification observer correction — 31 October

The baseline profile contains **511 Windows `ppid_map` calls / 6.765 cumulative
seconds**, reached through the qualification monitor's `Process.children`.
The profiling intervals also include concurrent probe/mock work; their totals
must not be presented as isolated production Engine CPU. The monitored daemon
cannot spawn export children: the existing non-daemon Manager owns them. The
supervisor already samples that complete family at 20 ms. The second in-host
Windows PID-map census was redundant and contended with the control host.

The existing qualifier now retains in-host RSS sampling but delegates the
Manager/child census only to that existing external supervisor, still at 20 ms.
Standalone runs retain their original local child monitor. An assertion rejects
selecting the external-only census in an unsupervised non-daemon process.
No application/runtime file changed in this correction, and no memory or timing
gate changed. Both raw observer runs are preserved separately.

With that correction, every timing criterion passed except one measured lock
wait. A standalone empty-critical-section test then proved that the Python
`TimedLock` wrapper itself scheduled GC while holding its otherwise empty lock.
Its `*args/**kwargs` acquisition call allocated call machinery around the C lock
return. The probe now uses the real lock's fixed argument signature, initializes
thread-local probe storage before acquisition and uses a fixed `__exit__`
signature. The same GC-stress test fails before and passes after. Production
GC and production locks are untouched; real blocking is still timed fully.

**11 observer/scope tests pass**, including mandatory enabled-capture
completeness and unchanged memory-budget gates. That intermediate qualification uses
`release02/observer2-load-qualification/` on those intermediate runtime hashes;
all preceding failed measurements remain available. This is a correction of
intrusive test instrumentation, not evidence explaining the historical
installed application's disk timeout or actor-85 behavior.

## Final pin-prefix correction and qualification

The corrected observer still exposed a real diagnostic allocation problem:
starting a pending prefix created two empty shared-input sets for every retained
row even in `simple_records` mode, which never uses shared envelopes. A forced-GC
reproduction with a 301-row prefix fails before the fix. The simple-record path
now clears the existing empty shared set once and sums the original entry sizes;
the legacy shared-envelope path is unchanged. Original bytes, format, quotas,
GC settings and control behavior are unchanged. This correction is separate
from the qualifier-only corrections above, and is not claimed as proof of the
historical application's inner pause or disk-lock owner.

The exact final runtime passes **73 affected regressions**, including both
actual daemon-host red/wait/green and reactivation/fault modes, overload,
exporter death, lineage and the new prefix-allocation reproduction. The
**11 qualifier/scope tests** pass separately. The earlier broader run remains
630 passes / 30 subtests plus its two now-corrected test-contract failures;
48 affected rechecks passed. These counts are not combined into a fictitious
whole-suite PASS. No full pytest rerun, skips, xfails or module renames.

Final source: `release02/prefix-load-qualification/`. Four sequential runs use
the same existing 1,400-tick / 70-second model, maximum traffic population,
combined capture and overlapping exports described above. Criteria SHA remains
`7a74d5032dabb5264c5d13bd8a1895adf335768f6a8b3be45cda2f1c480567ff`.

| Mode / capture | Whole tick p50 / p95 / p99 / max (ms) | Engine flush p99 / max (ms) |
| --- | --- | --- |
| Simple, off | 9.7888 / 13.7981 / 15.6755 / 24.1094 | 7.3521 / 10.0453 |
| Simple, on | 12.5590 / 15.8860 / 17.3483 / 32.7615 | 8.1089 / 22.0516 |
| Real, off | 10.4810 / 15.0871 / 17.0087 / 23.0590 | 7.8116 / 14.7225 |
| Real, on | 13.1168 / 17.2927 / 19.5647 / 33.4230 | 7.8682 / 14.7226 |

Added whole-tick p99 is **1.6728 / 2.5560 ms** (simple / real), within the
unchanged 8.33 ms gate. Absolute whole-tick and Engine gates also pass. Ring
acquisition wait p99 is 0.0012 / 0.0014 ms and maximum 0.0729 / 0.0678 ms,
within the unchanged 1 / 5 ms gates. No final assessment failures or export
timeouts; that does not retroactively make the earlier failed attempts pass.

| Final property | Simple / real | Verdict |
| --- | --- | --- |
| Actual warm window | Both 30.00 s before + 15.55 s after, exact Engine/AP attachment | PASS (model) |
| Backend detail | Both 1,927 exact pedal calls, matching chronological backend trace, no missing references/sequences | PASS (model) |
| Native periodic captures | Both 456 exact captures verified; original sampling/edge contract, not every native frame | PASS (model) |
| Capacity and identity | Zero capacity/capture drops; original bytes/types/frames/times/context checked | PASS (model) |
| Output/decision/reads | Identical off/on hashes and read counts within mode; 575,175 / 554,986 reads, no positive pedal overlap | PASS (model) |
| Engine/AP retained peaks | 39,491,118 / 39,145,259 B Engine; 7,699,010 / 7,546,047 B AP | PASS |
| Conservative runtime parent RSS upper | 318.5664 / 326.8945 MiB | Measurement |
| Additional parent / export child peak | 178.6211 / 186.5547 MiB; 1,084.4492 / 1,067.3945 MiB | PASS |
| Conservative family upper | 1,403.0156 / 1,394.2891 MiB; at most one export child | PASS |
| Warm dossier group size | 38,009,868 / 37,389,046 bytes | Measurement |

Memory remains within the approved additional-parent 512 MiB, child 1,536 MiB
and additional-family 2 GiB limits. Engine/AP rings remain 64/32 MiB and the
Engine file bound 32 MiB. Host RSS and full Manager/export family are sampled
separately at 20 ms; raw external peaks and offline-inspector allocations remain
available in the JSON, not attributed to runtime buffers. Backend return is
proof of a successful call, not proof that ETS2 consumed it.

Final `qualification-result.json`: `all_gates_passed=true`, unchanged controls,
57 installed entries and eight original manifests verified, compileall and
`git diff --check` passed. No plugin VERSION or DLL change. Assessment SHA:
`ddfbb5b2275376ca5fff9439e56d979c95895956b47fce1d5ee5005861344dce`.

## Single frozen handover

Directory: `docs/steering-audit/oct29-reactivation/release02/`.

| Archive | Bytes | SHA-256 |
| --- | --- | --- |
| `ultrapilot-oct29-reactivation-02-candidate.zip` | 70,483 | `f42e507655fb85ed3dcd46265a332cf6d978a1419e6264b4467c701122f1cc54` |
| `rollback-installed-base.zip` | 67,513 | `6ff55fa8f2a91fbab5c25baceeb587ea6088fd184b0fcb23f9a3b68555101d41` |

The candidate contains exactly the three runtime files below and its embedded
manifest/qualification. The return ZIP contains their exact installed originals
and original deployment receipt. No tests, report, DLL or unrelated dirty-tree
code is a runtime payload. Previous staging measurements/manifests are retained
but superseded; the preceding candidate 01 is the currently installed base,
not an uninstalled alternative. Preparation does not authorize deployment.
Final readback (`release02/archive-verification.json`) verifies both ZIP CRCs,
every internal payload hash, embedded qualification, exact rollback receipt,
all 57 installed base files, eight original manifests and eight unchanged
control files. Frozen test/qualifier hashes and the qualification proof are
unchanged. This readback did not rerun tests or rebuild either archive.

## Remaining boundaries

- The original 37-second evidence interval and AP part cannot be recovered.
- The precise historical disk-lock owner cannot be established from the generic
  timeout. A reproduced admission defect is not a historical ownership trace.
- Actor 85's exact pose/shape/coverage at generations 7717–7732 remains unknown;
  the user's observation of a rear vehicle is not replaced by a modeled pose.
- Native pointer IDs still have no incarnation guarantee. Python continuity
  checks reject observable ambiguities but cannot certify identical-shape
  pointer reuse without a native per-actor lifecycle field.
- OFFLINE VERIFIED applies only to qualified reproductions and diagnostic
  behavior. GAME NOT VERIFIED; no general ACC reliability or right-of-way claim.

## Runtime/return procedure (only after separate deployment approval)

The payload is exactly `core/steering_replay.py`,
`core/navigation/longitudinal_diagnostics.py` and
`core/navigation/diagnostic_build_config.py`. Candidate build ID changes only
the temporary diagnostic identity. Plugin VERSIONs and DLL stay unchanged.
The verification runtime is copied from all installed Python dependencies;
only these three files differ. Unrelated working-tree code is excluded.

1. Stop UltraPilot and ETS2; verify the current receipt and all 57 base hashes
   still match `candidate-manifest.json`. A changed base requires a new review,
   not copying this patch over an unknown installation.
2. Verify both ZIP hashes from the release receipt; extract the candidate into
   staging. Keep the supplied installed-original return archive separately.
3. Copy only the three runtime entries as one stopped-application transaction.
   On any failure restore **all three** originals and the original deployment
   receipt from the return archive before any application restart.
4. Re-read each destination SHA-256 against the manifest and write a truthful
   new deployment receipt including its parent receipt and uncommitted-source
   provenance. Preserve settings, map caches, evidence and the commit marker.
   The old deployment scripts are not authorization to install this candidate.
5. A future separately approved controlled capture requires no arm command:
   normal startup enables this existing temporary collector. With live
   telemetry, allow at least 30 s of history, then the user operates the route,
   braking/wait/resume and manual N. Keep telemetry/application running for at
   least 10 s after the final disable. Unsafe behavior requires immediate
   driver takeover; no deliberate emergency scenario is requested.
6. Inspect the resulting `route-diagnostics/incident-<id>.json` and any
   `-assembled.json` with the matching runtime's existing
   `core.steering_replay.inspect_incident` API. Require actual coverage, AP/input
   links and backend detail, not integrity alone. Keep every continuation and
   attachment, including originals and failure receipts. Early shutdown, pause
   or a real capacity/source failure remains explicitly incomplete.

No part of this preparation performs deployment or requests a new drive now.
