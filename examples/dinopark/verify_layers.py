#!/usr/bin/env python3
"""Compare an observed DinoPark branch with its fetch-only inverse from one checkpoint.

Requires user-owned game inputs and the layers backend. Output contains a private
byte-retaining database and machine checkpoints and must stay outside Git/packages.
"""
import argparse
import hashlib
import json
from pathlib import Path

from fdisbull.project import Project


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',required=True,type=Path)
    parser.add_argument('--game-dir',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    backend=args.executable.resolve(strict=True);game=args.game_dir.resolve(strict=True);out=args.output.resolve()
    if out==game or game in out.parents:
        raise ValueError('Evidence output must be outside the input game directory')
    binary=game/'DINOPARK.EXE'
    if hashlib.sha256(binary.read_bytes()).hexdigest()!='2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c':
        raise ValueError('This bounded replay requires the verified original DinoPark executable')
    def files():
        result=[]
        for path in sorted(game.rglob('*')):
            if path.is_symlink():raise ValueError('Game input must not contain symbolic links')
            if path.is_file():result.append({'path':path.relative_to(game).as_posix(),
                'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        return result
    original_files=files();out.mkdir(parents=True,exist_ok=False)
    def export(p,artifact,name):
        p.debug_export(artifact['artifact'],out/name)
        return json.loads((out/name).read_text()) if name.endswith('.json') else None
    with Project.create(out/'dinopark.fdb',binary,load_segment=0x1000) as p:
        p.analyze(start='1000:75bc',max_instructions=128)
        with p.debugger(backend,game) as d:
            if not d.rpc.capabilities.get('code_layers'):raise ValueError('A layers-capable backend is required')
            report={'backend_sha256':hashlib.sha256(backend.read_bytes()).hexdigest(),'run':d.run_id}
            report['intro']=d.run(guest_ms=35000,timeout_ms=10000,fast_forward=True)
            assert report['intro']['outcome']=='guest_time'
            report['screenshot']=d.screenshot('main-menu.png');export(p,report['screenshot'],'main-menu.png')
            bp=d.breakpoint('1000:75bc')
            assert d.run(timeout_ms=3000,fast_forward=True)['outcome']=='breakpoint'
            d.delete_breakpoint(bp['breakpoint_id'])
            entry=d.save_state('mouse-entry.sav')
            discovery=d.trace('discovery.json',count=128,timeout_ms=3000)
            events=export(p,discovery,'discovery.json')['events']
            def conditional(event):
                code=bytes.fromhex(event.get('execution_bytes',''))
                return bool(code) and (0x70<=code[0]<=0x7f or
                    len(code)>1 and code[0]==0x0f and 0x80<=code[1]<=0x8f)
            candidates=[e for e in events if e.get('project_segmented_address') and conditional(e)]
            assert candidates,'No observed Jcc in bounded mouse/caller trace'
            address=candidates[0]['project_segmented_address'];report['branch_address']=address
            d.load_state(entry['artifact'])
            bp=d.breakpoint(address,view='execute')
            assert d.run(timeout_ms=3000,fast_forward=True)['outcome']=='breakpoint'
            d.delete_breakpoint(bp['breakpoint_id']);state=d.save_state('before-branch.sav')
            original=d.code(address,length=8,view='ram')
            baseline=d.trace('baseline.json',count=8,timeout_ms=3000)
            before=export(p,baseline,'baseline.json')['events']
            d.load_state(state['artifact'])
            report['layer']=d.branch('invert observed DinoPark branch',address,mode='invert')
            changed=d.code(address,length=8)
            assert d.code(address,length=8,view='ram')['hex']==original['hex']
            alternate=d.trace('alternate.json',count=8,timeout_ms=3000)
            after=export(p,alternate,'alternate.json')['events']
            assert baseline['metadata']['complete'] and alternate['metadata']['complete']
            assert before[0]['project_address']==after[0]['project_address']
            assert before[0]['ram_bytes']==after[0]['ram_bytes']
            assert before[0]['execution_bytes']!=after[0]['execution_bytes']
            assert before[1]['address']!=after[1]['address'],'Observed successor did not change'
            report.update(original_view=original,execution_view=changed,baseline_first=before[:2],
                alternate_first=after[:2],baseline_trace=baseline,alternate_trace=alternate,
                native_state_exported=False,guest_code_ram_unchanged=True)
            d.load_state(state['artifact'])
            assert d.layers()['active']==[] and d.code(address,length=8)['hex']==original['hex']
            report.update(restore_original_view=True,result='pass')
        report['process_reaped']=d.rpc.process.poll() is not None
        assert report['process_reaped']
    assert files()==original_files,'Game input files changed during the experiment'
    report['game_files_unchanged']=len(original_files)
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'result':'pass','branch_address':address,'baseline':before[0]['instruction'],
        'alternate':after[0]['instruction'],'successor_changed':True,'underlying_ram_unchanged':True,
        'game_files_unchanged':len(original_files),'process_reaped':True}))


if __name__=='__main__':main()
