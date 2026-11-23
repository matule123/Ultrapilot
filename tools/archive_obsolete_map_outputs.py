"""Losslessly archive explicit obsolete generator outputs before cleanup."""
import hashlib
import json
from pathlib import Path
import zipfile
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'docs/steering-audit/mapconverter-159-work'
NAMES=('offline-verification-output','offline-native-boundaries-final',
       'native-world-features-110-20261019-v7','native-world-features-110-20261019-v5',
       'reference-integration-isolated','projected-node-export-20261019','build')

def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'docs/cleanup-archives'/stamp
    out.mkdir(parents=True)
    archive=out/'obsolete-map159-outputs.zip'
    entries=[]
    paths=[]
    for name in NAMES:
        folder=(BASE/name).resolve()
        assert folder.is_relative_to(BASE.resolve()) and folder.is_dir()
        for p in sorted(folder.rglob('*')):
            assert not p.is_symlink() and not p.is_junction(), str(p)
            if p.is_file():paths.append(p)
    total=sum(p.stat().st_size for p in paths)
    print(json.dumps(dict(stage='archive',files=len(paths),bytes=total)),flush=True)
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as z:
        for index,p in enumerate(paths):
            relative=p.relative_to(BASE).as_posix();digest=hashlib.sha256();size=0
            with p.open('rb') as source,z.open(relative,'w',force_zip64=True) as target:
                while chunk:=source.read(4*1024*1024):
                    digest.update(chunk);size+=len(chunk);target.write(chunk)
            entries.append(dict(path=relative,bytes=size,sha256=digest.hexdigest()))
            if index%200==0:print('Archived',index+1,'/',len(paths),flush=True)
    print('Verifying all archive contents and unchanged source hashes',flush=True)
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist())=={v['path'] for v in entries}
        for entry in entries:
            digest=hashlib.sha256();size=0
            with z.open(entry['path']) as source:
                while chunk:=source.read(4*1024*1024):digest.update(chunk);size+=len(chunk)
            assert size==entry['bytes'] and digest.hexdigest()==entry['sha256']
            digest=hashlib.sha256()
            with (BASE/entry['path']).open('rb') as source:
                while chunk:=source.read(4*1024*1024):digest.update(chunk)
            assert digest.hexdigest()==entry['sha256'],'Source changed: '+entry['path']
    result=dict(archive=str(archive),verified=True,source_base=str(BASE.resolve()),
        directories=[str((BASE/n).resolve()) for n in NAMES],files=entries,
        original_bytes=total,archive_bytes=archive.stat().st_size,originals_removed=False)
    (out/'manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('files','directories')},indent=2),flush=True)

if __name__=='__main__':main()
