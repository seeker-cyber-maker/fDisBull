"""Source/capture identity tests; authored artifacts do not claim native execution."""
import hashlib
import json

import pytest

from fdisbull.memory_search import snapshot_metadata
from fdisbull.project import Project
from test_le_mixed_loader import bound_le, mixed_le


EVIDENCE = dict(kind='modeled', reference='authored-fixture', sha256='ab' * 32)


def capture(project, raw, *, run='authored-run', version=1, start=0x123400,
            source_sha=None, task='counter', epoch='incarnation-1', pages=None, **updates):
    if not project.db.execute('SELECT 1 FROM debug_runs WHERE id=?', (run,)).fetchone():
        with project.transaction(True):
            project.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                               (run, version, 'authored', None, 'closed', '{}'))
    context = dict(source_sha256=source_sha or project.source_sha256(version),
                   version_id=version, version_sha256=project.version(version)['sha256'],
                   run_id=run, address_space='linear', region=dict(start=start, length=len(raw)),
                   task_id=task, capture_epoch=epoch)
    mapping = dict(kind='authored-map', allocation_identity='unqualified')
    if pages is not None:
        pages_raw = json.dumps(pages, sort_keys=True, separators=(',', ':')).encode()
        mapping = dict(kind='observed-386-pages', pages_sha256=hashlib.sha256(pages_raw).hexdigest(),
                       page_count=len(pages))
    canonical = json.dumps(mapping, sort_keys=True, separators=(',', ':')).encode()
    context['mapping_id'] = hashlib.sha256(canonical).hexdigest()
    context.update(updates)
    metadata = dict(snapshot=snapshot_metadata(raw, context=context, capture_id='authored-capture'),
                    capture=dict(mapping=mapping, pages=pages or []))
    return project._debug_artifact(run, 'authored.bin', 'memory-snapshot', raw, metadata)['artifact']


@pytest.fixture
def raw_project(tmp_path):
    target = tmp_path / 'fixture.bin'
    target.write_bytes(bytes(range(256)) * 32)
    with Project.create(tmp_path / 'fixture.fdb', target, arch='x86', bits=32) as project:
        yield project


def test_snapshot_extent_not_entire_object_and_reopen(raw_project):
    p = raw_project
    data = p.regions(1)[0].data[8:24]
    task = p.runtime_task_start('authored-run', 'counter', EVIDENCE, capture_epoch='incarnation-1')['task']
    snap = capture(p, data)
    receipt = p.runtime_map_snapshot(task, snap, 'region:0', 8, 16)
    rows = p.runtime_mappings(task)['bindings']
    assert rows[0]['id'] == receipt['binding']
    assert rows[0]['compared_bytes'] == 16
    assert rows[0]['physical_start'] is None
    assert 'ownership remains caller-declared' in rows[0]['qualification']
    assert p.runtime_resolve(task, 0x12340f)['matches'][0]['object_offset'] == 23
    assert p.runtime_resolve(task, 0x123410)['matches'] == []
    with Project(p.path) as reopened:
        assert reopened.runtime_mappings(task)['bindings'] == rows


@pytest.mark.parametrize('change', ['bytes', 'source', 'run', 'task', 'epoch', 'version_sha', 'extent', 'foreign'])
def test_snapshot_mismatches_do_not_publish_bindings_or_events(raw_project, change):
    p = raw_project
    task = p.runtime_task_start('authored-run', 'counter', EVIDENCE, capture_epoch='incarnation-1')['task']
    expected = p.regions(1)[0].data[:16]
    options = {}
    if change == 'source': options['source_sha'] = 'cd' * 32
    if change == 'run': options['run'] = 'other-run'
    if change == 'task': options['task'] = 'other-task'
    if change == 'epoch': options['epoch'] = 'incarnation-2'
    if change == 'version_sha': options['version_sha256'] = 'cd' * 32
    snap = capture(p, bytes(16) if change == 'bytes' else expected, **options)
    if change == 'foreign': snap = 'not-a-local-artifact'
    before = p.runtime_mapping_events(task)
    with pytest.raises(ValueError):
        p.runtime_map_snapshot(task, snap, 'region:0', 0, 17 if change == 'extent' else 16)
    assert p.runtime_mapping_events(task) == before
    assert p.runtime_mappings(task)['bindings'] == []


def test_mz_owns_capture_but_le_object_keys_are_distinct(tmp_path):
    target = tmp_path / 'bound.exe'
    original = bound_le(mixed_le())
    target.write_bytes(original)
    with Project.create(tmp_path / 'mz.fdb', target, image='mz') as p:
        catalog = p.runtime_objects()
        assert catalog['version_sha256'] == p.version(1)['sha256']
        bridge = next(o for o in catalog['objects'] if o['id'] == 'le:2')
        assert bridge['source_view'] == 'le' and bridge['preferred_start'] == 0x60000
        assert bridge['bits'] == 16
        # Synthetic LE second object has source B8 imm16 then RET. The two
        # immediate bytes are a declared symbolic fixup, never a caller mask.
        task = p.runtime_task_start('authored-run', 'counter', EVIDENCE, capture_epoch='incarnation-1')['task']
        snap = capture(p, bytes.fromhex('b81234c3'))
        p.runtime_map_snapshot(task, snap, 'le:2', 0, 4)
        binding = p.runtime_mappings(task)['bindings'][0]
        assert binding['compared_bytes'] == 2 and binding['excluded_fixup_bytes'] == 2
        assert binding['preferred_start'] == 0x60000
        assert binding['version_sha256'] == catalog['version_sha256']
        fixup_only = capture(p, b'\x12\x34')
        before = p.runtime_mapping_events(task)
        with pytest.raises(ValueError, match='no independently comparable'):
            p.runtime_map_snapshot(task, fixup_only, 'le:2', 1, 2, replace=[binding['id']])
        assert p.runtime_mapping_events(task) == before
    assert target.read_bytes() == original


