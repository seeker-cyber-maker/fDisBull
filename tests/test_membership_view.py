"""Project membership queries retain stored contexts and bounded coverage."""
import struct

import pytest

from fdisbull.membership_view import MembershipMixin
from fdisbull.project import Project


def _raw(tmp_path, data):
    source = tmp_path / 'members.bin'
    source.write_bytes(data)
    return Project.create(tmp_path / 'members.fdb', source, arch='x86', base=0x1000)


def _query(project, **options):
    return MembershipMixin.function_membership(project, **options)


def test_stored_shared_tail_and_interior_entries_are_read_only_and_named(tmp_path):
    data = bytearray(b'\xcc' * 0x20)
    data[:2], data[4:6], data[0x10:0x16] = bytes.fromhex('eb0e'), bytes.fromhex('eb0a'), bytes.fromhex('b801000000c3')
    with _raw(tmp_path, data) as project:
        project.analyze()
        project.analyze(start=0x1004)
        project.db.execute('INSERT OR IGNORE INTO functions(version,context,address,name,source) VALUES (?,?,?,?,?)',
                           (1, project.context, '0000000000001010', 'tail_candidate', 'test exact stored entry'))
        project.annotate(0x1010, 'shared_tail_name', kind='name')
        before = project.db.total_changes
        result = _query(project)
        assert project.db.total_changes == before
    assert result['complete'] and not result['input_truncated']
    assert result['resolved_entry_count'] == 3
    named = next(item for item in result['functions'] if item['address'] == '0x1010')
    assert named['name'] == 'shared_tail_name'
    shared = next(item for item in result['shared_tails'] if named['entry'] in item['instruction_ids'])
    assert len(shared['candidate_entries']) == 3
    assert any(item['entry'] == named['entry'] and len(item['reachable_from']) == 2 for item in result['overlapping_entries'])


def _mz(module, relocations):
    header = bytearray(64)
    size = len(header) + len(module)
    struct.pack_into('<14H', header, 0, 0x5A4D, size % 512, (size + 511) // 512,
                     len(relocations), 4, 0, 0xFFFF, 0, 0, 0, 0, 0, 28, 0)
    for index, offset in enumerate(relocations):
        struct.pack_into('<HH', header, 28 + index * 4, offset, 0)
    return bytes(header) + bytes(module)


def test_dos_far_edges_and_same_physical_address_keep_exact_cs_contexts(tmp_path):
    module = bytearray(96)
    module[:5], module[0x40] = bytes.fromhex('ea00000400'), 0xCB
    source = tmp_path / 'members.exe'
    source.write_bytes(_mz(module, [3]))
    with Project.create(tmp_path / 'dos.fdb', source) as project:
        project.analyze()
        project.analyze(start='1003:0010')
        result = _query(project)
    aliases = [item for item in result['instruction_membership'] if item['address'] == '0x10040']
    assert len(aliases) == 2
    assert {item['context'] for item in aliases} == {'x86:16:little:cs=1003', 'x86:16:little:cs=1004'}
    entry = next(item for item in result['functions'] if item['address'] == '0x10000')
    assert any('cs=1004' in identity for identity in entry['instruction_ids'])
    assert not any('cs=1003' in identity for identity in entry['instruction_ids'])


def test_reconstructed_fallthrough_and_resolved_branch_keep_provenance(tmp_path):
    with _raw(tmp_path, bytes.fromhex('90ffe0c3')) as project:
        project.analyze()
        project.analyze(start=0x1003)
        project.db.execute("DELETE FROM xrefs WHERE kind='fallthrough'")
        project.db.execute('INSERT INTO xrefs VALUES (?,?,?,?,?,?)',
                           (1, project.context, '0000000000001001', '0000000000001003', 'resolved_branch', 'generic flow resolution'))
        result = _query(project)
    first = next(item for item in result['functions'] if item['address'] == '0x1000')
    assert first['instruction_count'] == 3
    assert result['reconstructed_fallthrough_count'] == 1
    assert result['tail_call_candidates'][0]['evidence'] == 'generic flow resolution'


def test_input_cap_cannot_report_complete_even_when_loaded_slice_returns(tmp_path):
    with _raw(tmp_path, bytes.fromhex('c3ccc3')) as project:
        project.analyze()
        project.analyze(start=0x1002)
        result = _query(project, max_instructions=1)
    assert result['instruction_count'] == 1 and result['stored_instruction_count'] == 2
    assert result['input_truncated'] and not result['complete'] and not result['traversal_exhausted']
    assert result['truncation']['instructions'] == result['truncation']['candidate_entries'] == 1
    assert not result['functions'][0]['complete']
    assert any(item['reason'] == 'input_instructions_limit' for item in result['frontier'])


def test_calls_are_excluded_and_old_version_query_is_isolated(tmp_path):
    data = bytearray(b'\xcc' * 0x21)
    data[:6], data[0x20] = bytes.fromhex('e81b000000c3'), 0xC3
    with _raw(tmp_path, data) as project:
        project.analyze()
        original = _query(project)
        first = next(item for item in original['functions'] if item['address'] == '0x1000')
        assert first['instruction_count'] == 2 and original['excluded_call_edges']
        assert not any(identity.endswith('@0x1020') for identity in first['instruction_ids'])
        project.patch(0x1000, 'c3')
        project.analyze()
        current, old = _query(project), _query(project, version=1)
        assert next(item for item in current['functions'] if item['address'] == '0x1000')['instruction_count'] == 1
        assert next(item for item in old['functions'] if item['address'] == '0x1000')['instruction_count'] == 2
        for options in ({'max_instructions': 0}, {'max_instructions': True}, {'max_work': 0}):
            with pytest.raises(ValueError):
                _query(project, **options)
