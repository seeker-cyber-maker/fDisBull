"""Small, explicit straight-line source-to-UIL experiments, not a decompiler.

The two source readers are deliberately independent of the UIL symbolic
interpreter. No memory, control flow, flags, host effects, or ABI are modeled.
"""
from __future__ import annotations

import hashlib
import re

import capstone
from capstone import x86_const

from .interaction_il import validate_il
from .proofs import arithmetic_model, check_equivalence

_REGS = ('ax', 'cx', 'dx', 'bx', 'sp', 'bp', 'si', 'di')


def _contract(bindings, inputs, outputs, flags, pointer_assumptions):
    if not isinstance(bindings, dict) or not bindings or len(bindings) > 8:
        raise ValueError('bindings must be a nonempty register-to-variable mapping')
    if any(r not in _REGS or not isinstance(v, str) or not re.fullmatch(r'\$[A-Za-z_][A-Za-z_0-9]*', v) for r, v in bindings.items()):
        raise ValueError('invalid register binding')
    if len(set(bindings.values())) != len(bindings):
        raise ValueError('register bindings must be distinct')
    if not isinstance(inputs, (list, tuple)) or not isinstance(outputs, (list, tuple)):
        raise ValueError('inputs and outputs must be lists of bound registers')
    if not outputs or len(set(inputs)) != len(inputs) or len(set(outputs)) != len(outputs) or not (set(inputs) | set(outputs)) <= set(bindings):
        raise ValueError('invalid inputs or outputs')
    if flags != 'unobserved' or pointer_assumptions not in (None, []):
        raise ValueError('flags and memory/pointers are not supported')


def _asm(code):
    if not isinstance(code, bytes) or not 1 <= len(code) <= 256:
        raise ValueError('source bytes must contain 1..256 bytes')
    out, i = [], 0
    while i < len(code):
        opcode = code[i]
        if 0xb8 <= opcode <= 0xbf or opcode in (0x05, 0x2d):
            if i + 3 > len(code):
                raise ValueError('truncated instruction')
            value = int.from_bytes(code[i+1:i+3], 'little')
            reg = _REGS[opcode - 0xb8] if opcode >= 0xb8 else 'ax'
            op = 'set' if opcode >= 0xb8 else ('add' if opcode == 0x05 else 'subtract')
            out.append((op, reg, value)); i += 3
        elif 0x40 <= opcode <= 0x4f:
            out.append(('add' if opcode < 0x48 else 'subtract', _REGS[opcode % 8], 1)); i += 1
        else:
            raise ValueError(f'unsupported instruction at byte {i}')
    # Compare the entire decoded stream and operand facts with the native decoder.
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
    decoder.detail = True
    decoded = list(decoder.disasm(code, 0))
    if sum(ins.size for ins in decoded) != len(code) or len(decoded) != len(out):
        raise ValueError('native decoder does not cover the block')
    for ins, (op, reg, value) in zip(decoded, out):
        expected = {'set':'mov', 'add':'add', 'subtract':'sub'}[op]
        if ins.mnemonic in ('inc', 'dec'):
            expected = 'inc' if op == 'add' else 'dec'
        operands = ins.operands
        if (ins.mnemonic != expected or len(operands) != (1 if expected in ('inc', 'dec') else 2)
                or operands[0].type != x86_const.X86_OP_REG or operands[0].size != 2
                or ins.reg_name(operands[0].reg) != reg):
            raise ValueError('native instruction facts disagree with source model')
        if len(operands) == 2 and (operands[1].type != x86_const.X86_OP_IMM
                                   or operands[1].size != 2 or operands[1].imm != value):
            raise ValueError('native immediate facts disagree with source model')
    return out


def _c(source):
    # A syntactically restricted sequence of statements, not a C parser.
    # Identifiers are registers bound to uint16_t variables by the caller.
    # An admitted ASM block can contain 256 one-byte operations. Its
    # normalized C spelling is longer than its byte stream.
    if not isinstance(source, str) or not 1 <= len(source.encode('utf-8')) <= 4096:
        raise ValueError('invalid C subset source')
    statements = source.split(';')
    if statements[-1].strip():
        raise ValueError('missing semicolon')
    result = []
    for item in statements[:-1]:
        match = re.fullmatch(r'\s*(ax|cx|dx|bx|sp|bp|si|di)\s*(=|\+=|-=)\s*(0[xX][0-9a-fA-F]+|0|[1-9][0-9]*)\s*', item)
        if not match:
            raise ValueError('unsupported C statement')
        reg, op, literal = match.groups()
        value = int(literal, 16 if literal.lower().startswith('0x') else 10)
        if value > 65535:
            raise ValueError('C constant outside uint16_t range')
        result.append(({'=':'set', '+=':'add', '-=':'subtract'}[op], reg, value))
    if not result or len(result) > 256:
        raise ValueError('invalid statement count')
    return result


