"""External resources retain file-offset identity without becoming native memory."""
import hashlib
import struct

import pytest

from fdisbull.project import Project


def _project(tmp_path):
    source = tmp_path / 'program.bin'
    source.write_bytes(b'\xc3' + bytes(127))
    return Project.create(tmp_path / 'resources.fdb', source, arch='x86', base=0x1000)


def _file(tmp_path, name='save.dat', data=b'ABC\0\xff'):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _records(project):
    project.define_type('Record', {'kind': 'struct', 'size': 16, 'fields': []})
    project.define_type('RecordPointer', {'kind': 'pointer', 'size': 8, 'target': 'Record'})
    project.define_type('Record', {'kind': 'struct', 'size': 16, 'fields': [
        {'name': 'flags', 'offset': 0, 'type': 'u16'},
        {'name': 'delta', 'offset': 2, 'type': 'i16'},
        {'name': 'count', 'offset': 4, 'type': 'u32'},
        {'name': 'next', 'offset': 8, 'type': 'RecordPointer'}]})
    project.define_type('Records', {'kind': 'array', 'element': 'Record', 'count': 2})


def test_attachment_is_an_immutable_snapshot_surviving_source_changes_and_restart(tmp_path):
    original = b'External save data\x00\xff'
    source = _file(tmp_path, data=original)
    with _project(tmp_path) as project:
        native = project.regions(1)[0].data
        version_hash = project.version()['sha256']
        project.attach_file(source, name='save.dat', kind='save', author='analyst')
        source.write_bytes(b'replaced outside the project')
        source.unlink()
        listing = project.external_files()
        assert listing['total'] == 1 and listing['total_bytes'] == len(original)
        item = listing['items'][0]
        assert item['name'] == 'save.dat' and item['filename'] == 'save.dat'
        assert item['kind'] == 'save' and item['author'] == 'analyst'
        assert item['sha256'] == hashlib.sha256(original).hexdigest()
        assert 'data' not in item and 'bytes' not in item
        assert project.file_bytes('save.dat')['bytes'] == original.hex()
        assert project.regions(1)[0].data == native
        assert project.version()['sha256'] == version_hash
    with Project(tmp_path / 'resources.fdb') as reopened:
        assert reopened.file_bytes('save.dat')['bytes'] == original.hex()
        assert reopened.external_files()['items'][0]['sha256'] == hashlib.sha256(original).hexdigest()


def test_attachment_names_are_immutable_and_inventory_is_bounded_and_pageable(tmp_path):
    source = _file(tmp_path, data=b'first bytes')
    with _project(tmp_path) as project:
        project.attach_file(source, name='alpha.dat')
        project.attach_file(source, name='alpha.dat')  # Same identity/content is idempotent.
        assert project.external_files()['total'] == 1
        source.write_bytes(b'different bytes')
        with pytest.raises(ValueError):
            project.attach_file(source, name='alpha.dat')
        assert project.file_bytes('alpha.dat')['bytes'] == b'first bytes'.hex()
        project.attach_file(source, name='beta.dat')
        listing = project.external_files(limit=1, offset=1)
        assert listing['total'] == 2 and len(listing['items']) == 1
        assert listing['items'][0]['name'] == 'beta.dat'
        assert listing['limit'] == 1 and listing['offset'] == 1
        assert project.external_files(limit=1, offset=2)['items'] == []


@pytest.mark.parametrize('name', ['', '.', '..', '../save.dat', 'folder/save.dat',
                                  'folder\\save.dat', 'save\n.dat', 'save\x00.dat', 'save\x7f.dat', 'x' * 257])
def test_invalid_file_identities_cannot_be_attached(tmp_path, name):
    with _project(tmp_path) as project:
        with pytest.raises(ValueError):
            project.attach_file(_file(tmp_path), name=name)
        assert project.external_files()['total'] == 0


def test_attachment_per_file_and_aggregate_limits_are_atomic(tmp_path, monkeypatch):
    import fdisbull.external_files as external
    monkeypatch.setattr(external, 'MAX_EXTERNAL_FILE_SIZE', 16)
    monkeypatch.setattr(external, 'MAX_EXTERNAL_BYTES_PER_VERSION', 24)
    with _project(tmp_path) as project:
        with pytest.raises(ValueError):
            project.attach_file(_file(tmp_path, 'large.dat', bytes(17)))
        assert project.external_files()['total'] == 0
        project.attach_file(_file(tmp_path, 'first.dat', bytes(16)))
        with pytest.raises(ValueError):
            project.attach_file(_file(tmp_path, 'overflow.dat', bytes(9)))
        assert project.external_files()['total_bytes'] == 16
        project.attach_file(_file(tmp_path, 'fits.dat', bytes(8)))
        assert project.external_files()['total_bytes'] == 24


