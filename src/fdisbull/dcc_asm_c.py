"""Bounded DCC listing adapter; native decompilation is retained as evidence."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile

from .udl_blocks import lift_asm_block, lift_c_block


_ROW = re.compile(r'^\s*\d+\s+([0-9A-Fa-f]{6})\s+([0-9A-Fa-f]+)\s+([A-Za-z]+)\s*(.*?)\s*$')
_REGS = frozenset(('ax', 'cx', 'dx', 'bx', 'sp', 'bp', 'si', 'di'))


def _number(value):
    if re.fullmatch(r'[0-9]+', value):
        return int(value, 10)
    if re.fullmatch(r'[0-9A-Fa-f]+[hH]', value):
        return int(value[:-1], 16)
    raise ValueError('unsupported DCC immediate')


def _listing_facts(listing, code):
    rows = []
    for line in listing.splitlines():
        match = _ROW.fullmatch(line)
        if match:
            address, encoded, mnemonic, operands = match.groups()
            try:
                raw = bytes.fromhex(encoded)
            except ValueError as exc:
                raise ValueError('malformed DCC instruction bytes') from exc
            rows.append((int(address, 16), raw, mnemonic.upper(), operands.strip()))
        elif re.match(r'^\s*\d+\s+[0-9A-Fa-f]{6}\b', line):
            raise ValueError('malformed DCC listing row')
    offset, facts, statements = 0, [], []
    for address, raw, mnemonic, operands in rows:
        if address != 0x100 + offset or not raw:
            raise ValueError('DCC listing is discontinuous')
        if offset == len(code):
            if raw != b'\xc3' or mnemonic != 'RET' or operands:
                raise ValueError('DCC wrapper terminator missing')
            offset += 1
            continue
        if offset > len(code) or offset + len(raw) > len(code) or raw != code[offset:offset + len(raw)]:
            raise ValueError('DCC listing bytes do not match source')
        parts = [part.strip().lower() for part in operands.split(',')]
        if mnemonic not in ('MOV', 'ADD', 'SUB', 'INC', 'DEC') or parts[0] not in _REGS:
            raise ValueError('unsupported DCC instruction facts')
        if mnemonic in ('INC', 'DEC'):
            if len(parts) != 1:
                raise ValueError('unsupported DCC instruction operands')
            value = 1
        else:
            if len(parts) != 2:
                raise ValueError('unsupported DCC instruction operands')
            value = _number(parts[1])
            if not 0 <= value <= 65535:
                raise ValueError('DCC immediate outside uint16 range')
        reg = parts[0]
        symbol = {'MOV': '=', 'ADD': '+=', 'SUB': '-=', 'INC': '+=', 'DEC': '-='}[mnemonic]
        statements.append(f'{reg} {symbol} {value};')
        facts.append({'offset': offset, 'size': len(raw), 'mnemonic': mnemonic,
                      'register': reg, 'immediate': value})
        offset += len(raw)
    if offset != len(code) + 1:
        raise ValueError('DCC listing did not cover source and wrapper')
    return statements, facts


def render_dcc_asm_c(lift, *, executable, timeout_s=60):
    """Render the supported register-only block from DCC's assembly listing.

    The normalized statements repair native C omissions only in this restricted
    model. They do not model DOS interrupts or other external effects.
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
        executable = os.fspath(executable)
    except TypeError as exc:
        raise ValueError('DCC executable path is required') from exc
    if not executable:
        raise ValueError('DCC executable path is required')
    path = Path(executable)
    if not path.is_absolute() and (path.exists() or any(
            sep in executable for sep in (os.sep, os.altsep) if sep)):
        executable = str(path.resolve())
    if not isinstance(timeout_s, (int, float)) or isinstance(timeout_s, bool) or not 0 < timeout_s <= 3600:
        raise ValueError('invalid timeout')
    with tempfile.TemporaryDirectory(prefix='fdisbull-dcc-') as tmp:
        root = Path(tmp)
        (root / 'block.com').write_bytes(code + b'\xc3')
        listing_path = root / 'listing.asm'
        def run(args):
            try:
                proc = subprocess.run(args, cwd=root, capture_output=True, text=True,
                                      timeout=timeout_s, check=False)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError('DCC timed out') from exc
            except OSError as exc:
                raise RuntimeError('DCC could not start') from exc
            if proc.returncode:
                raise RuntimeError('DCC failed: ' + (proc.stderr + proc.stdout)[-4000:])
            return proc
        assembly = run([executable, '-a', '1', '-o', str(listing_path), 'block.com'])
        if not listing_path.is_file():
            raise RuntimeError('DCC produced no instruction listing')
        listing = listing_path.read_text(encoding='utf-8')
        statements, evidence = _listing_facts(listing, code)
        native = run([executable, 'block.com'])
        native_path = root / 'block.b'
        if not native_path.is_file():
            raise RuntimeError('DCC produced no native C')
        native_c = native_path.read_text(encoding='utf-8')
        if not native_c.strip():
            raise RuntimeError('DCC produced empty native C')
    text = '\n'.join(statements)
    lift_c_block(text, rebuilt['bindings'], inputs=rebuilt['inputs'], outputs=rebuilt['outputs'],
                 flags=rebuilt['flags'], pointer_assumptions=rebuilt['pointer_assumptions'])
    return {'format': 'fdisbull-dcc-asm-c-1', 'text': text,
            'source_sha256': hashlib.sha256(code).hexdigest(), 'native_c': native_c,
            'evidence': evidence,
            'diagnostics': {'covered_bytes': len(code), 'decompile_completed': True,
                'listing': listing, 'listing_output': assembly.stdout + assembly.stderr,
                'native_output': native.stdout + native.stderr,
                'synthetic_wrapper': {'offset': len(code), 'bytes': 'c3', 'format': 'DOS COM'},
                'text_provenance': 'DCC assembly instruction listing; independently normalized, not parsed from native C',
                'native_c_provenance': 'Unmodified DCC beta C output; may omit or misrepresent instruction effects',
                'scope': '16-bit register outputs only; flags, memory, interrupts, control flow, ABI and timing excluded'}}
