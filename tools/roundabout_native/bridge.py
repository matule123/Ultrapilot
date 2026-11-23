"""Opt-in binding for the frozen perf21 crossing admission experiment."""

from contextlib import contextmanager
import ctypes
from functools import wraps
import inspect
import math
from pathlib import Path
from textwrap import dedent
import time

import numpy as np


STEP = 0.25
PARALLEL_FACTOR = math.sin(math.radians(20.0))
UNWRITTEN = np.iinfo(np.uint32).max


class CrossingBatch:
    def __init__(self, library, *, check_pairs=False, profile=False):
        self.library = ctypes.CDLL(str(Path(library).resolve(strict=True)))
        self.call = self.library.crossing_pairs_v2
        floats = np.ctypeslib.ndpointer(dtype=np.float64, flags=('C_CONTIGUOUS', 'ALIGNED'))
        integers = np.ctypeslib.ndpointer(dtype=np.uint32, flags=('C_CONTIGUOUS', 'ALIGNED'))
        masks = np.ctypeslib.ndpointer(dtype=np.uint64, flags=('C_CONTIGUOUS', 'ALIGNED'))
        count = ctypes.c_uint32
        self.call.argtypes = (floats, count, integers, floats, count, floats, floats,
                              count, integers, masks, count, ctypes.POINTER(count))
        self.call.restype = ctypes.c_int32
        self.check_pairs = check_pairs
        self.profile = profile
        self.calls = 0
        self.checked_actors = 0
        self.peak_buffer_bytes = 0
        self.spans = []

    def admit(self, jobs, bounds, edges, first):
        """Return one ordered map per input actor, including explicit empty maps."""
        if not jobs:
            return []
        if len(jobs) > 80 or len(bounds) > 512:
            raise RuntimeError('Crossing batch exceeds its actor or edge capacity')
        if bounds.shape != (len(bounds), 4) or edges.shape != (len(bounds), 10):
            raise RuntimeError('Malformed route edge arrays')

        start = time.perf_counter() if self.profile else 0.0
        arrays, samples, limits, endpoints = [], [], [], []
        pose_count = 0
        for actor, bodies, motion, prepared in jobs:
            body_count, branch_count, sample_count, coordinates = prepared.shape
            if (body_count != len(bodies) or branch_count != len(motion['branches']) or
                not 1 <= body_count <= 4 or not 1 <= branch_count <= 8 or
                not 2 <= sample_count <= 33 or coordinates != 4 or
                any(len(branch['poses']) != sample_count for branch in motion['branches']) or
                prepared.dtype != np.float64 or not prepared.flags.c_contiguous):
                raise RuntimeError('Malformed crossing pose batch')
            tracks = body_count * branch_count
            limit = -1.0
            if all(body.get('speed', actor['speed']) == actor['speed'] for body in bodies):
                limit = PARALLEL_FACTOR * max(actor['speed'], 1e-6)
            arrays.append(prepared.reshape(-1, 4))
            samples.extend([sample_count] * tracks)
            limits.extend([limit] * tracks)
            pose_count += tracks * sample_count
            endpoints.append(pose_count)

        poses = arrays[0] if len(arrays) == 1 else np.concatenate(arrays)
        counts = np.asarray(samples, dtype=np.uint32)
        parallel = np.asarray(limits, dtype=np.float64)
        capacity = pose_count - len(counts)
        words = (len(bounds) + 63) // 64
        row_ids = np.full(capacity, UNWRITTEN, dtype=np.uint32)
        masks = np.zeros((capacity, words), dtype=np.uint64)
        completed_poses = ctypes.c_uint32(0)
        buffer_bytes = sum(array.nbytes for array in (poses, counts, parallel, row_ids, masks))
        self.peak_buffer_bytes = max(self.peak_buffer_bytes, buffer_bytes)
        packed = time.perf_counter() if self.profile else 0.0
        written = self.call(poses, pose_count, counts, parallel, len(counts),
                            bounds, edges, len(bounds), row_ids, masks, capacity,
                            ctypes.byref(completed_poses))
        returned = time.perf_counter() if self.profile else 0.0
        self.calls += 1
        if not isinstance(written, int) or not 0 <= written <= capacity or (written and not words):
            raise RuntimeError(f'Crossing batch failed or returned an invalid row count ({written})')
        if completed_poses.value != pose_count:
            raise RuntimeError('Crossing batch returned before acknowledging all input poses')
        if written < capacity and row_ids[written] != UNWRITTEN:
            raise RuntimeError('Crossing batch returned fewer rows than it wrote')

        results = [{} for _ in jobs]
        previous_row, job = -1, 0
        for output_row, row in enumerate(row_ids[:written].tolist()):
            if not previous_row < row < pose_count:
                raise RuntimeError('Crossing batch returned a missing, duplicate or unordered row')
            previous_row = row
            while row >= endpoints[job]:
                job += 1
            _, branches, per_track, _ = jobs[job][3].shape
            actor_offset = endpoints[job - 1] if job else 0
            track, sample = divmod(row - actor_offset, per_track)
            body, branch = divmod(track, branches)
            if sample + 1 == per_track:
                raise RuntimeError('Crossing batch returned the last pose as a segment')
            indices = []
            for word, bits in enumerate(masks[output_row].tolist()):
                while bits:
                    bit = bits & -bits
                    edge = word * 64 + bit.bit_length() - 1
                    if edge >= len(bounds):
                        raise RuntimeError('Crossing batch returned an invalid edge index')
                    indices.append(first + edge)
                    bits ^= bit
            if not indices:
                raise RuntimeError('Crossing batch returned an empty segment')
            x, y, z, _ = poses[row].tolist()
            next_x, _, next_z, _ = poses[row + 1].tolist()
            piece = (sample * STEP, x, y, z, (next_x - x) / STEP, (next_z - z) / STEP,
                     STEP, branch)
            results[job].setdefault(body, []).append((piece, indices))

        if self.profile:
            handled = time.perf_counter()
            self.spans.append((packed - start, returned - packed, handled - returned, buffer_bytes))
        if self.check_pairs:
            from core.actor_motion import crossing_pairs

            for (actor, bodies, motion, prepared), actual in zip(jobs, results, strict=True):
                expected = crossing_pairs(actor, bodies, motion, bounds, first,
                                          prepared=prepared, edge_values=edges)
                if actual != expected:
                    raise RuntimeError(f'Crossing pair mismatch for actor {actor["id"]!r}')
                self.checked_actors += 1
        return results


