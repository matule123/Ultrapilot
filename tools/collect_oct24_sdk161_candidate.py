"""Read isolated or standard buffers through real application decoders.

Does not create mappings, launch apps, import Engine or write controls.
Legacy camera/route buffers are explicitly untimed observations, not authority.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.sdk.existing_mapping import ExistingMapping
from core.sdk.traffic_snapshot import TrafficReader,LAYOUT as TRAFFIC_LAYOUT
from core.sdk.signal_snapshot import SignalReader,SCOPED_LAYOUT

AUDIT=ROOT/'docs/steering-audit/oct22-sdk161'


def probe_read(mapping,pid):
    header=mapping[:8];seq,size=struct.unpack('<II',header)
    if not seq or seq%2 or not 0<size<=16384:raise ValueError('Probe snapshot unavailable')
    raw=mapping[8:8+size]
    if mapping[:8]!=header:raise ValueError('Torn probe snapshot')
    result=json.loads(raw)
    if result['pid']!=pid or not result['read_only'] or result['production_ready']:raise ValueError('Unexpected probe identity')
    return result


def camera_decode(raw):
    row=struct.unpack('<4f2h27f',raw)
    finite=all(math.isfinite(v) for v in row)
    return dict(fov=row[0],world=[row[1]+row[4]*512,row[2],row[3]+row[5]*512],
        quaternion=list(row[6:10]),truck_world=list(row[26:29]),
        finite=finite,fov_plausible=finite and 1<row[0]<180,
        producer_timestamp_available=False,control_authority=False)


def route_decode(raw):
    rows=[dict(uid=format(uid&0xffffffffffffffff,'x'),remaining_m=distance,remaining_s=seconds)
        for uid,distance,seconds in struct.iter_unpack('<qff',raw) if uid]
    uid_bytes=b''.join(struct.pack('<Q',int(row['uid'],16)) for row in rows)
    return dict(count=len(rows),first=rows[:6],last=rows[-6:],
        uid_sequence_sha256=hashlib.sha256(uid_bytes).hexdigest(),sha256=hashlib.sha256(raw).hexdigest(),
        metrics_valid=all(math.isfinite(r['remaining_m']) and r['remaining_m']>=0
            and math.isfinite(r['remaining_s']) and r['remaining_s']>=0 for r in rows),
        producer_timestamp_available=False,control_authority=False)


def summarize_traffic(result):
    if result is None:return dict(valid=False,reason='candidate mapping unavailable')
    compact={k:v for k,v in result.items() if not isinstance(v,(bytes,bytearray))}
    if 'moving' in result:
        rows=struct.iter_unpack('<12f2h2b30f',result['moving'])
        compact['moving_sample']=[dict(id=r[13],world=list(r[:3]),speed_mps=r[10],
            acceleration=r[11],dimensions=list(r[7:10]),trailers=r[12]) for r in rows if r[13]][:8]
        compact['parked_nonzero_records']=sum(1 for r in struct.iter_unpack('<10fhb',result['parked']) if r[10])
    return compact


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--pid',required=True,type=int)
    parser.add_argument('--standard',action='store_true',help='Read deployed standard mappings, not the isolated candidate')
    parser.add_argument('--seconds',default=6,type=int);args=parser.parse_args()
    if args.pid<=0 or not 1<=args.seconds<=30:parser.error('Positive PID and 1..30 seconds required')
    mappings=[]
    def open_read(name,size):
        mapping=ExistingMapping(name,size);mappings.append(mapping);return mapping
    records=[]
    try:
        basic=open_read(f'Local\\UltraPilot161ReadOnlyProbe-{args.pid}',16392)
        traffic_name='UltraPilotTrafficV1' if args.standard else 'UltraPilot161CandidateTrafficV1'
        signal_name='UltraPilotSemaphoreV3' if args.standard else 'UltraPilot161CandidateSemaphoreV3'
        legacy_prefix='ETS2LA' if args.standard else 'UltraPilot161CandidateETS2LA'
        traffic=TrafficReader();traffic.buffer=open_read('Local\\'+traffic_name,TRAFFIC_LAYOUT.size)
        signal=SignalReader();signal.mapping_size=SCOPED_LAYOUT.size
        signal.buffer=open_read('Local\\'+signal_name,SCOPED_LAYOUT.size)
        camera=open_read('Local\\'+legacy_prefix+'CameraProps',128)
        route=open_read('Local\\'+legacy_prefix+'Route',96000)
        until=time.monotonic()+args.seconds
        while time.monotonic()<until:
            records.append(dict(read_at=time.monotonic(),probe=probe_read(basic,args.pid),
                traffic=summarize_traffic(traffic.read()),signal=signal.read(),
                camera_untimed=camera_decode(camera[:128]),route_untimed=route_decode(route[:96000])))
            time.sleep(.5)
    finally:
        for mapping in mappings:mapping.close()
    label='runtime-a-live' if args.standard else 'candidate-e-live'
    output=AUDIT/f'{label}-{args.pid}-{time.time_ns()}.json'
    output.write_text(json.dumps(dict(schema=1,pid=args.pid,read_only=True,controls_written=False,
        production_ready=False,standard_mappings=args.standard,records=records),indent=2,allow_nan=False),encoding='utf-8')
    print(output)
    print(json.dumps(dict(samples=len(records),probe_frames=[records[0]['probe']['frames'],records[-1]['probe']['frames']],
        paused_samples=sum(r['probe']['paused'] for r in records),
        traffic_valid=sum(r['traffic']['valid'] for r in records),
        traffic_reasons=sorted({r['traffic'].get('reason','') for r in records}),
        signal_valid=sum(r['signal'].get('valid',False) for r in records),
        signal_reasons=sorted({r['signal'].get('reason','') for r in records}),
        route_counts=sorted({r['route_untimed']['count'] for r in records}),
        cameras_plausible=all(r['camera_untimed']['fov_plausible'] for r in records)),indent=2))


if __name__=='__main__':main()
