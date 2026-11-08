"""Small read-only relationship matcher for source-backed investigation leads.

Adapters produce facts; this module contains no game names, offsets or opcodes.
A match establishes the supplied connected pattern, never native reachability.
"""
from __future__ import annotations
from collections import defaultdict
from hashlib import sha256
import json

RULES = (
    {'id':'combined-values-control-operation',
     'nodes':{'left':'read','right':'read','combine':'bit_combine','selector':'selector_test','gate':'branch','effect':'effect'},
     'edges':[('left','combine','left_value'),('right','combine','right_value'),
              ('combine','selector','value'),('selector','gate','predicate'),('gate','effect','controls')],
     'rank':88,'title':'Two loaded values combine before an exact selector chooses an operation',
     'next':'Trace both value producers. Preserve the full comparison and combination rather than replacing it with one button-bit test. Then qualify the chosen operation.',
     'limits':'A connected six-node data/control pattern, not proof that either operand is controller input or that the effect is navigation.'},

    {'id': 'loaded-mask-controls-branch',
     'nodes': {'read': 'read', 'mask': 'mask', 'gate': 'branch'},
     'edges': [('read','mask','value'), ('mask','gate','predicate')],
     'rank': 80,
     'title': 'A loaded value is tested as bits and controls a branch',
     'next': 'Resolve the captured load expression, then compare a set-bit and clear-bit case. Keep mask polarity and any index transform.',
     'limits': 'Bit use is established in the decoded slice; equipment, permissions and other domain meanings are not.'},
    {'id': 'dictionary-test-controls-effect',
     'nodes': {'words': 'word_pattern', 'gate': 'branch', 'effect': 'effect'},
     'edges': [('words','gate','predicate'), ('gate','effect','controls')],
     'rank': 95,
     'title': 'Dictionary-backed input test reaches a guarded effect',
     'next': 'Inspect the retained ordered condition, then test one matching input and one near miss from a qualified original state.',
     'limits': 'A dictionary occurrence is not universal command availability. Other predicates, stateful input claiming and entry context remain relevant.'},
    {'id': 'same-entity-test-and-mutation',
     'nodes': {'test': 'entity_test', 'gate': 'branch', 'effect': 'effect'},
     'edges': [('test','gate','predicate'), ('gate','effect','controls')],
     'equal': [('test','subject','effect','subject')],
     'rank': 90,
     'title': 'A predicate and conditional effect refer to the same entity',
     'next': 'Resolve the entity and compare the guarded alternatives; verify the original effect and later consumers before naming the lifecycle.',
     'limits': 'Connected static identity is not proof of execution, atomicity or a complete interaction.'},
    {'id': 'indexed-value-controls-branch',
     'nodes': {'read':'indexed_read','gate':'branch'},
     'edges':[('read','gate','predicate')],
     'rank':75,
     'title':'An indexed field participates in a conditional decision',
     'next':'Recover the index domain and table extent, then enumerate compatible entries while preserving inactive and unknown records.',
     'limits':'An address expression does not by itself prove record stride, count or domain labels.'},
)


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True)


