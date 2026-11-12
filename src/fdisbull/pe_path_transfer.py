"""A bounded symbolic register transfer for completed PE patch paths.

Only full-width register MOV, one-byte NOP, and direct near branches are
admitted. The result is conditional on the captured paths; branch guards,
unselected state and whole-program intent remain outside this contract.
"""
from __future__ import annotations

import re

from iced_x86 import Decoder, FlowControl, OpKind

from .behavior_diff import compare_trace_topology
from .debug_semantics import PE_TRACE_SEMANTICS
from .pe_step_model import check_pe_step_model
from .uil_catalog import from_asm_instruction
from .wine_arch import flags_name, ip_name, register_names, validate_context


_SHA256 = re.compile(r'[0-9a-f]{64}\Z')
_NEAR = {OpKind.NEAR_BRANCH16, OpKind.NEAR_BRANCH32, OpKind.NEAR_BRANCH64}


def _unknown(reason, topology=None):
    return {'status': 'unknown', 'reason': reason, 'topology': topology,
            'register_transfer': None, 'semantic_equivalence': None}


def _address(value):
    if not isinstance(value, str):
        raise ValueError('PE trace address must be a hexadecimal string')
    return int(value, 16)


def _qualified_trace(trace):
    if not isinstance(trace, dict) or not isinstance(trace.get('events'), list):
        raise ValueError('Raw PE trace with events is required')
    mapping = trace.get('mapping')
    if (not isinstance(mapping, dict) or mapping.get('backend') != 'wine-qemu'
            or type(mapping.get('bits')) is not int or mapping['bits'] not in (32, 64)
            or type(trace.get('version')) is not int
            or trace.get('semantics') != PE_TRACE_SEMANTICS
            or any(not isinstance(mapping.get(key), str)
                   or not _SHA256.fullmatch(mapping[key])
                   for key in ('source_sha256', 'version_sha256'))):
        raise ValueError('Source-bound completed Wine/QEMU PE trace is required')
    events = trace['events']
    if not 2 <= len(events) <= 10000 or any(not isinstance(item, dict) for item in events):
        raise ValueError('PE trace must contain 2..10000 events')
    bits, version = mapping['bits'], trace['version']
    for event in events:
        identity = event.get('identity')
        if (not isinstance(identity, dict) or identity.get('context') != 'flat'
                or identity.get('source_version') != version
                or identity.get('project_address') != event.get('project_address')
                or identity.get('runtime_address') != event.get('address')):
            raise ValueError('PE trace event identity is incomplete')
        try:
            _address(event['address'])
            _address(event['project_address'])
            validate_context(event['registers'], bits)
            if _address(event['registers'][ip_name(event['registers'])]) != _address(event['address']):
                raise ValueError('Pre-instruction PC differs from trace address')
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('PE trace event has incomplete register or address evidence') from exc
        observation = event.get('observation')
        if not isinstance(observation, dict) or observation.get('registers_stage') != 'before-instruction':
            raise ValueError('PE trace requires before-instruction register evidence')
    return bits


def _state(event, bits):
    registers = event['registers']
    general = register_names(bits) - {ip_name(registers), flags_name(registers)}
    return ({name: int(registers['general'][name], 16) for name in general},
            int(registers[flags_name(registers)], 16), registers.get('thread'))


