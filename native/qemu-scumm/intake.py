#!/usr/bin/env python3
"""Bounded Amiga OFS / enhanced SCUMM v2 resource intake (no game execution)."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import hashlib
import json
import re
import struct
import zipfile
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ofs_lfl(disk):
    if len(disk) != 901120 or disk[:4] != b'DOS\0':
        raise ValueError('expected 880 KiB Amiga OFS image')
    def block(n):
        if not 2 <= n < len(disk) // 512:
            raise ValueError('block out of range')
        b = disk[n * 512:(n + 1) * 512]
        if sum(struct.unpack('>128I', b)) & 0xffffffff:
            raise ValueError('block checksum mismatch')
        return b
    def u(b, off):
        return struct.unpack_from('>I', b, off)[0]
    files, errors, seen = {}, [], set()
    def walk(n, path, depth):
        if depth > 32:
            raise ValueError('directory depth exceeded')
        h = block(n)
        if u(h, 0) != 2:
            raise ValueError('invalid directory header')
        for pos in range(24, 312, 4):
            child = u(h, pos)
            while child:
                if child in seen:
                    raise ValueError('directory cycle or repeated header')
                seen.add(child)
                c = block(child)
                if u(c, 0) != 2 or u(c, 500) != n or c[432] > 30:
                    raise ValueError('invalid child header')
                name = c[433:433 + c[432]].decode('latin1')
                kind = struct.unpack_from('>i', c, 508)[0]
                full = path + name
                if kind == 2:
                    walk(child, full + '/', depth + 1)
                elif kind == -3 and re.fullmatch(r'\d{2}\.lfl', name, re.I):
                    try:
                        data, chain = bytearray(), set()
                        size, ptr = u(c, 324), u(c, 16)
                        if size > len(disk):
                            raise ValueError('file too large')
                        while len(data) < size:
                            if ptr in chain:
                                raise ValueError('data chain cycle')
                            chain.add(ptr)
                            b = block(ptr)
                            if (u(b, 0), u(b, 4), u(b, 8)) != (8, child, len(chain)):
                                raise ValueError(f'bad data block {ptr}, sequence {len(chain)}')
                            count = u(b, 12)
                            if not 0 < count <= min(488, size - len(data)):
                                raise ValueError('bad data size')
                            data.extend(b[24:24 + count])
                            ptr = u(b, 16)
                        if ptr:
                            raise ValueError('nonterminal chain')
                        rid = int(name[:2])
                        if rid in files and files[rid] != bytes(data):
                            raise ValueError('conflicting LFL within disk')
                        files[rid] = bytes(data)
                    except ValueError as e:
                        errors.append({'file': full, 'error': str(e)})
                child = u(c, 496)
    seen.add(880)
    walk(880, '', 0)
    return files, errors


def decode_bytes(b):
    return b.translate(bytes(range(255, -1, -1)))


def read_index(raw):
    b = decode_bytes(raw)
    if b[:2] != b'\x00\x01' or len(b) < 4:
        raise ValueError('not an enhanced v2 index')
    count = struct.unpack_from('<H', b, 2)[0]
    p = 4 + count
    if p > len(b):
        raise ValueError('truncated object table')
    tables = {}
    for kind in ('room', 'costume', 'script', 'sound'):
        if p >= len(b):
            raise ValueError('missing directory count')
        n = b[p]
        p += 1
        if p + 3 * n > len(b):
            raise ValueError('truncated resource directory')
        rooms = b[p:p+n]
        p += n
        offsets = struct.unpack_from(f'<{n}H', b, p)
        p += 2*n
        tables[kind] = list(zip(rooms, offsets))
    if p != len(b):
        raise ValueError('unexpected trailing index data')
    return b[4:4+count], tables


def check_runtime_output(output, runtime_output):
    """Keep the optional private catalog disjoint from the ordinary intake."""
    if '..' in runtime_output.parts:
        raise ValueError('runtime output must not contain parent traversal')
    target, ordinary = runtime_output.absolute(), output.resolve()
    if target.is_symlink() or target.exists():
        raise ValueError('runtime output already exists')
    if any(parent.is_symlink() for parent in target.parents):
        raise ValueError('runtime output has a symlink ancestor')
    target = target.resolve()
    if target == ordinary or target in ordinary.parents or ordinary in target.parents:
        raise ValueError('runtime and ordinary output directories must be disjoint')


def write_runtime_catalog(runtime_output, script_id, output, receipt, rooms, tables):
    """Materialize opaque, source-bound old-bundle spans; no resource execution."""
    check_runtime_output(output, runtime_output)
    if type(script_id) is not int or not 1 <= script_id < min(256, len(tables['script'])):
        raise ValueError('runtime script ID is outside the declared script table')
    receipt_bytes = (output / 'receipt.json').read_bytes()
    if json.loads(receipt_bytes) != receipt:
        raise ValueError('source receipt changed before runtime materialization')
    if any(item['error'] == 'conflicting LFL within disk' for item in receipt['issues']):
        raise ValueError('conflicting readable LFL copies cannot bind a runtime')
    disks = {item['member']: item['sha256'] for item in receipt['disks']}
    if len(disks) != len(receipt['disks']):
        raise ValueError('ambiguous duplicate ADF member names')
    files = {item['id']: item for item in receipt['room_files']}
    for rid, raw in rooms.items():
        if (rid not in files or len(raw) != files[rid]['size'] or
                sha(raw) != files[rid]['sha256']):
            raise ValueError('LFL source identity changed before materialization')

    planned, unavailable = [], []

    def add(kind, rid, lfl_id, offset, size, expected_sha256=None):
        raw = rooms[lfl_id]
        if offset < 0 or size < 4 or offset + size > len(raw):
            raise ValueError('runtime resource span is outside its source LFL')
        encoded = raw[offset:offset+size]
        decoded = decode_bytes(encoded)
        if int.from_bytes(decoded[:2], 'little') != size:
            raise ValueError('runtime resource length header changed')
        digest = sha(decoded)
        if expected_sha256 is not None and digest != expected_sha256:
            raise ValueError('runtime resource identity changed')
        rec = {'type': kind, 'id': rid, 'size': size, 'sha256': digest,
               'path': f'resources/{kind}/{rid:03}.bin',
               'source': {'lfl_id': lfl_id, 'offset': offset,
                          'lfl_sha256': files[lfl_id]['sha256'],
                          'raw_sha256': sha(encoded),
                          'adfs': [{'member': name, 'sha256': disks[name]}
                                   for name in files[lfl_id]['sources']]}}
        planned.append((rec, decoded))

    for rec in receipt['resources']:
        kind, rid, lfl_id = rec['kind'], rec['id'], rec['room']
        if rec['status'] != 'bounded' or not 1 <= lfl_id <= 127:
            unavailable.append({'type': kind, 'id': rid, 'status': rec['status'],
                                'room': lfl_id, 'offset': rec['offset']})
            continue
        add(kind, rid, lfl_id, rec['offset'], rec['size'], rec['sha256'])

    # A room resource is the first old-bundle span in the matching LFL file.
    # The directory selector is a disk hint, not a containing LFL identifier.
    for rid, (selector, directory_offset) in enumerate(tables['room']):
        reason = None
        if rid == 0:
            reason = 'reserved_index'
        elif rid > 127:
            reason = 'unresolved_room_mapper'
        elif rid not in rooms:
            reason = 'missing_lfl'
        else:
            raw = rooms[rid]
            size = int.from_bytes(decode_bytes(raw[:2]), 'little')
            if len(raw) < 4 or size < 4 or size > len(raw):
                reason = 'invalid_size'
            else:
                add('room', rid, rid, 0, size)
        if reason is not None:
            unavailable.append({'type': 'room', 'id': rid, 'status': reason,
                                'selector': selector, 'offset': directory_offset})

    selected = next((payload for rec, payload in planned
                     if rec['type'] == 'script' and rec['id'] == script_id), None)
    if selected is None or len(selected) <= 4:
        raise ValueError('runtime script must have a bound, nonempty code view')
    code = selected[4:]
    if (output / 'scripts' / f'{script_id:03}.bin').read_bytes() != code:
        raise ValueError('runtime script differs from its extracted code view')
    index = decode_bytes(rooms[0])
    position = 4 + len(receipt['objects'])
    directory_evidence = {}
    for kind in ('room', 'costume', 'script', 'sound'):
        size = 1 + 3 * len(tables[kind])
        directory_evidence[kind] = {
            'decoded_index_offset': position, 'size': size,
            'sha256': sha(index[position:position+size]),
            'entries': [{'selector': selector, 'offset': offset}
                        for selector, offset in tables[kind]],
        }
        position += size
    manifest = {
        'schema': 'fdisbull-scumm-v2-resources-1',
        'profile': 'amiga-v2-isolated',
        'source_receipt_sha256': sha(receipt_bytes),
        'script_id': script_id, 'code_sha256': sha(code),
        'counts': {kind: len(tables[kind])
                   for kind in ('costume', 'room', 'script', 'sound')},
        'resources': [rec for rec, _ in sorted(
            planned, key=lambda pair: (pair[0]['type'], pair[0]['id']))],
        'archive_sha256': receipt['archive_sha256'],
        'index_sha256': receipt['index_sha256'],
        'transformation': 'xor-ff',
        'directory_evidence': directory_evidence,
        'unavailable_resources': unavailable,
    }
    runtime_output.mkdir(mode=0o700, parents=True, exist_ok=False)
    (runtime_output / 'resources').mkdir(mode=0o700)
    for kind in ('costume', 'room', 'script', 'sound'):
        (runtime_output / 'resources' / kind).mkdir(mode=0o700)
    for rec, payload in planned:
        path = runtime_output / rec['path']
        with path.open('xb') as stream:
            stream.write(payload)
        path.chmod(0o600)
        if sha(path.read_bytes()) != rec['sha256']:
            raise ValueError('materialized resource verification failed')
    # Write the manifest only after payload verification. A partial JSON write
    # is rejected by the runtime loader rather than admitting incomplete data.
    path = runtime_output / 'manifest.json'
    with path.open('x') as stream:
        stream.write(json.dumps(manifest, indent=2) + '\n')
    path.chmod(0o600)
    return manifest


def inspect_archive(archive, output, *, runtime_output=None, runtime_script=1):
    if runtime_output is not None:
        check_runtime_output(output, runtime_output)
    output.mkdir(parents=True, exist_ok=False)
    rooms, origins, disks, issues = {}, {}, [], []
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            if not info.filename.lower().endswith('.adf'):
                continue
            if info.file_size != 901120 or len(disks) >= 16:
                raise ValueError('unexpected ADF size/count')
            disk = z.read(info)
            files, errors = ofs_lfl(disk)
            disks.append({'member': info.filename, 'sha256': sha(disk), 'lfl_count': len(files)})
            issues.extend({'disk': info.filename, **e} for e in errors)
            for rid, data in files.items():
                if rid in rooms and rooms[rid] != data:
                    raise ValueError(f'conflicting disk copies of {rid:02}.LFL')
                rooms[rid] = data
                origins.setdefault(rid, []).append(info.filename)
    if 0 not in rooms:
        raise ValueError('missing index')
    obj, tables = read_index(rooms[0])
    resources, scripts = [], output / 'scripts'
    scripts.mkdir()
    for kind in ('costume', 'script', 'sound'):
        for rid, (room, off) in enumerate(tables[kind]):
            rec = {'kind': kind, 'id': rid, 'room': room, 'offset': off}
            if off == 65535 or room == 0:
                rec['status'] = 'unbound'
            elif room not in rooms or off + 4 > len(rooms[room]):
                rec['status'] = 'invalid_location'
            else:
                data = rooms[room]
                size = int.from_bytes(decode_bytes(data[off:off+2]), 'little')
                if size < 4 or off + size > len(data):
                    rec.update(status='invalid_size', declared_size=size)
                else:
                    payload = decode_bytes(data[off:off+size])
                    rec.update(status='bounded', size=size, sha256=sha(payload),
                               room_sha256=sha(data), sources=origins[room])
                    if kind == 'script':
                        code = payload[4:]
                        rec.update(code_size=len(code), code_sha256=sha(code), code_offset=off+4)
                        (scripts / f'{rid:03}.bin').write_bytes(code)
            resources.append(rec)
    receipt = {'schema': 'fdisbull-scumm-v2-intake-1', 'archive_sha256': sha(archive.read_bytes()),
               'disks': disks, 'issues': issues, 'index_md5': hashlib.md5(rooms[0]).hexdigest(),
               'index_sha256': sha(rooms[0]), 'object_count': len(obj),
               'objects': [{'id': i, 'owner': b & 15, 'state': b >> 4} for i,b in enumerate(obj)],
               'room_files': [{'id': i, 'size': len(b), 'sha256': sha(b), 'sources': origins[i]} for i,b in sorted(rooms.items())],
               'directories': {k: len(v) for k,v in tables.items()}, 'resources': resources}
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    if runtime_output is not None:
        write_runtime_catalog(runtime_output, runtime_script, output, receipt, rooms, tables)
    return receipt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('archive', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--runtime-output', type=Path,
                   help='new private directory for an isolated v2 resource catalog')
    p.add_argument('--runtime-script', type=int, default=1,
                   help='bound global script for the isolated runtime (default: 1)')
    a = p.parse_args()
    r = inspect_archive(a.archive, a.output, runtime_output=a.runtime_output,
                        runtime_script=a.runtime_script)
    print(json.dumps({'room_files': len(r['room_files']), 'objects': r['object_count'],
                      'index_md5': r['index_md5'], 'issues': r['issues'],
                      'bounded_scripts': sum(x['kind'] == 'script' and x['status'] == 'bounded' for x in r['resources'])}))


if __name__ == '__main__':
    main()
