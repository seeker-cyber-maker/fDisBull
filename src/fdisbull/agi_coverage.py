"""Aggregate caller-supplied native trial receipts against one lifted graph.

Receipt contents are evidence supplied by the caller, not authenticated proof
of a native session. Only complete, source-bound, internally coherent trials
contribute. This is path coverage, not a whole-game parity claim.
"""
import re

_SHA = re.compile(r'^[0-9a-fA-F]{64}$')


def aggregate_native_coverage(projection, trials):
    """Return bounded source/effect/conditional coverage or raise ValueError."""
    try:
        return _aggregate(projection, trials)
    except (KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ValueError('malformed native coverage input') from exc


def _aggregate(projection, trials):
    if not isinstance(projection, dict) or projection.get('format') != 'fdisbull-agi-state-projection-3':
        raise ValueError('expected compact AGI projection')
    digest=projection['source']['resource_sha256']
    if not isinstance(digest,str) or not _SHA.fullmatch(digest): raise ValueError('invalid source identity')
    doc=projection['uil']; cont=doc['continuations']; source=projection['block_sources']; effects=projection['effect_operations']
    if not isinstance(cont,dict) or not 1<=len(cont)<=128 or not isinstance(effects,list) or len(effects)>128:
        raise ValueError('invalid graph coverage budget')
    offsets={k:source[k]['offset'] for k in cont}
    if any(type(v) is not int or v<0 for v in offsets.values()) or len(set(offsets.values()))!=len(offsets):
        raise ValueError('ambiguous source offsets')
    by_offset={v:k for k,v in offsets.items()}
    if doc['entry'] not in cont:raise ValueError('invalid graph entry')
    effect_offsets=set(); effect_opcodes={}
    for effect in effects:
        if type(effect['offset']) is not int or effect['offset'] not in by_offset or effect['offset'] in effect_offsets:
            raise ValueError('invalid effect site')
        effect_offsets.add(effect['offset'])
        if 'opcode' in effect:
            if type(effect['opcode']) is not int or not 0<=effect['opcode']<=255:raise ValueError('invalid effect opcode')
            effect_opcodes[effect['offset']]=effect['opcode']
    branches={};ambiguous=[]
    for key, block in cont.items():
        transfer=block['transfer'];op=transfer['op']
        if op=='if':
            a,b=transfer['then'],transfer['else']
            if a not in cont or b not in cont:raise ValueError('invalid conditional target')
            branches[offsets[key]]=(offsets[a],offsets[b])
            if a==b:ambiguous.append(offsets[key])
        elif op=='goto':
            if transfer['target'] not in cont:raise ValueError('invalid goto target')
        elif op not in ('return','stop'):raise ValueError('coverage supports leaf graphs only')
    if not isinstance(trials,list) or len(trials)>512:raise ValueError('invalid receipt budget')
    observed=set();seen_effects=set();seen_branches=set();identities=set()
    for trial in trials:
        if not isinstance(trial,dict) or trial.get('format')!='fdisbull-agi-original-host-trial-1' or trial.get('status')!='verified' or trial.get('complete') is not True or trial.get('native_execution') is not True or trial.get('differences')!=[]:
            raise ValueError('receipt is not a complete verified native trial')
        ident=trial['identity']
        if not isinstance(ident,dict) or ident.get('format')!='fdisbull-agi-dos-monitor-1' or ident.get('resource_sha256')!=digest or not isinstance(ident.get('epoch'),str) or not ident['epoch'] or not isinstance(ident.get('session_id'),str) or not ident['session_id']:
            raise ValueError('native identity mismatch')
        identity=(ident['session_id'],ident['epoch'])
        if identity in identities:raise ValueError('duplicate native invocation')
        identities.add(identity)
        attempts=trial['attempts']; seq=trial['source_offsets']
        if not isinstance(seq,list) or not 1<=len(seq)<=128 or not isinstance(attempts,list) or len(attempts)!=len(seq) or seq[0]!=offsets[doc['entry']]:raise ValueError('incomplete source trace')
        for i,(offset,attempt) in enumerate(zip(seq,attempts)):
            if type(offset) is not int or offset not in by_offset or not isinstance(attempt,dict) or attempt.get('offset')!=offset or attempt.get('identity')!=ident or attempt.get('native_execution') is not True:
                raise ValueError('native attempt identity or offset mismatch')
            if not isinstance(attempt.get('stop'),dict) or attempt['stop'].get('outcome')!='breakpoint':raise ValueError('missing native breakpoint evidence')
            if offset in effect_opcodes and attempt.get('opcode')!=effect_opcodes[offset]:raise ValueError('effect opcode mismatch')
            if i==len(seq)-1:
                if attempt.get('status')!='returned' or cont[by_offset[offset]]['transfer']['op']!='return':raise ValueError('missing native return')
            else:
                if attempt.get('status')!='completed' or attempt.get('next_offset')!=seq[i+1]:raise ValueError('missing native step or next offset')
                transfer=cont[by_offset[offset]]['transfer'];op=transfer['op'];nxt=seq[i+1]
                if op=='goto' and nxt!=offsets[transfer['target']]:raise ValueError('invalid native goto')
                if op=='if':
                    a,b=branches[offset]
                    if nxt not in (a,b):raise ValueError('invalid native branch')
                    if a!=b:seen_branches.add((offset,'then' if nxt==a else 'else'))
                elif op!='goto':raise ValueError('invalid native continuation')
        observed.update(seq);seen_effects.update(set(seq)&effect_offsets)
    wanted_branches={(off,d) for off in branches for d in ('then','else')}
    missing_branches=sorted(wanted_branches-seen_branches)
    missing_source=sorted(set(by_offset)-observed);missing_effects=sorted(effect_offsets-seen_effects)
    return {'format':'fdisbull-agi-native-coverage-1','resource_sha256':digest,
            'qualification':'caller-supplied native receipts; source-path coverage, not authenticated proof or whole-game parity',
            'trial_count':len(trials),'source':{'observed':len(observed),'total':len(by_offset),'missing':missing_source},
            'effects':{'observed':len(seen_effects),'total':len(effect_offsets),'missing':missing_effects},
            'branches':{'observed':len(seen_branches),'total':len(wanted_branches),'missing':[{'offset':o,'outcome':d} for o,d in missing_branches], 'same_target_unknown':sorted(ambiguous)},
            'complete':not (missing_source or missing_effects or missing_branches)}
