"""Private, fresh-process static acceptance on a caller-selected Cortex-M image.

No input bytes or listing are emitted in the compact receipt. Databases and
images are written only to the explicitly selected directory outside this repo.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('--base',type=lambda value:int(value,0),required=True)
    parser.add_argument('--vector-count',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    out=args.output.resolve()
    if out==repo or repo in out.parents:
        parser.error('private output must be outside this repository')
    out.mkdir(parents=True,exist_ok=False)
    original=args.input.resolve();before=hashlib.sha256(original.read_bytes()).hexdigest()
    source=out/'input.bin';shutil.copy2(original,source)
    db=out/'firmware.fdb';env=dict(os.environ,PYTHONPATH=str(repo/'src'))
    operations=[]

    def call(method,**params):
        result=subprocess.run([sys.executable,'-m','fdisbull','request',json.dumps(dict(method=method,params=params))],
                              env=env,text=True,capture_output=True,timeout=120,check=True)
        reply=json.loads(result.stdout)
        if not reply.get('ok'):
            raise RuntimeError(reply)
        operations.append(dict(method=method,params=params,result=reply['result']))
        (out/'operations.json').write_text(json.dumps(operations,indent=2)+'\n')
        return reply['result']

    def analyze(version):
        for _ in range(20):
            run=call('analyze',project=str(db),version=version,max_instructions=2000)
            if run['stable']:
                return run
        raise RuntimeError('native analysis budget exhausted; not a stable qualification')

    imported=call('import',project=str(db),path=str(source),profile='cortex-m',base=args.base,vector_count=args.vector_count)
    entry=int(imported['entry'],16)
    budget=call('analyze',project=str(db),max_instructions=1)
    assert not budget['stable'] and budget['budget_exhausted']
    analyze(1)
    info=call('info',project=str(db),version=1)
    call('rename',project=str(db),address=entry,name='qualified_reset',author='cortex-m-verifier')
    call('comment',project=str(db),address=entry,text='Static reset-vector candidate; no target execution observed.',author='cortex-m-verifier')
    parent=call('disasm',project=str(db),version=1,address=entry,lines=8)
    first=parent['instructions'][0]['bytes']
    source.rename(out/'input.preserved.bin')
    restarted=call('disasm',project=str(db),version=1,address=entry,lines=8)
    assert restarted==parent
    for format in ('png','svg'):
        call('render',project=str(db),version=1,address=entry,lines=8,output=str(out/f'reset.{format}'),format=format)
    call('render-cfg',project=str(db),version=1,address=entry,output=str(out/'reset-cfg.svg'))
    child=call('patch',project=str(db),version=1,address=entry,data='00bf',label='private-static-NOP-control')['version']
    analyze(child)
    assert call('disasm',project=str(db),version=1,address=entry,lines=1)['instructions'][0]['bytes']==first
    assert call('disasm',project=str(db),version=child,address=entry,lines=1)['instructions'][0]['bytes']=='00bf'
    number=lambda value:int(value,0) if isinstance(value,str) else value
    alternate=next(number(v['address']) for v in info['cortex_m']['vectors'] if v['valid'] and number(v['address'])!=entry)
    vector_child=call('patch',project=str(db),version=1,address=args.base+4,
                      data=(alternate|1).to_bytes(4,'little').hex(),label='private-reset-vector-control')['version']
    analyze(vector_child)
    assert call('status',project=str(db),version=vector_child)['entry']==hex(alternate)
    assert call('status',project=str(db),version=1)['entry']==hex(entry)
    status=call('status',project=str(db),version=1)
    after=hashlib.sha256(original.read_bytes()).hexdigest();assert before==after
    from PIL import Image
    with Image.open(out/'reset.png') as image:
        image.load();dimensions=image.size
    receipt=dict(scope='Cortex-M static native queues; not full code recovery or device behavior',
                 source_sha256=before,source_bytes=original.stat().st_size,base=hex(args.base),
                 vector_count=args.vector_count,entry=hex(entry),initial_sp=hex(number(info['cortex_m']['initial_sp'])),
                 valid_vector_candidates=sum(v['valid'] for v in info['cortex_m']['vectors']),
                 counts=status['counts'],native_stable=status['analysis']['stable'],issues=status['analysis']['issues'],
                 budget_stop_not_stable=True,fresh_process_restart_without_source=True,
                 parent_bytes_preserved=True,child_patch_isolated=True,vector_patch_reseeded=True,
                 annotation_preserved=restarted['instructions'][0]['name']=='qualified_reset',
                 stored_png_dimensions=dimensions,stored_svg=True,stored_cfg=True,original_input_unchanged=True,
                 target_execution=False,operation_count=len(operations))
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':
    main()
