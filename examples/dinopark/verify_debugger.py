"""Replay the project debugger acceptance against the user's original DinoPark.

No game assets are included. Run with the Python environment containing fdisbull.
The output directory must not already contain dinopark.fdb or exported artifacts.
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
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    binary=args.game_dir.resolve()/'DINOPARK.EXE'
    assert hashlib.sha256(binary.read_bytes()).hexdigest()=='2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c','Different game executable'
    database=output/'dinopark.fdb'
    with Project.create(database,binary) as project:
        project.analyze(start='1000:75bc',max_instructions=12)
    process=subprocess.Popen([sys.executable,'-m','fdisbull','serve','--project',str(database)],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    sequence=0
    with (output/'commands.jsonl').open('x',buffering=1) as log:
        def call(method,**params):
            nonlocal sequence
            sequence+=1
            request={'id':sequence,'method':method,'params':params}
            process.stdin.write(json.dumps(request)+'\n');process.stdin.flush()
            result=json.loads(process.stdout.readline())
            log.write(json.dumps({'request':request,'response':result})+'\n')
            assert result['ok'],result
            return result['result']
        try:
            launch=call('debug-launch',executable=str(args.executable.resolve()),game_dir=str(args.game_dir.resolve()))
            run=launch['run']
            skip=call('debug-run',run=run,guest_ms=10000,fast_forward=True,timeout_ms=5000)
            assert skip['outcome']=='guest_time' and skip['guest_elapsed_ms']>=10000
            assert not skip['timing_after']['fast_forward']
            call('debug-screenshot',run=run,name='intro-skipped.png')
            call('debug-run',run=run,guest_ms=8000,fast_forward=True,timeout_ms=5000)
            title=call('debug-screenshot',run=run,name='title.png')
            breakpoint=call('debug-breakpoint',run=run,address='1000:75bc')
            assert breakpoint['bytes_verified'] and breakpoint['runtime_bytes']=='b80300'
            call('debug-click',run=run,x=75,y=160,mode_id=title['metadata']['mode_id'],hold_ms=150)
            hit=call('debug-run',run=run,fast_forward=True,timeout_ms=3000)
            assert hit['outcome']=='breakpoint'
            assert hit['session']['stop_reason']['project_address']=='0x175bc'
            call('debug-delete-breakpoint',run=run,breakpoint_id=breakpoint['breakpoint_id'])
            trace=call('debug-trace',run=run,name='new-game-input.json',count=512,timeout_ms=3000)
            assert trace['metadata']['complete']
            call('debug-run',run=run,guest_ms=4000,fast_forward=True,timeout_ms=5000)
            bank=call('debug-screenshot',run=run,name='bank-loan.png')
            call('debug-click',run=run,x=160,y=132,mode_id=bank['metadata']['mode_id'])
            call('debug-run',run=run,guest_ms=3000,fast_forward=True,timeout_ms=5000)
            call('debug-click',run=run,x=290,y=100,button='right')
            call('debug-run',run=run,guest_ms=2000,fast_forward=True,timeout_ms=5000)
            call('debug-screenshot',run=run,name='city.png')
            call('debug-click',run=run,x=60,y=140)
            call('debug-run',run=run,guest_ms=4000,fast_forward=True,timeout_ms=5000)
            call('debug-screenshot',run=run,name='real-estate.png')
            timeout=call('debug-run',run=run,fast_forward=True,timeout_ms=30)
            assert timeout['outcome']=='timeout' and timeout['timed_out']
            assert timeout['session']['state']=='stopped' and not timeout['timing_after']['fast_forward']
            call('debug-stop',run=run)
        finally:
            process.stdin.close()
            assert process.wait(timeout=30)==0
    # A new database connection can export everything after server/emulator exit.
    with Project(database) as reopened:
        artifacts=reopened.debug_artifacts(version=1)
        assert len(artifacts['artifacts'])==6
        assert reopened.debug_runs(version=1)['runs'][0]['state']=='exited'
        for artifact in artifacts['artifacts']:
            reopened.debug_export(artifact['id'],output/artifact['name'])
    events=json.loads((output/'new-game-input.json').read_text())['events']
    assert len(events)==512 and events[0]['project_address']=='0x175bc'
    assert events[0]['project_segmented_address'] is not None
    assert events[1]['instruction']=='int  33'
    registers={}
    for event in events[:6]:registers.update(event['register_changes'])
    assert tuple(int(registers[key],16) for key in ('ebx','ecx','edx'))==(1,150,160)
    (output/'summary.json').write_text(json.dumps({'result':'pass','run':run,'skip':skip,
        'breakpoint':breakpoint,'hit':hit,'trace':trace,'timeout':timeout,'artifacts':artifacts},indent=2)+'\n')
    print('PASS: DinoPark through fDisBull; native fast-forward, mapped breakpoint, persisted trace/PNGs, timeout and offline export')


if __name__=='__main__':
    main()
