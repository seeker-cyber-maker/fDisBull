"""Generic selector/dispatch facts and bounded observed interaction effects.

No game names or known addresses are used. Code facts are candidates. Runtime
classification uses explicit context/field witnesses, not image-difference size.
"""
from __future__ import annotations
from hashlib import sha256
from .structure_patterns import canonical

SELECTOR_RULE = {
    'id': 'selector-controls-operation',
    'nodes': {'selector': 'selector_test', 'gate': 'branch', 'effect': 'effect'},
    'edges': [('selector', 'gate', 'predicate'), ('gate', 'effect', 'controls')],
    'rank': 84,
    'title': 'A scalar selector chooses a call, write, or return',
    'next': 'Trace the selector producer and the selected operation. An ordinary call is not a screen change; qualify any pending-context consumer and destination readiness.',
    'limits': 'Static short-arm dependency only. The selector is not yet an input event, the callee is not summarized, and local/dispatch outcome requires separate evidence.'}


def selector_facts(rows, predecessors, evidence, field, *, bits, base,
                   max_arm_steps=12, max_sites=2048):
    """Extract short CMP-immediate / JE-or-JNE / operation arms.

    The existing native producer supplies decoded, bounded candidate rows. A join,
    unknown instruction, another conditional, call, return, or memory store ends
    an arm. Edges describe conditional reachability, never an execution order
    across a call. Both equality and inequality alternatives are retained.
    """
    if type(max_arm_steps) is not int or not 1<=max_arm_steps<=64:
        raise ValueError('arm steps outside 1..64')
    if type(max_sites) is not int or not 1<=max_sites<=10000:
        raise ValueError('selector sites outside 1..10000')
    import capstone as cs
    from capstone.x86 import X86_OP_IMM, X86_OP_REG, X86_OP_MEM
    from .decoder import decode
    nodes=[]; edges=[]; sites=0; unresolved=[]
    # Competing decodes through instruction interiors are not a qualified arm.
    # Keep source traversal diagnostics, but refuse these local dependencies.
    overlap=set();active=[]
    for r in sorted(rows.values(),key=lambda r:r['at']):
        active=[p for p in active if p['at']+p['ins'].size>r['at']]
        for p in active:
            if p['at']!=r['at'] or p['ins'].size!=r['ins'].size:
                overlap.update((p['key'],r['key']))
        active.append(r)
    def checked(row):
        if row['key'] in overlap:return False
        ins=row['ins']; d=decode(bytes(ins.bytes),ins.address,'x86',bits)
        return d is not None and d['size']==ins.size
    def expr(o, ins):
        if o.type==X86_OP_REG:return {'register':ins.reg_name(o.reg),'width':o.size}
        if o.type==X86_OP_MEM:return {'memory':field(o,ins)}
        return {'immediate':o.imm,'width':o.size}
    for key,row in sorted(rows.items(),key=lambda kv:kv[1]['at']):
        ins=row['ins'];ops=ins.operands
        if ins.mnemonic!='cmp' or len(ops)!=2 or ops[0].type not in (X86_OP_REG,X86_OP_MEM) or ops[1].type!=X86_OP_IMM:continue
        gate=rows.get(row['next'])
        if not gate or predecessors[gate['key']]!=1 or gate['ins'].mnemonic not in ('je','jne','jz','jnz'):continue
        if not checked(row) or not checked(gate):continue
        if sites>=max_sites:
            unresolved.append({'reason':'selector site budget','offset':row['at']});break
        sites+=1;ev=evidence(row);prefix=ev['space']+':selector:'+str(row['at'])
        selector={'id':prefix+':test','role':'selector_test','operand':expr(ops[0],ins),
                  'value':ops[1].imm & ((1<<(8*ops[0].size))-1),'evidence':ev}
        branch={'id':prefix+':gate','role':'branch','condition':gate['ins'].mnemonic,
                'evidence':evidence(gate)}
        nodes.extend((selector,branch));edges.append((selector['id'],branch['id'],'predicate'))
        target=gate['ins'].operands[0].imm
        taken=(key[0],target&65535 if bits==16 else target-base)
        equality_taken=gate['ins'].mnemonic in ('je','jz')
        for path,at in (('taken',taken),('fallthrough',gate['next'])):
            seen=set();witness=[evidence(gate)];reason='arm budget'
            for _ in range(max_arm_steps):
                if at in seen:reason='loop';break
                seen.add(at)
                r=rows.get(at)
                if r is None:reason='undecoded continuation';break
                if predecessors[at]!=1:reason='join/other predecessor';break
                if not checked(r):reason='decoder disagreement';break
                i=r['ins'];o=i.operands;kind=None;payload={}
                witness.append(evidence(r))
                if i.group(cs.CS_GRP_CALL):
                    kind='call';payload={'target':o[0].imm if len(o)==1 and o[0].type==X86_OP_IMM else None,
                                         'operand_text':i.op_str,'callee_summary':'unknown'}
                elif i.mnemonic in ('ret','retf','iret','iretd'):
                    kind='return';payload={'return_value':'not inferred'}
                elif i.mnemonic in ('mov','and','or','xor','add','sub','inc','dec') and o and o[0].type==X86_OP_MEM:
                    kind='memory_write';payload={'destination':field(o[0],i),'write_operation':i.mnemonic,
                       'source':expr(o[1],i) if len(o)==2 else None,'storage_role':'unresolved'}
                if kind:
                    effect={'id':prefix+':'+path+':'+str(r['at']),'role':'effect','operation':kind,
                            'selector_relation':'equal' if ((path=='taken')==equality_taken) else 'not_equal',
                            'evidence':evidence(r),'path_witness':witness,**payload}
                    nodes.append(effect);edges.append((branch['id'],effect['id'],'controls'));reason=None;break
                if i.mnemonic=='jmp' and len(o)==1 and o[0].type==X86_OP_IMM:
                    at=(key[0],o[0].imm&65535 if bits==16 else o[0].imm-base);continue
                # Only explicit register/stack argument preparation, no opaque
                # string operations, interrupt, nested decision, or side effects.
                if i.mnemonic not in ('mov','movzx','movsx','lea','push','pop','add','sub','xor','and','or','inc','dec','nop'):
                    reason='unsummarized instruction';break
                if o and o[0].type==X86_OP_MEM:
                    reason='unsummarized memory effect';break
                at=r['next']
            if reason:unresolved.append({'selector_offset':row['at'],'arm':path,'reason':reason})
    return nodes,edges,{'selector_sites':sites,'operations':sum(n['role']=='effect' for n in nodes),
                       'unresolved_count':len(unresolved),'unresolved':unresolved[:50],
                       'overlapping_rows':len(overlap),'complete':not unresolved and not overlap,'scope':'bounded single-entry arms; no event or scene label inferred'}


