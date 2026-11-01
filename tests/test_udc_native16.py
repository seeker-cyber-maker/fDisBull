"""Authored block boundaries exercise actual CPU instructions, not a model stub."""
import pytest
pytest.importorskip('unicorn')
from fdisbull.udc_native16 import execute_native16, NativeBlockError


def arithmetic(code, left=0xffff, right=2, carry=1):
 return execute_native16(bytes.fromhex(code),{},
   {'inputs':{'left':{'register':'ax'},'right':{'register':'bx'}},
    'flag_inputs':{'carry':0},'outputs':{'sum':{'register':'ax'}}},
   {'left':left,'right':right,'carry':carry},
   {'left':'u16','right':'u16','carry':'u8'},{'sum':'u16'})


def test_real_add_adc_and_carry_neutralization():
 assert arithmetic('01d8')['outputs']=={'sum':1}
 assert arithmetic('11d8')['outputs']=={'sum':2}
 r=arithmetic('f811d8');assert r['outputs']=={'sum':1}
 assert r['restored_registers']==r['caller_registers']
 assert r['execution']=='unicorn-x86-16' and r['steps']==2


def test_declared_memory_inputs_and_outputs():
 r=execute_native16(bytes.fromhex('a1100001d8a31200'),{},
   {'inputs':{'a':{'segment':'ds','offset':16},'b':{'register':'bx'}},
    'outputs':{'sum':{'segment':'ds','offset':18}}},
   {'a':8,'b':7},{'a':'u16','b':'u16'},{'sum':'u16'})
 assert r['outputs']=={'sum':15} and len(r['memory_writes'])==1


@pytest.mark.parametrize('code,reason',[
 ('cd21','host/device'),('ebfe','budget'),('a11000','read'),('a31200','write')])
def test_unsupported_effects_unbound_memory_and_nontermination_refuse(code,reason):
 with pytest.raises(NativeBlockError,match=reason):
  execute_native16(bytes.fromhex(code),{}, {'inputs':{},'outputs':{}},{},{},{},max_steps=20)


def test_segment_relocation_and_separate_runtime_region():
 # Authored MOV AX,selector; MOV ES,AX; load a mode byte; store it in DS output.
 code=bytes.fromhex('b8ffff8ec026a01000a22000')
 adapter={'inputs':{'mode':{'region':'mode','offset':16}},'outputs':{'value':{'segment':'ds','offset':32}},
          'relocations':[{'offset':1,'expected_hex':'ffff','region':'mode'}]}
 r=execute_native16(code,{},adapter,{'mode':7},{'mode':'u8'},{'value':'u8'})
 assert r['outputs']=={'value':7} and r['source_code_sha256']!=r['adapted_code_sha256']
 assert r['native_exit_registers']['es']!=r['caller_registers']['es']
 assert r['restored_registers']['es']==r['caller_registers']['es']
 adapter['relocations'][0]['offset']=0
 with pytest.raises(NativeBlockError,match='MOV immediate'):
  execute_native16(code,{},adapter,{'mode':7},{'mode':'u8'},{'value':'u8'})


def test_nondeterministic_cpu_and_code_state_aliases_are_outside_profile():
 with pytest.raises(NativeBlockError,match='host/device'):
  execute_native16(bytes.fromhex('0f31'),{}, {'inputs':{},'outputs':{}},{},{},{})
 with pytest.raises(NativeBlockError,match='state region'):
  execute_native16(bytes.fromhex('90'),{}, {'inputs':{'a':{'region':'code','offset':0}},'outputs':{}},{'a':7},{'a':'u8'},{})
