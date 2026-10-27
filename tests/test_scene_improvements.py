"""0.18 scene contracts exercised through real native observations and stored data."""
from copy import deepcopy
import io
import json
import zipfile

import pytest
from PIL import Image
from fdisbull.project import Project
from fdisbull.scenes import SceneError
from test_debugger import emulator
from test_scenes import mouse_game, definition
from test_dos_loader import mz_file


def memory_word(address='1000:0100', type='u16'):
    return {'memory':dict(address=address,type=type)}


@pytest.fixture
def counter_game(tmp_path):
    # Mode 13h, DS=CS, real BIOS keyboard read, increment a 16-bit counter.
    game=tmp_path/'game';game.mkdir();binary=game/'COUNT.EXE'
    binary.write_bytes(mz_file(bytes.fromhex('b81300cd100e1f30e4cd16ff060001ebf6')+bytes(1024),ss=0,sp=0x400))
    path=tmp_path/'counter.fdb'
    with Project.create(path,binary) as p:p.analyze(max_instructions=30)
    return path,binary


def counter_definition(snapshot):
    doc=definition(snapshot);obj=doc['objects'][0]
    obj['ready']={'constant':True};obj['action']=dict(kind='press',key='a',hold_ms=20,gap_ms=20)
    obj['outcome']={'compare':dict(left=memory_word(),op='eq',right={'add':[{'before':memory_word()},1]})}
    return doc


def test_relative_outcomes_repeat_restore_and_compact_saved_script(counter_game,emulator):
    path,binary=counter_game
    with Project(path) as p,p.debugger(emulator,binary.parent) as d:
        d.run(guest_ms=100,timeout_ms=3000,fast_forward=True)
        scene=p.debug_save_scene('counter',counter_definition(d.screenshot()))
        checkpoint=d.save_state('zero.sav')
        for expected in (1,2):
            result=d.scene_act('counter','test.button',compact=True)
            assert result['complete'] and result['status']=='matched'
            full=p.debug_scene_observation(result['observation'])['result']
            assert full['evidence'][-1]['left']==full['evidence'][-1]['right']==expected
            assert list(full['baseline']['values'].values())==[{'value':expected-1}]
        d.load_state(checkpoint['artifact'])
        assert d.scene_check('counter',compact=True)['status']=='unavailable'
        d.run(guest_ms=100,timeout_ms=3000,fast_forward=True)
        result=d.script(dict(format='fdisbull-script-1',steps=[
            dict(op='scene-act',scene='counter',object='test.button',compact=True,**{'as':'click'}),
            dict(op='assert',value='$click.status',equals='matched')]))
        assert result['ok'],result
        assert d.memory('1000:0100',length=2)['hex']=='0100'
        # A required missing capture is incomplete even when another branch is true.
        doc=deepcopy(scene['definition']);doc['objects'][0]['outcome']={'any':[
            {'constant':True},{'compare':dict(left=memory_word('0x0'),op='eq',right={'before':memory_word('0x0')})}]}
        bad=p.debug_save_scene('counter',doc,parent=scene['id'])
        before=len(p.debug_events(d.run_id)['events'])
        with pytest.raises(SceneError) as error:d.scene_act(bad['id'],'test.button',compact=True)
        assert error.value.result['status']=='unavailable' and not error.value.result['complete']
        events=p.debug_events(d.run_id)['events'][before:]
        assert not any(e['operation']=='keyboard.press' for e in events)
        # A popup handler's required baseline must also exist before input.
        doc=deepcopy(scene['definition'])
        doc['handlers']=[dict(name='popup',when={'constant':True},action=dict(kind='press',key='b'),
            outcome={'compare':dict(left=memory_word(),op='eq',right={'before':memory_word('0x0')})})]
        popup=p.debug_save_scene('counter',doc,parent=bad['id'])
        before=len(p.debug_events(d.run_id)['events'])
        with pytest.raises(SceneError) as error:d.scene_act(popup['id'],'test.button',handle_popups=True)
        assert error.value.result['status']=='unavailable'
        assert not any(e['operation']=='keyboard.press' for e in p.debug_events(d.run_id)['events'][before:])


