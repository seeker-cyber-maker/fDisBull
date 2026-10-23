"""Public Linux linkage/call-effect integration with actual unexecuted ELF."""
import json
import shutil
import struct
import subprocess

import lief
import pytest

from fdisbull.cli import respond
from fdisbull.project import Project


@pytest.fixture(scope='module')
def linux_call_files(tmp_path_factory):
    gcc = shutil.which('gcc')
    if gcc is None:
        pytest.skip('gcc required for real Linux ELF calls')
    root = tmp_path_factory.mktemp('linux-calls')
    source = root / 'calls.c'
    # Explicit prototypes avoid fortified string.h wrappers lowering the calls
    # into builtins despite -fno-builtin. Hidden buffers produce direct static
    # addresses, without assuming a runtime interposable data-GOT value.
    source.write_text('''extern void *memcpy(void *,const void *,unsigned long);
extern void *memset(void *,int,unsigned long);
__attribute__((visibility("hidden"))) const unsigned char platform_src[64]="source";
__attribute__((visibility("hidden"))) unsigned char platform_dst[64];
void platform_entry(void) {
  memcpy(platform_dst,platform_src,12);
  memset(platform_dst+16,42,8);
}
extern void unknown_external(void);
void unversioned_entry(void) { unknown_external(); }
''')
    files = {}
    for mode, extra in (('plt', []), ('got', ['-fno-plt'])):
        output = root / (mode + '.so')
        subprocess.run([gcc, '-shared', '-fPIC', '-nostartfiles', '-O1', '-fno-builtin',
                        '-fno-optimize-sibling-calls', '-Wl,-e,platform_entry', '-Wl,-z,ibtplt',
                        *extra, str(source), '-o', str(output)], check=True, capture_output=True)
        native = lief.parse(output)
        if not isinstance(native, lief.ELF.Binary):
            pytest.skip('available compiler does not emit ELF')
        files[mode] = dict(path=output, entry=int(native.get_symbol('platform_entry').value),
                           source=int(native.get_symbol('platform_src').value),
                           destination=int(native.get_symbol('platform_dst').value))
    return files


def raw_import(project, name, version=None):
    return next(item for item in project._document(project.version(version)['id'])['imports'] if item['name'] == name)


def run(project, **options):
    result = project.auto_analyze(max_instructions=1024, max_functions=100,
                                  max_steps=10000, max_rounds=8, **options)
    assert result['stable'] and not result['budget_exhausted'], result
    return result


@pytest.mark.parametrize('mode', ('plt', 'got'))
def test_linux_calls_xrefs_and_shared_bulk_effects(linux_call_files, tmp_path, mode):
    fixture = linux_call_files[mode]
    with Project.create(tmp_path / (mode + '.fdb'), fixture['path']) as project:
        run(project)
        groups = {item['function']: item for item in project.calls(kind='library')['items']}
        assert {'memcpy', 'memset', 'unknown_external'} <= set(groups)
        for name in ('memcpy', 'memset'):
            record, group = raw_import(project, name), groups[name]
            assert record['kind'] == 'got' and record['binding_state'] == 'runtime_unresolved'
            assert record['module_source'] == 'ELF version requirement'
            assert record['module'] == group['module'] == 'libc.so.6'
            assert record['version'].startswith('GLIBC_')
            assert group['runtime_provider_unresolved'] and not group['runtime_observed']
            assert group['target_kind'] == 'import_slot'
            assert bool(record['stub_addresses']) is (mode == 'plt')
            assert any(row['kind'] == 'import_call' for row in project.xrefs(record['address']))
            site = group['call_sites'][0]
            instruction = project.disassembly(site['address'], lines=1)['instructions'][0]
            assert instruction['flow'] == ('call' if mode == 'plt' else 'indirect_call')
        unknown = raw_import(project, 'unknown_external')
        assert groups['unknown_external']['module'] is None and unknown['module'] is None
        assert unknown['module_candidates'] == ['libc.so.6']
        assert not any(item['kind'] == 'function' and item.get('function') in ('memcpy', 'memset')
                       for item in project.calls()['items'])
        effects = project.call_effects(include_unresolved=False)['items']
        actual = {(item['summary_name'], item['access'], item['address'], item['size']) for item in effects}
        assert actual == {('memcpy', 'read', fixture['source'], 12),
                          ('memcpy', 'write', fixture['destination'], 12),
                          ('memset', 'write', fixture['destination'] + 16, 8)}
        assert next(item for item in effects if item['summary_name'] == 'memset')['fill_byte'] == 42
        assert all(not item['runtime_observed'] for item in effects)
        assert {row['name'] for row in project.information('libraries')['items']} == {'libc.so.6'}
        assert project.information('relocations')['total'] >= 3
        assert project.information('linkage')['linkage']['native_stubs_executed'] is False


