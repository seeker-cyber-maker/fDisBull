"""Regression evidence for qualified contracts, orphaned jobs and binding history."""
import json
import struct

import pytest

from fdisbull.linkage import import_call_bindings
from fdisbull.project import Project
from test_advanced_formats import _elf64
from test_inspection import pe_import_fixture


def _raw_caller(tmp_path, imports):
    data = bytearray(0x200)
    data[:27] = bytes.fromhex('48bf4011000000000000be2a000000ba08000000ff1566000000c3')
    struct.pack_into('<Q', data, 0x80, 0x5000)
    source = tmp_path / 'caller.bin'
    source.write_bytes(data)
    project = Project.create(tmp_path / 'caller.fdb', source, arch='x86', base=0x1000)
    with project.transaction(True):
        document = project._document(1)
        document['imports'] = [dict(address=0x1080, module='declared.dll', callable=True, kind='got',
                                    pointer_width=8, binding_state='runtime_unresolved', **item) for item in imports]
        project.db.execute('UPDATE binary_info SET document=? WHERE version=1', (json.dumps(document),))
        project._index_symbols(1, document)
    return project


def _analyze(project):
    result = project.auto_analyze(abi='x86_64_sysv', max_rounds=8)
    assert result['stable'] and not result['budget_exhausted']


@pytest.mark.parametrize('recovered', ['opaque_target', 'memset'])
def test_recovered_import_identity_overrides_original_contract_in_public_effects(tmp_path, recovered):
    with _raw_caller(tmp_path, [dict(name='memcpy')]) as project:
        project.recover_imports(module_exports=[dict(address=0x5000, module='recovered.dll', name=recovered)],
                                candidate_slots=[0x1080], max_slots=1)
        _analyze(project)
        group, = project.calls(kind='library')['items']
        assert group['function'] == recovered and group['module'] == 'recovered.dll'
        effects = project.call_effects()['items']
        assert not any(item['summary_name'] == 'memcpy' for item in effects)
        if recovered == 'opaque_target':
            assert effects == []
        else:
            effect, = effects
            assert (effect['summary_name'], effect['address'], effect['size']) == ('memset', 0x1140, 8)
            assert effect['summary_source']['module'] == 'recovered.dll'


@pytest.mark.parametrize('competing', ['opaque_alias', 'memcpy'])
def test_every_competing_declared_slot_alias_must_support_the_same_contract(tmp_path, competing):
    with _raw_caller(tmp_path, [dict(name='memset'), dict(name=competing)]) as project:
        _analyze(project)
        assert project._summary_at(1, project.context, 0x1080) is None
        assert project.call_effects()['items'] == []
        aliases = project.calls(kind='library')['items'][0]['aliases']
        assert {item['name'] for item in aliases} == {'memset', competing}


def test_unknown_competing_recovered_alias_does_not_inherit_known_original_contract(tmp_path):
    with _raw_caller(tmp_path, [dict(name='memset')]) as project:
        project.recover_imports(module_exports=[dict(address=0x5000, module='recovered.dll', name='memset'),
                                                dict(address=0x5000, module='recovered.dll', name='opaque_alias')],
                                candidate_slots=[0x1080], max_slots=1)
        _analyze(project)
        assert project._summary_at(1, project.context, 0x1080) is None
        assert project.call_effects()['items'] == []
        assert len(project.calls(kind='library')['items'][0]['aliases']) == 2


