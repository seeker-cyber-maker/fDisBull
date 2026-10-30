"""Source-assisted retrieval stays separate from native facts and qualification."""
import hashlib
import sqlite3

import pytest

from fdisbull.cli import respond
from fdisbull.source_catalog import SourceCatalog


pytest.importorskip('tree_sitter')
pytest.importorskip('tree_sitter_c')

SOURCE = b"""struct City { int food_box; int population; };
int harvest(struct City *city, int amount) {
    city->food_box += amount;
    return city->food_box;
}
int famine(struct City *city) {
    if (city->food_box < 0) return --city->population;
    return city->population;
}
"""


def _import(catalog, root, edition='one', **kwargs):
    return catalog.import_tree(root, ['city.c'], 'https://example.invalid/game',
                               'commit-' + edition, edition, 'reconstructed-source', **kwargs)


@pytest.fixture
def inputs(tmp_path):
    root = tmp_path / 'sources'
    root.mkdir()
    (root / 'city.c').write_bytes(SOURCE)
    return root


def test_source_snapshot_preserves_bytes_locations_and_restarts(tmp_path, inputs):
    path = tmp_path / 'source.sqlite'
    native = tmp_path / 'original.exe'
    native.write_bytes(b'UNCHANGED NATIVE ORIGINAL')
    digest = hashlib.sha256(native.read_bytes()).hexdigest()
    with SourceCatalog.create(path) as catalog:
        result = _import(catalog, inputs, target_path=native, declared_output_sha256=digest)
        snapshot = result['id']
        assert result['document']['build_verified'] is False
        assert result['document']['target_relationship'] == 'declared-build-output'
        assert result['document']['target_sha256'] == digest
        assert not catalog.info()['native_mappings_created']
        assert _import(catalog, inputs, target_path=native, declared_output_sha256=digest)['created'] is False
        food = catalog.entities(snapshot=snapshot, name='food_box')['items'][0]
        assert food['kind'] == 'field' and food['owner'] == 'City' and food['line'] == 1
        assert catalog.source_text(food['id'])['text'] == 'int food_box;'
        harvest = catalog.entities(name='harvest')['items'][0]
        assert catalog.entities(kind='type')['total'] == 1  # References to struct City are not new definitions.
        saved = catalog.source_text(harvest['id'])['text']
        assert saved.startswith('int harvest(') and 'food_box += amount' in saved
        occurrences = catalog.occurrences('food_box')
        assert occurrences['total'] == 3
        assert {r['owner'] for r in occurrences['items']} == {'harvest', 'famine'}
        assert catalog.occurrences('Food_Box')['total'] == 0
        assert catalog.occurrences('food_box', limit=1)['has_more']
        assert catalog.entities(limit=1)['has_more']
        assert catalog.source_text(harvest['id'], size=10)['truncated']
        assert all(bytes(r[0]) != native.read_bytes() for r in catalog.db.execute('SELECT data FROM blobs'))
        inputs.joinpath('city.c').write_bytes(SOURCE.replace(b'+= amount', b'+= amount * 2'))
        second = _import(catalog, inputs, target_path=native, declared_output_sha256=digest)
        assert second['id'] != snapshot
        assert catalog.source_text(harvest['id'])['text'] == saved
    inputs.joinpath('city.c').unlink()
    with SourceCatalog(path) as reopened:
        assert reopened.source_text(harvest['id'])['text'] == saved
        assert reopened.info()['counts']['snapshots'] == 2
        assert reopened.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not reopened.db.execute('PRAGMA foreign_key_check').fetchall()
    assert hashlib.sha256(native.read_bytes()).hexdigest() == digest
    with pytest.raises(FileExistsError):
        SourceCatalog.create(path)


def test_revision_and_native_target_do_not_collapse_same_source(tmp_path, inputs):
    with SourceCatalog.create(tmp_path / 'c.sqlite') as catalog:
        a = _import(catalog, inputs, 'old')
        b = _import(catalog, inputs, 'new')
        assert a['id'] != b['id']
        assert catalog.info()['counts']['blobs'] == 1
        assert catalog.snapshots(limit=1)['has_more']
        assert catalog.snapshots(limit=1)['items'][0]['file_count'] == 1
        # Card text is shared but source entity and edition identity remain separate.
        assert catalog.info()['counts']['entities'] == 2 * len(catalog.entities(snapshot=a['id'])['items'])
        before = catalog.info()['counts']['snapshots']
        native = tmp_path / 'native'
        native.write_bytes(b'native')
        with pytest.raises(ValueError, match='declared output'):
            _import(catalog, inputs, target_path=native, declared_output_sha256='0' * 64)
        assert catalog.info()['counts']['snapshots'] == before


