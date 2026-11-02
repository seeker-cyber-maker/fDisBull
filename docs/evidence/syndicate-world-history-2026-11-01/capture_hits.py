"""Bounded original-game damage-site observer, not a per-projectile subscription.

Caller supplies a freshly verified private Controller configuration and same-run
engagement checkpoint. A different load or source must requalify the profile.
The two optional RAM edits are explicit test preparation and never touch files.
"""
from __future__ import annotations
import argparse,base64,hashlib,json,re,struct,sys,time
from pathlib import Path
from z_provider import Controller,MAIN_SHA
from syndicate_scene import Mission,identify_offset,digest
from world_history import WorldHistory,canonical


def verify_source_windows(c):
    """Verify selected runtime code after applying the actual object's LE fixups."""
    from fdisbull.le import load_le
    original=Path(c.cfg['original_vehicle_source']).read_bytes()
    if digest(original)!=MAIN_SHA:raise ValueError('Unexpected original program')
    image=load_le(original);code=image.regions[0];mapped=bytearray(code.data)
    bases={o['id']:o['runtime'] for o in c.mapping}
    for f in image.metadata['le']['fixups']:
        if f['source_object']==1:
            mapped[f['source_offset']:f['source_offset']+4]=(bases[f['target_object']]+f['target_offset']).to_bytes(4,'little')
    receipts=[]
    for a,b in [(0x127a0,0x127b8),(0x13b62,0x13bff),(0x3aa89,0x3ab68),(0x3add0,0x3aeb8),(0x12b4a,0x12baf),(0x32ce0,0x32db0),(0x32f60,0x3304e),(0x396b2,0x3970d)]:
        expected=bytes(mapped[a-code.start:b-code.start]);actual=c.read(a,b-a)
        if actual!=expected:raise ValueError('Damage/firing code binding mismatch')
        receipts.append({'preferred':hex(a),'bytes':b-a,'sha256':digest(actual),'relocation_context':'current verified object mapping'})
    return receipts

