"""Paired authored held-key progress and release: independent guest RAM oracle."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import os
from pathlib import Path

import pytest

from fdisbull.project import Project
from support.observed_movement_fixture import movement_guest
from test_qemu_clock_budget_native import clock_runtime, clock_disk
from test_qemu_dos_process_native import launch_options, process_record, com_address


def controls(project):
    return project.debug_define_macros(dict(format='fdisbull-macro-set-1',name='held-route',macros={
        'start':dict(steps=[dict(op='keyboard.key-down',key='a',**{'as':'down'})],outputs={'held':'$down.lease'}),
        'stop':dict(parameters={'lease':{'type':'input-lease'}},steps=[dict(op='keyboard.key-up',lease='$args.lease')])}))['id']


@contextmanager
def launch(tmp_path,runtime,disk,backend):
    code,symbols=movement_guest(tmp_path,runtime['nasm'])
    binary=tmp_path/'MOVE.COM';binary.write_bytes(code)
    if backend=='qemu':
        executable=runtime['executable'];options=launch_options(runtime,disk,qemu_clock='virtual')
    else:
        executable=os.environ.get('FDISBULL_DOSBOX_GAME_PARITY') or os.environ.get('FDISBULL_DOSBOX')
        if not executable:pytest.skip('Select the independent DOSBox runtime for paired movement')
        options={}
    before={str(p):hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (binary,runtime['boot_image'],Path(executable))}
    with Project.create(tmp_path/'move.fdb',binary,image='com') as project:
        project.analyze(start=hex(project.regions(1)[0].start+symbols['ready']-0x100),max_instructions=1)
        with project.debugger(executable,tmp_path,**options) as debug:
            if backend=='qemu':
                info=process_record(debug)
                address=lambda name:com_address(info,symbols[name])
                point=debug.breakpoint(address('ready'))
            else:
                address=lambda name:debug.runtime_load*16+symbols[name]
                point=debug.breakpoint(hex(project.regions(1)[0].start+symbols['ready']-0x100))
            assert debug.run(timeout_ms=10000)['outcome']=='breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            bound=debug.bind_runtime_memory('move-state',address('state'),length=29,
                expected_hex=b'MV01'.hex(),provenance=dict(fixture='authored IRQ1 and BIOS-tick COM',sha256=before[str(binary)]),space='physical')
            fields={name:{'runtime_memory':dict(binding=bound['id'],offset=symbols[name]-symbols['state'],
                type='u16' if name in ('position','ticks') else 'u8')}
                for name in ('position','ticks','held','settled','makes','breaks')}
            selected=dict(macro_set=controls(project),start=dict(name='start'),
                stop=dict(name='stop',args={'lease':'$start.outputs.held'}),observations=fields,
                until=dict(field='position',op='ge',value=3),settle=dict(field='settled',op='eq',value=1),
                progress=dict(fields=['position'],samples=8),guest_ms=1500,slice_ms=25,
                cleanup_guest_ms=500,max_polls=100,timeout_ms=15000)
            yield project,debug,symbols,address,bound,selected
            native=debug.vm.process if backend=='qemu' else None
        if native is not None:assert native.poll() is not None
    assert before=={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in before}


def state(debug,bound):
    raw=bytes.fromhex(debug.runtime_memory(bound['id'],offset=4,length=25)['hex'])
    return dict(position=int.from_bytes(raw[:2],'little'),ticks=int.from_bytes(raw[2:4],'little'),
        held=raw[4],settled=raw[5],makes=raw[6],breaks=raw[7],count=raw[8],edges=raw[9:25])


def advance(debug,backend,milliseconds):
    if backend=='qemu':return debug._clock_advance_with_hooks(milliseconds*1000000,timeout_ms=5000)
    return debug.run(guest_ms=milliseconds,timeout_ms=5000,fast_forward=True,stop_on_hook=True)


@pytest.mark.parametrize('backend',['qemu','dosbox'])
def test_authored_hold_progress_release_and_two_tick_settle(tmp_path,clock_runtime,clock_disk,backend):
    with launch(tmp_path,clock_runtime,clock_disk,backend) as (project,debug,symbols,address,bound,selected):
        before=state(debug,bound)
        advance(debug,backend,150)
        quiet=state(debug,bound)
        assert quiet['position']==before['position']==0 and quiet['ticks']-before['ticks']>=2
        result=debug.move(**selected)
        assert result['ok'] and result['complete'] and result['outcome']=='arrived',result
        assert result['cleanup']['settled'] and result['guest_elapsed_ms']>0
        final=state(debug,bound)
        assert final['position']>=3 and final['held']==0 and final['settled']==1
        assert final['makes']==final['breaks']==1 and final['count']==2 and final['edges'][:2]==b'\x1e\x9e'
        advance(debug,backend,150)
        later=state(debug,bound)
        assert later['position']==final['position'] and later['ticks']-final['ticks']>=2
        if backend=='qemu':assert not debug.input_state()['leases'] and not debug._input_pending()
        else:
            keyboard=debug.keyboard_state()['keyboard']
            assert keyboard['pending_events']==keyboard['owned_keys']==0


def test_native_first_irq_breakpoint_preserves_stop_without_release_or_resume(tmp_path,clock_runtime,clock_disk):
    with launch(tmp_path,clock_runtime,clock_disk,'qemu') as (_,debug,symbols,address,bound,selected):
        point=debug.breakpoint(address('irq_fence'))
        calls=[]
        peer=debug.vm.gdb
        original=peer.execute
        def execute(*args,**kwargs):calls.append(args);return original(*args,**kwargs)
        peer.execute=execute
        result=debug.move(**selected)
        assert not result['ok'] and result['outcome']=='stopped',result
        assert result['stop_result']['outcome']=='breakpoint'
        assert int(result['stop_result']['registers']['linear_pc'],16)==address('irq_fence')
        assert len(calls)==1 and not result['cleanup'].get('runs')
        assert not result['cleanup']['settled'] and debug.vm.process.poll() is not None


def test_native_caller_hold_remains_owned_after_movement_rejection(tmp_path,clock_runtime,clock_disk):
    with launch(tmp_path,clock_runtime,clock_disk,'qemu') as (_,debug,symbols,address,bound,selected):
        lease=debug.keyboard_key_down('a')['lease']
        debug.input_schedule(1)
        advance(debug,'qemu',100)
        before=deepcopy(debug.input_state())
        result=debug.move(**selected)
        assert result['outcome']=='initial_input_not_clear' and not result['cleanup']['attempted']
        assert debug.input_state()==before and lease in before['leases']
        held=state(debug,bound)
        assert held['held']==1 and held['settled']==0
        advance(debug,'qemu',150)
        assert state(debug,bound)['position']>held['position']
        debug.keyboard_key_up(lease)
        debug.input_schedule(1)
        advance(debug,'qemu',200)
        assert state(debug,bound)['held']==0 and state(debug,bound)['settled']==1
