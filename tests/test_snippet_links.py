"""Authored bytes exercise real project persistence and portable identities."""
from copy import deepcopy
import hashlib
import json
import shutil
import struct

import pytest

from fdisbull.project import Project


def project(tmp_path, name='one'):
    source = tmp_path / (name + '.bin')
    source.write_bytes(bytes.fromhex('b80100c3') + b'DATA')
    return Project.create(tmp_path / (name + '.fdb'), source, arch='x86', bits=16, base=0x1000)


def capture(p, name='entry', **kwargs):
    return p.capture_snippet(name, [dict(address=0x1000, size=3)], boundary='authored three-byte instruction', evidence='authored fixture', **kwargs)


def contract():
    return dict(format='fdisbull-block-contract-1', name='increment', inputs={'value': 'u16'}, outputs={'result': 'u16'}, behavior={'kind': 'declared', 'operation': 'increment'}, domain={'wrap': 16})


def layer(contract_id, snippet_id=None, name='original'):
    doc = dict(format='fdisbull-udl-layer-1', name=name, contract=contract_id,
               implementation={'executor': 'authored-fixture'}, adapter={'value': 'ax'},
               assurance='candidate', evidence='authored declaration only')
    if snippet_id is not None:doc['snippet'] = snippet_id
    return doc


def test_capture_has_source_version_context_and_exact_optional_payloads(tmp_path):
    with project(tmp_path) as p:
        receipt = capture(p, author='analyst')
        doc = receipt['document']; span = doc['spans'][0]
        assert doc['source']['source_sha256'] == hashlib.sha256(bytes.fromhex('b80100c3') + b'DATA').hexdigest()
        assert doc['source']['version_sha256'] == p.version(1)['sha256']
        assert doc['context'] == 'x86:16:little' and doc['boundary']['status'] == 'authored'
        assert span['sha256'] == hashlib.sha256(bytes.fromhex('b80100')).hexdigest()
        assert span['backing']['file_offset'] == 0
        assert str(tmp_path) not in json.dumps(doc)
        assert 'bytes_hex' not in json.dumps(p.snippet_info(receipt['id'], full=True))
        assert 'document' not in p.snippet_info(receipt['id'])
        full = p.snippet_info(receipt['id'], include_bytes=True)
        assert full['document']['spans'][0]['bytes_hex'] == full['document']['spans'][0]['source_bytes_hex'] == 'b80100'
        assert full['binding_status'] == 'local-source-verified'
        assert capture(p, author='analyst')['id'] == receipt['id']
        assert p.snippets()['total'] == 1


def test_child_source_mapping_and_reopen_do_not_rebase_captures_or_selection(tmp_path):
    path = tmp_path / 'one.fdb'
    with project(tmp_path) as p:
        old = capture(p)
        cid = p.store_contract(contract())['id']
        lid = p.store_udl_layer(layer(cid, old['id']))['id']
        selection = p.store_udl_selection(dict(format='fdisbull-udl-selection-1', name='pinned', bindings={'operation': lid}))
        child = p.patch(0x1001, '0200')['version']
        new = capture(p, version=child)
        assert new['id'] != old['id']
        payload = p.snippet_info(new['id'], include_bytes=True)['document']['spans'][0]
        assert payload['bytes_hex'] == 'b80200' and payload['source_bytes_hex'] == 'b80100'
        assert p.snippets(version=1)['items'][0]['id'] == old['id']
        assert p.snippets(version=child)['items'][0]['id'] == new['id']
        assert p.udl_selection_info(selection['id'], full=True)['document']['bindings']['operation'] == lid
    with Project(path) as p:
        assert p.snippet_info(old['id'], include_bytes=True)['document']['spans'][0]['bytes_hex'] == 'b80100'
        assert p.snippet_info(new['id'], include_bytes=True)['document']['spans'][0]['bytes_hex'] == 'b80200'
        assert p.udl_layer_info(lid, full=True)['document']['snippet'] == old['id']
        assert p.udl_selection_info(selection['id'], full=True)['document'] == selection['document']


