"""Authored paged readbacks through the real provider and snapshot machinery."""
from copy import deepcopy
import hashlib
import json
import struct
from types import SimpleNamespace

import pytest

from fdisbull import runtime_desqview as dv
from fdisbull.memory_search_runtime import MemorySearchSessionMixin
from fdisbull.project import Project
from test_runtime_desqview import Native


EVIDENCE = dict(kind='modeled', reference='authored-physical-provider', sha256='a'*64)


class PhysicalSession(Native):
    def __init__(self, project):
        super().__init__()
        self.ram.extend(bytes((16 << 20)-len(self.ram)))
        self.project, self.version = project, project.version()
        self._runtime_epoch, self.closed = 'authored-epoch', False
        self.metadata = dict(source_sha256=project.source_sha256(), version_sha256=self.version['sha256'])
        self.vm.process = object()
        self.vm.machine_configuration = dict(memory_mib=16, cpus=1)
        self.vm.qmp = SimpleNamespace(call=lambda *args, **kwargs: dict(status='paused', running=False))
        self.observed['address_state'].update(a20=True, paging=True, paging_mode='legacy-32',
            control=dict(CR0='0x80000001', CR3='0x100000', CR4='0x0', EFER='0x0'))
        struct.pack_into('<I', self.ram, 0x100000, 0x101003)
        for index in range(1024):
            struct.pack_into('<I', self.ram, 0x101000+4*index, index*4096 | 3)
        self.linear, self.physical = 0x123ff0, (0x600000, 0x640000)
        for linear, physical in ((0x123000,self.physical[0]), (0x124000,self.physical[1])):
            struct.pack_into('<I', self.ram, 0x101000+4*(linear>>12), physical | 3)
        raw = project.regions(1)[0].data[:32]
        self.ram[self.physical[0]+4080:self.physical[0]+4096] = raw[:16]
        self.ram[self.physical[1]:self.physical[1]+16] = raw[16:]
        self.calls, self.on_read = [], None
        self.remote = SimpleNamespace(memory=self.memory_read)

    def _stopped(self):
        assert not self.closed
        return self.remote

    def registers(self):
        result = deepcopy(self.observed['registers'])
        result['address_state'] = deepcopy(self.observed['address_state'])
        return result

    def memory_read(self, address, length, *, space):
        assert space in ('physical','virtual')
        self.calls.append((space,address,length))
        if space=='physical':
            data=bytes(self.ram[address:address+length])
        else:
            out=bytearray()
            for offset in range(length):
                linear=address+offset
                pde=struct.unpack_from('<I',self.ram,0x100000+4*(linear>>22))[0]
                pte=struct.unpack_from('<I',self.ram,(pde & ~4095)+4*((linear>>12)&1023))[0]
                assert pde & 1 and pte & 1
                out.append(self.ram[(pte & ~4095)+(linear & 4095)])
            data=bytes(out)
        return self.on_read(space,address,length,data) if self.on_read else data

    def _artifact(self,*args):
        return self.project._debug_artifact(self.run_id,*args)


@pytest.fixture
def physical(tmp_path,monkeypatch):
    monkeypatch.setenv('FDISBULL_TARGET_STORE',str(tmp_path/'objects'))
    source=tmp_path/'authored.bin';source.write_bytes(bytes(range(256))*32)
    with Project.create(tmp_path/'physical.fdb',source,arch='x86',bits=32) as project:
        session=PhysicalSession(project)
        monkeypatch.setattr(dv,'_source',lambda _: (session.source,session.source_identity))
        with project.transaction(True):
            project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                (session.run_id,1,'authored',None,'stopped','{}'))
        provider=dv.discover(session);native=provider.current_identity()
        external='authored-desqview-source-task'
        task=project.runtime_task_start(session.run_id,external,EVIDENCE,capture_epoch=session._runtime_epoch)['task']
        document=project._mapping_task(task)
        document.pop('started');document.pop('ended')
        document['automatic_tracking']=dict(identity=dict(provider='source-qualified-desqview',native=deepcopy(native)))
        with project.transaction(True):
            project.db.execute('UPDATE runtime_mapping_tasks SET document=? WHERE id=?',(json.dumps(document),task))
        snapshot=MemorySearchSessionMixin.memory_snapshot(session,session.linear,length=32,task_id=external)
        session.calls.clear()
        yield SimpleNamespace(project=project,session=session,provider=provider,native=native,
                              task=task,snapshot=snapshot,external=external)


