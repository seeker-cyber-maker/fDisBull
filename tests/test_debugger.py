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
            registers=debug.registers()
            assert registers['cs']==registers['segments']['cs'] and registers['ip']==registers['instruction_pointer']
            assert int(registers['general']['eax'],16)==0x1234
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


@pytest.fixture
def access_game(tmp_path):
    # Set DS=CS; write 1234 to word [100], read it, write the same value, loop read/write.
    binary = tmp_path/'ACCESS.EXE'
    binary.write_bytes(mz_file(bytes.fromhex('0e1fb83412a30001a10001a30001ebf8')+bytes(497),ss=0,sp=0x200))
    project=tmp_path/'access.fdb'
    with Project.create(project,binary) as db:
        db.analyze(start='1000:0000',max_instructions=10)
    return project,binary


def test_real_read_write_same_value_and_fetch_exclusion(access_game,emulator):
    with Project(access_game[0]) as db, db.debugger(emulator,access_game[1].parent) as debug:
        bp=debug.breakpoint('1000:0005')
        assert debug.run(timeout_ms=2000)['outcome']=='breakpoint'
        debug.delete_breakpoint(bp['breakpoint_id'])
        for mode,expected_ip in [('w',8),('r',11),('rw',14)]:
            bp=debug.breakpoint('1000:0101',access=mode) # High byte of a 16-bit access.
            hit=debug.run(timeout_ms=2000)
            assert hit['outcome']=='breakpoint',hit
            assert hit['session']['stop_reason']['breakpoint_id']==bp['breakpoints'][0]['breakpoint_id']
            assert int(debug.registers()['instruction_pointer'],16)==expected_ip
            assert debug.memory('1000:0100',length=2)['hex']=='3412'
            debug.delete_breakpoint(bp['breakpoints'][0]['breakpoint_id'])
        # Fetching instructions and host debugger reads must not count as guest data reads.
        bp=debug.breakpoint('1000:0008',access='r')
        debug.memory('1000:0008',length=3)
        assert debug.run(timeout_ms=30,fast_forward=True)['outcome']=='timeout'
        debug.delete_breakpoint(bp['breakpoints'][0]['breakpoint_id'])


def test_real_native_state_restores_memory_registers_and_new_session(access_game,emulator):
    path,binary=access_game
    with Project(path) as db:
        with db.debugger(emulator,binary.parent) as debug:
            bp=debug.breakpoint('1000:0005')
            assert debug.run(timeout_ms=2000)['outcome']=='breakpoint'
            debug.delete_breakpoint(bp['breakpoint_id'])
            state=debug.save_state('before-write.sav')
            assert state['kind']=='state'
            assert debug.memory('1000:0100',length=2)['hex']=='0000'
            bp=debug.breakpoint('1000:0100',access='w')
            assert debug.run(timeout_ms=2000)['outcome']=='breakpoint'
            assert debug.memory('1000:0100',length=2)['hex']=='3412'
            debug.delete_breakpoint(bp['breakpoints'][0]['breakpoint_id'])
            debug.load_state(state['artifact'])
            assert debug.memory('1000:0100',length=2)['hex']=='0000'
            assert int(debug.registers()['instruction_pointer'],16)==5
    with Project(path) as db, db.debugger(emulator,binary.parent) as debug:
        debug.load_state(state['artifact'])
        assert debug.memory('1000:0100',length=2)['hex']=='0000'
        assert int(debug.registers()['instruction_pointer'],16)==5
        bp=debug.breakpoint('1000:0100',access='w')
        assert debug.run(timeout_ms=2000)['outcome']=='breakpoint'
        debug.delete_breakpoint(bp['breakpoints'][0]['breakpoint_id'])
        extra=binary.parent/'NEW.DAT';extra.write_bytes(b'changed mount')
        with pytest.raises(ValueError,match='Mounted game files differ'):
            debug.load_state(state['artifact'])


def test_script_validation_persistence_and_real_execution(access_game,emulator):
    from fdisbull.debug_script import validate_script
    script={'format':'fdisbull-script-1','steps':[
        {'op':'breakpoint','address':'1000:0005','as':'bp'},
        {'op':'run','timeout_ms':2000,'as':'hit'},
        {'op':'assert','value':'$hit.outcome','equals':'breakpoint'},
        {'op':'delete-breakpoint','breakpoint_id':'$bp.breakpoint_id'},
        {'op':'save-state','as':'checkpoint'},
        {'op':'repeat','count':2,'steps':[
            {'op':'run','timeout_ms':1000,'guest_ms':10,'fast_forward':True},
            {'op':'load-state','artifact':'$checkpoint.artifact'}]},
        {'op':'memory','address':'1000:0100','length':2,'as':'word'},
        {'op':'assert','value':'$word.hex','equals':'0000'}]}
    with pytest.raises(ValueError):validate_script({'format':'fdisbull-script-1','steps':[{'op':'shell','command':'no'}]})
    with pytest.raises((ValueError,TypeError)):validate_script({'format':'fdisbull-script-1','steps':[{'op':'click','xx':1,'y':2}]})
    with Project(access_game[0]) as db:
        stored=db.debug_save_script('route.json',script)
    with Project(access_game[0]) as db, db.debugger(emulator,access_game[1].parent) as debug:
        assert db.debug_scripts()['scripts'][0]['sha256']==stored['sha256']
        result=debug.script(script_id=stored['script_id'])
        assert result['ok'],result
        assert result['completed_steps']==11
        failed=debug.script({'format':'fdisbull-script-1','steps':[
            {'op':'assert','value':1,'equals':2},{'op':'run','guest_ms':100}]})
        assert not failed['ok'] and failed['completed_steps']==0 and len(failed['steps'])==1


