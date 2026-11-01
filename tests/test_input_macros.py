import copy
import hashlib
import json
import time

import pytest

from fdisbull.input_macros import (MacroProjectMixin, MACRO_DDL, encode,
                                   expand_macro, validate_macro_set)
from fdisbull.project import Project
from test_debugger import emulator
from test_dos_loader import mz_file


def definition(macros):
    return {'format':'fdisbull-macro-set-1', 'name':'example', 'macros':macros}


def test_dag_is_bounded_and_expansion_limits_are_preflighted():
    macros = {'leaf':{'steps':[{'op':'status'}]}}
    for i in range(15):
        previous = 'leaf' if i == 0 else f'n{i-1}'
        macros[f'n{i}'] = {'steps':[{'op':'macro','name':previous},{'op':'macro','name':previous}]}
    started = time.monotonic()
    with pytest.raises(ValueError, match='limit'):
        validate_macro_set(definition(macros))
    assert time.monotonic() - started < 2
    with pytest.raises(ValueError, match='Recursive'):
        validate_macro_set(definition({'a':{'steps':[{'op':'macro','name':'a'}]}}))


def test_alias_order_lengths_and_nested_outputs():
    long = 'a'*64
    spec = definition({
        'start':{'steps':[{'op':'keyboard.key-down','key':'ctrl','as':long}],
                 'outputs':{'lease':'$'+long+'.lease'}},
        'outer':{'steps':[{'op':'macro','name':'start','as':'nested'},
                          {'op':'keyboard.key-up','lease':'$nested.outputs.lease'}],
                 'outputs':{'saved':'$nested.outputs.lease'}}})
    plan = expand_macro(spec,'outer')
    assert plan['script']['steps'][0]['as'] == 'm1a0'
    assert plan['script']['steps'][1]['lease'] == '$m1a0.lease'
    assert plan['outputs']['saved'] == '$m1a0.lease'
    bad = definition({'a':{'steps':[{'op':'assert','value':'$later.result','equals':1},
                                   {'op':'status','as':'later'}]}})
    with pytest.raises(ValueError, match='earlier'): expand_macro(bad,'a')
    bad = definition({'a':{'steps':[{'op':'keyboard.key-down','key':'ctrl','as':'down'}],
                           'outputs':{'lease':'$down.nonexistent'}}})
    with pytest.raises(ValueError, match='result field'): expand_macro(bad,'a')
    bad = definition({'a':{'steps':[{'op':'keyboard.key-down','key':'ctrl'},
                                   {'op':'status','as':'s'},
                                   {'op':'assert','value':'$s.not_a_field','equals':1}]}})
    with pytest.raises(ValueError, match='unverifiable result field'): expand_macro(bad,'a')


def test_types_and_late_step_validation():
    with pytest.raises(ValueError):
        validate_macro_set(definition({'a':{'parameters':{'n':{'type':'integer','enum':[True]}},'steps':[{'op':'status'}]}}))
    macros = definition({'a':{'parameters':{'n':{'type':'integer'}},'steps':[{'op':'status'},
                              {'op':'keyboard.press','key':'invalid'}]}})
    with pytest.raises(ValueError): expand_macro(macros,'a',{'n':True})
    with pytest.raises(ValueError): expand_macro(macros,'a',{'n':1})
    with pytest.raises(ValueError): expand_macro(macros,'a',[])


def test_export_import_restart_hash_and_patch_scope(tmp_path):
    binary=tmp_path/'a.bin';binary.write_bytes(b'\x90\xc3')
    path=tmp_path/'a.fdb'
    cls=Project if issubclass(Project,MacroProjectMixin) else type('MacroProject',(MacroProjectMixin,Project),{})
    spec=definition({'a':{'steps':[{'op':'status'}]}})
    with cls.create(path,binary,arch='x86',base=0x1000) as project:
        project.db.executescript(MACRO_DDL)
        saved=project.debug_define_macros(spec,author='test'); envelope=project.debug_export_macros(saved['id'])
        assert json.loads(json.dumps(envelope)) == envelope
        assert project.debug_import_macros(envelope,author='importer')['definition'] == spec
        changed=copy.deepcopy(envelope);changed['definition']['name']='tampered'
        with pytest.raises(ValueError,match='hash'):project.debug_import_macros(changed)
        changed['sha256']=hashlib.sha256(encode({k:v for k,v in changed.items() if k!='sha256'}).encode()).hexdigest()
        changed['binding']['source_sha256']='f'*64
        changed['sha256']=hashlib.sha256(encode({k:v for k,v in changed.items() if k!='sha256'}).encode()).hexdigest()
        with pytest.raises(ValueError,match='source or version'):project.debug_import_macros(changed)
        project.patch(0x1000,'c3')
        with pytest.raises(ValueError,match='source or version'):project.debug_import_macros(envelope)
        with pytest.raises(ValueError):project.debug_macro_info(saved['id'])
    with cls(path) as project:
        assert project.debug_macro_info(saved['id'],version=1)['definition'] == spec
        assert project.debug_export_macros(saved['id'],version=1)==envelope


