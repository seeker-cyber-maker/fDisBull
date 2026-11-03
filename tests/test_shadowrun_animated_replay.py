"""Public animated wrapper gates; private backend/native checks are separate."""
import json
import pytest
from fdisbull.game_il import author_program, canonical
from fdisbull import shadowrun_replay as replay, shadowrun_nes_animation as backend, udl_shadowrun

@pytest.fixture
def setup_wrapper(tmp_path,monkeypatch):
    rom=b'reviewed source stand-in'
    program=author_program('typedef unsigned char u8;u8 x;void step(void){x++;}')
    arrays={field:field.encode() for field,_ in replay.SNAPSHOT_FILES.values()}
    payloads={name:arrays[field] for name,(field,_) in replay.SNAPSHOT_FILES.items()}
    payloads.update({'program.uil.json':canonical(program),
                     'atlas/vdp-rgb.bin':b'rgb','atlas/vdp-coverage.bin':b'coverage',
                     'atlas/vdp-conflicts.bin':b'conflicts',
                     'atlas/raster-rgb.bin':b'raster', 'atlas/raster-coverage.bin':b'coverage2',
                     'atlas/raster-conflicts.bin':b'conflicts2'})
    manifest={'source':{'sha256':replay._sha(rom)},'recipe':{'atlas_origin_x':768,'atlas_origin_y':512,
        'atlas_row_offset':0,'max_pattern_merges':0}}
    (tmp_path/'bundle').mkdir()
    (tmp_path/'bundle/manifest.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(replay,'ANIMATED_ATLAS_SHA256',{name:replay._sha(payloads[name]) for name in ('atlas/vdp-rgb.bin','atlas/vdp-coverage.bin','atlas/vdp-conflicts.bin')})
    calls=[]
    def fake_backend(source,capture,output,**kwargs):
        calls.append((source,capture,kwargs))
        output.mkdir();(output/'animated.nes').write_bytes(b'nes artifact')
        return {'output_sha256':replay._sha(b'nes artifact'),'scope':'test'}
    monkeypatch.setattr(replay,'_bundle',lambda path:(tmp_path,manifest,payloads))
    monkeypatch.setattr(replay,'_read_rom',lambda path:rom)
    monkeypatch.setattr(udl_shadowrun,'lift_opening_stoker',lambda source:program)
    monkeypatch.setattr(replay,'_source_capture',lambda path,digest:({},arrays,{}))
    monkeypatch.setattr(backend,'build_right_walk_animation_probe',fake_backend)
    return manifest,payloads,arrays,calls


def build(tmp_path):
    return replay.build_animated_opening(tmp_path/'bundle/manifest.json',rom_path='rom',
        capture=tmp_path/'capture',cc65_root='tools',output=tmp_path/'out')


def test_wrapper_passes_bound_atlas_and_checks_output(tmp_path,setup_wrapper):
    _,_,_,calls=setup_wrapper
    result=build(tmp_path)
    assert result['output_sha256']==replay._sha(b'nes artifact')
    assert len(calls)==1
    kwargs=calls[0][2]
    assert (kwargs['atlas_rgb'],kwargs['atlas_coverage'],kwargs['atlas_conflicts'])==(b'rgb',b'coverage',b'conflicts')
    assert (kwargs['atlas_origin_x'],kwargs['atlas_origin_y'])==(768,512)


def test_wrapper_refuses_source_lift_mismatch_before_backend(tmp_path,setup_wrapper):
    _,payloads,_,calls=setup_wrapper
    payloads['program.uil.json']=canonical(author_program('typedef unsigned char u8;u8 x;void step(void){x=5;}'))
    with pytest.raises(ValueError,match='source lift'):
        build(tmp_path)
    assert not calls


def test_wrapper_refuses_snapshot_mismatch_before_backend(tmp_path,setup_wrapper):
    _,_,arrays,calls=setup_wrapper
    arrays['ram']=b'different'
    with pytest.raises(ValueError,match='initial state'):
        build(tmp_path)
    assert not calls


def test_wrapper_refuses_output_hash_mismatch(tmp_path,setup_wrapper,monkeypatch):
    def fake_backend(source,capture,output,**kwargs):
        output.mkdir();(output/'animated.nes').write_bytes(b'wrong')
        return {'output_sha256':replay._sha(b'expected')}
    monkeypatch.setattr(backend,'build_right_walk_animation_probe',fake_backend)
    with pytest.raises(ValueError,match='output hash'):
        build(tmp_path)


def test_wrapper_refuses_forged_self_declared_atlas(tmp_path,setup_wrapper):
    manifest,payloads,_,calls=setup_wrapper
    name='atlas/vdp-rgb.bin'
    payloads[name]=b'forged source imagery'
    # Even if a caller updated the bundle's self-declared records, the
    # separately reviewed digest remains the authority for this profile.
    manifest['files']={name:replay._record(payloads[name])}
    manifest['atlas']={'arrays':{name:replay._record(payloads[name])}}
    (tmp_path/'bundle/manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='independently reviewed atlas'):
        build(tmp_path)
    assert not calls


def test_wrapper_rechecks_rom_after_backend(tmp_path,setup_wrapper,monkeypatch):
    values=iter([b'reviewed source stand-in',b'changed source'])
    monkeypatch.setattr(replay,'_read_rom',lambda path:next(values))
    with pytest.raises(ValueError,match='ROM path changed'):
        build(tmp_path)


def test_wrapper_rejects_manifest_changed_during_backend(tmp_path,setup_wrapper,monkeypatch):
    def fake_backend(source,capture,output,**kwargs):
        output.mkdir();(output/'animated.nes').write_bytes(b'nes artifact')
        (tmp_path/'bundle/manifest.json').write_text('{"changed":true}')
        return {'output_sha256':replay._sha(b'nes artifact')}
    monkeypatch.setattr(backend,'build_right_walk_animation_probe',fake_backend)
    with pytest.raises(ValueError,match='manifest changed'):
        build(tmp_path)