def _lift(kind, source, bindings, inputs, outputs, flags, pointer_assumptions):
    _contract(bindings, inputs, outputs, flags, pointer_assumptions)
    instructions = _asm(source) if kind == 'asm16' else _c(source)
    initialized = set(inputs)
    body = []
    for i, (op, reg, value) in enumerate(instructions):
        if reg not in bindings or reg not in outputs or (op != 'set' and reg not in initialized):
            raise ValueError('unbound or uninitialized register')
        initialized.add(reg)
        body.append({'id': f'b{i}', 'op': op, 'var': bindings[reg], 'value': value})
    if not set(outputs) <= initialized:
        raise ValueError('output is uninitialized')
    raw = source if isinstance(source, bytes) else source.encode('utf-8')
    uil = {'format':'fdisbull-il-1', 'role':'uil',
           'variables':{name:{'type':'u16', 'initial':0} for name in bindings.values()},
           'resources':{}, 'body':body}
    validate_il(uil)
    return {'format':'fdisbull-block-lift-1', 'source_kind':kind,
            'source': source.hex() if kind == 'asm16' else source,
            'sha256':hashlib.sha256(raw).hexdigest(), 'bindings':dict(bindings),
            'inputs':list(inputs), 'outputs':list(outputs), 'flags':'unobserved',
            'pointer_assumptions':[], 'uil':uil,
            'scope':'16-bit register outputs at straight-line block exit; flags, memory, control flow, ABI, timing, intermediate state and external effects excluded',
            'assumptions':(['16-bit x86 real-mode instruction semantics'] if kind == 'asm16' else
                            ['bound variables are uint16_t; int has at least 32 bits; decimal constants are ordinary nonnegative integer constants'])}


def lift_asm_block(code, bindings, *, inputs, outputs, flags='unobserved', pointer_assumptions=None):
    return _lift('asm16', code, bindings, inputs, outputs, flags, pointer_assumptions)


def lift_c_block(source, bindings, *, inputs, outputs, flags='unobserved', pointer_assumptions=None):
    return _lift('c_u16_subset', source, bindings, inputs, outputs, flags, pointer_assumptions)


_ASM_C_ENGINES = ('builtin', 'ghidra', 'reko', 'dcc')


