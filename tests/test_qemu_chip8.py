"""Host-only contracts for the CHIP-8 architecture adapter; no guest is run."""
from types import SimpleNamespace
import threading
import pytest
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_chip8 import Chip8DebugSession, REGISTER_NAMES


class Remote:
    def __init__(self):
        self.bytes=bytearray(4096);self.packet_size=96;self.requests=[]
        self.values={name:'0x0' for name in REGISTER_NAMES};self.values['pc']='0x200'
        self.reply=(b'T05',False)
    def registers(self):return dict(self.values)
    def set_register(self,name,value):
        if name=='sp' and value<int(self.values['sp'],16):
            for i in range(value,16):self.values['stack%d'%i]='0x0'
        self.values[name]=hex(value)
    def request(self,command):
        self.requests.append(command)
        if command[0]=='m':
            address,size=(int(x,16) for x in command[1:].split(','));return self.bytes[address:address+size].hex().encode()
        if command[0]=='M':
            location,raw=command[1:].split(':');address,size=(int(x,16) for x in location.split(','))
            self.bytes[address:address+size]=bytes.fromhex(raw);return b'OK'
        if command[0] in 'Zz':return b'OK'
        raise AssertionError(command)
    def execute(self,command,timeout):return self.reply


class VM:
    def __init__(self):
        self.lock=threading.RLock();self.gdb=Remote();self.process=SimpleNamespace(poll=lambda:None)
        self.fault={'faulted':False,'fault-code':0,'fault-pc':0,'fault-opcode':0,
                    'profile':'chip8-classic-pilot-default-v1','cpu-subset':'fdisbull-chip8-cpu-smoke-1'}
        self.qmp=SimpleNamespace(call=lambda name:self.fault if name=='query-chip8-fault' else {'running':False});self.closed=False
    def close(self):self.closed=True


def session():
    s=Chip8DebugSession.__new__(Chip8DebugSession);s.vm=VM();s.closed=False
    s.identity={'cpu_subset':'fdisbull-chip8-cpu-smoke-1'}
    s.project=SimpleNamespace(_live_debuggers=[s],db=SimpleNamespace(in_transaction=False));s.breakpoints={};s.next_bp=1
    s._event=lambda *args:None
    return s


def test_registers_are_chip8_direct_pc_without_x86_hmp():
    s=session();r=s.registers()
    assert r['architecture']=='chip8' and r['linear_pc']=='0x200' and r['registers']['v0']=='0x0'
    s.vm.gdb.values['sp']='0x11'
    with pytest.raises(DebuggerError,match='range'):s.registers()


def test_flat_chunked_ram_and_guarded_edits():
    s=session();data=bytes(range(100))
    result=s.write_memory('0x200',data.hex(),expected_hex=bytes(100).hex())
    assert result['after_hex']==data.hex() and s.memory(0x200,length=100,space='virtual')['hex']==data.hex()
    assert sum(x.startswith('M') for x in s.vm.gdb.requests)>1
    with pytest.raises(DebuggerError,match='guard'):s.write_memory(0x200,'ff',expected_hex='ff')
    with pytest.raises(ValueError):s.memory(4095,length=2)
    assert not s.closed


def test_register_edits_validate_all_guards_before_mutation():
    s=session();s.write_registers({'v0':{'expected':0,'value':7}})
    assert s.registers()['registers']['v0']=='0x7'
    with pytest.raises(DebuggerError,match='guard'):
        s.write_registers({'v0':{'expected':7,'value':8},'v1':{'expected':1,'value':9}})
    assert s.registers()['registers']['v0']=='0x7'
    s.write_registers({'pc':{'expected':512,'value':4096}})
    assert s.registers()['linear_pc']=='0x1000'
    s.write_registers({'i':{'expected':0,'value':4096}})
    assert s.registers()['registers']['i']=='0x1000'
    with pytest.raises(ValueError):s.write_registers({'pc':{'expected':4096,'value':65536}})


