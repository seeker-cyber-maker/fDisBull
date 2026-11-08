"""Replay an investigator-qualified private menu profile in an original DOS guest.

Profiles contain target-specific references and recipes, not inferred semantics.
No game names or addresses occur in this runner. It does not discover controls.
"""
from __future__ import annotations
import argparse
import base64
from hashlib import sha256
import json
import os
from pathlib import Path
from fdisbull.project import Project
from fdisbull.debugger import DebugSession
from fdisbull.dosbox_rpc import DOSBoxRPC
from probe import collect_episode


class ArgumentRPC(DOSBoxRPC):
    def __init__(self,*args,launch_arguments=(),**kwargs):
        self.arguments=list(launch_arguments)
        if len(self.arguments)>8 or any(not isinstance(x,str) or not x or len(x)>64 for x in self.arguments):
            raise ValueError('bounded explicit launch arguments required')
        super().__init__(*args,**kwargs)
    def call(self,method,params=None,**kwargs):
        if method=='session.start':
            params=dict(params);params['target']=dict(params['target'],arguments=self.arguments)
        return super().call(method,params,**kwargs)


class Session(DebugSession):
    def __init__(self,*args,launch_arguments=(),**kwargs):
        self.arguments=tuple(launch_arguments);super().__init__(*args,**kwargs)
    def _open_rpc(self,executable,game_dir):
        # Existing native argument channel; native validation is not bypassed.
        return ArgumentRPC(executable,game_dir,window=self.window,
                           on_spawn=self._spawn_callback,launch_arguments=self.arguments)


