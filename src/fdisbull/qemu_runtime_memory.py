"""Witnessed RAM views on one owned, stopped QEMU DOS machine.

Bindings are caller-declared byte witnesses, not recovered source mappings or
allocation lifetimes. Physical addresses remain physical across CPU modes;
linear addresses require observed unpaged translation. Native task-private
views, layers, paged linear mappings and device memory require other APIs.
"""
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
import inspect
import json
import re
import time
import uuid

from .operation_budget import request_deadline
from .runtime_observations import _int, _memory_context, RuntimeMemoryWriteError


def validate_binding(name, address, *, length, expected_hex, mask_hex=None,
                     provenance, space='linear'):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9.:-]{0,127}', name):
        raise ValueError('Invalid runtime binding name')
    _int(address, 0, 0xffffffff, 'runtime address')
    _int(length, 1, 65536, 'runtime binding length')
    if address + length > 0x100000000:
        raise ValueError('Runtime binding crosses the 32-bit address limit')
    if space not in ('linear', 'physical'):
        raise ValueError('Runtime address space must be linear or physical')
    try:
        expected = bytes.fromhex(expected_hex)
        mask = bytes.fromhex(mask_hex) if mask_hex is not None else b'\xff' * len(expected)
    except (TypeError, ValueError):
        raise ValueError('Invalid identity witness') from None
    if not expected or len(expected) > length or len(mask) != len(expected) or not any(mask):
        raise ValueError('Invalid identity witness')
    if not isinstance(provenance, (dict, list, str)) or not provenance:
        raise ValueError('Nonempty provenance required')
    if len(json.dumps(provenance, allow_nan=False, ensure_ascii=False).encode()) > 65536:
        raise ValueError('Runtime provenance exceeds 64 KiB')
    return expected, mask


def validate_view(binding, *, offset=0, length=16):
    if not isinstance(binding, str) or not 1 <= len(binding) <= 128:
        raise ValueError('Expected a runtime binding name or ID')
    _int(offset, 0, 65535, 'runtime view offset')
    _int(length, 1, 65536, 'runtime view length')
    if offset + length > 65536:
        raise ValueError('Runtime view exceeds the maximum binding length')


def validate_write(binding, data_hex, *, expected_hex, offset=0):
    from .debug_state import byte_string
    data, expected = byte_string(data_hex), byte_string(expected_hex)
    if len(data) != len(expected):
        raise ValueError('Runtime RAM edits cannot resize a binding')
    validate_view(binding, offset=offset, length=len(data))
    return data, expected


def validate_script_parameters(operation, params, *, session=None):
    """Check every literal, even when another field is a result reference."""
    def reference(value):
        return isinstance(value, str) and value.startswith('$')
    if operation == 'bind-runtime-memory':
        samples = dict(name='reference', address=0, length=65536, expected_hex='00',
                       mask_hex=None, provenance='reference', space='physical')
        checked = {key: samples[key] if reference(value) else value for key, value in params.items()}
        if reference(params.get('length')):
            address = checked['address']
            if type(address) is int and 0 <= address <= 0xffffffff:
                checked['length'] = min(65536, 0x100000000 - address)
        if reference(params.get('expected_hex')) and checked.get('mask_hex') is not None:
            try:
                checked['expected_hex'] = '00' * len(bytes.fromhex(checked['mask_hex']))
            except (TypeError, ValueError):
                raise ValueError('Invalid identity witness') from None
        validate_binding(**checked)
        if (session is not None and not reference(params['address'])
                and not reference(params['length'])):
            session._layer_ram_extent(params['address'], params['length'])
    elif operation == 'runtime-memory':
        samples = dict(binding='reference', offset=0, length=1)
        validate_view(**{key: samples[key] if reference(value) else value for key, value in params.items()})
    else:
        from .debug_state import byte_string
        data = next((byte_string(params[key]) for key in ('data_hex', 'expected_hex')
                     if not reference(params[key])), b'\0')
        validate_view('reference' if reference(params['binding']) else params['binding'],
                      offset=0 if reference(params.get('offset')) else params.get('offset', 0),
                      length=len(data))


