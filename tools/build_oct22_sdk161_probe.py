"""Build an isolated, passive SCS telemetry/signature probe; never deploy it."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'docs/steering-audit/oct22-sdk161'
OUTPUT=AUDIT/'read-only-probe'
VCVARS=Path(r'C:\DevTools\VS2022BuildTools\VC\Auxiliary\Build\vcvars64.bat')


def main():
    if (OUTPUT/'UltraPilot161ReadOnlyProbe.dll').exists():raise RuntimeError('Refuse successful build overwrite')
    OUTPUT.mkdir(exist_ok=True)
    audit=json.loads((AUDIT/'pattern-audit.json').read_text())
    patterns=[r['pattern'] for r in audit['official_binaries']['official161']['patterns']]
    header='#pragma once\nconstexpr unsigned PROBE_PATTERN_COUNT='+str(len(patterns))+';\nconstexpr const char* PROBE_PATTERNS[]={'+','.join(json.dumps(p) for p in patterns)+'};\n'
    (OUTPUT/'probe_patterns.hpp').write_text(header,encoding='utf-8')
    sdk=ROOT/'docs/steering-audit/oct17-joint-lifecycle/native-candidate/vendor/scs_sdk/include'
    source=ROOT/'tools/sdk161_probe/probe.cpp'
    dll=OUTPUT/'UltraPilot161ReadOnlyProbe.dll'
    command=['cl','/nologo','/LD','/O2','/MT','/std:c++17','/EHsc','/utf-8','/Brepro',
        '/I'+str(sdk),'/I'+str(OUTPUT),str(source),'/link','/Brepro','/DEF:'+str(source.with_suffix('.def')),'/OUT:'+str(dll)]
    script=OUTPUT/'compile.cmd'
    script.write_text('@echo off\ncall "'+str(VCVARS)+'" >nul\nif errorlevel 1 exit /b 1\n'+subprocess.list2cmdline(command)+'\nexit /b %errorlevel%\n',encoding='utf-8')
    process=subprocess.run(['cmd','/d','/c',str(script)],cwd=OUTPUT,capture_output=True)
    (OUTPUT/'compile.log').write_bytes(process.stdout+process.stderr)
    if process.returncode:raise RuntimeError((process.stdout+process.stderr).decode(errors='replace'))
    receipt=dict(read_only=True,production_ready=False,native_layouts_verified=False,game_verified=False,deployed=False,
        official_pattern_count=len(patterns),game_sha256=audit['game_sha256'],
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),dll_sha256=hashlib.sha256(dll.read_bytes()).hexdigest(),
        sdk_headers={str(p.relative_to(sdk)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sdk.rglob('*.h')})
    (OUTPUT/'receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k!='sdk_headers'},indent=2))


if __name__=='__main__':main()
