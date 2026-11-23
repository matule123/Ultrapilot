"""Profile real archived Engine + AP assembly copies; originals remain read-only."""
import cProfile
import json
from pathlib import Path
import pstats
import shutil
import time
from core.steering_replay import complete_incident_assembly, _payload_hash
from tools.analyze_nov2_capture import APP, OUT

def main():
    import argparse,hashlib
    parser=argparse.ArgumentParser();parser.add_argument('--label',default='after')
    label=parser.parse_args().label
    incident='55bfc3027cad4dfd90fd37d7a4164c84-15672'
    directory=OUT/('exact-assembly-'+label);directory.mkdir(exist_ok=False)
    source=APP/'route-diagnostics'
    for path in (source/'archive'/('incident-'+incident)).iterdir():
        if path.is_file():shutil.copyfile(path,directory/path.name)
    shutil.copyfile(source/('ap-inputs-'+incident+'.json'),directory/('ap-inputs-'+incident+'.json'))
    profiler=cProfile.Profile();start=time.perf_counter();cpu=time.process_time()
    profiler.enable();path=complete_incident_assembly(directory,incident);profiler.disable()
    result=dict(operation='complete_incident_assembly',wall_s=time.perf_counter()-start,
        process_cpu_s=time.process_time()-cpu,profile_instrumented=True,result_path=path,
        historical_worker_phase_proven=False)
    profiler.dump_stats(str(OUT/('exact-assembly-'+label+'.prof')))
    with (OUT/('exact-assembly-'+label+'.txt')).open('w') as stream:
        pstats.Stats(profiler,stream=stream).sort_stats('cumulative').print_stats(25)
    if path:
        # The production operation returns only AFTER its full inspector has
        # succeeded. Do not add another full expansion outside the profile.
        value=json.loads(Path(path).read_bytes())
        hashes=(value['integrity']['payload_sha256']==_payload_hash(value) and all(
            hashlib.sha256((directory/r['name']).read_bytes()).hexdigest()==r['sha256'] for r in value['files']))
        result.update(integrity_valid=hashes,complete=value.get('complete'),
            component_failures=value.get('component_completeness'),full_readback_inside_operation=True)
    (OUT/('exact-assembly-'+label+'.json')).write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
