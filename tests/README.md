# Regression test layout

Run the complete suite from the repository root:

```powershell
$env:PYTHONCASEOK='1'
python -m pytest tests -q
```

The formerly date-prefixed incident regressions are grouped by behavior:

| Directory | Coverage |
| --- | --- |
| `signals/` | Signal relevance, timing, approach/stop geometry, hold and green restart |
| `traffic/` | ACC, crossing actors, roundabouts and brake ownership |
| `lifecycle/` | Activation, reactivation, refresh, destination and integrated handoffs |
| `diagnostics/` | Exact records, pedal history, budgets, incident assembly and daemon export |
| `sdk/` | Native probes and SDK 1.61 runtime contracts |
| `fixtures/` | Shared immutable historical inputs; retained in their original location |

Other established subsystem tests remain at the top level. Tests are named by
behavior, not by the day a bug was reported. Historical dates inside fixture
names, recorded incidents and regression descriptions remain useful provenance.

Example selections:

```powershell
python -m pytest tests/diagnostics -q
python -m pytest tests/traffic/test_moving_transition.py -q
python -m pytest tests/signals tests/lifecycle -q
```

`layout-migration.json` maps all 70 old paths to their replacements for old
reports and commands. Imports and active Python tool selections were migrated.
Previously frozen evidence/ZIPs/reports under `docs/` are deliberately not
rewritten. Translate a historical test path through the map when rerunning it
against current sources.

No regression scenario was removed or skipped during this reorganization:
all 3,304 collected node IDs match exactly after translating file paths.

Do not continue a pytest process that collected the old filenames while this
layout migration was taking place. Windows spawn imports target functions by
their collected module name, so that stale parent process will request an old
module that no longer exists. Finish/close that test run and use a fresh pytest
invocation with the paths above; no application or game restart is required.

Validation after migration: **3290 passed, 14 skipped, 1725 subtests passed**
in 1386.33 seconds. The two daemon/late-assembly spawn cases were additionally
rerun alone on the new paths: **2 passed in 6.12 seconds**. No further full-suite
run is needed merely for this path correction.
