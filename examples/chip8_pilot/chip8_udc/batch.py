"""One-command multi-program UDC compilation and bounded tool-friction audit.

Uses the existing CHIP-8 pilot ROM manifest and observation DB. No web fetch.
Generated Python modules are source-independent adapters; ROM input stays local.
"""
from __future__ import annotations
from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import sys
from .compiler import compile_rom, write_module
from .verify import import_generated, drive
from .swedes import SWEDES
from chip8lab.pilot import SEMANTIC_ROLES

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus',type=Path,default=ROOT/'corpus')
    p.add_argument('--observation-db',type=Path,default=None)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--budget',type=int,default=1600)
    p.add_argument('--udc-catalog',type=Path,help='Pinned local UDC rule registry snapshot')
    args=p.parse_args()
    if args.output.exists():raise FileExistsError('refusing to overwrite audit output directory')
    args.output.mkdir(parents=True)
    manifest=json.loads((ROOT/'corpus/manifest.json').read_text())
    results=[];missing=[];total=Counter();families=Counter();missing_impact=Counter();missing_sources={}
    for entry in manifest['programs']:
        if entry['platform']!='chip8':
            missing.append({'program':entry['key'],'reason':'unsupported dialect '+entry['platform']})
            continue
        path=args.corpus/(entry['key']+'.ch8')
        if not path.is_file():
            missing.append({'program':entry['key'],'reason':'ROM not available locally; explicit corpus fetch required'})
            continue
        raw=path.read_bytes()
        if len(raw)!=entry['size'] or hashlib.sha256(raw).hexdigest()!=entry['sha256']:
            raise ValueError('corpus identity mismatch '+entry['key'])
        name='udc_'+entry['key'].lower()
        source, doc=compile_rom(raw,module_name=name,index_path=args.observation_db,steps=args.budget,catalog_path=args.udc_catalog)
        directory=args.output/entry['key']
        write_module(directory,source,doc)
        generated=import_generated(directory/(name+'.py'))
        receipt=drive(generated,raw,budget=args.budget)
        (directory/'local-check.json').write_text(json.dumps(receipt,sort_keys=True,indent=2)+'\n')
        results.append({'program':entry['key'],'source_sha256':entry['sha256'],
                        'candidate_sites':doc['observed_site_count'],
                        'specialized_sites':doc['specialized_site_count'],
                        'fallback_sites':len(doc['fallback_sites']),
                        'manual_rules_used':sorted(doc['sweded_families_observed']),
                        'fallback_families':doc['fallback_family_count'],
                        'run':receipt,'source_output_sha256':doc['generated_source_sha256']})
        families.update(doc['sweded_families_observed'])
        for item in doc['fallback_sites']:
            family=item['family']
            if item['reason']=='manual_swede_or_VM_fallback_required':
                missing_impact[family]+=item['observed_count']
                missing_sources.setdefault(family,set()).add(entry['key'])
        total.update({'specialized_steps':receipt['specialized_steps'],
                      'fallback_steps':receipt['fallback_steps'],
                      'attempts':receipt['completed_attempts'],
                      'specialized_sites':doc['specialized_site_count'],
                      'fallback_sites':len(doc['fallback_sites'])})
    swede_work=[{'family':name,'reported_uil_intent_candidate':SEMANTIC_ROLES.get(name,'unresolved'),
                 'observed_instruction_attempts':impact,'programs':sorted(missing_sources[name]),
                 'next_action':'agent_swede_and_qualify_python_udc_rule',
                 'status':'unqualified_semantic_candidate_and_missing_python_rule',
                 'qualification_boundary':'preserve exact CHIP-8 VM state, traps, quirk policy; compare to pilot VM then independent emulator'}
                for name,impact in sorted(missing_impact.items(),key=lambda v:(-v[1],v[0]))]
    summary={'format':'fdisbull-chip8-python-udc-audit-1',
             'kind':'bounded same-VM differential experiment',
             'corpus_source_commit':manifest['source_commit'],
             'programs':results,'omitted':missing,
             'rule_catalog_source':'private SQLite rule registry (path omitted)' if args.udc_catalog else 'trusted Python template catalog (no SQLite)',
             'manual_rule_catalog_size':len(SWEDES),
             'manual_rule_catalog':sorted(SWEDES),
             'new_sweding_work_packets':swede_work,
             'actually_used_swedes':dict(sorted(families.items())),
             'totals':dict(total),
             'tool_first_process':['read CHIP-8 pilot manifest and SHA256','query existing observed instruction index',
                                    'classify using chip8lab.decoder',
                                    'reuse unqualified chip8lab.pilot intent labels',
                                    'substitute already-written Python UDC rules',
                                    'emit exact PC+word guarded Python code',
                                    'run same-VM bounded state differential',
                                    'record fallback obligations and receipts'],
             'manual_work':['author and review reusable swede templates once',
                            'choose VM fallback for missing complex semantics',
                            'select fixed host timing/key/RNG policy',
                            'provide/share only licensed ROMs and review outputs'],
             'not_claimed':['accepted fdisbull-common-uil-1 source semantics',
                            'independent emulator/hardware equivalence',
                            'full input, interactive or whole-game coverage',
                            'untrusted plugin execution or compiler safety',
                            'public UDC registry admission or code sharing rights']}
    (args.output/'batch-audit.json').write_text(json.dumps(summary,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'programs':len(results),'excluded':len(missing),
                      'rule_catalog_source':'private SQLite rule registry (path omitted)' if args.udc_catalog else 'trusted Python template catalog (no SQLite)',
             'manual_rule_catalog_size':len(SWEDES),
                      'used_rule_families':len(families),'totals':dict(total),
                      'audit':str(args.output/'batch-audit.json')},sort_keys=True,indent=2))

if __name__=='__main__':main()
