"""VBE CPU bank selection remains independent of the active timed scanout."""
from hashlib import sha256
import json
import os
from pathlib import Path
import struct

import pytest

from fdisbull.project import Project
from support.dos_process_fixture import assemble, digest
from test_qemu_clock_budget_native import clock_disk, clock_runtime, park
from test_qemu_dos_process_native import com_address, launch_options, process_record
from test_qemu_dosbox_vga_modes_native import _DAC, _SOURCE
from test_qemu_vga_640_checkpoint_native import (
    DOSBOX_RGB, PROFILE, TIMING, clock_identity, expected_pixels, finish, logical, restore, source,
)
from test_qemu_vga_phase_checkpoint_native import _reach


_LAYOUT = 'vbe-banked-101'


def banked_source():
    original = 'banked:\n    cmp byte [advance],3\n'
    assert _SOURCE.count(original) == 1
    source = _SOURCE.replace(original, '''banked:
    cmp byte [advance],4
    je choose_three
    cmp byte [advance],3
''')
    assert source.count('\nbanked_page:\n') == 1
    source = source.replace('\nbanked_page:\n', '''
choose_three:
    mov ax,3
    call select_bank
bank_three:
    cmp byte [advance],5
    jne bank_three
    mov ax,4
    call select_bank
bank_four:
    jmp bank_four

select_bank:
    mul word [bank_step]
    mov dx,ax
    mov ax,4f05h
    xor bx,bx
    int 10h
    cmp ax,4fh
    jne banked_page.fault
    push cs
    pop ds
    ret

banked_page:
''')
    return source.replace("db 'VGA3'\ndw first,planar,banked,last,advance",
                          "db 'VBEB'\ndw first,planar,banked,bank_three,bank_four,advance")


def bank_snapshot(debug, bank, *, require_success=False):
    before = clock_identity(debug)
    regs = debug.registers()
    config = debug.vga_configuration_observe()['current']
    native = source(debug)
    raw = config['raw']
    assert raw['vbe'][5] == bank and raw['bank-offset'] == bank * 65536
    assert raw['vbe-start-address'] == 0 and raw['vbe-line-offset'] == 640
    assert native['state'] == 'observing' and native['scanout-layout'] == _LAYOUT
    aperture = debug.memory(0xa0000, length=32, space='physical')['hex']
    assert aperture == f'{bank+1:02x}' * 32
    if require_success:
        values = regs['registers']
        assert int(values.get('eax', values.get('rax')), 0) & 65535 == 0x004f
    assert clock_identity(debug) == before and debug.registers() == regs
    return dict(clock=before, config=config, native=native, aperture=aperture)


def compare_transition(previous, current, first_deadline):
    before, after = previous['native'], current['native']
    for key in ('token', 'epoch', 'stream-generation', 'frame-sequence', 'scanout-layout'):
        assert after[key] == before[key], key
    assert before['rows-sampled'] <= after['rows-sampled'] < 480
    assert after['next-deadline-ns'] == first_deadline + after['rows-sampled'] * TIMING[_LAYOUT][0]
    assert current['clock']['virtual_ns'] > previous['clock']['virtual_ns']
    assert current['config']['configuration_generation'] > previous['config']['configuration_generation']
    assert current['config']['raw']['vbe-start-address'] == previous['config']['raw']['vbe-start-address']


@pytest.mark.skipif(os.environ.get('FDISBULL_REQUIRE_QEMU_VGA_640_BANK') != '1',
                    reason='Select the exact native QEMU VBE bank switch witness')
