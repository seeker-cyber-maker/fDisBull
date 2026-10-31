"""Persist recovered Snake blocks and build a private interchangeable browser.

Only semantic recipes are public. The EXE, ROM font, full model/UDL, FDB and
generated browser are explicit private inputs/outputs.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

from fdisbull.project import Project
from fdisbull.udc_layers import digest
from fdisbull.udc_memory_layers import register_contract,register_layer,select_layers
from fdisbull.udc_memory_shell import build_memory_shell


def plan(program,palette):
    from examples.recovery.snake_model import STATE,INPUT,FRAME
    keymap={
        'ArrowUp':(0,72),'ArrowRight':(0,77),'ArrowDown':(0,80),'ArrowLeft':(0,75),
        'KeyW':(119,17),'KeyA':(97,30),'KeyS':(115,31),'KeyD':(100,32),
        'KeyP':(112,25),'Space':(32,57),'KeyN':(110,49),'KeyR':(114,19),'Escape':(27,1),
        'KeyX':(120,45),
    }
    keys={'keyboard_kind':1,'pointer_kind':2,'clock_kind':0,'quit_index':STATE['quit_requested'],
        'function':'action','tick_ms':1000/18.20648193}
    keys.update({key:INPUT[key] for key in ('kind','ascii','scan','x','y','buttons','clock')})
    bounds={name:(0,65535) for name in STATE}
    bounds.update(snake_length=(1,600),direction=(0,3),pending_direction=(0,3),paused=(0,1),game_status=(0,2),
                  mouse_present=(0,1),turn_queued=(0,1),needs_render=(0,1),step_requested=(0,1),quit_requested=(0,1),
                  mouse_buttons=(0,7),mouse_x=(0,319),mouse_y=(0,199))
    return {'format':'fdisbull-memory-orchestration-1','title':'Snake · recovered DOS fixture',
        'help':'Click the game to focus. Arrows/WASD turn, Space/P pauses, N steps, R resets and Esc quits. You can also click the blue controls. Starts paused.',
        'initialize':'reset','concurrency':'ordered-events',
        'bindings':{name:'wasm' for name in program['functions']},'inputs':list(INPUT.values()),
        'outputs':{'reset':[[0,621]],'step':[[0,621]],'action':[[0,621]],
                   'render':[[STATE['frame_count'],1],[STATE['needs_render'],1],[760,13],[FRAME,64000]]},
        'commit_ranges':[[0,621],[FRAME,64000]],'replace_ranges':[[0,621],[FRAME,64000]],
        'scratch_ranges':[[760,13]],
        'guards':[{'index':STATE[k],'min':lo,'max':hi} for k,(lo,hi) in bounds.items()]+[{'index':i,'min':0,'max':599} for i in range(600)],
        'array_guards':[{'offset':0,'length_index':STATE['snake_length'],'capacity':600,'min':0,'max':599,
            'unique':True,'adjacent_columns':30,'exclude':{'index':STATE['food_cell'],'when_index':STATE['game_status'],'when_value':0}}],
        'render':{'function':'render','when_nonzero':STATE['needs_render']},
        'frame':{'offset':FRAME,'width':320,'height':200,'palette':palette},'events':keys,
        'keymap':{k:{'ascii':a,'scan':s} for k,(a,s) in keymap.items()},'logic_functions':['action','step','reset']}


def prepare(original_root,model_root,output,executable,*,nested_step=False):
    original_root,model_root,output=(Path(p).resolve() for p in (original_root,model_root,output))
    if output.exists() or any((p/'.git').exists() for p in (output,*output.parents)):
        raise ValueError('choose a new private study root outside Git')
    observed=json.loads((original_root/'originals.json').read_text())
    recovery=json.loads((model_root/'recovery.json').read_text())
    program=json.loads((model_root/'snake.uil.json').read_text())
    udl=json.loads((model_root/'snake.udl.json').read_text())
    assert program['role']=='uil' and udl['role']=='udl' and {**udl,'role':'uil'}==program
    assert digest(program)==recovery['uil_sha256']
    target=Path(executable).resolve(strict=True)
    raw=target.read_bytes();source_sha=hashlib.sha256(raw).hexdigest()
    assert source_sha==recovery['original_sha256']=='f8b672501f85d2b3feae0fb8acae626cbff96b8f3e4fccee6a3eb1746031d9be'
    initial=json.loads((model_root/'initial-words.json').read_text())
    palette=json.loads((original_root/'palette.json').read_text())['colors']
    output.mkdir(parents=True)
    database=output/'snake.fdb';selections={};contracts={};layers={}
    with Project.create(database,target) as project:
        project.analyze(max_instructions=6000)
        # Pair logical UDL/UIL with exact retained machine spans. No source bytes
        # leave the private project and no inferred semantics become native facts.
        snippets={}
        sources={'step':['step','find-food'],'action':['keyboard','mouse','queue-direction','reset','step','find-food'],
                 'reset':['reset'],'render':['render','fill-rectangle','draw-cell','text']}
        for function,names in sources.items():
            spans=[{'address':hex(span['address']),'size':span['size']} for name in names
                   for span in observed['snippets'][name]['document']['spans']]
            if function=='action':spans.append({'address':'0x1004d','size':0xa4})
            snippets[function]=project.capture_snippet('snake-'+function,
                spans=spans,version=1,
                evidence={'source_assisted':True,'original_sha256':source_sha})['id']
            contract={'format':'fdisbull-block-contract-1','name':'snake-'+function,
                'inputs':{'arena':{'type':'u32-array','words':program['memory']['words']}},
                'outputs':{'arena':{'type':'u32-array','words':program['memory']['words']}},
                'behavior':{'kind':'memory-uil','program':program,'function':function},'effects':[],
                'evidence':{'source_snippet':snippets[function],'recovery':recovery,
                            'udl':udl,'source_to_model':'finite original CPU/native checks; no universal proof'}}
            contracts[function]=register_contract(project,contract)['id']
        for backend,target_profile in [('wasm','wasm32-memory-1'),('webgpu','webgpu-wgsl-memory-1')]:
            layers[backend]={}
            for function in program['functions']:
                doc={'format':'fdisbull-udl-layer-1','name':'snake-'+function+'-'+backend,
                    'contract':contracts[function],'snippet':snippets[function],
                    'implementation':{'backend':'memory-uil','target':target_profile,'program':program,'function':function},
                    'assurance':'same exact semantic model; emitted execution qualified separately',
                    'evidence':{'original_sha256':source_sha,'uil_sha256':digest(program)}}
                layers[backend][function]=register_layer(project,doc)['id']
            selections[backend]=select_layers(project,'snake-'+backend,layers[backend],program=program,target=target_profile)['id']
        cuts=None
        if nested_step:
            cuts={'format':'fdisbull-memory-cuts-1','module_uil_sha256':digest(program),
                'cuts':[{'caller':'action','entry':entry,'callee':'step'} for entry in ('action.87','action.153')]}
        manifest=build_memory_shell(project,selections,plan(program,palette),initial,output/'browser',cuts=cuts)
    with Project(database) as project:
        assert project.db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        for backend,selection in selections.items():
            assert project.udl_selection_info(selection,full=True)['document']['program']==program
    receipt={'format':'fdisbull-snake-browser-build-1','original_sha256':source_sha,
        'module_uil_sha256':digest(program),'udl_sha256':digest(udl),'database':str(database),
        'database_reopened':True,'contracts':contracts,'layers':layers,'selections':selections,
        'browser':str(output/'browser'),'manifest_sha256':hashlib.sha256((output/'browser/memory-shell.json').read_bytes()).hexdigest(),
        'artifacts':manifest['artifacts'],'original_root':str(original_root),'model_root':str(model_root),
        'execution':False,'scope':'source-assisted recovered model and build identities; execution receipt separate'}
    if nested_step:receipt['cut_plan_sha256']=manifest['cuts']['cut_plan_sha256']
    (output/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('original',type=Path);p.add_argument('model',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--executable',type=Path,required=True)
    p.add_argument('--nested-step',action='store_true',help='Route exact recovered action step regions through the selected step backing')
    a=p.parse_args();print(json.dumps(prepare(a.original,a.model,a.output,a.executable,nested_step=a.nested_step)))