@contextmanager
def _scope(session, name, args, kwargs):
    """Use the ordinary guards with one deadline and an unchanged lock owner."""
    from .qemu_machine import _machine_operation_guard
    owner = session.vm
    if owner is None or getattr(owner, 'lock', None) is None:
        raise ValueError('Runtime observation requires its live owned machine')
    deadline = request_deadline(session, 10000)

    def limits():
        return [deadline, getattr(session, '_deadline', None),
                getattr(owner, 'operation_deadline', None),
                *(getattr(channel, 'operation_deadline', None) for channel in
                  (getattr(owner, 'qmp', None), getattr(owner, 'gdb', None)) if channel is not None)]

    deadline = min(value for value in limits() if value is not None)
    wait = min(10.0, deadline - time.monotonic())
    if wait <= 0 or not owner.lock.acquire(timeout=wait):
        raise TimeoutError('Runtime observation could not acquire its machine before the deadline')
    saved = None
    try:
        if session.vm is not owner:
            raise ValueError('Runtime observation owner changed during lock admission')
        deadline = min(value for value in limits() if value is not None)
        if time.monotonic() >= deadline:
            raise TimeoutError('Runtime observation deadline expired before admission')
        _machine_operation_guard(owner, name, args, kwargs)
        channels = [(channel, getattr(channel, 'operation_deadline', None)) for channel in
                    (getattr(owner, 'qmp', None), getattr(owner, 'gdb', None)) if channel is not None]
        saved = (getattr(session, '_rpc_deadline', None), getattr(session, '_deadline', None),
                 getattr(owner, 'operation_deadline', None), channels)
        session._rpc_deadline = session._deadline = owner.operation_deadline = deadline
        for channel, _ in channels:
            channel.operation_deadline = deadline
        yield deadline
    except BaseException as error:
        channels = (getattr(owner, 'qmp', None), getattr(owner, 'gdb', None))
        if (not getattr(owner, '_fdisbull_control_quarantine', None)
                and any(channel is not None and hasattr(channel, 'socket') and channel.socket is None
                        for channel in channels)):
            try:
                owner.close()
            except BaseException as cleanup_error:
                error.runtime_memory_cleanup_error = type(cleanup_error).__name__
        raise
    finally:
        if saved is not None:
            session._rpc_deadline, session._deadline, owner.operation_deadline, channels = saved
            for channel, previous in channels:
                channel.operation_deadline = previous
            for channel in (getattr(owner, 'qmp', None), getattr(owner, 'gdb', None)):
                if channel is not None and not any(channel is old for old, _ in channels):
                    channel.operation_deadline = saved[2]
        owner.lock.release()


def _operation(validator, *, write=False):
    def decorate(function):
        signature = inspect.signature(function)
        @wraps(function)
        def invoke(self, *args, **kwargs):
            arguments = signature.bind(self, *args, **kwargs)
            arguments.apply_defaults()
            validator(**{key: value for key, value in arguments.arguments.items() if key != 'self'})
            result = None
            try:
                with _scope(self, function.__name__, args, kwargs) as deadline:
                    result = function(self, *args, **kwargs)
                    if time.monotonic() >= deadline:
                        error = TimeoutError('Runtime observation exceeded its host deadline')
                        error.result = result
                        raise error
                    return result
            except BaseException as error:
                # The method handles uncertain dispatch itself. This covers an
                # expired outer deadline after a verified result was returned.
                if write and result is not None and not self.closed:
                    try:
                        self.close()
                    except BaseException as cleanup_error:
                        error.runtime_memory_cleanup_error = type(cleanup_error).__name__
                raise
        return invoke
    return decorate


def _masked_equal(actual, expected, mask):
    return len(actual) == len(expected) and all(
        a & m == e & m for a, e, m in zip(actual, expected, mask, strict=True))


