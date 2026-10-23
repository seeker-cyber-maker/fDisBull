"""Verify native state editing/reinjection and data watches with a user's DinoPark copy.

All byte-retaining databases/checkpoints stay in --output, which should be local.
No game data is bundled. The first available in-game save is used only as a fixture.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from fdisbull.project import Project


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',required=True,type=Path)
    parser.add_argument('--game-dir',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    executable=args.executable.resolve(strict=True);game=args.game_dir.resolve(strict=True)
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=False)
    binary=game/'DINOPARK.EXE'
    assert hashlib.sha256(binary.read_bytes()).hexdigest()=='2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c'
    database=output/'dinopark.fdb'
    script=json.loads(Path(__file__).with_name('routes').joinpath('load-dialog.json').read_text())
    with Project.create(database,binary) as project:
        project.analyze(start='1000:75bc',max_instructions=12)
        stored=project.debug_save_script('load-dialog.json',script)
    process=subprocess.Popen([sys.executable,'-m','fdisbull','serve','--project',str(database)],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    sequence=0
    with (output/'commands.jsonl').open('x',buffering=1) as log:
        def call(method,**params):
            nonlocal sequence
            sequence+=1
            request={'id':sequence,'method':method,'params':params}
            process.stdin.write(json.dumps(request)+'\n');process.stdin.flush()
            result=json.loads(process.stdout.readline());log.write(json.dumps({'request':request,'response':result})+'\n')
            assert result['ok'],result
            return result['result']

        def launch():
            return call('debug-launch',executable=str(executable),game_dir=str(game))['run']

        try:
            run=launch()
            routed=call('debug-script',run=run,script_id=stored['script_id'],timeout_ms=30000)
            assert routed['ok'],routed['error']
            dialog=routed['steps'][-1]['result']
            call('debug-stop',run=run)
            run=launch()
            call('debug-load-state',run=run,artifact=dialog['artifact'])
            loaded=call('debug-script',run=run,script={'format':'fdisbull-script-1','steps':[
                {'op':'run','guest_ms':100,'fast_forward':True},
                {'op':'screenshot','name':'restored-dialog.png'},
                {'op':'click','x':250,'y':73,'hold_ms':150},
                {'op':'run','guest_ms':3000,'fast_forward':True},
                {'op':'screenshot','name':'first-save.png'},
                {'op':'save-state','name':'parent.sav'},
                {'op':'memory','address':'0x471a6','length':8}]},timeout_ms=20000)
            assert loaded['ok'],loaded['error']
            parent=loaded['steps'][5]['result'];original=loaded['steps'][6]['result']['hex']
            # Data ranges require no stored instruction: arm the exact requested block.
            counter_watch=call('debug-breakpoint',run=run,address='0x471a6',access='w',length=8)
            assert len(counter_watch['breakpoints'])==8
            for entry in counter_watch['breakpoints']:
                call('debug-delete-breakpoint',run=run,breakpoint_id=entry['breakpoint_id'])
            call('debug-stop',run=run)
            before=original[:4]
            after=((int.from_bytes(bytes.fromhex(before),'little')+1)&65535).to_bytes(2,'little').hex()
            # This one-shot method restores/edits/recaptures in an isolated paused emulator.
            fork=call('debug-fork-state',artifact=parent['artifact'],executable=str(executable),game_dir=str(game),
                name='derived.sav',memory=[{'address':'0x471a6','expected_hex':before,'data_hex':after}])
            run=launch()
            injected=call('debug-load-state',run=run,artifact=fork['artifact'])
            modified=call('debug-memory',run=run,address='0x471a6',length=8)
            assert modified['hex']==after+original[4:]
            bp=call('debug-breakpoint',run=run,address='1000:75bc')
            hit=call('debug-run',run=run,timeout_ms=3000,fast_forward=True)
            assert hit['outcome']=='breakpoint'
            call('debug-delete-breakpoint',run=run,breakpoint_id=bp['breakpoint_id'])
            trace=call('debug-trace',run=run,name='modified-state-resume.json',count=64,timeout_ms=3000)
            assert trace['metadata']['complete']
            watches=[]
            # This is the observed game mouse-button sample, not an inferred parking/revenue counter.
            for access in ('w','r','rw'):
                watch=call('debug-breakpoint',run=run,address='0x4029a',access=access,length=2)
                stopped=call('debug-run',run=run,timeout_ms=3000,fast_forward=True)
                assert stopped['outcome']=='breakpoint'
                assert stopped['session']['stop_reason']['data_access']['access'] in access
                watches.append({'watch':watch,'stop':stopped})
                for entry in watch['breakpoints']:
                    call('debug-delete-breakpoint',run=run,breakpoint_id=entry['breakpoint_id'])
            call('debug-load-state',run=run,artifact=parent['artifact'])
            restored=call('debug-memory',run=run,address='0x471a6',length=8)
            assert restored['hex']==original
            info=call('debug-state-info',artifact=parent['artifact'])
            assert info['sha256']==parent['sha256']
            call('debug-stop',run=run)
        finally:
            process.stdin.close()
            assert process.wait(timeout=30)==0
    with Project(database) as reopened:
        artifacts=reopened.debug_artifacts(version=1)['artifacts']
        for artifact in artifacts:
            # Native state bytes remain embedded only in the local project database.
            if artifact['kind'] in ('screenshot','trace'):
                reopened.debug_export(artifact['id'],output/artifact['name'])
    summary={'result':'pass','emulator_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
        'script':stored,'dialog_state':dialog,'parent':parent,'derived':fork,'injected':injected,
        'address':'0x471a6','before_hex':before,'after_hex':after,
        'meaning':'user-proposed counter address; arithmetic meaning not established',
        'counter_write_watch_placement':counter_watch,'modified':modified,'breakpoint_hit':hit,'trace':trace,'data_watches':watches,
        'restored_parent':restored,'native_components':info['components'],'artifacts':artifacts}
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('PASS: native state captured, forked with checked RAM edit, reinjected, breakpoint/trace and r/w/rw verified, parent restored')


if __name__=='__main__':
    main()
