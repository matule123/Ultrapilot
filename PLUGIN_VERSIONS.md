# Plugin versioning

## Version format

Each built-in plugin declares its own `VERSION` class constant in
`plugins/<plugin>/main.py`, using `MAJOR.MINOR.PATCH`.

| Component | Increase when |
| --- | --- |
| PATCH | Fixing a bug without an incompatible interface change. |
| MINOR | Adding a backward-compatible feature. |
| MAJOR | Introducing an incompatible interface or configuration change. |

Versions do not increase automatically on startup or according to commit count.
Only increase the version of a plugin whose release changes.

## Release workflow

1. Update the affected plugin's `VERSION`.
2. Add a dated entry to [PLUGIN_CHANGELOG.md](PLUGIN_CHANGELOG.md).
3. Describe the change in the commit.

Tests and documentation that do not change plugin behavior do not necessarily
require a plugin version increase.

## Baseline and current versions

All 12 built-in plugins started independent versioning at 1.0.0: acc,
autopilot, collision, discord, drivepolicy, ecodrive, hud, lanecontrol,
map, toll, tts and turnsignals. This is not a certification of completeness
or a reconstruction of older releases.

Map subsequently advanced to 1.0.1 for the post-localization freshness fix.
Phase 7.1 advances Map to 1.0.2 and acc, autopilot, collision, drivepolicy and
ecodrive to 1.0.1 for their longitudinal-contract fixes. Core changes do not
advance unaffected plugin versions. These coordinated runtime files belong
to one application build; independent mixed-version plugin deployment is
not supported.
Phase 7.2 advances only ACC and Autopilot from 1.0.1 to 1.0.2 for speed/PID
and pedal-recovery fixes. EcoDrive's preference producer and the other plugins
are unchanged; consuming its preference differently does not release EcoDrive.
The plugin's `VERSION` declaration is always the source of truth for its
current version; the baseline list is historical.
Phase 7.3 advances ACC to 1.1.0 for route-candidate constraints and source-loss
handling, and DrivePolicy to 1.0.2 to avoid duplicate following constraints.
Engine/core guards do not release unchanged Autopilot, Map or Collision plugins.

## Display and runtime metadata

- The Plugins page displays the installed version on each card, including disabled plugins, by reading source metadata without executing plugin code.
- Unknown or invalid declarations are displayed as unknown, not guessed.
- The plugin manager validates version syntax when loading a plugin, logs its version and publishes `plugin_versions` for loaded plugins.
- Disabled plugins are not loaded.
- External plugins without their own declaration inherit 0.0.0, meaning unversioned.

## Planned capabilities

Independent plugin updates and dependency compatibility checks are not implemented.
Updates continue to use UltraPilot's existing application-update mechanism.
