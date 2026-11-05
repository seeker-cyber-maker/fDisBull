#!/usr/bin/env python3
"""Replay source-free checks; validate recorded witnesses, never rerun native DOS.

Requires fdisbull_player for authored Player tests. Original game
bytes and the native backend are not opened, downloaded or modified.
Historical native source identities are reported separately from current source
tests. Use --require-historical-sources only with the exact D003 scene snapshot.
"""
from __future__ import annotations
import argparse,hashlib,json,os,re,subprocess,sys
from pathlib import Path

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--scene-root',type=Path,required=True)
    ap.add_argument('--evidence',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--require-historical-sources',action='store_true',
                    help='Require the current scene files to equal the historical D003 native-tested source identities')
    args=ap.parse_args()
    if args.output.exists():raise ValueError('Output must be new')
    scene=args.scene_root.resolve(strict=True);e=args.evidence.resolve(strict=True)
    sys.path.insert(0,str(scene/'tools'))
    from interaction_contracts import door_person_candidate
    def load(name):return json.loads((e/name).read_text())
    assertions=0
    boundary=load('door-boundaries.json')['cases']
    assert len(boundary)==17
    for row in boundary:
        mutation=row['diagnostic_filter_mutation']
        model=door_person_candidate((16480,8416,256),row['position_raw'],excluded=mutation=='exclude',role_word=0 if mutation=='role' else 2)
        assert model['candidate']==row['returned_person0']==row['expected_match'],row['case']
        assertions+=1
    cycle=load('door-cycle.json')['events']
    assert [r['door_state'] for r in cycle]==[13,14,15,12];assertions+=1
    corridor=load('door-corridor.json')
    prior=corridor['start_raw']
    for label in ('door-walk-in','door-walk-out'):
        leg=corridor['legs'][label];rows=leg['samples'];assert len(rows)==33
        for index,row in enumerate(rows):
            now=row['position_raw'];expected_step=16 if index<32 else 0
            assert sum(abs(a-b) for a,b in zip(now,prior))==expected_step
            assert row['health']==16 and row['graph_valid'];prior=now;assertions+=1
        assert prior==leg['target_raw'] and rows[-1]['actor_state']==0
    native=load('player-native.json')
    assert native['commands_count']==15 and native['passed'];assertions+=1
    source_comparison={}
    for rel,digest in native['source_files'].items():
        current=hashlib.sha256((scene/rel).read_bytes()).hexdigest()
        source_comparison[rel]={'historical_sha256':digest,'current_sha256':current,
                                'matches_historical':current==digest}
        if args.require_historical_sources:
            assert current==digest,rel
    for row in native['commands']:
        if row['command'].startswith('examine') or row['index'] in (0,3):
            assert row['before_sha256']==row['after_sha256']
            assert row['before_revision']==row['after_revision'];assertions+=1
    orders=load('original-orders.json')['trials'];assert len(orders)==4
    for order in orders:
        assert order['complete']
        events=[x for x in order['events'] if x['kind']=='order-produced']
        assert len(events)==1 and events[0]['command']==(9 if order['verb']=='board' else 25)
        assertions+=1
    for row in load('door-player-passive.json')['observations']:
        assert row['before_sha256']==row['after_sha256'] and row['reply']['status']=='read';assertions+=1
    cleanup=load('preservation-cleanup.json')
    assert cleanup['restored_baseline'] and cleanup['restored_registers']
    assert cleanup['unchanged']==897 and not cleanup['new_files'] and not any(cleanup['final_owned_pids'].values())
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    process=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(scene/'tests'),'-v'],
                           cwd=scene,capture_output=True,text=True,timeout=60,env=env)
    text=process.stdout+process.stderr
    assert process.returncode==0,text
    match=re.search(r'^Ran (\d+) tests? in ',text,re.MULTILINE)
    assert match is not None,text[-1000:]
    tests=int(match.group(1));assert tests>0
    report={'status':'passed','authored_tests':tests,'historical_authored_tests':103,
            'recorded_witness_assertions':assertions,
            'source_comparison':source_comparison,
            'historical_source_match_required':args.require_historical_sources,
            'all_current_sources_match_historical':all(x['matches_historical'] for x in source_comparison.values()),
            'native_execution_this_checker':False,'network_or_installation':False,
            'native_scope':'Checks recorded original-game receipts, not a fresh reproduction',
            'python':sys.version,'output_log':text,
            'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('output_log','python')}))
    return 0
if __name__=='__main__':raise SystemExit(main())
