"""Actual QEMU CHIP-8 history witnesses with authored programs only."""
from contextlib import contextmanager
from io import BytesIO
import hashlib
import os
import pytest
from PIL import Image
from fdisbull.project import Project


def _inputs():
    binary=os.environ.get('FDISBULL_CHIP8_HISTORY_QEMU')
    tool=os.environ.get('FDISBULL_CHIP8_HISTORY_QEMU_IMG')
    if not binary or not tool:
        if os.environ.get('FDISBULL_REQUIRE_CHIP8_HISTORY')=='1':
            pytest.fail('CHIP-8 history QEMU and qemu-img are required')
        pytest.skip('Set FDISBULL_CHIP8_HISTORY_QEMU and FDISBULL_CHIP8_HISTORY_QEMU_IMG')
    return binary,tool


@contextmanager
def _machine(tmp_path,words,*,checkpoint=True):
    binary,tool=_inputs();rom=tmp_path/'history.ch8';source=bytes.fromhex(words);rom.write_bytes(source)
    with Project.create(tmp_path/'project.fdb',rom,arch='chip8') as project:
        options={'qemu_checkpoint_tool':tool} if checkpoint else {}
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',boot_timeout_ms=10000,**options) as d:
            yield project,d
    assert rom.read_bytes()==source


def _regs(d):return {k:int(v,16) for k,v in d.registers()['registers'].items()}


def _layer(d,name,address,before,after,kind):
    return d.layer_patch(name,address,expected_hex=before,data_hex=after,kind=kind,activate=False)['layer']


def _summary(d):
    env=d.chip8_environment()
    return {'registers':d.registers(),'ram':d.memory(0x300,length=1)['hex'],
            'code':d.code(0x206,length=2,view='execute')['hex'],
            'pixels':env['pixels-sha256'],'key':env['key-mask'],
            'rng':tuple(env[k] for k in ('rng-seed','rng-state','rng-draws')),
            'clock':tuple(env[k] for k in ('virtual-now-ns','next-deadline-ns','phase-numerator','virtual-ticks','manual-ticks')),
            'layers':d.layers()['active']}


def test_history_active_layers_frame_rng_branch_and_cold_project_reopen(tmp_path):
    binary,tool=_inputs();db=tmp_path/'project.fdb'
    # Draw a single pixel, then mask the random instruction through fetch view.
    with _machine(tmp_path,'6100 a310 d011 c0ff 7001 1206') as (project,d):
        d.write_memory(0x310,'80',expected_hex='00')
        for _ in range(3):assert d.step(timeout_ms=5000)['outcome']=='step'
        ram=_layer(d,'data',0x300,'00','7a','ram')
        fetch=_layer(d,'rng-mask',0x207,'ff','f0','execute')
        d.layers([ram,fetch]);d.chip8_seed_rng(0);d.chip8_keypad([0,15]);d.chip8_tick(2)
        image=d.screenshot();png=project.db.execute('select data from debug_artifacts where id=?',(image['artifact'],)).fetchone()
        with Image.open(BytesIO(bytes(png['data']))) as rendered:
            assert rendered.size==(64,32) and hashlib.sha256(rendered.convert('RGBA').tobytes()).hexdigest()==image['pixel_sha256']
        start=d.rewind_start(max_steps=8,timeout_ms=60000)
        assert start['format']=='fdisbull-qemu-chip8-history-v1' and start['valid']
        root=start['cursor'];old_revision=start['history'];original=_summary(d)
        one=d.rewind_record(count=1,timeout_ms=60000);node1=one['cursor']
        assert one['recorded_count']==1 and _regs(d)['v0']==0x30 and d.chip8_environment()['rng-draws']==1
        assert one['records'][0]['edge']['completed_instruction'] is None
        two=d.rewind_record(count=1,timeout_ms=60000);node2=two['cursor']
        assert _regs(d)['v0']==0x31
        previous=d.vm.process;d.rewind(count=2,timeout_ms=60000);assert previous.poll() is not None
        assert _summary(d)==original
        branch=d.rewind_record(count=1,timeout_ms=60000);branch_id=branch['cursor']
        assert _regs(d)['v0']==0x30
        status=d.rewind_status(history=old_revision)
        assert {root,node1,node2,branch_id}<=set(status['node_ids']) and status['captures_used']==4
        rows={n['id']:n for n in status['nodes']}
        assert rows[node1]['parent']==rows[branch_id]['parent']==root and rows[node2]['parent']==node1
        latest=status['history']
    with Project(db) as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            attached=d.rewind_start(history=latest,timeout_ms=60000)
            assert not attached['valid']
            old=d.vm.process;d.rewind(history=latest,node=root,timeout_ms=60000);assert old.poll() is not None
            assert _summary(d)==original
            assert d.rewind_record(count=1,timeout_ms=60000)['recorded_count']==1
            assert _regs(d)['v0']==0x30 and d.chip8_environment()['rng-draws']==1