def asm_to_c(lift, *, engine='builtin', tool_path=None, runtime_path=None,
             analyze_headless=None, java_home=None, timeout_s=60,
             require_equivalence=False):
    """Render the same bounded ASM lift through one selected engine.

    ``tool_path`` is the external executable (Ghidra analyzeHeadless, Reko
    CLI or DCC). ``runtime_path`` is the Java home for Ghidra or dotnet for
    Reko. The earlier Ghidra-specific names remain accepted. Native decompiler
    C is diagnostic; only ``text`` is in the restricted UIL reader's grammar.
    ``require_equivalence`` fails closed unless Z3 proves the declared outputs.
    """
    if engine not in _ASM_C_ENGINES:
        raise ValueError('unknown ASM-to-C engine')
    if (type(timeout_s) not in (int, float) or not 0 < timeout_s <= 3600
            or type(require_equivalence) is not bool):
        raise ValueError('invalid ASM-to-C options')
    if not isinstance(lift, dict) or lift.get('source_kind') != 'asm16':
        raise ValueError('ASM lift required')
    try:
        code = bytes.fromhex(lift['source'])
        rebuilt = lift_asm_block(code, lift['bindings'], inputs=lift['inputs'],
                                 outputs=lift['outputs'], flags=lift['flags'],
                                 pointer_assumptions=lift['pointer_assumptions'])
    except (KeyError, TypeError) as exc:
        raise ValueError('invalid ASM lift') from exc
    if rebuilt['sha256'] != lift.get('sha256'):
        raise ValueError('source digest mismatch')
    if engine == 'builtin':
        symbols = {'set':'=', 'add':'+=', 'subtract':'-='}
        raw = {'format': 'fdisbull-asm-c-view-1', 'source_sha256': rebuilt['sha256'],
               'text': '\n'.join(f'{reg} {symbols[op]} {value};' for op, reg, value in _asm(code)),
               'evidence': [], 'diagnostics': {'covered_bytes': len(code),
                   'text_provenance': 'fDisBull bounded ASM decoder; shared with source lift'},
               'assumptions': [
                   'Derived from the same bounded ASM decoder, not an independent decompiler or native parity check',
                   'Identifiers represent uint16_t objects and int has at least 32 bits',
                   'Flags, memory, control flow, ABI, timing and intermediate state are excluded']}
    elif engine == 'ghidra':
        if tool_path is not None and analyze_headless is not None:
            raise ValueError('supply tool_path or analyze_headless, not both')
        if runtime_path is not None and java_home is not None:
            raise ValueError('supply runtime_path or java_home, not both')
        from .ghidra_asm_c import render_ghidra_asm_c
        raw = render_ghidra_asm_c(
            rebuilt, analyze_headless=tool_path if tool_path is not None else analyze_headless,
            java_home=runtime_path if runtime_path is not None else java_home,
            timeout_s=timeout_s)
    elif engine == 'reko':
        from .reko_asm_c import render_reko_asm_c
        raw = render_reko_asm_c(rebuilt, executable=tool_path,
                                dotnet=runtime_path, timeout_s=timeout_s)
    else:
        if runtime_path is not None:
            raise ValueError('DCC does not take a runtime_path')
        from .dcc_asm_c import render_dcc_asm_c
        raw = render_dcc_asm_c(rebuilt, executable=tool_path, timeout_s=timeout_s)
    if not isinstance(raw, dict) or raw.get('source_sha256') != rebuilt['sha256']:
        raise RuntimeError('ASM-to-C engine returned the wrong source identity')
    if (not isinstance(raw.get('evidence', []), list)
            or not isinstance(raw.get('diagnostics', {}), dict)):
        raise RuntimeError('ASM-to-C engine returned invalid evidence')
    text = raw.get('text')
    if not isinstance(text, str):
        raise RuntimeError('ASM-to-C engine returned no normalized text')
    # Every successful engine result has the same parseable bounded statement
    # contract. This validation does not prove that native decompiler C agrees.
    lift_c_block(text, rebuilt['bindings'], inputs=rebuilt['inputs'], outputs=rebuilt['outputs'],
                 flags=rebuilt['flags'], pointer_assumptions=rebuilt['pointer_assumptions'])
    diagnostic = dict(raw.get('diagnostics') or {})
    diagnostic.setdefault('covered_bytes', len(code))
    native_c = raw.get('native_c', raw.get('ghidra_c'))
    if native_c is not None and not isinstance(native_c, str):
        raise RuntimeError('ASM-to-C engine returned invalid native C')
    view = {**raw, 'format': 'fdisbull-asm-c-view-2', 'engine': engine,
            'engine_result_format': raw.get('format'), 'source_kind': 'asm16',
            'bindings': dict(rebuilt['bindings']), 'inputs': list(rebuilt['inputs']),
            'outputs': list(rebuilt['outputs']), 'text': text,
            'native_c': native_c,
            'native_c_status': 'diagnostic_unverified' if native_c is not None else 'not_applicable',
            'evidence': list(raw.get('evidence') or []),
            'diagnostics': diagnostic,
            'assumptions': list(raw.get('assumptions') or [
                'Normalized statements are derived from this engine\'s decoded instruction listing, not its native C',
                'Identifiers represent uint16_t objects and int has at least 32 bits',
                'Flags, memory, control flow, ABI, timing and intermediate state are excluded'])}
    if require_equivalence:
        proof = qualify_asm_c_view(rebuilt, view)
        if proof['status'] != 'equivalent_under_assumptions':
            raise RuntimeError('ASM-to-C engine output is not qualified: ' + proof['status'])
        view['qualification'] = proof
    return view


