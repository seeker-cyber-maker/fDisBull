#!/usr/bin/env python3
"""Check sanitized D004 receipts and run the authored scene suite.

This rechecks recorded assertions and reports source-hash comparisons. It does NOT execute
Syndicate, restore a guest, or reproduce the original native observations.
Use --require-historical-sources only with the exact D004 scene snapshot.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene-root', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, default=Path(__file__).resolve().parent.parent/'evidence')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-historical-sources', action='store_true',
                        help='Require current scene files to equal historical D004 native-tested sources')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new output directory; retained receipts are never overwritten.')
    args.output.mkdir(parents=True)
    count = 0

    def require(condition: bool, label: str) -> None:
        nonlocal count
        count += 1
        if not condition:
            raise ValueError(label)

    def read(name: str):
        return json.loads((args.evidence/name).read_text(encoding='utf-8'))

    try:
        roots = read('original-routes.json')['trials']
        for name in ('agent0-approach', 'agent1-approach'):
            t = roots[name]; r = t['result']
            require(r['complete'] and r['orders'] == 4 and r['observations'] == 68, name+' result')
            require(r['start_raw'] == [15488,10368,256] and r['approach_raw'] == [15488,9344,256], name+' exact endpoints')
            samples = [x for x in t['events'] if x['kind'] == 'progress']
            orders = [x for x in t['events'] if x['kind'] == 'order-produced']
            writes = [x for x in t['events'] if x['kind'] == 'diagnostic-input-write']
            require(len(orders) == r['orders'] and len(samples) == r['observations'], name+' event counts')
            require(len(writes) == r['writes'], name+' write count')
            allowed = {0x5e552,0x55390,0x60b22,0x60b3f,0x60b12,0x60b14,0x60b1a,0x60b1c}
            require(all(x['preferred'] in allowed for x in writes), name+' declared diagnostic input fields only')
            require(all(x['health_raw'] == 16 for x in samples), name+' health preserved')
            for seg, order in zip(r['segments'],orders,strict=True):
                require(seg['complete'] and seg['stopped'] and seg['spatial_valid'] and seg['attachments_settled'], name+' segment completion')
                require(order['command'] == 3 and order['destination_raw'] == seg['destination_raw'], name+' original command')
                ss = [x for x in samples if x['segment'] == seg['index']]
                require(len(ss) == seg['samples'] and ss[-1]['position_raw'] == seg['destination_raw'] and ss[-1]['state_raw'] == 0, name+' exact stopped sample')
        t=roots['long-route-health-stop']; r=t['result']; samples=[x for x in t['events'] if x['kind']=='progress']
        require(not r['complete'] and r['orders']==23 and r['observations']==393, 'partial long route')
        require(sum(x['complete'] for x in r['segments'])==22, 'only 22 certified segments')
        require(r['error']=='Actor context/health changed' and samples[-1]['health_raw']==15 and samples[-1]['state_raw']==2,'actual stop reason')
        pc=read('player-controls.json')
        require(len(pc['agent0'])+len(pc['agent1'])==15,'15 final Player commands')
        for label in ('agent0','agent1'):
            rows=pc[label]; walks=[r for r in rows if r['command']=='walk route to car']
            require(len(walks)==2 and all(r['result']['status']=='success' for r in walks),'walk and duplicate '+label)
            require(walks[1]['revision_before']==walks[1]['revision_after'] and walks[1]['result']['effects']=='none-confirmed','duplicate no-op '+label)
            for r in rows:
                if r['result']['status']=='read':
                    require(r['revision_before']==r['revision_after'] and not r['result']['action_sent'],'passive read '+label)
            for command in ('board car','exit car'):
                require(any(r['command']==command and r['result']['status']=='success' for r in rows),command+' '+label)
        controls=pc['controls']
        require(controls[-1]['unchanged'] and 'held' in controls[-1]['error'].lower(),'held action not replayed')
        for row in controls:
            if row.get('result',{}).get('status')=='rejected':
                if row.get('case')=='stale token':
                    require(row['unchanged'] and row['result']['effects']=='none-confirmed','stale pre-input refusal')
                else:
                    require(row['revision_before']==row['revision_after'] and row['before_game_sha256']==row['after_game_sha256'],'pre-input refusal')
        doors=read('second-door.json')
        for label in ('forward','return'):
            r=doors[label]; ss=r['samples']; prev=r['start_raw']; motion=0
            require(len(ss)==33 and r['final_graph']['valid'],'door corridor samples '+label)
            for s in ss:
                p=s['position_raw'];
                require(p[0]==prev[0] and p[2]==prev[2] and s['health_raw']==16,'corridor domain '+label)
                step=abs(p[1]-prev[1]);require(step in (0,16),'corridor increment')
                motion += step!=0;prev=p
            require(motion==32 and prev==r['destination_raw'] and ss[-1]['status_raw']==0,'corridor arrival '+label)
        require(doors['forward']['destination_raw']==doors['return']['start_raw'],'continuous two-way endpoints')
        ob=read('obstruction.json')['observation']
        require(len(ob['samples'])==100 and ob['final_actor']['position_raw']!=ob['destination_raw'],'bounded obstruction nonarrival')
        require(ob['final_actor']['status_raw']==14 and ob['final_actor']['health_raw']==16,'obstruction state')
        wr=read('state14-writer.json')
        require(wr['pre_state']==0 and wr['after_store_state']==14 and wr['writer_preferred']=='0x30b2b','actual state writer')
        require(wr['AL_at_state_store']==192 and (192+wr['AL_addend'])%256==wr['final_direction_byte']==0,'partial-register arithmetic')
        require(wr['previous_direction_byte']==160 and wr['source_window']['live_matches'],'old stored direction differs from AL input')
        end=read('preservation-cleanup.json')
        require(end['restored']['baseline_game_equal'] and end['restored']['registers_equal'],'baseline restored')
        require(not end['remaining_breakpoints']['breakpoints'],'no remaining watches')
        require(end['originals']['count']==897 and not end['originals']['changed'] and not end['originals']['new'] and not end['originals']['missing'],'original files preserved')
        require(all(not p['final_exists'] for p in end['processes']) and not end['cleanup']['errors'],'owned cleanup')
        require(end['binding']['unexplained_code_object_differences']==0 and end['binding']['code_side_fixup_records']==9209,'final source mapping')
        src=read('source-identities.json')['files']
        source_comparison={}
        for name, identity in src.items():
            relative=Path(name).relative_to('scene'); data=(args.scene_root/relative).read_bytes()
            current_hash=hashlib.sha256(data).hexdigest()
            matches=len(data)==identity['bytes'] and current_hash==identity['sha256']
            source_comparison[str(relative)]={'historical_sha256':identity['sha256'],
                'current_sha256':current_hash,'matches_historical':matches}
            if args.require_historical_sources:
                require(matches,'historical source identity '+name)
        env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
        cp=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(args.scene_root/'tests'),'-v'],capture_output=True,text=True,env=env,timeout=90)
        (args.output/'authored-tests.log').write_text(cp.stdout+cp.stderr)
        match=re.search(r'^Ran (\d+) tests? in ',cp.stdout+cp.stderr,re.MULTILINE)
        require(cp.returncode==0 and match is not None and int(match.group(1))>0,'current authored tests')
        result={'status':'passed','recorded_assertions':count,'authored_tests':int(match.group(1)),
            'historical_authored_tests':140,'source_comparison':source_comparison,
            'historical_source_match_required':args.require_historical_sources,
            'all_current_sources_match_historical':all(x['matches_historical'] for x in source_comparison.values()),
            'native_execution':False,'scope':'Recorded receipt consistency and current authored tests; historical source hashes reported separately, no new original-game execution',
            'checker_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    except Exception as exc:
        result={'status':'failed','recorded_assertions_before_failure':count,'error':str(exc),'native_execution':False}
    (args.output/'receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    return 0 if result['status']=='passed' else 1

if __name__=='__main__':
    raise SystemExit(main())
