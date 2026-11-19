"""Real IRQ1 state drives passive scene true/false/true and restore invalidation."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib

import pytest

from fdisbull.project import Project
from fdisbull.scenes import SceneError
from support.observed_movement_fixture import movement_guest
from test_qemu_clock_budget_native import clock_runtime, clock_disk
from test_qemu_dos_process_native import launch_options, process_record, com_address
from test_qemu_dos_le_checkpoint_native import _checkpoint_tool


def definition():
    context=dict(state='authored IRQ1 key released',triggers=['real IRQ1 make/break handlers'])
    return dict(format='fdisbull-scene-2',observation_profile=dict(kind='runtime-memory',version=1),
        context=context,match={'runtime_memory':dict(binding='scene-state',offset=8,length=1,hex='00')},
        objects=[dict(name='actor',context=context,visible={'constant':True},ready={'constant':True},
            enabled={'constant':True},outcome={'constant':False})])


@contextmanager
def launch(tmp_path,runtime,disk):
    code,symbols=movement_guest(tmp_path,runtime['nasm']);binary=tmp_path/'SCENE.COM';binary.write_bytes(code)
    options=launch_options(runtime,disk,qemu_clock='virtual',qemu_checkpoint_tool=str(_checkpoint_tool()))
    with Project.create(tmp_path/'scene.fdb',binary,image='com') as project:
        project.analyze(start=hex(project.regions(1)[0].start+symbols['ready']-0x100),max_instructions=1)
        with project.debugger(runtime['executable'],tmp_path,**options) as debug:
            info=process_record(debug);address=com_address(info,symbols['state'])
            point=debug.breakpoint(com_address(info,symbols['ready']))
            assert debug.run(timeout_ms=10000)['outcome']=='breakpoint'
            debug.delete_breakpoint(point['breakpoint_id'])
            bind=lambda:debug.bind_runtime_memory('scene-state',address,length=29,expected_hex=b'MV01'.hex(),
                provenance=dict(fixture='actual IRQ1 COM state',sha256=hashlib.sha256(code).hexdigest()),space='physical')
            bound=bind();saved=project.debug_save_scene('released',definition())
            yield project,debug,bind,bound,saved
            native=debug.vm.process
        assert native.poll() is not None


def passive(debug,operation):
    before=debug.clock_observe();inputs=deepcopy(debug.input_state());process=deepcopy(debug._process)
    peer=debug.vm.gdb;original=peer.execute
    def forbidden(*args,**kwargs):pytest.fail('Passive scene check attempted native execution')
    peer.execute=forbidden
    try:result=operation()
    finally:peer.execute=original
    after=debug.clock_observe()
    assert (after['epoch'],after['virtual_ns'],after['counter'])==(before['epoch'],before['virtual_ns'],before['counter'])
    assert debug.input_state()==inputs and debug._process==process
    clock=result['observation_context']['clock']
    if result['capture_context_verified']:
        assert (clock['before']['epoch'],clock['before']['virtual_ns'],clock['before']['counter'])==(clock['after']['epoch'],clock['after']['virtual_ns'],clock['after']['counter'])
    else:
        assert clock['after'] is None and result['status']=='unavailable' and not result['complete']
    assert 'frame' not in result
    return result


def test_native_physical_make_break_produces_true_false_true_without_scene_execution(tmp_path,clock_runtime,clock_disk):
    with launch(tmp_path,clock_runtime,clock_disk) as (project,debug,bind,bound,saved):
        assert debug.capabilities['runtime_scene_observation']
        first=passive(debug,lambda:debug.scene_assert('released',object='actor'))
        assert first['status']=='matched'
        held=debug.keyboard_key_down('a');debug.input_schedule(1)
        debug._clock_advance_with_hooks(100000000,timeout_ms=5000)
        assert debug.runtime_memory(bound['id'],offset=8,length=1)['hex']=='01'
        second=passive(debug,lambda:debug.scene_check('released',object='actor'))
        assert second['status']=='mismatch' and second['complete']
        with pytest.raises(SceneError) as error:debug.scene_assert('released',object='actor')
        assert error.value.result['status']=='mismatch' and error.value.result['observation']
        debug.keyboard_key_up(held['lease']);debug.input_schedule(1)
        debug._clock_advance_with_hooks(150000000,timeout_ms=5000)
        third=passive(debug,lambda:debug.scene_check(saved['id'],object='actor'))
        assert third['status']=='matched'
        ledger=bytes.fromhex(debug.runtime_memory(bound['id'],offset=10,length=5)['hex'])
        assert ledger==bytes([1,1,2,0x1e,0x9e]) and not debug._input_pending()
        result=debug.script(dict(format='fdisbull-script-1',backend='qemu-dos',steps=[
            dict(op='scene-check',scene='released',**{'as':'scene'}),
            dict(op='scene-assert',scene='$scene.scene_revision',compact=True),
            dict(op='assert',value='$scene.status',equals='matched')]))
        assert result['ok'],result
        for observation in (first,second,third):
            assert project.debug_scene_observation(observation['observation'])['result']==observation


def test_native_restore_never_resurrects_stored_scene_binding(tmp_path,clock_runtime,clock_disk):
    with launch(tmp_path,clock_runtime,clock_disk) as (project,debug,bind,bound,scene):
        before=passive(debug,lambda:debug.scene_check('released'))
        saved=debug.save_machine_state()
        owner,epoch=debug.vm,debug._runtime_epoch
        restored=debug.load_machine_state(saved['artifact'])
        assert debug.vm is not owner and owner.process.poll() is not None and debug._runtime_epoch!=epoch
        assert restored['machine_state_restored'] and not restored['source_binding_restored']
        stale=passive(debug,lambda:debug.scene_check('released'))
        assert stale['status']=='unavailable' and not stale['complete']
        assert not debug._runtime_bindings
        fresh=bind();assert fresh['id']!=bound['id']
        after=passive(debug,lambda:debug.scene_assert('released'))
        assert after['status']=='matched' and after['observation_context']['capture_epoch']!=before['observation_context']['capture_epoch']
        assert not debug._process['source_mapping']['live']
        assert project.debug_scene_info(scene['id'])==scene
