"""LC_FUNCTION_STARTS offsets are not Mach-O preferred virtual addresses."""
import struct

import lief
import pytest

from fdisbull.loader import _macho_function_address, load_image
from fdisbull.project import Project
from fixtures_macho import CODE_ADDRESS, DATA_ADDRESS, IMAGE_BASE, _section, _segment, macho_fixture


def _source(*, next_delta=8):
    data = bytearray(macho_fixture('arm64'))
    command_count, command_bytes = struct.unpack_from('<II', data, 16)
    assert 32 + command_bytes + 16 <= 0x600
    # LC_FUNCTION_STARTS data lives in the authored __LINKEDIT tail. Deltas
    # describe __TEXT + 0x600 then another start inside __TEXT,__text.
    struct.pack_into('<4I', data, 32 + command_bytes, 0x26, 16, 0x3410, 4)
    struct.pack_into('<II', data, 16, command_count + 1, command_bytes + 16)
    text_section = data.find(b'__text\0')
    assert text_section > 0
    struct.pack_into('<Q', data, text_section + 40, 12)
    data[0x604:0x60c] = bytes.fromhex('c0035fd6c0035fd6')
    data[0x3410:0x3414] = bytes((0x80, 0x0c, next_delta, 0))
    return bytes(data)


def test_arm64_function_starts_become_distinct_source_labeled_candidate_seeds(tmp_path):
    source = tmp_path / 'authored.dylib'
    source.write_bytes(_source())
    loaded = load_image(source, module=True)
    seeds = {seed.address: seed for seed in loaded.seeds}
    assert CODE_ADDRESS in seeds  # Existing named symbol/export is preserved.
    assert seeds[CODE_ADDRESS].name == '_fixture_export'
    assert seeds[CODE_ADDRESS + 8].source == 'LC_FUNCTION_STARTS'
    assert seeds[CODE_ADDRESS + 8].name == f'sub_{CODE_ADDRESS + 8:x}'
    assert DATA_ADDRESS not in seeds
    assert loaded.metadata['macho_function_starts'] == {
        'declared': 2, 'seeded': 1,
        'source': 'LC_FUNCTION_STARTS relative to __TEXT', 'status': 'validated',
    }

    project_path = tmp_path / 'study.fdb'
    with Project.create(project_path, source, module=True) as project:
        functions = {int(row['address'], 16): row for row in project.functions()}
        assert CODE_ADDRESS in functions and CODE_ADDRESS + 8 in functions
        assert functions[CODE_ADDRESS + 8]['status'] == 'candidate'
    with Project(project_path) as reopened:
        functions = {int(row['address'], 16): row for row in reopened.functions()}
        assert functions[CODE_ADDRESS + 8]['source'] == 'LC_FUNCTION_STARTS'


@pytest.mark.parametrize('delta', [6, 0x40])
def test_arm64_function_starts_reject_unaligned_or_data_section_targets(tmp_path, delta):
    source = tmp_path / 'malformed.dylib'
    source.write_bytes(_source(next_delta=delta))
    with pytest.raises(ValueError, match='LC_FUNCTION_STARTS entry'):
        load_image(source, module=True)


def test_arm64_function_start_rejects_zero_filled_executable_tail(tmp_path):
    source = tmp_path / 'unbacked.dylib'
    data = bytearray(_source())
    # __TEXT still has a virtual instruction section at +0x600, but the
    # segment declares only the first 0x500 bytes as file-backed.
    struct.pack_into('<Q', data, 32 + 48, 0x500)
    source.write_bytes(data)
    with pytest.raises(ValueError, match='LC_FUNCTION_STARTS entry'):
        load_image(source, module=True)


