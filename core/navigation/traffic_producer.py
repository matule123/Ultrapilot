"""5E observed traffic and authenticated complete-feed adapter.

Legacy ABI has three trailer slots and acceleration, but no source timestamp,
generation, sensor range, coverage or dimension accuracy. Preserve these facts
without converting observation history into a coverage certificate.
"""
from collections import deque
from dataclasses import dataclass
import math
import struct

from core.navigation.drivable_surface import digest, identity_fingerprint
from core.navigation.maneuver_traffic import TrafficActor, TrafficObservation, TrafficSnapshot
from core.sdk.ets2la_data import _TRAFFIC_FMT, _TRAFFIC_SIZE, _PARKED_FMT, _PARKED_SIZE
from core.swept_envelope import finite, require

MISSING_TRAFFIC = 'MISSING_COMPLETE_TRAFFIC_HISTORY_COVERAGE_AND_BODY_PRODUCER'


@dataclass(frozen=True)
class TrafficCapture:
    session: str
    observed_at: float  # receiver time, NOT an invented sensor frame timestamp
    moving: bytes | None
    parked: bytes | None
    stable: bool


def capture_traffic(reader, session, now):
    def read(buf, size):
        if buf is None:
            return None, False
        try:
            first, second = bytes(buf[:size]), bytes(buf[:size])
            return (second, first == second and len(second) == size)
        except (OSError, ValueError, TypeError):
            return None, False
    moving, stable_a = read(getattr(reader, '_traffic_buf', None), _TRAFFIC_SIZE)
    parked, stable_b = read(getattr(reader, '_parked_buf', None), _PARKED_SIZE)
    return TrafficCapture(str(session), now, moving, parked, stable_a and stable_b)


@dataclass(frozen=True)
class ObservedTrafficBody:
    position_xyz: tuple
    quaternion: tuple
    dimensions_whl_m: tuple  # zeros stay zeros, never fallback sizes


@dataclass(frozen=True)
class ObservedTrafficActor:
    actor_id: str
    bodies: tuple[ObservedTrafficBody, ...]
    speed_mps: float
    acceleration_mps2: float
    temporary: bool
    trailer_flag: bool
    dimensions_present: bool


@dataclass(frozen=True)
class ObservedTrafficSnapshot:
    session: str
    sequence: int
    receiver_time_s: float
    status: str
    actors: tuple[ObservedTrafficActor, ...]
    complete: bool = False
    sensor_time_s: float | None = None
    sensor_range_m: float | None = None
    failure_reason: str = MISSING_TRAFFIC


class LegacyTrafficProducer:
    def __init__(self):
        self.sequence = 0
        self.session = None
        self.last_time = None
        self.history = deque(maxlen=128)

    def produce(self, capture, now):
        self.sequence += 1
        if self.session != capture.session:
            self.history.clear()
            self.last_time = None
            self.session = capture.session
        status, actors = 'unavailable', []
        if (not finite(now, capture.observed_at)
                or not 0 <= now-capture.observed_at < .1
                or (self.last_time is not None and capture.observed_at < self.last_time)):
            status = 'stale_snapshot'
        elif capture.moving is None:
            status = 'unavailable_buffer'
        elif not capture.stable:
            status = 'incomplete_or_changing_buffers'
        else:
            moving = struct.unpack(_TRAFFIC_FMT, capture.moving)
            parked = struct.unpack(_PARKED_FMT, capture.parked)
            seen = set()
            for source, data, stride in (('moving', moving, 46), ('parked', parked, 12)):
                for i in range(40):
                    row = data[i*stride:(i+1)*stride]
                    if row[0] == 0 and row[2] == 0:
                        continue  # ABI sentinel, not proof of no objects
                    count = int(row[12]) if source == 'moving' else 0
                    require(0 <= count <= 3, 'TRAFFIC_ARTICLE_COUNT_UNSUPPORTED')
                    vid = int(row[13] if source == 'moving' else row[10])
                    aid = f'{capture.session}:{vid}'
                    require(aid not in seen, 'AMBIGUOUS_TRAFFIC_ACTOR_ID')
                    seen.add(aid)
                    bodies = [ObservedTrafficBody(tuple(row[:3]), tuple(row[3:7]), tuple(row[7:10]))]
                    for j in range(count):
                        start = 16+j*10
                        bodies.append(ObservedTrafficBody(tuple(row[start:start+3]),
                            tuple(row[start+3:start+7]), tuple(row[start+7:start+10])))
                    require(all(finite(*b.position_xyz, *b.quaternion, *b.dimensions_whl_m)
                                for b in bodies), 'NONFINITE_TRAFFIC_BODY')
                    speed, acceleration = (row[10], row[11]) if source == 'moving' else (0., 0.)
                    require(finite(speed, acceleration), 'NONFINITE_TRAFFIC_KINEMATICS')
                    actors.append(ObservedTrafficActor(aid, tuple(bodies), speed, acceleration,
                        bool(row[14]) if source == 'moving' else False,
                        bool(row[15] if source == 'moving' else row[11]),
                        all(all(v > 0 for v in b.dimensions_whl_m) for b in bodies)))
            status = ('readable_empty_unproven_coverage' if not actors else
                      'unknown_actor_dimensions' if any(not a.dimensions_present for a in actors)
                      else 'observed_incomplete_coverage')
        self.last_time = capture.observed_at
        snapshot = ObservedTrafficSnapshot(capture.session, self.sequence,
                                          capture.observed_at, status, tuple(actors))
        self.history.append(snapshot)
        return snapshot


