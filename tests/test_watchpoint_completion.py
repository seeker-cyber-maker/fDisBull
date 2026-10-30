"""Whole REP completion must not be inferred from a native data watch."""
import os
from pathlib import Path

import pytest

from fdisbull.project import Project
from test_dos_loader import mz_file


@pytest.mark.parametrize('count,partial',[(4,False),(8192,True)])
def test_real_rep_watch_reports_access_without_claiming_whole_completion(tmp_path,count,partial):
    backend=os.environ.get('FDISBULL_DOSBOX')
    if not backend:
        pytest.skip('Set FDISBULL_DOSBOX for actual REP watchpoint qualification')
    module=bytearray(0xd000)
    # DS=ES=CS, source=0100, destination=8100, CLD; REP MOVSW; NOP/loop.
    module[:19]=bytes.fromhex('0e1f0e07be0001bf0081b90000fcf3a590ebfd')
    module[11:13]=count.to_bytes(2,'little')
    module[0x100:0x108]=bytes.fromhex('1122334455667788')
    program=tmp_path/'REP.EXE';original=mz_file(bytes(module),ss=0,sp=0xd000)
    program.write_bytes(original)
    database=tmp_path/'private.fdb'
    with Project.create(database,program) as project:
        project.analyze(max_instructions=20)
        with project.debugger(Path(backend).resolve(strict=True),tmp_path) as session:
            session.breakpoint('1000:8100',access='w')
            stopped=session.run(timeout_ms=5000)
            registers=session.registers()
            remaining=int(registers['general']['ecx'],16)
            pc=int(registers['instruction_pointer'],16)
            assert stopped['stop']['trigger']=='watchpoint'
            copied=count-remaining
            prefix=bytes.fromhex('1122334455667788')[:min(copied,4)*2]
            assert session.memory('1000:8100',length=8)['hex']==prefix.ljust(8,b'\0').hex()
            assert int(registers['general']['esi'],16)==0x100+copied*2
            assert int(registers['general']['edi'],16)==0x8100+copied*2
            if partial:
                assert 0<remaining<count and pc==0x0e
            else:
                assert remaining==0 and pc==0x10
            # The same native access hook does not certify whole-instruction
            # completion. Raw PC/count remain available for a qualified claim.
            assert stopped['stop']['instruction_completed'] is None
            assert stopped['stop']['registers_stage']=='after-access'
            assert stopped['stop']['causing_instruction']==stopped['session']['stop_reason']['data_access']['instruction']
            assert stopped['stop']['resume_pc']['offset']==registers['instruction_pointer']
    assert program.read_bytes()==original
