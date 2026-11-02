"""Bounded ordinary-input KQ1 boundary water-walk and one-pixel control.

The technique is reported by speedrunners. Numeric waypoints are derived from
the owner's exact AGI 2.917 resources and must be qualified by this native run.
Never place game inputs, native states, raw captures or databases in Git.
"""
import argparse
from hashlib import sha256,md5
import json
from pathlib import Path

from examples.agi.spatial_trial import native_game,read,require,manifest
from examples.agi.verify_goat import GoatRun
from fdisbull.agi import load_logic
from fdisbull.agi_picture import extract_v2_resource,decode_picture,WIDTH

PUBLIC_ANCHORS={'AGI':(39424,'4771062c7f64bf64c185178613fd665a'),
    'KQ1.COM':(3121,'f579e8fb39209a321d575ebdc5f79014'),
    'LOGDIR':(315,'10ad66e2ecbd66951534a50aedcd0128'),
    'OBJECT':(331,'6eca02fa540337308529ff13e9e764aa')}


def adjacent_water(state,target_x):
    """Only the admitted neighboring baseline inside the river is a control."""
    return (target_x==153 and state['room']==41 and state['ego']['x']==153
            and 109<=state['ego']['y']<=150 and (state['in_water'] or state['swimming']>0))


class RiverRun(GoatRun):
    def __init__(self,*args,x=154,**kwargs):
        super().__init__(*args,**kwargs);require(x in (153,154),'Use the admitted edge or adjacent control')
        self.target_x=x;self.samples=[];self.river_observations=[]
        for n in (8,40,41,101):self.resources[n]=load_logic(self.source/'LOGDIR',self.source,n,profile='2.917')
        for name,(size,digest) in PUBLIC_ANCHORS.items():
            raw=(self.source/name).read_bytes();require(len(raw)==size and md5(raw).hexdigest()==digest,'Public TAS edition anchor differs: '+name)
        self.report['public_edition_anchors']={k:{'length':v[0],'md5':v[1]} for k,v in PUBLIC_ANCHORS.items()}
        item=extract_v2_resource(self.source/'PICDIR',self.source,41);picture=decode_picture(item['payload'])
        self.priority=bytes(picture['priority'])
        self.report['river_picture_sha256']=item['sha256']
        self.report['implementation_sha256']['examples/agi/verify_river_walk.py']=sha256(Path(__file__).read_bytes()).hexdigest()

    def state(self):
        state=super().state();flags=read(self.d,self.ds+0x109,32);v=read(self.d,self.ds+9,256)
        flag=lambda n:bool(flags[n//8]&(0x80>>(n%8)))
        table=int.from_bytes(read(self.d,self.ds+0x963,2),'little');actor=read(self.d,self.ds+table,43)
        state.update(in_water=flag(0),swimming=v[94],bridge_active=flag(21),troll_removed=flag(150),
            troll_paid=flag(151),ego_width=int.from_bytes(actor[26:28],'little'),ego_view=actor[7],
            dead=flag(63),edge=v[2])
        return state

    def snapshot(self,name):
        self.advance(50);s=self.state();item=self.frame(name+'.png')
        record={'id':name,'state':s,'frame':{'path':name+'.png','sha256':item['sha256'],'metadata':item['metadata']}}
        self.river_observations.append(record)
        print(json.dumps({'observation':name,'state':s}),flush=True)
        return record

    def align(self):
        self.move('right',axis='x',target=145)
        self.ready();self.press('right',20,hold_ms=1,gap_ms=1)
        end=self.guest_elapsed+3000
        while self.guest_elapsed<end:
            s=self.state()
            require(s['room']==41 and s['ego']['x']<=self.target_x,'Alignment crossed target or room boundary')
            if s['ego']['x']==self.target_x:
                self.neutral();s=self.state()
                require(s['ego']['x']==self.target_x,'Movement did not settle at exact border')
                return
            self.advance(10)
        raise RuntimeError('Precise edge alignment budget exhausted')

    def route(self):
        initial=self.state();require(initial['room']==1 and initial['score']==0,'Fresh opening required')
        self.move('right',room=8)
        self.move('right',axis='x',target=70)
        self.move('down',room=41)
        require(self.state()['ego_width']==6 and not self.state()['bridge_active'],'Unqualified ego width or active encounter')
        self.align();self.snapshot('river-before')
        self.press('down',20,hold_ms=1,gap_ms=1);end=self.guest_elapsed+20000
        while self.guest_elapsed<end:
            s=self.state();self.samples.append({'guest_ms':self.guest_elapsed,'state':s})
            if adjacent_water(s,self.target_x):
                self.snapshot('adjacent-enters-water')
                self.report['river_control_water_observed']=True
                return {'complete':True,'result':'adjacent-pixel-enters-water','trigger_state':s,'state':self.state()}
            require(not s['swimming'] and not s['in_water'] and not s['dead'],'Boundary candidate entered water or death')
            require(s['ego']['x']==self.target_x and s['ego_width']==6 and s['ego_view']==0,
                    'Boundary baseline or normal walking actor changed')
            if s['room']==40:
                require(self.target_x==154,'Adjacent control crossed without the expected water observation')
                self.ready();record=self.snapshot('river-crossed')
                final=record['state']
                require(final['room']==40 and final['ego']['x']==154 and final['ego_width']==6
                    and final['ego_view']==0 and not final['in_water'] and not final['swimming']
                    and not final['dead'] and not final['ego']['direction']
                    and not final['troll_removed'] and not final['troll_paid'] and final['score']==0,
                    'Final crossing state is unsafe, displaced or used troll resolution/payment')
                self.report['river_edge_crossing_complete']=True
                return {'complete':True,'result':'boundary-waterwalk','state':final}
            require(s['room']==41 and s['ego']['x']==self.target_x,'Unexpected crossing displacement')
            if 110<=s['ego']['y']<=150 and not any(o['id']=='river-middle' for o in self.river_observations):
                # Pause/stop for a stored frame over the visible river, then
                # continue with another ordinary down key selected from state.
                self.neutral();self.snapshot('river-middle');self.press('down',20,hold_ms=1,gap_ms=1)
            self.advance(50)
        raise RuntimeError('River crossing budget exhausted')

    def capture(self):
        result=super().capture()
        if hasattr(self,'river_observations'):
            result.update(river_observations=self.river_observations,samples=self.samples,target_x=self.target_x,
                picture_baseline_at_y120=list(self.priority[120*WIDTH+self.target_x:120*WIDTH+self.target_x+6]))
        return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','backend','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--x',type=int,choices=(153,154),default=154);args=parser.parse_args()
    source=args.source.resolve();root=args.output.resolve();checkout=Path(__file__).resolve().parents[2]
    require(root!=checkout and checkout not in root.parents,'Keep runtime data outside Git');driver=None
    try:
        with native_game('kq1',source,root,args.backend.resolve(),fair_play=True) as (p,d,obs,restore,frame,report,game):
            driver=RiverRun(p,d,report,frame,source,root,x=args.x)
            try:
                report['river_result']=driver.route();(root/'capture.private.json').write_text(json.dumps(driver.capture(),indent=2)+'\n')
                print(json.dumps(report['river_result']),flush=True)
            except Exception as exc:
                report['error']=str(exc);report['last_state']=driver.state();frame('failure.png');raise
            finally:
                if driver.bp:d.call('breakpoints.delete',{'breakpoint_id':driver.bp})
    finally:
        if driver:
            (root/'journal.private.json').write_text(json.dumps(driver.journal,indent=2)+'\n')
            (root/'partial-capture.private.json').write_text(json.dumps(driver.capture(),indent=2)+'\n')
            report=json.loads((root/'result.json').read_text());original=report['source_manifest']
            report['post_teardown_source_unchanged']=manifest(source)==original
            report['post_teardown_copy_unchanged']=manifest(root/'game')==original
            (root/'result.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