def _project_path(trace, bits):
    events = trace['events']
    names = sorted(register_names(bits) - ({'rip', 'rflags'} if bits == 64 else {'eip', 'eflags'}))
    transfer = {name: name for name in names}
    moves, branches, neutral = [], [], []
    for index, (event, following) in enumerate(zip(events, events[1:], strict=False)):
        observation = event['observation']
        if observation.get('instruction_completed') is not True:
            return _unknown(f'Event {index} does not certify instruction completion')
        before, before_flags, thread = _state(event, bits)
        after, after_flags, next_thread = _state(following, bits)
        if thread is None or thread != next_thread:
            return _unknown(f'Event {index} changes selected thread')
        raw_hex = event.get('execution_bytes', event.get('bytes'))
        try:
            if not isinstance(raw_hex, str) or not 2 <= len(raw_hex) <= 30 or len(raw_hex) % 2:
                raise ValueError('invalid instruction length')
            raw = bytes.fromhex(raw_hex)
            address = _address(event['address'])
            next_address = _address(following['address'])
            instruction = Decoder(bits, raw, ip=address).decode()
            if instruction.is_invalid or instruction.len != len(raw):
                raise ValueError('instruction is not exact')
        except (KeyError, TypeError, ValueError):
            return _unknown(f'Event {index} lacks one exact executed instruction')
        if raw == b'\x90':
            kind, destination, source = 'nop', None, None
            allowed_next = {address + len(raw)}
        elif ((instruction.is_jmp_short_or_near or instruction.is_jcc_short_or_near)
              and instruction.flow_control in (FlowControl.UNCONDITIONAL_BRANCH,
                                               FlowControl.CONDITIONAL_BRANCH)
              and instruction.op_count == 1 and instruction.op0_kind in _NEAR):
            kind, destination, source = 'direct_branch', None, None
            allowed_next = {instruction.near_branch_target}
            if instruction.flow_control == FlowControl.CONDITIONAL_BRANCH:
                allowed_next.add(address + len(raw))
        else:
            try:
                model = from_asm_instruction(raw, bits=bits, flags='explicit')
            except ValueError:
                return _unknown(f'Event {index} is outside the register-only model')
            if model['source'].get('mnemonic') != 'mov':
                return _unknown(f'Event {index} is outside the MOV/NOP/branch profile')
            destination = model['source']['outputs'][0]
            source = model['source']['inputs'][0]
            if destination not in transfer or source not in transfer:
                return _unknown(f'Event {index} uses a partial register view')
            check = check_pe_step_model(trace, index)
            if check['status'] != 'agreement':
                return _unknown(f'Event {index} register model did not agree: {check["status"]}')
            kind = 'mov'
            allowed_next = {address + len(raw)}
        if next_address not in allowed_next:
            return _unknown(f'Event {index} does not lead to the recorded next site')
        if after_flags != before_flags:
            return _unknown(f'Event {index} changes flags outside this profile')
        if kind == 'mov':
            if after[destination] != before[source] or any(
                    after[name] != before[name] for name in names if name != destination):
                return _unknown(f'Event {index} changes undeclared register state')
            identity_write = transfer[destination] == transfer[source]
            transfer[destination] = transfer[source]
            moves.append({'event_index': index, 'destination': destination,
                          'source': source, 'identity_write': identity_write})
        elif after != before:
            return _unknown(f'Event {index} changes register state outside this profile')
        elif kind == 'nop':
            neutral.append(index)
        else:
            branches.append({'event_index': index,
                             'conditional': instruction.flow_control == FlowControl.CONDITIONAL_BRANCH})
    live = set(names)
    dead = []
    for move in reversed(moves):
        destination, source = move['destination'], move['source']
        if destination not in live:
            dead.append(move['event_index'])
        else:
            live.remove(destination)
            live.add(source)
    return {'status': 'admitted', 'transfer': transfer,
            'dead_write_events': sorted(dead),
            'identity_write_events': [move['event_index'] for move in moves if move['identity_write']],
            'nop_events': neutral, 'branch_events': branches,
            'instruction_count': len(events) - 1}


def compare_pe_register_paths(baseline, layer, *, same_source=False, correspondence=None):
    """Compare full-register transfer along two evidenced, captured PE paths.

    Equality holds for the admitted register-only instructions conditional on
    each captured control path. It does not compare path guards or other effects.
    """
    left_bits, right_bits = _qualified_trace(baseline), _qualified_trace(layer)
    if left_bits != right_bits:
        return _unknown('PE process widths differ')
    left_mapping, right_mapping = baseline['mapping'], layer['mapping']
    if same_source and any(left_mapping[key] != right_mapping[key]
                           for key in ('source_sha256', 'version_sha256')):
        raise ValueError('Same-source PE paths require matching byte identities')
    topology = compare_trace_topology(baseline, layer,
                                      same_source=same_source, correspondence=correspondence)
    segments = topology['segments']
    if (topology['alignment'] != 'evidenced' or topology['segments_truncated']
            or not segments or segments[0]['kind'] != 'common'
            or segments[-1]['kind'] != 'common'
            or segments[0]['baseline'][0] != 0 or segments[0]['layer'][0] != 0
            or segments[-1]['baseline'][1] != len(baseline['events'])
            or segments[-1]['layer'][1] != len(layer['events'])
            or any(segment['kind'] not in ('common', 'divergent') for segment in segments)):
        return _unknown('A complete evidenced path from common entry to common exit is required', topology)
    left, right = _project_path(baseline, left_bits), _project_path(layer, right_bits)
    if left['status'] != 'admitted' or right['status'] != 'admitted':
        return _unknown('At least one path is outside the admitted register-only profile', topology) | {
            'baseline': left, 'layer': right}
    relation = 'equal' if left['transfer'] == right['transfer'] else 'different'
    entry_state_equal = (_state(baseline['events'][0], left_bits)[:2]
                         == _state(layer['events'][0], right_bits)[:2])
    exit_state_equal = (_state(baseline['events'][-1], left_bits)[:2]
                        == _state(layer['events'][-1], right_bits)[:2])
    return {'status': 'compared', 'register_transfer': relation,
            'baseline': left, 'layer': right, 'topology': topology,
            'recorded_sources': {
                'baseline': {key: baseline['mapping'][key] for key in ('source_sha256', 'version_sha256')},
                'layer': {key: layer['mapping'][key] for key in ('source_sha256', 'version_sha256')}},
            'sampled_entry_state_equal': entry_state_equal,
            'sampled_exit_state_equal': exit_state_equal,
            'path_guards': 'uncompared', 'memory_effects': 'no memory operands in admitted instructions',
            'external_effects': 'outside selected-thread trace',
            'semantic_equivalence': None,
            'scope': 'Full-width register mapping and FLAGS preservation conditional on each captured path'}
