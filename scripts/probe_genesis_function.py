#!/usr/bin/env python3
"""Execute a declared original-ROM 68000 boundary in a pinned real Genesis core.

This is controlled function/block entry, not an ordinary game-reachability test.
The core's actual CPU executes instructions; Capstone supplies trace lengths only.
All byte-retaining outputs must be placed in a fresh private directory.
"""
from __future__ import annotations

import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import capstone
from capstone import CS_ARCH_M68K, CS_MODE_BIG_ENDIAN, CS_MODE_M68K_000, Cs


CORE_SHA256 = '27bc2ef8ca07c775f022ae90be381b2a2a500245c9c7e362356ba3077b25c268'
REGISTERS = {**{f'D{i}': i for i in range(8)}, **{f'A{i}': i + 8 for i in range(8)},
             'PC': 16, 'SR': 17}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def validate_contract(contract, rom_size):
    allowed = {'name', 'entry', 'code_ranges', 'registers', 'ram', 'watch',
               'max_instructions', 'max_master_cycles', 'stack_address',
               'return_address', 'stack_scratch_bytes', 'stop_pcs', 'ccr'}
    if not isinstance(contract, dict) or set(contract) - allowed:
        raise ValueError('invalid or unknown contract fields')
    if 'name' in contract and (not isinstance(contract['name'], str) or not contract['name'] or len(contract['name']) > 128):
        raise ValueError('name must be a nonempty string up to 128 characters')
    entry = contract.get('entry')
    if not _integer(entry, 0x200, rom_size - 2) or entry % 2:
        raise ValueError('entry must be an aligned source-ROM address')
    ranges = contract.get('code_ranges')
    if not isinstance(ranges, list) or not 1 <= len(ranges) <= 16:
        raise ValueError('code_ranges must contain 1..16 exact source intervals')
    occupied = set()
    for item in ranges:
        if not isinstance(item, dict) or set(item) != {'start', 'end'}:
            raise ValueError('each code range requires start and exclusive end')
        start, end = item['start'], item['end']
        if not (_integer(start, 0x200, rom_size - 2) and
                _integer(end, start + 2, rom_size) and not (start | end) % 2):
            raise ValueError('invalid aligned source code range')
        if (end - start) // 2 + len(occupied) > 32768:
            raise ValueError('total source budget exceeded')
        words = set(range(start, end, 2))
        if words & occupied:
            raise ValueError('overlapping source ranges')
        occupied |= words
    if len(occupied) > 32768 or entry not in occupied:
        raise ValueError('entry outside ranges or total source budget exceeded')
    registers = contract.get('registers', {})
    if (not isinstance(registers, dict) or set(registers) - (set(REGISTERS) - {'A7', 'PC', 'SR'}) or
            any(not _integer(v, 0, 0xffffffff) for v in registers.values())):
        raise ValueError('register inputs must be unsigned D0..D7 or A0..A6 values')
    if not _integer(contract.get('ccr', 0), 0, 31):
        raise ValueError('ccr must be 0..31; supervisor and interrupt mask are fixed')
    for key, default, maximum in (('max_instructions', 1000, 200000),
                                   ('max_master_cycles', 1000000, 10000000)):
        if not _integer(contract.get(key, default), 1, maximum):
            raise ValueError(f'invalid {key}')
    stack = contract.get('stack_address', 0xfffe00)
    sentinel = contract.get('return_address', 0xfffd00)
    scratch = contract.get('stack_scratch_bytes', 0)
    if (not _integer(stack, 0xff0100, 0xfffff8) or stack % 2 or
            not _integer(sentinel, 0xff0000, 0xfffffe) or sentinel % 2 or
            not _integer(scratch, 0, 1024) or stack - scratch < 0xff0000):
        raise ValueError('invalid controlled stack or return sentinel')
    stop_pcs = contract.get('stop_pcs')
    if stop_pcs is not None:
        if (not isinstance(stop_pcs, list) or not 1 <= len(stop_pcs) <= 32 or
                any(not _integer(v, 0, rom_size) or v % 2 or v == entry for v in stop_pcs) or
                len(set(stop_pcs)) != len(stop_pcs) or 'return_address' in contract):
            raise ValueError('invalid explicit stop PCs or conflicting return sentinel')
    seeded = set()
    ram = contract.get('ram', [])
    if not isinstance(ram, list) or len(ram) > 64:
        raise ValueError('ram seeds must be a list of up to 64 regions')
    total = 0
    for item in ram:
        if not isinstance(item, dict) or set(item) != {'address', 'data'} or not isinstance(item['data'], str):
            raise ValueError('ram seeds require address and hexadecimal data')
        try:
            data = bytes.fromhex(item['data'])
        except ValueError as exc:
            raise ValueError('invalid RAM seed encoding') from exc
        address = item['address']
        if (not 1 <= len(data) <= 4096 or not _integer(address, 0xff0000, 0xffffff) or
                address + len(data) > 0x1000000):
            raise ValueError('RAM seed outside work RAM or size bounds')
        positions = set(range(address, address + len(data)))
        if positions & seeded or (stop_pcs is None and positions & set(range(stack, stack + 4))):
            raise ValueError('overlapping RAM seeds or controlled return frame')
        seeded |= positions
        total += len(data)
    if total > 16384:
        raise ValueError('RAM seed budget exceeded')
    watches = contract.get('watch', [])
    if not isinstance(watches, list) or len(watches) > 64:
        raise ValueError('watch must contain up to 64 named RAM ranges')
    names = set()
    total = 0
    for item in watches:
        if not isinstance(item, dict) or set(item) != {'name', 'address', 'length'}:
            raise ValueError('watch entries require name, address and length')
        name, address, length = item['name'], item['address'], item['length']
        if (not isinstance(name, str) or not name or len(name) > 128 or name in names or
                not _integer(address, 0xff0000, 0xffffff) or not _integer(length, 1, 4096) or
                address + length > 0x1000000):
            raise ValueError('invalid or duplicate RAM watch')
        names.add(name)
        total += length
    if total > 32768:
        raise ValueError('RAM watch budget exceeded')
    return contract


