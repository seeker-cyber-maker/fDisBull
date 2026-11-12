"""Bound core tool replies while retaining original results as private artifacts.

Delivery completeness is separate from execution outcome. A spill never reruns
an operation, rolls it back, or authorizes a retry of uncertain effects.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import os

from .output_artifacts import ArtifactError, OutputArtifactStore

DEFAULT_INLINE_BYTES = 65536
MIN_INLINE_BYTES = 4096
MAX_INLINE_BYTES = 1048576
_policy = ContextVar('fdisbull_output_policy', default=None)


def _encoder():
    return json.JSONEncoder(ensure_ascii=True, separators=(',', ':'), allow_nan=False)


def validate_request_id(value):
    if value is not None and type(value) not in (str, int):
        raise ValueError('request id must be a string, integer or null')
    try:
        if len(_encoder().encode(value).encode('ascii')) > 256:
            raise ValueError('request id exceeds 256 encoded bytes')
    except (OverflowError, RecursionError):
        raise ValueError('invalid request id') from None
    return value


def _short(value):
    return value if isinstance(value, str) and len(value) <= 48 else None


def _execution(value, wrapped):
    body = value.get('result') if wrapped else value
    body = body if isinstance(body, dict) else {}
    return {'returned': True,
            'ok': value.get('ok') if wrapped else None,
            'complete': body.get('complete') if type(body.get('complete')) is bool else None,
            'status': _short(body.get('status'))}


class OutputPolicy:
    def __init__(self, max_inline_bytes=DEFAULT_INLINE_BYTES, artifact_dir=None, store=None):
        if type(max_inline_bytes) is not int or not MIN_INLINE_BYTES <= max_inline_bytes <= MAX_INLINE_BYTES:
            raise ValueError('inline output budget must be an integer from 4096 to 1048576 bytes')
        self.max_inline_bytes = max_inline_bytes
        self.artifact_dir = artifact_dir
        self._store = store
        self.delivery_failed = False

    @classmethod
    def from_environment(cls, *, max_inline_bytes=None, artifact_dir=None):
        if max_inline_bytes is None:
            raw = os.environ.get('FDISBULL_MAX_OUTPUT_BYTES', str(DEFAULT_INLINE_BYTES))
            try: max_inline_bytes = int(raw)
            except (ValueError, TypeError): raise ValueError('invalid FDISBULL_MAX_OUTPUT_BYTES') from None
        return cls(max_inline_bytes, artifact_dir)

    def store(self):
        if self._store is None:
            self._store = OutputArtifactStore(self.artifact_dir)
        return self._store

    def _marker(self, value, metadata, reason, observed, total_known):
        if metadata is None: self.delivery_failed = True
        wrapped = (isinstance(value, dict) and type(value.get('ok')) is bool
                   and 'id' in value and ('result' in value or 'error' in value))
        marker = {'format': 'fdisbull-output-ref-1', 'complete': False,
                  'status': 'artifact_required' if metadata else 'output_unavailable',
                  'execution': _execution(value, wrapped), 'retry_safe': False,
                  'inline_limit_bytes': self.max_inline_bytes, 'artifact': metadata,
                  'observed_bytes_at_least': observed,
                  'total_bytes': metadata['bytes'] if metadata else observed if total_known else None}
        if reason: marker['reason'] = reason
        if wrapped:
            ident = value.get('id')
            try: validate_request_id(ident)
            except ValueError: ident = None
            if value['ok']:
                return {'id': ident, 'ok': True, 'result': marker}
            return {'id': ident, 'ok': False,
                    'error': {'type': _short(value.get('error', {}).get('type')) if isinstance(value.get('error'), dict) else None,
                              'message': 'Full error response is in the output artifact' if metadata else 'Full error response could not be retained'},
                    'output': marker}
        return marker

    def bound(self, value):
        """Return an unchanged small value or an explicitly incomplete delivery."""
        progress = {'bytes': 0, 'done': False, 'encoding_failed': False}
        def chunks():
            pending = bytearray()
            try:
                for text in _encoder().iterencode(value):
                    data = text.encode('ascii')
                    for offset in range(0, len(data), 65536):
                        pending.extend(data[offset:offset+65536])
                        if len(pending) >= 65536:
                            part = bytes(pending[:65536]); del pending[:65536]
                            progress['bytes'] += len(part)
                            yield part
                if pending:
                    progress['bytes'] += len(pending)
                    yield bytes(pending)
                progress['done'] = True
            except (ValueError, TypeError, OverflowError, RecursionError, UnicodeError):
                progress['encoding_failed'] = True
                raise
        stream = chunks(); prefix = []; inline_size = 0
        try:
            for part in stream:
                prefix.append(part); inline_size += len(part)
                if inline_size + 1 > self.max_inline_bytes:
                    break
            else:
                return value
            def full_stream():
                yield from prefix
                yield from stream
            metadata = self.store().put_stream(full_stream())
            return self._marker(value, metadata, None, metadata['bytes'], True)
        except (ArtifactError, OSError, ValueError, TypeError, OverflowError, RecursionError, UnicodeError) as error:
            reason = 'serialization_failed' if progress['encoding_failed'] else error.code if isinstance(error, ArtifactError) else 'storage_failed'
            return self._marker(value, None, reason, progress['bytes'], progress['done'])
        finally:
            stream.close()

    def render(self, value):
        text = _encoder().encode(self.bound(value))
        if len(text.encode('ascii')) + 1 > self.max_inline_bytes:
            # The marker contains only small bounded fields. Keep a final guard
            # rather than ever returning an oversized or silently cut JSON line.
            raise ValueError('output descriptor exceeds inline budget')
        return text


def current_output_policy():
    return _policy.get() or OutputPolicy.from_environment()


@contextmanager
def output_policy_context(policy):
    token = _policy.set(policy)
    try: yield
    finally: _policy.reset(token)
