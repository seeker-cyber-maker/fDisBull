"""Authored packet envelopes; structural inventory is not pixel decoding."""
import hashlib
import struct

import pytest

from fdisbull.flic import inspect_flic


def subchunk(kind=16, payload=b'ABCD'):
    return struct.pack('<IH', 6 + len(payload), kind) + payload


def frame(*children, kind=0xF1FA, tail=b''):
    return struct.pack('<IHH8s', 16 + sum(map(len, children)) + len(tail),
                       kind, len(children), bytes(8)) + b''.join(children) + tail


def standard(*packets, magic=0xAF12, declared=None, size_field=None):
    data = b''.join(packets)
    header = bytearray(128)
    struct.pack_into('<I5H', header, 0, 128 + len(data) if size_field is None else size_field,
                     magic, len(packets) if declared is None else declared, 2, 2, 8)
    struct.pack_into('<I', header, 16, 67)
    return bytes(header) + data


def audio(payload=b'\x80\x81\x82'):
    return struct.pack('<IH', len(payload), 0xAAAA) + bytes(10) + payload


def write(tmp_path, raw, name='movie.bin'):
    path = tmp_path / name
    path.write_bytes(raw)
    return path


def test_standard_full_packet_and_subchunk_inventory(tmp_path):
    raw = standard(frame(subchunk(4)), frame(subchunk(7)), frame(subchunk(16)), declared=2)
    source = write(tmp_path, raw)
    found = inspect_flic(source)
    assert found['profile'] == 'standard-128'
    assert found['header']['depth_field'] == 8
    assert found['header']['rate_field'] == 67
    assert found['frame_packets'] == found['subchunks'] == 3
    assert found['frame_count_relation'] == 'one-extra-frame-chunk'
    assert found['chunks'][0]['offset'] == 128
    assert found['chunks'][-1]['offset'] + found['chunks'][-1]['bytes'] == len(raw)
    assert found['source']['sha256'] == hashlib.sha256(raw).hexdigest()
    assert found['packet_inventory_complete'] and not found['full_decode']
    assert not found['native_runtime_tested'] and not found['source_modified']
    assert not found['rewrite_supported'] and source.read_bytes() == raw


def test_compact_bullfrog_has_no_standard_depth_or_speed_field(tmp_path):
    raw = struct.pack('<I4H', 12, 0xAF12, 1, 4, 4) + frame(subchunk(15))
    found = inspect_flic(write(tmp_path, raw, 'compact.FLI'))
    assert found['profile'] == 'bullfrog-compact-12'
    assert found['header_bytes'] == 12 and found['chunks'][0]['offset'] == 12
    assert found['header']['size_field'] == 12
    assert found['header']['depth_field'] is None and found['header']['rate_field'] is None
    assert found['frame_count_relation'] == 'equal'



@pytest.mark.parametrize('magic', [0xAF11, 0xAF12])
def test_standard_speed_word_is_not_a_compact_frame_marker(tmp_path, magic):
    from fdisbull.format_registry import identify_file
    raw = bytearray(standard(frame(subchunk()), magic=magic))
    struct.pack_into('<I', raw, 16, 0xF1FA)
    path = write(tmp_path, raw, 'slow.FLI')
    found = inspect_flic(path)
    identified = identify_file(path)['identification']
    assert found['profile'] == 'standard-128'
    assert found['header_bytes'] == 128
    assert found['header']['rate_field'] == 0xF1FA
    assert found['frame_packets'] == 1 and found['packet_inventory_complete']
    assert identified['format_id'] == 'flic' and identified['header_valid']


