"""User structural interpretations share labels while bytes/versions stay intact."""
import struct

import pytest

from fdisbull.project import Project


def _project(tmp_path):
    raw = bytearray(0x100)
    raw[:7] = bytes.fromhex('8b053e000000c3')  # MOV EAX,[1044h]; RET.
    struct.pack_into('<HhIQ', raw, 0x40, 3, -4, 9, 0x1050)
    struct.pack_into('<HhIQ', raw, 0x50, 7, -8, 11, 0)
    source = tmp_path / 'types.bin'
    source.write_bytes(raw)
    return Project.create(tmp_path / 'types.fdb', source, arch='x86', base=0x1000)


def _record(project, field='count'):
    fields = [dict(name='flags', offset=0, type='u16'), dict(name='delta', offset=2, type='i16'),
              dict(name=field, offset=4, type='u32'), dict(name='next', offset=8, type='RecordPointer')]
    existing = {item['layout']['name'] for item in project.types()['types']}
    if 'Record' not in existing:
        project.define_type('Record', dict(kind='struct', size=16, fields=[]))
        project.define_type('RecordPointer', dict(kind='pointer', size=8, target='Record'))
    project.define_type('Record', dict(kind='struct', size=16, fields=fields))
    if 'Records' not in existing:
        project.define_type('Records', dict(kind='array', element='Record', count=2))


def test_struct_arrays_pointer_signed_values_and_read_only_shared_labels(tmp_path):
    with _project(tmp_path) as project:
        project.analyze()
        original = project.regions(1)[0].data
        _record(project)
        project.apply_type(0x1040, 'Records', name='ledger', author='analyst')
        before = project.db.total_changes
        typed = project.typed_data(0x1040)
        assert project.db.total_changes == before
        assert [item['value'] for item in typed['items'][:4]] == [3, -4, 9, 0x1050]
        assert typed['items'][3]['target'] == '0x1050' and typed['items'][3]['target_mapped']
        assert typed['items'][0]['path'] == 'ledger[0].flags'
        assert typed['items'][4]['path'] == 'ledger[1].flags'
        assert 'ledger[0].count' in project.disassembly(0x1000)['instructions'][0]['display_operands']
        assert project.regions(1)[0].data == original
        byte = project.locate(0x1045)
        assert byte['presentation']['name'] == 'ledger[0].count+0x1'
        assert byte['data'][0]['byte_offset'] == 1


def test_struct_field_and_binding_renames_propagate_through_all_reference_views(tmp_path):
    with _project(tmp_path) as project:
        project.analyze(); _record(project)
        project.apply_type(0x1040, 'Records', name='ledger')
        _record(project, field='total')
        project.annotate(0x1040, 'accounts', kind='name')
        assert 'accounts[0].total' in project.disassembly(0x1000)['instructions'][0]['display_operands']
        assert project.cfg(0x1000)['nodes'][0]['references'][0]['name'] == 'accounts[0].total'
        assert project.typed_data(0x1040)['items'][2]['path'] == 'accounts[0].total'
        project.annotate(0x1044, 'explicit_cash_field', kind='name')
        assert 'explicit_cash_field' in project.disassembly(0x1000)['instructions'][0]['display_operands']


def test_type_array_output_limits_and_pointer_address_models_are_explicit(tmp_path):
    with _project(tmp_path) as project:
        _record(project)
        project.apply_type(0x1040, 'Records', name='ledger')
        limited = project.typed_data(0x1040, max_items=3)
        assert limited['truncated'] and len(limited['items']) == 3
        project.define_type('NearUnknown', dict(kind='pointer', size=2, target='u8', address_space='near'))
        project.define_type('NearKnown', dict(kind='pointer', size=2, target='u8', address_space='near', segment=0x1000))
        project.define_type('FarPointer', dict(kind='pointer', size=4, target='u8', address_space='far16'))
        project.apply_type(0x1080, 'NearUnknown')
        project.apply_type(0x1082, 'NearKnown')
        project.apply_type(0x1084, 'FarPointer')
        assert project.typed_data(0x1080)['items'][0]['target'] is None
        assert project.typed_data(0x1082)['items'][0]['target'] == '0x10000'
        assert project.typed_data(0x1084)['items'][0]['target'] == '0x0'
        assert not project.typed_data(0x1084)['items'][0]['target_mapped']