def test_guarded_stack_batch_uses_final_depth_before_mutation():
    s=session();r=s.vm.gdb
    with pytest.raises(ValueError,match='Inactive'):
        s.write_registers({'stack0':{'expected':0,'value':0x222}})
    assert r.values['sp']=='0x0' and r.values['stack0']=='0x0'
    # Stack entry appears before SP in caller order; native must see SP first.
    s.write_registers({'stack0':{'expected':0,'value':0x222},'sp':{'expected':0,'value':1}})
    assert r.values['sp']=='0x1' and r.values['stack0']=='0x222'
    with pytest.raises(ValueError,match='Inactive'):
        s.write_registers({'sp':{'expected':1,'value':0},'stack0':{'expected':0x222,'value':1}})
    assert r.values['sp']=='0x1' and r.values['stack0']=='0x222'
    s.write_registers({'stack0':{'expected':0x222,'value':0},'sp':{'expected':1,'value':0}})
    assert r.values['sp']=='0x0' and r.values['stack0']=='0x0'


def test_real_stop_classification_uses_chip8_pc_and_timeout():
    s=session();bp=s.breakpoint(0x200);result=s.run()
    assert result['outcome']=='breakpoint' and result['session']['stop_reason']['breakpoint_ids']==[bp['breakpoint_id']]
    s.delete_breakpoint(bp['breakpoint_id']);assert s.step()['outcome']=='step'
    s.vm.gdb.reply=(b'T02',True);assert s.run()['outcome']=='timeout'
    with pytest.raises(ValueError,match='hooks'):s.run(stop_on_hook=True)


def test_unsupported_features_are_explicit():
    for key in ('frame','layers','hooks','histories','trials','input','timers'):
        assert Chip8DebugSession.capabilities[key] is False


def test_project_profile_admission_and_run_lifecycle(tmp_path,monkeypatch):
    import fdisbull.qemu_chip8 as module
    from fdisbull.project import Project
    rom=tmp_path/'probe.ch8';rom.write_bytes(bytes.fromhex('6001'))
    monkeypatch.setattr(module.subprocess,'check_output',lambda *a,**k:'QEMU emulator version fixture\n')
    monkeypatch.setattr(module,'_Owner',lambda *a,**k:VM())
    with Project.create(tmp_path/'probe.fdb',rom,arch='chip8',bits=16) as project:
        with Chip8DebugSession(project,'/usr/bin/true',rom=rom) as debug:
            assert debug.identity['profile']=='chip8-classic-pilot-default-v1'
            assert debug.status()['state']=='stopped'
            result=debug.step();assert result['outcome']=='step'
            assert project.db.execute('select count(*) from debug_events where run=?',(debug.run_id,)).fetchone()[0]==1
            run=debug.run_id
        row=project.db.execute('select ended,state from debug_runs where id=?',(run,)).fetchone()
        assert row['ended'] and row['state']=='exited'


def test_native_fault_wins_over_same_pc_breakpoint():
    s=session();s.breakpoint(0x200)
    s.vm.fault.update({'faulted':True,'fault-code':1,'fault-pc':0x200,'fault-opcode':0xffff})
    result=s.run()
    assert result['outcome']=='exception' and result['fault']['fault-code']==1
    assert result['session']['stop_reason']['breakpoint_ids']==[]


def test_snapshot_identity_rejected_before_replacing_owner(tmp_path,monkeypatch):
    import fdisbull.qemu_chip8 as module
    from fdisbull.project import Project
    rom=tmp_path/'probe.ch8';rom.write_bytes(bytes.fromhex('6001'))
    monkeypatch.setattr(module.subprocess,'check_output',lambda *a,**k:'QEMU emulator version fixture\n')
    def owner(*a,**k):
        vm=VM();vm.checkpoint_disk=tmp_path/'dummy.qcow2';return vm
    monkeypatch.setattr(module,'_Owner',owner)
    with Project.create(tmp_path/'probe.fdb',rom,arch='chip8',bits=16) as project:
        with Chip8DebugSession(project,'/usr/bin/true',rom=rom,checkpoint_tool='/usr/bin/true') as debug:
            bad=project._debug_artifact(debug.run_id,'bad.qcow2','state',b'not-qcow',
                {'format':'fdisbull-qemu-chip8-state-1','identity':{'source_sha256':'different'}})
            original=debug.vm
            with pytest.raises(ValueError,match='identity'):debug.load_state(bad['artifact'])
            assert debug.vm is original and not original.closed


