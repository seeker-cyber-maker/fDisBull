"""Read-only intent drafts, composition validation and invocation-trace audits.

Existing fdisbull-block-contract-1 documents supply behavior identities. This
module adds an analysis sidecar, not new executable UIL opcodes, host scheduling,
provider imports, guest hooks or authorization. Source-derived candidates never
become qualified contracts merely because a human-readable name was attached.
"""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re

from .structure_patterns import canonical
from .udc_layers import validate_contract

_NAME=re.compile(r'[A-Za-z_][A-Za-z0-9_.-]{0,127}\Z')
_SHA=re.compile(r'[0-9a-f]{64}\Z')


def _finite(value, maximum=4*1024*1024):
    try:raw=json.dumps(value,sort_keys=True,allow_nan=False,separators=(',',':')).encode()
    except (ValueError,TypeError,RecursionError) as exc:raise ValueError('bounded finite JSON required') from exc
    if len(raw)>maximum:raise ValueError('document byte budget exceeded')
    return raw


def read_json(path, maximum=16*1024*1024):
    p=Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size>maximum:raise ValueError('bounded regular JSON file required')
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d:raise ValueError('duplicate JSON key: '+k)
            d[k]=v
        return d
    with p.open('rb') as f:raw=f.read(maximum+1)
    if len(raw)>maximum:raise ValueError('document byte budget exceeded')
    try:doc=json.loads(raw,object_pairs_hook=unique)
    except (ValueError,RecursionError,UnicodeError) as exc:raise ValueError('invalid finite JSON document') from exc
    _finite(doc,maximum)
    return doc


def _name(value):
    if not isinstance(value,str) or not _NAME.fullmatch(value):raise ValueError('invalid bounded identifier')
    return value


def _evidence(value):
    if not isinstance(value,str) or not 1<=len(value)<=2048:raise ValueError('explicit evidence/assumption reference required')
    return value


def _acyclic(edges, label):
    # Iterative Kahn traversal also avoids recursion on hostile documents.
    count={k:0 for k in edges}
    for deps in edges.values():
        for dep in deps:
            if dep not in edges:raise ValueError('unknown '+label+' dependency')
    for key,deps in edges.items():count[key]=len(set(deps))
    reverse={k:[] for k in edges}
    for key,deps in edges.items():
        for dep in set(deps):reverse[dep].append(key)
    todo=sorted(k for k,v in count.items() if v==0);done=[]
    while todo:
        k=todo.pop();done.append(k)
        for other in reverse[k]:
            count[other]-=1
            if count[other]==0:todo.append(other)
    if len(done)!=len(edges):raise ValueError(label+' dependency cycle')
    return done


def intent_drafts(report, *, offset=0, limit=5):
    """Produce a page of non-executable components from existing discovery leads."""
    if not isinstance(report,dict) or report.get('format')!='fdisbull-structure-discovery-pilot-1':
        raise ValueError('expected shared discovery report')
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=25:raise ValueError('invalid page')
    findings=report.get('findings')
    if not isinstance(findings,list) or len(findings)>100000:raise ValueError('invalid finding budget')
    drafts=[]
    for finding in findings[offset:offset+limit]:
        components=[]
        for role,node in sorted(finding.get('bindings',{}).items()):
            components.append({'id':node['id'],'role':node['role'],'contract_ref':None,
                               'proposed_intent':None,'source_evidence':node['evidence'],
                               'operation_kind':node.get('operation'),'qualification':'source pattern only'})
        drafts.append({'id':finding['id'],'pattern':finding['pattern'],'contract_ref':None,
                       'proposed_intent':None,'components':components,
                       'relationships':finding.get('why',[]),
                       'state_effect':'unresolved','context_effect':'unresolved',
                       'completion_phases':[],'invocations':[],
                       'next_probe':finding['next_probe'],
                       'obligations':['Bind relevant object and context; do not infer original classes.',
                           'Qualify inputs, effects, continuation and completion separately.',
                           'Choose observable replacement boundaries; machine functions are not mandatory intent boundaries.',
                           'A proposed child is not automatically invoked by every parent implementation.'],
                       'execution_authorized':False})
    return {'status':'intent_candidates','items':drafts,'total':len(findings),
            'next_offset':offset+limit if offset+limit<len(findings) else None,
            'schema_changes_to_uil':False,'execution_authorized':False}


