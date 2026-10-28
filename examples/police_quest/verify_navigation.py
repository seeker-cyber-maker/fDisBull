"""Private Police Quest navigation probe. Supply your own game and backend.

Writes a fresh private copy, database, and evidence under --work-dir. Nothing in
this example distributes game data. Run only against the identified AGI build.
"""
import argparse, base64, hashlib, json, shutil
from pathlib import Path
from fdisbull.project import Project

SOURCE='29ddd3f3b91d65b6eade156608d7915e3c8b7f47701cb226ff119b717f3e8bd7'
POINTS=[[20,30],[30,35],[45,42],[75,35],[120,32],[200,32],[255,42],[280,38],[300,30],[290,60]]
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def manifest(p): return {str(f.relative_to(p)):digest(f) for f in sorted(p.rglob('*')) if f.is_file()}
def main():
    a=argparse.ArgumentParser(); a.add_argument('--game-dir',type=Path,required=True); a.add_argument('--backend',type=Path,required=True); a.add_argument('--work-dir',type=Path,required=True); a.add_argument('--output',type=Path,required=True); args=a.parse_args()
    source=args.game_dir.resolve(); root=args.work_dir.resolve(); output=args.output.resolve()
    if root.exists(): raise ValueError('work directory already exists')
    if root==source or source in root.parents or root in source.parents: raise ValueError('work and source directories must be separate')
    before=manifest(source)
    if digest(source/'AGI')!=SOURCE: raise ValueError('unexpected AGI.EXE hash')
    root.mkdir(parents=True); game=root/'game'; shutil.copytree(source,game)
    if manifest(game)!=before: raise ValueError('copy mismatch')
    shutil.copyfile(game/'AGI',game/'AGI.EXE')
    evidence={'source_sha256':SOURCE,'source_manifest_before':before,'copy_manifest_before':manifest(game),'backend_sha256':digest(args.backend),'steps':{},'claim_ceiling':'One fresh PQ1 build and backend; baseline-point observations only. No collision cause or complete control map inferred.'}
    def save():
        output.parent.mkdir(parents=True,exist_ok=True); output.write_text(json.dumps(evidence,indent=2,default=str)+'\n')
    save()
    try:
      with Project.create(root/'private.fdb',game/'AGI.EXE') as p:
       p.analyze(start='1000:7c06',max_instructions=1)
       with p.debugger(args.backend,game,version=1,boot_timeout_ms=30000) as d:
        def frame(name):
            f=d.screenshot(name,hooks=False); p.debug_export(f['artifact'],root/name); return f
        evidence['steps']['boot']=d.run(guest_ms=5000,timeout_ms=15000,fast_forward=False)
        evidence['steps']['title']=frame('title.png')
        d.keyboard_press('enter',hold_ms=60,gap_ms=50)
        evidence['steps']['enter']=d.run(guest_ms=5000,timeout_ms=15000,fast_forward=False)
        hall=frame('hallway.png'); evidence['steps']['hallway']=hall
        pixels=d.frame_probe(POINTS)['samples']
        def resolve():
            bp=d.breakpoint('1000:7c06'); result=d.run(timeout_ms=10000)
            if result.get('outcome')!='breakpoint' or not bp.get('bytes_verified'): raise RuntimeError('writer execution breakpoint failed')
            regs=d.registers(); ds=int(regs['segments']['ds'],16); di=int(regs['general']['edi'],16); addr=ds*16+di
            data=base64.b64decode(d.call('memory.read',{'address':{'space':'linear','offset':f'0x{addr:08X}'},'length':64})['data_base64'])
            b=d.bind_runtime_memory('ego',addr,length=64,expected_hex=data[:3].hex(),provenance={'source_sha256':SOURCE,'writer':'1000:7c06','method':'DS:DI at byte-verified writer execution breakpoint','DS':hex(ds),'DI':hex(di)})
            d.delete_breakpoint(bp['breakpoint_id']); return {'breakpoint':bp,'run':result,'registers':regs,'binding':b}
        evidence['steps']['resolution']=resolve(); save()
        pixel={'pixels':{'samples':pixels,'min_matches':len(pixels),'tolerance':0}}
        neutral={'runtime_memory':{'binding':'ego','offset':33,'length':1,'hex':'00'}}
        nav={'space':'agi-baseline','width':160,'height':200,'actor':{'width':1,'height':1,'anchor':[0,0]},'walkable':{'rect':[34,120,119,121]},'colliders':[], 'anchors':[],'portals':[], 'provenance':{'extraction_rule':'bounded prior observed baseline point trajectory, not actor footprint','source_facts':['PQ1 2.917 X=34..118 at Y=120; prior no-progress samples'], 'evidence_status':'observed bounded'}}
        doc={'format':'fdisbull-scene-1','width':320,'height':200,'mode_id':hall['metadata']['mode_id'],'reference':hall['artifact'],'context':{'state':'fresh station hallway','triggers':['Enter from title','ten sampled pixels']},'match':pixel,'content':{'requested':{'constant':True},'displayed':pixel,'ready':neutral},'navigation':nav,'objects':[{'name':'hallway','area':{'rect':[0,0,320,200]},'point':[1,1],'context':{'state':'sampled hallway displayed','triggers':['ten sampled pixels']},'visible':pixel,'ready':neutral,'enabled':{'constant':True},'action':{'kind':'press','key':'enter','hold_ms':60,'gap_ms':50},'outcome':{'constant':True},'outcome_phase':'state'}]}
        scene=p.debug_save_scene('pq1.hallway',doc,version=1,author='verification'); evidence['steps']['scene']=d.scene_check('pq1.hallway',compact=True)
        overlay=p.debug_scene_overlay(scene['id'],labels='numbers',grid_step=8,version=1); p.debug_export(overlay['artifact'],root/'overlay.png'); evidence['steps']['overlay']=overlay
        evidence['steps']['geometry_checks']={str(pt):d.scene_navigation('pq1.hallway',pt) for pt in ([60,120],[33,120])}
        macros={'format':'fdisbull-macro-set-1','name':'pq1-latched','provenance':{'source_sha256':SOURCE,'note':'Prior observed cardinal toggle behavior'},'macros':{}}
        for key in ('left','right'):
            for action in ('start','stop'):
                macros['macros'][key+'_'+action]={'parameters':{},'authority':'player-input','steps':[{'op':'keyboard.press','key':key,'hold_ms':60,'gap_ms':50}]}
        ms=p.debug_define_macros(macros,version=1,author='verification')
        obs={name:{'runtime_memory':{'binding':'ego','offset':off,'type':typ}} for name,off,typ in [('x',3,'u16'),('y',5,'u16'),('direction',33,'u8')]}
        def move(key,lo,hi):
            return dict(macro_set=ms['id'],start={'name':key+'_start'},stop={'name':key+'_stop'},observations=obs,until={'field':'x','op':'in_range','value':[lo,hi]},progress={'fields':['x'],'samples':8},settle={'field':'direction','op':'eq','value':0},slice_ms=50,guest_ms=10000,timeout_ms=20000,cleanup_guest_ms=500)
        checkpoint=d.save_state('fresh.sav'); evidence['steps']['checkpoint']=checkpoint
        for key,lo,hi in [('left',45,48),('right',60,63)]:
            result=d.move(**move(key,lo,hi)); evidence['steps']['move_'+key]=result; save()
            if not result['ok']: raise RuntimeError('movement failed: '+key)
        script={'format':'fdisbull-script-1','steps':[{'op':'move',**move('left',45,48)}]}
        saved=p.debug_save_script('pq1-left',script,version=1); evidence['steps']['script_saved']=saved
        evidence['steps']['script_execution']=d.script(script_id=saved['script_id'],timeout_ms=30000); save()
        if not evidence['steps']['script_execution']['ok']: raise RuntimeError('saved script failed')
        blocked=d.move(**move('left',10,10)); evidence['steps']['blocked']=blocked
        if blocked['outcome']!='blocked' or not blocked['cleanup']['settled']: raise RuntimeError('blocked trial did not settle')
        if blocked.get('diagnostic_frame'): p.debug_export(blocked['diagnostic_frame'],root/'blocked-diagnostic.png')
        evidence['steps']['restore']=d.load_state(checkpoint['artifact'])
        try: d.runtime_memory('ego',offset=3,length=2); evidence['steps']['old_binding_invalidated']=False
        except ValueError: evidence['steps']['old_binding_invalidated']=True
        evidence['steps']['reresolution']=resolve()
        for key,lo,hi in [('left',45,48),('right',60,63)]:
            evidence['steps']['restored_'+key]=d.move(**move(key,lo,hi)); save()
            if not evidence['steps']['restored_'+key]['ok']: raise RuntimeError('restored route failed: '+key)
        evidence['steps']['final']=frame('final.png')
        try:
            trace=d.trace('bounded-trace.json',count=32,timeout_ms=10000); p.debug_export(trace['artifact'],root/'bounded-trace.json'); evidence['steps']['trace']=trace
        except Exception as error: evidence['steps']['trace_error']=str(error)
    finally:
        evidence['source_manifest_after']=manifest(source); evidence['copy_manifest_after']=manifest(game); save()
if __name__=='__main__': main()
