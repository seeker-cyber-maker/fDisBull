"""Private PQ1/KQ1 transfer trial. Supply licensed game files and native backend.

This is a bounded, observed AGI control adapter, not an AGI implementation. The
player consumes the same projection protocol for both games. All game copies,
native states, databases and unfiltered results stay in --work-dir.
"""
import argparse
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import time

from PIL import Image

from fdisbull.project import Project
from fdisbull.progressive_scenes import resource_inventory
from fdisbull.scene_bundles import identity
from fdisbull.runtime_observations import capture_observations
from fdisbull.movement import matches
from fdisbull_player import Player

# Observed engine get.pos tail, checked again before the runtime breakpoint.
WRITER = bytes.fromhex('888709008bc65d5f5ec35657558bec83ec028b76088bde468a072ae42ef72e17')
RECIPES = {
    'kq1': {'binary':'KQ1.COM', 'image':'com', 'agi_sha256':'5ab189ebd9822739962767afe0113853e23797ef16dd4784d2dc93423934fb74',
            'keys':['escape','enter'], 'within':[130,100], 'key':'right', 'portal':[154,100], 'room':8, 'landing_x':[0,4], 'landing_y':100},
    'pq1': {'binary':'AGI', 'image':'mz', 'agi_sha256':'29ddd3f3b91d65b6eade156608d7915e3c8b7f47701cb226ff119b717f3e8bd7',
            'keys':['enter'], 'within':[80,120], 'key':'right', 'portal':[143,150], 'room':5, 'landing_x':[20,24], 'landing_y':130,
            'approach':{'key':'down','field':'y','value':[149,151]}},
}


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def manifest(root): return {p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
def conjunction(*items): return {'all':list(items)}
def eq(field, value): return {'field':field, 'op':'eq', 'value':value}
def landing_predicate(recipe):
    return conjunction(eq('room',recipe['room']),
                       {'field':'x','op':'in_range','value':recipe['landing_x']},
                       eq('y',recipe['landing_y']))
def neutral_predicate(): return conjunction(eq('direction',0),eq('control_direction',0))


def destination_pixels(baseline, destination):
    """Choose spatially distributed, actually differing interior pixels."""
    with Image.open(baseline) as first, Image.open(destination) as second:
        a, b = first.convert('RGB'), second.convert('RGB')
        if a.size != (320, 200) or b.size != a.size:
            raise ValueError('Expected matching 320x200 frames')
        if a.tobytes() == b.tobytes():
            raise ValueError('Destination frame is identical to baseline')
        # Eight horizontal bands select at most one point each, distributed
        # across the image; neither known animated flag point is sampled.
        selected = []
        for y in range(35, 196, 20):
            candidates = [(x, y) for x in range(10, 311, 10)
                          if (x, y) not in {(20,25), (90,25)} and a.getpixel((x, y)) != b.getpixel((x, y))]
            if candidates:
                selected.append(list(candidates[len(candidates) // 2]))
        if not selected:
            raise ValueError('No distinct destination pixels found on the interior grid')
        return selected


def run(args):
    recipe=RECIPES[args.game]; source=args.game_dir.resolve(); root=args.work_dir.resolve()
    if root.exists() or root==source or source in root.parents or root in source.parents:
        raise ValueError('Use a new work directory separate from the source')
    if sha(source/'AGI') != recipe['agi_sha256']: raise ValueError('This exact edition has not been qualified')
    original=manifest(source); root.mkdir(parents=True); game=root/'game'; shutil.copytree(source,game)
    report={'format':'fdisbull-progressive-trial-1','game':args.game,'source_manifest':original,
            'backend_sha256':sha(args.backend), 'claim':'Observed live-original slice; assisted travel changes traversal. No full AGI or game reconstruction.', 'steps':{}, 'trials':[]}
    def save(): (root/'result.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
    def require(condition, message):
        save()
        if not condition: raise RuntimeError(message)
    with Project.create(root/'private.fdb',game/recipe['binary'],image=recipe['image']) as p:
      with p.debugger(args.backend,game,version=1) as d:
        report['steps']['boot']=d.run(guest_ms=5000,timeout_ms=15000,fast_forward=True)
        for key in recipe['keys']:
            d.keyboard_press(key,hold_ms=60,gap_ms=50)
            report['steps']['boot_'+key]=d.run(guest_ms=5000,timeout_ms=15000,fast_forward=True)
        def read(address,length):
            return base64.b64decode(d.call('memory.read',{'address':{'space':'linear','offset':f'0x{address:08X}'},'length':length})['data_base64'])
        def resolve():
            # A source-qualified code fingerprint locates the decrypted KQ engine;
            # no static address translation from its COM launcher is asserted.
            hits=[]; tail=b''
            for start in range(0,0xa0000,65536):
                data=tail+read(start,65536); offset=0
                while (offset:=data.find(WRITER,offset))>=0:
                    hits.append(start-len(tail)+offset); offset+=1
                tail=data[-(len(WRITER)-1):]
            report['steps']['writer_candidates']=[hex(x) for x in hits]
            require(len(hits)==1,'Writer fingerprint is not unique')
            linear=hits[0]
            bp=d.call('breakpoints.create',{'kind':'execution','once':False,'address':{'space':'segmented','segment':f'0x{linear>>4:04X}','offset':f'0x{linear&15:08X}'}})
            stop=d.run(guest_ms=5000,timeout_ms=10000,fast_forward=True); regs=d.registers()
            require(stop['outcome']=='breakpoint','Observed writer breakpoint did not fire')
            require(int(regs['segments']['cs'],16)*16+int(regs['instruction_pointer'],16)==linear,'Writer stop disagrees with fingerprint')
            require(int(regs['general']['ecx'],16)==0,'get.pos selected a different object')
            ds=int(regs['segments']['ds'],16)*16; actor=ds+int(regs['general']['edi'],16)
            require(int.from_bytes(read(ds+0x963,2),'little')+ds==actor,'Actor pointer differs from observed get.pos base')
            witness=read(linear+0x2a,5)
            report['steps']['refresh_instruction']={'linear':hex(linear+0x2a),'bytes':witness.hex(),
                'scope':'reposition neighbor of observed get.pos; PQ refresh additionally observed in a private native probe'}
            require(witness==bytes.fromhex('814d250004'),'Expected reposition refresh instruction not present')
            defs=[{'name':'actor','address':actor,'length':64,'expected_hex':read(actor,3).hex(),
                   'provenance':{'method':'DS:DI at observed get.pos object zero','writer_sha256':hashlib.sha256(WRITER).hexdigest(),'source_agi_sha256':recipe['agi_sha256']}},
                  {'name':'variables','address':ds,'length':265,'expected_hex':read(ds,9).hex(),
                   'provenance':{'method':'decoded get.pos [bx+9] variable destination; candidate v0/v1 corroborated by the later native transition record',
                                 'control_direction':'AGI v6 semantics from ScummVM; DS+9+6 is inferred from this observed variable-array base and requires native corroboration'}}]
            bindings=[d.bind_runtime_memory(**item) for item in defs]
            d.call('breakpoints.delete',{'breakpoint_id':bp['breakpoint_id']})
            d.run(guest_ms=250,timeout_ms=5000,fast_forward=True)
            return {'writer_linear':hex(linear),'writer_hex':WRITER.hex(),'stop':stop,'registers':regs,'bindings':bindings,'definitions':defs}
        report['steps']['resolution']=resolve(); definitions=report['steps']['resolution']['definitions']
        observations={'x':{'runtime_memory':{'binding':'actor','offset':3,'type':'u16'}},
                      'y':{'runtime_memory':{'binding':'actor','offset':5,'type':'u16'}},
                      'direction':{'runtime_memory':{'binding':'actor','offset':33,'type':'u8'}},
                      'control_direction':{'runtime_memory':{'binding':'variables','offset':15,'type':'u8'}},
                      'room':{'runtime_memory':{'binding':'variables','offset':9,'type':'u8'}}}
        before=capture_observations(d,observations);require(before['complete'],'Initial actor captures absent')
        report['steps']['initial']=before; room=before['values']['room']; initial=d.save_state('baseline.sav'); report['steps']['baseline']=initial
        def restore():
            d.load_state(initial['artifact'])
            for item in definitions:d.bind_runtime_memory(**item)
            prepared=d.run(guest_ms=100,timeout_ms=5000,fast_forward=True,stop_on_hook=True)
            require(prepared['outcome']=='guest_time' and not prepared.get('hook_hits'),'Restore preparation stopped unexpectedly')
        def frame(name):
            result=d.screenshot(name,hooks=False);p.debug_export(result['artifact'],root/name);return result
        def wait_frames(label):
            frame_ids=[d.frame_probe([])['frame_id']]; frame_runs=[]; elapsed=0
            deadline=time.monotonic()+10
            report['steps'][label]={'frame_ids':frame_ids,'runs':frame_runs}
            while len(frame_ids)<3:
                remaining=int((deadline-time.monotonic())*1000)
                require(remaining>0 and elapsed<2000,'Frame wait exhausted its budget')
                waited=d.run(guest_ms=min(50,2000-elapsed), timeout_ms=remaining,
                             fast_forward=True,stop_on_hook=True)
                frame_runs.append(waited)
                require(waited.get('outcome')=='guest_time' and not waited.get('hook_hits'),
                        'Frame wait stopped unexpectedly')
                progress=waited.get('guest_elapsed_ms')
                require(type(progress) is int and progress>0,'Frame wait lacks guest progress')
                elapsed+=progress
                require(elapsed<=2000 and time.monotonic()<deadline,'Frame wait exceeded its budget')
                frame_id=d.frame_probe([])['frame_id']
                require(type(frame_id) is int and frame_id>=frame_ids[-1],'Frame identity regressed')
                if frame_id>frame_ids[-1]: frame_ids.append(frame_id)
            return frame_ids[-1]
        reference=frame('baseline.png')
        neutral={'all':[{'runtime_memory':{'binding':'actor','offset':33,'length':1,'hex':'00'}},
                        {'runtime_memory':{'binding':'variables','offset':15,'length':1,'hex':'00'}}]}
        def scene(name,number,reference,extra_pixels=()):
            recognition={'runtime_memory':{'binding':'variables','offset':9,'length':1,'hex':bytes([number]).hex()}}
            # Publicly observed pixels, including the menu bar, distinguish a
            # displayed context from a requested room while a menu blocks play.
            samples=d.frame_probe([[2,0],[12,0],[36,0],[64,0],[90,0],[105,0],[2,10],[50,10],
                                   [180,25],[280,25],[10,60],[100,60],[280,60],[300,110]] + list(extra_pixels))['samples']
            displayed={'pixels':{'samples':samples,'min_matches':len(samples),'tolerance':0}}
            yes={'constant':True}
            doc={'format':'fdisbull-scene-1','width':320,'height':200,'mode_id':reference['metadata']['mode_id'],'reference':reference['artifact'],
                 'context':{'state':name,'triggers':['observed original room transition; source-qualified runtime binding']},
                 'match':{'all':[recognition,displayed]},'content':{'requested':recognition,'displayed':displayed,'ready':neutral},
                 'objects':[{'name':'east','area':{'rect':[1,1,2,2]},'point':[1,1],
                 'context':{'state':'qualified east control','triggers':['room identity and neutral direction']},
                 'visible':yes,'ready':neutral,'enabled':yes,'action':{'kind':'press','key':recipe['key'],'hold_ms':60,'gap_ms':50},
                 'outcome':{'runtime_memory':{'binding':'actor','offset':33,'length':1,'hex':'03'}},'outcome_phase':'state'}]}
            return p.debug_save_scene(name,doc,version=1,author='bounded native verification')
        origin=scene(args.game+'.origin',room,reference)
        macros={'format':'fdisbull-macro-set-1','name':args.game+'-latched','provenance':{'scope':'observed cardinal toggle, this edition'},'macros':{}}
        for suffix in ('start','stop'):
            macros['macros'][suffix]={'parameters':{},'authority':'player-input','steps':[{'op':'keyboard.press','key':recipe['key'],'hold_ms':60,'gap_ms':50}]}
            if 'approach' in recipe:
                macros['macros']['approach_'+suffix]={'parameters':{},'authority':'player-input','steps':[{'op':'keyboard.press','key':recipe['approach']['key'],'hold_ms':60,'gap_ms':50}]}
        macro=p.debug_define_macros(macros,version=1)
        tx,ty=recipe['within']
        def movement(until,context):
            return {'macro_set':macro['id'],'start':{'name':'start'},'stop':{'name':'stop'},'observations':observations,'until':until,
                    'progress':{'fields':['x','y','room'],'samples':15},'settle':neutral_predicate(),'guest_ms':10000,'timeout_ms':20000,
                    'slice_ms':50,'cleanup_guest_ms':1000,'context':context}
        goal=conjunction({'field':'x','op':'in_range','value':[tx-1,tx+1]},eq('y',ty),eq('room',room))
        walk=movement(goal,eq('room',room))
        def travel(kind,point,number,until):
            return {'format':'fdisbull-assisted-travel-1','kind':kind,'scene_revision':origin['id'],
                    'observations':observations,'context':conjunction(eq('room',room),neutral_predicate()),
                    'writes':[{'binding':'actor','offset':off,'type':'u16','value':v} for off,v in ((3,point[0]),(5,point[1]))]
                             + [{'binding':'actor','offset':37,'type':'u16','set_bits':0x400}],
                    'inputs':[] if kind=='within-room' else [{'key':recipe['key'],'hold_ms':60,'gap_ms':50}],
                    'until':conjunction(until,neutral_predicate()), 'destination':{'label':kind+' east','room_field':'room','room_value':number},
                    'provenance':{'scope':'same native starting checkpoint; exact edition; original engine retained','source_agi_sha256':recipe['agi_sha256'],
                                  'refresh':'witnessed get.pos reposition-neighbor OR; PQ private native probe observed redraw, no full renderer proof'},
                    'guest_ms':5000,'slice_ms':50}
        teleport=travel('within-room',[tx,ty],room,goal)
        actions=[{'name':'walk.east','kind':'movement','scene_revision':origin['id'],'object_id':None,'dependencies':[],'evidence':[reference['artifact']]},
                 {'name':'teleport.east','kind':'assisted-travel','scene_revision':origin['id'],'object_id':None,'dependencies':[],'evidence':[reference['artifact']]}]
        workflow={'format':'fdisbull-progressive-workflow-1','source':identity(p,1),
                  'inventory':resource_inventory(game,engine='Sierra AGI',profile=args.game+':'+recipe['agi_sha256'],adapter='observed-get-pos-1'),
                  'research':[{'context':'unrecovered rooms','question':'Remaining game semantics','status':'unknown','evidence':['not analyzed by this slice']}], 'actions':actions}
        saved=p.debug_save_workflow('progressive',workflow,resource_root=game,version=1)
        public={'format':'fdisbull-text-projection-1','workflow_revision':saved['id'],'contexts':[{
                'id':'origin','title':'Observed '+args.game+' room','description':'A qualified eastward route is available. Other interactions remain outside this slice.',
                'scene_revision':origin['id'],'partial':True,'objects':[{'id':'marker','label':'east marker','aliases':['marker'],'description':'An observed destination in this room.',
                'scene_object':origin['definition']['objects'][0]['id'],'inventory':False,'bindings':[
                    {'verb':'walk','item':None,'action':'walk.east','dispatch':{'kind':'movement','args':walk}},
                    {'verb':'teleport','item':None,'action':'teleport.east','dispatch':{'kind':'assisted-travel','plan':teleport,'timeout_ms':10000}}]}]}]}
        projection=p.debug_save_text_projection('play',public,version=1)
        report['steps']['workflow']=saved;report['steps']['projection']=projection
        report['steps']['partial_queue']=d.workflow(saved['id'],resource_root=game).observe()
        for index in range(3):
            for command in ('walk east marker','teleport east marker'):
                restore(); backend=d.text_projection(projection['id'],game); player=Player(backend)
                status=d._timing();started=time.monotonic();text=player.execute(command);wall=(time.monotonic()-started)*1000
                observed=capture_observations(d,observations);elapsed=d._timing()['guest_ticks']-status['guest_ticks']
                trial={'index':index,'command':command,'reply':text,'host_elapsed_ms':wall,'guest_elapsed_ms':elapsed,'after':observed}
                report['trials'].append(trial); require(text.startswith('Success') and observed['complete'] and tx-1<=observed['values']['x']<=tx+1 and observed['values']['y']==ty and matches(neutral_predicate(),observed['values']) and observed['values']['room']==room,'Matched trial failed: '+text)
        within_frame_id=wait_frames('within_frame_wait')
        within_after=capture_observations(d,observations);report['steps']['within_rendered']=within_after
        require(within_after['complete'] and matches(conjunction(goal,neutral_predicate()),within_after['values']),
                'Within-room position changed while waiting for completed frames')
        report['steps']['within_frame']=frame('within.png')
        require(report['steps']['within_frame']['metadata']['frame_id']==within_frame_id,'Within-room capture differs from completed frame')
        restore(); channel=d.text_projection(projection['id'],game); admitted=channel.observe()
        require(admitted.get('complete'),'Fresh baseline projection missing')
        stale_request={'verb':'teleport','target':admitted['objects'][0]['id'],'item':None,'context_token':admitted['context']['token']}
        d.keyboard_press('escape',hold_ms=60,gap_ms=50);d.run(guest_ms=500,timeout_ms=5000,fast_forward=True)
        modal_check=d.scene(origin['id']).check();report['steps']['menu_check']=modal_check
        report['steps']['menu_frame']=frame('menu-blocked.png')
        timing=d._timing(); rejected=channel.act(stale_request); after_timing=d._timing()
        report['steps']['menu_refusal']={'result':rejected,'guest_elapsed_ms':after_timing['guest_ticks']-timing['guest_ticks']}
        require(modal_check['status']!='matched' and rejected['status']!='success' and after_timing['guest_ticks']==timing['guest_ticks'],'Menu should block input without execution')
        if recipe['portal'] is not None:
            # First establish the original transition and destination context.
            arrival=landing_predicate(recipe)
            settled=conjunction(arrival,neutral_predicate())
            restore(); original_route=movement(arrival,None)
            if 'approach' in recipe:
                approach=recipe['approach']; params=movement({'field':approach['field'],'op':'in_range','value':approach['value']},eq('room',room))
                params.update(start={'name':'approach_start'},stop={'name':'approach_stop'})
                approached=d.move(**params);report['steps']['original_approach']=approached
                require(approached['ok'],'Original approach did not complete')
            baseline=d.move(**original_route); report['steps']['original_room_route']=baseline
            require(baseline['ok'],'Original room route did not complete')
            arrived=capture_observations(d,observations); report['steps']['original_landing']=arrived
            require(arrived['complete'] and matches(settled,arrived['values']),'Original landing differs from the explicit settled recipe')
            destination_frame_id=wait_frames('destination_frame_wait')
            arrived=capture_observations(d,observations); report['steps']['rendered_landing']=arrived
            require(arrived['complete'] and matches(settled,arrived['values']),'Landing changed while waiting for completed frames')
            target_frame=frame('destination.png')
            require(target_frame['metadata']['frame_id']==destination_frame_id,'Destination capture differs from completed frame')
            require(sha(root/'baseline.png') != sha(root/'destination.png'),'Destination PNG matches baseline')
            distinct=destination_pixels(root/'baseline.png',root/'destination.png')
            report['steps']['destination_distinct_pixels']=distinct
            destination=scene(args.game+'.destination',recipe['room'],target_frame,distinct)
            restore(); jump=travel('room-jump',recipe['portal'],recipe['room'],arrival)
            jump['destination_scene']=destination['id']
            jump['cleanup']={'when':conjunction(arrival,{'field':'control_direction','op':'ne','value':0}),
                             'inputs':[{'key':recipe['key'],'hold_ms':60,'gap_ms':50}]}
            jumped=d.assisted_travel(jump,timeout_ms=10000);report['steps']['room_jump']=jumped
            require(jumped['ok'],'Qualified room jump failed')
            report['steps']['jump_frame']=frame('jump.png')
            require(jumped['after']['complete'] and matches(settled,jumped['after']['values']),'Assisted exit did not reach the declared settled range')
            workflow['actions'] += [{'name':'jump.east','kind':'assisted-travel','scene_revision':origin['id'],'object_id':None,'dependencies':[],'evidence':[reference['artifact'],target_frame['artifact']]}]
            newer=p.debug_save_workflow('progressive',workflow,resource_root=game,parent=saved['id'],version=1)
            public['workflow_revision']=newer['id']
            public['contexts'][0]['objects'].append({'id':'exit','label':'east exit','aliases':['exit'],'description':'A qualified exit to the observed neighboring room.',
                'scene_object':origin['definition']['objects'][0]['id'],'inventory':False,'bindings':[{'verb':'go','item':None,'action':'jump.east','dispatch':{'kind':'assisted-travel','plan':jump,'timeout_ms':10000}}]})
            public['contexts'].append({'id':'destination','title':'Observed neighboring room','description':'The original room initialization completed; further actions are not recovered.',
                                      'scene_revision':destination['id'],'partial':True,'objects':[]})
            projection=p.debug_save_text_projection('play',public,parent=projection['id'],version=1)
            restore();final_channel=d.text_projection(projection['id'],game);player=Player(final_channel)
            prior=final_channel.observe()
            old_request={'verb':'go','target':next(o['id'] for o in prior['objects'] if o['label']=='east exit'),
                         'item':None,'context_token':prior['context']['token']}
            report['steps']['room_text_before']=player.execute('look')
            report['steps']['room_text_action']=player.execute('go east exit'); report['steps']['room_text_after']=player.execute('look')
            require(report['steps']['room_text_action'].startswith('Success'),'Text room jump failed')
            stopped_at=d._timing(); old_context=final_channel.act(old_request)
            report['steps']['stale_refusal']={'result':old_context,'guest_elapsed_ms':d._timing()['guest_ticks']-stopped_at['guest_ticks']}
            require(old_context['status']!='success' and report['steps']['stale_refusal']['guest_elapsed_ms']==0,'Prior-context command advanced guest')
        restore()
        report['steps']['final_projection']=projection
        report['host_configuration']={'format':'fdisbull-text-host-1','project':str(p.path),'backend':str(args.backend.resolve()),'game_dir':str(game),
                                      'version':1,'projection':projection['id'],'state':initial['artifact'],'bindings':definitions,'prepare_guest_ms':100,'timeout_ms':60000}
        (root/'play-private.json').write_text(json.dumps(report['host_configuration'],indent=2))
        trace=d.trace('verified-original-trace.json',count=32,timeout_ms=10000);p.debug_export(trace['artifact'],root/'verified-original-trace.json');report['steps']['trace']=trace
        report['steps']['overlay']=p.debug_scene_overlay(origin['id'],labels='numbers',grid_step=8,version=1)
        p.debug_export(report['steps']['overlay']['artifact'],root/'overlay.png')
    report['source_manifest_after']=manifest(source); report['working_manifest_after']=manifest(game)
    require(report['source_manifest_after']==original and report['working_manifest_after']==original,'Game file manifest changed')
    report['summary']={command:{'median_host_ms':statistics.median(t['host_elapsed_ms'] for t in report['trials'] if t['command']==command),
                                'median_guest_ms':statistics.median(t['guest_elapsed_ms'] for t in report['trials'] if t['command']==command)} for command in ('walk east marker','teleport east marker')}
    report['complete']=True;save();print(json.dumps(report['summary'],indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',choices=RECIPES,required=True);parser.add_argument('--game-dir',type=Path,required=True)
    parser.add_argument('--backend',type=Path,required=True);parser.add_argument('--work-dir',type=Path,required=True)
    run(parser.parse_args())