@pytest.mark.parametrize('versioned', [False, True], ids=['plain-name', 'elf-versioned-name'])
def test_recovered_ordinal_only_alternative_cannot_inherit_combined_display_label(tmp_path, versioned):
    if versioned:
        entry, slot, destination = 0x400100, 0x400170, 0x400180
        code = bytearray(b'\x48\xbf' + struct.pack('<Q', destination) + b'\xbe\x2a\0\0\0\xba\x08\0\0\0')
        code += b'\xff\x15' + struct.pack('<i', slot - (entry + len(code) + 6)) + b'\xc3'
        data = bytearray(_elf64(code))
        struct.pack_into('<Q', data, slot - 0x400000, 0x5000)
        source = tmp_path / 'ordinal-alias.elf'
        source.write_bytes(data)
        project = Project.create(tmp_path / 'ordinal-alias.fdb', source)
        name = 'memcpy@GLIBC_2.14'
    else:
        project, slot, name = _raw_caller(tmp_path, [dict(name='memcpy')]), 0x1080, 'memcpy'
    with project:
        project.recover_imports(module_exports=[dict(address=0x5000, module='recovered.dll', name=name),
                                                dict(address=0x5000, module='recovered.dll', name=None, ordinal=7)],
                                candidate_slots=[slot], max_slots=1)
        row = project.db.execute("SELECT name,detail FROM symbols WHERE kind='recovered_import'").fetchone()
        assert row['name'] == name + '|ordinal_7'
        assert any(item['name'] is None and item['ordinal'] == 7 for item in json.loads(row['detail'])['alternatives'])
        assert project._summary_at(1, project.context, slot) is None
        _analyze(project)
        assert project.call_effects()['items'] == []


@pytest.mark.parametrize('identity', [dict(name='memset', addend=4), dict(name='memset', callable=False)])
def test_nonentry_addend_or_data_identity_cannot_supply_a_c_contract(tmp_path, identity):
    # Explicitly replace callable rather than pass duplicate keyword fields.
    callable_ = identity.get('callable', True)
    attributes = {key: value for key, value in identity.items() if key != 'callable'}
    with _raw_caller(tmp_path, [attributes]) as project:
        if not callable_:
            with project.transaction(True):
                row = project.db.execute("SELECT detail FROM symbols WHERE kind='imports'").fetchone()
                detail = dict(json.loads(row[0]), callable=False)
                project.db.execute("UPDATE symbols SET detail=? WHERE kind='imports'", (json.dumps(detail),))
        _analyze(project)
        assert project._summary_at(1, project.context, 0x1080) is None
        assert project.call_effects()['items'] == []


@pytest.mark.parametrize('taint', ['unchanged', 'unknown_write', 'overlap'])
def test_import_identity_remains_metadata_only_with_explicit_binding_history(taint):
    node = dict(id='call', context='native', address='0x1000', flow='indirect_call')
    expression = dict(op='load', address=dict(op='const', value=0x3000), width=8, signed=False)
    state = dict(registers={}, memory_tainted=taint == 'unknown_write', memory_writes=[])
    if taint == 'overlap':
        state['memory_writes'] = [dict(address=dict(op='const', value=0x3004), width=1)]
    binding, = import_call_bindings(dict(nodes=[node]), {'call': dict(indirect_target=expression)},
                                    dict(stable=True, in_states={'call': state}),
                                    [dict(name='memset', address=0x3000, module='fixture')], 8)
    assert binding['identity_basis'] == 'declared_import_metadata'
    assert binding['binding_unchanged_under_static_state'] is (taint == 'unchanged')
    assert binding['contract_condition'] and binding['external_target'] is None
    assert not binding['runtime_observed']


def test_direct_stub_without_flow_proof_keeps_binding_history_unknown():
    node = dict(id='call', context='native', address='0x1000', flow='call')
    graph = dict(nodes=[node], calls=[dict(source='call', target_address='0x2000')])
    binding, = import_call_bindings(graph, {}, dict(stable=False),
                                    [dict(name='memset', address=0x3000, stub_addresses=[0x2000])], 8)
    assert binding['identity_basis'] == 'declared_import_metadata'
    assert binding['binding_unchanged_under_static_state'] is None
    assert binding['contract_condition'] and binding['external_target'] is None