class GameInfo(C.Structure):
    _fields_ = [('path', C.c_char_p), ('data', C.c_void_p), ('size', C.c_size_t), ('meta', C.c_char_p)]


class SystemInfo(C.Structure):
    _fields_ = [('library_name', C.c_char_p), ('library_version', C.c_char_p),
                ('valid_extensions', C.c_char_p), ('need_fullpath', C.c_bool), ('block_extract', C.c_bool)]


class MemoryMap(C.Structure):
    _fields_ = [(name, C.c_void_p) for name in ('base', 'read8', 'read16', 'write8', 'write16')]


class PollState(C.Structure):
    _fields_ = [(name, C.c_uint) for name in ('pc', 'cycle', 'detected')]


class CpuPrefix(C.Structure):
    # f27655b core/m68k/m68k.h. The pinned arm64 binary additionally confirms
    # the signed master-cycle field is at offset 0x280c in m68k_run.
    _fields_ = [('memory_map', MemoryMap * 256), ('poll', PollState),
                ('cycles', C.c_int), ('refresh_cycles', C.c_int), ('cycle_end', C.c_uint)]


def _private_output(path):
    out = Path(path).expanduser().resolve()
    if out.exists() or not out.parent.is_dir():
        raise ValueError('output must be fresh and its parent must exist')
    if any((p / '.git').exists() for p in (out, *out.parents)):
        raise ValueError('byte-retaining output must be outside every Git worktree')
    return out


def expand_contracts(contract, rom_size):
    if not isinstance(contract, dict):
        raise ValueError('contract must be an object')
    common = {key: value for key, value in contract.items() if key != 'cases'}
    validate_contract(common, rom_size)
    cases = contract.get('cases')
    if cases is None:
        return [common]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 4096:
        raise ValueError('cases must contain 1..4096 boundary inputs')
    result = []
    names = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict) or set(case) - {'name', 'registers', 'ram', 'ccr'}:
            raise ValueError('batch cases may override name, registers, ram seeds or ccr only')
        merged = {**common, **case}
        if not isinstance(case.get('registers', {}), dict):
            raise ValueError('case register inputs must be an object')
        merged['registers'] = {**common.get('registers', {}), **case.get('registers', {})}
        merged['name'] = case.get('name', f'case{index:04d}')
        if not isinstance(merged['name'], str) or not merged['name'] or len(merged['name']) > 128 or merged['name'] in names:
            raise ValueError('case names must be unique nonempty strings up to 128 characters')
        names.add(merged['name'])
        result.append(validate_contract(merged, rom_size))
    if sum(item.get('max_instructions', 1000) for item in result) > 131072:
        raise ValueError('combined batch instruction budget exceeds 131072')
    return result


