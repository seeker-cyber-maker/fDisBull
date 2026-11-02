"""Finite-contract and comparison checks; these do not execute an NES."""
import importlib.util
from pathlib import Path
import pytest

from fdisbull import shadowrun_systems as systems
from fdisbull.cli import respond
from fdisbull.game_il import author_program

SCRIPT=Path(__file__).resolve().parents[1]/'scripts'/'check_shadowrun_system_nes.py'
spec=importlib.util.spec_from_file_location('shadowrun_system_native_check', SCRIPT)
native=importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)

@pytest.fixture
def program():
    return author_program('''typedef unsigned char u8;typedef signed int i16;
        u8 input;u8 output=2;i16 signed_value;
        void step(void){output+=input;signed_value=-input;}''')


def test_catalog_and_cli_declare_bounded_components():
    result=respond({'method':'shadowrun-systems'})
    assert result['ok'] is True
    assert result['result']['whole_game'] is False
    assert set(result['result']['systems']) == {'inventory','combat','dialogue','animation'}
    assert respond({'method':'shadowrun-systems','params':{'unexpected':1}})['ok'] is False
    with pytest.raises(ValueError,match='Unknown registered'):
        systems.lift_system(b'', 'not-a-system')


def test_checked_cases_reset_baseline_and_probe_has_signed_results(program):
    states=[{'input':3},{'input':4}]
    scalar,baseline,keys,results=systems._checked_cases(program,'step',states,['output','signed_value'])
    assert keys==['input'] and baseline['output']==2
    assert results==[{'output':5,'signed_value':-3},{'output':6,'signed_value':-4}]
    assert scalar['input'][0]==8
    source,probe_results=systems._probe_source(program,'step',states,['output','signed_value'])
    assert probe_results==results
    assert 'step();' in source and 'PUB[3]=0x57' in source


@pytest.mark.parametrize('states,watch',[
    ([],['output']), ([{'input':256}],['output']), ([{'input':True}],['output']),
    ([{'input':1},{'output':1}],['output']), ([{'input':1}],[]),
    ([{'input':1}],['output','output']), ([{'input':1}],['missing']),
])
def test_checked_cases_reject_invalid_contracts(program,states,watch):
    with pytest.raises(ValueError):
        systems._checked_cases(program,'step',states,watch)


def test_probe_rejects_argument_procedures_and_arrays(program):
    with pytest.raises(ValueError):
        systems._checked_cases(program,'absent',[{'input':1}],['output'])
    needs_arg=author_program('typedef unsigned char u8;u8 x;void step(u8 n){x=n;}')
    with pytest.raises(ValueError):
        systems._checked_cases(needs_arg,'step',[{'x':1}],['x'])
    array=author_program('typedef unsigned char u8;u8 x;u8 a[2];void step(void){x=a[0];}')
    with pytest.raises(ValueError,match='scalar'):
        systems._probe_source(array,'step',[{'x':1}],['x'])


def frame(index,value,marker=0x53,sequence=None):
    if sequence is None:
        sequence=2*(index+1)%256
    data=bytes([sequence,index & 255,index>>8,marker])+int(value & 0xffffffff).to_bytes(4,'little')
    return {'raw':{'publication':data.hex()}}


def test_native_comparison_requires_full_results_and_completion():
    expected={'watch':['answer'],'reference_results':[{'answer':-1},{'answer':17}]}
    valid={'frames':[frame(0,-1),frame(1,17,0x57)]}
    assert native.compare(valid,expected)=={'cases':2,'differences':0,'completed':True}
    with pytest.raises(AssertionError,match='mismatch'):
        native.compare({'frames':[frame(0,-1),frame(1,18,0x57)]},expected)
    with pytest.raises(AssertionError):
        native.compare({'frames':[frame(1,17,0x57)]},expected)
    with pytest.raises(AssertionError,match='preceded'):
        native.compare({'frames':[frame(0,-1,0x57)]},expected)
    with pytest.raises(ValueError,match='outside contract'):
        native.compare({'frames':[frame(2,17)]},expected)
    with pytest.raises(ValueError,match='wrong size'):
        native.compare({'frames':[{'raw':{'publication':'0000'}}]},expected)
    with pytest.raises(AssertionError):
        native.compare({'frames':[frame(0,-1,sequence=1),frame(1,17,0x57)]},expected)

def test_native_comparison_rejects_completion_before_prior_cases():
    expected={'watch':['answer'],'reference_results':[{'answer':2},{'answer':17}]}
    with pytest.raises(AssertionError):
        native.compare({'frames':[frame(1,17,0x57,4),frame(0,2,0x53,2)]},expected)

def test_native_comparison_accepts_stable_repeats_and_sequence_wrap():
    expected={'watch':['answer'],'reference_results':[{'answer':n} for n in range(129)]}
    frames=[]
    for index in range(129):
        frames.append(frame(index,index))
        if index==3:
            frames.append(frame(index,index))
    frames.append(frame(128,128,0x57))
    assert native.compare({'frames':frames},expected)['cases']==129


def test_native_comparison_rejects_wrong_even_sequence():
    expected={'watch':['answer'],'reference_results':[{'answer':2},{'answer':17}]}
    with pytest.raises(AssertionError):
        native.compare({'frames':[frame(0,2,sequence=6),frame(1,17,0x57)]},expected)

@pytest.mark.parametrize('tampered', ['reference_results','program_sha256','case_document_sha256'])
def test_native_runner_rejects_changed_build_metadata_before_launch(tmp_path,monkeypatch,tampered):
    import json
    import sys
    build=tmp_path/'build';build.mkdir()
    image=b'\0'*40976
    (build/'check.nes').write_bytes(image)
    core=tmp_path/'core';core.write_bytes(b'core')
    monkeypatch.setattr(native,'CORE_SHA',native.sha(b'core'))
    fresh={'format':'fdisbull-shadowrun-system-nes-check-1','system':'combat',
           'procedure':'step','source_sha256':'source','program_sha256':'program',
           'case_document_sha256':'cases','cartridge_sha256':native.sha(image),
           'watch':['answer'],'reference_results':[{'answer':1}],
           'publication':{'length':8}}
    recorded=dict(fresh)
    recorded[tampered]=[{'answer':2}] if tampered=='reference_results' else 'changed'
    (build/'check.json').write_text(json.dumps(recorded))
    monkeypatch.setattr(native,'export_system',lambda *a,**kw: None)
    monkeypatch.setattr(native,'build_system_check',lambda *a,**kw: fresh)
    monkeypatch.setattr(native.subprocess,'run',lambda *a,**kw: pytest.fail('must reject before native execution'))
    monkeypatch.setattr(sys,'argv',['check','--build',str(build),'--core',str(core),
        '--rom','private-rom','--cases','private-cases','--cc65-root','toolchain',
        '--output',str(tmp_path/'output')])
    with pytest.raises(AssertionError,match='fresh source build'):
        native.main()
