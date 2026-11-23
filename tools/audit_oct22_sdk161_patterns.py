"""Read-only static native SDK/reference/installed-game audit, no DLL loading."""
import hashlib
import json
from pathlib import Path
import re
import urllib.request

import pefile

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'docs/steering-audit/oct22-sdk161'
OLD=ROOT/'docs/steering-audit/oct17-joint-lifecycle/native-candidate'
GAME=Path(r'C:\Program Files (x86)\Steam\steamapps\common\Euro Truck Simulator 2\bin\win_x64\eurotrucks2.exe')


def digest(data):return hashlib.sha256(data).hexdigest()


def compile_pattern(text):
    tokens=text.split()
    if len(tokens)<6:raise ValueError('Pattern too short')
    return re.compile(b''.join(b'.' if token=='?' else re.escape(bytes.fromhex(token)) for token in tokens),re.DOTALL)


def patterns(path):
    text=path.read_text(encoding='utf-8-sig');result=[]
    for match in re.finditer(r'constexpr\s+auto\s+pattern\s*=\s*("[^"]+"(?:\s*"[^"]+")*)\s*;',text):
        value=' '.join(re.findall(r'"([^"]+)"',match[1]))
        result.append(dict(line=text.count('\n',0,match.start())+1,pattern=value))
    return result


def section_records(path):
    data=path.read_bytes();pe=pefile.PE(data=data,fast_load=True)
    assert pe.FILE_HEADER.Machine==0x8664
    sections={section.Name.rstrip(b'\0').decode():dict(bytes=len(section.get_data()),sha256=digest(section.get_data())) for section in pe.sections}
    return data,pe,sections


def main():
    target=AUDIT/'reference160.dll'
    commit='f6cd09fe1b6e808200b5c9279113b45f2c28f31a'
    url=f'https://raw.githubusercontent.com/ETS2LA/ETS2LA/{commit}/Assets/SDKs/1.60/Windows/ets2la_plugin.dll'
    if not target.exists():
        with urllib.request.urlopen(url,timeout=30) as response:data=response.read()
        # Git object pinned independently from the upstream tree.
        assert hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest()=='b932fdf033cf4a79a922e0f81978dd460504e4b5'
        target.write_bytes(data)
    upstream=next((AUDIT/'inputs/upstream').iterdir())
    game_data,game,sections=section_records(GAME)
    executable=[s for s in game.sections if s.Characteristics&0x20000000]
    def scan(text):
        regex=compile_pattern(text);matches=[]
        for section in executable:
            matches.extend(section.VirtualAddress+m.start() for m in regex.finditer(section.get_data()))
        return matches
    inventories={}
    for name,source in (('installed159_source',OLD),('public160_source',upstream)):
        rows=patterns(source/'src/patterns.win32.hpp')
        for row in rows:row['executable_rvas']=scan(row['pattern'])
        inventories[name]=rows
    binary_info={}
    for name,path in (('official160',target),('official161',AUDIT/'inputs/official161/ets2la_plugin.dll')):
        data,pe,info=section_records(path)
        strings=[s.decode('ascii') for s in re.findall(rb'[\x20-\x7e]{6,}',data)]
        native_patterns=[s for s in strings if re.fullmatch(r'(?:[a-fA-F0-9]{2}|\?)(?: (?:[a-fA-F0-9]{2}|\?)){5,}',s)]
        binary_info[name]=dict(sha256=digest(data),bytes=len(data),sections=info,
            embedded_versions=[s for s in strings if re.fullmatch(r'1\.6[01](?:\.[x0-9]+)?',s)],
            patterns=[dict(pattern=p,executable_rvas=scan(p)) for p in native_patterns])
    changes=[]
    for path in sorted((upstream/'src/prism').rglob('*')):
        if path.is_file():
            relative=path.relative_to(upstream);old=OLD/relative
            if not old.exists() or digest(path.read_bytes())!=digest(old.read_bytes()):changes.append(str(relative))
    result=dict(game_path=str(GAME),game_sha256=digest(game_data),game_sections=sections,
        source_inventories=inventories,official_binaries=binary_info,changed_prism_files=changes,
        official160_text_equals_161=binary_info['official160']['sections'].get('.text')==binary_info['official161']['sections'].get('.text'),
        public_source_declares_160='set(GAME_VERSION_MINOR 60)' in (upstream/'CMakeLists.txt').read_text(),
        dynamic_layouts_verified=False,deployed=False,executed_dll=False)
    (AUDIT/'pattern-audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(source_match_counts={name:[len(r['executable_rvas']) for r in rows] for name,rows in inventories.items()},
        binary_versions={name:info['embedded_versions'] for name,info in binary_info.items()},
        binary_pattern_counts={name:[len(r['executable_rvas']) for r in info['patterns']] for name,info in binary_info.items()},
        official160_text_equals_161=result['official160_text_equals_161'],changed_prism_files=len(changes)),indent=2))


if __name__=='__main__':main()
