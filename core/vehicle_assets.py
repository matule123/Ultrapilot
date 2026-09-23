"""Offline, bounded asset inspection. No runtime/control imports or writes.

ZIP is decoded by Python's standard library. HashFS is deliberately delegated
to an operator-pinned official SCS extractor; this is not a HashFS/PMC parser.
Package order is explicit, low to high priority, never inferred from a log.
"""
from dataclasses import dataclass
from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import time
import uuid
import zipfile

from core.swept_envelope import require

MAX_ASSET = 32 * 1024 * 1024
MAX_ENTRIES = 200000
MAX_EXTRACTED_BYTES = 128 * 1024 * 1024 * 1024


def asset_path(value):
    require(isinstance(value, str) and value and '\\' not in value
            and ':' not in value and '\x00' not in value, 'INVALID_ASSET_PATH')
    value = value.removeprefix('/')
    require(value and all(p not in ('', '.', '..') for p in value.split('/')),
            'INVALID_ASSET_PATH')
    require(all(not p.endswith((' ', '.')) for p in value.split('/')),
            'INVALID_ASSET_PATH')
    return value


def file_sha(path, deadline=None):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while chunk := f.read(1024 * 1024):
            require(deadline is None or time.monotonic() < deadline,
                    'ASSET_DEADLINE_EXCEEDED')
            h.update(chunk)
    return h.hexdigest()


def archive_format(path):
    with Path(path).open('rb') as f:
        head = f.read(8)
    if head[:4] == b'SCS#':
        return 'HashFS-v' + str(int.from_bytes(head[4:6], 'little'))
    if zipfile.is_zipfile(path):
        return 'ZIP'
    return 'unsupported'


@dataclass(frozen=True)
class Package:
    name: str
    path: Path


@dataclass(frozen=True)
class Asset:
    path: str
    package: str
    sha256: str
    data: bytes
    chain: tuple


