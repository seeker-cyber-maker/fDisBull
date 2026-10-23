"""A CFG is a reachable stored slice, with explicit gaps and assumptions."""
import struct

import pytest

from fdisbull.cfg import CFGMixin
from fdisbull.cli import respond
from fdisbull.project import Project


def _cfg(project, *args, **kwargs):
    # Keep the new module testable before the coordinator wires its mixin.
    return CFGMixin.cfg(project, *args, **kwargs)


def _raw(tmp_path, data):
    source = tmp_path / 'cfg.bin'
    source.write_bytes(data)
    return Project.create(tmp_path / 'cfg.fdb', source, arch='x86', base=0x1000)


def _loop_calls():
    data = bytearray(b'\xcc' * 0x21)
    data[:17] = bytes.fromhex('31c083f8027d09e814000000ffc0ebf2c3')
    data[0x20] = 0xC3
    return data


def test_cfg_follows_loops_and_call_continuation_not_callee_or_labels(tmp_path):
    with _raw(tmp_path, _loop_calls()) as project:
        assert project.analyze()['stable']
        project.annotate(0x100C, 'interior_label', kind='name')
        project.db.execute('INSERT INTO functions(version,context,address,name,source) VALUES (?,?,?,?,?)',
                           (1, project.context, '000000000000100c', 'candidate_interior', 'test'))
        before = project.db.total_changes
        result = _cfg(project, 0x1000, highlights=[0x100C, 0x1010, 0x1020])
        assert project.db.total_changes == before
        assert result['instruction_count'] == 7 and result['graph_closed']
        assert not result['function_boundary_proven'] and result['status'] == 'candidate'
        assert {node['address'] for node in result['nodes']} == {'0x1000', '0x1002', '0x1005', '0x1007', '0x100c', '0x100e', '0x1010'}
        assert result['calls'][0]['target_address'] == '0x1020'
        assert result['calls'][0]['resolved']
        back = next(edge for edge in result['edges'] if edge['source_address'] == '0x100e')
        assert back['target_address'] == '0x1002' and back['provenance'] == 'stored'
        assert any(edge['id'] == back['id'] for edge in result['block_edges'])
        branch = next(edge for edge in result['edges'] if edge['source_address'] == '0x1005' and edge['kind'] == 'branch')
        assert branch['predicate'] == dict(mnemonic='jge', operands='short 0000000000001010h', outcome='taken', truth_evaluated=False)
        assert [item['reachable'] for item in result['highlights']] == [True, True, False]
        match = result['highlights'][0]['matches'][0]
        assert match['path'][-1]['address'] == '0x100c' and match['assumed_call_returns'] == 1
        assert all(edge['evidence'] and edge['source_address'] and edge['target_address'] for edge in match['path_edges'])
        assert next(node for node in result['nodes'] if node['address'] == '0x100c')['name'] == 'interior_label'
        assert sum(block['instruction_count'] for block in result['basic_blocks']) == 7
        response = respond({'method': 'cfg', 'params': {'project': str(project.path), 'address': 0x1000,
                                                        'highlights': [{'address': 0x100C, 'label': 'interior'}]}})
        assert response['ok'] and response['result']['instruction_count'] == 7
        assert response['result']['highlights'][0]['reachable']


def test_cfg_reconstructs_missing_fallthrough_and_deduplicates_stored_edges(tmp_path):
    with _raw(tmp_path, bytes.fromhex('9090c3')) as project:
        project.analyze()
        project.db.execute("DELETE FROM xrefs WHERE kind='fallthrough'")
        reconstructed = _cfg(project, 0x1000)
        assert reconstructed['graph_closed'] and len(reconstructed['edges']) == 2
        assert all(edge['provenance'] == 'reconstructed' for edge in reconstructed['edges'])
        project.db.execute('INSERT INTO xrefs VALUES (?,?,?,?,?,?)',
                           (1, project.context, '0000000000001000', '0000000000001001', 'fallthrough', 'persisted native fallthrough'))
        stored = _cfg(project, 0x1000)
        assert len(stored['edges']) == 2
        assert stored['edges'][0]['provenance'] == 'stored'
        assert stored['edges'][0]['evidence'] == 'persisted native fallthrough'


def test_cfg_budget_and_missing_entry_are_explicit_without_nearest_instruction(tmp_path):
    with _raw(tmp_path, _loop_calls()) as project:
        project.analyze()
        result = _cfg(project, 0x1000, max_instructions=1, highlights=[0x100C])
        assert result['instruction_count'] == 1 and result['budget_exhausted']
        assert not result['graph_closed'] and not result['traversal_exhausted']
        assert result['frontier'][0]['address'] == '0x1002'
        assert not result['highlights'][0]['reachable']
        absent = _cfg(project, 0x1001)
        assert absent['instruction_count'] == 0 and not absent['graph_closed']
        assert absent['gaps'][0]['address'] == '0x1001'


