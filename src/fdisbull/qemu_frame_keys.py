"""Atomic, explicitly owned native renderer-boundary keyboard edges."""
from copy import deepcopy
import json
import uuid

from .debug_timeline import validate_edges
from .dosbox_rpc import DebuggerError
from .qemu_dos_history import _history_operation
from .qemu_frame_key_batch import (INPUT_RECEIPT_RESERVE, VerifiedBatchRefusal,
    apply_batch, batch_capability, frame_input_operation, input_owner, plan_batch)
from .qemu_input import _key, _QCODE, require_released_machine_input
from .keyboard_input import KEYS

FRAME_KEY_COMMANDS = frozenset({'x-fdisbull-query-frame-keys',
    'x-fdisbull-apply-frame-key-edges', 'x-fdisbull-detach-frame-keys'})
REPEAT_QUERY = 'x-fdisbull-query-frame-key-repeat'
_CANONICAL = { _key(k)[1]: _key(k)[0] for k in KEYS }


def validate_frame_key_state(native, *, token=None, epoch=None):
    if not isinstance(native, dict) or type(native.get('api-version')) is not int or native['api-version'] != 1:
        raise DebuggerError('Invalid native frame key receipt')
    fields = {'api-version','epoch','active','valid','generation','held','edge-capacity',
              'repeat-supported','accepted-edges','device-path','device-type','scan-enabled',
              'scancode-set','translated','modifier-mask','fifo-count','fifo-sha256',
              'controller-status','controller-mode','controller-pending','controller-obsrc',
              'controller-obdata','throttle-deadline-ns','foreign-held'}
    fields.update(('fifo-read-pointer','fifo-write-pointer','fifo-command-pointer','write-command'))
    if set(native) not in (fields, fields | {'token'}):
        raise DebuggerError('Unexpected native frame key receipt fields')
    for key in ('epoch','generation','accepted-edges','edge-capacity','scancode-set',
                'modifier-mask','fifo-count','controller-status','controller-mode',
                'controller-pending','controller-obsrc','controller-obdata'):
        if type(native.get(key)) is not int or not 0 <= native[key] < 1 << 64:
            raise DebuggerError('Invalid native frame key field: '+key)
    if native['epoch'] < 1 or native['edge-capacity'] > 32:
        raise DebuggerError('Invalid native frame key epoch or capacity')
    deadline = native.get('throttle-deadline-ns')
    if type(deadline) is not int or not -1 <= deadline < 1 << 63:
        raise DebuggerError('Invalid frame key throttle deadline')
    if (native['fifo-count'] > 256 or native['controller-obsrc'] >= 1 << 32
            or any(native[k] >= 256 for k in ('controller-status','controller-mode',
                                               'controller-pending','controller-obdata'))):
        raise DebuggerError('Invalid frame key controller proof')
    for field, minimum in (('fifo-read-pointer',0),('fifo-write-pointer',0),
                           ('fifo-command-pointer',-1),('write-command',-1)):
        if type(native.get(field)) is not int or not minimum <= native[field] < 256:
            raise DebuggerError('Invalid frame key FIFO field: '+field)
    for key in ('active','valid','repeat-supported','scan-enabled','translated'):
        if type(native.get(key)) is not bool:
            raise DebuggerError('Invalid native frame key field: '+key)
    if not native['valid']:
        raise DebuggerError('Native frame key owner is invalid')
    for key in ('held','foreign-held'):
        values = native.get(key)
        if (not isinstance(values,list) or len(values) > 64
                or any(not isinstance(k,str) for k in values)
                or values != sorted(set(values))):
            raise DebuggerError('Invalid native frame key set')
    if any(k not in _CANONICAL for k in native['held']):
        raise DebuggerError('Native frame owner contains unsupported keys')
    if (not isinstance(native.get('device-path'),str) or not 1 <= len(native['device-path']) <= 1024
            or not isinstance(native.get('device-type'),str) or not 1 <= len(native['device-type']) <= 128
            or not isinstance(native.get('fifo-sha256'),str) or len(native['fifo-sha256']) != 64
            or any(c not in '0123456789abcdef' for c in native['fifo-sha256'])):
        raise DebuggerError('Invalid native frame key device proof')
    if native['active']:
        if not isinstance(native.get('token'),str) or not native['token'] or native['generation'] < 1:
            raise DebuggerError('Invalid native frame key ownership')
    elif native.get('token') is not None or native['held']:
        raise DebuggerError('Invalid idle native frame key ownership')
    if token is not None and native.get('token') != token:
        raise DebuggerError('Native frame key token changed')
    if epoch is not None and native['epoch'] != epoch:
        raise DebuggerError('Native frame key epoch changed')
    return deepcopy(native)


