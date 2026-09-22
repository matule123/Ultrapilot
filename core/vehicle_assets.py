"""Offline, bounded asset inspection. No runtime/control imports or writes.

ZIP is decoded by Python's standard library. HashFS is deliberately delegated
to an operator-pinned official SCS extractor; this is not a HashFS/PMC parser.
Package order is explicit, low to high priority, never inferred from a log.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import time
import zipfile

from core.swept_envelope import require

MAX_ASSET = 32 * 1024 * 1024
MAX_ENTRIES = 200000


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
            for link in re.findall(r'\bcollision\s*:\s*"([^"\n]+)"', text):
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


def extractor_command(executable, expected_sha256, archive, output):
    exe, src, dst = Path(executable).resolve(), Path(archive).resolve(), Path(output).resolve()
    require(exe.is_file() and file_sha(exe) == expected_sha256, 'UNPINNED_EXTRACTOR')
    require(archive_format(src).startswith('HashFS-'), 'NOT_HASHFS_ARCHIVE')
    require(not dst.exists() and not src.is_relative_to(dst)
            and not exe.is_relative_to(dst), 'UNSAFE_EXTRACTION_TARGET')
    return [str(exe), str(src), str(dst)]


def extract_hashfs(executable, expected_sha256, archive, output, *, timeout_s=120.):
    """Explicit offline operation, shell-free and timed; never run by Engine.

    The pinned binary must be acquired from SCS by the operator. Outputs are
    untrusted local assets, NOT certified collision evidence. No binary ships.
    """
    command = extractor_command(executable, expected_sha256, archive, output)
    require(0 < timeout_s <= 600, 'INVALID_EXTRACTION_TIMEOUT')
    source_sha = file_sha(archive, time.monotonic() + timeout_s)
    Path(output).mkdir(parents=True, exist_ok=False)
    result = subprocess.run(command, shell=False, timeout=timeout_s,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    require(result.returncode == 0, 'SCS_EXTRACTOR_FAILED')
    require(file_sha(archive, time.monotonic() + timeout_s) == source_sha,
            'ARCHIVE_CHANGED_DURING_EXTRACTION')
    return {'archive_sha256': source_sha, 'extractor_sha256': expected_sha256,
            'collision_verified': False, 'runtime_authorized': False}
