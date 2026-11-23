"""Paired receipt-matching entry/current flow; explicit synthetic SDK inputs.

Uses the existing full-pipeline benchmark and production-path fixtures. Measures
wall/thread CPU separately, preserving GC outliers. Not measured ETS2 cadence.
"""
import gc
import json
import logging
import os
from pathlib import Path
import time

from pytest import MonkeyPatch
from tools.benchmark_oct15_crossing_dev_hud import run, percentiles
from tests.traffic.test_following_hold_signals import entry_runtime


def main():
    logging.disable(logging.WARNING)
    output=Path(__file__).resolve().parents[1]/'docs/steering-audit/oct17-following-hold-signals/performance.json'
    if output.exists():raise ValueError('Do not overwrite measurement')
    rows=[]
    for repeat in range(3):
        # Alternate order to avoid assigning all cold/warm effects to one side.
        for baseline in ((True,False) if repeat%2==0 else (False,True)):
            with MonkeyPatch.context() as patches:
                patches.setenv('UP_OCT17_FOLLOW_BASELINE','1' if baseline else '0')
                entry_runtime.__wrapped__(patches)
                for mode in (0,3):
                    for enabled in (False,True):
                        row=run(enabled,mode,80)
                        rows.append(dict(repeat=repeat,baseline=baseline,mode=mode,dev_enabled=enabled,**row))
    paired={}
    for mode in (0,3):
        for enabled in (False,True):
            key=f'{mode}:{enabled}'
            selected=[r for r in rows if r['mode']==mode and r['dev_enabled']==enabled]
            assert len({r['control_output_sha256'] for r in selected})==1
            assert all(r['faults'] is None for r in selected)
            assert all(r['source_reads']==selected[0]['source_reads'] for r in selected)
            paired[key]=True
    result=dict(basis='actual Map/traffic/Policy/ACC/Autopilot/Engine/Controller, simulated SDK poses; 25 warmup ticks per run',
        limitation='In-process mocked IPC; does not establish native sampling, real scheduling or game consumption',
        output_and_read_counts_equal=paired,rows=rows)
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    for baseline in (True,False):
        subset=[r for r in rows if r['baseline']==baseline]
        print('entry' if baseline else 'candidate',json.dumps({k:{p:max(r[k][p] for r in subset)
            for p in ('p50','p95','p99','max')} for k in ('wall_ms','control_thread_cpu_ms')}))


if __name__=='__main__':main()
