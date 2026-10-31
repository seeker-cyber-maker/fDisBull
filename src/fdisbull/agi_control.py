"""Bounded acyclic AGI scalar control flow lowered to shared IL primitives.

Calls are expanded with an explicit return stack and captured scan-entry
witnesses. An explicit component boundary inside a callee ends the projection;
it never fabricates a return or executes the caller's continuation.
"""
from collections import Counter
from copy import deepcopy

from .agi import AGI2917Processor
from .interaction_il import change_role, validate_il
from .processor import Location, decode_instruction


def _true():
    return {'op':'eq', 'left':0, 'right':0}


def _not(condition):
    return {'op':'not', 'condition':condition}


def _and(conditions):
    if not conditions:
        return _true()
    return conditions[0] if len(conditions) == 1 else {'op':'and', 'conditions':conditions}


class _Lift:
    def __init__(self, program, max_instructions, max_call_depth):
        self.program, self.root = program, program.root.logic
        self.resources, self.entries = program.resources, dict(program.callee_entries)
        self.processors = {key:AGI2917Processor(resource.space) for key,resource in self.resources.items()}
        self.stops = set(program.stop_points) | {(self.root, offset) for offset in program.stop_offsets}
        self.limit, self.call_limit = max_instructions, max_call_depth
        self.instructions, self.spans = {}, {}
        self.types, self.reads, self.writes = {}, set(), set()
        self.evidence, self.block_sources, self.occurrences = {}, {}, Counter()
        self.exits, self.calls = [], {}
        self.expansions = 0

    def variable(self, index, *, flag=False, read=False, write=False):
        name = f'$agi_{"f" if flag else "v"}{index}'
        self.types[name] = 'bool' if flag else 'u8'
        if read: self.reads.add(name)
        if write: self.writes.add(name)
        return name

    def ref(self, index, *, flag=False):
        return {'var':self.variable(index, flag=flag, read=True)}

    def evidence_for(self, logic, offset, facts=None):
        resource = self.resources[logic]
        ident = f'agi_{offset:04x}' if logic == self.root else f'agi_l{logic}_{offset:04x}'
        size = facts['size'] if facts else 0
        self.evidence[ident] = {
            'sha256':resource.resource_sha256, 'space':resource.space,
            'range':[offset+2, offset+2+size], 'code_range':[offset, offset+size],
            'volume_offset':resource.code_offset+offset,
            'instruction_bytes':facts['bytes'] if facts else '',
            'kind':'instruction' if facts else 'declared-component-boundary'}
        return ident

    def node(self, logic, offset, facts, op, *, primary=True, suffix='', **fields):
        evidence = self.evidence_for(logic, offset, facts)
        base = evidence + suffix
        self.occurrences[base] += 1
        ident = base if self.occurrences[base] == 1 else f'{base}_{self.occurrences[base]}'
        if len(self.block_sources) >= 1024:
            raise ValueError('expanded IL node budget exhausted')
        self.block_sources[ident] = {'logic':logic, 'offset':offset,
                                     'source_entry':primary,
                                     'instruction':facts['mnemonic'] if facts else 'component-stop'}
        return dict(id=ident, op=op, evidence=[evidence], **fields)

    def marker(self, logic, offset, facts, frames=()):
        result = self.node(logic, offset, facts, 'require', condition=_true())
        self.block_sources[result['id']]['call_stack'] = [
            {'logic':a,'resume_offset':b} for a,b in frames]
        return result

    def instruction(self, logic, pc):
        key = (logic, pc)
        if key not in self.instructions:
            resource = self.resources[logic]
            if not 0 <= pc < len(resource.code):
                raise ValueError('missing final return or out-of-range source target')
            if len(self.instructions) >= self.limit:
                raise ValueError('source instruction budget exhausted')
            decoded = decode_instruction(self.processors[logic], resource.code, Location(resource.space, pc))
            facts = decoded.facts
            end = pc + facts['size']
            if any(pc < old_end and old_start < end for old_start,old_end in self.spans.get(logic, ())):
                raise ValueError('overlapping AGI instruction interpretations')
            self.spans.setdefault(logic, []).append((pc,end))
            self.instructions[key] = decoded
        return self.instructions[key]

    def condition(self, items):
        if len(items) > 128:
            raise ValueError('condition term budget exhausted')
        terms, group, negate = [], None, False
        for item in items:
            marker = item.get('marker')
            if marker == 'not':
                if negate: raise ValueError('doubled NOT marker')
                negate = True
                continue
            if marker == 'or':
                if negate: raise ValueError('NOT before OR group unsupported')
                if group is None:
                    group = []
                else:
                    # Pure OR in terms of the existing AND/NOT primitives.
                    if not group: raise ValueError('empty OR group is not qualified')
                    terms.append(_not(_and([_not(term) for term in group])))
                    group = None
                continue
            op, args = item.get('opcode'), item.get('operands')
            if op not in range(1,8):
                raise ValueError('unsupported condition; runtime/parser predicates are not scalar facts')
            if op == 7:
                predicate = {'op':'eq', 'left':self.ref(args[0], flag=True), 'right':True}
            else:
                left = self.ref(args[0])
                right = self.ref(args[1]) if op % 2 == 0 else args[1]
                if op in (1,2): predicate = {'op':'eq', 'left':left, 'right':right}
                elif op in (3,4): predicate = {'op':'lt', 'left':left, 'right':right}
                else: predicate = {'op':'lt', 'left':right, 'right':left}
            if negate:
                predicate, negate = _not(predicate), False
            (group if group is not None else terms).append(predicate)
        if negate or group is not None:
            raise ValueError('unfinished condition markers')
        return _and(terms)

    def emit(self, logic, pc, frames=(), path=frozenset()):
        self.expansions += 1
        if self.expansions > 4096:
            raise ValueError('control expansion budget exhausted')
        if len(path) >= 256:
            raise ValueError('control path depth budget exhausted')
        key = (logic, pc, frames)
        if key in path:
            raise ValueError('cyclic AGI control flow is not qualified')
        path = path | {key}
        if (logic,pc) in self.stops:
            self.exits.append({'logic':logic,'offset':pc,'kind':'declared-component-stop',
                               'call_stack':[{'logic':a,'resume_offset':b} for a,b in frames],
                               'caller_continuation':'not_executed'})
            return [self.marker(logic,pc,None,frames)]
        decoded = self.instruction(logic,pc)
        facts, code = decoded.facts, self.resources[logic].code
        op, end = facts['opcode'], pc+facts['size']
        if op == 0:
            marker = self.marker(logic,pc,facts,frames)
            if frames:
                caller, resume = frames[-1]
                return [marker] + self.emit(caller,resume,frames[:-1],path)
            self.exits.append({'logic':logic,'offset':pc,'kind':'logic-return',
                               'call_stack':[],'caller_continuation':'unknown'})
            return [marker]
        if op == 0xff:
            predicate = self.condition(facts.get('conditions', []))
            edges = {edge.kind:edge.target for edge in decoded.successors}
            if any(edges.get(kind) is None for kind in ('true','false')):
                raise ValueError('unresolved conditional target')
            # Allocate parent first; children can expand the same source joins.
            node = self.node(logic,pc,facts,'if',condition=predicate,then=[],**{'else':[]})
            node['then'] = self.emit(logic,edges['true'].offset,frames,path)
            node['else'] = self.emit(logic,edges['false'].offset,frames,path)
            return [node]
        if op == 0xfe:
            target = decoded.successors[0].target
            if target is None: raise ValueError('unresolved branch target')
            return [self.marker(logic,pc,facts,frames)] + self.emit(logic,target.offset,frames,path)
        if op == 22:
            target = code[pc+1]
            if target == logic or target in [frame[0] for frame in frames]:
                raise ValueError('recursive logic calls are not qualified')
            if len(frames) >= self.call_limit:
                raise ValueError('logic call depth budget exhausted')
            if target not in self.resources or target not in self.entries:
                raise ValueError('logic call requires a captured callee and explicit scan-entry witness')
            entry = self.entries[target]
            self.calls[(logic,pc)] = {'logic':logic,'offset':pc,'target_logic':target,
                                      'entry_offset':entry,'resume_offset':end}
            return [self.marker(logic,pc,facts,frames)] + self.emit(target,entry,frames+((logic,end),),path)
        if op == 23:
            raise ValueError('indirect call.v target is not qualified')
        return self.scalar_nodes(logic,pc,facts) + self.emit(logic,end,frames,path)

    def scalar_nodes(self, logic, pc, facts, *, primary=True, suffix=''):
        """Shared scalar lowering; compact source entries own separate trace IDs."""
        op = facts['opcode']
        if op not in (*range(1,9),12,13,14):
            raise ValueError('unsupported instruction or runtime effect')
        args = self.resources[logic].code[pc+1:pc+facts['size']]
        flag = op in (12,13,14)
        name = self.variable(args[0],flag=flag,write=True)
        if op in (1,2):
            value = self.ref(args[0])
            condition = {'op':'lt','left':value if op==1 else 0,'right':255 if op==1 else value}
            child = self.node(logic,pc,facts,'add' if op==1 else 'subtract',
                              primary=False,suffix='_update',var=name,value=1)
            nodes = [self.node(logic,pc,facts,'if',primary=primary,suffix=suffix,condition=condition,then=[child],**{'else':[]})]
        elif op == 14:
            condition = {'op':'eq','left':self.ref(args[0],flag=True),'right':True}
            yes = self.node(logic,pc,facts,'set',primary=False,suffix='_reset',var=name,value=False)
            no = self.node(logic,pc,facts,'set',primary=False,suffix='_set',var=name,value=True)
            nodes = [self.node(logic,pc,facts,'if',primary=primary,suffix=suffix,condition=condition,then=[yes],**{'else':[no]})]
        else:
            value = (op==12) if flag else self.ref(args[1]) if op in (4,6,8) else args[1]
            if op in (5,6,7,8): self.reads.add(name)
            nodes = [self.node(logic,pc,facts,'set' if op in (3,4,12,13) else
                               'add' if op in (5,6) else 'subtract',primary=primary,suffix=suffix,var=name,value=value)]
        return nodes


