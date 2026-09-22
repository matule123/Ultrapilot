"""Offline Phase 5F audit, extractor bridge and deterministic candidate build.

All writes must stay in ignored docs/steering-audit. No automatic download,
installation, game launch or runtime settings modification.
"""
import argparse
from collections import Counter
from dataclasses import fields
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.asset_profile_compiler import compile_candidate, ProfileCache
from core.navigation.production_evidence import canonical
from core.sdk.vehicle_observation import VehicleObservation, ArticleObservation, WheelObservation
from core.swept_envelope import require
from core.vehicle_assets import AssetResolver, Package, archive_format, asset_path, extract_hashfs, file_sha
from core.vehicle_profile import configuration_fingerprint


def read_json(path):
    require(Path(path).stat().st_size <= 64*1024*1024, 'INPUT_TOO_LARGE')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def nonfinite(_):
        raise ValueError('NONFINITE_JSON')
    return json.loads(Path(path).read_text(encoding='utf-8-sig'),
                      object_pairs_hook=unique, parse_constant=nonfinite)


def output_path(path):
    target = Path(path).resolve()
    require(target.is_relative_to(ROOT/'docs'/'steering-audit'), 'OUTPUT_OUTSIDE_IGNORED_AUDIT_ROOT')
    return target


def write_json(path, value):
    target = output_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as f:
        f.write(canonical(value))


def decode_observation(value):
    articles = []
    for source in value['articles']:
        a = dict(source)
        a['wheels'] = tuple(WheelObservation(**dict(w, position_m=tuple(w['position_m'])))
                            for w in a['wheels'])
        for name in ('hook_local_m', 'position_m', 'rotation_rad'):
            a[name] = tuple(a[name])
        articles.append(ArticleObservation(**a))
    result = dict(value, articles=tuple(articles), game_version=tuple(value['game_version']))
    require(set(result) <= {f.name for f in fields(VehicleObservation)}, 'UNKNOWN_OBSERVATION_FIELD')
    return VehicleObservation(**result)


