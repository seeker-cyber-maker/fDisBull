"""Selected DOS process completion, independently of emulator/session cleanup."""
import json
import hashlib
import os
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from fdisbull.project import Project
from fdisbull.debugger import DebugSession, _native_dos_process_identity
from fdisbull.dosbox_rpc import DebuggerError
from test_dos_loader import mz_file
from native_fixture import prepare_native_fixture


REQUIRE_COLD_PROCESS_IDENTITY = 'FDISBULL_REQUIRE_COLD_DOS_GUEST_EXIT_IDENTITY'


@pytest.fixture
def emulator():
    value=os.environ.get('FDISBULL_DOSBOX')
    if not value:
        if os.environ.get(REQUIRE_COLD_PROCESS_IDENTITY)=='1':
            pytest.fail(f'Set FDISBULL_DOSBOX with {REQUIRE_COLD_PROCESS_IDENTITY}=1')
        pytest.skip('Set FDISBULL_DOSBOX for real DOS guest-exit acceptance')
    return str(Path(value).resolve(strict=True))


def create_project(directory, code, *, mz=False):
    binary=directory/('TARGET.EXE' if mz else 'TARGET.COM')
    binary.write_bytes(mz_file(code,ss=0,sp=0x400,minalloc=0x40) if mz else code)
    database=directory/'analysis.fdb'
    with Project.create(database,binary,**({} if mz else {'image':'com'})) as project:
        project.analyze(max_instructions=100)
    return database


def test_saved_dos_process_identity_requires_exact_state_hash_and_valid_psp():
    data = b'authored native state bytes'
    identity = dict(sha256=hashlib.sha256(data).hexdigest(), psp=0x0814)
    assert _native_dos_process_identity(None, data) is None
    assert _native_dos_process_identity(identity, data) == identity
    with pytest.raises(ValueError, match='does not match native state bytes'):
        _native_dos_process_identity(dict(identity, sha256='0' * 64), data)
    for psp in (0, -1, 0x10000, True, '0x814'):
        with pytest.raises(ValueError, match='PSP'):
            _native_dos_process_identity(dict(identity, psp=psp), data)
    with pytest.raises(ValueError, match='Invalid saved DOS process identity'):
        _native_dos_process_identity(dict(identity, extra='ignored?'), data)


class _NativeCheckpointHarness:
    def __init__(self, *, identity_bound=True, load_error=None):
        self.data = b'authored native state bytes'
        self.identity = dict(sha256=hashlib.sha256(self.data).hexdigest(), psp=0x0814)
        self.identity_bound = identity_bound
        self.load_error = load_error
        self.loaded_params = None
        self.closed = False
        self.metadata = dict(source_sha256='source', version_sha256='version',
            emulator_sha256='backend', runtime_load_segment=0x1000,
            runtime_profile='dos', game_dir='/private/game')
        self.rpc = SimpleNamespace(capabilities={'save_states': True}, lock=threading.RLock())

    def call(self, method, params=None):
        if method == 'input.mouse.state':
            return {'mouse': {}}
        if method == 'state.save':
            Path(params['path']).write_bytes(self.data)
            return {'dos_process_identity': dict(self.identity)}
        if method == 'state.load':
            self.loaded_params = dict(params)
            if self.load_error is not None:
                raise DebuggerError(self.load_error)
            return ({} if self.identity_bound is None else
                    {'dos_process_identity_bound': self.identity_bound})
        raise AssertionError(method)

    def _disk_manifest(self):
        return []

    def _layer_state(self):
        return {'active': []}

    def registers(self):
        return {'cpu_mode': 'real', 'general': {}, 'segments': {},
                'instruction_pointer': 0, 'flags': 0}

    def _restore_layer_state(self, _state):
        pass

    def _invalidate_runtime_bindings(self):
        pass

    def _event(self, *_args):
        pass

    def close(self):
        self.closed = True


