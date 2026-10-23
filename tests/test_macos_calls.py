"""Public static Mach-O call workflows; authored file bytes are never executed."""
import struct

import pytest

from fdisbull.project import Project
from fixtures_macho import (CODE_ADDRESS, DATA_ADDRESS, IMAGE_BASE, LAZY_SLOT,
                            LIBRARIES, NONLAZY_SLOT, STUB_ADDRESS, macho_fixture)


ARCHITECTURES = ('x86_64', 'arm64')
SOURCE = DATA_ADDRESS + 32
DESTINATION = DATA_ADDRESS + 64


def _commands(data):
    offset = 32
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        command, size = struct.unpack_from('<II', data, offset)
        yield command, offset
        offset += size


def _set_section_size(data, name, size):
    for command, offset in _commands(data):
        if command != 0x19:
            continue
        for index in range(struct.unpack_from('<I', data, offset + 64)[0]):
            section = offset + 72 + index * 80
            if data[section:section + 16].split(b'\0', 1)[0] == name.encode():
                struct.pack_into('<Q', data, section + 40, size)
                return
    raise AssertionError('missing authored section')


def _adr(register, instruction_address, target):
    displacement = target - instruction_address
    assert -(1 << 20) <= displacement < (1 << 20)
    word = 0x10000000 | ((displacement & 3) << 29)
    word |= (((displacement >> 2) & 0x7FFFF) << 5) | register
    return struct.pack('<I', word)