def lift_program(program, *, initial_state, max_instructions=128, max_call_depth=8):
    if type(max_instructions) is not int or not 1 <= max_instructions <= 128:
        raise ValueError('max_instructions must be in 1..128')
    if type(max_call_depth) is not int or not 1 <= max_call_depth <= 8:
        raise ValueError('max_call_depth must be in 1..8')
    if not isinstance(initial_state,dict):
        raise ValueError('initial_state must be an explicit mapping')
    compiler = _Lift(program,max_instructions,max_call_depth)
    body = compiler.emit(program.root.logic,program.entry_offset)
    for logic,offset in compiler.stops:
        if any(start < offset < end for start,end in compiler.spans.get(logic,())):
            raise ValueError('stop boundary overlaps an encoded instruction')
    if initial_state.keys() != compiler.types.keys():
        raise ValueError('initial_state must bind exactly all reachable read/write variables and flags')
    for name,typ in compiler.types.items():
        value = initial_state[name]
        if ((typ=='bool' and type(value) is not bool)
                or (typ=='u8' and (type(value) is not int or not 0<=value<=255))):
            raise ValueError('initial_state value has wrong type or width')
    variables = {name:{'type':typ,'initial':initial_state[name]} for name,typ in sorted(compiler.types.items())}
    udl = {'format':'fdisbull-il-1','role':'udl','variables':variables,'resources':{},
           'body':body,'evidence':compiler.evidence}
    validate_il(udl)
    return {'format':'fdisbull-agi-state-projection-2','source':program.provenance(),
            'udl':udl,'uil':change_role(udl,'uil'),'qualification':'state_projection_only',
            'runtime_execution':False,'coverage':'selected_acyclic_source_component',
            'exits':compiler.exits,'calls':list(compiler.calls.values()),
            'block_sources':compiler.block_sources,'initial_state':deepcopy(initial_state),
            'read_set':sorted(compiler.reads),'write_set':sorted(compiler.writes),
            'limits':{'max_instructions':max_instructions,'max_call_depth':max_call_depth,
                      'max_expanded_nodes':1024,'max_expansions':4096,'max_path_instructions':256},
            'bounds':['nominal scalar AGI semantics; explicit scan-entry witnesses',
                      'component stops do not return or run caller continuations',
                      'cycles, indirect calls, parser/I/O/scheduler and whole-game effects excluded']}
