"""Selected DOS process completion, independently of emulator/session cleanup."""
import json
import os
from pathlib import Path

import pytest

from fdisbull.project import Project
from test_dos_loader import mz_file


@pytest.fixture
def emulator():
    value=os.environ.get('FDISBULL_DOSBOX')
    if not value:
        pytest.skip('Set FDISBULL_DOSBOX for real DOS guest-exit acceptance')
    return str(Path(value).resolve(strict=True))


def create_project(directory, code, *, mz=False):
    binary=directory/('TARGET.EXE' if mz else 'TARGET.COM')
    binary.write_bytes(mz_file(code,ss=0,sp=0x400,minalloc=0x40) if mz else code)
    database=directory/'analysis.fdb'
    with Project.create(database,binary,**({} if mz else {'image':'com'})) as project:
        project.analyze(max_instructions=100)
    return database


@pytest.mark.parametrize('code,exit_code,resident,mz',[
    ('b8254ccd21',37,False,False),
    ('b82a4ccd21',42,False,True),
    ('cd20',0,False,False),
    ('c3',0,False,False),
    ('ba2000b82531cd21',37,True,False),
])
def test_selected_dos_process_exit_is_observed_before_session_close(tmp_path,emulator,code,exit_code,resident,mz):
    path=create_project(tmp_path,bytes.fromhex(code),mz=mz)
    with Project(path) as project:
        with project.debugger(emulator,tmp_path) as debug:
            entry=debug.registers()
            result=debug.run(timeout_ms=3000,guest_ms=1000,fast_forward=True)
            kind='guest_tsr' if resident else 'guest_exit'
            assert result['outcome']==kind,result
            assert result['session']['state']=='exited' and not result['timed_out']
            info=result['session']['stop_reason']['guest_exit']
            assert info['source']=='DOS_Terminate' and info['stage']=='after-process-cleanup'
            assert info['requested_exit_code']==exit_code and info['resident'] is resident
            assert info['psp']==entry['segments']['ds']
            assert info['psp']!=info['parent_psp']
            if mz:
                assert info['psp']!=entry['segments']['cs']
            assert result['stop']['guest_exit']==info
            # Status and repeated waiting/cleanup must retain the same native event.
            assert debug.status()['last_stop']['guest_exit']==info
            run_id=debug.run_id
            pid=debug.rpc.process.pid
        assert debug.closed and debug.rpc.process.poll() is not None,pid
    with Project(path) as reopened:
        events=[json.loads(row['evidence']) for row in reopened.db.execute(
            'SELECT evidence FROM debug_events WHERE run=? AND operation=?',(run_id,'run'))]
        assert events[-1]['session']['stop_reason']['guest_exit']==info
        closed=json.loads(reopened.db.execute(
            'SELECT evidence FROM debug_events WHERE run=? AND operation=?',(run_id,'close')).fetchone()['evidence'])
        assert closed['process_reaped'] and closed['state']=='exited'
        assert closed['stop_reason']['guest_exit']==info


def test_pause_and_explicit_session_close_are_not_dos_guest_exit(tmp_path,emulator):
    path=create_project(tmp_path,bytes.fromhex('ebfe'))
    with Project(path) as project:
        with project.debugger(emulator,tmp_path) as debug:
            result=debug.run(timeout_ms=3000,guest_ms=30,fast_forward=True)
            assert result['outcome']=='guest_time'
            assert 'guest_exit' not in result['session']['stop_reason']
            run_id=debug.run_id
        closed=json.loads(project.db.execute(
            'SELECT evidence FROM debug_events WHERE run=? AND operation=?',(run_id,'close')).fetchone()['evidence'])
        assert closed['state']=='exited' and closed['process_reaped']
        assert closed['stop_reason']['kind']=='program_exit'
        assert 'guest_exit' not in closed['stop_reason']


