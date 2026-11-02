"""Stored authored layouts: no original game, live pose or native claim."""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
import uuid
import zipfile

from PIL import Image
import pytest

from fdisbull.cli import invoke, parser
from fdisbull.project import Project, now
from fdisbull.scenes import encoded
from fdisbull.spatial_map import spatial_check
from test_spatial_integration import Session, action, spatial_doc


def domains(*, alerts=True):
    return {'format': 'fdisbull-coordinate-domains-1',
            'space': {'name': 'room', 'unit': 'game'},
            'bounds': {'world': [0, 0, 8, 6], 'room': [0, 0, 8, 6],
                       'collision': [0, 0, 8, 6], 'viewport': [0, 0, 4, 6]},
            'objects': [{'id': 'scroll-column', 'role': 'prefetch', 'pose': [4, 0],
                         'render': [0, 0, 1, 6], 'collision': None}],
            'expectations': [{'id': 'scroll-buffer', 'mechanism': 'scroll-prefetch',
                              'roles': ['prefetch'], 'domains': ['viewport'], 'parts': ['render'],
                              'max_margins': {'left': 0, 'top': 0, 'right': 1, 'bottom': 0},
                              'reason': 'Authored scrolling buffer, not a platform whitelist.',
                              'evidence_status': 'declared'}],
            'alerts': alerts, 'provenance': {'scope': 'Authored offline metadata only.'}}


def binary(tmp_path):
    path = tmp_path/'x.com'; path.write_bytes(bytes.fromhex('b8004ccd21'))
    return path


def scene(project):
    raw = BytesIO(); Image.new('RGB', (8, 6), 'black').save(raw, format='PNG')
    run = uuid.uuid4().hex
    with project.transaction(True):
        project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                           (run, project.version()['id'], now(), now(), 'authored', '{}'))
    snapshot = project._debug_artifact(run, 'authored.png', 'screenshot', raw.getvalue(),
                {'width': 8, 'height': 6, 'mode_id': 19, 'source_bpp': 8,
                 'double_width': False, 'double_height': False, 'source': 'authored_fixture'})
    context = {'state': 'authored layout', 'triggers': ['authored fixture']}
    return {'format': 'fdisbull-scene-1', 'width': 8, 'height': 6, 'mode_id': 19,
            'reference': snapshot['artifact'], 'context': context, 'match': {'constant': True},
            'objects': [{'name': 'button', 'context': context,
                         'area': {'rect': [0, 0, 3, 3]}, 'original_area': {'rect': [0, 0, 3, 3]},
                         'point': [1, 1], 'visible': {'constant': True}, 'ready': {'constant': True},
                         'enabled': {'constant': True}, 'action': {'kind': 'click'},
                         'outcome': {'constant': True}}]}


def test_scene_restart_and_bundle_preserve_expected_layout_and_clean_snapshot(tmp_path):
    source = binary(tmp_path); db = tmp_path/'source.fdb'; bundle = tmp_path/'scenes.zip'
    with Project.create(db, source, image='com') as p:
        doc = scene(p); doc['coordinate_domains'] = domains(); before = deepcopy(doc)
        saved = p.debug_save_scene('layout', doc)
        assert doc == before
        first = p.debug_scene_domain_audit(saved['id'])
        assert first['complete'] and first['historical_only'] and not first['live_state_verified']
        assert first['navigation_authority'] == 'none'
        assert first['audit']['summary']['dispositions']['expected'] == 1
        assert first['audit']['summary']['unknown_relations'] == 4
        p.debug_export_scenes([saved['id']], bundle)
        raw_domains = deepcopy(saved['definition']['coordinate_domains'])
    with Project(db) as p:
        assert p.debug_scene_domain_audit(saved['id']) == first
        assert p.debug_scene_info(saved['id'])['definition']['objects'][0]['original_area'] == before['objects'][0]['original_area']
        overlay = p.debug_scene_overlay(saved['id'], grid_step=None)
        p.debug_export(overlay['artifact'], tmp_path/'overlay.png')
        with Image.open(tmp_path/'overlay.png') as im: assert im.size == (8, 6)
    with Project.create(tmp_path/'import.fdb', source, image='com') as p:
        imported = p.debug_import_scenes(bundle)
        restored = p.debug_scene_info('layout')
        assert imported['historical_only'] and not imported['live_state_verified']
        assert restored['definition']['coordinate_domains'] == raw_domains
        audit = p.debug_scene_domain_audit('layout')
        assert audit['audit'] == first['audit']
        assert audit['reference'] != first['reference']
        metadata = p.debug_artifacts(run=imported['run'])['artifacts'][0]['metadata']
        assert metadata['historical_only'] is True


def test_legacy_missing_descriptor_stays_unknown_and_cli_is_offline(tmp_path):
    db = tmp_path/'x.fdb'
    with Project.create(db, binary(tmp_path), image='com') as p:
        saved = p.debug_save_scene('legacy', scene(p))
    result = invoke('debug-scene-domain-audit', {'project': str(db), 'scene': saved['id']})
    assert result['status'] == 'not_defined' and not result['complete'] and result['audit'] is None
    args = parser().parse_args(['debug-scene-domain-audit', str(db), 'legacy', '--max-checks', '1'])
    assert args.max_checks == 1


