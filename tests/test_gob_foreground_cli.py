"""Real Gob process ownership through the public foreground server."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys

import pytest

from fdisbull.project import Project


@pytest.mark.skipif(not(os.environ.get('FDISBULL_GOB_NATIVE') and os.environ.get('FDISBULL_LOSTTIME_EN_DIR')),
                    reason='requires patched Gob executable and private original Lost in Time English')
def test_gob_public_typed_reads_async_pause_and_stored_image(tmp_path):
    game=Path(os.environ['FDISBULL_LOSTTIME_EN_DIR'])
    database=tmp_path/'gob-cli.fdb'
    with Project.create(database,game/'lost.exe'):pass
    env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'))
    process=subprocess.Popen([sys.executable,'-m','fdisbull','debug',str(database),
        '--backend','scummvm-gob','--game-id','gob:lit','--language','us','--platform','dos',
        '--executable',os.environ['FDISBULL_GOB_NATIVE'],'--game-dir',str(game)],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
    artifact=None
    def receive(seconds=20):
        assert select.select([process.stdout],[],[],seconds)[0], 'foreground Gob response timed out'
        line=process.stdout.readline()
        assert line, 'foreground Gob server closed'
        value=json.loads(line)
        assert value['ok'],value
        return value['result']
    try:
        launched=receive();run=launched['run']
        def call(method,**params):
            process.stdin.write(json.dumps({'method':method,'params':{'run':run,**params}})+'\n')
            process.stdin.flush()
            return receive()
        memory=call('debug-read-variable',offset=13435,width=1,signed=True)
        assert memory['backend']=='scummvm-gob' and type(memory['value']) is int
        state=call('debug-engine-state')
        assert state['script']['name'].upper().endswith('.TOT')
        job=call('debug-run-async',max_instructions=1000000,guest_ms=500000,timeout_ms=10000)
        pause=call('debug-pause',timeout_ms=5000)
        assert pause['confirmed_stopped'],pause
        result=call('debug-run-result',operation=job['operation'],wait_ms=1000)
        assert result['complete'] and result['error'] is None,result
        assert result['result']['outcome']=='pause',result
        frame=call('debug-screenshot',name='gob-cli.png',hooks=False)
        artifact=frame['artifact']
        receipt=call('debug-stop')
        assert receipt['closed'] and receipt['process_reaped']
        process.stdin.close();process.wait(timeout=10)
        assert process.returncode==0,process.stderr.read()
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=5)
    with Project(database) as project:
        assert project.debug_runs()['runs'][0]['metadata']['backend']=='scummvm-gob'
        project.debug_export(artifact,tmp_path/'gob-cli.png')
        assert (tmp_path/'gob-cli.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n')


@pytest.mark.skipif(not(os.environ.get('FDISBULL_GOB_NATIVE') and os.environ.get('FDISBULL_LOSTTIME_EN_DIR')),
                    reason='requires patched Gob executable and original Lost in Time English')
def test_populated_hotspot_receipts_survive_repeated_reads_and_execution(tmp_path):
    """Regression: the first populated response used to free the retained tree."""
    game=Path(os.environ['FDISBULL_LOSTTIME_EN_DIR'])
    with Project.create(tmp_path/'events.fdb',game/'lost.exe') as project:
        with project.debugger(os.environ['FDISBULL_GOB_NATIVE'],game,backend='scummvm-gob',
                              language='us',platform='dos') as engine:
            def advance(ms):
                result=engine.run(guest_ms=ms,timeout_ms=15000,max_instructions=1000000)
                assert result['outcome']=='guest_time',result
            advance(5000);engine.keyboard_press('space')
            advance(1500);engine.keyboard_press('escape')
            advance(6000);advance(20000)
            # Exact-edition opening narration, followed by a physical poster inspection.
            frame=engine.frame_probe([])
            assert (frame['width'],frame['height'])==(320,200)
            engine.click(160,178);advance(1500)
            assert engine.engine_state()['script']['name'].casefold()=='emam1017.tot'
            engine.click(74,76);advance(1500)
            assert engine.read_variable(12637,width=1,signed=True)['value']==1
            first=engine.hotspot_events()
            assert first['entries'],first
            for _ in range(3):
                assert engine.hotspot_events()['entries']==first['entries']
                assert engine.engine_state()['script']['name'].casefold()=='emam1017.tot'
            advance(500)
            assert engine.hotspot_events()['entries']
            assert engine.rpc.process.poll() is None
