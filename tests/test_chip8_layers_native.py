"""Authored actual-QEMU RAM/fetch-layer, hook and checkpoint witnesses."""
from contextlib import contextmanager
import os
import pytest
from fdisbull.dosbox_rpc import DebuggerError
from fdisbull.project import Project


def _inputs():
    binary=os.environ.get('FDISBULL_CHIP8_LAYERS_QEMU')
    tool=os.environ.get('FDISBULL_CHIP8_LAYERS_QEMU_IMG')
    if not binary or not tool:
        if os.environ.get('FDISBULL_REQUIRE_CHIP8_LAYERS')=='1':pytest.fail('CHIP-8 layer runtime and qemu-img required')
        pytest.skip('Set FDISBULL_CHIP8_LAYERS_QEMU and FDISBULL_CHIP8_LAYERS_QEMU_IMG')
    return binary,tool


@contextmanager
def _machine(tmp_path,words):
    binary,tool=_inputs();rom=tmp_path/'layers.ch8';source=bytes.fromhex(words);rom.write_bytes(source)
    with Project.create(tmp_path/'project.fdb',rom,arch='chip8') as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as debug:
            yield project,debug
    assert rom.read_bytes()==source


def _regs(d):return {k:int(v,16) for k,v in d.registers()['registers'].items()}


def _step(d,pc,**values):
    result=d.step(timeout_ms=5000);assert result['outcome']=='step',result
    registers=_regs(d);assert registers['pc']==pc
    for key,value in values.items():assert registers[key]==value,(key,registers)
    return result


def _layer(d,name,address,before,after,kind):
    return d.layer_patch(name,address,expected_hex=before,data_hex=after,kind=kind,activate=False)['layer']


def test_warmed_fetch_layers_stack_and_remove_without_changing_ram(tmp_path):
    with _machine(tmp_path,'6001 1200') as (_,d):
        _step(d,0x202,v0=1);_step(d,0x200)
        a=_layer(d,'two',0x201,'01','02','execute');b=_layer(d,'three',0x201,'01','03','execute')
        before=d.registers();d.layers([a]);assert d.registers()==before
        assert d.code(0x200,length=2,view='ram')['hex']=='6001'
        assert d.code(0x200,length=2,view='execute')['hex']=='6002'
        _step(d,0x202,v0=2);_step(d,0x200)
        d.layers([a,b]);_step(d,0x202,v0=3);_step(d,0x200)
        d.layers([a]);_step(d,0x202,v0=2);_step(d,0x200)
        d.layers([]);_step(d,0x202,v0=1)
        assert d.memory(0x200,length=2)['hex']=='6001' and d.chip8_environment()['rng-draws']==0


def test_fetch_view_overrides_ram_layer_and_each_reveals_its_base(tmp_path):
    with _machine(tmp_path,'6001 1200') as (_,d):
        ram=_layer(d,'RAM two',0x201,'01','02','ram')
        fetch=_layer(d,'fetch three',0x201,'01','03','execute')
        d.layers([ram,fetch])
        assert d.memory(0x200,length=2)['hex']=='6002'
        assert d.code(0x200,length=2,view='execute')['hex']=='6003'
        _step(d,0x202,v0=3);_step(d,0x200)
        d.layers([ram]);_step(d,0x202,v0=2);_step(d,0x200)
        d.layers([]);_step(d,0x202,v0=1)


def test_guest_changed_ram_layer_requires_explicit_keep_changed(tmp_path):
    with _machine(tmp_path,'6009 a300 f055 1206') as (_,d):
        ram=_layer(d,'initial seven',0x300,'00','07','ram');d.layers([ram])
        assert d.memory(0x300,length=1)['hex']=='07'
        _step(d,0x202,v0=9);_step(d,0x204,i=0x300);_step(d,0x206,i=0x301)
        before=d.layers();registers=d.registers()
        with pytest.raises(ValueError,match='conflict|changed'):d.layers([])
        assert d.layers()==before and d.registers()==registers
        assert d.memory(0x300,length=1)['hex']=='09'
        d.layers([],conflict='keep_changed')
        assert d.layers()['active']==[] and d.memory(0x300,length=1)['hex']=='09'


def test_native_transition_preflights_entire_batch_and_post_ram_guard(tmp_path):
    with _machine(tmp_path,'1200') as (_,d):
        before=d.vm.qmp.call('query-chip8-layers');env=d.chip8_environment();regs=d.registers();ram=d.memory(0,length=4096)
        base={'expected-generation':before['generation'],'expected-state-generation':env['state-generation']}
        bad=[{'ram':[{'address':0x300,'expected-hex':'00','data-hex':'11'},
                     {'address':0x1000,'expected-hex':'00','data-hex':'22'}],'execute':[]},
             {'ram':[{'address':0x300,'expected-hex':'00','data-hex':'11'}],
              'execute':[{'address':0x300,'expected-hex':'00','data-hex':'22'}]},
             {'ram':[{'address':0x300,'expected-hex':'00,11;769,00','data-hex':'22'}],'execute':[]},
             {'ram':[{'address':0x300,'expected-hex':'00','data-hex':'11;769,00,22'}],'execute':[]},
             {'ram':[],'execute':[{'address':0x300,'expected-hex':'00,11;769,00','data-hex':'22'}]},
             {'ram':[],'execute':[],'expected-generation':before['generation']+1}]
        for args in bad:
            with pytest.raises(DebuggerError):d.vm.qmp.call('x-chip8-configure-layers',base|args)
            assert d.registers()==regs and d.memory(0,length=4096)==ram and d.chip8_environment()==env
            assert d.vm.qmp.call('query-chip8-layers')==before