def test_remapped_int20_that_returns_is_not_process_exit(tmp_path,emulator):
    # Set vector 20h to our IRET, invoke it, and loop. Merely decoding CD20
    # must never be promoted to a DOS process-completion event.
    path=create_project(tmp_path,bytes.fromhex('ba0d01b82025cd21cd20ebfe90cf'))
    with Project(path) as project, project.debugger(emulator,tmp_path) as debug:
        result=debug.run(timeout_ms=3000,guest_ms=30,fast_forward=True)
        assert result['outcome']=='guest_time',result
        assert result['session']['state']=='stopped'
        assert 'guest_exit' not in result['session']['stop_reason']


def test_child_exit_does_not_complete_parent_process(tmp_path,emulator):
    # Shrink the COM allocation, EXEC CHILD.COM, mark success, then exit 17.
    # All addresses below are COM offsets, including its 100h PSP prefix.
    code=bytearray.fromhex('0e1f0e078cc8a38401a38801a38c01bc0004bb8000b44acd21')
    failures=[]
    failures.append(len(code));code.extend(b'\x72\0')
    code.extend(bytes.fromhex('baa001bb8001b8004bcd21'))
    failures.append(len(code));code.extend(b'\x72\0')
    code.extend(bytes.fromhex('b8efbea3b001'))
    after_child=0x100+len(code)
    code.extend(bytes.fromhex('b8114ccd21'))
    failure=len(code);code.extend(bytes.fromhex('b87f4ccd21'))
    for offset in failures:
        code[offset+1]=failure-offset-2
    code.extend(bytes(0x80-len(code)))
    code.extend(bytes.fromhex('0000900100005c0000006c000000'))
    code.extend(bytes(0x90-len(code)));code.extend(b'\0\r')
    code.extend(bytes(0xa0-len(code)));code.extend(b'CHILD.COM\0')
    code.extend(bytes(0xb2-len(code)))
    path=create_project(tmp_path,bytes(code))
    (tmp_path/'CHILD.COM').write_bytes(bytes.fromhex('b8254ccd21'))
    with Project(path) as project, project.debugger(emulator,tmp_path) as debug:
        parent_psp=debug.registers()['segments']['ds']
        breakpoint=debug.breakpoint(f'1000:{after_child:04x}')
        result=debug.run(timeout_ms=3000,fast_forward=True)
        assert result['outcome']=='breakpoint',result
        assert debug.memory('1000:01b0',length=2)['hex']=='efbe'
        debug.delete_breakpoint(breakpoint['breakpoint_id'])
        result=debug.run(timeout_ms=3000,fast_forward=True)
        assert result['outcome']=='guest_exit',result
        info=result['session']['stop_reason']['guest_exit']
        assert info['psp']==parent_psp and info['requested_exit_code']==17


def test_native_state_restore_retains_selected_process_identity(tmp_path,emulator):
    code=bytes.fromhex('b80700050500a32001b8004ccd21')
    path=create_project(tmp_path,code)
    with Project(path) as project, project.debugger(emulator,tmp_path) as debug:
        psp=debug.registers()['segments']['ds']
        breakpoint=debug.breakpoint('1000:0109')
        assert debug.run(timeout_ms=3000,fast_forward=True)['outcome']=='breakpoint'
        state=debug.save_state()
        debug.load_state(state['artifact'])
        debug.delete_breakpoint(breakpoint['breakpoint_id'])
        result=debug.run(timeout_ms=3000,fast_forward=True)
        assert result['outcome']=='guest_exit',result
        assert result['session']['stop_reason']['guest_exit']['psp']==psp


def test_foreign_session_snapshot_does_not_guess_target_process(tmp_path,emulator):
    path=create_project(tmp_path,bytes.fromhex('b82a4ccd21'))
    with Project(path) as project:
        with project.debugger(emulator,tmp_path) as first:
            state=first.save_state()
        with project.debugger(emulator,tmp_path) as second:
            second.load_state(state['artifact'])
            # Native bytes alone do not carry the previous host session's
            # selected-target binding. No current child PSP may be adopted.
            result=second.run(timeout_ms=3000,guest_ms=30,fast_forward=True)
            assert result['outcome']=='guest_time',result
            assert 'guest_exit' not in result['session']['stop_reason']
