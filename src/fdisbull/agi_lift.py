"""Source-bound AGI v2 scalar state projection into existing IL.

A decoded instruction is not a runtime observation. The legacy linear shape is
retained; bounded acyclic components add conditions and captured direct calls.
No ASM, guest runtime, scheduler or I/O is used.
"""
from copy import deepcopy

from .agi import AGI2917Processor
from .interaction_il import change_role, validate_il
from .processor import Location, decode_instruction


from .agi_source import bind_program, validate_resource as _validate_resource


def _lift_linear(resource, *, initial_state, max_instructions=128):
    """Return source-bound UDL and UIL for a complete admitted fragment.

    ``initial_state`` exactly binds every touched ``$agi_vN`` (u8) and
    ``$agi_fN`` (bool). The return instruction is an explicit boundary,
    not an IL instruction or a claim about the caller's continuation.
    """
    _validate_resource(resource)
    if type(max_instructions) is not int or not 1 <= max_instructions <= 128:
        raise ValueError('max_instructions must be in 1..128')
    if not isinstance(initial_state, dict):
        raise ValueError('initial_state must be an explicit mapping')
    p = AGI2917Processor(resource.space)
    code = resource.code
    instructions = []
    offset = 0
    for _ in range(max_instructions):
        if offset >= len(code):
            raise ValueError('missing final return')
        decoded = decode_instruction(p, code, Location(resource.space, offset))
        facts = decoded.facts
        opcode = facts['opcode']
        if opcode not in (0, 3, 12, 13):
            raise ValueError('unsupported instruction or control flow')
        instructions.append((offset, facts))
        offset += facts['size']
        if opcode == 0:
            if offset != len(code):
                raise ValueError('trailing code after return is unsupported')
            break
    else:
        raise ValueError('instruction budget exhausted before return')
    touched = {}
    for _, facts in instructions:
        op = facts['opcode']
        if op == 3:
            touched[f"$agi_v{facts['operands'][0]['index']}"] = 'u8'
        elif op in (12, 13):
            touched[f"$agi_f{facts['operands'][0]['index']}"] = 'bool'
    if initial_state.keys() != touched.keys():
        raise ValueError('initial_state must bind exactly the touched variables and flags')
    for name, typ in touched.items():
        value = initial_state[name]
        if (typ == 'bool' and type(value) is not bool) or (typ == 'u8' and (type(value) is not int or not 0 <= value <= 255)):
            raise ValueError('initial_state value has wrong type or width')
    variables = {name: {'type': typ, 'initial': initial_state[name]} for name, typ in sorted(touched.items())}
    body, evidence = [], {}
    for offset, facts in instructions:
        ident = f'agi_{offset:04x}'
        evidence[ident] = {'sha256': resource.resource_sha256, 'range': [offset + 2, offset + 2 + facts['size']],
                           'space': resource.space, 'code_range': [offset, offset + facts['size']],
                           'volume_offset': resource.code_offset + offset,
                           'instruction_bytes': facts['bytes']}
        op = facts['opcode']
        if op == 0:
            continue
        index = facts['operands'][0]['index']
        name = f'$agi_v{index}' if op == 3 else f'$agi_f{index}'
        value = facts['operands'][1]['value'] if op == 3 else op == 12
        body.append({'id': ident, 'op': 'set', 'var': name, 'value': value, 'evidence': [ident]})
    udl = {'format': 'fdisbull-il-1', 'role': 'udl', 'variables': variables,
           'resources': {}, 'body': body, 'evidence': evidence}
    validate_il(udl)
    return {'format': 'fdisbull-agi-state-projection-1', 'source': resource.provenance(),
            'udl': udl, 'uil': change_role(udl, 'uil'),
            'return_boundary': {'space': resource.space, 'offset': instructions[-1][0],
                                'kind': 'logic-return', 'continuation': 'unknown'},
            'qualification': 'state_projection_only', 'runtime_execution': False,
            'bounds': ['straight-line assignn/set/reset; final return',
                       'scheduler, I/O, caller and whole-game behavior excluded'],
            'initial_state': deepcopy(initial_state)}


def _linear_candidate(code):
    offset = 0
    while offset < len(code):
        op = code[offset]
        if op == 0:
            return True
        if op not in (3,12,13):
            return False
        offset += 3 if op == 3 else 2
    return True


def lift_logic(resource, *, initial_state, max_instructions=128, entry_offset=0,
               stop_offsets=(), callees=(), callee_entries=None, max_call_depth=8,
               stop_points=()):
    """Lift a bounded scalar source component, including explicit direct calls.

    Callee entries witness cached AGI scan-start positions, in code-relative
    bytes. An explicit stop inside a callee ends the entire component there;
    its caller does not resume. No target is inferred from the initial values.
    """
    program = bind_program(resource, callees=callees, callee_entries=callee_entries,
                           entry_offset=entry_offset, stop_offsets=stop_offsets,
                           stop_points=stop_points)
    if type(max_call_depth) is not int or not 1 <= max_call_depth <= 8:
        raise ValueError('max_call_depth must be in 1..8')
    if (entry_offset == 0 and not stop_offsets and not stop_points and not callees
            and not callee_entries and _linear_candidate(resource.code)):
        return _lift_linear(resource,initial_state=initial_state,max_instructions=max_instructions)
    from .agi_control import lift_program
    return lift_program(program,initial_state=initial_state,max_instructions=max_instructions,
                        max_call_depth=max_call_depth)
