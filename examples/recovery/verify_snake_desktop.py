"""Qualify native Windows x86/x64, Win16 NE and Linux Snake artifacts.

Use the exact private original/RNG study from the earlier qualified pilot. This
recipe compares independent DOS witnesses with native output; it does not use a
second UIL interpreter as a source oracle. Original-RNG expectations come from
DOS witnesses; deliberately different LFSR expectations come from the declared
variant reference. Programmatic Windows/X11 event paths,
owned native surfaces, physical hardware and Microsoft Windows execution are
separate claims. An explicit runner can transport bytes into a local test VM.
"""
from __future__ import annotations

import argparse
import base64
from fractions import Fraction
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import struct
import subprocess

from verify_snake_macos import CANONICAL_UIL, SCALARS, digest, file_hash, same

UDL = '986713c25859408dcefe33186b74eb249956934d71d69ad71797c787da9c56d1'
STUDY = 'f9349c934e4db4a2abf6d29f75a2e0e5c5182930ac6f61f0f57c12a7d59aeeae'
SNAPSHOT, KEY, POINTER, CLOCK, SELECT, RESIZE, REPLACE, FOCUS, INITIALIZE, CLOSE, CALL = range(11)
FRAME, VIEW, EXPECT_REFUSAL = 1, 2, 4


def command(kind, **values):
    return {'kind': kind, **values}


def rgba(indexed, palette):
    table = {int(key): bytes([*value, 255]) for key, value in palette.items()}
    return b''.join(table[index] for index in indexed)


def fitted_view(indexed, palette, source_width, source_height, width, height):
    """Independent rational fit and exact pixel-center source selection."""
    scale = min(Fraction(width, source_width), Fraction(height, source_height))
    rw, rh = int(source_width * scale), int(source_height * scale)
    if not rw or not rh:
        raise ValueError('Empty expected viewport')
    left, top = (width-rw)//2, (height-rh)//2
    result = bytearray(bytes([0, 0, 0, 255]) * (width*height))
    colors = {int(key): bytes([*value, 255]) for key, value in palette.items()}
    xs = [int(Fraction(2*x+1, 2) * source_width/rw) for x in range(rw)]
    ys = [int(Fraction(2*y+1, 2) * source_height/rh) for y in range(rh)]
    for dy, sy in enumerate(ys):
        row = b''.join(colors[indexed[sy*source_width+sx]] for sx in xs)
        at = ((top+dy)*width+left)*4
        result[at:at+rw*4] = row
    return bytes(result), [left, top, rw, rh]


def local_runner(bundle, destination):
    def run(executable, input_bytes, label):
        incoming, outgoing = destination/(label+'.input.bin'), destination/(label+'.output.bin')
        incoming.write_bytes(input_bytes)
        invocation = [str(executable), '--adapter-test', str(incoming), str(outgoing)]
        done = subprocess.run(invocation, cwd=bundle, capture_output=True, timeout=600)
        output = outgoing.read_bytes() if outgoing.exists() else b''
        receipt = {'argv': invocation, 'exit_code': done.returncode,
            'stdout': done.stdout.decode(errors='replace'), 'stderr': done.stderr.decode(errors='replace'),
            'host': platform.platform(), 'executable_sha256': file_hash(executable),
            'input_sha256': hashlib.sha256(input_bytes).hexdigest(), 'output_sha256': hashlib.sha256(output).hexdigest()}
        (destination/(label+'-execution.json')).write_text(json.dumps(receipt, indent=2)+'\n')
        (destination/(label+'.input.gz')).write_bytes(gzip.compress(input_bytes, mtime=0))
        if outgoing.exists():
            (destination/(label+'.output.gz')).write_bytes(gzip.compress(output, mtime=0))
            outgoing.unlink()
        incoming.unlink()
        if done.returncode:
            raise AssertionError('Native process failed: '+json.dumps(receipt))
        return output, receipt
    return run


