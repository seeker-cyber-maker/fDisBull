"""ONE full quest continuation from a normal-gameplay quest-start checkpoint.

This is a restored continuation, never a fresh-game observation. It launches
only when explicitly invoked and does not retry, alter guest memory, redirect
execution, or load another checkpoint. Do not call the continuation fresh gameplay.
"""
from hashlib import sha256
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import shutil
import argparse

from fdisbull.project import Project
from examples.agi.spatial_trial import PROFILES, WRITER, find, manifest, read, require
from examples.agi.verify_gnome_giant import QuestRun

CHECKOUT=Path(__file__).resolve().parents[2]
DEPENDENCIES=(
    'examples/agi/resume_gnome_giant.py', 'examples/agi/verify_gnome_giant.py',
    'examples/agi/verify_leprechaun.py', 'examples/agi/verify_mushroom.py',
    'examples/agi/verify_bridge_clip.py', 'examples/agi/verify_goat.py',
    'examples/agi/spatial_trial.py', 'examples/agi/distance_probe.py',
    'examples/agi/motion_probe.py', 'examples/agi/inventory_probe.py',
    'examples/agi/verify_troll.py', 'examples/agi/verify_host.py',
    'examples/agi/scan_collision_candidates.py',
    'src/fdisbull/agi.py', 'src/fdisbull/agi_layout.py', 'src/fdisbull/agi_picture.py',
    'src/fdisbull/agi_lift.py', 'src/fdisbull/project.py', 'src/fdisbull/debugger.py',
    'src/fdisbull/agi_print.py', 'src/fdisbull/agi_host.py',
    'src/fdisbull/agi_dos.py', 'src/fdisbull/agi_resources.py',
)

def digest(path):return sha256(path.read_bytes()).hexdigest()
def save(path,value):path.write_text(json.dumps(value,indent=2,default=str)+'\n')

