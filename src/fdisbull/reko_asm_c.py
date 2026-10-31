"""Optional Reko instruction-fact renderer for bounded 16-bit blocks."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile

from .udl_blocks import lift_asm_block, lift_c_block

_LINE = re.compile(r'^0C00:([0-9A-Fa-f]{4})\s+((?:[0-9A-Fa-f]{2}\s+)+)\s*([A-Za-z]+)\s*(.*?)\s*$', re.I)
_REGS = {'ax', 'cx', 'dx', 'bx', 'sp', 'bp', 'si', 'di'}


def render_reko_asm_c(lift, *, executable, dotnet=None, timeout_s=60):
    """Render Reko's decoded facts; its inferred C is diagnostic only."""
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
    try:
        exe = os.fspath(executable)
        runtime = os.fspath(dotnet) if dotnet is not None else None
    except TypeError as exc:
        raise ValueError('executable path is required') from exc
    if not exe or (dotnet is not None and not runtime):
        raise ValueError('executable path is required')
    exe_path = Path(exe)
    if not exe_path.is_absolute() and (exe_path.exists() or any(
            sep in exe for sep in (os.sep, os.altsep) if sep)):
        exe = str(exe_path.resolve())
    if runtime:
        runtime_path = Path(runtime)
        if not runtime_path.is_absolute() and (runtime_path.exists() or any(
                sep in runtime for sep in (os.sep, os.altsep) if sep)):
            runtime = str(runtime_path.resolve())
    if not isinstance(timeout_s, (int, float)) or isinstance(timeout_s, bool) or not 0 < timeout_s <= 3600:
        raise ValueError('invalid timeout')
    with tempfile.TemporaryDirectory(prefix='fdisbull-reko-') as tmp:
        root = Path(tmp)
        source = root / 'block.com'
        source.write_bytes(code + b'\xc3')
        command = ([runtime, exe] if runtime else [exe]) + [
            'decompile', '--arch', 'x86-real-16', '--env', 'ms-dos',
            '--base', '0C00:0100', '--dasm-address', '--dasm-bytes', str(source)]
        try:
            proc = subprocess.run(command, cwd=root, capture_output=True, text=True,
                                  timeout=timeout_s, check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('Reko timed out') from exc
        except OSError as exc:
            raise RuntimeError('Reko could not start') from exc
        asm_path = root / 'block.reko' / 'block_code.asm'
        c_path = root / 'block.reko' / 'block_code.c'
        if proc.returncode or not asm_path.is_file() or not c_path.is_file():
            raise RuntimeError('Reko failed or produced incomplete output: ' + (proc.stderr + proc.stdout)[-4000:])
        try:
            lines = asm_path.read_text(encoding='utf-8').splitlines()
            native_c = c_path.read_text(encoding='utf-8')
        except (UnicodeError, OSError) as exc:
            raise RuntimeError('Reko output is unreadable') from exc
    if not native_c.strip():
        raise RuntimeError('Reko produced empty C output')
    statements, evidence, offset, saw_ret = [], [], 0, False
    symbols = {'mov': '=', 'add': '+=', 'sub': '-=', 'inc': '+=', 'dec': '-='}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(';;') or re.fullmatch(r'\w+\s+proc', stripped):
            continue
        match = _LINE.fullmatch(stripped)
        if not match:
            raise ValueError('unsupported or malformed Reko assembly facts')
        addr, raw, op, args = match.groups()
        raw = bytes.fromhex(raw)
        op = op.lower()
        if saw_ret or int(addr, 16) != 0x100 + offset or raw != (code + b'\xc3')[offset:offset + len(raw)]:
            raise ValueError('Reko assembly byte coverage mismatch')
        if offset == len(code):
            if op != 'ret' or args or raw != b'\xc3':
                raise ValueError('Reko terminator mismatch')
            saw_ret = True
            continue
        if offset + len(raw) > len(code) or op not in symbols:
            raise ValueError('unsupported Reko instruction facts')
        operands = [x.strip().lower() for x in args.split(',')]
        if operands[0] not in _REGS or len(operands) != (1 if op in ('inc', 'dec') else 2):
            raise ValueError('unsupported Reko operand facts')
        if len(operands) == 1:
            value = 1
        else:
            literal = operands[1]
            if not re.fullmatch(r'[0-9a-f]+h', literal):
                raise ValueError('unsupported Reko immediate')
            value = int(literal[:-1], 16)
            if value > 65535:
                raise ValueError('unsupported Reko immediate')
        statements.append(f'{operands[0]} {symbols[op]} {value};')
        evidence.append({'offset': offset, 'size': len(raw), 'mnemonic': op.upper(),
                         'register': operands[0], 'immediate': value})
        offset += len(raw)
    if offset != len(code) or not saw_ret:
        raise ValueError('Reko did not cover all source bytes and terminator')
    text = '\n'.join(statements)
    lift_c_block(text, rebuilt['bindings'], inputs=rebuilt['inputs'], outputs=rebuilt['outputs'],
                 flags=rebuilt['flags'], pointer_assumptions=rebuilt['pointer_assumptions'])
    return {'format': 'fdisbull-reko-asm-c-1', 'source_sha256': hashlib.sha256(code).hexdigest(),
            'text': text, 'native_c': native_c, 'evidence': evidence,
            'diagnostics': {'covered_bytes': offset, 'decompile_completed': True,
                'synthetic_wrapper': {'offset': len(code), 'bytes': 'c3', 'format': 'COM',
                                      'purpose': 'RET terminator excluded from source digest and coverage'},
                'text_provenance': 'Reko decoded assembly facts; not decompiled C',
                'scope': '16-bit register outputs only; flags, memory, control flow, ABI and timing excluded',
                'native_c_limitation': 'Diagnostic only; inferred return-only C may omit register effects'}}
