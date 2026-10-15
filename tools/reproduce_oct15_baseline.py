"""Run the unchanged new production-flow counterexamples on preserved HEAD.

Historical modules are loaded in memory; no checkout or installation is edited.
Expected nonzero pytest status is evidence of the counterexample, not success.
"""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.run_longitudinal_handoff_bench import version


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ref', default='3ee9786')
    args = p.parse_args()
    import pytest
    with version(args.ref):
        raise SystemExit(pytest.main([
            'tests/test_oct15_traffic_refresh.py', '-q',
            '-k', 'traffic_expires_after_selection or unrecoverable_late_expiry or source_timed_native']))
