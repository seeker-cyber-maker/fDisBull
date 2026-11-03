"""Source-bound SNES task signaling and bounded whitelist interpreter."""
import hashlib
from pathlib import Path

from .game_il import GameMachine, author_program
from .shadowrun_snes_field import ROM_SHA256

SOURCE = Path(__file__).parent / 'game_sources/shadowrun_snes_script.c'
TASK_WORDS = 48
TASK_FIELDS = {'task_wait': 0x0bbe, 'task_link': 0x038e,
               'task_flags': 0x0c7e, 'task_delay': 0x0c1e}


def tasks_from_capture(rom, snapshot):
    """Seed task arrays once from qualified source and caller-owned WRAM.

    The interpreter recognizes a bounded subset; actor callbacks and source
    task scheduling require a caller-owned shared-state adapter.
    """
    if len(rom) != 1048576 or hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('wrong SNES source')
    if len(snapshot) != 131072:
        raise ValueError('128 KiB source WRAM required')
    raw = SOURCE.read_bytes()
    program = author_program(raw.decode(), [{'id': 0, 'length': len(rom), 'sha256': ROM_SHA256}], evidence={
        'kind': 'source-task-signal-and-readiness',
        'source_range': '80:C8C9-C8E2,80:C399-C3D0,80:C76C-C791,80:F342-F4F9',
        'source_sha256': ROM_SHA256,
        'snapshot_sha256': hashlib.sha256(snapshot).hexdigest(),
        'authoring_sha256': hashlib.sha256(raw).hexdigest(),
        'scope': 'bounded task signal, wait, coordinate setter and whitelist interpreter; callbacks require shared-state bridge'})
    machine = GameMachine(program, {0: rom})
    machine.set_state({name: [int.from_bytes(snapshot[base + i:base + i + 2], 'little')
                              for i in range(0, TASK_WORDS * 2, 2)]
                       for name, base in TASK_FIELDS.items()} | {
        'task_next': [int.from_bytes(snapshot[0x32e + i:0x330 + i], 'little')
                      for i in range(0, TASK_WORDS * 2, 2)],
        'task_list_head': int.from_bytes(snapshot[0x268:0x26a], 'little'),
        'task_list_free': int.from_bytes(snapshot[0x26a:0x26c], 'little'),
        'task_list_current': int.from_bytes(snapshot[0x26c:0x26e], 'little'),
        'task_callback': [int.from_bytes(snapshot[0x2ce + i:0x2d0 + i], 'little')
                          for i in range(0, TASK_WORDS * 2, 2)],
        'task_frame': [int.from_bytes(snapshot[0x26e + i:0x270 + i], 'little')
                       for i in range(0, TASK_WORDS * 2, 2)],
        'task_heap': list(snapshot[0x3f2:0xbbe]),
        'task_shared': list(snapshot[:65536]),
        'task_vm_resume': [
            (0 if int.from_bytes(snapshot[0x2ce+i:0x2d0+i], 'little') == 0 else
             1 if (int.from_bytes(snapshot[0x2ce+i:0x2d0+i], 'little') == 0xf4d2 and
                   int.from_bytes(snapshot[int.from_bytes(snapshot[0x26e+i:0x270+i], 'little')+9:
                                           int.from_bytes(snapshot[0x26e+i:0x270+i], 'little')+11], 'little') == 0x9e)
             else 2)
            for i in range(0, TASK_WORDS * 2, 2)]})
    if SOURCE.read_bytes() != raw:
        raise ValueError('task source changed')
    return machine
