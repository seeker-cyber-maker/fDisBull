#!/usr/bin/env python3
"""Native scene-framework acceptance on a private NEW GAME DinoPark copy."""
from copy import deepcopy
from collections import Counter
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import statistics
import time

from PIL import Image
from fdisbull.project import Project
from fdisbull.scenes import SceneError

EXE_SHA='2127315b475b560f8c0fe409769fd6d137e26d9390d2fafc7d03a60a266a827c'


def inventory(root):
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file()}


def main(args):
    original=args.game_dir.resolve();output=args.output.resolve();evidence=args.evidence.resolve()
    for directory in (output,evidence):
        if directory==original or directory in original.parents or original in directory.parents:
            raise ValueError('Outputs must be separate from original input')
        if any((p/'.git').exists() for p in (directory,*directory.parents)):
            raise ValueError('Private game, checkpoint and database output must be outside Git')
    assert output!=evidence and output not in evidence.parents and evidence not in output.parents
    before=inventory(original);assert before['DINOPARK.EXE']==EXE_SHA
    output.mkdir(parents=True,exist_ok=False);evidence.mkdir(parents=True,exist_ok=False)
    game=output/'game';shutil.copytree(original,game,ignore=lambda p,n:[s for s in n if s.upper().startswith('DINOSG.')])
    copied=inventory(game);database=output/'scene.fdb';processes=[]

    def save(n,value):(evidence/(n+'.json')).write_text(json.dumps(value,indent=2)+'\n')
    def run(ms):return dict(op='run',guest_ms=ms,timeout_ms=15000,fast_forward=True,expect='guest_time')
    def click(x,y,n):return dict(op='click-frame',x=x,y=y,name=n+'.png',grid_step=8,hold_ms=80)
    def route(p,d,n,steps):
        script=dict(format='fdisbull-script-1',steps=steps);save(n+'.script',script)
        saved=p.debug_save_script(n,script);result=d.script(script_id=saved['script_id'],timeout_ms=60000)
        save(n+'.result',result);assert result['ok'],result
        return result
    def shot(p,d,n):
        frame=d.screenshot(n+'.png');p.debug_export(frame['artifact'],evidence/(n+'.png'));save(n+'.metadata',frame)
        return frame
    def signature(p,frame,coords):
        row=p.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(frame['artifact'],)).fetchone()
        with Image.open(io.BytesIO(row['data'])) as image:
            image=image.convert('RGB');samples=[dict(x=x,y=y,rgb=list(image.getpixel((x,y)))) for x,y in coords]
        return {'pixels':dict(samples=samples,min_matches=len(samples)-1,tolerance=0)}
    def selector(d):return {'memory':dict(address='4020:3c5c',length=2,hex=d.memory('4020:3c5c',length=2)['hex'])}
    def obj(n,area,point,visible,ready,outcome):
        reported={'office.bank':[0,0,102,53],'office.ledger':[119,60,220,177],'office.sell_park':[205,135,298,172]}
        return dict(name=n,area=area,original_area={'rect':reported[n]} if n in reported else deepcopy(area),point=point,
            context=dict(state=n,triggers=['containing scene controls built'],reported_bounds=reported.get(n),
            boundary_note='Reported source upper-edge convention unverified; action masks use declared native raster geometry',
            confidence='runtime-observed point; readiness selector calibrated',
            source='User-provided office rectangles; native NEW GAME calibration',
            readiness_limit='Dispatch selector correlation plus successful bounded action, not a universal registration proof',
            cost_reward=dict(cost='sparse RGB samples and one known memory word',reward='reuse verified navigation without image inference')),
            visible=visible,ready=ready,enabled={'constant':True},action={'kind':'click'},outcome=outcome,guest_ms=12000,timeout_ms=10000)
    def manifest(frame,state,match,objects):
        return dict(format='fdisbull-scene-1',reference=frame['artifact'],width=320,height=200,mode_id=frame['metadata']['mode_id'],
            context=dict(state=state,triggers=['original guest navigation'],camera='fixed office UI',modal='none'),match=match,objects=objects)
    def failures(p,d,n,call):
        try:call()
        except SceneError as error:
            save(n,error.result)
            for key in ('snapshot','overlay'):
                if key in error.result:p.debug_export(error.result[key],evidence/(n+'-'+key+'.png'))
            for i,a in enumerate(error.result.get('conflict_overlays',[])):p.debug_export(a,evidence/(n+f'-conflict-{i}.png'))
            return error.result
        raise AssertionError('Expected a scene exception: '+n)

    receipt=dict(scope='Unreleased scene implementation with native DOSBox probe; private original NEW GAME',
        original_exe_sha256=EXE_SHA,source_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),sessions=[])
    import fdisbull
    receipt['tool_version']=fdisbull.__version__
    receipt['tool_module']=str(Path(fdisbull.__file__).resolve())
    receipt['framework_source_sha256']={n:hashlib.sha256((Path(fdisbull.__file__).parent/n).read_bytes()).hexdigest()
        for n in ('scenes.py','scene_geometry.py','debugger.py','debug_script.py','cli.py')}
    with Project.create(database,game/'DINOPARK.EXE',load_segment=0x1000) as p:
        with p.debugger(args.executable,game) as d:
            processes.append(d.rpc.process);receipt['backend_sha256']=d.metadata['emulator_sha256'];receipt['sessions'].append(d.run_id)
            route(p,d,'new-game-office',[run(35000),click(80,160,'new'),run(2500),click(160,132,'loan'),run(5000),click(175,140,'office'),run(2500)])
            office=shot(p,d,'office-reference');office_ready=selector(d)
            office_match=signature(p,office,[(x,y) for y in (15,38,64,87,112,143) for x in (12,48,85,118,158,198,238,283)])
            route(p,d,'calibrate-bank',[click(51,26,'bank'),run(2500)])
            bank=shot(p,d,'bank-reference');bank_ready=selector(d)
            bank_match=signature(p,bank,[(x,y) for y in (15,38,64,87) for x in (12,48,85,118,158,198,238,283)])
            route(p,d,'calibrate-bank-return',[click(173,187,'back'),run(2500),click(169,118,'ledger'),run(2500)])
            ledger=shot(p,d,'ledger-reference');ledger_ready=selector(d)
            ledger_match=signature(p,ledger,[(x,y) for y in (15,38,64,87,112,143) for x in (95,118,158,198,238,283)])
            route(p,d,'calibrate-ledger-return',[click(173,187,'back'),run(2500),click(251,153,'sell-dialog'),run(1200)])
            modal=shot(p,d,'sell-modal-reference')
            modal_match=signature(p,modal,[(x,y) for y in (81,83,85,87,89,91,93,95) for x in (102,120,140,160,180,200,218)])
            route(p,d,'calibrate-cancel-sale',[click(147,110,'cancel-sale'),run(2500)])
            checkpoint=d.save_state('private-office.sav')
            doc=manifest(office,'office',office_match,[
                obj('office.bank',{'union':[{'rect':[1,1,102,30]},{'rect':[1,30,102,53]}]},[51,26],office_match,office_ready,bank_match),
                obj('office.ledger',{'subtract':[{'rect':[119,60,220,177]},{'rect':[205,135,299,173]}]},[169,118],office_match,office_ready,ledger_match),
                obj('office.sell_park',{'rect':[205,135,299,173]},[251,153],office_match,office_ready,modal_match)])
            doc['handlers']=[dict(name='cancel_sale',when=modal_match,action={'kind':'click','hold_ms':80},point=[147,110],outcome=office_match)]
            first=p.debug_save_scene('office',doc,author='scene acceptance')
            bank_scene=p.debug_save_scene('bank',manifest(bank,'bank',bank_match,[obj('bank.back',{'rect':[161,177,185,200]},[173,187],bank_match,bank_ready,office_match)]))
            ledger_scene=p.debug_save_scene('ledger',manifest(ledger,'ledger',ledger_match,[obj('ledger.back',{'rect':[161,177,185,200]},[173,187],ledger_match,ledger_ready,office_match)]))
            overlay=p.debug_scene_overlay(first['id']);p.debug_export(overlay['artifact'],evidence/'office-overlay.png')
            overlay_hash=overlay['sha256'];save('office-manifest',first)
            # Input is prevented even while the office is visible.
            blocked=deepcopy(first['definition']);blocked['objects'][0]['ready']={'constant':False}
            second=p.debug_save_scene('office',blocked,parent=first['id'])
            clicks=lambda:sum(x['operation']=='click' for x in p.debug_events(d.run_id,limit=1000)['events'])
            old=clicks();error=failures(p,d,'not-ready',lambda:d.scene_click(second['id'],'office.bank'))
            assert error['availability']['visible'] is True and error['availability']['ready'] is False and clicks()==old
            disabled=deepcopy(first['definition']);disabled['objects'][0]['enabled']={'constant':False}
            third=p.debug_save_scene('office',disabled,parent=second['id'])
            error=failures(p,d,'disabled',lambda:d.scene_click(third['id'],'office.bank'));assert error['availability']['enabled'] is False and clicks()==old
            restored=deepcopy(first['definition']);restored['objects'][0]['name']='office.bank_account'
            final=p.debug_save_scene('office',restored,parent=third['id'])
            assert final['definition']['objects'][0]['id']==first['definition']['objects'][0]['id']
            invalid=deepcopy(final['definition']);invalid['objects'][1]['point']=[210,150]
            try:p.debug_save_scene('office',invalid,parent=final['id'])
            except ValueError:pass
            else:raise AssertionError('Point in subtracted overlap was accepted')
            rival=p.debug_save_scene('office_conflict',doc)
            collision=failures(p,d,'collision',lambda:d.scene_assert(final['id']))
            assert collision['status']=='ambiguous' and collision['conflict_overlays']
            off=deepcopy(rival['definition']);off['match']={'constant':False}
            p.debug_save_scene('office_conflict',off,parent=rival['id'])
            route(p,d,'named-ledger',[{'op':'scene-click','scene':final['id'],'object':'office.ledger'},
                {'op':'scene-click','scene':ledger_scene['id'],'object':'ledger.back'}])
            route(p,d,'named-modal-and-bank',[{'op':'scene-click','scene':final['id'],'object':'office.sell_park'},
                {'op':'scene-click','scene':final['id'],'object':'office.bank','handle_popups':True},
                {'op':'scene-click','scene':bank_scene['id'],'object':'bank.back'}])
            shot(p,d,'after-named-actions')
            # Preserve a real original-game breakpoint stop inside scene waiting.
            warm=d.trace('scene-loop-sample.trace.json',count=128,timeout_ms=10000)
            assert warm['metadata']['complete'];p.debug_export(warm['artifact'],evidence/'scene-loop-sample.trace.json')
            events=json.loads((evidence/'scene-loop-sample.trace.json').read_text())['events']
            candidates=Counter(e['project_segmented_address'] for e in events if e.get('project_segmented_address'))
            location,count=candidates.most_common(1)[0]
            segment,offset=location.split(':');address=int(segment,16)*16+int(offset,16)
            save('input-loop-selection',dict(location=location,occurrences=count,basis='Observed repeated instruction in the current original-game trace'))
            analysis=p.analyze(start=hex(address),cs='0x'+segment,max_instructions=16);save('input-loop-analysis',analysis)
            bp=d.breakpoint(location);save('input-loop-breakpoint',bp);assert bp['bytes_verified']
            error=failures(p,d,'breakpoint-preserved',lambda:d.scene_wait(second['id'],object='office.bank',guest_ms=4000,timeout_ms=5000))
            assert error['status']=='stopped' and error['stop']['outcome']=='breakpoint'
            d.delete_breakpoint(bp['breakpoint_id'])
            hook=d.hook(location,actions=[{'op':'layers','layers':[]}])
            hook_stop=failures(p,d,'hook-preserved',lambda:d.scene_wait(second['id'],object='office.bank',guest_ms=4000,timeout_ms=5000))
            assert hook_stop['status']=='stopped' and hook_stop['stop']['hook_hits']
            assert all(h['hook']!=hook['hook'] for h in d.hooks()['hooks'])  # once=True is already disarmed.
            trace=d.trace('scene-input.trace.json',count=128,timeout_ms=10000)
            assert trace['metadata']['complete'];p.debug_export(trace['artifact'],evidence/'scene-input.trace.json');save('scene-input.trace.metadata',trace)
            d.run(guest_ms=1000,timeout_ms=5000,fast_forward=True)
            watches=d.breakpoint('4020:3c5c',access='w',length=2)
            watch_stop=failures(p,d,'watchpoint-preserved',lambda:d.scene_click(final['id'],'office.bank'))
            assert watch_stop['status']=='stopped' and watch_stop['stop']['stop']['trigger']=='watchpoint'
            assert watch_stop['stop']['session']['stop_reason']['data_access']['access']=='w'
            for watched in watches['breakpoints']:d.delete_breakpoint(watched['breakpoint_id'])
            d.scene_wait(bank_scene['id'],guest_ms=12000,timeout_ms=10000)
            d.scene_click(bank_scene['id'],'bank.back')
            coords=[[s['x'],s['y']] for s in office_match['pixels']['samples']]
            probe_times=[];png_times=[];probe_sizes=[];png_sizes=[]
            for _ in range(10):
                start=time.perf_counter();value=d.frame_probe(coords);probe_times.append((time.perf_counter()-start)*1000);probe_sizes.append(len(json.dumps(value).encode()))
                start=time.perf_counter();value=d.call('video.screenshot');png_times.append((time.perf_counter()-start)*1000);png_sizes.append(len(json.dumps(value).encode()))
            receipt['probe_measurement']=dict(samples=len(coords),iterations=10,median_probe_ms=statistics.median(probe_times),median_png_ms=statistics.median(png_times),probe_response_bytes=probe_sizes,png_response_bytes=png_sizes,scope='Same stopped native guest; probe includes event persistence, raw PNG call does not')
            receipt['object_id']=first['definition']['objects'][0]['id'];receipt['scene_revision']=final['id']
            receipt['collision_observation']=collision['observation'];receipt['controls_ready_limit']=office_ready
    with Project(database) as p:
        assert p.debug_scene_info(final['id'])['definition']['objects'][0]['id']==receipt['object_id']
        offline=p.debug_scene_overlay(first['id']);assert offline['sha256']==overlay_hash
        p.debug_export(offline['artifact'],evidence/'office-overlay-after-restart.png')
        with p.debugger(args.executable,game) as d:
            processes.append(d.rpc.process);receipt['sessions'].append(d.run_id)
            d.load_state(checkpoint['artifact'])
            unavailable=d.scene_check(final['id']);assert unavailable['status']=='unavailable';save('restored-before-first-frame',unavailable)
            d.run(guest_ms=1000,timeout_ms=5000,fast_forward=True)
            d.scene_assert(final['id'])
            route(p,d,'fresh-named-bank',[{'op':'scene-click','scene':final['id'],'object':'office.bank'},
                {'op':'scene-click','scene':bank_scene['id'],'object':'bank.back'}])
            fresh=shot(p,d,'fresh-office')
            overlay=p.debug_scene_overlay(final['id'],artifact=fresh['artifact']);p.debug_export(overlay['artifact'],evidence/'fresh-office-overlay.png')
        save('observations',p.debug_scene_observations(limit=1000))
    assert inventory(original)==before and inventory(game)==copied
    assert all(process.poll() is not None for process in processes)
    receipt.update(ok=True,original_files_unchanged=len(before),private_files_unchanged=len(copied),processes_reaped=True,
        native_checkpoint_restores=1,private_state_exported=False,offline_overlay_byte_identical=True,game_files_states_databases_in_evidence=False,
        preserved_stops=['breakpoint','watchpoint','hook'])
    save('VERIFICATION',receipt);save('SHA256SUMS',inventory(evidence));print(json.dumps(receipt,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for n in ('executable','game-dir','output','evidence'):parser.add_argument('--'+n,type=Path,required=True)
    main(parser.parse_args())
