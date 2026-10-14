"""Native acquisition sidecar v1. Receipt time is never observation time.

Completeness here means one atomic acquisition, NOT traffic coverage, measured
lane membership, accurate acceleration or an actor-lifetime certificate.
"""
import math
import struct
import time

from core.sdk.existing_mapping import ExistingMapping

LAYOUT = struct.Struct('<IIIIQQQdI6960s1720sII160sffffdI')


def decode(data, now, sequence_after=None):
    result = dict(schema=1, valid=False, reason='unavailable_source_capture')
    try:
        seq, magic, version, size, life, gen, frame, at, flags, moving, parked, count, body_flags, ego, x, y, z, speed, speed_at, end = LAYOUT.unpack(data)
        if not seq or seq % 2 or seq != end or (sequence_after is not None and seq != sequence_after):
            raise ValueError('torn_source_capture')
        if (magic, version, size) != (0x31545055, 1, LAYOUT.size):
            raise ValueError('unsupported_source_capture')
        result.update(lifecycle=life, generation=gen, frame_us=frame, observed_at=at,
                      sequence=seq, moving=moving, parked=parked,
                      ego_body_count=count, ego_body_flags=body_flags, ego_body_payload=ego,
                      ego_anchor=(x,y,z), ego_speed_mps=speed, ego_speed_observed_at=speed_at)
        if flags != 3 or not life or not gen or not frame:
            raise ValueError('inactive_or_incomplete_source_capture')
        if not math.isfinite(at) or not 0 <= now-at <= .5:
            raise ValueError('stale_source_capture')
        result.update(valid=True, reason='')
    except (ValueError, struct.error) as error:
        result['reason'] = str(error)
    return result


class TrafficReader:
    def __init__(self):
        self.buffer = None
        self.retry_at = 0.
        self.seen = False
        self.last = None
        self.last_data = None

    def read(self, now=None):
        now = time.monotonic() if now is None else now
        if self.buffer is None and now >= self.retry_at:
            self.retry_at = now+1.
            try:
                self.buffer = ExistingMapping(r'Local\UltraPilotTrafficV1', LAYOUT.size)
            except (OSError, ValueError):
                pass
        if self.buffer is None:
            return None  # Old DLL retains its explicitly unqualified contract.
        self.seen = True
        try:
            data = bytes(self.buffer[:LAYOUT.size])
            after = struct.unpack('<I', bytes(self.buffer[:4]))[0]
            result = decode(data, now, after)
        except (OSError, ValueError, TypeError, struct.error):
            result = dict(schema=1, valid=False, reason='torn_source_capture')
        stamp = (result.get('lifecycle'), result.get('generation'), result.get('frame_us'), result.get('observed_at'))
        if result['valid'] and self.last and stamp[0] == self.last[0]:
            if (stamp[1] < self.last[1] or stamp[2] < self.last[2] or stamp[3] < self.last[3]
                    or (stamp[1] == self.last[1] and (stamp != self.last or data != self.last_data))
                    or (stamp[1] > self.last[1] and (stamp[2] <= self.last[2] or stamp[3] <= self.last[3]))):
                result.update(valid=False, reason='regressing_source_capture')
        if result['valid']:
            self.last = stamp
            self.last_data = data
        return result
