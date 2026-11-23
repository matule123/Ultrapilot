"""Focused profiler reproduction; concurrent probe work is NOT isolated Engine CPU."""
from pathlib import Path
import cProfile,pstats,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'docs/steering-audit/oct29-transition/release01/verification-runtime'))


def main():
    from core.engine import UltraPilotEngine
    from tools.qualify_oct25_traffic_capture import run
    target=ROOT/'docs/steering-audit/oct29-reactivation/baseline-flush-profile'
    assert not target.exists()
    profile=cProfile.Profile();original=UltraPilotEngine._flush_controls
    def measured(self,*args,**kwargs):
        profile.enable()
        try:return original(self,*args,**kwargs)
        finally:profile.disable()
    UltraPilotEngine._flush_controls=measured
    try:
        run(mode=0,enabled=False,count=40,trailers=3,ticks=1400,directory=target,
            pace=0.,capacity_probe_mib=None,export_enabled=False,file_probe_mib=None,
            profile_export=False)
    finally:UltraPilotEngine._flush_controls=original
    profile.dump_stats(str(target.with_suffix('.pstats')))
    with target.with_suffix('.txt').open('x') as stream:
        stream.write('Profile intervals around flush may include concurrent probe/mock work; NOT isolated production Engine CPU, release timing or ETS2 evidence.\n')
        pstats.Stats(profile,stream=stream).strip_dirs().sort_stats('cumulative').print_stats(28)
    print(target.with_suffix('.txt').read_text())


if __name__=='__main__':main()
