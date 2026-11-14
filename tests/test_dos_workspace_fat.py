"""FAT workspace volume and composite C/D disk contracts."""
import struct

import pytest

from fdisbull import dos_workspace_fat as fat


def _floppy():
    image = bytearray(fat.FLOPPY_BYTES)
    image[:3] = b'\xeb\x3c\x90'
    image[3:11] = b'FREEDOS '
    struct.pack_into('<HBHBHHBHHHII', image, 11, 512, 1, 1, 2, 224, 2880,
                     0xf0, 9, 18, 2, 0, 0)
    image[36] = 0
    image[38] = 0x29
    image[43:54] = b'FREEDOS    '
    image[54:62] = b'FAT12   '
    image[510:512] = b'\x55\xaa'
    fat_start = 512
    image[fat_start:fat_start + 3] = b'\xf0\xff\xff'
    second = fat_start + 9 * 512
    image[second:second + 3] = b'\xf0\xff\xff'
    return bytes(image)


def _entries():
    return {
        'ASSETS': {'type': 'directory'},
        'ASSETS\\EMPTY.DAT': {'type': 'file', 'data': b''},
        'ASSETS\\LEVEL1.BIN': {'type': 'file', 'data': bytes(range(256)) * 13,
                                'attributes': 0x21, 'dos_date': 0x5c21, 'dos_time': 0x7a20},
        'SAVE.DAT': {'type': 'file', 'data': b'save-state'},
    }


def test_fat16_roundtrip_files_directories_empty_and_metadata():
    image = fat.build_volume(_entries())
    parsed = fat.parse_volume(image)
    assert parsed == {
        'ASSETS': {'type': 'directory', 'data': b'', 'attributes': 0x10,
                   'dos_date': 0x21, 'dos_time': 0},
        'ASSETS\\EMPTY.DAT': {'type': 'file', 'data': b'', 'attributes': 0x20,
                               'dos_date': 0x21, 'dos_time': 0},
        'ASSETS\\LEVEL1.BIN': {'type': 'file', 'data': bytes(range(256)) * 13,
                                'attributes': 0x21, 'dos_date': 0x5c21, 'dos_time': 0x7a20},
        'SAVE.DAT': {'type': 'file', 'data': b'save-state', 'attributes': 0x20,
                     'dos_date': 0x21, 'dos_time': 0},
    }


@pytest.mark.parametrize('size_bytes', [32 * 1024 * 1024, 48 * 1024 * 1024])
def test_large_volumes_use_shorter_chains_without_changing_file_bytes(size_bytes):
    # Authored bytes at the observed large-asset scale, not an original WAD.
    payload = (bytes(range(256)) * 48470)[:12408292]
    entries = {'ASSET.BIN': {'type': 'file', 'data': payload},
               'EMPTY.DAT': {'type': 'file', 'data': b''}}
    image = fat.build_volume(entries, size_bytes=size_bytes)
    assert image[13] == 8
    fs = fat._Fat16(image)
    first = struct.unpack_from('<H', image, fs.root_offset + 26)[0]
    assert len(fs.chain(first)) == 3030
    parsed = fat.parse_volume(image)
    assert parsed['ASSET.BIN']['data'] == payload
    assert parsed['EMPTY.DAT']['data'] == b''
    assert image == fat.build_volume(dict(reversed(list(entries.items()))), size_bytes=size_bytes)


def test_preferred_layout_keeps_enough_fat_sectors_at_rounding_boundary():
    # The needed FAT length alternates between 32 and 33 sectors if each
    # iteration shrinks to the new minimum. The smaller table is too short.
    image = fat.build_volume({'A.DAT': {'type': 'file', 'data': b'authored'}},
                             size_bytes=33600000)
    assert fat.parse_volume(image)['A.DAT']['data'] == b'authored'
    assert image[13] == 8 and struct.unpack_from('<H', image, 22)[0] == 33
    legacy = fat._layout_fat16(33600000)
    assert (legacy['spc'], legacy['fat_sectors'], legacy['clusters']) == (1, 255, 65082)