def test_portable_endpoints_and_authored_one_to_many_relations(tmp_path):
    with project(tmp_path, 'a') as a, project(tmp_path, 'b') as b:
        source = capture(a, author='source-author')
        first = capture(b, name='first')
        second = b.capture_snippet('second', [dict(address=0x1003, size=1)])
        relation = b.link_snippets([source], [first['id'], second['id']], 'candidate-correspondence',
                                  domain={'inputs': 'u16'}, evidence={'method': 'static interpretation'}, unknowns=['caller effects'])
        assert relation['document']['sources'] == [source['id']]
        assert relation['document']['targets'] == [first['id'], second['id']]
        assert relation['document']['assurance'] == 'candidate'
        assert relation['document']['assertion_status'] == 'authored-declaration'
        foreign = b.snippet_info(source['id'], full=True)
        assert foreign['document'] == source['document']
        assert foreign['binding_status'] == 'external-endpoint-declaration' and not foreign['payload_available']
        with pytest.raises(ValueError, match='unavailable'):b.snippet_info(source['id'], include_bytes=True)
        explicit = a.snippet_info(source['id'], include_bytes=True)
        b.link_snippets([explicit], [first['id']], 'equivalent-under-contract', domain={'inputs': [0, 1]}, evidence='two authored cases', assurance='equivalence')
        assert b.snippet_info(source['id'], include_bytes=True)['document']['spans'][0]['bytes_hex'] == 'b80100'
        assert b.snippet_links()['total'] == 2


def test_contract_layer_selection_documents_are_immutable_and_author_portable(tmp_path):
    with project(tmp_path, 'a') as a, project(tmp_path, 'b') as b:
        original = contract(); c = a.store_contract(original, author='human')
        original['behavior']['operation'] = 'changed'
        assert a.contract_info(c['id'], full=True)['document']['behavior']['operation'] == 'increment'
        assert b.store_contract(c['document'])['id'] == c['id']
        with pytest.raises(ValueError, match='author'):b.store_contract(c['document'], author='other')
        first = a.store_udl_layer(layer(c['id'], name='first'))
        second = a.store_udl_layer(layer(c['id'], name='second'))
        assert first['id'] != second['id']
        s = a.store_udl_selection(dict(format='fdisbull-udl-selection-1', name='explicit', bindings={'slot': first['id']}))
        assert a.udl_selection_info(s['id'], full=True)['document']['bindings']['slot'] == first['id']
        assert 'document' not in a.contracts()['items'][0]
        assert a.udl_layers()['total'] == 2 and a.udl_selections()['total'] == 1
        assert a.udl_layers(limit=1)['has_more']


def test_attached_and_original_file_spans_are_retained_without_guessing_addresses(tmp_path):
    attached = tmp_path / 'overlay.bin'; attached.write_bytes(b'OVERLAY')
    with project(tmp_path) as p:
        p.attach_file(attached)
        receipt = p.capture_snippet('file-parts', [dict(file='source', offset=0, size=2), dict(file='overlay.bin', offset=1, size=3)])
        attached.unlink()
        spans = p.snippet_info(receipt['id'], include_bytes=True)['document']['spans']
        assert [s['bytes_hex'] for s in spans] == ['b801', b'VER'.hex()]
        assert all('address' not in s for s in spans)
        assert spans[1]['file_sha256'] == hashlib.sha256(b'OVERLAY').hexdigest()


@pytest.mark.parametrize('mutation', ['payload', 'document', 'sha256', 'source', 'region'])
def test_content_tamper_is_detected_before_use(tmp_path, mutation):
    with project(tmp_path) as p:
        receipt = capture(p)
        if mutation == 'payload':p.db.execute("UPDATE snippet_payloads SET data=x'000000' WHERE role='bytes'")
        elif mutation == 'document':p.db.execute("UPDATE snippet_objects SET document='{}'")
        elif mutation == 'sha256':p.db.execute("UPDATE snippet_objects SET sha256=?", ('0' * 64,))
        elif mutation == 'source':p.db.execute("UPDATE binary_info SET source_bytes=x'00' WHERE version=1")
        else:p.db.execute("UPDATE regions SET data=x'00' WHERE version=1")
        p.db.commit()
        with pytest.raises(ValueError, match='digest|inventory'):p.snippet_info(receipt['id'], include_bytes=True)


def test_dependency_tamper_rejects_a_pinned_selection(tmp_path):
    with project(tmp_path) as p:
        c = p.store_contract(contract()); l = p.store_udl_layer(layer(c['id']))
        s = p.store_udl_selection(dict(format='fdisbull-udl-selection-1', name='choice', bindings={'slot': l['id']}))
        p.db.execute("UPDATE snippet_objects SET document='{}' WHERE id=?", (c['id'],)); p.db.commit()
        with pytest.raises(ValueError, match='digest'):p.udl_selection_info(s['id'], full=True)


