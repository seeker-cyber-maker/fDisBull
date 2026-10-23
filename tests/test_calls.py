"""Call views identify stored targets and preserve ambiguous static evidence."""
import struct

import pytest

from fdisbull.cli import respond
from fdisbull.project import Project
from test_inspection import pe_import_fixture


def _raw_project(tmp_path, data):
    path = tmp_path / 'calls.bin'
    path.write_bytes(data)
    return Project.create(tmp_path / 'calls.fdb', path, arch='x86', base=0x1000)


def _two_direct_calls():
    raw = bytearray(b'\xCC' * 0x11)
    raw[:11] = bytes.fromhex('e80b000000e806000000c3')
    raw[0x10] = 0xC3
    return bytes(raw)


def test_direct_calls_group_incoming_sites_and_shared_rename(tmp_path):
    with _raw_project(tmp_path, _two_direct_calls()) as project:
        assert project.analyze()['stable']
        before = project.db.total_changes
        result = project.calls()
        assert result['total'] == 1 and result['total_call_sites'] == 2
        target = result['items'][0]
        assert target['kind'] == 'function' and target['target'] == '0x1010'
        assert target['call_site_count'] == 2
        assert [site['address'] for site in target['call_sites']] == ['0x1000', '0x1005']
        assert all(site['raw_operands'] and site['evidence'] for site in target['call_sites'])
        assert not target['runtime_observed'] and not target['function_boundary_proven']
        assert project.db.total_changes == before
        project.annotate(0x1010, 'useful_function', kind='name')
        assert project.calls()['items'][0]['name'] == 'useful_function'
        assert project.calls()['items'][0]['function'] == 'useful_function'
        response = respond({'method': 'calls', 'params': {'project': str(project.path), 'kind': 'function'}})
        assert response['ok'] and response['result']['items'][0]['name'] == 'useful_function'


def test_resolved_memory_call_remains_static_pointer_evidence(tmp_path):
    raw = bytearray(0x30)
    raw[:7] = bytes.fromhex('ff150a000000c3')
    struct.pack_into('<Q', raw, 0x10, 0x1020)
    raw[0x20] = 0xC3
    with _raw_project(tmp_path, raw) as project:
        project.analyze()
        target = project.calls()['items'][0]
        assert target['target'] == '0x1020' and target['kind'] == 'function'
        site = target['call_sites'][0]
        assert site['flow'] == 'indirect_call'
        assert site['resolved_targets'][0]['kind'] == 'resolved_call'
        assert site['memory_operands'][0]['address'] == '0x1010'
        assert not target['runtime_observed']


def test_unresolved_indirect_calls_stay_separate_by_source(tmp_path):
    with _raw_project(tmp_path, bytes.fromhex('ffd0ffd1c3')) as project:
        project.analyze()
        result = project.calls(kind='unresolved')
        assert result['total'] == 2 and result['total_call_sites'] == 2
        assert {item['call_sites'][0]['address'] for item in result['items']} == {'0x1000', '0x1002'}
        assert all(item['target'] is None and item['function'] is None and item['module'] is None for item in result['items'])
        assert project.calls(kind='library')['items'] == []


@pytest.mark.parametrize('ordinal', [None, 123])
def test_actual_pe_import_slot_calls_preserve_library_identity(tmp_path, ordinal):
    data = bytearray(pe_import_fixture())
    data[0x200:0x207] = bytes.fromhex('ff15ca010000c3')
    if ordinal is not None:
        struct.pack_into('<QQ', data, 0x3C0, (1 << 63) | ordinal, 0)
        struct.pack_into('<QQ', data, 0x3D0, (1 << 63) | ordinal, 0)
    path = tmp_path / 'import.exe'
    path.write_bytes(data)
    with Project.create(tmp_path / 'imports.fdb', path) as project:
        assert project.analyze()['stable']
        result = project.calls(kind='library')
        assert result['total'] == 1
        imported = result['items'][0]
        assert imported['target'] == '0x1400011d0' and imported['target_kind'] == 'import_slot'
        assert imported['library'] == imported['module'] == 'KERNEL32.dll'
        assert imported['function'] == ('Sleep' if ordinal is None else None)
        assert imported['ordinal'] == ordinal
        assert imported['call_site_count'] == 1 and imported['call_sites'][0]['address'] == '0x140001000'
        project.annotate(0x1400011D0, 'custom_import_label', kind='name')
        renamed = project.calls(kind='library')['items'][0]
        assert renamed['name'] == 'custom_import_label' and renamed['module'] == 'KERNEL32.dll'