def qualify_asm_c_view(lift, view, *, timeout_ms=1000):
    """Check the normalized C view at the declared register boundary only."""
    if (not isinstance(view, dict) or view.get('format') != 'fdisbull-asm-c-view-2'
            or view.get('source_kind') != 'asm16'
            or view.get('engine') not in _ASM_C_ENGINES
            or view.get('source_sha256') != lift.get('sha256')
            or view.get('bindings') != lift.get('bindings')
            or view.get('inputs') != lift.get('inputs')
            or view.get('outputs') != lift.get('outputs')):
        raise ValueError('ASM-to-C view interface differs from source')
    candidate = lift_c_block(view['text'], lift['bindings'], inputs=lift['inputs'],
                             outputs=lift['outputs'], flags=lift['flags'],
                             pointer_assumptions=lift['pointer_assumptions'])
    return verify_block(lift, candidate['uil'], timeout_ms=timeout_ms)


def _check_expression_budget(expressions):
    """Bound expanded trees before JSON serialization, even for shared DAGs."""
    pending = [(expression, 0) for expression in expressions]
    count = 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if count > 1000 or depth > 30:
            raise ValueError('proof expression budget exceeded')
        if isinstance(node, dict) and 'args' in node:
            pending.extend((child, depth + 1) for child in node['args'])


def verify_block(lift, candidate_uil, *, timeout_ms=1000):
    """Compare source and candidate models for each declared output.

    Equivalence is only for the modeled interface and assumptions; it does not
    establish decoder fidelity, ABI correctness, flag preservation, or whole-program parity.
    """
    kind = lift.get('source_kind')
    if kind not in ('asm16', 'c_u16_subset'):
        raise ValueError('unknown source kind')
    try:
        source = bytes.fromhex(lift['source']) if kind == 'asm16' else lift['source']
        rebuilt = _lift(kind, source, lift['bindings'], lift['inputs'], lift['outputs'], lift['flags'], lift['pointer_assumptions'])
    except (KeyError, TypeError) as exc:
        raise ValueError('invalid lift') from exc
    if rebuilt['sha256'] != lift.get('sha256'):
        raise ValueError('source digest mismatch')
    validate_il(candidate_uil)
    if candidate_uil['role'] != 'uil' or candidate_uil['resources'] or set(candidate_uil['variables']) != set(rebuilt['uil']['variables']) or candidate_uil['variables'] != rebuilt['uil']['variables']:
        raise ValueError('candidate interface differs')
    bindings = rebuilt['bindings']
    variables = {r:16 for r in rebuilt['inputs']}
    initial = {bindings[r]:{'var':r} for r in rebuilt['inputs']}
    src = dict(initial)
    for op, reg, value in (_asm(source) if kind == 'asm16' else _c(source)):
        name = bindings[reg]; const = {'const':value, 'width':16}
        src[name] = const if op == 'set' else {'op': 'add' if op == 'add' else 'sub', 'args':[src[name],const]}
    dst = dict(initial)
    for block in candidate_uil['body']:
        op, name = block['op'], block.get('var')
        if op not in ('set','add','subtract') or name not in {bindings[r] for r in rebuilt['outputs']}:
            raise ValueError('candidate uses unsupported effects or control flow')
        v = block['value']
        if isinstance(v, dict):
            if v['var'] not in dst: raise ValueError('candidate reads uninitialized variable')
            value = dst[v['var']]
        else:
            if type(v) is not int or not 0 <= v <= 65535: raise ValueError('invalid candidate value')
            value = {'const':v, 'width':16}
        if op != 'set' and name not in dst: raise ValueError('candidate reads uninitialized variable')
        dst[name] = value if op == 'set' else {'op':'add' if op == 'add' else 'sub', 'args':[dst[name],value]}
    results = {}
    for reg in rebuilt['outputs']:
        name = bindings[reg]
        if name not in dst: raise ValueError('candidate output uninitialized')
        _check_expression_budget((src[name], dst[name]))
        spec = arithmetic_model(variables, src[name], dst[name], scope=rebuilt['scope'])
        results[reg] = {**check_equivalence(spec, timeout_ms=timeout_ms), 'spec':spec}
    statuses = [v['status'] for v in results.values()]
    status = 'counterexample' if 'counterexample' in statuses else ('equivalent_under_assumptions' if all(s == 'equivalent_under_assumptions' for s in statuses) else ('unavailable' if 'unavailable' in statuses else 'unknown'))
    return {'format':'fdisbull-block-verification-1', 'status':status, 'source_sha256':rebuilt['sha256'],
            'assumptions':rebuilt['assumptions'], 'scope':rebuilt['scope'], 'outputs':results}
