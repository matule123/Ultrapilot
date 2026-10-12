# Semaphore stopping position: geometry audit, 11 October 2026

## Verdict

**OFFLINE VERIFIED:** the reference-distance chain, single subtraction of the
existing spatial margins, and preservation of the stop/hold/green/restart path.
**GAME NOT VERIFIED / requested 1–2 m bumper-to-painted-line position NOT VERIFIED.**
This task has **not fixed the reported excessive physical stopping gap**. No
proven duplicate subtraction or valid truck-specific/painted-line replacement
was found. The conservative fallback is unchanged, not presented as a repair.
Changing its constants would guess the missing geometry and consume a reserve
the user explicitly required us to preserve until measured.

## Source, installation and retained evidence

HEAD `787d012a2a78ac917bb5506e0958c32d8d06575f` plus preserved inherited local
changes. No `AGENTS.md` exists in this checkout or its checked parent directories.
The three requested Oct 11 reports and plugin versioning rules were read.

The installed destination-lifecycle receipt is
`manual-deployment-destination-lifecycle-20261011T095307684Z`;
all **20 installed receipt hashes match**. Receipt SHA-256:
`840992c4f76d63ffc9734854d61b11177631626fd829ddfcaab76051b9a5ce55`.
LF/CRLF-normalized comparison still distinguishes the preceding uninstalled
joint-traffic candidate from the installation. Its ACC 1.1.8 / TurnSignals 1.0.1
changes remain intact. Installed ACC is 1.1.7; DrivePolicy 1.1.3 / Autopilot 1.3.4 /
Map 1.1.1 / DLL `1.59.3-up-signal-scope` are not newly released by this task.

Both original exports pass the existing integrity codec:

| Installed `route-diagnostics` artifact | Identity / content |
| --- | --- |
| `steering-replay-20261011T104936.895268Z-automatic_disable.json` | Pedal incident, SHA-256 `09e3e6508d85c8cb0902171324bee3c5319755ec13edb7bc4a6c36ea76170e0a` |
| `steering-replay-20261011T104938.211656Z-automatic_disable.json` | Dense replay, SHA-256 `e17d17fb489aa3e881917151f763d9958f447c4076ae51bfcb74f439bdd3b15c`, 1,069 samples / 6,444 execution rows |

The retained hold has activation `5688400855600`, session 1, map `promods-1.59`,
dataset `d6cc7936fce4e902761abb5d`, intent `a24f7a16112944b1a758a00989f2f268`,
revision 7, build `c00e4335da75496facf8cab9a15c509c` and immutable geometry
`lane_path/c9b44eacf4cf985f790208939220d1848a26ed0fc117d497480b45a16bd3e5de`.
No different activation or older photographed stop is substituted for it.

## Complete distance and physical-write chain

1. `SignalReader` preserves the native scoped observation time, generation,
   lifecycle, head ID/color and owner. `RouteSignalSelector` matches owner,
   authored directed control group, placement and heading. Head proximity or
   color alone is not authority.
2. Map's `prepare_signal_passages` uses the **first authored curve of the
   selected directed passage**, transforms it with the placed prefab and
   projects it onto the same LanePath. A control group on an inner curve still
   protects that passage entrance. This is not a surveyed physical boundary or
   painted stop line. The lamp position is a qualification input, not the target.
3. The SDK chassis reference and the authored entry are expressed in directed
   route progress. The selector constructs
   `distance = entry_progress - sdk_progress - 6 m - 2 m`.
   The 6 m value is explicitly an **unmeasured front allowance**. The 2 m value
   is a junction stand-off. Each is subtracted **once**, including locked-head
   lookup and the distance-aware unresolved-entry fallback.
4. The shared stopping envelope uses
   `sqrt(2 * 1 m/s² * max(0, distance - speed * (1 s + 0.5 s)))`.
   Its response/transfer allowance is speed-dependent and approaches zero at
   rest; it is not another fixed front allowance. Policy applies this same
   current stop constraint after non-stop preference smoothing. ACC owns the
   ordinary speed/PID decision. Independent valid obstacle/emergency demands
   retain priority through the shared arbitral command.