class CompleteTrafficProducer:
    """Import an independently authenticated, source-timed complete sensor feed.

    This adapter does not turn LegacyTrafficProducer into that missing sensor.
    Different elevation actors remain conservatively included in X/Z checks.
    """
    def __init__(self):
        self._last = None

    def produce(self, artifact, identity, now):
        require(artifact.kind == 'traffic_frame', 'WRONG_TRAFFIC_ARTIFACT_KIND')
        p = artifact.payload()
        require(p.get('identity_sha256') == identity_fingerprint(identity)
                and p.get('clock_domain') == 'host_monotonic'
                and p.get('sensor_contract') == 'complete_body_history_coverage_v1'
                and p.get('all_entries_observed') is True
                and p.get('history_includes_departed_actors') is True,
                MISSING_TRAFFIC)
        require(p.get('elevation_layer') == identity.layer,
                'TRAFFIC_SENSOR_ELEVATION_MISMATCH')
        require(type(p.get('actors')) is list and len(p['actors']) <= 256,
                'INVALID_TRAFFIC_ACTOR_SET')
        actors = []
        for a in p['actors']:
            require(type(a.get('history')) is list and 2 <= len(a['history']) <= 128,
                    'INVALID_TRAFFIC_HISTORY_SIZE')
            require(a.get('elevation_layer') is not None,
                    'UNKNOWN_TRAFFIC_ACTOR_ELEVATION')
            # No actor is discarded merely because it is on another deck or
            # outside the current corridor. 5D reachable tubes decide relevance.
            observations = tuple(TrafficObservation(
                r['observation_id'], r['time_s'], r['x_m'], r['z_m'], r['heading_rad'],
                r['speed_mps'], r['velocity_x_mps'], r['velocity_z_mps'],
                tuple(tuple(tuple(v) for v in poly) for poly in r['polygons_xz']))
                for r in a['history'])
            actors.append(TrafficActor(a['actor_id'], observations,
                tuple(tuple(tuple(v) for v in poly) for poly in a['polygons_xz']),
                p['source'], artifact.sha256, a['dimensions_confirmed'], a['confidence'],
                a['position_error_m'], a['corner_velocity_error_mps'],
                a['corner_acceleration_bound_mps2'], a['valid_until_s']))
        snapshot = TrafficSnapshot(identity, p['snapshot_id'], p['sequence'],
            p['observed_at_s'], p['valid_until_s'], tuple(actors),
            tuple(tuple(v) for v in p['coverage_xz']), p['complete'],
            p['unseen_speed_bound_mps'], p['source'], artifact.sha256, p['coverage_since_s'])
        snapshot.validate(identity, now)
        stamp = (identity, snapshot.sequence, snapshot.observed_at_s, artifact.sha256)
        if self._last is not None and self._last[0] == identity:
            require(stamp[1] >= self._last[1] and stamp[2] >= self._last[2],
                    'REGRESSING_TRAFFIC_SEQUENCE')
            require(stamp[1] != self._last[1] or stamp == self._last,
                    'REUSED_TRAFFIC_SEQUENCE_WITH_CHANGED_SNAPSHOT')
        self._last = stamp
        return snapshot