def verify(bundle, study_path, destination, *, runner_path=None):
    from fdisbull.udc_memory_desktop import encode_study, decode_study
    bundle, study_path, destination = map(lambda p: Path(p).expanduser().resolve(),
                                          (bundle, study_path, destination))
    if destination.exists() or any((p/'.git').exists() for p in (destination, *destination.parents)):
        raise ValueError('Choose a new private qualification directory outside Git')
    manifest_bytes = (bundle/'native-shell.json').read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = json.loads(manifest_bytes)
    study = json.loads(study_path.read_text())
    if (file_hash(study_path) != STUDY or study['uil_sha256'] != CANONICAL_UIL or
        digest(manifest['program']) != CANONICAL_UIL or manifest['module_uil_sha256'] != CANONICAL_UIL or
        manifest['module_udl_sha256'] != UDL or digest({**manifest['program'], 'role': 'udl'}) != UDL):
        raise ValueError('Qualified study or canonical UDL/UIL identity differs')
    if manifest.get('stage') != 'compiled' or manifest.get('platform') not in ('windows-x86', 'windows-x86-16', 'windows-x64', 'linux-x64'):
        raise ValueError('A sealed native desktop build is required')
    for field in ('application', 'probe'):
        name = manifest[field]
        if Path(name).name != name or file_hash(bundle/name) != manifest['artifacts'][name]:
            raise ValueError('Native executable artifact identity differs')
        raw = (bundle/name).read_bytes()
        if manifest['platform'] == 'linux-x64':
            if raw[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', raw, 18)[0] != 62:
                raise ValueError('Expected little-endian x86-64 ELF')
        else:
            if raw[:2] != b'MZ' or len(raw) < 64:
                raise ValueError('Expected native Windows image')
            pe = struct.unpack_from('<I', raw, 60)[0]
            if manifest['platform']=='windows-x86-16':
                if raw[pe:pe+2]!=b'NE' or raw[pe+54]!=2 or struct.unpack_from('<H',raw,pe+12)[0]&0x8000:
                    raise ValueError('Expected Windows NE executable')
            else:
                machine,magic=(0x14c,0x10b) if manifest['platform']=='windows-x86' else (0x8664,0x20b)
                if raw[pe:pe+4]!=b'PE\0\0' or struct.unpack_from('<H',raw,pe+4)[0]!=machine or struct.unpack_from('<H',raw,pe+24)[0]!=magic:
                    raise ValueError('Expected matching Windows PE architecture')
    destination.mkdir(parents=True, mode=0o700)
    (destination/'selected-native-shell.json').write_bytes(manifest_bytes)
    runner_identity = {'type': 'local-process'}
    if runner_path is None:
        run = local_runner(bundle, destination)
    else:
        path = Path(runner_path).expanduser().resolve(strict=True)
        spec = importlib.util.spec_from_file_location('explicit_snake_desktop_runner', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        run = module.create_runner(bundle, destination)
        runner_identity = {'type': 'explicit-python-runner', 'source_sha256': file_hash(path)}
    functions = manifest['runtime']['function_order']
    keys = manifest['runtime']['key_order']
    controls = manifest['runtime']['region_controls']
    slot = next(i for i, value in enumerate(controls) if value['name'] == 'rng')
    variants = {value['name']: i for i, value in enumerate(controls[slot]['variants'])}
    if set(variants) != {'original', 'lfsr16'}:
        raise ValueError('Both exact and intentionally different RNG choices are required')
    state = study['layout']['state']; plan = manifest['plan']; frame = plan['frame']
    width, height = frame['width'], frame['height']
    initial = json.loads((bundle/'initial.json').read_text())
    services = study['initial_services']
    source_prefix = list(initial[:621])
    for name, value in services.items():
        source_prefix[state[name]] = value
    summary = {'format': 'fdisbull-snake-desktop-qualification-1', 'status': 'running',
        'platform': manifest['platform'], 'profile': manifest['profile'],
        'module_uil_sha256': CANONICAL_UIL, 'module_udl_sha256': UDL,
        'manifest_sha256': manifest_sha256, 'study_sha256': file_hash(study_path),
        'verifier_sha256': file_hash(__file__), 'runner': runner_identity,
        'application_sha256': manifest['artifacts'][manifest['application']],
        'probe_sha256': manifest['artifacts'][manifest['probe']],
        'cases': {}, 'core_carried': {}, 'adapters': {}, 'outcomes': {}, 'seed_probes': [], 'runs': [],
        'scope': 'Generated '+manifest['architecture']+' processes versus original-RNG DOS witnesses and explicitly different LFSR references; declared logical events, native responder paths and owned native surfaces; physical hardware and Microsoft Windows OS require separate evidence'}

    def execute(mode, commands, label, *, clock=services['last_tick']):
        incoming = encode_study(manifest, commands, clock=clock,
            x=services['mouse_x'], y=services['mouse_y'], buttons=0)
        output, receipt = run(bundle/manifest['application' if mode == 'ui' else 'probe'], incoming, label)
        rows = decode_study(manifest, output)
        if len(rows) != len(commands):
            raise AssertionError(label+' native command count differs')
        summary['runs'].append({'label': label, 'mode': mode,
            'input_sha256': hashlib.sha256(incoming).hexdigest(),
            'output_sha256': hashlib.sha256(output).hexdigest(), 'rows': len(rows)})
        return rows

    def start(choice, clock):
        return [command(SELECT, a=slot, b=variants[choice]),
            command(REPLACE, payload=list(source_prefix)), command(INITIALIZE, clock=clock)]

    def logical_event(event):
        payload = []
        for name in ('kind', 'ascii', 'scan', 'x', 'y', 'buttons', 'clock'):
            payload.extend([plan['events'][name], event.get(name, 0)])
        return command(CALL, a=functions.index(plan['events']['function']), b=1, payload=payload)

    def ui_event(event, buttons):
        kind = event['kind']
        if kind == plan['events']['keyboard_kind']:
            matches = [name for name, value in plan['keymap'].items()
                       if value == {'ascii': event['ascii'], 'scan': event['scan']}]
            if len(matches) != 1:
                raise ValueError('Source key does not have one declared native mapping')
            return command(KEY, a=keys.index(matches[0]), c=1, clock=event['clock']), buttons
        if kind == plan['events']['pointer_kind']:
            value = event['buttons']
            if value not in (0, 1) or buttons not in (0, 1):
                raise ValueError('Original pointer corpus exceeds its left-button scope')
            phase = 1 if value and not buttons else 2 if buttons and not value else 3 if value else 0
            return command(POINTER, a=phase, b=0, c=event['x'], d=event['y'], clock=event['clock']), value
        if kind == plan['events']['clock_kind']:
            return command(CLOCK, clock=event['clock']), buttons
        raise ValueError('Unknown normalized original event')

    def compare(actual, expected, label, *, native_view=False):
        words = actual['words']
        same(list(words[:len(expected['expected_state'])]), expected['expected_state'], label+' state')
        indexed = bytes(list(words[frame['offset']:frame['offset']+width*height]))
        pixels = base64.b64decode(study['raster_data'][expected['frame']['sha256']])
        same(indexed, pixels, label+' indexed raster')
        colors = rgba(pixels, frame['palette'])
        if actual.get('frame_rgba') != colors:
            raise AssertionError(label+' complete palette RGBA differs')
        if native_view and actual.get('view_rgba') != colors:
            raise AssertionError(label+' complete intrinsic native surface RGBA differs')
        return {'id': expected['id'],
            'state_sha256': hashlib.sha256(struct.pack('<621I', *words[:621])).hexdigest(),
            'indexed_sha256': hashlib.sha256(indexed).hexdigest(),
            'frame_rgba_sha256': hashlib.sha256(colors).hexdigest(),
            **({'native_view_rgba_sha256': hashlib.sha256(actual['view_rgba']).hexdigest()} if native_view else {})}

    try:
        for choice, cases, expected_key in [('original', study['cases'], 'original'),
                                             ('lfsr16', study['rng']['cases'], 'alternate')]:
            hashes, changed, invocations = [], 0, 0
            for batch in range(0, len(cases), 64):
                commands = [command(SELECT, a=slot, b=variants[choice])]
                indexes = []
                for item in cases[batch:batch+64]:
                    prefix = [0]*621
                    cells = item['initial'].get('all_cells', item['initial']['cells'])
                    prefix[:len(cells)] = cells
                    for name in SCALARS:
                        prefix[state[name]] = item['initial'][name]
                    commands.append(command(REPLACE, payload=prefix))
                    commands.append(command(CALL, a=functions.index('step'), b=0))
                    indexes.append(len(commands)-1)
                commands.append(command(CLOSE))
                observed = execute('core', commands, 'cases-'+choice+'-'+str(batch//64))
                invocations += observed[-2]['region_counts']['rng'][choice]
                for item, index in zip(cases[batch:batch+64], indexes):
                    words = observed[index]['words']; expected = item[expected_key]
                    same(list(words[:600]), expected['all_cells'], item['id']+' body')
                    for name in SCALARS:
                        if words[state[name]] != expected[name]:
                            raise AssertionError(choice+' '+item['id']+' '+name+' differs')
                    changed += choice == 'lfsr16' and expected['rng_seed'] != item['original']['rng_seed']
                    hashes.append(hashlib.sha256(struct.pack('<614I', *words[:614])).hexdigest())
                if not observed[-1]['closed']:
                    raise AssertionError('Core study did not close')
            summary['cases'][choice] = {'cases': len(cases), 'mismatches': 0,
                'intentionally_changed_cases': changed, 'compared_state_words': 614, 'region_invocations': invocations,
                'projection_sha256': digest(hashes)}
            if choice == 'lfsr16' and changed != 84:
                raise AssertionError('Alternative negative control did not distinguish84cases')

        expected_views = {}
        for mode in ('core', 'ui'):
            for choice, source_rows in [('original', study['observations']),
                                        ('lfsr16', study['rng']['alternate_observations'])]:
                commands = start(choice, services['last_tick'])
                views = []
                if mode == 'ui':
                    for name, size in [('two-times', (width*2, height*2)), ('wide', (800, 600)), ('tall', (600, 800))]:
                        commands.append(command(RESIZE, a=size[0], b=size[1]))
                        commands.append(command(SNAPSHOT, flags=VIEW))
                        views.append((name, size, len(commands)-1))
                    commands.append(command(RESIZE, a=width, b=height))
                indexes, buttons, events, interventions, seen_keys, pointer_commands, clocks = [], 0, 0, 0, set(), 0, []
                for source in source_rows:
                    if source.get('intervention'):
                        if source['intervention']['kind'] != 'declared-original-ram-state':
                            raise ValueError('Unknown original RAM intervention')
                        commands.append(command(REPLACE, payload=source['intervention']['words']))
                        interventions += 1
                    for event in source['events']:
                        if mode == 'ui':
                            native, buttons = ui_event(event, buttons)
                            commands.append(native)
                            if native['kind'] == KEY: seen_keys.add(keys[native['a']])
                            if native['kind'] == POINTER: pointer_commands += 1
                            if native['kind'] == CLOCK: clocks.append(native['clock'])
                        else:
                            commands.append(logical_event(event))
                        events += 1
                    commands.append(command(SNAPSHOT, flags=FRAME | (VIEW if mode == 'ui' else 0)))
                    indexes.append(len(commands)-1)
                observed = execute(mode, commands, mode+'-carried-'+choice)
                comparisons = [compare(observed[index], row, mode+' '+choice+' '+row['id'], native_view=mode == 'ui')
                               for index, row in zip(indexes, source_rows)]
                checks = []
                if mode == 'ui':
                    pixels = base64.b64decode(study['raster_data'][source_rows[0]['frame']['sha256']])
                    for name, size, index in views:
                        if size not in expected_views:
                            expected_views[size] = fitted_view(pixels, frame['palette'], width, height, *size)
                        expected, rectangle = expected_views[size]
                        if observed[index]['view_rgba'] != expected:
                            same(observed[index]['view_rgba'], expected, choice+' '+name+' exact native viewport')
                        checks.append({'name': name, 'size': list(size), 'integer_fit_rectangle': rectangle,
                            'rgba_sha256': hashlib.sha256(expected).hexdigest(), 'exact_bytes': True})
                    if seen_keys != set(keys):
                        raise AssertionError('Native original corpus did not cover every declared key')
                if not observed[-1]['closed']:
                    raise AssertionError('Esc did not preserve a final snapshot and close')
                arm = {'observations': comparisons, 'normalized_events': events,
                    'declared_ram_interventions': interventions, 'ordinary_answer_resets': 0,
                    'complete_state_words': 621, 'complete_indexed_pixels': width*height,
                    'closed': observed[-1]['closed'], 'view_checks': checks}
                if mode == 'ui':
                    arm['event_coverage'] = {'key_commands': sum(c['kind'] == KEY for c in commands),
                        'declared_keys': sorted(seen_keys), 'pointer_commands': pointer_commands,
                        'clock_commands': clocks}
                summary['adapters' if mode == 'ui' else 'core_carried'][choice] = arm

        for choice in ('original', 'lfsr16', 'hot_swap'):
            commands = [command(RESIZE, a=width, b=height),
                *start('original' if choice == 'hot_swap' else choice, 100)]
            indexes, buttons, selection_index = [], 0, None
            for number, source in enumerate(study['rng']['outcome'][choice], 1):
                if choice == 'hot_swap' and number == 5:
                    commands.append(command(SELECT, a=slot, b=variants['lfsr16']))
                    selection_index = len(commands)-1
                for event in source['events']:
                    native, buttons = ui_event(event, buttons)
                    commands.append(native)
                commands.append(command(SNAPSHOT, flags=FRAME | VIEW))
                indexes.append(len(commands)-1)
            commands.append(command(CLOSE))
            observed = execute('ui', commands, 'native-route-'+choice, clock=100)
            comparisons = []
            for index, source in zip(indexes, study['rng']['outcome'][choice]):
                row = observed[index]; words = row['words']
                comparisons.append({**compare(row, source, choice+' '+source['id'], native_view=True),
                    **{name: words[state[name]] for name in ('snake_length', 'score', 'rng_seed', 'food_cell', 'game_status')},
                    'head': words[0]})
            if selection_index is not None:
                before, after = observed[selection_index-1], observed[selection_index]
                same(before['words'], after['words'], 'Natural selector must preserve all state')
                if before['revision'] != after['revision'] or before['words'][state['rng_seed']] != 10589 or before['words'][state['food_cell']] != 389:
                    raise AssertionError('Natural selector changed revision/current seed/current food')
                if comparisons[22]['rng_seed'] != 41134 or comparisons[22]['food_cell'] != 334:
                    raise AssertionError('Natural switch did not consume the retained seed')
            counts = observed[indexes[-1]]['region_counts']['rng']
            if choice == 'hot_swap' and counts != {'original': 1, 'lfsr16': 1}:
                raise AssertionError('Natural switch did not invoke each selected region once')
            same(observed[-1]['words'], observed[indexes[-1]]['words'], 'Owned final state must survive teardown')
            if not observed[-1]['closed']:
                raise AssertionError('Route process did not close')
            summary['outcomes'][choice] = {'observations': comparisons, 'region_invocations': counts,
                'board_or_seed_interventions': 0, 'selector_preserved_all_words': selection_index is not None}

        commands, indexes = [], []
        for choice in ('original', 'lfsr16'):
            commands.append(command(SELECT, a=slot, b=variants[choice]))
            for transition in study['rng']['transitions']:
                prefix = list(source_prefix); prefix[state['rng_seed']] = transition['before']
                commands.append(command(REPLACE, payload=prefix)); before = len(commands)-1
                commands.append(command(CALL, a=functions.index('rng'), b=0))
                indexes.append((choice, transition, before, len(commands)-1))
        commands.append(command(CLOSE))
        observed = execute('core', commands, 'seed-footprints')
        for choice, transition, before, after in indexes:
            expected = transition['original_next' if choice == 'original' else 'alternate_next']
            old, new = list(observed[before]['words']), list(observed[after]['words'])
            if new[state['rng_seed']] != expected:
                raise AssertionError('Selected generator seed transition differs')
            new[state['rng_seed']] = old[state['rng_seed']]
            same(new, old, 'One-word selected RNG footprint')
            if observed[after]['region_counts']['rng'][choice] != observed[before]['region_counts']['rng'][choice]+1:
                raise AssertionError('Selected RNG invocation counter differs')
            summary['seed_probes'].append({'choice': choice, 'before': transition['before'], 'after': expected})

        invalid = list(source_prefix); invalid[1] = invalid[0]
        commands = start('original', services['last_tick']) + [command(SNAPSHOT),
            command(CALL, a=functions.index('step'), b=0, flags=EXPECT_REFUSAL, payload=[study['layout']['font'], 0]),
            command(SNAPSHOT), command(REPLACE, flags=EXPECT_REFUSAL, payload=invalid),
            command(SNAPSHOT), command(CLOSE), command(SELECT, a=slot, b=variants['original'], flags=EXPECT_REFUSAL)]
        observed = execute('core', commands, 'guard-and-terminal-refusals')
        baseline = observed[3]
        for row in observed[4:8]:
            same(row['words'], baseline['words'], 'Refused operation must preserve committed state')
            if row['revision'] != baseline['revision']:
                raise AssertionError('Refused operation changed revision')
        if observed[4]['committed'] or observed[6]['committed'] or not observed[-1]['closed']:
            raise AssertionError('Refusal or terminal-close contract differs')
        summary['guard_refusals'] = ['immutable-input-patch', 'invalid-active-body', 'unchanged-state-and-revision', 'closed-owner-mutation']
        if (bundle/'native-shell.json').read_bytes() != manifest_bytes:
            raise AssertionError('Selected native manifest changed during qualification')
        if file_hash(study_path) != STUDY or any(file_hash(bundle/manifest[field]) != manifest['artifacts'][manifest[field]] for field in ('application', 'probe')):
            raise AssertionError('Selected study or native executable changed during qualification')
        summary['selected_artifacts_unchanged'] = True
        summary['status'] = 'passed'
        summary['checks'] = ['original-and-alternate-342-kernel-cases', 'original-and-alternate-69-core-and-native-ui-observations',
            'complete621-word-and64000-pixel-comparisons', 'native-original-14-key-and-left-button-timer-paths',
            'exact-intrinsic-wide-tall-and-integer2x-native-surfaces', 'native-original-alternate-and-natural-hot-swap-routes',
            'one-word-seed-footprints', 'guarded-rollback-and-owned-terminal-snapshot']
    except Exception as error:
        summary.update(status='failed', error=str(error))
        (destination/'verification.json').write_text(json.dumps(summary, indent=2)+'\n')
        raise
    (destination/'verification.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    parser.add_argument('study', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--runner', type=Path, help='Explicit Python module exposing create_runner(bundle,destination)')
    args = parser.parse_args()
    report = verify(args.bundle, args.study, args.destination, runner_path=args.runner)
    print(json.dumps({'status': report['status'], 'platform': report['platform'], 'cases': report['cases'],
        'core_carried': {k: len(v['observations']) for k, v in report['core_carried'].items()},
        'adapters': {k: len(v['observations']) for k, v in report['adapters'].items()},
        'routes': {k: len(v['observations']) for k, v in report['outcomes'].items()}}))
