"""Authored fixtures and code-shape checks for the direct Python backend."""
from __future__ import annotations
import ast
import copy
import importlib
import json
from pathlib import Path
import random
import subprocess
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'examples'/'z3_python_blocks'))
sys.path.insert(0,str(ROOT/'examples'/'text_asset_pilot'))
sys.path.insert(0,str(Path(__file__).parent))
from test_text_asset_pilot import fixture, text, packed_codes
import transpile
from asset_package import PackageError,canonical,sha
from fdisbull_player.word16 import Word16Runtime,Word16Error


def direct(tmp_path,program):
    root=tmp_path/'product'
    transpile.build(program,root)
    sys.path.insert(0,str(root))
    from runtime import DirectGame
    globals()["NativeError"] = importlib.import_module("state_services").Word16Error
    return DirectGame(root),root


def test_no_interpreter_or_game_graph_shipped(tmp_path):
    p=fixture(tmp_path)
    g,root=direct(tmp_path,p)
    support=(root/'state_services.py').read_text()
    assert all(x not in support for x in ('def _nodes(', 'def _expr(', 'def _library(', 'validate_program('))
    spec=json.loads((root/'program.json').read_text())
    assert 'blocks' not in spec and 'block_ids' in spec
    for f in (root/'game_code').glob('b*.py'):
        tree=ast.parse(f.read_text())
        assert any(isinstance(n,ast.FunctionDef) for n in tree.body)
        assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in ('eval','exec') for n in ast.walk(tree))
    assert not any(n in support for n in ('from fdisbull', 'import fdisbull'))
    assert (root/'media.zip').exists() and (root/'memory.zip').exists()


def test_full_input_boundary_and_state_match(tmp_path):
    p=fixture(tmp_path)
    g,_=direct(tmp_path,p);b=Word16Runtime(p)
    assert g.run()==b.run()
    assert g.snapshot()==b.snapshot()
    assert g.command('hello')==b.command('hello')
    assert g.snapshot()==b.snapshot()


def test_global_variable_alias_and_wrapping(tmp_path):
    g,_=direct(tmp_path,fixture(tmp_path))
    g.state.globals[7]=65537
    address=g.layout['globals']+14
    assert g._read(address,16)==1
    g._write(address,16,65535)
    assert g.state.globals[7]==65535
    with pytest.raises(NativeError):g.state.globals[240]=0
    with pytest.raises(NativeError):g.state.globals[0]=True


def test_object_flags_alias_memory(tmp_path):
    g,_=direct(tmp_path,fixture(tmp_path))
    g.state.set_flag(1,3,True)
    address=g.layout['objects']+62
    assert g.memory[address]&0x10
    g.memory[address]=0
    assert g.state.flag(1,3) is False
    with pytest.raises(NativeError):g.state.set_flag(1,32,True)


def test_live_memory_roundtrip_and_atomic_refusal(tmp_path):
    p=fixture(tmp_path);g,root=direct(tmp_path,p)
    g.run();container=g.memory_container()
    assert 'dynamic_hex' in container['state'] and 'memory' not in container['state']
    assert len(container['state']['dynamic_hex'])==g.writable_end*2
    from runtime import DirectGame
    h=DirectGame(root);h.restore_memory_container(container)
    assert g.snapshot()==h.snapshot()
    assert g.command('x')==h.command('x')
    before=h.snapshot()
    bad=copy.deepcopy(container);bad['state']['frames'][0]['base']=1000000
    with pytest.raises(NativeError):h.restore_memory_container(bad)
    assert h.snapshot()==before
    bad=copy.deepcopy(container);bad['media_sha256']='0'*64
    with pytest.raises(PackageError):h.restore_memory_container(bad)
    assert h.snapshot()==before


def test_changed_text_fallback_and_strict_refusal(tmp_path):
    p=fixture(tmp_path,bytes.fromhex('8703a0ba'),[(0x3a0,text('alpha'))])
    g,root=direct(tmp_path,p)
    g.memory[0x3a0:0x3a4]=text('omega')
    assert g.run()['text']=='omega' and g.changed_dependencies==1
    from runtime import DirectGame
    strict=DirectGame(root,strict_text=True)
    strict.memory[0x3a0:0x3a4]=text('omega')
    with pytest.raises(NativeError,match='media binding'):strict.run()


def test_code_mutation_refused(tmp_path):
    g,_=direct(tmp_path,fixture(tmp_path))
    g.memory[g.pc]^=1
    with pytest.raises(NativeError,match='self-modified'):g.run()
    assert g.fault is not None


