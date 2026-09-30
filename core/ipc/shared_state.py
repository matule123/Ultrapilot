import multiprocessing as mp
import pickle
import uuid
from typing import Any, Dict, Optional


def lane_publication_batch(data):
    """Version every geometry publication, including same-revision rebases.

    The token and snapshot travel in ONE Manager.update, never two writes.
    No telemetry or command timestamp is changed by this transport cache.
    """
    if "lane_trajectory" not in data:
        return data
    return {**data, "lane_trajectory_publication_token": uuid.uuid4().hex}


class LaneSnapshotReader:
    """Avoid repeated geometry IPC; preserve independent returned copies."""
    def __init__(self):
        self.cached = None

    def read(self, state, default):
        token = state.get("lane_trajectory_publication_token")
        cached = self.cached
        if token and cached is not None and cached[0] == token:
            # Callers may edit the result before publishing a replacement.
            # Such an edit must never mutate another reader's cached authority.
            return pickle.loads(cached[1])
        snapshot = state.get("lane_trajectory", default)
        after = state.get("lane_trajectory_publication_token")
        # Serialize only the value already received from our Manager. This is
        # not an external pickle input. Loading makes an independent copy with
        # the same semantics as a Manager.get, without transferring geometry.
        self.cached = ((token, pickle.dumps(snapshot, pickle.HIGHEST_PROTOCOL))
                       if token and token == after else None)
        return snapshot


class SharedState:
    """
    Shared dictionary-style state for inter-process communication.

    Improvement over the original: a SharedState can wrap an *existing* managed
    dict.  The bootloader creates ONE ``manager.dict()`` and hands the same
    proxy to the Engine, UI, HUD and every plugin, so they all see the same
    data.  Previously each component created its own manager and they never
    actually shared anything.
    """

    def __init__(self, shared_dict: Optional[Dict[str, Any]] = None):
        self._lane_snapshot_reader = LaneSnapshotReader()
        if shared_dict is not None:
            self._manager = None
            self._state = shared_dict
        else:
            self._manager = mp.Manager()
            self._state = self._manager.dict()

    @property
    def raw(self) -> Dict[str, Any]:
        """The underlying managed dict (picklable, shareable across processes)."""
        return self._state

    def set(self, key: str, value: Any):
        if key == "lane_trajectory":
            self._state.update(lane_publication_batch({key: value}))
        else:
            self._state[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        try:
            if key == "lane_trajectory":
                return self._lane_snapshot_reader.read(self._state, default)
            return self._state.get(key, default)
        except Exception:
            return default

    def update_batch(self, data: Dict[str, Any]):
        self._state.update(lane_publication_batch(data))

    def get_all(self) -> Dict[str, Any]:
        return dict(self._state)
