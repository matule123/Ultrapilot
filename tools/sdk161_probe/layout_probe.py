"""Bounded, external READ-ONLY layout evidence. Never invokes game functions.

Offsets from the public 1.60 source are hypotheses, not production contracts.
No game mappings are published. This tool cannot certify an entire ABI.
"""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import time

# Standalone analysis dependency, never installed into the app or game.
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'docs/steering-audit/oct22-sdk161/python-tools'))
from capstone import Cs, CS_ARCH_X86, CS_MODE_64

ROOT=Path(__file__).resolve().parents[2]
AUDIT=ROOT/'docs/steering-audit/oct22-sdk161'
MAX_READ=4096
MAX_TOTAL=2*1024*1024


def checked_array(raw,limit=64):
    if len(raw)!=40:raise ValueError('Truncated Windows array_dyn hypothesis')
    vtable,data,size,capacity,allocator=struct.unpack('<5Q',raw)
    if size>capacity or size>limit or capacity>100000:raise ValueError('Array bounds rejected')
    if size and (data<0x10000 or data%8):raise ValueError('Array pointer rejected')
    return dict(vtable=vtable,data=data,size=size,capacity=capacity,allocator=allocator)


def decode_placement(raw):
    if len(raw)!=32:raise ValueError('Truncated placement')
    x,y,z,cx,cz,qw,qx,qy,qz=struct.unpack('<3f2h4f',raw)
    if not all(math.isfinite(v) for v in (x,y,z,qw,qx,qy,qz)):raise ValueError('Nonfinite placement')
    norm=sum(v*v for v in (qw,qx,qy,qz))
    if not .8<norm<1.2:raise ValueError('Implausible placement')
    return dict(local=[x,y,z],cell=[cx,cz],quaternion=[qw,qx,qy,qz],world=[x+cx*512,y,z+cz*512])


class Reader:
    def __init__(self,pid):
        self.k=ctypes.WinDLL('kernel32',use_last_error=True)
        self.k.OpenProcess.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.DWORD)
        self.k.OpenProcess.restype=wintypes.HANDLE
        self.k.CloseHandle.argtypes=(wintypes.HANDLE,)
        self.k.ReadProcessMemory.argtypes=(wintypes.HANDLE,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t))
        self.k.ReadProcessMemory.restype=wintypes.BOOL
        self.k.K32EnumProcessModules.argtypes=(wintypes.HANDLE,ctypes.POINTER(wintypes.HMODULE),wintypes.DWORD,ctypes.POINTER(wintypes.DWORD))
        self.k.K32GetModuleFileNameExW.argtypes=(wintypes.HANDLE,wintypes.HMODULE,wintypes.LPWSTR,wintypes.DWORD)
        self.handle=self.k.OpenProcess(0x410,False,pid) # QUERY_INFORMATION | VM_READ only
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        self.total=0
        try:
            modules=(wintypes.HMODULE*1024)();needed=wintypes.DWORD()
            if not self.k.K32EnumProcessModules(self.handle,modules,ctypes.sizeof(modules),ctypes.byref(needed)):
                raise ctypes.WinError(ctypes.get_last_error())
            self.base=modules[0];path=ctypes.create_unicode_buffer(32768)
            if not self.k.K32GetModuleFileNameExW(self.handle,self.base,path,len(path)):raise ctypes.WinError(ctypes.get_last_error())
            self.path=Path(path.value)
            pinned=json.loads((AUDIT/'static-profile-161.json').read_text())
            if self.path.name.lower()!='eurotrucks2.exe' or hashlib.sha256(self.path.read_bytes()).hexdigest()!=pinned['game_sha256']:
                raise ValueError('Running module is not the pinned game EXE')
            if self.read(self.base,2)!=b'MZ':raise ValueError('Module header mismatch')
        except BaseException:
            self.close();raise

    def close(self):
        if self.handle:self.k.CloseHandle(self.handle);self.handle=None

    def read(self,address,size):
        if not 0<size<=MAX_READ or self.total+size>MAX_TOTAL:raise ValueError('Read budget exceeded')
        if not 0x10000<=address<0x7fffffffffff-size:raise ValueError('Invalid address')
        self.total+=size
        value=ctypes.create_string_buffer(size);received=ctypes.c_size_t()
        if not self.k.ReadProcessMemory(self.handle,address,value,size,ctypes.byref(received)) or received.value!=size:
            raise OSError('Unreadable bounded field')
        return value.raw

    def pointer(self,address):return struct.unpack('<Q',self.read(address,8))[0]

    def constant_type(self,address):
        """Decode a constant get_type body; NEVER call a virtual method."""
        vtable=self.pointer(address);function=self.pointer(vtable+8)
        ins=list(Cs(CS_ARCH_X86,CS_MODE_64).disasm(self.read(function,16),function))
        if len(ins)>=2 and ins[0].mnemonic=='mov' and ins[0].op_str.startswith('eax, ') and ins[1].mnemonic=='ret':
            return int(ins[0].op_str.split(', ')[1],0)
        raise ValueError('Type method is not a verified constant-return instruction sequence')