def test_arm64_function_starts_accept_file_backed_text_exec_section(tmp_path):
    source = tmp_path / 'text-exec.dylib'
    data = bytearray(_source())
    command_count, command_bytes = struct.unpack_from('<II', data, 16)
    section = _section('__text', '__TEXT_EXEC', IMAGE_BASE + 0x4600, 8,
                       0x4600, 0x80000400)
    segment = _segment('__TEXT_EXEC', IMAGE_BASE + 0x4000, 0x1000,
                       0x4000, 0x1000, 5, [section])
    assert 32 + command_bytes + len(segment) <= 0x600
    data[32 + command_bytes:32 + command_bytes + len(segment)] = segment
    struct.pack_into('<II', data, 16, command_count + 1, command_bytes + len(segment))
    # LC_FUNCTION_STARTS remains relative to __TEXT, even when code resides
    # in a distinct executable segment. The first offset is 0x4600.
    struct.pack_into('<I', data, 32 + command_bytes - 4, 5)
    data[0x3410:0x3415] = bytes((0x80, 0x8c, 0x01, 4, 0))
    data.extend(b'\0' * (0x5000 - len(data)))
    data[0x4600:0x4608] = bytes.fromhex('c0035fd6c0035fd6')
    source.write_bytes(data)

    loaded = load_image(source, module=True)
    seeds = {seed.address: seed for seed in loaded.seeds}
    assert seeds[IMAGE_BASE + 0x4600].source == 'LC_FUNCTION_STARTS'
    assert seeds[IMAGE_BASE + 0x4604].source == 'LC_FUNCTION_STARTS'
    assert loaded.metadata['macho_function_starts']['seeded'] == 2


def test_arm64_function_starts_do_not_change_x86_64_loader_seeds(tmp_path):
    source = tmp_path / 'x86.dylib'
    source.write_bytes(macho_fixture('x86_64'))
    loaded = load_image(source, module=True)
    assert loaded.arch == 'x86'
    assert 'macho_function_starts' not in loaded.metadata
    assert CODE_ADDRESS in {seed.address for seed in loaded.seeds}


def test_relative_unwind_address_normalizes_without_function_starts(tmp_path):
    """A separate unwind-derived offset can be qualified without LC_FUNCTION_STARTS."""
    source = tmp_path / 'unwind-address.dylib'
    source.write_bytes(macho_fixture('arm64'))  # No LC_FUNCTION_STARTS command.
    binary = lief.MachO.parse(source.read_bytes())[0]
    loaded = load_image(source, module=True)
    sections = [section for section in binary.sections if section.name == '__text']
    assert not binary.has_function_starts and len(sections) == 1
    mappings = loaded.metadata['file_mappings']
    size = source.stat().st_size
    assert _macho_function_address(0x600, IMAGE_BASE, sections, loaded.regions, mappings, size) == (CODE_ADDRESS, True)
    assert _macho_function_address(CODE_ADDRESS, IMAGE_BASE, sections, loaded.regions, mappings, size) == (CODE_ADDRESS, False)
    assert _macho_function_address(0x640, IMAGE_BASE, sections, loaded.regions, mappings, size) == (0x640, False)
    assert _macho_function_address(0x602, IMAGE_BASE, sections, loaded.regions, mappings, size) == (0x602, False)


def test_function_start_seed_survives_restart_and_patch_preserves_original(tmp_path):
    source = tmp_path / 'authored.dylib'
    source.write_bytes(_source())
    path = tmp_path / 'study.fdb'
    with Project.create(path, source, module=True) as project:
        assert project.analyze(max_instructions=100)['stable']
        original = project.disassembly(CODE_ADDRESS + 8, version=1, lines=1)['instructions'][0]
        assert original['bytes'] == 'c0035fd6'
        child = project.patch(CODE_ADDRESS + 8, '1f2003d5')['version']
        project.analyze(version=child, max_instructions=100)
        assert project.disassembly(CODE_ADDRESS + 8, version=child, lines=1)['instructions'][0]['bytes'] == '1f2003d5'
    source.unlink()
    with Project(path) as reopened:
        assert reopened.disassembly(CODE_ADDRESS + 8, version=1, lines=1)['instructions'][0]['bytes'] == 'c0035fd6'
        assert reopened.disassembly(CODE_ADDRESS + 8, version=child, lines=1)['instructions'][0]['bytes'] == '1f2003d5'
        assert reopened.status(version=1)['counts']['instructions'] > 0
