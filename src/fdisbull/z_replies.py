"""Durable overflow replies for a single owned Z worker.

Delivery acknowledgement never certifies a game effect. Reading retained bytes
never calls the guest; releasing the delivery hold requires the same native
session/revision and leaves action/checkpoint recovery holds alone.
"""
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile

from .output_artifacts import ArtifactError, OutputArtifactStore, _json_decode, _private_directory


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


class ZReplyJournal:
    def __init__(self, work):
        self.root = Path(work) / 'z-replies'
        self.failed = False
        self._store = None
        self._identity = None

    def storage(self):
        root = _private_directory(self.root)
        info = root.stat()
        identity = (info.st_dev, info.st_ino)
        if self._identity is not None and identity != self._identity:
            raise ArtifactError('unsafe_path')
        self._identity = identity
        if self._store is None:
            self._store = OutputArtifactStore(root / 'artifacts')
        return self._store

    def _read(self, name):
        self.storage()
        path = self.root / name
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_size > 16384):
            raise ArtifactError('unsafe_receipt')
        return _json_decode(path.read_bytes())

    def _write(self, name, value, *, exclusive=False):
        self.storage()
        fd, temporary = tempfile.mkstemp(prefix='.receipt-', dir=self.root)
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(encoded(value)); output.flush(); os.fsync(output.fileno())
            if exclusive:
                os.link(temporary, self.root / name, follow_symlinks=False)
            else:
                os.replace(temporary, self.root / name)
            directory = os.open(self.root, os.O_RDONLY)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally:
            try: os.unlink(temporary)
            except FileNotFoundError: pass

    def state(self):
        if not self.root.exists() and not self.root.is_symlink():
            return {}
        try: state = self._read('state.json')
        except FileNotFoundError: return {'unavailable': True}
        if (not isinstance(state, dict) or not set(state) <= {'pending', 'accepted', 'unavailable'}
                or any(not isinstance(state[k], str) or not re.fullmatch(r'reply-[0-9a-f]{32}', state[k])
                       for k in ('pending', 'accepted') if k in state)
                or 'unavailable' in state and type(state['unavailable']) is not bool):
            raise ArtifactError('invalid_receipt_state')
        return state

    @property
    def blocked(self):
        try:
            state = self.state()
            return self.failed or bool(state.get('pending') or state.get('unavailable'))
        except (OSError, ValueError):
            self.failed = True
            return True

    def unavailable(self):
        self.failed = True
        try:
            state = self.state()
            self._write('state.json', {**state, 'unavailable': True})
        except (OSError, ValueError):
            pass  # The live worker remains held even if its disk cannot record the failure.

    def record(self, ident):
        if not isinstance(ident, str) or not re.fullmatch(r'reply-[0-9a-f]{32}', ident):
            raise ArtifactError('invalid_reply_id')
        if not self.root.exists():
            raise ArtifactError('reply_not_found')
        record = self._read(ident + '.json')
        if record.get('id') != ident:
            raise ArtifactError('invalid_receipt')
        metadata = self.storage().info(record['artifact']['id'])
        if metadata != record['artifact']:
            raise ArtifactError('integrity_error')
        return record

    @staticmethod
    def reference(record):
        return {'id': record['id'], 'artifact_id': record['artifact']['id'],
                **{k: record['artifact'][k] for k in ('sha256', 'bytes', 'media_type')}}

    def retain(self, data, binding, execution):
        if self.blocked:
            raise ArtifactError('reply_already_pending')
        # Persist a failure tombstone first: interruption while spilling must
        # never make an already executed action look safe to submit again.
        self._write('state.json', {'unavailable': True})
        artifact = self.storage().put_stream([data])
        record = {'format': 'fdisbull-z-retained-reply-1', 'id': 'reply-' + secrets.token_hex(16),
                  'artifact': artifact, 'binding': binding, 'execution': execution}
        self._write(record['id'] + '.json', record, exclusive=True)
        self._write('state.json', {'pending': record['id']})
        return self.status()

    def status(self):
        state = self.state()
        if self.failed or state.get('unavailable'):
            return {'complete': False, 'status': 'reply-unavailable', 'retry_safe': False,
                    'delivery_pending': True, 'message': 'Reply retention failed; do not replay the action.'}
        if not state.get('pending'):
            return {'complete': True, 'status': 'reply-clear', 'delivery_pending': False}
        record = self.record(state['pending'])
        return {'format': 'fdisbull-z-reply-ref-1', 'complete': False, 'status': 'reply-retained',
                'retry_safe': False, 'delivery_pending': True, 'reply': self.reference(record),
                'execution': record['execution'],
                'message': 'Read the retained reply; acknowledge delivery against the unchanged native session. Do not replay the action.'}

    def read(self, ident, offset=0, length=8192):
        record = self.record(ident)
        return {'complete': True, 'status': 'reply-data', 'reply_id': ident,
                **self.storage().read(record['artifact']['id'], offset, length)}

    def select(self, ident, pointer=''):
        record = self.record(ident)
        return {'status': 'reply-selection', 'reply_id': ident,
                **self.storage().select(record['artifact']['id'], pointer, max_bytes=16384)}

    def accept(self, ident, digest, binding):
        record = self.record(ident)
        state = self.state()
        if (self.failed or state.get('unavailable') or digest != record['artifact']['sha256']
                or binding is None or record['binding'] is None or binding != record['binding']
                or state.get('pending', state.get('accepted')) != ident):
            return {'complete': False, 'status': 'unresolved', 'delivery_pending': self.blocked,
                    'message': 'Receipt or native session changed; delivery hold preserved. Do not replay the action.'}
        already = not state.get('pending')
        self._write('state.json', {'accepted': ident})
        return {'complete': True, 'status': 'reply-already-accepted' if already else 'reply-accepted',
                'reply_id': ident, 'delivery_pending': False,
                'scope': 'delivery acknowledged; original action and checkpoint recovery are unchanged'}