5. Autopilot validates authority/observations and publishes the paired command.
   Engine validates again before Controller writes the SCS channels in order.
   Terminal service hold is bound to an acknowledged forward-started positive
   brake chain. It keeps zero throttle / continuous positive brake at rest;
   same-head fresh green clears it only with the existing confirmation and no
   other stop dependency. No parking-brake actuation is used.

The actual hold contains **46 summary rows**, monotonic
**5711.6136629–5718.410371 s**, original SDK frames **268439262–275155660**,
locked head **1**, passage
`45540e750098d8f1fc11bc8b76cd20b1ae161420a94ae48b90dad1891389062f`.
Entry progress is **399.833364518 m**, XYZ
**[34753.473500664, 6.90234375, 45663.958017401]**.

Reference-to-derived-target gap is **2.551387–2.551436 m**. With the hash-verified
generator's 6 + 2 m constants, the SDK reference is therefore about **10.5514 m
before the authored entrance**. The compact summary does not itself store the
2 m constant; this inference is distinguished from a captured field.
Retained physical-write aggregates report throttle **0**, brake
**0.1174879596** and no write error. Exact per-write timing for this earlier hold
has aged out of the short journal; all 46 summary rows explicitly indicate
incomplete capture. Thus uninterrupted consumption by ETS2 is not independently
proved by these aggregates. Later green restart is retained in the same drive.

## Geometry availability and precise blocker

| Source inspected | Available | Not established |
| --- | --- | --- |
| Full active map cache: 4,838 prefab descriptions | 74,366 directed nav curves; 8,071 semaphore placements; control IDs, endpoints, map points and transforms | Painted stop-line endpoints or a validated curve-entry-to-line offset |
| SDK chassis/axle geometry, 122 dense rows during this hold | Front axle local Z −1.640 m, rear axle Z +2.094279 m, wheelbase 3.734279 m; origin/heading | Front bumper/body extent; cabin joint, tyre radius and hitch are not the bumper |
| Installed settings and `VehicleProfileProvider` | SDK-observable configuration; existing external profile interface | No configured `vehicle_profiles` catalog; log reports `MISSING_CONFIRMED_BODY_PROFILE` for configuration `e412f13ad3fb22186614354fd724da0b3dfb1ebcde848323bd222677213d8bc1` |
| Existing collision-asset compiler/catalog | Explicit candidate dimensions, provenance and confirmation validation | Compiler states `MISSING_VERIFIED_COLLISION_DECODER` and `MISSING_ATOMIC_ACTIVE_ASSET_BINDING`; synthetic/candidate profiles cannot become live measurements |
| Pinned native traffic source | Other actors' box centers/dimensions | `get_player_traffic_data` explicitly excludes our own tractor/trailers; no existing ego-bumper output contract |

Map cache SHA-256:
`b873d516c0d5f378c66eb54e8376dbdd2265aa78a4042ace1d8ba7e7709eba35`.
Native source is the already pinned `1f16156b9b37b70cf182c2bc09120fa1b234e129`.
The shared-memory SDK configuration exposes axle/cabin/head/hook positions,
not body-front dimensions. Possible native ego box access is not an existing
validated transport and is not implemented speculatively by changing the DLL.

An existing confirmed `Body.front_m`, if actually supplied, would be referenced
to the **rear axle**, not the SDK chassis origin. With Z positive backwards,
the origin-to-front extent is `Body.front_m - rear_axle_local_z`, not wheelbase,
front-axle distance or `Body.front_m` alone. A test demonstrates two different
synthetic fronts (2.9 / 4.4 m from origin) consistent with exactly the same SDK
axles. Neither is a calibration of this user's truck.

**Smallest required evidence:** one metric calibration record containing the
actual front bumper segment in this truck's SDK-local coordinates and the
painted line endpoints in the placed prefab's/world coordinates, with units,
uncertainty, vehicle configuration, dataset/placement and a bound SDK frame/pose.
An existing verified asset measurement or a stationary measurement can provide
it; no new drive is requested. A photograph or one guessed universal offset
cannot. On a curve, transform/project the actual bumper on the directed route
and locate its intersection with the correct lane's line. A nominal 1.5 m
clearance would then be applied once. The reference planning target and actuator
stopping residual must remain separate. The hold's extra 2.5514 m residual
cannot be attributed to one exact earlier write because those writes are missing.

## Unchanged closed-plant verification

