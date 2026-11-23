"""Read-only disk preflight. A plan is not permission to move or delete files."""
from pathlib import Path
import argparse
import hashlib
import json
from core.steering_replay import incident_diagnostic_budget, _payload_hash, SCHEMA_VERSION

def preflight(directory):
    root=Path(directory)
    budget=incident_diagnostic_budget(root)
    referenced=set()
    for path in root.glob('incident-*.json'):
        value=json.loads(path.read_bytes())
        if value.get('integrity',{}).get('payload_sha256')!=_payload_hash(value):
            raise ValueError('INCIDENT_PREFLIGHT_MANIFEST_HASH')
        referenced.update(r['name'] for r in value.get('files',()))
    reserve=32*1024*1024
    candidates=[];remaining=budget['active_bytes'];archived=budget['archive_bytes']
    for path in sorted(root.glob('steering-replay-*-devinputs.json'),key=lambda p:p.stat().st_mtime):
        if remaining+reserve<=budget['active_limit_bytes']:break
        if path.name in referenced:continue
        raw=path.read_bytes();value=json.loads(raw)
        if value.get('schema_version')!=SCHEMA_VERSION or value.get('integrity')!=dict(
            algorithm='sha256',payload_sha256=_payload_hash(value)):
            raise ValueError('INCIDENT_PREFLIGHT_STANDALONE_HASH')
        if archived+len(raw)>budget['archive_limit_bytes']:break
        candidates.append(dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
            destination=str(root/'archive'/('standalone-'+hashlib.sha256(raw).hexdigest())/path.name)))
        remaining-=len(raw);archived+=len(raw)
    return dict(budget=budget,reserve_bytes=reserve,
        ready_without_archival=budget['ready'] and budget['active_bytes']+reserve<=budget['active_limit_bytes'],
        possible_after_verified_archive=budget['ready'] and remaining+reserve<=budget['active_limit_bytes'],
        proposed_standalone_archive=candidates,projected_active_bytes=remaining,
        projected_archive_bytes=archived,files_changed=False,
        pending_ap_parts_preserved=True,game_verified=False)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=preflight(args.directory)
    text=json.dumps(result,indent=2)
    if args.output:args.output.write_text(text,encoding='utf-8')
    print(text)
