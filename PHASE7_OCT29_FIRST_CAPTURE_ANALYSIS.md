# October 29 first diagnostic capture — read-only findings

Scope: analysis only; no runtime or installed changes. Source incident:
`incident-d8f8382277da40c398b28c5fcf315a11-14102.json` under the installed
UltraPilot route-diagnostics directory. Its Engine replay is
`steering-replay-20261029T130620.051281Z-diagnostic_incident.json`.

## Proven physical-boundary rejection

At local 14:05:31 the Engine reported `ACC moving constraint unavailable before
write`. This is not an input-lease expiry. The selected decision at monotonic
22771.6907128 retains moving_target_ids/observed_motion_ids=[66], throttle
0.24694000000017696, brake=0, and expires_at=22771.8308795.

Consumed traffic record 16993 still contains crossing constraint 66 (slot 2,
native lifecycle 104452067223580, generation 4250), cap=1.2598660036521165 m/s.
ACC record 16994 is valid, following_target_id=66, following_kind=crossing,
computed_at=22771.638775, expires_at=22771.9819228.

The final traffic reread, record 17004 at 22771.7443556, is also valid and
expires_at=22772.0760269, but motion_constraint=None. Crossing conflicts are
empty. The same actor's native continuity remains recorded (generation 4253),
explicitly *not* a proof of clearance. Thus actor disappearance is not proven.
Binding record at 22771.7560637 points to consumer_traffic=17004 and
consumer_acc=16994. The selected result becomes engine_safety with the exact
rejection above. `core/longitudinal.py:signal_drive_write_guard` rejects when
original moving IDs exist but newer traffic motion_constraint is absent.

This establishes an older ACC constraint versus newer traffic qualification
transition at the last write guard. It does not establish that unqualified
traffic can safely authorize acceleration or that the guard should be removed.

## Earlier braking is a separate question

Output summaries show curve braking around 22764.46 (26.3 km/h), protective
crossing constraints for actors 39/51 around 22767.18, then actor 66 around
22770.57 with selected brake 0.35 at 15.6 km/h. Around 22771.57 a positive
throttle is selected at 1.47 km/h; the technical rejection follows near zero.
Determining whether the crossing prediction itself was physically warranted
requires reconstructing actor/body versus ego trajectory geometry. IDs alone
do not prove an obstacle or identify its make/color.

## Capture defects and usable evidence

Outer incident and Engine replay integrity checks pass, but complete=false,
assembly_complete=false. AP_PART_NOT_DELIVERED_WITHIN_ASSEMBLY_WINDOW is recorded.
The AP file exists separately, created at 13:06:56Z and written by 14:07:02,
after incident finalization around 14:06:34. Its own replay integrity passes;
994 ap_decision records remain, capture_failures=1. This analysis does not
retroactively certify it as an assembled complete part.

Engine full backend detail: 565 calls, zero missing call sequences, zero missing
decision/consumed-input references, no invalid calls. Decision-summary capture
reports six failures, with exact exceptions not established here. Native
daemon-child AssertionError from October 26 is not present in this event's log.
The new defect is late assembly delivery, not proof that no AP data were saved.

No further drive is needed to reproduce the demonstrated write-guard transition.
Keep originals. Next engineering work should replay the exact pinned ACC and
new traffic pair, separately inspect crossing geometry, and reproduce late AP
delivery without granting unproven clearance or extending freshness limits.
