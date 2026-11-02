"""Generated freestanding C realizes the fixed scalar contract and private ABI."""
import copy
import shutil
from pathlib import Path
import pytest
from fdisbull.udc_c import generate_c,compile_c
from fdisbull.udc_shell import build_windows_shell
from fdisbull.udc_linux import build_linux_shell
from test_udc_linux import example,adapters


def compiler():
 c=shutil.which('clang')
 if not c:pytest.skip('Explicit clang required for freestanding C backend')
 return c


def test_c_math_is_relocatable_free_and_identical_between_native_shells(tmp_path):
 plan,modules=example();modules['math']['backend']='c-uil';before=copy.deepcopy(modules)
 c=compile_c(modules['math'],compiler());assert c['code_hex'] and c['inputs']==['$left','$right'] and c['outputs']==['$sum']
 assert 'unsigned long long udc_block' in c['source'] and c['compiler']['sha256']
 w=build_windows_shell(plan,modules,tmp_path/'win',c_compiler=compiler())
 l=build_linux_shell(plan,modules,tmp_path/'linux',service_adapters=adapters(),capture_state=True,c_compiler=compiler())
 assert w['slots']['module:math']['sha256']==l['slots']['module:math']['sha256']
 assert w['c_modules']['math']['code_sha256']==l['c_modules']['math']['code_sha256']
 assert modules==before


def test_c_refuses_effects_and_missing_compiler(tmp_path):
 plan,modules=example();m=modules['math'];m['backend']='c-uil'
 with pytest.raises(ValueError,match='explicit clang'):compile_c(m,None)
 m['program']['resources']={'x':{'kind':'text','text':'x'}};m['program']['body'].append({'id':'text','op':'text','resource':'x'})
 with pytest.raises(ValueError,match='pure scalar'):generate_c(m)
 assert not (tmp_path/'bad').exists()


def test_c_backend_reuses_definition_across_binaries_and_state_placements(tmp_path):
 from fdisbull.project import Project
 from fdisbull.udc_layers import register_contract,register_layer,select_layers,build_selection_shell
 identities=[];kernels=[];wrappers=[]
 for i in range(2):
  plan,m=example();program=m['math']['program'];src=tmp_path/f'source{i}.bin';src.write_bytes(b'\xc3'+bytes(i))
  if i:plan['state']['$aaa']={'type':'u8','initial':7}
  with Project.create(tmp_path/f'p{i}.fdb',src,arch='x86',bits=16,base=0x1000) as p:
   c=register_contract(p,{'format':'fdisbull-block-contract-1','name':'reusable','inputs':{'left':'u16','right':'u16'},'outputs':{'sum':'u16'},'behavior':{'kind':'uil','program':program}})
   l=register_layer(p,{'format':'fdisbull-udl-layer-1','name':'portable.C','contract':c['id'],'implementation':{'backend':'c-uil','program':program,'return':'$sum'}})
   plan['functions']['main']['body']=plan['functions']['main']['body'][:1]
   s=select_layers(p,'fixed',{'math':l['id']},program=program)
   b=build_selection_shell(p,s['id'],plan,tmp_path/f'out{i}',target='linux-x64',capture_state=True,c_compiler=compiler())
   identities.append((c['id'],l['id']));kernels.append(b['c_modules']['math']['code_sha256']);wrappers.append(b['slots']['module:math']['sha256'])
 assert identities[0]==identities[1] and kernels[0]==kernels[1]
 assert wrappers[0]!=wrappers[1]  # physical arena offsets belong to the adapter


def typed_case(tmp_path):
 program={'format':'fdisbull-il-1','role':'uil','variables':{'$byte':{'type':'u8','initial':0},'$signed':{'type':'i16','initial':0},'$flag':{'type':'bool','initial':False},'$wide':{'type':'u16','initial':0},'$sum':{'type':'u16','initial':0}},'resources':{},'body':[
 {'id':'sign','op':'require','condition':{'op':'and','conditions':[{'op':'bit_test','value':{'var':'$signed'},'bit':63},{'op':'not','condition':{'op':'eq','left':{'var':'$signed'},'right':{'var':'$wide'}}}]}},
 {'id':'byte','op':'add','var':'$byte','value':1},{'id':'signed','op':'subtract','var':'$signed','value':32767},
 {'id':'flag','op':'set','var':'$flag','value':True},{'id':'sum','op':'set','var':'$sum','value':{'var':'$wide'}},{'id':'wrap','op':'add','var':'$sum','value':2}]}
 state=copy.deepcopy(program['variables']);state['$byte']['initial']=255;state['$signed']['initial']=-1;state['$wide']['initial']=65535
 plan={'format':'fdisbull-native-shell-1','entry':'main','state':state,'resources':{},'functions':{'main':{'body':[{'op':'call','binding':'math'}],'return':{'var':'$sum'}}}}
 m={'math':{'backend':'c-uil','program':program,'return':'$sum','state_adapter':{'inputs':['$byte','$signed','$flag','$wide'],'outputs':['$byte','$signed','$flag','$sum']}}}
 return build_linux_shell(plan,m,tmp_path,capture_state=True,c_compiler=compiler())


def test_actual_c_word_ports_signed_input_wrapping_and_boolean_output(tmp_path):
 from test_udc_linux import run_native_linux
 from fdisbull.udc_linux import decode_observation
 build=typed_case(tmp_path/'typed')
 run,frame=run_native_linux(tmp_path/'typed/program',tmp_path)
 decoded=decode_observation(frame,build)
 assert run.returncode==0 and decoded['value']==1
 assert decoded['state']=={'$byte':0,'$signed':-32768,'$flag':True,'$wide':65535,'$sum':1}
