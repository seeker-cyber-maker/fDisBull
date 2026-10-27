#!/usr/bin/env python3
"""0.18 scene acceptance; original files, checkpoints and databases stay private."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
import zipfile

from fdisbull import __version__
from fdisbull.project import Project
from verify_scenes import main as calibrate, inventory


def main(args):
    # Reuse the independently auditable NEW GAME route, clean-frame calibration,
    # mask/negative checks and real breakpoint/watchpoint/hook checks from 0.17.
    calibrate(args)
    out=args.output.resolve();evidence=args.evidence.resolve();database=out/'scene.fdb'
    def save(name,value):(evidence/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
    processes=[];game=out/'game';copied=inventory(game);original=inventory(args.game_dir)
    receipt=dict(version=__version__,scope='Local candidate, real private DinoPark NEW GAME and fresh native restore',
                 source_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    import fdisbull
    receipt['tool_module']=str(Path(fdisbull.__file__).resolve())
    receipt['framework_source_sha256']={n:hashlib.sha256((Path(fdisbull.__file__).parent/n).read_bytes()).hexdigest()
        for n in ('scenes.py','scene_geometry.py','scene_values.py','scene_bundles.py','debugger.py','debug_script.py','cli.py')}
    bundle=evidence/'office-scenes.zip'
    with Project(database) as p:
        first=p.debug_scene_info('office');doc=deepcopy(first['definition'])
        invariant={'memory':dict(address='0x471ac',type='u16')}
        for obj in doc['objects']:
            obj['ready']={'all':[deepcopy(obj['ready']) for _ in range(5)]}
            obj['outcome']={'all':[obj['outcome'],{'compare':dict(left=invariant,op='eq',right={'before':invariant})}]}
            obj['context']['relative_outcome']='Parking counter unchanged across navigation; visual destination independently required'
        saved=p.debug_save_scene('office',doc,parent=first['id'],author='0.18 acceptance')
        for name in ('bank','ledger'):
            old=p.debug_scene_info(name);doc=deepcopy(old['definition'])
            doc['objects'][0]['outcome']={'all':[doc['objects'][0]['outcome'],{'compare':dict(left=invariant,op='eq',right={'before':invariant})}]}
            p.debug_save_scene(name,doc,parent=old['id'],author='0.18 acceptance')
        checkpoint=p.db.execute("SELECT * FROM debug_artifacts WHERE kind='state' AND name='private-office.sav'").fetchone()
        state=dict(data=bytes(checkpoint['data']),metadata=json.loads(checkpoint['metadata']))
        with p.debugger(args.executable,game) as d:
            processes.append(d.rpc.process);d.load_state(checkpoint['id']);d.run(guest_ms=1000,timeout_ms=5000,fast_forward=True)
            calls=[];memory=d.memory
            def counted(*a,**kw):calls.append((a,kw));return memory(*a,**kw)
            d.memory=counted
            start=time.perf_counter();full=d.scene_check('office',object='office.bank');full_ms=(time.perf_counter()-start)*1000
            assert full['status']=='matched' and len(calls)==2,full
            start=time.perf_counter();compact=d.scene_check('office',object='office.bank',compact=True);compact_ms=(time.perf_counter()-start)*1000
            assert len(calls)==4 and compact['read_statistics']['unique_reads']==2
            retained=p.debug_scene_observation(compact['observation'])['result']
            assert full['frame']['state_revision']==retained['frame']['state_revision']
            receipt['observation']=dict(statistics=retained['read_statistics'],backend_calls_two_observations=len(calls),
                full_reply_bytes=len(json.dumps(retained).encode()),compact_reply_bytes=len(json.dumps(compact).encode()),
                full_call_ms=full_ms,compact_call_ms=compact_ms,scope='Two checks on one paused guest; compact and full sizes use the same retained observation')
            save('deduplicated-full',retained);save('deduplicated-compact',compact)
            raw=d.screenshot('numbered-office.png')
            overlay=p.debug_scene_overlay(saved['id'],artifact=raw['artifact'],labels='numbers')
            p.debug_export(overlay['artifact'],evidence/'office-numbered.png')
            p.debug_export(overlay['legend_artifact'],evidence/'office-legend.json');save('office-numbered.metadata',overlay)
            assert len(overlay['metadata']['legend'])==3
            receipt['numbered_overlay_sha256']=overlay['sha256']
            receipt['backend_sha256']=d.metadata['emulator_sha256']
        exported=p.debug_export_scenes(['office','bank','ledger'],bundle);save('bundle-export',exported)
        with zipfile.ZipFile(bundle) as archive:
            assert archive.testzip() is None
            assert all(n=='manifest.json' or (n.startswith('snapshots/') and n.endswith('.png')) for n in archive.namelist())
        receipt['bundle']=exported
    target=out/'independent.fdb'
    with Project.create(target,game/'DINOPARK.EXE',load_segment=0x1000) as p:
        imported=p.debug_import_scenes(bundle);save('bundle-import',imported)
        assert len(imported['scene_map'])==3
        assert p.debug_scene_info('office')['id']!=saved['id']
        private=p._debug_artifact(imported['run'],'private-office.sav','state',state['data'],state['metadata'])
        imported_id=p.debug_scene_info('office')['id']
        offline=p.debug_scene_overlay(imported_id,labels='numbers');offline_sha=offline['sha256']
    with Project(target) as p:
        assert p.debug_scene_overlay(imported_id,labels='numbers')['sha256']==offline_sha
        with p.debugger(args.executable,game) as d:
            processes.append(d.rpc.process);d.load_state(private['artifact'])
            assert d.scene_check(imported_id,compact=True)['status']=='unavailable'
            d.run(guest_ms=1000,timeout_ms=5000,fast_forward=True)
            assert d.scene_assert(imported_id,object='office.bank',compact=True)['status']=='matched'
            steps=[]
            for _ in range(2):
                for scene,obj in [('office','office.bank'),('bank','bank.back'),('office','office.ledger'),('ledger','ledger.back')]:
                    steps.append(dict(op='scene-click',scene=p.debug_scene_info(scene)['id'],object=obj,compact=True))
            script=dict(format='fdisbull-script-1',steps=steps);save('portable-navigation.script',script)
            stored=p.debug_save_script('portable navigation',script)
            result=d.script(script_id=stored['script_id'],timeout_ms=120000);save('portable-navigation.result',result)
            assert result['ok'],result
            observations=p.debug_scene_observations(run=d.run_id,limit=1000);save('portable-observations',observations)
            outcomes=[o['result'] for o in observations['observations'] if o['result'].get('action_object')]
            assert len(outcomes)==8 and all(o['complete'] and o['baseline']['values'] for o in outcomes)
            assert len({o['baseline']['observation'] for o in outcomes})==8
            frame=d.screenshot('portable-office.png');p.debug_export(frame['artifact'],evidence/'portable-office.png')
            trace=d.trace('portable-navigation.trace.json',count=128,timeout_ms=10000)
            assert trace['metadata']['complete'];p.debug_export(trace['artifact'],evidence/'portable-navigation.trace.json')
            receipt['relative_checks']=dict(actions=8,fresh_baselines=8,condition='u16 parking counter equals its own pre-action value AND destination pixels match',
                limitation='Navigation invariant; increment/decrement and wrap arithmetic are separately tested with an authored native guest')
    assert inventory(args.game_dir)==original and inventory(game)==copied
    assert all(p.poll() is not None for p in processes)
    receipt.update(ok=True,processes_reaped=True,original_files_unchanged=len(original),private_files_unchanged=len(copied),
                   scene_bundle_native_rechecked=True,offline_overlay_restart_identical=True,private_state_in_bundle=False,
                   preserved_stops=['breakpoint','watchpoint','hook'],game_files_states_databases_in_evidence=False)
    save('IMPROVEMENTS-VERIFICATION',receipt);save('SHA256SUMS',inventory(evidence))
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('executable','game-dir','output','evidence'):parser.add_argument('--'+name,type=Path,required=True)
    main(parser.parse_args())