def test_native_state_fork_edits_and_reinjects_without_changing_parent(access_game,emulator):
    path,binary=access_game
    with Project(path) as db:
        static_before=db.disassembly(address='1000:0005',lines=1)['instructions'][0]['bytes']
        with db.debugger(emulator,binary.parent) as debug:
            bp=debug.breakpoint('1000:0005')
            assert debug.run(timeout_ms=2000)['outcome']=='breakpoint'
            debug.delete_breakpoint(bp['breakpoint_id'])
            parent=debug.save_state('parent.sav')
        info=db.debug_state_info(parent['artifact'])
        assert {'CPU','Memory','Vga','Pic'} <= {i['name'] for i in info['components']}
        fork=db.debug_fork_state(parent['artifact'],emulator,binary.parent,
            memory=[{'address':'1000:0100','expected_hex':'0000','data_hex':'9999'}],
            registers={'eax':{'expected':'0x1234','value':'0xbeef'}})
        assert fork['metadata']['derivation']['parent_sha256']==parent['sha256']
        assert not fork['metadata']['derivation']['guest_execution_during_edits']
        assert db.debug_state_info(parent['artifact'])['sha256']==parent['sha256']
        with db.debugger(emulator,binary.parent) as debug:
            debug.load_state(fork['artifact'])
            assert debug.memory('1000:0100',length=2)['hex']=='9999'
            assert int(debug.registers()['general']['eax'],16)==0xbeef
            bp=debug.breakpoint('1000:0100',access='w')
            hit=debug.run(timeout_ms=2000)
            assert hit['outcome']=='breakpoint'
            assert hit['session']['stop_reason']['data_access']['project_instruction']=='0x10005'
            assert debug.memory('1000:0100',length=2)['hex']=='efbe'
            debug.delete_breakpoint(bp['breakpoints'][0]['breakpoint_id'])
            debug.load_state(parent['artifact'])
            assert debug.memory('1000:0100',length=2)['hex']=='0000'
            assert int(debug.registers()['general']['eax'],16)==0x1234
        with pytest.raises(ValueError,match='expected bytes mismatch'):
            db.debug_fork_state(parent['artifact'],emulator,binary.parent,
                memory=[{'address':'1000:0100','expected_hex':'ffff','data_hex':'1111'}])
        assert db.disassembly(address='1000:0005',lines=1)['instructions'][0]['bytes']==static_before
        assert len(db.debug_artifacts()['artifacts'])==2 # Failed edit creates no derivative snapshot.


def test_real_explicit_seed_places_breakpoint_despite_persistent_backlog(tmp_path,emulator):
    module=bytearray(b'\x90'*512)
    module[0x60:0x65]=bytes.fromhex('b87856ebfe')
    binary=tmp_path/'SEED.EXE'
    binary.write_bytes(mz_file(bytes(module),ss=0,sp=0x200))
    path=tmp_path/'seed.fdb'
    with Project.create(path,binary) as db:
        db.analyze(max_instructions=1)
    with Project(path) as db:
        result=db.analyze(start='1000:0060',max_instructions=1)
        assert not result['stable'] and result['pending']>0
        with db.debugger(emulator,binary.parent) as debug:
            bp=debug.breakpoint('1000:0060')
            assert bp['bytes_verified'] and bp['runtime_bytes']=='b87856'
            hit=debug.run(timeout_ms=2000,fast_forward=True)
            assert hit['outcome']=='breakpoint'
            assert hit['session']['stop_reason']['project_address']=='0x10060'
        # Runtime observations and explicit seeding leave old recursive work intact.
        db.analyze(max_instructions=1)
        assert db.disassembly('1000:0001',lines=1)['instructions'][0]['bytes']=='90'


def test_real_rep_word_watch_stops_after_copy_without_duplicate_byte_hit(tmp_path,emulator):
    # DS=ES=CS; copy four distinct words from 100 to 110, then loop without writes.
    module=bytearray(512)
    module[:19]=bytes.fromhex('0e1f0e07be0001bf1001b90400fcf3a590ebfd')
    module[0x100:0x108]=bytes.fromhex('1122334455667788')
    binary=tmp_path/'REP.EXE'
    binary.write_bytes(mz_file(bytes(module),ss=0,sp=0x200))
    with Project.create(tmp_path/'rep.fdb',binary) as db:
        db.analyze(max_instructions=20)
        with db.debugger(emulator,binary.parent) as debug:
            # Both byte watches overlap one word access at the end of the copy.
            watch=debug.breakpoint('1000:0116',access='w',length=2)
            assert debug.memory('1000:0110',length=8)['hex']=='0000000000000000'
            hit=debug.run(timeout_ms=2000,fast_forward=True)
            assert hit['outcome']=='breakpoint',hit
            access=hit['session']['stop_reason']['data_access']
            assert access['project_instruction']=='0x1000e' and access['length']==2
            assert int(access['address'],16)==debug.runtime_load*16+0x116
            assert hit['session']['stop_reason']['breakpoint_id'] in {b['breakpoint_id'] for b in watch['breakpoints']}
            assert debug.memory('1000:0110',length=8)['hex']=='1122334455667788'
            registers=debug.registers()
            assert int(registers['ip'],16)==0x10
            assert int(registers['general']['ecx'],16)==0
            assert int(registers['general']['esi'],16)==0x108
            assert int(registers['general']['edi'],16)==0x118
            # Watches stay armed: no deferred second halfword stop on continuation.
            trace=debug.trace(count=16)
            assert trace['metadata']['complete'] and trace['metadata']['event_count']==16
