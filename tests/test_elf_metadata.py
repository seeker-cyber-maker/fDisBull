"""Real compiler/linker ELF metadata and native slot-proof checks; never run ELF."""
import json
from pathlib import Path
import shutil
import struct
import subprocess

import iced_x86 as ix
import lief
import pytest

from fdisbull.elf_metadata import inspect_elf, _arm64_stubs, _x86_stubs


@pytest.fixture(scope='module')
def elf_files(tmp_path_factory):
    gcc = shutil.which('gcc')
    if gcc is None:
        pytest.skip('gcc required for actual ELF shared-library and PIE fixtures')
    root = tmp_path_factory.mktemp('elf-metadata')
    source = root / 'meta.c'
    source.write_text('''#include <stdio.h>
extern int external_object;
extern int unresolved_function(int);
int export_data=7;
__thread int export_tls=5;
int export_function(int x) {
  puts("ELF metadata fixture");
  return unresolved_function(x)+external_object+export_data;
}
static int implementation(void) { return 42; }
typedef int (*function_pointer)(void);
static function_pointer resolver(void) { return implementation; }
int dispatch(void) __attribute__((ifunc("resolver")));
__asm__(".globl absolute_export\\n.set absolute_export,0x1234");
''')
    versions = root / 'versions.map'
    versions.write_text('LIB_META_1 { global: export_function; export_data; export_tls; dispatch; absolute_export; local: *; };\n')
    library = root / 'libmeta.so'
    command = [gcc, '-shared', '-fPIC', '-Wl,--version-script=' + str(versions), '-Wl,-soname,libmeta.so',
               '-Wl,-z,ibtplt', '-Wl,--enable-new-dtags,-rpath,$ORIGIN/meta', str(source), '-o', str(library)]
    subprocess.run(command, check=True, capture_output=True)
    if not isinstance(lief.parse(library), lief.ELF.Binary):
        pytest.skip('available gcc does not produce ELF files')
    main = root / 'main.c'
    main.write_text('''#include <stdio.h>
extern int export_function(int);
extern int export_data;
extern __thread int export_tls;
int main(void) { return export_function(export_data)+export_tls+puts("PIE metadata"); }
''')
    pie = root / 'pie'
    subprocess.run([gcc, '-fPIE', '-pie', str(main), '-L' + str(root), '-lmeta',
                    '-Wl,--unresolved-symbols=ignore-in-shared-libs', '-Wl,--disable-new-dtags,-rpath,$ORIGIN/old',
                    '-o', str(pie)], check=True, capture_output=True)
    no_plt = root / 'libnoplts.so'
    subprocess.run([gcc, '-shared', '-fPIC', '-fno-plt', str(source), '-o', str(no_plt)], check=True, capture_output=True)
    multiple = root / 'multiple.c'
    multiple.write_text('int old_foo(void){return 1;} int new_foo(void){return 2;}\n'
                        '__asm__(".symver old_foo,foo@V1");\n'
                        '__asm__(".symver new_foo,foo@@V2");\n')
    multiple_versions = root / 'multiple.map'
    multiple_versions.write_text('V1 {}; V2 {} V1;\n')
    versioned = root / 'multiple.so'
    subprocess.run([gcc, '-shared', '-fPIC', str(multiple), '-Wl,--version-script=' + str(multiple_versions),
                    '-o', str(versioned)], check=True, capture_output=True)
    return dict(root=root, gcc=gcc, library=library, pie=pie, no_plt=no_plt, versioned=versioned)


def metadata(path, **options):
    data = Path(path).read_bytes()
    return inspect_elf(lief.parse(data), data, **options)


def named(rows, name):
    return next(item for item in rows if item['name'] == name)


def test_got_slots_come_from_actual_relocations_and_keep_module_proof(elf_files):
    result = metadata(elf_files['library'])
    puts = named(result['imports'], 'puts')
    assert puts['kind'] == 'got' and puts['address'] > 0
    assert puts['relocation_type'] == 'X86_64_JUMP_SLOT'
    assert puts['module'] == puts['required_module'] == 'libc.so.6'
    assert puts['version'].startswith('GLIBC_') and puts['version_source'] == 'requirement'
    assert puts['module_source'] == 'ELF version requirement'
    assert not puts['runtime_provider_observed']
    assert puts['binding_state'] == 'runtime_unresolved' and puts['pointer_width'] == 8
    relocation = next(item for item in result['relocations'] if item['slot'] == puts['address'])
    assert relocation['symbol'] == 'puts' and relocation['size_bits'] == 64
    assert relocation['has_addend'] and relocation['addend_source'] == 'explicit_RELA'
    # The fixture intentionally leaves both names undefined and unversioned.
    # One DT_NEEDED libc entry does not prove that libc supplies either name.
    for name in ('external_object', 'unresolved_function'):
        entry = named(result['imports'], name)
        assert entry['module'] is None and entry['required_module'] is None
        assert entry['module_candidates'] == ['libc.so.6']
    assert named(result['imports'], 'external_object')['symbol_type'] == 'NOTYPE'
    assert named(result['imports'], '_ITM_registerTMCloneTable')['weak']
    assert json.loads(json.dumps(result)) == result