@pytest.mark.parametrize('paths', [['../city.c'], ['/city.c'], ['city.c', 'city.c'],
                                  ['x/../city.c'], ['x\\city.c'], ['city.c', 'missing.c']])
def test_invalid_source_intake_is_atomic(tmp_path, inputs, paths):
    with SourceCatalog.create(tmp_path / 'c.sqlite') as catalog:
        with pytest.raises((ValueError, OSError)):
            catalog.import_tree(inputs, paths, 'repo', 'rev', 'edition', 'original-source')
        assert catalog.info()['counts']['files'] == 0
        assert catalog.info()['counts']['snapshots'] == 0


def test_symlinks_and_oversize_sources_are_not_followed(tmp_path, inputs, monkeypatch):
    inputs.joinpath('alias.c').symlink_to(inputs / 'city.c')
    with SourceCatalog.create(tmp_path / 'c.sqlite') as catalog:
        with pytest.raises(ValueError, match='symlinks'):
            catalog.import_tree(inputs, ['alias.c'], 'repo', 'rev', 'edition', 'original-source')
        import fdisbull.source_catalog as module
        monkeypatch.setattr(module, 'MAX_FILE', 10)
        with pytest.raises(ValueError, match='regular file'):
            _import(catalog, inputs)
        assert catalog.info()['counts']['snapshots'] == 0


def test_unknown_formats_encoding_and_parse_errors_remain_explicit(tmp_path, inputs):
    inputs.joinpath('opaque.asm').write_bytes(b'\x00\xff ORIGINAL ASSEMBLY')
    inputs.joinpath('unknown.c').write_bytes(b'\xff invalid encoding')
    inputs.joinpath('broken.c').write_bytes(b'int f(void) { return ; @@@ }\n')
    with SourceCatalog.create(tmp_path / 'c.sqlite') as catalog:
        result = catalog.import_tree(inputs, ['opaque.asm', 'unknown.c', 'broken.c'],
                                     'repo', 'rev', 'edition', 'reconstructed-source')
        states = {r['path']: r['status'] for r in catalog.db.execute('SELECT * FROM files')}
        assert catalog.files()['total'] == 3
        assert catalog.files(limit=1)['has_more']
        assert states['opaque.asm'] == 'retained-unparsed'
        assert states['unknown.c'] == 'unsupported-text-encoding'
        assert states['broken.c'] == 'partial-syntax'
        assert result['partial_files'] == 1
        assert result['document']['native_equivalence'] is False


def test_concepts_are_exact_authored_links_and_not_search_training_text(tmp_path, inputs):
    with SourceCatalog.create(tmp_path / 'c.sqlite') as catalog:
        _import(catalog, inputs, 'one')
        _import(catalog, inputs, 'two')
        cards = catalog.info()['counts']['cards']
        concept = catalog.register_concept('city.food.stock', 'Accumulated food', unit='food units')
        assert catalog.concepts(key='city.food.stock')['items'] == [concept]
        assert catalog.concepts(key='unknown')['total'] == 0
        assert catalog.register_concept('city.food.stock', 'Accumulated food', unit='food units') == concept
        with pytest.raises(ValueError, match='immutable'):
            catalog.register_concept('city.food.stock', 'Food production per turn')
        for entity in catalog.entities(name='food_box')['items']:
            link = catalog.link_concept(concept['id'], entity['id'], 'represents',
                                        'Reviewed field declaration; inferred upstream naming.',
                                        assurance='source-supported')
            assert not link['document']['binary_equivalence']
            assert not link['document']['layer_admission']
            catalog.link_concept(concept['id'], entity['id'], 'represents',
                                 'Reviewed field declaration; inferred upstream naming.',
                                 assurance='source-supported')
        bindings = catalog.concept_bindings(concept['id'], limit=1)
        assert bindings['total'] == 2 and bindings['has_more']
        assert catalog.info()['counts']['cards'] == cards
        assert catalog.search('Accumulated')['items'] == []
        with pytest.raises(ValueError):
            catalog.link_concept(concept['id'], entity['id'], 'writes', 'Spelling alone does not prove a write.')


