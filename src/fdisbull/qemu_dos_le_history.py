"""Capture-only, source-qualified LE checkpoint DAGs, separate from MZ history."""
from copy import deepcopy
from functools import wraps
import sys

from .qemu_dos_history import (
    MAX_NODES, MAX_HISTORY_BYTES, MAX_STATE, QemuDOSHistoryMixin,
    _READ_ONLY, _hex_digest, _history_operation, _positive_int,
)

FORMAT = 'fdisbull-qemu-dos-le-history-1'


def _checkpoints():
    from . import qemu_dos_le_checkpoint
    return qemu_dos_le_checkpoint


def _source_identity(session):
    from .le import load_runtime_le_carrier
    from .qemu_dos_source_admission import _source
    raw, _ = _source(session, session.metadata['source_sha256'])
    image = load_runtime_le_carrier(raw)
    return dict(source_view='embedded-le',
                application_source_sha256=image.metadata['le']['application_source_sha256'])


def _capture_only(function):
    bounded = _history_operation(function)

    @wraps(function)
    def invoke(self, count=1, timeout_ms=60000, *, advance='capture'):
        # Reject unsupported execution before even invoking the history guard.
        if type(count) is not int or count != 1 or advance != 'capture':
            raise ValueError('LE history records one stopped capture; stepping is unsupported')
        return bounded(self, count=count, timeout_ms=timeout_ms, advance=advance)
    return invoke