def classify_episode(episode):
    """Classify *observed* effects with independent context and state axes.

    Caller supplies retained, source-bound observation references. Context is a
    qualified semantic view identity, NOT an image hash or pixel-change score.
    A same-context outcome is bounded to this episode, never proof of no deferred
    changes. This function issues no input, memory edits, or automatic retries.
    """
    if not isinstance(episode,dict):raise ValueError('episode must be an object')
    import json
    import re
    try:json.dumps(episode,allow_nan=False)
    except (ValueError,TypeError) as exc:raise ValueError('episode must contain finite JSON data') from exc
    before=episode.get('before');samples=episode.get('after');idle=episode.get('idle',[])
    if not isinstance(before,dict) or not isinstance(samples,list) or not 1<=len(samples)<=4096:
        raise ValueError('require before and 1..4096 after observations')
    if not isinstance(idle,list) or len(idle)>4096:raise ValueError('idle observation budget')
    identity=before.get('identity')
    if not isinstance(identity,dict) or any(k not in identity or identity[k] is None or identity[k]=='' for k in ('source_sha256','run','epoch')):
        raise ValueError('require source, run and restoration epoch')
    if not isinstance(identity['source_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',identity['source_sha256']):
        raise ValueError('invalid original source hash')
    def validate(o):
        if not isinstance(o,dict) or o.get('identity')!=identity:raise ValueError('mixed observation identity')
        if not isinstance(o.get('evidence'),str) or not o['evidence']:raise ValueError('missing observation evidence')
        if type(o.get('tick')) is not int or o['tick']<0:raise ValueError('invalid logical time')
        if not isinstance(o.get('fields',{}),dict) or len(o.get('fields',{}))>64:raise ValueError('invalid selected fields')
        for key in ('ready','pending','presentation_changed'):
            if o.get(key) is not None and type(o[key]) is not bool:
                raise ValueError(key+' must be Boolean or unknown')
        if o.get('context') is not None and (not isinstance(o['context'],str) or not o['context']):
            raise ValueError('context must be a nonempty qualified identity or unknown')
    validate(before)
    previous=before['tick']
    for o in samples:
        validate(o)
        if o['tick']<=previous:raise ValueError('after observations must advance logical time')
        previous=o['tick']
    idle_tick=-1
    for o in idle:
        validate(o)
        if not idle_tick<o['tick']<before['tick']:
            raise ValueError('idle samples must precede the pre-input observation in order')
        idle_tick=o['tick']
    last=samples[-1];old=before.get('context');new=last.get('context')
    contexts=[o.get('context') for o in samples]
    active_pending=any(o.get('pending') is True for o in samples) and last.get('pending') is not False
    pending=True if active_pending else (False if last.get('pending') is False else None)
    boundary_known=old is not None and new is not None and before.get('ready') is True and last.get('ready') is True
    context_changes=[c for c in contexts if c is not None and old is not None and c!=old]
    nav='changed' if boundary_known and old!=new else ('roundtrip' if boundary_known and context_changes else ('same' if boundary_known else 'unresolved'))
    if pending is True:nav='unresolved'
    bf=before.get('fields',{});af=last.get('fields',{})
    unstable={k for o in idle for k in bf if k not in o.get('fields',{}) or o['fields'][k]!=bf[k]}
    changed={k:{'before':bf[k],'after':af[k]} for k in sorted(bf.keys()&af.keys()) if bf[k]!=af[k]}
    discriminating={k:v for k,v in changed.items() if k not in unstable}
    state=('unobserved' if not bf and not af else
           ('changed' if discriminating else
            ('unresolved' if bf.keys()!=af.keys() or changed else 'unchanged-selected')))
    if nav=='unresolved':category='pending-or-unresolved'
    elif nav in ('changed','roundtrip'):category='mixed' if state=='changed' else 'dispatch-effect'
    elif state=='changed':category='local-effect'
    elif last.get('presentation_changed') is True:category='presentation-only-candidate'
    else:category='no-selected-effect'
    next_probe={'pending-or-unresolved':'Follow the pending operation/consumer and wait within a bounded budget; do not replay a possibly accepted input.',
      'mixed':'Qualify both the state change and the context transition before exposing a combined action.',
      'dispatch-effect':'Trace the context-request writer and dispatcher; verify destination controls, not just new pixels.',
      'local-effect':'Find readers/writers of the changed selected fields and test reversal or confirmation while preserving context.',
      'presentation-only-candidate':'Find whether feedback precedes a semantic effect; a pressed button is not completed activation.',
      'no-selected-effect':'Check input consumption, disabled/empty choice, wrong context, and missing observations.'}[category]
    return {'format':'fdisbull-interaction-classification-1','category':category,
            'context_effect':nav,'state_effect':state,'changed_fields':discriminating,
            'idle_varying_fields':sorted(unstable),'idle_samples':len(idle),'pending':pending,
            'idle_context_stable':bool(idle) and all(o.get('context')==old and o.get('ready') is True for o in idle),
            'control_design':'preceding idle interval, not a matched counterfactual replay',
            'before_context':old,'after_context':new,'observed_contexts':list(dict.fromkeys(contexts)),
            'last_tick':last['tick'],'sample_count':len(samples),
            'scope':'selected fields and sampled contexts over the recorded interval; classification does not prove causation or completeness',
            'next_probe':next_probe,'execution_authorized':False,
            'episode_sha256':sha256(canonical(episode).encode()).hexdigest()}


def main(argv=None):
    """Read one retained episode and print its bounded classification as JSON."""
    import argparse
    import json
    from pathlib import Path
    parser=argparse.ArgumentParser(description='Classify a retained interaction; never execute its inputs')
    parser.add_argument('episode',type=Path)
    args=parser.parse_args(argv)
    try:
        if args.episode.is_symlink() or not args.episode.is_file():raise ValueError('require a regular episode file')
        with args.episode.open('rb') as stream:raw=stream.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:raise ValueError('episode exceeds 8 MiB')
        doc=json.loads(raw)
        print(canonical(classify_episode(doc)))
    except (ValueError,OSError,TypeError) as exc:
        parser.exit(2,'interaction refused: '+str(exc)+'\n')


if __name__=='__main__':main()
