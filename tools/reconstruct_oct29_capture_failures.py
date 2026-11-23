"""Exhaust the same session's earlier original exports; no invented causes."""
import json
from pathlib import Path
from core.steering_replay import inspect_replay
from core.navigation.longitudinal_diagnostics import _decision_summary, _DecisionHistory


def main():
    root=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot\route-diagnostics')
    results=[]
    for path in sorted(root.glob('*20261029*.json')):
        if path.name.startswith('steering-timing'):continue
        checked=inspect_replay(path)
        if not checked['integrity_valid']:
            results.append(dict(name=path.name,valid=False));continue
        block=checked['replay'].get('longitudinal') or {}
        rows=(block.get('diagnostic_incident') or {}).get('records') or []
        history=_DecisionHistory();errors=[]
        for row in rows:
            if row['kind'] not in ('consumed_decision','pedal_binding'):continue
            try:
                small,identity=_decision_summary(row['value']);count=history.failures
                history.observe(row['at_s'],small,identity)
                if history.failures!=count:errors.append(dict(sequence=row['sequence'],at_s=row['at_s'],error='budget_or_incomplete'))
            except Exception as e:errors.append(dict(sequence=row['sequence'],at_s=row['at_s'],error=type(e).__name__,detail=str(e)))
        source=checked['replay'].get('diagnostic_consumed_inputs') or {}
        results.append(dict(name=path.name,valid=True,created_at=checked['replay']['created_at'],
            history_count=(block.get('decision_history') or {}).get('capture_failures'),
            window_count=(block.get('diagnostic_incident') or {}).get('capture_failures'),
            exact_source_rows=len(rows),reconstructed_errors=errors,
            ap_count=source.get('capture_failures'),ap_record_failures=[
                dict(at_s=r['at_s'],count=r['value'].get('capture_failures'))
                for r in source.get('records',[]) if r['value'].get('capture_failures')]))
    out=Path(__file__).resolve().parents[1]/'docs/steering-audit/oct29-transition/session-failure-audit.json'
    out.write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2))


if __name__=='__main__':main()