def test_tftd_audio_extents_and_explicit_index_group_lengths(tmp_path):
    # First visual prefix has only its six-byte extent envelope; it is opaque.
    prefix = struct.pack('<IH', 6, 0xF100)
    a = audio()
    b = frame(subchunk(16))
    raw = standard(a, prefix, a, b, declared=2, size_field=128 + len(prefix) + len(b))
    source = write(tmp_path, raw, 'game.VID')
    idx_raw = struct.pack('<III', len(a) + len(prefix), len(a) + len(b), 0xFFFFFFFF)
    index = write(tmp_path, idx_raw, 'game.IDX')
    found = inspect_flic(source, index_path=index)
    assert found['profile'] == 'tftd-audio-128'
    assert found['audio']['packets'] == 2 and found['audio']['payload_bytes'] == 6
    assert found['audio']['packet_grouping_exact']
    assert found['chunks'][0]['stored_size'] == 3 and found['chunks'][0]['bytes'] == 19
    assert found['chunks'][0]['payload_offset'] == 144
    assert found['frame_packets'] == 1
    assert found['companion_index']['status'] == 'packet-group-lengths-match'
    assert found['companion_index']['entries'] == 2
    assert found['companion_index']['semantic_interpretation'] == 'not_verified'
    assert found['warnings'] and found['recovery_required']
    assert source.read_bytes() == raw and index.read_bytes() == idx_raw
    missing = inspect_flic(source)
    assert missing['companion_index']['status'] == 'not_supplied'
    index.write_bytes(struct.pack('<III', 1, 2, 0xFFFFFFFF))
    with pytest.raises(ValueError, match='IDX words'):
        inspect_flic(source, index_path=index)


def test_unknown_chunks_and_opaque_frame_tails_remain_recovery_gaps(tmp_path):
    raw = standard(frame(subchunk(0x9999), tail=b'\0'), struct.pack('<IH', 6, 0x1234), declared=1)
    found = inspect_flic(write(tmp_path, raw))
    assert found['unknown_top_packet_types'] == {'0x1234': 1}
    assert found['unknown_subchunk_types'] == {'0x9999': 1}
    assert found['opaque_frame_tail_bytes'] == 1
    assert found['packet_inventory_complete']
    assert any('Unknown' in note for note in found['recovery_required'])


def test_extended_flx_is_recognized_but_not_inventoried(tmp_path):
    found = inspect_flic(write(tmp_path, standard(frame(), magic=0xAF44)))
    assert found['status'] == 'recognized-unsupported-layout'
    assert not found['packet_inventory_complete'] and found['recovery_required']
    with pytest.raises(ValueError, match='IDX companion is unsupported'):
        inspect_flic(write(tmp_path, standard(frame(), magic=0xAF44), 'extra.flx'), index_path=tmp_path / 'x.idx')


@pytest.mark.parametrize('raw,reason', [
    (b'FLI', 'header'),
    (bytes(128), 'recognized'),
    (standard(frame())[:-1], 'declared file length'),
    (standard(struct.pack('<IH', 0, 0xF1FA)), 'packet length'),
    (standard(struct.pack('<IH', 100, 0xF1FA)), 'packet extent'),
    (standard(struct.pack('<IHH8s', 16, 0xF1FA, 1, bytes(8))), 'subchunk'),
    (standard(frame(struct.pack('<IH', 100, 16))), 'subchunk extent'),
])
def test_malformed_bounds_refuse(tmp_path, raw, reason):
    with pytest.raises(ValueError, match=reason):
        inspect_flic(write(tmp_path, raw))


def test_invalid_audio_grouping_cannot_qualify_an_index(tmp_path):
    raw = standard(audio(), audio(), frame(), declared=2)
    index = write(tmp_path, struct.pack('<II', 1, 0xFFFFFFFF), 'x.idx')
    with pytest.raises(ValueError, match='packet grouping'):
        inspect_flic(write(tmp_path, raw), index_path=index)


def test_companion_index_on_non_tftd_refuses(tmp_path):
    with pytest.raises(ValueError, match='only for'):
        inspect_flic(write(tmp_path, standard(frame())), index_path=tmp_path / 'missing.idx')


def test_record_return_limit_does_not_hide_full_census(tmp_path, monkeypatch):
    import fdisbull.flic as flic
    monkeypatch.setattr(flic, 'MAX_REPORTED_PACKETS', 1)
    found = inspect_flic(write(tmp_path, standard(frame(), frame())))
    assert found['frame_packets'] == 2 and found['packet_inventory_complete']
    assert found['returned_chunk_records'] == 1 and found['chunk_records_truncated']
    monkeypatch.setattr(flic, 'MAX_PACKETS', 1)
    with pytest.raises(ValueError, match='packet inventory budget'):
        inspect_flic(write(tmp_path, standard(frame(), frame(), declared=1), 'long.bin'))


def test_source_symlinks_are_not_silently_accepted_by_media_reader(tmp_path):
    source = write(tmp_path, standard(frame()))
    alias = tmp_path / 'alias'
    alias.symlink_to(source)
    with pytest.raises(ValueError, match='symlink'):
        inspect_flic(alias)
