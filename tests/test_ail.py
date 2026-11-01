"""Authored AIL fixtures; no original game or SDK binary is distributed."""
import hashlib
import struct
import xml.etree.ElementTree as ET

import pytest
from PIL import Image

from fdisbull.cli import respond
from fdisbull.inspection import identify_header, inspect_binary
from fdisbull.loader import load_image
from fdisbull.project import Project


def ail_fixture():
    data = bytearray(0x180)
    notice = b'Copyright (C) 1991,1992 Miles Design, Inc.\x1a'
    directory = 2 + len(notice)
    struct.pack_into('<H', data, 0, directory)
    data[2:directory] = notice
    for i, (function, offset) in enumerate(((100, 0x100), (101, 0x110),
            (102, 0x120), (103, 0x130), (104, 0x140), (170, 0x150), (171, 0x150))):
        struct.pack_into('<HH', data, directory + i * 4, function, offset)
    struct.pack_into('<H', data, directory + 28, 0xffff)
    struct.pack_into('<HH4sHHhhhhHH', data, 0x80, 200, 3, b'AD\0\0',
                     0xa0, 0, 0x220, -1, -1, -1, 120, 0)
    data[0xa0:0xb0] = b'Authored device\0\0'
    data[0x100:0x104] = bytes.fromhex('b88000cb')
    data[0x110:0x114] = bytes.fromhex('b80100cb')
    data[0x120] = 0xcb
    # Independent starts at 130h (OR BH,0) and 131h (IRET).
    data[0x130:0x138] = bytes.fromhex('80cf000ee8faffcb')
    data[0x140] = 0xcb
    data[0x150:0x154] = bytes.fromhex('b83412cb')
    return bytes(data)


def test_ail_recognition_is_byte_based_and_exposes_directory_descriptor():
    data = ail_fixture()
    header = identify_header(data)
    assert header['format'] == 'AIL' and header['valid']
    view = inspect_binary(data)
    assert view['selected_image'] == 'ail'
    assert view['ail']['address_space'] == 'module-relative'
    assert view['header']['entrypoint'] is None
    assert len(view['exports']) == 7
    assert view['exports'][0]['name'] == 'AIL.describe_driver'
    assert view['exports'][0]['address'] == 0x100
    assert view['exports'][0]['ordinal'] == 100
    assert view['ail']['descriptor']['service_rate_hz'] == 120
    assert view['ail']['descriptor']['supported_device_names'] == ['Authored device']
    assert view['ail']['descriptor']['runtime_observed'] is False
    assert identify_header(b'not an AIL file')['format'] == 'unknown'


def test_ail_import_deferred_seeds_restart_patch_and_real_exports(tmp_path):
    data = ail_fixture()
    binary = tmp_path / 'driver.unknown'; binary.write_bytes(data)
    db = tmp_path / 'driver.fdb'
    loaded = load_image(binary)
    assert loaded.format == 'AIL' and loaded.entry is None
    assert loaded.regions[0].start == 0 and loaded.regions[0].data == data
    assert loaded.metadata['source_sha256'] == hashlib.sha256(data).hexdigest()
    with Project.create(db, binary) as p:
        assert p.status()['entry'] is None
        limited = p.analyze(max_instructions=1)
        assert not limited['stable'] and limited['budget_exhausted']
        done = p.analyze(max_instructions=1000)
        assert done['stable']
        starts = {r[0] for r in p.db.execute('SELECT address FROM instructions WHERE version=1')}
        assert '0000000000000130' in starts and '0000000000000131' in starts
        assert len(p.information('exports')['items']) == 7
        child = p.patch(0x151, '7856')['version']
        p.analyze(version=child, max_instructions=1000)
        assert p.disassembly(0x150, lines=1, version=1)['instructions'][0]['bytes'] == 'b83412'
        assert p.disassembly(0x150, lines=1, version=child)['instructions'][0]['bytes'] == 'b87856'
        stored = p.db.execute('SELECT source_bytes FROM binary_info WHERE version=1').fetchone()[0]
        assert stored == data
    with Project(db) as p:
        assert p.information('exports', version=1)['items'][0]['name'] == 'AIL.describe_driver'
        assert p.disassembly(lines=1, version=1)['instructions']
    for suffix in ('svg', 'png'):
        out = tmp_path / ('driver.' + suffix)
        result = respond({'method':'render', 'params':{'project':str(db),
            'address':0x100, 'lines':12, 'version':1, 'output':str(out)}})
        assert result['ok'], result
        if suffix == 'svg':
            assert 'AIL.describe_driver' in ' '.join(ET.parse(out).getroot().itertext())
        else:
            with Image.open(out) as image:
                image.verify()


@pytest.mark.parametrize('mutation', ['truncated', 'bad_offset', 'duplicate_id', 'no_end', 'wrong_family'])
def test_invalid_ail_is_not_loadable_and_does_not_create_a_project(tmp_path, mutation):
    data = bytearray(ail_fixture()); directory = struct.unpack_from('<H', data)[0]
    if mutation == 'truncated': data = data[:directory+3]
    if mutation == 'bad_offset': struct.pack_into('<H', data, directory+2, 0xffff)
    if mutation == 'duplicate_id': struct.pack_into('<H', data, directory+4, 100)
    if mutation == 'no_end': data[directory+28:] = bytes(len(data)-directory-28)
    if mutation == 'wrong_family': data[2:11] = b'Other SDK'
    path = tmp_path / 'looks_like.ADV'; path.write_bytes(data)
    db = tmp_path / 'invalid.fdb'
    with pytest.raises(ValueError): Project.create(db, path, image='ail')
    assert not db.exists()


def test_ail_cli_explicit_selection_and_conflicting_mapping(tmp_path):
    binary = tmp_path / 'driver.bin'; binary.write_bytes(ail_fixture())
    for method in ('identify', 'inspect'):
        answer = respond({'method':method, 'params':{'path':str(binary)}})
        assert answer['ok'], answer
    answer = respond({'method':'import', 'params':{'path':str(binary),
        'project':str(tmp_path/'cli.fdb'), 'image':'ail'}})
    assert answer['ok'], answer
    for option in ({'base':1}, {'bits':16}, {'load_segment':0x2000}, {'slice_arch':'arm64'}):
        with pytest.raises(ValueError): load_image(binary, image='ail', **option)