def test_product_tamper_refused(tmp_path):
    _,root=direct(tmp_path,fixture(tmp_path))
    file=next((root/'game_code').glob('b*.py'))
    file.write_text(file.read_text()+'\n# modification\n')
    from runtime import DirectGame
    with pytest.raises(PackageError,match='digest mismatch'):DirectGame(root)


def test_memory_output_stream_controls(tmp_path):
    p=fixture(tmp_path,b'\xb2'+text('a\t\v\nb')+b'\xba')
    g,_=direct(tmp_path,p);b=Word16Runtime(p)
    for r in (g,b):
        r._host('output_stream',[3,0x360]);assert r.run()['text']==''
        r._host('output_stream',[-3])
    assert g.snapshot()==b.snapshot()
    assert g.memory[0x360:0x367]==b'\x00\x05a\x09\x0b\x0db'


def test_abbreviation_guard(tmp_path):
    p=fixture(tmp_path,b'\xb2'+packed_codes([1,0])+b'\xba',
              [(640,(0x3a0//2).to_bytes(2,'big')),(0x3a0,text('alpha')),(0x3b0,text('omega'))])
    g,_=direct(tmp_path,p)
    g.memory[640:642]=(0x3b0//2).to_bytes(2,'big')
    assert g.run()['text']=='omega' and g.changed_dependencies==1


def test_numeric_primitives_match_reference(tmp_path):
    p=fixture(tmp_path);_,_=direct(tmp_path,p)
    primitive=importlib.import_module('primitives');b=Word16Runtime(p)
    rng=random.Random(83402)
    values=[-32768,-11,-1,0,1,2,32767,65535]+[rng.randint(-65535,65535) for _ in range(80)]
    checked=0
    for op in ('add','sub','mul','div','mod','and','or','xor','lt','gt','le','ge'):
        fn=getattr(primitive,'calc_'+op)
        for a in values:
            for c in (-13,-2,-1,0,1,2,11):
                if op in ('div','mod') and c==0:
                    with pytest.raises(NativeError):fn(a,c)
                    continue
                assert fn(a,c)==b._expr({'calc':op,'args':[a,c]},{}), (op,a,c)
                checked+=1
    assert checked>7000
    assert primitive.calc_div(-11,2)==-5
    assert primitive.calc_mod(-13,5)==-3


def test_budget_resumption_matches(tmp_path):
    p=fixture(tmp_path);g,_=direct(tmp_path,p);b=Word16Runtime(p)
    for _ in range(100):
        assert g.run(max_steps=1)==b.run(max_steps=1)
        assert g.snapshot()==b.snapshot()
        if g.pending_input:break
    else:pytest.fail('no input boundary')


def test_call_and_indirect_stack_semantics(tmp_path):
    # call packed 0x240 (routine at 0x480), store returned 7 in global 0; quit.
    p=fixture(tmp_path,bytes.fromhex('e03f024010ba'),[(0x480,bytes.fromhex('009b07'))])
    g,_=direct(tmp_path,p);b=Word16Runtime(p)
    assert g.run()==b.run() and g.snapshot()==b.snapshot()
    assert g.state.globals[0]==7
    for r in (g,b):
        r._push(10);assert r._read_var(0,True)==10
        r._write_var(0,12,True);assert r.stack[-1]==12
        assert r._read_var(0)==12
    assert g.snapshot()==b.snapshot()


def test_standalone_python_isolation_and_restore(tmp_path):
    _,root=direct(tmp_path,fixture(tmp_path))
    commands=tmp_path/'empty.json';commands.write_text('[]')
    save=tmp_path/'state.json'
    a=subprocess.run([sys.executable,'-I',str(root/'play.py'),'--commands',str(commands),'--checkpoint',str(save)],
                     capture_output=True,text=True,timeout=20,cwd='/tmp')
    assert a.returncode==0,a.stderr
    (tmp_path/'authored.z3').unlink()
    b=subprocess.run([sys.executable,'-I',str(root/'play.py'),'--resume',str(save)],input='hello\n',
                     capture_output=True,text=True,timeout=20,cwd='/tmp')
    assert b.returncode==0,b.stderr
    assert b.stdout=='omega'


def test_build_determinism(tmp_path):
    p=fixture(tmp_path)
    a=transpile.build(p,tmp_path/'a');b=transpile.build(p,tmp_path/'b')
    assert a==b
    assert (tmp_path/'a/product.json').read_bytes()==(tmp_path/'b/product.json').read_bytes()
