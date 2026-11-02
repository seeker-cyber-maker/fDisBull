"""One restored dragon boundary diagnostic; never a fresh-game claim."""
from hashlib import sha256
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import shutil
import argparse

from fdisbull.project import Project
from examples.agi.spatial_trial import PROFILES, WRITER, find, manifest, read, require
from examples.agi.verify_dragon_mirror import DragonRun, DEPENDENCIES as DRAGON_DEPENDENCIES
from examples.agi.dragon_probes import DragonWaterProbe
from examples.agi.dragon_inside_probe import InsideWaterProbe

CHECKOUT=Path(__import__("examples.agi.verify_dragon_mirror",fromlist=["__file__"]).__file__).resolve().parents[2]
PRIVATE_FILES=(Path(__file__).resolve(),Path(__file__).with_name("dragon_inside_probe.py").resolve())
DEPENDENCIES=DRAGON_DEPENDENCIES

CPU_FIELDS=('cpu_mode','general','segments','instruction_pointer','flags')
def cpu_equal(a,b):
    return all(k in a and k in b and type(a[k]) is type(b[k]) and a[k]==b[k] for k in CPU_FIELDS)

def digest(path):return sha256(path.read_bytes()).hexdigest()
def save(path,value):path.write_text(json.dumps(value,indent=2,default=str)+'\n')

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','backend','project','artifact','source-capture','source-result','output'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--target-y',required=True,type=int,choices=(166,167))
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
    DB_SHA=digest(ORIGINAL_DB);EXPECTED={name:digest(CHECKOUT/name) for name in DEPENDENCIES};PRIVATE_EXPECTED={str(path):digest(path) for path in PRIVATE_FILES}
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
    require(prior.get('normal_dragon_mirror_complete') is True and prior.get('post_teardown_source_unchanged') is True and
            prior.get('post_teardown_copy_unchanged') is True and len(checkpoints)==1 and
            checkpoints[0].get('sha256')==CHECKPOINT_SHA and checkpoints[0].get('loaded') is False and
            type(checkpoints[0].get('guest_ms')) in (int,float) and
            checkpoints[0]['guest_ms']==donor['observations']['dragon-before']['guest_ms'] and
            donor['runtime'].get('policy')=='physical' and donor['runtime'].get('fresh_game') is True and
            donor['runtime'].get('interventions')==[] and donor['source']['agi_sha256']==digest(SOURCE/'AGI') and
            donor['source']['object_sha256']==digest(SOURCE/'OBJECT'), 'Donor checkpoint provenance differs')
    source_state=donor['observations']['dragon-before']['state']
    OUT.mkdir()
    shutil.copyfile(donor_capture,OUT/'origin-source-capture.private.json')
    shutil.copyfile(donor_result,OUT/'origin-source-result.private.json')
    require(digest(OUT/'origin-source-capture.private.json')==donor_capture_sha and
            digest(OUT/'origin-source-result.private.json')==donor_result_sha,'Donor evidence copy differs')
    report={'format':'fdisbull-restored-dragon-boundary-diagnostic-1','fresh_game':False,
        'scope':'One restored dragon-before checkpoint, ordinary inputs, and one boundary test; not a fresh game.',
        'checkpoint_id':CHECKPOINT_ID,'checkpoint_sha256':CHECKPOINT_SHA,'original_db_sha256':DB_SHA,
        'source_manifest':original,'backend_sha256':digest(BACKEND),'dependency_sha256':EXPECTED,'private_dependency_sha256':PRIVATE_EXPECTED,'observations':[],
        'checkpoint_loads_attempted':0,'complete':False,'restored_boundary_complete':False}
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
                report['post_load_registers']=post
                report['post_load_receipt']=restored
                checkpoint_report()
                require(cpu_equal(post,saved_metadata['registers']) and cpu_equal(restored['registers'],post) and
                        post['cpu_mode']=='real' and int(post['segments']['cs'],16)==int(regs['segments']['cs'],16) and
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
                driver=DragonRun(p,d,report,frame,SOURCE,OUT)
                require(driver._idle() and driver.watch is None and not driver.trace_active,'Restored keyboard not settled')
                require(cpu_equal(saved_metadata['registers'],restored['registers']),'Restored CPU differs')
                initial=driver.state()
                def contains(actual, expected):
                    if isinstance(expected,dict):return isinstance(actual,dict) and all(k in actual and contains(actual[k],v) for k,v in expected.items())
                    return type(actual) is type(expected) and actual==expected
                require(contains(initial,source_state),'Restored state differs from donor observation')
                report['initial_restored_state']=initial
                require(initial['room']==51 and initial['score']==15 and initial['water_carried'] and
                    initial['quest_variables']['75']==0 and not initial['quest_flags']['20'] and
                    initial['ego']['direction']==0 and driver._idle(),'Restored branch preconditions differ')
                checkpoint_report()
                driver.type_text('throw water')
                driver.precise(x=130)
                driver.precise(y=args.target_y)
                driver.observe_clip('boundary-launch')
                s=driver.clip_observations['boundary-launch']['state'];report['launch_observation']=driver.clip_observations['boundary-launch'];checkpoint_report()
                require(s['room']==51 and s['score']==15 and s['ego']['x']==130 and
                    s['ego']['y']==args.target_y and s['ego']['direction']==0 and not s['quest_flags']['20'] and
                    s['water_carried'] and s['quest_variables']['75']==0 and driver._idle(),
                    'Exact neutral requested boundary not observed')
                driver.water_probe=(InsideWaterProbe(driver) if args.target_y==166 else DragonWaterProbe(driver))
                driver.water_probe.start()
                try:
                    driver.press('enter',300,hold_ms=1,gap_ms=1)
                    end=driver.guest_elapsed+1000
                    while driver.water_probe.active:
                        driver.safe_state();require(driver.guest_elapsed<end,'Water branch observation budget exceeded')
                        driver.advance(min(20,end-driver.guest_elapsed))
                    require(driver.water_probe.proof.get('complete') is True and driver.water_probe.proof.get('status')=='verified','Water transaction incomplete')
                except BaseException as error:
                    if driver.water_probe.active and not driver.water_probe.failed:driver.water_probe._fail(error,'controller')
                    raise
                expected_offset=0x429 if args.target_y==166 else 0x45e
                require(any(z.get('logic')==51 and z.get('source_offset')==expected_offset and z.get('message_id')==(33 if args.target_y==166 else 34) and z.get('status')=='completed' for z in driver.messages),'Original message not complete')
                report['water_proof']=driver.water_probe.proof
                driver.observe_clip('boundary-outcome')
                outcome=driver.clip_observations['boundary-outcome'];report['outcome_observation']=outcome
                after=outcome['state']
                require(after['room']==51 and after['score']==(13 if args.target_y==166 else 20) and not after['water_carried'] and not after['quest_flags']['88'],
                    'Outcome snapshot disagrees with completed transaction')
                report['scope']='One restored checkpoint; no fresh-game or throw-distance claim.'
                native_checks_complete=True
                report['stop']='boundary outcome complete';checkpoint_report()
            except BaseException as error:
                if primary is None:primary=error
                report.update(complete=False,restored_boundary_complete=False)
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
                    if driver.water_probe is not None:
                        report['retained_water_proof']=driver.water_probe.proof
                    retain('independent pre-teardown receipt',checkpoint_report)
    except BaseException as error:
        report.update(complete=False,restored_boundary_complete=False)
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
            'frozen_hashes_unchanged':lambda:all(digest(CHECKOUT/name)==value for name,value in EXPECTED.items()) and all(digest(Path(name))==value for name,value in PRIVATE_EXPECTED.items()),
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
            report.update(complete=False,restored_boundary_complete=False)
            if primary is None:primary=RuntimeError('Diagnostic evidence persistence failed')
        if primary is None and intact and native_checks_complete:
            report.update(complete=True,restored_boundary_complete=True)
        else:report.update(complete=False,restored_boundary_complete=False)
        try:checkpoint_report()
        except BaseException as error:
            if primary is None:primary=error
    if primary is not None:raise primary
    require(intact,'Post-teardown integrity differs')

if __name__=='__main__':main()
