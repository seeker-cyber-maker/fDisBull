"""End-to-end persisted module selection under a fixed shared UIL contract."""
import copy
import pytest
from fdisbull.project import Project
from fdisbull.udc_layers import register_contract, register_layer, select_layers, run_selection, LayerQualificationError


def project(tmp_path,name,byte=0xc3):
 source=tmp_path/(name+'.bin');source.write_bytes(bytes([byte])+bytes(31))
 return Project.create(tmp_path/(name+'.fdb'),source,arch='x86',bits=16,base=0x1000)


def contract():
 program={'format':'fdisbull-il-1','role':'uil','variables':{n:{'type':'u16' if n!='$carry' else 'u8','initial':0} for n in ('$left','$right','$sum','$carry')},'resources':{},'body':[
  {'id':'copy','op':'set','var':'$sum','value':{'var':'$left'}},{'id':'add','op':'add','var':'$sum','value':{'var':'$right'}}]}
 return {'format':'fdisbull-block-contract-1','name':'intent.add.two','inputs':{'left':'u16','right':'u16','carry':'u8'},'outputs':{'sum':'u16'},'domain':{'carry':{'min':0,'max':1}},'behavior':{'kind':'uil','program':program}}


def layer(cid,name,code):
 return {'format':'fdisbull-udl-layer-1','name':name,'contract':cid,'implementation':{'backend':'x86-16','code_hex':code},'adapter':{
  'inputs':{'left':{'register':'ax'},'right':{'register':'bx'}},'flag_inputs':{'carry':0},'outputs':{'sum':{'register':'ax'}}}}


def test_select_add_or_carry_neutralized_adc_in_two_different_projects(tmp_path):
 pytest.importorskip('unicorn')
 with project(tmp_path,'a') as p:
  c=register_contract(p,contract());a=register_layer(p,layer(c['id'],'add','01d8'));b=register_layer(p,layer(c['id'],'adc-clear','f811d8'))
  s1=select_layers(p,'first',{'math':a['id']});s2=select_layers(p,'second',{'math':b['id']})
  for chosen in (s1,s2):
   r=run_selection(p,chosen['id'],'math',{'left':65535,'right':2,'carry':1});assert r['outputs']=={'sum':1};assert r['comparison']=='matched_reference_uil'
  with pytest.raises(LayerQualificationError):
   wrong=register_layer(p,layer(c['id'],'adc-observes-carry','11d8'));s=select_layers(p,'wrong',{'math':wrong['id']});run_selection(p,s['id'],'math',{'left':4,'right':7,'carry':1})
 with Project(tmp_path/'a.fdb') as p:assert run_selection(p,s2['id'],'math',{'left':1,'right':2,'carry':0})['outputs']=={'sum':3}
 with project(tmp_path,'different',0x90) as p:
  c2=register_contract(p,contract());b2=register_layer(p,layer(c2['id'],'adc-clear','f811d8'))
  assert c2['id']==c['id'] and b2['id']==b['id']
  s=select_layers(p,'third',{'math':b2['id']});assert run_selection(p,s['id'],'math',{'left':10,'right':3,'carry':1})['outputs']=={'sum':13}


def test_incompatible_selection_and_bad_inputs_fail_without_mutation(tmp_path):
 with project(tmp_path,'a') as p:
  c=register_contract(p,contract());a=register_layer(p,layer(c['id'],'add','01d8'));s=select_layers(p,'one',{'math':a['id']})
  with pytest.raises(ValueError):run_selection(p,s['id'],'math',{'left':1,'right':2,'carry':3})
  with pytest.raises(ValueError):run_selection(p,s['id'],'missing',{'left':1,'right':2,'carry':0})
  assert p.version()['id']==1


@pytest.mark.parametrize('change', ['metadata', 'text', 'order', 'resource-data'])
def test_event_contract_compares_behavior_and_retains_provenance(tmp_path, change):
 from fdisbull.udc_qualify import qualify_uil
 from fdisbull.udc_layers import run_layer
 reference=contract()
 program=reference['behavior']['program']
 program['resources']={'first':{'kind':'text','text':'First'},'second':{'kind':'text','text':'Second'}}
 program['evidence']={'reference':{'description':'authored reference'}}
 program['body'] += [{'id':'original-first','op':'text','resource':'first','evidence':['reference']},
                     {'id':'original-second','op':'text','resource':'second'}]
 replacement=copy.deepcopy(program)
 replacement['evidence']={'implementation':{'description':'authored replacement'}}
 replacement['body'][-2].update(id='replacement-first',evidence=['implementation'])
 replacement['body'][-1]['id']='replacement-second'
 if change=='text':replacement['body'][-2]['resource']='second'
 if change=='order':replacement['body'][-2:]=reversed(replacement['body'][-2:])
 if change=='resource-data':replacement['resources']['first']['text']='Changed'
 implementation={'backend':'uil','program':replacement}
 with project(tmp_path,'event') as p:
  c=register_contract(p,reference)
  l=register_layer(p,{'format':'fdisbull-udl-layer-1','name':'event-replacement','contract':c['id'],'implementation':implementation})
  if change=='metadata':
   assert qualify_uil(reference,implementation)['status']=='equivalent_under_contract'
   receipt=run_layer(p,l['id'],{'left':1,'right':2,'carry':0})
   assert receipt['events'][0]['block_id']=='replacement-first'
   assert receipt['events'][0]['evidence']==['implementation']
   assert receipt['expected']['events'][0]['block_id']=='original-first'
   s=select_layers(p,'event-selection',{'math':l['id']})
   assert run_selection(p,s['id'],'math',{'left':1,'right':2,'carry':0})['comparison']=='matched_reference_uil'
  else:
   with pytest.raises(LayerQualificationError):run_layer(p,l['id'],{'left':1,'right':2,'carry':0})
