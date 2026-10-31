"""Source-bound straight-line AGI v2 state projection into existing IL.

A decoded instruction is not a runtime observation. Only assignn, set, reset
and a final return are admitted; no ASM, guest runtime, scheduler or I/O is used.
"""
from copy import deepcopy
from hashlib import sha256

from .agi import AGI2917Processor, AGILogicResource
from .interaction_il import change_role, validate_il
from .processor import Location, decode_instruction


def _validate_resource(resource):
    if type(resource) is not AGILogicResource:
        raise ValueError('expected immutable AGI logic resource')
    directory, volume, payload, code = resource._directory, resource._volume, resource.payload, resource.code
    if any(type(v) is not bytes for v in (directory, volume, payload, code)):
        raise ValueError('invalid resource snapshot bytes')
    if (resource.profile != '2.917' or type(resource.logic) is not int or not 0 <= resource.logic <= 255
            or len(directory) > 768 or len(directory) % 3 or resource.logic * 3 + 3 > len(directory)
            or len(volume) > 2 * 1024 * 1024):
        raise ValueError('invalid resource snapshot metadata')
    entry = int.from_bytes(directory[resource.logic*3:resource.logic*3+3], 'big')
    number, offset = entry >> 20, entry & 0xfffff
    if (offset == 0xfffff or type(resource.volume) is not int or resource.volume != number
            or type(resource.resource_offset) is not int or resource.resource_offset != offset
            or offset + 5 > len(volume) or volume[offset:offset+2] != b'\x12\x34'
            or volume[offset+2] != number):
        raise ValueError('resource directory or volume header mismatch')
    length = int.from_bytes(volume[offset+3:offset+5], 'little')
    if (type(resource.resource_length) is not int or length != resource.resource_length
            or length < 2 or offset + 5 + length > len(volume)
            or payload != volume[offset+5:offset+5+length]
            or type(resource.code_offset) is not int or resource.code_offset != offset+7):
        raise ValueError('resource payload provenance mismatch')
    size = int.from_bytes(payload[:2], 'little')
    if (size == 0 or size + 2 > len(payload) or code != payload[2:2+size]
            or resource.directory_sha256 != sha256(directory).hexdigest()
            or resource.volume_sha256 != sha256(volume).hexdigest()
            or resource.resource_sha256 != sha256(payload).hexdigest()
            or resource.space != f'agi.logic.{resource.logic}.{sha256(payload).hexdigest()}'):
        raise ValueError('resource source identity mismatch')


def lift_logic(resource, *, initial_state, max_instructions=128):
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