def test_failed_foreign_link_is_atomic_inside_an_existing_transaction(tmp_path):
    with project(tmp_path, 'a') as a, project(tmp_path, 'b') as b:
        foreign = capture(a, 'foreign'); local = capture(b)
        with b.transaction(True):
            b.annotate(0x1000, 'keep this note')
            with pytest.raises(ValueError, match='finite'):
                b.link_snippets([foreign], [local['id']], 'candidate', domain={'x': float('nan')}, evidence='authored')
            assert b.db.execute('SELECT count(*) FROM snippet_objects').fetchone()[0] == 1
        assert b.db.execute('SELECT text FROM annotations').fetchone()[0] == 'keep this note'


@pytest.mark.parametrize('bad', [[], [dict(address=0x2000, size=1)], [dict(address=0x1000, size=0)], [dict(file='source', offset=8, size=1)], [dict(address=0x1000, size=True)]])
def test_capture_failures_leave_no_partial_records(tmp_path, bad):
    with project(tmp_path) as p:
        with pytest.raises(ValueError):p.capture_snippet('bad', bad)
        assert p.snippets()['total'] == 0


def test_exact_id_references_and_json_budgets_are_required(tmp_path, monkeypatch):
    with project(tmp_path) as p:
        c = p.store_contract(contract())
        for bad in ('increment', 'contract:' + '0' * 64):
            with pytest.raises(ValueError):p.store_udl_layer(layer(bad))
        with pytest.raises(ValueError):p.store_udl_selection(dict(format='fdisbull-udl-selection-1', name='bad', bindings={'slot': c['id']}))
        import fdisbull.snippet_links as snippets
        monkeypatch.setattr(snippets, 'MAX_DOCUMENT', 100)
        with pytest.raises(ValueError, match='4 MiB'):p.store_contract(contract())


def test_optional_tables_initialize_on_reopen_without_core_schema_bump(tmp_path):
    with project(tmp_path) as p:
        schema = p.db.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()[0]
        p.db.executescript('DROP TABLE snippet_payloads; DROP TABLE snippet_objects;')
    with Project(tmp_path / 'one.fdb') as p:
        assert p.snippets()['total'] == p.contracts()['total'] == 0
        assert p.db.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()[0] == schema


def test_attached_source_tamper_invalidates_local_binding(tmp_path):
    attached = tmp_path / 'overlay.bin'; attached.write_bytes(b'OVERLAY')
    with project(tmp_path) as p:
        p.attach_file(attached)
        snippet = p.capture_snippet('overlay', [dict(file='overlay.bin', offset=0, size=3)])
        p.db.execute("UPDATE external_files SET data=x'00000000000000'"); p.db.commit()
        with pytest.raises(ValueError, match='attached|source|digest'):p.snippet_info(snippet['id'])


