"""Run bounded original x86 helper probes using private caller-supplied inputs.

Linux x86-64, ptrace compatibility execution, gcc and installed fDisBull are
required. No DOS guest is launched and no original instruction is patched.
Raw observations remain in the new private workspace, never inside Git.
"""
import argparse,hashlib,json,os,shutil,struct,subprocess,sys
from pathlib import Path
from campaign import MAIN_SHA256,SECTIONS,decode_save


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--main',type=Path,required=True);ap.add_argument('--save',type=Path,required=True)
    ap.add_argument('--workspace',type=Path,required=True)
    ap.add_argument('--case',choices=['ret','admission','weapon-completion','mod-completion','save-prefix'],required=True)
    ap.add_argument('--territory',type=int,default=9);ap.add_argument('--cash',type=int,default=30001)
    args=ap.parse_args();root=args.workspace.absolute()
    if root.exists() or any((p/'.git').exists() for p in [root,*root.parents]):
        raise ValueError('Use a new private workspace outside Git')
    original=args.main.read_bytes()
    if hashlib.sha256(original).hexdigest()!=MAIN_SHA256:raise ValueError('Wrong original MAIN')
    seed=args.save.read_bytes();decode_save(seed,source_sha256=MAIN_SHA256)
    root.mkdir(parents=True,mode=0o700)
    from fdisbull.le import load_le
    image=load_le(original);manifest={'original_sha256':MAIN_SHA256,'regions':{}}
    for region in image.regions:
        data=bytes(region.data);(root/f'region-{region.start:x}.bin').write_bytes(data)
        manifest['regions'][hex(region.start)]={'sha256':hashlib.sha256(data).hexdigest(),'size':len(data)}
    (root/'region-manifest.json').write_text(json.dumps(manifest,indent=2))
    source=Path(__file__).with_name('slice_loader64.c')
    subprocess.run(['gcc','-O2','-Wall','-no-pie',str(source),'-o',str(root/'slice_loader64')],check=True,capture_output=True)
    os.environ['SYNDICATE_PRIVATE']=str(root)
    from probe_cpu64 import run
    writes={address:seed[offset:offset+size] for _,offset,size,address in SECTIONS}
    writes.update({0x60b16:bytes(2),0x5539a:bytes(1)})
    stop=()
    if args.case=='ret':entry=0x3d640
    elif args.case=='admission':
        if not 0<=args.territory<50:raise ValueError('Territory outside selected edition')
        entry=0x28d60;writes[0x200ff04]=struct.pack('<I',args.territory)
    elif args.case=='save-prefix':
        if not 0<=args.cash<=0xffffffff:raise ValueError('Cash outside u32')
        entry=0x38420;stop=(0x38470,);company=bytearray(writes[0x5e49c]);struct.pack_into('<I',company,0,args.cash);writes[0x5e49c]=company
    else:
        kind,index,base=(2,4,4) if args.case=='weapon-completion' else (1,1,185)
        active=bytearray(489);active[1]=kind;active[2]=index
        struct.pack_into('<iH',active,3,9,base);struct.pack_into('<23H',active,9,*range(100,2400,100));writes[0x55594]=active
        company=bytearray(writes[0x5e49c]);struct.pack_into('<I',company,0,30000);writes[0x5e49c]=company
        entry=0x35e20
    out=run(entry,writes=writes,observe=[(address,size) for _,_,size,address in SECTIONS],
            stop_at=stop,max_steps=20000,seconds=30)
    (root/'original-observation.json').write_text(json.dumps(out,indent=2)+'\n')
    summary={'case':args.case,'reason':out['reason'],'steps':out['steps'],'execution':out['execution'],
             'original_sha256':MAIN_SHA256,'not_DOS':True,'original_inputs_modified':False}
    if args.case.endswith('completion') and out['reason']=='returned':
        w2={int(address,16):bytes.fromhex(value['after']) for address,value in out['observations'].items()}
        w2[0x60b16]=bytes(2)
        final=run(0x36190,writes=w2,observe=[(address,size) for _,_,size,address in SECTIONS],max_steps=20000,seconds=30)
        (root/'finalizer-observation.json').write_text(json.dumps(final,indent=2)+'\n')
        summary['finalizer_reason']=final['reason']
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
    return 0 if out['reason'] in ('returned','selected_stop') else 1

if __name__=='__main__':raise SystemExit(main())
