"""Independent DOSBox-X oracle for Doom's protected-mode level-time increment."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from time import monotonic

from fdisbull.le import load_runtime_le_carrier
from fdisbull.project import Project
from fdisbull.qemu_dos_le_match import SourceMatchError, match


CODE_OFFSET = 0x33120
DATA_OFFSET = 0x2D354


def read(debug, space, offset, length, selector=None):
    address = dict(space=space, offset=f'0x{offset:08x}')
    if selector is not None:
        address['segment'] = f'0x{selector:04x}'
    reply = debug.call('memory.read', {'address': address, 'length': length})
    raw = base64.b64decode(reply['data_base64'], validate=True)
    assert len(raw) == length
    return raw


def placement(debug, image):
    regs = debug.registers()
    context = regs.get('address_context', {})
    cs, ip = int(regs['cs'], 16), int(regs['ip'], 16)
    if (regs['cpu_mode'] != 'protected' or regs['code_bits'] != 32
            or context['paging_enabled'] or not context['a20_enabled']
            or not (cs & ~7) or cs & 4):
        return None
    diagnostic = debug.call('debugger.execute_command', {'command': 'CPU'})
    base_limit = re.findall(r'GDT base=([0-9a-fA-F]{8}) limit=([0-9a-fA-F]{8})', diagnostic['raw_output'])
    assert len(base_limit) == 1
    base, limit = (int(value, 16) for value in base_limit[0])
    assert 7 <= limit <= 65535

    def linear(address, length):
        raw = read(debug, 'linear', address, length)
        assert raw == read(debug, 'physical', address, length)
        return raw

    gdt = linear(base, limit + 1)
    row = gdt[cs & ~7:(cs & ~7) + 8]
    if len(row) != 8 or row[5] & 0x98 != 0x98 or not row[6] & 0x40:
        return None
    cs_base = int.from_bytes(row[2:4], 'little') | row[4] << 16 | row[7] << 24
    cs_limit = int.from_bytes(row[:2], 'little') | (row[6] & 15) << 16
    if row[6] & 0x80:
        cs_limit = cs_limit << 12 | 0xfff
    if ip + 95 > cs_limit:
        return None
    assert read(debug, 'segmented', ip, 96, cs) == linear(cs_base + ip, 96)
    cpu = dict(mode='protected', bits=32, cs=cs, ip=ip, cs_base=cs_base, cs_limit=cs_limit,
               cs_attributes=(row[5] << 8) | ((row[6] & 0xf0) << 16))
    proof = match(image, cpu, gdt, linear)
    if proof is None:
        return None
    assert debug.registers() == regs and linear(base, limit + 1) == gdt
    ident = proof['identity_evidence']
    assert ident['code_object'] == 1
    code = ident['runtime_code_base'] + CODE_OFFSET
    target = next(p['runtime_base'] for p in ident['object_proofs'] if p['object_index'] == 3) + DATA_OFFSET
    assert 0 <= code - cs_base <= cs_limit - 5
    runtime_bytes = linear(code, 6)
    assert runtime_bytes == read(debug, 'segmented', code - cs_base, 6, cs)
    assert runtime_bytes[:2].hex() == 'ff05' and int.from_bytes(runtime_bytes[2:], 'little') == target
    return dict(cs=cs, ip=ip, cs_base=cs_base, cs_limit=cs_limit, descriptor_hex=row.hex(),
                gdt_sha256=hashlib.sha256(gdt).hexdigest(), runtime_address=code,
                runtime_target=target, runtime_bytes=runtime_bytes.hex())


def reach_site(debug, image):
    deadline = monotonic() + 90
    for _ in range(55):
        start = debug.call('execution.timing')['guest_ticks']
        op = debug.call('execution.continue')
        while monotonic() < deadline:
            stop = debug.call('execution.wait', dict(operation_id=op['operation_id'], timeout_ms=20))
            assert stop.get('running'), stop
            if debug.call('execution.timing')['guest_ticks'] >= start + 1000:
                pause = debug.call('execution.pause')
                stop = debug.call('execution.wait', dict(operation_id=pause['operation_id'], timeout_ms=3000))
                assert stop['stop_reason']['kind'] == 'pause'
                break
        else:
            raise TimeoutError('DOSBox did not reach an eligible protected stop')
        try:
            site = placement(debug, image)
        except SourceMatchError as exc:
            if str(exc) != 'ambiguous source placement within one object':
                raise
            continue
        if site:
            break
    else:
        raise AssertionError('Doom never exposed an unambiguous protected-mode placement')
    bp = debug.call('breakpoints.create', dict(kind='execution', once=True, address=dict(
        space='segmented', segment=f"0x{site['cs']:04x}", offset=f"0x{site['runtime_address']-site['cs_base']:08x}")))
    op = debug.call('execution.continue')
    while monotonic() < deadline:
        stop = debug.call('execution.wait', dict(operation_id=op['operation_id'], timeout_ms=100))
        if not stop.get('running'):
            assert stop['stop_reason']['breakpoint_id'] == bp['breakpoint_id'], stop
            return
    raise TimeoutError('Doom never executed the selected offset32 site')


def run(stage, phase):
    if phase not in ('hot', 'cold'):
        raise ValueError('Expected hot or cold')
    game = stage / 'game'
    source = Path(os.environ['FDISBULL_DOOM_LE_SOURCE'])
    native = Path(os.environ['FDISBULL_DOSBOX']).resolve(strict=True)
    database = stage / 'doom.fdb'
    hot_file = stage / 'dosbox-hot.json'
    if phase == 'hot':
        game.mkdir(parents=True)
        for name in ('DOOM.EXE', 'DOOM.WAD', 'DEFAULT.CFG', 'AUD512.LMP'):
            shutil.copyfile(source / name, game / name)
    image = load_runtime_le_carrier((game / 'DOOM.EXE').read_bytes())
    meta = image.metadata['le']
    fixup, = [f for f in meta['fixups'] if f['source_object'] == 1 and f['source_offset'] == CODE_OFFSET + 2]
    assert (fixup['source_type'], fixup['width'], fixup['target_object'], fixup['target_offset']) == ('offset32', 4, 3, DATA_OFFSET)
    obj = next(o for o in meta['objects'] if o['index'] == 1)
    region = next(r for r in image.regions if r.start == obj['virtual_address'])
    owners = []
    with (Project.create(database, game / 'DOOM.EXE', image='mz') if phase == 'hot' else Project(database)) as project:
        with project.debugger(str(native), game, _on_spawn=owners.append) as debug:
            if phase == 'hot':
                reach_site(debug, image)
                state_id = debug.save_state('doom-le.sav')['artifact']
            else:
                original = json.loads(hot_file.read_text())
                state_id = original['state_artifact']
                debug.load_state(state_id)
            site = placement(debug, image)
            assert site and site['cs_base'] + site['ip'] == site['runtime_address']
            result = dict(**site, object_index=1, object_offset=CODE_OFFSET,
                          source_sha256=image.metadata['source_sha256'],
                          preferred_address=region.start + CODE_OFFSET,
                          canonical_bytes=region.data[CODE_OFFSET:CODE_OFFSET+6].hex(),
                          target_object=3, target_offset=DATA_OFFSET,
                          fixup_record_file_offset=fixup['record_file_offset'],
                          state_artifact=state_id, producer_sha256=debug.metadata['emulator_sha256'])
    assert owners and all(p.poll() == 0 for p in owners)
    if phase == 'cold':
        assert result == original
    (stage / ('dosbox-' + phase + '.json')).write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    run(Path(sys.argv[1]), sys.argv[2])