def test_guest_write_under_fetch_overlay_stops_before_stale_instruction(tmp_path):
    with _machine(tmp_path,'a209 6009 f055 1208 6001 1208') as (_,d):
        d.write_registers({'pc':{'expected':0x200,'value':0x208}})
        _step(d,0x20a,v0=1)
        d.write_registers({'pc':{'expected':0x20a,'value':0x200},'v0':{'expected':1,'value':0}})
        fetch=_layer(d,'future two',0x209,'01','02','execute');d.layers([fetch])
        stopped=d.run(timeout_ms=5000)
        assert stopped['outcome']=='layer_conflict',stopped
        assert _regs(d)['pc']==0x206 and _regs(d)['v0']==9 and _regs(d)['i']==0x20a
        assert d.memory(0x209,length=1)['hex']=='09' and not stopped['fault']['faulted']
        assert d.chip8_environment()['rng-draws']==0
        d.layers([]);_step(d,0x208);_step(d,0x20a,v0=9)


def test_repeating_hook_displaces_once_and_exhausts_at_exact_hit(tmp_path):
    with _machine(tmp_path,'7001 1200') as (_,d):
        h=d.hook(0x200,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':0}}}],once=False,max_hits=2)
        first=d.run(timeout_ms=5000,stop_on_hook=True)
        assert first['outcome']=='hook' and _regs(d)['v0']==0
        assert first['hook_hits'][0]['hit']==1 and d.hooks()['hooks'][0]['hook']==h['hook']
        second=d.run(timeout_ms=5000,stop_on_hook=True)
        assert second['outcome']=='hook' and _regs(d)['v0']==1
        assert second['hook_hits'][0]['hit']==2 and d.hooks()['hooks']==[]
        _step(d,0x202,v0=2)


def test_hook_applies_fetch_layer_without_hidden_instruction_or_rng_draw(tmp_path):
    with _machine(tmp_path,'7001 1200') as (_,d):
        d.chip8_seed_rng(123)
        fetch=_layer(d,'increment two',0x201,'01','02','execute')
        d.hook(0x200,actions=[{'op':'layers','layers':[fetch]}])
        stopped=d.run(timeout_ms=5000,stop_on_hook=True)
        assert stopped['outcome']=='hook' and _regs(d)['pc']==0x200 and _regs(d)['v0']==0
        assert d.code(0x200,length=2,view='execute')['hex']=='7002'
        assert d.memory(0x200,length=2)['hex']=='7001'
        assert (d.chip8_environment()['rng-state'],d.chip8_environment()['rng-draws'])==(123,0)
        _step(d,0x202,v0=2)


def test_user_breakpoint_collision_refuses_and_action_guard_failure_closes(tmp_path):
    with _machine(tmp_path,'7001 1200') as (_,d):
        point=d.breakpoint(0x200)
        with pytest.raises(ValueError):d.hook(0x200,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':1}}}])
        assert d.hooks()['hooks']==[]
        assert d.run(timeout_ms=5000)['outcome']=='breakpoint' and _regs(d)['i']==0
        d.delete_breakpoint(point['breakpoint_id'])
        d.hook(0x200,actions=[{'op':'registers','registers':{'v0':{'expected':1,'value':2}}}])
        with pytest.raises((DebuggerError,ValueError)):d.run(timeout_ms=5000,stop_on_hook=True)
        assert d.closed


def test_sticky_guest_fault_wins_over_same_pc_hook(tmp_path):
    with _machine(tmp_path,'ffff') as (_,d):
        assert d.step()['outcome']=='exception'
        d.hook(0x200,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':1}}}])
        result=d.run(timeout_ms=5000,stop_on_hook=True)
        assert result['outcome']=='exception' and _regs(d)['i']==0
        assert d.hooks()['hooks'][0]['hits']==0


def test_cold_restore_preserves_active_layers_hook_pending_rng_and_clock(tmp_path):
    binary,tool=_inputs();rom=tmp_path/'saved.ch8';source=bytes.fromhex('60ff f015 f018 c0ff 1206 120a');rom.write_bytes(source);path=tmp_path/'project.fdb'
    with Project.create(path,rom,arch='chip8') as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            _step(d,0x202,v0=255);_step(d,0x204);_step(d,0x206)
            d.chip8_seed_rng(123);d.chip8_keypad([0,15])
            d.write_registers({'pc':{'expected':0x206,'value':0x20a}})
            assert d.run(timeout_ms=50)['outcome']=='timeout'
            assert d.chip8_environment()['virtual-now-ns']>0
            d.write_registers({'pc':{'expected':0x20a,'value':0x206}})
            ram=_layer(d,'saved RAM',0x300,'00','7a','ram');fetch=_layer(d,'masked RNG',0x207,'ff','0f','execute');d.layers([ram,fetch])
            hook=d.hook(0x206,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':0}}}],once=False,max_hits=3)
            assert d.run(timeout_ms=5000,stop_on_hook=True)['hook_hits'][0]['hit']==1
            saved_env=d.chip8_environment();checkpoint=d.save_state(timeout_ms=30000)['artifact']
            _step(d,0x208,v0=8)
            future=d.run(timeout_ms=5000,stop_on_hook=True);assert future['hook_hits'][0]['hit']==2
            expected_regs=d.registers();expected_rng={k:d.chip8_environment()[k] for k in ('rng-seed','rng-state','rng-draws')}
    with Project(path) as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            old=d.vm.process;d.load_state(checkpoint,timeout_ms=30000);assert old.poll() is not None
            assert d.chip8_environment()==saved_env
            assert d.layers()['active']==[ram,fetch] and d.memory(0x300,length=1)['hex']=='7a'
            assert d.hooks()['hooks'][0]['hook']==hook['hook'] and d.hooks()['hooks'][0]['hits']==1
            _step(d,0x208,v0=8)
            actual=d.run(timeout_ms=5000,stop_on_hook=True)
            assert actual['hook_hits'][0]['hit']==2 and d.registers()==expected_regs
            assert {k:d.chip8_environment()[k] for k in expected_rng}==expected_rng
    assert rom.read_bytes()==source


def test_checkpoint_retains_ram_write_conflict_until_explicit_clear(tmp_path):
    with _machine(tmp_path,'6009 a300 f055 1206') as (_,d):
        layer=_layer(d,'written RAM',0x300,'00','07','ram');d.layers([layer])
        _step(d,0x202);_step(d,0x204);_step(d,0x206)
        checkpoint=d.save_state(timeout_ms=30000)['artifact']
        d.layers([],conflict='keep_changed')
        old=d.vm.process;d.load_state(checkpoint,timeout_ms=30000);assert old.poll() is not None
        assert d.layers()['active']==[layer] and d.memory(0x300,length=1)['hex']=='09'
        with pytest.raises(ValueError,match='conflict|changed'):d.layers([])
        d.layers([],conflict='keep_changed');assert d.memory(0x300,length=1)['hex']=='09'


def test_checkpoint_retains_native_fetch_fault_without_rebasing(tmp_path):
    with _machine(tmp_path,'a209 6009 f055 1208 6001 1208') as (_,d):
        layer=_layer(d,'guarded fetch',0x209,'01','02','execute');d.layers([layer])
        assert d.run(timeout_ms=5000)['outcome']=='layer_conflict'
        before=d.vm.qmp.call('query-chip8-layers');assert before['faulted'] and not before['backing-valid']
        checkpoint=d.save_state(timeout_ms=30000)['artifact']
        d.layers([]);old=d.vm.process;d.load_state(checkpoint,timeout_ms=30000);assert old.poll() is not None
        restored=d.vm.qmp.call('query-chip8-layers')
        assert not restored['stop-owned']
        assert {k:v for k,v in restored.items() if k!='stop-owned'}=={k:v for k,v in before.items() if k!='stop-owned'}
        assert d.memory(0x209,length=1)['hex']=='09'
        d.layers([]);_step(d,0x208);_step(d,0x20a,v0=9)


def test_layer_and_hook_public_json_routes(tmp_path):
    from fdisbull.cli import respond
    from fdisbull.debugger import DebugWorkspace
    binary,tool=_inputs();rom=tmp_path/'json.ch8';rom.write_bytes(bytes.fromhex('6001 1200'));path=tmp_path/'project.fdb'
    with Project.create(path,rom,arch='chip8'):pass
    workspace=DebugWorkspace()
    def call(method,**params):return respond({'method':method,'params':{'project':str(path),**params}},debugger=workspace)
    launch=call('debug-launch',executable=binary,game_dir=str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool)
    assert launch['ok'],launch
    run=launch['result']['run'];process=workspace.sessions[run].rpc.process
    try:
        patch=call('debug-layer-patch',run=run,name='JSON fetch',address=0x201,expected_hex='01',data_hex='02',kind='execute')
        assert patch['ok'],patch
        assert call('debug-code',run=run,address=0x200,length=2,view='execute')['result']['hex']=='6002'
        hook=call('debug-hook',run=run,address=0x200,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':3}}}])
        assert hook['ok'],hook
        result=call('debug-run',run=run,timeout_ms=5000,stop_on_hook=True)
        assert result['ok'] and result['result']['outcome']=='hook',result
        stepped=call('debug-step',run=run,timeout_ms=5000)
        assert stepped['ok'] and stepped['result']['registers']['registers']['v0']=='0x2'
        assert stepped['result']['registers']['registers']['i']=='0x3'
        assert call('debug-stop',run=run)['result']['process_reaped'] and process.poll() is not None
    finally:workspace.close()
