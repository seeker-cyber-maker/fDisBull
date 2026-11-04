"""Source-bound SNES task-list reset and guarded root-task creation."""
import hashlib
from pathlib import Path

from .game_il import GameMachine, author_program
from .shadowrun_snes_field import ROM_SHA256
from .shadowrun_snes_script import SOURCE as VM_SOURCE

SOURCE = Path(__file__).parent / 'game_sources/shadowrun_snes_task_init.c'


def task_init_machine(rom):
    """Create a fresh task-construction model bound to the qualified ROM.

    Reset and task creation are explicit calls. The caller supplies each source
    script ID and its real direct-page argument bytes; no source checkpoint is
    used to construct future task state. Nested tasks and scene creation are
    separate edges.
    """
    if len(rom) != 1048576 or hashlib.sha256(rom).hexdigest() != ROM_SHA256:
        raise ValueError('wrong SNES source')
    vm, init = VM_SOURCE.read_bytes(), SOURCE.read_bytes()
    program = author_program((vm + b'\n' + init).decode(),
        [{'id': 0, 'length': len(rom), 'sha256': ROM_SHA256}],
        evidence={'kind': 'source-task-reset-and-root-construction',
                  'source_sha256': ROM_SHA256,
                  'source_range': '80:C176-C199,80:C212-C28C,80:C298-C335',
                  'authoring_sha256': hashlib.sha256(vm + b'\n' + init).hexdigest(),
                  'scope': 'guarded task-list reset, heap allocation and root task creation; scene and nested tasks excluded'})
    result = GameMachine(program, {0: rom})
    if VM_SOURCE.read_bytes() != vm or SOURCE.read_bytes() != init:
        raise ValueError('task initialization source changed')
    return result
