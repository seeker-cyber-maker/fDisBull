"""Public rewind contracts against a selected real native DOS backend."""
import os

import pytest

from fdisbull.cli import METHODS, respond
from fdisbull.debug_script import validate_script
from fdisbull.debugger import DebugWorkspace
from fdisbull.project import Project
from test_dos_loader import mz_file


def test_rewind_routes_are_live_owned_and_script_arguments_are_checked():
    for method in ('debug-rewind-start','debug-rewind-record','debug-rewind-status','debug-rewind'):
        assert method in METHODS
        result=respond({'method':method,'params':{'run':'not-owned'}})
        assert not result['ok']
    validate_script({'format':'fdisbull-script-1','steps':[
        {'op':'rewind-start','max_steps':8},
        {'op':'rewind-record','count':2}, {'op':'rewind','count':1},
        {'op':'rewind-status'}]})
    with pytest.raises(ValueError):
        validate_script({'format':'fdisbull-script-1','steps':[
            {'op':'run','guest_ms':1}, {'op':'rewind-record','count':True}]})


@pytest.fixture
def native(tmp_path,monkeypatch):
    executable=os.environ.get('FDISBULL_DOSBOX')
    if not executable:
        pytest.skip('Set FDISBULL_DOSBOX for real native rewind checks')
    game=tmp_path/'game';game.mkdir()
    # CLI; PUSH CS; POP DS; MOV AX,100h; MOV BX,3; MOV [100h],AX;
    # ADD AX,BX; INC word[100h]; XOR AX,55h; MOV [102h],AX;
    # INC BX; ADD word[100h],BX; NOP; guard loop.
    code=bytes.fromhex('fa0e1fb80001bb0300a3000101d8ff060001355500a3020143011e000190ebfe')
    target=game/'REWIND.EXE';target.write_bytes(mz_file(code.ljust(512,b'\0'),ss=0,sp=0x1f0))
    monkeypatch.setenv('FDISBULL_TARGET_STORE',str(tmp_path/'objects'))
    with Project.create(tmp_path/'rewind.fdb',target) as project:
        with project.debugger(executable,game) as debug:
            yield project,debug,game


def observed(debug):
    registers=debug.registers()
    return ({key:registers[key] for key in ('general','segments','instruction_pointer','flags')},
            debug.memory('1000:0000',length=512)['hex'])


def test_real_record_rewind_and_new_branch_restore_cpu_and_all_mapped_ram(native):
    project,debug,_=native
    workspace=DebugWorkspace();workspace.sessions[debug.run_id]=debug
    def invoke(method,**params):
        return workspace.invoke(method,project.path,{'run':debug.run_id,**params})
    invoke('debug-rewind-start',max_steps=12)
    states=[]
    for _ in range(6):
        states.append(observed(debug))
        invoke('debug-rewind-record')
    assert int(debug.registers()['instruction_pointer'],16)==12
    invoke('debug-rewind',count=2)
    assert observed(debug)==states[4]
    debug.rewind_record()
    assert int(debug.registers()['instruction_pointer'],16)==9
    debug.rewind()
    assert observed(debug)==states[4]
    # Ordinary unrecorded execution cannot silently leave a usable cursor.
    debug.trace(count=2,fast_forward=True)
    assert invoke('debug-rewind-status')['valid'] is False
    with pytest.raises(ValueError): debug.rewind()


def test_real_budget_refusal_never_advances_guest_or_persists_oversize_state(native):
    project,debug,_=native
    before=observed(debug)
    debug.rewind_start(max_steps=1,max_bytes=1)
    with pytest.raises(ValueError,match='budget'):
        debug.rewind_record()
    assert observed(debug)==before
    assert not [a for a in project.debug_artifacts()['artifacts'] if a['kind']=='state']


def test_real_changed_host_file_blocks_rewind_without_restoring_cpu(native):
    _,debug,game=native
    debug.rewind_start(max_steps=2)
    debug.rewind_record(count=2)
    before=observed(debug)
    (game/'EXTRA.BIN').write_bytes(b'authored changed host-file control')
    with pytest.raises(ValueError,match='Mounted game files'):
        debug.rewind()
    assert observed(debug)==before
    assert not debug.rewind_status()['valid']


def test_real_script_rewind_respects_shared_budget_and_restores_boundary(native):
    _,debug,_=native
    result=debug.script({'format':'fdisbull-script-1','steps':[
        {'op':'rewind-start','max_steps':4},
        {'op':'rewind-record','count':3,'timeout_ms':10000},
        {'op':'rewind','count':2},
        {'op':'rewind-status','as':'history'}]},timeout_ms=20000)
    assert result['ok']
    assert int(debug.registers()['instruction_pointer'],16)==1
    assert debug.rewind_status()['cursor']==1
