"""Private native AGI spatial verification support; supply licensed originals.

This exact-edition adapter resolves a live writer before binding coordinates.
It does not infer a general AGI object layout from a launcher address.
"""
import base64
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import shutil

from fdisbull.project import Project
from fdisbull.runtime_observations import capture_observations

WRITER = bytes.fromhex('888709008bc65d5f5ec35657558bec83ec028b76088bde468a072ae42ef72e17')
PROFILES = {
    'kq1':('KQ1.COM','com','5ab189ebd9822739962767afe0113853e23797ef16dd4784d2dc93423934fb74',['escape','enter']),
    'pq1':('AGI','mz','29ddd3f3b91d65b6eade156608d7915e3c8b7f47701cb226ff119b717f3e8bd7',['enter']),
}


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def manifest(root): return {p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
def require(value, message):
    if not value: raise RuntimeError(message)


def read(session, address, size):
    result=session.call('memory.read',{'address':{'space':'linear','offset':f'0x{address:08X}'},'length':size})
    data=base64.b64decode(result['data_base64'],validate=True)
    require(len(data)==size,'Incomplete native read')
    return data


def find(session, signature):
    hits=[]; tail=b''
    for start in range(0,0xa0000,65536):
        data=tail+read(session,start,65536); offset=0
        while (offset:=data.find(signature,offset))>=0:
            hits.append(start-len(tail)+offset); offset+=1
        tail=data[-(len(signature)-1):]
    return hits


def eq(field, value): return {'field':field,'op':'eq','value':value}
def all_of(*items): return {'all':list(items)}


def scene(project, session, frame, room):
    yes={'constant':True}
    neutral={'all':[{'runtime_memory':{'binding':'actor','offset':33,'length':1,'hex':'00'}},
                    {'runtime_memory':{'binding':'variables','offset':15,'length':1,'hex':'00'}}]}
    requested={'runtime_memory':{'binding':'variables','offset':9,'length':1,'hex':bytes([room]).hex()}}
    # Static picture witnesses avoid the moving ego and animated flags in the
    # bounded routes below. A room number alone cannot identify its picture.
    points=([[110,108],[176,133],[190,153],[280,133],[318,123]] if room==1
            else [[20,68],[300,88],[200,148],[300,148]])
    displayed={'pixels':{'samples':session.frame_probe([[2,0],[12,0],[36,0],[64,0],[90,0],[2,10]]+points)['samples'],'tolerance':0}}
    document={'format':'fdisbull-scene-1','width':320,'height':200,'mode_id':frame['metadata']['mode_id'],
        'reference':frame['artifact'],'context':{'state':'qualified room','triggers':['source-bound original AGI frame']},
        'match':{'all':[requested,displayed]},'content':{'requested':requested,'displayed':displayed,'ready':neutral},
        'objects':[{'name':'original-input','area':{'rect':[1,1,2,2]},'point':[1,1],
          'context':{'state':'original keyboard action','triggers':['qualified room and neutral input']},
          'visible':yes,'ready':neutral,'enabled':yes,'action':{'kind':'press','key':'enter'},
          'outcome':yes,'outcome_phase':'state'}]}
    return project.debug_save_scene('spatial-origin',document,version=1)


def travel(scene_revision, observations, room, point):
    neutral=all_of(eq('direction',0),eq('control_direction',0))
    return {'format':'fdisbull-assisted-travel-1','kind':'within-room','scene_revision':scene_revision,
        'observations':observations,'context':all_of(eq('room',room),neutral),
        'writes':[{'binding':'actor','offset':off,'type':'u16','value':value} for off,value in zip((3,5),point)]
                 +[{'binding':'actor','offset':37,'type':'u16','set_bits':0x400}],
        'inputs':[],'until':all_of(eq('room',room),eq('x',point[0]),eq('y',point[1]),neutral),
        'destination':{'label':'qualified spatial anchor','room_field':'room','room_value':room},
        'provenance':{'qualification':'exact-edition live ego writer and original reposition refresh; diagnostic placement'},
        'guest_ms':2000,'slice_ms':50}


@contextmanager
def native_game(game_name, source, work, backend, *, fair_play=False):
    source=Path(source).resolve(); work=Path(work).resolve()
    require(not work.exists() and source not in work.parents and work not in source.parents,'Use a fresh private work directory')
    binary,image,digest,keys=PROFILES[game_name]
    require(sha(source/'AGI')==digest,'Unqualified AGI edition')
    original=manifest(source); work.mkdir(parents=True); game=work/'game'; shutil.copytree(source,game)
    report={'format':'fdisbull-native-spatial-trial-1','game':game_name,'source_manifest':original,
            'backend_sha256':sha(backend),'steps':{}}
    try:
      with Project.create(work/'private.fdb',game/binary,image=image) as p:
       with p.debugger(backend,game,version=1,fair_play=fair_play) as d:
        report['boot']=[d.run(guest_ms=5000,timeout_ms=15000,fast_forward=True)]
        for key in keys:
            d.keyboard_press(key,hold_ms=60,gap_ms=50)
            report['boot'].append(d.run(guest_ms=5000,timeout_ms=15000,fast_forward=True))
        hits=find(d,WRITER); require(len(hits)==1,'Live get.pos writer is ambiguous')
        linear=hits[0]
        bp=d.call('breakpoints.create',{'kind':'execution','once':False,'address':{'space':'segmented','segment':f'0x{linear>>4:04X}','offset':f'0x{linear&15:08X}'}})
        stopped=d.run(guest_ms=5000,timeout_ms=10000,fast_forward=True); regs=d.registers()
        require(stopped['outcome']=='breakpoint' and int(regs['segments']['cs'],16)*16+int(regs['instruction_pointer'],16)==linear,'Live writer did not stop')
        require(int(regs['general']['ecx'],16)==0,'get.pos selected another object')
        ds=int(regs['segments']['ds'],16)*16; actor=ds+int(regs['general']['edi'],16)
        require(int.from_bytes(read(d,ds+0x963,2),'little')+ds==actor,'Actor pointer witness disagrees')
        require(read(d,linear+0x2a,5)==bytes.fromhex('814d250004'),'Reposition refresh instruction differs')
        definitions=[dict(name='actor',address=actor,length=64,expected_hex=read(d,actor,3).hex(),provenance={'method':'live get.pos object0 DS:DI','writer_sha256':hashlib.sha256(WRITER).hexdigest(),'agi_sha256':digest}),
                     dict(name='variables',address=ds,length=265,expected_hex=read(d,ds,9).hex(),provenance={'method':'live get.pos variable array [BX+9]','agi_sha256':digest})]
        for item in definitions:d.bind_runtime_memory(**item)
        d.call('breakpoints.delete',{'breakpoint_id':bp['breakpoint_id']})
        d.run(guest_ms=250,timeout_ms=5000,fast_forward=True)
        observations={name:{'runtime_memory':{'binding':binding,'offset':offset,'type':kind}}
            for name,binding,offset,kind in [('x','actor',3,'u16'),('y','actor',5,'u16'),('direction','actor',33,'u8'),
                    ('control_direction','variables',15,'u8'),('room','variables',9,'u8'),('score','variables',12,'u8')]}
        report['resolution']={'writer_linear':hex(linear),'actor_linear':hex(actor),'ds_linear':hex(ds),'stop':stopped,'registers':regs,'definitions':definitions}
        report['initial']=capture_observations(d,observations)
        baseline=d.save_state('spatial-baseline.sav')
        def restore():
            d.load_state(baseline['artifact'])
            for item in definitions:d.bind_runtime_memory(**item)
            stop=d.run(guest_ms=100,timeout_ms=5000,fast_forward=True,stop_on_hook=True)
            require(stop['outcome']=='guest_time' and not stop.get('hook_hits'),'Restoration preparation interrupted')
        def frame(name):
            item=d.screenshot(name,hooks=False);p.debug_export(item['artifact'],work/name);return item
        yield p,d,observations,restore,frame,report,game
        report['copy_originals_unchanged']=all(sha(game/name)==digest for name,digest in original.items())
        require(report['copy_originals_unchanged'],'Private original files changed')
      report['copy_unchanged']=manifest(game)==original
      require(report['copy_unchanged'],'Private copy contains a changed or extra file after teardown')
      report['source_unchanged']=manifest(source)==original
      require(report['source_unchanged'],'Source game files changed')
    finally:
      (work/'result.json').write_text(json.dumps(report,indent=2,default=str)+'\n')
