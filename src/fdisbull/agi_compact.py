"""Source-bound acyclic AGI graphs with one shared continuation per location.

Opaque actions retain known encoded control flow but prohibit evaluation.
They never stand in for executed engine effects.
"""
from collections import Counter
from copy import deepcopy

from .agi_control import _Lift
from .interaction_il import change_role, validate_il


class _CompactLift(_Lift):
    def __init__(self, program, max_instructions, max_call_depth, allow_opaque):
        super().__init__(program, max_instructions, max_call_depth)
        self.allow_opaque = allow_opaque
        self.continuations, self.completed, self.active = {}, {}, set()
        self.opaque = []

    def build(self, logic, pc, call_path=()):
        key = (logic, pc)
        if key in self.active:
            raise ValueError('cyclic AGI control flow is not qualified')
        if key in self.completed:
            return self.completed[key]
        if len(self.active) >= 256:
            raise ValueError('control construction depth budget exhausted')
        self.active.add(key)
        stopped = key in self.stops
        decoded = None if stopped else self.instruction(logic, pc)
        facts = decoded.facts if decoded else None
        ident = self.evidence_for(logic, pc, facts)
        self.block_sources[ident] = dict(logic=logic, offset=pc, source_entry=True,
                                        instruction=facts['mnemonic'] if facts else 'component-stop')
        body, returns, depth = [], False, 0
        if stopped:
            transfer = {'op':'stop'}
            self.exits.append(dict(logic=logic, offset=pc, kind='declared-component-stop',
                                   caller_continuation='not_executed', call_stack='runtime'))
        else:
            op, end = facts['opcode'], pc+facts['size']
            if op == 0:
                transfer, returns = {'op':'return'}, True
                self.exits.append(dict(logic=logic, offset=pc, kind='logic-return', call_stack='runtime'))
            elif op == 0xff:
                condition = self.condition(facts.get('conditions', []))
                edges = {e.kind:e.target for e in decoded.successors}
                if any(edges.get(k) is None for k in ('true','false')):
                    raise ValueError('unresolved conditional target')
                yes, yr, yd = self.build(logic, edges['true'].offset, call_path)
                no, nr, nd = self.build(logic, edges['false'].offset, call_path)
                transfer = {'op':'if','condition':condition,'then':yes,'else':no}
                returns, depth = yr or nr, max(yd,nd)
            elif op == 22:
                target = self.resources[logic].code[pc+1]
                if target == logic or target in call_path:
                    raise ValueError('recursive logic calls are not qualified')
                if target not in self.resources or target not in self.entries:
                    raise ValueError('logic call requires a captured callee and explicit scan-entry witness')
                entry = self.entries[target]
                callee, callee_returns, callee_depth = self.build(target,entry,call_path+(logic,))
                resume, resume_returns, resume_depth = (None,False,0)
                if callee_returns:
                    resume, resume_returns, resume_depth = self.build(logic,end,call_path)
                depth = max(1+callee_depth,resume_depth)
                if depth > self.call_limit:
                    raise ValueError('logic call depth budget exhausted')
                returns = callee_returns and resume_returns
                transfer = {'op':'call','target':callee,'resume':resume}
                self.calls[key] = dict(logic=logic,offset=pc,target_logic=target,
                                       entry_offset=entry,resume_offset=end,
                                       continuation_admitted=resume is not None)
            elif op == 23:
                raise ValueError('indirect call.v target is not qualified')
            else:
                if op == 0xfe:
                    target = decoded.successors[0].target
                    if target is None:raise ValueError('unresolved branch target')
                    next_pc = target.offset
                else:
                    if op in (*range(1,9),12,13,14):
                        body = self.scalar_nodes(logic,pc,facts,primary=False,suffix='_effect')
                    elif self.allow_opaque and facts['mnemonic'] != 'unsupported':
                        node = self.node(logic,pc,facts,'opaque',primary=False,suffix='_opaque',
                                         reason='Unmodeled AGI action: '+facts['mnemonic'])
                        body = [node]
                        self.opaque.append(dict(logic=logic,offset=pc,opcode=op,
                                                instruction=facts['mnemonic'],block_id=node['id']))
                    else:
                        raise ValueError('unsupported instruction or runtime effect')
                    next_pc = end
                target, returns, depth = self.build(logic,next_pc,call_path)
                transfer = {'op':'goto','target':target}
        self.continuations[ident] = {'body':body,'transfer':transfer}
        self.active.remove(key)
        result = (ident,returns,depth)
        self.completed[key] = result
        return result


def lift_compact(program, *, initial_state, max_instructions=128, max_call_depth=8,
                 allow_opaque=False):
    if type(max_instructions) is not int or not 1 <= max_instructions <= 128:
        raise ValueError('max_instructions must be in 1..128')
    if type(max_call_depth) is not int or not 1 <= max_call_depth <= 8:
        raise ValueError('max_call_depth must be in 1..8')
    if type(allow_opaque) is not bool or not isinstance(initial_state,dict):
        raise ValueError('explicit state mapping and boolean allow_opaque required')
    compiler = _CompactLift(program,max_instructions,max_call_depth,allow_opaque)
    entry,_,depth = compiler.build(program.root.logic,program.entry_offset)
    if depth > max_call_depth:raise ValueError('logic call depth budget exhausted')
    for logic,offset in compiler.stops:
        if any(start < offset < end for start,end in compiler.spans.get(logic,())):
            raise ValueError('stop boundary overlaps an encoded instruction')
    if initial_state.keys() != compiler.types.keys():
        raise ValueError('initial_state must bind exactly all reachable read/write variables and flags')
    variables = {name:{'type':typ,'initial':initial_state[name]}
                 for name,typ in sorted(compiler.types.items())}
    udl = dict(format='fdisbull-il-2',role='udl',variables=variables,resources={},
               entry=entry,continuations=dict(sorted(compiler.continuations.items())),
               evidence=compiler.evidence)
    validate_il(udl)
    incoming = Counter()
    for item in compiler.continuations.values():
        transfer = item['transfer']
        for field in ('target','resume','then','else'):
            if transfer.get(field) is not None:incoming[transfer[field]] += 1
    return dict(format='fdisbull-agi-state-projection-3',source=program.provenance(),
                control_flow='shared_continuations',udl=udl,uil=change_role(udl,'uil'),
                qualification='control_flow_only' if compiler.opaque else 'state_projection_only',
                runtime_execution=False,coverage='selected_acyclic_source_graph',
                exits=compiler.exits,calls=list(compiler.calls.values()),
                block_sources=compiler.block_sources,initial_state=deepcopy(initial_state),
                read_set=sorted(compiler.reads),write_set=sorted(compiler.writes),
                opaque_operations=compiler.opaque,
                static_metrics=dict(source_instructions=len(compiler.instructions),
                                    continuations=len(compiler.continuations),
                                    shared_joins=sum(n>1 for n in incoming.values())),
                limits=dict(max_instructions=max_instructions,max_call_depth=max_call_depth,
                            max_il_nodes=1024,max_document_bytes=65536),
                bounds=['nominal scalar AGI semantics; explicit scan-entry assumptions',
                        'opaque actions prohibit execution of the entire graph',
                        'cycles, indirect calls, parser and whole-game effects excluded'])
