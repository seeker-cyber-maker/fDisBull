"""Author ordinary keyboard inputs in stock JPC-RR; inspect original RAM read-only.

This is a TAS authoring assistant, not a playback dependency. Final movies must
be replayed from power-on using only the unmodified stock JAR and PCRunner.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys
import time
import traceback
import importlib

sys.path.insert(0, str(Path(__file__).with_name('authoring')))
from client import Author, AuthoringError

KEYS = dict(up=72, ne=73, right=77, se=81, down=80, sw=79,
            left=75, nw=71, center=76, enter=28, esc=1, f5=63)
DIRS = dict(up=1, ne=2, right=3, se=4, down=5, sw=6, left=7, nw=8)
DIRKEY = {v:k for k,v in DIRS.items()}
ALIASES=dict(home='nw',pageup='ne',pgup='ne',end='sw',pagedown='se',pgdn='se',
             upleft='nw',upright='ne',downleft='sw',downright='se')
LETTERS = dict(zip('qwertyuiop', range(16, 26)))
LETTERS.update(zip('asdfghjkl', range(30, 39)))
LETTERS.update(zip('zxcvbnm', range(44, 51)))
LETTERS.update(zip('1234567890', range(2, 12)))
LETTERS[' '] = 57


class Driver:
    def __init__(self, author: Author, out: Path, ds: int = 264752):
        self.a, self.out, self.ds = author, out, ds
        self.now = 0
        self.tail = 0
        self.log = open(out/'authoring-events.jsonl', 'x', encoding='utf-8')
        self.snap_n = 0

    def record(self, kind, **data):
        self.log.write(json.dumps(dict(kind=kind, **data))+'\n')
        self.log.flush()

    def load(self, path, mode='state'):
        r = self.a.command('load', path, mode)
        self.now = r['time_ns']
        self.tail = r.get('last_input_ns', 0)
        self.record('load', result=r)
        return self.state()

    def state(self):
        vflags = self.a.read(self.ds+9, 310)
        ptrs = self.a.read(self.ds+0x963, 10)
        actor_ptr = int.from_bytes(ptrs[:2], 'little')
        inv_start = int.from_bytes(ptrs[6:8], 'little')
        inv_end = int.from_bytes(ptrs[8:10], 'little')
        if not (0 < actor_ptr < 0x10000 and inv_end-inv_start == 81):
            raise RuntimeError('Original AGI data layout is not qualified at this point')
        actor_records = self.a.read(self.ds+actor_ptr, 43*4)
        actor = actor_records[:43]
        actors=[]
        for index in range(4):
            record=actor_records[index*43:(index+1)*43]
            af=int.from_bytes(record[37:39],'little')
            actors.append(dict(x=int.from_bytes(record[3:5],'little'),
                               y=int.from_bytes(record[5:7],'little'),view=record[7],
                               loop=record[10],cel=record[14],
                               width=int.from_bytes(record[26:28],'little'),
                               direction=record[33],flags_word=af,
                               drawn=bool(af&1),updating=bool(af&0x10),cycling=bool(af&0x20),
                               ignore_objects=bool(af&0x200),ignore_blocks=bool(af&2)))
        inventory = self.a.read(self.ds+inv_start, 81)
        flags = [n for n in range(256) if vflags[256+n//8] & (0x80>>(n%8))]
        s = dict(time_ns=self.now, room=vflags[0], previous_room=vflags[1],
                 score=vflags[3], control=vflags[6], speed=vflags[10],
                 x=int.from_bytes(actor[3:5], 'little'),
                 y=int.from_bytes(actor[5:7], 'little'),
                 view=actor[7], loop=actor[10], cel=actor[14],
                 width=int.from_bytes(actor[26:28], 'little'),
                 step=actor[30], direction=actor[33],
                 drawn=bool(int.from_bytes(actor[37:39],'little')&1),
                 player_control=bool(int.from_bytes(vflags[0x139-9:0x13b-9],'little')),
                 window=int.from_bytes(self.a.read(self.ds+0xd15,2),'little'),
                 items=[n for n in range(27) if inventory[n*3+2] == 255],
                 flags=flags, vars=list(vflags[:256]), actors=actors,actor_pointer=actor_ptr)
        return s

    @staticmethod
    def short(s):
        return {k:v for k,v in s.items() if k not in ('vars','flags','actors','actor_pointer')}

    def advance(self, ns):
        target = self.now+int(ns)
        while self.now < target:
            r = self.a.run_until(target)
            self.now = r['time_ns']
            if r['reason'] not in ('target', 'host_budget'):
                raise RuntimeError(f'Native execution stopped: {r}')
        return self.state()

    def edge(self, code, earliest=None):
        r = self.a.command('keyedge', code, max(self.now, self.tail if earliest is None else earliest))
        self.tail = r['scheduled_ns']
        self.record('keyedge', result=r)
        return self.tail

    def pulse(self, key, hold_ns=666_666, gap_ns=666_666):
        key=ALIASES.get(key,key)
        code = KEYS.get(key, key)
        down = self.edge(code, max(self.now, self.tail+gap_ns))
        up = self.edge(code, down+hold_ns)
        return dict(key=key, down_ns=down, up_ns=up)

    def type_text(self, text, submit=True):
        events = []
        for char in text.lower():
            events.append(self.pulse(LETTERS[char]))
        if submit:
            events.append(self.pulse('enter'))
        self.advance(max(0, self.tail-self.now)+1_000_000)
        return dict(text=text, submit=submit, events=events, state=self.state())

    def wait(self, predicate, max_ns=2_000_000_000, quantum_ns=200_000,
             dismiss=False, allow_failure=False):
        start = self.now
        s = self.state()
        while not predicate(s):
            if 63 in s['flags'] and not allow_failure:
                raise RuntimeError('Original game failure flag63 is set')
            if self.now-start >= max_ns:
                raise TimeoutError(f'Condition not reached: {self.short(s)}')
            if dismiss and s['window']:
                s = self.dismiss_window('wait-output',stop_after=True)
            else:
                s = self.advance(quantum_ns)
        return s

    def direction(self, key):
        key=ALIASES.get(key,key)
        s = self.state()
        want = DIRS[key]
        for _ in range(8):
            if s['window']:
                s=self.dismiss_window('direction-output',stop_after=True)
                continue
            if s['control']==want:return s
            self.pulse(key)
            s = self.wait(lambda s:s['control']==want or s['window']>0, max_ns=500_000_000,
                          quantum_ns=100_000)
        raise RuntimeError('Direction did not settle after original output')

    def stop(self):
        s = self.state()
        if s['window']:
            self.pulse('center')
            for _ in range(8):
                s=self.dismiss_window('navigation-output',stop_after=True)
                if not s['window']:break
            else:raise RuntimeError('Original entry output did not settle')
        if s['control'] in DIRKEY:
            self.pulse('center')
            s = self.wait(lambda s:s['control']==0 and s['direction']==0, max_ns=500_000_000,
                          quantum_ns=50_000,dismiss=True)
        elif s['direction']:
            s = self.wait(lambda s:s['control']==0 and s['direction']==0,
                          max_ns=500_000_000, quantum_ns=50_000,dismiss=True)
        if self.tail > self.now:
            s = self.advance(self.tail-self.now)
        return s

    def pulse_at(self, key, down_ns):
        down=self.edge(KEYS[key],down_ns)
        up=self.edge(KEYS[key],down+666_660)
        return down,up

    def walk_axis(self, dx, dy, count, max_trials=18):
        self.active_leg_start=None
        try:
            return self._walk_axis_trials(dx,dy,count,max_trials)
        except Exception as exc:
            if self.active_leg_start is not None:
                restore_path=self.active_leg_start
                try:
                    self.record('movement_exception_rollback',error=str(exc),
                                checkpoint=restore_path,state=self.state())
                    self.snapshot(f'leg-{self.leg_serial:04d}-exception')
                    self.checkpoint(f'leg-{self.leg_serial:04d}-exception')
                finally:
                    self.load(restore_path)
            raise
        finally:
            self.active_leg_start=None

    def _walk_axis_trials(self, dx, dy, count, max_trials=18):
        """Find an ordinary direction/center segment by native rerecording.

        A duration is accepted only at a neutral original-game endpoint. Failed
        candidate timings are retained in authoring-events, then restored using
        the emulator's own checkpoint. No coordinate or game-memory writes.
        """
        start=self.stop()
        if start['window']:raise RuntimeError('Walking requested with original modal open')
        direction={(0,-1):'up',(1,-1):'ne',(1,0):'right',(1,1):'se',
                   (0,1):'down',(-1,1):'sw',(-1,0):'left',(-1,-1):'nw'}[(dx,dy)]
        target=(start['x']+dx*count,start['y']+dy*count)
        serial=getattr(self,'leg_serial',0)+1;self.leg_serial=serial
        label=f'leg-{serial:04d}-start'
        path=self.checkpoint(label)
        self.active_leg_start=path
        period=getattr(self,'periods',{}).get((start['room'],start['view'],start['speed']),
                                            1_550_000 if start['speed']==0 else 110_000_000)
        # A direction arrives through the game's original 20-Hz BIOS poll.
        # Keypad center is the game's normal immediate stop event. Branch only
        # after the direction has actually been imported, before fitting the
        # center-key time. Both input types remain ordinary stock KEYEDGEs.
        self.direction(direction)
        moving=self.state()
        origin_ns=self.now
        moving_path=self.checkpoint(label+'-moving')
        already=((moving['x']-start['x'])*dx if dx else (moving['y']-start['y'])*dy)
        duration=max(0,int((count-already-1)*period))
        lo=0;hi=None;trials=[]
        for trial in range(max_trials):
            if trial:self.load(moving_path)
            windows_before=getattr(self,'dismiss_count',0)
            last,last_release=self.pulse_at('center',max(origin_ns+duration,self.tail+666_660))
            # Both input edges have been delivered before scoring the endpoint.
            self.advance(max(0,last_release+3_000_000-self.now))
            s=self.wait(lambda s:s['control']==0 and s['direction']==0,
                        max_ns=1_000_000_000,quantum_ns=200_000,allow_failure=True,dismiss=True)
            # Verify no queued step remains. This does not alter a stopped ego.
            previous=(s['x'],s['y']);s=self.advance(2_000_000)
            neutral=s['control']==0 and s['direction']==0 and (s['x'],s['y'])==previous
            if not set(start['items']).issubset(s['items']):
                raise RuntimeError('Carried inventory was lost during a walking trial')
            progress=((s['x']-start['x'])*dx if dx else (s['y']-start['y'])*dy)
            record=dict(trial=trial,duration_ns=duration,movement_origin_ns=origin_ns,
                        last_down_ns=last,progress=progress,neutral=neutral,
                        state=self.short(s),target=target)
            trials.append(record);self.record('movement_trial',**record)
            if neutral and (s['x'],s['y'])==target and s['room']==start['room'] and 63 not in s['flags']:
                self.periods=getattr(self,'periods',{})
                if count-already>3:
                    self.periods[(start['room'],start['view'],start['speed'])]=max(100_000,(last-origin_ns)/(count-already-1))
                return dict(start=self.short(start),target=target,trials=trials,state=s)
            if (neutral and s['room']==start['room'] and 63 not in s['flags']
                and getattr(self,'dismiss_count',0)>windows_before and 0<progress<count
                and s['x']==start['x']+dx*progress and s['y']==start['y']+dy*progress):
                self.record('movement_interrupted_by_output',start=self.short(start),
                            intended_target=target,partial_endpoint=self.short(s))
                return dict(start=self.short(start),target=target,trials=trials,
                            interrupted_by_output=True,goal_reached=False,state=s)
            if hi is None and len(trials)>=3 and len({(t['state']['room'],t['state']['x'],t['state']['y']) for t in trials[-3:]})==1 and trials[-1]['duration_ns']-trials[-3]['duration_ns']>10_000_000:
                break  # Increasing key duration cannot pass this observed block.
            if s['room'] != start['room'] or 63 in s['flags']:
                # An overshooting trial may cross a transition or hazard. It is
                # not accepted; the next trial reloads the exact earlier state.
                hi=duration if hi is None else min(hi,duration)
            elif progress < count:
                lo=max(lo,duration)
            else:
                hi=duration if hi is None else min(hi,duration)
            if hi is not None and hi-lo < 66_666:break
            corrected=duration+int((count-progress)*period)
            if hi is None:
                duration=max(duration+100_000,corrected)
            else:
                duration=(lo+hi)//2
        self.snapshot(f'leg-{serial:04d}-failed')
        self.checkpoint(f'leg-{serial:04d}-failed')
        self.load(path)
        self.active_leg_start=None
        raise RuntimeError(f'No verified timing to {target}; trials={trials}')

    def walk_to(self,x=None,y=None):
        s=self.stop();x=s['x'] if x is None else x;y=s['y'] if y is None else y
        results=[]
        for _ in range(16):
            s=self.state();dx=x-s['x'];dy=y-s['y']
            if dx==0 and dy==0:return dict(legs=results,state=s)
            sx=(dx>0)-(dx<0);sy=(dy>0)-(dy<0)
            count=min(abs(dx),abs(dy)) if dx and dy else max(abs(dx),abs(dy))
            results.append(self.walk_axis(sx,sy,count))
        raise RuntimeError('Coordinate decomposition did not converge')

    def walk_until_room(self,key,room,max_ns=3_000_000_000):
        key=ALIASES.get(key,key)
        start=self.state()
        if start['room']==room:
            self.wait(lambda s:s['room']==room and s['drawn'] and 5 not in s['flags'],
                      max_ns=1_000_000_000,quantum_ns=200_000,dismiss=True)
            s=self.stop()
            if s['room']!=room or not s['drawn'] or 5 in s['flags']:
                raise RuntimeError('Target room did not remain initialized')
            return s
        self.direction(key);begin=self.now
        while True:
            s=self.state()
            if s['room']==room:break
            if 63 in s['flags']:raise RuntimeError('Original failure during room traversal')
            if self.now-begin>max_ns:raise TimeoutError(f'Room {room} not reached from {start["room"]}')
            if s['window']:
                self.dismiss_window('traversal-output',stop_after=True)
                self.direction(key)
            elif s['player_control'] and s['control']!=DIRS[key]:self.direction(key)
            else:self.advance(200_000)
        # new.room changes v0 before loading/drawing/repositioning the actor.
        s=self.wait(lambda s:s['room']==room and s['drawn'] and 5 not in s['flags'],max_ns=1_000_000_000,quantum_ns=200_000,dismiss=True)
        s=self.stop()
        if s['room']!=room or not s['drawn'] or 5 in s['flags']:
            raise RuntimeError('Target room did not remain initialized')
        self.record('room_transition',start=self.short(start),end=self.short(s),key=key)
        return s

    def plan_walk_to(self,x,y,step_id=None):
        from route_support import Planner
        planner=getattr(self,'planner',None)
        if planner is None:self.planner=planner=Planner()
        s=self.stop()
        if step_id is None:
            proposal=planner.plan(s['room'],(s['x'],s['y']),(x,y),width=s['width'])
        else:
            proposal=planner.plan_step(step_id,(s['x'],s['y']),width=s['width'])
        self.record('offline_path_candidate',proposal=proposal)
        if proposal['status']!='found':
            raise RuntimeError(f'No qualified static path candidate: {proposal["status"]}')
        results=[]
        for point in proposal['waypoints']:
            results.append(self.walk_to(x=point[0],y=point[1]))
        return dict(proposal=proposal,legs=results,state=self.state())

    def dismiss_window(self,label,stop_after=False):
        s=self.state()
        if not s['window']:return s
        if 63 in s['flags']:raise RuntimeError('Retain original failure output')
        self.dismiss_count=getattr(self,'dismiss_count',0)+1
        # Give original drawing and the native VGA refresh time to complete.
        # This authoring choice costs game time and is retained in the movie.
        self.advance(30_000_000)
        self.snapshot(label)
        self.pulse('enter')
        deadline=self.now+100_000_000
        while self.now<deadline:
            s=self.advance(50_000)
            if not s['window']:
                if stop_after:
                    self.pulse('center')
                    s=self.advance(max(0,self.tail-self.now)+2_000_000)
                return s
        # A second original print can open before the polling reader observes
        # the intervening zero depth. The caller captures that output anew.
        return self.state()

    def await_contract(self,step_id,max_ns=5_000_000_000):
        from route_support import check_step
        begin=self.now;windows=0
        while True:
            s=self.state();check=check_step(step_id,s)
            if check['complete'] and s['drawn'] and all(f not in s['flags'] for f in (2,4,5)):
                # State can commit before its print starts (HI sets f22 first).
                # Require the original parser-cycle flags to clear and observe
                # a stable continuation before treating the interaction as done.
                s=self.advance(3_000_000);check=check_step(step_id,s)
                if check['complete'] and s['drawn'] and all(f not in s['flags'] for f in (2,4,5)):
                    self.record('verified_effect',step_id=step_id,check=check,state=s)
                    return s
            if 63 in s['flags']:raise RuntimeError(f'Original failure during step{step_id}')
            if self.now-begin>max_ns:
                raise TimeoutError(f'Step{step_id} effects unresolved: {check}')
            if check['unknown']:
                raise RuntimeError(f'Step{step_id} requires observations not yet qualified: {check["unknown"]}')
            if s['window']:
                windows+=1
                self.dismiss_window(f'step-{step_id:03d}-output-{windows:02d}')
            else:
                self.advance(500_000)

    def run_candidate(self,start,end):
        from route_support import load_candidate,check_step,CONTRACTS,thief_decision
        steps=load_candidate()['steps'];results=[]
        for step in steps[start:end+1]:
            sid=step['id'];kind=step['kind'];args=step['args'];before=self.state()
            checkpoint=self.checkpoint(f'step-{sid:03d}-start')
            self.record('candidate_step_start',step=step,state=before)
            try:
                if sid in CONTRACTS and kind not in ('wait_effect','stop_movement'):
                    pre=check_step(sid,before,'pre')
                    if not pre['complete']:
                        raise RuntimeError(f'Step{sid} prerequisite is unresolved: {pre}')
                if kind=='walk_to':result=self.walk_to(**args)
                elif kind=='walk_until_room':result=self.walk_until_room(**args)
                elif kind=='plan_walk_to':result=self.plan_walk_to(**args,step_id=sid)
                elif kind=='type_and_submit':
                    self.type_text(args['text']);result=self.await_contract(sid)
                elif kind=='pretype':
                    result=self.type_text(args['text'],submit=False)
                    self.record('pretype_unobserved_buffer',step_id=sid,text=args['text'],
                                claim='Physical key edges recorded; input-line RAM field not recovered')
                elif kind=='submit_pretyped':
                    self.pulse('enter');result=self.await_contract(sid)
                elif kind=='wait_effect':
                    if sid==80:
                        phase=self.wait(lambda s:s['room']==73 and (98 in s['flags'] or s['view'] in (103,104,105)),max_ns=1_000_000_000)
                        self.record('landing_phase_observed',state=phase)
                    result=self.await_contract(sid)
                elif kind=='stop_movement':
                    self.stop();result=self.await_contract(sid) if sid in CONTRACTS else self.state()
                elif kind=='ordinary_key_pulse':
                    if sid==79:
                        self.direction('up');result=self.wait(lambda s:s['room']==73,max_ns=3_000_000_000)
                    elif sid==102:
                        self.direction('down')
                        self.wait(lambda s:s['window']>0,max_ns=500_000_000)
                        self.pulse('center')
                        self.dismiss_window('step-102-output-01',stop_after=True)
                        self.stop();result=self.await_contract(sid)
                    elif sid==116:
                        self.direction('left');result=self.wait(lambda s:s['room']==36,max_ns=3_000_000_000)
                    elif sid==214:
                        self.direction('down');result=self.await_contract(sid)
                    else:raise ValueError(f'Unqualified pulse step{sid}')
                elif kind=='conditional_authoring_loop':
                    attempts=[]
                    for attempt in range(args['attempt_budget']):
                        decision=thief_decision(self.state());attempts.append(decision)
                        self.record('thief_authoring_decision',step_id=sid,attempt=attempt,decision=decision)
                        if decision['action']=='continue_candidate':break
                        if decision['action']!='consider_ordinary_retreat':
                            raise RuntimeError(f'Thief state unresolved: {decision}')
                        self.walk_to(x=94,y=160);self.walk_until_room('down',67)
                        self.walk_to(x=120,y=41);self.walk_until_room('up',68)
                    else:raise RuntimeError('Thief retry budget exhausted')
                    result=self.await_contract(sid)
                else:raise ValueError(f'Unqualified candidate kind {kind}')
                final=self.state()
                if 63 in final['flags']:raise RuntimeError('Original failure at step endpoint')
                self.record('candidate_step_complete',step_id=sid,state=final)
                results.append(dict(step_id=sid,state=self.short(final)))
                print(json.dumps({'step':sid,'complete':True,'state':self.short(final)}),flush=True)
            except Exception as exc:
                try:
                    self.record('candidate_step_failed',step_id=sid,error=str(exc),state=self.state())
                    self.snapshot(f'step-{sid:03d}-failed')
                    self.checkpoint(f'step-{sid:03d}-failed')
                finally:
                    self.load(checkpoint)
                raise
        return results

    def sample_motion(self, key, duration_ns, quantum_ns=100_000):
        self.direction(key)
        finish = self.now+duration_ns
        records=[]; last=None
        while self.now < finish:
            s=self.advance(quantum_ns)
            signature=(s['room'],s['x'],s['y'],s['control'],s['direction'])
            if signature != last:
                records.append(self.short(s));last=signature
        return records

    def checkpoint(self, label):
        p=self.out/(label+'.jrsr')
        version=1
        while p.exists():
            p=self.out/(label+f'-v{version}'+'.jrsr');version+=1
        result=self.a.command('save_state',p)
        self.record('checkpoint',result=result,state=self.state())
        return str(p)

    def snapshot(self, label):
        self.snap_n += 1
        p=self.out/(label+'.png')
        version=1
        while p.exists():
            p=self.out/(label+f'-v{version}'+'.png');version+=1
        return self.a.command('snapshot', p)

    def execute(self, action):
        kind=action['kind'];args=action.get('args',{})
        if kind=='state': return self.state()
        if kind=='advance': return self.advance(**args)
        if kind=='pulse': return self.pulse(**args)
        if kind=='type': return self.type_text(**args)
        if kind=='stop': return self.stop()
        if kind=='direction': return self.direction(**args)
        if kind=='walk_to': return self.walk_to(**args)
        if kind=='walk_until_room': return self.walk_until_room(**args)
        if kind=='plan_walk_to': return self.plan_walk_to(**args)
        if kind=='run_candidate': return self.run_candidate(**args)
        if kind=='await_contract': return self.await_contract(**args)
        if kind=='wait_checks':
            from route_support import evaluate
            return self.wait(lambda s:evaluate(args['checks'],s)['complete'],
                             max_ns=args.get('max_ns',2_000_000_000),
                             quantum_ns=args.get('quantum_ns',200_000))
        if kind=='sample_motion': return self.sample_motion(**args)
        if kind=='snapshot': return self.snapshot(**args)
        if kind=='checkpoint': return self.checkpoint(**args)
        if kind=='load': return self.load(**args)
        if kind=='refresh':
            if 'route_support' in sys.modules:importlib.reload(sys.modules['route_support'])
            module=importlib.import_module('drive_route')
            module=importlib.reload(module)
            self.__class__=module.Driver
            return {'refreshed':True,'time_ns':self.now}
        if kind=='header': return self.a.command('header',args['key'],*args.get('fields',[]))
        if kind=='save_movie': return self.a.command('save_movie',self.out/(args['label']+'.jrsr'))
        if kind=='boundary_smoke':
            before=self.a.command('info')['time_ns']
            rejected=False
            try:self.a.read(0xa0000,1)
            except AuthoringError:rejected=True
            self.state()
            after=self.a.command('info')['time_ns']
            return dict(vga_read_rejected=rejected,before_ns=before,after_ns=after)
        if kind=='quit': return {'quit':True}
        raise ValueError(f'Unknown action {kind}')


def serve(args):
    out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    requests=out/'requests';requests.mkdir()
    with Author(args.jar,args.library,out/'native.log') as a:
        d=Driver(a,out,args.ds)
        initial=d.load(args.state,args.mode)
        (out/'ready.json').write_text(json.dumps(initial,indent=2)+'\n')
        print(json.dumps({'ready':str(out),'state':d.short(initial)}),flush=True)
        done=set()
        while True:
            pending=[p for p in sorted(requests.glob('*.json')) if p.name not in done]
            if not pending:
                time.sleep(.05);continue
            for p in pending:
                request=json.loads(p.read_text());results=[];ok=True;error=None
                try:
                    for action in request['actions']:
                        before=d.state();result=d.execute(action)
                        d.record('action',action=action,before=before,result=result)
                        results.append(result)
                except Exception as exc:
                    ok=False;error=dict(type=type(exc).__name__,message=str(exc),traceback=traceback.format_exc())
                    d.record('error',error=error)
                final=d.state()
                response=dict(ok=ok,request=p.name,results=results,error=error,state=final)
                path=out/(p.stem+'.response.json');tmp=path.with_suffix('.tmp')
                tmp.write_text(json.dumps(response,indent=2)+'\n');tmp.rename(path)
                done.add(p.name)
                print(json.dumps({'request':p.name,'ok':ok,'state':d.short(final),'error':error}),flush=True)
                if any(x['kind']=='quit' for x in request['actions']):
                    d.log.close();return


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--jar',required=True);p.add_argument('--library',required=True)
    p.add_argument('--state',required=True);p.add_argument('--mode',default='state',choices=['movie','state'])
    p.add_argument('--out',required=True);p.add_argument('--ds',type=int,default=264752)
    serve(p.parse_args())
