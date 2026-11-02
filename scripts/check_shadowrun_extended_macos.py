#!/usr/bin/env python3
"""Full-state native comparison for source-prepared extended arena routes.

The three assisted input schedules and source checkpoints are read from
hash-bound original receipts. Original RAM supplies expected outputs only.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.game_il import GameMachine, author_program, canonical
from fdisbull.shadowrun_assisted_arena import assisted_arena_from_capture
from fdisbull.shadowrun_menu import SOURCE as MENU_SOURCE
from fdisbull.shadowrun_macos import captured_courtyard_from_capture
from fdisbull.shadowrun_replay import _read_rom
from check_shadowrun_macos import Native


def sha(b): return hashlib.sha256(b).hexdigest()


# The ROM/core and these private source receipts identify previously retained
# original runs. They contain no runtime inputs or game bytes in this script.
FIXTURES = {
 'moving-long-original-01': ('79b3f619540c6bfee1708b2c2b9692333820c49431e220d4ed006dc84fb2785b','ffa86ee7286c0ec90c4bbea71000a76bbce4ab24aef7ba6c5730ee71d8045fbe'),
 'moving-repeated-original-01': ('bf46c5d63d61eae97061502167008a3eb1c0d52bb9d7291d920859c89f06e4b1','5af7e095ef74563403c54e4d2b6ec81dde13d7998e0aeed220b7e429da7fecf6'),
 'retreat-original-01': ('0f3c88c9f6d62f39a5b01176c7e166a33b0e70f513af564e6a4e8969deaf1e70','7a94567c364850eddcb6ec494b107274a34fd7a6c0bda30f8b2db91a1379e7ff'),
 'retreat-boundary-original-02': ('9be4d432e2298a745cd55eb65c2636d23ca0822893c4946a1bbef6498941691c','2fb8bfee1dc1ebb6c1135aca90fa8db1bccb50babb1bc28cce9e0a430f2df15a'),
 'retreat-relaunch-original-01': ('21ec6fc5774c90bbd2b3ba5821fc7111bda2bc806e9310e5cdad6aafd1b45d27','f6d365ad0207af012f8c945e2f7de844ddd69cd380382920500ab5ec604c729c'),
 'offense-original-01': ('06128c7812c9fcbbc5e1e7b52aa698375225d160e6af0dd3184a499c3e910efe','399edebe3ee9e7d425fddc6868ee067a762f071ee18127bc76eabef41aecc7c7'),
 'down-long-original-01': ('1849286cde8036a9d9fd058850cdf0381af4bd74eff894bb64b92cea9093c035','1bf6d4b52212bea68233c595ad4b45db0e45361d46010f8d816f6b51f5feecfd'),
}
PATCH_SHA = 'f9d2f3ceea5eb835991e2d6fb96da4299d97e53504a7651fd939ef71c97df5c5'
BUTTONS = {'UP':1, 'DOWN':2, 'LEFT':4, 'RIGHT':8, 'B':16, 'A':64, 'START':128}


def menu_compare(path):
    native = ctypes.CDLL(str(path)); native.shadowrun_menu_tick.argtypes = []
    native.shadowrun_menu_tick.restype = None
    names = ('phase','cursor','preview','archetype','supported','pressed')
    fields = {n: (ctypes.c_uint if n == 'pressed' else ctypes.c_ubyte).in_dll(native, 'shadowrun_menu_' + n)
              for n in names}
    m = GameMachine(author_program(MENU_SOURCE.read_text()))
    flags = (0x100,0x200,0x1000,0x2000,0x4000,0x8000)
    cases = 0
    for phase in (0,1):
        for cursor in range(2 if phase == 0 else 3):
            for bits in range(1 << len(flags)):
                pressed = sum(flag for i,flag in enumerate(flags) if bits & (1 << i))
                values = {'phase':phase,'cursor':cursor,'preview':cursor,'archetype':0,'supported':0,'pressed':pressed}
                for n,v in values.items(): fields[n].value = v
                m.set_state({'shadowrun_menu_' + n:v for n,v in values.items()})
                m.call('shadowrun_menu_tick'); native.shadowrun_menu_tick(); s = m.snapshot()
                for n in names:
                    if fields[n].value != s['shadowrun_menu_' + n]: raise AssertionError(('menu',phase,cursor,pressed,n))
                cases += 1
    # Source transition boundaries must remain explicit, with no second transition.
    for phase in (2,3):
        for n,v in {'phase':phase,'cursor':0,'preview':0,'archetype':0,'supported':1,'pressed':0x4000}.items(): fields[n].value=v
        native.shadowrun_menu_tick()
        if fields['phase'].value != phase or fields['supported'].value: raise AssertionError('menu boundary')
    return {'cases':cases,'source_boundary_cases':2,'library_sha256':sha(path.read_bytes()),
            'source_sha256':sha(MENU_SOURCE.read_bytes()),'scope':'compiled menu C versus independent GameMachine; rendering and prepared-arena switch separate'}


def frontend_compare(executable, app_receipt, rom, capture, program_sha, library, output, admit, model):
    raw=app_receipt.read_bytes();rec=json.loads(raw)
    frontend_source=ROOT/'src/fdisbull/game_sources/shadowrun_macos_app.m'
    if (rec['program_sha256']!=program_sha or rec['frontend_sha256']!=sha(executable.read_bytes()) or
        rec['frontend_source_sha256']!=sha(frontend_source.read_bytes()) or
        rec['native_core']['dylib_sha256']!=sha(library.read_bytes()) or rec['preset']!='moving'):
        raise ValueError('frontend receipt mismatch')
    def run(label, edges, extra=(), expected_rc=0):
        # Every native-generated image has its own fresh external admission.
        admission=subprocess.run([sys.executable,str(admit),'--path',str(output),'--expected-bytes','8388608',
                                  '--destination-reserve-bytes','20000000000'],capture_output=True,text=True,env=os.environ.copy())
        if admission.returncode or not json.loads(admission.stdout)['admitted']:
            raise RuntimeError('storage admission refused frontend snapshot')
        image=output/(label+'.png')
        cmd=[str(executable),'--rom',str(rom),'--snapshot',str(image),'--menu-edges',edges,*extra]
        result=subprocess.run(cmd,capture_output=True,text=True,env=os.environ.copy(),timeout=120)
        if result.returncode!=expected_rc:raise AssertionError((label,result.returncode,result.stderr))
        if expected_rc:
            if image.exists():raise AssertionError('refused menu action wrote an image')
            return None
        if not image.is_file():raise AssertionError('missing frontend snapshot')
        data=json.loads(result.stdout)
        if data['stopped']:raise AssertionError((label,'frontend stopped'))
        return data
    initial=run('menu-main','')
    load=run('menu-load','512,4096')
    archetype=run('menu-archetype','16384,256')
    chosen=run('menu-initializer-boundary','16384,16384')
    expected=[(initial,0,0),(load,3,1),(archetype,1,2),(chosen,2,0)]
    for data,phase,cursor in expected:
        if (data['menu_phase'],data['menu_cursor'],data['arena_entered'],data['arena_ticks'])!=(phase,cursor,False,0):
            raise AssertionError(('frontend menu gate',phase,cursor,data))
        s=model.snapshot()
        if (data['hp'],data['player_x'],data['player_y'])!=(s['shadowrun_arena_hp'],s['shadowrun_player_x'],s['shadowrun_player_y']):
            raise AssertionError('menu changed prepared arena state')
    run('menu-refused-step','16384,16384',('--pads','4'),expected_rc=2)
    m=assisted_arena_from_capture(rom.read_bytes(),capture, moving=True)
    m.call('shadowrun_arena_frame',0);m.call('shadowrun_arena_frame',4);expected_state=m.snapshot()
    timings=[];hashes=[]
    for i in range(5):
        label='prepared-render-'+str(i)
        data=run(label,'16384,16384',('--enter-prepared','--pads','0,4','--render-benchmark','120'))
        if (data['menu_phase'],data['arena_entered'],data['arena_ticks'])!=(2,True,2):
            raise AssertionError(('explicit prepared entry',data))
        if (data['hp'],data['player_x'],data['player_y'])!=(expected_state['shadowrun_arena_hp'],expected_state['shadowrun_player_x'],expected_state['shadowrun_player_y']):
            raise AssertionError('prepared frontend differs from model')
        if data['render_iterations']!=120:raise AssertionError('render budget mismatch')
        timings.append(data['render_ns']);hashes.append(sha((output/(label+'.png')).read_bytes()))
    if len(set(hashes))!=1:raise AssertionError('stored-state renders differ')
    return {'app_receipt_sha256':sha(raw),'frontend_sha256':sha(executable.read_bytes()),
            'menu_boundary_and_pause_cases':4,'premature_arena_step_refused':True,
            'prepared_entry_ticks':2,'render_repeats':5,'draws_each':120,'render_total_ns_each':timings,
            'rendered_image_sha256':hashes[0],
            'scope':'offscreen stored-state draw; not onscreen presentation, startup, PNG encoding or original art'}


def main():
    p=argparse.ArgumentParser()
    for n in ('rom','capture','library','stationary-library','stationary-original','courtyard-library','courtyard-program-sha256','menu-library','app-executable','app-receipt','storage-admit','field-root','baseline-receipt','baseline-library','baseline-python','output','program-sha256'):
        p.add_argument('--'+n,required=True)
    a=p.parse_args(); out=Path(a.output)
    if out.exists(): raise FileExistsError(out)
    out.mkdir(mode=0o700,parents=True); rom=_read_rom(Path(a.rom)); library=Path(a.library); fixture_root=Path(a.field_root)
    model=assisted_arena_from_capture(rom,Path(a.capture),moving=True); program_sha=sha(canonical(model.program))
    if program_sha != a.program_sha256: raise ValueError('unexpected new program')
    build_raw=(library.parent/'receipt.json').read_bytes();build=json.loads(build_raw)
    seed=sha(json.dumps(model.snapshot(),sort_keys=True,separators=(',',':')).encode())
    if (build['program_sha256']!=program_sha or build['dylib_sha256']!=sha(library.read_bytes()) or build['seed_sha256']!=seed or
        build.get('architecture')!='arm64' or build.get('macho_filetype')!='dylib' or not build.get('compiler_sha256') or
        build['source_sha256']!=sha((library.parent/'fdisbull_native.c').read_bytes()) or
        build['header_sha256']!=sha((library.parent/'fdisbull_native.h').read_bytes())):
        raise ValueError('native build receipt mismatch')
    def inventory():
        return [Path(__file__).resolve(),ROOT/'scripts/check_shadowrun_macos.py',ROOT/'src/fdisbull/udc_macos.py',
                ROOT/'src/fdisbull/game_il.py',*sorted((ROOT/'src/fdisbull').glob('shadowrun_*.py')),
                *sorted((ROOT/'src/fdisbull/game_sources').glob('shadowrun_*.c')),
                ROOT/'src/fdisbull/game_sources/shadowrun_macos_app.m',library,Path(a.stationary_library),Path(a.courtyard_library),
                Path(a.menu_library),Path(a.app_executable),Path(a.app_receipt)]
    watched=inventory()
    watched_hashes={str(x):sha(x.read_bytes()) for x in watched}
    fixtures={}
    for name,(rh,ch) in FIXTURES.items():
        root=fixture_root/name; rr=(root/'native/receipt.json').read_bytes(); cr=(root/'capture.json').read_bytes()
        if sha(rr)!=rh or sha(cr)!=ch: raise ValueError('unreviewed original fixture '+name)
        rec=json.loads(rr);cap=json.loads(cr)
        if rec['patches_input_sha256']!=PATCH_SHA or len(rec['patches'])!=5 or any(x['frame']!=6000 for x in rec['patches']):
            raise ValueError('unexpected assisted patch setup')
        fixtures[name]=(root,rec,cap)
    routes={'moving':['moving-long-original-01','moving-repeated-original-01'],
            'retreat':['retreat-original-01','retreat-boundary-original-02','retreat-relaunch-original-01'],
            'offense':['offense-original-01'], 'down-survivor':['down-long-original-01']}
    courtyard_ids={
        'courtyard-original-01':('b54d52417567b97590cea958215b36abb0cd26b4a9c4d59c967db055d93086eb','7ee8be20afafffb774aa6e91b7342b63845808c651f6e2b65a6da6cd9482cc8e'),
        'courtyard-boundary-original-01':('5d85e63e8b171b1e2643700e1d719b177030f3c37ceac0cf6bb48c1dbd58ce60','282523587a0482819048e570326708d6e7b96ea038a74541169469d98fa13e12'),
        'courtyard-boundary-6389-original-01':('d3e3c707d952f5e76da7d28cb55c9c5431026f0b0576268c5beeec7999b0e3d4','c035ad13ea74d1fe4d6a89a8aca9df2df46d4502e1e767793fcec84567c00dc9'),
        'courtyard-boundary-6391-original-01':('fdfbe3c1cdbd66959c040581bf10b4fa324aa23b97c7696a72a0494337e10a84','6d9a26a81e1e1b0c11e2803e774254d9a55229ac072d356c7c30cc8fc8d6378a')}
    courtyard_records=[]
    for name,(rh,ch) in courtyard_ids.items():
        root=fixture_root/name;rr=(root/'native/receipt.json').read_bytes();cr=(root/'capture.json').read_bytes()
        if sha(rr)!=rh or sha(cr)!=ch:raise ValueError('unreviewed courtyard fixture')
        rec=json.loads(rr);cap=json.loads(cr)
        if rec['patches']:raise ValueError('courtyard fixture is patched')
        courtyard_records.append((root,rec,cap))
    baseline_raw=Path(a.baseline_receipt).read_bytes(); baseline=json.loads(baseline_raw)
    if (sha(baseline_raw)!='7e99ff00d7c8189d2b4f086f2da1339100bc06e47eda828977ecf49c61dc1652' or
        baseline['baseline_commit']!='acfb843fa972cd2f2bbca468ab832e4d270a0dfe' or baseline['completed_ticks']!=124 or
        baseline['rejected_source_frame']!=6124 or baseline['step_return']!=1 or not baseline['whole_state_unchanged']):
        raise ValueError('unexpected baseline refusal receipt')
    results={};natives=[]
    try:
        # Reproduce the previous release's refusal in its own installed model
        # and native library. A subprocess prevents mixing Python package versions.
        baseline_code = '''import hashlib,json,sys,fdisbull
from pathlib import Path
from fdisbull.game_il import canonical
from fdisbull.shadowrun_assisted_arena import assisted_arena_from_capture
rom=Path(sys.argv[1]).read_bytes();m=assisted_arena_from_capture(rom,Path(sys.argv[2]),moving=True)
print(json.dumps({'program':hashlib.sha256(canonical(m.program)).hexdigest(),'seed':m.snapshot(),'module':fdisbull.__file__},separators=(',',':')))
'''
        child=subprocess.run([a.baseline_python,'-I','-c',baseline_code,a.rom,a.capture],capture_output=True,
                             text=True,check=True,timeout=120,env=os.environ.copy())
        old=json.loads(child.stdout)
        if old['program']!=baseline['baseline_program_sha256'] or not Path(old['module']).is_relative_to(Path(a.baseline_python).absolute().parents[1]):
            raise ValueError('baseline model identity mismatch')
        old_library=Path(a.baseline_library);old_build=json.loads((old_library.parent/'receipt.json').read_bytes())
        if old_build['program_sha256']!=old['program'] or old_build['dylib_sha256']!=sha(old_library.read_bytes()):
            raise ValueError('baseline native build mismatch')
        old_native=Native(old_library,Path(a.rom));natives.append(old_native);old_native.compare(old['seed'],'baseline seed')
        for index in range(124):
            if old_native.step(4 if 1<=index<=40 else 0):raise AssertionError(('baseline early stop',index))
        def native_snapshot(native, shape):
            state={}
            for name, value in shape.items():
                items=value if isinstance(value,list) else [value];values=[]
                for index in range(len(items)):
                    out_value=ctypes.c_int64()
                    if native.lib.fdisbull_state_get(native.ctx,name.encode(),index,ctypes.byref(out_value)):
                        raise AssertionError(('baseline read',name,index))
                    values.append(out_value.value)
                state[name]=values if isinstance(value,list) else values[0]
            return state
        baseline_before=native_snapshot(old_native,old['seed'])
        if old_native.step(0)!=1:raise AssertionError('baseline did not refuse frame6124')
        old_native.compare(baseline_before,'baseline rollback')
        results['baseline']={'completed_ticks':124,'rejected_source_frame':6124,'whole_state_unchanged':True,
                             'program_sha256':old['program'],'library_sha256':sha(old_library.read_bytes()),
                             'state_sha256':sha(json.dumps(baseline_before,sort_keys=True,separators=(',',':')).encode())}
        for route,names in routes.items():
            records=[fixtures[n] for n in names];intervals=records[0][1]['inputs']
            tail=lambda xs:[x for x in xs if x['start']>=6000]
            if any(tail(r[1]['inputs'])!=tail(intervals) for r in records[1:]): raise ValueError('fixture input schedules disagree')
            m=assisted_arena_from_capture(rom,Path(a.capture),moving=True);native=Native(library,Path(a.rom));natives.append(native)
            elements=native.compare(m.snapshot(),route+':seed'); compared=completed=0;frames=[]
            terminal_reached=False;unsupported_frame=None
            for frame in range(6000,6301):
                buttons=[]
                for item in intervals:
                    if item['start'] <= frame < item['end']: buttons.extend(item['buttons'])
                if len(buttons)!=len(set(buttons)) or any(x not in BUTTONS for x in buttons): raise ValueError('invalid original input schedule')
                pad=sum(BUTTONS[x] for x in buttons);before=m.snapshot();m.call('shadowrun_arena_frame',pad);state=m.snapshot();rc=native.step(pad)
                if state['shadowrun_arena_frame_status']==2:
                    if rc!=1: raise AssertionError((route,frame,'unsupported status',rc))
                    native.compare(before,route+':rollback');unsupported_frame=frame;break
                if rc: raise AssertionError((route,frame,'native fault',rc))
                native.compare(state,route+':'+str(frame));completed+=1
                for root,rec,cap in records:
                    key=f'native/scene-{frame:06d}/ram.bin'
                    if key not in cap['files']: continue
                    raw=(root/key).read_bytes()
                    if len(raw)!=65536 or sha(raw)!=cap['files'][key]['sha256']: raise ValueError('changed original snapshot')
                    b=bytes(raw[i^1] for i in range(65536));fields=(('shadowrun_player_x',0x100,2),('shadowrun_player_y',0x104,2),('shadowrun_arena_hp',0x14c,1),('shadowrun_play_ammo',0x14e,1),('shadowrun_hostile_x',0x400,2),('shadowrun_hostile_y',0x404,2),('shadowrun_hostile_ammo',0x44e,1),('shadowrun_hostile_rng',0xf9f8,2))
                    compare_fields=fields if state['shadowrun_arena_frame_status']!=3 else (('shadowrun_arena_hp',0x14c,1),('shadowrun_hostile_rng',0xf9f8,2))
                    for name,offset,width in compare_fields:
                        expected=int.from_bytes(b[offset:offset+width],'big')
                        if state[name]!=expected: raise AssertionError((route,frame,name,state[name],expected))
                    if state['shadowrun_arena_frame_status']!=3 and state['shadowrun_play_actor_hp'][0]!=b[0x44c]:
                        raise AssertionError((route,frame,'hostile_hp',state['shadowrun_play_actor_hp'][0],b[0x44c]))
                    if state['shadowrun_arena_frame_status']!=3:
                        timer_name=('shadowrun_play_shot_timer' if state['shadowrun_arena_player_ready'] else
                                    'shadowrun_reaction_action_timer')
                        original_timer=int.from_bytes(b[0x1dc:0x1de],'big')
                        if state[timer_name]!=original_timer:
                            raise AssertionError((route,frame,'player_action_timer',state[timer_name],original_timer,timer_name))
                    compared+=1;frames.append(frame)
                if state['shadowrun_arena_frame_status']==3:
                    if route=='down-survivor': raise AssertionError('survivor route ended early')
                    if state['shadowrun_arena_hp']!=0: raise AssertionError('terminal HP mismatch')
                    candidates=[(f,root,cap) for root,rec,cap in records for f in cap['captures'] if f>=frame]
                    if not candidates: raise AssertionError('no original terminal or later checkpoint')
                    observed_frame,observed_root,observed_cap=min(candidates,key=lambda x:x[0])
                    key=f'native/scene-{observed_frame:06d}/ram.bin';raw=(observed_root/key).read_bytes()
                    if len(raw)!=65536 or sha(raw)!=observed_cap['files'][key]['sha256']:
                        raise ValueError('changed original terminal observation')
                    original_ram=bytes(raw[i^1] for i in range(65536))
                    if original_ram[0x14c]!=0: raise AssertionError(('original terminal observation',observed_frame))
                    frozen=m.snapshot();m.call('shadowrun_arena_frame',0)
                    if native.step(0):raise AssertionError('terminal hold failed')
                    native.compare(m.snapshot(),route+':terminal-hold')
                    terminal_changes=[k for k,v in frozen.items() if m.snapshot()[k]!=v]
                    if m.snapshot()['shadowrun_arena_hp']!=0 or m.snapshot()['shadowrun_arena_frame_status']!=3:
                        raise AssertionError((route,frame,'terminal boundary not held'))
                    terminal_reached=True
                    break
            if route=='down-survivor' and unsupported_frame is None:
                if terminal_reached or frame!=6300 or state['shadowrun_arena_hp']!=3:
                    raise AssertionError('survivor route did not reach its observed boundary')
            elif route!='down-survivor' and not terminal_reached and unsupported_frame is None:
                raise AssertionError(route+' did not reach terminal or unsupported boundary')
            if native.lib.fdisbull_reset(native.ctx): raise AssertionError('reset failed')
            native.compare(assisted_arena_from_capture(rom,Path(a.capture),moving=True).snapshot(),route+':reset')
            results[route]={'completed_ticks':completed,'last_completed_frame':6000+completed-1,
                            'first_unsupported_frame':unsupported_frame,
                            'outcome':'unsupported' if unsupported_frame is not None else ('terminal' if terminal_reached else 'survived_to_6300'),
                            'full_state_elements_per_tick':elements,
                            'source_checkpoints_compared':compared,'source_frames':frames,
                            'passed_prior_6124_boundary':6000+completed-1>=6124,'terminal_hp':0 if terminal_reached else None,'reset':'passed'}
            if terminal_reached:
                results[route]['original_hp0_observed_frame']=observed_frame
                results[route]['original_terminal_exact_frame_observed']=observed_frame==frame
                results[route]['terminal_hold_internal_fields_changed']=terminal_changes
            if route=='down-survivor':
                reference_root,_,reference_cap=records[0];key='native/scene-006300/ram.bin';raw=(reference_root/key).read_bytes()
                if len(raw)!=65536 or sha(raw)!=reference_cap['files'][key]['sha256']:
                    raise ValueError('changed source survival checkpoint')
                memory=bytes(raw[i^1] for i in range(65536))
                if memory[0x14c]!=3:raise AssertionError('source survival HP mismatch')
                results[route]['original_survival_observed_frame']=6300
                results[route]['original_survival_hp']=3
        # Interleave independent contexts with differing input schedules.
        m1=assisted_arena_from_capture(rom,Path(a.capture),moving=True);m2=assisted_arena_from_capture(rom,Path(a.capture),moving=True)
        n1=Native(library,Path(a.rom));n2=Native(library,Path(a.rom));natives += [n1,n2]
        for i in range(60):
            p1=4 if 1<=i<=40 else 0;p2=4 if 1<=i<=40 else (1 if i>=41 else 0)
            m1.call('shadowrun_arena_frame',p1);m2.call('shadowrun_arena_frame',p2)
            if n1.step(p1) or n2.step(p2):raise AssertionError('interleaved native refused')
            n1.compare(m1.snapshot(),'interleaved-one');n2.compare(m2.snapshot(),'interleaved-two')
        results['interleaved_contexts_ticks_each']=60
        results['menu']=menu_compare(Path(a.menu_library))
        results['frontend']=frontend_compare(Path(a.app_executable),Path(a.app_receipt),Path(a.rom),Path(a.capture),
                                             program_sha,library,out,Path(a.storage_admit),model)
        # The separate stationary source witness establishes held-A fire and
        # recovery; it is not substituted for the moving offense route.
        sr=Path(a.stationary_original);rr=(sr/'native/receipt.json').read_bytes();cr=(sr/'capture.json').read_bytes()
        if (sha(rr)!='3e8ea721088dfaea695ead43633f2a21b98a6bfecab46594e0d50be8c9cca32a' or
            sha(cr)!='a4b1f40b59b3c3d035e96b6e079ec038e8bc8967a67d0a8acd8a18dcd5743563'):
            raise ValueError('unreviewed stationary return-fire witness')
        srrec=json.loads(rr);srcap=json.loads(cr)
        if (srrec['patches_input_sha256']!='35b9e1f42f112ea972f26e2a5c168cadce30a95511d3f1ccaffb86433294f79e' or
            [x for x in srrec['inputs'] if x['start']>=6000] != [{'start':6013,'end':6080,'buttons':['A']}]):
            raise ValueError('unexpected stationary patch schedule')
        slib=Path(a.stationary_library);sbr=(slib.parent/'receipt.json').read_bytes();sbuild=json.loads(sbr)
        sm=assisted_arena_from_capture(rom,Path(a.capture),moving=False)
        sseed=sha(json.dumps(sm.snapshot(),sort_keys=True,separators=(',',':')).encode())
        if (sha(canonical(sm.program))!=program_sha or sbuild['program_sha256']!=program_sha or
            sbuild['seed_sha256']!=sseed or sbuild['dylib_sha256']!=sha(slib.read_bytes()) or
            sbuild['source_sha256']!=sha((slib.parent/'fdisbull_native.c').read_bytes()) or
            sbuild['header_sha256']!=sha((slib.parent/'fdisbull_native.h').read_bytes())):
            raise ValueError('stationary native build mismatch')
        sn=Native(slib,Path(a.rom));natives.append(sn);selements=sn.compare(sm.snapshot(),'stationary seed');sf=[]
        for f in range(6000,6080):
            pad=64 if f>=6013 else 0;sm.call('shadowrun_arena_frame',pad);ss=sm.snapshot();rc=sn.step(pad)
            if rc or ss['shadowrun_arena_frame_status']!=1:raise AssertionError(('stationary held A',f,rc))
            sn.compare(ss,'stationary held A '+str(f));key=f'native/scene-{f:06d}/ram.bin'
            if key not in srcap['files']:continue
            raw=(sr/key).read_bytes()
            if len(raw)!=65536 or sha(raw)!=srcap['files'][key]['sha256']:raise ValueError('changed stationary snapshot')
            b=bytes(raw[i^1] for i in range(65536))
            fields=(('shadowrun_arena_hp',0x14c,1),('shadowrun_hostile_rng',0xf9f8,2),
                    ('shadowrun_hostile_ammo',0x44e,1),('shadowrun_play_ammo',0x14e,1),
                    ('shadowrun_attack_callback',0x43a,4),('shadowrun_attack_animation',0x416,2),
                    ('shadowrun_attack_service_timer',0x4b6,2),('shadowrun_attack_action_timer',0x4dc,2),
                    ('shadowrun_attack_counter',0x4b5,1))
            if f in (6043,6044,6050):fields += (('shadowrun_linked_x_fixed',0xc00,4),('shadowrun_linked_y_fixed',0xc04,4),('shadowrun_play_shot_timer',0x1dc,2))
            for name,offset,width in fields:
                value=int.from_bytes(b[offset:offset+width],'big')
                if ss[name]!=value:raise AssertionError(('stationary source',f,name,ss[name],value))
            if ss['shadowrun_play_actor_hp'][0]!=b[0x44c]:raise AssertionError(('stationary hostile HP',f))
            if f>=6043 and (ss['shadowrun_field_first_slot'],ss['shadowrun_field_second_slot'])!=(10,11):
                raise AssertionError(('stationary projectile slots',f))
            sf.append(f)
        if len(sf)!=15 or ss['shadowrun_play_ammo']!=11:raise AssertionError('stationary fire witness incomplete')
        if sn.lib.fdisbull_reset(sn.ctx):raise AssertionError('stationary reset failed')
        sn.compare(assisted_arena_from_capture(rom,Path(a.capture),moving=False).snapshot(),'stationary reset')
        results['stationary_held_fire']={'completed_ticks':80,'full_state_elements_per_tick':selements,
            'source_checkpoints_compared':len(sf),'source_frames':sf,'player_ammo':[12,11],
            'source_receipt_sha256':sha(rr),'source_capture_sha256':sha(cr),'native_build_receipt_sha256':sha(sbr),
            'scope':'separate assisted stationary source window, not the moving offense route'}
        # The captured courtyard is a separate unpatched source scene and
        # separately generated program, not the constructed hostile arena.
        cm=captured_courtyard_from_capture(rom,Path(a.capture));clib=Path(a.courtyard_library)
        cprogram=sha(canonical(cm.program));cr=(clib.parent/'receipt.json').read_bytes();cb=json.loads(cr)
        cseed=sha(json.dumps(cm.snapshot(),sort_keys=True,separators=(',',':')).encode())
        if (cprogram!=a.courtyard_program_sha256 or cb['program_sha256']!=cprogram or cb['seed_sha256']!=cseed or
            cb['dylib_sha256']!=sha(clib.read_bytes()) or cb['source_sha256']!=sha((clib.parent/'fdisbull_native.c').read_bytes()) or
            cb['header_sha256']!=sha((clib.parent/'fdisbull_native.h').read_bytes()) or cb.get('architecture')!='arm64'):
            raise ValueError('courtyard native receipt mismatch')
        cn=Native(clib,Path(a.rom));natives.append(cn);celements=cn.compare(cm.snapshot(),'courtyard seed')
        cintervals=courtyard_records[0][1]['inputs']
        if any(tail(x[1]['inputs'])!=tail(cintervals) for x in courtyard_records[1:]):raise ValueError('courtyard schedules disagree')
        cc=0; cf=[]; stopped=None
        for frame in range(6000,6451):
            buttons=[button for item in cintervals if item['start']<=frame<item['end'] for button in item['buttons']]
            if len(buttons)!=len(set(buttons)) or any(x not in BUTTONS for x in buttons):raise ValueError('invalid courtyard input')
            pad=sum(BUTTONS[x] for x in buttons);before=cm.snapshot();cm.call('shadowrun_arena_frame',pad);state=cm.snapshot();rc=cn.step(pad)
            if state['shadowrun_arena_frame_status']==2:
                if rc!=1:raise AssertionError(('courtyard refusal',frame,rc))
                cn.compare(before,'courtyard rollback');stopped=frame;break
            if rc:raise AssertionError(('courtyard native fault',frame,rc))
            cn.compare(state,'courtyard '+str(frame))
            for root,rec,cap in courtyard_records:
                key=f'native/scene-{frame:06d}/ram.bin'
                if key not in cap['files']:continue
                raw=(root/key).read_bytes()
                if len(raw)!=65536 or sha(raw)!=cap['files'][key]['sha256']:raise ValueError('changed courtyard snapshot')
                b=bytes(raw[i^1] for i in range(65536));w=lambda i:int.from_bytes(b[i:i+2],'big')
                got=(state['shadowrun_player_x'],state['shadowrun_player_y'],state['shadowrun_arena_hp'],
                     *[v for pair in zip(state['shadowrun_target_x'][:3],state['shadowrun_target_y'][:3]) for v in pair])
                expected=(w(0x100),w(0x104),b[0x14c],*[w(0x400+i*256+j) for i in range(3) for j in (0,4)])
                if got!=expected:raise AssertionError(('courtyard source',frame,got,expected))
                cc+=1;cf.append(frame)
        if cn.lib.fdisbull_reset(cn.ctx):raise AssertionError('courtyard reset failed')
        cseed_state=captured_courtyard_from_capture(rom,Path(a.capture)).snapshot();cn.compare(cseed_state,'courtyard reset')
        if cn.step(64)!=1:raise AssertionError('unsupported courtyard action accepted')
        cn.compare(cseed_state,'courtyard invalid input rollback')
        results['courtyard']={'preset':'unpatched captured scene2','program_sha256':cprogram,
            'build_receipt_sha256':sha(cr),'fixture_hashes':courtyard_ids,'input_schedule_sha256':sha(json.dumps(cintervals,sort_keys=True,separators=(',',':')).encode()),
            'last_completed_frame':frame if stopped is None else stopped-1,'first_unsupported_frame':stopped,
            'full_state_elements_per_tick':celements,'source_checkpoints_compared':cc,'source_frames':cf,
            'unsupported_action_and_reset':'passed','scope':'no source patches; player/three actor positions and HP at original checkpoints'}
        # Equal completed budgets; update timing excludes UI, model and setup.
        samples=[]
        for _ in range(10):
            if n1.lib.fdisbull_reset(n1.ctx):raise AssertionError('benchmark reset')
            start=time.perf_counter_ns()
            for i in range(60):
                if n1.step(4 if 1<=i<=40 else 0):raise AssertionError('benchmark incomplete')
            samples.append(time.perf_counter_ns()-start)
        results['native_update_benchmark']={'repeats':10,'completed_ticks_each':60,'total_ns_each':samples,
            'scope':'moving preset, native update including ctypes only; not per-frame deadlines or onscreen rendering'}
    finally:
        for native in natives:native.close()
    if watched_hashes!={str(x):sha(x.read_bytes()) for x in watched}:
        raise ValueError('bound source file or native library changed')
    unfinished=any(results[name]['outcome']=='unsupported' for name in routes) or results['courtyard']['first_unsupported_frame'] is not None
    report={'status':'bounded_with_unsupported' if unfinished else 'passed','program_sha256':program_sha,'native_build_receipt_sha256':sha(build_raw),
            'native_library_sha256':sha(library.read_bytes()),'baseline_refusal_receipt_sha256':sha(baseline_raw),
            'baseline_scope':'previous release recorded a transactional refusal at frame6124; this checker validates its receipt and compares new continuation independently',
            'fixture_hashes':{n:{'receipt':v[0],'capture':v[1],
                                  'input_schedule_sha256':sha(json.dumps(fixtures[n][1]['inputs'],sort_keys=True,separators=(',',':')).encode())}
                              for n,v in FIXTURES.items()},
            'patch_input_sha256':PATCH_SHA,'checker_sha256':watched_hashes[str(Path(__file__).resolve())],
            'results':results,'limits':['assisted constructed encounter; no natural progression claim',
            'original full-frame checkpoints compare only named actor/HP/RNG projection',
            'HP0 is a damage-terminal boundary; source death continuation is not modeled',
            'menu initializer and load remain explicit source boundaries, separate from prepared arena']}
    path=out/'summary.json';path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'summary_sha256':sha(path.read_bytes()),'results':results}))

if __name__=='__main__':main()