def test_recovered_import_aliases_are_not_arbitrarily_selected_or_double_counted(tmp_path):
    raw = bytearray(0x30)
    raw[:7] = bytes.fromhex('ff150a000000c3')
    struct.pack_into('<Q', raw, 0x10, 0x1020)
    raw[0x20] = 0xC3
    with _raw_project(tmp_path, raw) as project:
        project.analyze()
        project.recover_imports(module_exports=[
            {'address': 0x1020, 'module': 'test.dll', 'name': 'A', 'ordinal': 1},
            {'address': 0x1020, 'module': 'test.dll', 'name': 'AliasA', 'ordinal': 2},
        ], candidate_slots=[0x1010], max_slots=1)
        result = project.calls()
        assert result['total'] == result['total_call_sites'] == 1
        target = result['items'][0]
        assert target['kind'] == 'library' and target['target'] == '0x1010'
        assert target['function'] == 'A|AliasA' and target['ordinal'] is None
        assert len(target['aliases']) == 2
        assert target['call_sites'][0]['resolved_targets'][0]['target'] == '0x1020'


def _alias_callees_mz():
    module = bytearray(128)
    module[:11] = bytes.fromhex('9a000004009a10000300c3')
    module[0x40] = 0xCB
    size = 64 + len(module)
    header = bytearray(64)
    struct.pack_into('<14H', header, 0, 0x5A4D, size % 512, (size + 511) // 512,
                     2, 4, 0, 0xFFFF, 0, 32, 0, 0, 0, 28, 0)
    struct.pack_into('<HHHH', header, 28, 3, 0, 8, 0)
    return bytes(header) + bytes(module)


def test_dos_call_targets_preserve_cs_aliases_without_invented_libraries(tmp_path):
    path = tmp_path / 'aliases.exe'
    path.write_bytes(_alias_callees_mz())
    with Project.create(tmp_path / 'aliases.fdb', path) as project:
        assert project.analyze()['stable']
        project.annotate('1004:0000', 'shared_static_helper', kind='name')
        result = project.calls()
        assert result['total'] == 2 and result['total_call_sites'] == 2
        assert {item['target'] for item in result['items']} == {'0x10040'}
        assert {item['target_segmented_address'] for item in result['items']} == {'1004:0000', '1003:0010'}
        assert {item['target_context'] for item in result['items']} == {'x86:16:little:cs=1004', 'x86:16:little:cs=1003'}
        assert all(item['name'] == 'shared_static_helper' and item['module'] is None and item['kind'] == 'function' for item in result['items'])
        assert {item['call_sites'][0]['segmented_address'] for item in result['items']} == {'1000:0000', '1000:0005'}
        page = project.calls(limit=1, offset=1)
        assert len(page['items']) == 1 and not page['has_more']


def test_call_site_payload_is_bounded_but_count_is_complete(tmp_path):
    count = 101
    target = count * 5 + 1
    raw = bytearray(target + 1)
    for index in range(count):
        address = index * 5
        raw[address:address + 5] = b'\xe8' + struct.pack('<i', target - address - 5)
    raw[count * 5] = raw[target] = 0xC3
    with _raw_project(tmp_path, raw) as project:
        assert project.analyze()['stable']
        result = project.calls()
        group = result['items'][0]
        assert result['total_call_sites'] == group['call_site_count'] == count
        assert len(group['call_sites']) == result['call_site_limit'] == 100
        assert group['call_sites_truncated']


def test_call_views_preserve_old_versions_and_reject_invalid_options(tmp_path):
    with _raw_project(tmp_path, _two_direct_calls()) as project:
        project.analyze()
        old = project.calls()['items']
        project.patch(0x1000, 'c3')
        project.analyze()
        assert project.calls()['items'] == []
        assert project.calls(version=1)['items'] == old
        for options in ({'kind': 'branch'}, {'limit': True}, {'offset': -1}):
            with pytest.raises(ValueError):
                project.calls(**options)
