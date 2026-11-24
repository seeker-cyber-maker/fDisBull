"""Private, identity-bound AGI guest save artifacts."""
import hashlib
import json
import re
import time

from .dosbox_rpc import DebuggerError
from .qemu_agi_checkpoint import _identity_admit
from .qemu_agi_reply import MAX_GUEST_SNAPSHOT_BYTES

FORMAT = 'fdisbull-qemu-agi-guest-save-1'
ERROR_FORMAT = 'fdisbull-qemu-agi-guest-save-error-1'
KIND = 'agi-guest-save'
PROPERTY = 'agi-runtime-snapshot-hex'


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _validate_envelope(data, identity):
    package_sha = identity.get('runtime_package_sha256')
    if (not isinstance(package_sha, str) or re.fullmatch('[0-9a-f]{64}', package_sha) is None
            or not data.startswith(b'FDBAGIS1' + package_sha.encode('ascii') + b'\0')):
        raise ValueError('AGI guest save header or runtime resource identity differs')
    if len(data) < 88:
        raise ValueError('AGI guest save envelope is truncated')
    # AgiRuntimeSnapshotHeader v1 pads the ASCIIZ resource digest to offset 76,
    # followed by three native-order uint32 fields: state size, endian marker, version.
    marker = data[80:84]
    if marker == b'\x04\x03\x02\x01':
        byteorder = 'little'
    elif marker == b'\x01\x02\x03\x04':
        byteorder = 'big'
    else:
        raise ValueError('AGI guest save endian marker is invalid')
    size = int.from_bytes(data[76:80], byteorder)
    version = int.from_bytes(data[84:88], byteorder)
    if version != 1:
        raise ValueError('AGI guest save envelope version is unsupported')
    if not size or size != len(data) - 88:
        raise ValueError('AGI guest save state length differs from envelope')


def artifact_data(session, artifact):
    if type(artifact) is not str or not artifact:
        raise ValueError('Invalid AGI guest save artifact')
    row = session.project.db.execute(
        'SELECT a.sha256,a.metadata,a.data FROM debug_artifacts a '
        'JOIN debug_runs r ON r.id=a.run WHERE a.id=? AND a.kind=? AND r.version=? '
        'AND fdb_length(a.data) BETWEEN 1 AND ?',
        (artifact, KIND, session.version['id'], MAX_GUEST_SNAPSHOT_BYTES)).fetchone()
    if row is None:
        raise ValueError('Invalid AGI guest save artifact or project version')
    try:
        metadata = json.loads(row['metadata'])
    except (TypeError, ValueError) as error:
        raise ValueError('Invalid AGI guest save metadata') from error
    if (not isinstance(metadata, dict) or metadata.get('format') != FORMAT
            or metadata.get('identity') != session.identity):
        raise ValueError('AGI guest save identity differs')
    data = bytes(row['data'])
    if (not 1 <= len(data) <= MAX_GUEST_SNAPSHOT_BYTES or _sha(data) != row['sha256']
            or metadata.get('payload_sha256') != row['sha256']
            or type(metadata.get('payload_size')) is not int or metadata['payload_size'] != len(data)):
        raise ValueError('AGI guest save payload hash or size differs')
    _validate_envelope(data, session.identity)
    return data


def capture(session, ticket, *, name, timeout_ms):
    from .external_files import _file_name
    from .qemu_agi import _remaining, _timeout
    _file_name(name)
    _timeout(timeout_ms)
    if type(ticket) is not int or not 1 <= ticket <= 0xffffffffffffffff:
        raise ValueError('AGI guest save ticket must be a positive uint64')
    if session.project.db.in_transaction:
        raise ValueError('AGI guest save requires no caller transaction')
    deadline = time.monotonic() + timeout_ms / 1000
    artifact = None
    try:
        with session._budget(session.vm, deadline):
            if not session.capabilities.get('agi_guest_saves'):
                raise ValueError('AGI native guest save interface is unavailable')
            session._stopped()
            _identity_admit(session, context='guest save')
            before = session._state()
            guest = before.get('guest')
            pending = guest.get('pending_effect') if isinstance(guest, dict) else None
            if (not isinstance(pending, dict) or guest.get('status') != 'pending'
                    or type(pending.get('id')) is not int or pending['id'] != ticket
                    or type(pending.get('opcode')) is not int or pending['opcode'] != 125
                    or pending.get('reply') != 'ack'):
                raise ValueError('AGI guest save ticket does not match the current save.game request')
            value = session.vm.qmp.call('qom-get', {'path': session.cpu_path, 'property': PROPERTY},
                timeout_ms=_remaining(deadline), max_reply_bytes=2 * MAX_GUEST_SNAPSHOT_BYTES + 4096)
            if (not isinstance(value, str) or not value or len(value) > 2 * MAX_GUEST_SNAPSHOT_BYTES
                    or len(value) % 2 or re.fullmatch('[0-9a-fA-F]+', value) is None):
                raise DebuggerError('Invalid native AGI guest save encoding')
            data = bytes.fromhex(value)
            _validate_envelope(data, session.identity)
            if session._state() != before:
                raise DebuggerError('AGI state changed during guest save capture')
            metadata = dict(format=FORMAT, identity=dict(session.identity), ticket=ticket,
                            payload_sha256=_sha(data), payload_size=len(data))
            _remaining(deadline)
            artifact = session.project._debug_artifact(session.run_id, name, KIND, data, metadata)
        return artifact
    except BaseException as error:
        if artifact is not None and getattr(error, 'result', None) is None:
            error.result = dict(format=ERROR_FORMAT, artifact=artifact, do_not_replay=True,
                                disposition='publication completed')
        raise
