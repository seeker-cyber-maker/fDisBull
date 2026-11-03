"""Build a Python CHIP-8 UDC candidate using existing pilot observations.

Usage: PYTHONPATH=. python -m chip8_udc.cli --help
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from .compiler import compile_rom, write_module
from .verify import import_generated, drive


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('build','test','inspect'))
    p.add_argument('--rom',type=Path,required=True, help='Locally supplied licensed CHIP-8 program')
    p.add_argument('--output',type=Path,required=True, help='Private output directory (new on build)')
    p.add_argument('--name',default='udc_chip8')
    p.add_argument('--udc-catalog',type=Path,help='Optional immutable local registered swede rule index')
    p.add_argument('--observation-db',type=Path,help='Existing chip8lab pilot SQLite observation database')
    p.add_argument('--steps',type=int,default=1600)
    args=p.parse_args()
    rom=args.rom.read_bytes()
    if args.command=='build':
        source,manifest=compile_rom(rom,module_name=args.name,index_path=args.observation_db,steps=args.steps,catalog_path=args.udc_catalog)
        write_module(args.output,source,manifest)
        info={'output':str(args.output),'module':str(args.output/(args.name+'.py')),
              'source_sha256':manifest['source_sha256'],
              'specialized_sites':manifest['specialized_site_count'],
              'fallback_sites':len(manifest['fallback_sites']), 'next':'test'}
    elif args.command=='test':
        manifest=json.loads((args.output/'manifest.json').read_text())
        source=args.output/(manifest['module_name']+'.py')
        if hashlib.sha256(source.read_bytes()).hexdigest()!=manifest['generated_source_sha256']:
            raise ValueError('generated source changed: refuse stale verification')
        mod=import_generated(source)
        info=drive(mod,rom,budget=args.steps)
        (args.output/'local-check.json').write_text(json.dumps(info,sort_keys=True,indent=2)+'\n')
    else:
        manifest=json.loads((args.output/'manifest.json').read_text())
        info={'module':manifest['module_name'], 'source_sha256':manifest['source_sha256'],
              'observed_sites':manifest['observed_site_count'],
              'specialized_sites':manifest['specialized_site_count'],
              'fallback_families':manifest['fallback_family_count'],
              'manual_rules':manifest['manual_rules'],
              'verified_against':'pilot VM, not independent historical oracle'}
    print(json.dumps(info,sort_keys=True,indent=2))

if __name__=='__main__':main()