class AssetResolver:
    """Read-only ZIP VFS with exact, case-sensitive paths and override receipts."""
    def __init__(self, packages, *, timeout_s=120.):
        self.packages = tuple(packages)
        require(0 < len(self.packages) <= 256, 'INVALID_PACKAGE_COUNT')
        require(len({p.name for p in self.packages}) == len(self.packages)
                and all(isinstance(p.name, str) and p.name for p in self.packages),
                'DUPLICATE_PACKAGE_ID')
        self.deadline = time.monotonic() + timeout_s
        self._archives, self._indexes, self.receipts, self._stamps = [], [], [], []
        self._read_bytes = 0
        try:
            for p in self.packages:
                if Path(p.path).is_dir():
                    root = Path(p.path).resolve()
                    index, rows, cases = {}, [], set()
                    for path in sorted(root.rglob('*')):
                        require(time.monotonic() < self.deadline, 'ASSET_DEADLINE_EXCEEDED')
                        require(not path.is_symlink()
                                and not getattr(path.lstat(), 'st_file_attributes', 0) & 0x400,
                                'ASSET_SYMLINK')
                        if not path.is_file():
                            continue
                        name = asset_path(path.relative_to(root).as_posix())
                        require(name.casefold() not in cases, 'AMBIGUOUS_PACKAGE_PATH')
                        require(len(index) < MAX_ENTRIES, 'PACKAGE_INDEX_TOO_LARGE')
                        cases.add(name.casefold())
                        checksum = file_sha(path, self.deadline)
                        index[name] = (path, checksum)
                        rows.append((name, checksum))
                    sha = hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest()
                    self._archives.append(None); self._indexes.append(index); self._stamps.append(None)
                    self.receipts.append({'package': p.name, 'sha256': sha, 'format': 'extracted-tree'})
                    continue
                require(archive_format(p.path) == 'ZIP', 'HASHFS_REQUIRES_OFFICIAL_EXTRACTOR')
                before = Path(p.path).stat()
                sha = file_sha(p.path, self.deadline)
                z = zipfile.ZipFile(p.path)
                self._archives.append(z)
                index, cases = {}, set()
                require(len(z.infolist()) <= MAX_ENTRIES, 'PACKAGE_INDEX_TOO_LARGE')
                for info in z.infolist():
                    if info.is_dir():
                        continue
                    name = asset_path(info.filename)
                    require(name.casefold() not in cases, 'AMBIGUOUS_PACKAGE_PATH')
                    require(not stat.S_ISLNK(info.external_attr >> 16), 'ASSET_SYMLINK')
                    cases.add(name.casefold()); index[name] = info
                self._indexes.append(index)
                after = Path(p.path).stat()
                require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
                        'PACKAGE_CHANGED_DURING_READ')
                self._stamps.append((after.st_size, after.st_mtime_ns))
                self.receipts.append({'package': p.name, 'sha256': sha, 'format': 'ZIP'})
        except BaseException:
            self.close()
            raise

    def close(self):
        for z in self._archives:
            if z is not None:
                z.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def resolve(self, name):
        name = asset_path(name)
        chain, data, winner = [], None, None
        for p, z, index, stamp in zip(self.packages, self._archives, self._indexes, self._stamps):
            require(time.monotonic() < self.deadline, 'ASSET_DEADLINE_EXCEEDED')
            info = index.get(name)
            if info is None:
                continue
            if z is None:
                path, expected = info
                require(path.resolve().is_relative_to(Path(p.path).resolve())
                        and path.stat().st_size <= MAX_ASSET, 'INVALID_EXTRACTED_ASSET')
                data = path.read_bytes()
                require(hashlib.sha256(data).hexdigest() == expected, 'ASSET_CHANGED_DURING_READ')
                self._read_bytes += len(data)
                require(self._read_bytes <= 256*MAX_ASSET, 'ASSET_READ_BUDGET_EXCEEDED')
                winner = p.name
                chain.append({'package': winner, 'sha256': expected})
                continue
            current = Path(p.path).stat()
            require((current.st_size, current.st_mtime_ns) == stamp, 'PACKAGE_CHANGED_DURING_READ')
            require(0 <= info.file_size <= MAX_ASSET and not info.flag_bits & 1,
                    'OVERSIZED_OR_ENCRYPTED_ASSET')
            self._read_bytes += info.file_size
            require(self._read_bytes <= 256 * MAX_ASSET, 'ASSET_READ_BUDGET_EXCEEDED')
            with z.open(info) as stream:
                data = stream.read(MAX_ASSET + 1)
            require(len(data) == info.file_size, 'ASSET_LENGTH_MISMATCH')
            winner = p.name
            chain.append({'package': winner, 'sha256': hashlib.sha256(data).hexdigest()})
        require(data is not None, 'MISSING_ASSET:' + name)
        return Asset(name, winner, chain[-1]['sha256'], data, tuple(chain))

    def definition_graph(self, roots):
        """Bounded textual SII/include dependency inspection, not unit evaluation.

        Binary/encrypted SII, malformed includes and cycles fail closed. All
        model references are recorded; no default variant/pivot is invented.
        """
        found, active, collisions, models = {}, set(), set(), set()

        def visit(path, depth=0):
            path = asset_path(path)
            require(depth <= 32 and len(found) < 512, 'DEFINITION_GRAPH_LIMIT')
            require(path not in active, 'CYCLIC_SII_INCLUDE')
            if path in found:
                return
            active.add(path)
            a = self.resolve(path)
            text = a.data.decode('utf-8-sig', errors='strict')
            require('\x00' not in text and not text.startswith(('ScsC', 'BSII')),
                    'BINARY_SII_UNSUPPORTED')
            # Strip comments while preserving quoted paths and string escapes.
            token = re.compile(r'"(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\n]*|\#[^\n]*', re.S)
            text = token.sub(lambda m: m[0] if m[0].startswith('"') else ' ', text)
            includes = re.findall(r'@include\s+"([^"\n]+)"', text)
            require(text.count('@') == len(includes), 'UNSUPPORTED_SII_DIRECTIVE')
            found[path] = {'path': path, 'chain': list(a.chain), 'sha256': a.sha256}
            for link in includes:
                target = link if link.startswith('/') else str(PurePosixPath(path).parent / link)
                visit(target, depth + 1)
            # Cab/chassis definitions use ``collision`` while addon
            # accessories use ``coll``.  Both are physical-model references;
            # neither is decoded or promoted merely because it was found.
            for link in re.findall(r'\b(?:collision|coll)\s*:\s*"([^"\n]+)"', text):
                collisions.add(asset_path(link))
            for link in re.findall(r'"([^"\n]+\.(?:pmd|pmg|pmc|pma|tobj))"', text):
                models.add(asset_path(link))
            active.remove(path)

        require(isinstance(roots, list) and 0 < len(roots) <= 128, 'MISSING_DEFINITION_ROOTS')
        for root in roots:
            visit(root)
        return {'definitions': [found[k] for k in sorted(found)],
                'collision_assets': sorted(collisions), 'model_assets': sorted(models),
                'unit_semantics_verified': False}