def _rehash(receipt):
    encoded = json.dumps(receipt['document'], sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    receipt['sha256'] = hashlib.sha256(encoded).hexdigest()
    receipt['id'] = 'snippet:' + receipt['sha256']
    return receipt


@pytest.mark.parametrize('mutation', ['backing', 'arch', 'file_hash', 'source_field', 'extent'])
def test_malformed_portable_identities_refuse_without_partial_import(tmp_path, mutation):
    with project(tmp_path, 'a') as a, project(tmp_path, 'b') as b:
        foreign = capture(a, 'foreign'); local = capture(b)
        if mutation == 'backing':del foreign['document']['spans'][0]['backing']
        elif mutation == 'arch':del foreign['document']['source']['arch']
        elif mutation == 'file_hash':foreign['document']['spans'][0]['backing']['file_sha256'] = '0' * 64
        elif mutation == 'source_field':foreign['document']['source']['machine_path'] = '/private/unknown'
        else:foreign['document']['spans'][0]['address'] = (1 << 64) - 1
        _rehash(foreign)
        with pytest.raises(ValueError):b.link_snippets([foreign], [local['id']], 'candidate', {'x': 'u16'}, 'authored')
        assert b.snippets()['total'] == 1 and b.snippet_links()['total'] == 0


def test_full_payload_extents_refuse_before_registration(tmp_path):
    with project(tmp_path, 'a') as a, project(tmp_path, 'b') as b:
        foreign = capture(a, 'foreign'); local = capture(b)
        foreign = a.snippet_info(foreign['id'], include_bytes=True)
        foreign['document']['spans'][0]['bytes_hex'] = '00' * 1000
        with pytest.raises(ValueError, match='payload|extent'):b.link_snippets([foreign], [local['id']], 'candidate', {'x': 'u16'}, 'authored')
        assert b.snippets()['total'] == 1


def test_copied_project_remains_valid_without_original_paths(tmp_path):
    with project(tmp_path) as p:
        captured = capture(p)
    moved = tmp_path / 'moved.fdb'; shutil.copyfile(tmp_path / 'one.fdb', moved)
    (tmp_path / 'one.bin').unlink()
    with Project(moved) as p:
        assert p.snippet_info(captured['id'], include_bytes=True)['document']['spans'][0]['bytes_hex'] == 'b80100'


def test_explicit_local_recapture_can_qualify_an_identical_external_endpoint(tmp_path):
    with project(tmp_path, 'a') as a, project(tmp_path, 'b') as b:
        source = capture(a)
        local = capture(b, 'other')
        b.link_snippets([source], [local['id']], 'candidate', {'x': 'u16'}, 'authored')
        assert b.snippet_info(source['id'])['binding_status'] == 'external-endpoint-declaration'
        assert capture(b)['id'] == source['id']
        assert b.snippet_info(source['id'])['binding_status'] == 'local-source-verified'


def test_ne_identity_zero_fill_and_exact_source_backing(tmp_path):
    from test_ne_loader import ne_file
    source = tmp_path / 'authored-ne.exe'; original = ne_file(); source.write_bytes(original)
    with Project.create(tmp_path / 'ne.fdb', source) as p:
        captured = p.capture_snippet('far-call', [dict(address='ne:1:0', size=5)])
        part = p.snippet_info(captured['id'], include_bytes=True)['document']['spans'][0]
        assert part['logical_location']['segment_index'] == 1 and part['logical_location']['runtime_selector'] is None
        assert part['bytes_hex'] == '9affff0000'
        assert bytes.fromhex(part['source_bytes_hex']) == original[part['backing']['file_offset']:part['backing']['file_offset'] + 5]
        zero = p.capture_snippet('allocation', [dict(address='ne:3:0x20', size=4)])
        part = p.snippet_info(zero['id'], include_bytes=True)['document']['spans'][0]
        assert part['backing'] is None and 'source_bytes_hex' not in part and part['bytes_hex'] == '00000000'
        with pytest.raises(ValueError, match='boundary'):p.capture_snippet('wrap', [dict(address='ne:1:0xffff', size=2)])
        with pytest.raises(ValueError, match='split spans'):p.capture_snippet('mixed', [dict(address='ne:3:0', size=16)])


def test_dos_exact_context_is_applied_to_every_ordered_span(tmp_path):
    header = bytearray(64)
    struct.pack_into('<14H', header, 0, 0x5a4d, 128, 1, 0, 4, 0, 0xffff, 0, 0, 0, 0, 0, 64, 0)
    source = tmp_path / 'authored-mz.exe'; source.write_bytes(header + bytes.fromhex('b80100c3') + bytes(60))
    with Project.create(tmp_path / 'dos.fdb', source) as p:
        captured = p.capture_snippet('entry', [dict(address='1000:0000', size=3)])
        assert captured['document']['context'] == 'x86:16:little:cs=1000'
        with pytest.raises(ValueError, match='CS'):
            p.capture_snippet('late-cs', [dict(address=0x10000, size=3), dict(address='1001:0000', size=1)])
        with pytest.raises(ValueError, match='one exact'):
            p.capture_snippet('multiple-cs', [dict(address='1000:0000', size=1), dict(address='1001:0000', size=1)])
        assert p.snippets()['total'] == 1


def test_json_depth_and_wrong_descriptor_types_fail_atomically(tmp_path):
    with project(tmp_path) as p:
        doc = contract(); nested = []
        for _ in range(2000):nested = [nested]
        doc['effects'] = nested
        with pytest.raises(ValueError, match='depth'):p.store_contract(doc)
        assert p.contracts()['total'] == 0
        for value in (True, 1, []):
            bad = contract(); bad['inputs']['value'] = value
            with pytest.raises(ValueError):p.store_contract(bad)


def test_bad_explicit_byte_hash_rolls_back_endpoint_registration(tmp_path):
    with project(tmp_path, 'a') as a, project(tmp_path, 'b') as b:
        foreign = capture(a, 'foreign'); local = capture(b)
        foreign = a.snippet_info(foreign['id'], include_bytes=True)
        foreign['document']['spans'][0]['bytes_hex'] = '000000'
        with pytest.raises(ValueError, match='digest'):b.link_snippets([foreign], [local['id']], 'candidate', {'x': 'u16'}, 'authored')
        assert b.snippets()['total'] == 1
