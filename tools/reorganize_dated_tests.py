"""One-shot mechanical test-layout migration; no scenario removal or merging."""
import ast
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
GROUPS={
 'signals': '''oct4_signal_lifecycle oct7_coast_and_signal_scope oct8_signal_approach_consistency oct8_signal_coverage oct8_stop_lifecycle oct10_native_signal_direction oct10_signal_approach oct10_signal_timing oct11_red_approach oct11_stationary_stop_comparison oct11_stop_geometry_audit oct11_terminal_approach oct13_stop_reference oct16_green_restart oct17_signal_completion''',
 'traffic': '''oct5_traffic_approach oct9_traffic_control_contract oct10_traffic_availability oct13_acc_anticipation oct13_acc_departure oct14_roundabout_incident oct15_crossing_dev_hud oct16_brake_owner_handoff oct16_joint_traffic_regressions oct16_native_owner_contract oct17_following_hold_signals oct29_moving_transition''',
 'lifecycle': '''oct3_longitudinal_activation_races oct6_joint_stop_flow oct7_command_observation_pairing oct9_packet_refresh oct10_reactivation_traffic oct11_destination_flow oct11_joint_regressions oct12_joint_lifecycle oct12_stop_and_indicators oct13_followup oct13_plugin_lifecycle oct14_completion oct14_followup oct14_stop_completion oct15_refresh_protocol oct15_traffic_refresh oct17_joint_lifecycle oct17_systemic_longitudinal oct18_joint_handoffs''',
 'sdk': '''oct14_native_probe oct22_sdk161_probe oct22_sdk161_static_profile oct24_sdk161_candidate oct24_sdk161_runtime''',
 'diagnostics': '''oct17_evidence_quota oct24_incident_packaging oct25_diagnostic_window oct25_exact_record_codec oct25_export_overhead oct25_full_pedal_window oct25_incident_assembly_failures oct25_incident_assembly oct25_incident_capacity oct25_populated_capture oct26_approved_diagnostic_budget oct26_combined_deferred_pedals oct26_daemon_incident_export oct26_diagnostic_tail_and_contention oct26_export_service_crash oct26_qualification_baseline_scope oct26_stop_episode_capture oct29_capture_failures oct29_late_assembly''',
}
NAMES={
 'oct13_followup':'acc_departure_reactivation',
 'oct14_followup':'traffic_hold_followup',
 'oct14_completion':'longitudinal_completion',
 'oct14_native_probe':'native_stop_boundary_probe',
 'oct22_sdk161_probe':'sdk161_probe_tools',
 'oct24_sdk161_candidate':'sdk161_read_candidate',
 'oct24_sdk161_runtime':'sdk161_runtime_bundle',
 'oct17_joint_lifecycle':'joint_signal_owner_lifecycle',
 'oct12_joint_lifecycle':'joint_reactivation_lifecycle',
}

def main():
    mapping={}
    for group,words in GROUPS.items():
        for word in words.split():
            suffix=NAMES.get(word,word.split('_',1)[1])
            mapping['tests/test_'+word+'.py']='tests/'+group+'/test_'+suffix+'.py'
    found={p.relative_to(ROOT).as_posix() for p in (ROOT/'tests').glob('test_oct*.py')}
    assert found==set(mapping),(found-set(mapping),set(mapping)-found)
    assert len(set(mapping.values()))==len(mapping)
    assert all(not (ROOT/dst).exists() for dst in mapping.values())
    modules={src[:-3].replace('/','.'):dst[:-3].replace('/','.') for src,dst in mapping.items()}
    sources={}
    for name in subprocess.check_output(['rg','--files','-g','*.py','tests','tools'],cwd=ROOT,text=True).splitlines():
        path=ROOT/name
        if path.resolve()==Path(__file__).resolve():continue
        raw=path.read_bytes();text=raw.decode('utf-8')
        updated=text
        # Fully qualified imports, monkeypatch targets and pytest node paths.
        for src,dst in sorted(modules.items(),key=lambda x:-len(x[0])):
            updated=updated.replace(src,dst)
        for src,dst in mapping.items():
            updated=updated.replace(src,dst)
        for src,dst in modules.items():
            updated=updated.replace('from tests import '+src.rsplit('.',1)[1],
                'from '+dst.rsplit('.',1)[0]+' import '+dst.rsplit('.',1)[1])
        rel=path.relative_to(ROOT).as_posix()
        if rel in mapping:
            updated=updated.replace('Path(__file__).resolve().parents[1]', 'Path(__file__).resolve().parents[2]')
            updated=updated.replace("Path(__file__).parent/'fixtures", "Path(__file__).parent.parent/'fixtures")
            updated=updated.replace('Path(__file__).parent / "fixtures', 'Path(__file__).parent.parent / "fixtures')
        if updated!=text:ast.parse(updated);sources[path]=updated.encode('utf-8')
    # All file targets are explicit, unique, confined to tests and absent.
    for src,dst in mapping.items():
        assert (ROOT/src).resolve().is_relative_to((ROOT/'tests').resolve())
        assert (ROOT/dst).resolve().is_relative_to((ROOT/'tests').resolve())
    for path,raw in sources.items():path.write_bytes(raw)
    for src,dst in mapping.items():
        target=ROOT/dst;target.parent.mkdir(exist_ok=True)
        (ROOT/src).rename(target)
    (ROOT/'tests/layout-migration.json').write_text(json.dumps(mapping,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(moved=len(mapping),updated_python_files=len(sources)),indent=2))

if __name__=='__main__':main()
