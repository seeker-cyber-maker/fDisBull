"""Atomic, explicitly owned native renderer-boundary keyboard edges."""
from copy import deepcopy
import json
import uuid

from .debug_timeline import validate_edges
from .dosbox_rpc import DebuggerError
from .qemu_dos_history import _history_operation
from .qemu_input import _key, _QCODE, require_released_machine_input
from .keyboard_input import KEYS

FRAME_KEY_COMMANDS = frozenset({'x-fdisbull-query-frame-keys',
    'x-fdisbull-apply-frame-key-edges', 'x-fdisbull-detach-frame-keys'})
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
    if not native['valid'] or native['repeat-supported']:
        raise DebuggerError('Native frame key owner is invalid or unsupported')
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
    used = sum(n['checkpoint']['size'] + n['frame']['image']['size'] for n in manifest['nodes'])
    journal_bytes = len(json.dumps(journal,sort_keys=True,separators=(',',':')).encode())
    reserve = count * 8192
    if used + journal_bytes + reserve > manifest['max_bytes']:
        raise ValueError('Renderer input journal byte budget exhausted')
    used_project = int(session.project.db.execute(
        'SELECT coalesce(sum(fdb_length(data)),0) FROM debug_artifacts').fetchone()[0])
    manifest_bytes = len(json.dumps(manifest,sort_keys=True,separators=(',',':')).encode())
    if used_project + 2 * (manifest_bytes + reserve) > 256 * 1024**2:
        raise ValueError('Project artifact budget cannot reserve input journal revisions')


class QemuFrameKeysMixin:
    def _frame_keys_checkpoint_preflight(self):
        if (self.vm.machine_configuration.get('clock_profile',{}).get('profile') == 'virtual'
                and FRAME_KEY_COMMANDS <= self.vm.qmp_commands):
            return self._frame_keys_query()
        return None

    def _frame_keys_before_physical_input(self):
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
        if not FRAME_KEY_COMMANDS <= self.vm.qmp_commands:
            raise ValueError('Native frame key ownership is unavailable')
        native = validate_frame_key_state(self.vm.qmp.call('x-fdisbull-query-frame-keys'))
        owner = getattr(self.vm,'_frame_key_owner',None)
        if native['foreign-held'] and not allow_foreign:
            raise ValueError('Foreign keyboard holds prevent frame input')
        if owner is None:
            if native['active']:
                raise DebuggerError('Native frame key owner is not bound to this session')
        elif (not native['active'] or any(native[k] != owner[v] for k,v in
                (('token','token'),('epoch','epoch'),('generation','generation'),
                 ('held','held'),('accepted-edges','accepted_edges')))):
            raise DebuggerError('Native frame key owner changed unexpectedly')
        return native

    def _frame_keys_prepare(self, edges, native=None):
        if self.vm.machine_configuration.get('clock_profile',{}).get('profile') != 'virtual':
            raise ValueError('Frame key ownership requires an explicit virtual clock')
        require_released_machine_input(self.vm)
        if self._input_schedule_bound():
            raise ValueError('Resolve scheduled input before frame input')
        if getattr(self.vm,'_active_frame_fence',None) is not None:
            raise ValueError('Resolve the frame fence before frame input')
        from .qemu_instrumented_checkpoint import preflight
        preflight(self)
        self._input_no_transaction()
        self._stopped()
        native = native or self._frame_keys_query()
        converted, held = _edges(edges,native['held'])
        return native, converted, held

    def _frame_keys_apply(self, native, edges, expected_held):
        if not edges: return dict(native=deepcopy(native),edges=[],held=sorted(_CANONICAL[x] for x in native['held']))
        if len(edges) > native['edge-capacity']:
            raise ValueError('Native frame key edge capacity is unavailable')
        token = native.get('token') or uuid.uuid4().hex
        intent = dict(token=token,expected_generation=native['generation'],edges=deepcopy(edges))
        self._event('frame-inputs-intent', intent)
        try:
            raw = self.vm.qmp.call('x-fdisbull-apply-frame-key-edges',
                {'token':token,'expected-generation':native['generation'],'edges':edges})
            result = validate_frame_key_state(raw,token=token,epoch=native['epoch'])
            if (result['generation'] != native['generation'] + 1 or result['held'] != expected_held
                    or result['accepted-edges'] != native['accepted-edges'] + len(edges)
                    or result['foreign-held']):
                raise DebuggerError('Native frame key application receipt differs from intent')
            adopt_frame_keys(self.vm,result,expected_held=expected_held)
            receipt = dict(native=result,edges=deepcopy(edges),held=sorted(_CANONICAL[x] for x in expected_held),
                           guest_consumed=None,repeat_supported=False)
            self._event('frame-inputs',receipt)
            return receipt
        except BaseException as error:
            if 'raw' in locals(): error.result = deepcopy(raw)
            self.close()
            raise

    @_history_operation
    def frame_inputs(self, edges, *, timeout_ms=1000):
        native, converted, held = self._frame_keys_prepare(edges)
        if len(converted) > native['edge-capacity']:
            raise ValueError('Native frame key edge capacity is unavailable')
        live = getattr(self,'_qemu_history_live',None)
        manifest = None
        if live and live.get('valid'):
            selected, _ = self._history_latest(live['history'])
            if selected.get('history_kind') == 'renderer-frames':
                manifest = selected
                self._frame_current(manifest)
                _input_journal_budget(self,manifest,int(bool(converted)))
            elif converted:
                live.update(valid=False,cursor=None,invalid_reason='unrecorded frame key input')
        with self._history_internal():
            if manifest is not None and converted:
                self._history_pending(manifest,manifest['cursor'],'renderer-input',receipt=dict(edges=deepcopy(converted)))
            receipt = self._frame_keys_apply(native,converted,held)
            if manifest is not None and converted:
                try:
                    journal = manifest.setdefault('input_journal',[])
                    journal.append(deepcopy(receipt))
                    manifest.setdefault('pending_inputs',[]).append(deepcopy(receipt))
                    manifest['input_dirty'] = True
                    updated, artifact = self._history_new_revision(manifest)
                    self._qemu_history_live.update(history=artifact['artifact'],fingerprint=self._history_live_fingerprint())
                except BaseException as error:
                    error.result = receipt
                    self.close()
                    raise
        if manifest is not None:
            try:
                receipt['timeline'] = self._frame_summary(self._frame_manifest())
            except BaseException as error:
                if converted:
                    error.result = deepcopy(receipt)
                    self.close()
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
        native = self._frame_keys_query(allow_foreign=True)
        physical['keyboard'] = dict(frame_keys=sorted(_CANONICAL[k] for k in native['held']),
                                    frame_edge_capacity=native['edge-capacity'],native=native)
        return physical
