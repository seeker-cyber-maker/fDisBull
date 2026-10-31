"""Derive private RNG experiments without changing the accepted Snake UIL.

The alternative references intentionally differ from the original semantics.
Actual emitted execution and original CPU witnesses remain separate evidence.
"""
from copy import deepcopy
import base64
import hashlib
import json
from pathlib import Path

from fdisbull.udc_layers import digest
from fdisbull.udc_web_memory import execute_memory_uil
from examples.recovery.snake_model import STATE, INPUT, FRAME


def prepare(model_root, probe_root, destination):
    model_root,probe_root,destination=map(Path,(model_root,probe_root,destination))
    if destination.exists() or any((p/'.git').exists() for p in (destination,*destination.parents)):
        raise ValueError('choose new private output outside Git')
    study=json.loads((model_root/'browser-study-06.json').read_text())
    canonical=json.loads((model_root/'snake.uil.json').read_text())
    initial=json.loads((model_root/'initial-words.json').read_text())
    assert digest(canonical)==study['uil_sha256']=='a2b8887d968ce6418b0e5ed0b91c631809c010d69f1b727f3cfcc998530cc720'
    variant=json.loads((probe_root/'lfsr16-variant-store.json').read_text())
    probe=json.loads((probe_root/'independent-rng-results.json').read_text())
    alternate=deepcopy(canonical)
    def replace(nodes):
        for node in nodes:
            if node.get('id') in ('step.44','action.130','action.196'):
                node.update(value=deepcopy(variant['value']))
            if node['op']=='if':replace(node['then']);replace(node['else'])
            elif node['op']=='while':replace(node['body'])
    for fn in alternate['functions'].values():replace(fn['body'])
    def source_initial():
        words=initial.copy()
        for name,value in study['initial_services'].items():words[STATE[name]]=value
        return words
    def apply(program,words,function,event=None):
        staged=words.copy()
        for name,value in (event or {}).items():staged[INPUT[name]]=value
        result=execute_memory_uil(program,function,staged)
        assert result['status']=='complete',(function,result['status'])
        staged=result['words']
        if staged[STATE['needs_render']]:
            result=execute_memory_uil(program,'render',staged);assert result['status']=='complete'
            staged=result['words']
        words[:621]=staged[:621];words[FRAME:FRAME+64000]=staged[FRAME:FRAME+64000]
    def observation(words,ident,events,intervention=None):
        frame=bytes(words[FRAME:FRAME+64000]);sha=hashlib.sha256(frame).hexdigest()
        study['raster_data'][sha]=base64.b64encode(frame).decode()
        result={'id':ident,'events':events,'expected_state':words[:621],
                'frame':{'sha256':sha}}
        if intervention:result['intervention']=intervention
        return result
    words=source_initial();apply(alternate,words,'reset',{'clock':study['initial_services']['last_tick']})
    observations=[]
    for row in study['observations']:
        if row.get('intervention'):words[:len(row['intervention']['words'])]=row['intervention']['words']
        for event in row['events']:apply(alternate,words,'action',event)
        observations.append(observation(words,row['id'],row['events'],row.get('intervention')))
    print('alternate carried references complete',flush=True)
    outcome={}
    for choice,program in [('original',canonical),('lfsr16',alternate),('hot_swap',canonical)]:
        words=source_initial();apply(program,words,'reset',{'clock':100})
        rows=[];clock=100
        for number in range(1,27):
            if choice=='hot_swap' and number==5:program=alternate
            events=[]
            direction={22:80,24:75,25:72,26:77}.get(number)
            if direction:events.append({'kind':1,'ascii':0,'scan':direction,'clock':clock+1})
            events.append({'kind':1,'ascii':110,'scan':49,'clock':clock+2})
            for event in events:apply(program,words,'action',event)
            clock+=2
            witness=probe['ordinary_route']['steps'][number-1]
            original_path=choice!='lfsr16'
            expected=dict(witness['original' if original_path else 'alternate'])
            if choice=='hot_swap' and number>=23:expected.update(rng_seed=41134,food_cell=334)
            for name,value in expected.items():assert words[STATE[name]]==value,(choice,number,name)
            body=witness['original_cells' if original_path else 'alternate_cells']
            assert words[:len(body)]==body
            rows.append(observation(words,'outcome-step-'+str(number),events))
        outcome[choice]=rows
        print(choice+' outcome references complete',flush=True)
    cases=json.loads((probe_root/'alternate-cases.json').read_text())['cases']
    study['rng']={'cases':cases,'transitions':probe['transitions'],'alternate_observations':observations,
        'outcome':outcome,'reference':{
            'canonical_uil_sha256':digest(canonical),'alternative_reference_sha256':digest(alternate),
            'method':'independent scalar recurrence plus intentionally changed private model; unchanged source-qualified renderer',
            'original_outcome_cpu_calls':probe['ordinary_route']['original_cpu_step_calls'],
            'original_outcome_adapter':probe['ordinary_route']['adapter'],
            'claim':'Alternative expectations are not original-equivalence claims; original CPU witnesses qualify the baseline separately'}}
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(study,separators=(',',':'))+'\n')
    print(json.dumps({'destination':str(destination),'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
        'alternate_cases':len(cases),'alternate_observations':len(observations),'outcome_steps':26}))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model_root',type=Path);parser.add_argument('probe_root',type=Path);parser.add_argument('destination',type=Path)
    args=parser.parse_args();prepare(args.model_root,args.probe_root,args.destination)
