"""Build-specific instruction evidence; never reads running game object memory.

Several sites may prove the same value. Never select the first match when
decoded operands disagree. This is NOT a certificate for any Prism layout.
"""
import hashlib
import json
from pathlib import Path
import re
import struct

import pefile

ROOT=Path(__file__).resolve().parents[2]
AUDIT=ROOT/'docs/steering-audit/oct22-sdk161'
REFERENCE_SHA256='0e1893719f84f28079857451b82a22a263401d98b8fc299cd561eb7695bfa88f'
PATTERNS_SHA256='431aba108fed2189e6c0a36bab47ae0a77a728757c991b1821fa1bf6859a6db8'


def consensus(values):
    unique=set(values)
    if len(unique)!=1:raise ValueError('Missing or divergent decoded instruction values')
    return unique.pop()


def decode_operand(code,rva,instruction_offset,opcode,kind):
    prefix=bytes.fromhex(opcode);start=instruction_offset
    if code[start:start+len(prefix)]!=prefix:raise ValueError('Instruction opcode/layout mismatch')
    offset=start+len(prefix)
    if len(code)<offset+4:raise ValueError('Truncated operand')
    if kind=='rip_relative_global':return rva+offset+4+struct.unpack_from('<i',code,offset)[0]
    if kind=='member_offset':return struct.unpack_from('<I',code,offset)[0]
    raise ValueError('Unknown operand kind')


def resolve_binding(pe,matches,instruction_offset,opcode,kind):
    sites=[]
    for rva in matches:
        section=pe.get_section_by_rva(rva)
        width=instruction_offset+len(bytes.fromhex(opcode))+4
        if (section is None or not section.Characteristics&0x20000000
                or rva+width>section.VirtualAddress+min(section.Misc_VirtualSize,section.SizeOfRawData)):
            raise ValueError('Instruction is outside file-backed executable section')
        code=pe.get_data(rva,width)
        value=decode_operand(code,rva,instruction_offset,opcode,kind)
        if kind=='rip_relative_global':
            target=pe.get_section_by_rva(value)
            if (value%8 or target is None or not target.Characteristics&0x80000000
                    or target.Characteristics&0x20000000 or value+8>target.VirtualAddress+target.Misc_VirtualSize):
                raise ValueError('Global slot is outside writable non-executable data')
        elif value==0 or value>=0x100000 or value%4:
            raise ValueError('Implausible or unaligned member offset')
        sites.append(dict(instruction_rva=rva,operand=value,instruction_bytes=code.hex(' ')))
    return dict(kind=kind,value=consensus(s['operand'] for s in sites),sites=sites,
        site_consensus=True,object_layout_verified=False)


def verify_occurrences(pe,row):
    """Re-scan the pinned EXE rather than trusting saved locations alone."""
    tokens=row['pattern'].split()
    if len(tokens)<6:raise ValueError('Pattern too short')
    regex=re.compile(b''.join(b'.' if t=='?' else re.escape(bytes.fromhex(t)) for t in tokens),re.DOTALL)
    actual=[]
    for section in pe.sections:
        if section.Characteristics&0x20000000:
            actual.extend(section.VirtualAddress+m.start() for m in regex.finditer(section.get_data()))
    if actual!=row['executable_rvas']:raise ValueError('Saved pattern occurrences do not match EXE')


def main():
    audit_path=AUDIT/'pattern-audit.json';audit=json.loads(audit_path.read_text())
    game=Path(audit['game_path']);data=game.read_bytes()
    if hashlib.sha256(data).hexdigest()!=audit['game_sha256']:raise ValueError('Game EXE changed; rerun static audit')
    pe=pefile.PE(data=data,fast_load=True)
    if pe.FILE_HEADER.Machine!=0x8664:raise ValueError('Expected x64 game')
    reference=(AUDIT/'inputs/official161/ets2la_plugin.dll').read_bytes()
    if hashlib.sha256(reference).hexdigest()!=REFERENCE_SHA256:raise ValueError('Reference DLL changed')
    upstream=list((AUDIT/'inputs/upstream').glob('*/src/patterns.win32.hpp'))
    if len(upstream)!=1:raise ValueError('Expected one pinned source pattern file')
    source_bytes=upstream[0].read_bytes()
    if hashlib.sha256(source_bytes).hexdigest()!=PATTERNS_SHA256:raise ValueError('Source pattern file changed')
    binary=audit['official_binaries']['official161']['patterns']
    source=audit['source_inventories']['public160_source']
    # Check provenance, every occurrence and opcode; never choose a first hit.
    for row in binary:
        if row['pattern'].encode()+b'\0' not in reference:raise ValueError('Pattern absent from reference DLL')
        verify_occurrences(pe,row)
    if source[4]['pattern'].encode() not in source_bytes:raise ValueError('Camera pattern absent from source')
    verify_occurrences(pe,source[4])
    specs=(
        ('base_ctrl_global',binary[0],0,'48 8b 05','rip_relative_global'),
        ('game_actor_member',binary[0],13,'48 8b 80','member_offset'),
        ('nearby_non_ai_list',binary[1],5,'48 8d b9','member_offset'),
        ('nearby_kdop_items',binary[2],0,'4c 8d 81','member_offset'),
        ('gps_manager_member',binary[3],0,'48 8d 88','member_offset'),
        ('game_traffic_global',binary[4],3,'48 8b 0d','rip_relative_global'),
        ('slave_trailer_member',binary[5],0,'48 8b 86','member_offset'),
        ('trailer_member',binary[6],4,'49 8b 8e','member_offset'),
        ('steering_member',binary[7],2,'f3 0f 10 97','member_offset'),
        ('camera_manager_global',source[4],0,'48 8b 05','rip_relative_global'),
    )
    result=dict(schema=1,game_sha256=audit['game_sha256'],audit_sha256=hashlib.sha256(audit_path.read_bytes()).hexdigest(),
        reference_sha256=REFERENCE_SHA256,source_patterns_sha256=PATTERNS_SHA256,
        bindings={},production_ready=False,dynamic_layouts_verified=False,game_memory_read=False)
    for name,row,offset,opcode,kind in specs:
        binding=resolve_binding(pe,row['executable_rvas'],offset,opcode,kind)
        binding['pattern']=row['pattern'];result['bindings'][name]=binding
    result['unverified']=['1.61 Prism object sizes/field ownership','traffic actor arrays and incarnations',
        'GPS route-task and node layouts','traffic lights and directed prefab ownership',
        'camera matrices/placement layout','custom signal/traffic publication lifecycle']
    output=AUDIT/'static-profile-161.json';output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(bindings={name:dict(value=hex(row['value']),sites=len(row['sites'])) for name,row in result['bindings'].items()},
        production_ready=False,dynamic_layouts_verified=False),indent=2))


if __name__=='__main__':main()