def validate_frame_key_repeat(value, *, held):
    fields = {'parameter', 'delay-ns', 'interval-ns', 'deadline-ns'}
    if (type(value) is not dict or set(value) not in (fields, fields | {'key'})
            or any(type(value[name]) is not int for name in fields)
            or not 0 <= value['parameter'] <= 127
            or not -1 <= value['deadline-ns'] < 1 << 63):
        raise DebuggerError('Invalid native frame key repeat state')
    parameter = value['parameter']
    delay = (1 + (parameter >> 5)) * 250_000_000
    cycles = (8 + (parameter & 7)) << ((parameter >> 3) & 3)
    key = value.get('key')
    if (value['delay-ns'] != delay or value['interval-ns'] != cycles * 1_000_000_000 // 240
            or ('key' in value) != (value['deadline-ns'] >= 0)
            or 'key' in value and (type(key) is not str or key not in held)):
        raise DebuggerError('Native frame key repeat timing or ownership differs')
    return deepcopy(value)


def adopt_frame_keys(vm, native, *, expected_held=None):
    native = validate_frame_key_state(native)
    if expected_held is not None and native['held'] != sorted(expected_held):
        raise DebuggerError('Restored frame key ownership differs')
    if native['foreign-held']:
        raise DebuggerError('Foreign keyboard ownership prevents frame key adoption')
    vm._frame_key_owner = (dict(token=native['token'],epoch=native['epoch'],
        generation=native['generation'],held=list(native['held']),accepted_edges=native['accepted-edges'])
        if native['active'] else None)
    return deepcopy(vm._frame_key_owner)


def validate_frame_key_checkpoint(record, *, epoch):
    fields = {'active','source-epoch','generation','accepted-edges','held','device-path',
              'device-type','scan-enabled','scancode-set','translated','modifier-mask',
              'fifo-count','fifo-sha256','controller-status','controller-mode',
              'controller-pending','controller-obsrc','controller-obdata','throttle-deadline-ns'}
    fields.update(('fifo-read-pointer','fifo-write-pointer','fifo-command-pointer','write-command'))
    if not isinstance(record,dict) or set(record) != fields or record.get('source-epoch') != epoch:
        raise ValueError('Invalid frame key checkpoint identity or fields')
    synthetic = dict(record)
    synthetic['epoch'] = synthetic.pop('source-epoch')
    synthetic.update({'api-version':1,'valid':True,'edge-capacity':0,
                      'repeat-supported':False,'foreign-held':[]})
    if synthetic.get('active') is True: synthetic['token'] = 'checkpoint-owner'
    try:
        validate_frame_key_state(synthetic)
    except DebuggerError as error:
        raise ValueError('Invalid frame key checkpoint proof') from error
    return deepcopy(record)


def _edges(edges, held):
    validate_edges(edges)
    held = set(held)
    converted = []
    for edge in edges:
        _, qcode = _key(edge['key'])
        if (qcode in held) == edge['pressed']:
            raise ValueError('Frame input key is already in the requested held/released state')
        (held.add if edge['pressed'] else held.remove)(qcode)
        converted.append(dict(key=qcode,pressed=edge['pressed']))
    return converted, sorted(held)


def _input_journal_budget(session, manifest, count):
    journal = manifest.get('input_journal',[])
    if not isinstance(journal,list) or len(journal) + count > 1024:
        raise ValueError('Renderer input journal budget exhausted')
    used = (session._frame_state_bytes(manifest)
            + sum(n['frame']['image']['size'] for n in manifest['nodes']))
    journal_bytes = len(json.dumps(journal,sort_keys=True,separators=(',',':')).encode())
    reserve = count * INPUT_RECEIPT_RESERVE
    if used + journal_bytes + reserve > manifest['max_bytes']:
        raise ValueError('Renderer input journal byte budget exhausted')
    used_project = int(session.project.db.execute(
        'SELECT coalesce(sum(fdb_length(data)),0) FROM debug_artifacts').fetchone()[0])
    manifest_bytes = len(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode())
    if used_project + 2 * (manifest_bytes + reserve) > 256 * 1024**2:
        raise ValueError('Project artifact budget cannot reserve input journal revisions')


def resolve_batch_intent(session, manifest, pending):
    """Clear only this proven no-effect intent; retain all accepted history."""
    owner = input_owner(session)
    if manifest.get('pending') != pending:
        raise DebuggerError('Frame input pending intent changed before refusal resolution')
    updated, _ = owner.call('_history_new_revision', manifest, pending=None)
    if updated.get('pending') is not None:
        raise DebuggerError('Frame input refusal resolution retained an unresolved intent')
    manifest.clear()
    manifest.update(updated)
    owner.check()
    owner.intent_written = False


