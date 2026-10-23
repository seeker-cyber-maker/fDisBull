"""Executable segment permissions do not make a Mach-O data export code."""
import struct

import pytest

from fdisbull.cli import respond
from fdisbull.loader import load_image
from fdisbull.project import Project
from fixtures_macho import CODE_ADDRESS, IMAGE_BASE, macho_fixture


CONSTANT_ADDRESS = IMAGE_BASE + 0x640


def _data_in_text(arch):
    data = bytearray(macho_fixture(arch))
    # Move the actual exported data symbol and trie leaf into __TEXT:__const,
    # whose segment is executable but whose section has no instruction flags.
    struct.pack_into('<Q', data, 0x3100 + 16 + 8, CONSTANT_ADDRESS)
    data[0x3100 + 16 + 5] = 3  # n_sect: __TEXT:__const.
    leaf = data.index(bytes.fromhex('0300904000'), 0x3080, 0x3100)
    data[leaf + 2:leaf + 4] = bytes.fromhex('c00c')  # ULEB(0x640).
    # These bytes would decode as RET if an erroneous seed promoted the data.
    data[0x640:0x648] = (bytes.fromhex('c390909090909090') if arch == 'x86_64'
                         else bytes.fromhex('c0035fd600000000'))
    return bytes(data)


def _write(tmp_path, arch):
    source = tmp_path / f'{arch}.dylib'
    source.write_bytes(_data_in_text(arch))
    return source


@pytest.mark.parametrize('arch', ['x86_64', 'arm64'])
def test_loader_does_not_promote_native_abstract_data_export_to_function_seed(tmp_path, arch):
    image = load_image(_write(tmp_path, arch), module=True)
    assert image.metadata['entrypoint_present'] is False
    assert any(region.executable and region.start <= CONSTANT_ADDRESS < region.start + len(region.data)
               for region in image.regions)
    assert CODE_ADDRESS in {seed.address for seed in image.seeds}
    assert CONSTANT_ADDRESS not in {seed.address for seed in image.seeds}


@pytest.mark.parametrize('arch', ['x86_64', 'arm64'])
def test_deferred_export_seeding_keeps_constant_data_while_decoding_real_code(tmp_path, arch):
    source = _write(tmp_path, arch)
    with Project.create(tmp_path / 'deferred.fdb', source, module=True) as project:
        receipt = project.analyze(max_instructions=100)
        assert receipt['stable'] and not receipt['pending_seed_phase'], receipt
        assert project.disassembly(CODE_ADDRESS, lines=1)['instructions'][0]['mnemonic'] == 'ret'
        assert not any(row['address'] == hex(CONSTANT_ADDRESS)
                       for row in project.disassembly()['instructions'])
        assert not any(row['address'] == hex(CONSTANT_ADDRESS) for row in project.functions())
        assert project.analyze(max_instructions=100)['attempted'] == 0


@pytest.mark.parametrize('arch', ['x86_64', 'arm64'])
def test_explicit_module_export_selection_rejects_data_and_accepts_real_code(tmp_path, arch):
    source = _write(tmp_path, arch)
    rejected = tmp_path / 'data.fdb'
    response = respond({'method': 'analyze-module', 'params': {
        'path': str(source), 'project': str(rejected), 'export': '_fixture_data'}})
    assert not response['ok'] and not rejected.exists()
    assert 'not a concrete native function' in response['error']['message']
    selected = tmp_path / 'code.fdb'
    response = respond({'method': 'analyze-module', 'params': {
        'path': str(source), 'project': str(selected), 'export': '_fixture_export'}})
    assert response['ok'] and response['result']['analysis']['stable'], response
    with Project(selected) as project:
        instructions = project.disassembly()['instructions']
        assert {row['address'] for row in instructions} == {hex(CODE_ADDRESS)}
        assert instructions[0]['mnemonic'] == 'ret'
