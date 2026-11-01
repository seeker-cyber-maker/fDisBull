"""Fresh physical KQ1 clover/diamonds/shield cave route; private inputs only.

Static paths are proposals. Original collision, parser, inventory, dialogue
and room-entry code decide their outcomes. No guest edits, redirected calls,
teleports or native-state loads are used. This is one branch, not full KQ1.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from examples.agi.spatial_trial import native_game, read, require, manifest
from examples.agi.verify_goat import GoatRun
from examples.agi.verify_mushroom import MushroomRun
from examples.agi.verify_bridge_clip import retain_private_evidence
from examples.agi.verify_troll import OBJECT_SHA256, SCORE_WRITER
from examples.agi.scan_collision_candidates import bounded_path, extract_water_guards
from fdisbull.agi import load_logic
from fdisbull.agi_layout import logic_layout
from fdisbull.agi_picture import decode_picture, extract_v2_resource


class CaveRun(MushroomRun):
    guest_budget_ms = 900000
    wall_budget_ms = 1800000

    def __init__(self, *args):
        super().__init__(*args)
        for n in (6, 7, 23, 24, 36, 73, 74, 75, 76, 77, 78):
            self.resources[n] = load_logic(self.source/'LOGDIR', self.source, n, profile='2.917')
        self.preparation = []
        self.allow_small_walk = False
        self.bind_inventory()
        self.report['implementation_sha256']['examples/agi/verify_leprechaun.py'] = sha256(Path(__file__).read_bytes()).hexdigest()

    def bind_inventory(self):
        raw = (self.source/'OBJECT').read_bytes(); key = b'Avis Durgan'
        decoded = bytes(value ^ key[i % len(key)] for i,value in enumerate(raw))
        require(sha256(raw).hexdigest() == OBJECT_SHA256 and int.from_bytes(decoded[:2],'little') == 81,
                'Inventory source table differs')
        records = {}
        for item in (8,15,16,21,24):
            name = int.from_bytes(decoded[3+3*item:5+3*item],'little')
            end = decoded.find(b'\0',3+name)
            require(81 <= name and 3+name < end < len(decoded) and end-3-name <= 64,
                    'Inventory source name bounds differ')
            text = decoded[3+name:end+1]
            require(read(self.d,self.ds+self.inventory['base']+3*item,2) == name.to_bytes(2,'little') and
                    read(self.d,self.ds+self.inventory['base']+name,len(text)) == text,
                    'Live inventory record/name differs')
            records[str(item)] = {'record_offset':3*item, 'name_offset':name,
                                  'name_sha256':sha256(text).hexdigest(), 'location_offset':3*item+2}
        self.report['cave_inventory_binding'] = {**self.inventory, 'records':records}

    def state(self):
        s = super().state()
        f = read(self.d, self.ds+0x109, 32)
        flag = lambda n: bool(f[n//8] & (0x80 >> (n % 8)))
        s.update(clover_active=flag(87), mushroom_available=flag(123), small=flag(120),
                 mushroom_consumed=flag(124), rat_removed=flag(138), landing=flag(98), stair_move_done=flag(148))
        table = int.from_bytes(read(self.d,self.ds+0x963,2),'little')
        s['ignore_blocks'] = bool(int.from_bytes(read(self.d,self.ds+table+37,2),'little') & 2)
        s['small_timer'] = read(self.d,self.ds+9+82,1)[0]
        if hasattr(self, 'inventory'):
            locations = {str(n): read(self.d, self.ds+self.inventory['base']+3*n+2, 1)[0]
                         for n in (8, 15, 16, 21, 24)}
            s['inventory_locations'] = locations
            for name, item in (('clover',8), ('diamonds',15), ('bag',16), ('shield',21), ('mushroom',24)):
                s[name+'_carried'] = locations[str(item)] == 255
        return s

    def safe_state(self):
        s = self.state()
        self.samples.append({'guest_ms': self.guest_elapsed, 'state': s})
        require(not s['dead'] and not s['in_water'] and not s['swimming'], 'Original guest entered water/death')
        if getattr(self,'allow_small_walk',False):
            require(s['room']==78 and s['small'] and s['ego_width']==4 and s['ego_view']==60 and
                    s['ignore_blocks'] and s['small_timer']>1, 'Original small-walking state changed')
        else:
            require(s['ego_width'] == 6 and s['ego_view'] == 0, 'Walking footprint changed')
        require(s['step_size']==1, 'Walking step size changed')
        return s

    def advance(self, ms=100):
        require(not getattr(self,'execution_blocked',False),
                'Earlier execution/observation failed; preserve the stop and start a fresh session')
        try:
            return super().advance(ms)
        except BaseException as exc:
            # A second call must not silently turn a lost reply or unqualified
            # stop into permission for more execution. Queries remain usable.
            self.execution_blocked=True
            self.report['execution_blocked']={'error':str(exc),'journal_entries':len(self.journal)}
            raise

    def type_text(self, text):
        """Type once without Enter; input delivery alone is not an outcome."""
        previous = self.fast_forward
        self.fast_forward = False
        try:
            require(self._idle(), 'Keyboard not idle')
            item = {'kind':'keyboard', 'key':'type:'+text, 'delivered':None, 'complete':False}
            self.inputs.append(item); self.journal.append({'kind':'input', 'record':item})
            item['delivery'] = self.d.keyboard_type(text, hold_ms=1, gap_ms=1)
            item['delivered'] = item['delivery'].get('accepted')
            self.advance(len(text)*2+20)
            item['complete'] = self._idle()
            require(item['delivered'] is True and item['complete'], 'Typed input outcome unknown')
        finally:
            self.fast_forward = previous

    def command(self, text):
        previous=self.fast_forward; self.fast_forward=False
        try:
            self.type_text(text)
            self.press('enter',300,hold_ms=1,gap_ms=1)
        finally:self.fast_forward=previous

    def wait_for(self, predicate, label, budget=15000):
        end = self.guest_elapsed+budget
        while True:
            s = self.state()
            require(not s['dead'], 'Original guest death during '+label)
            if predicate(s): return s
            require(self.guest_elapsed < end, label+' observation budget exhausted')
            self.advance(min(100, end-self.guest_elapsed))

    def _precise(self, *, x=None, y=None):
        """Sample near the endpoint more often; preserve exact unit waypoints."""
        self.ready(); start = self.safe_state(); a = start['ego']
        targets = {k:v for k,v in (('x',x),('y',y)) if v is not None}
        require(bool(targets), 'Missing waypoint')
        dx = 0 if x is None else x-a['x']; dy = 0 if y is None else y-a['y']
        if dx == dy == 0: return start
        require(not (dx and dy) or abs(dx) == abs(dy), 'Expected straight or unit diagonal waypoint')
        sx = (dx>0)-(dx<0); sy = (dy>0)-(dy<0)
        key = {(0,-1):'up',(1,-1):'pageup',(1,0):'right',(1,1):'pagedown',
               (0,1):'down',(-1,1):'end',(-1,0):'left',(-1,-1):'home'}[(sx,sy)]
        self.press(key, 20, hold_ms=1, gap_ms=1)
        end = self.guest_elapsed+25000; last = None; still_ms = 0
        while self.guest_elapsed < end:
            s = self.safe_state(); p = s['ego']
            require(s['room'] == start['room'], 'Waypoint changed room unexpectedly')
            if all(p[k] == v for k,v in targets.items()):
                self.neutral(); final = self.safe_state()
                require(all(final['ego'][k] == v for k,v in targets.items()), 'Waypoint did not settle precisely')
                return final
            require((not sx or (p['x']-x)*sx <= 0) and (not sy or (p['y']-y)*sy <= 0), 'Waypoint overshoot')
            distance = max(abs(p[k]-v) for k,v in targets.items())
            step = 100 if distance > 3 else 10
            point = (p['x'],p['y'])
            still_ms = still_ms+step if point == last else 0; last = point
            require(still_ms < 1500, 'Precise route blocked')
            self.advance(step)
        raise RuntimeError('Precise waypoint observation budget exhausted')

    def path_model(self, room, start, target, *, allow_priority_one):
        resource = self.resources[room]
        item = extract_v2_resource(self.source/'PICDIR', self.source, room)
        plane = bytearray(decode_picture(item['payload'])['priority'])
        horizon = 43
        for p in logic_layout(resource.payload)['instructions']:
            if resource.payload[p] == 63:
                horizon = resource.payload[p+1]; break
        plane[:(horizon+1)*160] = bytes((horizon+1)*160)
        guards = extract_water_guards(resource.payload, logic_number=room)
        # The original actor flag selects conditional priority-one passability.
        # This reads guest policy; it never changes it to admit a proposed path.
        result = bounded_path(bytes(plane), start, target, width=6,
            allow_priority_one=allow_priority_one, hazards=[r for g in guards for r in g['rectangles']],
            max_nodes=26880, max_steps=1024)
        return result, item

    def static_path(self, x, y):
        self.ready(); s = self.safe_state(); room = s['room']
        result, picture = self.path_model(room, (s['ego']['x'],s['ego']['y']), (x,y),
                                         allow_priority_one=s['ignore_blocks'])
        require(result['status'] == 'found', 'Static proposal absent/incomplete: '+result['status'])
        points = result['path']; turns = []
        for i,p in enumerate(points[1:], 1):
            if i == len(points)-1 or (p[0]-points[i-1][0],p[1]-points[i-1][1]) != (points[i+1][0]-p[0],points[i+1][1]-p[1]):
                turns.append(p)
        self.journal.append({'kind':'static-path-proposal', 'room':room, 'picture_sha256':picture['sha256'],
            'logic_sha256':self.resources[room].resource_sha256, 'waypoints':turns,
            'priority_one_allowed_by_original_actor':s['ignore_blocks'],
            'scope':'Static baseline proposal; dynamic objects, added cels and original execution decide passability.'})
        for a,b in turns:
            current = self.state()['ego']
            self.precise(**({'x':a} if a != current['x'] else {'y':b}))

    def surface_exit(self, key, room, preferred=None):
        self.ready(); s = self.safe_state(); n = s['room']
        values = ([preferred] if preferred is not None else [])
        values += ([s['ego']['y'],150,140,130,120,110,100,90,80,70,60,160]
                   if key in ('left','right') else [s['ego']['x'],20,70,100,130,40,150])
        target = None
        for v in dict.fromkeys(values):
            point = ((153 if key == 'right' else 2),v) if key in ('left','right') else (v,48 if key == 'up' else 165)
            candidate, _ = self.path_model(n, (s['ego']['x'],s['ego']['y']), point,
                                           allow_priority_one=s['ignore_blocks'])
            if candidate['status'] == 'found': target = point; break
        require(target is not None, 'No static exit proposal')
        self.static_path(*target); self.move(key, room=room)

    def prep_frame(self, name):
        self.ready(); self.safe_state(); item = self.frame(name+'.png')
        self.preparation.append({'id':name, 'state':self.state(),
            'frame':{'path':name+'.png','sha256':item['sha256'],'metadata':item['metadata']}})
        print(json.dumps({'preparation':name,'state':self.state()}), flush=True)

    def prepare(self):
        require(self.state()['room'] == 1 and self.state()['score'] == 0, 'Fresh game required')
        self.surface_exit('right',8); self.surface_exit('up',9,20); self.surface_exit('up',24,20)
        self.static_path(65,140); self.command('get clover')
        self.wait_for(lambda s:s['clover_carried'] and s['clover_active'] and s['score']==2, 'clover pickup')
        self.prep_frame('clover')
        self.surface_exit('right',23); self.surface_exit('down',10)
        self.surface_exit('right',11); self.surface_exit('down',6,100)
        self.static_path(30,120); self.command('get bag')
        self.wait_for(lambda s:s['bag_carried'] and s['score']==5, 'bag pickup')
        self.prep_frame('bag')
        self.precise(y=110); self.surface_exit('left',7,110); self.surface_exit('up',10,150)
        self.surface_exit('left',9,165); self.surface_exit('down',8,20)
        self.static_path(70,140); self.move('down',room=41)
        self.precise(x=154); self.move('down',room=40)
        self.precise(y=100); self.static_path(1,100); self.move('left',room=33)
        self.precise(x=154); self.precise(y=87); self.precise(y=55); self.move('up',room=48)
        self.static_path(129,140); self.static_path(1,150); self.move('left',room=47)
        self.static_path(94,90); self.command('get mushroom')
        self.wait_for(lambda s:s['mushroom_carried'] and s['mushroom_available'] and s['score']==6, 'mushroom pickup')
        self.prep_frame('mushroom')

    def route(self):
        self.prepare()
        return self.resume_cave()

    def resume_cave(self):
        require(self.state()['room']==47 and self.state()['score']==6 and self.state()['mushroom_carried'],
                'Prepared cave start differs')
        self.static_path(153,150); self.move('right',room=48); self.static_path(81,130)
        before = self.observe_clip('hole-before'); i,m = len(self.inputs),len(self.messages)
        self.press('up',20,hold_ms=1,gap_ms=1)
        self.wait_for(lambda s:s['room']==73 and not s['initializing'] and not s['landing'] and
                      s['ego']['drawn'] and s['ego_view']==0 and s['ego_width']==6, 'hole descent', 30000)
        self.ready(); after = self.observe_clip('hole-after'); self.action('enter-hole',before,after,i,m)
        before=after; i,m=len(self.inputs),len(self.messages)
        self.command('open bag')
        self.wait_for(lambda s:s['diamonds_carried'] and not s['bag_carried'] and s['score']==9, 'open bag')
        after=self.observe_clip('bag-opened'); self.action('open-bag',before,after,i,m)
        before=after; i,m=len(self.inputs),len(self.messages)
        self.move('down',room=74); self.static_path(2,115); self.move('left',room=75)
        self.static_path(149,115)
        after=self.observe_clip('rat-before'); self.action('follow-tunnel',before,after,i,m)
        self.approach_rat(after)
        self.enter_throne()
        self.take_shield()
        return self.finish_exit()

    def approach_rat(self, before):
        i,m=len(self.inputs),len(self.messages)
        previous=self.fast_forward; self.fast_forward=False
        try:
            # Pretyping is an ordinary parser action visible in Robb's video.
            # Submit while moving, before a stop/type round trip changes range.
            self.type_text('give bag'); self.press('left',20,hold_ms=1,gap_ms=1)
            end=self.guest_elapsed+20000
            while True:
                s=self.state()
                require(s['room']==75 and not s['dead'] and s['distance']>15, 'Rat engagement unsafe')
                if 22<=s['distance']<=28:break
                require(self.guest_elapsed<end, 'Rat payment range observation budget exhausted')
                self.advance(10)
            self.report['rat_submit_state']=self.state()
            self.press('enter',300,hold_ms=1,gap_ms=1)
            require(not any(x.get('logic')==75 and x.get('source_offset')==0x201 for x in self.messages[m:]),
                    'Original rat refused this payment; preserve the refusal')
            self.wait_for(lambda s:not s['diamonds_carried'] and s['score']==3, 'rat payment commit', 2000)
            self.neutral()
            self.wait_for(lambda s:s['rat_removed'], 'rat departure', 5000)
        finally:self.fast_forward=previous
        self.static_path(82,115)
        after=self.observe_clip('rat-paid'); self.action('pay-rat',before,after,i,m)
        return after

    def enter_throne(self):
        s=self.safe_state()
        require(s['room']==75 and s['score']==3 and s['rat_removed'] and s['clover_active'], 'Prepared rat exit differs')
        before='rat-paid' if 'rat-paid' in self.clip_observations else self.observe_clip('rat-paid')
        i,m=len(self.inputs),len(self.messages)
        self.static_path(40,115); self.command('open door')
        self.wait_for(lambda s:s['room']==76, 'cave door')
        self.ready(); self.static_path(105,165); self.move('down',room=77)
        self.static_path(87,70)
        after=self.observe_clip('throne-before'); self.action('enter-throne',before,after,i,m)
        self.shield_action=(after,len(self.inputs),len(self.messages))
        return after

    def source_binding(self, regs):
        require(int(regs['segments']['cs'],16)==self.cs and int(regs['segments']['ds'],16)*16==self.ds,
                'Shield segment binding changed')
        record=int.from_bytes(read(self.d,self.ds+0x979,2),'little')
        desc=read(self.d,self.ds+record,10); code=int.from_bytes(desc[4:6],'little')
        resource=self.resources[77]
        require(desc[2]==77 and code+len(resource.code)<=65536 and
                read(self.d,self.ds+code,len(resource.code))==resource.code and
                resource.code[0x3dd:0x3e2]==bytes.fromhex('5c15050308'), 'Shield source binding changed')
        return code

    def persist_shield(self):
        (self.root/'shield-pickup.private.json').write_text(json.dumps(self.predicate_proof,indent=2)+'\n')

    def take_shield(self):
        before,i,m=self.shield_action
        # The upper part of the source guard is inside the King's barrier.
        # The drawn shield also collides on its baseline. Walk below both
        # before moving east, inside the same original posn box.
        self.static_path(100,135); self.static_path(133,135); s=self.safe_state()
        self.bind_inventory()
        require(s['room']==77 and s['score']==3 and not s['shield_carried'] and
                s['inventory_locations']['21']==0 and self._idle(), 'Shield action already committed or input unsettled')
        require(read(self.d,self.cs*16+0x72d4,len(SCORE_WRITER))==SCORE_WRITER, 'Score writer differs')
        self.predicate_proof={'format':'fdisbull-agi-shield-pickup-1','status':'incomplete','complete':False,
            'native_execution':False,'source_logic':77,'source_logic_sha256':self.resources[77].resource_sha256,
            'item_source_offset':0x3dd,'score_source_offset':0x3df,
            'before':{'score':3,'item_location':0},'inventory_binding':self.report['cave_inventory_binding']}
        self.persist_shield(); self.watch_kind='shield-item'
        self.arm('w',self.ds+self.inventory['base']+65)
        self.command('get shield')
        self.wait_for(lambda s:s['shield_carried'] and s['score']==11, 'shield pickup')
        require(self.predicate_proof['complete'] is True, 'Original shield effects incomplete')
        after=self.observe_clip('shield-taken'); self.action('take-shield',before,after,i,m)
        self.clip_actions[-1]['native_pickup']={'path':'shield-pickup.private.json',
            'sha256':sha256((self.root/'shield-pickup.private.json').read_bytes()).hexdigest()}
        self.exit_action=(after,len(self.inputs),len(self.messages))
        return after

    def handle_stop(self, out):
        reason=(out.get('session') or {}).get('stop_reason',{})
        require(self.watch is not None and reason.get('breakpoint_id')==self.watch, 'Foreign stop preserved')
        regs=self.d.registers(); code=self.source_binding(regs); ip=int(regs['instruction_pointer'],16)
        proof=self.predicate_proof
        if self.watch_kind=='shield-return':
            ss,bp,original_code=self.item_frame
            require(not reason.get('data_access') and ip==0x2fa and code==original_code and
                    int(regs['segments']['ss'],16)==ss and int(regs['general']['esp'],16)&65535==bp+8 and
                    int(regs['general']['eax'],16)&65535==code+0x3df and
                    read(self.d,ss*16+bp+8,2)==(code+0x3df).to_bytes(2,'little'),
                    'Original shield get handler return differs')
            proof['handler_return']={'offset':0x2fa,'observed':True,'source_cursor_offset':0x3df,'stack_verified':True}
            self.persist_shield(); self.remove_watch(); self.watch_kind='shield-score'; self.arm('w',self.ds+12)
            return
        access=reason.get('data_access',{}); cause=access.get('instruction',{})
        offset,resume=(0x7482,0x7486) if self.watch_kind=='shield-item' else (0x72da,0x72de)
        require(self.watch_kind in ('shield-item','shield-score') and access.get('access')=='w' and
                cause.get('space')=='segmented' and int(cause.get('segment','-1'),16)==self.cs and
                int(cause.get('offset','-1'),16)==offset and ip==resume, 'Unqualified shield writer')
        if self.watch_kind=='shield-item':
            di=int(regs['general']['edi'],16)&65535; bp=int(regs['general']['ebp'],16)&65535
            sp=int(regs['general']['esp'],16)&65535; ss=int(regs['segments']['ss'],16)
            require(di==self.inventory['base']+63 and sp==bp<=65525 and
                    read(self.d,ss*16+bp+6,4)==(0x2fa).to_bytes(2,'little')+(code+0x3df).to_bytes(2,'little') and
                    self.state()['inventory_locations']['21']==255 and self.state()['score']==3,
                    'Shield item write/call frame differs')
            self.item_frame=(ss,bp,code)
            proof['item_writer']={'cause_offset':offset,'resume_offset':resume,'di_offset':di}
            proof['known_effects']={'score':3,'item_location':255}; self.persist_shield()
            self.remove_watch(); self.watch_kind='shield-return'; self.arm('execution',0x2fa,'segmented')
            self.trace_receipt={'format':'fdisbull-agi-shield-trace-1','maximum_count':128,'complete':False,'events':[],
                'runs':[],'scope':'Native fetch observations; item write, real handler return and score write observed separately.'}
            self.trace_start_index=len(self.journal); self.trace_active=True
            self.d.call('trace.start',{'detail':'normal','instruction_count':128}); return
        bx=int(regs['general']['ebx'],16)&65535; al=int(regs['general']['eax'],16)&255
        require(bx==3 and al==8 and int(regs['general']['esi'],16)&65535==code+0x3e2 and
                self.state()['score']==11 and self.state()['inventory_locations']['21']==255, 'Shield score operands differ')
        proof['score_writer']={'cause_offset':offset,'resume_offset':resume,'bx':bx,'al':al}
        proof['known_effects']={'score':11,'item_location':255}; self.persist_shield(); self.remove_watch()
        page=self.d.call('trace.read',{'cursor':None,'limit':256}); events=page['events']
        require(isinstance(events,list), 'Shield trace events unavailable')
        known=self.trace_receipt['events']
        require(len(events)>=len(known) and events[:len(known)]==known, 'Shield trace readback contradicts known events')
        # Preserve observations even when this page demonstrates exhaustion.
        # A later failed cleanup read must not erase a page already received.
        self.trace_receipt['events']=events
        self.trace_receipt['runs']=[x['result'] for x in self.journal[self.trace_start_index:] if isinstance(x.get('result'),dict)]
        require(not page.get('next_cursor') and 0<len(events)<128, 'Shield trace exhausted/incomplete')
        self.stop_trace(); self.trace_receipt['complete']=True
        path=self.root/'shield-trace.private.json'; path.write_text(json.dumps(self.trace_receipt,indent=2)+'\n')
        proof.update(native_execution=True,status='verified',complete=True,after={'score':11,'item_location':255},
            trace={'path':path.name,'sha256':sha256(path.read_bytes()).hexdigest(),'event_count':len(events),'maximum_count':128})
        self.persist_shield()

    def finish_exit(self):
        before,i,m=self.exit_action
        self.static_path(70,135); self.static_path(70,95); self.static_path(2,95)
        self.press('left',20,hold_ms=1,gap_ms=1)
        self.wait_for(lambda s:s['room']==78 and not s['initializing'] and s['stair_move_done'] and
                      (s['ego']['x'],s['ego']['y'])==(145,130), 'stairs entry')
        self.ready(); self.static_path(20,80)
        self.command('eat mushroom')
        small=self.wait_for(lambda s:s['small'] and not s['mushroom_carried'] and not s['mushroom_available'] and
                            s['ego_view']==60 and s['ego_width']==4 and s['ignore_blocks'] and
                            s['small_timer']>1 and s['score']==13, 'original shrink')
        frame=self.frame('small-at-opening.png')
        self.report['small_exit']={'before_exit':small,'frame':{'path':'small-at-opening.png',
            'sha256':frame['sha256'],'metadata':frame['metadata']},
            'scope':'The original mushroom mechanic sets ignore.blocks; no debugger edit.'}
        self.allow_small_walk=True
        try:self.precise(x=2)
        finally:self.allow_small_walk=False
        self.press('left',20,hold_ms=1,gap_ms=1)
        self.wait_for(lambda s:s['room']==36 and not s['small'] and not s['initializing'] and not s['window'] and
                      s['ego_view']==0 and s['ego_width']==6 and s['score']==14, 'original exit and regrowth')
        self.ready(); after=self.observe_clip('cave-outside')
        self.action('leave-cave',before,after,i,m)
        self.report['small_exit']['after_exit']=self.state()
        self.report['normal_leprechaun_complete']=True
        return self.capture()

    def capture(self):
        result = super().capture()
        result.update(format='fdisbull-agi-leprechaun-capture-1', preparation=self.preparation)
        result['source']['object_sha256'] = OBJECT_SHA256
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','backend','output'): parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args(); source=args.source.resolve(); root=args.output.resolve()
    checkout=Path(__file__).resolve().parents[2]
    require(root!=checkout and checkout not in root.parents and root!=source and source not in root.parents,
            'Keep inputs, states, databases and raw captures private')
    driver=None; report=None; primary=None
    def secondary(label, fn):
        nonlocal primary
        try: fn()
        except Exception as exc:
            if primary is None: primary=exc
            report.setdefault('persistence_errors',[]).append({'operation':label,'error':str(exc)})
    try:
        with native_game('kq1',source,root,args.backend.resolve(),fair_play=True) as (p,d,obs,restore,frame,report,game):
            driver=CaveRun(p,d,report,frame,source,root)
            try:
                capture=driver.route()
                (root/'capture.private.json').write_text(json.dumps(capture,indent=2)+'\n')
                report.update(normal_leprechaun_complete=True,final_state=driver.state())
            except BaseException as exc:
                primary=exc; report.update(normal_leprechaun_complete=False,error=str(exc))
                secondary('failure state',lambda:report.update(last_state=driver.state()))
                secondary('failure frame',lambda:frame('failure.png'))
            finally:
                if driver.trace_active: secondary('partial trace readback',driver.retain_trace_readback)
                if driver.trace_active: secondary('trace cleanup',driver.stop_trace)
                if driver.trace_receipt is not None:
                    secondary('trace persistence',lambda:(root/'partial-shield-trace.private.json').write_text(json.dumps(driver.trace_receipt,indent=2)+'\n'))
                if driver.watch: secondary('owned watch cleanup',driver.remove_watch)
                if driver.bp: secondary('print breakpoint cleanup',lambda:d.call('breakpoints.delete',{'breakpoint_id':driver.bp}))
    except BaseException as exc:
        if primary is None: primary=exc
        elif report is not None: report.setdefault('persistence_errors',[]).append({'operation':'native context cleanup','error':str(exc)})
    finally:
        if report is not None:
            errors=retain_private_evidence(driver,source,root,report)
            if primary is None and errors: primary=errors[0]
    if primary is not None: raise primary
    print(json.dumps({'complete':True,'state':report['final_state']}),flush=True)


if __name__=='__main__': main()
