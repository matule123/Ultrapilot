"""Offline tests never attach an unrelated live Windows traffic producer.

Native contract tests supply their exact ABI buffer (including invalid flags,
torn reads and stale clocks), or an explicit mapping factory in the test. The
implicit process-global named mapping is not part of a synthetic fixture.
"""
import pytest
from pathlib import Path


@pytest.fixture
def spawn_test_import_root(monkeypatch):
    """Spawn unpickles test targets in a fresh interpreter, not pytest's cache.

    Explicitly put this checkout before any external `tests` package. The
    parent's already imported tests can otherwise hide a bad child search path.
    This changes test infrastructure only, not the application's spawn setup.
    """
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]))
    # Keep an explicitly selected frozen runtime ahead of this checkout in
    # spawned hosts too. The checkout must supply tests, not silently replace
    # the candidate core/config with today's working tree in child processes.
    import sys
    core=sys.modules.get('core')
    locations=list(getattr(core,'__path__',()))
    if locations:
        runtime=Path(locations[0]).resolve().parent
        if runtime!=Path(__file__).resolve().parents[1]:
            monkeypatch.syspath_prepend(str(runtime))


@pytest.fixture(autouse=True)
def isolated_native_traffic_mapping():
    def unavailable(*args, **kwargs):
        raise OSError('No implicit live traffic mapping in offline tests')
    # Own only this mapping patch. Sharing the test's monkeypatch fixture would
    # create it before a flow fixture patches time.monotonic; its later undo
    # could then restore the flow's already-retired mock clock into other tests.
    with pytest.MonkeyPatch.context() as isolated:
        isolated.setattr('core.sdk.traffic_snapshot.ExistingMapping', unavailable)
        yield
