"""Producer-timed signal sidecar. Route relevance remains a heuristic.

QPC seconds share Python's Windows monotonic clock domain. Reading memory does
not create an observation. Legacy buffers may brake, never authorize release.
"""
import math
import struct
import time

from core.sdk.existing_mapping import ExistingMapping
from core.sdk.ets2la_data import ETS2LAData
from core.acc_following import RouteLeadSelector

LAYOUT = struct.Struct('<IIIIQQQdII1920sI')
SIZE = LAYOUT.size


def compact(signal):
    result = {k: signal[k] for k in ('valid','reason','lifecycle','generation',
              'frame_us','observed_at','relevance') if k in signal}
    candidate = signal.get('candidate')
    if candidate:
        result['candidate'] = {k: candidate[k] for k in (
            'id','x','y','z','color','distance','distance_basis','stop_line_verified') if k in candidate}
    return result


def decode(data, now, sequence_after=None):
    result = dict(valid=False, reason='signal snapshot unavailable', schema=2)
    try:
        seq, magic, version, size, lifecycle, generation, frame, observed, flags, count, payload, end = LAYOUT.unpack(data)
        if seq == 0 or seq % 2 or seq != end or (sequence_after is not None and seq != sequence_after):
            raise ValueError('torn signal snapshot')
        if (magic, version, size) != (0x32535055, 2, SIZE):
            raise ValueError('unsupported signal schema')
        result.update(lifecycle=lifecycle, generation=generation, frame_us=frame,
                      observed_at=observed, sequence=seq)
        if flags != 3 or not lifecycle or not generation or not frame or not 0 <= count <= 40:
            raise ValueError('inactive or incomplete signal producer')
        if not math.isfinite(observed) or not 0 <= now-observed <= .5:
            raise ValueError('signal producer observation stale or incoherent')
        reader = ETS2LAData()
        reader._ensure = lambda: None
        reader._sem_buf = payload
        lights = reader.read_traffic_lights()
        if len(lights) > count or len({x['id'] for x in lights}) != len(lights):
            raise ValueError('ambiguous signal IDs or count')
        for light in lights:
            if not all(math.isfinite(light[k]) for k in ('x', 'y', 'z', 'yaw')):
                raise ValueError('invalid signal pose')
        for i in range(count):
            row = struct.unpack_from('<fffhhffffifii', payload, i*48)
            if row[9] == 1 and not .9 <= sum(v*v for v in row[5:9]) <= 1.1:
                raise ValueError('invalid signal quaternion')
        result.update(valid=True, reason='', lights=lights)
    except (ValueError, struct.error) as error:
        result['reason'] = str(error)
    return result


class SignalReader:
    def __init__(self):
        self.buffer = None
        self.retry_at = 0.
        self.last = None
        self.last_bytes = None

    def read(self):
        now = time.monotonic()
        if self.buffer is None and now >= self.retry_at:
            self.retry_at = now+1.
            try:
                self.buffer = ExistingMapping(r'Local\UltraPilotSemaphoreV2', SIZE)
            except OSError:
                pass
        if self.buffer is None:
            return dict(valid=False, schema=2, reason='producer-timed signal plugin unavailable')
        try:
            data = self.buffer[:SIZE]
            after = struct.unpack('<I', self.buffer[:4])[0]
            result = decode(data, time.monotonic(), after)
            if result.get('valid'):
                current = tuple(result[k] for k in ('lifecycle','generation','frame_us','observed_at'))
                if self.last and current[0] == self.last[0]:
                    if (any(a < b for a,b in zip(current[1:],self.last[1:]))
                            or (current[1] == self.last[1] and data != self.last_bytes)):
                        return dict(result, valid=False, reason='signal producer frame/generation regressed or changed in place')
                self.last, self.last_bytes = current, data
            return result
        except (OSError, struct.error):
            self.buffer = None
            return dict(valid=False, schema=2, reason='signal mapping read failed')


class RouteSignalSelector:
    """Bounded XYZ projection; 6 m relevance gate is NOT a physical road edge.

    Same-approach heads within 3 m progress are ambiguous. Orientation is used
    only when supplied; sidecar always supplies the source quaternion/yaw.
    """
    def __init__(self):
        self.route = RouteLeadSelector()
        self.lock = None

    def select(self, snapshot, points, publication, authority, truck, progress):
        result = {k: v for k, v in snapshot.items() if k != 'lights'}
        result.update(authority=authority, relevance='route_geometry_heuristic', candidate=None)
        if not snapshot.get('valid'):
            return result
        try:
            self.route.prepare(points, publication)
            progress = float(progress)
            if not math.isfinite(progress) or not 0 <= progress <= self.route.arcs[-1]:
                raise ValueError('invalid route progress')
            ego = self.route._project(dict(truck, yaw=truck['rotation']), max(0., progress-20.), progress+20.)
            if ego is None or ego[0] > 1.2:
                raise ValueError('signal route localization unavailable')
            candidates = []
            locked_id = self.lock['candidate']['id'] if self.lock else None
            for light in snapshot['lights']:
                # A traffic head faces against the directed approach tangent.
                actor = dict(light, yaw=float(light.get('yaw', truck['rotation']+math.pi))+math.pi)
                # Acquisition remains strictly ahead. Once braking locked this
                # same head, retain its actual fresh observation across passage
                # of the SDK reference. Do not acquire a different behind head,
                # jump to another route lap, or fabricate stop-line geometry.
                retained = light['id'] == locked_id
                low = max(0., ego[1] - (20. if retained else .5))
                p = self.route._project(actor, low, ego[1]+120.)
                if p is not None and p[0] <= 6. and (retained or p[1] > ego[1]):
                    candidates.append(dict(light, distance=p[1]-ego[1], lateral_distance=p[0],
                        route_progress_m=p[1], distance_basis='sdk_reference_to_signal_head',
                        stop_line_verified=False))
            candidates.sort(key=lambda x: (x['distance'], x['id']))
            if self.lock:
                if self.lock['authority'] != authority or self.lock['lifecycle'] != snapshot['lifecycle']:
                    raise ValueError('locked signal authority or producer lifecycle changed')
                chosen = next((x for x in candidates if x['id'] == self.lock['candidate']['id']), None)
                if chosen is None:
                    raise ValueError('locked signal missing or no longer route relevant')
                original = self.lock['candidate']
                if math.dist([chosen[k] for k in ('x','y','z')], [original[k] for k in ('x','y','z')]) > 1.:
                    raise ValueError('locked signal placement changed')
            else:
                chosen = candidates[0] if candidates else None
            if chosen is None:
                raise ValueError('no relevant signal; coverage unproven')
            if any(x['id'] != chosen['id'] and abs(x['distance']-chosen['distance']) <= 3. for x in candidates):
                raise ValueError('ambiguous route signal candidates')
            result['candidate'] = chosen
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            result.update(valid=False, reason=str(error))
        return result