def test_cold_native_checkpoint_carries_only_bridge_issued_identity():
    harness = _NativeCheckpointHarness()
    checkpoint = DebugSession._capture_native_checkpoint(harness)
    assert checkpoint['metadata']['dos_process_identity'] == harness.identity
    restored = DebugSession._restore_native_checkpoint(harness, checkpoint)
    assert restored['sha256'] == harness.identity['sha256']
    assert harness.loaded_params['dos_process_identity'] == harness.identity


@pytest.mark.parametrize('bridge_reply', [False, None])
def test_cold_native_checkpoint_forged_psp_fails_closed_when_bridge_rejects(bridge_reply):
    harness = _NativeCheckpointHarness(identity_bound=bridge_reply)
    checkpoint = DebugSession._capture_native_checkpoint(harness)
    forged = dict(checkpoint)
    forged['metadata'] = dict(checkpoint['metadata'],
                              dos_process_identity=dict(harness.identity, psp=0x0815))
    with pytest.raises(DebuggerError, match='did not confirm the saved DOS process identity'):
        DebugSession._restore_native_checkpoint(harness, forged)
    assert harness.loaded_params['dos_process_identity']['psp'] == 0x0815
    assert harness.closed


def test_cold_native_checkpoint_state_load_error_closes_session():
    harness = _NativeCheckpointHarness(load_error='Native state bytes changed during restore')
    checkpoint = DebugSession._capture_native_checkpoint(harness)
    with pytest.raises(DebuggerError, match='Native state bytes changed during restore'):
        DebugSession._restore_native_checkpoint(harness, checkpoint)
    assert harness.closed


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
        prepare_native_fixture(debug)
        psp=debug.registers()['segments']['ds']
        breakpoint=debug.breakpoint('1000:0109')
        assert debug.run(timeout_ms=3000,fast_forward=True)['outcome']=='breakpoint'
        state=debug.save_state()
        debug.load_state(state['artifact'])
        debug.delete_breakpoint(breakpoint['breakpoint_id'])
        result=debug.run(timeout_ms=3000,fast_forward=True)
        assert result['outcome']=='guest_exit',result
        assert result['session']['stop_reason']['guest_exit']['psp']==psp


def test_cold_session_restore_uses_only_saved_process_identity(tmp_path,emulator):
    path=create_project(tmp_path,bytes.fromhex('b82a4ccd21'))
    with Project(path) as project:
        with project.debugger(emulator,tmp_path) as first:
            prepare_native_fixture(first)
            entry_psp=first.registers()['segments']['ds']
            state=first.save_state()
            saved=json.loads(project.db.execute(
                'SELECT metadata FROM debug_artifacts WHERE id=?',(state['artifact'],)).fetchone()['metadata'])
            identity=saved.get('dos_process_identity')
            if os.environ.get(REQUIRE_COLD_PROCESS_IDENTITY)=='1':
                assert identity is not None, f'{REQUIRE_COLD_PROCESS_IDENTITY}=1 requires bridge-issued process identity'
            if identity is not None:
                artifact=project.db.execute(
                    'SELECT sha256 FROM debug_artifacts WHERE id=?',(state['artifact'],)).fetchone()
                assert identity['sha256']==artifact['sha256']
                assert type(identity['psp']) is int and 1 <= identity['psp'] <= 0xffff
                assert identity['psp']==int(entry_psp,16)
        with project.debugger(emulator,tmp_path) as second:
            second.load_state(state['artifact'])
            if identity is None:
                # Legacy native payloads carry no trusted selected-target
                # identity, so restoring their current PSP must not adopt it.
                result=second.run(timeout_ms=3000,guest_ms=30,fast_forward=True)
                assert result['outcome']=='guest_time',result
                assert 'guest_exit' not in result['session']['stop_reason']
            else:
                result=second.run(timeout_ms=3000,fast_forward=True)
                assert result['outcome']=='guest_exit',result
                info=result['session']['stop_reason']['guest_exit']
                assert info['requested_exit_code']==42 and not info['resident']
                assert int(info['psp'],16)==identity['psp']