def test_provider_qualifies_complete_discontinuous_page_capture(physical):
    o=physical
    before=o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]
    certificate=o.provider.qualify_physical(o.snapshot['artifact'],o.native)
    from fdisbull.runtime_desqview_physical import FORMAT,SCOPE
    assert certificate==dict(format=FORMAT,qualified=True,snapshot=o.snapshot['artifact'],
        snapshot_sha256=o.snapshot['sha256'],mapping_id=o.snapshot['snapshot']['context']['mapping_id'],
        context_sha256=hashlib.sha256(json.dumps(o.snapshot['snapshot']['context'],sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        native_identity_sha256=hashlib.sha256(json.dumps(o.native,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        ranges=[dict(linear_start=0x123ff0,physical_start=0x600ff0,length=16,
                     sha256=hashlib.sha256(bytes(range(16))).hexdigest()),
                dict(linear_start=0x124000,physical_start=0x640000,length=16,
                     sha256=hashlib.sha256(bytes(range(16,32))).hexdigest())],
        verification_scope=SCOPE,passes=2)
    assert o.project.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]==before
    for address in (0x600ff0,0x640000):
        assert sum(space=='physical' and at==address and length==16 for space,at,length in o.session.calls)==2


def mutate_snapshot(o, change):
    from fdisbull.memory_search import snapshot_metadata
    row=o.project.db.execute('SELECT data,metadata FROM debug_artifacts WHERE id=?',
                             (o.snapshot['artifact'],)).fetchone()
    data=bytes(row['data']);metadata=json.loads(row['metadata'])
    change(metadata)
    context=metadata['snapshot']['context']
    metadata['snapshot']=snapshot_metadata(data,context=context,capture_id='authored-resealed')
    with o.project.transaction(True):
        o.project.db.execute('UPDATE debug_artifacts SET metadata=? WHERE id=?',
                             (json.dumps(metadata),o.snapshot['artifact']))


def test_two_virtual_aliases_can_share_a_physical_frame(physical):
    o=physical;s=o.session
    s.ram[0x600000:0x601000]=bytes(range(256))*16
    struct.pack_into('<I',s.ram,0x101000+4*0x124,0x600003)
    snapshot=MemorySearchSessionMixin.memory_snapshot(s,0x123000,length=8192,task_id=o.external)
    certificate=o.provider.qualify_physical(snapshot['artifact'],o.native)
    assert [row['physical_start'] for row in certificate['ranges']]==[0x600000,0x600000]
    assert [row['linear_start'] for row in certificate['ranges']]==[0x123000,0x124000]
    assert [row['length'] for row in certificate['ranges']]==[4096,4096]


@pytest.mark.parametrize('field,value', [('source_sha256','f'*64),('version_id',2),
    ('version_sha256','f'*64),('run_id','foreign'),('task_id','foreign'),('capture_epoch','stale')])
def test_foreign_source_run_task_version_and_epoch_are_identity_errors(physical,field,value):
    o=physical
    mutate_snapshot(o,lambda metadata:metadata['snapshot']['context'].__setitem__(field,value))
    with pytest.raises(dv.DesqviewProviderError):
        o.provider.qualify_physical(o.snapshot['artifact'],o.native)


def test_substituted_native_identity_is_not_a_physical_only_failure(physical):
    o=physical;other=deepcopy(o.native);other['handle']+=1
    with pytest.raises(dv.DesqviewProviderError,match='supplied native'):
        o.provider.qualify_physical(o.snapshot['artifact'],other)


@pytest.mark.parametrize('kind', ['unpaged','a20','pae','long-mode','cr3-reserved','unknown-mode'])
def test_unsupported_paging_refuses_without_qualified_ranges(physical,kind):
    from fdisbull.memory_search_runtime import _paused
    from fdisbull.runtime_desqview_physical import DesqviewPhysicalError
    o=physical;state=o.session.observed['address_state']
    if kind=='unpaged':state['paging']=False;state['control']['CR0']='0x1'
    elif kind=='a20':state['a20']=False
    elif kind=='pae':state['control']['CR4']='0x20'
    elif kind=='long-mode':state['control']['EFER']='0x500'
    elif kind=='cr3-reserved':state['control']['CR3']='0x100001'
    elif kind=='unknown-mode':state['paging_mode']='unknown'
    mutate_snapshot(o,lambda metadata:metadata['capture'].__setitem__('before',_paused(o.session)))
    with pytest.raises(DesqviewPhysicalError,match='legacy'):
        o.provider.qualify_physical(o.snapshot['artifact'],o.native)


@pytest.mark.parametrize('kind', ['physical','linear','pte'])
def test_same_identity_readback_or_pte_change_is_physical_failure(physical,kind):
    from fdisbull.runtime_desqview_physical import DesqviewPhysicalError
    o=physical
    if kind=='linear':o.session.ram[0x600ff5]^=1
    else:
        def changed(space,address,length,data):
            if space=='physical' and address==0x600ff0 and length==16:
                if kind=='physical':return bytes([data[0]^1])+data[1:]
                struct.pack_into('<I',o.session.ram,0x101000+4*0x124,0x650003)
            return data
        o.session.on_read=changed
    with pytest.raises(DesqviewPhysicalError):
        o.provider.qualify_physical(o.snapshot['artifact'],o.native)


@pytest.mark.parametrize('drift', ['cpu','identity','epoch','owner'])
def test_identity_drift_cannot_hide_behind_simultaneous_physical_mismatch(physical,drift):
    o=physical
    def changed(space,address,length,data):
        if space=='physical' and address==0x600ff0 and length==16:
            if drift=='cpu':o.session.observed['registers']['registers']['eip']='0x201'
            elif drift=='identity':
                o.session.add_task(0x9333,0x1550,0x1300,0x7000,0x100)
                o.session.select_task(0x9333,0x1550,0x1300)
            elif drift=='epoch':o.session._runtime_epoch='new-epoch'
            elif drift=='owner':o.session.vm.process=object()
            return bytes([data[0]^1])+data[1:]
        return data
    o.session.on_read=changed
    with pytest.raises(dv.DesqviewProviderError):
        o.provider.qualify_physical(o.snapshot['artifact'],o.native)


@pytest.mark.parametrize('kind',['short','io','timeout'])
def test_native_transport_and_deadline_failures_are_not_optional_physical_failures(physical,kind):
    from fdisbull.runtime_desqview_physical import DesqviewPhysicalError
    o=physical
    def failed(space,address,length,data):
        if space=='physical' and address==0x600ff0 and length==16:
            if kind=='short':return data[:-1]
            if kind=='io':raise OSError('authored native channel lost')
            raise TimeoutError('authored inherited deadline expired')
        return data
    o.session.on_read=failed
    with pytest.raises((ValueError,OSError,TimeoutError)) as error:
        o.provider.qualify_physical(o.snapshot['artifact'],o.native)
    assert not isinstance(error.value,DesqviewPhysicalError)


@pytest.mark.parametrize('kind',['layer','view','unknown-ram','over-ram','mmio','bytes-bound','page-bound'])
def test_view_ram_and_allocation_bounds_refuse_before_physical_publication(physical,kind):
    from fdisbull.runtime_desqview_physical import DesqviewPhysicalError
    o=physical
    if kind=='layer':o.session._layer_active=['authored-execute-layer']
    elif kind=='view':mutate_snapshot(o,lambda m:m['snapshot']['context'].__setitem__('qemu_memory_view',dict(view='execute')))
    elif kind=='unknown-ram':o.session.vm.machine_configuration={}
    elif kind=='over-ram':o.session.vm.machine_configuration['memory_mib']=4
    elif kind=='mmio':
        def patch(metadata):
            pages=metadata['capture']['pages'];pages[0]['physical']='0xa0000'
            metadata['capture']['mapping']['pages_sha256']=hashlib.sha256(json.dumps(pages,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            metadata['snapshot']['context']['mapping_id']=hashlib.sha256(json.dumps(metadata['capture']['mapping'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        mutate_snapshot(o,patch)
    elif kind=='bytes-bound':
        artifact=o.project._debug_artifact(o.session.run_id,'large.bin','memory-snapshot',bytes(1024*1024+1),{})
        with pytest.raises(DesqviewPhysicalError,match='1 MiB'):
            o.provider.qualify_physical(artifact['artifact'],o.native)
        return
    elif kind=='page-bound':
        def patch(metadata):
            pages=metadata['capture']['pages'];pages.extend(deepcopy(pages[-1]) for _ in range(255))
            metadata['capture']['mapping'].update(page_count=len(pages),pages_sha256=hashlib.sha256(json.dumps(pages,sort_keys=True,separators=(',',':')).encode()).hexdigest())
            metadata['snapshot']['context']['mapping_id']=hashlib.sha256(json.dumps(metadata['capture']['mapping'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        mutate_snapshot(o,patch)
    with pytest.raises(DesqviewPhysicalError):
        o.provider.qualify_physical(o.snapshot['artifact'],o.native)


@pytest.mark.parametrize('where',['rpc','session','vm','qmp','gdb'])
def test_inherited_expired_deadline_refuses_before_any_native_read(physical,where):
    import time
    o=physical;expired=time.monotonic()-1
    if where=='rpc':o.session._rpc_deadline=expired
    elif where=='session':o.session._deadline=expired
    elif where=='vm':o.session.vm.operation_deadline=expired
    elif where=='qmp':o.session.vm.qmp.operation_deadline=expired
    else:o.session.vm.gdb=SimpleNamespace(operation_deadline=expired)
    with pytest.raises(TimeoutError,match='inherited'):
        o.provider.qualify_physical(o.snapshot['artifact'],o.native)
    assert not o.session.calls


@pytest.mark.parametrize('deadline',[float('nan'),float('inf'),True,'later'])
def test_invalid_inherited_deadline_is_a_generic_failure(physical,deadline):
    from fdisbull.runtime_desqview_physical import DesqviewPhysicalError
    o=physical;o.session._rpc_deadline=deadline
    with pytest.raises(ValueError,match='finite') as error:
        o.provider.qualify_physical(o.snapshot['artifact'],o.native)
    assert not isinstance(error.value,DesqviewPhysicalError) and not o.session.calls


def test_midpass_cannot_widen_the_initial_inherited_deadline(physical,monkeypatch):
    from fdisbull import runtime_desqview_physical as physical_module
    o=physical;clock=SimpleNamespace(now=1.0)
    monkeypatch.setattr(physical_module.time,'monotonic',lambda:clock.now)
    o.session._rpc_deadline=2.0
    def expires(space,address,length,data):
        if space=='physical' and address==0x600ff0 and length==16:
            clock.now=3.0;o.session._rpc_deadline=100.0
        return data
    o.session.on_read=expires
    with pytest.raises(TimeoutError,match='inherited'):
        o.provider.qualify_physical(o.snapshot['artifact'],o.native)
    assert not any(space=='physical' and address==0x640000 and length==16 for space,address,length in o.session.calls)


@pytest.mark.parametrize('drift',['epoch','process'])
def test_final_identity_observation_cannot_change_owned_session_before_return(physical,monkeypatch,drift):
    o=physical;original=o.provider.current_identity;calls=0
    def identity():
        nonlocal calls
        value=original();calls+=1
        if calls==4:
            if drift=='epoch':o.session._runtime_epoch='changed-after-final-identity'
            else:o.session.vm.process=object()
        return value
    monkeypatch.setattr(o.provider,'current_identity',identity)
    with pytest.raises(dv.DesqviewProviderError,match='owner/run/epoch'):
        o.provider.qualify_physical(o.snapshot['artifact'],o.native)


@pytest.mark.parametrize('fails',[False,True])
def test_one_finite_transport_scope_restores_exact_parent_fields(physical,monkeypatch,fails):
    from fdisbull import runtime_desqview_physical as module
    o=physical;clock=SimpleNamespace(now=1.0)
    monkeypatch.setattr(module.time,'monotonic',lambda:clock.now)
    o.session._rpc_deadline=30.0;o.session.vm.operation_deadline=40.0
    o.session.vm.qmp.operation_deadline=25.0;o.session.vm.gdb=SimpleNamespace(operation_deadline=20.0)
    def read(space,address,length,data):
        assert o.session.vm.operation_deadline==o.session.vm.qmp.operation_deadline==o.session.vm.gdb.operation_deadline==11.0
        if fails and space=='physical' and address==0x600ff0:raise OSError('authored failure')
        return data
    o.session.on_read=read
    if fails:
        with pytest.raises(OSError):o.provider.qualify_physical(o.snapshot['artifact'],o.native)
    else:o.provider.qualify_physical(o.snapshot['artifact'],o.native)
    assert o.session._rpc_deadline==30.0 and o.session.vm.operation_deadline==40.0
    assert o.session.vm.qmp.operation_deadline==25.0 and o.session.vm.gdb.operation_deadline==20.0


def test_lazily_admitted_debugger_restores_previous_vm_allowance(physical):
    o=physical
    assert not hasattr(o.session.vm,'gdb')
    def read(space,address,length,data):
        if not hasattr(o.session.vm,'gdb'):
            o.session.vm.gdb=SimpleNamespace(operation_deadline=o.session.vm.operation_deadline)
        return data
    o.session.on_read=read
    o.provider.qualify_physical(o.snapshot['artifact'],o.native)
    assert o.session.vm.gdb.operation_deadline is None
    assert not hasattr(o.session.vm,'operation_deadline')
    assert not hasattr(o.session.vm.qmp,'operation_deadline')


def test_final_observation_expiry_never_returns_a_certificate_and_restores_bound(physical,monkeypatch):
    from fdisbull import runtime_desqview_physical as module
    o=physical;clock=SimpleNamespace(now=1.0);original=o.provider.current_identity;calls=0
    monkeypatch.setattr(module.time,'monotonic',lambda:clock.now)
    def identity():
        nonlocal calls
        value=original();calls+=1
        if calls==4:clock.now=12.0
        return value
    monkeypatch.setattr(o.provider,'current_identity',identity)
    with pytest.raises(TimeoutError):o.provider.qualify_physical(o.snapshot['artifact'],o.native)
    assert not hasattr(o.session.vm,'operation_deadline') and not hasattr(o.session.vm.qmp,'operation_deadline')
