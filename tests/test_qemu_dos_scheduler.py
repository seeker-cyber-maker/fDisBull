"""Host-only scheduler admission and checkpoint policy; no guest execution."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.qemu_dos_tasks import FORMAT as TASK_FORMAT, _identifier
from fdisbull.qemu_dos_scheduler import (COMMANDS, FORMAT, MODEL, GPRS, QemuDOSSchedulerMixin,
    _context, _mutate, _native_status, _status as _scheduler_status, after_scheduler_stop,
    capture_scheduler, validate_scheduler, verify_scheduler)


def _binding(cookie=1, nonce='22'*16):
    value = dict(format=TASK_FORMAT, anchor_address=0x5000, monitor_uuid='11'*16,
                 cookie=cookie, incarnation=1, process_nonce=nonce)
    value['task_id'] = _identifier(value)
    return value


def _key(binding):
    return dict(uuid=binding['monitor_uuid'],cookie=binding['cookie'],incarnation=binding['incarnation'])


def _slot(binding):
    return dict(_key(binding),slot=0,runnable=True,blocked=False,retired=False,
        **{'context-valid':True,'context-sha256':'aa'*32,'frame-sha256':'bb'*32,
           'execution-sha256':'cc'*32,'execution-bytes':0,'eip':0x100,'esp':0xff00,
           'eflags':0x202,'interrupt-depth':0,'mode':'real','pages':[]})


def _status(binding):
    return {'model':MODEL,'api-version':1,'epoch':1,'generation':1,'runqueue-generation':1,
        'enabled':True,'yield-vector':0x60,'block-vector':0x62,'pending-irq-count':0,
        'pending-switch':False,'selected-uuid':binding['monitor_uuid'],
        'selected-cookie':binding['cookie'],'selected-incarnation':binding['incarnation'],
        'tasks':[_slot(binding)]}


def _cpu(binding):
    regs = [0]*16; regs[4] = 0xff00
    seg = dict(selector=0x100,base=0x1000,limit=0xffff,flags=0)
    return dict(_key(binding),live=True,mode='real',registers=regs,eip=0x100,eflags=0x202,
        cr0=0x10,cr2=0,cr3=0,cr4=0,efer=0,**{'a20-mask':0xffffffff,
        'context-sha256':'aa'*32,'xstate-sha256':'dd'*32,'segments':[deepcopy(seg) for _ in range(6)],
        'system-segments':[deepcopy(seg) for _ in range(4)],'interrupt-depth':0,'frames':[]})


class _Qmp:
    def __init__(self, status, cpu):
        self.status, self.cpu = status, cpu
        self.calls = []
        self.failure = None
    def call(self, command, arguments=None):
        self.calls.append((command, arguments))
        if self.failure: raise self.failure
        if command == 'x-fdisbull-task-scheduler-observe': return deepcopy(self.status)
        if command == 'x-fdisbull-task-context-read': return deepcopy(self.cpu)
        return {}


class _Session(QemuDOSSchedulerMixin):
    def __init__(self):
        self.binding = _binding(); child = _binding(2)
        self.vm = SimpleNamespace(qmp=_Qmp(_status(self.binding),_cpu(self.binding)),qmp_commands=COMMANDS)
        self.metadata = {'source_sha256':'s','version_sha256':'v'}
        self._dos_task_binding = self.binding
        self._dos_task_views = {self.binding['task_id']:{'binding':self.binding,'retired':False,'pages':[]},
                                child['task_id']:{'binding':child,'retired':False,'pages':[]}}
        self._process = {'source_mapping':{'live_ranges':[]}, 'allocation':{'start':0x1000,'end':0x20000}}
        self._dos_scheduler = {'format':FORMAT,'enabled':True,'native_epoch':1,
                               'slots':{self.binding['task_id']:{'binding':self.binding}}}
        self.child = child
        self.closed = False
        self.project = SimpleNamespace(db=SimpleNamespace(in_transaction=False))
    def close(self): self.closed = True
    def _layer_spans(self, address, length, space):
        if address != 'entry': raise ValueError('source outside owned module')
        return 0x1100,None,[],{}


@pytest.mark.parametrize('field,value', [
    ('model','bad'),('api-version',True),('epoch',0),('generation',0),
    ('pending-switch',None),('tasks','bad'),('yield-vector',0x61),
])
def test_scheduler_rejects_malformed_status(field,value):
    s = _Session(); s.vm.qmp.status[field] = value
    with pytest.raises(DebuggerError): _native_status(s.vm)


def test_scheduler_fault_is_preserved_as_a_refusal_receipt():
    s = _Session(); s.vm.qmp.status['fault'] = 'unowned interrupt stack'
    with pytest.raises(DebuggerError, match='unowned interrupt stack') as caught:
        _native_status(s.vm)
    assert caught.value.native_scheduler == s.vm.qmp.status


@pytest.mark.parametrize('field,value', [
    ('registers',[0]*15),('context-sha256','bad'),('interrupt-depth',1),
    ('segments',[]),('live',1),
])
def test_scheduler_rejects_malformed_cpu_context(field,value):
    s = _Session(); s.vm.qmp.cpu[field] = value
    with pytest.raises(DebuggerError): _context(s.vm,s.binding)


@pytest.mark.parametrize('failure,closed', [(DebuggerError('PRECONDITION: refused'),False),
    (DebuggerError('transport failure'),True),(TimeoutError('lost response'),True)])
def test_scheduler_mutation_failure_closes_on_uncertainty(failure,closed):
    s = _Session(); s.vm.qmp.failure = failure
    with pytest.raises(type(failure)): _mutate(s,'x-fdisbull-task-slot-fork',{})
    assert s.closed is closed


def test_scheduler_all_blocked_no_selected_owner_is_a_live_idle_stop():
    session = _Session()
    status = session.vm.qmp.status
    status.update({'selected-uuid': '', 'selected-cookie': 0, 'selected-incarnation': 0})
    status['tasks'][0].update(runnable=False, blocked=True)
    assert _scheduler_status(session) == status
    result = {'outcome': 'breakpoint', 'session': {'stop_reason': {'breakpoint_ids': []}}}
    observed = after_scheduler_stop(session, result)
    assert observed['outcome'] == 'scheduler-idle' and not session.closed


@pytest.mark.parametrize('private_cookie,accepted', [(1, True), (2, False)])
def test_scheduler_adoption_requires_matching_committed_private_selection(monkeypatch, private_cookie, accepted):
    import fdisbull.qemu_dos_scheduler as scheduler
    session = _Session()
    monkeypatch.setattr(scheduler, '_observe', lambda *_: {
        'selected-uuid': session.binding['monitor_uuid'], 'selected-cookie': private_cookie,
        'selected-incarnation': session.binding['incarnation']})
    if accepted:
        assert _scheduler_status(session, adopt=True)['selected-cookie'] == 1
        assert session._dos_task_binding['task_id'] == session.binding['task_id']
    else:
        with pytest.raises(DebuggerError, match='differs from the committed private view'):
            _scheduler_status(session, adopt=True)
        assert session._dos_task_binding['task_id'] == session.binding['task_id']


@pytest.mark.parametrize('bad', ['source','stack','frame','registers'])
def test_fork_admission_refuses_invalid_inputs_before_native_mutation(monkeypatch,bad):
    import fdisbull.qemu_dos_scheduler as sched
    s = _Session()
    monkeypatch.setattr(sched,'_preflight',lambda *_:None)
    monkeypatch.setattr(sched,'_status',lambda *_,**__:None)
    monkeypatch.setattr(sched,'require_task',lambda *_:None)
    context = _cpu(s.binding)
    if bad == 'frame': context['interrupt-depth'] = 1
    monkeypatch.setattr(sched,'_context',lambda *_:context)
    values = dict(task=s.child['task_id'],entry='entry',stack=0x2000)
    if bad == 'source': values['entry'] = 'outside'
    elif bad == 'stack': values['stack'] = 0x1000
    elif bad == 'registers': values['registers'] = {'rsp':2}
    with pytest.raises(ValueError): QemuDOSSchedulerMixin.dos_task_fork.__wrapped__(s,**values)
    assert not s.vm.qmp.calls and not s.closed


def _checkpoint(s):
    binding=s.binding; cpu=_cpu(binding); native=_status(binding)
    admission = dict(binding=deepcopy(binding),parent=None,source_sha256='s',version_sha256='v',
        source_mapping=deepcopy(s._process['source_mapping']),allocation=deepcopy(s._process['allocation']),
        entry_ip=0x100,stack_pointer=0xff00)
    metadata = dict(enabled=True,native_epoch=1,slots={binding['task_id']:admission})
    return dict(format=FORMAT,metadata=metadata,native=native,contexts={binding['task_id']:cpu})


@pytest.mark.parametrize('bad', ['nonce','source','allocation','slot-key','context','frame'])
def test_scheduler_checkpoint_rejects_identity_and_context_mismatch(bad):
    s=_Session(); saved=_checkpoint(s); binding=s.binding
    private = {'views':[{'binding':deepcopy(binding)}]}
    if bad == 'nonce': saved['metadata']['slots'][binding['task_id']]['binding']['process_nonce']='33'*16
    elif bad == 'source': saved['metadata']['slots'][binding['task_id']]['source_sha256']='other'
    elif bad == 'allocation': saved['metadata']['slots'][binding['task_id']]['allocation']['end'] += 1
    elif bad == 'slot-key': saved['native']['tasks'][0]['cookie'] += 1
    elif bad == 'context': saved['contexts'][binding['task_id']]['context-sha256']='00'*32
    else: saved['contexts'][binding['task_id']]['interrupt-depth']=1
    with pytest.raises((ValueError,DebuggerError)):
        validate_scheduler(s,saved,binding['process_nonce'],private,s._process)


def test_scheduler_checkpoint_requires_every_valid_slot_context():
    s = _Session(); saved = _checkpoint(s)
    saved['contexts'] = {}
    with pytest.raises((ValueError, DebuggerError)):
        validate_scheduler(s, saved, s.binding['process_nonce'],
                           {'views': [{'binding': deepcopy(s.binding)}]}, s._process)


def test_scheduler_checkpoint_refuses_pending_switch_at_capture(monkeypatch):
    import fdisbull.qemu_dos_scheduler as sched
    s = _Session(); native = _status(s.binding); native['pending-switch'] = True
    monkeypatch.setattr(sched, '_status', lambda *args, **kwargs: native)
    with pytest.raises((ValueError, DebuggerError), match='pending'):
        capture_scheduler(s)


def test_scheduler_checkpoint_refuses_saved_pending_switch():
    s = _Session(); saved = _checkpoint(s)
    saved['native']['pending-switch'] = True
    with pytest.raises((ValueError, DebuggerError), match='pending'):
        validate_scheduler(s, saved, s.binding['process_nonce'],
                           {'views': [{'binding': deepcopy(s.binding)}]}, s._process)


@pytest.mark.parametrize('bad', ['epoch','generation','queue','cpu','frame'])
def test_scheduler_cold_restore_verifies_native_queue_and_cpu_context(bad):
    s=_Session(); saved=_checkpoint(s)
    current=deepcopy(saved['native']); current.update(epoch=2,generation=2)
    s.vm.qmp.status=current
    assert verify_scheduler(s.vm,saved) == current
    if bad == 'epoch': current['epoch']=1
    elif bad == 'generation': current['generation']=1
    elif bad == 'queue': current['runqueue-generation']+=1
    elif bad == 'cpu': s.vm.qmp.cpu['registers'][0]=1
    else: s.vm.qmp.cpu['frames']=[{'sequence':1}]
    with pytest.raises(DebuggerError): verify_scheduler(s.vm,saved)
