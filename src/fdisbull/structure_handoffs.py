"""Bounded, source-scoped storage and device investigation avenues.

An address association is not a reaching-definition proof or an event delivery.
No queue/latch label is inferred from two coincident numerical addresses.
"""
from collections import defaultdict
from hashlib import sha256
from .structure_patterns import canonical


def inspect_handoffs(accesses, *, max_groups=512):
    if not isinstance(accesses,list) or len(accesses)>100000:
        raise ValueError('memory access budget exceeded')
    if type(max_groups) is not int or not 1<=max_groups<=10000:raise ValueError('invalid group budget')
    groups=defaultdict(list);waits=[];seen=set()
    for a in accesses:
        if not isinstance(a,dict) or not isinstance(a.get('id'),str) or a['id'] in seen or a.get('kind') not in ('read','write','wait'):
            raise ValueError('invalid or duplicate access fact')
        seen.add(a['id']);e=a.get('evidence')
        if not isinstance(e,dict) or not e.get('source_sha256') or not e.get('space'):raise ValueError('source identity required')
        if a['kind']=='wait':waits.append(a);continue
        storage=a.get('storage')
        if not isinstance(storage,dict) or set(storage)!={'scope','space','address','width'}:
            raise ValueError('exact scoped storage identity required')
        if storage['scope']!=e['space'] or type(storage['address']) is not int or storage['address']<0 or storage['width'] not in (8,16,32,64):
            raise ValueError('invalid storage context')
        groups[(e['source_sha256'],canonical(storage))].append(a)
    leads=[];exhausted=False
    def lead(pattern,rows,storage,title,next_probe):
        ident=pattern+canonical({'ids':sorted(r['id'] for r in rows),'storage':storage})
        return {'id':'lead-'+sha256(ident.encode()).hexdigest()[:20],'pattern':pattern,'rank':72,
                'title':title,'status':'candidate','evidence':{'storage':storage,'witnesses':rows[:8],
                    'witness_count':len(rows),'witnesses_truncated':len(rows)>8},
                'why':['Exact source, mapping scope, storage identity and width retained.'],
                'next_probe':next_probe,'limitations':['Static expression association, not a concrete runtime alias, temporal order, causal delivery, scene identity or execution authorization.'],
                'runtime_observed':False,'execution_authorized':False}
    for (_,storage),rows in sorted(groups.items()):
        rows=sorted(rows,key=lambda r:r['id']);kinds={r['kind'] for r in rows}
        if kinds=={'read','write'} and all(r.get('domain') in ('state','symbolic-state') for r in rows):
            if len(leads)>=max_groups:exhausted=True;break
            leads.append(lead('storage-producer-consumer',rows,rows[0]['storage'],
                              'Matching scoped storage expressions occur in writers and readers',
                              'First establish the live segment/base and allocation lifetime. Follow the reader guard and writer values. Distinguish a latch, a pending-command slot, queue storage, and an ordinary variable; compare repeated requests and clear/consume behavior.'))
        elif any(r.get('domain')=='device' for r in rows):
            if len(leads)>=max_groups:exhausted=True;break
            leads.append(lead('device-service-boundary',rows,rows[0]['storage'],
                              'An operation crosses a mapped device boundary',
                              'Bind the platform/peripheral register and its direction. Separate input sampling, request submission, device completion and visible presentation; preserve repeated ordered writes.'))
    for row in waits:
        if len(leads)>=max_groups:exhausted=True;break
        leads.append(lead('wait-continuation', [row],None,'Execution yields at an explicit wait boundary',
                          'Identify the releasing interrupt/event and continuation before proposing a completion phase or a join.'))
    return {'findings':leads,'group_budget_exhausted':exhausted,'storage_groups':len(groups),
            'scope':'exact-address candidate associations; no alias, cross-mapping or cross-source unification'}