def parse_composition(doc):
    """Check declared contracts, implementation-specific children and phase joins.

    This validates a proposed plan. It does not prove the declared dependencies
    against a target, start a worker, wait, or execute any selected provider.
    """
    raw=_finite(doc)
    allowed={'format','root','contracts','phases','implementations','selection','evidence'}
    if not isinstance(doc,dict) or doc.get('format')!='fdisbull-structure-composition-1' or set(doc)-allowed:
        raise ValueError('invalid composition sidecar')
    contracts=doc.get('contracts'); phases=doc.get('phases'); implementations=doc.get('implementations'); selection=doc.get('selection')
    if not isinstance(contracts,dict) or not 1<=len(contracts)<=256 or not isinstance(phases,dict) or set(phases)!=set(contracts):
        raise ValueError('contract and phase catalogues must correspond')
    for name,contract in contracts.items():
        _name(name);validate_contract(contract)
        spec=phases[name]
        if not isinstance(spec,dict) or set(spec)!={'terminal','observations'}:raise ValueError('invalid completion phases')
        observations=spec['observations']
        if not isinstance(observations,dict) or not 1<=len(observations)<=32 or spec['terminal'] not in observations:
            raise ValueError('terminal completion phase required')
        phase_edges={}
        for phase,obs in observations.items():
            _name(phase)
            if not isinstance(obs,dict) or set(obs)!={'condition','evidence','after'}:raise ValueError('phase requires an acceptance condition and evidence')
            _evidence(obs['condition']);_evidence(obs['evidence'])
            if not isinstance(obs['after'],list) or len(obs['after'])>32 or any(x not in observations for x in obs['after']):
                raise ValueError('invalid phase dependency')
            phase_edges[phase]=obs['after']
        _acyclic(phase_edges,'phase')
        if any(spec['terminal'] in deps for deps in phase_edges.values()):
            raise ValueError('terminal phase cannot precede another phase of the same invocation')
    if not isinstance(implementations,dict) or not 1<=len(implementations)<=512 or not isinstance(selection,dict):
        raise ValueError('invalid implementation catalogue/selection')
    for ident,impl in implementations.items():
        _name(ident)
        if not isinstance(impl,dict) or set(impl)!={'contract','children','complete_after','evidence'} or impl['contract'] not in contracts:
            raise ValueError('invalid implementation contract binding')
        _evidence(impl['evidence'])
        if not isinstance(impl['children'],list) or len(impl['children'])>64:raise ValueError('child budget')
        slots={}
        for child in impl['children']:
            if not isinstance(child,dict) or set(child)!={'slot','contract','owner','on_restore','on_cancel','after'}:raise ValueError('invalid child declaration')
            _name(child['slot'])
            if child['slot'] in slots or child['contract'] not in contracts:raise ValueError('duplicate slot or unknown child contract')
            if child['owner'] not in ('parent','context','session') or any(child[k] not in ('cancel','invalidate-result','finish-detached','reconstruct') for k in ('on_restore','on_cancel')):
                raise ValueError('explicit child lifetime/restore policy required')
            slots[child['slot']]=child
        def refs(refs):
            if not isinstance(refs,list) or len(refs)>128:raise ValueError('join budget')
            for ref in refs:
                if not isinstance(ref,dict) or set(ref)!={'slot','phase'} or ref['slot'] not in slots:
                    raise ValueError('unknown child join')
                if ref['phase'] not in phases[slots[ref['slot']]['contract']]['observations']:
                    raise ValueError('unknown required completion phase')
            return refs
        refs(impl['complete_after']); depgraph={}
        for child in slots.values():
            deps=refs(child['after']);depgraph[child['slot']]=[r['slot'] for r in deps]
            terminal=phases[child['contract']]['terminal']
            if child['owner']=='parent' and {'slot':child['slot'],'phase':terminal} not in impl['complete_after']:
                raise ValueError('parent-owned child must finish before parent completion')
        _acyclic(depgraph,'child')
    for contract,ident in selection.items():
        if contract not in contracts or ident not in implementations or implementations[ident]['contract']!=contract:
            raise ValueError('selection must bind an implementation of the same contract')
    root=doc.get('root')
    if root not in contracts or root not in selection:raise ValueError('selected root required')
    reached={};todo=[root]
    while todo:
        contract=todo.pop()
        if contract in reached:continue
        if contract not in selection:raise ValueError('unselected invoked child contract')
        impl=implementations[selection[contract]]
        reached[contract]=[ch['contract'] for ch in impl['children']];todo.extend(reached[contract])
    _acyclic(reached,'selected contract')
    return {'status':'validated_analysis_plan','composition_sha256':sha256(raw).hexdigest(),
            'selected_contracts':sorted(reached),'inactive_selections':sorted(set(selection)-set(reached)),
            'implementation_children':{c:[x['slot'] for x in implementations[selection[c]]['children']] for c in sorted(reached)},
            'execution_authorized':False,'scheduler_implemented':False,'behavior_qualified':False,
            'note':'Hierarchy and phase dependencies are declarations, not recovered implementation proof.'}


