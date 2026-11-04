"""The public foreground server owns and reaps the real engine process."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys

import pytest

from fdisbull.project import Project


@pytest.mark.skipif(not (os.environ.get('FDISBULL_SCUMMVM_NATIVE') and os.environ.get('FDISBULL_AGI_KQ1_DIR')),
                    reason='requires patched ScummVM and private KQ1 original')
def test_real_scummvm_foreground_cli_and_offline_artifacts(tmp_path):
    game=Path(os.environ['FDISBULL_AGI_KQ1_DIR'])
    database=tmp_path/'cli.fdb'
    with Project.create(database,game/'AGI',arch='x86',bits=16):pass
    environment=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'src'))
    process=subprocess.Popen([sys.executable,'-m','fdisbull','debug',str(database),
        '--backend','scummvm-agi','--game-id','agi:kq1',
        '--executable',os.environ['FDISBULL_SCUMMVM_NATIVE'],'--game-dir',str(game)],
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=environment)
    try:
        assert select.select([process.stdout],[],[],20)[0], 'foreground launch did not return'
        launch=json.loads(process.stdout.readline())
        assert launch['ok'],launch
        run=launch['result']['run']
        def exchange(request):
            process.stdin.write(json.dumps(request)+'\n');process.stdin.flush()
            assert select.select([process.stdout],[],[],15)[0], 'foreground operation did not return'
            return json.loads(process.stdout.readline())
        asynchronous=exchange({'id':4,'method':'debug-run-async',
            'params':{'run':run,'max_instructions':1000000,'timeout_ms':10000}})
        assert asynchronous['ok'],asynchronous
        operation=asynchronous['result']['operation']
        paused=exchange({'id':5,'method':'debug-pause','params':{'run':run,'timeout_ms':5000}})
        assert paused['ok'] and paused['result']['confirmed_stopped'],paused
        collected=exchange({'id':6,'method':'debug-run-result',
            'params':{'run':run,'operation':operation,'wait_ms':1000}})
        assert collected['ok'] and collected['result']['complete'],collected
        assert collected['result']['error'] is None,collected
        assert collected['result']['result']['outcome']=='pause',collected
        requests=[{'id':1,'method':'debug-step','params':{'run':run,'count':1}},
                  {'id':2,'method':'debug-screenshot','params':{'run':run,'name':'cli.png'}},
                  {'id':3,'method':'debug-stop','params':{'run':run}}]
        stdout,stderr=process.communicate(''.join(json.dumps(r)+'\n' for r in requests),timeout=20)
        assert process.returncode==0,stderr
        replies=[json.loads(line) for line in stdout.splitlines()]
        assert [r['id'] for r in replies]==[1,2,3]
        assert all(r['ok'] for r in replies),replies
        assert replies[-1]['result']['process_reaped'] is True
        screenshot=replies[1]['result']['artifact']
    finally:
        if process.poll() is None:
            process.kill();process.wait(timeout=5)
    with Project(database) as project:
        assert project.debug_runs()['runs'][0]['metadata']['replacement_engine'] is True
        result=project.debug_export(screenshot,tmp_path/'cli.png')
        assert (tmp_path/'cli.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
