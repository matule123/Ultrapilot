"""Prepare the standard-name 1.61 read producer; never installs into the game.

Only mapping/version labels differ from the live-tested isolated candidate-e.
Controls stay disabled; SCS controller is the app's independent control backend.
"""
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.prepare_oct24_sdk161_candidate import compile_source

AUDIT=ROOT/'docs/steering-audit/oct22-sdk161'
BASE=AUDIT/'read-candidate-e'
OUTPUT=AUDIT/'read-runtime-a'
REPLACEMENTS=(('UltraPilot161Candidate',''),
    ('1.61.0-up-read-candidate','1.61.0-up-scoped-read'),
    ('isolated diagnostic, NO controls','data producer; controls owned by SCS backend'),
    ('UltraPilot161ReadCandidate','ets2la_plugin'))


def transform(text):
    # Sidecar prefix and legacy buffer prefix have different standard names.
    text=text.replace('UltraPilot161CandidateSemaphore','UltraPilotSemaphore')
    text=text.replace('UltraPilot161CandidateTraffic','UltraPilotTraffic')
    text=text.replace('UltraPilot161CandidateETS2LA','ETS2LA')
    for old,new in REPLACEMENTS[1:]:text=text.replace(old,new)
    return text


def main():
    if OUTPUT.exists():raise ValueError('Use a new runtime output; do not overwrite evidence')
    base_receipt=json.loads((BASE/'build-receipt.json').read_text())
    for name,digest in base_receipt['files'].items():
        if hashlib.sha256((BASE/name).read_bytes()).hexdigest()!=digest:raise ValueError('Candidate-e changed: '+name)
    shutil.copytree(BASE,OUTPUT,ignore=shutil.ignore_patterns('*.dll','*.obj','*.exe','*.lib','*.exp','*.pdb',
        'verification','sentinel-regression*','build-receipt.json','compile.*'))
    transformed=[]
    for path in (OUTPUT/'src').rglob('*'):
        if path.suffix not in ('.cpp','.hpp'):continue
        text=path.read_text(encoding='utf-8-sig');new=transform(text)
        if new!=text:path.write_text(new,encoding='utf-8');transformed.append(str(path.relative_to(OUTPUT)))
    definition=OUTPUT/'ets2la_plugin.def'
    definition.write_text(transform(definition.read_text()),encoding='utf-8')
    compile_source(OUTPUT,'ets2la_plugin.dll')
    result=dict(version='1.61.0-up-scoped-read',controls_enabled=False,production_ready=False,
        deployed=False,game_verified=False,standard_mappings=True,multiplayer_motion_supported=False,
        derived_from_candidate_sha256=base_receipt['dll_sha256'],game_sha256=base_receipt['game_sha256'],
        transformed_source_labels=transformed,
        files={str(p.relative_to(OUTPUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUTPUT.rglob('*')
            if p.suffix in ('.cpp','.hpp','.dll')})
    result['dll_sha256']=result['files']['ets2la_plugin.dll']
    (OUTPUT/'build-receipt.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='files'},indent=2))


if __name__=='__main__':main()
