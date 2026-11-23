"""Rebuild packaged native sources in an isolated folder, never in the game."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.sdk.versioned_sdk import load_bundle
from tools.verify_oct17_native_records import VCVARS


def main():
    folder,manifest=load_bundle(str(ROOT/'assets'),'1.61');folder=Path(folder)
    archive=folder/'native-source.zip'
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=manifest['source_archive_sha256']:
        raise ValueError('Source archive changed')
    output=ROOT/'docs/steering-audit/oct22-sdk161/packaged-source-rebuild'
    output.mkdir(exist_ok=False)
    with zipfile.ZipFile(archive) as source:
        for name in source.namelist():
            if not (output/name).resolve().is_relative_to(output.resolve()):
                raise ValueError('Archive traversal')
        source.extractall(output)
    command=output/'verify-build.cmd'
    command.write_text('@echo off\n'+f'call "{VCVARS}" >nul\nif errorlevel 1 exit /b 1\n'
        +'call build.cmd\nexit /b %errorlevel%\n',encoding='utf-8')
    built=subprocess.run(['cmd','/d','/c',str(command)],cwd=output,capture_output=True)
    (output/'build.log').write_bytes(built.stdout+built.stderr)
    if built.returncode:raise RuntimeError((built.stdout+built.stderr).decode(errors='replace'))
    host=ROOT/'docs/steering-audit/oct22-sdk161/read-runtime-a/verification/candidate-host.exe'
    tested=subprocess.run([str(host),str(output/'ets2la_plugin.dll')],capture_output=True,text=True,timeout=20)
    if tested.returncode:raise RuntimeError(tested.stdout+tested.stderr)
    result=dict(source_archive_sha256=manifest['source_archive_sha256'],build_pass=True,
        native_host_pass=True,native_host_output=tested.stdout.strip(),
        rebuilt_dll_sha256=hashlib.sha256((output/'ets2la_plugin.dll').read_bytes()).hexdigest(),
        note='Paths/compiler inputs may affect binary identity; release uses manifest-pinned DLL.',
        game_executed=False,deployed=False)
    (output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