# Replace the admission call site only in the offline process. Keeping the
# exact source anchor and its surrounding perf21 code avoids a second copy of
# crossing policy and leaves the default Python selector and frozen files alone.
ADMISSION_SITE = '''            for original in actors:
                motion = self.actor_motion(original) if not timed or speed > .1 else None
                mapped=None
                if motion:
                    from core.actor_motion import crossing_pairs
                    mapped=crossing_pairs(original,original.get('bodies') or [original],motion,
                        self._crossing_bounds[first:last],first,
                        prepared=self.actor_body_motion(original,motion),
                        edge_values=self._crossing_values[first:last])
'''
NATIVE_SITE = '''            predictions = (_offline_admit(self, actors, first, last)
                           if not timed or speed > .1 else {})
            for original in actors:
                motion, mapped = predictions.get(original['id'], (None, None))
'''


@contextmanager
def use_native(batch):
    from core.acc_following import RouteLeadSelector

    def admit_tick(selector, actors, first, last):
        jobs = []
        for actor in actors:
            motion = selector.actor_motion(actor)
            if motion:
                bodies = actor.get('bodies') or [actor]
                jobs.append((actor, bodies, motion, selector.actor_body_motion(actor, motion)))
        mapped = batch.admit(jobs, selector._crossing_bounds[first:last],
                             selector._crossing_values[first:last], first)
        return {actor['id']: (motion, pairs)
                for (actor, _, motion, _), pairs in zip(jobs, mapped, strict=True)}

    original = RouteLeadSelector.crossing
    source = inspect.getsource(original)
    if source.count(ADMISSION_SITE) != 1:
        raise RuntimeError('Offline adapter requires the original perf21 crossing method')
    namespace = dict(original.__globals__, _offline_admit=admit_tick)
    updated = dedent(source.replace(ADMISSION_SITE, NATIVE_SITE))
    exec(compile(updated, '<offline perf21 crossing admission>', 'exec'), namespace)
    RouteLeadSelector.crossing = wraps(original)(namespace['crossing'])
    try:
        yield
    finally:
        RouteLeadSelector.crossing = original
