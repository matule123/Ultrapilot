"""Prepare an installed-base DIAGNOSTIC ONLY overlay; never installs or arms.

The workspace's unfinished driving changes are deliberately NOT its baseline.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import zipfile
import copy
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
APP=Path(r'C:\Users\PC\AppData\Local\Programs\UltraPilot')
BUILD='UP-DIAGNOSTIC-20261026-26'
OUT=ROOT/'docs/steering-audit/oct25-incident-assembly'


def sha(raw):return hashlib.sha256(raw).hexdigest()


def deferred_combined_source(source):
    """Only the observational combined hook: packed handoff and accepted cursor."""
    if 'expanded=False) if journal is not None and journal.enabled' in source:return source
    edits=[
        ("journal.snapshot(after_sequence=getattr(self,'_combined_pedal_cursor',0))",
         "journal.snapshot(after_sequence=getattr(self,'_combined_pedal_cursor',0),expanded=False)"),
        ("            if pedals is not None:\n                self._combined_pedal_cursor = pedals['last_sequence']\n",''),
        ('            diagnostic.offer(capture_diagnostic_application(',
         '            accepted = diagnostic.offer(capture_diagnostic_application('),
        ('                longitudinal=pedals))\n',
         "                longitudinal=pedals))\n            if accepted and pedals is not None:\n                self._combined_pedal_cursor = pedals['last_sequence']\n")]
    for old,new in edits:
        if source.count(old)!=1:raise ValueError('COMBINED_OBSERVER_ANCHOR: '+old)
        source=source.replace(old,new,1)
    return source


def verify_control_baseline(stage):
    class Strip(ast.NodeTransformer):
        def visit_Expr(self,node):
            if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id in (
                    'observe_engine_incident','diagnostic_consume','decorate_traffic_diagnostic',
                    'diagnostic_autopilot_begin','diagnostic_autopilot_end','diagnostic_autopilot_close'):
                return None
            return self.generic_visit(node)
        def visit_Try(self,node):
            # Only the observational _control_tick envelope is removable.
            if (not node.handlers and not node.orelse and len(node.finalbody)==1
                    and isinstance(node.finalbody[0],ast.Expr)
                    and isinstance(node.finalbody[0].value,ast.Call)
                    and isinstance(node.finalbody[0].value.func,ast.Name)
                    and node.finalbody[0].value.func.id=='diagnostic_autopilot_locals'):
                return [self.visit(n) for n in node.body]
            return self.generic_visit(node)
        def visit_ImportFrom(self,node):
            if node.module=='core.navigation.longitudinal_diagnostics' and all(
                    n.name=='diagnostic_consume' for n in node.names):return None
            return node
    checked=[]
    for name,excluded in (
            ('core/engine.py',{'__init__','stop','_start_significant_export_preflight',
                '_finish_automatic_longitudinal_incident','_finish_significant_longitudinal_event'}),
            ('core/longitudinal.py',set()),('plugins/autopilot/main.py',{'on_start'})):
        original_text=(APP/name).read_text(encoding='utf-8-sig')
        if name=='core/engine.py':original_text=deferred_combined_source(original_text)
        original=ast.parse(original_text)
        candidate=ast.parse((Path(stage)/name).read_text(encoding='utf-8-sig'))
        def functions(tree):
            nodes=list(tree.body)
            for node in tree.body:
                if isinstance(node,ast.ClassDef):nodes.extend(node.body)
            # Nested functions belong to their parent's complete AST. In
            # particular the preflight's local `check` is diagnostic-only.
            return {n.name:n for n in nodes if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        old,new=functions(original),functions(candidate)
        for function,node in old.items():
            if function in excluded:continue
            if function not in new:raise ValueError('CONTROL_FUNCTION_REMOVED: '+function)
            cleaned=Strip().visit(copy.deepcopy(new[function]))
            node=Strip().visit(copy.deepcopy(node))
            if ast.dump(node,include_attributes=False)!=ast.dump(cleaned,include_attributes=False):
                raise ValueError('CONTROL_AST_CHANGED: '+name+'::'+function)
            checked.append(name+'::'+function)
    return dict(installed_control_functions_ast_equal=len(checked),functions=checked,
        combined_observer_diff='Exact packed-snapshot/accepted-cursor transformation checked; all other AST unchanged',
        exclusions='Only diagnostic initialization/preflight/export and shutdown export wait; driving functions not excluded')


def engine_source(original):
    """Exact observational insertions on installed source, no driving diff."""
    source=deferred_combined_source(original.replace('\r\n','\n'))
    if 'observe_engine_incident, finish_engine_incident, decorate_traffic_diagnostic' in source:return source
    def insert(anchor,after):
        nonlocal source
        if source.count(anchor)!=1:raise ValueError('ENGINE_HOOK_ANCHOR: '+anchor[:80])
        source=source.replace(anchor,anchor+after,1)
    prefix=('from core.navigation.longitudinal_diagnostics import '
        'observe_engine_incident, finish_engine_incident, decorate_traffic_diagnostic\n')
    # Keep future imports legal, if the installed file later gains one.
    tree=ast.parse(source)
    first=next((n for n in tree.body if isinstance(n,ast.Import)),None)
    if first is None:raise ValueError('ENGINE_IMPORT_ANCHOR')
    lines=source.splitlines(True);lines.insert(first.lineno-1,prefix);source=''.join(lines)
    insert('        truck_telemetry = ((self.shared_state.get("telemetry", {}) or {})\n'
           '                           .get("truck", {}) or {})\n',
           "        observe_engine_incident(self, 'ego', truck_telemetry)\n")
    insert('        self.controller = Controller()\n',
        "        from core.navigation.longitudinal_diagnostics import PedalJournal\n"
        "        self.controller._pedal_journal = PedalJournal()\n"
        "        self.controller._pedal_journal.enabled = True\n")
    insert("        self.shared_state.update_batch({**presentation,'longitudinal_traffic':published})\n",
        "        observe_engine_incident(self, 'traffic', dict(packet=published, ego=truck,\n"
        "            capture=dict(session=capture.session,receiver_time_s=capture.observed_at,\n"
        "                moving=capture.moving,parked=capture.parked,stable=capture.stable,source=capture.source)))\n")
    anchor="        self.shared_state.update_batch({**presentation,'longitudinal_traffic':published})\n"
    source=source.replace(anchor,"        decorate_traffic_diagnostic(self,published)\n"+anchor)
    insert('        snapshot = self._signal_reader.read()\n',
        "        observe_engine_incident(self, 'signal_native', snapshot)\n")
    insert('        sequence = getattr(self, "_drive_boundary_sequence", 0) + 1\n',
        "        observe_engine_incident(self, 'drive_boundary',dict(action=action,ego=truck,reason=reason,\n"
        "            selector=selector,returned=returned,steering=steering,throttle=throttle,brake=brake))\n")
    anchor='            if rejection_reason:\n                logging.error("Hotkey N -> %s", msg)\n'
    if source.count(anchor)!=1:raise ValueError('HOTKEY_DIAGNOSTIC_HOOK')
    source=source.replace(anchor,
        "            observe_engine_incident(self,'activation',dict(source='hotkey',enabled=new_state,\n"
        "                pending_started=pending_started,reason=rejection_reason,request_id=request_id,\n"
        "                initialization=initialization,ego=locals().get('truck'),steering_packet=locals().get('packet')))\n"+anchor)
    insert('        self._first_pedal_started_at = time.monotonic() if desired else None\n',
        "        observe_engine_incident(self,'activation',dict(source='ui',enabled=desired,\n"
        "            pending_started=pending_started,reason=rejection_reason,request_id=seq,\n"
        "            initialization=initialization,ego=locals().get('truck')))\n")
    # Keep the pre-existing immediate automatic-disable pedal replay. Grouped
    # non-disable dossiers use the same writer from the significant-event hook;
    # a 10 s dossier tail must not suppress the original 100 ms safety export.
    for name in ('_finish_significant_longitudinal_event',):
        node=next(n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.FunctionDef) and n.name==name)
        lines=source.splitlines(True)
        lines.insert(node.body[0].lineno-1,
            '        if finish_engine_incident(self,journal,shutdown=shutdown):return\n')
        source=''.join(lines)
    # Existing preflight stays on the existing worker. Its old significant-event
    # quota is irrelevant to the new grouped diagnostic dossiers.
    source=source.replace('budget=significant_event_export_budget(directory)',
        "from core.steering_replay import incident_diagnostic_budget\n"
        "            budget=incident_diagnostic_budget(directory)\n"
        "            if hasattr(self,'shared_state'):\n"
        "                self.shared_state.set('diagnostic_capture_status',dict(budget,build='"+BUILD+"'))",1)
    begin=source.index("            if not budget['ready']:",source.index('def _start_significant_export_preflight'))
    end=source.index('        submitted=writer.submit(check)',begin)
    source=source[:begin]+("            logging.info('Temporary diagnostic build %s: capture_ready=%s, free_bytes=%s, archive_bytes=%s',\n"
        "                '"+BUILD+"',budget['ready'],budget['free_bytes'],budget['archive_bytes'])\n")+source[end:]
    tree=ast.parse(source)
    stop=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='stop')
    lines=source.splitlines(True)
    for i in range(stop.lineno-1,stop.end_lineno):
        lines[i]=lines[i].replace('writer.wait(5.)','writer.wait(30.)')
    source=''.join(lines)
    ast.parse(source)
    return source


def longitudinal_source(original):
    source=original.replace('\r\n','\n')
    if 'diagnostic_consume' in source:return source
    tree=ast.parse(source)
    read=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='read')
    target=next(n for n in read.body if isinstance(n,ast.If) and
        ast.unparse(n.test)=='diagnostic is not None')
    lines=source.splitlines(True)
    lines.insert(target.lineno-1,
        "    from core.navigation.longitudinal_diagnostics import diagnostic_consume\n"
        "    diagnostic_consume(state,source,dict(packet=value,reason=reason or coverage_reason,\n"
        "        read_started_at=read_started_at,read_returned_at=read_returned_at,\n"
        "        checked_at=checked_at,reread_count=reread_count),checked_at)\n")
    source=''.join(lines)
    anchor='    return CommandObservation(binding, value, truck, dict(\n'
    if source.count(anchor)!=1:raise ValueError('COMMAND_OBSERVATION_HOOK')
    source=source.replace(anchor,
        "    from core.navigation.longitudinal_diagnostics import diagnostic_consume\n"
        "    diagnostic_consume(state,'command_pair',dict(command=value,truck=truck,\n"
        "        initial_vehicle=initial,read_started_at=read_started,read_returned_at=command_read_at,\n"
        "        checked_at=checked_at,reread_count=int(retry)),checked_at)\n"+anchor)
    finalize=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='finalize')
    target=next(n for n in finalize.body if isinstance(n,ast.Assign) and
        any(isinstance(t,ast.Name) and t.id=='returned_at' for t in n.targets))
    lines=source.splitlines(True)
    lines.insert(target.end_lineno,
        "    from core.navigation.longitudinal_diagnostics import diagnostic_consume\n"
        "    diagnostic_consume(state,'ap_command',dict(packet=value),returned_at)\n")
    source=''.join(lines)
    ast.parse(source)
    return source


def autopilot_source(original):
    source=original.replace('\r\n','\n')
    if 'self._diagnostic_part_assembler = AutopilotIncidentParts(self)' in source:return source
    anchor='        self._steering_replay = SteeringReplayBuffer()\n'
    if source.count(anchor)!=1:raise ValueError('AUTOPILOT_REPLAY_HOOK')
    source=source.replace(anchor,anchor+
        "        if self._steering_replay._diagnostic_inputs is not None:\n"
        "            from core.navigation.longitudinal_diagnostics import AutopilotIncidentParts\n"
        "            self._diagnostic_part_assembler = AutopilotIncidentParts(self)\n"
        "            self.sdk.shared_state._diagnostic_consumer = self._diagnostic_part_assembler.consume\n")
    source=("from core.navigation.longitudinal_diagnostics import "
        "diagnostic_autopilot_begin, diagnostic_autopilot_end, diagnostic_autopilot_close, diagnostic_autopilot_locals\n")+source
    # The installed source has no __future__ statement; fail rather than moving one.
    if 'from __future__' in original:raise ValueError('AP_FUTURE_IMPORT_REQUIRES_EXPLICIT_HOOK')
    anchor='        self._longitudinal_truck = {}\n'
    if source.count(anchor)!=1:raise ValueError('AP_BEGIN_HOOK')
    source=source.replace(anchor,anchor+'        diagnostic_autopilot_begin(self)\n')
    tick=next(n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.FunctionDef) and n.name=='on_tick')
    final=next(n for n in tick.body if isinstance(n,ast.Try)).finalbody[0]
    lines=source.splitlines(True);lines.insert(final.lineno-1,'            diagnostic_autopilot_end(self)\n');source=''.join(lines)
    stop=next(n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.FunctionDef) and n.name=='on_stop')
    lines=source.splitlines(True);lines.insert(stop.end_lineno,'        diagnostic_autopilot_close(self)\n');source=''.join(lines)
    control=next(n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.FunctionDef) and n.name=='_control_tick')
    lines=source.splitlines(True);begin=control.body[0].lineno-1;end=control.end_lineno
    lines[begin:end]=['        try:\n']+['    '+s if s.strip() else s for s in lines[begin:end]]+[
        '        finally:\n','            diagnostic_autopilot_locals(self,locals())\n']
    source=''.join(lines)
    ast.parse(source)
    return source


def manager_source(original):
    source=original.replace('\r\n','\n')
    if 'class ControlDictionary(' not in source:
        local=(ROOT/'core/ipc/shared_state.py').read_text();tree=ast.parse(local)
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='ControlDictionary')
        methods='\n\n'.join('    '+ast.get_source_segment(local,n).replace('\n','\n    ')
            for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in (
                'reserve_diagnostic_export','release_diagnostic_export','diagnostic_export'))
        source+='\n\nimport threading\nfrom multiprocessing.managers import SyncManager, DictProxy\n'
        source+='\nclass DiagnosticDictionary(dict):\n    def __init__(self,*args,**kwargs):\n        super().__init__(*args,**kwargs)\n        self._diagnostic_export_lock=threading.Lock()\n        self._diagnostic_export_ticket=None\n\n'+methods+'\n'
        proxy=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='ControlDictionaryProxy')
        pm='\n\n'.join('    '+ast.get_source_segment(local,n).replace('\n','\n    ')
            for n in proxy.body if isinstance(n,ast.FunctionDef) and n.name in (
                'reserve_diagnostic_export','release_diagnostic_export','diagnostic_export'))
        source+="\nclass DiagnosticDictionaryProxy(DictProxy):\n    _exposed_=(*DictProxy._exposed_,'reserve_diagnostic_export','release_diagnostic_export','diagnostic_export')\n"+pm+'\n'
        source+="\nclass DiagnosticStateManager(SyncManager):pass\nDiagnosticStateManager.register('dict',DiagnosticDictionary,DiagnosticDictionaryProxy)\n"
        ast.parse(source);return source
    local=(ROOT/'core/ipc/shared_state.py').read_text()
    tree=ast.parse(local)
    methods=('reserve_diagnostic_export','release_diagnostic_export','diagnostic_export')
    for clsname in ('ControlDictionary','ControlDictionaryProxy'):
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==clsname)
        additions='\n\n'.join('    '+ast.get_source_segment(local,n).replace('\n','\n    ')
            for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in methods)
        anchor='class '+clsname+'('
        start=source.index(anchor);end=source.find('\nclass ',start+1)
        if end<0:raise ValueError('MANAGER_DIAGNOSTIC_ANCHOR')
        source=source[:end]+'\n'+additions+'\n\n'+source[end:]
    source=source.replace('        self._publication_lock = threading.RLock()\n',
        '        self._publication_lock = threading.RLock()\n        self._diagnostic_export_lock = threading.Lock()\n        self._diagnostic_export_ticket = None\n')
    source=source.replace("_exposed_ = (*DictProxy._exposed_, 'publish_longitudinal')",
        "_exposed_ = (*DictProxy._exposed_, 'publish_longitudinal', 'reserve_diagnostic_export', 'release_diagnostic_export', 'diagnostic_export')")
    ast.parse(source);return source


def prepare(output, *, simple_records=False, approved_budget=False):
    if approved_budget and not simple_records:raise ValueError('Approved budget belongs to the verified simple-record design')
    output=Path(output).resolve()
    if not output.is_relative_to(OUT) or output.exists():raise ValueError('Use NEW diagnostic output')
    receipt=(APP/'manual-deployment.json').read_bytes()
    deployed=json.loads(receipt.decode('utf-8-sig'))
    for row in deployed['files']:
        if sha(Path(row['target']).read_bytes())!=row['sha256'].lower():
            raise ValueError('INSTALLED_RECEIPT_DRIFT: '+row['target'])
    payload={name:(ROOT/name).read_bytes() for name in
        ('core/navigation/longitudinal_diagnostics.py','core/steering_replay.py',
         'core/navigation/evidence_diagnostics.py')}
    payload['core/engine.py']=engine_source((APP/'core/engine.py').read_text(encoding='utf-8-sig')).encode('utf-8')
    payload['core/longitudinal.py']=longitudinal_source((APP/'core/longitudinal.py').read_text(encoding='utf-8-sig')).encode('utf-8')
    payload['plugins/autopilot/main.py']=autopilot_source((APP/'plugins/autopilot/main.py').read_text(encoding='utf-8-sig')).encode('utf-8')
    payload['core/ipc/shared_state.py']=manager_source((APP/'core/ipc/shared_state.py').read_text(encoding='utf-8-sig')).encode('utf-8')
    boot=(APP/'bootloader.py').read_text(encoding='utf-8-sig')
    if boot.count('    manager = mp.Manager()')!=1:raise ValueError('DIAGNOSTIC_MANAGER_BOOT_ANCHOR')
    payload['bootloader.py']=boot.replace('    manager = mp.Manager()',
        '    from core.ipc.shared_state import DiagnosticStateManager\n    manager = DiagnosticStateManager()\n    manager.start()').encode('utf-8')
    payload['core/navigation/diagnostic_build_config.py']=(
        '"""Temporary observational build. No control authority."""\n'
        'ENABLED = True\nBUILD = '+repr(BUILD)+'\nSIMPLE_RECORDS = '+repr(simple_records)+
        '\nMEMORY_BUDGET_APPROVED = '+repr(approved_budget)+'\n').encode()
    output.mkdir(parents=True)
    # Full installed Python context for OFFLINE verification, not deployment.
    stage=output/'verification-runtime'
    for folder in ('core','plugins','sdk','ui'):
        for path in (APP/folder).rglob('*.py'):
            target=stage/path.relative_to(APP);target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(path.read_bytes())
    for name,raw in payload.items():
        target=stage/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    # Prevent pytest's source-path insertion AND spawned export children from
    # resolving namespace packages against the unrelated dirty workspace.
    # Verification-only package markers are never included in the runtime ZIP.
    for folder in [stage/name for name in ('core','plugins','sdk','ui')]+[
            p for p in stage.rglob('*') if p.is_dir() and any(p.glob('*.py'))]:
        marker=folder/'__init__.py'
        if not marker.exists():marker.write_text('# Isolated installed-base verification namespace.\n',encoding='utf-8')
    control=verify_control_baseline(stage)
    (output/'control-baseline-proof.json').write_text(json.dumps(control,indent=2),encoding='utf-8')
    manifest=dict(build=BUILD,kind='temporary_diagnostic_only',ready_for_drive=False,
        simple_records_proposal=bool(simple_records),memory_budget_approved=bool(approved_budget),
        approved_budget=(dict(approval_date='2026-10-26',authority='Explicit user reply in this chat; no deployment approval',
            engine_ring_mib=64,autopilot_ring_mib=32,engine_file_mib=32,
            child_rss_mib=1536,parent_additional_rss_mib=512,family_additional_rss_mib=2048)
            if approved_budget else None),
        deployment_authorized=False,base_receipt_sha256=sha(receipt),required_base=deployed['files'],
        files=[dict(path=n,sha256=sha(b),bytes=len(b),previous_sha256=sha((APP/n).read_bytes())
            if (APP/n).exists() else None) for n,b in payload.items()],
        installed_control_baseline=['core/engine.py','core/longitudinal.py','plugins/autopilot/main.py'],
        unchanged_files=['core/transmission_mode.py'],
        sdk161_changed=False,plugin_versions_changed=False,game_verified=False,
        open_gates=['Installed-base integration/output equivalence and overhead measurements',
            'Complete raw consumer evidence/activation-rejection coverage',
            'Worker shutdown and durable export failure recovery'])
    (output/'candidate-manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    # Do not create a deployable ZIP until these explicit readiness gates pass.
    print(json.dumps(dict(stage=str(stage),build=BUILD,files=len(payload),ready_for_drive=False),indent=2))


def qualify(output):
    output=Path(output).resolve()
    if not output.is_relative_to(OUT):raise ValueError('Qualification stays in workspace')
    manifest=json.loads((output/'candidate-manifest.json').read_text(encoding='utf-8'))
    stage=output/'verification-runtime'
    before={r['path']:sha((stage/r['path']).read_bytes()) for r in manifest['files']}
    if before!={r['path']:r['sha256'] for r in manifest['files']}:raise ValueError('CANDIDATE_DRIFT')
    proof=verify_control_baseline(stage)
    frozen=output/'qualification-frozen.json';log=output/'qualification-tests.log'
    if frozen.exists() or log.exists():raise ValueError('Preserve previous qualification')
    frozen.write_text(json.dumps(dict(build=BUILD,runtime_sha256=before,
        test_sha256={name:sha((ROOT/name).read_bytes()) for name in (
            'tests/diagnostics/test_diagnostic_window.py','tests/diagnostics/test_incident_assembly.py',
            'tests/diagnostics/test_incident_assembly_failures.py','tests/diagnostics/test_incident_capacity.py',
            'tests/diagnostics/test_populated_capture.py','tests/diagnostics/test_full_pedal_window.py')},
        control=proof),indent=2),encoding='utf-8')
    targets=['tests/diagnostics/test_diagnostic_window.py','tests/diagnostics/test_incident_assembly.py',
        'tests/diagnostics/test_incident_assembly_failures.py','tests/diagnostics/test_incident_capacity.py',
        'tests/diagnostics/test_populated_capture.py','tests/diagnostics/test_full_pedal_window.py','tests/signals/test_signal_lifecycle.py',
        'tests/test_longitudinal_evidence_diagnostics.py','tests/test_drive_engagement_safety.py',
        'tests/test_signal_stop_resume.py','tests/test_steering_replay.py','tests/test_real_evidence_diagnostics.py',
        'tests/test_acc_following.py','tests/test_continuous_service_stop.py',
        'tests/test_longitudinal_arbitration.py','tests/test_phase7_joint_validation.py',
        'tests/test_pedal_decision_history.py','tests/test_transmission_mode_activation.py',
        'tests/test_signal_clearance_source_contract.py','tests/test_scoped_signal_contract.py']
    legacy_tests=[]
    if manifest.get('simple_records_proposal'):
        # These tests assert the private storage graph of the rejected shared-
        # envelope proposal, not evidence values/control safety. Preserve them
        # unchanged, but qualify the chosen exact-record representation using
        # all semantic pedal tests plus its independent codec/immutability suite.
        file='tests/diagnostics/test_full_pedal_window.py'
        targets.remove(file)
        for name in ('test_full_window_retains_each_call_and_exact_binding_after_short_journal_eviction',
                'test_large_input_compression_never_runs_on_caller_thread',
                'test_gear_transition_event_silence_is_not_a_missing_periodic_frame',
                'test_pedal_detail_missing_binding_cannot_be_complete',
                'test_each_actually_consumed_packet_is_retained_between_periodic_samples'):
            targets.append(file+'::'+name)
        legacy_tests=[file+'::'+name for name in (
            'test_exact_repeated_packet_is_shared_but_each_read_keeps_original_time',
            'test_equal_ipc_copies_share_storage_despite_different_python_reference_counts',
            'test_nested_consumed_input_shares_exact_traffic_evidence_without_rewriting_rows')]
        targets+=['tests/diagnostics/test_exact_record_codec.py','tests/diagnostics/test_export_overhead.py',
            'tests/diagnostics/test_approved_diagnostic_budget.py','tests/diagnostics/test_combined_deferred_pedals.py',
            'tests/diagnostics/test_daemon_incident_export.py','tests/diagnostics/test_stop_episode_capture.py',
            'tests/diagnostics/test_export_service_crash.py','tests/diagnostics/test_diagnostic_tail_and_contention.py']
    (output/'test-selection.json').write_text(json.dumps(dict(targets=targets,
        preserved_legacy_storage_only_tests=legacy_tests,
        reason='The approved independent-record format does not implement the rejected nested-sharing storage graph',
        test_sha256={name:sha((ROOT/name).read_bytes()) for name in sorted({v.split('::')[0] for v in targets})}),indent=2))
    script=('import sys;sys.path.insert(0,'+repr(str(stage))+');'
        'import core.engine,plugins.autopilot.main,core.longitudinal,core.steering_replay,core.navigation.longitudinal_diagnostics;'
        'print("TESTED ENGINE",core.engine.__file__);'
        'print("TESTED AUTOPILOT",plugins.autopilot.main.__file__);'
        'import pytest;raise SystemExit(pytest.main('+repr(targets+['-q'])+'))')
    with log.open('x',encoding='utf-8') as stream:
        result=subprocess.run([sys.executable,'-c',script],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    after={name:sha((stage/name).read_bytes()) for name in before}
    record=dict(exit_code=result.returncode,unchanged=before==after,
        frozen_sha256=sha(frozen.read_bytes()),log_sha256=sha(log.read_bytes()),
        test_selection_sha256=sha((output/'test-selection.json').read_bytes()),
        runtime_sha256=after,whole_pytest_run=False,game_verified=False,deployed=False)
    (output/'qualification-result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(log.read_text(encoding='utf-8').splitlines()[-1])
    if result.returncode or before!=after:raise SystemExit(1)


def package(output):
    output=Path(output).resolve()
    if not output.is_relative_to(OUT):raise ValueError('Package stays in workspace')
    manifest=json.loads((output/'candidate-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('simple_records_proposal') and not manifest.get('memory_budget_approved'):
        raise ValueError('Proposal only: explicit memory-budget approval required; no ZIP')
    proof=json.loads((output/'qualification-result.json').read_text(encoding='utf-8'))
    if proof['exit_code']!=0 or not proof['unchanged']:raise ValueError('Qualification not passed')
    if sha((output/'qualification-tests.log').read_bytes())!=proof['log_sha256']:raise ValueError('Qualification log drift')
    if proof.get('test_selection_sha256')!=sha((output/'test-selection.json').read_bytes()):
        raise ValueError('Qualification test selection drift')
    selection=json.loads((output/'test-selection.json').read_text())
    if any(sha((ROOT/name).read_bytes())!=digest for name,digest in selection['test_sha256'].items()):
        raise ValueError('Qualification tests changed after freeze')
    benchmark_path=output/'traffic-qualification.json'
    assessment=json.loads(benchmark_path.read_text(encoding='utf-8'))
    if assessment['verdict']!='READY FOR CONTROLLED CAPTURE':
        raise ValueError('No further BLOCKED deliverable: resolve qualification before packaging')
    traffic_frozen=output/'traffic-runtime-frozen.json'
    traffic_identity=json.loads(traffic_frozen.read_text(encoding='utf-8'))
    if ({r['path']:r['sha256'] for r in traffic_identity['runtime']} !=
            {r['path']:r['sha256'] for r in manifest['files']}):
        raise ValueError('Traffic benchmark was run on another runtime')
    if traffic_identity['criteria_sha256']!=assessment['criteria_sha256']:
        raise ValueError('Traffic acceptance criteria changed')
    if manifest.get('memory_budget_approved'):
        approval=assessment.get('approved_budget') or {}
        if (approval.get('approved_budget')!=manifest.get('approved_budget') or
                traffic_identity.get('budget_approval_sha256')!=assessment.get('budget_approval_sha256')):
            raise ValueError('Approved budget provenance changed')
    if len(assessment['pairs'])!=2:raise ValueError('Full traffic benchmark missing')
    scope_hash=assessment.get('baseline_scope_approval_sha256')
    if scope_hash:
        scope_file=output/'baseline-scope-approval.json'
        if sha(scope_file.read_bytes())!=scope_hash:raise ValueError('Baseline scope approval drift')
    for pair in assessment['pairs']:
        a,b=pair['off'],pair['on']
        if (a['physical_writes_sha256']!=b['physical_writes_sha256'] or a['reads']!=b['reads'] or
                a['decisions_sha256']!=b['decisions_sha256'] or
                a['fault'] is not None or b['fault'] is not None or not b['post_warm_dossiers']):
            raise ValueError('Assembly output/read/export verification failed')
        if b['engine_ring']['capacity_drops'] or b['engine_ring']['capture_failures']:
            raise ValueError('Original capacity load still loses Engine evidence')
        for case in b['post_warm_dossiers']:
            if (case['range']['pre_s']<29.9 or case['range']['post_s']<10.
                    or not case['assembly_complete'] or case['incomplete']):
                raise ValueError('Required thirty-before/ten-after assembled capacity not met')
            detail=case.get('backend') or {}
            if (detail.get('incomplete',True) or detail.get('storage')!='full_incident_window'
                    or detail.get('missing_call_sequences') or detail.get('missing_decision_references')
                    or detail.get('missing_consumed_input_references')
                    or case.get('exact_physical_pedal_calls')!=detail.get('event_count')):
                raise ValueError('Exact full-window backend call proof missing')
    receipt=(APP/'manual-deployment.json').read_bytes()
    if sha(receipt)!=manifest['base_receipt_sha256']:raise ValueError('Installed receipt changed')
    for row in manifest['required_base']:
        if sha(Path(row['target']).read_bytes())!=row['sha256'].lower():raise ValueError('Installed file drift')
    stage=output/'verification-runtime';payload={}
    for row in manifest['files']:
        raw=(stage/row['path']).read_bytes()
        if sha(raw)!=row['sha256'] or sha(raw)!=proof['runtime_sha256'][row['path']]:raise ValueError('Candidate drift')
        payload[row['path']]=raw
    ready=assessment['verdict']=='READY FOR CONTROLLED CAPTURE'
    status='READY_FOR_CONTROLLED_CAPTURE_AWAITING_APPROVAL' if ready else 'BLOCKED_TIMING_QUALIFICATION'
    release=dict(manifest,ready_for_drive=False,ready_for_separate_collection_approval=ready,
        offline_capture_verified=True,whole_pytest_run=False,deployment_authorized=False,
        release_status=status,
        open_gates=[
            'No deployment approval or game verification',
            'Bounded stream loss, missing/failed/late parts and early shutdown remain explicitly incomplete; assembly is not a successful-drive verdict']+assessment['failures'],
        qualification_sha256=sha((output/'qualification-result.json').read_bytes()),
        assembly_benchmark_sha256=sha(benchmark_path.read_bytes()),
        traffic_runtime_frozen_sha256=sha(traffic_frozen.read_bytes()),
        source_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        working_tree_uncommitted=True,logical_retained_budget_mib=dict(engine_ring=64 if manifest.get('memory_budget_approved') else 32,
            pinned_pre=64 if manifest.get('memory_budget_approved') else 32,autopilot_consumer_ring=32,autopilot_pinned_pre=32,
            one_retry_window_upper=128 if manifest.get('memory_budget_approved') else 64,autopilot_frozen_window_upper=64,
            autopilot_next_case_pin=32,autopilot_predecessor_overlap=32,autopilot_retired_ring=32,
            one_internal_spawn_transfer=128),
        retention_note='Logical owner ceilings overlap shared exact row references; not additive measured RSS. Runtime host/broker/child peaks and unchanged approved gates are in traffic qualification. No hard OS reservation claim.',
        approved_memory_budget=manifest.get('approved_budget'),
        baseline_scope_approval=assessment.get('baseline_scope_approval'),
        baseline_scope_approval_sha256=scope_hash,
        disk_budget_mib=dict(active_dossiers_and_new_dense=128,closed_archive=512,failure_records=.0625),
        compression_transport_limits=dict(worker_threads_per_process=1,registered_windows=16,
            weak_work_references_per_window=32768,batch_records=32,maximum_original_record_bytes=524288,
            payload_queue='none; weak references to existing bounded ring entries',
            aggregate_event_receipt_bytes=4194304),
        old_candidates_superseded=True)
    new=output/('ultrapilot-diagnostic-'+BUILD.removeprefix('UP-DIAGNOSTIC-')+'-candidate.zip')
    rollback=output/'rollback-installed-base.zip'
    payload['diagnostic-manifest.json']=json.dumps(release,indent=2).encode('utf-8')
    originals={r['path']:(APP/r['path']).read_bytes() for r in manifest['files'] if (APP/r['path']).exists()}
    originals['manual-deployment.json']=receipt
    for archive_name,values in ((new,payload),(rollback,originals)):
        with zipfile.ZipFile(archive_name,'x',zipfile.ZIP_DEFLATED) as archive:
            for name,raw in values.items():archive.writestr(name,raw)
        with zipfile.ZipFile(archive_name) as archive:
            for name,raw in values.items():
                if sha(archive.read(name))!=sha(raw):raise ValueError('Archive readback')
    result=dict(candidate=str(new),candidate_sha256=sha(new.read_bytes()),
        rollback=str(rollback),rollback_sha256=sha(rollback.read_bytes()),
        new_files_without_original=[r['path'] for r in manifest['files'] if r['previous_sha256'] is None],
        runtime_files=len(manifest['files']),deployed=False,game_verified=False,
        ready_for_separate_collection_approval=ready,whole_pytest_run=False,
        release_status=status)
    (output/'release-receipt.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (output/'release-manifest.json').write_bytes(payload['diagnostic-manifest.json'])
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--simple-records',action='store_true',help='Use the independently verified existing lossless format')
    p.add_argument('--approved-budget',action='store_true',help='Record the explicit 26 October user approval; never authorizes deployment')
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--output',type=Path);group.add_argument('--status',type=Path);group.add_argument('--inspect',type=Path)
    group.add_argument('--qualify',type=Path);group.add_argument('--package',type=Path)
    args=p.parse_args()
    if args.qualify:qualify(args.qualify)
    elif args.package:package(args.package)
    elif args.status:
        from core.steering_replay import incident_diagnostic_budget
        print(json.dumps(incident_diagnostic_budget(args.status),indent=2))
    elif args.inspect:
        from core.steering_replay import inspect_incident
        result=inspect_incident(args.inspect)
        print(json.dumps({k:v for k,v in result.items() if k not in ('replay','dossier')},indent=2))
        if not result['integrity_valid']:raise SystemExit(2)
    else:prepare(args.output,simple_records=args.simple_records,approved_budget=args.approved_budget)
