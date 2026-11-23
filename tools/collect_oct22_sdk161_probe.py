"""Read existing passive probe mapping; NEVER creates mappings or sends input."""
import argparse
import ctypes
import json
from pathlib import Path
import struct
import time
from ctypes import wintypes

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid',type=int,required=True)
    parser.add_argument('--seconds',type=int,default=10)
    args=parser.parse_args()
    if args.pid<=0 or not 1<=args.seconds<=60:parser.error('Positive PID and 1..60 seconds required')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenFileMappingW.argtypes=(wintypes.DWORD,wintypes.BOOL,wintypes.LPCWSTR);kernel.OpenFileMappingW.restype=wintypes.HANDLE
    kernel.MapViewOfFile.argtypes=(wintypes.HANDLE,wintypes.DWORD,wintypes.DWORD,wintypes.DWORD,ctypes.c_size_t);kernel.MapViewOfFile.restype=ctypes.c_void_p
    kernel.UnmapViewOfFile.argtypes=(ctypes.c_void_p,);kernel.CloseHandle.argtypes=(wintypes.HANDLE,)
    handle=kernel.OpenFileMappingW(4,False,f'Local\\UltraPilot161ReadOnlyProbe-{args.pid}')
    if not handle:raise RuntimeError('Passive probe is not running; no mapping was created')
    pointer=None;records=[]
    try:
        pointer=kernel.MapViewOfFile(handle,4,0,0,16392)
        if not pointer:raise ctypes.WinError(ctypes.get_last_error())
        until=time.monotonic()+args.seconds
        while time.monotonic()<until:
            first=ctypes.string_at(pointer,8);seq,size=struct.unpack('<II',first)
            if seq and seq%2==0 and 0<size<=16384:
                payload=ctypes.string_at(pointer+8,size)
                if ctypes.string_at(pointer,8)==first:
                    record=json.loads(payload)
                    if record['pid']!=args.pid or not record['read_only'] or record['production_ready']:
                        raise RuntimeError('Unexpected probe protocol')
                    records.append(record)
            time.sleep(.5)
    finally:
        if pointer:kernel.UnmapViewOfFile(pointer)
        kernel.CloseHandle(handle)
    output=ROOT/'docs/steering-audit/oct22-sdk161'/f'passive-{args.pid}-{time.time_ns()}.json'
    output.write_text(json.dumps(dict(records=records,controls_written=False,production_ready=False),indent=2),encoding='utf-8')
    print(output)
    print('Snapshots:',len(records),'(diagnostics only; native traffic/GPS layouts NOT certified)')


if __name__=='__main__':main()