def sample(reader,bindings):
    roots={name:reader.pointer(reader.base+bindings[name]['value']) for name in
        ('base_ctrl_global','game_traffic_global','camera_manager_global')}
    result=dict(roots=roots,hypotheses={},errors={})
    def attempt(name,operation):
        try:result['hypotheses'][name]=operation()
        except (OSError,ValueError,struct.error) as error:result['errors'][name]=str(error)
    base=roots['base_ctrl_global'];traffic=roots['game_traffic_global'];camera=roots['camera_manager_global']
    def ego():
        actor=reader.pointer(base+bindings['game_actor_member']['value'])
        truck=reader.pointer(actor+0x18)
        box=struct.unpack('<6f',reader.read(truck+0x18,24))
        return dict(actor=actor,truck=truck,aabox=box)
    attempt('ego',ego)
    def gps():
        manager=base+bindings['gps_manager_member']['value']
        # gps_manager has its own vtable then simple_route_source at +8.
        task=reader.pointer(manager+8+0x20)
        result=dict(manager=manager,task=task)
        if task:
            arr=checked_array(reader.read(task+0x50,40),limit=6000)
            result['physical_route_items']=arr
            result['first_items']=[]
            for index in range(min(arr['size'],4)):
                raw=reader.read(arr['data']+index*32,32);node=struct.unpack_from('<Q',raw)[0]
                result['first_items'].append(dict(node=node,uid=reader.pointer(node+0x30),
                    node_coords=struct.unpack('<3i',reader.read(node,12)),
                    distance_time=struct.unpack_from('<4f',raw,12)))
        result['trip']=struct.unpack('<4f',reader.read(manager+0x274,16))
        return result
    attempt('gps',gps)
    def cameras():
        current,total=struct.unpack('<2I',reader.read(camera+0x10,8))
        arr=checked_array(reader.read(camera+0x30,40))
        if current>=arr['size']:raise ValueError('Camera index outside candidate array')
        ptr=reader.pointer(arr['data']+current*8)
        fov,near,far=struct.unpack('<3f',reader.read(ptr+0x20,12))
        return dict(current=current,total=total,array=arr,camera=ptr,fov=fov,near=near,far=far,
            placement=decode_placement(reader.read(ptr+0x40,32)))
    attempt('camera',cameras)
    for name,offset,stride in (('spawned',0xf0,16),('objects',0x1e0,8)):
        def actors(offset=offset,stride=stride):
            arr=checked_array(reader.read(traffic+offset,40));items=[]
            # Only bounded first entries; not a complete traffic acquisition.
            for index in range(min(arr['size'],8)):
                ptr=reader.pointer(arr['data']+index*stride)
                item=dict(pointer=ptr)
                try:
                    item['type']=reader.constant_type(ptr)
                    if item['type'] not in (1,2,3,4,5,6,7):raise ValueError('Object is not a traffic actor')
                    item['placement']=decode_placement(reader.read(ptr+0x28,32))
                    item['box']=struct.unpack('<6f',reader.read(ptr+0x48,24))
                    if item['type']==1:
                        physics=reader.pointer(ptr+0x238)
                        item['physics']=physics
                        item['speed_acceleration']=struct.unpack('<2f',reader.read(physics+0x70,8))
                except (ValueError,OSError,struct.error) as error:item['error']=str(error)
                items.append(item)
            return dict(array=arr,items=items,complete=False)
        attempt(name,actors)
    def prefabs():
        arr=checked_array(reader.read(base+bindings['nearby_kdop_items']['value'],40),limit=100000)
        items=[]
        # Sample a bounded prefix and report it as incomplete, never empty-clear.
        for index in range(min(arr['size'],512)):
            ptr=reader.pointer(arr['data']+index*8)
            kind=reader.read(ptr+0xa,1)[0]
            if kind!=4:continue
            segment=reader.pointer(ptr+0x48)
            item=dict(pointer=ptr,uid=reader.pointer(ptr+0x40),segment=segment,
                nodes=[],origin_candidates=struct.unpack('<3Q',reader.read(ptr+0x118,24)))
            for node in struct.unpack('<6Q',reader.read(ptr+0x60,48)):
                item['nodes'].append(reader.pointer(node+0x30) if node else 0)
            if segment:
                sem=checked_array(reader.read(segment+0x80,40))
                item['semaphores']=dict(array=sem,items=[])
                for slot in range(min(sem['size'],16)):
                    sid,unknown,actor=struct.unpack('<IIQ',reader.read(sem['data']+slot*16,16))
                    light=dict(id=sid,actor=actor)
                    if actor:
                        light['type']=reader.constant_type(actor)
                        light['placement']=decode_placement(reader.read(actor+0x28,32))
                        if light['type']==7:
                            rule=reader.pointer(actor+0x100);light['rule']=rule
                            if rule:
                                light['rule_type']=reader.constant_type(rule)
                                if light['rule_type']==0x2000:
                                    light['state']=struct.unpack('<I',reader.read(rule+0x70,4))[0]
                                    light['time_remaining']=struct.unpack('<f',reader.read(rule+0xb8,4))[0]
                    item['semaphores']['items'].append(light)
            items.append(item)
            if len(items)>=12:break
        return dict(array=arr,items=items,complete=False)
    attempt('prefabs',prefabs)
    result['roots_unchanged']=all(reader.pointer(reader.base+bindings[name]['value'])==value for name,value in roots.items())
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--pid',required=True,type=int)
    args=parser.parse_args()
    if args.pid<=0:parser.error('Positive PID required')
    profile=json.loads((AUDIT/'static-profile-161.json').read_text())
    reader=Reader(args.pid)
    try:
        result=dict(schema=1,pid=args.pid,read_only=True,production_ready=False,native_layouts_verified=False,
            source_layout='public 1.60 hypothesis; NOT verified 1.61',game_sha256=profile['game_sha256'],
            profile_sha256=hashlib.sha256((AUDIT/'static-profile-161.json').read_bytes()).hexdigest(),
            module_base=reader.base,snapshot=sample(reader,profile['bindings']))
        result['bytes_read']=reader.total
    finally:reader.close()
    path=AUDIT/f'layout-{args.pid}-{time.time_ns()}.json'
    path.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    print(path);print(json.dumps(result,indent=2,allow_nan=False))


if __name__=='__main__':main()