class QemuFrameKeysMixin:
    def _frame_keys_checkpoint_preflight(self):
        if (self.vm.machine_configuration.get('clock_profile',{}).get('profile') == 'virtual'
                and FRAME_KEY_COMMANDS <= self.vm.qmp_commands):
            return self._frame_keys_query()
        return None

    def _frame_keys_before_physical_input(self):
        from .qemu_video_control import require_no_video_frame_fence
        require_no_video_frame_fence(self.vm, 'frame-key detachment')
        from .qemu_step_over import require_no_step_over
        require_no_step_over(self.vm, 'frame-key detachment')
        if (self.vm.machine_configuration.get('clock_profile',{}).get('profile') != 'virtual'
                or not FRAME_KEY_COMMANDS <= self.vm.qmp_commands):
            return
        native = self._frame_keys_query(allow_foreign=True)
        if native['held']:
            raise ValueError('Release frame-owned keys before ordinary physical input')
        if native['active']:
            try:
                result = validate_frame_key_state(self.vm.qmp.call('x-fdisbull-detach-frame-keys',
                    {'token':native['token'],'expected-generation':native['generation']}),epoch=native['epoch'])
                if (result['active'] or result['held'] or result['foreign-held']
                        or result['generation'] != native['generation'] + 1
                        or result['accepted-edges'] != native['accepted-edges']):
                    raise DebuggerError('Native frame key detach did not release its owner')
                self.vm._frame_key_owner = None
            except BaseException:
                self.close()
                raise

    def _frame_keys_query(self, *, allow_foreign=False):
        owner = getattr(self, '_frame_input_owner', None)
        vm = owner.check().vm if owner is not None else self.vm
        if not FRAME_KEY_COMMANDS <= vm.qmp_commands:
            raise ValueError('Native frame key ownership is unavailable')
        raw = owner.qmp('x-fdisbull-query-frame-keys') if owner is not None else vm.qmp.call('x-fdisbull-query-frame-keys')
        native = validate_frame_key_state(raw)
        if native['repeat-supported'] != (REPEAT_QUERY in vm.qmp_commands):
            raise DebuggerError('Native frame key repeat capability differs from its command inventory')
        if owner is not None: owner.check()
        ledger = getattr(vm,'_frame_key_owner',None)
        if native['foreign-held'] and not allow_foreign:
            raise ValueError('Foreign keyboard holds prevent frame input')
        if ledger is None:
            if native['active']:
                raise DebuggerError('Native frame key owner is not bound to this session')
        elif (not native['active'] or any(native[k] != ledger[v] for k,v in
                (('token','token'),('epoch','epoch'),('generation','generation'),
                 ('held','held'),('accepted-edges','accepted_edges')))):
            raise DebuggerError('Native frame key owner changed unexpectedly')
        return native

    def _frame_keys_prepare(self, edges, native=None):
        owner = input_owner(self)
        vm = owner.vm
        owner.invoke(owner.preflights[0], vm, 'frame-key mutation')
        owner.invoke(owner.preflights[1], vm, 'frame-key mutation')
        if vm.machine_configuration.get('clock_profile',{}).get('profile') != 'virtual':
            raise ValueError('Frame key ownership requires an explicit virtual clock')
        owner.invoke(owner.preflights[2], vm)
        if owner.call('_input_schedule_bound'):
            raise ValueError('Resolve scheduled input before frame input')
        if getattr(vm,'_active_frame_fence',None) is not None:
            raise ValueError('Resolve the frame fence before frame input')
        owner.invoke(owner.preflights[3], self)
        owner.call('_input_no_transaction')
        owner.call('_stopped')
        native = native or owner.call('_frame_keys_query')
        converted, held = _edges(edges,native['held'])
        return native, converted, held

    def _frame_keys_apply(self, native, edges, expected_held, planned=None):
        owner = input_owner(self)
        if not edges: return dict(native=deepcopy(native),edges=[],held=sorted(_CANONICAL[x] for x in native['held']))
        if batch_capability(owner.vm):
            return apply_batch(self, native, edges, expected_held, planned)
        if len(edges) > native['edge-capacity']:
            raise ValueError('Native frame key edge capacity is unavailable')
        token = native.get('token') or uuid.uuid4().hex
        intent = dict(token=token,expected_generation=native['generation'],edges=deepcopy(edges))
        owner.call('_event', 'frame-inputs-intent', intent)
        try:
            raw = owner.qmp('x-fdisbull-apply-frame-key-edges',
                {'token':token,'expected-generation':native['generation'],'edges':edges}, mutating=True)
            owner.accepted_evidence = deepcopy(raw)
            result = validate_frame_key_state(raw,token=token,epoch=native['epoch'])
            if (result['generation'] != native['generation'] + 1 or result['held'] != expected_held
                    or result['accepted-edges'] != native['accepted-edges'] + len(edges)
                    or result['foreign-held']):
                raise DebuggerError('Native frame key application receipt differs from intent')
            owner.adopt(adopt_frame_keys, result, expected_held)
            receipt = dict(native=result,edges=deepcopy(edges),held=sorted(_CANONICAL[x] for x in expected_held),
                           guest_consumed=None,repeat_supported=result['repeat-supported'])
            owner.accepted_evidence = deepcopy(receipt)
            owner.call('_event', 'frame-inputs', receipt)
            return receipt
        except BaseException as error:
            if 'raw' in locals() and getattr(error, 'result', None) is None: error.result = deepcopy(raw)
            raise

    @frame_input_operation
    def frame_inputs(self, edges, *, timeout_ms=1000):
        owner = input_owner(self)
        native, converted, held = owner.call('_frame_keys_prepare', edges)
        if not batch_capability(owner.vm) and len(converted) > native['edge-capacity']:
            raise ValueError('Native frame key edge capacity is unavailable')
        planned = plan_batch(self, native, converted, held)
        live = getattr(self,'_qemu_history_live',None)
        manifest = invalidation = None
        if live and live.get('valid'):
            selected, _ = owner.call('_history_latest', live['history'])
            if selected.get('history_kind') == 'renderer-frames':
                manifest = selected
                owner.call('_frame_current', manifest)
                owner.invoke(_input_journal_budget, self, manifest, int(bool(converted)))
            elif converted:
                invalidation = live
        pending = None
        try:
            if manifest is not None and converted:
                owner.intent_written = True
                owner.call('_history_pending', manifest, manifest['cursor'], 'renderer-input',
                           receipt=dict(edges=deepcopy(converted)))
                pending = deepcopy(manifest['pending'])
            receipt = owner.call('_frame_keys_apply', native, converted, held, planned=planned)
            if invalidation is not None:
                owner.check()
                invalidation.update(valid=False,cursor=None,invalid_reason='unrecorded frame key input')
            if manifest is not None and converted:
                manifest.setdefault('input_journal',[]).append(deepcopy(receipt))
                manifest.setdefault('pending_inputs',[]).append(deepcopy(receipt))
                manifest['input_dirty'] = True
                updated, artifact = owner.call('_history_new_revision', manifest)
                manifest.clear(); manifest.update(updated)
                owner.intent_written = False
        except VerifiedBatchRefusal:
            if pending is not None:
                resolve_batch_intent(self, manifest, pending)
            raise
        except BaseException as error:
            if 'receipt' in locals() and getattr(error, 'result', None) is None:
                error.result = deepcopy(receipt)
            if invalidation is not None and owner.can_notify() and owner.mutating:
                invalidation.update(valid=False,cursor=None,invalid_reason='uncertain frame key input')
            raise
        if manifest is not None:
            try:
                receipt['timeline'] = owner.call('_frame_summary', owner.call('_frame_manifest'))
            except BaseException as error:
                if converted and getattr(error, 'result', None) is None:
                    error.result = deepcopy(receipt)
                raise
        return receipt

    @_history_operation
    def keyboard_state(self):
        physical = super().keyboard_state()
        if self._input_schedule_bound():
            if getattr(self.vm,'_frame_key_owner',None) is not None:
                raise DebuggerError('Bound input schedule conflicts with frame-key ownership')
            return physical
        if (self.vm.machine_configuration.get('clock_profile',{}).get('profile') != 'virtual'
                or not FRAME_KEY_COMMANDS <= self.vm.qmp_commands):
            return physical
        vm = self.vm
        qmp = vm.qmp
        native = self._frame_keys_query(allow_foreign=True)
        keyboard = dict(frame_keys=sorted(_CANONICAL[k] for k in native['held']),
                        frame_edge_capacity=native['edge-capacity'],native=native)
        if native['repeat-supported'] and not native['foreign-held']:
            if self.vm is not vm or vm.qmp is not qmp:
                raise DebuggerError('Frame key repeat observation owner changed')
            repeat = qmp.call(REPEAT_QUERY)
            if self.vm is not vm or vm.qmp is not qmp:
                raise DebuggerError('Frame key repeat observation owner changed')
            keyboard['frame_key_repeat'] = validate_frame_key_repeat(repeat, held=native['held'])
        physical['keyboard'] = keyboard
        return physical
