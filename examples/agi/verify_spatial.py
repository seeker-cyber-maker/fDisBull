"""Verify qualified spatial policies on private original PQ1/KQ1 copies.

All resources, native states, databases, maps, frames and raw receipts remain
inside a new --work-dir. This does not qualify arbitrary editions or rooms.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from fdisbull.agi_picture import extract_v2_resource, decode_picture, priority_row_runs
from fdisbull.runtime_observations import capture_observations
from spatial_trial import native_game, find, read, require, eq, all_of, scene, travel


def save_map(p, game, room, width, root, *, reference, zones=()):
    item=extract_v2_resource(game/'PICDIR',game,room); decoded=decode_picture(item['payload'])
    resource=root/f'picture-{room}.bin'; resource.write_bytes(item['payload'])
    attached=p.attach_file(resource,name=f'picture-{room}')
    # This conservative profile excludes the upper unqualified horizon and
    # all trigger/water/barrier pixels. It does not promise global walkability.
    bounds={'rect':[0,90,160,156]}
    doc={'format':'fdisbull-spatial-map-1',
      'source':{'sha256':p.version()['sha256'],'context':reference['scene_revision'],'room':str(room),'resource':item['sha256']},
      'space':{'name':'agi-baseline','width':160,'height':168,'unit':'agi-unit'},
      'actor':{'width':width,'height':1,'anchor':[0,0]},'known':bounds,
      'safe':{'intersection':[bounds,priority_row_runs(decoded,list(range(4,16)))]},
      'layers':list(zones),
      'evidence':{'picture':{'file':f'picture-{room}','sha256':item['sha256'],'range':[0,len(item['payload'])],'bytes':item['payload'].hex()},
         'qualification':{'description':'conservative source control-plane candidate mask; native probes below are bounded, not whole-room movement equivalence'}}}
    if reference is not None:
        doc['evidence']['frame']={'artifact':reference['artifact'],'sha256':reference['sha256'],
                                'description':'original native room frame; byte identity does not prove mask semantics'}
    for ident,kind,values in [('barriers','obstacle',[0,1]),('water','hazard',[3]),('unqualified-triggers','hazard',[2])]:
        area=priority_row_runs(decoded,values)
        if area['row_runs']:doc['layers'].append({'id':ident,'kind':kind,'area':area})
    info=p.debug_save_spatial_map('room-map',doc)
    p.debug_spatial_overlay(info['id'],root/'map.png')
    return info,decoded


def radio_action(d, observations, revision, code_digest):
    return {'format':'fdisbull-spatial-action-1','id':'get-radio','version':1,'map_revision':revision,
      'observations':observations,'context':eq('room',6),
      'nonspatial_before':all_of(eq('score',0),eq('direction',0),eq('control_direction',0)),
      'nonspatial_after':all_of(eq('direction',0),eq('control_direction',0)), 'outcome':eq('score',2),
      'position':{'x':'x','y':'y'},
      'proximity':all_of({'field':'x','op':'in_range','value':[55,85]},{'field':'y','op':'in_range','value':[92,100]}),
      'inputs':[{'text':'GET RADIO','hold_ms':40,'gap_ms':40},{'key':'enter','hold_ms':250,'gap_ms':50},
                {'key':'enter','hold_ms':60,'gap_ms':50}],
      'guest_ms':5000,'slice_ms':100,'stationary':True,
      'spatial_guards':[{'kind':'spatial-resource','binding':'logic6','offset':0x282,
        'expected_hex':'0b00375c5564','data_hex':'0b0000009fa7',
        'provenance':{'source_sha256':d.metadata['source_sha256'],'version_sha256':d.metadata['version_sha256'],
          'resource_sha256':code_digest,'file':'logic6-code','resource_offset':0x282,
          'evidence':'LOGIC6 code IF27f sets f227; said(get14,radio268) at757 checks f227 then original inventory/state gates; addn(v3,2) at7e2'}}]}


def pq1(p,d,obs,restore,frame,report,game,root):
    source=extract_v2_resource(game/'LOGDIR',game,6)['payload']
    require(hashlib.sha256(source).hexdigest()=='5b83ca6f597788d2a57ed4fd5f5409a7cac4fc91e4dd0b57dc76f1f6222320c1','Unqualified PQ room logic')
    code=source[:2+int.from_bytes(source[:2],'little')]
    resource=root/'logic6-code.bin';resource.write_bytes(code);p.attach_file(resource,name='logic6-code')
    def bind():
        hits=find(d,code);require(len(hits)==1,'Logic code mapping is ambiguous')
        return d.bind_runtime_memory('logic6',hits[0],length=len(code),expected_hex=code[:2].hex(),
            provenance={'file':'logic6-code','sha256':hashlib.sha256(code).hexdigest(),'method':'unique full original code prefix in paused conventional RAM'})
    binding=bind();report['steps']['logic_binding']=binding
    reference=frame('initial.png');origin=scene(p,d,reference,6)
    reference['scene_revision']=origin['id']
    info,_=save_map(p,game,6,7,root,zones=[{'id':'radio','kind':'object','area':{'rect':[55,92,86,101]},'interaction_points':[[67,98]]}],reference=reference)
    report['steps']['map_revision']=info['id']; definition=radio_action(d,obs,info['id'],hashlib.sha256(code).hexdigest())
    d.spatial_policy('physical')
    refused=d.spatial_action(info['id'],definition);report['steps']['physical_far']=refused
    require(not refused['ok'] and not refused['inputs'],'Physical mode accepted a far target')
    # The original command is also tested at the original position to establish
    # the guest's own spatial rejection independently of the host preflight.
    d.keyboard_type('GET RADIO\n');d.run(guest_ms=2000,timeout_ms=10000,fast_forward=True)
    report['steps']['original_far']=capture_observations(d,obs);frame('original-far.png')
    require(report['steps']['original_far']['values']['score']==0,'Original far command unexpectedly awarded points')
    restore();bind(); d.spatial_policy('story')
    story=d.spatial_action(info['id'],definition);report['steps']['story']=story;frame('story.png')
    require(story['ok'] and story['complete'],'Story action did not complete')
    require(story['before']['values']['x']==story['after']['values']['x']==60 and story['before']['values']['y']==story['after']['values']['y']==120,'Story action moved the actor')
    require(d.runtime_memory('logic6',offset=0,length=len(code))['hex']==code.hex(),'Story guard did not restore')
    # Repeat through the original parser after the guard is gone: inventory and
    # the one-time award remain guest-owned. Dismiss any previous message first.
    d.keyboard_press('enter');d.run(guest_ms=400,timeout_ms=5000,fast_forward=True)
    d.keyboard_type('GET RADIO\n');d.run(guest_ms=2000,timeout_ms=10000,fast_forward=True)
    report['steps']['repeat_original']=capture_observations(d,obs);frame('repeat-original.png')
    require(report['steps']['repeat_original']['values']['score']==2,'Original one-time award changed')
    restore();bind(); d.spatial_policy('assisted')
    recipe={'x':{'binding':'actor','offset':3,'type':'u16'},'y':{'binding':'actor','offset':5,'type':'u16'},
            'refresh':[{'binding':'actor','offset':37,'type':'u16','set_bits':0x400}]}
    assisted=d.spatial_action(info['id'],definition,zone='radio',actor_recipe=recipe,
                            travel_plan=travel(origin['id'],obs,6,[67,98]))
    report['steps']['assisted']=assisted;frame('assisted.png')
    require(assisted['ok'] and assisted['after']['values']['score']==2,'Assisted original pickup did not complete')
    restore();bind();d.spatial_policy('assisted')
    placed=d.assisted_travel(travel(origin['id'],obs,6,[67,98]));require(placed['ok'],'Control anchor placement failed')
    d.spatial_policy('physical');physical=d.spatial_action(info['id'],definition)
    report['steps']['physical_near']=physical;frame('physical-near.png')
    require(physical['ok'] and physical['after']['values']['score']==2,'Near physical pickup failed')
    # Preserve an actual debugger stop during the story action, then capture a
    # bounded native trace of the original score-commit continuation.
    restore();bind();d.spatial_policy('story')
    writer=int(report['resolution']['writer_linear'],16)
    bp=d.call('breakpoints.create',{'kind':'execution','once':False,
        'address':{'space':'segmented','segment':f'0x{writer>>4:04X}','offset':f'0x{writer&15:08X}'}})
    require(d.run(guest_ms=5000,timeout_ms=10000,fast_forward=True)['outcome']=='breakpoint','Watch preparation writer did not stop')
    watch=d.call('breakpoints.create',{'kind':'w','once':False,
        'address':{'space':'linear','offset':f"0x{int(report['resolution']['ds_linear'],16)+12:08X}"}})
    d.call('breakpoints.delete',{'breakpoint_id':bp['breakpoint_id']})
    stopped=d.spatial_action(info['id'],definition);report['steps']['watchpoint_action']=stopped
    require(stopped['status']=='stopped' and not stopped['ok'],'Action ran through the score watchpoint')
    require(d.runtime_memory('logic6',offset=0,length=len(code))['hex']==code.hex(),'Guard was not restored at the debugger stop')
    traced=d.trace('radio-score-trace.json',count=32,timeout_ms=10000,fast_forward=True)
    p.debug_export(traced['artifact'],root/'radio-score-trace.json');report['steps']['trace']=traced
    d.call('breakpoints.delete',{'breakpoint_id':watch['breakpoint_id']})
    d.run(guest_ms=300,timeout_ms=5000,fast_forward=True)
    report['steps']['after_trace']=capture_observations(d,obs)
    require(report['steps']['after_trace']['values']['score']==2,'Original native score continuation differed')
    # The separately packaged player receives a public named target and action.
    # Guard bytes, coordinates and disassembly stay in the private projection.
    from fdisbull.progressive_scenes import resource_inventory
    from fdisbull.scene_bundles import identity
    from fdisbull_player import Player
    restore();bind();d.spatial_policy('story')
    object_id=origin['definition']['objects'][0]['id']
    workflow=p.debug_save_workflow('radio-player',{'format':'fdisbull-progressive-workflow-1',
        'source':identity(p,1),'inventory':resource_inventory(game,engine='agi',profile='pq1-2.917',adapter='qualified-radio-022'),
        'research':[],'actions':[{'name':'take-radio','kind':'spatial','scene_revision':origin['id'],
            'object_id':object_id,'dependencies':[],'evidence':[reference['artifact']]}]},resource_root=game)
    projection=p.debug_save_text_projection('radio-player',{'format':'fdisbull-text-projection-1','workflow_revision':workflow['id'],
        'contexts':[{'id':'hall','title':'Station hallway','description':'The qualified radio pickup is available.',
          'scene_revision':origin['id'],'partial':True,'objects':[{'id':'radio','label':'radio','aliases':['extender'],
            'description':'A radio extender.','scene_object':object_id,'inventory':False,
            'bindings':[{'verb':'take','item':None,'action':'take-radio','dispatch':{'kind':'spatial',
                'args':{'map_revision':info['id'],'definition':definition}}}]}]}]})
    public=d.text_projection(projection['id'],game)
    report['steps']['player_observation']=public.observe()
    reply=Player(public).execute('take radio');report['steps']['player_reply']=reply
    require(reply=='Success: Action completed.\nSpatial policy: story.','Separate player did not complete the named story action')
    require('spatial_guards' not in json.dumps(report['steps']['player_observation']),'Private guard leaked into player observation')
    report['steps']['player_after']=capture_observations(d,obs);frame('player-story.png')
    require(report['steps']['player_after']['values']==story['after']['values'],'Player and direct story outcomes differed')
    report['ok']=True


def kq1(p,d,obs,restore,frame,report,game,root):
    reference=frame('initial.png');origin=scene(p,d,reference,1)
    reference['scene_revision']=origin['id']
    info,decoded=save_map(p,game,1,6,root,zones=[{'id':'tree-approach','kind':'object',
        'area':{'union':[{'rect':[120,120,128,128]},{'rect':[120,95,130,105]}]},
        'interaction_points':[[125,125],[125,100]]}],reference=reference)
    report['steps']['map_revision']=info['id']
    masks={name:p.debug_spatial_check(info['id'],point) for name,point in
        [('clear-path',[125,100]),('tree-approach',[125,125]),('tree-trunk',[133,125]),
         ('moat-edge',[106,150]),('moat-water',[118,150]),('upper-unknown',[110,40])]}
    report['steps']['mask_checks']=masks
    require(all(masks[name]['classification']=='clear' for name in ('clear-path','tree-approach','moat-edge')),'Expected test anchors are not clear')
    require(masks['tree-trunk']['classification']=='blocked' and masks['moat-water']['classification']=='blocked','Tree or moat was not excluded')
    require(masks['upper-unknown']['classification']=='unknown','Unqualified region became clear')
    report['steps']['candidates']=p.debug_spatial_candidates(info['id'],zone='tree-approach',origin=[110,100],limit=8,clearance=1)
    report['steps']['route']=p.debug_spatial_route(info['id'],[110,100],[125,125],maxnodes=20000)
    require(report['steps']['route']['status']=='found','Map route to tree approach not found')
    macros={'format':'fdisbull-macro-set-1','name':'spatial-latched','provenance':{'scope':'observed KQ edition cardinal toggle'},'macros':{}}
    for key in ('left','right','up','down'):
        for suffix in ('start','stop'):
            macros['macros'][key+'-'+suffix]={'parameters':{},'authority':'player-input',
                'steps':[{'op':'keyboard.press','key':key,'hold_ms':60,'gap_ms':50}]}
    macro=p.debug_define_macros(macros,version=1)
    trials=[('clear-path',[125,100],'right','x',146,'reached'),
            ('tree',[125,125],'right','x',145,'blocked'),
            ('moat-guarded',[106,150],'right','x',125,'refused'),
            ('moat-diagnostic',[106,150],'right','x',125,'hazard')]
    report['steps']['walking']=[]
    for name,point,key,axis,target,expected in trials:
        restore();d.spatial_policy('assisted')
        check=p.debug_spatial_check(info['id'],point);require(check['classification']=='clear','Unsafe diagnostic start')
        placed=d.assisted_travel(travel(origin['id'],obs,1,point));require(placed['ok'],'Diagnostic placement failed')
        frame(name+'-start.png');d.spatial_policy('physical')
        map_options={} if expected=='hazard' else {'spatial_map':info['id'],'position':{'x':'x','y':'y'},'target':[target,point[1]]}
        goal=({'field':axis,'op':'in_range','value':[144,149]} if expected=='reached' else {'field':axis,'op':'ge','value':target})
        moved=d.move(macro['id'],start={'name':key+'-start'},stop={'name':key+'-stop'},observations=obs,
            until=all_of(eq('room',1),goal),
            progress={'fields':['x','y','room'],'samples':15},settle=all_of(eq('direction',0),eq('control_direction',0)),
            context=eq('room',1),guest_ms=10000,timeout_ms=20000,slice_ms=50,cleanup_guest_ms=1000,target_tolerance=3 if expected=='reached' else 0,**map_options)
        after=capture_observations(d,obs);frame(name+'-end.png')
        report['steps']['walking'].append({'name':name,'map_start':check,'placement':placed,'movement':moved,'after':after})
        print(name,moved.get('outcome'),moved.get('classification'),after.get('values'),flush=True)
        require(after['complete'] and after['values']['room']==1 and after['values']['direction']==after['values']['control_direction']==0,'Walking did not end neutral in original room')
        if expected=='reached':require(moved.get('ok') is True and 144<=after['values'][axis]<=149,'Clear route was not traversed')
        elif expected=='blocked':require(moved.get('outcome')=='blocked' and moved.get('classification')=='blocked_known_boundary' and after['values'][axis]==127,'Original tree boundary disagreed with the mask')
        elif expected=='refused':require(moved.get('outcome')=='destination_blocked' and [after['values']['x'],after['values']['y']]==point and not moved['cleanup']['attempted'],'Hazard destination was not refused before input')
        else:
            checked=p.debug_spatial_check(info['id'],[after['values']['x'],after['values']['y']])
            require(checked['classification']=='blocked' and 'water' in checked['reasons']['blocked'] and after['values']['y']==166,'Diagnostic moat hazard was not observed')
    restore();d.spatial_policy('physical',fair_play=True);restore()
    refused=d.assisted_travel({});report['steps']['fair_play_restore']=refused
    require(refused['status']=='refused' and d._spatial_mode=='physical' and d._fair_play,'Restore weakened fair-play policy')
    report['ok']=True


def run(args):
    root=args.work_dir.resolve()
    with native_game(args.game,args.game_dir,root,args.backend) as values:
        p,d,obs,restore,frame,report,game=values
        (pq1 if args.game=='pq1' else kq1)(p,d,obs,restore,frame,report,game,root)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',choices=['pq1','kq1'],required=True)
    parser.add_argument('--game-dir',type=Path,required=True);parser.add_argument('--work-dir',type=Path,required=True)
    parser.add_argument('--backend',type=Path,required=True)
    run(parser.parse_args())
