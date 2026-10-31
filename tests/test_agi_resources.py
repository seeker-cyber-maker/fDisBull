from hashlib import sha256

import pytest

from fdisbull.agi import load_logic
from fdisbull.agi_resources import capture_view, logic_messages, view_metadata


def view():
    # One loop, one cel, two rows of three pixels.
    return bytes([0, 0, 1, 0, 0, 7, 0, 1, 3, 0, 3, 2, 0, 0x13, 0, 0x23, 0])


def test_view_geometry_and_malformed_rows():
    data = view()
    assert view_metadata(data) == {'sha256': sha256(data).hexdigest(), 'loops': [[{'width': 3, 'height': 2}]]}
    for bad in (data[:-1], data[:13] + b'\x14' + data[14:],
                data[:5] + b'\xff\xff' + data[7:], data[:10] + b'\x00' + data[11:]):
        with pytest.raises(ValueError): view_metadata(bad)


def test_capture_view_hashes_and_source_unchanged(tmp_path):
    payload = view(); directory = b'\x00\x00\x02'; volume = b'xx\x12\x34\x00' + len(payload).to_bytes(2, 'little') + payload
    (tmp_path / 'VIEWDIR').write_bytes(directory); (tmp_path / 'VOL.0').write_bytes(volume)
    r = capture_view(tmp_path / 'VIEWDIR', tmp_path, 0, profile='2.917')
    assert r['metadata'] == view_metadata(payload)
    assert r['resource_offset'] == 2 and r['resource_length'] == len(payload)
    assert r['directory_sha256'] == sha256(directory).hexdigest() and r['volume_sha256'] == sha256(volume).hexdigest()
    assert (tmp_path / 'VIEWDIR').read_bytes() == directory and (tmp_path / 'VOL.0').read_bytes() == volume
    with pytest.raises(ValueError): capture_view(tmp_path / 'VIEWDIR', tmp_path, 0, profile='unknown')


def logic_fixture(tmp_path, offsets=(6, 9), text=b'Hi\x00Bye\x00'):
    key = b'Avis Durgan'; encrypted = bytes(b ^ key[i % len(key)] for i, b in enumerate(text))
    section = bytes([len(offsets)]) + (2 + 2 * len(offsets) + len(text)).to_bytes(2, 'little')
    section += b''.join(x.to_bytes(2, 'little') for x in offsets) + encrypted
    payload = b'\x01\x00\x00' + section
    (tmp_path / 'LOGDIR').write_bytes(b'\x00\x00\x00')
    (tmp_path / 'VOL.0').write_bytes(b'\x12\x34\x00' + len(payload).to_bytes(2, 'little') + payload)
    return load_logic(tmp_path / 'LOGDIR', tmp_path, 0, profile='2.917')


def test_logic_messages_and_bad_offsets(tmp_path):
    resource = logic_fixture(tmp_path)
    assert logic_messages(resource) == {resource.resource_sha256: {'1': 'Hi', '2': 'Bye'}}
    resource = logic_fixture(tmp_path, offsets=(99,), text=b'X\x00')
    with pytest.raises(ValueError): logic_messages(resource)
    resource = logic_fixture(tmp_path, offsets=(4,), text=b'X')
    with pytest.raises(ValueError): logic_messages(resource)