def execute_boundary(lib, cpu, raw_ram, rom, contract, out, retain_ram):
    report = {'complete': False, 'contract': contract, 'full_ram_retained': retain_ram}
    trace = []
    before_ram = None
    C.memset(C.addressof(raw_ram), 0, len(raw_ram))
    try:
        def put(address, data):
            for index, byte in enumerate(data):
                raw_ram[((address + index) & 0xffff) ^ 1] = byte

        def architectural_ram():
            raw = bytes(raw_ram)
            return bytes(raw[i ^ 1] for i in range(len(raw)))

        def registers():
            return {name: lib.m68k_get_reg(number) for name, number in REGISTERS.items()}

        for number in range(16):
            lib.m68k_set_reg(number, 0)
        lib.m68k_set_reg(REGISTERS['SR'], 0x2700 | contract.get('ccr', 0))
        lib.m68k_set_irq(0)
        for name, value in contract.get('registers', {}).items():
            lib.m68k_set_reg(REGISTERS[name], value)
        stack = contract.get('stack_address', 0xfffe00)
        lib.m68k_set_reg(REGISTERS['A7'], stack)
        for item in contract.get('ram', []):
            put(item['address'], bytes.fromhex(item['data']))
        stop_pcs = contract.get('stop_pcs')
        sentinel = contract.get('return_address', 0xfffd00)
        if stop_pcs is None:
            put(stack, sentinel.to_bytes(4, 'big'))
            stop_pcs = [sentinel]
            report['boundary'] = {'mode': 'RTS return sentinel', 'stop_pcs': stop_pcs}
        else:
            report['boundary'] = {'mode': 'explicit stop before executing exit PC', 'stop_pcs': stop_pcs}
        lib.m68k_set_reg(REGISTERS['PC'], contract['entry'])
        before_ram = architectural_ram()
        report['registers_before'] = registers()
        report['ram_before'] = {item['name']: before_ram[item['address'] & 0xffff:(item['address'] & 0xffff) + item['length']].hex()
                                for item in contract.get('watch', [])}
        start_cycles = cpu.cycles
        if not 0 <= start_cycles < 0x7fffffff - 10000000:
            raise RuntimeError('unexpected initial CPU cycle counter')
        decoder = Cs(CS_ARCH_M68K, CS_MODE_BIG_ENDIAN | CS_MODE_M68K_000)
        for index in range(contract.get('max_instructions', 1000)):
            pc = lib.m68k_get_reg(REGISTERS['PC'])
            if index and pc in stop_pcs:
                break
            span = next((item for item in contract['code_ranges'] if item['start'] <= pc < item['end']), None)
            if span is None:
                raise RuntimeError(f'CPU left declared source ranges at {pc:#x}')
            instruction = next(decoder.disasm(rom[pc:min(pc + 22, span['end'])], pc, count=1), None)
            if instruction is None or instruction.address + instruction.size > span['end']:
                raise RuntimeError(f'incomplete or undecodable source instruction at {pc:#x}')
            for address in range(pc, pc + instruction.size, 2):
                base = cpu.memory_map[address >> 16].base
                if not base or C.c_ushort.from_address(base + (address & 0xffff)).value != int.from_bytes(rom[address:address + 2], 'big'):
                    raise RuntimeError(f'native instruction mapping differs from retained source at {address:#x}')
            previous = cpu.cycles
            lib.m68k_run(previous + 1)
            now = cpu.cycles
            if now <= previous:
                raise RuntimeError('CPU instruction did not advance its cycle counter')
            trace.append({'index': index, 'pc': pc, 'bytes': bytes(instruction.bytes).hex(),
                          'mnemonic': instruction.mnemonic, 'operands': instruction.op_str,
                          'next_pc': lib.m68k_get_reg(REGISTERS['PC']),
                          'master_cycles': now - previous, 'registers_after': registers()})
            if now - start_cycles > contract.get('max_master_cycles', 1000000):
                raise RuntimeError('native master-cycle budget exhausted')
        else:
            # A final bounded instruction is allowed to reach the exit.
            if lib.m68k_get_reg(REGISTERS['PC']) not in stop_pcs:
                raise RuntimeError('native instruction budget exhausted')
        final_pc = lib.m68k_get_reg(REGISTERS['PC'])
        if not trace or final_pc not in stop_pcs:
            raise RuntimeError('native boundary was not completed')
        if contract.get('stop_pcs') is None and lib.m68k_get_reg(REGISTERS['A7']) != stack + 4:
            raise RuntimeError('return did not consume exactly the controlled four-byte frame')
        report['complete'] = True
        report['status'] = 'returned' if contract.get('stop_pcs') is None else 'reached-explicit-stop'
        report['instructions_executed'] = len(trace)
        report['master_cycles'] = cpu.cycles - start_cycles
        report['registers_after'] = registers()
    except Exception as exc:
        report['status'] = 'failed'
        report['failure'] = f'{type(exc).__name__}: {exc}'
    finally:
        if raw_ram is not None:
            after = bytes(raw_ram[i ^ 1] for i in range(len(raw_ram)))
            if retain_ram:
                (out / 'ram-after.bin').write_bytes(after)
            report['ram_after_sha256'] = sha(after)
            report['ram_after'] = {item['name']: after[item['address'] & 0xffff:(item['address'] & 0xffff) + item['length']].hex()
                                   for item in contract.get('watch', [])}
            if before_ram is not None:
                if retain_ram:
                    (out / 'ram-before.bin').write_bytes(before_ram)
                report['ram_before_sha256'] = sha(before_ram)
                changed = [0xff0000 + i for i, (a, b) in enumerate(zip(before_ram, after)) if a != b]
                report['changed_ram_addresses'] = changed
                watched = {item['address'] + i for item in contract.get('watch', []) for i in range(item['length'])}
                stack = contract.get('stack_address', 0xfffe00)
                scratch = set(range(stack - contract.get('stack_scratch_bytes', 0), stack + 4))
                allowed = watched | scratch
                report['changes_outside_watches_and_stack'] = [address for address in changed if address not in allowed]
                if report['changes_outside_watches_and_stack']:
                    report['complete'] = False
                    report['status'] = 'failed'
                    report['failure'] = 'native writes changed work RAM outside declared watches and explicit stack scratch'
        trace_bytes = (json.dumps(trace, separators=(',', ':')) + '\n').encode()
        report['trace_sha256'] = sha(trace_bytes)
    return report, trace