def _windows_file_version(path):
    """Read a PE fixed file version without executing the candidate binary."""
    if os.name != 'nt':
        return None
    try:
        version = ctypes.WinDLL('version', use_last_error=True)
        size = version.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return None
        blob = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(str(path), 0, size, blob):
            return None
        pointer, length = ctypes.c_void_p(), ctypes.c_uint()
        if not version.VerQueryValueW(blob, '\\', ctypes.byref(pointer),
                                      ctypes.byref(length)) or length.value < 52:
            return None
        # VS_FIXEDFILEINFO: signature, structure/file/product versions, flags,
        # OS/type/subtype and two timestamps. Only the file version is needed.
        values = ctypes.cast(pointer, ctypes.POINTER(ctypes.c_uint32 * 13)).contents
        if values[0] != 0xFEEF04BD:
            return None
        ms, ls = values[2], values[3]
        return '.'.join(str(value) for value in
                        (ms >> 16, ms & 0xffff, ls >> 16, ls & 0xffff))
    except (AttributeError, OSError, ValueError):
        return None


def extractor_identity(executable, expected_sha256, expected_version=None):
    """Pin the official-tool candidate by exact filename and content hash."""
    supplied = Path(executable)
    require(not supplied.is_symlink(), 'INVALID_SCS_EXTRACTOR')
    require(supplied.is_file(), 'MISSING_OFFICIAL_SCS_EXTRACTOR')
    exe = supplied.resolve()
    require(exe.name.casefold() == 'scs_extractor.exe' and exe.is_file()
            and not exe.is_symlink(), 'INVALID_SCS_EXTRACTOR')
    require(isinstance(expected_sha256, str)
            and re.fullmatch(r'[0-9a-f]{64}', expected_sha256),
            'INVALID_EXTRACTOR_SHA256')
    actual_sha = file_sha(exe)
    require(actual_sha == expected_sha256, 'UNPINNED_EXTRACTOR')
    actual_version = _windows_file_version(exe)
    if expected_version is not None:
        require(isinstance(expected_version, str) and expected_version,
                'INVALID_EXTRACTOR_VERSION')
        require(actual_version == expected_version, 'EXTRACTOR_VERSION_MISMATCH')
    return {'name': exe.name, 'path': str(exe), 'sha256': actual_sha,
            'file_version': actual_version, 'version_verified': expected_version is not None,
            'size_bytes': exe.stat().st_size}


def extractor_command(executable, expected_sha256, archive, output,
                      *, expected_version=None):
    exe, src, dst = Path(executable).resolve(), Path(archive).resolve(), Path(output).resolve()
    extractor_identity(executable, expected_sha256, expected_version)
    require(archive_format(src).startswith('HashFS-'), 'NOT_HASHFS_ARCHIVE')
    require(not dst.exists() and not src.is_relative_to(dst)
            and not exe.is_relative_to(dst), 'UNSAFE_EXTRACTION_TARGET')
    return [str(exe), str(src), str(dst)]