def test_map_domain_metadata_preserves_masks_candidates_and_old_revisions(tmp_path):
    path = tmp_path/'map.fdb'
    with Project.create(path, binary(tmp_path), image='com') as p:
        doc = spatial_doc(p.version()['sha256']); original = deepcopy(doc)
        plain = p.debug_save_spatial_map('room', doc)
        assert p.debug_spatial_domain_audit(plain['id'])['status'] == 'not_defined'
        doc['coordinate_domains'] = domains(alerts=False)
        saved = p.debug_save_spatial_map('room', doc, parent=plain['id'])
        before = p.debug_spatial_check(saved['id'], [4, 3])
        audit = p.debug_spatial_domain_audit(saved['id'])
        assert audit['complete'] and audit['audit']['alerts'] is False
        assert p.debug_spatial_check(saved['id'], [4, 3]) == before
        assert before == spatial_check(original, [4, 3])
        for key in ('known', 'safe', 'layers', 'actor'):
            assert saved['document'][key] == original[key]
        assert p.debug_spatial_candidates(saved['id']) == p.debug_spatial_candidates(plain['id'])
    result = invoke('debug-spatial-domain-audit', {'project': str(path), 'revision': saved['id'], 'max_checks': 1})
    assert not result['complete'] and result['audit']['summary']['count_scope'] == 'examined_only'
    with Project(path) as p:
        assert 'coordinate_domains' not in p.debug_spatial_map_info(plain['id'])['document']
        assert p.debug_spatial_map_info(saved['id'])['document']['coordinate_domains'] == doc['coordinate_domains']


@pytest.mark.parametrize('fault', ['space', 'unit', 'room', 'alerts'])
def test_invalid_map_domain_contract_is_refused_before_revision_write(tmp_path, fault):
    with Project.create(tmp_path/'map.fdb', binary(tmp_path), image='com') as p:
        doc = spatial_doc(p.version()['sha256']); doc['coordinate_domains'] = domains()
        if fault == 'space': doc['coordinate_domains']['space']['name'] = 'unconverted-pixels'
        elif fault == 'unit': doc['coordinate_domains']['space']['unit'] = 'tiles'
        elif fault == 'room': doc['coordinate_domains']['bounds']['room'][2] = 9
        else: doc['coordinate_domains']['alerts'] = 'disabled'
        with pytest.raises(ValueError): p.debug_save_spatial_map('bad', doc)


def test_expected_margin_and_disabled_alerts_do_not_authorize_guest_input(tmp_path, monkeypatch):
    with Project.create(tmp_path/'map.fdb', binary(tmp_path), image='com') as p:
        doc = spatial_doc(p.version()['sha256']); doc['coordinate_domains'] = domains(alerts=False)
        saved = p.debug_save_spatial_map('room', doc)
        session = Session(p); definition = action(saved['id'], session.version['id'])
        capture = lambda s, spec: {'complete': True, 'values': dict(s.values)}
        monkeypatch.setattr('fdisbull.spatial.capture_observations', capture)
        monkeypatch.setattr('fdisbull.spatial_modes.capture_observations', capture)
        result = session.spatial_action(saved['id'], definition, zone='item')
        assert not result['ok'] and session.presses == 0
        session.spatial_policy('physical', fair_play=True)
        session.values.update(x=0, y=0)
        result = session.spatial_action(saved['id'], definition, zone='item')
        assert not result['ok'] and session.presses == 0
        with pytest.raises(ValueError, match='Fair play'): session.spatial_policy('assisted')


def test_invalid_bundled_domain_contract_rolls_back_imported_artifacts(tmp_path):
    source = binary(tmp_path); bundle = tmp_path/'good.zip'
    with Project.create(tmp_path/'source.fdb', source, image='com') as p:
        doc = scene(p); doc['coordinate_domains'] = domains()
        saved = p.debug_save_scene('layout', doc); p.debug_export_scenes([saved['id']], bundle)
    with zipfile.ZipFile(bundle) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(entries['manifest.json'])
    item = manifest['scenes'][0]; item['definition']['coordinate_domains']['alerts'] = 'disabled'
    item['sha256'] = sha256(encoded(item['definition'])).hexdigest()
    entries['manifest.json'] = encoded(manifest)
    broken = tmp_path/'broken.zip'
    with zipfile.ZipFile(broken, 'x') as archive:
        for name, data in entries.items(): archive.writestr(name, data)
    with Project.create(tmp_path/'target.fdb', source, image='com') as p:
        with pytest.raises(ValueError): p.debug_import_scenes(broken)
        assert p.debug_scenes()['scenes'] == []
        assert p.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0] == 0
        assert p.db.execute('SELECT count(*) FROM debug_runs').fetchone()[0] == 0
