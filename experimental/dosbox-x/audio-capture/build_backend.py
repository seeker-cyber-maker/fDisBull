#!/usr/bin/env python3
"""Build a source-pinned optional mixer-capture backend in a new private workdir.

This does not download upstream source, modify an input checkout, install a
backend, or change the established stable/layers patch manifests.
"""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True,help='Existing local upstream Git source containing the pinned baseline commit')
    parser.add_argument('--work',type=Path,required=True,help='New private external build directory, after applicable storage admission')
    parser.add_argument('--variant',choices=['stable','layers'],default='stable')
    parser.add_argument('--jobs',type=int,default=4)
    args=parser.parse_args()
    original=args.source.expanduser().resolve();work=args.work.expanduser().resolve();repo=ROOT.parent.parent.resolve()
    if not original.is_dir() or work.exists() or not work.parent.is_dir() or work==repo or repo in work.parents:
        parser.error('source must exist; work must be new, have an existing parent, and lie outside the tool checkout')
    if not 1<=args.jobs<=16:parser.error('jobs must be in1..16')
    overlay=json.loads((ROOT/'audio-capture-manifest.json').read_text());base_root=ROOT if args.variant=='stable' else ROOT/'layers';base=json.loads((base_root/'source-manifest.json').read_text());binding=overlay['variants'][args.variant]
    if (base['baseline_commit']!=overlay['baseline_commit'] or sha(base_root/'headless-agent.patch')!=binding['base_patch_sha256'] or sha(base_root/'source-manifest.json')!=binding['base_manifest_sha256'] or sha(ROOT/'audio-capture.patch')!=overlay['patch_sha256']):
        parser.error('Source/patch binding changed; regenerate and requalify the overlay instead of guessing')
    work.mkdir();(work/'tmp').mkdir();source=work/'source';environment=dict(os.environ,TMPDIR=str(work/'tmp'));commands=[];started=time.monotonic()
    def run(command,cwd=work):
        commands.append(command)
        with (work/'BUILD.log').open('a') as log:
            log.write('COMMAND '+repr(command)+'\n');log.flush()
            subprocess.run(command,cwd=cwd,env=environment,stdout=log,stderr=subprocess.STDOUT,check=True)
    try:
        run(['git','clone','--shared','--no-checkout',str(original),str(source)])
        run(['git','checkout','--detach',overlay['baseline_commit']],source)
        run(['git','apply',str(base_root/'headless-agent.patch')],source)
        for row in base['source_files']:
            if sha(source/row['path'])!=row['sha256']:raise RuntimeError('Base source hash mismatch: '+row['path'])
        for name,expected in binding['before'].items():
            if sha(source/name)!=expected:raise RuntimeError('Overlay input hash mismatch: '+name)
        run(['git','apply',str(ROOT/'audio-capture.patch')],source)
        for row in binding['result_source_files']:
            if sha(source/row['path'])!=row['sha256']:raise RuntimeError('Overlay result hash mismatch: '+row['path'])
        run(['c++','-std=c++11','-Wall','-Wextra','-Werror','-I'+str(source/'include'),str(HERE/'tests/capture_buffer_tests.cpp'),'-o',str(work/'capture_buffer_tests')])
        run([str(work/'capture_buffer_tests')])
        run(['./autogen.sh'],source)
        run(['./configure','--enable-sdl2','--enable-debug=heavy','--enable-dosbox_agent','--disable-avcodec','--disable-libslirp','--disable-libfluidsynth'],source)
        run(['make','-j'+str(args.jobs)],source)
        binary=source/'src/dosbox-x';result=dict(status='passed',variant=args.variant,baseline_commit=overlay['baseline_commit'],base_patch_sha256=binding['base_patch_sha256'],overlay_sha256=overlay['patch_sha256'],source_result_hashes=binding['result_source_files'],backend=str(binary),backend_sha256=sha(binary),commands=commands,elapsed_seconds=round(time.monotonic()-started,3),native_runtime_tested=False,installed=False)
    except Exception as error:
        result=dict(status='failed',error=repr(error),commands=commands,elapsed_seconds=round(time.monotonic()-started,3),installed=False)
    (work/'BUILD-RESULT.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return 0 if result['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
