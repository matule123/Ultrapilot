# Local commit plan — 12 October 2026

Repository: `C:/Users/PC/Documents/GitHub/ets2la`

Baseline HEAD: `787d012 fix: synchronize longitudinal commands with vehicle observations`.
This is a file-level partition of the current accumulated changes, not a reconstruction
of the original chronological fixes. Shared runtime files contain several tasks;
splitting those tasks needs selective hunks and separately verified intermediate states.
No files were staged and no commit or push was performed.

The four commits form one dependent series. Their intermediate snapshots have not
been tested independently; run the full suite on the complete series. Tests import
new analytical tools, and those tools can import test fixtures. Do not describe each
intermediate commit as independently green.

All paths below are absolute and identify only current modified/untracked files.

## 1. Shared runtime and plugin versions

Subject:
```text
fix: stabilize traffic control and update ACC, Map and TurnSignals
```

Body:
```text
Consolidate pending signal ownership, phase-aware stopping, longitudinal lease and brake-continuity fixes; retain bounded pedal history and original timestamps. Handle observed lead departures and trailer conflicts, improve destination completion and PID drive inhibition, and select roundabout indicators from connected topology. Update ACC to 1.1.9, Map to 1.1.2, TurnSignals to 1.0.2, DrivePolicy to 1.1.3 and Autopilot to 1.3.4. Preserve manual indicators, safety gates and documented geometry limitations.
```

Files (24):

- [PLUGIN_CHANGELOG.md](C:/Users/PC/Documents/GitHub/ets2la/PLUGIN_CHANGELOG.md)
- [core/acc_following.py](C:/Users/PC/Documents/GitHub/ets2la/core/acc_following.py)
- [core/engine.py](C:/Users/PC/Documents/GitHub/ets2la/core/engine.py)
- [core/longitudinal.py](C:/Users/PC/Documents/GitHub/ets2la/core/longitudinal.py)
- [core/navigation/evidence_worker.py](C:/Users/PC/Documents/GitHub/ets2la/core/navigation/evidence_worker.py)
- [core/navigation/longitudinal_diagnostics.py](C:/Users/PC/Documents/GitHub/ets2la/core/navigation/longitudinal_diagnostics.py)
- [core/navigation/prefab_signals.py](C:/Users/PC/Documents/GitHub/ets2la/core/navigation/prefab_signals.py)
- [core/navigation/road_network.py](C:/Users/PC/Documents/GitHub/ets2la/core/navigation/road_network.py)
- [core/pid.py](C:/Users/PC/Documents/GitHub/ets2la/core/pid.py)
- [core/plugin_manager.py](C:/Users/PC/Documents/GitHub/ets2la/core/plugin_manager.py)
- [core/sdk/ets2la_data.py](C:/Users/PC/Documents/GitHub/ets2la/core/sdk/ets2la_data.py)
- [core/sdk/signal_snapshot.py](C:/Users/PC/Documents/GitHub/ets2la/core/sdk/signal_snapshot.py)
- [core/service_brake_hold.py](C:/Users/PC/Documents/GitHub/ets2la/core/service_brake_hold.py)
- [core/steering_replay.py](C:/Users/PC/Documents/GitHub/ets2la/core/steering_replay.py)
- [core/transmission_mode.py](C:/Users/PC/Documents/GitHub/ets2la/core/transmission_mode.py)
- [plugins/acc/main.py](C:/Users/PC/Documents/GitHub/ets2la/plugins/acc/main.py)
- [plugins/autopilot/main.py](C:/Users/PC/Documents/GitHub/ets2la/plugins/autopilot/main.py)
- [plugins/drivepolicy/main.py](C:/Users/PC/Documents/GitHub/ets2la/plugins/drivepolicy/main.py)
- [plugins/map/main.py](C:/Users/PC/Documents/GitHub/ets2la/plugins/map/main.py)
- [plugins/turnsignals/main.py](C:/Users/PC/Documents/GitHub/ets2la/plugins/turnsignals/main.py)
- [tools/build_signal_plugin.py](C:/Users/PC/Documents/GitHub/ets2la/tools/build_signal_plugin.py)
- [tools/signal_plugin/snapshot.hpp](C:/Users/PC/Documents/GitHub/ets2la/tools/signal_plugin/snapshot.hpp)
- [ui/visualization.py](C:/Users/PC/Documents/GitHub/ets2la/ui/visualization.py)
- [core/navigation/turn_maneuvers.py](C:/Users/PC/Documents/GitHub/ets2la/core/navigation/turn_maneuvers.py)