def match_graph(nodes, edges, *, rules=RULES, max_matches=10000, max_work=250000):
    """Bounded connected-pattern joins with deterministic bindings and witnesses.

    Rules admit 2..8 nodes and 1..12 directed edges, in any connected order.
    Both incoming and outgoing joins are indexed. Depth-first enumeration keeps
    intermediate memory bounded by rule depth, not the Cartesian product.
    Original source/mapping identity and non-null equality guards remain active.
    """
    if type(max_matches) is not int or not 1<=max_matches<=100000:
        raise ValueError('max_matches must be in 1..100000')
    if len(nodes)>500000 or len(edges)>1000000:raise ValueError('fact budget exceeded')
    if type(max_work) is not int or not 1<=max_work<=2000000:raise ValueError('max_work outside bounds')
    if len(rules)>64:raise ValueError('rule budget exceeded')
    by_id={}
    for n in nodes:
        if not isinstance(n,dict) or not isinstance(n.get('id'),str) or not n['id'] or not isinstance(n.get('role'),str) or not isinstance(n.get('evidence'),dict):
            raise ValueError('each node needs id, role, and source evidence')
        if n['id'] in by_id:raise ValueError('duplicate node id')
        by_id[n['id']]=n
    by_rel=defaultdict(list);outgoing=defaultdict(list);incoming=defaultdict(list);edge_set=set()
    for e in edges:
        if not isinstance(e,(list,tuple)) or len(e)!=3 or any(not isinstance(v,str) for v in e) or e[0] not in by_id or e[1] not in by_id:
            raise ValueError('invalid fact edge')
        edge_set.add(tuple(e))
    for left,right,rel in sorted(edge_set):
        by_rel[rel].append((left,right));outgoing[(left,rel)].append(right);incoming[(right,rel)].append(left)
    for rule in rules:
        rn=rule.get('nodes');re=rule.get('edges')
        if not isinstance(rn,dict) or not 2<=len(rn)<=8 or not isinstance(re,(list,tuple)) or not 1<=len(re)<=12:
            raise ValueError('connected rules require 2..8 nodes and 1..12 edges')
        if any(not isinstance(k,str) or not isinstance(v,str) for k,v in rn.items()):raise ValueError('invalid role binding')
        adjacent={k:set() for k in rn}
        for edge in re:
            if len(edge)!=3 or any(not isinstance(v,str) for v in edge):raise ValueError('invalid rule edge')
            x,y,r=edge
            if x not in rn or y not in rn or x==y:raise ValueError('invalid rule endpoint')
            adjacent[x].add(y);adjacent[y].add(x)
        reached=set();todo=[next(iter(rn))]
        while todo:
            x=todo.pop()
            if x not in reached:reached.add(x);todo.extend(adjacent[x]-reached)
        if len(reached)!=len(rn):raise ValueError('disconnected rule')
        for eq in rule.get('equal',()):
            if len(eq)!=4 or any(not isinstance(x,str) for x in eq) or eq[0] not in rn or eq[2] not in rn:
                raise ValueError('invalid equality constraint')
    matches=[];seen=set();truncated=False;work=0;work_exhausted=False
    def spend():
        nonlocal work,work_exhausted
        if work>=max_work:work_exhausted=True;return False
        work+=1;return True
    def extend(bind,x,left,y,right,rule):
        candidate=dict(bind)
        for var,ident in ((x,left),(y,right)):
            if var in candidate and candidate[var]!=ident:return None
            if by_id[ident]['role']!=rule['nodes'][var]:return None
            candidate[var]=ident
        if len(set(candidate.values()))!=len(candidate):return None
        if any(not isinstance(by_id[v]['evidence'].get('space'),str) or not isinstance(by_id[v]['evidence'].get('source_sha256'),str) for v in candidate.values()):return None
        spaces={by_id[v]['evidence'].get('space') for v in candidate.values()}
        hashes={by_id[v]['evidence'].get('source_sha256') for v in candidate.values()}
        if len(spaces)!=1 or None in spaces or len(hashes)!=1 or None in hashes:return None
        for a,k,b,j in rule.get('equal',()):
            if a in candidate and b in candidate:
                value=by_id[candidate[a]].get(k)
                if value is None or canonical(value)!=canonical(by_id[candidate[b]].get(j)):return None
        return candidate
    def walk(bind,remaining,rule):
        if not remaining:
            yield bind;return
        index=next((i for i,(x,y,_) in enumerate(remaining) if not bind or x in bind or y in bind),None)
        if index is None:raise ValueError('disconnected join')
        x,y,relation=remaining[index];rest=remaining[:index]+remaining[index+1:]
        if x in bind and y in bind:
            pairs=((bind[x],bind[y]),) if (bind[x],bind[y],relation) in edge_set else ()
        elif x in bind:pairs=((bind[x],dest) for dest in outgoing[(bind[x],relation)])
        elif y in bind:pairs=((src,bind[y]) for src in incoming[(bind[y],relation)])
        else:pairs=by_rel[relation]
        for left,right in pairs:
            if not spend():return
            new=extend(bind,x,left,y,right,rule)
            if new is not None:
                yield from walk(new,rest,rule)
                if work_exhausted:return
    for rule in rules:
        for bind in walk({},list(rule['edges']),rule):
            identity=rule['id']+canonical(bind)
            if identity in seen:continue
            seen.add(identity)
            if len(matches)>=max_matches:truncated=True;break
            matches.append({'id':'lead-'+sha256(identity.encode()).hexdigest()[:20],
                            'pattern':rule['id'],'rank':rule['rank'],'title':rule['title'],
                            'status':'structural_match','bindings':{k:by_id[v] for k,v in sorted(bind.items())},
                            'why':[f'{x} --{r}--> {y}' for x,y,r in rule['edges']],
                            'next_probe':rule['next'],'limitations':[rule['limits']],
                            'execution_authorized':False,'runtime_observed':False})
        if truncated or work_exhausted:break
    return {'matches':sorted(matches,key=lambda x:(-x['rank'],x['id'])),
            'match_budget_exhausted':truncated,'work_budget_exhausted':work_exhausted,
            'join_work':work,'rules_sha256':sha256(canonical(rules).encode()).hexdigest()}
