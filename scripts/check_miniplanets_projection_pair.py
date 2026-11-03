#!/usr/bin/env python3
"""Compare every paired projection result with the retained full source tables.

Calls execute in the actual mapped NES cartridge. Debug command completion and
runtime faults are checked before accepting either coordinate. Original data,
generated cartridges and raw observations stay in a new private output folder.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from fdisbull.udl_miniplanets_full import checked_rom, globe_assets
from check_miniplanets_nes_game import patch, run_host, save
from check_miniplanets_native import _private_output
from verify_miniplanets_level import NES_SHA


def sha(raw):return hashlib.sha256(raw).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('rom','cartridge','core','output'):ap.add_argument('--'+name,required=True)
    args=ap.parse_args()
    rom_path=Path(args.rom).resolve();rom=checked_rom(rom_path.read_bytes())
    cartridge=Path(args.cartridge).resolve();core=Path(args.core).resolve()
    manifest_path=cartridge.with_name('manifest.json')
    manifest=json.loads(manifest_path.read_text())
    if sha(cartridge.read_bytes())!=manifest['rom_sha256'] or sha(core.read_bytes())!=NES_SHA:
        raise ValueError('Cartridge/core identity mismatch')
    procedure=manifest['debug']['projection_pair_procedure']
    assets=globe_assets(rom)
    cases=[(x,y,raft,assets[name][x*256+y]|assets[name][y*256+x]<<8)
           for raft,name in enumerate(('objects','rafts'))
           for x in range(64,193) for y in range(64,193)]
    out=_private_output(args.output);out.mkdir()
    inputs=(rom_path,cartridge,core,manifest_path,Path(__file__).resolve())
    before={str(p):sha(p.read_bytes()) for p in inputs}
    report={'format':'miniplanets-native-projection-pair-1','status':'running',
            'cartridge_sha256':manifest['rom_sha256'],'core_sha256':NES_SHA,
            'domain':'x,y64..192inclusive; object/raft, signed coordinate bits packed low/high',
            'cases_checked':0,'batches':[]}
    try:
        for start in range(0,len(cases),512):
            batch=cases[start:start+512]
            patches=[patch(10,2,0x7d4,b'\1'),patch(12,2,0x7d6,bytes((procedure,)))]
            for index,(x,y,raft,_) in enumerate(batch):
                at=30+index*4
                patches.extend((patch(at,2,0x7d9,b''.join(n.to_bytes(4,'little') for n in (x,y,raft))),
                                patch(at,2,0x7d5,b'\1')))
            receipt,trace,_=run_host(core,cartridge,out/f'batch-{start//512:03d}',
                34+len(batch)*4,[{'name':'debug','memory_id':2,'offset':0x7d0,'length':0x26}],patches=patches)
            for index,(x,y,raft,expected) in enumerate(batch):
                raw=bytes.fromhex(trace['frames'][30+index*4+3]['raw']['debug'])
                if raw[5] or raw[29]:raise AssertionError(f'Unfinished/faulted projection command:{start+index}')
                observed=int.from_bytes(raw[32:36],'little')
                if observed!=expected:raise AssertionError(f'Projection differs at{x,y,raft}:{observed}/{expected}')
            report['cases_checked']+=len(batch)
            report['batches'].append({'cases':len(batch),'trace_sha256':receipt['ram_trace_sha256']})
        report['inputs_unchanged']=before=={str(p):sha(p.read_bytes()) for p in inputs}
        if not report['inputs_unchanged']:raise AssertionError('Projection inputs changed')
        report['status']='passed'
    except Exception as error:
        report['failure']=str(error);report['status']='failed';raise
    finally:save(out/'receipt.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='batches'},indent=2))


if __name__=='__main__':main()
