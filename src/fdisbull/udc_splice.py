"""Hash-bound byte derivation for explicitly selected native backings.

This compiler performs declared, same-size source patches and ordered appends.
It does not assemble instructions, infer relocations, execute code, or establish
semantic equivalence. Those obligations belong to the selected backing and its
separately qualified adapters. The input bytes are always immutable.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re

FORMAT = 'fdisbull-udc-splice-1'
MAX_BYTES = 64 * 1024 * 1024
MAX_PARTS = 4096
RECEIPT_NAME = 'splice-receipt.json'


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def _fields(value, required, optional=(), label='manifest'):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError(f'{label} has missing or unsupported fields')


def _integer(value, label, minimum=0, maximum=MAX_BYTES):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f'{label} must be an integer in {minimum}..{maximum}')
    return value


def _hash(value, label):
    if not isinstance(value, str) or re.fullmatch('[0-9a-fA-F]{64}', value) is None:
        raise ValueError(f'{label} must be a SHA-256 hexadecimal hash')
    return value.lower()


def _hex_size(value, label, *, validate=True):
    if (not isinstance(value, str) or not value or len(value) % 2 or len(value) > MAX_BYTES * 2
            or validate and re.fullmatch('[0-9a-fA-F]+', value) is None):
        raise ValueError(f'{label} requires nonempty, bounded, even hexadecimal bytes')
    return len(value) // 2


def build_splice(source_bytes: bytes, manifest: dict) -> tuple[bytes, dict]:
    """Validate every source/payload hash before deriving an output in memory.

    ``manifest`` uses ``format``, ``source_sha256``, ``patches`` and ``appended``.
    Each patch contains ``offset``, ``expected_sha256`` and ``replace_hex``;
    its original span has exactly the replacement length. Each appended part
    contains ``bytes_hex`` and ``sha256``. An optional ``max_output_bytes`` can
    narrow the 64 MiB ceiling, for example to the caller's COM image limit.
    Patches cannot overlap, change size, or target appended content.
    """
    if not isinstance(source_bytes, bytes) or not 1 <= len(source_bytes) <= MAX_BYTES:
        raise ValueError('source must contain 1..64 MiB immutable bytes')
    _fields(manifest, ('format', 'source_sha256', 'patches', 'appended'), ('max_output_bytes',))
    if manifest['format'] != FORMAT:
        raise ValueError(f'unsupported splice format; expected {FORMAT}')
    source_hash = _hash(manifest['source_sha256'], 'source hash')
    if _sha(source_bytes) != source_hash:
        raise ValueError('source hash differs from the selected immutable backing')
    budget = _integer(manifest.get('max_output_bytes', MAX_BYTES), 'max_output_bytes', 1)
    if len(source_bytes) > budget:
        raise ValueError('source exceeds the declared output byte budget')
    for field in ('patches', 'appended'):
        if not isinstance(manifest[field], list) or len(manifest[field]) > MAX_PARTS:
            raise ValueError(f'{field} must contain at most {MAX_PARTS} records')

    patches = []
    for index, patch in enumerate(manifest['patches']):
        _fields(patch, ('offset', 'expected_sha256', 'replace_hex'), label=f'patch {index}')
        offset = _integer(patch['offset'], 'patch offset')
        size = _hex_size(patch['replace_hex'], 'patch replace_hex', validate=False)
        if offset + size > len(source_bytes):
            raise ValueError('patch span exceeds original source bounds')
        expected = _hash(patch['expected_sha256'], 'patch hash')
        patches.append(dict(offset=offset, expected_sha256=expected,
                            replace_hex=patch['replace_hex'], size=size))
    patches.sort(key=lambda item: item['offset'])
    end = 0
    for patch in patches:
        if patch['offset'] < end:
            raise ValueError('source patches overlap')
        end = patch['offset'] + patch['size']
    # Reject overlap and aggregate bounds before scanning/hashing large spans.
    # A caller can otherwise repeat one large Python object in many records.
    for patch in patches:
        _hex_size(patch['replace_hex'], 'patch replace_hex')
        offset, size = patch['offset'], patch['size']
        if _sha(source_bytes[offset:offset + size]) != patch['expected_sha256']:
            raise ValueError('patch hash differs from the original source span')
        patch['replace_hex'] = patch['replace_hex'].lower()

    appended, total = [], len(source_bytes)
    for index, part in enumerate(manifest['appended']):
        _fields(part, ('bytes_hex', 'sha256'), label=f'append {index}')
        size = _hex_size(part['bytes_hex'], 'append bytes_hex', validate=False)
        if total + size > budget:
            raise ValueError('appended content exceeds the declared output byte budget')
        _hex_size(part['bytes_hex'], 'append bytes_hex')
        expected = _hash(part['sha256'], 'append hash')
        payload = bytes.fromhex(part['bytes_hex'])
        if _sha(payload) != expected:
            raise ValueError('append payload hash differs from its declared hash')
        appended.append(dict(offset=total, size=size, sha256=expected,
                             bytes_hex=part['bytes_hex'].lower()))
        total += size

    output = bytearray(source_bytes)
    unchanged, cursor = [], 0
    for patch in patches:
        offset, size = patch['offset'], patch['size']
        if cursor < offset:
            unchanged.append(dict(offset=cursor, size=offset - cursor,
                                  sha256=_sha(source_bytes[cursor:offset])))
        output[offset:offset + size] = bytes.fromhex(patch['replace_hex'])
        cursor = offset + size
    if cursor < len(source_bytes):
        unchanged.append(dict(offset=cursor, size=len(source_bytes) - cursor,
                              sha256=_sha(source_bytes[cursor:])))
    for part in appended:
        output.extend(bytes.fromhex(part['bytes_hex']))
    output = bytes(output)
    normalized = dict(format=FORMAT, source_sha256=source_hash,
                      patches=[{key: p[key] for key in ('offset', 'expected_sha256', 'replace_hex')} for p in patches],
                      appended=[{key: p[key] for key in ('bytes_hex', 'sha256')} for p in appended],
                      max_output_bytes=budget)
    receipt = dict(format='fdisbull-udc-splice-receipt-1',
                   manifest_sha256=_sha(_encoded(normalized)),
                   source_sha256=source_hash, source_size=len(source_bytes),
                   output_sha256=_sha(output), output_size=len(output),
                   source_byte_identity=output == source_bytes,
                   patches=[dict(offset=p['offset'], size=p['size'], expected_sha256=p['expected_sha256'],
                                 replacement_sha256=_sha(bytes.fromhex(p['replace_hex']))) for p in patches],
                   appended=[{key: p[key] for key in ('offset', 'size', 'sha256')} for p in appended],
                   unchanged_spans=unchanged,
                   semantics='byte derivation only; behavior requires separate qualification')
    return output, receipt


def _filename(value):
    devices = {'CON', 'PRN', 'AUX', 'NUL'} | {f'{p}{i}' for p in ('COM', 'LPT') for i in range(1, 10)}
    if (not isinstance(value, str) or not 1 <= len(value) <= 128 or value.lower() in ('.', '..', '.git', RECEIPT_NAME)
            or any(ord(c) < 32 or c in '/\\:<>"|?*' for c in value)
            or value.endswith(('.', ' ')) or PureWindowsPath(value).drive
            or value.split('.')[0].upper() in devices):
        raise ValueError('output name must be a safe single artifact name distinct from the receipt')
    return value


def emit_splice(source_bytes: bytes, manifest: dict, output_dir, *, output_name='PROGRAM.COM') -> dict:
    """Emit one validated artifact into a new directory outside Git.

    The receipt is written last, after output readback. Failure cleanup removes
    only files and a directory still owned by this invocation. A crash can leave
    an incomplete new directory without a receipt; it is never silently reused.
    No original input path is opened for writing and no existing output is used.
    """
    output, receipt = build_splice(source_bytes, manifest)
    output_name = _filename(output_name)
    target = Path(output_dir).resolve()
    if target.exists() or target.is_symlink() or any((p / '.git').exists() for p in (target, *target.parents)):
        raise ValueError('splice output must be new and outside Git')
    if not target.parent.is_dir():
        raise ValueError('splice output parent directory must already exist')
    try:
        target.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise ValueError('splice output must be new') from exc
    owned = target.stat()
    created = []

    def write_new(path, data):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        identity = os.fstat(fd)
        created.append((path, identity.st_dev, identity.st_ino))
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())

    try:
        artifact = target / output_name
        write_new(artifact, output)
        if _sha(artifact.read_bytes()) != receipt['output_sha256']:
            raise ValueError('emitted artifact readback hash differs')
        receipt = dict(receipt, output_name=output_name, readback_verified=True)
        write_new(target / RECEIPT_NAME, _encoded(receipt) + b'\n')
    except BaseException:
        for path, device, inode in reversed(created):
            try:
                current = path.lstat()
                if (current.st_dev, current.st_ino) == (device, inode):
                    path.unlink()
            except FileNotFoundError:
                pass
        try:
            current = target.lstat()
            if (current.st_dev, current.st_ino) == (owned.st_dev, owned.st_ino):
                target.rmdir()
        except OSError:
            pass
        raise
    return dict(receipt, output=str(target), artifact=str(artifact))
