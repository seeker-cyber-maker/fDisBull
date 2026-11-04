"""Compiled bridge + real inherited socket tests, not a full ScummVM build.

The driver supplies scripted hook calls. Separate opt-in tests below require
an actual instrumented ScummVM executable and a caller-owned story.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import time

import pytest

from fdisbull.scummvm_rpc import ScummVMError, ScummVMRPC
from fdisbull.scummvm_zcode import ScummVMZCodeSession

ROOT = Path(__file__).resolve().parents[1]


def invented(mode=0):
    raw=bytearray(2048)
    raw[0]=3
    for at,value in ((2,1),(4,1024),(6,1024),(8,900),(10,544),(12,64),
                     (14,1024),(24,640),(26,1024),(613,615)):
        raw[at:at+2]=value.to_bytes(2,'big')
    raw[18:24]=b'000001'
    raw[900:904]=bytes([0,4,0,0])
    raw[1024:1100]=bytes([0xb4])*76 # Authored no-op bytes; driver does NOT execute.
    raw[100]=mode
    raw[28:30]=(sum(raw[64:])&65535).to_bytes(2,'big')
    return bytes(raw)


@pytest.fixture(scope='session')
def native_driver(tmp_path_factory):
    compiler=shutil.which('g++') or shutil.which('clang++')
    if compiler is None:
        pytest.skip('Native bridge driver needs C++11 compiler')
    dest=tmp_path_factory.mktemp('zcode-native-driver')/'driver'
    proc=subprocess.run([compiler,'-std=c++11','-Wall','-Wextra','-Werror','-O1',
                         '-fno-exceptions','-fno-rtti','-fsanitize=undefined',
                         '-fno-sanitize-recover=all','-I',str(ROOT),
                         str(ROOT/'tests/fixtures/zcode_agent_driver.cpp'),'-o',str(dest)],
                        capture_output=True,text=True,timeout=60)
    assert proc.returncode==0, proc.stdout+proc.stderr
    return dest


@pytest.fixture
def launch(native_driver,tmp_path):
    sessions=[]
    def create(mode=0, raw=None):
        path=tmp_path/f'authored-{len(sessions)}-{mode}.z3'
        path.write_bytes(invented(mode) if raw is None else raw)
        s=ScummVMZCodeSession(native_driver,path,runtime_parent=tmp_path,boot_timeout_ms=3000)
        sessions.append(s)
        return s
    yield create
    for s in sessions: s.close()


def test_native_socket_launch_full_source_binding_and_passive_reads(launch):
    s=launch()
    initial=s.state()
    assert initial['phase']=='before_opcode' and initial['pc']==1024
    assert s.metadata['native_source_bytes']==2048
    assert s.metadata['source_binding']=='all declared original bytes compared'
    assert s.metadata['original_x86_executed'] is False
    assert s.state()==initial
    assert s.memory(80,1)==b'\0'
    assert s.state()==initial
    one=s.step()
    assert one['completed_dispatches']==1 and one['pc']==1025
    assert one['text']=='A' and s.memory(80,1)==b'\x07'
    assert s.output()['text']=='' # Capture drains once, no guest advancement.


def test_complete_readback_detects_changed_unexecuted_source(native_driver,tmp_path):
    path=tmp_path/'wrong.z3'; path.write_bytes(invented(1))
    spawned=[]
    with pytest.raises(ScummVMError,match='differs'):
        ScummVMZCodeSession(native_driver,path,runtime_parent=tmp_path,
                            boot_timeout_ms=3000,on_spawn=spawned.append)
    assert spawned and spawned[0].poll() is not None
    assert not list(tmp_path.glob('fdisbull-zcode-*'))


def test_breakpoint_hit_resume_guard_and_removal(launch):
    s=launch()
    b=s.breakpoint(1025,expected_hex='b4')
    hit=s.run()
    assert hit['reason']=='breakpoint' and hit['pc']==1025
    assert hit['completed_dispatches']==1
    stepped=s.step()
    assert stepped['completed_dispatches']==1 and stepped['pc']==1026
    assert s.delete_breakpoint(b['breakpoint_id'])['removed'] is True
    assert s.run()['reason']=='input_pending'


def test_breakpoint_rehits_after_explicit_resume(launch):
    s=launch(); s.breakpoint(1040)
    a=s.run()
    assert a['reason']=='breakpoint'
    b=s.run()
    assert b['reason']=='input_pending' and b['completed_dispatches']==0
    r=s.command('alpha',expected_revision=s.state()['revision'])
    assert r['reason']=='breakpoint' and r['text']=='[alpha]\n'


def test_input_request_revision_status_and_completion(launch):
    s=launch(); a=s.run()
    assert a['reason']=='input_pending' and a['completed_dispatches']==2
    state=s.state(); assert state['input_kind']=='line'
    before=s.memory(64,64)
    assert s.run()['reason']=='input_pending' # No input supplied, no spin/block.
    assert s.memory(64,64)==before
    r=s.command('alpha',expected_revision=state['revision'])
    assert r['text']=='[alpha]\n' and r['completed_dispatches']==1
    assert r['input_receipt']['consumed'] is False # Queue acknowledgement only.
    assert any(e['window']==1 and e['text']=='S' for e in r['events'])
    with pytest.raises(ValueError,match='Stale'):
        s.command('duplicate',expected_revision=state['revision'])
    assert s.state()['phase']=='input_pending'
    s.command('beta',expected_revision=s.state()['revision'])
    done=s.command('gamma',expected_revision=s.state()['revision'])
    assert done['reason']=='quit' and done['phase']=='exited'
    assert s.state()['phase']=='exited'
    with pytest.raises(ValueError,match='exited'): s.run()


def test_nested_dispatch_not_claimed_as_outer_completion(launch):
    s=launch(2); s.step(); nested=s.step()
    assert nested['text']=='N' and nested['completed_dispatches']==1
    assert nested['starting_dispatch_completed'] is None
    events=s.trace()['events']
    assert events[-1]['kind']=='after'
    assert events[-1]['position']['parent_span_id']>0
    assert s.step()['completed_dispatches']==1


def test_trace_capacity_exact_drop_count(launch):
    s=launch(3); s.run(max_instructions=10000)
    t=s.trace()
    assert len(t['events'])==2048 and t['dropped']==2357
    assert t['whole_run_complete'] is False


def test_native_cooperative_host_budget_stops(launch):
    s=launch(5)
    stop=s.run(timeout_ms=100)
    assert stop['reason']=='host_timeout'
    assert 2<=stop['completed_dispatches']<102


def test_hard_timeout_reaps_non_yielding_native_callback(launch):
    s=launch(4); process=s.rpc.process
    with pytest.raises(ScummVMError,match='Timed out'):
        s.run(timeout_ms=150)
    assert s.closed and process.poll() is not None
    with pytest.raises(ScummVMError,match='closed'): s.run()


def test_owner_close_reaps_child_and_cleans_runtime(launch):
    s=launch(); p=s.rpc.process; private=Path(s.temporary.name)
    s.run(); s.close(); s.close()
    assert p.poll() is not None and not private.exists()


def test_private_source_drift_aborts_without_running(launch):
    s=launch(); p=s.rpc.process
    s.staged_story.chmod(0o600)
    s.staged_story.write_bytes(b'changed')
    with pytest.raises(ScummVMError,match='changed'): s.state()
    assert s.closed and p.poll() is not None


@pytest.mark.parametrize('value',[True,0,-1,1.2,1000001])
def test_invalid_execution_budgets_leave_state_unchanged(launch,value):
    s=launch(); before=s.state()
    with pytest.raises(ValueError): s.run(max_instructions=value)
    assert s.state()==before


@pytest.mark.parametrize('value',['non-ascii-\u2603','x'*33,'embedded\nline'])
def test_invalid_input_does_not_consume_request(launch,value):
    s=launch(); s.run(); before=s.state()
    with pytest.raises(ValueError): s.command(value,expected_revision=before['revision'])
    assert s.state()==before


def test_save_opcode_is_explicitly_refused(launch):
    raw=bytearray(invented()); raw[1025]=0xb5
    raw[28:30]=(sum(raw[64:])&65535).to_bytes(2,'big')
    s=launch(raw=bytes(raw)); result=s.run()
    assert result['reason']=='unsupported_save_restore' and s.state()['faulted']
    with pytest.raises(ValueError,match='faulted'): s.run()


def test_raw_owner_eof_exits_native_process(native_driver,tmp_path):
    (tmp_path/'story.z3').write_bytes(invented())
    parent,child=socket.socketpair()
    env=dict(os.environ,FDISBULL_SCUMMVM_FD=str(child.fileno()))
    p=subprocess.Popen([str(native_driver),'--path='+str(tmp_path)],env=env,
                       pass_fds=(child.fileno(),),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    child.close()
    try:
        parent.sendall(b'{"id":1,"op":"hello"}\n'); parent.settimeout(3)
        assert json.loads(parent.recv(4096))['ok'] is True
        parent.close()
        assert p.wait(timeout=3)==0
    finally:
        parent.close()
        if p.poll() is None: p.kill(); p.wait()


@pytest.mark.parametrize('bad',[
    b'{"id":1,"id":2,"op":"hello"}\n',
    b'{"id":true,"op":"hello"}\n',
    b'{"id":1.0,"op":"hello"}\n',
    b'{"id":01,"op":"hello"}\n',
    b'{"id":1,"op":"hello","x":[]}\n',
    b'{"id":1,"op":"hello","x":9007199254740992}\n',
    b'{"id":1,"op":"hello","x":"\\uD800"}\n',
])
def test_native_json_parser_fails_closed(native_driver,tmp_path,bad):
    (tmp_path/'story.z3').write_bytes(invented())
    a,b=socket.socketpair()
    p=subprocess.Popen([str(native_driver),'--path='+str(tmp_path)],
                       env=dict(os.environ,FDISBULL_SCUMMVM_FD=str(b.fileno())),
                       pass_fds=(b.fileno(),),stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    b.close()
    try:
        a.sendall(bad); a.settimeout(3)
        reply=json.loads(a.recv(4096)); assert reply['ok'] is False
        assert p.wait(timeout=3)==74
    finally:
        a.close()
        if p.poll() is None: p.kill(); p.wait()


def test_real_scummvm_owned_zork_acceptance(tmp_path):
    binary=os.environ.get('FDISBULL_SCUMMVM_ZCODE_EXE')
    story=os.environ.get('FDISBULL_ZORK_STORY')
    extra=os.environ.get('FDISBULL_SCUMMVM_ENGINE_DATA')
    if not binary or not story or not extra:
        pytest.skip('Requires actual patched ScummVM + private owned Zork + engine data')
    with ScummVMZCodeSession(binary,story,runtime_parent=tmp_path,extra_path=extra) as s:
        assert s.state()['phase']=='before_opcode'
        assert s.step()['completed_dispatches']==1
        first=s.run(max_instructions=1000000,timeout_ms=30000)
        assert first['reason']=='input_pending' and first['text']
        for command in ('open mailbox','take leaflet','north','east','open window','in'):
            state=s.state()
            r=s.command(command,expected_revision=state['revision'],max_instructions=1000000,timeout_ms=30000)
            assert r['reason']=='input_pending' and r['text']
        p=s.rpc.process
    assert p.poll() is not None


def test_compound_deadline_is_not_reset_after_preflight(launch,monkeypatch):
    s=launch(); before=s.state(); original=s.state
    def slow_state():
        result=original(); time.sleep(.06); return result
    monkeypatch.setattr(s,'state',slow_state)
    with pytest.raises(TimeoutError,match='before execution'):
        s.run(timeout_ms=100)
    monkeypatch.setattr(s,'state',original)
    assert s.state()==before


def test_stock_or_wrong_backend_is_not_admitted(native_driver,tmp_path):
    game=tmp_path/'data'; game.mkdir(); (game/'story.z3').write_bytes(invented())
    processes=[]
    with pytest.raises(ScummVMError,match='AGI'):
        ScummVMRPC(native_driver,game,game_id='kq1',engine='agi',
                   runtime_parent=tmp_path,boot_timeout_ms=3000,on_spawn=processes.append)
    assert len(processes)==1 and processes[0].poll() is not None


def test_cli_uses_native_process_not_word16(native_driver,tmp_path):
    story=tmp_path/'story.z3'; story.write_bytes(invented())
    commands=tmp_path/'commands.json'; commands.write_text('["a","b","c"]')
    import sys
    result=subprocess.run([sys.executable,'-m','fdisbull.scummvm_zcode','--executable',str(native_driver),
                           '--story',str(story),'--runtime-parent',str(tmp_path),
                           '--commands',str(commands)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    rows=[json.loads(line) for line in result.stdout.splitlines()]
    assert len(rows)==4 and rows[-1]['result']['reason']=='quit'
    assert rows[1]['result']['text']=='[a]\n'
    assert rows[0]['metadata']['backend']=='scummvm-zcode'
    assert not list(tmp_path.glob('fdisbull-zcode-*'))


def hook_module():
    file=ROOT/'experimental/scummvm/zcode/apply.py'
    spec=importlib.util.spec_from_file_location('zcode_hooks',file)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('path,body,hook',[
    ('mem.cpp','\tloadMemory();\n','agent().loaded'),
    ('processor.cpp','void Processor::interpret() {\n\tdo {\n\t\tzbyte opcode;\n\t\tCODE_BYTE(opcode);\n#if defined(DJGPP) && defined(SOUND_SUPPORT)\n','agent().before'),
    ('glk_interface.cpp','zchar GlkInterface::os_read_line(int max, zchar *buf, int timeout, int width, int continued) {\n}\nzchar GlkInterface::os_read_key(int timeout, bool show_cursor) {\n}\n','agent().input'),
    ('processor_screen.cpp','void Processor::screen_char(zchar c) {\n}\n','agent().character'),
    ('zcode.cpp','\t// Game loop\n\tinterpret();\n','agent().exited'),
])
def test_hook_generator_exact_anchors_and_no_double_apply(path,body,hook):
    module=hook_module()
    # Deliberately minimal authored anchor fixture, not a full upstream source.
    source='#include "authored.h"\n'+body
    target='engines/glk/zcode/'+path
    result=module.transform(target,source)
    assert hook in result and 'FDISBULL_ZCODE_AGENT' in result
    if path=='processor.cpp':
        assert result.index('agent().before')<result.index('CODE_BYTE(opcode)')
        assert result.index('agent().after')>result.index('CODE_BYTE(opcode)')
    with pytest.raises(ValueError,match='already'):
        module.transform(target,result)
    with pytest.raises(ValueError,match='anchor'):
        module.transform(target,source+body)


def test_hook_prepare_refuses_wrong_checkout(tmp_path):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    (tmp_path/'authored.txt').write_text('synthetic checkout\n')
    subprocess.run(['git','-C',str(tmp_path),'add','.'],check=True)
    subprocess.run(['git','-C',str(tmp_path),'-c','user.name=Test','-c','user.email=test@example.invalid',
                    'commit','-qm','authored fixture'],check=True)
    with pytest.raises(ValueError,match='Expected upstream'):
        hook_module().prepare(tmp_path)
