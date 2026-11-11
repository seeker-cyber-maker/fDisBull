"""Host admission and receipts for native-owned DOS CPU scheduling.

Only native QEMU code captures/restores CPU slots or handles interrupt frames.
These controls bind a scheduler to one explicitly shared DOS source allocation.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re

from .dosbox_rpc import DebuggerError
from .memory_search_runtime import _locked
from .qemu_dos_task_views import _arguments, _observe, _preflight, _row
from .qemu_dos_tasks import require_task, task_key

MODEL = 'qemu-pc-task-scheduler-v1'
FORMAT = 'fdisbull-native-dos-scheduler-1'
COMMANDS = frozenset(('x-fdisbull-task-scheduler-init','x-fdisbull-task-slot-capture',
    'x-fdisbull-task-slot-fork','x-fdisbull-task-slot-runnable',
    'x-fdisbull-task-scheduler-observe','x-fdisbull-task-context-read',
    'x-fdisbull-task-scheduler-disable'))
GPRS = ('rax','rcx','rdx','rbx','rsp','rbp','rsi','rdi','r8','r9','r10','r11','r12','r13','r14','r15')


def _uint(value, minimum=0):
    return type(value) is int and minimum <= value < 1 << 64


def _digest(value):
    return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value)


def _key(value):
    if (not isinstance(value,dict) or not isinstance(value.get('uuid'),str)
            or not re.fullmatch('[0-9a-f]{32}',value['uuid'])
            or not _uint(value.get('cookie'),1) or not _uint(value.get('incarnation'),1)):
        raise DebuggerError('Invalid native scheduler task key')
    return value['uuid'],value['cookie'],value['incarnation']


def _binding_key(binding):
    return binding['monitor_uuid'],binding['cookie'],binding['incarnation']


def _number(value, label):
    try: number = int(value,0) if isinstance(value,str) else value
    except ValueError: raise ValueError('Invalid '+label) from None
    if not _uint(number): raise ValueError('Invalid '+label)
    return number


def _validate_native_status(raw):
    if (not isinstance(raw,dict) or raw.get('model') != MODEL
            or type(raw.get('api-version')) is not int or raw['api-version'] != 1
            or not _uint(raw.get('epoch'),1) or not _uint(raw.get('generation'),1)
            or not _uint(raw.get('runqueue-generation')) or type(raw.get('enabled')) is not bool
            or raw.get('yield-vector') != 0x60 or raw.get('block-vector') != 0x62
            or not _uint(raw.get('pending-irq-count'))
            or type(raw.get('pending-switch')) is not bool
            or not isinstance(raw.get('tasks'),list) or len(raw['tasks']) > 16):
        raise DebuggerError('Invalid native scheduler status receipt')
    seen, slots = set(), set()
    for item in raw['tasks']:
        key = _key(item)
        if (key in seen or type(item.get('slot')) is not int or not 0 <= item['slot'] < 16
                or item['slot'] in slots
                or any(type(item.get(name)) is not bool for name in
                    ('runnable','blocked','retired','context-valid'))
                or any(not _digest(item.get(name)) for name in
                    ('context-sha256','frame-sha256','execution-sha256'))
                or any(not _uint(item.get(name)) for name in ('eip','esp','eflags','execution-bytes'))
                or type(item.get('interrupt-depth')) is not int or not 0 <= item['interrupt-depth'] <= 16
                or item.get('mode') not in ('real','protected','v86')
                or not isinstance(item.get('pages'),list) or len(item['pages']) > 16
                or item['retired'] and (item['runnable'] or item['context-valid'])):
            raise DebuggerError('Invalid native CPU slot receipt')
        seen.add(key); slots.add(item['slot'])
    return raw


def _native_status(vm):
    raw = _validate_native_status(vm.qmp.call('x-fdisbull-task-scheduler-observe'))
    if raw.get('fault'):
        error = DebuggerError('Native CPU scheduler refused execution: '+str(raw['fault']))
        error.native_scheduler = deepcopy(raw)
        raise error
    return raw


def _status(session, *, adopt=False):
    meta = getattr(session,'_dos_scheduler',None)
    if not isinstance(meta,dict): raise ValueError('Native CPU scheduling is not initialized')
    raw = _native_status(session.vm)
    if (raw['epoch'] != meta['native_epoch'] or raw['enabled'] != meta['enabled']
            or {_key(row) for row in raw['tasks']} !=
               {_binding_key(row['binding']) for row in meta['slots'].values()}):
        raise DebuggerError('Native scheduler differs from its admitted owner or slot registry')
    prior = getattr(session.vm,'_dos_scheduler_frontier',None)
    if prior and (prior[0] != raw['epoch'] or prior[1] > raw['generation']
                  or prior[2] > raw['runqueue-generation']):
        raise DebuggerError('Native scheduler owner or runqueue observation regressed')
    session.vm._dos_scheduler_frontier = (raw['epoch'],raw['generation'],raw['runqueue-generation'])
    selected = (raw.get('selected-uuid'),raw.get('selected-cookie'),raw.get('selected-incarnation'))
    binding = next((row['binding'] for row in meta['slots'].values()
                    if _binding_key(row['binding']) == selected),None)
    idle = selected == ('',0,0) and not any(row['runnable'] for row in raw['tasks'])
    if raw['tasks'] and binding is None and not idle:
        raise DebuggerError('Native scheduler selected an unadmitted task')
    if binding is not None:
        view = _observe(session,_row(session,binding['task_id']))
        if (view['selected-uuid'],view['selected-cookie'],view['selected-incarnation']) != selected:
            raise DebuggerError('Native CPU scheduler selection differs from the committed private view')
    for item in raw['tasks']:
        task = next(task for task,row in meta['slots'].items() if _binding_key(row['binding'])==_key(item))
        if item['retired'] != session._dos_task_views[task]['retired']:
            raise DebuggerError('Native CPU slot retirement differs from its private task lifetime')
    if adopt and binding is not None:
        # Every slot was admitted as a fork of this exact source allocation.
        # Source queries retain their independent live MCB/PSP/PC checks.
        session._dos_task_binding = deepcopy(binding)
        session.metadata['dos_task_binding'] = deepcopy(binding)
    return raw


def _context(vm, binding):
    raw = vm.qmp.call('x-fdisbull-task-context-read',_arguments(binding))
    if (not isinstance(raw,dict) or _key(raw) != _binding_key(binding)
            or type(raw.get('live')) is not bool or raw.get('mode') not in ('real','protected','v86')
            or not isinstance(raw.get('registers'),list) or len(raw['registers']) != 16
            or any(not _uint(value) for value in raw['registers'])
            or any(not _uint(raw.get(name)) for name in ('eip','eflags','cr0','cr2','cr3','cr4','efer'))
            or any(not _digest(raw.get(name)) for name in ('context-sha256','xstate-sha256'))
            or not isinstance(raw.get('segments'),list) or len(raw['segments']) != 6
            or not isinstance(raw.get('system-segments'),list) or len(raw['system-segments']) != 4
            or type(raw.get('interrupt-depth')) is not int or not 0 <= raw['interrupt-depth'] <= 16
            or not isinstance(raw.get('frames'),list) or len(raw['frames']) != raw['interrupt-depth']):
        raise DebuggerError('Invalid native task CPU context receipt')
    for segment in raw['segments']+raw['system-segments']:
        if not isinstance(segment,dict) or any(not _uint(segment.get(name))
                for name in ('selector','base','limit','flags')):
            raise DebuggerError('Invalid native CPU segment-cache receipt')
    for frame in raw['frames']:
        if (not isinstance(frame,dict) or not _uint(frame.get('sequence'),1)
                or type(frame.get('vector')) is not int or not 0 <= frame['vector'] <= 255
                or not isinstance(frame.get('kind'),str)
                or any(not _uint(frame.get(name)) for name in ('pre-cs','pre-eip','pre-ss','pre-sp','frame-sp','width','error-code'))
                or type(frame.get('error-code-present')) is not bool):
            raise DebuggerError('Invalid native interrupt-frame ownership receipt')
    return raw


def _mutate(session, command, arguments=None):
    try: return session.vm.qmp.call(command,arguments)
    except DebuggerError as error:
        if 'PRECONDITION' not in str(error):
            temporary = getattr(session.vm,'temporary',None)
            if temporary is not None:
                log = Path(temporary.name)/'qemu.log'
                try:
                    with log.open('rb') as stream:
                        stream.seek(0,2);size=stream.tell();stream.seek(max(0,size-4096))
                        detail=stream.read().decode(errors='replace').strip()
                    if detail: error.args=(str(error)+'\n'+detail,)
                except OSError: pass
            session.close()
        raise
    except BaseException:
        session.close()
        raise


def _admission(session, binding, context, *, parent=None, entry=None, stack=None):
    process = session._process
    return dict(binding=deepcopy(binding), parent=parent,
        source_sha256=session.metadata['source_sha256'],version_sha256=session.metadata['version_sha256'],
        source_mapping=deepcopy(process['source_mapping']),allocation=deepcopy(process['allocation']),
        entry_ip=context['eip'] if entry is None else entry,
        stack_pointer=context['registers'][4] if stack is None else stack)


def after_scheduler_stop(session, result):
    if not getattr(session,'_dos_scheduler',None) or not session._dos_scheduler['enabled']:
        return result
    try:
        previous = (getattr(session,'_dos_task_binding',None) or {}).get('task_id')
        raw = _status(session,adopt=True)
        if previous != session._dos_task_binding['task_id']: session._persist_process()
        result['scheduler'] = raw
        if not any(row['runnable'] for row in raw['tasks']):
            if not result.get('session',{}).get('stop_reason',{}).get('breakpoint_ids'):
                result['outcome'] = 'scheduler-idle'
        return result
    except BaseException as error:
        session.close()
        if getattr(error,'result',None) is None: error.result = result
        raise


def before_scheduler_execution(session):
    if (getattr(session,'_dos_scheduler',None) or {}).get('enabled'):
        try: _status(session,adopt=True)
        except BaseException:
            session.close()
            raise


def capture_scheduler(session):
    meta = getattr(session,'_dos_scheduler',None)
    if meta is None: return None
    raw = _status(session,adopt=True)
    if raw['pending-switch']:
        raise ValueError('Continue the pending native runqueue change before checkpointing')
    contexts = {}
    for task, admission in meta['slots'].items():
        native = next(row for row in raw['tasks'] if _key(row)==_binding_key(admission['binding']))
        if native['context-valid']:
            context = _context(session.vm,admission['binding'])
            if (context['context-sha256'] != native['context-sha256']
                    or context['interrupt-depth'] != native['interrupt-depth']):
                raise DebuggerError('Native scheduler CPU/frame state changed during capture')
            contexts[task] = context
    return dict(format=FORMAT,metadata=deepcopy(meta),native=raw,contexts=contexts)


def validate_scheduler(session, saved, origin_nonce, private_views, process):
    if saved is None: return
    if (not isinstance(saved,dict) or saved.get('format') != FORMAT
            or not COMMANDS <= session.vm.qmp_commands or private_views is None
            or not isinstance(saved.get('metadata'),dict)
            or not isinstance(saved['metadata'].get('slots'),dict)
            or not 1 <= len(saved['metadata']['slots']) <= 16
            or type(saved['metadata'].get('enabled')) is not bool
            or not isinstance(saved.get('contexts'),dict)
            or not isinstance(saved.get('native'),dict)):
        raise ValueError('Invalid or unsupported native scheduler checkpoint')
    views = {row['binding']['task_id']:row for row in private_views['views']}
    slots = saved['metadata']['slots']
    seen = set()
    for task,admission in slots.items():
        binding = admission['binding']; task_key(binding)
        if (task != binding.get('task_id') or task not in views
                or task_key(binding) != task_key(views[task]['binding'])
                or binding['process_nonce'] != origin_nonce
                or admission.get('source_sha256') != session.metadata['source_sha256']
                or admission.get('version_sha256') != session.metadata['version_sha256']
                or admission.get('source_mapping') != process['source_mapping']
                or admission.get('allocation') != process['allocation']
                or not _uint(admission.get('entry_ip')) or not _uint(admission.get('stack_pointer'))):
            raise ValueError('Native CPU slot differs from its shared source/allocation admission')
        parent = admission.get('parent')
        if parent is not None and parent not in slots:
            raise ValueError('Native CPU slot has an unknown fork parent')
        seen.add(_binding_key(binding))
    native = saved['native']
    _validate_native_status(native)
    if native['pending-switch']:
        raise ValueError('Native scheduler checkpoint contains a pending runqueue change')
    if ({_key(row) for row in native.get('tasks',[])} != seen
            or native.get('enabled') != saved['metadata']['enabled']
            or native.get('epoch') != saved['metadata'].get('native_epoch')
            or any(task not in slots for task in saved['contexts'])):
        raise ValueError('Native scheduler checkpoint slot census differs')
    expected_contexts = {task for task,admission in slots.items() if next(
        row for row in native['tasks'] if _key(row)==_binding_key(admission['binding']))['context-valid']}
    if set(saved['contexts']) != expected_contexts:
        raise ValueError('Native scheduler checkpoint context census is incomplete')
    for task in slots:
        chain = set()
        parent = task
        while parent is not None:
            if parent in chain: raise ValueError('Native scheduler fork admissions contain a cycle')
            chain.add(parent)
            parent = slots[parent].get('parent')
    for task,context in saved['contexts'].items():
        slot = next(row for row in native['tasks'] if _key(row)==_binding_key(slots[task]['binding']))
        if (not isinstance(context,dict) or _key(context)!=_binding_key(slots[task]['binding'])
                or context.get('context-sha256') != slot.get('context-sha256')
                or context.get('interrupt-depth') != slot.get('interrupt-depth')):
            raise ValueError('Native CPU context checkpoint differs from its slot digest')


def prime_scheduler(vm, saved, private_views):
    if saved is not None:
        if not COMMANDS <= vm.qmp_commands:
            raise ValueError('Fresh QEMU lacks native scheduler restore support')
        vm.qmp.call('x-fdisbull-task-scheduler-init',
            {'anchor-address':private_views['monitor']['anchor_address'],'prepare-only':True})


def _stable_status(raw):
    return {key:value for key,value in raw.items() if key not in ('epoch','generation')}


def _differences(expected, actual, path=''):
    if isinstance(expected,dict) and isinstance(actual,dict):
        return [item for key in sorted(expected.keys()|actual.keys())
                for item in _differences(expected.get(key),actual.get(key),path+'.'+str(key))]
    if isinstance(expected,list) and isinstance(actual,list) and len(expected)==len(actual):
        return [item for i,(a,b) in enumerate(zip(expected,actual))
                for item in _differences(a,b,path+f'[{i}]')]
    return [] if expected==actual else [path]


def verify_scheduler(vm, saved):
    if saved is None: return None
    raw = _native_status(vm)
    if (raw['epoch'] <= saved['native']['epoch'] or raw['generation'] <= saved['native']['generation']
            or _stable_status(raw) != _stable_status(saved['native'])):
        changes = _differences(_stable_status(saved['native']),_stable_status(raw))
        changes += [key for key in ('epoch','generation')
                    if raw[key] <= saved['native'][key]]
        contexts = {task:_context(vm,saved['metadata']['slots'][task]['binding'])
                    for task in saved['contexts']}
        changes += _differences(saved['contexts'],contexts,'contexts')
        error = DebuggerError('Restored native scheduler/CPU/frame state differs from checkpoint: '+', '.join(changes))
        error.native_scheduler = deepcopy(raw)
        error.native_contexts = contexts
        raise error
    for task,expected in saved['contexts'].items():
        actual = _context(vm,saved['metadata']['slots'][task]['binding'])
        if actual != expected:
            raise DebuggerError('Restored native task CPU context or interrupt frame differs')
    return raw


def restore_scheduler(session, saved, proof):
    session._dos_scheduler = None
    if saved is None:
        session.metadata.pop('native_scheduler',None)
        return
    session._dos_scheduler = deepcopy(saved['metadata'])
    session._dos_scheduler['native_epoch'] = proof['epoch']
    session.metadata['native_scheduler'] = dict(model=MODEL,enabled=proof['enabled'])
    _status(session,adopt=True)


class QemuDOSSchedulerMixin:
    @_locked
    def dos_task_scheduler(self):
        from .qemu_dos_checkpoint import _origin,_verify_process
        _preflight(self)
        if not COMMANDS <= self.vm.qmp_commands: raise ValueError('Native CPU scheduler extension is unavailable')
        if getattr(self,'_dos_scheduler',None): return self.dos_task_scheduler_observe()
        require_task(self)
        _verify_process(self,self._process,_origin(self))
        binding = deepcopy(self._dos_task_binding)
        _mutate(self,'x-fdisbull-task-scheduler-init',{'anchor-address':binding['anchor_address']})
        try:
            raw = _native_status(self.vm)
            if not raw['enabled'] or raw['tasks']: raise DebuggerError('Native scheduler initialization is not empty')
            self._dos_scheduler = dict(format=FORMAT,enabled=True,native_epoch=raw['epoch'],slots={})
            view = _row(self,binding['task_id'])
            _mutate(self,'x-fdisbull-task-slot-capture',dict(_arguments(binding),
                pages=[{'address':address} for address in view['pages']]))
            context = _context(self.vm,binding)
            self._dos_scheduler['slots'][binding['task_id']] = _admission(self,binding,context)
            raw = _status(self,adopt=True)
            self.metadata['native_scheduler'] = dict(model=MODEL,enabled=True)
            self._event('dos-native-scheduler-init',dict(native=raw,task_id=binding['task_id']))
            return dict(enabled=True,task=deepcopy(binding),native=raw)
        except BaseException:
            self.close()
            raise

    @_locked
    def dos_task_scheduler_observe(self):
        _preflight(self)
        try:
            raw = _status(self,adopt=True)
            self._event('dos-native-scheduler-observe',raw)
            return deepcopy(raw)
        except BaseException:
            self.close()
            raise

    @_locked
    def dos_task_context(self, *, task=None):
        _preflight(self)
        row = _row(self,task)
        _status(self)
        if row['binding']['task_id'] not in self._dos_scheduler['slots']:
            raise ValueError('Task has no admitted native CPU context')
        raw = _context(self.vm,row['binding'])
        return dict(raw,task_id=row['binding']['task_id'])

    @_locked
    def dos_task_fork(self, *, task, entry, stack, registers=None, eflags=None):
        _preflight(self)
        _status(self,adopt=True)
        parent = deepcopy(self._dos_task_binding)
        child = _row(self,task)
        if child['retired'] or task in self._dos_scheduler['slots']:
            raise ValueError('Task CPU context is retired or already admitted')
        require_task(self)
        context = _context(self.vm,parent)
        if context['interrupt-depth']:
            raise ValueError('Fork native CPU tasks outside an owned interrupt frame')
        linear,_,_,_ = self._layer_spans(entry,1,'source')
        stack = _number(stack,'task stack address')
        allocation = self._process['allocation']
        if not allocation['start'] <= stack-64 < stack <= allocation['end']:
            raise ValueError('Task stack must fit the shared owned DOS allocation')
        cs,ss = context['segments'][1],context['segments'][2]
        ip,sp = linear-cs['base'],stack-ss['base']
        if not 0 <= ip <= cs['limit'] or not 64 <= sp <= ss['limit']:
            raise ValueError('Task entry or stack is outside the cloned CPU segment caches')
        values = list(context['registers'])
        if registers is None: registers = {}
        if not isinstance(registers,dict) or any(name not in GPRS or name=='rsp' for name in registers):
            raise ValueError('Task fork register overrides require named GPRs; stack sets RSP')
        for name,value in registers.items(): values[GPRS.index(name)] = _number(value,'task register')
        values[4] = sp
        flags = context['eflags'] if eflags is None else _number(eflags,'task EFLAGS')
        args = dict(_arguments(child['binding']),
            **{'parent-uuid':parent['monitor_uuid'],'parent-cookie':parent['cookie'],
               'parent-incarnation':parent['incarnation'],'entry-eip':ip},
            pages=[{'address':address} for address in child['pages']],registers=values,eflags=flags)
        _mutate(self,'x-fdisbull-task-slot-fork',args)
        try:
            actual = _context(self.vm,child['binding'])
            if actual['eip'] != ip or actual['registers'] != values or actual['eflags'] != flags:
                raise DebuggerError('Native task fork differs from its admitted entry context')
            for name in ('mode','segments','system-segments','cr0','cr2','cr3','cr4','efer',
                         'a20-mask','xstate-sha256','interrupt-depth','frames'):
                if actual[name] != context[name]:
                    raise DebuggerError('Native task fork changed inherited CPU state: '+name)
            self._dos_scheduler['slots'][task] = _admission(self,child['binding'],actual,
                parent=parent['task_id'],entry=ip,stack=sp)
            native = _status(self)
            self._event('dos-native-task-fork',dict(task_id=task,parent=parent['task_id'],native=native))
            return dict(task_id=task,binding=deepcopy(child['binding']),context=actual,native=native)
        except BaseException:
            self.close()
            raise

    @_locked
    def dos_task_runnable(self, task, *, runnable=True):
        _preflight(self)
        _status(self)
        if type(runnable) is not bool: raise ValueError('Task runnable state must be boolean')
        row = _row(self,task)
        if task not in self._dos_scheduler['slots'] or row['retired']:
            raise ValueError('Task lacks a live admitted CPU slot')
        _mutate(self,'x-fdisbull-task-slot-runnable',dict(_arguments(row['binding']),runnable=runnable))
        try:
            raw = _status(self)
            item = next(item for item in raw['tasks'] if _key(item)==_binding_key(row['binding']))
            if item['runnable'] is not runnable: raise DebuggerError('Native runnable state differs')
            self._event('dos-native-task-runnable',dict(task_id=task,runnable=runnable,native=raw))
            return dict(task_id=task,runnable=runnable,native=raw)
        except BaseException:
            self.close()
            raise

    @_locked
    def dos_task_scheduler_disable(self):
        _preflight(self)
        _status(self,adopt=True)
        _mutate(self,'x-fdisbull-task-scheduler-disable')
        try:
            self._dos_scheduler['enabled'] = False
            raw = _status(self)
            if raw['enabled']: raise DebuggerError('Native scheduler remained enabled')
            self.metadata['native_scheduler'] = dict(model=MODEL,enabled=False)
            self._event('dos-native-scheduler-disable',raw)
            return dict(enabled=False,native=raw)
        except BaseException:
            self.close()
            raise