def test_history_pending_hook_capture_and_restore_displaces_once(tmp_path):
    with _machine(tmp_path,'c0ff 1200') as (_,d):
        d.chip8_seed_rng(0)
        hook=d.hook(0x200,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':0}}}],once=False,max_hits=3)
        assert d.run(timeout_ms=5000,stop_on_hook=True)['hook_hits'][0]['hit']==1
        start=d.rewind_start(max_steps=4,timeout_ms=60000);root=start['cursor']
        before=d.rewind_status();env=d.chip8_environment();owner=d.vm.process
        with pytest.raises(ValueError,match='pending hook'):d.rewind_record(count=1)
        assert d.rewind_status()==before and d.chip8_environment()==env and d.vm.process is owner
        captured=d.rewind_record(advance='capture');assert captured['records'][0]['edge']['kind']=='capture'
        old=d.vm.process;d.rewind(history=captured['history'],node=root,timeout_ms=60000);assert old.poll() is not None
        assert d.hooks()['pending']==hook['hook'] and d.hooks()['hooks'][0]['hits']==1
        result=d.step(timeout_ms=5000)
        assert result['outcome']=='step' and result['hook_hits']==[] and _regs(d)['v0']==0x3c
        assert d.chip8_environment()['rng-draws']==1 and d.hooks()['hooks'][0]['hits']==1


def test_history_unrecorded_mutation_invalidates_then_capture_is_unobserved(tmp_path):
    with _machine(tmp_path,'6001 7001 1202') as (_,d):
        start=d.rewind_start(max_steps=4);root=start['cursor']
        d.write_memory(0x300,'7a',expected_hex='00')
        assert not d.rewind_status()['valid']
        with pytest.raises(ValueError,match='cursor'):d.rewind_record(count=1)
        captured=d.rewind_record(advance='capture')
        assert captured['records'][0]['edge']['kind']=='capture'
        assert captured['records'][0]['edge']['completed_instruction'] is None
        d.rewind(history=captured['history'],node=root)
        assert d.memory(0x300,length=1)['hex']=='00'


@pytest.mark.parametrize('word,outcome', [('f00a','key_wait'),('ffff','exception')])
def test_history_nonordinary_stop_records_no_extra_step(tmp_path,word,outcome):
    with _machine(tmp_path,word) as (_,d):
        d.rewind_start(max_steps=4)
        result=d.rewind_record(count=2,timeout_ms=60000)
        assert result['recorded_count']==1 and result['records'][0]['edge']['kind']=='stopped'
        assert result['records'][0]['edge']['outcome']==outcome
        assert _regs(d)['pc']==0x200 and d.chip8_environment()['rng-draws']==0


def test_history_budget_and_user_breakpoint_refuse_before_effect(tmp_path):
    with _machine(tmp_path,'6001 1200') as (_,d):
        bp=d.breakpoint(0x200);before=d.registers()
        with pytest.raises(ValueError,match='breakpoint'):d.rewind_start(max_steps=2)
        assert d.registers()==before and not d.closed
        d.delete_breakpoint(bp['breakpoint_id'])
        started=d.rewind_start(max_steps=1)
        before=d.rewind_status();env=d.chip8_environment()
        with pytest.raises(ValueError,match='budget'):d.rewind_record(count=1)
        assert d.rewind_status()==before and d.chip8_environment()==env
        assert started['cursor']==before['cursor']


def test_history_json_and_persisted_script_routes(tmp_path):
    from fdisbull.cli import respond
    from fdisbull.debugger import DebugWorkspace
    with _machine(tmp_path,'6001 7001 1202') as (project,d):
        workspace=DebugWorkspace();workspace.sessions[d.run_id]=d
        def call(method,**params):
            reply=respond({'method':method,'params':{'project':str(project.path),'run':d.run_id,**params}},debugger=workspace)
            assert reply['ok'],reply
            return reply['result']
        try:
            root=call('debug-rewind-start',max_steps=6)
            record=call('debug-rewind-record',count=1)
            assert record['recorded_count']==1 and _regs(d)['v0']==1
            call('debug-rewind',history=record['history'],node=root['cursor'])
            assert _regs(d)['pc']==0x200
            saved=project.debug_save_script('history-route',{'format':'fdisbull-script-1','backend':'qemu-chip8',
                'steps':[{'op':'rewind-record','count':1},{'op':'rewind-record','advance':'capture'}]})
            report=d.script(script_id=saved['script_id'],timeout_ms=60000)
            assert report['ok'] and report['completed_steps']==2 and _regs(d)['v0']==1
            assert call('debug-rewind-status')['captures_used']==4
        finally:
            workspace.sessions.clear()


def test_history_requires_explicit_checkpoint_tool_without_effect(tmp_path):
    with _machine(tmp_path,'6001 1200',checkpoint=False) as (_,d):
        before=d.registers();owner=d.vm.process
        with pytest.raises(ValueError,match='checkpoint'):d.rewind_start(max_steps=2)
        assert d.registers()==before and d.vm.process is owner and not d.closed


def test_history_guest_write_layer_conflict_captures_and_refuses_stale_fetch(tmp_path):
    # Fx55 writes 09 into the backing of the layered 6001 instruction.
    with _machine(tmp_path,'a209 6009 f055 1208 6001 1208') as (_,d):
        fetch=_layer(d,'protected-fetch',0x209,'01','02','execute');d.layers([fetch])
        d.rewind_start(max_steps=8)
        result=d.rewind_record(count=3,timeout_ms=60000)
        assert result['recorded_count']==3
        assert [record['edge']['kind'] for record in result['records']]==['step','step','stopped']
        last=result['records'][-1]
        assert last['edge']['outcome']=='layer_conflict'
        assert _regs(d)['pc']==0x206 and _regs(d)['v0']==9
        assert d.memory(0x209,length=1)['hex']=='09' and d.chip8_environment()['rng-draws']==0
        previous=d.vm.process;d.rewind(history=result['history'],node=last['node'])
        assert previous.poll() is not None
        before=d.registers();env=d.chip8_environment()
        assert d.memory(0x209,length=1)['hex']=='09' and d.layers()['active']==[fetch]
        repeated=d.rewind_record(count=1,timeout_ms=60000)
        assert repeated['records'][0]['edge']['outcome']=='layer_conflict'
        assert d.registers()==before and d.chip8_environment()==env
        assert d.memory(0x209,length=1)['hex']=='09'


def test_history_contended_vm_lock_respects_deadline_without_effect(tmp_path):
    import threading,time
    with _machine(tmp_path,'6001 1200') as (_,d):
        start=d.rewind_start(max_steps=4);before=d.rewind_status();registers=d.registers();env=d.chip8_environment()
        owner=d.vm.process;acquired=threading.Event();release=threading.Event()
        def holder():
            with d.vm.lock:
                acquired.set();release.wait(3)
        thread=threading.Thread(target=holder);thread.start();assert acquired.wait(1)
        clock=time.monotonic()
        try:
            with pytest.raises(TimeoutError):d.rewind_record(count=1,timeout_ms=30)
            assert time.monotonic()-clock<0.5
        finally:
            release.set();thread.join(timeout=2)
        assert not thread.is_alive() and d.vm.process is owner and owner.poll() is None and not d.closed
        assert d.rewind_status()==before and d.registers()==registers and d.chip8_environment()==env
        assert start['cursor']==before['cursor']