## 2. Analysis and reproduction tools

Subject:
```text
chore: add Phase 7 incident analysis and control benchmarks
```

Body:
```text
Add read-only incident analysis, frozen-baseline reproductions, native-signal inspection, local stop-pose comparison and paired closed-loop benchmarks. Distinguish backend writes and model results from game consumption, physical stop-line calibration and game verification.
```

Files (36):

- [tools/analyze_longitudinal_evidence.py](C:/Users/PC/Documents/GitHub/ets2la/tools/analyze_longitudinal_evidence.py)
- [tools/benchmark_signal_snapshot.py](C:/Users/PC/Documents/GitHub/ets2la/tools/benchmark_signal_snapshot.py)
- [tools/run_prefab_signal_bench.py](C:/Users/PC/Documents/GitHub/ets2la/tools/run_prefab_signal_bench.py)
- [tools/analyze_oct10_signal_approach.py](C:/Users/PC/Documents/GitHub/ets2la/tools/analyze_oct10_signal_approach.py)
- [tools/analyze_oct10_signal_flow.py](C:/Users/PC/Documents/GitHub/ets2la/tools/analyze_oct10_signal_flow.py)
- [tools/analyze_oct10_traffic_incident.py](C:/Users/PC/Documents/GitHub/ets2la/tools/analyze_oct10_traffic_incident.py)
- [tools/analyze_oct11_lifecycle.py](C:/Users/PC/Documents/GitHub/ets2la/tools/analyze_oct11_lifecycle.py)
- [tools/analyze_oct11_red_approach.py](C:/Users/PC/Documents/GitHub/ets2la/tools/analyze_oct11_red_approach.py)
- [tools/analyze_oct11_regressions.py](C:/Users/PC/Documents/GitHub/ets2la/tools/analyze_oct11_regressions.py)
- [tools/analyze_oct8_signal_stop.py](C:/Users/PC/Documents/GitHub/ets2la/tools/analyze_oct8_signal_stop.py)
- [tools/analyze_oct9_packet_flow.py](C:/Users/PC/Documents/GitHub/ets2la/tools/analyze_oct9_packet_flow.py)
- [tools/audit_oct10_history.py](C:/Users/PC/Documents/GitHub/ets2la/tools/audit_oct10_history.py)
- [tools/audit_oct10_native_signal.py](C:/Users/PC/Documents/GitHub/ets2la/tools/audit_oct10_native_signal.py)
- [tools/audit_oct11_stop_geometry.py](C:/Users/PC/Documents/GitHub/ets2la/tools/audit_oct11_stop_geometry.py)
- [tools/benchmark_automatic_longitudinal.py](C:/Users/PC/Documents/GitHub/ets2la/tools/benchmark_automatic_longitudinal.py)
- [tools/benchmark_oct10_signal_flow.py](C:/Users/PC/Documents/GitHub/ets2la/tools/benchmark_oct10_signal_flow.py)
- [tools/benchmark_oct10_traffic_contract.py](C:/Users/PC/Documents/GitHub/ets2la/tools/benchmark_oct10_traffic_contract.py)
- [tools/benchmark_oct11_joint.py](C:/Users/PC/Documents/GitHub/ets2la/tools/benchmark_oct11_joint.py)
- [tools/benchmark_oct9_control_flow.py](C:/Users/PC/Documents/GitHub/ets2la/tools/benchmark_oct9_control_flow.py)
- [tools/compare_oct11_stationary_stop.py](C:/Users/PC/Documents/GitHub/ets2la/tools/compare_oct11_stationary_stop.py)
- [tools/extract_oct10_signal_ppd.ps1](C:/Users/PC/Documents/GitHub/ets2la/tools/extract_oct10_signal_ppd.ps1)
- [tools/profile_oct9_map.py](C:/Users/PC/Documents/GitHub/ets2la/tools/profile_oct9_map.py)
- [tools/recover_steering_route.py](C:/Users/PC/Documents/GitHub/ets2la/tools/recover_steering_route.py)
- [tools/reproduce_oct10_signal_place.py](C:/Users/PC/Documents/GitHub/ets2la/tools/reproduce_oct10_signal_place.py)
- [tools/reproduce_oct9_baseline.py](C:/Users/PC/Documents/GitHub/ets2la/tools/reproduce_oct9_baseline.py)
- [tools/run_oct10_signal_timing_bench.py](C:/Users/PC/Documents/GitHub/ets2la/tools/run_oct10_signal_timing_bench.py)
- [tools/run_oct11_destination_bench.py](C:/Users/PC/Documents/GitHub/ets2la/tools/run_oct11_destination_bench.py)
- [tools/run_oct11_red_approach_bench.py](C:/Users/PC/Documents/GitHub/ets2la/tools/run_oct11_red_approach_bench.py)
- [tools/run_oct11_terminal_stop_bench.py](C:/Users/PC/Documents/GitHub/ets2la/tools/run_oct11_terminal_stop_bench.py)
- [tools/run_oct12_stop_indicators_bench.py](C:/Users/PC/Documents/GitHub/ets2la/tools/run_oct12_stop_indicators_bench.py)
- [tools/run_oct8_signal_approach_bench.py](C:/Users/PC/Documents/GitHub/ets2la/tools/run_oct8_signal_approach_bench.py)
- [tools/run_oct8_stop_lifecycle_bench.py](C:/Users/PC/Documents/GitHub/ets2la/tools/run_oct8_stop_lifecycle_bench.py)
- [tools/signal_plugin/probe_scoped.cpp](C:/Users/PC/Documents/GitHub/ets2la/tools/signal_plugin/probe_scoped.cpp)
- [tools/summarize_oct10_profiles.py](C:/Users/PC/Documents/GitHub/ets2la/tools/summarize_oct10_profiles.py)
- [tools/verify_oct10_signal_baseline.py](C:/Users/PC/Documents/GitHub/ets2la/tools/verify_oct10_signal_baseline.py)
- [tools/verify_oct11_joint_baseline.py](C:/Users/PC/Documents/GitHub/ets2la/tools/verify_oct11_joint_baseline.py)

