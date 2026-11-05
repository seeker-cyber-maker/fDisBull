"""Read-only JSON-lines Z history projection over a supplied semantic snapshot.

This process reads an existing journal and never launches a guest or reconstructs
an attack from proximity. The chosen perspective filters history only; it does
not convert a globally diagnostic scene into a fair-play world view.
"""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from world_history import WorldHistory,HistoryBackend,canonical
from z_provider import SceneBackend

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--journal',type=Path,required=True)
    p.add_argument('--perspective',choices=['diagnostic','player'],default='diagnostic')
    p.add_argument('--after',type=int,default=0)
    a=p.parse_args()
    if not a.journal.is_file():raise ValueError('Existing history required; missing is not an empty history')
    snapshot=json.loads(a.snapshot.read_text())
    with WorldHistory(a.journal) as h:
        backend=HistoryBackend(SceneBackend(snapshot=snapshot),h,perspective=a.perspective,after=a.after)
        for line in sys.stdin:
            if len(line)>65536:raise ValueError('Request limit exceeded')
            try:
                q=json.loads(line)
                if q.get('op')=='observe':r=backend.observe()
                elif q.get('op')=='act':r=backend.act(q.get('action'))
                else:r={'complete':False,'error':'History endpoint supports passive observe only; game actions are refused'}
            except Exception as e:r={'complete':False,'error':str(e)}
            print(canonical(r),flush=True)

if __name__=='__main__':main()
