"""Authored mapping journals: no guest launch or claimed native observations."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import re

import pytest

from fdisbull.project import Project
from fdisbull.le import load_le
from test_le_loader import le_file


RAW = bytes(range(256)) * 32
EVIDENCE = {
    'kind': 'modeled',
    'reference': 'authored-test:runtime-layout',
    'sha256': hashlib.sha256(b'authored runtime layout evidence').hexdigest(),
    'note': 'An authored model, not an emulator observation.',
}


def evidence(label='default', kind='modeled'):
    return dict(EVIDENCE, reference='authored-test:'+label, kind=kind)


@pytest.fixture
def project(tmp_path):
    source = tmp_path/'authored.bin'
    source.write_bytes(RAW)
    with Project.create(tmp_path/'authored.fdb', source, arch='x86', bits=32, base=0, entry=0) as p:
        yield p


def start(p, external='dos-task-7', run='modeled-run-1', **kwargs):
    r = p.runtime_task_start(run, external, evidence('task-start'), **kwargs)
    assert isinstance(r['task'], str) and re.fullmatch(r'task:[0-9a-f]{32}', r['task'])
    assert type(r['event']) is int and r['event'] > 0
    assert r['identity']['id'] == r['task']
    assert r['guest_modified'] is False
    return r


def bind(p, task, *, object_id='region:0', object_offset=0, length=16,
         linear_start=0x1000, **kwargs):
    r = p.runtime_map(task, object_id, object_offset, length, linear_start,
                      evidence('map'), **kwargs)
    assert isinstance(r['binding'], str) and re.fullmatch(r'mapping:[0-9a-f]{32}', r['binding'])
    assert type(r['event']) is int
    assert r['task'] == task and r['guest_modified'] is False
    return r


def journal_state(p, task):
    # Queries are part of the public surface; failed mutations must change neither.
    return deepcopy(p.runtime_mappings(task)), deepcopy(p.runtime_mapping_events(task))


def assert_refused_without_event(p, task, operation):
    before = journal_state(p, task)
    with pytest.raises(ValueError):
        operation()
    assert journal_state(p, task) == before


def test_source_version_task_identity_and_linear_translation(project):
    p = project
    original = p.version(1)
    t = start(p, capture_epoch='authored-epoch-1')
    task = t['task']
    identity = t['identity']
    assert identity['run'] == 'modeled-run-1' and identity['external_id'] == 'dos-task-7'
    assert identity['source_sha256'] == hashlib.sha256(RAW).hexdigest()
    assert identity['version'] == 1 and identity['version_sha256'] == original['sha256']
    assert identity['started'] == t['event'] and identity['ended'] is None
    m = bind(p, task, object_offset=7, length=23, linear_start=0x4000)
    view = p.runtime_mappings(task)
    assert view['at'] == m['event'] and view['task']['id'] == task
    b = view['bindings'][0]
    assert b['id'] == m['binding'] and b['object_id'] == 'region:0'
    assert b['object_offset'] == 7 and b['length'] == 23 and b['opened'] == m['event']
    assert b['closed'] is None and b['restored_from'] is None
    assert b['source_sha256'] == identity['source_sha256']
    match = p.runtime_resolve(task, 0x4005)['matches'][0]
    assert match['object_offset'] == 12 and match['preferred_address'] == 12
    assert match['linear_address'] == 0x4005 and match['physical_address'] is None
    assert not p.runtime_resolve(task, 0x3fff)['matches']
    assert not p.runtime_resolve(task, 0x4017)['matches']
    assert p.version(1) == original
    assert p._live_debuggers == []
    assert p.source_info(1)['identity']['sha256'] == hashlib.sha256(RAW).hexdigest()


def test_physical_aliases_and_preferred_reverse_lookup_return_every_relation(project):
    p = project; task = start(p)['task']
    a = bind(p, task, object_offset=0, linear_start=0x1000, physical_start=0x9000)
    b = bind(p, task, object_offset=0, linear_start=0x2000, physical_start=0x9000)
    physical = p.runtime_resolve(task, 0x9006, space='physical')
    assert {x['id'] for x in physical['matches']} == {a['binding'], b['binding']}
    assert {x['linear_address'] for x in physical['matches']} == {0x1006, 0x2006}
    assert {x['object_offset'] for x in physical['matches']} == {6}
    reverse = p.runtime_resolve(task, 6, space='preferred')
    assert {x['id'] for x in reverse['matches']} == {a['binding'], b['binding']}
    assert len(p.runtime_resolve(task, 0x1006)['matches']) == 1
    assert not p.runtime_resolve(task, 0x9010, space='physical')['matches']


def test_physical_alias_of_different_source_offsets_is_explicitly_ambiguous(project):
    p = project; task = start(p)['task']
    bind(p, task, object_offset=0, linear_start=0x1000, physical_start=0x9000)
    bind(p, task, object_offset=64, linear_start=0x2000, physical_start=0x9000)
    found = p.runtime_resolve(task, 0x9003, space='physical')
    assert found['ambiguous'] is True
    assert {x['object_offset'] for x in found['matches']} == {3, 67}


def test_le_objects_have_independent_runtime_deltas(tmp_path):
    source = tmp_path/'authored-le.exe'
    source.write_bytes(le_file(code=b'\xb8\x01\x00\x00\x00\xc3', data=b'\xb8\x02\x00\xc3',
                              fixups=[b'', b''], object_bases=(0x10000, 0x60000),
                              object_flags=(0x2045, 0x2045)))
    with Project.create(tmp_path/'le.fdb', source) as p:
        catalog={x['id']:x for x in p.runtime_objects()['objects']}
        assert catalog['le:1']['bits']==32 and catalog['le:2']['bits']==32
        assert not any(key.startswith('region:') for key in catalog)
        task = start(p)['task']
        bind(p, task, object_id=1, length=6, linear_start=0x1b8000)
        bind(p, task, object_id=2, length=4, linear_start=0x1ff000)
        one = p.runtime_resolve(task, 0x1b8002)['matches'][0]
        two = p.runtime_resolve(task, 0x1ff002)['matches'][0]
        assert one['object_id'] == 'le:1' and two['object_id'] == 'le:2'
        assert one['preferred_address'] == 0x10002 and two['preferred_address'] == 0x60002
        assert one['linear_address'] - one['preferred_address'] != two['linear_address'] - two['preferred_address']
        assert_refused_without_event(p, task, lambda: bind(p, task, object_id=3, linear_start=0x300000))
        assert_refused_without_event(p, task, lambda: bind(p, task, object_id=True, linear_start=0x300000))


def test_selector_is_declared_base_plus_offset_not_real_mode_paragraph_math(project):
    p = project; task = start(p)['task']
    desc = {'value':0x170, 'base':0x400000, 'limit':0xffff, 'bits':16}
    context = {'domain':'authored-protected-task', 'paging':{'cr3':0x1000}}
    m = bind(p, task, object_offset=0x100, length=32, linear_start=0x400100,
             selector=desc, mapping_context=context)
    desc['base'] = 0; context['paging']['cr3'] = 0
    current = p.runtime_mappings(task)['bindings'][0]
    assert current['selector']['base'] == 0x400000
    assert current['mapping_context']['paging']['cr3'] == 0x1000
    found = p.runtime_resolve(task, 0x108, space='selector', selector=0x170)['matches']
    assert len(found) == 1 and found[0]['id'] == m['binding']
    assert found[0]['linear_address'] == 0x400108 and found[0]['object_offset'] == 0x108
    assert not p.runtime_resolve(task, 0x108, space='selector', selector=0x178)['matches']
    assert not p.runtime_resolve(task, 0x10000, space='selector', selector=0x170)['matches']
    assert not p.runtime_resolve(task, 0x170*16+0x108)['matches']


def test_explicit_replacement_is_atomic_and_preserves_history(project):
    p = project; task = start(p)['task']
    old = bind(p, task)
    independent = bind(p, task, object_offset=32, linear_start=0x2000)
    assert_refused_without_event(p, task, lambda: bind(p, task, linear_start=0x1008, length=8))
    new = bind(p, task, object_offset=64, linear_start=0x1008, length=8, replace=[old['binding']])
    assert {x['id'] for x in p.runtime_mappings(task)['bindings']} == {new['binding'], independent['binding']}
    previous = p.runtime_mappings(task, at=independent['event'])['bindings']
    assert {x['id'] for x in previous} == {old['binding'], independent['binding']}
    old_record = next(x for x in previous if x['id'] == old['binding'])
    assert old_record['closed'] == new['event']
    assert p.runtime_resolve(task, 0x1008, at=old['event'])['matches'][0]['object_offset'] == 8
    assert p.runtime_resolve(task, 0x1008, at=new['event'])['matches'][0]['object_offset'] == 64
    assert not p.runtime_resolve(task, 0x1000)['matches']


def test_replacement_must_name_every_overlap_and_invalid_replacement_rolls_back(project):
    p = project; task = start(p)['task']
    a = bind(p, task, linear_start=0x1000, length=8)
    b = bind(p, task, linear_start=0x1008, object_offset=8, length=8)
    assert_refused_without_event(p, task, lambda: bind(p, task, length=16, replace=[a['binding']]))
    assert_refused_without_event(p, task, lambda: bind(p, task, length=16, replace=[a['binding'], 'mapping:'+('0'*32)]))
    assert_refused_without_event(p, task, lambda: bind(p, task, length=16, replace=[a['binding'], a['binding']]))
    c = bind(p, task, length=16, object_offset=32, replace=[a['binding'], b['binding']])
    assert [x['id'] for x in p.runtime_mappings(task)['bindings']] == [c['binding']]


def test_unmap_task_end_and_external_identity_reuse_do_not_inherit_bindings(project):
    p = project; old = start(p); task = old['task']
    m = bind(p, task)
    ended = p.runtime_task_end(task, evidence('task-end'))
    assert ended['guest_modified'] is False
    assert not p.runtime_mappings(task)['bindings']
    assert p.runtime_mappings(task)['task']['ended'] == ended['event']
    assert p.runtime_resolve(task, 0x1001, at=m['event'])['matches']
    assert not p.runtime_resolve(task, 0x1001)['matches']
    for operation in (
        lambda: bind(p, task), lambda:p.runtime_unmap(task,[m['binding']],evidence()),
        lambda:p.runtime_map_checkpoint(task,evidence()), lambda:p.runtime_task_end(task,evidence()),
    ):
        assert_refused_without_event(p, task, operation)
    new = start(p)
    assert new['task'] != task and new['event'] > ended['event']
    assert not p.runtime_mappings(new['task'])['bindings']


def test_active_external_identity_is_unique_per_run_not_global(project):
    p = project; task = start(p)['task']
    assert_refused_without_event(p, task, lambda:start(p))
    other = start(p, run='different-modeled-run')['task']
    assert other != task
    # Separate task incarnations can use identical numeric address ranges.
    bind(p, task)
    bind(p, other)
    assert len(p.runtime_mappings(task)['bindings']) == len(p.runtime_mappings(other)['bindings']) == 1


def test_checkpoint_restore_creates_new_bindings_and_does_not_rewrite_history(project):
    p = project; task = start(p)['task']
    a = bind(p, task, object_offset=16, linear_start=0x1000, physical_start=0x8000)
    b = bind(p, task, object_offset=64, linear_start=0x2000, physical_start=0x8000)
    cp = p.runtime_map_checkpoint(task, evidence('checkpoint'))
    assert re.fullmatch(r'checkpoint:[0-9a-f]{32}', cp['checkpoint'])
    unmapped = p.runtime_unmap(task, [a['binding']], evidence('unmap'))
    c = bind(p, task, object_offset=128, linear_start=0x3000)
    restored = p.runtime_map_restore(task, cp['checkpoint'], evidence('restore'))
    current = p.runtime_mappings(task)['bindings']
    assert {x['id'] for x in current} == set(restored['bindings'])
    assert not {a['binding'],b['binding'],c['binding']} & set(restored['bindings'])
    assert {x['restored_from'] for x in current} == {a['binding'], b['binding']}
    assert all(x['opened'] == restored['event'] and x['closed'] is None for x in current)
    assert {x['id'] for x in p.runtime_mappings(task,at=cp['event'])['bindings']} == {a['binding'],b['binding']}
    assert {x['id'] for x in p.runtime_mappings(task,at=unmapped['event'])['bindings']} == {b['binding']}
    assert {x['object_offset'] for x in p.runtime_resolve(task,0x8003,space='physical')['matches']} == {19,67}
    assert restored['guest_modified'] is False and p._live_debuggers == []


def test_empty_checkpoint_restore_and_task_foreign_checkpoint_refusal(project):
    p = project; task = start(p)['task']
    empty = p.runtime_map_checkpoint(task,evidence('empty'))
    m = bind(p,task)
    other = start(p,external='task-other')['task']
    assert_refused_without_event(p, other, lambda:p.runtime_map_restore(other,empty['checkpoint'],evidence()))
    assert_refused_without_event(p, other, lambda:p.runtime_unmap(other,[m['binding']],evidence()))
    p.runtime_map_restore(task,empty['checkpoint'],evidence('restore-empty'))
    assert p.runtime_mappings(task)['bindings'] == []
    p.runtime_task_end(task,evidence('end'))
    assert_refused_without_event(p, task, lambda:p.runtime_map_restore(task,empty['checkpoint'],evidence()))


def test_reopen_keeps_history_and_checkpoint_without_original_file(tmp_path):
    source=tmp_path/'authored.bin';source.write_bytes(RAW)
    with Project.create(tmp_path/'reopen.fdb',source,arch='x86',bits=32,base=0,entry=0) as p:
        task=start(p)['task'];first=bind(p,task)
        cp=p.runtime_map_checkpoint(task,evidence('checkpoint'))
        p.runtime_unmap(task,[first['binding']],evidence('unmap'))
        before=p.runtime_mapping_events(task);path=p.path
    source.unlink()
    with Project(path) as reopened:
        assert reopened.runtime_mapping_events(task)==before
        assert reopened.runtime_mappings(task)['bindings']==[]
        restored=reopened.runtime_map_restore(task,cp['checkpoint'],evidence('reopen-restore'))
        assert len(restored['bindings'])==1
        assert reopened.runtime_mappings(task)['bindings'][0]['restored_from']==first['binding']
        assert reopened.source_info(1)['identity']['sha256']==hashlib.sha256(RAW).hexdigest()


def test_patch_version_isolation_and_source_bytes_never_change(project):
    p=project; task=start(p)['task']; original=bind(p,task)
    old_hash=p.version(1)['sha256']; source_hash=p.source_info(1)['identity']['sha256']
    child=p.patch(0,'90')['version']
    newer=start(p,external='task-v2',run='modeled-run-2',version=child)
    assert newer['identity']['version']==child and newer['identity']['version_sha256']!=old_hash
    assert p.runtime_mappings(newer['task'])['bindings']==[]
    assert p.runtime_mappings(task)['task']['version']==1
    assert p.runtime_mappings(task)['bindings'][0]['id']==original['binding']
    bind(p,newer['task'],object_offset=16,linear_start=0x2000)
    assert p.runtime_resolve(task,0x1000)['matches'][0]['version_sha256']==old_hash
    assert p.runtime_resolve(newer['task'],0x2000)['matches'][0]['version_sha256']==p.version(child)['sha256']
    assert p.version(1)['sha256']==old_hash and p.source_info(1)['identity']['sha256']==source_hash


def test_local_run_version_mismatch_is_refused_without_journal_writes(project):
    p=project
    with p.transaction(True):
        p.db.execute('INSERT INTO debug_runs VALUES (?,?,?,?,?,?)',
                     ('authored-local-run',1,'2000-01-01T00:00:00Z',None,'stopped',json.dumps({'fixture':'modeled row, not native execution'})))
    child=p.patch(0,'90')['version']
    before=p.db.execute('SELECT count(*) FROM runtime_mapping_events').fetchone()[0]
    with pytest.raises(ValueError,match='different code version'):
        start(p,run='authored-local-run',version=child)
    assert p.db.execute('SELECT count(*) FROM runtime_mapping_events').fetchone()[0]==before
    identity=start(p,run='authored-local-run',version=1)['identity']
    assert identity['run_reference']=='local-debug-run'


def test_history_event_cursor_and_query_limits_are_explicit(project):
    p=project; task=start(p)['task']
    for i in range(4):bind(p,task,object_offset=i*16,linear_start=0x1000+i*0x100)
    all_events=p.runtime_mapping_events(task)['events']
    assert [x['sequence'] for x in all_events]==sorted({x['sequence'] for x in all_events})
    first=p.runtime_mapping_events(task,limit=2)
    assert first['events']==all_events[:2] and first['truncated'] is True
    second=p.runtime_mapping_events(task,after=first['next_after'],limit=2)
    assert second['events']==all_events[2:4]
    assert p.runtime_mapping_events(task,after=all_events[-1]['sequence'])['events']==[]
    view=p.runtime_mappings(task,offset=1,limit=2)
    assert view['count']==4 and len(view['bindings'])==2 and view['truncated'] is True
    assert 'not proof' in view['validity']
    for call in (
        lambda:p.runtime_mapping_events(task,limit=0),lambda:p.runtime_mapping_events(task,limit=1001),
        lambda:p.runtime_mapping_events(task,after=-1),lambda:p.runtime_mapping_events(task,after=True),
        lambda:p.runtime_mappings(task,limit=4097),lambda:p.runtime_mappings(task,offset=-1),
        lambda:p.runtime_mappings(task,at=0),lambda:p.runtime_mappings(task,at=all_events[-1]['sequence']+100),
    ):
        assert_refused_without_event(p,task,call)


@pytest.mark.parametrize('change',[
    {'object_id':'region:deadbeef'},{'object_id':True},{'object_offset':-1},{'object_offset':True},
    {'object_offset':len(RAW),'length':1},{'length':0},{'length':-1},{'length':True},
    {'length':16*1024*1024+1},{'linear_start':-1},{'linear_start':True},
    {'linear_start':1<<64},{'linear_start':(1<<64)-1,'length':2},
    {'physical_start':-1},{'physical_start':True},{'physical_start':(1<<64)-1,'length':2},
    {'mapping_context':[]},{'mapping_context':{'bad':float('nan')}},
    {'mapping_context':{'oversized':'x'*17000}}, {'replace':'mapping:wrong'},
])
def test_bad_mapping_validation_is_transactional(project,change):
    p=project; task=start(p)['task']
    assert_refused_without_event(p,task,lambda:bind(p,task,**change))


@pytest.mark.parametrize('bad',[
    None,{},'evidence',{'kind':'native','reference':'x','sha256':'0'*64},
    {'kind':'modeled','reference':' ','sha256':'0'*64},
    {'kind':'modeled','reference':'x','sha256':'0'*63},
    {'kind':'recorded','reference':'x','sha256':'g'*64},
    {'kind':'modeled','reference':'x','sha256':'0'*64,'note':False},
    {'kind':'modeled','reference':'x','sha256':'0'*64,'extra':'unbounded'},
])
def test_evidence_required_and_failed_validation_never_creates_an_event(project,bad):
    p=project; task=start(p)['task']
    assert_refused_without_event(p,task,lambda:p.runtime_map(task,'region:0',0,1,0x1000,bad))
    assert_refused_without_event(p,task,lambda:p.runtime_task_start('run-x','task-x',bad))


@pytest.mark.parametrize('desc',[
    {},{'value':0x170,'base':0,'limit':0xffff,'bits':8},
    {'value':65536,'base':0,'limit':0xffff,'bits':16},
    {'value':True,'base':0,'limit':0xffff,'bits':16},
    {'value':0x170,'base':-1,'limit':0xffff,'bits':16},
    {'value':0x170,'base':0,'limit':-1,'bits':16},
    {'value':0x170,'base':0,'limit':0xff,'bits':16},
    {'value':0x170,'base':0x2000,'limit':0xffff,'bits':16},
])
def test_selector_validation_and_extent_limits(project,desc):
    p=project; task=start(p)['task']
    assert_refused_without_event(p,task,lambda:bind(p,task,selector=desc))


def test_address_domain_edges_and_unsupported_queries(project):
    p=project; task=start(p)['task']
    top=(1<<64)-1
    bind(p,task,length=1,linear_start=top,physical_start=top)
    assert p.runtime_resolve(task,top)['matches'][0]['object_offset']==0
    assert p.runtime_resolve(task,top,space='physical')['matches']
    for call in (
        lambda:p.runtime_resolve(task,-1),lambda:p.runtime_resolve(task,True),
        lambda:p.runtime_resolve(task,1<<64),lambda:p.runtime_resolve(task,0,space='segmented'),
        lambda:p.runtime_resolve(task,0,space='selector'),
        lambda:p.runtime_resolve(task,0,selector=0x170),
    ):
        assert_refused_without_event(p,task,call)


def test_checkpoint_serialization_supports_the_declared_active_binding_capacity(project):
    p=project;task=start(p)['task']
    first=bind(p,task,length=1)
    original=p.runtime_mappings(task)['bindings'][0]
    # Seed an authored storage fixture at the public capacity without making
    # quadratic public overlap scans part of an ordinary unit test. Every
    # extent has valid object bounds and a distinct, nonoverlapping linear byte.
    rows=[]
    for i in range(1,4096):
        document={k:deepcopy(v) for k,v in original.items() if k not in ('opened','closed')}
        identifier='mapping:'+format(i,'032x')
        document.update(id=identifier,object_offset=i,preferred_start=i,linear_start=0x1000+2*i)
        rows.append((identifier,task,first['event'],None,json.dumps(document)))
    with p.transaction(True):
        p.db.executemany('INSERT INTO runtime_mapping_bindings VALUES (?,?,?,?,?)',rows)
    assert p.runtime_mappings(task,limit=4096)['count']==4096
    assert_refused_without_event(p,task,lambda:bind(p,task,length=1,linear_start=0x800000))
    checkpoint=p.runtime_map_checkpoint(task,evidence('maximum-capacity-checkpoint'))
    assert re.fullmatch(r'checkpoint:[0-9a-f]{32}',checkpoint['checkpoint'])
    assert p.runtime_mappings(task,at=checkpoint['event'],limit=4096)['count']==4096


def test_legacy_uniform_le_catalog_uses_retained_object_flags(tmp_path):
    # Old released LE projects have no decode_regions and no object.bits.
    # Their declared flags still retain the default width of each object.
    image=load_le(le_file())
    metadata=deepcopy(image.metadata)
    metadata.pop('decode_regions', None)
    for obj in metadata['le']['objects']:obj.pop('bits', None)
    with Project._create_image(tmp_path/'legacy-le.fdb','authored.exe',replace(image,metadata=metadata)) as p:
        assert int(p.db.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()[0])==9
        assert p.meta['loader_metadata'].get('decode_regions', [])==[]
        objects=p.runtime_objects()['objects']
        assert {obj['id']:obj['bits'] for obj in objects}=={'le:1':32,'le:2':32}
        task=start(p)['task']
        bind(p,task,object_id=1,length=6,linear_start=0x800000)
        assert p.runtime_resolve(task,0x800001)['matches'][0]['preferred_address']==0x10001