@pytest.mark.parametrize('access',['x','w'])
def test_relative_outcome_preserves_debugger_stops(counter_game,emulator,access):
    path,binary=counter_game
    with Project(path) as p,p.debugger(emulator,binary.parent) as d:
        d.run(guest_ms=100,timeout_ms=3000,fast_forward=True)
        scene=p.debug_save_scene('counter',counter_definition(d.screenshot()))
        if access=='hook':d.hook('1000:000b',actions=[{'op':'layers','layers':[]}])
        else:d.breakpoint('1000:000b' if access=='x' else '1000:0100',access=access)
        with pytest.raises(SceneError) as error:d.scene_act(scene['id'],'test.button',compact=True)
        result=error.value.result
        assert result['status']=='stopped' and not result['complete'] and result['snapshot']
        assert result['stop']['outcome']=='breakpoint' or result['stop'].get('hook_hits')
        assert p.debug_scene_observation(result['observation'])['result']['baseline']['values']


@pytest.mark.parametrize('value,expected',[
    ({'wrap':{'type':'u8','value':{'add':[255,1]}}},0),
    ({'wrap':{'type':'i8','value':128}},-128),
    ({'sub':[0,1]},-1),({'add':[65535,1]},65536),
])
def test_typed_arithmetic_is_explicit(value,expected):
    from fdisbull.scene_values import expression,evaluate_expression
    expression(value)
    assert evaluate_expression(value,None,None)==expected


@pytest.mark.parametrize('value',[
    {'before':memory_word()}, {'memory':dict(address='0x10000',type='int')},
    {'memory':dict(address='0x10000',type='u16',endian='native')},
    {'wrap':{'type':'u16'}}, {'add':[1]}, True,
])
def test_invalid_relative_expressions_fail_before_input(value):
    from fdisbull.scene_values import expression
    with pytest.raises(ValueError):expression(value)


def test_one_observation_deduplicates_aliases_but_next_observation_is_fresh(counter_game,emulator):
    path,binary=counter_game
    with Project(path) as p,p.debugger(emulator,binary.parent) as d:
        d.run(guest_ms=100,timeout_ms=3000,fast_forward=True)
        doc=definition(d.screenshot());mem={'memory':dict(address='1000:0100',length=1,hex='00')}
        doc['match']={'all':[deepcopy(mem) for _ in range(5)]}
        for field in ('visible','ready','enabled'):doc['objects'][0][field]=deepcopy(mem)
        # Same static byte through a different segmented spelling.
        doc['objects'][0]['enabled']['memory']['address']='1010:0000'
        scene=p.debug_save_scene('repeat',doc)
        calls=[];original=d.memory
        def counted(*args,**kwargs):calls.append((args,kwargs));return original(*args,**kwargs)
        d.memory=counted
        full=d.scene_check(scene['id'])
        assert full['status']=='matched'
        assert len(calls)==1
        assert full['read_statistics']==dict(evaluations=8,unique_reads=1,cache_hits=7)
        compact=d.scene_check(scene['id'],compact=True)
        assert len(calls)==2  # no read/availability cache spans observations
        assert compact['reply_format']=='fdisbull-scene-compact-1'
        assert 'evidence' not in compact and 'samples' not in compact['frame']
        retained=p.debug_scene_observation(compact['observation'])['result']
        assert len(retained['evidence'])==8 and retained['read_statistics']['unique_reads']==1
        assert len(json.dumps(compact))<len(json.dumps(retained))
        d.keyboard.press('a',hold_ms=20,gap_ms=20)
        d.run(guest_ms=100,timeout_ms=3000,fast_forward=True)
        assert d.scene_check(scene['id'],compact=True)['status']=='mismatch'


def test_numbered_overlay_has_stable_legend_and_offline_restart(mouse_game,emulator,tmp_path):
    path,binary=mouse_game
    with Project(path) as p,p.debugger(emulator,binary.parent) as d:
        d.run(guest_ms=100,timeout_ms=3000,fast_forward=True)
        saved=p.debug_save_scene('test',definition(d.screenshot()))
        rendered=p.debug_scene_overlay(saved['id'],labels='numbers')
        assert rendered['metadata']['labels']=='numbers'
        assert rendered['metadata']['legend'][0]['name']=='test.button'
        assert rendered['metadata']['legend'][0]['object_id']==saved['definition']['objects'][0]['id']
        p.debug_export(rendered['legend_artifact'],tmp_path/'legend.json')
        assert json.loads((tmp_path/'legend.json').read_text())['targets'][0]['marker']==1
        p.debug_export(rendered['artifact'],tmp_path/'numbers.png')
        with Image.open(tmp_path/'numbers.png') as im:assert im.size==(320,200)
        revision=saved['id'];sha=rendered['sha256']
    with Project(path) as p:
        assert p.debug_scene_overlay(revision,labels='numbers')['sha256']==sha
        with pytest.raises(ValueError):p.debug_scene_overlay(revision,labels='unknown')