def audit(game, mods, collection=None, *, timeout_s=90.):
    """Inventory container headers and named ZIP assets without extracting them.

    Installed/subscribed mods are NOT asserted to be active. A historical
    game's mount log cannot certify current accessories or override order.
    """
    deadline = time.monotonic() + timeout_s
    report = {'schema_version': 1, 'confirmed': False, 'runtime_authorized': False,
              'packages': [], 'found_scania_assets': [], 'mod_activity': 'UNKNOWN',
              'blockers': ['MISSING_COMPLETE_ACTIVE_CONFIGURATION',
                           'MISSING_VERIFIED_COLLISION_DECODER',
                           'MISSING_ATOMIC_GROUND_REFERENCE']}
    for root, role in ((Path(game), 'base_or_dlc'), (Path(mods), 'installed_mod')):
        for path in sorted(root.iterdir()):
            if not path.is_file() or path.suffix.lower() not in ('.zip', '.scs'):
                continue
            require(time.monotonic() < deadline, 'AUDIT_DEADLINE_EXCEEDED')
            row = {'name': path.name, 'role': role, 'size_bytes': path.stat().st_size,
                   'format': archive_format(path), 'active': None}
            report['packages'].append(row)
            if row['format'] != 'ZIP':
                continue
            try:
                with zipfile.ZipFile(path) as z:
                    row['entries'] = len(z.infolist())
                    matches = [i for i in z.infolist() if not i.is_dir()
                               and ('scania.s_2016' in i.filename.lower()
                                    or 'scania_2016' in i.filename.lower())
                               and Path(i.filename).suffix.lower() in ('.sii','.sui','.pmc','.pmd','.pmg','.pic')]
                    row['scan_complete'] = len(matches) <= 128
                    row['matching_assets'] = len(matches)
                    for info in matches[:128]:
                        require(time.monotonic() < deadline, 'AUDIT_DEADLINE_EXCEEDED')
                        if info.file_size > 4*1024*1024 or info.flag_bits & 1:
                            continue
                        name = asset_path(info.filename)
                        data = z.read(info)
                        found = {'package': path.name, 'path': name,
                                 'sha256': hashlib.sha256(data).hexdigest(), 'size_bytes': len(data)}
                        if name.endswith(('.sii','.sui')):
                            text = data.decode('utf-8-sig', errors='replace')
                            found['collision_links'] = re.findall(r'\bcollision\s*:\s*"([^"\n]+)"', text)
                        report['found_scania_assets'].append(found)
            except (ValueError, OSError, zipfile.BadZipFile, RuntimeError) as error:
                row['read_error'] = type(error).__name__ + ':' + str(error)
    report['formats'] = dict(Counter(p['format'] for p in report['packages']))
    if collection:
        source = Path(collection)/'automatic-observations.json'
        document = read_json(source)
        require(document.get('integrity_sha256') == hashlib.sha256(canonical(
            {k:v for k,v in document.items() if k != 'integrity_sha256'})).hexdigest(),
            'CAB_COLLECTION_INTEGRITY_MISMATCH')
        rows = document.get('samples', document.get('observations', []))
        observations = [r.get('vehicle_profile', {}).get('observation') for r in rows]
        valid = [o for o in observations if o and not o.get('failure_reason')]
        if valid:
            o = decode_observation(valid[0])
            report['cab01'] = {'configuration_fingerprint': configuration_fingerprint(o),
                              'truck_id': o.articles[0].vehicle_id,
                              'atomic': o.atomic, 'raw_sample_count': len(rows),
                              'source_sha256': file_sha(source),
                              'resolution': 'BLOCKED: incomplete cabin/chassis/accessory identity'}
        else:
            report['cab01'] = {'resolution': 'NO_USABLE_OBSERVATION'}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    a = sub.add_parser('audit')
    a.add_argument('--game', required=True); a.add_argument('--mods', required=True)
    a.add_argument('--collection'); a.add_argument('--output', required=True)
    e = sub.add_parser('extract')
    e.add_argument('--extractor', required=True); e.add_argument('--extractor-sha256', required=True)
    e.add_argument('--archive', required=True); e.add_argument('--output', required=True)
    b = sub.add_parser('build')
    b.add_argument('--job', required=True); b.add_argument('--output', required=True)
    b.add_argument('--cache'); b.add_argument('--cache-key-file')
    args = parser.parse_args()
    if args.command == 'audit':
        result = audit(args.game, args.mods, args.collection)
        write_json(args.output, result)
        print(json.dumps({'formats': result['formats'], 'assets': len(result['found_scania_assets']),
                          'cab01': result.get('cab01'), 'runtime_authorized': False}))
    elif args.command == 'extract':
        dst = output_path(args.output)
        receipt = extract_hashfs(args.extractor, args.extractor_sha256, args.archive, dst)
        write_json(dst.parent/(dst.name+'.receipt.json'), receipt)
        print(json.dumps(receipt))
    else:
        job = read_json(args.job)
        observation = decode_observation(read_json(job['observation_file']))
        packages = [Package(p['id'], Path(p['path'])) for p in job['packages_low_to_high']]
        with AssetResolver(packages) as resolver:
            result = compile_candidate(observation, job['configuration'], resolver,
                                       job['collision_exports'], job['limits'])
            repeated = compile_candidate(observation, job['configuration'], resolver,
                                         job['collision_exports'], job['limits'])
            require(canonical(result) == canonical(repeated), 'NONDETERMINISTIC_PROFILE_BUILD')
        write_json(args.output, result)
        if args.cache:
            require(args.cache_key_file is not None, 'MISSING_CACHE_KEY_FILE')
            ProfileCache(output_path(args.cache), Path(args.cache_key_file).read_bytes()).put(result)
        print(json.dumps({'asset_fingerprint': result['asset_fingerprint'],
                          'geometry_complete': result['geometry_complete'],
                          'blockers': result['blockers'], 'runtime_authorized': False}))


if __name__ == '__main__':
    main()
