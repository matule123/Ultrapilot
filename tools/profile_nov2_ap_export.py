"""Profile exact stored AP rows offline; never runs from a control tick."""
import cProfile
import json
import time
from pathlib import Path
from core.steering_replay import inspect_replay, export_autopilot_part
from tools.analyze_nov2_capture import APP, OUT

def main():
    original=APP/'route-diagnostics/ap-inputs-55bfc3027cad4dfd90fd37d7a4164c84-15672.json'
    started=time.perf_counter()
    source=inspect_replay(original)
    assert source['integrity_valid']
    snapshot=source['replay']['diagnostic_consumed_inputs']
    from core.navigation.longitudinal_diagnostics import freeze_primitive_record
    snapshot=dict(snapshot,records=[dict(row,value=freeze_primitive_record(row['value']))
        for row in snapshot['records']])
    load=time.perf_counter()-started
    directory=OUT/'exact-ap-simple-profile';directory.mkdir(exist_ok=True)
    profile=cProfile.Profile()
    start=time.perf_counter();cpu=time.process_time()
    profile.enable()
    path=export_autopilot_part(directory,snapshot)
    profile.disable()
    elapsed=time.perf_counter()-start;cpu=time.process_time()-cpu
    profile.dump_stats(str(OUT/'exact-ap-simple-export.prof'))
    import pstats
    with (OUT/'exact-ap-simple-export-profile.txt').open('w') as stream:
        pstats.Stats(profile,stream=stream).sort_stats('cumulative').print_stats(35)
    result=dict(original=str(original),load_wall_s=load,export_wall_s=elapsed,
        export_process_cpu_s=cpu,bytes=Path(path).stat().st_size,records=len(snapshot['records']),
        profile_instrumented=True,historical_timeout_cause_proven=False)
    (OUT/'exact-ap-simple-export-profile.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))

if __name__=='__main__':main()
