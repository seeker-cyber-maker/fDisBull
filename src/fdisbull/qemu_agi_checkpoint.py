"""Private, source-bound native AGI checkpoints and staged owner replacement."""
import hashlib
import json
import re
import time

from .dosbox_rpc import DebuggerError

FORMAT = 'fdisbull-qemu-agi-state-1'
ERROR_FORMAT = 'fdisbull-qemu-agi-checkpoint-error-1'
PROPERTY = 'agi-debug-checkpoint-hex'
LIMIT = 16 * 1024 * 1024


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _digest(value):
    return _sha(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode())


def _remaining(deadline):
    value = int((deadline - time.monotonic()) * 1000)
    if value < 1:
        raise TimeoutError('AGI checkpoint deadline expired')
    return min(value, 600000)


def _timeout(value):
    if type(value) is not int or not 1 <= value <= 600000:
        raise ValueError('AGI checkpoint timeout must be 1..600000 ms')


def checkpoint_available(owner, deadline):
    entries = owner.qmp.call('qom-list', {'path': owner.cpu_path}, timeout_ms=_remaining(deadline))
    if not isinstance(entries, list):
        raise DebuggerError('Invalid AGI QOM property inventory')
    return any(isinstance(item, dict) and item.get('name') == PROPERTY and item.get('type') == 'string'
               for item in entries)


def _snapshot(owner, deadline):
    value = owner.qmp.call('qom-get', {'path': owner.cpu_path, 'property': PROPERTY},
                           timeout_ms=_remaining(deadline), max_reply_bytes=2 * LIMIT + 4096)
    if (not isinstance(value, str) or not value or len(value) > 2 * LIMIT
            or len(value) % 2 or re.fullmatch('[0-9a-f]+', value) is None):
        raise DebuggerError('Invalid native AGI checkpoint encoding')
    return bytes.fromhex(value)


def _read_json(owner, property_name, deadline):
    value = owner.qmp.call('qom-get', {'path': owner.cpu_path, 'property': property_name},
                           timeout_ms=_remaining(deadline), max_reply_bytes=4 * 1024 * 1024)
    try:
        result = json.loads(value)
    except (TypeError, ValueError) as error:
        raise DebuggerError('Invalid AGI native checkpoint observation') from error
    if not isinstance(result, dict):
        raise DebuggerError('Invalid AGI native checkpoint observation')
    return result


def _observation(owner, runtime, deadline):
    state = _read_json(owner, 'agi-state-json', deadline)
    if not isinstance(state.get('source'), dict) or not isinstance(state.get('guest'), dict):
        raise DebuggerError('Incomplete AGI native checkpoint observation')
    scene = _read_json(owner, 'agi-runtime-scene-json', deadline) if runtime else None
    registers = owner.gdb.registers()
    if set(registers) != {'pc'} or registers['pc'] is None:
        raise DebuggerError('Incomplete AGI checkpoint register readback')
    source, guest = state['source'], state['guest']
    logic_id = source.get('logic_id')
    logic_sha = source.get('logic_sha256') if runtime else source.get('sha256')
    pc = guest.get('pc')
    if (type(logic_id) is not int or not 0 <= logic_id <= 255 or
            type(pc) is not int or not 0 <= pc <= 65536 or
            not isinstance(logic_sha, str) or re.fullmatch('[0-9a-f]{64}', logic_sha) is None):
        raise DebuggerError('Invalid AGI checkpoint logical position')
    position = dict(logic_id=logic_id, pc=pc, source_sha256=logic_sha)
    return dict(source=source, guest_sha256=_digest(guest), registers=registers,
                logical_position=position,
                scene_sha256=_digest(scene) if scene is not None else None)


def _artifact_data(project, artifact):
    row = project.db.execute('SELECT a.kind,a.sha256,a.metadata,a.data,r.version '
        'FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run '
        'WHERE a.id=? AND fdb_length(a.data) BETWEEN 1 AND ?', (artifact, LIMIT)).fetchone()
    if row is None or row['kind'] != 'state':
        raise ValueError('Invalid AGI checkpoint artifact or byte bound')
    try:
        metadata = json.loads(row['metadata'])
    except (TypeError, ValueError) as error:
        raise ValueError('Invalid AGI checkpoint metadata') from error
    if (not isinstance(metadata, dict) or metadata.get('format') != FORMAT
            or not isinstance(metadata.get('identity'), dict)
            or metadata['identity'].get('source_sha256') != project.source_sha256(row['version'])
            or metadata['identity'].get('version_sha256') != project.version(row['version'])['sha256']
            or not isinstance(metadata.get('observation'), dict)
            or metadata.get('host_files_restored') is not False):
        raise ValueError('AGI checkpoint metadata or source identity differs')
    data = bytes(row['data'])
    if not 1 <= len(data) <= LIMIT or _sha(data) != row['sha256']:
        raise ValueError('AGI checkpoint payload hash differs')
    return row, data, metadata


def inspect_agi_state(project, artifact):
    row, data, metadata = _artifact_data(project, artifact)
    return dict(artifact=artifact, version=row['version'], sha256=row['sha256'], size=len(data),
                metadata=metadata, logical_position=metadata['observation'].get('logical_position'),
                components=[dict(name='agi-native-checkpoint', size=len(data))],
                scope='stopped native AGI checkpoint; host files excluded')