def test_every_preferred_geometry_has_capacity_for_all_cluster_entries():
    invalid = []
    for sectors in range(32 * 1024 * 1024 // 512, 48 * 1024 * 1024 // 512 + 1):
        layout = fat._layout_fat16(sectors * 512, prefer_large_clusters=True)
        if layout['fat_sectors'] * 512 < (layout['clusters'] + 2) * 2:
            invalid.append(sectors)
    assert invalid == []


@pytest.mark.parametrize('size_bytes', [4 * 1024 * 1024, 16 * 1024 * 1024,
                                      32 * 1024 * 1024 - 512])
def test_small_volumes_keep_existing_512_byte_clusters(size_bytes):
    image = fat.build_volume(_entries(), size_bytes=size_bytes)
    assert image[13] == 1
    assert fat.parse_volume(image)['SAVE.DAT']['data'] == b'save-state'


@pytest.mark.parametrize('file_count', [8160, 8191])
def test_large_volume_falls_back_when_file_and_directory_rounding_exceed_capacity(file_count):
    # 8160 file clusters alone fit 8179 preferred clusters, but the directory
    # needs another 64. The second case also reaches the 8192-entry limit.
    entries = {f'BULK\\F{index:07d}': {'type': 'file', 'data': b'x'}
               for index in range(file_count)}
    image = fat.build_volume(entries)
    assert image[13] == 1
    parsed = fat.parse_volume(image)
    assert len(parsed) == file_count + 1
    assert all(item['data'] == b'x' for item in parsed.values() if item['type'] == 'file')


def test_empty_files_do_not_force_a_capacity_fallback():
    entries = {f'BULK\\F{index:07d}': {'type': 'file', 'data': b''}
               for index in range(8191)}
    image = fat.build_volume(entries)
    assert image[13] == 8
    parsed = fat.parse_volume(image)
    assert len(parsed) == 8192
    assert all(item['data'] == b'' for item in parsed.values())


def test_preferred_volume_exact_capacity_and_overflow():
    # 65536 sectors minus one reserved, two 32-sector FATs and 32 root sectors
    # leave 8179 complete 4096-byte clusters; the trailing seven sectors do
    # not create another cluster.
    capacity = 8179 * 4096
    image = fat.build_volume({'FULL.BIN': {'type': 'file', 'data': b'x' * capacity}})
    assert image[13] == 8
    assert len(fat.parse_volume(image)['FULL.BIN']['data']) == capacity
    with pytest.raises(ValueError, match='exceed the FAT16 volume'):
        fat.build_volume({'FULL.BIN': {'type': 'file', 'data': b'x' * (capacity + 1)}})


@pytest.mark.parametrize('size_bytes', [True, 4 * 1024 * 1024 - 512,
                                      48 * 1024 * 1024 + 512, 32 * 1024 * 1024 + 1])
def test_cluster_policy_preserves_volume_size_bounds(size_bytes):
    with pytest.raises(ValueError, match='sector-aligned and 4..48 MiB'):
        fat.build_volume({}, size_bytes=size_bytes)


def test_cluster_policy_preserves_entry_limit():
    entries = {f'F{index:07d}': {'type': 'file', 'data': b''} for index in range(8193)}
    with pytest.raises(ValueError, match='entry count'):
        fat.build_volume(entries)


@pytest.mark.parametrize('entries', [
    {'A.TXT': {'type': 'file', 'data': b'a'}, 'a.txt': {'type': 'file', 'data': b'b'}},
    {'LONGNAME9.TXT': {'type': 'file', 'data': b'x'}},
    {'CON.TXT': {'type': 'file', 'data': b'x'}},
    {'PARENT.TXT': {'type': 'file', 'data': b'x'}, 'PARENT.TXT\\CHILD.TXT': {'type': 'file', 'data': b'y'}},
])
def test_builder_refuses_ambiguous_or_invalid_dos_paths(entries):
    with pytest.raises(ValueError):
        fat.build_volume(entries)


def test_parser_rejects_mismatched_fat_copies_and_lfn():
    image = bytearray(fat.build_volume({'A.TXT': {'type': 'file', 'data': b'a'}}))
    fat_size = struct.unpack_from('<H', image, 22)[0] * 512
    second_fat = 512 + fat_size
    image[second_fat + 17] ^= 0x01
    with pytest.raises(ValueError, match='copies disagree'):
        fat.parse_volume(bytes(image))

    image = bytearray(fat.build_volume({'A.TXT': {'type': 'file', 'data': b'a'}}))
    root_start = (1 + 2 * struct.unpack_from('<H', image, 22)[0]) * 512
    image[root_start + 11] = 0x0f
    with pytest.raises(ValueError, match='Long filename'):
        fat.parse_volume(bytes(image))


def test_parser_rejects_cross_linked_file_chains():
    image = bytearray(fat.build_volume({
        'A.TXT': {'type': 'file', 'data': b'a' * 700},
        'B.TXT': {'type': 'file', 'data': b'b' * 700},
    }))
    fat_sectors = struct.unpack_from('<H', image, 22)[0]
    root_start = (1 + 2 * fat_sectors) * 512
    first = struct.unpack_from('<H', image, root_start + 26)[0]
    struct.pack_into('<H', image, root_start + 32 + 26, first)
    with pytest.raises(ValueError, match='cross-linked'):
        fat.parse_volume(bytes(image))


def test_parser_rejects_unowned_allocated_clusters():
    image = bytearray(fat.build_volume({'A.TXT': {'type': 'file', 'data': b'a'}}))
    fat_sectors = struct.unpack_from('<H', image, 22)[0]
    first_fat = 512
    second_fat = first_fat + fat_sectors * 512
    orphan = 17
    struct.pack_into('<H', image, first_fat + orphan * 2, 0xffff)
    struct.pack_into('<H', image, second_fat + orphan * 2, 0xffff)
    with pytest.raises(ValueError, match='unowned allocated cluster'):
        fat.parse_volume(bytes(image))


def test_composite_boot_partition_receipt_and_workspace_replacement():
    system = _floppy()
    workspace = fat.build_volume(_entries())
    composite, receipt = fat.build_composite(system, workspace)
    layout = fat.volume_layout(composite)
    c, d = layout['C'], layout['D']
    assert len(composite) < 64 * 1024 * 1024
    assert receipt['partitions']['C']['start_lba'] == 2048
    assert composite[c['offset']:c['offset'] + 3] == b'\xeb\x3c\x90'
    assert struct.unpack_from('<I', composite, c['offset'] + 28)[0] == c['start_lba']
    assert struct.unpack_from('<I', composite, d['offset'] + 28)[0] == d['start_lba']
    assert composite[c['offset'] + 36] == 0x80
    assert fat.parse_volume(composite[d['offset']:d['offset'] + d['size']]) == fat.parse_volume(workspace)

    mbr = composite[:512]
    assert mbr[510:512] == b'\x55\xaa'
    # The authored LBA DAP is embedded in the code body; it reads the C VBR.
    assert mbr[:24] == bytes.fromhex('fa31c08ed88ec0be007cbf0006b90001fcf3a5ea18006000')
    assert struct.unpack_from('<Q', mbr, 74)[0] == c['start_lba']
    assert b'\x88\x16' in mbr[24:64]  # BIOS DL is saved before the disk read.

    updated = fat.build_volume({'NEXT.DAT': {'type': 'file', 'data': b'new'}})
    replaced = fat.replace_workspace(composite, updated)
    assert replaced[:d['offset']] == composite[:d['offset']]
    assert fat.parse_volume(replaced[d['offset']:d['offset'] + d['size']]) == fat.parse_volume(updated)
    with pytest.raises(ValueError, match='admitted size'):
        fat.replace_workspace(composite, fat.build_volume({}, size_bytes=16 * 1024 * 1024))


def test_composite_refuses_non_freedos_floppy_or_fat12_workspace():
    with pytest.raises(ValueError, match='1.44 MiB'):
        fat.build_composite(b'bad', fat.build_volume({}))
    fat12 = _floppy()
    with pytest.raises(ValueError, match='FAT16'):
        fat.build_composite(_floppy(), fat12)


def test_composite_layout_refuses_mbr_loader_or_partition_tampering():
    image, _ = fat.build_composite(_floppy(), fat.build_volume({}))
    changed_loader = bytearray(image)
    changed_loader[0] ^= 0x01
    with pytest.raises(ValueError, match='MBR boot code'):
        fat.volume_layout(bytes(changed_loader))

    changed_start = bytearray(image)
    # Changing D's BPB hidden-sector value cannot silently rebase the volume.
    d = fat.volume_layout(image)['D']
    struct.pack_into('<I', changed_start, d['offset'] + 28, d['start_lba'] + 1)
    with pytest.raises(ValueError, match='BPB'):
        fat.volume_layout(bytes(changed_start))
