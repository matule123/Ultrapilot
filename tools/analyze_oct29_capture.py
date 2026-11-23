"""Read-only incident analysis; writes no runtime files."""
import json
from collections import Counter
from pathlib import Path
from core.steering_replay import inspect_replay

ROOT = Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics')
def emit(label, value):
    print(label, json.dumps(value, default=lambda x: '<bytes:%d>' % len(x) if isinstance(x, bytes) else str(x), ensure_ascii=True)[:1800])

def main():
    result = inspect_replay(ROOT / 'steering-replay-20261029T130620.051281Z-diagnostic_incident.json')
    incident = result['replay']['longitudinal']['diagnostic_incident']
    rows = incident['records']
    emit('KINDS', Counter(r['kind'] for r in rows))
    for row in rows:
        if 22771.60<row['at_s']<22771.79 and row['kind'] in ('consumer_traffic','consumer_acc','pedal_binding','consumed_decision'):
            v=row['value'];p=v.get('packet') or {}
            if p:
                emit('EXACT_PACKET',dict(kind=row['kind'],at=row['at_s'],reason=v.get('reason'),**{k:p.get(k) for k in ('valid','computed_at','observation_timestamp','expires_at','following_target_id','following_kind','following_status','motion_constraint','moving_target_ids','observed_motion_ids','following')}))
            elif v.get('selected'):
                emit('EXACT_DECISION',dict(at=row['at_s'],selected=v['selected'],inputs_keys=list(v.get('inputs') or {}),refs=v.get('consumed_input_references')))
    last = None
    for row in rows:
        v = row['value']
        if row['kind'] == 'output_summary' and 22755 < row['at_s'] < 22773:
            keys = ('selected_source','reason','acc_target_id','acc_status','traffic_target_id','traffic_target_status','hold_phase','hold_reason','pedal_mode','motion_constraint')
            signature = tuple(str(v.get(k)) for k in keys if k!='motion_constraint')
            if signature != last:
                emit('TRANSITION',dict(at=row['at_s'], sequence=row['sequence'], **{k:v.get(k) for k in keys if k!='motion_constraint'},speed=v.get('speed_mps'),throttle=v.get('throttle'),brake=v.get('brake')))
                last=signature
    for kind in sorted(set(r['kind'] for r in rows)-{'output_summary'}):
        matches=[r for r in rows if r['kind']==kind and 22771.3<r['at_s']<22771.9]
        for row in matches[-2:]:
            v=row['value']
            emit('FAULT_'+kind,dict(at=row['at_s'],sequence=row['sequence'],keys=list(v) if isinstance(v,dict) else str(type(v)),value=v if kind in ('consumer_traffic','consumer_acc','consumed_decision','backend_call') else None))
    ap = inspect_replay(ROOT / 'ap-inputs-d8f8382277da40c398b28c5fcf315a11-14102.json')
    emit('AP_INTEGRITY',{k:v for k,v in ap.items() if k!='replay'})
    data=ap.get('replay',{}).get('diagnostic_consumed_inputs',{})
    emit('AP_META',{k:v for k,v in data.items() if k not in ('records','subevents')})
    emit('AP_KINDS',Counter(r.get('kind') for r in data.get('records',[])))
    for row in data.get('records',[])[-1:]:emit('AP_LAST_KEYS',dict(at=row.get('at_s'),keys=list(row.get('value',{}))))

if __name__=='__main__':main()
