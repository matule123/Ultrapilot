import pickle
import uuid
import threading
from multiprocessing.managers import SyncManager, DictProxy
from typing import Any, Dict, Optional


class ControlDictionary(dict):
    """Manager-owned atomic publication, bounded by the existing producer slots.

    Identity writes and packet commit share this short server-local lock. No
    calculation, disk I/O, proxy call or wait for a producer runs under it.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._publication_lock = threading.RLock()
        self._diagnostic_export_lock = threading.Lock()
        self._diagnostic_export_ticket = None

    def reserve_diagnostic_export(self):
        """One payload in flight; no unbounded Manager request/payload queue."""
        ticket=self._diagnostic_export_ticket
        if ticket and len(ticket)==2 and __import__('time').monotonic()-ticket[1]>5.:
            # A client killed before submitting its payload must not reserve
            # the sole slot forever. Running jobs have the third marker and
            # retain the existing export-child deadline/RSS cleanup instead.
            self.release_diagnostic_export(ticket[0])
        if not self._diagnostic_export_lock.acquire(blocking=False):return None
        token=uuid.uuid4().hex
        self._diagnostic_export_ticket=(token,__import__('time').monotonic())
        return token

    def release_diagnostic_export(self,token):
        if self._diagnostic_export_ticket and self._diagnostic_export_ticket[0]==token:
            self._diagnostic_export_ticket=None;self._diagnostic_export_lock.release()

    def diagnostic_export(self,token,kind,args):
        # This service runs in the application's existing non-daemon Manager,
        # never in its publication lock or a controller thread. Only fixed
        # production export entry points may be requested; no callable RPC.
        from core import steering_replay as replay
        targets={'_autopilot_part_child':replay._autopilot_part_child,
            '_incident_export_child':replay._incident_export_child,
            '_replay_export_child':replay._replay_export_child}
        ticket=self._diagnostic_export_ticket
        if not ticket or ticket[0]!=token:raise ValueError('DIAGNOSTIC_EXPORT_TICKET')
        self._diagnostic_export_ticket=(*ticket,True)
        try:
            if kind not in targets:raise ValueError('DIAGNOSTIC_EXPORT_KIND')
            return replay._run_diagnostic_export(targets[kind],args)
        finally:self.release_diagnostic_export(token)

    def __setitem__(self, key, value):
        with self._publication_lock:
            super().__setitem__(key, value)

    def __delitem__(self, key):
        with self._publication_lock:
            super().__delitem__(key)

    def update(self, *args, **kwargs):
        with self._publication_lock:
            super().update(*args, **kwargs)

    def publish_longitudinal(self, key, value):
        from core.longitudinal import publication_rejection
        with self._publication_lock:
            if publication_rejection(self, key, value):
                return False
            super().__setitem__(key, value)
            return True


class ControlDictionaryProxy(DictProxy):
    _exposed_ = (*DictProxy._exposed_, 'publish_longitudinal',
        'reserve_diagnostic_export','release_diagnostic_export','diagnostic_export')

    def reserve_diagnostic_export(self):return self._callmethod('reserve_diagnostic_export')
    def release_diagnostic_export(self,token):return self._callmethod('release_diagnostic_export',(token,))
    def diagnostic_export(self,token,kind,args):return self._callmethod('diagnostic_export',(token,kind,args))

    def publish_longitudinal(self, key, value):
        return self._callmethod('publish_longitudinal', (key, value))


class ControlStateManager(SyncManager):
    pass


ControlStateManager.register('control_dict', ControlDictionary, ControlDictionaryProxy)


def lane_publication_batch(data):
    """Version every geometry publication, including same-revision rebases.

    The token and snapshot travel in ONE Manager.update, never two writes.
    No telemetry or command timestamp is changed by this transport cache.
    """
    if "lane_trajectory" not in data:
        return data
    snapshot = data["lane_trajectory"] or {}
    identity = {key: snapshot.get(key) for key in (
        "navigation_intent_id", "revision", "route_build_id",
        "source_game_session_id", "source_map_key", "source_dataset_fingerprint")}
    publication = uuid.uuid4().hex
    fingerprint = snapshot.get("lane_path_fingerprint")
    # Map computes this digest from the complete validated LanePath, including
    # XYZ, curvature, directed LaneIds and elevation. A proven UID-window
    # rebase retains that immutable geometry. Cache invalidation is deliberately
    # more frequent than control-authority invalidation.
    proven_digest = (isinstance(fingerprint, str) and len(fingerprint) == 64
                     and all(c in '0123456789abcdef' for c in fingerprint))
    geometry = (("lane_path", fingerprint, snapshot.get("valid") is True)
                if proven_digest else ("publication", publication))
    return {**data, "lane_trajectory_publication_token": publication,
            "lane_trajectory_identity": identity,
            # Keep build and geometry in ONE compact immutable RPC value.
            # Unknown/legacy geometry continues to invalidate on publication.
            "lane_trajectory_longitudinal_identity": {
                **identity, "geometry_token": geometry}}


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
            self._manager = ControlStateManager()
            self._manager.start()
            self._state = self._manager.control_dict()

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

    def publish_longitudinal(self, key, value):
        commit = getattr(self._state, 'publish_longitudinal', None)
        if callable(commit):
            return commit(key, value)
        # Compatibility for explicitly supplied in-process dictionaries.
        from core.longitudinal import publication_rejection
        if publication_rejection(self, key, value):
            return False
        self._state[key] = value
        return True
