"""One fixed, hash-bound repair for the production qualification policy input."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat


CONTROL_ROOT = Path('/var/lib/fdisbull-ci/control/production')
CANONICAL_POLICY = CONTROL_ROOT / 'qualification-policy.canonical.json'
ACTIVE_ROOT = CONTROL_ROOT / 'job-inputs'
ACTIVE_POLICY = ACTIVE_ROOT / 'qualification-policy.json'
EXPECTED_SHA256 = '36b34e8b17309855408e4d0556bf047be3135ceb455359c806a45967c2a3ffeb'
MAX_POLICY_BYTES = 16_384
TARGET_FIELDS = {'provider', 'repository', 'run_id', 'run_attempt', 'job_id', 'source_sha',
                 'job_name', 'runner_id', 'ref', 'control_sha'}
DIAGNOSTIC_FIELDS = {'kind', 'reason', 'input_key', 'expected_sha256', 'target'}
CLOSED_EVIDENCE_FIELDS = ('host_export_verified', 'closed_inventory_verified',
                          'source_postcheck_verified', 'provider_trace_verified')


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode('ascii')


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _key_hash(key):
    if (not isinstance(key, str) or not 1 <= len(key) <= 200
            or any(ord(ch) < 32 or ord(ch) == 127 for ch in key)):
        raise ValueError('invalid action key')
    return hashlib.sha256(key.encode('utf-8')).hexdigest()


def _exact_target(value):
    if type(value) is not dict or set(value) != TARGET_FIELDS:
        return None
    if (value.get('provider') != 'github' or value.get('repository') != 'seeker-cyber-maker/fDisBull'
            or value.get('job_name') != 'qualification' or str(value.get('runner_id')) != '21'):
        return None
    for field in ('run_id', 'run_attempt', 'job_id', 'runner_id'):
        item = value.get(field)
        if isinstance(item, bool) or not isinstance(item, (str, int)) or not str(item).isascii() or not str(item).isdecimal() or int(item) <= 0:
            return None
    for field in ('source_sha', 'control_sha'):
        if not isinstance(value.get(field), str) or not re.fullmatch(r'[0-9a-f]{40}', value[field]):
            return None
    ref = value.get('ref')
    if (not isinstance(ref, str) or not re.fullmatch(r'[A-Za-z0-9_./-]{1,200}', ref)
            or '..' in ref or ref.startswith(('/', '-')) or ref.endswith(('/', '.'))):
        return None
    return {**value, **{field: str(int(value[field])) for field in ('run_id', 'run_attempt', 'job_id', 'runner_id')}}


def classify(observation, evidence):
    """Classify only the verified exported missing-policy diagnostic; all else blocks."""
    blocked = {'verified': True, 'eligible_for_repair': False, 'kind': 'blocked',
               'reason': 'diagnostic_unverified', 'fingerprint': 'qualification-policy:blocked'}
    try:
        if type(observation) is not dict or type(evidence) is not dict:
            return blocked
        target = _exact_target({key: observation[key] for key in TARGET_FIELDS})
        if (target is None or observation.get('status') != 'failed'
                or evidence.get('status') != 'export-verified' or evidence.get('job_status') != 'failed'):
            return blocked
        if (evidence.get('target') != target or any(evidence.get(name) is not True for name in CLOSED_EVIDENCE_FIELDS)
                or not isinstance(evidence.get('receipt_path'), str) or not evidence['receipt_path']):
            return blocked
        diagnostic = evidence.get('diagnostic')
        digest = evidence.get('diagnostic_sha256')
        if (type(diagnostic) is not dict or set(diagnostic) != DIAGNOSTIC_FIELDS
                or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest)):
            return blocked
        diag_target = _exact_target(diagnostic.get('target'))
        if (diagnostic.get('kind') != 'infrastructure' or diagnostic.get('reason') != 'missing_ci_owned_input'
                or diagnostic.get('input_key') != 'qualification-policy'
                or diagnostic.get('expected_sha256') != EXPECTED_SHA256 or diag_target != target):
            return blocked
        fingerprint = _hash(_json_bytes({'target': target, 'diagnostic_sha256': digest,
                                         'expected_sha256': EXPECTED_SHA256,
                                         'input_key': 'qualification-policy'}))
        return {'verified': True, 'eligible_for_repair': True, 'kind': 'infrastructure',
                'reason': 'missing_ci_owned_input', 'fingerprint': fingerprint,
                'target': target, 'input_key': 'qualification-policy',
                'expected_sha256': EXPECTED_SHA256,
                'diagnostic_sha256': digest, 'evidence_receipt': evidence.get('receipt_path')}
    except (KeyError, TypeError, ValueError, OverflowError):
        return blocked


class KnownInputRepair:
    """Create exactly one fixed policy file; journal every action without overwriting."""

    def __init__(self, private_incident_root, *, ensure_lease):
        self.private_root = Path(private_incident_root)
        self.ensure_lease = ensure_lease
        if not callable(ensure_lease):
            raise ValueError('verified lease check required')

    def _private_root(self):
        root = self.private_root
        if not root.is_absolute():
            raise RuntimeError('private incident root must be absolute')
        if not root.exists() or root.is_symlink() or not root.is_dir():
            raise RuntimeError('private incident root unavailable')
        if root.stat().st_uid != os.geteuid() or root.stat().st_mode & 0o077:
            raise RuntimeError('private incident root permissions invalid')
        if any(parent.is_symlink() for parent in root.parents):
            raise RuntimeError('private incident root path unsafe')
        return root

    def _paths(self, key):
        root = self._private_root()
        stem = _key_hash(key)
        return root, root / (stem + '.intent.json'), root / (stem + '.created.json'), root / (stem + '.receipt.json')

    def _locked(self, root):
        fd = os.open(root / '.known-input-repair.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        try:
            os.fchmod(fd, 0o600)
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_uid != os.geteuid():
                raise RuntimeError('private repair lock unsafe')
        except BaseException:
            os.close(fd)
            raise
        return fd

    @staticmethod
    def _durable_exclusive(path, data, mode=0o600):
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
        fd = os.open(path, flags, mode)
        try:
            with os.fdopen(fd, 'wb') as stream:
                os.fchmod(stream.fileno(), mode)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            parent_fd = os.open(path.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
        except BaseException:
            raise

    @staticmethod
    def _read_regular(path, *, max_bytes=MAX_POLICY_BYTES, owner=None, modes=None):
        if path.is_symlink():
            raise ValueError('symlink refused')
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > max_bytes:
                raise ValueError('nonregular or oversized file')
            if owner is not None and st.st_uid != owner:
                raise ValueError('file owner mismatch')
            if modes is not None and stat.S_IMODE(st.st_mode) not in modes:
                raise ValueError('file mode mismatch')
            chunks = []
            remaining = max_bytes + 1
            while remaining:
                block = os.read(fd, min(65536, remaining))
                if not block:
                    break
                chunks.append(block)
                remaining -= len(block)
            data = b''.join(chunks)
            if len(data) > max_bytes:
                raise ValueError('file exceeds bound')
            return data, st
        finally:
            os.close(fd)

    def _source_bytes(self):
        # Both paths are constants; callers never select an input file.
        parent = CANONICAL_POLICY.parent
        if (not parent.is_dir() or any(p.is_symlink() for p in (CANONICAL_POLICY, parent, *parent.parents))
                or ACTIVE_POLICY.parent != parent / 'job-inputs' or ACTIVE_ROOT != parent / 'job-inputs'
                or ACTIVE_POLICY.name != 'qualification-policy.json'):
            raise RuntimeError('fixed policy path unavailable')
        parent_st = os.stat(parent, follow_symlinks=False)
        if parent_st.st_uid != os.geteuid() or parent_st.st_mode & 0o077:
            raise RuntimeError('canonical policy directory is not private')
        data, st = self._read_regular(CANONICAL_POLICY, owner=os.geteuid(), modes={0o400, 0o600})
        if _hash(data) != EXPECTED_SHA256:
            raise RuntimeError('canonical policy identity mismatch')
        return data, st

    @staticmethod
    def _active_parent():
        parent = ACTIVE_ROOT
        if (parent != CANONICAL_POLICY.parent / 'job-inputs' or ACTIVE_POLICY.parent != parent
                or not parent.is_dir() or any(p.is_symlink() for p in (parent, *parent.parents))
                or parent.stat().st_uid != os.geteuid() or stat.S_IMODE(parent.stat().st_mode) != 0o700):
            raise RuntimeError('active policy parent unsafe')
        try:
            canonical_st = os.stat(CANONICAL_POLICY.parent, follow_symlinks=False)
            active_st = os.stat(parent, follow_symlinks=False)
        except OSError:
            raise RuntimeError('active policy parent unavailable') from None
        if (active_st.st_uid != os.geteuid() or canonical_st.st_uid != os.geteuid()
                or active_st.st_dev != canonical_st.st_dev or os.path.ismount(parent)):
            raise RuntimeError('policy directory mount or identity drift')
        return parent

    def _validate_action(self, key, payload):
        if type(payload) is not dict or set(payload) != {'project', 'target', 'observation', 'evidence', 'classification'}:
            raise ValueError('invalid repair payload')
        observation, evidence = payload['observation'], payload['evidence']
        expected = classify(observation, evidence)
        if (expected.get('eligible_for_repair') is not True or payload.get('classification') != expected
                or payload.get('target') != expected['target'] or payload.get('project') != expected['target']['repository']):
            raise ValueError('repair not authorized by verified diagnostic')
        return expected

    def _receipt(self, key, target, state, digest, origin):
        return {'schema': 'fdisbull-known-input-repair-1', 'key': key, 'target': target,
                'input_key': 'qualification-policy', 'expected_sha256': EXPECTED_SHA256,
                'active_sha256': digest, 'origin': origin, 'status': state}

    def repair(self, key, payload):
        if self.ensure_lease() is False:
            raise RuntimeError('verified executor lease required')
        classification = self._validate_action(key, payload)
        target = classification['target']
        source, _ = self._source_bytes()
        parent = self._active_parent()
        root, intent_path, created_path, receipt_path = self._paths(key)
        lock_fd = self._locked(root)
        try:
            with os.fdopen(lock_fd, 'r+') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if any(p.exists() or p.is_symlink() for p in (intent_path, created_path, receipt_path)):
                    raise RuntimeError('repair action already exists; reconcile only')
                intent = {'schema': 'fdisbull-known-input-intent-1', 'key': key, 'target': target,
                          'input_key': 'qualification-policy', 'expected_sha256': EXPECTED_SHA256,
                          'status': 'prepared'}
                self._durable_exclusive(intent_path, _json_bytes(intent))
                if self.ensure_lease() is False:
                    raise RuntimeError('verified executor lease required')
                current_source, _ = self._source_bytes()
                if current_source != source:
                    raise RuntimeError('canonical policy changed during repair')
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
                try:
                    fd = os.open(ACTIVE_POLICY, flags, 0o644)
                except FileExistsError:
                    active, st = self._read_regular(ACTIVE_POLICY, owner=os.geteuid(), modes={0o644})
                    if active != source or _hash(active) != EXPECTED_SHA256:
                        raise RuntimeError('active policy conflict; refusing overwrite') from None
                    active_fd = os.open(ACTIVE_POLICY, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
                    try:
                        os.fsync(active_fd)
                    finally:
                        os.close(active_fd)
                    parent_fd = os.open(parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
                    try:
                        os.fsync(parent_fd)
                    finally:
                        os.close(parent_fd)
                    reread, reread_st = self._read_regular(ACTIVE_POLICY, owner=os.geteuid(), modes={0o644})
                    if reread != source or reread_st.st_ino != st.st_ino or reread_st.st_dev != st.st_dev:
                        raise RuntimeError('active policy changed during verification')
                    receipt = self._receipt(key, target, 'completed', _hash(reread), 'existing-identical')
                    self._durable_exclusive(receipt_path, _json_bytes(receipt))
                    return {'status': 'completed', 'receipt_path': str(receipt_path), 'target': target,
                            'expected_sha256': EXPECTED_SHA256}
                try:
                    with os.fdopen(fd, 'wb') as stream:
                        os.fchmod(stream.fileno(), 0o644)
                        stream.write(source)
                        stream.flush()
                        os.fsync(stream.fileno())
                    parent_fd = os.open(parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
                    try:
                        os.fsync(parent_fd)
                    finally:
                        os.close(parent_fd)
                    active, st = self._read_regular(ACTIVE_POLICY, owner=os.geteuid(), modes={0o644})
                    if active != source or _hash(active) != EXPECTED_SHA256:
                        raise RuntimeError('active policy readback mismatch')
                    created = {'schema': 'fdisbull-known-input-created-1', 'key': key,
                               'target': target, 'expected_sha256': EXPECTED_SHA256,
                               'active_dev': st.st_dev, 'active_ino': st.st_ino,
                               'active_sha256': _hash(active)}
                    self._durable_exclusive(created_path, _json_bytes(created))
                    receipt = self._receipt(key, target, 'completed', _hash(active), 'exclusive-create')
                    self._durable_exclusive(receipt_path, _json_bytes(receipt))
                    return {'status': 'completed', 'receipt_path': str(receipt_path), 'target': target,
                            'expected_sha256': EXPECTED_SHA256}
                except BaseException:
                    # Never remove or replace a file after an ambiguous create/write.
                    raise
        except BaseException:
            raise

    def reconcile(self, key, payload):
        try:
            if self.ensure_lease() is False:
                return None
            classification = self._validate_action(key, payload)
            target = classification['target']
            parent = self._active_parent()
            root, intent_path, created_path, receipt_path = self._paths(key)
            lock_fd = self._locked(root)
            with os.fdopen(lock_fd, 'r+') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                intent_bytes, _ = self._read_regular(intent_path, owner=os.geteuid(), modes={0o600})
                intent = json.loads(intent_bytes)
                expected_intent = {'schema': 'fdisbull-known-input-intent-1', 'key': key,
                                   'target': target, 'input_key': 'qualification-policy',
                                   'expected_sha256': EXPECTED_SHA256, 'status': 'prepared'}
                if intent != expected_intent:
                    return None
                active, active_st = self._read_regular(ACTIVE_POLICY, owner=os.geteuid(), modes={0o644})
                if _hash(active) != EXPECTED_SHA256:
                    return None
                source, _ = self._source_bytes()
                if active != source:
                    return None
                if receipt_path.exists() or receipt_path.is_symlink():
                    receipt_bytes, _ = self._read_regular(receipt_path, owner=os.geteuid(), modes={0o600})
                    receipt = json.loads(receipt_bytes)
                    if type(receipt) is not dict or receipt.get('origin') not in ('exclusive-create', 'existing-identical'):
                        return None
                    if receipt != self._receipt(key, target, 'completed', EXPECTED_SHA256, receipt['origin']):
                        return None
                    if receipt['origin'] == 'exclusive-create':
                        created_bytes, _ = self._read_regular(created_path, owner=os.geteuid(), modes={0o600})
                        created = json.loads(created_bytes)
                        if created != {'schema': 'fdisbull-known-input-created-1', 'key': key,
                                       'target': target, 'expected_sha256': EXPECTED_SHA256,
                                       'active_dev': active_st.st_dev, 'active_ino': active_st.st_ino,
                                       'active_sha256': EXPECTED_SHA256}:
                            return None
                    elif created_path.exists() or created_path.is_symlink():
                        return None
                    return {'status': 'completed', 'receipt_path': str(receipt_path), 'target': target,
                            'expected_sha256': EXPECTED_SHA256}
                if not created_path.exists() or created_path.is_symlink():
                    return None
                created_bytes, _ = self._read_regular(created_path, owner=os.geteuid(), modes={0o600})
                created = json.loads(created_bytes)
                if (created != {'schema': 'fdisbull-known-input-created-1', 'key': key,
                                'target': target, 'expected_sha256': EXPECTED_SHA256,
                                'active_dev': active_st.st_dev, 'active_ino': active_st.st_ino,
                                'active_sha256': EXPECTED_SHA256}):
                    return None
                active_fd = os.open(ACTIVE_POLICY, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
                try:
                    os.fsync(active_fd)
                finally:
                    os.close(active_fd)
                parent_fd = os.open(parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
                try:
                    os.fsync(parent_fd)
                finally:
                    os.close(parent_fd)
                reread, reread_st = self._read_regular(ACTIVE_POLICY, owner=os.geteuid(), modes={0o644})
                if reread != source or (reread_st.st_dev, reread_st.st_ino) != (active_st.st_dev, active_st.st_ino):
                    return None
                receipt = self._receipt(key, target, 'completed', EXPECTED_SHA256, 'exclusive-create')
                self._durable_exclusive(receipt_path, _json_bytes(receipt))
                return {'status': 'completed', 'receipt_path': str(receipt_path), 'target': target,
                        'expected_sha256': EXPECTED_SHA256}
        except (OSError, ValueError, TypeError, RuntimeError, KeyError):
            return None
