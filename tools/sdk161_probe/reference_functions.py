"""Offline disassembly evidence from the pinned reference DLL, never loads it."""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
AUDIT=ROOT/'docs/steering-audit/oct22-sdk161'
sys.path.insert(0,str(AUDIT/'python-tools'))
import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_64, CS_OP_MEM, CS_OP_IMM
from capstone.x86 import X86_REG_RIP


def main():
    data=(AUDIT/'inputs/official161/ets2la_plugin.dll').read_bytes()
    if hashlib.sha256(data).hexdigest()!='0e1893719f84f28079857451b82a22a263401d98b8fc299cd561eb7695bfa88f':
        raise ValueError('Reference changed')
    pe=pefile.PE(data=data);base=pe.OPTIONAL_HEADER.ImageBase
    functions={row.struct.BeginAddress:row.struct.EndAddress for row in pe.DIRECTORY_ENTRY_EXCEPTION}
    strings={pe.get_rva_from_offset(m.start()):m.group().decode() for m in re.finditer(rb'[\x20-\x7e]{6,}',data)}
    relevant={r:s for r,s in strings.items() if any(k in s.lower() for k in ('throttle input','brake input','camera_manager','vehicle_shared','game_actor','base_ctrl','gps_manager','game_traffic','memory patterns')) or re.fullmatch(r'(?:[0-9a-fA-F]{2}|\?)(?: (?:[0-9a-fA-F]{2}|\?)){5,}',s)}
    dis=Cs(CS_ARCH_X86,CS_MODE_64);dis.detail=True;hits=[]
    for begin,end in functions.items():
        instructions=list(dis.disasm(pe.get_data(begin,end-begin),base+begin));refs=[]
        for ins in instructions:
            for operand in ins.operands:
                if operand.type==CS_OP_MEM and operand.mem.base==X86_REG_RIP:
                    target=ins.address+ins.size+operand.mem.disp-base
                    if target in relevant:refs.append(dict(at=hex(ins.address-base),target=hex(target),text=relevant[target]))
        if refs:
            hits.append(dict(begin=hex(begin),end=hex(end),references=refs,
                instructions=[f'{i.address-base:08x} {i.bytes.hex(" "):30} {i.mnemonic} {i.op_str}' for i in instructions]))
    output=AUDIT/'reference-functions-161.json'
    output.write_text(json.dumps(dict(dll_sha256=hashlib.sha256(data).hexdigest(),functions=hits,
        executed=False,production_ready=False),indent=2),encoding='utf-8')
    for hit in hits:
        print(hit['begin'],[(r['at'],r['text']) for r in hit['references']])
    print(output)


if __name__=='__main__':main()