def capture(root, label, weapon_type, budget_ms=30000, first_fire=True, journal=None):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',label):raise ValueError('Invalid trial label')
    if type(budget_ms) is not int or not 1<=budget_ms<=120000:raise ValueError('Invalid capture budget')
    if weapon_type not in (2,6):raise ValueError('Unqualified weapon substitution')
    root=Path(root);folder=root/'private'/label;folder.mkdir(exist_ok=False)
    cfg=json.loads((root/'private/mission-binding.json').read_text());c=Controller(cfg)
    cp=json.loads((root/'private/engagement.json').read_text())
    call=c.call;requests={}
    def meter(op,args=None,**kw):
        key=kw.get('method',op);requests[key]=requests.get(key,0)+1
        return call(op,args,**kw)
    c.call=meter
    c.rpc('state.load',{'path':cp['path']});b=c.snapshot()
    if digest(b)!=cp['game_sha256']:raise ValueError('Checkpoint GAME identity mismatch')
    if c.rpc('breakpoints.list')['breakpoints']:raise ValueError('Another observer owns breakpoints')
    es={e['id']:e for e in Mission(b).summary()['entities']}
    weapon=es['weapon-6']
    if weapon['owner_id']!='person-11' or weapon['status_raw']!=2:raise ValueError('Unexpected original weapon/owner profile')
    windows=verify_source_windows(c)
    wp=0x80108+weapon['source_offset'];writes=[]
    # Equal ammunition preparation in both arms avoids comparing empty and full
    # weapons. The selected number is an experiment parameter, not a native cap.
    for at,data,why in [(wp+20,struct.pack('<h',200),'matched test ammunition'),(wp+25,bytes([weapon_type]),'requested weapon substitution')]:
        old=c.read(at,len(data))
        if old==data:continue
        c.rpc('memory.write',{'address':{'space':'linear','offset':f'0x{c.address(at):08X}'},'expected_sha256':digest(old),'data_base64':base64.b64encode(data).decode()})
        assert c.read(at,len(data))==data
        writes.append({'preferred':hex(at),'before':int.from_bytes(old,'little'),'after':int.from_bytes(data,'little'),'bytes':len(data),'purpose':why})
    history=WorldHistory(Path(journal) if journal else folder/'history.sqlite');stream=label
    history.stream(stream,metadata={'source_sha256':MAIN_SHA,'run_id':cfg['run_id'],'checkpoint_sha256':cp['game_sha256'],'weapon_type':weapon_type,'diagnostic_edits':writes})
    history.append(stream,'controller','begin',{'kind':'experiment-start','message':f'Original weapon type {weapon_type}; RAM-only test; ammo=200; no health edits.'})
    # Before/after stores establish committed health changes. This profile covers
    # only the qualified decrement sink; final HP accounting reports any gap.
    before_pc=0x13be4;after_pc=0x13be8;keys=[];hits=[];fire_witness=None
    def linear(at,n):
        return base64.b64decode(c.rpc('memory.read',{'address':{'space':'linear','offset':f'0x{at:08X}'},'length':n})['data_base64'])
    def entity(ptr):
        ref=ptr-c.address(0x8810e);x=identify_offset(ref)
        return f'{x[0]}-{x[1]}' if x else None
    def breakpoint(p,once):
        key=c.rpc('breakpoints.create',{'kind':'execution','address':{'space':'segmented','segment':cfg['cs'],'offset':f'0x{c.address(p):08X}'},'once':once})['breakpoint_id'];keys.append(key);return key
    def delete(k):
        try:c.rpc('breakpoints.delete',{'breakpoint_id':k})
        except Exception as e:
            if 'BREAKPOINT_NOT_FOUND' not in str(e):raise
    initial_tick=c.rpc('execution.timing')['guest_ticks'];last_tick=initial_tick;started=time.monotonic();reason='guest-budget';firingsite=0x3ab34 if weapon_type==2 else 0x3ae79
    breakpoint(before_pc,False);firekey=breakpoint(firingsite,True) if first_fire else None
    try:
        while last_tick-initial_tick<budget_ms and time.monotonic()-started<70 and len(hits)<128:
            r=c.call('run',{'guest_ms':min(1000,budget_ms-(last_tick-initial_tick)),'timeout_ms':4000,'fast_forward':True})
            last_tick=r['timing_after']['guest_ticks'];reg=c.call('regs');pc=int(reg['instruction_pointer'],16)
            if first_fire and pc==c.address(firingsite):
                ptr=int(reg['general']['edi'],16);w=linear(ptr,36)
                fire_witness={'weapon_id':entity(ptr),'type':w[25],'ammo':int.from_bytes(w[20:22],'little',signed=True),'guest_tick':last_tick,'preferred_pc':hex(firingsite)}
                history.append(stream,'source-witness','first-fire',{'kind':'first-fire-verified','message':f'Original firing branch for type {w[25]}','guest_tick':last_tick,'witness':fire_witness})
                continue
            if pc!=c.address(before_pc):
                if r['outcome']=='breakpoint':raise RuntimeError('Unexpected watch stop')
                continue
            victim=int(reg['general']['ebx'],16);effect=int(reg['general']['ebp'],16)
            victim_id=entity(victim);raw=linear(victim,28);old=int.from_bytes(raw[20:22],'little',signed=True)
            eff=linear(effect,32);effect_id=entity(effect);owner_ref=int.from_bytes(eff[28:30],'little');who=identify_offset(owner_ref)
            source_id=f'{who[0]}-{who[1]}' if who else None
            valid=eff[24]==3 and eff[25] in (29,30) and who and who[0]=='person'
            # Do not infer a weapon from what the owner holds at impact. The one-
            # weapon substitution is a separate experimental fact, not that rule.
            context={'effect_id':effect_id,'kind_raw':eff[24],'subtype_raw':eff[25],'owner_ref':owner_ref,'owner_id':source_id,
                     'victim_position_raw':list(struct.unpack_from('<HHH',raw,4)),'before_pc':hex(before_pc)}
            nextkey=breakpoint(after_pc,True)
            end=c.call('run',{'guest_ms':1000,'timeout_ms':4000,'fast_forward':True});post=c.call('regs')
            if int(post['instruction_pointer'],16)!=c.address(after_pc):raise RuntimeError('Health store completion not observed')
            new=int.from_bytes(linear(victim+20,2),'little',signed=True);last_tick=end['timing_after']['guest_ticks']
            if new>=old:raise RuntimeError('Qualified decrement did not decrease health')
            hit={'kind':'damage','guest_tick':last_tick,'victim_id':victim_id or 'unresolved-victim','health_before':old,'health_after':new,'amount':old-new,
                 'cause':{'actor_id':source_id if valid else None,'damage_type':'projectile' if valid else 'unknown','basis':'immediate qualified effect context at committed health store'},
                 'certainty':'native-observed' if valid else 'unattributed-native-change','observation_basis':'before/after original health store; no rewind and no per-bullet watches',
                 'context':context,'profile_scope':'known decrement sink only','after_pc':hex(after_pc)}
            inserted=history.append(stream,'health-sink',str(len(hits)+1),hit,player={'kind':'damage','guest_tick':last_tick,'victim_id':hit['victim_id'],'health_before':old,'health_after':new,'amount':old-new,
                'cause':{'actor_id':None,'damage_type':'unknown'},'certainty':'observed-health-loss','observation_basis':'test projection of player-visible health; no shooter perception supplied'})
            hits.append(hit|inserted)
            with (folder/'hits.jsonl').open('a') as f:f.write(canonical(hits[-1])+'\n')
            if victim_id=='person-0' and new<=0:reason='victim-nonpositive-health';break
        else:
            if time.monotonic()-started>=70:reason='host-budget'
            if len(hits)>=128:reason='hit-budget'
    except BaseException:
        # Persistence or attribution failure is a hold. Do not resume to a prettier
        # observation boundary after losing a record. The caller owns recovery.
        (folder/'CAPTURE_HELD.json').write_text(json.dumps({'capture_held':True,'guest_resume_in_cleanup':False,'completed_events':len(hits)}))
        raise
    finally:
        try:
            for k in keys:delete(k)
        finally:
            history.close()
    # Only normal, recorded completion may advance back to the foreground.
    c.vehicle_interactions.advance_to_frame()
    final=Mission(c.snapshot()).summary();fs={e['id']:e for e in final['entities']}
    history=WorldHistory(Path(journal) if journal else folder/'history.sqlite')
    try:
        history.append(stream,'controller','end',{'kind':'experiment-end','message':reason,'guest_tick':last_tick})
        history.export_jsonl(folder/'events.jsonl')
    finally:history.close()
    victim_hits=[h for h in hits if h['victim_id']=='person-0']
    result={'label':label,'weapon_type':weapon_type,'preparation_writes':writes,'first_fire':fire_witness,'hit_count':len(hits),'victim_hits':len(victim_hits),
            'victim_hp_before':es['person-0']['health_raw'],'victim_hp_after':fs['person-0']['health_raw'],'recorded_victim_loss':sum(h['amount'] for h in victim_hits),
            'final_health_accounting_gap':es['person-0']['health_raw']-fs['person-0']['health_raw']-sum(h['amount'] for h in victim_hits),
            'weapon_ammo_after':fs['weapon-6']['health_raw'],'guest_start_tick':initial_tick,'guest_last_observed_tick':last_tick,'wall_seconds':time.monotonic()-started,
            'stop_reason':reason,'requests':requests,'hits':hits,'source_sha256':MAIN_SHA,'run_id':cfg['run_id'],
            'no_rewind_during_capture':True,'per_projectile_creation_watches':0,'first_fire_watches':int(first_fire),'binding_windows':windows}
    (folder/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('hits','requests')},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('label');p.add_argument('weapon_type',type=int,choices=[2,6]);p.add_argument('--guest-ms',type=int,default=30000);p.add_argument('--no-fire-watch',action='store_true');p.add_argument('--journal',type=Path);a=p.parse_args();capture(a.root,a.label,a.weapon_type,a.guest_ms,not a.no_fire_watch,a.journal)