def _call_setup(arch, name):
    """Real CPU instructions setting the first three integer ABI arguments."""
    second = SOURCE if name == 'memcpy' else 42
    if arch == 'x86_64':
        code = b'\x48\xbf' + struct.pack('<Q', DESTINATION)  # MOV RDI,imm64
        code += (b'\x48\xbe' + struct.pack('<Q', second) if name == 'memcpy'
                 else b'\xbe' + struct.pack('<I', second))  # MOV RSI/ESI
        code += b'\xba' + struct.pack('<I', 8)  # MOV EDX,8
        site = CODE_ADDRESS + len(code)
        code += b'\xe8' + struct.pack('<i', STUB_ADDRESS - site - 5) + b'\xc3'
    else:
        code = _adr(0, CODE_ADDRESS, DESTINATION)
        code += (_adr(1, CODE_ADDRESS + 4, second) if name == 'memcpy'
                 else struct.pack('<I', 0xD2800001 | (second << 5)))  # MOV X1,42
        code += struct.pack('<I', 0xD2800002 | (8 << 5))  # MOV X2,8
        site = CODE_ADDRESS + len(code)
        code += struct.pack('<I', 0x94000000 | ((STUB_ADDRESS - site) // 4))
        code += bytes.fromhex('c0035fd6')  # RET
    assert CODE_ADDRESS + len(code) <= STUB_ADDRESS
    return code, site


def _consumer(arch, name, *, addend=0):
    data = bytearray(macho_fixture(arch, consumer=True))
    code, site = _call_setup(arch, name)
    data[0x600:0x620] = code.ljust(32, b'\0')
    _set_section_size(data, '__text', len(code))
    _set_section_size(data, '__data', 96)
    data[SOURCE - IMAGE_BASE:SOURCE - IMAGE_BASE + 8] = b'source!!'
    # Preserve string-table indexes while changing the undefined nlist name.
    original = b'_fixture_call\0'
    string_offset = data.index(original, 0x3180, 0x3200)
    replacement = ('_' + name).encode() + b'\0'
    data[string_offset:string_offset + len(original)] = replacement.ljust(len(original), b'\0')
    # Rebuild the actual lazy bind stream, including optional SET_ADDEND_SLEB.
    assert 0 <= addend < 64
    lazy = b'\x12\x40' + replacement
    if addend:
        lazy += bytes([0x60, addend])
    lazy += b'\x72\0\x90\0'
    data[0x3040:0x3080] = lazy.ljust(64, b'\0')
    for command, offset in _commands(data):
        if command == 0x80000022:
            struct.pack_into('<I', data, offset + 36, len(lazy))
            break
    return bytes(data), site


def _create(tmp_path, data):
    source = tmp_path / 'consumer.dylib'
    source.write_bytes(data)
    # A dylib has no process entry command. Choose its authored exported code.
    return Project.create(tmp_path / 'consumer.fdb', source, entry=CODE_ADDRESS)


def _run(project):
    receipt = project.auto_analyze(max_instructions=256, max_functions=20,
                                   max_steps=10000, max_rounds=8)
    assert receipt['stable'] and not receipt['budget_exhausted'], receipt
    return receipt


def _imports(project):
    return {item['original_name']: item for item in project.information('imports')['items']}


@pytest.mark.parametrize('arch', ARCHITECTURES)
def test_native_macho_metadata_stubs_and_abi_survive_public_workflow(tmp_path, arch):
    with _create(tmp_path, macho_fixture(arch, consumer=True, modern_exports=True)) as project:
        summary = project.information('summary')
        assert summary['counts']['imports'] == 2 and summary['counts']['exports'] == 3
        assert summary['counts']['sections'] == 6 and summary['counts']['relocations'] == 1
        imported = _imports(project)['_fixture_call']
        assert imported['address'] == hex(LAZY_SLOT)
        assert imported['module'] == LIBRARIES[1] and imported['library_ordinal'] == 2
        assert imported['stub_addresses'] == [STUB_ADDRESS]
        assert imported['binding_state'] == 'runtime_unresolved' and imported['target'] is None
        assert imported['pointer_width'] == 8
        assert [row['name'] for row in project.information('libraries')['items']] == list(LIBRARIES)
        exports = {row.get('original_name', row['name']): row
                   for row in project.information('exports')['items']}
        assert exports['_fixture_export']['is_code']
        assert not exports['_fixture_data']['is_code']
        assert exports['_fixture_reexport']['kind'] == 'reexport'
        assert exports['_fixture_reexport']['address'] is None
        relocation = project.information('relocations')['items'][0]
        assert relocation['address'] == hex(DATA_ADDRESS) and relocation['width'] == 8
        sections = {row['full_name']: row for row in project.information('sections')['items']}
        assert sections['__TEXT:__text']['permissions'] == 'r-x'
        assert sections['__TEXT:__const']['permissions'] == 'r-x'
        assert not sections['__TEXT:__const']['is_code']
        assert sections['__DATA:__data']['permissions'] == 'rw-'

        assert project.analyze(max_instructions=256)['stable']
        groups = project.calls(kind='library')['items']
        assert len(groups) == 1
        call = groups[0]
        assert call['function'] == '_fixture_call' and call['module'] == LIBRARIES[1]
        assert call['target'] == hex(LAZY_SLOT) and call['stub_addresses'] == [hex(STUB_ADDRESS)]
        assert call['call_site_count'] == 1 and call['runtime_provider_unresolved']
        assert not call['runtime_observed'] and not call['function_boundary_proven']
        _run(project)
        result = project.function_analysis(CODE_ADDRESS)
        assert result['state'] == 'done' and not result['stale']
        frame = result['result']['frame']
        assert frame['abi']['profile']['name'] == ('x86_64_sysv' if arch == 'x86_64' else 'aarch64_darwin')
        assert any(row['kind'] == 'import_call' and row['source'] == hex(CODE_ADDRESS)
                   for row in project.xrefs(LAZY_SLOT))
        assert not project.call_effects()['items']  # No contract for an unknown symbol.


@pytest.mark.parametrize('arch', ARCHITECTURES)
@pytest.mark.parametrize('name', ('memcpy', 'memset'))
def test_decorated_macho_contracts_use_native_argument_values(tmp_path, arch, name):
    data, site = _consumer(arch, name)
    with _create(tmp_path, data) as project:
        _run(project)
        imported = _imports(project)['_' + name]
        assert imported['address'] == hex(LAZY_SLOT) and imported['addend'] == 0
        call = project.calls(kind='library')['items'][0]
        assert call['function'] == '_' + name and call['call_sites'][0]['address'] == hex(site)
        assert any(row['kind'] == 'import_call' and row['source'] == hex(site)
                   for row in project.xrefs(LAZY_SLOT))
        effects = project.call_effects(include_unresolved=False)['items']
        actual = {(row['summary_name'], row['access'], row['address'], row['size']) for row in effects}
        expected = {(name, 'write', DESTINATION, 8)}
        if name == 'memcpy':
            expected.add((name, 'read', SOURCE, 8))
        else:
            assert effects[0]['fill_byte'] == 42
        assert actual == expected
        assert all(row['summary_source']['kind'] == 'import'
                   and row['summary_source']['original_name'] == '_' + name
                   and row['call_site'] == hex(site) and not row['runtime_observed']
                   for row in effects)


@pytest.mark.parametrize('arch', ARCHITECTURES)
@pytest.mark.parametrize('chained', (False, True))
def test_unresolved_dyld_slot_bytes_never_become_internal_code_target(tmp_path, arch, chained):
    data = bytearray(macho_fixture(arch, consumer=True, chained=chained))
    if arch == 'x86_64':
        code = b'\xff\x15' + struct.pack('<i', NONLAZY_SLOT - CODE_ADDRESS - 6) + b'\xc3'
    else:
        code = _adr(16, CODE_ADDRESS, NONLAZY_SLOT)
        code += bytes.fromhex('100240f900023fd6c0035fd6')  # LDR X16,[X16]; BLR X16; RET
    data[0x600:0x620] = code.ljust(32, b'\0')
    _set_section_size(data, '__text', len(code))
    if not chained:
        # Even a plausible executable preferred address is only disk data at
        # an unresolved dyld binding site, not its eventual runtime provider.
        struct.pack_into('<Q', data, 0x1000, STUB_ADDRESS)
    with _create(tmp_path, bytes(data)) as project:
        _run(project)
        imported = _imports(project)['_fixture_nonlazy']
        assert imported['binding_state'] == 'runtime_unresolved' and imported['target'] is None
        call = project.calls(kind='library')['items'][0]
        assert call['function'] == '_fixture_nonlazy' and call['target'] == hex(NONLAZY_SLOT)
        assert call['runtime_provider_unresolved'] and not call['runtime_observed']
        assert any(row['kind'] == 'import_call' for row in project.xrefs(NONLAZY_SLOT))
        site = call['call_sites'][0]['address']
        assert not any(row['kind'] == 'resolved_call'
                       for row in project.xrefs(site, direction='from'))


@pytest.mark.parametrize('arch', ARCHITECTURES)
def test_nonzero_binding_addend_keeps_identity_but_does_not_apply_memcpy_contract(tmp_path, arch):
    data, site = _consumer(arch, 'memcpy', addend=1)
    with _create(tmp_path, data) as project:
        _run(project)
        imported = _imports(project)['_memcpy']
        assert imported['addend'] == 1 and imported['address'] == hex(LAZY_SLOT)
        call = project.calls(kind='library')['items'][0]
        assert call['function'] == '_memcpy' and call['call_sites'][0]['address'] == hex(site)
        assert not project.call_effects()['items']