def test_file_byte_ranges_report_partial_eof_and_never_read_unbounded_bytes(tmp_path):
    payload = b'A\x00\nZ\xff'
    with _project(tmp_path) as project:
        project.attach_file(_file(tmp_path, data=payload))
        whole = project.file_bytes('save.dat', size=len(payload))
        assert whole['bytes'] == payload.hex() and whole['size'] == len(payload)
        assert whole['eof'] and whole['complete'] and not whole['truncated']
        partial = project.file_bytes('save.dat', offset=3, size=8)
        assert partial['bytes'] == payload[3:].hex() and partial['size'] == 2
        assert partial['requested_size'] == 8 and partial['file_size'] == len(payload)
        assert partial['ascii'] == 'Z.' and partial['eof'] and partial['truncated']
        end = project.file_bytes('save.dat', offset=len(payload))
        assert end['bytes'] == '' and end['size'] == 0 and end['eof']
        for options in ({'offset': 6}, {'offset': -1}, {'offset': True},
                        {'size': 65537}, {'size': -1}, {'size': True}):
            with pytest.raises(ValueError):
                project.file_bytes('save.dat', **options)


def test_nested_file_types_keep_offsets_signed_values_and_encoded_pointers(tmp_path):
    payload = struct.pack('<HhIQHhIQ', 3, -4, 9, 0x1040, 7, -8, 11, 0)
    with _project(tmp_path) as project:
        project.attach_file(_file(tmp_path, data=payload))
        _records(project)
        project.apply_file_type('save.dat', 'Records', name='ledger')
        native = project.regions(1)[0].data
        typed = project.typed_file('save.dat')
        assert not typed['truncated'] and len(typed['items']) == 8
        assert [item['value'] for item in typed['items'][:4]] == [3, -4, 9, 0x1040]
        assert [item['file_offset'] for item in typed['items'][:4]] == [0, 2, 4, 8]
        assert typed['items'][0]['path'] == 'ledger[0].flags'
        assert typed['items'][4]['path'] == 'ledger[1].flags'
        assert typed['items'][3]['bytes'] == struct.pack('<Q', 0x1040).hex()
        assert all(not ({'address', 'target', 'target_mapped'} & set(item)) for item in typed['items'])
        limited = project.typed_file('save.dat', max_items=3)
        assert limited['truncated'] and len(limited['items']) == 3
        with pytest.raises(ValueError):
            project.typed_file('save.dat', offset=4)
        assert project.regions(1)[0].data == native


def test_file_type_redefinition_updates_sizes_and_rejects_overlap_or_eof_atomically(tmp_path):
    with _project(tmp_path) as project:
        project.attach_file(_file(tmp_path, data=bytes(32)))
        project.define_type('Small', {'kind': 'scalar', 'size': 4})
        project.apply_file_type('save.dat', 'Small', name='head')
        project.apply_file_type('save.dat', 'u32', offset=8, name='next')
        project.define_type('Small', {'kind': 'scalar', 'size': 8})
        assert project.typed_file('save.dat')['items'][0]['size'] == 8
        before = project.types()
        with pytest.raises(ValueError):
            project.define_type('Small', {'kind': 'scalar', 'size': 16})
        assert project.types() == before
        assert project.typed_file('save.dat')['items'][0]['size'] == 8
        project.define_type('Tail', {'kind': 'scalar', 'size': 4})
        project.apply_file_type('save.dat', 'Tail', offset=28, name='tail')
        before = project.types()
        with pytest.raises(ValueError):
            project.define_type('Tail', {'kind': 'scalar', 'size': 8})
        assert project.types() == before
        assert project.typed_file('save.dat', offset=28)['items'][0]['size'] == 4


def test_native_patch_copies_external_snapshots_and_types_without_mutating_parent(tmp_path):
    with _project(tmp_path) as project:
        project.attach_file(_file(tmp_path, data=b'\x07\x00'))
        project.apply_file_type('save.dat', 'u16', name='saved_count')
        parent = project.typed_file('save.dat', version=1)
        child = project.patch(0x1000, '90')['version']
        assert project.file_bytes('save.dat', version=child)['bytes'] == '0700'
        assert project.typed_file('save.dat', version=child)['items'][0]['value'] == 7
        project.apply_file_type('save.dat', 'u16', name='child_count', version=child)
        assert project.typed_file('save.dat', version=child)['items'][0]['path'] == 'child_count'
        assert project.typed_file('save.dat', version=1) == parent
        project.attach_file(_file(tmp_path, 'extra.dat', b'new'), version=child)
        assert project.external_files(version=child)['total'] == 2
        assert project.external_files(version=1)['total'] == 1
    with Project(tmp_path / 'resources.fdb') as reopened:
        assert reopened.typed_file('save.dat', version=1) == parent
        assert reopened.typed_file('save.dat')['items'][0]['path'] == 'child_count'
