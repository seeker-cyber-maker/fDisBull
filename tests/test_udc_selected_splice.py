"""Selection-to-artifact wiring uses public scalar/UIL and byte-placement contracts."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
from fdisbull.project import Project
from fdisbull.udc_layers import register_contract,register_layer,select_layers,compile_splice_selection
from fdisbull.udc_blueprint import execute_module_uil


def sha(b):return hashlib.sha256(b).hexdigest()


def setup(tmp_path):
 source=tmp_path/'source.com';source.write_bytes(bytes.fromhex('909090900000c3'))
 p=Project.create(tmp_path/'source.fdb',source,arch='x86',bits=16,base=0x100)
 snippet=p.capture_snippet('whole source',[{'file':'source','offset':0,'size':7}])
 c=register_contract(p,{'format':'fdisbull-block-contract-1','name':'step','inputs':{'seed':'u16'},'outputs':{'seed':'u16'},'behavior':{'kind':'bounded','bounds':{'seed':{'min':0,'max':65535}},'policy':'algorithm intentionally variable'}})
 l=register_layer(p,{'format':'fdisbull-udl-layer-1','name':'increment','contract':c['id'],'implementation':{'backend':'x86-16','code_hex':'40'},'adapter':{'inputs':{'seed':{'register':'ax'}},'outputs':{'seed':{'register':'ax'}}}})
 program={'format':'fdisbull-module-uil-1','role':'uil','variables':{'$seed':{'type':'u16','initial':9}},'resources':{'notice':{'kind':'text','text':'OK'}},'body':[{'id':'step','op':'invoke','binding':'rng','contract':c['id'],'inputs':{'seed':{'var':'$seed'}},'outputs':{'seed':'$seed'}},{'id':'message','op':'text','resource':'notice'}]}
 s=select_layers(p,'fixed',{'rng':l['id']},program=program)
 recipe={'format':'fdisbull-udc-splice-selection-1','source_snippet':snippet['id'],'placements':[{'binding':'rng','offset':0,'size':3,'expected_sha256':sha(b'\x90'*3),'prologue_hex':'','epilogue_hex':'','continuation':3}],'data_bindings':[{'block':'message','encoding':'ascii-text','offsets':[4,5],'expected_sha256':[sha(b'\0')]*2}]}
 return p,source,program,s,recipe


def test_fixed_uil_drives_module_and_text_placement_and_pinned_capsule(tmp_path):
 with setup(tmp_path)[0] as p:
  # Reopen setup inputs through the persisted store, without retained host objects.
  s=p.udl_selections()['items'][0];program=p.udl_selection_info(s['id'],full=True)['document']['program']
  source=tmp_path/'source.com';snippet=p.snippets()['items'][0]
  recipe={'format':'fdisbull-udc-splice-selection-1','source_snippet':snippet['id'],'placements':[{'binding':'rng','offset':0,'size':3,'expected_sha256':sha(b'\x90'*3),'prologue_hex':'','epilogue_hex':'','continuation':3}],'data_bindings':[{'block':'message','encoding':'ascii-text','offsets':[4,5],'expected_sha256':[sha(b'\0')]*2}]}
  result=compile_splice_selection(p,s['id'],recipe,tmp_path/'output')
  out=Path(result['artifact']).read_bytes()
  assert out[:3]==bytes.fromhex('e90400') and out[4:6]==b'OK' and out[7:]==bytes.fromhex('40e9f8ff')
  capsule=json.loads(Path(result['selection_capsule']).read_text());assert capsule['selection']==s['id'] and capsule['uil_sha256']==sha(json.dumps(program,sort_keys=True,separators=(',',':')).encode())
  assert source.read_bytes()==bytes.fromhex('909090900000c3') and p.version()['id']==1


def test_bad_bindings_hashes_and_names_never_emit(tmp_path):
 p,source,program,s,recipe=setup(tmp_path)
 with p:
  bads=[]
  bad=copy.deepcopy(recipe);bad['data_bindings'][0]['expected_sha256'][0]='0'*64;bads.append(bad)
  bad=copy.deepcopy(recipe);bad['placements'][0]['binding']='missing';bads.append(bad)
  bad=copy.deepcopy(recipe);bad['data_bindings'][0]['offsets']=[4];bads.append(bad)
  bad=copy.deepcopy(recipe);bad['data_patches']=[];bads.append(bad)
  for i,bad in enumerate(bads):
   with pytest.raises(ValueError):compile_splice_selection(p,s['id'],bad,tmp_path/f'bad{i}')
   assert not (tmp_path/f'bad{i}').exists()
  with pytest.raises(ValueError,match='conflicts'):compile_splice_selection(p,s['id'],recipe,tmp_path/'reserved',output_name='SELECTION-CAPSULE.JSON')
  assert not (tmp_path/'reserved').exists()
  changed=copy.deepcopy(program);changed['body']=changed['body'][1:]
  no_call=select_layers(p,'no call',{'rng':s['document']['bindings']['rng']},program=changed)
  with pytest.raises(ValueError,match='fixed UIL'):compile_splice_selection(p,no_call['id'],recipe,tmp_path/'no-call')


def test_capsule_failure_removes_only_its_new_output(tmp_path,monkeypatch):
 p,source,program,s,recipe=setup(tmp_path)
 with p:
  original_open=Path.open
  def fail_capsule(self,*args,**kwargs):
   if self.name=='selection-capsule.json':raise OSError('injected write failure')
   return original_open(self,*args,**kwargs)
  monkeypatch.setattr(Path,'open',fail_capsule)
  with pytest.raises(OSError,match='injected'):
   compile_splice_selection(p,s['id'],recipe,tmp_path/'partial')
  assert not (tmp_path/'partial').exists()
  assert source.read_bytes()==bytes.fromhex('909090900000c3')
