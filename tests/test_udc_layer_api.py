"""Immutable documents and typed ports survive the public JSON protocol."""
from fdisbull.cli import respond
from fdisbull.project import Project


def test_contract_and_snippet_protocol_preserves_scalar_fields_named_address(tmp_path):
 raw=tmp_path/'raw.bin';raw.write_bytes(b'\xc3'+bytes(31));db=tmp_path/'a.fdb'
 with Project.create(db,raw,arch='x86',bits=16,base=0x1000):pass
 def call(method,**params):
  result=respond({'method':method,'params':{'project':str(db),**params}})
  assert result['ok'],result
  return result['result']
 contract={'format':'fdisbull-block-contract-1','name':'identity','inputs':{'address':'u16'},'outputs':{'target':'u16'},'behavior':{'kind':'uil','program':{
  'format':'fdisbull-il-1','role':'uil','variables':{'$address':{'type':'u16','initial':0},'$target':{'type':'u16','initial':0}},'resources':{},'body':[{'id':'copy','op':'set','var':'$target','value':{'var':'$address'}}]}}}
 c=call('store-block-contract',document=contract)
 layer={'format':'fdisbull-udl-layer-1','name':'portable','contract':c['id'],'implementation':{'backend':'uil','program':contract['behavior']['program']}}
 l=call('store-udl-layer',document=layer);s=call('select-udl-layers',name='chosen',bindings={'slot':l['id']})
 r=call('run-udl-selection',selection=s['id'],binding='slot',inputs={'address':7})
 assert r['inputs']['address']==7 and r['outputs']['target']==7
 snippet=call('capture-snippet',name='ret',spans=[{'address':'0x1000','size':1}])
 info=call('snippet-info',snippet=snippet['id'],full=True)
 assert info['document']==snippet['document'] and type(info['document']['spans'][0]['address']) is int


def test_wrong_native_backing_returns_replayable_counterexample(tmp_path):
 import pytest
 pytest.importorskip('unicorn')
 raw=tmp_path/'raw.bin';raw.write_bytes(b'\xc3'+bytes(31));db=tmp_path/'a.fdb'
 with Project.create(db,raw,arch='x86',bits=16,base=0x1000):pass
 def call(method,**params):return respond({'method':method,'params':{'project':str(db),**params}})
 program={'format':'fdisbull-il-1','role':'uil','variables':{v:{'type':'u16','initial':0} for v in ('$left','$right','$sum')},'resources':{},'body':[{'id':'copy','op':'set','var':'$sum','value':{'var':'$left'}},{'id':'plus','op':'add','var':'$sum','value':{'var':'$right'}}]}
 c=call('store-block-contract',document={'format':'fdisbull-block-contract-1','name':'sum','inputs':{'left':'u16','right':'u16'},'outputs':{'sum':'u16'},'behavior':{'kind':'uil','program':program}})['result']
 # Carry is deliberately set in the physical adapter, while the logical intent
 # is just two-value addition. ADC must be rejected for the supplied inputs.
 l=call('store-udl-layer',document={'format':'fdisbull-udl-layer-1','name':'wrong-adc','contract':c['id'],'implementation':{'backend':'x86-16','code_hex':'f911d8'},'adapter':{'inputs':{'left':{'register':'ax'},'right':{'register':'bx'}},'outputs':{'sum':{'register':'ax'}}}})['result']
 response=call('run-udl-layer',layer=l['id'],inputs={'left':4,'right':7})
 assert response['ok'] is False
 receipt=response['error']['qualification']
 assert receipt['inputs']=={'left':4,'right':7} and receipt['outputs']=={'sum':12} and receipt['expected']['outputs']=={'sum':11}