def test_plt_stubs_are_native_validated_not_fixed_stride_guesses(elf_files):
    path = elf_files['library']
    data, binary = path.read_bytes(), lief.parse(path)
    result = inspect_elf(binary, data)
    puts = named(result['imports'], 'puts')
    assert puts['stub_addresses']
    for address in puts['stub_addresses']:
        stub = next(item for item in result['linkage']['stubs'] if item['address'] == address)
        assert stub['slot'] == puts['address'] and stub['section'] == '.plt.sec'
        raw = bytes.fromhex(stub['bytes'])
        rows = list(ix.Decoder(64, raw, ip=address))
        assert rows[0].mnemonic == ix.Mnemonic.ENDBR64
        jump = rows[-1]
        assert jump.mnemonic == ix.Mnemonic.JMP
        assert jump.is_ip_rel_memory_operand and jump.ip_rel_memory_address == puts['address']
    # Section entry_size is metadata, not the proof or assumed entry stride.
    for section in binary.sections:
        if section.name.startswith('.plt'):
            section.entry_size = 0
    assert named(inspect_elf(binary, data)['imports'], 'puts')['stub_addresses'] == puts['stub_addresses']


def test_function_data_ifunc_tls_and_absolute_exports_have_distinct_identity(elf_files):
    result = metadata(elf_files['library'])
    function = named(result['exports'], 'export_function')
    assert function['is_function'] and function['code_seed_eligible']
    data = named(result['exports'], 'export_data')
    assert data['symbol_type'] == 'OBJECT' and data['address'] > 0 and not data['code_seed_eligible']
    resolver = named(result['exports'], 'dispatch')
    assert resolver['is_ifunc'] and not resolver['code_seed_eligible']
    assert resolver['address_kind'] == 'ifunc_resolver' and resolver['resolver_address'] == resolver['address']
    tls = named(result['exports'], 'export_tls')
    assert tls['is_tls'] and tls['address'] is None and tls['tls_offset'] == 0
    absolute = named(result['exports'], 'absolute_export')
    assert absolute['absolute'] and absolute['address'] is None and absolute['absolute_value'] == 0x1234
    assert not tls['code_seed_eligible'] and not absolute['code_seed_eligible']
    assert named(result['imports'], 'export_data')['callable'] is False


def test_pie_copy_storage_tls_and_versioned_dependency_are_not_callable_slots(elf_files):
    result = metadata(elf_files['pie'])
    assert result['header']['is_pie']
    assert result['linkage']['interpreter'].endswith('ld-linux-x86-64.so.2')
    assert result['linkage']['rpath'] == ['$ORIGIN/old'] and not result['linkage']['runpath']
    assert {row['name'] for row in result['libraries']} == {'libmeta.so', 'libc.so.6'}
    function = named(result['imports'], 'export_function')
    assert function['module'] == 'libmeta.so' and function['version'] == 'LIB_META_1'
    copy = named(result['imports'], 'export_data')
    assert copy['kind'] == 'copy_storage' and copy['address'] is None and copy['storage_address'] > 0
    assert copy['callable'] is False and 'runtime_unresolved' not in copy
    assert copy['required_module'] == 'libmeta.so'
    copy_relocation = next(item for item in result['relocations'] if item['type'] == 'X86_64_COPY')
    assert copy_relocation['copy_storage'] == copy['storage_address'] and copy_relocation['slot'] is None
    tls = named(result['imports'], 'export_tls')
    assert tls['symbol_type'] == 'TLS' and tls['address'] is None and tls['callable'] is False
    assert tls['module'] == 'libmeta.so'
    assert named(result['exports'], 'export_data')['imported_copy']


def test_fno_plt_uses_glob_dat_without_fabricating_a_stub(elf_files):
    result = metadata(elf_files['no_plt'])
    puts = named(result['imports'], 'puts')
    assert puts['kind'] == 'got' and puts['relocation_type'] == 'X86_64_GLOB_DAT'
    assert puts['address'] > 0 and puts['callable'] is True
    assert puts['stub_addresses'] == []


def test_duplicate_versioned_export_names_remain_separate(elf_files):
    result = metadata(elf_files['versioned'])
    symbols = [item for item in result['exports'] if item['name'] == 'foo']
    assert len(symbols) == 2 and len({item['address'] for item in symbols}) == 2
    assert {(item['version'], item['version_hidden']) for item in symbols} == {('V1', True), ('V2', False)}
    assert all(item['code_seed_eligible'] for item in symbols)


def test_conflicting_version_requirement_indices_do_not_prove_a_module(elf_files):
    data = bytearray(elf_files['pie'].read_bytes())
    binary = lief.parse(bytes(data))
    section = binary.get_section('.gnu.version_r')
    offset, end = int(section.offset), int(section.offset + section.size)
    patched = False
    while offset + 16 <= end:
        _, count, _, auxiliary, following = struct.unpack_from('<HHIII', data, offset)
        aux = offset + auxiliary
        for _ in range(count):
            other = struct.unpack_from('<H', data, aux + 6)[0]
            if other != 2:
                struct.pack_into('<H', data, aux + 6, 2)
                patched = True
                break
            step = struct.unpack_from('<I', data, aux + 12)[0]
            if not step:
                break
            aux += step
        if patched or not following:
            break
        offset += following
    assert patched
    result = inspect_elf(lief.parse(bytes(data)), bytes(data))
    assert any('Conflicting version requirement' in warning for warning in result['warnings'])
    for symbol in result['imports']:
        if symbol['version_index'] == 2:
            assert symbol['module'] is None


