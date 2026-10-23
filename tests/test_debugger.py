"""Runtime contracts exercised with a real external DOSBox build when selected."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from fdisbull.cli import respond
from fdisbull.project import Project
from test_dos_loader import mz_file


@pytest.fixture
def game(tmp_path):
    # mov ax,1234; mov bx,5678; inc word [100]; jmp 6
    module = bytes.fromhex('b83412bb7856ff060001ebfa') + bytes(500)
    binary = tmp_path/'GAME.EXE'
    binary.write_bytes(mz_file(module,ss=0,sp=0x200))
    project = tmp_path/'game.fdb'
    with Project.create(project,binary) as db:
        db.analyze(start='1000:0000',max_instructions=8)
    return project,binary


@pytest.fixture
def emulator():
    path = os.environ.get('FDISBULL_DOSBOX')
    if not path:
        pytest.skip('Set FDISBULL_DOSBOX to run real DOS debugger integration')
    return str(Path(path).resolve(strict=True))


def test_launch_rejects_wrong_source_and_patched_versions_before_spawn(game):
    project,binary = game
    with Project(project) as db:
        binary.write_bytes(binary.read_bytes()+b'changed')
        with pytest.raises(ValueError,match='source hash'):
            db.debugger('/does/not/exist',binary.parent)
        child=db.patch('1000:0000','90')
        with pytest.raises(ValueError,match='unpatched'):
            db.debugger('/does/not/exist',binary.parent,version=child['id'] if 'id' in child else child['version'])
        assert not db.debug_runs(version=1)['runs']


def test_one_shot_launch_requires_owned_server(game):
    result=respond({'method':'debug-launch','params':{'project':str(game[0]),'executable':'anything','game_dir':str(game[1].parent)}})
    assert not result['ok'] and 'serve' in result['error']['message']


def test_real_breakpoint_translation_trace_restart_and_patch_isolation(game,emulator,tmp_path):
    path,binary=game
    with Project(path) as db:
        with db.debugger(emulator,binary.parent) as debug:
            breakpoint=debug.breakpoint('1000:0003')
            assert breakpoint['bytes_verified'] and breakpoint['runtime_bytes']=='bb7856'
            stopped=debug.run(timeout_ms=2000,fast_forward=True)
            assert stopped['outcome']=='breakpoint' and not stopped['timed_out']
            assert stopped['session']['stop_reason']['project_address']=='0x10003'
            assert not stopped['timing_after']['fast_forward']
            assert int(debug.registers()['general']['eax'],16)==0x1234
            debug.delete_breakpoint(breakpoint['breakpoint_id'])
            trace=debug.trace(count=4)
            assert trace['metadata']['complete'] and trace['metadata']['event_count']==4
            moved=debug.run(guest_ms=1000,timeout_ms=2000,fast_forward=True)
            assert moved['outcome']=='guest_time' and moved['guest_elapsed_ms']>=1000
            screenshot=debug.screenshot('guest.png')
            pid=debug.rpc.process.pid
        assert debug.rpc.process.poll() is not None
        child=db.patch('1000:0000','90')
        child_id=child.get('id',child.get('version'))
        assert db.debug_artifacts(version=child_id)['artifacts']==[]
    # All observations survive emulator and Project restart, inside SQLite.
    with Project(path) as reopened:
        artifacts=reopened.debug_artifacts(version=1)['artifacts']
        assert {x['kind'] for x in artifacts}=={'trace','screenshot'}
        assert reopened.debug_runs(version=1)['runs'][0]['state']=='exited'
        output=tmp_path/'saved.png'
        reopened.debug_export(screenshot['artifact'],output)
        assert output.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
        assert hashlib.sha256(output.read_bytes()).hexdigest()==screenshot['sha256']
        with pytest.raises(ValueError,match='cannot overwrite'):
            reopened.debug_export(screenshot['artifact'],path)
        trace_path=tmp_path/'trace.json'
        reopened.debug_export(trace['artifact'],trace_path)
        events=json.loads(trace_path.read_text())['events']
        assert [e['project_address'] for e in events]==['0x10003','0x10006','0x1000a','0x10006']


def test_real_timeout_is_not_breakpoint_and_speed_is_restored(game,emulator):
    with Project(game[0]) as db, db.debugger(emulator,game[1].parent) as debug:
        result=debug.run(timeout_ms=30,fast_forward=True)
        assert result['timed_out'] and result['outcome']=='timeout'
        assert result['session']['state']=='stopped'
        assert result['session']['stop_reason']['kind']=='pause'
        assert not result['timing_after']['fast_forward']
        assert debug.registers()['cpu_mode']=='real'
        for options in ({'timeout_ms':0},{'timeout_ms':True},{'guest_ms':-1},{'fast_forward':1}):
            with pytest.raises(ValueError):debug.run(**options)
        assert not debug._timing()['fast_forward']


def test_real_relocated_instruction_bytes_are_checked(game,emulator):
    path,binary=game
    relocated=binary.with_name('RELOC.EXE')
    relocated.write_bytes(mz_file(bytes.fromhex('b80000ebfe')+bytes(507),relocations=[(1,0)],ss=0,sp=0x200))
    with Project.create(path.with_name('reloc.fdb'),relocated,load_segment=0x2000) as db:
        db.analyze(max_instructions=4)
        with db.debugger(emulator,binary.parent) as debug:
            result=debug.breakpoint('2000:0000')
            assert result['bytes_verified']
            assert int.from_bytes(bytes.fromhex(result['runtime_bytes'])[1:],'little')==debug.runtime_load
            debug.delete_breakpoint(result['breakpoint_id'])
            address=result['address']
            before=debug.call('memory.read',{'address':address,'length':1})
            debug.call('memory.write',{'address':address,'data_base64':'kA==','expected_sha256':before['sha256']})
            with pytest.raises(ValueError,match='Runtime code bytes differ'):
                debug.breakpoint('2000:0000')
            assert db.disassembly(address='2000:0000',lines=1)['instructions'][0]['bytes'].startswith('b8')


def test_real_server_eof_reaps_session_and_offline_export_works(game,emulator):
    process=subprocess.Popen([sys.executable,'-m','fdisbull','debug',str(game[0]),
        '--executable',emulator,'--game-dir',str(game[1].parent)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    try:
        launch=json.loads(process.stdout.readline())
        assert launch['ok'],launch
        run=launch['result']['run']
        process.stdin.write(json.dumps({'id':2,'method':'debug-run','params':{'run':run,'guest_ms':100,'fast_forward':True}})+'\n')
        process.stdin.flush()
        result=json.loads(process.stdout.readline())
        assert result['ok'] and result['result']['outcome']=='guest_time'
        process.stdin.close()
        assert process.wait(timeout=10)==0
        with Project(game[0]) as db:
            record=db.debug_runs()['runs'][0]
            assert record['state']=='exited' and record['ended']
    finally:
        if process.poll() is None:process.kill();process.wait()