18 actual PPD → native-byte reader → selector → Traffic → Policy → ACC →
Autopilot → Engine → real Controller / chronological BytesIO-backend cases:
20/35/50 km/h, both automatic modes, straight and left/right radius-60 m
synthetic approaches tangent to the same authored prefab entrance.
Geometry is a modeled approach, not the physical lane/painted line of the drive.
100 m initial reference distance, seeded 33/50/80 ms ticks, producer delays
12/8/10 ms, 120 ms actuator transport and 350 ms response. Existing flat plant:
`a=(2.2*T-4*B)/1.4-0.12-0.004*v²`, with speed clamped at zero.

| Speed | Samples per case / duration | Reference gap to derived target | Peak deceleration | Peak model jerk | Pedal mode changes |
| --- | --- | --- | --- | --- | --- |
| 20 km/h | 456 / 24.365 s | 1.3869–1.3882 m | 1.2441–1.2443 m/s² | 11.950–12.077 m/s³ | 2 |
| 35 km/h | 373 / 20.090 s | 1.3378–1.3389 m | 1.3408–1.3410 m/s² | 11.771–11.881 m/s³ | 2 |
| 50 km/h | 362 / 19.454 s | 1.3776–1.3785 m | 1.6288–1.6290 m/s² | 28.128–28.541 m/s³ | 1 |

The table is **one unchanged runtime**, not a claimed before/after improvement.
Jerk uses actual adjacent sampled acceleration differences / elapsed dt,
including the model's zero-speed clamp; terminal peaks are not certified ETS2
comfort. Brake onset reference distance to entrance is 31.710–31.725,
67.750–67.765 and 99.292–99.307 m, respectively.
All 18 cases: zero modeled-front entry overruns, positive pedal overlaps,
standstill brake-zero samples or parking writes; active hold and green restart.
No time below 5 km/h more than 10 m from the derived target.

Front sensitivity is explicitly post-processing of the same plant: assumed
SDK-front extents 3/4/6 m imply **6.338–6.388 / 5.338–5.388 / 3.338–3.388 m**
to the authored entry. These are neither different calibrated vehicle-response
models nor bumper-to-painted-line gaps. The latter remains null / NOT VERIFIED.
No criterion is invented to call those gaps the requested 1–2 m PASS.

No failing production fix is claimed: tests expose insufficient geometry and
check the existing single-subtraction/hold/restart contracts. Initial new tests
incorrectly put a truck off the rotated fixture approach; their pose now follows
that fixture's actual tangent. Production localization checks were not changed.

## Reproduction, files and handoff

From this repository, `PYTHONCASEOK=1`:

```powershell
python -m tools.audit_oct11_stop_geometry --output docs/steering-audit/oct11-stop-geometry/audit.json
python -m tools.audit_oct11_stop_geometry --output docs/steering-audit/oct11-stop-geometry/model-audit.json --models
python -m pytest tests/test_oct11_stop_geometry_audit.py tests/test_prefab_signal_binding.py tests/test_oct11_red_approach.py tests/test_oct10_signal_timing.py tests/test_stage5b1_vehicle_profile.py tests/test_service_prefab_diagnostics.py -q
```

Changed only this report, `DEFERRED_WORK.md`,
`tools/audit_oct11_stop_geometry.py` and `tests/test_oct11_stop_geometry_audit.py`.
Verification: **97 existing targeted tests + 34 subtests passed**, covering
prefab binding, red-profile/green timing, geometry absence/ambiguity, signal
loss, foreign ownership, context changes and diagnostic preservation.
After fixing the new fixture's pose, **all 16 new targeted tests passed**
(17.91 s). The three earlier new-fixture failures are not claimed as production
reproductions. All 18 model cases pass their explicit invariants. `compileall`
and `git diff --check` pass. The full pytest suite was not run.

**New runtime/DLL deployment delta for this task: EMPTY.** No plugin version
or changelog release is appropriate for an analysis/test-only change. Existing
uninstalled joint-traffic runtime changes are listed in the preceding report
and must not be silently deployed as a stop-line fix. No steering/planner/PID,
timeout, geometry, brake hold or installed file was changed. The snapshot of
all 120 Python runtime files verifies preservation.

The exact painted-line/bumper target remains open until the bound geometry is
available. Full pytest and explicit deployment approval remain user gates for
any later actual runtime correction. No game, deployment, commit or push.
