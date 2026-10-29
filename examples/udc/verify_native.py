"""Compare bounded original and compiler-emitted DOS Zork actions privately.

Inputs must be separate directories and include emitted executable/resources.
No game payload, project database, checkpoint or capture is made public here.
"""
import argparse
import copy
import subprocess
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import time

from PIL import Image

from fdisbull.project import Project
from fdisbull.zmachine import inspect_story
from fdisbull.zork_recovery import state_from_ram


def inventory(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def zork_helpers():
    path=Path(__file__).resolve().parents[1]/'zork'/'verify_harness.py'
    spec=importlib.util.spec_from_file_location('_udc_zork_helpers',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def verify_zork(original,emitted,backend,output):
    original=Path(original).resolve(strict=True);emitted=Path(emitted).resolve(strict=True)
    output=Path(output).resolve();backend=Path(backend).resolve(strict=True)
    if output.exists() or original==emitted or any(a==b or a in b.parents or b in a.parents
        for a,b in ((output,original),(output,emitted),(original,emitted))):
        raise ValueError('Input and new output directories must be distinct and disjoint')
    selected=('_ZORK1.COM','DATA/ZORK1.DAT','SETUP.INF')
    hashes={}
    for name in selected:
        a=(original/name).read_bytes();b=(emitted/name).read_bytes()
        if a!=b:raise ValueError('Emitted input does not match original: '+name)
        hashes[name]=hashlib.sha256(a).hexdigest()
    if hashes['_ZORK1.COM']!='2a6f366349be71ef4a164e3fc9c31a4a3d8c24ee6ddac93ed345c993c3562514':
        raise ValueError('Unqualified Zork interpreter')
    initial={'original':inventory(original),'emitted':inventory(emitted)}
    output.mkdir(parents=True);helper=zork_helpers();results={};started=time.monotonic()
    for label,source in (('original',original),('emitted',emitted)):
        target=output/label;game=target/'game';game.mkdir(parents=True)
        for name in selected:
            destination=game/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,destination)
        copied=inventory(game);story=game/'DATA/ZORK1.DAT';info=inspect_story(story)
        with Project.create(target/'private.fdb',game/'_ZORK1.COM',image='com') as project:
            project.analyze(start='1000:2bdd',max_instructions=2000)
            with project.debugger(backend,game,version=1) as dos:
                breakpoint=dos.breakpoint('1000:2bdd');stop=dos.run(timeout_ms=5000,fast_forward=True)
                if stop['outcome']!='breakpoint':raise RuntimeError('Story mapping breakpoint not reached')
                registers=dos.registers();base=helper.scalar(registers,'ds')*16+helper.scalar(registers,'edx')
                if helper.read(dos,base,512)!=story.read_bytes()[:512]:raise RuntimeError('Story mapping mismatch')
                dos.delete_breakpoint(breakpoint['breakpoint_id']);opening=helper.prompt(dos)
                before=state_from_ram(helper.read(dos,base,info['static_memory']))
                dos.keyboard_type('open mailbox\n');first=helper.prompt(dos)
                after=state_from_ram(helper.read(dos,base,info['static_memory']))
                first_text=helper.normalized(helper.response(opening,first,'open mailbox'))
                shot=dos.screenshot('mailbox.png');project.debug_export(shot['artifact'],target/'mailbox.png')
                dos.keyboard_type('open mailbox\n');second=helper.prompt(dos)
                second_text=helper.normalized(helper.response(first,second,'open mailbox'))
                repeated=state_from_ram(helper.read(dos,base,info['static_memory']))
                trace=dos.trace('prompt-trace.json',count=64,timeout_ms=5000,fast_forward=True)
                project.debug_export(trace['artifact'],target/'prompt-trace.json')
                results[label]={'before':before,'after':after,'repeated':repeated,'first_text':first_text,
                                'second_text':second_text,'screenshot_sha256':shot['sha256'],
                                'trace_complete':trace['metadata'].get('complete') is True}
        if inventory(game)!=copied:raise RuntimeError('Private input changed during native run')
        with Project(target/'private.fdb') as project:
            project.debug_export(shot['artifact'],target/'mailbox-reopened.png')
            if hashlib.sha256((target/'mailbox-reopened.png').read_bytes()).hexdigest()!=shot['sha256']:
                raise RuntimeError('Stored screenshot changed after reopen')
    if inventory(original)!=initial['original'] or inventory(emitted)!=initial['emitted']:
        raise RuntimeError('An input directory changed')
    equal={key:results['original'][key]==results['emitted'][key] for key in ('before','after','repeated','first_text','second_text')}
    receipt={'format':'fdisbull-udc-native-zork-1','input_sha256':hashes,'backend_sha256':hashlib.sha256(backend.read_bytes()).hexdigest(),
             'scope':'Fresh independent DOS runs; selected mailbox fields and normalized command responses only',
             'comparisons':equal,'trace_complete':{k:v['trace_complete'] for k,v in results.items()},
             'screenshot_sha256':{k:v['screenshot_sha256'] for k,v in results.items()},
             'inputs_unchanged':True,'stored_screenshot_reopen':True,'elapsed_seconds':round(time.monotonic()-started,3)}
    (output/'verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if not all(equal.values()) or not all(receipt['trace_complete'].values()):raise RuntimeError('Bounded comparison incomplete')
    return receipt


def verify_dinopark(original,emitted,backend,output):
    original=Path(original).resolve(strict=True);emitted=Path(emitted).resolve(strict=True)
    output=Path(output).resolve();backend=Path(backend).resolve(strict=True)
    if output.exists() or any(a==b or a in b.parents or b in a.parents
        for a,b in ((output,original),(output,emitted),(original,emitted))):
        raise ValueError('Input and new output directories must be distinct and disjoint')
    source_inventory=inventory(original)
    selected={k:v for k,v in source_inventory.items() if not Path(k).name.upper().startswith('DINOSG.')}
    if selected.get('DINOPARK.EXE')!='2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c':
        raise ValueError('Unqualified DinoPark executable')
    emitted_inventory=inventory(emitted)
    if any(emitted_inventory.get(k)!=v for k,v in selected.items()):raise ValueError('Emitted game resources differ')
    output.mkdir(parents=True);results={};started=time.monotonic()
    for label,source in (('original',original),('emitted',emitted)):
        target=output/label;game=target/'game';game.mkdir(parents=True)
        for name in selected:
            dest=game/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,dest)
        copied=inventory(game)
        with Project.create(target/'private.fdb',game/'DINOPARK.EXE',load_segment=0x1000) as project:
            with project.debugger(backend,game) as dos:
                def run(ms):
                    result=dos.run(guest_ms=ms,timeout_ms=15000,fast_forward=True,stop_on_hook=True)
                    if result['outcome']!='guest_time' or result.get('hook_hits'):raise RuntimeError('Unexpected guest stop')
                def click(x,y):dos.click(x,y,hold_ms=80)
                def frame(name):
                    shot=dos.screenshot(name+'.png');project.debug_export(shot['artifact'],target/(name+'.png'))
                    return {'sha256':shot['sha256'],'artifact':shot['artifact'],'selector_hex':dos.memory('4020:3c5c',length=2)['hex']}
                run(35000);click(80,160);run(2500);click(160,132);run(5000);click(175,140);run(2500)
                office=frame('office');click(51,26);run(2500);bank=frame('bank')
                click(173,187);run(2500);returned=frame('returned')
                trace=dos.trace('office-trace.json',count=64,timeout_ms=5000,fast_forward=True)
                project.debug_export(trace['artifact'],target/'office-trace.json')
                results[label]={'office':office,'bank':bank,'returned':returned,'trace_complete':trace['metadata'].get('complete') is True}
        if inventory(game)!=copied:raise RuntimeError('Private game files changed')
        with Project(target/'private.fdb') as project:
            for name in ('office','bank','returned'):
                frame=results[label][name];path=target/(name+'-reopened.png')
                project.debug_export(frame['artifact'],path)
                if hashlib.sha256(path.read_bytes()).hexdigest()!=frame['sha256']:
                    raise RuntimeError('Stored screenshot changed after reopen')
    if inventory(original)!=source_inventory or inventory(emitted)!=emitted_inventory:raise RuntimeError('An input directory changed')
    comparisons={k:results['original'][k]['selector_hex']==results['emitted'][k]['selector_hex'] for k in ('office','bank','returned')}
    points=[(x,y) for y in (15,38,64,87,112,143) for x in (12,48,85,118,158,198,238,283)]
    def pixels(label,name):
        with Image.open(output/label/(name+'.png')) as image:
            if image.size!=(320,200):raise ValueError('Unexpected DinoPark frame dimensions')
            rgb=image.convert('RGB');return [rgb.getpixel(p) for p in points]
    visuals={name:sum(a==b for a,b in zip(pixels('original',name),pixels('emitted',name)))
             for name in ('office','bank','returned')}
    distinct=sum(a!=b for a,b in zip(pixels('original','office'),pixels('original','bank')))
    return_matches=sum(a==b for a,b in zip(pixels('original','office'),pixels('original','returned')))
    receipt={'format':'fdisbull-udc-native-dinopark-1','source_exe_sha256':selected['DINOPARK.EXE'],
             'backend_sha256':hashlib.sha256(backend.read_bytes()).hexdigest(),'input_files':len(selected),
             'scope':'Independent fresh NEW GAME office-bank-return; observed selector and stored frames only',
             'selector_equal':comparisons,'visual_samples':{'count':len(points),'same_scene_matches':visuals,'office_vs_bank_differing':distinct,'office_vs_return_matches':return_matches},'frames':{k:{n:v[n] for n in ('office','bank','returned')} for k,v in results.items()},
             'trace_complete':{k:v['trace_complete'] for k,v in results.items()},'inputs_unchanged':True,'stored_screenshot_reopen':True,
             'elapsed_seconds':round(time.monotonic()-started,3)}
    (output/'verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if (not all(comparisons.values()) or not all(receipt['trace_complete'].values())
        or any(value<47 for value in visuals.values()) or distinct<5 or return_matches<40):
        raise RuntimeError('Bounded comparison incomplete')
    return receipt


def compile_and_verify(game,source,backend,output):
    from fdisbull.udc import capture_dos_definition, compile_dos
    source=Path(source).resolve(strict=True);output=Path(output).resolve()
    if output.exists() or output==source or output in source.parents or source in output.parents:
        raise ValueError('Output must be a new directory separate from source')
    output.mkdir(parents=True)
    if game=='zork':
        executable='_ZORK1.COM';image='com';files=['DATA/ZORK1.DAT','SETUP.INF']
    else:
        executable='DINOPARK.EXE';image=None
        files=[p.relative_to(source).as_posix() for p in sorted(source.rglob('*')) if p.is_file()
               and p.relative_to(source).as_posix()!=executable and not p.name.upper().startswith('DINOSG.')]
    before=inventory(source)
    with Project.create(output/'definition.fdb',source/executable,**({'image':image} if image else {'load_segment':0x1000})) as project:
        resources={}
        for index,name in enumerate(files):
            ident='resource-'+str(index);project.attach_file(source/name,name=ident,kind='resource');resources[name]=ident
        definition=capture_dos_definition(project,'native-rebuild',resources=resources,version=1)
        built=compile_dos(project,definition['id'],output/'emitted')
        (output/'compile-receipt.json').write_text(json.dumps({'definition':definition,'build':built},indent=2)+'\n')
    if inventory(source)!=before:raise RuntimeError('Original source files changed during capture')
    result=(verify_zork if game=='zork' else verify_dinopark)(source,output/'emitted',backend,output/'comparison')
    return {'definition':definition['id'],'compiler':built,'native':result}


def verify_synthetic(backend,output,*,llvm=None):
    from fdisbull.udc import capture_dos_definition,compile_dos,shared_programs,UDCQualificationError
    from fdisbull.udl_blocks import lift_asm_block,lift_c_block,asm_to_c,verify_block
    from fdisbull.interaction_il import execute_il
    from fdisbull.debug_state import apply_edits,register_value
    output=Path(output).resolve();backend=Path(backend).resolve(strict=True)
    if llvm is None:
        configured=os.environ.get('FDISBULL_LLVM_DIR')
        mc=shutil.which('llvm-mc') if not configured else None
        llvm=Path(configured) if configured else Path(mc).parent if mc else Path('/opt/homebrew/opt/llvm/bin')
    llvm=Path(llvm).resolve(strict=True)
    if output.exists() or any((p/'.git').exists() for p in (output,*output.parents)):
        raise ValueError('Synthetic output must be new and outside Git')
    output.mkdir(parents=True);source=Path(__file__).with_name('synthetic_game.asm').resolve()
    obj=output/'game.o';original=output/'GAME.COM'
    def command(args):return subprocess.check_output([str(llvm/args[0]),*map(str,args[1:])],text=True)
    command(['llvm-mc','-triple=i386','-filetype=obj',source,'-o',obj])
    reloc=command(['llvm-readobj','--relocations',obj])
    if 'Relocations [\n]' not in reloc:raise ValueError('Synthetic source has unresolved relocations')
    command(['llvm-objcopy','-O','binary','--only-section=.text',obj,original])
    symbols={}
    for line in command(['llvm-nm','-n',obj]).splitlines():
        parts=line.split()
        if len(parts)==3:symbols[parts[2]]=int(parts[0],16)
    begin=symbols['effect_begin'];end=symbols['effect_end'];written=symbols['result_written']
    raw=original.read_bytes();block=raw[begin:end]
    if block!=bytes.fromhex('05c80048'):raise ValueError('Unexpected assembled semantic source')
    lift=lift_asm_block(block,{'ax':'$score'},inputs=['ax'],outputs=['ax'])
    with Project.create(output/'definition.fdb',original,image='com') as project:
        definition=capture_dos_definition(project,'authored-game',semantic_blocks=[{'id':'score','offset':begin,'lift':lift}])
        programs=shared_programs(project,definition['id'],role='uil')
        proof=verify_block(lift,programs['score'])
        if proof['status']!='equivalent_under_assumptions':raise RuntimeError('Authentic UIL did not qualify')
        wrong=copy.deepcopy(programs);wrong['score']['body'][0]['value']+=1
        counterexample=verify_block(lift,wrong['score'])
        if counterexample['status']!='counterexample':raise RuntimeError('Incorrect block did not produce a counterexample')
        try:compile_dos(project,definition['id'],output/'refused',programs=wrong)
        except UDCQualificationError as error:
            if error.verification['status']!='counterexample':raise
        else:raise RuntimeError('Incorrect block was accepted')
        if (output/'refused').exists():raise RuntimeError('Refused compilation created output')
        compiled=compile_dos(project,definition['id'],output/'compiled',programs=programs)
        c_view=asm_to_c(lift)
        c_lift=lift_c_block(c_view['text'],lift['bindings'],inputs=lift['inputs'],outputs=lift['outputs'])
        c_proof=verify_block(lift,c_lift['uil'])
        if c_proof['status']!='equivalent_under_assumptions':raise RuntimeError('C-lifted UIL did not qualify')
        c_compiled=compile_dos(project,definition['id'],output/'compiled-c',programs={'score':c_lift['uil']})
    result={};helper=zork_helpers()
    for label,path in (('original',original),('emitted',output/'compiled'/'GAME.COM'),('c_emitted',output/'compiled-c'/'GAME.COM')):
        target=output/label;target.mkdir()
        game=target/'GAME.COM';shutil.copyfile(path,game)
        with Project.create(target/'private.fdb',game,image='com') as project:
            project.analyze(start='1000:0100',max_instructions=100)
            with project.debugger(backend,target) as dos:
                entry=dos.breakpoint(f'1000:{0x100+begin:04x}')
                run=dos.run(guest_ms=250,timeout_ms=5000,fast_forward=True,stop_on_hook=True)
                if run['outcome']!='guest_time':raise RuntimeError('Guest did not await input')
                dos.keyboard_press('a')
                run=dos.run(guest_ms=1000,timeout_ms=5000,fast_forward=True,stop_on_hook=True)
                if run['outcome']!='breakpoint':raise RuntimeError('Effect entry not reached')
                before=helper.scalar(dos.registers(),'eax');dos.delete_breakpoint(entry['breakpoint_id'])
                trace=dos.trace('score.trace.json',count=2,timeout_ms=5000,fast_forward=True)
                project.debug_export(trace['artifact'],target/'score.trace.json')
                if trace['metadata'].get('complete') is not True:raise RuntimeError('Effect trace incomplete')
                events=json.loads((target/'score.trace.json').read_text())['events']
                addresses=[event.get('project_segmented_address','').lower() for event in events]
                if addresses!=[f'1000:{0x100+begin:04x}',f'1000:{0x100+end-1:04x}']:
                    raise RuntimeError('Trace does not cover the declared source block')
                exit_break=dos.breakpoint(f'1000:{0x100+written:04x}')
                run=dos.run(guest_ms=1000,timeout_ms=5000,fast_forward=True,stop_on_hook=True)
                if run['outcome']!='breakpoint':raise RuntimeError('Result write not reached')
                after=helper.scalar(dos.registers(),'eax')
                stored=int.from_bytes(helper.read(dos,int(dos.registers()['segments']['ds'],16)*16+0x180,2),'little')
                dos.delete_breakpoint(exit_break['breakpoint_id'])
                run=dos.run(guest_ms=250,timeout_ms=5000,fast_forward=True,stop_on_hook=True)
                if run['outcome']!='guest_time':raise RuntimeError('Completion did not settle')
                screen=helper.screen(dos)
                if 'Score committed.' not in screen['text']:raise RuntimeError('Guest completion text missing')
                shot=dos.screenshot('score.png');project.debug_export(shot['artifact'],target/'score.png')
                checkpoint=dos.save_state('post-completion.sav')
                samples=[]
                for value in (0,1,65336,65337,65535):
                    dos.load_state(checkpoint['artifact'])
                    regs=dos.registers()
                    if regs.get('cpu_mode')!='real':raise RuntimeError('Boundary probe requires real mode')
                    if int(regs['segments']['cs'],16)*16 != 0x10000+dos.delta:
                        raise RuntimeError('Boundary probe code segment changed')
                    code=dos.code(f'1000:{0x100+begin:04x}',length=len(block),view='ram')
                    if code.get('hex')!=block.hex():raise RuntimeError('Boundary probe source bytes changed')
                    expected=register_value(regs,'eax')
                    edit=apply_edits(dos,[],{'eax':{'expected':expected,'value':value},
                                             'eip':{'expected':register_value(regs,'eip'),'value':0x100+begin}})
                    exit_break=dos.breakpoint(f'1000:{0x100+written:04x}')
                    stop=dos.run(guest_ms=1000,timeout_ms=5000,fast_forward=True,stop_on_hook=True)
                    if stop['outcome']!='breakpoint':raise RuntimeError('Boundary probe did not reach exit')
                    actual=helper.scalar(dos.registers(),'eax')
                    native_memory=int.from_bytes(helper.read(dos,int(dos.registers()['segments']['ds'],16)*16+0x180,2),'little')
                    expected_result=(value+199)&0xffff
                    model=execute_il(programs['score'],{'$score':value})
                    if not model.get('complete') or model['state']['$score']!=expected_result or actual!=expected_result or native_memory!=expected_result:
                        raise RuntimeError('Boundary native and source model disagree')
                    dos.delete_breakpoint(exit_break['breakpoint_id'])
                    samples.append({'input_ax':value,'output_ax':actual,'stored_u16':native_memory,
                                    'model_u16':model['state']['$score'],'cpu_mode':'real',
                                    'source_hex':code['hex'],'register_edits_verified':all(item['verified'] for item in edit['registers'])})
                result[label]={'input_ax':before,'output_ax':after,'stored_u16':stored,'guest_completion':True,
                               'trace_complete':True,'screenshot_sha256':shot['sha256'],
                               'assisted_boundary_samples':samples}
        with Project(target/'private.fdb') as project:
            project.debug_export(shot['artifact'],target/'score-reopened.png')
            if hashlib.sha256((target/'score-reopened.png').read_bytes()).hexdigest()!=shot['sha256']:
                raise RuntimeError('Stored screenshot changed after reopen')
        if (before,after,stored)!=(10,209,209):raise RuntimeError('Synthetic native state differs from expected: '+str((before,after,stored)))
    receipt={'format':'fdisbull-udc-native-synthetic-1','source_asm_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
             'assembled_com_sha256':hashlib.sha256(raw).hexdigest(),'block_hex':block.hex(),'block_offset':begin,
             'definition_sha256':definition['sha256'],'qualification':compiled['qualification'],
             'wrong_candidate':'counterexample','wrong_output_created':False,
             'c_view':{'sha256':hashlib.sha256(c_view['text'].encode()).hexdigest(),'source_sha256':c_view['source_sha256'],
                       'proof_status':c_proof['status'],'qualification':c_compiled['qualification']['status'],
                       'scope':'ASM-derived C view shares decoder; no independent native or C-code generation claim'},
             'native':result,
             'stored_screenshot_reopen':True,'generated_dos_lowering':False,
             'boundary_sample_scope':'Assisted paused AX and instruction-pointer edits from a post-completion checkpoint; not ordinary gameplay.',
             'scope':'Authored 16-bit COM; pure AX block and native keypress, memory, text, trace and screenshot; original native bytes retained.'}
    (output/'verification.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',choices=('zork','dinopark','synthetic'),required=True)
    parser.add_argument('--source');parser.add_argument('--backend',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if args.game=='synthetic':result=verify_synthetic(args.backend,args.output)
    else:
        if not args.source:parser.error('--source required for original game')
        result=compile_and_verify(args.game,args.source,args.backend,args.output)
    print(json.dumps(result,indent=2))