class QemuRuntimeMemoryMixin:
    def _runtime_lifetime(self):
        process = getattr(self, '_process', None) or {}
        partial = getattr(self, '_qemu_cpu_delta_history', None) or {}
        return dict(run=self.run_id, version=self.version['id'],
            epoch=self._runtime_epoch, checkpoint_epoch=getattr(self, '_checkpoint_epoch', 0),
            source_sha256=self.metadata.get('source_sha256'),
            version_sha256=self.metadata.get('version_sha256'),
            process_epoch=process.get('capture_epoch'), psp_segment=process.get('psp_segment'),
            process_state=process.get('state'), machine_closed=bool(process.get('machine_closed')),
            selected_projection=(dict(history=partial.get('id'), cursor=partial.get('cursor'))
                                 if partial.get('frozen') else None))

    def _runtime_state(self):
        # Other observation helpers call this initializer. In particular it
        # must never replace QEMU's run:process:N capture epoch with a UUID.
        owners = (self.vm, getattr(self.vm, 'process', None), self.project)
        lifetime = self._runtime_lifetime()
        old = getattr(self, '_qemu_runtime_owners', ())
        if (len(old) != len(owners) or any(left is not right for left, right in zip(old, owners))
                or getattr(self, '_qemu_runtime_lifetime', None) != lifetime):
            self._runtime_bindings, self._runtime_names = {}, {}
            self._qemu_runtime_owners, self._qemu_runtime_lifetime = owners, lifetime
            self._qemu_runtime_generation = uuid.uuid4().hex
        return self._runtime_bindings

    def _invalidate_runtime_bindings(self):
        self._runtime_state()
        self._runtime_bindings.clear()
        self._runtime_names.clear()
        self._qemu_runtime_generation = uuid.uuid4().hex

    def _runtime_admit(self):
        vm, process = self.vm, getattr(self, '_process', None)
        native = getattr(vm, 'process', None)
        if (self.closed or vm.qmp is None or native is None or not callable(getattr(native, 'poll', None))
                or native.poll() is not None or not isinstance(process, dict)
                or process.get('machine_closed') or process.get('capture_epoch') != self._runtime_epoch):
            raise ValueError('Runtime observation requires its live owned machine and capture epoch')
        if self.project.db.in_transaction:
            raise ValueError('Runtime observation requires a project outside a caller-owned transaction')
        if (vm.machine_configuration.get('cpus') != 1
                or type(vm.machine_configuration.get('memory_mib')) is not int):
            raise ValueError('Runtime observation requires one configured vCPU and known PC RAM')
        version = self.project.version(self.version['id'])
        if (self.metadata.get('source_sha256') != self.project.meta['source_sha256']
                or self.metadata.get('version_sha256') != version['sha256']
                or self.version['sha256'] != version['sha256']):
            raise ValueError('Runtime binding source or version context changed')
        if any(getattr(self, key, None) for key in ('_layer_active', '_layer_exec', '_layer_ram_applied',
                '_dos_task_binding', '_dos_task_monitor', '_dos_task_views', '_dos_scheduler')):
            raise ValueError('Runtime bindings require ordinary machine RAM without active layers or task-private views')

    def _runtime_paused(self):
        self._runtime_admit()
        self._stopped()
        registers = self.registers()
        state = registers.get('address_state', {})
        mode = registers.get('cpu_mode')
        if (mode not in ('real', 'protected', 'v86') or state.get('cpu_mode') != mode
                or state.get('machine_vcpus') != 1 or state.get('register_context_match') is not True):
            raise ValueError('Runtime observation requires one observed real, protected or v86 CPU context')
        stop = self.vm.qmp.call('query-status')
        if not isinstance(stop, dict) or stop.get('running') is not False:
            raise ValueError('Runtime observation requires a paused guest')
        control = state.get('control', {})
        context = dict(cpu_mode=mode, paging_enabled=state.get('paging'),
            cr0=control.get('CR0'), cr3=control.get('CR3'), cr4=control.get('CR4'),
            a20_enabled=state.get('a20'), code_bits=state.get('code_bits'), stack_bits=state.get('stack_bits'))
        return dict(observation_cpu_mode=mode, observation_address_context=context,
                    registers=deepcopy(registers), stop=deepcopy(stop))

    def _runtime_domain(self, stopped, address, length, space):
        domain = _memory_context(stopped, space)
        if space == 'linear':
            if stopped['observation_cpu_mode'] == 'real' and address + length > 0x100000:
                raise ValueError('Runtime binding crosses real-mode linear limit')
            if not domain['a20_enabled'] and address + length > 0x100000:
                raise ValueError('Extended linear bindings require observed A20 enablement')
        # Reuse the existing positive PC RAM qualification; no reads, layer
        # activation, source inference or native extension are needed here.
        self._layer_ram_extent(address, length)
        return domain

    def _runtime_identity(self, domain):
        self._runtime_state()
        return dict(self._runtime_lifetime(), owner_generation=self._qemu_runtime_generation,
                    memory_context=deepcopy(domain), runtime_load=None)

    def _runtime_read(self, address, length, space):
        result = self.memory(address, length=length, space='virtual' if space == 'linear' else 'physical')
        try:
            data = bytes.fromhex(result['hex'])
        except (KeyError, TypeError, ValueError):
            raise ValueError('Incomplete runtime memory capture') from None
        if len(data) != length:
            raise ValueError('Incomplete runtime memory capture')
        return data

    def _runtime_recheck(self, before, identity, item):
        after = self._runtime_paused()
        domain = self._runtime_domain(after, item['address'], item['length'], item['space'])
        if before != after or identity != self._runtime_identity(domain):
            raise ValueError('Runtime binding CPU, address context or owner changed during observation')
        return after

    @_operation(validate_binding)
    def bind_runtime_memory(self, name, address, *, length, expected_hex, mask_hex=None,
                            provenance, space='linear'):
        expected, mask = validate_binding(name, address, length=length, expected_hex=expected_hex,
                                         mask_hex=mask_hex, provenance=provenance, space=space)
        self._runtime_state()
        if name in self._runtime_names:
            raise ValueError('Runtime binding name already exists')
        before = self._runtime_paused()
        domain = self._runtime_domain(before, address, length, space)
        identity = self._runtime_identity(domain)
        actual = self._runtime_read(address, len(expected), space)
        item = dict(id=uuid.uuid4().hex, name=name, address=address, space=space, length=length,
            expected_hex=expected.hex(), mask_hex=mask.hex(), provenance=deepcopy(provenance),
            identity=identity, witness_hex=actual.hex(), observed_cpu_mode=before['observation_cpu_mode'],
            mapping_claim='explicit owned-machine RAM witness; no source, selector, task or allocation lifetime inference')
        self._runtime_recheck(before, identity, item)
        if not _masked_equal(actual, expected, mask):
            raise ValueError('Runtime identity witness mismatch')
        self._event('runtime-memory-bind', item)
        self._runtime_bindings[item['id']] = item
        self._runtime_names[name] = item['id']
        return deepcopy(item)

    @_operation(validate_view)
    def runtime_memory(self, binding, *, offset=0, length=16):
        self._runtime_state()
        key = self._runtime_names.get(binding, binding)
        if key not in self._runtime_bindings:
            raise ValueError('Unknown or invalidated runtime binding')
        item = self._runtime_bindings[key]
        if offset + length > item['length']:
            raise ValueError('Runtime view exceeds binding')
        before = self._runtime_paused()
        domain = self._runtime_domain(before, item['address'], item['length'], item['space'])
        if self._runtime_identity(domain) != item['identity']:
            raise ValueError('Runtime binding context changed')
        witness = self._runtime_read(item['address'], len(bytes.fromhex(item['expected_hex'])), item['space'])
        if not _masked_equal(witness, bytes.fromhex(item['expected_hex']), bytes.fromhex(item['mask_hex'])):
            raise ValueError('Runtime identity witness mismatch')
        data = self._runtime_read(item['address'] + offset, length, item['space'])
        self._runtime_recheck(before, item['identity'], item)
        result = dict(binding=item['id'], name=item['name'], offset=offset, length=length, hex=data.hex(),
            identity=deepcopy(item['identity']), witness_hex=witness.hex(), expected_hex=item['expected_hex'],
            mask_hex=item['mask_hex'])
        self._event('runtime-memory-read', result)
        return result

    @_operation(validate_write, write=True)
    def write_runtime_memory(self, binding, data_hex, *, expected_hex, offset=0):
        data, expected = validate_write(binding, data_hex, expected_hex=expected_hex, offset=offset)
        observed = self.runtime_memory(binding, offset=offset, length=len(data))
        if observed['hex'] != expected.hex():
            raise ValueError('Runtime RAM edit expected bytes mismatch; write refused')
        item = self._runtime_bindings[observed['binding']]
        before = self._runtime_paused()
        domain = self._runtime_domain(before, item['address'], item['length'], item['space'])
        if self._runtime_identity(domain) != item['identity']:
            raise ValueError('Runtime RAM edit address context changed; write refused')
        address = item['address'] + offset
        receipt = dict(kind='live-runtime-ram-edit', run=self.run_id, binding=item['id'],
            address=dict(space=item['space'], offset=f'0x{address:08X}'), length=len(data),
            state_restore_used=False, before_hex=expected.hex(), after_hex=None,
            verified=False, dispatch_outcome='unknown')
        self._event('runtime-memory-write-attempt', receipt)
        try:
            # Retain native expected-byte CAS, source/tracker retirement,
            # history/provenance guards and poisoned-channel cleanup.
            self.write_memory(address, data.hex(), expected_hex=expected.hex(),
                              space='virtual' if item['space'] == 'linear' else 'physical')
            actual = self._runtime_read(address, len(data), item['space'])
            if actual != data:
                raise ValueError('Runtime RAM edit readback mismatch')
            witness = self._runtime_read(item['address'], len(bytes.fromhex(item['expected_hex'])), item['space'])
            self._runtime_recheck(before, item['identity'], item)
            if self._runtime_bindings.get(item['id']) is not item:
                raise ValueError('Runtime RAM binding changed during the write')
            valid = _masked_equal(witness, bytes.fromhex(item['expected_hex']), bytes.fromhex(item['mask_hex']))
            if not valid:
                del self._runtime_bindings[item['id']]
                self._runtime_names.pop(item['name'], None)
            receipt.update(after_hex=actual.hex(), verified=True, dispatch_outcome='readback-verified',
                           binding_invalidated=not valid, frame_presentation_verified=False)
            self._event('runtime-memory-write', receipt)
            return receipt
        except BaseException as error:
            receipt.update(error_type=type(error).__name__, error=str(error),
                           verified=False, dispatch_outcome='unknown')
            try:
                self._event('runtime-memory-write-unknown', receipt)
            except BaseException as publication_error:
                receipt['publication_error'] = type(publication_error).__name__
            try:
                self.close()
            except BaseException as cleanup_error:
                receipt['cleanup_error'] = type(cleanup_error).__name__
            raise RuntimeMemoryWriteError(receipt, error) from error
