#!/usr/bin/env python3
"""Bounded actual-core qualification for procedural Genesis cartridges.

Component calls are assisted debugger-style state/command injections. Normal
sessions use only ordinary pad input and compare completed published snapshots
with UIL execution. Original-CPU witnesses are consumed separately. All ROM,
state, and trace artifacts remain in a new private directory outside Git.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from fdisbull.game_il import GameMachine, canonical
from check_miniplanets_native import _private_output
from check_miniplanets_nes_game import controlled_cases
from verify_miniplanets_level import GEN_SHA, plans, schedule

RAM_SIZE = 65536
DEBUG_BASE = 0x1f00
HV_BASE = 0x1e00


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2) + '\n')


def arch_read(raw, base, offset, length):
    """Decode architectural bytes from Genesis Plus GX word-swapped host RAM."""
    if any(type(n) is not int for n in (base, offset, length)) or base < 0 or offset < 0 or length < 0:
        raise ValueError('invalid RAM range')
    if offset + length > RAM_SIZE:
        raise ValueError('architectural range exceeds work RAM')
    indices = [((offset + i) ^ 1) - base for i in range(length)]
    if any(i < 0 or i >= len(raw) for i in indices):
        raise ValueError('raw RAM slice does not contain mapped bytes')
    return bytes(raw[i] for i in indices)


def physical_patches(frame, writes):
    """Pack architectural byte writes into sorted contiguous raw-RAM patches."""
    raw = {}
    for offset, data in writes:
        if type(offset) is not int or offset < 0 or offset + len(data) > RAM_SIZE:
            raise ValueError('architectural patch outside work RAM')
        for i, value in enumerate(data):
            physical = (offset + i) ^ 1
            if physical in raw:
                raise ValueError('overlapping architectural patches')
            raw[physical] = value
    result = []
    for physical in sorted(raw):
        if result and result[-1]['offset'] + len(result[-1]['data']) == physical:
            result[-1]['data'].append(raw[physical])
        else:
            result.append({'offset': physical, 'data': bytearray([raw[physical]])})
    return [{'frame': frame, 'memory_id': 2, 'offset': p['offset'],
             'data_hex': bytes(p['data']).hex()} for p in result]


def validate_layout(layout, *, packed=False):
    if not isinstance(layout, dict) or not layout:
        raise ValueError('missing state layout')
    used = set()
    for name, field in layout.items():
        if not isinstance(name, str) or not isinstance(field, dict):
            raise ValueError('invalid state field')
        offset = field.get('offset')
        bits, count, length = field.get('element_bits'), field.get('array_length'), field.get('length')
        if (type(offset) is not int or offset < 0 or bits not in (8, 16, 32)
                or type(count) is not int or count < 1 or type(length) is not int
                or length != (bits // 8) * count or type(field.get('signed')) is not bool
                or offset + length > (616 if packed else RAM_SIZE)):
            raise ValueError('invalid state field layout: ' + name)
        if not packed and (field.get('memory_id') != 2 or field.get('address', -1) & 0xffff != offset):
            raise ValueError('state address does not match system RAM offset')
        positions = set(range(offset, offset + length))
        if used & positions:
            raise ValueError('overlapping state fields')
        used.update(positions)
    return layout


def state_writes(state, layout):
    validate_layout(layout)
    if set(state) != set(layout):
        raise ValueError('state names differ from target layout')
    writes = []
    for name, field in layout.items():
        count, width = field['array_length'], field['element_bits'] // 8
        values = state[name] if count != 1 else [state[name]]
        if not isinstance(values, (list, tuple)) or len(values) != count:
            raise ValueError('state array length mismatch: ' + name)
        if any(type(value) is not int for value in values):
            raise ValueError('state values must be integers')
        mask = (1 << (width * 8)) - 1
        writes.append((field['offset'], b''.join((value & mask).to_bytes(width, 'big') for value in values)))
    return writes


def decode_fields(raw, layout, *, base=0):
    result = {}
    for name, field in layout.items():
        width, count = field['element_bits'] // 8, field['array_length']
        at = base + field['offset']
        if at < 0 or at + field['length'] > len(raw):
            raise ValueError('state slice is truncated: ' + name)
        values = [int.from_bytes(raw[at+i*width:at+(i+1)*width], 'big', signed=field['signed'])
                  for i in range(count)]
        result[name] = values if count != 1 else values[0]
    return result


def normalise_watched(row, prefix, base, length):
    """Reassemble even-aligned raw chunks and normalize by absolute address."""
    if base & 1 or length & 1:
        raise ValueError('watched aggregate must be word aligned')
    raw = b''.join(bytes.fromhex(row['raw'][f'{prefix}{i}']) for i in range(0, length, 1024))
    if len(raw) != length:
        raise ValueError('truncated RAM watch')
    return arch_read(raw, base, base, length)


def watches_for(manifest):
    layout = validate_layout(manifest['state_layout'])
    start = min(f['offset'] for f in layout.values()) & ~1
    end = (max(f['offset'] + f['length'] for f in layout.values()) + 1) & ~1
    regions = [('state', start, end - start), ('debug', DEBUG_BASE, 36),
               ('publication', 0, 4 * 704)]
    watches = []
    for prefix, base, size in regions:
        for pos in range(0, size, 1024):
            watches.append({'name': f'{prefix}{pos}', 'memory_id': 2,
                            'offset': base + pos, 'length': min(1024, size-pos)})
    if len(watches) > 64:
        raise ValueError('state watches exceed host capability')
    return watches, start, end-start


def debug_bytes(row):
    return normalise_watched(row, 'debug', DEBUG_BASE, 36)


def sampled_state(row, manifest, base, length):
    raw = normalise_watched(row, 'state', base, length)
    relative = {name: {**field, 'offset': field['offset'] - base}
                for name, field in manifest['state_layout'].items()}
    return decode_fields(raw, relative)


def publication_records(trace, manifest):
    pub = manifest['publication']
    if (pub['base'] != 0 or pub['slots'] != 4 or pub['stride'] != 704):
        raise ValueError('unsupported publication geometry')
    fields = validate_layout(pub['state_fields'], packed=True)
    if set(fields) != set(manifest['state_layout']):
        raise ValueError('publication does not bind all target state fields')
    for name, field in fields.items():
        source = manifest['state_layout'][name]
        if any(field[k] != source[k] for k in ('length', 'element_bits', 'signed', 'array_length')):
            raise ValueError('publication field type differs from native state layout: ' + name)
    expected = 1
    result = []
    for row in trace['frames']:
        raw = normalise_watched(row, 'publication', 0, 4 * 704)
        for _ in range(4):
            packet = raw[(expected % 4)*704:(expected % 4 + 1)*704]
            if packet[0] & 1 or packet[1] != 1:
                break
            epoch = int.from_bytes(packet[2:4], 'big')
            if epoch != expected:
                if result and epoch > expected and (epoch-expected) % 4 == 0:
                    raise AssertionError(f'publication ring overrun: expected {expected}, observed {epoch}')
                break
            count = packet[7]
            if count > 32:
                raise AssertionError('published HV count exceeds 32')
            hv_start = 16 + 616
            hv = [int.from_bytes(packet[hv_start+i*2:hv_start+i*2+2], 'big') for i in range(count)]
            result.append({'epoch': epoch, 'host_frame': row['frame'],
                           'input_frame': int.from_bytes(packet[4:6], 'big'),
                           'buttons': packet[6], 'sound_busy': packet[8],
                           'state': decode_fields(packet, fields, base=16), 'hv': hv})
            expected += 1
            if expected > 65535:
                raise ValueError('publication epoch wraps; shorten the run')
    return result


def shadow_publications(program, rom, manifest, receipt, trace):
    records = publication_records(trace, manifest)
    if not records:
        raise AssertionError('no completed native publications')
    first = records[0]['host_frame']
    for row in trace['frames'][first:]:
        if debug_bytes(row)[31]:
            raise AssertionError(f"native runtime fault {debug_bytes(row)[31]} at host frame {row['frame']}")
    machine = GameMachine(program, {0: rom}, environment={'hv16': [0], 'sound_busy': [0]})
    machine.call('game_boot')
    counters = {}
    for row in trace['frames']:
        value = int.from_bytes(debug_bytes(row)[:2], 'big')
        counters.setdefault(value, []).append(row['frame'])
    bits = {'RIGHT': 1, 'LEFT': 2, 'UP': 4, 'DOWN': 8, 'A': 16, 'B': 32, 'START': 64, 'SELECT': 128}
    gaps, checked_inputs, hv_words = [], 0, 0
    previous_frame = None
    for record in records:
        current = record['input_frame']
        if previous_frame is not None and not 0 < ((current - previous_frame) & 65535) < 32768:
            raise AssertionError('native scheduler reused or reversed an input frame')
        previous_frame = current
        positions = counters.get(current, [])
        if len(positions) == 1:
            host = positions[0]
            mask = trace['frames'][host]['input_mask']
            wanted = sum(bit for name, bit in bits.items()
                         if name in receipt['input_map'] and mask & (1 << receipt['input_map'][name]))
            if wanted != record['buttons']:
                raise AssertionError(f"controller mismatch at epoch {record['epoch']}")
            checked_inputs += 1
        else:
            gaps.append({'epoch': record['epoch'], 'input_frame': current, 'candidate_host_frames': positions})
        machine.set_state({'input_buttons': record['buttons']})
        machine.environment = {'hv16': record['hv'] or [0], 'sound_busy': [record['sound_busy']]}
        machine.environment_cursor = {}
        machine.events = []
        machine.call('game_frame')
        if machine.environment_cursor.get('hv16', 0) != len(record['hv']):
            raise AssertionError(f"HV consumption mismatch at epoch {record['epoch']}")
        expected, actual = machine.snapshot(), record['state']
        differences = {name: {'uil': expected[name], 'native': actual.get(name)}
                       for name in expected if name not in actual or expected[name] != actual[name]}
        if differences:
            raise AssertionError(f"completed state mismatch at epoch {record['epoch']}: {differences}")
        hv_words += len(record['hv'])
    return {'completed_ticks': len(records), 'state_fields': len(manifest['state_layout']),
            'independent_controller_checks': checked_inputs, 'controller_mapping_gaps': gaps,
            'hv_words_replayed': hv_words, 'first_epoch': records[0]['epoch'],
            'last_epoch': records[-1]['epoch'],
            'scope': 'normal native publications compared with UIL; ambiguous input-frame mapping remains unknown'}


def capture_inputs(out, paths):
    captured, identities = {}, {}
    folder = out / 'inputs'
    folder.mkdir()
    for name, path in paths.items():
        source = Path(path).expanduser().resolve()
        raw = source.read_bytes()
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        captured[name] = target
        identities[name] = {'source': str(source), 'sha256': sha(raw), 'size': len(raw)}
    return captured, identities


def run_host(core, cartridge, host_script, out, frames, watches, *, patches=(), inputs=(), audio=False):
    save(out.parent / (out.name + '-watches.json'), watches)
    save(out.parent / (out.name + '-patches.json'), list(patches))
    save(out.parent / (out.name + '-inputs.json'), list(inputs))
    args = [sys.executable, str(host_script), '--core', str(core), '--rom', str(cartridge),
            '--system', 'genesis', '--frames', str(frames),
            '--watch', str(out.parent / (out.name + '-watches.json')),
            '--patches', str(out.parent / (out.name + '-patches.json')),
            '--inputs', str(out.parent / (out.name + '-inputs.json')),
            '--output', str(out), '--timeout', '300']
    if audio:
        args.append('--capture-audio')
    run = subprocess.run(args, capture_output=True, text=True, timeout=320)
    if run.returncode:
        raise RuntimeError(run.stderr[-5000:])
    receipt = json.loads((out / 'receipt.json').read_text())
    if receipt['core_sha256'] != GEN_SHA or receipt['rom_sha256'] != sha(Path(cartridge).read_bytes()):
        raise AssertionError('core or target cartridge differs from captured inputs')
    return receipt, json.loads((out / 'ram_trace.json').read_text())


def component_checks(program, rom, manifest, cases, core, cartridge, host, out, watches, state_base, state_length,
                     *, spacing, batch_size):
    machine = GameMachine(program, {0: rom}, environment={'hv16': [0], 'sound_busy': [0]})
    totals = Counter()
    batches = []
    for start in range(0, len(cases), batch_size):
        batch = cases[start:start+batch_size]
        # Allow VDP/asset initialization to finish before seeding any case.
        patches = physical_patches(120, [(DEBUG_BASE+4, b'\x01')])
        expected = []
        for i, case in enumerate(batch):
            machine.set_state(case['before'])
            machine.events = []
            machine.environment_cursor = {}
            machine.environment = {'hv16': case['hv'] if case['hv'] else [0], 'sound_busy': [0]}
            result = machine.call(case['entry'], *case['args'])
            wanted, hv_count, events = machine.snapshot(), machine.environment_cursor.get('hv16', 0), list(machine.events)
            samples = case['hv'] or [0] * 32
            if len(samples) > 32 or len(case['args']) > 4:
                raise ValueError('case exceeds Genesis debug argument/HV contract')
            if case['entry'] not in manifest['procedures']:
                raise ValueError('case procedure is absent from target manifest')
            at = 150 + i * spacing
            command = bytearray(32)
            command[0] = 1  # debug mode
            command[1] = 1  # pending command
            command[2:4] = int(manifest['procedures'][case['entry']]).to_bytes(2, 'big')
            for j, value in enumerate(case['args']):
                command[4+j*4:8+j*4] = (value & 0xffffffff).to_bytes(4, 'big')
            command[20:24] = bytes.fromhex('deadbeef')
            command[24] = len(samples)
            writes = state_writes(case['before'], manifest['state_layout'])
            writes += [(HV_BASE, b''.join(x.to_bytes(2, 'big') for x in samples)),
                       (DEBUG_BASE+4, command)]
            patches.extend(physical_patches(at, writes))
            expected.append((wanted, result['result'] & 0xffffffff, hv_count, events))
        folder = out / f'components-{start//batch_size:03d}'
        receipt, trace = run_host(core, cartridge, host, folder, 150+len(batch)*spacing,
                                  watches, patches=patches)
        rows = trace['frames']
        for i, (case, exp) in enumerate(zip(batch, expected)):
            at = 150+i*spacing
            previous = debug_bytes(rows[at-1])
            if previous[5] != 0:
                raise AssertionError('previous native command was not completed')
            previous_epoch = int.from_bytes(previous[2:4], 'big')
            completed = None
            for row in rows[at:at+spacing]:
                control = debug_bytes(row)
                if control[31]:
                    raise AssertionError(f"native fault {control[31]} in {case['name']}")
                if control[5] == 0 and int.from_bytes(control[2:4], 'big') == ((previous_epoch+1)&65535):
                    completed = row
                    break
            if completed is None:
                raise AssertionError(f"native command timeout/epoch mismatch: {case['name']}")
            wanted, wanted_result, hv_count, events = exp
            actual = sampled_state(completed, manifest, state_base, state_length)
            differences = {k: {'uil': wanted[k], 'native': actual.get(k)} for k in wanted
                           if k not in actual or wanted[k] != actual[k]}
            if differences:
                raise AssertionError(f"state mismatch for {case['name']}: {differences}")
            control = debug_bytes(completed)
            if int.from_bytes(control[24:28], 'big') != wanted_result:
                raise AssertionError(f"return mismatch for {case['name']}")
            if control[29] != hv_count:
                raise AssertionError(f"HV consumption mismatch for {case['name']}")
            if int.from_bytes(control[32:34], 'big') != len(events):
                raise AssertionError(f"event count mismatch for {case['name']}")
            if events and (control[34], control[35]) != (events[-1]['kind'], events[-1]['id']):
                raise AssertionError(f"last event mismatch for {case['name']}")
            totals[case['entry']] += 1
        batches.append({'batch': start//batch_size, 'checked': len(batch),
                        'trace_sha256': receipt['ram_trace_sha256'],
                        'patch_trace_sha256': receipt['patch_trace_sha256']})
        print(f'Genesis components {start+len(batch)}/{len(cases)}', flush=True)
    return {'case_count': sum(totals.values()), 'procedures': dict(totals), 'batches': batches,
            'scope': 'assisted direct calls and state seeds; original-CPU source witness is separate'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('rom', 'cartridge', 'core', 'output'):
        ap.add_argument('--'+name, required=True)
    ap.add_argument('--manifest')
    ap.add_argument('--program')
    ap.add_argument('--phase', choices=('smoke', 'components', 'normal', 'all'), default='all')
    ap.add_argument('--common-cases-root')
    ap.add_argument('--actor-cases-root', action='append', default=[])
    ap.add_argument('--case-limit', type=int)
    ap.add_argument('--spacing', type=int, default=24)
    ap.add_argument('--batch-size', type=int, default=16)
    ap.add_argument('--normal-frames', type=int, default=1800)
    args = ap.parse_args()
    if not 4 <= args.spacing <= 100 or not 1 <= args.batch_size <= 32:
        ap.error('invalid bounded component schedule')
    if not 100 <= args.normal_frames <= 10000 or (args.case_limit is not None and args.case_limit < 1):
        ap.error('invalid finite test budget')
    cartridge = Path(args.cartridge).resolve()
    manifest_path = Path(args.manifest).resolve() if args.manifest else cartridge.with_name('manifest.json')
    program_path = Path(args.program).resolve() if args.program else cartridge.with_name('program.json')
    paths = {'source.rom': args.rom, 'target.md': cartridge, 'core.dylib': args.core,
             'manifest.json': manifest_path, 'program.json': program_path,
             'host.py': ROOT/'scripts/check_console_udc.py', 'verifier.py': Path(__file__),
             'source-game-il.py': ROOT/'src/fdisbull/game_il.py',
             'source-case-reader.py': ROOT/'scripts/check_miniplanets_nes_game.py',
             'source-level-verifier.py': ROOT/'scripts/verify_miniplanets_level.py',
             'source-contract.json': ROOT/'src/fdisbull/data/miniplanets_full_contract.json'}
    if args.common_cases_root:
        folder = Path(args.common_cases_root)
        for p in folder.glob('*.json'):
            paths['common/'+p.name] = p
            if p.name != 'summary.json':
                receipt = folder / p.stem / 'receipt.json'
                paths[f'common/{p.stem}/receipt.json'] = receipt
    for i, name in enumerate(args.actor_cases_root):
        folder = Path(name)
        for p in folder.glob('contract-*.json'):
            paths[f'actors-{i}/{p.name}'] = p
            receipt = folder / ('native-'+p.stem.split('-')[-1]) / 'receipt.json'
            paths[f'actors-{i}/{receipt.parent.name}/receipt.json'] = receipt
    output = _private_output(args.output)
    output.mkdir()
    captured, identities = capture_inputs(output, paths)
    rom = captured['source.rom'].read_bytes()
    target = captured['target.md']
    core = captured['core.dylib']
    manifest = json.loads(captured['manifest.json'].read_text())
    program = json.loads(captured['program.json'].read_text())
    if (manifest.get('format') != 'fdisbull-genesis-game-1'
            or manifest.get('rom_sha256') != sha(target.read_bytes())
            or manifest.get('source_rom_sha256') != sha(rom)
            or manifest.get('program_sha256') != sha(canonical(program))
            or sha(core.read_bytes()) != GEN_SHA):
        raise ValueError('Genesis cartridge/source/core/program identity mismatch')
    watches, state_base, state_length = watches_for(manifest)
    machine = GameMachine(program, {0: rom})
    if set(machine.snapshot()) != set(manifest['state_layout']):
        raise ValueError('Genesis layout does not bind every UIL state field')
    summary = {'format': 'fdisbull-genesis-game-verification-1', 'status': 'running',
               'cartridge_sha256': manifest['rom_sha256'], 'source_rom_sha256': sha(rom),
               'core_sha256': GEN_SHA, 'program_sha256': sha(canonical(program)),
               'inputs': identities, 'components': None, 'normal': None,
               'scope': 'bounded target native-core observations; original witnesses and ordinary play are separate'}
    try:
        if args.phase in ('smoke', 'components', 'all'):
            common = output/'inputs/common' if args.common_cases_root else None
            actors = [output/f'inputs/actors-{i}' for i in range(len(args.actor_cases_root))]
            # The stored contract's exact bytes must match the original-core
            # completion receipt, not merely the summary's claimed case count.
            for folder, pattern in ([(common, '*.json')] if common else []) + [(x, 'contract-*.json') for x in actors]:
                for contract in sorted(folder.glob(pattern)):
                    if contract.name == 'summary.json':
                        continue
                    actor = folder.name.startswith('actors-')
                    receipt_path = (folder / ('native-'+contract.stem.split('-')[-1]) / 'receipt.json'
                                    if actor else folder / contract.stem / 'receipt.json')
                    proof = json.loads(receipt_path.read_text())
                    case_doc = json.loads(contract.read_text())
                    if (not proof.get('complete') or not proof.get('inputs_unchanged')
                            or proof.get('source_sha256') != sha(rom) or proof.get('core_sha256') != GEN_SHA
                            or proof.get('contract_sha256') != sha(contract.read_bytes())
                            or len(proof.get('cases', [])) != len(case_doc.get('cases', []))):
                        raise ValueError('original-core case receipt mismatch: ' + contract.name)
            cases = controlled_cases(program, rom, common, actors)
            if args.phase == 'smoke':
                cases = cases[:4]
            if args.case_limit is not None:
                cases = cases[:args.case_limit]
            if not cases:
                raise ValueError('no controlled cases selected')
            summary['components'] = component_checks(program, rom, manifest, cases, core, target,
                captured['host.py'], output, watches, state_base, state_length,
                spacing=args.spacing, batch_size=args.batch_size)
        if args.phase in ('normal', 'all'):
            values = plans()['complete_level']
            route = schedule(values, 600)
            inputs = [{'start': 150, 'end': 155, 'buttons': ['START']}] + route
            inputs = [x for x in inputs if x['end'] <= args.normal_frames]
            receipt, trace = run_host(core, target, captured['host.py'], output/'normal-route',
                                      args.normal_frames, watches, inputs=inputs, audio=True)
            summary['normal'] = shadow_publications(program, rom, manifest, receipt, trace)
            summary['normal']['assistance'] = 'ordinary scheduled controller input; no RAM writes'
            summary['normal']['trace_sha256'] = receipt['ram_trace_sha256']
        for name, identity in identities.items():
            if sha(Path(identity['source']).read_bytes()) != identity['sha256'] or sha(captured[name].read_bytes()) != identity['sha256']:
                raise AssertionError('captured input changed during verification: ' + name)
        summary['inputs_unchanged'] = True
        summary['status'] = 'passed'
    except BaseException as exc:
        summary['status'] = 'failed'
        summary['failure'] = f'{type(exc).__name__}: {exc}'
        save(output/'summary.json', summary)
        raise
    save(output/'summary.json', summary)
    print(output/'summary.json')


if __name__ == '__main__':
    main()