## 3. Regression tests and fixtures

Subject:
```text
test: cover signal lifecycles, ACC departures and maneuver indicators
```

Body:
```text
Add and update regression coverage for activation races, packet freshness, continuous service-brake holding, same-signal green restart, destination completion, lead departure and traffic availability. Cover topology-owned roundabout exits, manual indicator priority, bounded diagnostic history and calibration limits using explicit fixtures.
```

Files (46):

- [tests/test_app_release_notice.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_app_release_notice.py)
- [tests/test_control_safety_regressions.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_control_safety_regressions.py)
- [tests/test_oct4_signal_lifecycle.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct4_signal_lifecycle.py)
- [tests/test_oct5_traffic_approach.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct5_traffic_approach.py)
- [tests/test_oct6_joint_stop_flow.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct6_joint_stop_flow.py)
- [tests/test_policy_signal_light_regressions.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_policy_signal_light_regressions.py)
- [tests/test_prefab_signal_binding.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_prefab_signal_binding.py)
- [tests/test_roundabout_intervention_reporting.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_roundabout_intervention_reporting.py)
- [tests/test_signal_cpp_probe.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_signal_cpp_probe.py)
- [tests/test_signal_stop_resume.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_signal_stop_resume.py)
- [tests/test_stop_handover_and_quiet_logging.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_stop_handover_and_quiet_logging.py)
- [tests/fixtures/oct10-signal-place.json](C:/Users/PC/Documents/GitHub/ets2la/tests/fixtures/oct10-signal-place.json)
- [tests/fixtures/oct11-joint-original-functions.json](C:/Users/PC/Documents/GitHub/ets2la/tests/fixtures/oct11-joint-original-functions.json)
- [tests/fixtures/oct11-red-original-functions.json](C:/Users/PC/Documents/GitHub/ets2la/tests/fixtures/oct11-red-original-functions.json)
- [tests/fixtures/oct11-terminal-original.json](C:/Users/PC/Documents/GitHub/ets2la/tests/fixtures/oct11-terminal-original.json)
- [tests/fixtures/oct12-circulation-topology.json](C:/Users/PC/Documents/GitHub/ets2la/tests/fixtures/oct12-circulation-topology.json)
- [tests/fixtures/oct12-original-functions.json](C:/Users/PC/Documents/GitHub/ets2la/tests/fixtures/oct12-original-functions.json)
- [tests/fixtures/oct8-deployed-prefabs.json](C:/Users/PC/Documents/GitHub/ets2la/tests/fixtures/oct8-deployed-prefabs.json)
- [tests/fixtures/oct8-observed-route-prefix.json](C:/Users/PC/Documents/GitHub/ets2la/tests/fixtures/oct8-observed-route-prefix.json)
- [tests/fixtures/oct8-real-signal-prefabs.json](C:/Users/PC/Documents/GitHub/ets2la/tests/fixtures/oct8-real-signal-prefabs.json)
- [tests/test_automatic_longitudinal_replay.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_automatic_longitudinal_replay.py)
- [tests/test_oct10_native_signal_direction.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct10_native_signal_direction.py)
- [tests/test_oct10_reactivation_traffic.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct10_reactivation_traffic.py)
- [tests/test_oct10_signal_approach.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct10_signal_approach.py)
- [tests/test_oct10_signal_timing.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct10_signal_timing.py)
- [tests/test_oct10_traffic_availability.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct10_traffic_availability.py)
- [tests/test_oct11_destination_flow.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct11_destination_flow.py)
- [tests/test_oct11_joint_regressions.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct11_joint_regressions.py)
- [tests/test_oct11_red_approach.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct11_red_approach.py)
- [tests/test_oct11_stationary_stop_comparison.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct11_stationary_stop_comparison.py)
- [tests/test_oct11_stop_geometry_audit.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct11_stop_geometry_audit.py)
- [tests/test_oct11_terminal_approach.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct11_terminal_approach.py)
- [tests/test_oct12_stop_and_indicators.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct12_stop_and_indicators.py)
- [tests/test_oct7_coast_and_signal_scope.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct7_coast_and_signal_scope.py)
- [tests/test_oct8_signal_approach_consistency.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct8_signal_approach_consistency.py)
- [tests/test_oct8_signal_coverage.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct8_signal_coverage.py)
- [tests/test_oct8_stop_lifecycle.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct8_stop_lifecycle.py)
- [tests/test_oct9_packet_refresh.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct9_packet_refresh.py)
- [tests/test_oct9_traffic_control_contract.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_oct9_traffic_control_contract.py)
- [tests/test_pedal_decision_history.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_pedal_decision_history.py)
- [tests/test_replay_route_recovery.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_replay_route_recovery.py)
- [tests/test_scoped_signal_binding.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_scoped_signal_binding.py)
- [tests/test_scoped_signal_contract.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_scoped_signal_contract.py)
- [tests/test_service_hold_comfort.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_service_hold_comfort.py)
- [tests/test_signal_hud_presentation.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_signal_hud_presentation.py)
- [tests/test_significant_longitudinal_events.py](C:/Users/PC/Documents/GitHub/ets2la/tests/test_significant_longitudinal_events.py)