def audit_invocations(composition, trace):
    """Replay *observations*, never work: detect premature/stale/duplicate effects.

    Supports a bounded DAG per parent occurrence. Loops use a new parent
    invocation; recursive/dynamic slot reuse is not inferred. Post-restore work
    is retained as stale rather than authorized to commit to a new epoch.
    """
    plan=parse_composition(composition);_finite(trace,16*1024*1024)
    if not isinstance(trace,dict) or set(trace)!={'source_sha256','run','clock','initial_epoch','events'}:
        raise ValueError('invalid invocation trace')
    if not isinstance(trace['source_sha256'],str) or not _SHA.fullmatch(trace['source_sha256']):raise ValueError('source hash required')
    _name(trace['run'])
    if trace['clock'] not in ({'domain':'logical','unit':'tick'},{'domain':'logical','unit':'frame'}):
        raise ValueError('explicit logical clock required; host time is not guest time')
    if type(trace['initial_epoch']) is not int or trace['initial_epoch']<0 or not isinstance(trace['events'],list) or len(trace['events'])>100000:
        raise ValueError('invalid epoch/event budget')
    current=trace['initial_epoch']; last_tick=-1; inv={};violations=[];effects=set();restore_records=[]
    def bad(index,code,invocation=None):violations.append({'event':index,'code':code,'invocation':invocation})
    phases=composition['phases'];impls=composition['implementations'];select=composition['selection']
    for index,event in enumerate(trace['events']):
        if not isinstance(event,dict):raise ValueError('event must be object')
        kind=event.get('kind');epoch=event.get('epoch');tick=event.get('tick')
        if type(tick) is not int or tick<0 or type(epoch) is not int or epoch<0:raise ValueError('invalid logical tick/epoch')
        _evidence(event.get('evidence'))
        if kind=='restore':
            if set(event)!={'kind','epoch','tick','evidence'} or epoch<=current:raise ValueError('restore must advance epoch')
            for (old,ident),record in inv.items():
                if old==current and not record['terminal'] and not record['cancelled']:
                    restore_records.append({'invocation':ident,'epoch':old,'policy':record['on_restore'],'effect_undo_observed':False})
            current=epoch;last_tick=tick;continue
        if kind not in ('begin','phase','effect','cancel','uncertain'):raise ValueError('unknown observation kind')
        ident=_name(event.get('invocation'));key=(epoch,ident)
        if epoch!=current:bad(index,'stale-or-foreign-epoch',ident);continue
        if tick<last_tick:raise ValueError('nonmonotonic logical time within epoch')
        last_tick=tick
        if kind=='begin':
            if set(event)!={'kind','epoch','tick','evidence','invocation','contract','implementation','parent','slot'}:raise ValueError('invalid invocation begin')
            if key in inv:bad(index,'duplicate-invocation',ident);continue
            contract=event['contract'];implementation=event['implementation'];parent=event['parent'];slot=event['slot'];owner='session';policy='invalidate-result';cancel_policy='invalidate-result'
            if contract not in select or select[contract]!=implementation:bad(index,'implementation-selection-mismatch',ident);continue
            if parent is None:
                if contract!=composition['root'] or slot is not None:bad(index,'unexpected-root',ident);continue
            else:
                _name(parent);_name(slot);p=inv.get((epoch,parent))
                if p is None or p['terminal'] or p['cancelled']:bad(index,'inactive-parent',ident);continue
                child=next((x for x in impls[p['implementation']]['children'] if x['slot']==slot),None)
                if child is None or child['contract']!=contract:bad(index,'child-not-in-selected-implementation',ident);continue
                if slot in p['children']:bad(index,'slot-already-invoked',ident);continue
                for dep in child['after']:
                    sibling=inv.get((epoch,p['children'].get(dep['slot'])))
                    if not sibling or dep['phase'] not in sibling['phases']:bad(index,'dependency-not-complete',ident)
                p['children'][slot]=ident;owner=child['owner'];policy=child['on_restore'];cancel_policy=child['on_cancel']
            inv[key]={'contract':contract,'implementation':implementation,'parent':parent,'slot':slot,
                      'owner':owner,'on_restore':policy,'on_cancel':cancel_policy,'phases':set(),'children':{},'terminal':False,'cancelled':False}
            continue
        record=inv.get(key)
        if record is None:bad(index,'unknown-invocation',ident);continue
        if record['cancelled']:bad(index,'completion-after-cancel-or-uncertainty',ident);continue
        if record['parent'] is not None:
            parent_record=inv.get((epoch,record['parent']))
            if parent_record and parent_record['cancelled'] and record['on_cancel']!='finish-detached':
                bad(index,'child-completion-after-parent-cancellation',ident);continue
            if parent_record and parent_record['terminal'] and record['owner']=='parent':
                bad(index,'parent-owned-work-outlived-parent',ident);continue
        if kind in ('cancel','uncertain'):
            if set(event)!={'kind','epoch','tick','evidence','invocation'}:raise ValueError('invalid cancellation/uncertainty event')
            record['cancelled']=True;continue
        if kind=='effect':
            if set(event)!={'kind','epoch','tick','evidence','invocation','effect_id','payload'}:raise ValueError('invalid effect observation')
            eid=_name(event['effect_id']);ek=(epoch,ident,eid)
            if record['terminal']:bad(index,'effect-after-terminal-phase',ident)
            if ek in effects:bad(index,'duplicate-effect-id',ident)
            effects.add(ek);continue
        if set(event)!={'kind','epoch','tick','evidence','invocation','phase'}:raise ValueError('invalid phase observation')
        phase=event['phase'];contract=record['contract'];pdef=phases[contract]
        if phase not in pdef['observations']:bad(index,'unknown-phase',ident);continue
        if phase in record['phases']:bad(index,'duplicate-phase',ident);continue
        if record['terminal']:bad(index,'phase-after-terminal-phase',ident);continue
        if any(p not in record['phases'] for p in pdef['observations'][phase]['after']):bad(index,'phase-prerequisite-missing',ident)
        if phase==pdef['terminal']:
            for dep in impls[record['implementation']]['complete_after']:
                child=inv.get((epoch,record['children'].get(dep['slot'])))
                if not child or dep['phase'] not in child['phases']:bad(index,'premature-parent-completion',ident)
            record['terminal']=True
        record['phases'].add(phase)
    outstanding=[{'invocation':ident,'epoch':epoch,'contract':r['contract'],'owner':r['owner']}
                 for (epoch,ident),r in inv.items() if epoch==current and not r['terminal'] and not r['cancelled']]
    return {'status':'violations' if violations else 'consistent-prefix','violations':violations,
            'invocations':len(inv),'observed_effect_ids':len(effects),'outstanding':outstanding,
            'restoration_obligations':restore_records,'trace_sha256':sha256(_finite(trace,16*1024*1024)).hexdigest(),
            'composition_sha256':plan['composition_sha256'],'execution_authorized':False,
            'limits':['Observation consistency does not prove phase witnesses or target equivalence.',
                      'No effects executed, rolled back, cancelled, or rescheduled by this audit.',
                      'A partial trace with outstanding work is not a successful complete execution.']}