@pytest.mark.parametrize('prefix', ('64', '65'))
def test_segment_base_override_cannot_prove_a_rip_relative_got_slot(prefix):
    data = bytes.fromhex(prefix + 'ff2500000000')
    assert _x86_stubs(data, 0x1000, 64, {0x1007: []}, [16], []) == []


def test_arm64_plt_sequence_requires_its_loaded_register_and_exact_slot():
    # ADRP X16,0x1000; LDR X17,[X16,#16]; ADD X16,X16,#16; BR X17.
    raw = bytes.fromhex('10000090110a40f91042009120021fd6')
    stubs = _arm64_stubs(raw, 0x1000, {0x1010: []}, [32], [])
    assert len(stubs) == 1 and stubs[0]['slot'] == 0x1010 and stubs[0]['bytes'] == raw.hex()
    assert _arm64_stubs(raw, 0x1000, {0x1018: []}, [32], []) == []
    wrong_register = raw[:-4] + bytes.fromhex('00021fd6')  # BR X16 (address, not loaded pointer)
    assert _arm64_stubs(wrong_register, 0x1000, {0x1010: []}, [32], []) == []
    # LDR XZR discards the loaded value. BR XZR cannot inherit its slot.
    zero_register = bytes.fromhex('100000901f0a40f9e0031fd6')
    assert _arm64_stubs(zero_register, 0x1000, {0x1010: []}, [32], []) == []


def test_limits_cap_metadata_and_path_lists_with_warnings(elf_files):
    result = metadata(elf_files['library'], max_items=1)
    for key in ('imports', 'exports', 'relocations', 'libraries'):
        assert len(result[key]) <= 1
    assert any('cap' in warning or 'budget' in warning for warning in result['warnings'])
    binary = lief.parse(elf_files['library'])
    path = next(entry for entry in binary.dynamic_entries if str(entry.tag).endswith('.RUNPATH'))
    path.runpath = '/a:/b:/c:/d'
    # Put the path first so an overall dynamic-entry cap cannot hide this test.
    first = next(iter(binary.dynamic_entries))
    old_tag, old_value = first.tag, first.value
    if old_tag != path.tag:
        # Raising the entry budget to the existing table count includes RUNPATH;
        # its own split-list bound still uses that same explicit item budget.
        limit = len(list(binary.dynamic_entries))
        path.runpath = ':'.join('/item' + str(i) for i in range(limit + 2))
        result = inspect_elf(binary, elf_files['library'].read_bytes(), max_items=limit)
        assert len(result['linkage']['runpath']) == limit
        assert any('RUNPATH components capped' in warning for warning in result['warnings'])


def test_rel_encoding_does_not_claim_an_explicit_zero_addend(elf_files):
    source, output = elf_files['root'] / 'rel32.c', elf_files['root'] / 'rel32.so'
    source.write_text('extern void imported(void); void exported(void){ imported(); }\n')
    compiled = subprocess.run([elf_files['gcc'], '-m32', '-nostdlib', '-shared', '-fPIC', str(source), '-o', str(output)], capture_output=True)
    if compiled.returncode:
        pytest.skip('32-bit ELF assembler/linker support unavailable')
    result = metadata(output)
    relocation = next(item for item in result['relocations'] if item['symbol'] == 'imported')
    assert not relocation['has_addend'] and relocation['addend'] is None
    assert relocation['addend_source'] == 'implicit_REL_storage_not_decoded'
    assert isinstance(relocation['lief_addend_raw'], int)


def test_unversioned_copy_storage_keeps_dependency_candidates_without_attribution(elf_files):
    source, output = elf_files['root'] / 'copy.c', elf_files['root'] / 'copy'
    source.write_text('extern int export_data; int main(void){ return export_data; }\n')
    subprocess.run([elf_files['gcc'], '-fPIE', '-pie', str(source), '-L' + str(elf_files['root']),
                    '-lnoplts', '-Wl,--unresolved-symbols=ignore-in-shared-libs', '-o', str(output)],
                   check=True, capture_output=True)
    result = metadata(output)
    copy = named(result['imports'], 'export_data')
    assert copy['kind'] == 'copy_storage' and copy['module'] is None
    assert 'libnoplts.so' in copy['module_candidates']
    assert copy['address'] is None and copy['storage_address'] > 0 and not copy['callable']


@pytest.mark.parametrize('max_items', (0, True, 100001, '2'))
def test_bad_limits_are_rejected(elf_files, max_items):
    path = elf_files['library']
    with pytest.raises(ValueError, match='max_items'):
        inspect_elf(lief.parse(path), path.read_bytes(), max_items=max_items)
