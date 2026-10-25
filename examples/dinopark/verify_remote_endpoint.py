"""Replay DinoPark through the IDA-style DOS endpoint; all inputs stay private.

--output must be a new directory outside Git. Only evidence/ contains shareable
observations; private/ holds the copied game, project and any native states.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import socket

from fdisbull.ida_dosbox import Endpoint,DOSRemoteDebugger
from fdisbull.project import Project


def inventory(root):
    if any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('Game inputs must not contain symbolic links')
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob('*')) if p.is_file()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',required=True,type=Path)
    parser.add_argument('--game-dir',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--backend',choices=['dosbox','dosbox-qemu'],default='dosbox')
    parser.add_argument('--kernel',type=Path);parser.add_argument('--initramfs',type=Path)
    parser.add_argument('--timeout-ms',type=int,default=120000)
    args=parser.parse_args()
    source=args.game_dir.resolve(strict=True);output=args.output.resolve()
    if any((parent/'.git').exists() for parent in [output,*output.parents]):
        raise ValueError('Private output must be outside Git')
    if output==source or source in output.parents or output in source.parents:
        raise ValueError('Output must be separate from the original inputs')
    original=inventory(source)
    if original['DINOPARK.EXE']!='2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c':
        raise ValueError('This route targets the verified original DinoPark executable')
    output.mkdir(parents=True,exist_ok=False)
    private=output/'private';private.mkdir()
    evidence=output/'evidence';evidence.mkdir()
    (output/'.gitignore').write_text('/private/\n')
    game=private/'game';shutil.copytree(source,game)
    path=private/'dinopark.fdb'
    with Project.create(path,game/'DINOPARK.EXE') as project:
        project.analyze(start='1000:75bc',max_instructions=12)
    observations=[]
    def record(label,value):
        observations.append(dict(label=label,result=value))
        (evidence/'actions.json').write_text(json.dumps(observations,indent=2)+'\n')
        print(label,flush=True)
        return value
    options=dict(backend=args.backend)
    if args.backend=='dosbox-qemu':options.update(kernel=args.kernel,initramfs=args.initramfs,files=list(original))
    with Endpoint(path,args.executable.resolve(),game,**options) as endpoint:
        client=DOSRemoteDebugger(socket.create_connection(endpoint.address,timeout=5))
        try:
            started=record('launch',client.start('DINOPARK.EXE',bits=16,timeout_ms=600000))
            intro=record('intro',client.extension('run',guest_ms=35000,timeout_ms=args.timeout_ms,fast_forward=True))
            assert intro['outcome']=='guest_time'
            record('menu',client.extension('screenshot',name='remote-menu-grid8.png',grid=True,grid_step=8))
            address=started['module']['base']+0x75bc
            before=client.read(address,3,logical=False)
            bp=client.breakpoint(address)
            assert client.read(address,3,logical=False)==before==bytes.fromhex('b80300')
            record('new-game-click',client.extension('click-frame',x=75,y=160,hold_ms=150,name='new-game-click.png',grid_step=8))
            hit=record('game-code-breakpoint',client.run(args.timeout_ms))
            assert hit['stop_reason']['kind']=='breakpoint' and client.registers()['cs']*16+client.registers()['eip']==address
            client.delete_breakpoint(bp)
            trace=record('input-trace',client.extension('trace',name='remote-new-game-input.json',count=512,timeout_ms=args.timeout_ms))
            assert trace['metadata']['complete']
            record('bank-run',client.extension('run',guest_ms=4000,timeout_ms=args.timeout_ms,fast_forward=True))
            record('bank',client.extension('screenshot',name='remote-bank-grid8.png',grid=True,grid_step=8))
            record('registers',client.registers())
        finally:
            client.close()
    assert endpoint.debug.rpc.process.poll() is not None
    with Project(path) as project:
        artifacts=project.debug_artifacts()['artifacts']
        for artifact in artifacts:
            if artifact['kind'] in ('screenshot','screenshot-grid','trace'):
                project.debug_export(artifact['id'],evidence/artifact['name'])
        assert project.disassembly(address='1000:75bc',version=1,lines=1)['instructions'][0]['bytes']=='b80300'
    assert inventory(source)==original
    saved=json.loads((evidence/'remote-new-game-input.json').read_text())
    assert saved['complete'] and saved['events'][0]['project_address']=='0x175bc'
    (evidence/'summary.json').write_text(json.dumps(dict(result='pass',protocol=31,
        engine='DOSBox heavy-debug virtual breakpoints',backend=args.backend,guest_code_modified_by_breakpoint=False,
        original_game_unchanged=True,process_reaped=True,trace_events=len(saved['events']),artifacts=artifacts),indent=2)+'\n')
    print('PASS: real DinoPark, patchless breakpoint, click-frame, 512 fetch records, offline exports',flush=True)


if __name__=='__main__':main()
