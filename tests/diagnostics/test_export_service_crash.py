"""Kill only the export child of this test's Manager; no application processes."""
import multiprocessing as mp
import threading
import time
import pytest


def test_real_export_child_death_releases_service_and_never_attests_complete(tmp_path):
    import psutil
    import core.ipc.shared_state as transport
    if not hasattr(transport,'DiagnosticStateManager'):pytest.skip('Exact diagnostic candidate required')
    errors=[]
    with transport.DiagnosticStateManager(ctx=mp.get_context('spawn')) as manager:
        state=manager.dict();ticket=state.reserve_diagnostic_export()
        snapshot=dict(request=dict(schema=2,incident_id='a'*32+'-1',phase='seal',
            start_s=0.,end_s=100.,token='model-crash'),records=[dict(stream_id='model',
            sequence=i,at_s=float(i),value=dict(inputs=[dict(source='model',at_s=float(i),
                value=dict(raw=bytes(range(256))*160,index=i))],command=None)) for i in range(200)])
        def submit():
            try:state.diagnostic_export(ticket,'_autopilot_part_child',(str(tmp_path),snapshot))
            except Exception as error:errors.append(type(error).__name__)
        worker=threading.Thread(target=submit,daemon=True);worker.start()
        broker=psutil.Process(manager._process.pid);deadline=time.perf_counter()+10.
        children=[]
        while time.perf_counter()<deadline:
            children=broker.children(recursive=False)
            if children:break
            time.sleep(.01)
        assert len(children)==1,'Expected this test Manager to own exactly one exporter'
        child=children[0]
        assert child.ppid()==manager._process.pid
        child.terminate();child.wait(5.)
        worker.join(10.)
        assert not worker.is_alive() and errors
        assert not list(tmp_path.glob('incident-*.json'))
        assert not list(tmp_path.glob('ap-inputs-'+'a'*32+'-1.json'))
        next_ticket=state.reserve_diagnostic_export();assert next_ticket
        state.release_diagnostic_export(next_ticket)