def test_portable_bundle_remaps_evidence_and_ids_atomically(mouse_game,emulator,tmp_path):
    path,binary=mouse_game;bundle=tmp_path/'scenes.zip'
    with Project(path) as p,p.debugger(emulator,binary.parent) as d:
        d.run(guest_ms=100,timeout_ms=3000,fast_forward=True)
        saved=p.debug_save_scene('test',definition(d.screenshot()),author='original agent')
        export=p.debug_export_scenes([saved['id']],bundle)
        assert export['snapshots']==1 and export['scenes']==1
        with zipfile.ZipFile(bundle) as archive:
            assert set(archive.namelist())=={'manifest.json',*['snapshots/'+s+'.png' for s in export['snapshot_hashes']]}
    target=tmp_path/'imported.fdb'
    with Project.create(target,binary) as p:
        imported=p.debug_import_scenes(bundle)
        new=p.debug_scene_info('test');oid=new['definition']['objects'][0]['id']
        assert oid!=saved['definition']['objects'][0]['id']
        assert new['definition']['reference']!=saved['definition']['reference']
        assert imported['object_map'][saved['definition']['objects'][0]['id']]==oid
        assert new['definition']['context']['bundle_origin']['author']=='original agent'
        p.debug_scene_overlay(new['id'],labels='numbers')
        with pytest.raises(ValueError,match='exists'):p.debug_import_scenes(bundle)
        assert len(p.debug_scenes()['scenes'])==1
        with p.debugger(emulator,binary.parent) as d:
            d.run(guest_ms=100,timeout_ms=3000,fast_forward=True)
            assert d.scene_assert('test',compact=True)['status']=='matched'
    # Extra binary/state members and modified images are rejected before any writes.
    hostile=tmp_path/'hostile.zip'
    with zipfile.ZipFile(bundle) as source,zipfile.ZipFile(hostile,'w') as dest:
        for item in source.infolist():dest.writestr(item.filename,source.read(item))
        dest.writestr('checkpoint.state',b'forbidden')
    other=tmp_path/'other.fdb'
    with Project.create(other,binary) as p:
        before=p.db.total_changes
        with pytest.raises(ValueError):p.debug_import_scenes(hostile)
        assert p.db.total_changes==before and p.debug_runs()['runs']==[]
        child=p.patch('0x10000','90')['version']
        with pytest.raises(ValueError,match='compatible'):p.debug_import_scenes(bundle,version=child)
        assert p.debug_scenes()['scenes']==[]
    with Project.create(tmp_path/'relocated.fdb',binary,load_segment=0x2000) as p:
        with pytest.raises(ValueError,match='compatible'):p.debug_import_scenes(bundle)
    # An invalid later definition rolls back earlier imported records, including
    # when a caller already owns an outer transaction.
    from fdisbull.scenes import encoded
    with zipfile.ZipFile(bundle) as source:
        contents={n:source.read(n) for n in source.namelist()}
    manifest=json.loads(contents['manifest.json']);second=deepcopy(manifest['scenes'][0])
    second.update(id='second',scene='second',name='second')
    second['definition']['objects'][0]['point']=[20,20]  # inside the excluded hole
    second['sha256']=__import__('hashlib').sha256(encoded(second['definition'])).hexdigest()
    manifest['scenes'].append(second);contents['manifest.json']=encoded(manifest)
    with zipfile.ZipFile(tmp_path/'late-invalid.zip','w') as archive:
        for n,data in contents.items():archive.writestr(n,data)
    with Project.create(tmp_path/'atomic.fdb',binary) as p:
        with p.transaction(True):
            with pytest.raises(ValueError,match='outside'):p.debug_import_scenes(tmp_path/'late-invalid.zip')
            assert p.debug_scenes()['scenes']==[] and p.debug_runs()['runs']==[]
            assert p.db.execute('SELECT count(*) FROM debug_artifacts').fetchone()[0]==0
    # The ordinary JSON command path exposes bundle import/export and labels.
    from fdisbull.cli import invoke
    params=dict(project=str(target),scene='test',labels='numbers')
    rendered=invoke('debug-scene-overlay',params)
    assert rendered['legend_artifact']
    from fdisbull.cli import respond
    (tmp_path/'bad.zip').write_bytes(b'invalid zip')
    failed=respond(dict(method='debug-import-scenes',params=dict(project=str(target),bundle=str(tmp_path/'bad.zip'))))
    assert not failed['ok'] and failed['error']['type']=='ValueError'
