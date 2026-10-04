# UltraPilot

Driving assistance for **Euro Truck Simulator 2**, built around map-based navigation, lane keeping, speed control and an in-game HUD. Inspired by [ETS2LA](https://github.com/ETS2LA/Euro-Truck-Simulator-2-Lane-Assist).

![version](https://img.shields.io/badge/version-0.5.0-2563EB)
![platform](https://img.shields.io/badge/platform-Windows%2010%2F11-475569)
![python](https://img.shields.io/badge/python-3.10%2B-475569)
![status](https://img.shields.io/badge/status-experimental-D97706)

[Getting started](#getting-started) · [What's new](#whats-new-in-v050) · [Plugins](#plugins) · [Known limitations](#known-limitations) · [Development](#development)

> UltraPilot is experimental simulator software, not a fully autonomous driver. Stay ready to take over. Offline tests do not certify every road, intersection, vehicle or game version.

## What's new in v0.5.0

This release brings together the work since v0.4.2, whose source commit dates to **1 August 2026**.

- **Reworked steering:** map-based lateral control, improved lane projection and cab reference, calibrated steering dynamics and a separate high-frequency command executor.
- **Faster navigation:** reuse of unchanged route/prefab geometry, fewer IPC transfers and removal of unnecessary route validation from the steering path.
- **Fresher commands:** coherent SDK observations, freshness checks after preparation/localization and fixes for activation, heartbeat and command-handoff races. The 500 ms steering-observation limit remains.
- **Stronger route building:** fixes for connected prefab entries, confidence on validated corridors, LaneId continuity and advancing GPS windows.
- **Coordinated pedals:** paired throttle/brake commands, shared arbitration, ACC braking, smoother ordinary throttle recovery and anticipatory curve-speed constraints. Emergency response bypasses comfort ramping.
- **Transmission-aware activation:** automatic mode detection and a settings override; bounded throttle launch for simple automatic and Drive confirmation for real automatic.
- **Traffic-light waiting:** supported continuous service-brake waiting and restart from fresh, relevant green evidence, with the updated ETS2LA signal DLL. No parking-brake automation.
- **Clearer UI and diagnostics:** HUD/AR/map improvements, notification sounds, precise intervention reasons, quieter routine logging and integrity-checked diagnostic exports.
- **Cleaner updates:** runtime-only ZIP installation, protected user data and app-version announcements with individual plugin release histories.

See [the complete v0.5.0 release notes](RELEASE_NOTES_0.5.0.md) for the reviewed commit inventory and verification boundaries. The [plugin changelog](PLUGIN_CHANGELOG.md) records individual plugin releases.

## What UltraPilot does

| Area | Current capability |
| --- | --- |
| Navigation and lane keeping | Builds a directed lane trajectory from game GPS/map data and calculates steering from current SDK observations. |
| Speed and pedals | Combines speed limits, curve constraints and braking requests through one longitudinal-command path. |
| ACC and traffic | Uses route-projected traffic candidates when available; target loss and uncertain evidence can require driver takeover. |
| Signals | Supports brake waiting and conditional restart using the new producer-timed signal source. See the limitations below. |
| Visualization | Transparent HUD, experimental AR route overlay and a live map view. |
| Interface | Plugin controls and versions, transmission settings, status notifications, sound cues and voice announcements. |
| Diagnostics | Steering replays and opt-in combined collections with command provenance, timestamps and integrity checks. |

## Getting started

### Requirements and compatibility

- Windows 10/11 and a compatible game installation.
- A map dataset matching the **running game version and map/mod configuration**. Do not substitute an older dataset just because it downloads successfully.
- Compatible game-side SDK/traffic DLLs. The new signal producer shipped for this release targets **ETS2 1.59.x**; that is not a compatibility guarantee for other game versions.
- For source installations: Python 3.10+ and the packages in [requirements.txt](requirements.txt).

Some code paths also support ATS. ETS2 validation must not be treated as equivalent ATS or TruckersMP validation; check the specific game, dataset and DLL combination before use.

### Install from source

Run in PowerShell:

```powershell
git clone https://github.com/matule123/Ultrapilot.git
cd Ultrapilot
python -m pip install -r requirements.txt
python main.py
```

This follows the repository's current default branch, not a pinned v0.5.0 package. Run the application as a **normal user**, not as administrator.

### Windows installer

If an `UltraPilot_Installer.exe` is published, obtain it from this repository's [Releases page](https://github.com/matule123/Ultrapilot/releases). A version-bump commit does not itself publish an installer or GitHub Release.

The installer downloads application sources, prepares Python/dependencies and sets up shortcuts and game integrations. Onboarding guides language, SDK and map setup. Close the game when installing or replacing its DLLs; an in-app Python update cannot replace a DLL already loaded by ETS2.

### First drive

1. Complete setup and select the dataset matching your game and mods.
2. Set a **GPS destination in the game** and wait for UltraPilot to report a valid route and current telemetry.
3. Check the detected transmission mode in Settings. Override it only when detection does not match your actual game configuration.
4. Begin on a clear, simple section of road. Use **N** or the application's autopilot control to request activation; read any refusal or takeover message instead of repeatedly requesting activation.
5. Monitor the vehicle and be ready to take over. Do not test uncertain behavior in traffic or assume an empty traffic buffer means a clear road.

Disabling cancels driving authority and releases commanded inputs. Released pedals do **not** guarantee the truck will remain stationary on a slope.

## Updates and release history

The sidebar shows the **UltraPilot version and source commit separately**. Commit-only updates can arrive between app releases. On an app-version upgrade, a scrollable release window shows application changes and every documented intermediate plugin version; dismissal is remembered per installation.

For ZIP installations, the updater installs runtime directories and selected user-facing files. It preserves settings, routes, map caches, logs and diagnostic collections. Tests, audit tools, phase reports and hidden development folders are excluded from new payloads. Previously installed development files are not automatically cleaned up.

The download is still a source archive, not a minimal runtime package. Source checkouts updated by Git retain the full repository. Updates are not an all-files transaction or a complete rollback system, and dependency/game-DLL installation is separate from ZIP application.

Details: [update policy](UPDATE_POLICY.md) · [release-note maintenance](APP_RELEASE_NOTES.md).

## Plugins

All 12 built-in plugins have independent versions, visible on their cards even when disabled. The table below is the **v0.5.0 release snapshot**, not an assertion that every capability is complete.

| Plugin | Version | Responsibility |
| --- | --- | --- |
| Autopilot | 1.2.0 | Coordinates steering, paired pedals, activation and supported signal waiting/restart. |
| ACC | 1.1.1 | Speed PID, traffic-candidate constraints and target-loss handling. |
| Map | 1.0.3 | Map dataset, lane localization, GPS trajectory and bound steering/curve data. |
| DrivePolicy | 1.0.3 | Driving preferences and speed ceilings under current constraints. |
| Collision | 1.0.1 | Relays collision/traffic braking evidence without renewing its validity. |
| EcoDrive | 1.0.1 | Optional bounded throttle-recovery preference; does not own the pedals. |
| LaneControl | 1.0.0 | Lane-control assistance; does not certify general overtaking or merging. |
| TurnSignals | 1.0.0 | Route-related indicator assistance. |
| Toll | 1.0.0 | Toll assistance. |
| TTS | 1.0.0 | Spoken notifications. |
| HUD | 1.0.0 | HUD data integration; the main overlay is a separate process. |
| Discord | 1.0.0 | Optional Discord Rich Presence. |

Plugins ship as a coordinated application build. Independent mixed-version updates and plugin dependency checks are not implemented. See [versioning rules](PLUGIN_VERSIONS.md) and [per-version changes](PLUGIN_CHANGELOG.md).

## Known limitations

- **Signals:** restart requires the compatible new DLL, fresh acquisitions of the same relevant locked signal, uninterrupted brake evidence and valid route/control authority. Signal relevance is a geometric heuristic, not a proven signal-to-lane binding for every junction.
- **Traffic:** the legacy traffic source does not prove complete coverage or actor freshness. Predictive roundabout gap acceptance and general ACC stop-and-go remain unsupported or unverified.
- **Holding:** continuous software brake writes are not proof of uninterrupted game consumption or physical hill holding. UltraPilot does not automate the parking brake.
- **Steering and timing:** naturalness on every curve and elimination of all long scheduling pauses are not established. Stale or invalid evidence can still trigger a controlled stop or takeover.
- **Trailer/manoeuvre work:** vehicle-profile compilation, swept-envelope and local-manoeuvre foundations are present, but experimental trailer guidance and general overtaking are not automatically authorized.

For precise scope, see [deferred work](DEFERRED_WORK.md), [Phase 6 results](PHASE6_FINAL_RESULTS.md) and [Phase 7 results](PHASE7_FINAL_RESULTS.md). These reports distinguish offline verification from actual game measurements.

## Development

### Runtime structure

```text
main.py → bootloader.py
          ├─ Engine → plugin processes → guarded Controller writes
          ├─ UI → control panel and release announcements
          ├─ HUD → transparent information overlay
          └─ AR → experimental road-route overlay
```

Processes exchange state through `core/ipc/shared_state.py`. Plugins produce intents and bound commands; Engine owns the physical controller. Process supervision is not a guarantee that driving can continue safely after a component failure.

Control backends: **SCS SDK** (`scs_sdk_controller.dll` / `Local\SCSControls`) → **virtual controller** → **digital keyboard fallback**. Mode-specific launch/wait features need their supported backend and evidence; fallback backends are not interchangeable guarantees.

### Tests

Install pytest separately from runtime dependencies, then run from the repository root:

```powershell
python -m pip install pytest
$env:PYTHONCASEOK = '1'
python -m pytest tests -q
```

`PYTHONCASEOK` supports legacy uppercase `UI` imports on Windows. Some tests use Qt's offscreen platform. Tests and simulations do not replace a supervised game check.

### Build the installer

```powershell
python -m pip install pyinstaller
python build_installer.py
# Output: dist/UltraPilot_Installer.exe
```

This builds the installer tool, which fetches the application during installation. `freeze_app.py` is a separate cx_Freeze application-build path, not the same installer command.

### Languages

Translation files live in [languages/](languages). Slovak and English are bundled; additional translations can be selected/downloaded through setup or Settings. Missing keys fall back to English. Coverage varies, and not every UI string or changelog entry is translated.

## Links and attribution

- [Repository](https://github.com/matule123/Ultrapilot)
- [Report an issue](https://github.com/matule123/Ultrapilot/issues) — include game version, map/mod setup, app commit, plugin versions and the first relevant log reason. Remove personal data before sharing diagnostics.
- [ETS2LA](https://github.com/ETS2LA/Euro-Truck-Simulator-2-Lane-Assist) — inspiration and upstream integrations.
- [Bundled ETS2LA plugin attribution](assets/ets2la_plugin.LICENSE.md) · [fmt license](assets/ets2la_plugin.FMT_LICENSE) · [sound sources](assets/sounds/SOURCES.md).

Intended for educational and entertainment use in a simulator. Provided as-is, without warranty. Third-party components retain their own licenses and requirements. Do not treat attribution or intended use as a blanket license grant for every repository file.