def _pe_caller(tmp_path, mutate=False):
    data = bytearray(pe_import_fixture())
    struct.pack_into('<II', data, 0x98 + 112, 0, 0)  # Remove the unrelated helper export.
    name = data.index(b'Sleep\0')
    data[name:name + 7] = b'memset\0'
    entry, slot, destination = 0x140001000, 0x1400011D0, 0x140001080
    code = bytearray(b'\x48\xb9' + struct.pack('<Q', destination) + b'\xba\x2a\0\0\0\x41\xb8\x08\0\0\0')
    if mutate:
        code += b'\x48\x83\x35' + struct.pack('<i', slot - (entry + len(code) + 8)) + b'\x01'  # XOR QWORD[IAT],1.
    code += b'\xff\x15' + struct.pack('<i', slot - (entry + len(code) + 6)) + b'\xc3'
    data[0x200:0x200 + len(code)] = code
    data[0x270] = 0xC3
    source = tmp_path / 'conditional.exe'
    source.write_bytes(data)
    return source, entry, slot, destination


@pytest.mark.parametrize('mutate', [False, True])
def test_native_public_import_effects_retain_binding_evidence_across_restart(tmp_path, mutate):
    source, entry, slot, destination = _pe_caller(tmp_path, mutate)
    database = tmp_path / 'conditional.fdb'
    with Project.create(database, source) as project:
        assert project.auto_analyze()['stable']
        effect, = project.call_effects(destination, access='write', include_unresolved=False)['items']
        assert (effect['summary_name'], effect['address'], effect['size']) == ('memset', destination, 8)
        evidence, = effect['binding_evidence']
        assert evidence['slot'] == slot and evidence['identity_basis'] == 'declared_import_metadata'
        assert evidence['binding_unchanged_under_static_state'] is (not mutate)
        assert evidence['contract_condition'] and any('unchanged' in condition for condition in effect['conditions'])
        assert not evidence['runtime_observed'] and evidence['external_target'] is None
        assert project.function_analysis(entry)['result']['import_calls'][0] == evidence
    source.unlink()
    with Project(database) as project:
        assert project.call_effects(destination, access='write', include_unresolved=False)['items'] == [effect]


def test_metadata_refresh_preserves_orphans_until_explicit_candidate_restoration(tmp_path):
    source, entry, _, _ = _pe_caller(tmp_path)
    orphan, database = entry + 0x70, tmp_path / 'orphans.fdb'
    with Project.create(database, source) as project:
        assert project.auto_analyze(start=orphan)['stable']
        key = f'{orphan:016x}'
        original_generation = project.function_analysis(orphan)['generation']
        with project.transaction(True):
            project.db.execute('DELETE FROM functions WHERE version=1 AND context=? AND address=?', (project.context, key))
            project.db.execute("UPDATE advanced_jobs SET state='orphaned',reason='supporting call retracted' WHERE version=1 AND context=? AND address=?", (project.context, key))
            project._derived_dependency(1, project.context, orphan, 'call', entry, dependency_context=project.context)
        versions, raw = project.versions(), bytes(project.db.execute('SELECT source_bytes FROM binary_info WHERE version=1').fetchone()[0])
        source.unlink()
        project.refresh_metadata()
        cached = project.function_analysis(orphan)
        assert cached['state'] == 'orphaned' and cached['generation'] == original_generation
        assert project.versions() == versions
        assert bytes(project.db.execute('SELECT source_bytes FROM binary_info WHERE version=1').fetchone()[0]) == raw
        receipt = project.auto_analyze()
        assert receipt['stable'] and all(job['address'] != hex(orphan) for job in receipt['jobs'])
        assert project.function_analysis(orphan)['state'] == 'orphaned'
        assert project.auto_analyze(start=orphan)['stable']
        restored = project.function_analysis(orphan)
        assert restored['state'] == 'done' and restored['generation'] > original_generation
    with Project(database) as reopened:
        assert reopened.function_analysis(orphan)['state'] == 'done'