@pytest.mark.parametrize('remove',[False,True])
def test_uncertain_breakpoint_transport_closes_owner(remove):
    s=session()
    if remove:point=s.breakpoint(0x200)['breakpoint_id']
    def fail(command):raise OSError('connection lost after dispatch')
    s.vm.gdb.request=fail
    with pytest.raises(OSError):
        if remove:s.delete_breakpoint(point)
        else:s.breakpoint(0x200)
    assert s.closed and s.vm.closed


def test_execution_error_preserves_bounded_native_diagnostics_before_close():
    s=session();calls=[]
    def execute(*args):raise DebuggerError('GDB channel closed')
    s.vm.gdb.execute=execute
    def diagnostics():
        calls.append(('diagnostics',s.vm.closed))
        return {'native_exit_code':-6,'native_stderr':'native assertion'}
    s.vm.diagnostics=diagnostics
    with pytest.raises(DebuggerError) as error:s.step()
    assert calls==[('diagnostics',False)] and s.vm.closed
    assert error.value.result['native_exit_code']==-6
    assert error.value.result['native_stderr']=='native assertion'


def test_owner_diagnostics_bounds_tail_and_reports_exit(tmp_path):
    from fdisbull.qemu_chip8 import _Owner
    owner=_Owner.__new__(_Owner);owner.log_path=tmp_path/'qemu.log'
    owner.log_path.write_bytes(b'A'*17000+b'final error')
    owner.process=SimpleNamespace(poll=lambda:42)
    info=owner.diagnostics()
    assert info['native_exit_code']==42 and info['native_stderr'].endswith('final error')
    assert len(info['native_stderr'].encode())==16384


def test_timeout_recovery_has_reserved_outer_budget_and_single_dispatch(monkeypatch):
    import fdisbull.qemu_chip8 as module
    clock=[1000.0];monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
    s=session();calls=[];events=[];s._event=lambda name,value:events.append((name,value))
    def timed(command,timeout):
        calls.append((command,timeout));clock[0]+=(timeout+8)/1000
        return b'T02',True
    s.vm.gdb.execute=timed
    result=s.run(timeout_ms=120)
    assert result['outcome']=='timeout' and result['timed_out'] and not s.closed
    assert len(calls)==1 and calls[0][0]=='c' and 1<=calls[0][1]<=90
    assert len(events)==1 and events[0][1]['outcome']=='timeout'


def test_stop_recovery_that_truly_exceeds_outer_deadline_closes_owner(monkeypatch):
    import fdisbull.qemu_chip8 as module
    clock=[1000.0];monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
    s=session();calls=[]
    def slow(command,timeout):
        calls.append((command,timeout));clock[0]+=.09
        return b'T02',True
    s.vm.gdb.execute=slow
    with pytest.raises(TimeoutError) as error:s.run(timeout_ms=50)
    assert len(calls)==1 and s.closed and error.value.result['outcome']=='timeout'


def test_tiny_predispatch_budget_refusal_keeps_owner_and_sends_no_execution(monkeypatch):
    import fdisbull.qemu_chip8 as module
    monkeypatch.setattr(module.time,'monotonic',lambda:1000.0)
    s=session();calls=[]
    s.vm.gdb.execute=lambda *args:calls.append(args)
    with pytest.raises(TimeoutError):s.run(timeout_ms=2)
    assert not calls and not s.closed and not s.vm.closed
