"""Optional, bounded Ghidra instruction-fact renderer for 16-bit blocks."""
from __future__ import annotations

import base64
import binascii
import hashlib
import os
from pathlib import Path
import subprocess
import struct
import tempfile

from .udl_blocks import lift_asm_block, lift_c_block


def render_ghidra_asm_c(lift, *, analyze_headless, java_home=None, timeout_s=60):
    """Render a validated ASM block using independently decoded Ghidra facts.

    Only straight-line 16-bit register/immediate MOV, ADD, SUB, INC and DEC
    are accepted. Flags are excluded from the modeled interface; no claim is
    made about behavior outside the restricted block. Native decompiler C is
    returned separately and is not the source of the normalized statements.
    """
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
        headless_path = os.fspath(analyze_headless)
    except TypeError as exc:
        raise ValueError('analyze_headless path is required') from exc
    if not headless_path:
        raise ValueError('analyze_headless path is required')
    if not isinstance(timeout_s, (int, float)) or isinstance(timeout_s, bool) or not 0 < timeout_s <= 3600:
        raise ValueError('invalid timeout')
    script_source = Path(__file__).parent / 'data' / 'FdisbullGhidraAsmC.txt'
    with tempfile.TemporaryDirectory(prefix='fdisbull-ghidra-') as tmp:
        root = Path(tmp)
        source = root / 'block.exe'
        # DOS MZ header and RET are import scaffolding, not source bytes.
        size = 32 + len(code) + 1
        header = struct.pack('<14H', 0x5a4d, size % 512, (size + 511) // 512,
                             0, 2, 0, 0xffff, 0, 0xfffe, 0, 0, 0, 0x1c, 0) + bytes(4)
        source.write_bytes(header + code + b'\xc3')
        script = root / 'FdisbullGhidraAsmC.java'
        script.write_bytes(script_source.read_bytes())
        facts = root / 'facts.txt'
        env = os.environ.copy()
        if java_home is not None:
            env['JAVA_HOME'] = os.fspath(java_home)
        cmd = [headless_path, str(root), 'project', '-import', str(source),
               '-noanalysis', '-scriptPath', str(root), '-postScript', script.name,
               str(facts), str(len(code))]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, env=env, check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError('Ghidra headless timed out') from exc
        except OSError as exc:
            raise RuntimeError('Ghidra headless could not start') from exc
        if proc.returncode or not facts.is_file():
            raise RuntimeError('Ghidra headless failed or produced no facts: ' + (proc.stderr + proc.stdout)[-4000:])
        lines = facts.read_text(encoding='utf-8').splitlines()
    if lines and lines[-1].startswith('ERROR\t'):
        try:
            error = base64.b64decode(lines[-1].split('\t', 1)[1], validate=True).decode('utf-8')
        except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
            raise RuntimeError('Ghidra decompilation failed: malformed error record') from exc
        raise RuntimeError('Ghidra decompilation failed: ' + (error or 'unknown error'))
    if not lines or not lines[0].startswith('VERSION\t') or lines[-1] != f'COMPLETE\t{len(code)}':
        raise RuntimeError('Ghidra facts are incomplete: ' + (proc.stderr + proc.stdout)[-4000:])
    version = lines[0].split('\t', 1)[1]
    if not version:
        raise RuntimeError('Ghidra version missing')
    try:
        if len(lines) < 4 or not lines[-3].startswith('DECOMPILED\t') or not lines[-2].startswith('WARNINGS\t'):
            raise ValueError('decompiler output missing')
        ghidra_c = base64.b64decode(lines[-3].split('\t', 1)[1], validate=True).decode('utf-8')
        warnings = base64.b64decode(lines[-2].split('\t', 1)[1], validate=True).decode('utf-8')
        if not ghidra_c.strip():
            raise ValueError('empty decompiler output')
    except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
        raise RuntimeError('Ghidra decompiler output is invalid or incomplete') from exc
    statements, evidence, offset = [], [], 0
    symbols = {'MOV': '=', 'ADD': '+=', 'SUB': '-=', 'INC': '+=', 'DEC': '-='}
    regs = {'ax', 'cx', 'dx', 'bx', 'sp', 'bp', 'si', 'di'}
    try:
        for line in lines[1:-3]:
            tag, pos, size, mnemonic, register, bits, value, count = line.split('\t')
            pos, size, bits, value, count = map(int, (pos, size, bits, value, count))
            reg = register.lower()
            op = mnemonic.upper()
            if (tag != 'INS' or pos != offset or size < 1 or pos + size > len(code)
                    or reg not in regs or bits != 16 or op not in symbols
                    or count != (1 if op in ('INC', 'DEC') else 2)
                    or not 0 <= value <= 65535):
                raise ValueError('unsupported Ghidra instruction facts')
            statements.append(f'{reg} {symbols[op]} {value};')
            evidence.append({'offset': pos, 'size': size, 'mnemonic': op,
                             'register': reg, 'immediate': value})
            offset += size
    except (ValueError, TypeError) as exc:
        raise ValueError('unsupported or malformed Ghidra instruction facts') from exc
    if offset != len(code):
        raise ValueError('Ghidra did not cover all source bytes')
    text = '\n'.join(statements)
    lift_c_block(text, rebuilt['bindings'], inputs=rebuilt['inputs'], outputs=rebuilt['outputs'],
                 flags=rebuilt['flags'], pointer_assumptions=rebuilt['pointer_assumptions'])
    return {'format': 'fdisbull-ghidra-asm-c-1', 'text': text,
            'source_sha256': hashlib.sha256(code).hexdigest(), 'ghidra_version': version,
            'evidence': evidence, 'ghidra_c': ghidra_c,
            'diagnostics': {'covered_bytes': offset, 'decompile_completed': True,
                'decompiler_warnings': warnings, 'synthetic_wrapper': {'offset': len(code), 'bytes': 'c3',
                'header_format': 'DOS MZ', 'header_bytes': header.hex(), 'header_size': len(header),
                'purpose': 'MZ import header and RET function terminator; excluded from source digest and coverage'},
                'text_provenance': 'Ghidra decoded instruction facts; not parsed from decompiled C',
                'scope': '16-bit register outputs only; flags, memory, control flow, ABI and timing excluded'}}