def project_quest_start(raw):
    # Fixed projection used by the exporter, kept local so no mutable exporter
    # is imported into a live native controller.
    fields=('room','score','x','y','direction','ego_width','ego_view','step_size','swimming','player_control')
    ego=raw['ego'];state={k:ego[k] if k in ('x','y','direction') else raw[k] for k in fields}
    state.update(drawn=ego['drawn'],in_water=raw['in_water'],dead=raw['dead'],ignore_blocks=raw['ignore_blocks'])
    variables={'wrong_stage':'84','door_state':'66','giant_state':'86'}
    flags={'room_callback':'21','room_name_prompt':'22','key_taken':'84','door_scored':'85',
           'shield_active':'102','chest_taken':'104','chest_callback':'169','sleep_scored':'205'}
    state.update({k:raw['quest_variables'][v] for k,v in variables.items()})
    state.update({k:raw['quest_flags'][v] for k,v in flags.items()})
    for name,item in {'chest':2,'key':5,'clover':8,'diamonds':15,'bag':16,'shield':21,'mushroom':24}.items():
        state[name+'_carried']=raw[name+'_carried'];state['inventory_'+str(item)]=raw['inventory_locations'][str(item)]
    state['gnome_key_ready']=state['room']==40 and state['room_callback'] is True
    return state


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','backend','project','artifact','source-capture','source-result','output'):
        parser.add_argument('--'+name,required=True)
    args=parser.parse_args(argv)
    SOURCE=Path(args.source).resolve();BACKEND=Path(args.backend).resolve()
    ORIGINAL_DB=Path(args.project).resolve();donor_capture=Path(args.source_capture).resolve()
    donor_result=Path(args.source_result).resolve();CHECKPOINT_ID=args.artifact
    requested=Path(args.output);OUT=requested.resolve()
    require(not requested.exists() and not requested.is_symlink(), 'Output already exists or is a symlink')
    require(CHECKPOINT_ID and ORIGINAL_DB.is_file() and donor_capture.is_file() and donor_result.is_file(),
            'Missing checkpoint project or donor evidence')
    wal=Path(str(ORIGINAL_DB)+'-wal');journal=Path(str(ORIGINAL_DB)+'-journal')
    require((not wal.exists() or wal.stat().st_size==0) and not journal.exists(),
            'Original project has uncheckpointed writes')
    DB_SHA=digest(ORIGINAL_DB);EXPECTED={name:digest(CHECKOUT/name) for name in DEPENDENCIES}
    with closing(sqlite3.connect(ORIGINAL_DB.as_uri()+'?mode=ro&immutable=1',uri=True)) as db:
        db.row_factory=sqlite3.Row
        require(db.execute('pragma integrity_check').fetchone()[0]=='ok','Original project integrity differs')
        row=db.execute("""SELECT a.name,a.kind,a.sha256,a.metadata,a.data,r.version
            FROM debug_artifacts a JOIN debug_runs r ON r.id=a.run WHERE a.id=?""",(CHECKPOINT_ID,)).fetchone()
        require(row is not None and row['kind']=='state' and sha256(bytes(row['data'])).hexdigest()==row['sha256'],
                'Selected artifact is not an intact saved state')
        CHECKPOINT_SHA=row['sha256'];CHECKPOINT_NAME=row['name'];VERSION=row['version']
        metadata=json.loads(row['metadata']);GAME=Path(metadata['game_dir']).resolve()
        require(metadata.get('format')=='dosbox-x-native' and metadata.get('disk_restore') is False and
                metadata.get('code_layers')=={'active':[],'ram_base':{},'ram_applied':{}} and
                'derivation' not in metadata,
                'Checkpoint includes unsupported layers, derivation or disk restoration')
    require(isinstance(CHECKPOINT_NAME,str) and Path(CHECKPOINT_NAME).name==CHECKPOINT_NAME and
            type(VERSION) is int and VERSION>0,'Checkpoint name or version differs')
    for forbidden in (CHECKOUT,SOURCE,GAME,ORIGINAL_DB.parent,donor_capture.parent,donor_result.parent):
        require(OUT!=forbidden and forbidden not in OUT.parents,'Output must be separate from checkout and inputs')
    require(not any(p.is_symlink() for root in (SOURCE,GAME) for p in root.rglob('*')),
            'Source and game copy may not contain symlinks')
    donor_capture_sha=digest(donor_capture);donor_result_sha=digest(donor_result)
    donor=json.loads(donor_capture.read_text());prior=json.loads(donor_result.read_text())
    original=prior['source_manifest']
    require(len(original)==24 and manifest(SOURCE)==original and manifest(GAME)==original,
            'Source or checkpoint game copy differs before admission')
    require(digest(BACKEND)==prior['backend_sha256'] and digest(BACKEND)==metadata.get('emulator_sha256') and
            str(GAME)==metadata.get('game_dir'),'Checkpoint backend or game directory differs')
    checkpoints=[x for x in prior['private_checkpoints'] if x.get('path')==CHECKPOINT_NAME]
    require(prior.get('normal_leprechaun_complete') is True and prior.get('post_teardown_source_unchanged') is True and
            prior.get('post_teardown_copy_unchanged') is True and len(checkpoints)==1 and
            checkpoints[0].get('sha256')==CHECKPOINT_SHA and checkpoints[0].get('loaded') is False and
            type(checkpoints[0].get('guest_ms')) in (int,float) and
            checkpoints[0]['guest_ms']==donor['observations']['quest-start']['guest_ms'] and
            donor['runtime'].get('policy')=='physical' and donor['runtime'].get('fresh_game') is True and
            donor['runtime'].get('interventions')==[] and donor['source']['agi_sha256']==digest(SOURCE/'AGI') and
            donor['source']['object_sha256']==digest(SOURCE/'OBJECT'), 'Donor checkpoint provenance differs')
    source_state=donor['observations']['quest-start']['state']
    source_projection=project_quest_start(source_state)
    OUT.mkdir()
    shutil.copyfile(donor_capture,OUT/'origin-source-capture.private.json')
    shutil.copyfile(donor_result,OUT/'origin-source-result.private.json')
    require(digest(OUT/'origin-source-capture.private.json')==donor_capture_sha and
            digest(OUT/'origin-source-result.private.json')==donor_result_sha,'Donor evidence copy differs')
    report={'format':'fdisbull-restored-quest-diagnostic-1','fresh_game':False,
        'scope':'One restored quest-start checkpoint followed by all eight original-input quest actions; not a fresh game.',
        'checkpoint_id':CHECKPOINT_ID,'checkpoint_sha256':CHECKPOINT_SHA,'original_db_sha256':DB_SHA,
        'source_manifest':original,'backend_sha256':digest(BACKEND),'dependency_sha256':EXPECTED,'observations':[],
        'checkpoint_loads_attempted':0,'complete':False,'restored_quest_complete':False}
    def checkpoint_report():save(OUT/'diagnostic.private.json',report)
    checkpoint_report(); primary=None;driver=None;origin_reference=None;native_checks_complete=False
    try:
        uri=ORIGINAL_DB.as_uri()+'?mode=ro&immutable=1'
        with closing(sqlite3.connect(uri,uri=True)) as src, closing(sqlite3.connect(OUT/'private-copy.fdb')) as dst:
            require(src.execute('pragma integrity_check').fetchone()[0]=='ok','Original database integrity differs')
            src.backup(dst)
            require(dst.execute('pragma integrity_check').fetchone()[0]=='ok','Database copy integrity differs')
        with Project(OUT/'private-copy.fdb') as p:
          with p.debugger(BACKEND,GAME,version=VERSION,fair_play=True) as d:
            try:
                # Fresh runtime identity discovery uses original game boot only,
                # then the one requested native checkpoint replaces that CPU state.
                binary,image,agi,keys=PROFILES['kq1']
                require(digest(SOURCE/'AGI')==agi,'AGI identity differs')
                boot=[d.run(guest_ms=5000,timeout_ms=15000,fast_forward=True)]
                for key in keys:
                    d.keyboard_press(key,hold_ms=60,gap_ms=50)
                    boot.append(d.run(guest_ms=5000,timeout_ms=15000,fast_forward=True))
                hits=find(d,WRITER);require(len(hits)==1,'Fresh runtime writer ambiguous')
                linear=hits[0]
                bp=d.call('breakpoints.create',{'kind':'execution','once':False,'address':
                    {'space':'segmented','segment':f'0x{linear>>4:04X}','offset':f'0x{linear&15:08X}'}})['breakpoint_id']
                stopped=d.run(guest_ms=5000,timeout_ms=10000,fast_forward=True);regs=d.registers()
                require(stopped['outcome']=='breakpoint' and
                        (stopped.get('session') or {}).get('stop_reason',{}).get('breakpoint_id')==bp and
                        int(regs['segments']['cs'],16)*16+int(regs['instruction_pointer'],16)==linear and
                        int(regs['general']['ecx'],16)==0,'Fresh runtime writer stop differs')
                ds=int(regs['segments']['ds'],16)*16; actor=ds+int(regs['general']['edi'],16)
                require(int.from_bytes(read(d,ds+0x963,2),'little')+ds==actor and
                        read(d,linear+0x2a,5)==bytes.fromhex('814d250004'),'Fresh runtime actor binding differs')
                definitions=[dict(name='actor',address=actor,length=64,expected_hex=read(d,actor,3).hex(),
                    provenance={'method':'fresh live get.pos object0 DS:DI','agi_sha256':agi}),
                    dict(name='variables',address=ds,length=265,expected_hex=read(d,ds,9).hex(),
                    provenance={'method':'fresh live get.pos variable array','agi_sha256':agi})]
                d.call('breakpoints.delete',{'breakpoint_id':bp})
                report['boot']=boot;report['resolution']={'writer_linear':hex(linear),'actor_linear':hex(actor),
                    'ds_linear':hex(ds),'stop':stopped,'registers':regs,'definitions':definitions}
                report['checkpoint_loads_attempted']=1;checkpoint_report()
                row=p.db.execute('SELECT metadata,sha256 FROM debug_artifacts WHERE id=?',(CHECKPOINT_ID,)).fetchone()
                require(row is not None and row['sha256']==CHECKPOINT_SHA,'Copied checkpoint artifact differs')
                saved_metadata=json.loads(row['metadata'])
                restored=d.load_state(CHECKPOINT_ID) # Full built-in metadata, disk and CPU validation.
                require(restored['sha256']==CHECKPOINT_SHA,'Loaded checkpoint hash differs')
                post=d.registers()
                require(post['cpu_mode']=='real' and int(post['segments']['cs'],16)==int(regs['segments']['cs'],16) and
                        int(post['segments']['ds'],16)*16==ds and
                        int.from_bytes(read(d,ds+0x963,2),'little')+ds==actor and
                        read(d,linear,len(WRITER))==WRITER,'Restored runtime identity differs')
                # Restore invalidates bindings: witness the restored bytes at
                # the independently rediscovered and revalidated addresses.
                restored_definitions=[{**item,
                    'expected_hex':read(d,item['address'],3 if item['name']=='actor' else 9).hex(),
                    'provenance':{**item['provenance'],'witness':'restored state after validated identity'}}
                    for item in definitions]
                for item in restored_definitions:d.bind_runtime_memory(**item)
                report['restored']={'receipt':restored,'session_id':d.session_id,
                                    'definitions':restored_definitions}
                def frame(name):
                    item=d.screenshot(name,hooks=False);p.debug_export(item['artifact'],OUT/name);return item
                driver=QuestRun(p,d,report,frame,SOURCE,OUT);driver.quest_started=True
                require(driver._idle() and driver.watch is None and not driver.trace_active,'Restored input is not settled')
                def observe(label):
                    state=driver.state();v=read(d,ds+9,256);f=read(d,ds+0x109,32)
                    record={'label':label,'guest_ms':driver.guest_elapsed,'state':state,
                            'diagnostics':{'f73':bool(f[73//8]&(0x80>>(73%8))),
                                           'f79':bool(f[79//8]&(0x80>>(79%8))),
                                           'v63':v[63],'v64':v[64]}}
                    report['observations'].append(record);checkpoint_report();return state
                s=observe('restored-quest-start')
                original_state=source_state
                def contains(actual, expected):
                    if isinstance(expected,dict):
                        return isinstance(actual,dict) and all(k in actual and contains(actual[k],v) for k,v in expected.items())
                    return type(actual) is type(expected) and actual==expected
                require(contains(s,original_state),'Restored state differs from original quest-start observation')
                require(s['room']==36 and s['score']==14 and s['ego']['direction']==0 and s['ego']['drawn'] is True and
                        s['shield_carried'] and s['quest_flags']['102'] and s['clover_carried'] and
                        not s['mushroom_carried'] and not s['key_carried'] and not s['chest_carried'] and
                        s['player_control']==1,'Restored quest-start state differs')
                report['original_quest_start_projection_verified']=True
                # Native load invalidates the framebuffer; prime one bounded
                # original slice before the normal fresh-frame observation.
                before_priming=driver.guest_elapsed
                driver.advance(50)
                report['renderer_priming_guest_ms']=driver.guest_elapsed-before_priming
                driver.observe_clip('quest-start')
                require(project_quest_start(driver.clip_observations['quest-start']['state'])==source_projection,
                        'Primed quest-start projection changed')
                cpu_fields=('cpu_mode','general','segments','instruction_pointer','flags')
                saved_cpu={k:saved_metadata['registers'][k] for k in cpu_fields}
                restored_cpu={k:restored['registers'][k] for k in cpu_fields}
                require(saved_cpu==restored_cpu,'Restored saved CPU differs')
                origin={'format':'fdisbull-agi-checkpoint-origin-1','complete':True,'load_count':1,
                    'state_sha256':CHECKPOINT_SHA,'loaded_state_sha256':restored['sha256'],
                    'source_agi_sha256':donor['source']['agi_sha256'],'object_sha256':donor['source']['object_sha256'],
                    'backend_sha256':digest(BACKEND),'loaded_session_id':d.session_id,'policy':'physical',
                    'disk_manifest_verified':True,'no_guest_edits':True,'source_observation_id':'quest-start',
                    'initial_projected_state':source_projection,'saved_cpu':saved_cpu,'restored_cpu':restored_cpu,
                    'source_capture':{'path':'origin-source-capture.private.json','sha256':donor_capture_sha},
                    'source_result':{'path':'origin-source-result.private.json','sha256':donor_result_sha}}
                save(OUT/'native-origin.private.json',origin)
                origin_reference={'path':'native-origin.private.json','sha256':digest(OUT/'native-origin.private.json')}
                report['native_origin']=origin_reference
                capture=driver.resume_quest()
                report.pop('normal_gnome_giant_complete',None)
                require(isinstance(capture,dict) and len(capture.get('actions',[]))==8 and
                        len(capture.get('observations',{}))==9 and len(capture.get('guess_observations',[]))==3 and
                        'door_observation' in capture,'Restored quest capture incomplete')
                capture['runtime']['fresh_game']=False
                capture['runtime']['interventions']=[{'kind':'native-checkpoint-load','state_sha256':CHECKPOINT_SHA}]
                # Native origin receipt is supplied by the agreed contract.
                capture['native_origin']=origin_reference
                save(OUT/'capture.private.json',capture)
                s=observe('restored-quest-complete')
                distance=driver.distance_probe.proof;pickup=driver.quest_probe.proof;trace=pickup.get('trace',{})
                require(s['room']==58 and s['score']==34 and s['key_carried'] and s['shield_carried'] and
                        s['chest_carried'] and s['quest_flags']['104'] and s['quest_flags']['169'] and
                        s['quest_variables']['86']==3,'Restored chest final state differs')
                require(distance.get('status')=='verified' and distance.get('complete') is True and
                        distance.get('native_execution') is True and pickup.get('status')=='verified' and
                        pickup.get('complete') is True and pickup.get('native_execution') is True and
                        pickup.get('order')==['score','item','return'] and driver.trace_receipt is not None and
                        driver.trace_receipt.get('name')=='chest' and driver.trace_receipt.get('complete') is True and
                        isinstance(trace.get('path'),str) and Path(trace['path']).name==trace['path'] and
                        digest(OUT/trace['path'])==trace.get('sha256') and
                        sum(item.get('key')=='type:get chest' for item in driver.inputs)==1,
                        'Original distance, pickup, trace or single input differs')
                native_checks_complete=True
                report.update(stop='restored-quest-complete',final_state=s)
                checkpoint_report()
            except BaseException as error:
                if primary is None:primary=error
                report.update(complete=False,restored_quest_complete=False)
                report.pop('normal_gnome_giant_complete',None)
                report['error']={'type':type(error).__name__,'message':str(error)}
                raise
            finally:
                if driver is not None:
                    def retain(label, fn):
                        try:fn()
                        except BaseException as extra:
                            report.setdefault('persistence_errors',[]).append({'operation':label,
                                'type':type(extra).__name__,'message':str(extra)})
                    # Read/stop an active trace without advancing the guest.
                    if driver.trace_active:retain('partial trace readback',driver.retain_trace_readback)
                    if driver.trace_active:retain('trace cleanup',driver.stop_trace)
                    retain('last state',lambda:report.update(last_state_before_teardown=driver.state()))
                    report['inputs']=driver.inputs;report['journal']=driver.journal
                    report['messages']=driver.messages;report['samples']=driver.samples
                    report['component_observations']=driver.clip_observations
                    report['component_actions']=driver.clip_actions
                    def retain_partial_capture():
                        partial=driver.capture()
                        partial['runtime']['fresh_game']=False
                        partial['runtime']['interventions']=[{'kind':'native-checkpoint-load','state_sha256':CHECKPOINT_SHA}]
                        if origin_reference is not None:partial['native_origin']=origin_reference
                        save(OUT/'partial-capture.private.json',partial)
                    retain('restored partial capture',retain_partial_capture)
                    report['trace_receipt']=driver.trace_receipt
                    if driver.distance_probe is not None:
                        report['retained_distance_proof']=driver.distance_probe.proof
                    if driver.quest_probe is not None:
                        report['retained_pickup_proof']=driver.quest_probe.proof
                    if driver.motion_probe is not None:
                        report['retained_motion_proof']=driver.motion_probe.record
                    retain('independent pre-teardown receipt',checkpoint_report)
    except BaseException as error:
        report.update(complete=False,restored_quest_complete=False)
        if primary is None:
            primary=error;report['error']={'type':type(error).__name__,'message':str(error)}
        elif error is not primary:
            report.setdefault('persistence_errors',[]).append({'operation':'native teardown',
                'type':type(error).__name__,'message':str(error)})
    finally:
        if driver is not None:
            # No guest execution: record all returned stops/input deliveries.
            report['inputs']=driver.inputs;report['journal']=driver.journal
            report['messages']=driver.messages
        for name,path in (('source',SOURCE),('game_copy',GAME)):
            try:report[name+'_post_manifest_matches']=manifest(path)==original
            except BaseException as error:report[name+'_post_manifest_error']=str(error)
        checks={
            'original_db_unchanged':lambda:digest(ORIGINAL_DB)==DB_SHA,
            'donor_capture_unchanged':lambda:digest(donor_capture)==donor_capture_sha,
            'donor_result_unchanged':lambda:digest(donor_result)==donor_result_sha,
            'backend_unchanged':lambda:digest(BACKEND)==prior['backend_sha256'],
            'frozen_hashes_unchanged':lambda:all(digest(CHECKOUT/name)==value for name,value in EXPECTED.items()),
        }
        for name,check in checks.items():
            try:report[name]=check()
            except BaseException as error:
                report[name]=False
                report.setdefault('persistence_errors',[]).append({'operation':name,
                    'type':type(error).__name__,'message':str(error)})
        intact=all(report.get(k) is True for k in ('source_post_manifest_matches','game_copy_post_manifest_matches',
            'original_db_unchanged','donor_capture_unchanged','donor_result_unchanged','backend_unchanged','frozen_hashes_unchanged'))
        if not intact:report['complete']=False;report['integrity_error']='Post-teardown integrity differs'
        if report.get('persistence_errors'):
            report.update(complete=False,restored_quest_complete=False)
            if primary is None:primary=RuntimeError('Diagnostic evidence persistence failed')
        if primary is None and intact and native_checks_complete:
            report.update(complete=True,restored_quest_complete=True)
        else:report.update(complete=False,restored_quest_complete=False)
        try:checkpoint_report()
        except BaseException as error:
            if primary is None:primary=error
    if primary is not None:raise primary
    require(intact,'Post-teardown integrity differs')

if __name__=='__main__':main()