class LESourceHistoryProvider(QemuDOSHistoryMixin):
    HISTORY_FORMAT = FORMAT

    def __init__(self, owner):
        object.__setattr__(self, '_owner', owner)

    def __getattr__(self, name):
        return getattr(self._owner, name)

    def __setattr__(self, name, value):
        if name == '_owner':
            object.__setattr__(self, name, value)
        else:
            aliases = {'_qemu_history_live':'_qemu_le_history_live', '_history_busy':'_le_history_busy'}
            setattr(self._owner, aliases.get(name, name), value)

    @property
    def _qemu_history_live(self):
        return getattr(self._owner, '_qemu_le_history_live', None)

    @property
    def _history_busy(self):
        return getattr(self._owner, '_le_history_busy', False)

    def close(self):
        primary = sys.exception()
        self.vm._fdisbull_control_quarantine = (getattr(self.vm, '_fdisbull_control_quarantine', None)
                                               or 'uncertain LE history operation')
        try:
            self._owner.close()
        except BaseException as cleanup:
            if primary is None:
                raise
            primary.le_history_cleanup_error = type(cleanup).__name__

    def _history_bind(self):
        vm = self.vm
        previous = getattr(vm, 'history_operation_guard', None)
        if getattr(previous, '_qemu_le_history_owner', None) is self:
            return

        def chained(name, args=(), kwargs=None):
            if previous is not None:
                previous(name, args, kwargs or {})
            self._history_before_operation(name, args, kwargs or {})

        chained._qemu_le_history_owner = self
        chained._qemu_dos_history_owner = getattr(previous, '_qemu_dos_history_owner', None)
        vm.history_operation_guard = chained

    def _history_before_operation(self, name, args=(), kwargs=None):
        # The preceding legacy guard owns its CPU/provenance checks. Our busy
        # scope must never suppress the actual session's MZ history guard.
        kwargs = kwargs or {}
        readonly = name in _READ_ONLY and name not in ('dos_source_bind', 'dos_source_unbind')
        if name in ('layers', 'dos_task_layers'):
            readonly = kwargs.get('active', args[0] if args else None) is None
        if self._history_busy or readonly:
            return
        live = self._qemu_history_live
        if live and live.get('valid'):
            live.update(valid=False, cursor=None, invalid_reason='unrecorded operation: '+str(name))

    def _history_identity(self):
        identity = super()._history_identity()
        identity.update(_source_identity(self._owner))
        return identity

    def _history_admission(self):
        from .qemu_owned_checkpoint import _preflight
        from .qemu_dos_checkpoint import _serial_idle
        _preflight(self._owner)
        _serial_idle(self._owner)

    def _history_require_live(self):
        super()._history_require_live()
        binding = getattr(self._owner, '_le_source', None)
        valid = getattr(self._owner, '_le_source_owner_valid', None)
        if (not isinstance(binding, dict) or binding.get('state') != 'qualified-stopped'
                or not callable(valid) or not valid(binding)):
            raise ValueError('LE history requires the current qualified stopped source binding')

    def _history_live_fingerprint(self):
        result = super()._history_live_fingerprint()
        binding = getattr(self._owner, '_le_source', None)
        if not isinstance(binding, dict):
            result['le_source'] = None
        else:
            from .qemu_dos_le_binding import _producer
            recipe = binding.get('recipe', {})
            valid = getattr(self._owner, '_le_source_owner_valid', None)
            producer = deepcopy(binding.get('producer'))
            try:
                producer_current = producer == _producer()
            except OSError:
                producer_current = False
            result['le_source'] = dict(handle=id(binding), binding_id=recipe.get('binding_id'),
                capture_epoch=recipe.get('capture_epoch'), state=binding.get('state'),
                generation=binding.get('generation'), owner_valid=bool(callable(valid) and valid(binding)),
                producer=producer, producer_current=producer_current,
                owner=id(self.vm), process=id(getattr(self.vm, 'process', None)))
        return result

    def _history_base_response(self):
        response = super()._history_base_response()
        response.update(implementation='immutable full LE source checkpoints; explicit stopped captures only',
            source_view='embedded-le', recording='capture-only; unobserved intervals are not instruction histories',
            checkpoint_scope='owned native machine plus saved/revalidated LE source identity; no MZ allocation lifetime')
        return response

    @classmethod
    def _validate_manifest(cls, manifest):
        super()._validate_manifest(manifest)
        identity = manifest['identity']
        if (identity.get('source_view') != 'embedded-le'
                or not _hex_digest(identity.get('application_source_sha256'))):
            raise ValueError('LE history source identity is invalid')
        for node in manifest['nodes']:
            cp = node['checkpoint']
            machine = cp.get('machine')
            if (type(cp.get('manifest_size')) is not int or cp['manifest_size'] < 1
                    or not isinstance(machine, dict) or set(machine) != {'artifact', 'sha256', 'size'}
                    or not isinstance(machine['artifact'], str) or not machine['artifact']
                    or not _hex_digest(machine['sha256']) or type(machine['size']) is not int
                    or machine['size'] < 1 or cp['size'] != cp['manifest_size'] + machine['size']
                    or cp['size'] > MAX_STATE or node['edge'].get('kind') not in ('root', 'capture')):
                raise ValueError('LE history checkpoint index or capture edge is invalid')

    def _history_checkpoint(self, *, remaining_bytes, node_name):
        limit = min(MAX_STATE, max(1, remaining_bytes))
        before = self._history_disk_bytes()
        saved = _checkpoints().save_le_source_state(self._owner, node_name, max_bytes=limit,
                                                  timeout_ms=self._history_remaining_ms())
        after = self._history_disk_bytes()
        checked = _checkpoints().read_le_source_state(self._owner, saved['artifact'], full_machine=False)
        if any(saved.get(key) != checked.get(key) for key in
               ('artifact', 'sha256', 'size', 'charged_size', 'machine')):
            raise ValueError('LE checkpoint readback differs from its capture receipt')
        if type(checked.get('charged_size')) is not int or not 1 <= checked['charged_size'] <= limit:
            raise ValueError('LE history checkpoint exceeds its charged byte budget')
        return dict(artifact=checked['artifact'], sha256=checked['sha256'], size=checked['charged_size'],
            manifest_size=checked['size'], machine=deepcopy(checked['machine']),
            live_disk_bytes_before=before, live_disk_bytes_after=after,
            live_disk_bytes_growth=None if before is None or after is None else max(0, after-before))

    def _history_capacity(self, manifest, parent, count):
        used = super()._history_capacity(manifest, parent, count)
        if manifest['max_bytes'] - used <= _checkpoints().MAX_DESCRIPTOR:
            raise ValueError('LE history cannot reserve the source checkpoint descriptor budget')
        return used

    def _history_state_artifact(self, checkpoint):
        checked = _checkpoints().read_le_source_state(self._owner, checkpoint['artifact'], full_machine=False)
        expected = dict(artifact=checkpoint['artifact'], sha256=checkpoint['sha256'],
            size=checkpoint['manifest_size'], charged_size=checkpoint['size'], machine=checkpoint['machine'])
        if any(checked.get(key) != value for key, value in expected.items()):
            raise ValueError('LE history checkpoint reference differs from its retained source state')
        return checked

    def _history_prepare_restore(self, manifest, target):
        return self._history_state_artifact(target['checkpoint'])

    def _history_load_prepared(self, prepared, *, timeout_ms):
        return _checkpoints().load_le_source_state(self._owner, prepared['artifact'], timeout_ms=timeout_ms)

    def _history_verify_restored(self, restored):
        self._history_require_live()
        mapping = self._process.get('source_mapping', {})
        if (self.closed or not isinstance(restored, dict)
                or restored.get('le_source_checkpoint_restored') is not True
                or restored.get('protected_source_rebound') is not True
                or restored.get('machine_state_restored') is not True
                or restored.get('source_binding_restored') is not False
                or restored.get('capture_epoch') != self._runtime_epoch
                or mapping.get('live') is not False or mapping.get('live_ranges') != []):
            raise ValueError('LE history restore did not verify its scoped source checkpoint')

    @_history_operation
    def rewind_start(self, max_steps=16, max_bytes=536870912, *, history=None, timeout_ms=60000):
        _positive_int(max_steps, 'max_steps', 1, MAX_NODES)
        _positive_int(max_bytes, 'max_bytes', 1, MAX_HISTORY_BYTES)
        self._history_supported()
        if history is None:
            if max_bytes <= _checkpoints().MAX_DESCRIPTOR:
                raise ValueError('LE history root must reserve the source checkpoint descriptor budget')
            _checkpoints().admit_le_source_capture(self._owner, timeout_ms=self._history_remaining_ms())
        return QemuDOSHistoryMixin.rewind_start.__wrapped__(self, max_steps=max_steps, max_bytes=max_bytes,
                                                          history=history, timeout_ms=timeout_ms)

    @_capture_only
    def rewind_record(self, count=1, timeout_ms=60000, *, advance='capture'):
        self._history_supported()
        _checkpoints().admit_le_source_capture(self._owner, timeout_ms=self._history_remaining_ms())
        return QemuDOSHistoryMixin.rewind_record.__wrapped__(self, count=count, timeout_ms=timeout_ms,
                                                           advance=advance)


def get_provider(session):
    # The legacy chain retains selected-undo/provenance guards independently
    # of this provider's own capture busy scope.
    session._history_bind()
    provider = getattr(session, '_qemu_le_history_provider', None)
    if provider is None:
        provider = LESourceHistoryProvider(session)
        session._qemu_le_history_provider = provider
    elif not isinstance(provider, LESourceHistoryProvider) or provider._owner is not session:
        raise ValueError('LE history provider belongs to another session')
    provider._history_bind()
    return provider
