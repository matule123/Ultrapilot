"""Prepare a verified archive + explicit reversible quota-recovery script.

Offline preparation only: never moves installation evidence, arms or starts it.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from tools.check_event_export_readiness import inventory
from core.steering_replay import inspect_replay


def prepare(directory,output):
    source=Path(directory).resolve();output=Path(output).resolve()
    workspace=Path(__file__).resolve().parents[1]
    if not output.is_relative_to(workspace/'docs/steering-audit') or output.exists():
        raise ValueError('Use a NEW workspace audit output directory')
    status=inventory(source)
    payload={}
    for row in status['files']:
        p=source/row['name']
        if not inspect_replay(p)['integrity_valid']:raise ValueError('Invalid original: '+p.name)
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('Source changed during preparation')
        payload[row['name']]=raw
    output.mkdir(parents=True)
    receipt=dict(source=str(source),inventory=status,originals_unchanged=True,
        installation_ready=status['ready'],action='PREPARED_NOT_APPLIED',runtime_authorized=False)
    (output/'archive-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    archive=output/'significant-events.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as zipped:
        for name,raw in payload.items():zipped.writestr(name,raw)
    with zipfile.ZipFile(archive) as zipped:
        for name,raw in payload.items():assert zipped.read(name)==raw
    # Dry run by default. Apply uses only exact manifest files, preflights all
    # hashes/collisions and rolls back the whole move on failure. No deletion.
    script=r'''param([switch]$Apply)
$ErrorActionPreference='Stop'
$manifest=Get-Content -LiteralPath (Join-Path $PSScriptRoot 'archive-receipt.json') -Raw | ConvertFrom-Json
$sourceRoot=[IO.Path]::GetFullPath($manifest.source)
$archiveRoot=[IO.Path]::GetFullPath((Join-Path $sourceRoot ('archive\'+[IO.Path]::GetFileName($PSScriptRoot))))
if(-not $archiveRoot.StartsWith($sourceRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Archive escapes diagnostic root'}
foreach($entry in $manifest.inventory.files){
  $from=[IO.Path]::GetFullPath((Join-Path $sourceRoot $entry.name))
  if([IO.Path]::GetDirectoryName($from) -ne $sourceRoot){throw 'Invalid source path'}
  if((Get-FileHash -LiteralPath $from -Algorithm SHA256).Hash -ne $entry.sha256){throw "Source changed: $from"}
  if(Test-Path -LiteralPath (Join-Path $archiveRoot $entry.name)){throw 'Refusing overwrite'}
}
if(-not $Apply){Write-Output 'PREPARED: no evidence moved. Close UltraPilot and ETS2, then run with -Apply.';return}
if(Get-Process -Name UltraPilot,eurotrucks2,amtrucks -ErrorAction SilentlyContinue){throw 'Close UltraPilot and ETS2 first'}
$moved=[Collections.Generic.List[string]]::new()
New-Item -ItemType Directory -Path $archiveRoot -ErrorAction Stop | Out-Null
try{
  foreach($entry in $manifest.inventory.files){
    Move-Item -LiteralPath (Join-Path $sourceRoot $entry.name) -Destination (Join-Path $archiveRoot $entry.name) -ErrorAction Stop
    $moved.Add($entry.name)
    if((Get-FileHash -LiteralPath (Join-Path $archiveRoot $entry.name)).Hash -ne $entry.sha256){throw 'Archive hash mismatch'}
  }
}catch{
  foreach($name in $moved){Move-Item -LiteralPath (Join-Path $archiveRoot $name) -Destination (Join-Path $sourceRoot $name) -ErrorAction Stop}
  throw
}
Write-Output 'Evidence archived without deletion. Run tools/check_event_export_readiness.py before a future collection.'
'''
    (output/'archive-events.ps1').write_text(script,encoding='utf-8')
    result=dict(directory=str(output),files=len(payload),archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        original_quota_ready=status['ready'],applied=False)
    print(json.dumps(result,indent=2));return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();prepare(args.directory,args.output)


if __name__=='__main__':main()