@pytest.mark.skipif(os.environ.get(REQUIRE_COLD_PROCESS_IDENTITY)!='1',
                    reason=f'Set {REQUIRE_COLD_PROCESS_IDENTITY}=1 for candidate identity-negative acceptance')
def test_cold_restore_rejects_forged_process_identity_psp(tmp_path,emulator):
    path=create_project(tmp_path,bytes.fromhex('b82a4ccd21'))
    with Project(path) as project:
        with project.debugger(emulator,tmp_path) as first:
            prepare_native_fixture(first)
            state=first.save_state()
            original=project.db.execute(
                'SELECT * FROM debug_artifacts WHERE id=?',(state['artifact'],)).fetchone()
            metadata=json.loads(original['metadata'])
            identity=metadata.get('dos_process_identity')
            assert identity is not None, f'{REQUIRE_COLD_PROCESS_IDENTITY}=1 requires bridge-issued process identity'
            forged_psp=identity['psp'] ^ 1
            if forged_psp==0:
                forged_psp=2
            assert forged_psp!=identity['psp']
            forged_metadata=dict(metadata,
                dos_process_identity=dict(identity,psp=forged_psp))
            forged=project._debug_artifact(state['run'],'forged-process-identity.sav','state',
                                           bytes(original['data']),forged_metadata)
            preserved=project.db.execute(
                'SELECT * FROM debug_artifacts WHERE id=?',(state['artifact'],)).fetchone()
            assert preserved['sha256']==original['sha256']
            assert bytes(preserved['data'])==bytes(original['data'])
            assert preserved['metadata']==original['metadata']
        with project.debugger(emulator,tmp_path) as second:
            run_id=second.run_id
            process=second.rpc.process
            with pytest.raises(DebuggerError,match='did not confirm the saved DOS process identity'):
                second.load_state(forged['artifact'])
            assert second.closed and process.poll() is not None
            runs=[json.loads(row['evidence']) for row in project.db.execute(
                "SELECT evidence FROM debug_events WHERE run=? AND operation='run'",(run_id,))]
            assert not any('guest_exit' in item.get('session',{}).get('stop_reason',{}) for item in runs)


@pytest.mark.skipif(os.environ.get(REQUIRE_COLD_PROCESS_IDENTITY)!='1',
                    reason=f'Set {REQUIRE_COLD_PROCESS_IDENTITY}=1 for candidate native failure acceptance')
def test_direct_native_state_load_failure_retires_stopped_session(tmp_path,emulator):
    path=create_project(tmp_path,bytes.fromhex('ebfe'))
    missing_state=tmp_path/'missing-native-state.sav'
    assert not missing_state.exists()
    with Project(path) as project:
        with project.debugger(emulator,tmp_path) as debug:
            stopped=debug.run(timeout_ms=3000,guest_ms=30,fast_forward=True)
            assert stopped['outcome']=='guest_time' and stopped['session']['state']=='stopped',stopped
            run_id=debug.run_id
            process=debug.rpc.process

            # Use the native RPC directly: the Python load wrapper would close
            # the owner itself and conceal whether the bridge retired the session.
            with pytest.raises(DebuggerError,match=r'STATE_FAILED'):
                debug.call('state.load',{'path':str(missing_state)})

            status=debug.status()
            assert status['state']=='failed',status
            assert 'guest_exit' not in status.get('last_stop',{}),status
            with pytest.raises(DebuggerError):
                debug.call('execution.continue')
        assert debug.closed and process.poll() is not None

        run_events=[json.loads(row['evidence']) for row in project.db.execute(
            "SELECT evidence FROM debug_events WHERE run=? AND operation='run'",(run_id,))]
        assert run_events
        assert not any('guest_exit' in item.get('session',{}).get('stop_reason',{})
                       for item in run_events)
