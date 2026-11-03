"""A fixed symbolic UIL invokes selected, reusable native module definitions."""
import copy
import pytest
from fdisbull.project import Project
from fdisbull.udc_layers import register_contract,register_layer,select_layers
from fdisbull.udc_blueprint import execute_module_uil


def test_fixed_rng_intent_allows_declared_algorithm_variation(tmp_path):
 pytest.importorskip('unicorn')
 raw=tmp_path/'a.bin';raw.write_bytes(b'\xc3'+bytes(31))
 with Project.create(tmp_path/'a.fdb',raw,arch='x86',bits=16,base=0x1000) as p:
  c=register_contract(p,{'format':'fdisbull-block-contract-1','name':'rng.seed.step','inputs':{'seed':'u16'},'outputs':{'seed':'u16'},'behavior':{'kind':'bounded','bounds':{'seed':{'min':0,'max':65535}},'policy':'deterministic native seed step; algorithm/sequence implementation-defined; no fairness claim'}})
  layers=[]
  for name,code in [('add-one','40'),('add-three','050300')]:
   layers.append(register_layer(p,{'format':'fdisbull-udl-layer-1','name':name,'contract':c['id'],'implementation':{'backend':'x86-16','code_hex':code},'adapter':{'inputs':{'seed':{'register':'ax'}},'outputs':{'seed':{'register':'ax'}}}}))
  program={'format':'fdisbull-module-uil-1','role':'uil','variables':{'$seed':{'type':'u16','initial':9},'$face':{'type':'u16','initial':0}},'resources':{},'body':[
   {'id':'roll','op':'invoke','binding':'rng','contract':c['id'],'inputs':{'seed':{'var':'$seed'}},'outputs':{'seed':'$seed'}},
   {'id':'copy','op':'set','var':'$face','value':{'var':'$seed'}},{'id':'reduce','op':'remainder','var':'$face','value':6},{'id':'one-based','op':'add','var':'$face','value':1}]}
  selections=[select_layers(p,name,{'rng':layer['id']},program=program) for name,layer in zip(('a','b'),layers)]
  results=[execute_module_uil(p,program,s['id']) for s in selections]
  assert [r['state']['$seed'] for r in results]==[10,12]
  assert [r['state']['$face'] for r in results]==[5,1]
  assert results[0]['uil_sha256']==results[1]['uil_sha256']
  udl=copy.deepcopy(program);udl['role']='udl'
  assert execute_module_uil(p,udl,selections[0]['id'])['state']==results[0]['state']
  refused=execute_module_uil(p,program,selections[0]['id'],max_steps=1)
  assert refused['status']=='refused' and refused['state']['$seed']==9
  malformed=copy.deepcopy(program);malformed['body'][0]['outputs']['seed']='$face';malformed['variables']['$face']['type']='u8'
  with pytest.raises(ValueError,match='type differs'):execute_module_uil(p,malformed,selections[0]['id'])
