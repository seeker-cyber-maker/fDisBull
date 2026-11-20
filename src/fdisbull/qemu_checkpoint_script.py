"""Admission and evidence for the explicit full DOS checkpoint script profile."""
from contextlib import contextmanager
import json
import time

OPERATIONS = frozenset({'save-state', 'load-state', 'save-anchor-stone', 'load-anchor-stone'})


def validate_parameters(operation, params, *, session=None, references=True):
    from .external_files import _file_name
    from .qemu_dos_checkpoint import MAX_STATE, checkpoint_format
    if 'name' in params:
        _file_name(params['name'])
        if params['name'].startswith('$'):
            raise ValueError('Checkpoint script names must be literal')
    if params.get('max_bytes') is not None:
        value = params['max_bytes']
        if type(value) is not int or not 1 <= value <= MAX_STATE:
            raise ValueError('Checkpoint script max_bytes must be a literal integer in 1..134217728')
    if 'timeout_ms' in params:
        value = params['timeout_ms']
        if type(value) is not int or not 1 <= value <= 600000:
            raise ValueError('Checkpoint script timeout_ms must be a literal integer in 1..600000')
    artifact = params.get('artifact')
    if operation.startswith('load-'):
        if not isinstance(artifact, str) or not artifact or not references and artifact.startswith('$'):
            raise ValueError('Checkpoint script artifact must resolve to a nonempty identifier')
    if session is None:
        return
    from .qemu_dos_process import QemuDOSProcessSession
    from .qemu_dos_checkpoint import COMMAND
    if (not isinstance(session, QemuDOSProcessSession)
            or session.metadata.get('backend') != 'qemu-dos'
            or session.capabilities.get('save_states') is not True
            or COMMAND not in getattr(session.vm, 'qmp_commands', ())
            or getattr(session.vm, 'checkpoint_disk', None) is None
            or not getattr(session, '_checkpoint_launch', {}).get('checkpoint_tool')):
        raise ValueError('Unsupported operation for native QEMU scripts: full DOS process checkpoints are required')
    if session.project.db.in_transaction:
        raise ValueError('Full DOS checkpoint scripts require no caller transaction')
    if operation.startswith('load-') and not (references and artifact.startswith('$')):
        row = session.project.db.execute(
            'SELECT a.kind,a.metadata,r.version FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?',
            (artifact,)).fetchone()
        if row is None or row['kind'] != 'state' or row['version'] != session.version['id']:
            raise ValueError('Checkpoint script artifact must be a full state for the selected project version')
        metadata = json.loads(row['metadata'])
        if (not isinstance(metadata, dict) or metadata.get('format') != checkpoint_format(session)
                or metadata.get('source_sha256') != session.metadata['source_sha256']
                or metadata.get('version_sha256') != session.metadata['version_sha256']):
            raise ValueError('Checkpoint scripts require the matching full DOS process format/source/version; no entry, raw, owned-machine or LE fallback')


@contextmanager
def script_admission(session, timeout_ms):
    """Budget the existing QEMU script gate before installing shared fields."""
    from .debug_timeline import FrameTimelineSessionMixin
    from .operation_budget import request_deadline
    deadline = request_deadline(session, timeout_ms)
    def intersect():
        owner = session.vm
        return min(value for value in (deadline, getattr(session,'_deadline',None),
            getattr(session,'_rpc_deadline',None), getattr(owner,'operation_deadline',None),
            *(getattr(channel,'operation_deadline',None) for channel in
              (getattr(owner,'qmp',None),getattr(owner,'gdb',None)) if channel is not None))
            if value is not None)
    deadline = intersect()
    gate = FrameTimelineSessionMixin._timeline_gate(session)
    wait = min(10., deadline - time.monotonic())
    if wait <= 0 or not gate.acquire(timeout=wait):
        raise TimeoutError('QEMU script deadline expired waiting for its timeline gate')
    had_rpc = hasattr(session, '_rpc_deadline')
    previous = getattr(session, '_rpc_deadline', None)
    try:
        deadline = intersect()
        if time.monotonic() >= deadline:
            raise TimeoutError('QEMU script deadline expired before admission')
        session._rpc_deadline = deadline
        yield
    finally:
        if had_rpc:
            session._rpc_deadline = previous
        elif hasattr(session, '_rpc_deadline'):
            del session._rpc_deadline
        gate.release()


def retain_script_failure(error, report):
    """Keep primary native evidence separate from an observed script prefix."""
    error.script_result = report
    error._qemu_checkpoint_script_error = True
    return error
