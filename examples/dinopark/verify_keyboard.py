"""Verify controller typing in a private DinoPark save-name dialog.

Does not confirm/save the game or qualify a durable leaderboard entry. Private
native states, game copies and the project database stay outside Git.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil

from fdisbull import __version__
from fdisbull.project import Project


def inventory(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',type=Path,required=True)
    parser.add_argument('--game-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    game=args.game_dir.resolve(strict=True);output=args.output.resolve()
    backend=args.executable.resolve(strict=True)
    if output==game or game in output.parents or output in game.parents:
        raise ValueError('Output must be separate from game input')
    if any((p/'.git').exists() for p in [output,*output.parents]):
        raise ValueError('Private output must be outside Git')
    before=inventory(game)
    assert before['DINOPARK.EXE']=='2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c'
    output.mkdir(parents=True,exist_ok=False)
    private=output/'private';private.mkdir();evidence=output/'evidence';evidence.mkdir()
    mounted=private/'game';shutil.copytree(game,mounted)
    route=[]
    def run(ms,fast=False):route.append(dict(op='run',guest_ms=ms,timeout_ms=15000,fast_forward=fast))
    def click(x,y,name,ms=600):
        route.append(dict(op='click-frame',x=x,y=y,name=name+'.png',grid_step=8,hold_ms=80));run(ms)
    def press(key):route.append(dict(op='keyboard.press',key=key));run(180)
    run(35000,True)
    click(80,160,'new-game',1800);press('escape');run(500);press('escape');run(500)
    click(175,187,'leave-bank');click(145,187,'main-menu');click(216,122,'save-game');click(96,57,'name-field',200)
    press('home')
    route.append(dict(op='repeat',count=8,steps=[dict(op='keyboard.press',key='delete'),
        dict(op='run',guest_ms=180,timeout_ms=5000,fast_forward=True)]))
    route.append(dict(op='keyboard.type',text='FD16TEST'));run(1300)
    press('backspace');route.append(dict(op='keyboard.type',text='1'));run(180)
    route.append(dict(op='keyboard.state',**{'as':'keyboard'}))
    script=dict(format='fdisbull-script-1',steps=route)
    (evidence/'keyboard-route.json').write_text(json.dumps(script,indent=2)+'\n')
    processes=[]
    with Project.create(private/'dinopark.fdb',mounted/'DINOPARK.EXE') as project:
        saved=project.debug_save_script('DinoPark controller name entry',script)
        with project.debugger(backend,mounted) as debug:
            processes.append(debug.rpc.process)
            result=debug.script(script_id=saved['script_id'],timeout_ms=120000)
            project.debug_export(result['artifact'],evidence/'keyboard-route-result.json')
            assert result['ok'],result
            assert debug.keyboard.state()['keyboard']==dict(pending_events=0,owned_keys=0,queued_guest_ms=0)
            frame=debug.screenshot('typed-name.png',grid=True,grid_step=8)
            project.debug_export(frame['artifact'],evidence/'typed-name.png')
            # The dialog owns a heap buffer outside the mapped EXE. Scan bounded
            # conventional RAM, retaining addresses and the expected text only.
            matches=[];needle=b'FD16TES1';tail=b''
            for off in range(0,0xa0000,32768):
                observed=debug.call('memory.read',{'address':{'space':'linear','offset':f'0x{off:08X}'},'length':32768})
                data=base64.b64decode(observed['data_base64'],validate=True)
                chunk=tail+data;start=0
                while (pos:=chunk.find(needle,start))>=0:
                    matches.append(f'0x{off-len(tail)+pos:08X}');start=pos+1
                tail=chunk[-len(needle)+1:]
            assert matches,'Typed text absent from conventional guest RAM'
            trace=debug.trace('name-dialog-trace.json',count=32,timeout_ms=10000)
            assert trace['metadata']['complete'],trace
            project.debug_export(trace['artifact'],evidence/'name-dialog-trace.json')
            checkpoint=debug.save_state('typed-name.sav')
        with project.debugger(backend,mounted) as debug:
            processes.append(debug.rpc.process)
            debug.load_state(checkpoint['artifact'])
            debug.run(guest_ms=120,timeout_ms=5000,fast_forward=True)
            frame=debug.screenshot('restored-typed-name.png',grid=True,grid_step=8)
            project.debug_export(frame['artifact'],evidence/'restored-typed-name.png')
            observed=debug.call('memory.read',{'address':{'space':'linear','offset':matches[0]},'length':len(needle)})
            assert base64.b64decode(observed['data_base64'],validate=True)==needle
            queue=debug.keyboard.state()['keyboard']
    assert all(p.poll() is not None for p in processes)
    assert inventory(game)==before and inventory(mounted)==before
    report=dict(version=__version__,backend_sha256=hashlib.sha256(backend.read_bytes()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),source_sha256=before['DINOPARK.EXE'],
        input='FD16TEST then Backspace then 1',observed_ascii='FD16TES1',runtime_linear_addresses=matches,
        native_state_restored_in_fresh_session=True,keyboard_after_restore=queue,
        original_files_unchanged=len(before),copied_files_unchanged=len(before),processes_reaped=True,
        scope='Save-name dialog typing and native restoration; no save confirmation or durable leaderboard claim')
    (evidence/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    hashes=inventory(evidence)
    (evidence/'SHA256SUMS.json').write_text(json.dumps(hashes,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
