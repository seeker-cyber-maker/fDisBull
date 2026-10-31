"""Independent MZ header/relocation checks for the DOS code-layout adapter."""
import struct

import pytest

from fdisbull.dos import load_mz
from fdisbull.project import Project
from tests.test_dos_udc import setup_project, definition


ASSUMPTIONS = dict.fromkeys(('no_code_reads', 'no_code_writes',
    'no_computed_entries', 'address_identity_unobserved', 'timing_unobserved'), True)


@pytest.mark.parametrize('segment', [0x1000, 0x2345])
def test_mz_loader_relocates_bootstrap_and_preserves_code_ports(tmp_path, segment):
    project, _, native, _, terminal = setup_project(tmp_path)
    with project:
        spec = definition(project, native, terminal)
        com = project.udc_dos_compile(spec['id'], assumptions=ASSUMPTIONS)
        mz = project.udc_dos_compile(spec['id'], assumptions=ASSUMPTIONS, container='mz')
    raw = bytes.fromhex(mz['bytes'])
    fields = struct.unpack_from('<14H', raw)
    assert fields[0] == 0x5a4d
    assert (fields[2] - (fields[1] != 0)) * 512 + fields[1] == len(raw)
    assert fields[3:5] == (1, 2)  # One loader relocation; 32-byte header.
    assert fields[7:9] == (0, 0xfffe)
    assert fields[10:14] == (0xf7, 0, 0x1c, 0)
    assert struct.unpack_from('<HH', raw, 0x1c) == (0xf9, 0)
    assert raw[0x20 + 0xf7:0x20 + 0x100] == bytes.fromhex('50b800008ed88ec058')
    assert raw[0x120:] == bytes.fromhex(com['bytes'])
    assert mz['ports'] == com['ports']
    assert mz['definition_sha256'] == com['definition_sha256']
    assert mz['qualification'] == 'structural_only' and mz['native_execution'] is False
    image = load_mz(raw, load_segment=segment)
    dos = image.metadata['dos']
    assert dos['entry_cs'] == dos['stack_ss'] == segment
    assert dos['entry_ip'] == 0xf7 and dos['allocation_size'] == 0x10000
    loaded = image.regions[0].data
    assert int.from_bytes(loaded[0xf9:0xfb], 'little') == segment
    assert loaded[0x100:0x100 + len(bytes.fromhex(com['bytes']))] == bytes.fromhex(com['bytes'])
    for old, new in zip(com['fixups'], mz['fixups'], strict=True):
        assert new['file_offset'] == old['file_offset'] + 0x120
    assert mz['data'][0]['file_offset'] == 0x20 + 0x110


@pytest.mark.parametrize('container', ['', 'pe', None, False, 1])
def test_unknown_container_is_rejected(tmp_path, container):
    project, _, native, _, terminal = setup_project(tmp_path)
    with project:
        spec = definition(project, native, terminal)
        with pytest.raises(ValueError, match='container'):
            project.udc_dos_compile(spec['id'], assumptions=ASSUMPTIONS, container=container)


@pytest.mark.parametrize('ending', ['c3', 'c20400'])
def test_mz_refuses_com_return_without_a_process_return_adapter(tmp_path, ending):
    source = tmp_path / 'RETURN.COM'
    source.write_bytes(bytes.fromhex('b81100' + ending))
    with Project.create(tmp_path / 'return.fdb', source, image='com') as project:
        project.analyze()
        native = project.udc_native_capture('return-source', ['1000:0100'])
        spec = project.udc_dos_define('return-code', native['id'])
        retained = project.udc_dos_compile(spec['id'], assumptions=ASSUMPTIONS)
        assert retained['target'] == 'dos-com16-i386'
        with pytest.raises(ValueError, match='return.*adapter'):
            project.udc_dos_compile(spec['id'], assumptions=ASSUMPTIONS, container='mz')