def test_live_vbe_bios_bank_switch_preserves_partial_and_complete_scanout(tmp_path, clock_runtime, clock_disk):
    executable = clock_runtime['executable']
    tool = Path(os.environ['FDISBULL_QEMU_IMG']).resolve(strict=True)
    assert digest(executable) == os.environ['FDISBULL_QEMU_VGA_640_SHA256']
    assert digest(tool) == os.environ['FDISBULL_QEMU_VGA_640_IMG_SHA256']
    pattern = expected_pixels('banked')
    assert sha256(pattern).hexdigest() == DOSBOX_RGB[_LAYOUT]
    code = assemble(tmp_path, 'live-bank', banked_source()+'\ncolors: db '
                    + ','.join(str(value) for color in _DAC for value in color), clock_runtime['nasm'])
    assert code[-64:-60] == b'VBEB'
    entry, graphics, held, three, four, flag = struct.unpack('<6H', code[-60:-48])
    binary = tmp_path/'BANK.COM'
    binary.write_bytes(code)
    database = tmp_path/'bank.fdb'
    receipt = dict(qemu_sha256=digest(executable), qemu_img_sha256=digest(tool),
                   authored_com_sha256=digest(binary), completed=False)
    owners = {}

    def launch(project):
        return project.debugger(executable, tmp_path, **launch_options(
            clock_runtime, clock_disk, qemu_clock='virtual', qemu_retrace='precise',
            qemu_video_source_profile=PROFILE, qemu_checkpoint_tool=str(tool)))

    def resume(debug, from_bank_three, held_four, selector, first_deadline):
        debug.write_memory(selector, '05', expected_hex='04')
        park(debug, held_four)
        again = bank_snapshot(debug,4,require_success=True)
        compare_transition(from_bank_three,again,first_deadline)
        finished = finish(debug,_LAYOUT,first_deadline,pattern)
        return dict(bank_generation=again['config']['configuration_generation'],
                    bank_clock_ns=again['clock']['virtual_ns'],
                    source=logical(again['native']),future=finished)

    try:
        with Project.create(database,binary,image='com') as project:
            with launch(project) as debug:
                owners['first'] = debug.vm.process
                info = process_record(debug)
                entry, graphics, held, three, four, flag = (com_address(info, n) for n in
                                                             (entry,graphics,held,three,four,flag))
                park(debug,entry)
                debug.write_memory(flag,'01',expected_hex='00')
                park(debug,graphics)
                debug.write_memory(flag,'02',expected_hex='01')
                park(debug,held)
                native = debug.video_frame_start()['native']
                line, period = TIMING[_LAYOUT]
                first_deadline = native['next-deadline-ns']
                receipt['intact'] = finish(debug,_LAYOUT,first_deadline,pattern)
                first_deadline += period
                _reach(debug,first_deadline + 119*line + line//2)
                original = bank_snapshot(debug,4)
                assert original['native']['rows-sampled'] == 120
                debug.write_memory(flag,'04',expected_hex='02')
                park(debug,three)
                lower = bank_snapshot(debug,3,require_success=True)
                compare_transition(original,lower,first_deadline)
                assert logical(lower['native'])['frame'] == receipt['intact']['frame']
                receipt['before_bank_switch'] = original
                receipt['after_bank_switch'] = lower
                selection = debug.save_state('active-bank-three')
                receipt['checkpoint'] = selection['sha256']
                receipt['forward'] = resume(debug,lower,four,flag,first_deadline)
                owners['hot'] = restore(debug,selection['artifact'],lower['native'])
                restored = bank_snapshot(debug,3,require_success=True)
                assert restored['config']['raw'] == lower['config']['raw']
                assert restored['config']['configuration_generation'] == lower['config']['configuration_generation']
                receipt['hot'] = resume(debug,restored,four,flag,first_deadline)
                assert receipt['hot'] == receipt['forward']
        assert all(owner.poll() == 0 for owner in owners.values())
        receipt['completed'] = True
    finally:
        receipt['owners'] = {k:dict(pid=owner.pid,returncode=owner.poll()) for k,owner in owners.items()}
        assert binary.read_bytes() == code and digest(clock_disk['image']) == clock_disk['prepared_sha256']
        (tmp_path/'vbe-bank-replay.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
