"""Read-only cross-format structural discovery with compact investigation venues.

Run after the existing intake/extraction step. No game identity is required.
All detailed output is private and remains candidate evidence, not playable UIL.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import time
import stat

from . import __version__
from .structure_patterns import canonical, match_graph, RULES
from .structure_events import SELECTOR_RULE
from .structure_tables import record_candidates, pointer_string_tables
from .structure_native import native_views, native_facts
from .structure_vm import agi_facts, z_catalog, z_facts


def _lead(pattern, title, source, evidence, why, next_probe, limitations, rank):
    identity=canonical({'pattern':pattern,'source':source['sha256'],'evidence':evidence})
    return {'id':'lead-'+sha256(identity.encode()).hexdigest()[:20], 'pattern':pattern,
            'title':title,'source':source,'evidence':evidence,'why':why,
            'next_probe':next_probe,'limitations':limitations,'rank':rank,
            'status':'candidate','runtime_observed':False,'execution_authorized':False}


def scan_directory(root, *, max_files=3000, max_file_bytes=32*1024*1024,
                   max_total_bytes=64*1024*1024, max_instructions=30000,
                   max_native=8, max_matches=5000, candidate_functions=False,
                   max_console_views=8, console_profile=None):
    """Return deterministic findings; timings belong to the caller's receipt.

    Reuses AGI census and native instruction decoder. Paths identify inputs but
    never select game-specific algorithms. Unanalyzed files and code are explicit.
    """
    for label,value,hi in [('max_files',max_files,10000),('max_file_bytes',max_file_bytes,64*1024*1024),
                           ('max_total_bytes',max_total_bytes,256*1024*1024),('max_instructions',max_instructions,100000),
                           ('max_native',max_native,32),('max_matches',max_matches,20000)]:
        if type(value) is not int or not 1<=value<=hi:raise ValueError(f'{label} outside 1..{hi}')
    if type(candidate_functions) is not bool:raise ValueError('candidate_functions must be Boolean')
    if type(max_console_views) is not int or not 1<=max_console_views<=64:
        raise ValueError('max_console_views outside 1..64')
    from .structure_inputs import snapshot_inputs, verify_snapshots
    root,snapshots,manifest,originals,skipped,file_limit,total,path_count=snapshot_inputs(
        root,max_files=max_files,max_file_bytes=max_file_bytes,max_total_bytes=max_total_bytes)
    profiles={}
    if console_profile is not None:
        from .structure_intents import read_json
        config=read_json(console_profile)
        if not isinstance(config,dict) or set(config)!={'sources'} or not isinstance(config['sources'],dict):
            raise ValueError('console profile needs source-hash-keyed views')
        profiles=config['sources']
        if set(profiles)-{x['sha256'] for x in manifest}:raise ValueError('console profile source not present in inputs')
    source_map={x['path']:x for x in manifest}
    findings=[];producers=[];issues=[];native_queue=[];agi_dirs=set()
    for rel,data in sorted(snapshots.items()):
        src=source_map[rel];path=Path(rel)
        if root.is_dir() and '!' not in rel and path.name.upper()=='LOGDIR':agi_dirs.add(path.parent)
        if data[:4] in (b'IWAD',b'PWAD'):
            from .structure_wad import inspect_wad
            try:wad=inspect_wad(data)
            except ValueError as exc:
                issues.append({'source':rel,'producer':'classic-wad','error':str(exc)});continue
            findings.append(_lead('indexed-resource-directory','An ordered resource directory supplies named, source-bound members',src,
                {'container':wad['container'],'directory_offset':wad['directory_offset'],'entries':len(wad['directory']),
                 'duplicate_names':wad['duplicate_names'],'map_markers':wad['map_markers'],'decoded_maps':len(wad['maps'])},
                ['Validated file and directory extents; duplicate names and directory order retained.'],
                'Follow member consumers and namespace precedence. Select one map definition and inspect its linked record families.',
                ['A container index is not a renderer, interpreter or live scene. No cross-WAD override set was supplied.'],99))
            for scene in wad['maps']:
                findings.append(_lead('linked-scene-records','Linked geometric and entity-definition tables form a scene draft',src,
                    scene,['Format-profile strides and selected index references were checked without title-specific offsets.'],
                    'Inspect special/tag consumers and difficulty-dependent spawn rules. Qualify one interaction, then apply its shared handler contract to compatible definitions.',
                    ['Sectors are not automatically rooms. Adjacency is not walkability; special/tag equality is not an event contract; static things are not active entities.','Reference errors remain explicit. BSP, collision and runtime script effects are not reconstructed.'],96))
            producers.append({'source':src,'producer':'classic-wad-linked-records',
                'coverage':{'directory_entries':len(wad['directory']),'map_markers':wad['map_markers'],'decoded_maps':len(wad['maps']),
                            'decoded_record_positions':wad['decoded_record_positions']},'unresolved':wad['unresolved']})
            continue
        from .structure_console import inspect_console
        from .structure_handoffs import inspect_handoffs
        console=inspect_console(data,max_instructions=max_instructions,max_views=max_console_views,
                                max_matches=max_matches,explicit=profiles.get(src['sha256']))
        if console is not None:
            findings.append(_lead('console-execution-context','Console code needs an explicit execution and input context',src,
                {'platform':console['header']['platform'],'metadata':console['header']['metadata'],
                 'views_scanned':len(console['views']),'diagnostics':console['diagnostics']},
                ['Content-identified ROM container; fixed source/CPU views; processor width and bank frontiers retained.'],
                'Inspect reset/input/interrupt roots. Resolve any mapping or width frontier before following the next operation. Do not equate a bank change with a scene change.',
                ['Mapping views are static candidates, not runtime observations. Peripheral identity and input acceptance remain unqualified.'],99))
            for match in console.pop('findings'):
                match['source']=src;findings.append(match)
            for view in console['views']:
                accesses=view.pop('accesses')
                links=inspect_handoffs(accesses)
                for finding in links.pop('findings'):
                    finding['source']=src;findings.append(finding)
                view['handoff_coverage']=links
            producers.append({'source':src,'producer':'console-contextual-facts',**console})
            continue
        if len(data)>=64 and data[0] in (3,5):
            try:cat=z_catalog(data)
            except ValueError:pass
            else:
                findings.append(_lead('vm-dictionary','A bounded VM dictionary supplies lexical candidates',src,
                    {k:v for k,v in cat['dictionary'].items() if k!='entries'},['Header, checksum, record extents and encoded order agree.'],
                    'Follow consumers of dictionary-entry metadata and parse-buffer entries; separate word recognition from command grammar.',
                    ['Game-specific metadata is opaque. Recognized words are not all accepted commands.'],98))
                findings.append(_lead('vm-entity-graph','An object directory contains persistent IDs, links and properties',src,
                    {k:v for k,v in cat['objects'].items() if k!='rows'},['Directory extent and property pointers checked; links retained.'],
                    'Resolve property and attribute consumers, then classify selected entities before composing scenes.',
                    ['Object count uses the stated contiguous-layout inference; object IDs are not automatically rooms or visible items.'],97))
                n,e,c=z_facts(data,cat,max_instructions=max_instructions);m=match_graph(n,e,rules=RULES+(SELECTOR_RULE,),max_matches=max_matches)
                for match in m['matches']:match['source']=src
                findings+=m['matches']
                producers.append({'source':src,'producer':'z-machine-core','version':cat['version'],'catalogue':cat,
                                  'coverage':c,'match_budget_exhausted':m['match_budget_exhausted'],
                                  'work_budget_exhausted':m['work_budget_exhausted'],'join_work':m['join_work']})
                continue
        if data[:2]==b'MZ':
            native_queue.append((rel,data));continue
        # Data candidates do not require known file extensions or record lengths.
        if 32<=len(data)<=512*1024:
            for rec in record_candidates(data):
                findings.append(_lead('labelled-record-array','Repeated padded labels suggest a record population',src,rec,
                    [f"{rec['label_count']} labels align to stride {rec['stride']}; {rec['adjacent_spacing_witnesses']} adjacent spacings."],
                    'Find the file reader or indexed consumer; distinguish record positions from occupied entities and test competing strides.',
                    ['Spacing and divisibility are candidates, not a recovered field schema or live roster. Multiples can also fit.'],rec['rank']))
    # Reuse the installed format-family reader. Never label the filename as a game.
    from .agi_scenes import inspect_scenes
    for rel_dir in sorted(agi_dirs):
        try:
            for entry in (root/rel_dir).iterdir():
                name=entry.name.upper()
                if name in ('LOGDIR','PICDIR','VIEWDIR','SNDDIR','WORDS.TOK','OBJECT') or name.startswith('VOL.'):
                    if entry.is_symlink() or entry.relative_to(root).as_posix() not in snapshots:
                        raise ValueError('AGI resource is outside admitted snapshots: '+entry.name)
            census=inspect_scenes(root/rel_dir,profile='2.917',include_ir=True,include_text=True)
            # The census reopens resources: verify the inventoried snapshots still match.
            for rel,data in snapshots.items():
                if Path(rel).parent==rel_dir and (root/rel).read_bytes()!=data:raise ValueError('AGI input changed during analysis')
            n,e,c=agi_facts(census);m=match_graph(n,e,rules=RULES+(SELECTOR_RULE,),max_matches=max_matches)
            for match in m['matches']:
                match['source']={'path':rel_dir.as_posix(),'sha256':census['sha256']}
            findings+=m['matches']
            coverage=census['coverage'];v=census['vocabulary'];src={'path':rel_dir.as_posix(),'sha256':census['sha256']}
            findings.append(_lead('dictionary-guard-census','Vocabulary groups are used in executable script conditions',src,
                {k:coverage[k] for k in ('decoded_logics','command_patterns','vocabulary_groups','vocabulary_entries','inventory_objects','scene_candidates')},
                ['Existing AGI resource/layout/IR readers connect vocabulary groups to said conditions.'],
                'Choose a retained said guard; test matching groups, a near miss and input-consumed state. Inspect its other ordered predicates and effects.',
                ['2.917 is an analysis profile, not a newly established exact interpreter version. Scene candidates are not executable scenes.'],100))
            producers.append({'source':src,'producer':'agi-existing-census','coverage':coverage,'fact_coverage':c,
                              'match_budget_exhausted':m['match_budget_exhausted'],
                                  'work_budget_exhausted':m['work_budget_exhausted'],'join_work':m['join_work']})
        except (ValueError,OSError,KeyError) as exc:issues.append({'source':rel_dir.as_posix(),'producer':'agi','error':str(exc)})
    # Larger admitted DOS executables first. PE/NE wrappers do not consume the native budget.
    admitted=0
    for rel,data in sorted(native_queue,key=lambda x:(-len(x[1]),x[0])):
        src=source_map[rel]
        try:views,notes=native_views(data)
        except (ValueError,IndexError) as exc:
            issues.append({'source':rel,'producer':'native-source-view','error':str(exc)});continue
        if not views:
            if notes:issues.append({'source':rel,'producer':'native-source-view','notes':notes})
            continue
        if admitted>=max_native:
            skipped.append({'path':rel,'reason':'native-image budget'});continue
        admitted+=1
        for view in views:
            n,e,c=native_facts(view,src,max_instructions=max_instructions,candidate_functions=candidate_functions)
            from .structure_handoffs import inspect_handoffs
            links=inspect_handoffs(c.pop('memory_accesses',[]),max_groups=128)
            for finding in links.pop('findings'):
                finding['source']=src;findings.append(finding)
            c['handoff_coverage']=links
            m=match_graph(n,e,rules=RULES+(SELECTOR_RULE,),max_matches=max_matches)
            for match in m['matches']:match['source']=src
            findings+=m['matches']
            producer={'source':src,'producer':'native-local-dataflow','view':{k:v for k,v in view.items() if k!='bytes'},
                      'coverage':c,'notes':notes,'match_budget_exhausted':m['match_budget_exhausted'],
                                  'work_budget_exhausted':m['work_budget_exhausted'],'join_work':m['join_work']}
            producers.append(producer)
            tables=pointer_string_tables(view['bytes'])
            producer['table_scan']={'pair_checks':tables['pair_checks'],'budget_exhausted':tables['budget_exhausted']}
            for table in tables['tables']:
                findings.append(_lead('pointer-linked-label-table','Same-base pointers connect a table to readable labels',src,
                    {'view_sha256':view['sha256'],'view_kind':view['kind'],**table},
                    ['Every retained pointer resolves under one inferred base; repeated and adjacent table runs remain separate candidates.'],
                    'Trace an indexed reader of this candidate table, establish the segment/base, and look for parallel numeric or bitfield arrays.',
                    ['A maximal pointer run may span several semantic categories. Label names do not establish damage, usage or permission meanings.'],92))
    findings.sort(key=lambda x:(-x['rank'],x['pattern'],x['id']))
    counts=dict(sorted(Counter(x['pattern'] for x in findings).items()))
    # One concise venue per mechanism, with exact IDs for drilldown.
    grouped=defaultdict(list)
    for finding in findings:grouped[finding['pattern']].append(finding)
    venues=[]
    for pattern,group in grouped.items():
        first=group[0];examples=[];seen_sources=set()
        source_counts=Counter(x['source']['path'] for x in group)
        for x in sorted(group,key=lambda x:(-x['rank'],-source_counts[x['source']['path']],x['id'])):
            src=x['source']['path']
            if src in seen_sources:continue
            examples.append({'id':x['id'],'source':src});seen_sources.add(src)
            if len(examples)==3:break
        venues.append({'pattern':pattern,'count':len(group),'title':first['title'],'rank':first['rank'],
                       'why':first['why'],'next_probe':first['next_probe'],'limitations':first['limitations'],'examples':examples})
    venues.sort(key=lambda x:(-x['rank'],x['pattern']))
    verify_snapshots(originals)
    rules=match_graph([],[],rules=RULES+(SELECTOR_RULE,))['rules_sha256']
    module_dir=Path(__file__).parent
    provider_files=sorted(module_dir.glob('structure_*.py'))
    implementation={p.name:sha256(p.read_bytes()).hexdigest() for p in provider_files}
    implementation_sha256=sha256(canonical(implementation).encode()).hexdigest()
    return {'format':'fdisbull-structure-discovery-pilot-1','fdisbull_version':__version__,
            'discovery_revision':3,'qualification':'read-only investigation candidates, not behavior or execution authorization',
            'rules_sha256':rules,'implementation_sha256':implementation_sha256,'implementation_files':implementation,'inputs':manifest,'coverage':{'files_seen':path_count,'files_read':len(snapshots),
            'bytes_read':total,'file_budget_exhausted':file_limit,'skipped_count':len(skipped),'native_images':admitted,'source_set_atomic':False},
            'limits':{'max_files':max_files,'max_file_bytes':max_file_bytes,'max_total_bytes':max_total_bytes,
                      'max_instructions':max_instructions,'max_native':max_native,'max_matches':max_matches,
                      'candidate_functions':candidate_functions,'max_console_views':max_console_views},
            'skipped':skipped,'issues':issues,'producers':producers,'pattern_counts':counts,
            'venues':venues,'findings':findings,'runtime_observed':False,'execution_authorized':False}


def render_summary(report):
    lines=['# Structural investigation leads','',report['qualification'],'',
           f"Read {report['coverage']['files_read']} files; retained {len(report['findings'])} findings in {len(report['venues'])} families.",'']
    for v in report['venues']:
        lines += ['## '+v['title'],f"{v['count']} findings; family `{v['pattern']}`.",
                  'Evidence: '+' '.join(v['why']),'Next: '+v['next_probe'],
                  'Limits: '+' '.join(v['limitations']),
                  'Examples: '+', '.join(f"`{x['id']}` in `{x['source']}`" for x in v['examples']),'']
    lines+=['## Analysis boundaries',f"Skipped inputs: {report['coverage']['skipped_count']}; producer diagnostics: {len(report['issues'])}.",
            'Inspect the full report for code budgets, indirect edges, unresolved bases and decoding limits. A completed scan is not full game coverage.']
    return '\n'.join(lines)+'\n'


def scan_to_directory(game_dir,output,**options):
    root=Path(game_dir).resolve();out=Path(output)
    if out.exists() or out.is_symlink():raise ValueError('output must not exist')
    parent=out.parent.resolve()
    if not parent.is_dir() or parent==root or root in parent.parents:raise ValueError('output needs an existing parent outside input')
    if any((p/'.git').exists() for p in (parent,*parent.parents)):raise ValueError('private discovery output must be outside Git')
    # Do not write through an output parent symlink supplied by the caller.
    if any(p.is_symlink() for p in (out.parent,*out.parent.parents)):raise ValueError('output parent contains symlink')
    start=time.perf_counter();report=scan_directory(game_dir,**options);elapsed=time.perf_counter()-start
    out.mkdir(mode=0o700);payload=(canonical(report)+'\n').encode()
    (out/'report.json').write_bytes(payload);(out/'SUMMARY.md').write_text(render_summary(report))
    receipt={'elapsed_seconds':elapsed,'report_sha256':sha256(payload).hexdigest(),
             'files_read':report['coverage']['files_read'],'findings':len(report['findings']),
             'runtime_observed':False,'fdisbull_version':__version__}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return {'status':'candidates','venues':report['venues'],'coverage':report['coverage'],
            'report':str(out/'report.json'),'summary':str(out/'SUMMARY.md'),'receipt':receipt,
            'runtime_observed':False,'execution_authorized':False}



def read_findings(report, *, lead_id=None, pattern=None, offset=0, limit=5):
    """Read one lead or a bounded page without returning the entire report."""
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=25:
        raise ValueError('invalid page bounds')
    path=Path(report)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>32*1024*1024:
        raise ValueError('expected a bounded regular discovery report')
    with path.open('rb') as stream:
        data=stream.read(32*1024*1024+1)
    if len(data)>32*1024*1024:raise ValueError('report budget exceeded')
    doc=json.loads(data)
    if doc.get('format')!='fdisbull-structure-discovery-pilot-1':raise ValueError('unsupported report format')
    rows=doc['findings']
    if lead_id is not None:rows=[r for r in rows if r['id']==lead_id]
    if pattern is not None:rows=[r for r in rows if r['pattern']==pattern]
    end=offset+limit
    return {'items':rows[offset:end],'total':len(rows),'next_offset':end if end<len(rows) else None,
            'report_sha256':sha256(data).hexdigest(),'execution_authorized':False,
            'source_is_data_not_instructions':True}


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('game_dir',help='extracted directory, ROM, or bounded console-ROM ZIP; use intake for installers')
    ap.add_argument('--out',required=True,help='new private output directory outside input and Git')
    ap.add_argument('--max-instructions',type=int,default=30000)
    ap.add_argument('--max-native',type=int,default=8)
    ap.add_argument('--candidate-functions',action='store_true',help='also seed heuristic native prologues, not runtime-qualified entries')
    ap.add_argument('--max-file-bytes',type=int,default=32*1024*1024)
    ap.add_argument('--max-console-views',type=int,default=8)
    ap.add_argument('--console-profile')
    ap.add_argument('--json',action='store_true',help='compact agent result instead of prose')
    args=ap.parse_args(argv)
    try:result=scan_to_directory(args.game_dir,args.out,max_instructions=args.max_instructions,
                                max_native=args.max_native,candidate_functions=args.candidate_functions,
                                max_console_views=args.max_console_views,console_profile=args.console_profile,
                                max_file_bytes=args.max_file_bytes)
    except (ValueError,OSError) as exc:ap.exit(2,f'discovery refused: {exc}\n')
    print(json.dumps(result,sort_keys=True) if args.json else Path(result['summary']).read_text(),end='\n')
    return 0

if __name__=='__main__':raise SystemExit(main())