def test_cfg_unknown_indirect_jump_stops_but_unknown_call_has_assumed_continuation(tmp_path):
    with _raw(tmp_path, bytes.fromhex('ffd0ffe0c3')) as project:
        project.analyze()
        result = _cfg(project, 0x1000)
        assert result['instruction_count'] == 2 and not result['graph_closed']
        assert {item['kind'] for item in result['unresolved']} == {'call', 'branch'}
        assert result['calls'][0]['target'] is None
        assert len(result['edges']) == 1 and result['edges'][0]['assumed_return']


def test_cfg_missing_direct_branch_xref_is_an_honest_gap(tmp_path):
    with _raw(tmp_path, bytes.fromhex('eb00c3')) as project:
        project.analyze()
        project.db.execute("DELETE FROM xrefs WHERE kind='branch'")
        result = _cfg(project, 0x1000)
        assert result['instruction_count'] == 1 and not result['graph_closed']
        assert result['unresolved'][0]['reason'] == 'no_stored_branch_target'


def _mz(module, ip=0, relocations=()):
    header_size = max(64, (28 + len(relocations) * 4 + 15) // 16 * 16)
    header = bytearray(header_size)
    size = header_size + len(module)
    struct.pack_into('<14H', header, 0, 0x5A4D, size % 512, (size + 511) // 512,
                     len(relocations), header_size // 16, 0, 0xFFFF, 0, 0, 0, ip, 0, 28, 0)
    for index, offset in enumerate(relocations):
        struct.pack_into('<HH', header, 28 + index * 4, offset, 0)
    return bytes(header) + bytes(module)


def test_cfg_dos_reconstructed_fallthrough_wraps_ip_within_same_cs(tmp_path):
    module = bytearray(65536)
    module[0] = 0xCB
    module[-2:] = b'\x90\x90'
    source = tmp_path / 'wrap.exe'
    source.write_bytes(_mz(module, ip=0xFFFE))
    with Project.create(tmp_path / 'wrap.fdb', source) as project:
        assert project.analyze()['stable']
        project.db.execute("DELETE FROM dos_edges WHERE kind='fallthrough'")
        result = _cfg(project, '1000:fffe', highlights=['1000:0000'])
        assert result['graph_closed'] and result['instruction_count'] == 3
        assert {node['segmented_address'] for node in result['nodes']} == {'1000:fffe', '1000:ffff', '1000:0000'}
        wrap = next(edge for edge in result['edges'] if edge['source_segmented_address'] == '1000:ffff')
        assert wrap['target_segmented_address'] == '1000:0000' and wrap['provenance'] == 'reconstructed'
        assert result['highlights'][0]['reachable']


def test_cfg_dos_far_jump_preserves_aliases_and_requires_unambiguous_entry(tmp_path):
    module = bytearray(128)
    module[:5] = bytes.fromhex('ea00000400')
    module[0x40] = 0xCB
    source = tmp_path / 'aliases.exe'
    source.write_bytes(_mz(module, relocations=[3]))
    with Project.create(tmp_path / 'aliases.fdb', source) as project:
        project.analyze()
        project.analyze(start='1003:0010')
        with pytest.raises(ValueError, match='multiple stored CS'):
            _cfg(project, 0x10040)
        result = _cfg(project, '1000:0000', highlights=[0x10040, '1003:0010', '1004:0000'])
        assert result['instruction_count'] == 2 and result['graph_closed']
        assert result['edges'][0]['target_context'] == 'x86:16:little:cs=1004'
        assert [item['reachable'] for item in result['highlights']] == [True, False, True]
        assert _cfg(project, 0x10040, cs='1003')['instruction_count'] == 1


def test_cfg_shared_references_old_version_and_input_validation(tmp_path):
    raw = bytearray(0x21)
    raw[:8] = bytes.fromhex('488b0519000000c3')
    with _raw(tmp_path, raw) as project:
        project.analyze()
        project.annotate(0x1020, 'shared_field', kind='name')
        result = _cfg(project, 0x1000, highlights=[{'address': 0x1001, 'label': 'inside load'}])
        assert 'shared_field' in result['nodes'][0]['display_operands']
        assert result['highlights'][0]['matches'][0]['byte_offset'] == 1
        project.patch(0x1000, 'c3')
        project.analyze()
        assert _cfg(project, 0x1000)['instruction_count'] == 1
        assert _cfg(project, 0x1000, version=1)['instruction_count'] == 2
        for options in ({'max_instructions': True}, {'max_instructions': 0}, {'cs': '1000'},
                        {'highlights': '0x1000'}, {'highlights': [{}]}, {'highlights': [{'address': 0x1000, 'label': 1}]}):
            with pytest.raises(ValueError):
                _cfg(project, 0x1000, **options)
