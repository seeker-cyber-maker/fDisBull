"""Check one completed PE trace step against the bounded x86 UIL adapter.

This is a sampled model check, not a general PE lifter or a proof that the
adapter matches all x86 execution. Memory, aliases and host effects are outside
the admitted full-width register instruction profile.
"""
from __future__ import annotations

from .common_uil import default_value, digest, required_capabilities
from .debug_semantics import PE_TRACE_SEMANTICS
from .uil_catalog import from_asm_instruction, function_semantic_id
from .uil_runtime import execute_program
from .wine_arch import context_bits, flags_name, ip_name, register_names, validate_context


FLAG_BITS = {'cf': 0, 'pf': 2, 'af': 4, 'zf': 6, 'sf': 7, 'of': 11}
SCOPE = ('One completed selected-thread PE instruction, full-width general register ports '
         'and CF/PF/AF/ZF/SF/OF at the next trace pre-state; memory, other flags, '
         'aliases, traps, ABI, other threads and external effects unobserved')


def _unknown(reason, status='unknown'):
    return {'status': status, 'reason': reason, 'scope': SCOPE}


def check_pe_step_model(trace, index):
    """Compare an admitted x86 instruction model with adjacent PE trace states.

    The next event's pre-instruction registers are the first event's post-state.
    Only a trace captured with completed-step semantics and one selected thread
    can establish this relationship. Returned agreement is for these outputs
    and this one observation, not for unselected machine state.
    """
    if type(index) is not int or index < 0:
        raise ValueError('trace index must be a nonnegative integer')
    if not isinstance(trace, dict) or not isinstance(trace.get('events'), list):
        raise ValueError('trace requires events')
    events = trace['events']
    if index >= len(events):
        raise ValueError('trace index is outside captured events')
    if trace.get('semantics') not in ('completed_steps', PE_TRACE_SEMANTICS):
        return _unknown('Trace does not certify completed PE steps')
    if index + 1 >= len(events):
        return _unknown('No following pre-instruction state was captured')
    before, after = events[index:index + 2]
    if not isinstance(before, dict) or not isinstance(after, dict):
        return _unknown('Trace event is malformed')
    first, second = before.get('identity'), after.get('identity')
    if (not isinstance(first, dict) or not isinstance(second, dict)
            or first.get('context') != 'flat' or second.get('context') != 'flat'
            or first.get('source_version') is None
            or first.get('source_version') != second.get('source_version')
            or not isinstance(first.get('project_address'), str)
            or not isinstance(second.get('project_address'), str)
            or first['project_address'] != before.get('project_address')
            or second.get('project_address') != after.get('project_address')
            or first.get('runtime_address') != before.get('address')
            or second.get('runtime_address') != after.get('address')):
        return _unknown('PE source and flat-site identity are not established')
    first_observation, next_observation = before.get('observation'), after.get('observation')
    if (not isinstance(first_observation, dict) or not isinstance(next_observation, dict)
            or first_observation.get('instruction_completed') is not True
            or first_observation.get('registers_stage') != 'before-instruction'
            or next_observation.get('registers_stage') != 'before-instruction'):
        return _unknown('Completed step and next pre-instruction state are not established')
    left, right = before.get('registers'), after.get('registers')
    if not isinstance(left, dict) or not isinstance(right, dict):
        return _unknown('Register snapshots are missing')
    try:
        bits = context_bits(left)
        validate_context(left, bits)
        validate_context(right, bits)
        if left.get('thread') is None or left['thread'] != right.get('thread'):
            return _unknown('The selected thread is not the same in both samples')
        if int(left[ip_name(left)], 16) != int(before['address'], 16):
            return _unknown('Pre-instruction PC does not match the recorded site')
        code = bytes.fromhex(before.get('execution_bytes', before['bytes']))
    except (KeyError, TypeError, ValueError):
        return _unknown('PE register, PC or executed-byte evidence is malformed')
    try:
        model = from_asm_instruction(code, bits=bits, flags='explicit')
    except ValueError:
        return _unknown('Instruction is outside the bounded register model', 'unsupported')
    try:
        expected_next = (int(before['address'], 16) + len(code)) % (1 << bits)
        if (int(after['address'], 16) != expected_next
                or int(right[ip_name(right)], 16) != expected_next):
            return _unknown('The next trace site is not this straight-line instruction successor')
    except (KeyError, TypeError, ValueError):
        return _unknown('The next PE instruction pointer is malformed')
    ports = model['source']
    general = register_names(bits) - {ip_name(left), flags_name(left)}
    if any(name not in general and name not in FLAG_BITS
           for name in ports['inputs'] + ports['outputs']):
        return _unknown('Instruction uses a partial or aliased register view', 'unsupported')
    def value(context, name):
        return (bool(int(context[flags_name(context)], 16) & (1 << FLAG_BITS[name]))
                if name in FLAG_BITS else int(context['general'][name], 16))

    program = {'format': 'fdisbull-common-uil-1', 'imports': [],
               'functions': [model['function']], 'entry': 0, 'capabilities': []}
    program['capabilities'] = sorted(required_capabilities(program))
    function = model['function']
    initial = [str(default_value(item)) if item['type'].startswith(('u', 'i'))
               else default_value(item) for item in function['variables']]
    presentation = {'format': 'fdisbull-uil-presentation-1',
                    'program_sha256': digest(program), 'resources': [],
                    'functions': [{'initial': initial, 'constants': model['constants']}]}
    try:
        predicted = execute_program(program, presentation,
                                    inputs=[value(left, name) for name in ports['inputs']])['outputs']
        observed = [value(right, name) for name in ports['outputs']]
    except ValueError:
        return _unknown('Model input or execution cannot be compared')
    mismatches = [name for name, expected, actual in zip(ports['outputs'], predicted, observed, strict=True)
                  if expected != actual]
    return {'status': 'mismatch' if mismatches else 'agreement',
            'source_version': first['source_version'],
            'project_address': first['project_address'],
            'instruction_sha256': ports['sha256'],
            'semantic_id': function_semantic_id(function, model['constants']),
            'observed_outputs': ports['outputs'], 'mismatched_outputs': mismatches,
            'scope': SCOPE}