def test_vector_rank_scope_coverage_and_immutability(tmp_path, inputs):
    with SourceCatalog.create(tmp_path / 'c.sqlite') as catalog:
        old = _import(catalog, inputs, 'old')['id']
        _import(catalog, inputs, 'new')
        model = catalog.register_model('test-geometry', 'immutable-rev', 2, 'test-only vectors')['id']
        other = catalog.register_model('test-geometry', 'different-rev', 3, 'test-only vectors')['id']
        assert catalog.models(limit=1)['has_more']
        assert {r['id'] for r in catalog.models()['items']} == {model, other}
        harvest = catalog.entities(snapshot=old, name='harvest')['items'][0]
        famine = catalog.entities(snapshot=old, name='famine')['items'][0]
        rows = list(catalog.db.execute('SELECT * FROM entity_cards WHERE entity IN (?,?)',
                                       (harvest['id'], famine['id'])))
        items = [dict(card=r['card'], vector=[2, 0] if r['entity'] == harvest['id'] else [0, 3]) for r in rows]
        catalog.embed_cards(model, items)
        catalog.embed_cards(model, items)  # Idempotent after normalization/float32 storage.
        result = catalog.search('unrelated query spelling', mode='vector', model=model, vector=[1, 0],
                                snapshots=[old], kind='function')
        assert result['items'][0]['entity'] == harvest['id']
        assert all(r['snapshot'] == old for r in result['items'])
        assert result['embedding_coverage'] == 1
        assert result['score_kind'] == 'reciprocal-rank-fusion-k60'
        lexical = catalog.search('famine', snapshots=[old], kind='function')
        assert lexical['items'][0]['name'] == 'famine'
        hybrid = catalog.search('harvest', mode='hybrid', model=model, vector=[1, 0], snapshots=[old])
        assert hybrid['items'][0]['name'] == 'harvest'
        assert catalog.cards(model=model)['total'] < catalog.cards()['total']
        missing = catalog.search('query', mode='vector', model=other, vector=[1, 0, 0], snapshots=[old])
        assert missing['embedded_cards'] == 0 and missing['embedding_coverage'] == 0
        with pytest.raises(ValueError, match='immutable'):
            catalog.embed_cards(model, [dict(card=items[0]['card'], vector=[1, 1])])
        for bad in ([0, 0], [float('nan'), 1], [True, 0], [1]):
            with pytest.raises(ValueError):
                catalog.search('query', mode='vector', model=model, vector=bad)
        with pytest.raises(ValueError, match='unknown source snapshot'):
            catalog.search('harvest', snapshots=['not-a-source'])
        with pytest.raises(ValueError, match='unknown source card'):
            catalog.embed_cards(model, [dict(card='0' * 64, vector=[1, 0])])
        card = catalog.cards(model=other)['items'][0]['sha']
        with pytest.raises(ValueError, match='conflicting duplicate'):
            catalog.embed_cards(other, [dict(card=card, vector=[1, 0, 0]), dict(card=card, vector=[0, 1, 0])])
        assert catalog.cards(model=other)['total'] == catalog.cards()['total']
        with pytest.raises(ValueError):
            catalog.embed_cards(model, [items[0], dict(card=items[1]['card'], vector=[1])])


def test_source_json_methods_are_standalone_and_keep_byte_offsets_numeric(tmp_path, inputs):
    path = str(tmp_path / 'api.sqlite')
    request = lambda method, **params: respond({'method': method, 'params': dict(catalog=path, **params)},
                                               default_project='/nonexistent/native-project.fdb')
    assert request('source-create')['ok']
    result = request('source-import', root=str(inputs), paths=['city.c'], repository='repo',
                     revision='commit', edition='one', source_role='reconstructed-source')
    assert result['ok'], result
    entities = request('source-entities', name='harvest')
    assert entities['ok']
    entity = entities['result']['items'][0]
    assert type(entity['start']) is int and type(entity['end']) is int
    assert request('source-text', entity=entity['id'])['result']['text'].startswith('int harvest(')
    assert request('source-search', query='harvest')['result']['items'][0]['name'] == 'harvest'
    assert not request('source-info', unexpected=True)['ok']
    assert not request('source-create')['ok']


def test_creation_failure_cannot_leave_a_partially_initialized_catalog(tmp_path, monkeypatch):
    import fdisbull.source_catalog as module
    monkeypatch.setattr(module, 'DDL', module.DDL + '\nINVALID SQL;')
    path = tmp_path / 'bad.sqlite'
    with pytest.raises(sqlite3.Error):
        SourceCatalog.create(path)
    assert not path.exists()


def test_ranking_ties_do_not_depend_on_unrelated_snapshot_metadata(tmp_path, inputs):
    with SourceCatalog.create(tmp_path / 'c.sqlite') as catalog:
        snapshots = [_import(catalog, inputs, str(i))['id'] for i in range(3)]
        model = catalog.register_model('identical-vectors', 'v1', 2, 'test-only')['id']
        cards = catalog.cards()['items']
        catalog.embed_cards(model, [dict(card=c['sha'], vector=[1, 0]) for c in cards])
        orders = [[(r['name'], r['path'], r['start'], r['kind'])
                   for r in catalog.search('unused', mode='hybrid', model=model, vector=[1, 0],
                                           snapshots=[s])['items']] for s in snapshots]
        assert orders[0] == orders[1] == orders[2]
