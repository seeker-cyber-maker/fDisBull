"""Architecture-neutral frame observations from generic IR and solved states.

Offsets describe the logical stack relative to SP on routine entry. They are
not concrete runtime addresses, source-language variables, or a proven calling
convention. ABI profiles describe candidate locations until a signature exists.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import re


def _profile(name, arch, bits, sp, fp, arguments, returns, return_address,
             stack_arguments, outgoing=0, shadow=0, cleanup=None, clobbers=()):
    return dict(name=name, arch=arch, bits=bits, stack_pointer=sp, frame_pointer=fp,
                word_size=bits // 8, argument_registers=arguments, return_registers=returns,
                return_address_size=return_address, stack_argument_offset=stack_arguments,
                outgoing_stack_argument_offset=outgoing, shadow_space=shadow,
                callee_cleanup=cleanup, caller_clobbers=list(clobbers))


ABI_PROFILES = {
    'x86_16_cdecl_near': _profile('x86_16_cdecl_near', 'x86', 16, 'sp', 'bp', [], ['ax', 'dx'], 2, 2, cleanup=0, clobbers=('ax', 'cx', 'dx')),
    'x86_16_cdecl_far': _profile('x86_16_cdecl_far', 'x86', 16, 'sp', 'bp', [], ['ax', 'dx'], 4, 4, cleanup=0, clobbers=('ax', 'cx', 'dx')),
    'x86_32_cdecl': _profile('x86_32_cdecl', 'x86', 32, 'esp', 'ebp', [], ['eax', 'edx'], 4, 4, cleanup=0, clobbers=('eax', 'ecx', 'edx')),
    'x86_32_stdcall': _profile('x86_32_stdcall', 'x86', 32, 'esp', 'ebp', [], ['eax', 'edx'], 4, 4, clobbers=('eax', 'ecx', 'edx')),
    'x86_32_fastcall': _profile('x86_32_fastcall', 'x86', 32, 'esp', 'ebp', ['ecx', 'edx'], ['eax'], 4, 4, clobbers=('eax', 'ecx', 'edx')),
    'x86_32_thiscall': _profile('x86_32_thiscall', 'x86', 32, 'esp', 'ebp', ['ecx'], ['eax'], 4, 4, clobbers=('eax', 'ecx', 'edx')),
    'x86_64_sysv': _profile('x86_64_sysv', 'x86', 64, 'rsp', 'rbp', ['rdi', 'rsi', 'rdx', 'rcx', 'r8', 'r9'], ['rax', 'rdx'], 8, 8,
                              cleanup=0, clobbers=('rax', 'rcx', 'rdx', 'rsi', 'rdi', 'r8', 'r9', 'r10', 'r11')),
    'x86_64_win64': _profile('x86_64_win64', 'x86', 64, 'rsp', 'rbp', ['rcx', 'rdx', 'r8', 'r9'], ['rax'], 8, 40, outgoing=32, shadow=32,
                               cleanup=0, clobbers=('rax', 'rcx', 'rdx', 'r8', 'r9', 'r10', 'r11')),
    'aarch64_aapcs64': _profile('aarch64_aapcs64', 'arm64', 64, 'sp', 'x29', [f'x{i}' for i in range(8)], ['x0', 'x1'], 0, 0,
                                  cleanup=0, clobbers=tuple(f'x{i}' for i in range(19)) + ('x30',)),
}
# Darwin shares integer x0..x7 locations with AAPCS64, but stack packing and
# variadic placement require typed signatures. Leave those offsets unknown.
ABI_PROFILES['aarch64_darwin']=dict(ABI_PROFILES['aarch64_aapcs64'],name='aarch64_darwin',
    stack_argument_offset=None,outgoing_stack_argument_offset=None,
    stack_arguments_require_types=True,platform='Darwin',
    note='Integer register arguments only; Darwin packed stack and variadic arguments are not inferred.')

_ALIASES = {'darwin_arm64':'aarch64_darwin','sysv_x86_64': 'x86_64_sysv', 'sysv_amd64': 'x86_64_sysv', 'sysv': 'x86_64_sysv',
            'win64': 'x86_64_win64', 'windows_x64': 'x86_64_win64', 'aapcs64': 'aarch64_aapcs64',
            'arm64_aapcs64': 'aarch64_aapcs64', 'cdecl16_near': 'x86_16_cdecl_near', 'cdecl16_far': 'x86_16_cdecl_far'}
_STACK_KEY = re.compile(r'^entry_sp:([+-]?\d+):(\d+)$')
_MAX_NODES = 100000


def _unknown(reason):
    return dict(op='unknown', reason=reason)


def _expr(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return dict(op='const', value=value)
    return _unknown('value unavailable')


def _known(value):
    if not isinstance(value, dict):
        return False
    if value.get('op') in ('const', 'stack'):
        return True
    return value.get('op') in ('add', 'sub', 'mul', 'shl', 'and', 'or', 'xor') and all(_known(item) for item in value.get('args', []))


def _affine(value):
    """Return (entry-SP coefficient, constant), retaining only exact relations."""
    if not isinstance(value, dict):
        return None
    op = value.get('op')
    if op == 'stack' and value.get('base') == 'entry_sp' and isinstance(value.get('offset'), int):
        return 1, value['offset']
    if op == 'const' and isinstance(value.get('value'), int):
        return 0, value['value']
    args = value.get('args', [])
    if op in ('add', 'sub') and len(args) == 2:
        left, right = _affine(args[0]), _affine(args[1])
        if left is not None and right is not None:
            sign = -1 if op == 'sub' else 1
            return left[0] + sign * right[0], left[1] + sign * right[1]
    return None


def _offset(value):
    relation = _affine(value)
    return relation[1] if relation is not None and relation[0] == 1 else None


def _architecture(snapshot, semantics):
    first = next(iter(semantics.values()), {})
    context = str(snapshot.get('context') or next((n.get('context') for n in snapshot.get('nodes', []) if n.get('context')), ''))
    parts = context.split(':')
    arch = snapshot.get('arch') or first.get('arch') or (parts[0] if parts else None)
    bits = snapshot.get('bits') or first.get('bits') or (int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None)
    sp = first.get('stack_pointer')
    if bits is None:
        bits = {'rsp': 64, 'esp': 32, 'sp': 16 if arch == 'x86' else 64}.get(sp)
    if arch in ('aarch64', 'arm64'):
        arch = 'arm64'
    return arch, bits


def _select_abi(snapshot, semantics, abi):
    arch, bits = _architecture(snapshot, semantics)
    if isinstance(abi, str):
        name = _ALIASES.get(abi.lower().replace('-', '_'), abi.lower().replace('-', '_'))
        if name not in ABI_PROFILES:
            raise ValueError(f'unknown ABI profile: {abi}')
        profile = deepcopy(ABI_PROFILES[name])
        alternatives, selection = [], 'explicit'
    elif isinstance(abi, dict):
        name = abi.get('name', 'custom')
        canonical = _ALIASES.get(name, name)
        profile = deepcopy(ABI_PROFILES.get(canonical, {}))
        profile.update(deepcopy(abi))
        alternatives, selection = [], 'explicit'
    elif abi is None:
        alternatives = [name for name, item in ABI_PROFILES.items() if item['arch'] == arch and item['bits'] == bits]
        first = next(iter(semantics.values()), {})
        profile = dict(name='unspecified', arch=arch, bits=bits,
                       stack_pointer=first.get('stack_pointer') or ('rsp' if bits == 64 and arch == 'x86' else 'esp' if bits == 32 else 'sp'),
                       frame_pointer=first.get('frame_pointer') or ('x29' if arch == 'arm64' else 'rbp' if arch == 'x86' and bits == 64 else 'ebp' if arch == 'x86' and bits == 32 else 'bp' if arch == 'x86' else 'fp'),
                       word_size=bits // 8 if bits else None, argument_registers=[],
                       return_registers=['x0', 'x1'] if arch == 'arm64' else ['rax', 'rdx'] if arch == 'x86' and bits == 64 else ['eax', 'edx'] if arch == 'x86' and bits == 32 else ['ax', 'dx'] if arch == 'x86' else [],
                       return_address_size=None, stack_argument_offset=None,
                       outgoing_stack_argument_offset=None, shadow_space=None, callee_cleanup=None)
        selection = 'unspecified'
    else:
        raise ValueError('abi must be a profile name, profile object, or None')
    for key in ('argument_registers', 'return_registers'):
        if not isinstance(profile.get(key), list) or len(profile[key]) > 64 or any(not isinstance(reg, str) for reg in profile[key]):
            raise ValueError(f'ABI {key} must be a list of at most 64 register names')
    for key in ('word_size', 'return_address_size', 'stack_argument_offset', 'outgoing_stack_argument_offset', 'shadow_space', 'callee_cleanup'):
        value = profile.get(key)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 65536):
            raise ValueError(f'ABI {key} must be a nonnegative integer or None')
    if not isinstance(profile.get('stack_pointer'), str) or not isinstance(profile.get('frame_pointer'), str):
        raise ValueError('ABI requires stack_pointer and frame_pointer register names')
    if profile.get('word_size') == 0:
        raise ValueError('ABI word_size must be positive')
    if selection == 'explicit' and ((arch and profile.get('arch') and arch != profile['arch'])
                                    or (bits and profile.get('bits') and bits != profile['bits'])):
        raise ValueError('ABI architecture or bit width does not match the snapshot')
    return profile, alternatives, selection


def _slot_kind(offset, width, profile):
    if offset < 0:
        return 'local_or_saved_value_candidate'
    return_size, argument_offset = profile.get('return_address_size'), profile.get('stack_argument_offset')
    if return_size is None or argument_offset is None:
        return 'unclassified_stack'
    if offset < return_size:
        return 'return_address_candidate' if offset + width <= return_size else 'overlapping_return_address'
    if offset < argument_offset:
        return 'register_home_space_candidate'
    return 'incoming_argument_candidate'


def _arguments(profile, state, evaluate):
    arguments = []
    for index, register in enumerate(profile['argument_registers']):
        value = evaluate(dict(op='reg', name=register), state)
        arguments.append(dict(index=index, location=dict(kind='register', register=register),
                              value=value, known=_known(value), candidate=True))
    sp = evaluate(dict(op='reg', name=profile['stack_pointer']), state)
    origin, start, word = _offset(sp), profile.get('outgoing_stack_argument_offset'), profile.get('word_size')
    if origin is not None and start is not None and word:
        cells = []
        for key, value in state.get('memory', {}).items():
            match = _STACK_KEY.fullmatch(str(key))
            if not match:
                continue
            offset, width = map(int, match.groups())
            relative = offset - origin
            if start <= relative < start + 256 and width > 0:
                cells.append((relative, width, offset, value))
        for relative, width, offset, value in sorted(cells, key=lambda cell: (cell[0], -cell[1]))[:64]:
            index = len(profile['argument_registers']) + (relative - start) // word if (relative - start) % word == 0 else None
            value = evaluate(_expr(value), state)
            arguments.append(dict(index=index, location=dict(kind='stack', offset=relative, entry_sp_offset=offset, width=width),
                                  value=value, known=_known(value), candidate=True))
    indexed = defaultdict(list)
    for argument in arguments:
        if argument['index'] is not None:
            indexed[argument['index']].append(argument['value'])
    values = []
    for index in range(max(indexed, default=-1) + 1):
        candidates = indexed.get(index, [])
        values.append(candidates[0] if candidates and all(value == candidates[0] for value in candidates)
                      else _unknown('no unique value at candidate argument location'))
    return dict(abi=profile['name'], arguments=arguments, argument_values=values,
                stack_pointer=sp, stack_pointer_known=origin is not None, shadow_space=profile.get('shadow_space'),
                signature_known=False, candidate=True,
                note='ABI candidate locations and observed stack cells; neither an argument count nor a source signature is established.')


def analyze_frame(snapshot: dict, semantics_by_id: dict, flow_result: dict, abi=None) -> dict:
    """Describe stack accesses, calls and returns using solved pre/post states.

    ``semantics_by_id`` is generic instruction IR; ``flow_result`` supplies
    ``in_states`` and ``out_states`` keyed by exact context-aware instruction ID.
    No instructions are decoded, followed, or executed by this function.
    """
    from .flowdata import evaluate_expression

    if not isinstance(snapshot, dict) or not isinstance(semantics_by_id, dict) or not isinstance(flow_result, dict):
        raise ValueError('frame inputs must be snapshot, semantics and flow-result objects')
    nodes = snapshot.get('nodes', [])
    if not isinstance(nodes, list) or len(nodes) > _MAX_NODES or any(not isinstance(node, dict) for node in nodes):
        raise ValueError(f'frame snapshot requires at most {_MAX_NODES} instruction objects')
    profile, alternatives, selection = _select_abi(snapshot, semantics_by_id, abi)
    in_states, out_states = flow_result.get('in_states', {}), flow_result.get('out_states', {})
    if not isinstance(in_states, dict) or not isinstance(out_states, dict):
        raise ValueError('flow in_states and out_states must be objects keyed by instruction ID')
    def evaluate(value, state):
        result = evaluate_expression(_expr(value), state)
        return _expr(result)

    slots, relations, stack_states, calls, returns, unresolved = {}, defaultdict(list), [], [], [], []
    covered = 0
    for node in nodes:
        identity = node.get('id')
        semantic, state = semantics_by_id.get(identity), in_states.get(identity)
        location = dict(instruction=identity, address=node.get('address'), context=node.get('context'))
        if not isinstance(semantic, dict):
            unresolved.append(dict(location, kind='semantics', reason='no_semantics_for_instruction'))
            continue
        if not isinstance(state, dict):
            unresolved.append(dict(location, kind='state', reason='no_reachable_or_analyzed_input_state'))
            continue
        covered += 1
        after = out_states.get(identity, {})
        sp = semantic.get('stack_pointer') or profile['stack_pointer']
        fp = semantic.get('frame_pointer') or profile['frame_pointer']
        before_sp = evaluate(dict(op='reg', name=sp), state)
        after_sp = evaluate(dict(op='reg', name=sp), after) if after else _unknown('post-state unavailable')
        stack_states.append(dict(location, register=sp, before=before_sp, after=after_sp,
                                 before_offset=_offset(before_sp), after_offset=_offset(after_sp)))
        for phase, current in (('before', state), ('after', after)):
            if current:
                offset = _offset(evaluate(dict(op='reg', name=fp), current))
                if offset is not None:
                    relations[(fp, offset, phase)].append(identity)
        if _offset(before_sp) is None:
            unresolved.append(dict(location, kind='stack_pointer', reason='entry_sp_relation_unknown'))
        for memory in semantic.get('memory', []):
            if not isinstance(memory, dict):
                continue
            segment = memory.get('segment_register')
            # DOS frame offsets must exclude SS*16 and the address-size mask.
            segmented = semantic.get('bits') == 16
            expression = memory.get('stack_address')
            if expression is None:
                expression = memory.get('unwrapped_offset', memory.get('offset', memory.get('address'))) if segmented and segment else memory.get('address')
            address = evaluate(expression, state)
            offset = _offset(address)
            if offset is None:
                continue
            if segmented and segment and segment != 'ss':
                segment_value = evaluate(dict(op='reg', name=segment), state)
                ss_value = evaluate(dict(op='reg', name='ss'), state)
                if not (_known(segment_value) and _known(ss_value) and segment_value == ss_value):
                    unresolved.append(dict(location, kind='segmented_stack_alias', segment_register=segment,
                                           reason='non_ss_segment_not_proven_equal_to_ss'))
                    continue
            width = memory.get('width')
            if not isinstance(width, int) or isinstance(width, bool) or not 0 < width <= 4096:
                unresolved.append(dict(location, kind='stack_access', reason='unknown_or_unsupported_access_width'))
                continue
            key = offset, width
            if key not in slots:
                slots[key] = dict(offset=offset, width=width, classification=_slot_kind(offset, width, profile), accesses=[])
            access = dict(location, access=memory.get('access', 'unknown'), width=width, offset=offset,
                          segment_register=segment, address_expression=address)
            if 'operand_index' in memory:
                access['operand_index'] = memory['operand_index']
            if memory.get('value') is not None:
                access['value'] = evaluate(memory['value'], state)
            elif memory.get('access') in ('read', 'read_write'):
                load = dict(op='load', address=memory.get('address'), width=width)
                if memory.get('stack_address') is not None:
                    load['stack_address'] = memory['stack_address']
                access['value'] = evaluate(load, state)
            slots[key]['accesses'].append(access)
        flow = semantic.get('flow', node.get('flow'))
        if flow in ('call', 'indirect_call'):
            call = dict(location, **_arguments(profile, state, evaluate))
            if alternatives:
                call['alternatives'] = [_arguments(ABI_PROFILES[name], state, evaluate) for name in alternatives]
            calls.append(call)
        if flow == 'return':
            values = [dict(register=register, value=evaluate(dict(op='reg', name=register), state))
                      for register in profile['return_registers']]
            for value in values:
                value['known'] = _known(value['value'])
            cleanup = semantic.get('return_pop')
            returns.append(dict(location, values=values, callee_cleanup=cleanup,
                                return_kind=semantic.get('return_kind', 'unknown'),
                                return_address_size=semantic.get('return_address_size'),
                                entry_sp_offset_before_return=_offset(before_sp), stack_delta=semantic.get('stack_delta')))
    observed_cleanup = sorted({item['callee_cleanup'] for item in returns if isinstance(item['callee_cleanup'], int)})
    budget_exhausted = bool(snapshot.get('budget_exhausted') or flow_result.get('budget_exhausted'))
    assumptions = ['Frame slots are logical offsets from entry SP, not concrete runtime addresses or recovered source variables.',
                   'Calls use pre-call states and ABI candidate locations; argument counts and signatures remain unknown.',
                   'Only integer register conventions and observed stack accesses are described; floating-point, vector and variadic classification is not inferred.',
                   '16-bit stack offsets are unwrapped symbolic relations; segment identity, offset wrapping and concrete memory validity require separate checks.']
    if selection == 'explicit':
        assumptions.append(f'ABI profile {profile["name"]} was selected explicitly; compatibility is an assumption rather than a proven convention.')
    else:
        assumptions.append('No ABI was selected. Calling-convention alternatives are retained; ABI-specific stack roles are unclassified.')
    return dict(status='candidate', function_boundary_proven=False, entry=snapshot.get('entry'),
                abi=dict(profile=profile, selection=selection, alternatives=alternatives),
                offset_origin='entry_sp', width_unit='bytes',
                stack_slots=[slots[key] for key in sorted(slots)],
                frame_pointer_relations=[dict(register=key[0], entry_sp_offset=key[1], phase=key[2], instructions=value)
                                         for key, value in sorted(relations.items())],
                stack_states=stack_states, calls=calls, returns=returns,
                callee_cleanup=dict(observed_bytes=observed_cleanup, consistent=len(observed_cleanup) <= 1,
                                    expected_bytes=profile.get('callee_cleanup'),
                                    matches_selected_abi=all(value == profile['callee_cleanup'] for value in observed_cleanup)
                                    if profile.get('callee_cleanup') is not None and observed_cleanup else None,
                                    note='RET immediate observations do not prove a calling convention.'),
                unresolved=unresolved, unresolved_count=len(unresolved),
                flow_unresolved=deepcopy(flow_result.get('unresolved', [])),
                flow_unresolved_count=len(flow_result.get('unresolved', [])),
                coverage=dict(instruction_count=len(nodes), analyzed_state_count=covered),
                budget_exhausted=budget_exhausted, complete=not budget_exhausted and covered == len(nodes),
                complete_scope='Input-state and semantic coverage of the supplied nodes, not CFG closure or runtime completeness.',
                frontier=deepcopy(flow_result.get('frontier', snapshot.get('frontier', []))), assumptions=assumptions)
