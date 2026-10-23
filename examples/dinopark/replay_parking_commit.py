#!/usr/bin/env python3
"""Replay the observed parking purchase from a user-owned pre-OK machine state.

This requires the exact local fixture documented in docs/PARKING_COMMIT.md.
It copies the input database through SQLite backup before adding observations.
No game, save, checkpoint, or database bytes are distributed with this script.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True,type=Path)
    parser.add_argument('--checkpoint',required=True,help='Pre-OK state artifact ID in the input project')
    parser.add_argument('--executable',required=True,type=Path)
    parser.add_argument('--game-dir',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path,help='New local evidence directory')
    parser.add_argument('--wheel',type=Path,help='Import this wheel using existing dependency environment')
    args=parser.parse_args()
    if args.wheel:
        sys.path.insert(0,str(args.wheel.resolve(strict=True)))
    import fdisbull
    from fdisbull import debugger
    from fdisbull.project import Project

    project=args.project.resolve(strict=True)
    backend=args.executable.resolve(strict=True)
    game=args.game_dir.resolve(strict=True)
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    # Copy committed database content without touching the original experiment.
    with sqlite3.connect(project.as_uri()+'?mode=ro',uri=True) as source:
        with sqlite3.connect(output/'parking.fdb') as target:
            source.backup(target)
    report={'result':'fail','package_version':fdisbull.__version__,'module':debugger.__file__,
            'backend_sha256':hashlib.sha256(backend.read_bytes()).hexdigest(),
            'input_project':str(project),'checkpoint':args.checkpoint}
    process=None
    try:
        with Project(output/'parking.fdb') as p, p.debugger(backend,game) as d:
            process=d.rpc.process
            report['run']=d.run_id
            report['restored']=d.load_state(args.checkpoint)
            d.run(guest_ms=120,timeout_ms=3000)
            report['before']=d.memory('0x471a6',length=8)
            report['pending_order']=d.memory('0x4bb14',length=8)
            assert report['before']['hex']=='0000000000000000','Unexpected live counter fixture'
            assert report['pending_order']['hex']=='0000000000000100','Expected one staged parking purchase'
            report['watch']=d.breakpoint('0x471ac',access='w',length=2)
            d.click(218,188,hold_ms=100)
            report['hit']=d.run(timeout_ms=3000)
            assert report['hit']['outcome']=='breakpoint',report['hit']
            access=report['hit']['session']['stop_reason']['data_access']
            assert access['project_instruction']=='0x14fcb' and access['length']==2,access
            report['after']=d.memory('0x471a6',length=8)
            assert report['after']['hex']=='0000000000000100','Parking counter did not commit'
            report['continuation']=d.trace('return.json',count=128,timeout_ms=3000)
            assert report['continuation']['metadata']['complete'],'Unexpected additional watch stop'
            assert report['continuation']['metadata']['run']['guest_elapsed_ms']==0
            p.debug_export(report['continuation']['artifact'],output/'return.json')
            # The copy is observed before the next completed video frame.
            d.run(guest_ms=1000,timeout_ms=3000)
            report['screenshot']=d.screenshot('after-ok.png')
            p.debug_export(report['screenshot']['artifact'],output/'after-ok.png')
        assert process.poll() is not None,'Emulator was not reaped'
        report['result']='pass'
    except Exception as exc:
        report['error']=str(exc)
        raise
    finally:
        report['process_reaped']=process is not None and process.poll() is not None
        (output/'replay.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'result':report['result'],'package_version':report['package_version'],
                      'process_reaped':report['process_reaped'],'output':str(output)}))


if __name__=='__main__':
    main()