@pytest.mark.parametrize('mode', ('plt', 'got'))
def test_patched_got_disk_pointer_does_not_become_an_internal_call(linux_call_files, tmp_path, mode):
    fixture = linux_call_files[mode]
    with Project.create(tmp_path / 'pointer.fdb', fixture['path']) as project:
        run(project)
        imported = raw_import(project, 'memcpy')
        slot, target = imported['address'], fixture['entry']
        parent_source = project.version(1)['sha256']
        patch = project.patch(slot, struct.pack('<Q', target).hex(), label='unresolved runtime slot bytes')
        assert patch['version'] == 2
        run(project)
        assert project.version(1)['sha256'] == parent_source
        assert raw_import(project, 'memcpy')['binding_state'] == 'runtime_unresolved'
        groups = project.calls(kind='library')['items']
        call = next(item for item in groups if item['function'] == 'memcpy')
        sources = {int(site['address'], 16) for site in call['call_sites']}
        assert any(row['kind'] == 'import_call' for row in project.xrefs(slot))
        for source in sources:
            assert not any(row['kind'] == 'resolved_call' and int(row['target'], 16) == target
                           for row in project.xrefs(source, direction='from'))
        assert not project.db.execute("SELECT 1 FROM xrefs WHERE version=2 AND target=? AND kind IN ('resolved_call','resolved_branch')",
                                      (f'{target:016x}',)).fetchone()
        # The known library identity is useful even while on-disk pointer bytes
        # are deliberately unusable as a runtime provider address.
        assert any(item['summary_name'] == 'memcpy' for item in project.call_effects()['items'])


def test_refresh_upgrades_legacy_metadata_preserving_versions_annotations_and_bytes(linux_call_files, tmp_path):
    fixture = linux_call_files['plt']
    with Project.create(tmp_path / 'refresh.fdb', fixture['path']) as project:
        run(project)
        slot = raw_import(project, 'memcpy')['address']
        project.annotate(fixture['entry'], 'user_platform', kind='name', author='reviewer')
        project.annotate(slot, 'user_copy_slot', kind='name', author='reviewer')
        region = project._mapping(1, fixture['entry'])
        byte = region.data[fixture['entry'] - region.start:fixture['entry'] - region.start + 1]
        project.patch(fixture['entry'], byte.hex(), label='version isolation control')
        run(project)
        versions_before = project.versions()
        counts_before = project.status()['counts']['instructions']
        legacy = project._document(2)
        legacy['imports'] = [dict(name=item['name'], address=None, module=None, kind='dynamic_symbol', ordinal=None)
                             for item in legacy['imports']]
        for key in ('libraries', 'relocations', 'linkage', 'metadata_revision'):
            legacy.pop(key, None)
        with project.transaction(True):
            project.db.execute('UPDATE binary_info SET document=? WHERE version=2', (json.dumps(legacy),))
            project.db.execute("DELETE FROM symbols WHERE version=2 AND kind IN ('imports','import_stubs')")
            project.db.execute('INSERT INTO symbols VALUES (2,?,?,?,?,?)',
                               (f'{0xdeadbeef:016x}', 'import_stubs', 'ghost_import', '', '{}'))
        refreshed = project.refresh_metadata()
        assert refreshed['imports'] >= 3 and refreshed['relocations'] >= 3
        assert refreshed['invalidated_tasks']
        assert project.versions() == versions_before
        assert project.status()['counts']['instructions'] == counts_before
        assert project.function_analysis(fixture['entry'])['stale']
        assert not project.call_effects()['items'] and project.call_effects()['stale_jobs_excluded'] > 0
        assert not project.db.execute("SELECT 1 FROM symbols WHERE version=2 AND name='ghost_import'").fetchone()
        displayed = next(item for item in project.information('imports')['items'] if item['original_name'] == 'memcpy')
        assert displayed['name'] == 'user_copy_slot' and displayed['module'] == 'libc.so.6'
        assert project.function_analysis(fixture['entry'], version=1)['state'] == 'done'
        run(project)
        assert project.disassembly(fixture['entry'], lines=1)['instructions'][0]['name'] == 'user_platform'
        assert len(project.call_effects(include_unresolved=False)['items']) == 3
        assert project.versions() == versions_before