def worker(args):
    core = Path(args.core).resolve()
    source = Path(args.rom).resolve()
    contract_path = Path(args.contract).resolve()
    core_bytes = core.read_bytes()
    if sha(core_bytes) != CORE_SHA256:
        raise ValueError('native CPU ABI and RAM mapping are qualified only for the pinned core hash')
    if not 0x200 <= source.stat().st_size <= 4 * 1024 * 1024:
        raise ValueError('source must be a direct-mapped Genesis ROM of 512 bytes through 4 MiB')
    rom = source.read_bytes()
    if contract_path.stat().st_size > 1024 * 1024:
        raise ValueError('contract exceeds 1 MiB')
    contract_bytes = contract_path.read_bytes()
    contract = json.loads(contract_bytes)
    contracts = expand_contracts(contract, len(rom))
    out = _private_output(args.output)
    out.mkdir()
    report = {'format': 'fdisbull-genesis-native-boundary-1', 'complete': False,
              'mode': 'controlled entry into original ROM mapping; ordinary game reachability not established',
              'source_sha256': sha(rom), 'core_sha256': CORE_SHA256,
              'trace_decoder': {'name': 'Capstone', 'version': capstone.__version__,
                                'role': 'instruction lengths and trace facts only; native CPU executes semantics'},
              'contract_sha256': sha(contract_bytes),
              'probe_source_sha256': sha(Path(__file__).read_bytes()), 'contract': contract,
              'assumptions': ['work RAM cleared to zero before declared seeds',
                              'all data/address registers cleared before declared inputs',
                              'supervisor mode, interrupt level masked to 7, IRQ pins clear',
                              'core hardware initialization at load; no ordinary game frames executed',
                              'raw Genesis RAM bytes are pair swapped for this exact core'],
              'limits': ['controlled CPU boundary only; not a gameplay, device-timing or whole-game equivalence claim']}
    trace = []
    lib = None
    loaded = False
    initialized = False
    raw_ram = None
    try:
        if CpuPrefix.cycles.offset != 0x280c or C.sizeof(MemoryMap) != 40:
            raise RuntimeError('host ctypes layout does not match qualified arm64 CPU ABI')
        lib = C.CDLL(str(core))
        ENV = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
        VIDEO = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
        AUDIO = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
        BATCH = C.CFUNCTYPE(C.c_size_t, C.POINTER(C.c_int16), C.c_size_t)
        POLL = C.CFUNCTYPE(None)
        STATE = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)
        system_dir = C.create_string_buffer(os.fsencode(out))

        @ENV
        def environment(cmd, data):
            if cmd == 10:
                return C.cast(data, C.POINTER(C.c_int))[0] in (0, 1, 2)
            if cmd in (9, 31):
                C.cast(data, C.POINTER(C.c_char_p))[0] = C.cast(system_dir, C.c_char_p)
                return True
            if cmd == 3:
                C.cast(data, C.POINTER(C.c_bool))[0] = True
                return True
            return False

        callbacks = [(lib.retro_set_environment, environment),
                     (lib.retro_set_video_refresh, VIDEO(lambda *unused: None)),
                     (lib.retro_set_audio_sample, AUDIO(lambda *unused: None)),
                     (lib.retro_set_audio_sample_batch, BATCH(lambda data, count: count)),
                     (lib.retro_set_input_poll, POLL(lambda: None)),
                     (lib.retro_set_input_state, STATE(lambda *unused: 0))]
        for setter, callback in callbacks:
            setter.argtypes = [type(callback)]
            setter(callback)
        lib.retro_init()
        initialized = True
        info = SystemInfo()
        lib.retro_get_system_info(C.byref(info))
        report['core_name'] = info.library_name.decode()
        report['core_version'] = info.library_version.decode()
        rom_buffer = C.create_string_buffer(rom)
        game = GameInfo(os.fsencode(source), None if info.need_fullpath else C.cast(rom_buffer, C.c_void_p), len(rom), None)
        lib.retro_load_game.argtypes = [C.POINTER(GameInfo)]
        lib.retro_load_game.restype = C.c_bool
        if not lib.retro_load_game(C.byref(game)):
            raise RuntimeError('core rejected source cartridge')
        loaded = True
        lib.m68k_get_reg.argtypes = [C.c_uint]
        lib.m68k_get_reg.restype = C.c_uint
        lib.m68k_set_reg.argtypes = [C.c_uint, C.c_uint]
        lib.m68k_set_reg.restype = None
        lib.m68k_set_irq.argtypes = [C.c_uint]
        lib.m68k_set_irq.restype = None
        lib.m68k_run.argtypes = [C.c_uint]
        lib.m68k_run.restype = None
        cpu = CpuPrefix.in_dll(lib, 'm68k')
        raw_ram = (C.c_ubyte * 65536).in_dll(lib, 'work_ram')
        report['cases'] = []
        report['cases_requested'] = len(contracts)
        for index, item in enumerate(contracts):
            case_report, steps = execute_boundary(lib, cpu, raw_ram, rom, item, out, len(contracts) == 1)
            report['cases'].append(case_report)
            trace.append({'case_index': index, 'steps': steps})
            if not case_report['complete']:
                raise RuntimeError(f"case {index}: {case_report.get('failure', 'boundary incomplete')}")
        report['complete'] = True
        report['status'] = 'completed'
        report['cases_completed'] = len(report['cases'])
        report['instructions_executed'] = sum(item['instructions_executed'] for item in report['cases'])
        report['master_cycles'] = sum(item['master_cycles'] for item in report['cases'])
    except Exception as exc:
        report['status'] = 'failed'
        report['failure'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        trace_bytes = (json.dumps(trace, separators=(',', ':')) + '\n').encode()
        (out / 'trace.json').write_bytes(trace_bytes)
        report['trace_sha256'] = sha(trace_bytes)
        unchanged = (sha(source.read_bytes()) == report['source_sha256'] and
                     sha(core.read_bytes()) == CORE_SHA256 and sha(contract_path.read_bytes()) == report['contract_sha256'] and
                     sha(Path(__file__).read_bytes()) == report['probe_source_sha256'])
        report['inputs_unchanged'] = unchanged
        if not unchanged:
            report['complete'] = False
            report['status'] = 'failed'
            report['failure'] = 'source, core, contract or probe changed during execution'
        (out / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
        if loaded:
            lib.retro_unload_game()
        if initialized:
            lib.retro_deinit()
    if not report['complete']:
        raise RuntimeError(report.get('failure', 'native boundary incomplete'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', required=True)
    parser.add_argument('--rom', required=True)
    parser.add_argument('--contract', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 0 < args.timeout <= 600:
        parser.error('timeout must be 0..600 seconds')
    try:
        _private_output(args.output)
    except ValueError as exc:
        parser.error(str(exc))
    if args.worker:
        worker(args)
    else:
        try:
            result = subprocess.run([sys.executable, __file__, *sys.argv[1:], '--worker'],
                                    capture_output=True, text=True, timeout=args.timeout)
        except subprocess.TimeoutExpired:
            raise SystemExit('native function worker timed out')
        if result.returncode:
            raise SystemExit(f'native function worker failed ({result.returncode}): {result.stderr[-4000:]}')
        print(Path(args.output).resolve() / 'receipt.json')


if __name__ == '__main__':
    main()
