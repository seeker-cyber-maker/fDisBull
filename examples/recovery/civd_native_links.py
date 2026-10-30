"""Qualify CivD source/native links across independently rebuilt DOS editions.

Supply a private source catalog, build manifest and pinned independent EXEPACK
decoder. This makes a new catalog copy and derived resident-only native projects;
it never edits originals or executes a game. Plain relinks must already exist.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import subprocess

from fdisbull.project import Project
from fdisbull.render import render_snapshot
from fdisbull.source_catalog import SourceCatalog
from fdisbull.source_native import unpack_exepack, parse_link_map, parse_cod, map_procedure, static_call_sites


FAMILIES = ('tile_yield', 'add_tile_yield', 'city_process', 'civ_economy', 'game_turn', 'food_stock_update')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def mz_parts(data):
    h = struct.unpack_from('<14H', data)
    end = (h[2] - 1) * 512 + h[1] if h[1] else h[2] * 512
    return data[h[4] * 16:end], [struct.unpack_from('<HH', data, h[12] + i * 4) for i in range(h[3])]


def run(catalog, manifest, output, reference):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    specs = json.loads(Path(manifest).read_text())
    target = sqlite3.connect(output / 'source-native.sqlite')
    with sqlite3.connect('file:' + str(Path(catalog).resolve()) + '?mode=ro', uri=True) as source:
        source.backup(target)
    target.close()
    originals_before = {s['original_path']: sha(Path(s['original_path']).read_bytes()) for s in specs}
    images, witnesses, projects, snapshots, builds, mappings, transfers = {}, {}, {}, {}, {}, {}, []
    call_sites = []
    with SourceCatalog(output / 'source-native.sqlite') as db:
        available = db.snapshots()['items']
        for spec in specs:
            edition = spec['edition']
            directory = Path(spec['directory'])
            selected = [s for s in available if s['document']['edition'] == edition]
            if len(selected) != 1:
                raise ValueError('source edition selection is missing or ambiguous')
            snapshots[edition] = selected[0]['id']
            builds[edition] = db.register_build(snapshots[edition], directory, spec['original_path'])
            original = Path(spec['original_path']).read_bytes()
            view = unpack_exepack(original)
            images[edition] = view
            reference_file = output / (edition + '-reference.exe')
            with (output / (edition + '-reference.log')).open('wb') as log:
                subprocess.run([str(reference), spec['original_path'], str(reference_file)],
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=30)
            reference_module, reference_relocs = mz_parts(reference_file.read_bytes())
            if view['module'] != reference_module or view['relocations'] != reference_relocs:
                raise ValueError('independent EXEPACK decoder differs')
            plain_module, _ = mz_parts((directory / 'PLAIN.EXE').read_bytes())
            plain_map = parse_link_map((directory / 'PLAIN.MAP').read_text())
            link = parse_link_map((directory / 'CIV.MAP').read_text())
            checks = []
            for family in FAMILIES[:-1]:
                entity = db.entities(snapshot=snapshots[edition], name=family, kind='function')['items']
                if len(entity) != 1:
                    raise ValueError('source function is missing or ambiguous')
                listing = Path(entity[0]['path']).stem + '.COD'
                result = map_procedure(link, parse_cod((directory / listing).read_text()), view, '_' + family)
                if link['symbols']['_' + family] != plain_map['symbols']['_' + family]:
                    raise ValueError('plain/packed relinks place a function differently')
                for span in result['spans']:
                    a, n = span['module_offset'], span['size']
                    if plain_module[a:a + n] != view['module'][a:a + n]:
                        raise ValueError('independent plain relink differs in mapped function')
                    for packed in span['packed_spans']:
                        if packed['kind'] == 'literal':
                            a, n, b = packed['module_offset'], packed['size'], packed['packed_offset']
                            if original[b:b + n] != view['module'][a:a + n]:
                                raise ValueError('original packed literal provenance differs')
                checks.append(family)
            for caller, filename, callees in (
                    ('_game_turn', 'TURN', ['_civ_economy']),
                    ('_civ_economy', 'ECONOMY', ['_city_process']),
                    ('_city_process', 'CITYMGT', ['_add_tile_yield', '_tile_yield']),
                    ('_add_tile_yield', 'CITYMGT', ['_tile_yield'])):
                sites = static_call_sites(link, parse_cod((directory / (filename + '.COD')).read_text()),
                                          view, caller, callees)
                if not sites:
                    raise ValueError('selected source/native direct-call connection is missing')
                call_sites.extend(dict(edition=edition, **s) for s in sites)
            image = output / (edition + '-resident.exe')
            image.write_bytes(view['image'])
            project = output / (edition + '-resident.fdb')
            with Project.create(project, image) as native:
                entry_status = native.analyze(max_instructions=128)
            projects[edition] = project
            witnesses[edition] = dict(independent_decoder_module_match=True, independent_decoder_relocations_match=True,
                                     plain_relink_functions_match=checks,
                                     reference_image_sha256=sha(reference_file.read_bytes()),
                                     plain_image_sha256=sha((directory / 'PLAIN.EXE').read_bytes()),
                                     decoded_image_sha256=view['image_sha256'],
                                     decoded_module_sha256=view['module_sha256'],
                                     overlay_bytes_not_loaded=view['original_overlay_size'],
                                     entry_analysis_stable=entry_status['stable'])
        baseline = '474.03'
        base_spec = next(s for s in specs if s['edition'] == baseline)
        for family in FAMILIES:
            name = 'city_process' if family == 'food_stock_update' else family
            entity = db.entities(snapshot=snapshots[baseline], name=name, kind='function')['items'][0]
            line = None
            if family == 'food_stock_update':
                raw = bytes(db.db.execute('SELECT data FROM blobs WHERE sha=(SELECT sha FROM files WHERE snapshot=? AND path=?)',
                                          (snapshots[baseline], entity['path'])).fetchone()[0])
                lines = [i + 1 for i, text in enumerate(raw.splitlines()) if b'townbuf[city].food_box +=' in text]
                if len(lines) != 1:
                    raise ValueError('food update statement is ambiguous')
                line = lines[0]
            mapped = db.map_native(entity['id'], builds[baseline]['id'], base_spec['directory'],
                                   base_spec['original_path'], line, projects[baseline])
            mappings[(baseline, family)] = mapped
            for spec in specs:
                edition = spec['edition']
                if edition == baseline:
                    continue
                transfer = db.propagate_native_map(mapped['id'], snapshots[edition], spec['directory'],
                                                    spec['original_path'], projects[edition])
                transfers.append(dict(family=family, target_edition=edition, **transfer))
                target_map = db._build_get('source_native_maps', transfer['document']['target_map'])
                mappings[(edition, family)] = dict(id=transfer['document']['target_map'], document=target_map)
        stock = db.concepts(key='city.food.stock')['items'][0]['id']
        stock_links = []
        for edition in projects:
            mapped = mappings[(edition, 'food_stock_update')]
            stock_links.append(db.link_concept(stock, mapped['document']['entity'], 'related',
                'Compiled source statement updates food_box; exact original-byte witness ' + mapped['id']
                + '. Execution conditions and dynamic reachability were not observed.',
                assurance='source-and-build-supported static relationship', author='verified-source-build'))
        native_links, observations = [], []
        for edition, project in projects.items():
            with Project(project) as native:
                for family in FAMILIES[:-1]:
                    span = mappings[(edition, family)]['document']['spans'][0]
                    address = f"{0x1000 + span['segment']:04x}:{span['offset']:04x}"
                    native.analyze(start=address, max_instructions=128)
                    native.annotate(address, family, kind='name', author='civd-verified-build')
                food = mappings[(edition, 'food_stock_update')]['document']['spans'][0]
                linear = 0x10000 + food['module_offset']
                cs = 0x1000 + food['segment']
                address = f"{cs:04x}:{food['offset']:04x}"
                context = f'x86:16:little:cs={cs:04x}'
                for _ in range(3):
                    status = native.analyze(start=address, max_instructions=2048)
                    rows = native.db.execute('SELECT address,bytes FROM instructions WHERE version=1 AND context=? '
                                             'AND address>=? AND address<? ORDER BY address',
                                             (context, f'{linear:016x}', f'{linear + food["size"]:016x}')).fetchall()
                    if sum(len(bytes.fromhex(r['bytes'])) for r in rows) == food['size']:
                        break
                if sum(len(bytes.fromhex(r['bytes'])) for r in rows) != food['size']:
                    raise ValueError('bounded analysis has not stored the complete food update')
                snap = native.disassembly(address=address, lines=len(rows), version=1)
                exports = [render_snapshot(snap, output / (edition + '-food.' + fmt), fmt) for fmt in ('svg', 'png')]
                version1 = native.version(1)['sha256']
                original_regions = [(r.start, r.data) for r in native.regions(1)]
                old = images[edition]['module'][food['module_offset'] + 1]
                isolation_path = output / (edition + '-isolation.fdb')
                with sqlite3.connect(isolation_path) as isolated:
                    native.db.backup(isolated)
                with Project(isolation_path) as isolated:
                    child = isolated.patch(linear + 1, f'{old ^ 1:02x}', version=1,
                                           label='diagnostic mapped-child isolation',
                                           origin='isolation check only; no executable file write or execution')
                    assert isolated.version(1)['sha256'] == version1
                    assert [(r.start, r.data) for r in isolated.regions(1)] == original_regions
                assert native.version(1)['sha256'] == version1
                assert [(r.start, r.data) for r in native.regions(1)] == original_regions
                assert len(native.versions()) == 1
                for family in FAMILIES:
                    native.snippet_info(mappings[(edition, family)]['document']['analysis_endpoint']['id'])
                if edition != baseline:
                    for family in FAMILIES:
                        source_endpoint = mappings[(baseline, family)]['document']['analysis_endpoint']
                        target_endpoint = mappings[(edition, family)]['document']['analysis_endpoint']
                        transfer = next(t for t in transfers if t['family'] == family and t['target_edition'] == edition)
                        link = native.link_snippets([source_endpoint], [target_endpoint],
                            kind='cross-edition-build-correspondence',
                            domain=dict(program='CivD DOS Civilization', source_edition=baseline, target_edition=edition,
                                        source_mapping=mappings[(baseline, family)]['id'],
                                        target_mapping=mappings[(edition, family)]['id']),
                            evidence=dict(source_map_transfer=transfer['id']),
                            assurance='independently-build-checked static correspondence',
                            unknowns=['No semantic equivalence or UDL layer admission; source names are reconstructed.'])
                        native_links.append(dict(edition=edition, family=family, id=link['id']))
                observations.append(dict(edition=edition, stored_food_instructions=len(rows), exports=exports,
                                         original_version_sha256=version1, child_version=child,
                                         isolation_project=isolation_path.name, canonical_project_version=1,
                                         parent_bytes_preserved=True, remaining_analysis_stable=status['stable']))
            with Project(project) as reopened:
                assert reopened.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not db.db.execute('PRAGMA foreign_key_check').fetchall()
    with SourceCatalog(output / 'source-native.sqlite') as reopened:
        assert reopened.native_maps()['total'] == 18 and reopened.map_transfers()['total'] == 12
    originals_after = {p: sha(Path(p).read_bytes()) for p in originals_before}
    assert originals_before == originals_after
    result = dict(schema='fdisbull-civd-native-links-1', specs=specs, witnesses=witnesses,
                  builds=builds, maps=[dict(edition=e, family=f, **m) for (e, f), m in mappings.items()],
                  transfers=transfers, native_snippet_links=native_links, observations=observations,
                  static_call_sites=call_sites, food_stock_source_relations=stock_links,
                  reference_decoder_sha256=sha(Path(reference).read_bytes()), originals_before=originals_before,
                  originals_after=originals_after, restart_verified=True, sqlite_integrity='ok',
                  native_game_execution=False, source_assisted=True,
                  scope='Build-checked resident source/native correspondences and independently requalified transfers; '
                        'not gameplay, historical symbol names, whole-game recovery or semantic equivalence.')
    (output / 'report.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(dict(output=str(output), builds=len(builds), maps=len(mappings), transfers=len(transfers),
                          native_snippet_links=len(native_links), original_hashes_unchanged=True), indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('catalog', 'manifest', 'output', 'reference'):
        p.add_argument('--' + name, required=True)
    a = p.parse_args()
    run(a.catalog, a.manifest, a.output, a.reference)