## 4. Reports and deferred work

Subject:
```text
docs: document Phase 7 fixes and remaining verification limits
```

Body:
```text
Record incident findings, implementation boundaries, offline results, deployment history and calibration evidence. Keep physical bumper-to-painted-line placement, unresolved historical causes and unverified game behavior explicit; update longitudinal diagnostic documentation and deferred work.
```

Files (25):

- [DEFERRED_WORK.md](C:/Users/PC/Documents/GitHub/ets2la/DEFERRED_WORK.md)
- [PHASE7_LONGITUDINAL_DIAGNOSTICS.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_LONGITUDINAL_DIAGNOSTICS.md)
- [PHASE7_AUTOMATIC_PEDAL_EVIDENCE_20261007.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_AUTOMATIC_PEDAL_EVIDENCE_20261007.md)
- [PHASE7_COAST_AND_SIGNAL_SCOPE_20261007.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_COAST_AND_SIGNAL_SCOPE_20261007.md)
- [PHASE7_DESTINATION_AND_APPROACH_REVIEW_20261011.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_DESTINATION_AND_APPROACH_REVIEW_20261011.md)
- [PHASE7_JOINT_TRAFFIC_AND_INDICATORS_20261011.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_JOINT_TRAFFIC_AND_INDICATORS_20261011.md)
- [PHASE7_PACKET_REFRESH_DEPLOYMENT_20261010.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_PACKET_REFRESH_DEPLOYMENT_20261010.md)
- [PHASE7_PACKET_REFRESH_RELIABILITY_20261010.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_PACKET_REFRESH_RELIABILITY_20261010.md)
- [PHASE7_PEDAL_HISTORY_20261007.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_PEDAL_HISTORY_20261007.md)
- [PHASE7_REACTIVATION_TRAFFIC_20261010.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_REACTIVATION_TRAFFIC_20261010.md)
- [PHASE7_RED_APPROACH_PROFILE_20261011.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_RED_APPROACH_PROFILE_20261011.md)
- [PHASE7_SIGNAL_AND_TRAFFIC_COMPLETION_20261009.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_SIGNAL_AND_TRAFFIC_COMPLETION_20261009.md)
- [PHASE7_SIGNAL_APPROACH_CONSISTENCY_20261008.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_SIGNAL_APPROACH_CONSISTENCY_20261008.md)
- [PHASE7_SIGNAL_APPROACH_TIMING_20261010.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_SIGNAL_APPROACH_TIMING_20261010.md)
- [PHASE7_SIGNAL_COVERAGE_AND_BRAKE_REVIEW_20261009.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_SIGNAL_COVERAGE_AND_BRAKE_REVIEW_20261009.md)
- [PHASE7_SIGNAL_DISTANCE_CONTRACT_20261010.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_SIGNAL_DISTANCE_CONTRACT_20261010.md)
- [PHASE7_SIGNAL_NATIVE_DIRECTION_20261010.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_SIGNAL_NATIVE_DIRECTION_20261010.md)
- [PHASE7_SIGNAL_STOP_LIFECYCLE_20261008.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_SIGNAL_STOP_LIFECYCLE_20261008.md)
- [PHASE7_STATIONARY_STOP_COMPARISON_20261011.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_STATIONARY_STOP_COMPARISON_20261011.md)
- [PHASE7_STOP_AND_MANEUVER_INDICATORS_20261012.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_STOP_AND_MANEUVER_INDICATORS_20261012.md)
- [PHASE7_STOP_LINE_GEOMETRY_20261011.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_STOP_LINE_GEOMETRY_20261011.md)
- [PHASE7_TERMINAL_APPROACH_20261012.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_TERMINAL_APPROACH_20261012.md)
- [PHASE7_TRAFFIC_AVAILABILITY_20261010.md](C:/Users/PC/Documents/GitHub/ets2la/PHASE7_TRAFFIC_AVAILABILITY_20261010.md)
- [](C:/Users/PC/Documents/GitHub/ets2la/)
- [COMMIT_PLAN_20261012.md](C:/Users/PC/Documents/GitHub/ets2la/COMMIT_PLAN_20261012.md)

## Exclude

Do not stage `.tmp*`, `.codex`, settings, map/model caches, logs, raw game collections,
route replays, backups, deployment receipts, executables or local `docs/steering-audit`
outputs. Do not use `git add -f` to include ignored artifacts. Controlled fixtures
under `tests/fixtures` are intentionally separate from raw game exports.

No DLL binary is currently listed as modified/untracked by git status. Native source
and build-script changes do not imply a new compiled DLL is included. Verify release
packaging separately if binary delivery is needed; do not invent a DLL update here.

The latest user-reported full-suite PASS applies to the completed working tree,
not to a guarantee that physical signal placement or every game scenario is fixed.

