#!/usr/bin/env python3
"""Authored OFS/index fixtures for optional private runtime materialization.

Run directly with the Python standard library, or through pytest. No original
game files, network connection, native emulator, or third-party modules are used.
"""
# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

import intake


def encoded(data):
    return bytes(value ^ 0xff for value in data)


def checksum(block):
    struct.pack_into('>I', block, 20, 0)
    value = -sum(struct.unpack('>128I', block)) & 0xffffffff
    struct.pack_into('>I', block, 20, value)
    return block


def ofs_image(files, *, corrupt_name=None):
    """Author a small, real OFS directory and checked file-data chains."""
    image = bytearray(901120)
    image[:4] = b'DOS\0'
    next_block, records = 2, []
    for name, data in files:
        header = next_block
        next_block += 1
        chunks = [data[pos:pos+488] for pos in range(0, len(data), 488)]
        numbers = list(range(next_block, next_block + len(chunks)))
        next_block += len(chunks)
        records.append((name, data, header, chunks, numbers))
    if next_block >= 880:
        raise AssertionError('authored fixture unexpectedly overlaps root block')
    for index, (name, data, header, chunks, numbers) in enumerate(records):
        block = bytearray(512)
        struct.pack_into('>I', block, 0, 2)
        struct.pack_into('>I', block, 4, header)
        struct.pack_into('>I', block, 16, numbers[0] if numbers else 0)
        struct.pack_into('>I', block, 324, len(data))
        block[432] = len(name)
        block[433:433+len(name)] = name.encode('ascii')
        following = records[index + 1][2] if index + 1 < len(records) else 0
        struct.pack_into('>I', block, 496, following)
        struct.pack_into('>I', block, 500, 880)
        struct.pack_into('>i', block, 508, -3)
        image[header*512:(header+1)*512] = checksum(block)
        for part, (number, chunk) in enumerate(zip(numbers, chunks)):
            block = bytearray(512)
            sequence = part + 1
            if name == corrupt_name and part == 0:
                sequence += 1
            following = numbers[part + 1] if part + 1 < len(numbers) else 0
            struct.pack_into('>5I', block, 0, 8, header, sequence, len(chunk), following)
            block[24:24+len(chunk)] = chunk
            image[number*512:(number+1)*512] = checksum(block)
    root = bytearray(512)
    struct.pack_into('>I', root, 0, 2)
    struct.pack_into('>I', root, 24, records[0][2] if records else 0)
    struct.pack_into('>I', root, 508, 1)
    image[880*512:881*512] = checksum(root)
    return bytes(image)


def fixture(*, script_code=b'\x00', bad_resource=b'\x0a\x00\xcc\xdd',
            room_count=4, index_tail=b'', zero_script_bound=False):
    # Unknown header words deliberately remain nonzero. They are opaque.
    room = b'\x06\x00\xaa\xbb\xcc\xdd'
    costume = b'\x06\x00\x11\x22\x33\x44'
    script1 = struct.pack('<H', 4 + len(script_code)) + b'\x55\x66' + script_code
    script2 = b'\x06\x00\x77\x88\x80\x00'
    sound = b'\x07\x00\x99\xaa\x10\x20\x30'
    blocks = [('room', 1, room), ('costume', 1, costume),
              ('script', 1, script1), ('script', 2, script2), ('sound', 1, sound)]
    payload = bytearray()
    offsets = {}
    for kind, rid, block in blocks:
        offsets[(kind, rid)] = len(payload)
        payload.extend(block)
    invalid_offset = len(payload)
    payload.extend(bad_resource)
    room_directory = [(0x90, 0x1234), (49, 0)] + [(255, 65535)] * (room_count - 2)
    tables = {
        'room': room_directory,
        'costume': [(255, 65535), (1, offsets[('costume', 1)]), (0, 0), (128, 0)],
        'script': [((1, offsets[('script', 1)]) if zero_script_bound else (255, 65535)),
                   (1, offsets[('script', 1)]), (1, offsets[('script', 2)])],
        'sound': [(255, 65535), (1, offsets[('sound', 1)]), (1, invalid_offset)],
    }
    # The index exceeds 256 bytes: accidentally treating its magic as a room
    # length could look bounded, so room-zero exclusion is substantive.
    objects = bytes(300)
    index = bytearray(b'\x00\x01' + struct.pack('<H', len(objects)) + objects)
    directory_spans = {}
    for kind, rows in tables.items():
        start = len(index)
        index.append(len(rows))
        index.extend(selector for selector, _ in rows)
        index.extend(struct.pack('<' + 'H' * len(rows), *(offset for _, offset in rows)))
        directory_spans[kind] = (start, bytes(index[start:]))
    index.extend(index_tail)
    raw = {0: encoded(index), 1: encoded(payload)}
    return {'files': [('00.LFL', raw[0]), ('01.LFL', raw[1])], 'raw': raw,
            'tables': tables, 'blocks': blocks, 'directory_spans': directory_spans}


class RuntimeIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='scumm-intake-authored-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def archive(self, data, images=None):
        path = self.root / 'authored.zip'
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for number, image in enumerate(images or [ofs_image(data['files'])], 1):
                archive.writestr(f'authored-disk{number}.adf', image)
        return path

    def test_materialization_preserves_default_output_and_whole_spans(self):
        data = fixture()
        archive = self.archive(data)
        baseline, ordinary, runtime = (self.root / name for name in ('baseline', 'ordinary', 'runtime'))
        intake.inspect_archive(archive, baseline)
        receipt = intake.inspect_archive(archive, ordinary,
                                         runtime_output=runtime, runtime_script=2)
        self.assertEqual((baseline / 'receipt.json').read_bytes(),
                         (ordinary / 'receipt.json').read_bytes())
        self.assertEqual((ordinary / 'scripts/001.bin').read_bytes(), b'\x00')
        self.assertEqual((ordinary / 'scripts/002.bin').read_bytes(), b'\x80\x00')
        self.assertEqual(receipt['schema'], 'fdisbull-scumm-v2-intake-1')
        self.assertEqual(sorted(path.name for path in ordinary.iterdir()), ['receipt.json', 'scripts'])
        manifest = json.loads((runtime / 'manifest.json').read_text())
        self.assertEqual(manifest['schema'], 'fdisbull-scumm-v2-resources-1')
        self.assertEqual(manifest['profile'], 'amiga-v2-isolated')
        self.assertEqual(manifest['script_id'], 2)
        self.assertEqual(manifest['code_sha256'], hashlib.sha256(b'\x80\x00').hexdigest())
        self.assertEqual(manifest['source_receipt_sha256'],
                         hashlib.sha256((ordinary / 'receipt.json').read_bytes()).hexdigest())
        self.assertEqual(manifest['counts'], {'costume': 4, 'room': 4, 'script': 3, 'sound': 3})
        expected = {(kind, rid): block for kind, rid, block in data['blocks']}
        observed = {(row['type'], row['id']): row for row in manifest['resources']}
        self.assertEqual(set(observed), set(expected))
        self.assertNotIn(('room', 0), observed)
        self.assertNotIn(('costume', 2), observed)  # Current-room fallback is unresolved.
        self.assertNotIn(('costume', 3), observed)  # Mapper context is unresolved.
        for key, body in expected.items():
            row = observed[key]
            relative = Path(row['path'])
            self.assertFalse(relative.is_absolute())
            self.assertNotIn('..', relative.parts)
            self.assertEqual((runtime / relative).read_bytes(), body)
            self.assertEqual(row['size'], len(body))
            self.assertEqual(row['sha256'], hashlib.sha256(body).hexdigest())
            self.assertEqual(row['source']['raw_sha256'], hashlib.sha256(encoded(body)).hexdigest())
        self.assertLess(observed[('room', 1)]['size'], len(data['raw'][1]))
        for kind, (start, raw) in data['directory_spans'].items():
            evidence = manifest['directory_evidence'][kind]
            self.assertEqual((evidence['decoded_index_offset'], evidence['size']), (start, len(raw)))
            self.assertEqual(evidence['sha256'], hashlib.sha256(raw).hexdigest())

    def test_invalid_size_and_truncated_header_remain_unavailable(self):
        for number, bad in enumerate([b'\x00\x00\xaa\xbb', b'\x03\x00\xaa\xbb',
                                      b'\xff\xff\xaa\xbb', b'\x05\x00\xaa']):
            with self.subTest(case=number):
                data = fixture(bad_resource=bad)
                archive = self.archive(data)
                ordinary, runtime = self.root / f'intake{number}', self.root / f'runtime{number}'
                receipt = intake.inspect_archive(archive, ordinary, runtime_output=runtime)
                bad_row = next(row for row in receipt['resources']
                               if row['kind'] == 'sound' and row['id'] == 2)
                self.assertIn(bad_row['status'], ('invalid_size', 'invalid_location'))
                manifest = json.loads((runtime / 'manifest.json').read_text())
                self.assertFalse(any(row['type'] == 'sound' and row['id'] == 2
                                     for row in manifest['resources']))
                self.assertEqual(manifest['counts']['sound'], 3)

    def test_exact_eof_span_is_available(self):
        data = fixture(bad_resource=b'\x04\x00\xa5\x5a')
        runtime = self.root / 'runtime'
        intake.inspect_archive(self.archive(data), self.root / 'ordinary', runtime_output=runtime)
        manifest = json.loads((runtime / 'manifest.json').read_text())
        row = next(row for row in manifest['resources'] if row['type'] == 'sound' and row['id'] == 2)
        self.assertEqual((runtime / row['path']).read_bytes(), b'\x04\x00\xa5\x5a')

    def test_selected_script_must_be_bound_in_range_and_nonempty(self):
        data = fixture()
        archive = self.archive(data)
        for number, script_id in enumerate([-1, 0, 3, True]):
            with self.subTest(script_id=script_id):
                runtime = self.root / f'runtime{number}'
                with self.assertRaises(ValueError):
                    intake.inspect_archive(archive, self.root / f'intake{number}',
                                           runtime_output=runtime, runtime_script=script_id)
                self.assertFalse(runtime.exists())
        empty = fixture(script_code=b'')
        with self.assertRaisesRegex(ValueError, 'nonempty'):
            intake.inspect_archive(self.archive(empty), self.root / 'empty-intake',
                                   runtime_output=self.root / 'empty-runtime')
        self.assertFalse((self.root / 'empty-runtime').exists())

    def test_changed_code_view_refuses_materialization(self):
        data = fixture()
        ordinary, runtime = self.root / 'ordinary', self.root / 'runtime'
        receipt = intake.inspect_archive(self.archive(data), ordinary)
        (ordinary / 'scripts/001.bin').write_bytes(b'\x80')
        with self.assertRaisesRegex(ValueError, 'code view'):
            intake.write_runtime_catalog(runtime, 1, ordinary, receipt, data['raw'], data['tables'])
        self.assertFalse(runtime.exists())

    def test_script_zero_is_rejected_even_with_a_bound_code_view(self):
        data = fixture(zero_script_bound=True)
        ordinary, runtime = self.root / 'ordinary', self.root / 'runtime'
        with self.assertRaisesRegex(ValueError, 'script ID'):
            intake.inspect_archive(self.archive(data), ordinary,
                                   runtime_output=runtime, runtime_script=0)
        receipt = json.loads((ordinary / 'receipt.json').read_text())
        row = next(row for row in receipt['resources']
                   if row['kind'] == 'script' and row['id'] == 0)
        self.assertEqual(row['status'], 'bounded')
        self.assertEqual((ordinary / 'scripts/000.bin').read_bytes(), b'\x00')
        self.assertFalse(runtime.exists())

    def test_bad_copy_can_use_verified_alternate_with_exact_origin(self):
        data = fixture()
        archive = self.archive(data, [ofs_image(data['files'], corrupt_name='01.LFL'),
                                     ofs_image(data['files'])])
        runtime = self.root / 'runtime'
        receipt = intake.inspect_archive(archive, self.root / 'ordinary', runtime_output=runtime)
        self.assertEqual(len(receipt['issues']), 1)
        manifest = json.loads((runtime / 'manifest.json').read_text())
        for row in manifest['resources']:
            self.assertEqual([source['member'] for source in row['source']['adfs']],
                             ['authored-disk2.adf'])

    def test_conflicting_copies_are_not_admitted(self):
        data = fixture()
        changed = data['raw'][1][:-1] + bytes([data['raw'][1][-1] ^ 1])
        within = self.archive(data, [ofs_image(data['files'] + [('01.LFL', changed)])])
        with self.assertRaisesRegex(ValueError, 'conflicting readable'):
            intake.inspect_archive(within, self.root / 'within-intake',
                                   runtime_output=self.root / 'within-runtime')
        self.assertFalse((self.root / 'within-runtime').exists())
        across = self.archive(data, [ofs_image(data['files']),
                                    ofs_image([('00.LFL', data['raw'][0]), ('01.LFL', changed)])])
        with self.assertRaisesRegex(ValueError, 'conflicting disk copies'):
            intake.inspect_archive(across, self.root / 'across-intake',
                                   runtime_output=self.root / 'across-runtime')
        self.assertFalse((self.root / 'across-runtime').exists())

    def test_mapper_room_slots_are_unavailable(self):
        data = fixture(room_count=129)
        runtime = self.root / 'runtime'
        intake.inspect_archive(self.archive(data), self.root / 'ordinary', runtime_output=runtime)
        manifest = json.loads((runtime / 'manifest.json').read_text())
        self.assertEqual(manifest['counts']['room'], 129)
        row = next(row for row in manifest['unavailable_resources']
                   if row['type'] == 'room' and row['id'] == 128)
        self.assertEqual(row['status'], 'unresolved_room_mapper')

    def test_unsafe_or_existing_runtime_targets_are_rejected_before_intake(self):
        archive = self.archive(fixture())
        ordinary = self.root / 'ordinary'
        existing = self.root / 'existing'
        existing.mkdir()
        (existing / 'sentinel').write_text('retain')
        link = self.root / 'linked'
        link.symlink_to(existing, target_is_directory=True)
        targets = [ordinary, ordinary / 'nested', self.root,
                   self.root / 'unused' / '..' / 'escaped', existing, link / 'child']
        for target in targets:
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    intake.inspect_archive(archive, ordinary, runtime_output=target)
                self.assertFalse(ordinary.exists())
        self.assertEqual((existing / 'sentinel').read_text(), 'retain')

    def test_trailing_index_data_is_rejected(self):
        data = fixture(index_tail=b'\x00')
        runtime = self.root / 'runtime'
        with self.assertRaisesRegex(ValueError, 'trailing index data'):
            intake.inspect_archive(self.archive(data), self.root / 'ordinary', runtime_output=runtime)
        self.assertFalse(runtime.exists())


if __name__ == '__main__':
    unittest.main()