def test_patch_copies_interpretations_and_preserves_parent_type_and_bytes(tmp_path):
    with _project(tmp_path) as project:
        _record(project)
        project.apply_type(0x1040, 'Records', name='ledger')
        project.annotate(0x1040, 'accounts', kind='name')
        original = project.typed_data(0x1040)
        child = project.patch(0x1040, '0500')['version']
        assert project.typed_data(0x1040, version=child)['items'][0]['value'] == 5
        assert project.typed_data(0x1040, version=1) == original
        assert project.typed_data(0x1040, version=child)['items'][0]['path'] == 'accounts[0].flags'
        project.define_type('RecordPointer', dict(kind='pointer', size=8, target='u8'), version=child)
        assert project.typed_data(0x1040, version=1)['items'][3]['target_type'] == 'Record'
        assert project.typed_data(0x1040, version=child)['items'][3]['target_type'] == 'u8'
    with Project(tmp_path / 'types.fdb') as reopened:
        assert reopened.typed_data(0x1040, version=1)['items'][0]['value'] == 3
        assert reopened.typed_data(0x1040)['items'][0]['value'] == 5


def test_recursive_pointer_layout_is_allowed_but_by_value_cycles_and_overlaps_are_atomic(tmp_path):
    with _project(tmp_path) as project:
        _record(project)
        before = project.types()
        invalid = [dict(kind='struct', size=16, fields=[dict(name='self', offset=0, type='Record')]),
                   dict(kind='struct', size=16, fields=[dict(name='a', offset=0, type='u64'), dict(name='b', offset=4, type='u64')]),
                   dict(kind='array', element='Record', count=True)]
        for definition in invalid:
            with pytest.raises(ValueError):
                project.define_type('Record', definition)
            assert project.types() == before
        with pytest.raises(ValueError):
            project.define_type('u32', dict(kind='scalar', size=1))
        with pytest.raises(ValueError):
            project.apply_type(0x10FC, 'Record')


def test_redefinition_cannot_grow_binding_into_adjacent_binding(tmp_path):
    with _project(tmp_path) as project:
        project.define_type('Small', dict(kind='scalar', size=4))
        project.apply_type(0x1040, 'Small')
        project.apply_type(0x1048, 'u32')
        before = project.types()
        with pytest.raises(ValueError, match='overlap'):
            project.define_type('Small', dict(kind='scalar', size=16))
        assert project.types() == before


def test_dos_segment_aliases_share_one_physical_typed_field_identity(tmp_path):
    module = bytearray(128)
    module[0] = 0xCB
    struct.pack_into('<HH', module, 0x60, 7, 9)
    header = bytearray(64)
    size = len(header) + len(module)
    struct.pack_into('<14H', header, 0, 0x5A4D, size, 1, 0, 4, 0, 0xFFFF, 0, 0, 0, 0, 0, 28, 0)
    source = tmp_path / 'typed-dos.exe'
    source.write_bytes(header + module)
    with Project.create(tmp_path / 'typed-dos.fdb', source) as project:
        project.define_type('Pair', dict(kind='struct', size=4, fields=[dict(name='key', offset=0, type='u16'), dict(name='value', offset=2, type='u16')]))
        project.apply_type('1000:0060', 'Pair', name='player')
        assert project.locate('1000:0062')['presentation']['name'] == 'player.value'
        assert project.locate('1001:0052')['presentation']['name'] == 'player.value'
        project.annotate('1001:0052', 'shared_alias_value', kind='name')
        assert project.locate('1000:0062')['presentation']['name'] == 'shared_alias_value'
        assert project.typed_data('1000:0060')['items'][1]['value'] == 9
