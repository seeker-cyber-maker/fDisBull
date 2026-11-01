"""Source-bound desktop emission and shared authored native fixtures."""
from importlib.util import module_from_spec,spec_from_file_location
import json
from pathlib import Path

import pytest

from fdisbull.project import Project
from fdisbull.udc_layers import digest
from fdisbull.udc_memory_desktop import emit_memory_desktop_shell,seal_memory_desktop_shell


def fixture_module():
    spec=spec_from_file_location('desktop_region_fixture',Path(__file__).with_name('test_memory_region_shell.py'))
    module=module_from_spec(spec);spec.loader.exec_module(module);return module


def fixture_sources(destination,target):
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    source=destination.parent/'authored.com';source.write_bytes(bytes.fromhex('b8004ccd21'))
    fixture=fixture_module()
    with Project.create(destination.parent/'authored.fdb',source,image='com') as project:
        selections=fixture.exact_selections(project,fixture.model())
        regions=fixture.region_plan(project,fixture.model())
        plan=fixture.shell_plan();plan['events']['quit_index']=15
        plan['keymap']={'KeyA':{'ascii':65,'scan':1}}
        return emit_memory_desktop_shell(project,selections,plan,fixture.initial(),destination,
            target=target,regions=regions,cuts={'format':'fdisbull-memory-cuts-2',
                'module_uil_sha256':digest(fixture.model()),
                'cuts':[{'caller':'advance','entry':'advance.update','callee':'update'}]})


@pytest.mark.parametrize('target',['windows-x64','linux-x64'])
def test_desktop_emission_preserves_source_and_records_real_target(tmp_path,target):
    manifest=fixture_sources(tmp_path/'sources',target)
    assert manifest['stage']=='source-only' and not manifest['native_execution']
    assert manifest['source_selections'] and manifest['runtime']['region_controls']
    assert all(v['target']==manifest['target'] for v in manifest['realizations'].values())
    assert 'memory-host-config.h' in manifest['source_artifacts']
    assert json.loads((tmp_path/'sources/native-shell.json').read_text())==manifest


def test_changed_source_refuses_before_artifact_sealing(tmp_path):
    fixture_sources(tmp_path/'sources','linux-x64')
    (tmp_path/'sources/memory-desktop.c').write_text('changed')
    with pytest.raises(ValueError,match='source artifact changed'):seal_memory_desktop_shell(tmp_path/'sources')


def test_manifest_symlink_cannot_overwrite_another_receipt(tmp_path):
    destination=tmp_path/'sources';fixture_sources(destination,'linux-x64')
    original=(destination/'native-shell.json').read_bytes()
    outside=tmp_path/'retained.json';outside.write_bytes(original)
    (destination/'native-shell.json').unlink();(destination/'native-shell.json').symlink_to(outside)
    with pytest.raises(ValueError,match='owned regular file'):seal_memory_desktop_shell(destination)
    assert outside.read_bytes()==original


def test_compiler_recipe_cannot_redirect_outputs(tmp_path):
    from fdisbull.udc_memory_desktop import compile_memory_desktop_shell
    destination=tmp_path/'sources';manifest=fixture_sources(destination,'linux-x64')
    manifest['commands'][0][-1]='../original.bin'
    (destination/'native-shell.json').write_text(json.dumps(manifest))
    retained=tmp_path/'original.bin';retained.write_bytes(b'preserved')
    with pytest.raises(ValueError,match='compiler recipe differs'):compile_memory_desktop_shell(destination)
    assert retained.read_bytes()==b'preserved'


def observation(manifest,*,x=0,y=0,closed=0,selected=None):
    import struct
    controls=manifest['runtime']['region_controls'];functions=manifest['runtime']['function_order']
    pack=lambda *v:struct.pack('<'+'I'*len(v),*v)
    encoded=b'FDBOUT1\0'+pack(16,1,len(controls),len(functions))
    encoded+=pack(*[len(c['variants']) for c in controls])
    encoded+=pack(0,0,0,closed,0,0,x,y,0,2,2,0)
    encoded+=pack(*([c['default_index'] for c in controls] if selected is None else selected))
    encoded+=bytes(8*(len(functions)+sum(len(c['variants']) for c in controls)))
    encoded+=pack(*fixture_module().initial())
    return encoded


def test_observer_rejects_impossible_pointer_state_and_incomplete_frames(tmp_path):
    from fdisbull.udc_memory_desktop import decode_study
    m=fixture_sources(tmp_path/'sources','linux-x64');good=observation(m)
    assert list(decode_study(m,good)[0]['words'])==fixture_module().initial()
    for malformed in [observation(m,x=2),observation(m,y=0xffffffff),good[:-1],good+b'\0',
                      observation(m,closed=1),observation(m,selected=[0xffffffff])]:
        with pytest.raises(ValueError):decode_study(m,malformed)