def test_stub_patch_retracts_library_identity_and_derived_call_xref_only_in_child(linux_call_files, tmp_path):
    fixture = linux_call_files['plt']
    with Project.create(tmp_path / 'stub.fdb', fixture['path']) as project:
        run(project)
        imported = raw_import(project, 'memcpy')
        slot, stub = imported['address'], imported['stub_addresses'][0]
        group = next(item for item in project.calls(kind='library')['items'] if item['function'] == 'memcpy')
        call_site = group['call_sites'][0]['address']
        # Native CET ENDBR64 then RIP-relative JMP[GOT]. Preserve ENDBR and
        # replace the six-byte jump; its former slot binding must disappear.
        native = next(item for item in project.information('linkage')['linkage']['stubs'] if item['address'] == stub)
        raw = bytes.fromhex(native['bytes'])
        assert raw[:4] == bytes.fromhex('f30f1efa') and raw[4:6] == bytes.fromhex('ff25')
        project.patch(stub + 4, '90' * 6, label='remove native PLT slot proof')
        assert not raw_import(project, 'memcpy')['stub_addresses']
        assert not project.db.execute("SELECT 1 FROM symbols WHERE version=2 AND kind='import_stubs' AND address=?",
                                      (f'{stub:016x}',)).fetchone()
        run(project)
        assert not any(row['kind'] == 'import_call' and int(row['target'], 16) == slot
                       for row in project.xrefs(call_site, direction='from'))
        assert not any(item['summary_name'] == 'memcpy' and item['call_site'] == call_site
                       for item in project.call_effects()['items'])
        assert any(row['kind'] == 'import_call' and int(row['target'], 16) == slot
                   for row in project.xrefs(call_site, direction='from', version=1))
        assert raw_import(project, 'memcpy', version=1)['stub_addresses'] == [stub]


def test_dependency_name_patch_rebuilds_versioned_modules_without_ghosts(linux_call_files, tmp_path):
    fixture = linux_call_files['got']
    with Project.create(tmp_path / 'header.fdb', fixture['path']) as project:
        run(project)
        document = project._document(1)
        source = fixture['path'].read_bytes()
        offset = source.index(b'libc.so.6\0')
        mapping = next(item for item in document['file_mappings'] if item['file_offset'] <= offset < item['file_offset'] + item['file_size'])
        address = mapping['virtual_address'] + offset - mapping['file_offset']
        project.patch(address, b'libx.so.6'.hex(), label='change declared loader dependency')
        assert {row['name'] for row in project.information('libraries')['items']} == {'libx.so.6'}
        assert raw_import(project, 'memcpy')['required_module'] == 'libx.so.6'
        assert not project.db.execute("SELECT 1 FROM symbols WHERE version=2 AND module='libc.so.6'").fetchone()
        run(project)
        assert next(item for item in project.calls(kind='library')['items'] if item['function'] == 'memcpy')['module'] == 'libx.so.6'
        assert raw_import(project, 'memcpy', version=1)['module'] == 'libc.so.6'
        assert {row['name'] for row in project.information('libraries', version=1)['items']} == {'libc.so.6'}


def test_import_name_patch_replaces_old_symbol_alias_and_contract(linux_call_files, tmp_path):
    fixture = linux_call_files['plt']
    with Project.create(tmp_path / 'name.fdb', fixture['path']) as project:
        run(project)
        original = raw_import(project, 'memcpy')
        source = fixture['path'].read_bytes()
        offset = source.index(b'memcpy\0')
        mapping = next(item for item in project._document(1)['file_mappings']
                       if item['file_offset'] <= offset < item['file_offset'] + item['file_size'])
        address = mapping['virtual_address'] + offset - mapping['file_offset']
        project.patch(address, b'memcmp'.hex(), label='change declared imported symbol')
        assert not any(item['name'] == 'memcpy' for item in project._document(2)['imports'])
        assert not project.db.execute("SELECT 1 FROM symbols WHERE version=2 AND name='memcpy'").fetchone()
        assert raw_import(project, 'memcmp')['address'] == original['address']
        run(project)
        functions = {item['function'] for item in project.calls(kind='library')['items']}
        assert 'memcmp' in functions and 'memcpy' not in functions
        assert not any(item['summary_name'] == 'memcpy' for item in project.call_effects()['items'])
        assert any(item['summary_name'] == 'memset' for item in project.call_effects()['items'])
        assert raw_import(project, 'memcpy', version=1)['stub_addresses'] == original['stub_addresses']
        assert any(item['summary_name'] == 'memcpy' for item in project.call_effects(version=1)['items'])


def test_public_linkage_json_methods_and_refresh_return_structured_results(linux_call_files, tmp_path):
    fixture = linux_call_files['plt']
    with Project.create(tmp_path / 'methods.fdb', fixture['path']) as project:
        path = str(project.path)
    for method in ('libraries', 'relocations', 'linkage', 'refresh-metadata'):
        response = respond(dict(id=method, method=method, params=dict(project=path)))
        assert response['ok'], response
        assert response['id'] == method
