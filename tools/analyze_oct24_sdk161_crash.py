"""Join preserved game crash addresses to the exact quarantined candidate PE."""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'docs/steering-audit/oct22-sdk161'
sys.path.insert(0,str(AUDIT/'python-tools'))
import pefile
from capstone import Cs,CS_ARCH_X86,CS_MODE_64


def main():
    folder=AUDIT/'quarantine-candidate-d'
    dll=(folder/'UltraPilot161ReadCandidate.dll.disabled').read_bytes()
    digest=hashlib.sha256(dll).hexdigest()
    if digest!='2dbedf8da6479785e409163ee2755a299d509f88982ba832bec149c19c4d7add':raise ValueError('Wrong crash candidate')
    crash=(folder/'game.crash.txt').read_bytes();text=crash.decode('utf-8',errors='replace')
    pe=pefile.PE(data=dll);dis=Cs(CS_ARCH_X86,CS_MODE_64);incidents=[]
    for block in text.split('Crash log created on: ')[1:]:
        fault=re.search(r'Fault address: ([0-9A-F]+) .*UltraPilot161ReadCandidate\.dll',block)
        module=re.search(r'^([0-9A-F]{16}) [0-9A-F]{8} [0-9A-F]{16} .*plugins\\UltraPilot161ReadCandidate\.dll',block,re.M)
        if not fault or not module:continue
        rva=int(fault[1],16)-int(module[1],16)
        instruction=next(dis.disasm(pe.get_data(rva,8),rva))
        if instruction.mnemonic!='call' or instruction.op_str!='qword ptr [rax + 0x28]':raise ValueError('Unexpected fault instruction')
        # Decode known instruction boundaries separately rather than assuming
        # arbitrary preceding bytes start at an instruction boundary.
        condition=list(dis.disasm(pe.get_data(rva-0x24,11),rva-0x24))
        incidents.append(dict(created=block.splitlines()[0],exception=re.search(r'Exception code: (.+)',block)[1],
            module_base=module[1],fault_rva=hex(rva),rax=re.search(r'RAX:([0-9A-F]+)',block)[1],
            instruction=instruction.mnemonic+' '+instruction.op_str,instruction_bytes=instruction.bytes.hex(' '),
            empty_count_condition=[i.mnemonic+' '+i.op_str for i in condition]))
    if len(incidents)<2:raise ValueError('Two candidate incidents were not found')
    result=dict(candidate_sha256=digest,crash_sha256=hashlib.sha256(crash).hexdigest(),incidents=incidents,
        causal_path='zero-size non-AI list -> legacy sentinel traversal -> virtual descriptor call via vtable 5',
        historical_autopilot_cause_proven=False,production_ready=False)
    (AUDIT/'candidate-d-crash-analysis.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