def compare_observations(expected, actual):
    """Compare exact declared outputs and ordered effects, not implementation bytes."""
    for d in (expected,actual):
        _finite(d)
        if not isinstance(d,dict) or set(d)!={'contract_sha256','scope','inputs','outputs','effects','complete'}:
            raise ValueError('invalid contract observation')
        if not isinstance(d['contract_sha256'],str) or not _SHA.fullmatch(d['contract_sha256']):raise ValueError('contract identity required')
        if not isinstance(d['scope'],str) or not d['scope'] or not isinstance(d['inputs'],dict) or not isinstance(d['outputs'],dict) or not isinstance(d['effects'],list) or type(d['complete']) is not bool:
            raise ValueError('explicit observation scope required')
    if expected['contract_sha256']!=actual['contract_sha256'] or expected['scope']!=actual['scope'] or canonical(expected['inputs'])!=canonical(actual['inputs']):
        raise ValueError('comparison requires same contract, scope and admitted inputs')
    if not expected['complete'] or not actual['complete']:
        return {'status':'incomplete','equivalent':None,'execution_authorized':False}
    todo=[('effects',expected['effects'],actual['effects']),('outputs',expected['outputs'],actual['outputs'])]
    differences=[];work=0;omitted=False
    while todo and work<100000 and len(differences)<32:
        path,a,b=todo.pop();work+=1
        if type(a) is not type(b):differences.append({'path':path,'kind':'type'});continue
        if isinstance(a,dict):
            for k in sorted(set(a)|set(b),reverse=True):
                if k not in a or k not in b:
                    if len(differences)<32:differences.append({'path':path+'.'+k,'kind':'missing-key'})
                    else:omitted=True
                else:todo.append((path+'.'+k,a[k],b[k]))
        elif isinstance(a,list):
            if len(a)!=len(b):differences.append({'path':path,'kind':'length','expected':len(a),'actual':len(b)})
            todo.extend((f'{path}[{i}]',a[i],b[i]) for i in reversed(range(min(len(a),len(b)))))
        elif a!=b:differences.append({'path':path,'kind':'value'})
    exhausted=bool(todo) or omitted
    return {'status':'mismatch' if differences else 'incomplete' if exhausted else 'matched-declared-observations',
            'equivalent':False if differences else None if exhausted else True,'differences':differences,
            'comparison_truncated':exhausted,'execution_authorized':False,
            'scope':'exact declared outputs and ordered effects only; no universal behavior or scheduler proof'}


def draft_file(report, **options):return intent_drafts(read_json(report,64*1024*1024),**options)
def composition_file(spec):return parse_composition(read_json(spec))
def audit_files(spec,trace):return audit_invocations(read_json(spec),read_json(trace))
def compare_files(expected,actual):return compare_observations(read_json(expected),read_json(actual))