class AGICheckpointMixin:
    def _agi_checkpoint_admit(self):
        if self.project.db.in_transaction:
            raise ValueError('AGI checkpoint requires no caller transaction')
        if not self.capabilities.get('save_states'):
            raise ValueError('AGI native checkpoint interface is unavailable')
        self._stopped()
        row = self.project.db.execute('SELECT source_bytes FROM binary_info WHERE version=?',
                                      (self.version['id'],)).fetchone()
        if (not self.project.source_info(self.version['id']).get('verified') or row is None
                or row[0] is None or _sha(bytes(row[0])) != self.identity['source_sha256']
                or _sha(self._source_data) != self.identity['source_sha256']
                or _sha(self._executable.read_bytes()) != self.identity['qemu_sha256']
                or (_sha(self._runtime_package) if self._runtime_package is not None else None)
                != self.identity['runtime_package_sha256']):
            raise ValueError('AGI checkpoint source or native identity changed')

    def save_state(self, name='agi-checkpoint.bin', *, max_bytes=None, timeout_ms=60000):
        from .external_files import _file_name
        _file_name(name)
        _timeout(timeout_ms)
        if max_bytes is not None and (type(max_bytes) is not int or not 1 <= max_bytes <= LIMIT):
            raise ValueError('Invalid AGI checkpoint byte bound')
        deadline = time.monotonic() + timeout_ms / 1000
        owner = self.vm
        artifact = None
        try:
            with self._budget(owner, deadline):
                self._agi_checkpoint_admit()
                before = _observation(owner, self._runtime_package is not None, deadline)
                data = _snapshot(owner, deadline)
                after = _observation(owner, self._runtime_package is not None, deadline)
                if before != after:
                    raise DebuggerError('AGI state changed during checkpoint capture')
                if len(data) > (max_bytes or LIMIT):
                    raise ValueError('AGI checkpoint exceeds byte bound')
                metadata = dict(format=FORMAT, identity=dict(self.identity), observation=before,
                                host_files_restored=False)
                _remaining(deadline)
                artifact = self.project._debug_artifact(self.run_id, name, 'state', data, metadata)
                artifact['logical_position'] = before['logical_position']
            return artifact
        except BaseException as error:
            if artifact is not None and getattr(error, 'result', None) is None:
                error.result = dict(format=ERROR_FORMAT, artifact=artifact, do_not_replay=True,
                                    disposition='publication completed')
            raise

    def load_state(self, artifact, *, timeout_ms=60000):
        from .qemu_agi import _Owner
        _timeout(timeout_ms)
        deadline = time.monotonic() + timeout_ms / 1000
        old = self.vm
        if not old.lock.acquire(timeout=_remaining(deadline) / 1000):
            raise TimeoutError('AGI checkpoint owner is busy')
        candidate = None
        transition = False
        adopted = False
        try:
            with self._budget(old, deadline):
                self._agi_checkpoint_admit()
                row, data, metadata = _artifact_data(self.project, artifact)
                if row['version'] != self.version['id']:
                    raise ValueError('AGI checkpoint belongs to another project version')
                if metadata.get('identity') != self.identity:
                    raise ValueError('AGI checkpoint identity or payload differs')
                candidate = _Owner(self._executable, self._source_data, deadline=deadline,
                                   runtime_package=self._runtime_package)
                candidate.qmp.operation_deadline = deadline
                candidate.gdb.operation_deadline = deadline
                if not checkpoint_available(candidate, deadline):
                    raise ValueError('AGI candidate lacks native checkpoint interface')
                if _sha(self._executable.read_bytes()) != self.identity['qemu_sha256']:
                    raise ValueError('AGI native binary changed during restore')
                candidate.qmp.call('qom-set', {'path': candidate.cpu_path, 'property': PROPERTY,
                                              'value': data.hex()}, timeout_ms=_remaining(deadline))
                if (_snapshot(candidate, deadline) != data or
                        _observation(candidate, self._runtime_package is not None, deadline)
                        != metadata['observation']):
                    raise DebuggerError('Restored AGI native checkpoint readback differs')
                _remaining(deadline)
                result = dict(artifact=artifact, sha256=_sha(data), verified=True,
                              observation=metadata['observation'],
                              logical_position=metadata['observation'].get('logical_position'),
                              host_files_restored=False)
            # Keep the original lock held through the owner transition.
            transition = True
            old.close()
            candidate.lock = old.lock
            self.vm = self.rpc = candidate
            self.cpu_path = candidate.cpu_path
            adopted = True
            candidate.qmp.operation_deadline = None
            candidate.gdb.operation_deadline = None
            candidate = None
            self._event('machine-load-state', result)
            return result
        except BaseException as error:
            if transition:
                if getattr(error, 'result', None) is None:
                    error.result = dict(format=ERROR_FORMAT, restore=result, do_not_replay=True,
                                        owner_adopted=adopted,
                                        disposition='owner transition or provenance uncertain')
                try:
                    self.close()
                except BaseException:
                    pass
                if isinstance(getattr(error, 'result', None), dict):
                    error.result['owner_closed'] = self._owner_reaped()
            raise
        finally:
            try:
                if candidate is not None:
                    candidate.close()
            finally:
                old.lock.release()
