#!/usr/bin/env python3
"""Read-only stored-fact coverage accounting for an fDisBull SQLite project.

No fDisBull modules, seeds, classifications or analysis calls are used. All
address-key TEXT values are hexadecimal, including digit-only keys. Byte
unions describe stored tags, not executable truth or runtime reachability.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import time

RESOLVED_CONTROL_KINDS = {'resolved_call','resolved_branch','import_call','call','branch','jump'}
INDIRECT_FLOWS = ('indirect_call','indirect_jump')


def address(value):
    if value is None:
        return None
    return value if isinstance(value,int) else int(value,16)


def union(spans):
    result=[]
    for start,end in sorted((a,b) for a,b in spans if b>a):
        if result and start<=result[-1][1]:
            result[-1]=(result[-1][0],max(result[-1][1],end))
        else:
            result.append((start,end))
    return result


def length(spans):
    return sum(end-start for start,end in spans)


def intersection(left,right):
    result=[];i=j=0
    while i<len(left) and j<len(right):
        a,b=left[i];c,d=right[j]
        if max(a,c)<min(b,d):result.append((max(a,c),min(b,d)))
        if b<d:i+=1
        else:j+=1
    return result


def clip(spans,start,end):
    return union((max(a,start),min(b,end)) for a,b in spans if a<end and b>start)


def complement(spans,start,end):
    result=[];cursor=start
    for a,b in spans:
        if a>cursor:result.append((cursor,a))
        cursor=max(cursor,b)
    if cursor<end:result.append((cursor,end))
    return result


def display_spans(spans):
    return [{'start':a,'end_exclusive':b,'start_hex':hex(a),'end_exclusive_hex':hex(b),'bytes':b-a} for a,b in spans]


def rows(connection,query,args=()):
    return [dict(row) for row in connection.execute(query,args)]


def export(database:Path,version:int,fixups_path:Path):
    start_time=time.monotonic()
    connection=sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True)
    connection.row_factory=sqlite3.Row
    connection.execute('PRAGMA query_only=ON')
    connection.execute('BEGIN')  # One consistent read snapshot; no mutation.
    tables={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not connection.execute('SELECT 1 FROM versions WHERE id=?',(version,)).fetchone():
        raise ValueError('Requested stored version is absent')
    selected_version=dict(connection.execute('SELECT * FROM versions WHERE id=?',(version,)).fetchone())
    metadata=dict(connection.execute('SELECT key,value FROM metadata'))
    regions=rows(connection,'SELECT name,start,length(data) AS bytes,executable,writable FROM regions WHERE version=? ORDER BY start',(version,))
    for region in regions:
        region['start_key']=region['start'];region['start']=address(region['start'])
        region['end_exclusive']=region['start']+region['bytes']
    instructions=rows(connection,'SELECT context,address,size,mnemonic,operands,flow,target FROM instructions WHERE version=?',(version,))
    data_items=rows(connection,'SELECT context,address,size,representation,source FROM data_items WHERE version=?',(version,))
    functions=rows(connection,'SELECT context,address,name,source,status FROM functions WHERE version=?',(version,))
    for collection in (instructions,data_items,functions):
        for item in collection:
            item['address_key']=item['address'];item['address']=address(item['address'])
            if 'target' in item:
                item['target_key']=item['target'];item['target']=address(item['target'])
    instruction_spans=union((i['address'],i['address']+i['size']) for i in instructions)
    data_spans=union((i['address'],i['address']+i['size']) for i in data_items)
    region_spans=union((r['start'],r['end_exclusive']) for r in regions)
    instruction_starts=defaultdict(list);function_entries=defaultdict(list)
    for item in instructions:instruction_starts[item['address']].append(item)
    for item in functions:function_entries[item['address']].append(item)
    objects=[]
    for region in regions:
        a,b=region['start'],region['end_exclusive']
        code=clip(instruction_spans,a,b);data=clip(data_spans,a,b)
        both=intersection(code,data);either=union(code+data);neither=complement(either,a,b)
        starts=[i for i in instructions if a<=i['address']<b]
        touching=[i for i in instructions if i['address']<b and i['address']+i['size']>a]
        ds=[i for i in data_items if a<=i['address']<b]
        fs=[f for f in functions if a<=f['address']<b]
        obj={**region,'start_hex':hex(a),'end_exclusive_hex':hex(b),
            'instruction_records_starting_inside':len(starts),
            'instruction_records_touching':len(touching),
            'unique_decoded_instruction_bytes':length(code),
            'instruction_record_byte_sum_clipped':sum(min(i['address']+i['size'],b)-max(i['address'],a) for i in touching),
            'data_item_records_starting_inside':len(ds),'stored_data_item_union_bytes':length(data),
            'code_data_overlap_bytes':length(both),'code_only_bytes':length(code)-length(both),
            'data_only_bytes':length(data)-length(both),'neither_classified_bytes':length(neither),
            'instruction_flow_counts':dict(Counter(i['flow'] for i in starts)),
            'data_representation_counts':dict(Counter(i['representation'] for i in ds)),
            'function_entry_records':len(fs),
            'function_source_counts':dict(Counter(f['source'] for f in fs)),
            'function_status_counts':dict(Counter(f['status'] for f in fs)),
            'instruction_union_ranges':display_spans(code),'data_union_ranges':display_spans(data),
            'code_data_overlap_ranges':display_spans(both),'neither_classified_ranges':display_spans(neither)}
        if obj['code_only_bytes']+obj['data_only_bytes']+obj['code_data_overlap_bytes']+obj['neither_classified_bytes']!=region['bytes']:
            raise ValueError('Object classification partition failed')
        objects.append(obj)

    def state_summary(table):
        if table not in tables:return {'table_absent':True}
        return {'total':connection.execute(f'SELECT count(*) FROM {table} WHERE version=?',(version,)).fetchone()[0],
          'states':{row[0]:row[1] for row in connection.execute(f'SELECT state,count(*) FROM {table} WHERE version=? GROUP BY state',(version,))}}

    native={table:state_summary(table) for table in ('work','investigations','dos_states','dos_seeds')}
    native['work_state_reason_counts']=rows(connection,'SELECT state,reason,count(*) AS records FROM work WHERE version=? GROUP BY state,reason ORDER BY state,reason',(version,))
    native['investigation_state_reason_counts']=rows(connection,'SELECT state,reason,count(*) AS records FROM investigations WHERE version=? GROUP BY state,reason ORDER BY state,reason',(version,))
    native['analysis_state']=rows(connection,'SELECT * FROM analysis_state WHERE version=?',(version,))
    native['facts_revision']=rows(connection,'SELECT * FROM analysis_facts_revision WHERE version=?',(version,)) if 'analysis_facts_revision' in tables else []
    derived=state_summary('advanced_jobs')
    derived['state_reason_counts']=rows(connection,'SELECT state,reason,count(*) AS records,min(generation) AS min_generation,max(generation) AS max_generation FROM advanced_jobs WHERE version=? GROUP BY state,reason ORDER BY state,reason',(version,)) if 'advanced_jobs' in tables else []
    derived['unregistered_decoded_function_entries']=connection.execute('SELECT count(*) FROM functions f JOIN instructions i ON i.version=f.version AND i.context=f.context AND i.address=f.address WHERE f.version=? AND NOT EXISTS(SELECT 1 FROM advanced_jobs j WHERE j.version=f.version AND j.context=f.context AND j.address=f.address)',(version,)).fetchone()[0] if 'advanced_jobs' in tables else None
    derived['stored_results']=[]
    if 'advanced_results' in tables:
        # Read one compact projection from each stored result. The original
        # result body remains in the project; absent summaries stay null.
        query='''SELECT r.context,r.address,r.generation,j.state AS job_state,j.generation AS job_generation,
          json_extract(r.document,'$.budget_exhausted') AS budget_exhausted,
          json_extract(r.document,'$.graph.closed') AS graph_closed,
          json_array_length(r.document,'$.graph.gaps') AS graph_gap_count,
          json_array_length(r.document,'$.graph.unresolved') AS graph_unresolved_count,
          json_array_length(r.document,'$.graph.frontier') AS graph_frontier_count,
          json_extract(r.document,'$.dataflow.stable') AS dataflow_stable,
          json_extract(r.document,'$.dataflow.budget_exhausted') AS dataflow_budget_exhausted,
          json_array_length(r.document,'$.dataflow.unresolved') AS dataflow_unresolved_count
          FROM advanced_results r LEFT JOIN advanced_jobs j ON j.version=r.version AND j.context=r.context AND j.address=r.address WHERE r.version=?'''
        for row in connection.execute(query,(version,)):
            item=dict(row);item['address_key']=item['address'];item['address']=address(item['address'])
            item['address_hex']=hex(item['address'])
            item['current_done_result']=item['job_state']=='done' and item['generation']==item['job_generation']
            derived['stored_results'].append(item)
        derived['stored_result_count']=len(derived['stored_results'])
        derived['current_done_result_count']=sum(r['current_done_result'] for r in derived['stored_results'])
        derived['noncurrent_or_nondone_result_count']=sum(not r['current_done_result'] for r in derived['stored_results'])
        derived['result_budget_exhausted_count']=sum(r['budget_exhausted']==1 for r in derived['stored_results'])
        derived['current_done_results_with_graph_unknowns']=sum(r['current_done_result'] and any((r[k] or 0)>0 for k in ('graph_gap_count','graph_unresolved_count','graph_frontier_count')) for r in derived['stored_results'])
    derived['interpretation']='done is a fixed point of an implemented job, not whole-function or whole-binary semantic completion; partial and pending remain unfinished, and stale/nondone stored results are retained as such.'

    indirect=[i for i in instructions if i['flow'] in INDIRECT_FLOWS]
    identities={(i['context'],i['address']):i for i in indirect}
    outgoing=defaultdict(list);owners=defaultdict(list)
    query="SELECT x.* FROM xrefs x JOIN instructions i ON i.version=x.version AND i.context=x.context AND i.address=x.source WHERE x.version=? AND i.flow IN ('indirect_call','indirect_jump')"
    for row in connection.execute(query,(version,)):
        item=dict(row);item['source_key']=item['source'];item['source']=address(item['source']);item['target_key']=item['target'];item['target']=address(item['target'])
        item['target_hex']=hex(item['target'])
        try:item['evidence']=json.loads(item['evidence'])
        except (json.JSONDecodeError,TypeError):pass
        outgoing[(item['context'],item['source'])].append(item)
    if 'advanced_edges' in tables:
        query="""SELECT e.*,j.state AS owner_job_state,j.generation AS owner_job_generation
          FROM advanced_edges e JOIN instructions i ON i.version=e.version AND i.context=e.source_context AND i.address=e.source
          LEFT JOIN advanced_jobs j ON j.version=e.version AND j.context=e.owner_context AND j.address=e.owner_address
          WHERE e.version=? AND i.flow IN ('indirect_call','indirect_jump')"""
        for row in connection.execute(query,(version,)):
            item=dict(row)
            for key in ('owner_address','source','target'):
                item[key+'_key']=item[key];item[key]=address(item[key]);item[key+'_hex']=hex(item[key])
            owners[(item['source_context'],item['source'])].append(item)
    sites=[]
    for identity,item in sorted(identities.items(),key=lambda pair:(pair[0][1],pair[0][0])):
        edges=outgoing.get(identity,[])
        resolved=[edge for edge in edges if edge['kind'] in RESOLVED_CONTROL_KINDS]
        site={**item,'address_hex':hex(item['address']),
          'stored_resolved_control_edges':resolved,
          'other_stored_outgoing_xrefs':[edge for edge in edges if edge['kind'] not in RESOLVED_CONTROL_KINDS],
          'derived_edge_owners':owners.get(identity,[]),
          'resolution_status':'stored_static_target_candidates' if resolved else 'no_stored_resolved_control_target',
          'exhaustive_runtime_targets_proven':False}
        sites.append(site)

    fixups=json.loads(fixups_path.read_text())
    relevant=[r for r in fixups if r['source_object']==2 and r['target_object']==1]
    targets=sorted({r['relocated_value'] for r in relevant})
    target_comparison=[]
    for target in targets:
        isites=instruction_starts.get(target,[]);fentries=function_entries.get(target,[])
        target_comparison.append({'address':target,'address_hex':hex(target),
          'relocation_pointer_sources':sorted({r['source_address'] for r in relevant if r['relocated_value']==target}),
          'decoded_instruction_start':bool(isites),'decoded_instruction_records':isites,
          'candidate_function_entry':bool(fentries),'function_entry_records':fentries,
          'inside_other_instruction_records':[i for i in instructions if i['address']<target<i['address']+i['size']]})
    connection.rollback();connection.close()
    result={'format':'fdisbull-stored-analysis-coverage-1','database':str(database.resolve()),
      'captured_at_utc':datetime.now(timezone.utc).isoformat(),'selected_version':selected_version,
      'project_metadata':{k:metadata.get(k) for k in ('application','arch','bits','entry','format','schema','source_sha256')},
      'address_key_convention':'All SQLite address TEXT values parsed as hexadecimal, including digit-only keys.',
      'scope':'Stored static classifications only; unique byte unions are not ground-truth code/data identity, recovered intent, or runtime reachability.',
      'totals':{'mapped_region_bytes':sum(r['bytes'] for r in regions),
        'stored_instruction_records':len(instructions),'stored_data_item_records':len(data_items),'function_entry_records':len(functions),
        'unique_instruction_bytes_inside_regions':length(intersection(instruction_spans,region_spans)),
        'unique_data_item_bytes_inside_regions':length(intersection(data_spans,region_spans)),
        'code_data_overlap_bytes_inside_regions':sum(o['code_data_overlap_bytes'] for o in objects),
        'neither_classified_bytes_inside_regions':sum(o['neither_classified_bytes'] for o in objects),
        'unique_instruction_bytes_outside_regions':length(instruction_spans)-length(intersection(instruction_spans,region_spans)),
        'unique_data_item_bytes_outside_regions':length(data_spans)-length(intersection(data_spans,region_spans)),
        'instruction_flow_counts':dict(Counter(i['flow'] for i in instructions)),
        'function_source_counts':dict(Counter(f['source'] for f in functions)),
        'function_status_counts':dict(Counter(f['status'] for f in functions))},
      'objects':objects,'native_analysis_state':native,'derived_analysis_state':derived,
      'indirect_transfer_scope':'All stored instructions whose flow is indirect_call or indirect_jump. Return instructions are counted separately in flow counts; caller-dependent return destinations are not resolved here.',
      'indirect_transfers':{'sites':sites,'site_count':len(sites),'sites_with_stored_control_candidates':sum(bool(s['stored_resolved_control_edges']) for s in sites),'sites_without_stored_control_candidates':sum(not s['stored_resolved_control_edges'] for s in sites)},
      'data_to_code_fixup_targets':{'source':str(fixups_path),'pointer_record_count':len(relevant),'distinct_target_count':len(targets),'targets':target_comparison},
      'elapsed_seconds':round(time.monotonic()-start_time,3),
      'limitations':['No seeds, instructions, data definitions, database records or analysis jobs were added or changed.',
        'Overlapping instruction or data tags are unioned, not accepted as mutually exclusive truth.',
        'Stored resolved edges remain conditional static candidates; their presence does not establish an exhaustive runtime target set.',
        'A drained base queue or a done derived job does not establish complete binary recovery.',
        'Derived results whose owners are not done, or whose generations disagree, are explicitly marked noncurrent or unfinished.']}
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('database',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--version',type=int,default=1)
    parser.add_argument('--fixups',type=Path,default=Path(__file__).with_name('independent-fixup-records.json'))
    args=parser.parse_args()
    result=export(args.database,args.version,args.fixups)
    args.output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n');args.output.chmod(0o600)
    print(json.dumps({'output':str(args.output),'bytes':args.output.stat().st_size,'totals':result['totals'],
      'native_states':{k:v for k,v in result['native_analysis_state'].items() if k in ('work','investigations','dos_states','dos_seeds')},
      'derived_states':result['derived_analysis_state'].get('states'),
      'derived_result_count':result['derived_analysis_state'].get('stored_result_count'),
      'indirect_sites':result['indirect_transfers']['site_count'],
      'indirect_sites_without_stored_targets':result['indirect_transfers']['sites_without_stored_control_candidates'],
      'fixup_targets_decoded':sum(t['decoded_instruction_start'] for t in result['data_to_code_fixup_targets']['targets']),
      'fixup_targets_functions':sum(t['candidate_function_entry'] for t in result['data_to_code_fixup_targets']['targets']),
      'elapsed_seconds':result['elapsed_seconds']},indent=2))

if __name__=='__main__':main()
