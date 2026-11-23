"""Fetch pinned public SDK reference inputs; never executes or installs DLLs."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'docs/steering-audit/oct22-sdk161/inputs'
GITLAB='c925bd965a96c58b73eaea9ca033fe0f0dc623a7'
GITHUB='f6cd09fe1b6e808200b5c9279113b45f2c28f31a'


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'UltraPilot-SDK-audit'}),timeout=45) as response:
        return response.read()


def main():
    if OUTPUT.exists():raise RuntimeError('Use untouched dedicated input directory')
    OUTPUT.mkdir(parents=True)
    receipt=dict(gitlab_commit=GITLAB,github_commit=GITHUB,artifacts=[],installed=False,executed=False)
    url=f'https://gitlab.com/api/v4/projects/ETS2LA%2Fets2la_plugin/repository/archive.tar.gz?sha={GITLAB}'
    data=fetch(url);(OUTPUT/'producer.tar.gz').write_bytes(data)
    receipt['artifacts'].append(dict(path='producer.tar.gz',url=url,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        archive.extractall(OUTPUT/'upstream',filter='data')
    tree=json.loads(fetch(f'https://api.github.com/repos/ETS2LA/ETS2LA/git/trees/{GITHUB}?recursive=1'))
    blobs={r['path']:r['sha'] for r in tree['tree'] if r['type']=='blob'}
    for name in ('ets2la_plugin.dll','scs-telemetry.dll','scs_sdk_controller.dll','sources.txt','ets2la_1.61'):
        path=f'Assets/SDKs/1.61/Windows/{name}'
        url=f'https://raw.githubusercontent.com/ETS2LA/ETS2LA/{GITHUB}/{path}'
        data=fetch(url)
        assert hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()==blobs[path],'Git object mismatch'
        dest=OUTPUT/'official161'/name;dest.parent.mkdir(exist_ok=True);dest.write_bytes(data)
        receipt['artifacts'].append(dict(path=str(dest.relative_to(OUTPUT)),url=url,git_blob=blobs[path],sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
    receipt['upstream_files']={str(p.relative_to(OUTPUT)) :hashlib.sha256(p.read_bytes()).hexdigest() for p in (OUTPUT/'upstream').rglob('*') if p.is_file()}
    (OUTPUT/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k!='upstream_files'},indent=2))


if __name__=='__main__':main()