def test_source_byte_mismatch_outside_fixup_is_rejected(tmp_path):
    target = tmp_path / 'mixed.exe'
    target.write_bytes(mixed_le())
    with Project.create(tmp_path / 'le.fdb', target, image='le') as p:
        task = p.runtime_task_start('authored-run', 'counter', EVIDENCE, capture_epoch='incarnation-1')['task']
        snap = capture(p, bytes.fromhex('901234c3'))
        with pytest.raises(ValueError, match='do not match'):
            p.runtime_map_snapshot(task, snap, 2, 0, 4)


def test_le_generic_region_alias_cannot_bypass_object_guards(tmp_path):
    target = tmp_path / 'mixed.exe'
    target.write_bytes(mixed_le())
    with Project.create(tmp_path / 'le.fdb', target, image='le') as p:
        assert all(o['id'].startswith('le:') for o in p.runtime_objects()['objects'])
        task = p.runtime_task_start('authored-run', 'counter', EVIDENCE, capture_epoch='incarnation-1')['task']
        snap = capture(p, bytes.fromhex('b81234c3'))
        with pytest.raises(ValueError, match='unknown source object'):
            p.runtime_map_snapshot(task, snap, 'region:60000', 0, 4)
        assert p.runtime_mappings(task)['bindings'] == []


def test_mz_allocation_padding_is_not_a_file_witness(tmp_path):
    import struct
    # One byte of file-backed code, paragraph padding and extra allocation.
    header = bytearray(64)
    struct.pack_into('<14H', header, 0, 0x5a4d, 65, 1, 0, 4, 1, 0xffff,
                     0, 0, 0, 0, 0, 64, 0)
    target = tmp_path / 'allocation.exe'
    target.write_bytes(bytes(header) + b'\xc3')
    with Project.create(tmp_path / 'mz.fdb', target, image='mz') as p:
        obj = p.runtime_objects()['objects'][0]
        assert obj['length'] > 1
        task = p.runtime_task_start('authored-run', 'counter', EVIDENCE, capture_epoch='incarnation-1')['task']
        snap = capture(p, bytes(8))
        with pytest.raises(ValueError, match='unbacked source bytes'):
            p.runtime_map_snapshot(task, snap, obj['id'], 1, 8)
        assert p.runtime_mappings(task)['bindings'] == []


def test_reused_task_number_cannot_adopt_older_snapshot(raw_project):
    p = raw_project
    task = p.runtime_task_start('authored-run', 'counter', EVIDENCE, capture_epoch='incarnation-1')['task']
    snap = capture(p, p.regions(1)[0].data[:16])
    p.runtime_map_snapshot(task, snap, 'region:0', 0, 16)
    p.runtime_task_end(task, EVIDENCE)
    new_task = p.runtime_task_start('authored-run', 'counter', EVIDENCE, capture_epoch='incarnation-1')['task']
    with pytest.raises(ValueError, match='predates this task incarnation'):
        p.runtime_map_snapshot(new_task, snap, 'region:0', 0, 16)
    fresh = capture(p, p.regions(1)[0].data[:16])
    p.runtime_map_snapshot(new_task, fresh, 'region:0', 0, 16)


@pytest.mark.parametrize('second_physical,expected', [(0x871000, 0x870ff0), (0x880000, None)])
def test_physical_extent_requires_contiguous_observed_pages(raw_project, second_physical, expected):
    p = raw_project
    task = p.runtime_task_start('authored-run', 'counter', EVIDENCE, capture_epoch='incarnation-1')['task']
    pages = [dict(linear='0x123000', physical='0x870000', entries=[]),
             dict(linear='0x124000', physical=hex(second_physical), entries=[])]
    snap = capture(p, p.regions(1)[0].data[:32], start=0x123ff0, pages=pages)
    p.runtime_map_snapshot(task, snap, 'region:0', 0, 32)
    assert p.runtime_mappings(task)['bindings'][0]['physical_start'] == expected


def test_duplicate_page_evidence_does_not_choose_one_alias(raw_project):
    p = raw_project
    task = p.runtime_task_start('authored-run', 'counter', EVIDENCE, capture_epoch='incarnation-1')['task']
    pages = [dict(linear='0x123000', physical='0x870000', entries=[]),
             dict(linear='0x123000', physical='0x880000', entries=[])]
    snap = capture(p, p.regions(1)[0].data[:16], pages=pages)
    with pytest.raises(ValueError, match='ambiguous duplicate'):
        p.runtime_map_snapshot(task, snap, 'region:0', 0, 16)
    assert p.runtime_mappings(task)['bindings'] == []


def test_page_map_must_match_the_sealed_capture_context(raw_project):
    p = raw_project
    task = p.runtime_task_start('authored-run', 'counter', EVIDENCE, capture_epoch='incarnation-1')['task']
    pages = [dict(linear='0x123000', physical='0x870000', entries=[])]
    snap = capture(p, p.regions(1)[0].data[:16], pages=pages)
    row = p.db.execute('SELECT metadata FROM debug_artifacts WHERE id=?', (snap,)).fetchone()
    metadata = json.loads(row[0])
    metadata['capture']['pages'][0]['physical'] = '0x880000'
    with p.transaction(True):
        p.db.execute('UPDATE debug_artifacts SET metadata=? WHERE id=?', (json.dumps(metadata), snap))
    with pytest.raises(ValueError, match='page evidence differs'):
        p.runtime_map_snapshot(task, snap, 'region:0', 0, 16)
    assert p.runtime_mappings(task)['bindings'] == []
