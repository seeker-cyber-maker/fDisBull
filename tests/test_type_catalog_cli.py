"""Type catalogs cross real CLI processes without carrying source bindings."""
import json

from fdisbull.cli import invoke, main, parser, respond
from fdisbull.project import Project


def _source(tmp_path, name):
    binary = tmp_path / (name + '.bin')
    binary.write_bytes(b'\xc3' + bytes(63))
    database = tmp_path / (name + '.fdb')
    with Project.create(database, binary, arch='x86', bits=16, base=0x1000):
        pass
    return database


def test_catalog_json_protocol_exchanges_definitions_without_bindings(tmp_path):
    source, target = _source(tmp_path, 'source'), _source(tmp_path, 'target')
    with Project(source) as project:
        project.define_type('Pair', {'kind': 'struct', 'size': 4, 'fields': [
            {'name': 'count', 'offset': 0, 'type': 'u16'},
            {'name': 'flags', 'offset': 2, 'type': 'u16'}]}, author='source-analyst')
        project.apply_type(0x1010, 'Pair', name='source_record')
    exported = respond({'id': 1, 'method': 'export-types', 'params': {'project': str(source)}})
    assert exported['ok'], exported
    imported = respond({'id': 2, 'method': 'import-types', 'params': {
        'project': str(target), 'catalog': exported['result'], 'author': 'target-analyst'}})
    assert imported['ok'], imported
    assert imported['result']['imported'] == 1
    with Project(target) as project:
        assert project.types()['bindings'] == []
        assert 'Pair' in {row['layout']['name'] for row in project.types()['types']}


def test_cli_exports_a_raw_catalog_to_a_new_file_and_reimports(tmp_path, capsys):
    source, target = _source(tmp_path, 'first'), _source(tmp_path, 'second')
    with Project(source) as project:
        project.define_type('Words', {'kind': 'array', 'element': 'u16', 'count': 2})
    output = tmp_path / 'catalog.json'
    parser().parse_args(['export-types', str(source), '--output', str(output)])
    assert main(['export-types', str(source), '--output', str(output)]) == 0
    assert json.loads(capsys.readouterr().out)['ok']
    assert json.loads(output.read_text())['format'] == 'fdisbull-types-1'
    original = output.read_bytes()
    assert main(['export-types', str(source), '--output', str(output)]) == 1
    assert not json.loads(capsys.readouterr().out)['ok']
    assert output.read_bytes() == original
    assert main(['import-types', str(target), str(output), '--author', 'recipient']) == 0
    assert json.loads(capsys.readouterr().out)['result']['imported'] == 1
    with Project(target) as project:
        assert project.types()['bindings'] == []


def test_export_refuses_project_and_alias_output_and_import_file_budget(tmp_path):
    database = _source(tmp_path, 'protected')
    alias = tmp_path / 'database-alias'
    alias.symlink_to(database)
    for output in (database, alias):
        result = respond({'method': 'export-types', 'params': {
            'project': str(database), 'output': str(output)}})
        assert not result['ok']
        with Project(database) as project:
            assert project.status()['version']['id'] == 1
    oversized = tmp_path / 'large.json'
    oversized.write_bytes(b' ' * (4 * 1024 * 1024 + 1))
    result = respond({'method': 'import-types', 'params': {
        'project': str(database), 'catalog_file': str(oversized)}})
    assert not result['ok'] and '4 MiB' in result['error']['message']


def test_file_export_uses_the_catalog_utf8_byte_budget(tmp_path, capsys):
    source, target = _source(tmp_path, 'unicode-source'), _source(tmp_path, 'unicode-target')
    author = '\U00010400' * 256
    with Project(source) as project:
        project.define_type('Seed', {'kind': 'scalar', 'size': 2}, author=author)
        seed_catalog = project.export_types()
        seed = seed_catalog['types'][0]
        seed_catalog['types'] = [dict(seed, name=f'Scalar_{i}') for i in range(1200)]
        project.import_types(seed_catalog)
        expected_count = len(project.export_types()['types'])
    output = tmp_path / 'unicode-catalog.json'
    assert main(['export-types', str(source), '--output', str(output)]) == 0
    assert json.loads(capsys.readouterr().out)['ok']
    assert output.stat().st_size < 4 * 1024 * 1024
    assert main(['import-types', str(target), str(output)]) == 0
    assert json.loads(capsys.readouterr().out)['result']['imported'] == expected_count
    with Project(target) as project:
        assert all(row['author'] == author for row in project.export_types()['types'])


def test_exact_four_mib_catalog_roundtrips_through_file_commands(tmp_path):
    source, target = _source(tmp_path, 'exact-source'), _source(tmp_path, 'exact-target')
    encode = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'),
                                      ensure_ascii=False, allow_nan=False).encode('utf-8')
    with Project(source) as project:
        catalog = project.export_types()
        author = '\U0001f600' * 256
        catalog['types'] = [dict(name=f'Type_{i}', definition={'kind': 'scalar', 'size': 1},
                                 author=author, origin=dict(status='imported_interpretation',
                                 source=catalog['source'], author=author, imported_by='review'))
                            for i in range(1660)]
        remaining = 4 * 1024 * 1024 - len(encode(catalog))
        assert 0 <= remaining <= sum(128 - len(row['name']) for row in catalog['types'])
        for row in catalog['types']:
            count = min(remaining, 128 - len(row['name']))
            row['name'] += '_' * count
            remaining -= count
        assert remaining == 0
        project.import_types(catalog, author='review')
        expected = encode(project.export_types())
        assert len(expected) == 4 * 1024 * 1024
    output = tmp_path / 'exact.json'
    result = invoke('export-types', {'project': str(source), 'output': str(output)})
    assert result['bytes'] == 4 * 1024 * 1024 and output.read_bytes() == expected
    result = invoke('import-types', {'project': str(target), 'catalog_file': str(output)})
    assert result['imported'] == 1660 and result['bindings_imported'] == 0


def test_cli_selects_portable_types_without_exporting_unrelated_fixed_pointers(tmp_path, capsys):
    source = _source(tmp_path, 'selected')
    with Project(source) as project:
        project.define_type('Portable', {'kind': 'scalar', 'size': 2})
        project.define_type('ContextPointer', {'kind': 'pointer', 'size': 2,
                                             'target': 'Portable', 'address_space': 'near',
                                             'segment': 0x1000})
    output = tmp_path / 'selected.json'
    assert main(['export-types', str(source), '--name', 'Portable', '--output', str(output)]) == 0
    assert json.loads(capsys.readouterr().out)['ok']
    assert [row['name'] for row in json.loads(output.read_text())['types']] == ['Portable']


def test_json_catalog_preserves_enum_members_named_like_native_addresses(tmp_path):
    source, target = _source(tmp_path, 'enum-source'), _source(tmp_path, 'enum-target')
    members = {'address': 7, 'source': 8, 'target': 9, 'start': 10, 'end': 11}
    with Project(source) as project:
        project.define_type('Markers', {'kind': 'enum', 'size': 2, 'members': members})
    exported = respond({'method': 'export-types', 'params': {'project': str(source)}})
    assert exported['ok']
    assert exported['result']['types'][0]['definition']['members'] == members
    imported = respond({'method': 'import-types', 'params': {
        'project': str(target), 'catalog': exported['result']}})
    assert imported['ok'] and imported['result']['imported'] == 1