def _extracted_tree_receipt(root, deadline):
    root = Path(root).resolve()
    rows, total = [], 0
    for path in sorted(root.rglob('*')):
        require(time.monotonic() < deadline, 'ASSET_DEADLINE_EXCEEDED')
        mode = path.lstat()
        require(not path.is_symlink()
                and not getattr(mode, 'st_file_attributes', 0) & 0x400,
                'EXTRACTOR_OUTPUT_LINK')
        if not path.is_file():
            continue
        require(path.resolve().is_relative_to(root), 'EXTRACTOR_OUTPUT_TRAVERSAL')
        name = asset_path(path.relative_to(root).as_posix())
        size = path.stat().st_size
        total += size
        require(len(rows) < MAX_ENTRIES, 'EXTRACTOR_OUTPUT_TOO_MANY_FILES')
        require(total <= MAX_EXTRACTED_BYTES, 'EXTRACTOR_OUTPUT_TOO_LARGE')
        rows.append((name, size))
    require(rows, 'EMPTY_EXTRACTOR_OUTPUT')
    return {'file_count': len(rows), 'total_bytes': total,
            'metadata_sha256': hashlib.sha256(json.dumps(
                rows, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()}


def collision_asset_receipt(asset):
    """Record binary collision evidence without pretending to decode PMC.

    SCS documents PMC as binary dynamic collision data but does not publish a
    stable binary layout.  The receipt intentionally remains non-authorizing.
    """
    require(isinstance(asset, Asset), 'INVALID_COLLISION_ASSET')
    suffix = PurePosixPath(asset.path).suffix.casefold()
    require(suffix in ('.pmc', '.pic'), 'RENDER_ASSET_NOT_COLLISION')
    require(0 < len(asset.data) <= MAX_ASSET, 'INVALID_COLLISION_ASSET_SIZE')
    if suffix == '.pmc':
        require(len(asset.data) >= 16, 'TRUNCATED_PMC_ASSET')
        kind, representation = 'prism_model_collision', 'binary'
        reason = 'MISSING_VERIFIED_PMC_COLLISION_DECODER'
        first_u32 = int.from_bytes(asset.data[:4], 'little')
    else:
        require(b'\x00' not in asset.data, 'INVALID_PIC_TEXT')
        asset.data.decode('utf-8-sig', errors='strict')
        kind, representation = 'prism_intermediate_collision', 'text'
        reason, first_u32 = 'MISSING_VERIFIED_PIC_PARSER_AND_TRANSFORM', None
    return {'asset_path': asset.path, 'source_package': asset.package,
            'source_chain': list(asset.chain), 'sha256': asset.sha256,
            'size_bytes': len(asset.data), 'format': kind,
            'representation': representation,
            'header_hex': asset.data[:64].hex(),
            'unverified_first_u32_le': first_u32,
            'format_version_verified': False, 'collision_geometry_decoded': False,
            'collision_authority': False, 'confirmed': False,
            'runtime_authorized': False, 'failure_reason': reason}


@contextmanager
def _extraction_lock(directory):
    """Serialize exports in this cache; OS releases the lock if we die."""
    path = directory / '.scs-extract.lock'
    with path.open('a+b') as lock:
        if lock.seek(0, os.SEEK_END) == 0:
            lock.write(b'\0')
            lock.flush()
        lock.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                require(False, 'SCS_EXTRACTOR_ALREADY_RUNNING')
            try:
                yield
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                require(False, 'SCS_EXTRACTOR_ALREADY_RUNNING')
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)


def _windows_kill_on_close_job(process):
    """Attach the extractor to a Windows job owned only by this Python process."""
    if os.name != 'nt':
        return None
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [('per_process_time', ctypes.c_longlong),
                    ('per_job_time', ctypes.c_longlong),
                    ('flags', wintypes.DWORD),
                    ('min_working_set', ctypes.c_size_t),
                    ('max_working_set', ctypes.c_size_t),
                    ('active_process_limit', wintypes.DWORD),
                    ('affinity', ctypes.c_size_t),
                    ('priority_class', wintypes.DWORD),
                    ('scheduling_class', wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in
                    ('read_operations', 'write_operations', 'other_operations',
                     'read_bytes', 'write_bytes', 'other_bytes')]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [('basic', BasicLimits), ('io', IoCounters),
                    ('process_memory_limit', ctypes.c_size_t),
                    ('job_memory_limit', ctypes.c_size_t),
                    ('peak_process_memory', ctypes.c_size_t),
                    ('peak_job_memory', ctypes.c_size_t)]

    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    api.CreateJobObjectW.restype = wintypes.HANDLE
    api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                            ctypes.c_void_p, wintypes.DWORD]
    api.SetInformationJobObject.restype = wintypes.BOOL
    api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    api.AssignProcessToJobObject.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    job = api.CreateJobObjectW(None, None)
    require(bool(job), 'SCS_EXTRACTOR_JOB_FAILED')
    try:
        limits = ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        require(bool(api.SetInformationJobObject(job, 9, ctypes.byref(limits),
                                                 ctypes.sizeof(limits))),
                'SCS_EXTRACTOR_JOB_FAILED')
        require(bool(api.AssignProcessToJobObject(job, int(process._handle))),
                'SCS_EXTRACTOR_JOB_FAILED')
        return api, job
    except BaseException:
        api.CloseHandle(job)
        raise


def _run_extractor(command, stage, directory, deadline):
    """Bound one real extractor process and report its staged output growth."""
    process = None
    job = None
    started = time.monotonic()
    next_report = started
    try:
        process = subprocess.Popen(command, shell=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        job = _windows_kill_on_close_job(process)
        print(json.dumps({'extractor_pid': process.pid, 'state': 'running'}),
              flush=True)
        while True:
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'SCS_EXTRACTOR_TIMEOUT')
            try:
                code = process.wait(timeout=min(10., remaining))
                require(code == 0, 'SCS_EXTRACTOR_FAILED')
                return
            except subprocess.TimeoutExpired:
                pass
            require(shutil.disk_usage(directory).free >= 2 * 1024**3,
                    'SCS_EXTRACTOR_DISK_RESERVE_EXHAUSTED')
            if time.monotonic() >= next_report:
                files = size = 0
                for root, _, names in os.walk(stage):
                    for name in names:
                        try:
                            size += (Path(root) / name).stat().st_size
                            files += 1
                        except FileNotFoundError:
                            pass
                print(json.dumps({'extractor_pid': process.pid,
                    'elapsed_s': round(time.monotonic() - started, 1),
                    'staged_files': files, 'staged_bytes': size,
                    'free_bytes': shutil.disk_usage(directory).free}), flush=True)
                next_report = time.monotonic() + 30.
    except OSError:
        require(False, 'SCS_EXTRACTOR_LAUNCH_FAILED')
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait()
        if job is not None:
            job[0].CloseHandle(job[1])


def extract_hashfs(executable, expected_sha256, archive, output, *, timeout_s=120.,
                   expected_version=None):
    """Explicit offline operation, shell-free and timed; never run by Engine.

    The pinned binary must be acquired from SCS by the operator. Outputs are
    untrusted local assets, NOT certified collision evidence. No binary ships.
    """
    require(0 < timeout_s <= 7200, 'INVALID_EXTRACTION_TIMEOUT')
    dst, src = Path(output).resolve(), Path(archive).resolve()
    require(not dst.exists(), 'UNSAFE_EXTRACTION_TARGET')
    stage = dst.parent / ('.' + dst.name + '.partial-' + uuid.uuid4().hex)
    command = extractor_command(executable, expected_sha256, src, stage,
                                expected_version=expected_version)
    dst.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout_s
    started = time.monotonic()
    with _extraction_lock(dst.parent):
        require(shutil.disk_usage(dst.parent).free >=
                max(12 * 1024**3, src.stat().st_size * 4),
                'INSUFFICIENT_EXTRACTION_DISK_SPACE')
        source_sha = file_sha(src, deadline)
        identity = extractor_identity(executable, expected_sha256, expected_version)
        require(not dst.exists(), 'UNSAFE_EXTRACTION_TARGET')
        try:
            stage.mkdir(exist_ok=False)
            _run_extractor(command, stage, dst.parent, deadline)
            tree = _extracted_tree_receipt(stage, deadline)
            require(file_sha(src, deadline) == source_sha,
                    'ARCHIVE_CHANGED_DURING_EXTRACTION')
            os.replace(stage, dst)
        finally:
            require(stage.resolve().is_relative_to(dst.parent),
                    'UNSAFE_EXTRACTION_CLEANUP')
            if stage.exists():
                shutil.rmtree(stage)
    return {'archive_path': str(src), 'archive_format': archive_format(src),
            'archive_sha256': source_sha, 'extractor': identity,
            'output_path': str(dst), 'output_tree': tree,
            'elapsed_s': time.monotonic() - started,
            'collision_verified': False, 'confirmed': False,
            'runtime_authorized': False}
