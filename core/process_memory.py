"""Read-only process memory measurements (decimal MB, not exclusive RAM)."""
import os

try:
    import psutil
except ImportError:
    psutil = None


def resident_mb(pid=None):
    """RSS includes the interpreter and shared pages; unavailable is not zero."""
    if psutil is None:
        return None
    try:
        return psutil.Process(pid or os.getpid()).memory_info().rss / 1_000_000
    except (psutil.Error, OSError):
        return None


def collect_memory(state=None):
    """Return app RSS, reserved CPU slot and plugin RSS using published PIDs.

    Only a runtime-published root may include siblings. A standalone UI must
    never count its terminal, editor or unrelated children as UltraPilot RAM.
    CPU is unavailable here: cpu_percent on a fresh Process is not a sample.
    """
    if psutil is None:
        return None, None, []
    root_pid = state.get("runtime_root_pid", None) if state is not None else None
    published = state.get("plugin_processes", {}) if state is not None else {}
    pids = {os.getpid()}
    if root_pid:
        try:
            root = psutil.Process(int(root_pid))
            pids.add(root.pid)
            pids.update(p.pid for p in root.children(recursive=True))
        except (psutil.Error, OSError, ValueError, TypeError):
            pass
    plugins = []
    for name, pid in dict(published or {}).items():
        try:
            pid = int(pid)
            value = resident_mb(pid)
            if value is not None:
                pids.add(pid)
                plugins.append((str(name).replace("_", " ").title(), value, None))
        except (TypeError, ValueError):
            continue
    values = [resident_mb(pid) for pid in pids]
    available = [value for value in values if value is not None]
    return (sum(available) if available else None), None, plugins