@pytest.mark.parametrize('path', ['/Users/example/game', '~/game', r'C:\\games\\game', r'\\\\server\\share'])
def test_portable_export_rejects_host_paths(tmp_path,path):
    binary=tmp_path/'a.bin';binary.write_bytes(b'\xc3')
    cls=Project if issubclass(Project,MacroProjectMixin) else type('MacroProject',(MacroProjectMixin,Project),{})
    with cls.create(tmp_path/'a.fdb',binary,arch='x86',base=0x1000) as project:
        project.db.executescript(MACRO_DDL)
        spec=definition({'a':{'steps':[{'op':'status'}], 'evidence':{'host_path':path}}})
        saved=project.debug_define_macros(spec)
        with pytest.raises(ValueError,match='absolute paths'):project.debug_export_macros(saved['id'])


def test_native_held_lease_public_macro_and_failure_cleanup(tmp_path,emulator):
    binary=tmp_path/'LOOP.EXE';binary.write_bytes(mz_file(bytes.fromhex('fbebfd')+bytes(1024),ss=0,sp=0x400))
    spec=definition({
        'start':{'steps':[{'op':'keyboard.key-down','key':'ctrl','as':'down'},
                          {'op':'run','guest_ms':20}], 'outputs':{'lease':'$down.lease'}},
        'fail':{'steps':[{'op':'keyboard.key-down','key':'ctrl'}, {'op':'run','guest_ms':20},
                         {'op':'assert','value':1,'equals':2}]},
        'unreturned':{'steps':[{'op':'keyboard.key-down','key':'ctrl'}, {'op':'run','guest_ms':20}]},
        'bad':{'steps':[{'op':'keyboard.key-down','key':'ctrl'}, {'op':'keyboard.press','key':'invalid'}]},
        'release_fail':{'parameters':{'lease':{'type':'input-lease'}},
                        'steps':[{'op':'keyboard.key-up','lease':'$args.lease'},
                                 {'op':'assert','value':1,'equals':2}]},
    })
    with Project.create(tmp_path/'native.fdb',binary) as project:
        project.analyze(max_instructions=4)
        saved=project.debug_define_macros(spec)
        with project.debugger(emulator,tmp_path) as debug:
            with pytest.raises(ValueError):debug.macro(saved['id'],'bad')
            assert debug.keyboard_state()['keyboard']['owned_keys']==0
            result=debug.macro(saved['id'],'start')
            token=result['outputs']['lease'];assert result['ok'] and token in debug._keyboard_leases
            assert result['input_before']['keyboard']['owned_keys']==0
            assert result['input_after']['keyboard']['owned_keys']==1
            assert debug.keyboard_state()['keyboard']['owned_keys']==1
            debug.keyboard_key_up(token)
            debug.run(guest_ms=20,timeout_ms=3000,fast_forward=True)
            assert debug.keyboard_state()['keyboard']['owned_keys']==0
        with project.debugger(emulator,tmp_path) as debug:
            result=debug.macro(saved['id'],'unreturned')
            assert not result['ok'] and debug.closed and result['cleanup'][0]['closed']
        with project.debugger(emulator,tmp_path) as debug:
            result=debug.macro(saved['id'],'fail')
            assert not result['ok'] and debug.closed
            assert result['input_after']['reason']=='session_closed'
        with project.debugger(emulator,tmp_path) as debug:
            token=debug.macro(saved['id'],'start')['outputs']['lease']
            result=debug.macro(saved['id'],'release_fail',args={'lease':token})
            assert not result['ok'] and debug.closed
