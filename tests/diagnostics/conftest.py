"""Independent application models must not retain earlier test-only cycles."""
import gc
import pytest


@pytest.fixture(autouse=True)
def retire_unreachable_previous_test_models():
    # Prior flow fixtures contain Plugin <-> assembler / mock call-history
    # cycles. They can occupy all 16 weak compression registrations until
    # cyclic GC, despite no longer belonging to a live application model.
    # Collect only unreachable objects at the test boundary. Never clear a
    # registry/counter, alter a budget, or collect inside the measured tick.
    # Live overload scenarios retain their real strong references and limits.
    gc.collect()
