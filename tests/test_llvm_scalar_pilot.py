"""Differential tests against the existing IL evaluator, plus real LLVM backend."""
import ctypes
import shutil
import subprocess
import pytest
from fdisbull.interaction_il import execute_il
from fdisbull.llvm_scalar_pilot import LLVMScalarError, emit_llvm_scalar_v1


def program():
    return {'format':'fdisbull-il-1','role':'uil',
            'variables':{'$value':{'type':'u8','initial':0},'$limit':{'type':'u8','initial':0},
                         '$enabled':{'type':'bool','initial':False}},'resources':{},
            'body':[{'id':'c','op':'if',
                     'condition':{'op':'and','conditions':[
                         {'op':'eq','left':{'var':'$enabled'},'right':True},
                         {'op':'lt','left':{'var':'$value'},'right':{'var':'$limit'}}]},
                     'then':[{'id':'plus','op':'add','var':'$value','value':2}],
                     'else':[{'id':'minus','op':'subtract','var':'$value','value':1}]}]}


def test_refuses_effects_and_wide_types():
    p=program();p['variables']['$value']['type']='u16'
    with pytest.raises(LLVMScalarError,match='Only u8'):emit_llvm_scalar_v1(p)
    p=program();p['resources']={'beep':{'kind':'sound','uri':'sound/1'}}
    p['body'].append({'id':'beep','op':'play_sound','resource':'beep'})
    with pytest.raises(LLVMScalarError,match='Resource'):emit_llvm_scalar_v1(p)


def test_real_native_code_matches_reference(tmp_path):
    clang=shutil.which('clang')
    if not clang:pytest.skip('clang not installed: LLVM code emitted, no native qualification')
    p=program();result=emit_llvm_scalar_v1(p)
    ir=tmp_path/'sample.ll';so=tmp_path/'sample.so';ir.write_text(result['llvm_ir'])
    subprocess.run([clang,'-O2','-shared','-fPIC','-x','ir',str(ir),'-o',str(so)],check=True,
                   capture_output=True,text=True)
    dll=ctypes.CDLL(str(so));fun=dll.fdisbull_scalar;fun.argtypes=[ctypes.POINTER(ctypes.c_ubyte)]
    for val in range(256):
        for enabled in (False,True):
            original={'$value':val,'$limit':137,'$enabled':enabled}
            oracle=execute_il(p,original)
            assert oracle['status']=='complete'
            buf=(ctypes.c_ubyte*len(result['state_slots']))(*[int(original[n]) for n in result['state_slots']])
            fun(buf)
            actual={name:bool(buf[i]) if p['variables'][name]['type']=='bool' else buf[i]
                    for i,name in enumerate(result['state_slots'])}
            assert actual == oracle['state']