def replay(profile_path, game, backend, output):
    profile_path=Path(profile_path).resolve();cfg=json.loads(profile_path.read_text())
    if cfg.get('format')!='fdisbull-menu-experiment-profile-1':raise ValueError('wrong profile')
    game=Path(game).resolve();output=Path(output).absolute()
    if output.exists() or output.is_symlink() or not output.parent.is_dir():raise ValueError('new output required')
    if any((p/'.git').exists() or p.is_symlink() for p in (output.parent,*output.parent.parents)):
        raise ValueError('output must be private and outside Git')
    source=(game/cfg['executable']).resolve()
    if source.parent!=game or sha256(source.read_bytes()).hexdigest()!=cfg['source_sha256']:
        raise ValueError('original executable identity mismatch')
    if not 1<=len(cfg['steps'])<=64:raise ValueError('step budget')
    output.mkdir(mode=0o700)
    os.environ['FDISBULL_TARGET_STORE']=str(output/'target-objects')
    ordinal=0;calls={};results=[];checkpoints={};deadline=0
    def record(kind,payload):
        nonlocal ordinal
        ordinal+=1;path=output/f'{ordinal:04d}-{kind}.json'
        path.write_text(json.dumps(payload,sort_keys=True,indent=2));return str(path)
    with Project.create(output/'session.fdb',source,image='mz') as project:
        bundle=(profile_path.parent/cfg['scene_bundle']).resolve()
        imported=project.debug_import_scenes(bundle)
        contexts={name:imported['scene_map'][old] for name,old in cfg['contexts'].items()}
        with Session(project,backend,game,launch_arguments=cfg.get('arguments',[]),spatial_mode='physical') as d:
            nativecall=d.call
            def counted(method,params=None):
                calls[method]=calls.get(method,0)+1;return nativecall(method,params)
            d.call=counted
            record('runtime-identity',d.metadata)
            def advance(ms):
                if type(ms) is not int or not 1<=ms<=200000:raise ValueError('guest duration budget')
                r=d.run(guest_ms=ms,timeout_ms=15000,fast_forward=True,stop_on_hook=True)
                record('run',r)
                if r['outcome']!='guest_time' or r.get('hook_hits'):raise ValueError('unexpected guest stop')
            def guard(name):
                r=d.scene_assert(contexts[name],compact=True);return r['frame']
            def send(action,before):
                nonlocal deadline
                hold=action.get('hold_ms',80)
                if action['kind']=='click':
                    deadline=before['tick']+hold;f=before['frame']
                    return d.click(action['x'],action['y'],hold_ms=hold,mode_id=f['mode_id'],frame_id=f['frame_id'])
                if action['kind']=='press':return d.keyboard_press(action['key'],hold_ms=hold)
                if action['kind']=='type':return d.keyboard_type(action['text'],hold_ms=hold,gap_ms=60)
                raise ValueError('unknown input kind')
            def ready_input(tick):return tick>deadline
            def read_field(spec):
                if d.registers()['cpu_mode']!='real':raise ValueError('module-relative field needs real-mode qualification')
                offset=spec['module_offset'];length=spec['length']
                if type(offset) is not int or type(length) is not int or not 0<=offset<d.module_size or not 1<=length<=256 or offset+length>d.module_size:
                    raise ValueError('field outside original module')
                r=d.call('memory.read',{'address':{'space':'physical','offset':f'0x{d.runtime_base+offset:08X}'},'length':length,'view':'ram'})
                b=base64.b64decode(r['data_base64'],validate=True)
                if len(b)!=length or sha256(b).hexdigest()!=r['sha256']:raise ValueError('invalid field read')
                return b.hex()
            fields={k:(lambda v=v:read_field(v)) for k,v in cfg.get('fields',{}).items()}
            for step in cfg['steps']:
                op=step['op']
                if op=='run':advance(step['guest_ms'])
                elif op=='await':
                    for _ in range(40):
                        r=d.scene_check(contexts[step['context']],compact=True)
                        if r['status']=='matched':break
                        advance(250)
                    else:raise ValueError('qualified context not reached')
                elif op=='reference-input':
                    # Startup reference is historical; native probe is fresh.
                    from PIL import Image
                    image_path=(profile_path.parent/step['reference']).resolve()
                    if sha256(image_path.read_bytes()).hexdigest()!=step['reference_sha256']:raise ValueError('reference changed')
                    with Image.open(image_path) as im:
                        im=im.convert('RGB');points=[[x,y] for y,left,right in step['rows'] for x in range(left,right)]
                        expected=[list(im.getpixel(tuple(x))) for x in points]
                    f=d.frame_probe(points)
                    if [s['rgb'] for s in f['samples']]!=expected:raise ValueError('startup guard mismatch')
                    before={'frame':f,'tick':d.call('execution.timing')['guest_ticks']}
                    record('startup-input-intent',step);record('startup-input',send(step['action'],before))
                elif op=='save':checkpoints[step['name']]=d.save_state(step['name']+'.sav')['artifact']
                elif op=='restore':
                    record('restore',d.load_state(checkpoints[step['name']]));advance(250)
                elif op=='episode':
                    before_calls=dict(calls)
                    ep,res=collect_episode(d,contexts=contexts,expected_context=step['context'],
                        action=lambda before:send(step['action'],before),record=record,fields=fields,
                        slice_ms=100,samples=step.get('samples',20),idle_samples=3,
                        readiness_evidence=cfg['readiness_evidence'],input_ready=ready_input)
                    res['label']=step['label'];res['call_delta']={k:calls[k]-before_calls.get(k,0) for k in calls}
                    record('result',res);results.append(res)
                    if res['category']!=step['expected']:raise ValueError('observed effect differs from qualified profile')
                else:raise ValueError('unknown profile step')
    summary={'results':results,'native_calls':calls,'profile_sha256':sha256(profile_path.read_bytes()).hexdigest(),
             'qualification':'fresh original guest; caller-authored profile; no original memory/code edits',
             'complete':True}
    (output/'SUMMARY.json').write_text(json.dumps(summary,indent=2))
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('profile');p.add_argument('--game',required=True);p.add_argument('--backend',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();r=replay(a.profile,a.game,a.backend,a.output)
    print(json.dumps({'complete':r['complete'],'results':[(x['label'],x['category']) for x in r['results']]}))

if __name__=='__main__':main()
