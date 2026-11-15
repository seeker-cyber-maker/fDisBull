"""Real CHIP-8 selected CPU/RAM undo is frozen partial state."""
from contextlib import contextmanager
import os
import pytest
from fdisbull.project import Project


def _inputs():
    binary=os.environ.get('FDISBULL_CHIP8_FRAME_KEYS_QEMU');tool=os.environ.get('FDISBULL_CHIP8_FRAME_KEYS_QEMU_IMG')
    if not binary or not tool:
        if os.environ.get('FDISBULL_REQUIRE_CHIP8_FRAME_KEYS')=='1':pytest.fail('CHIP-8 v6 runtime and qemu-img required')
        pytest.skip('Set CHIP-8 v6 runtime and qemu-img')
    return binary,tool


@contextmanager
def _machine(tmp_path,words='6001 a300 f055 6102 f155 c2ff 120c'):
    binary,tool=_inputs();rom=tmp_path/'undo.ch8';original=bytes.fromhex(words);rom.write_bytes(original)
    with Project.create(tmp_path/'undo.fdb',rom,arch='chip8') as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            yield project,d
    assert rom.read_bytes()==original


def _regs(d):return {k:int(v,16) for k,v in d.registers()['registers'].items()}
def _mem(d,address,length=1):return bytes.fromhex(d.memory(address,length=length)['hex'])
def _selected():return [{'address':0x300,'length':1}]


def test_partial_undo_preserves_unselected_and_devices_then_anchor_recovers(tmp_path):
    with _machine(tmp_path) as (_,d):
        ram=d.layer_patch('ram',0x350,expected_hex='00',data_hex='7a',kind='ram',activate=False)['layer']
        code=d.layer_patch('fetch',0x221,expected_hex='00',data_hex='01',kind='execute',activate=False)['layer']
        d.layers([ram,code]);d.frame_inputs([{'key':'f','pressed':True}]);d.chip8_seed_rng(123)
        hook=d.hook(0x230,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':0}}}],once=False,max_hits=3)
        before=_regs(d);keys=d.keyboard_state()['keyboard']['frame_keys'];anchor_env=d.chip8_environment()
        start=d.cpu_delta_start(_selected(),registers=['v0','i','pc'],max_steps=8)
        assert start['anchor']['artifact'] and _mem(d,0x300)==b'\0'
        recorded=d.cpu_delta_record(count=6);assert recorded['outcome']=='completed' and recorded['recorded_count']==6
        later=_regs(d);env=d.chip8_environment();assert later['v0']==1 and later['v1']==2
        assert _mem(d,0x300)==b'\x01' and _mem(d,0x302)==b'\x02' and env['rng-draws']==anchor_env['rng-draws']+1
        result=d.cpu_delta_rewind(count=6)
        assert result['partial_restored'] and not result['full_machine_restored'] and not result['devices_restored']
        assert not result['resume_safe'] and not result['execution_allowed'] and d.cpu_delta_status()['frozen']
        after=_regs(d);assert all(after[k]==before[k] for k in ('v0','i','pc'))
        assert after['v1']==later['v1'] and after['v2']==later['v2']
        assert _mem(d,0x300)==b'\0' and _mem(d,0x302)==b'\x02' and _mem(d,0x350)==b'\x7a'
        actual=d.chip8_environment()
        for key in ('rng-state','rng-draws','key-mask','delay-timer','sound-timer','pixels-sha256','virtual-ticks'):
            assert actual[key]==env[key]
        assert d.keyboard_state()['keyboard']['frame_keys']==keys and d.hooks()['hooks'][0]['hook']==hook['hook']
        assert d.layers()['active']==[ram,code]
        for operation in (lambda:d.step(),lambda:d.run(),lambda:d.save_state(),
                          lambda:d.frame_inputs([{'key':'f','pressed':False}]),lambda:d.layers([])):
            with pytest.raises(ValueError,match='frozen|partial'):operation()
        old=d.vm.process;restored=d.cpu_delta_recover()
        assert restored['full_native_anchor_loaded'] and old.poll() is not None and not d.cpu_delta_status()['frozen']
        assert _regs(d)==before and _mem(d,0x300)==b'\0' and _mem(d,0x302)==b'\0'
        assert d.chip8_environment()['rng-state']==anchor_env['rng-state']
        assert d.keyboard_state()['keyboard']['frame_keys']==['f'] and d.layers()['active']==[ram,code]
        assert d.step()['outcome']=='step'


def test_pending_hook_refuses_record_before_intent(tmp_path):
    with _machine(tmp_path,'6001 1200') as (project,d):
        hook=d.hook(0x200,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':0}}}],once=False,max_hits=2)
        assert d.run(stop_on_hook=True)['outcome']=='hook'
        start=d.cpu_delta_start(_selected(),registers=['v0','pc'],max_steps=3)
        before=d.registers(),d.chip8_environment(),d.hooks(),d.cpu_delta_status()
        events=project.db.execute('select count(*) from debug_events').fetchone()[0]
        with pytest.raises(ValueError,match='hook'):d.cpu_delta_record()
        assert (d.registers(),d.chip8_environment(),d.hooks(),d.cpu_delta_status())==before
        assert project.db.execute('select count(*) from debug_events').fetchone()[0]==events
        assert d.hooks()['pending']==hook['hook'] and start['valid']


@pytest.mark.parametrize('mode',['full','delta'])
def test_frame_point_full_restore_thaws_partial_undo(tmp_path,mode):
    with _machine(tmp_path) as (project,d):
        ram=d.layer_patch('frame-ram',0x350,expected_hex='00',data_hex='7a',kind='ram',activate=False)['layer']
        code=d.layer_patch('frame-fetch',0x221,expected_hex='00',data_hex='01',kind='execute',activate=False)['layer']
        d.layers([ram,code]);d.frame_inputs([{'key':'f','pressed':True}]);d.chip8_seed_rng(123)
        hook=d.hook(0x230,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':0}}}],once=False,max_hits=3)
        bad=d.save_state()
        timeline=d.timeline_start(storage_mode=mode,max_frames=4)
        if mode=='delta':
            timeline=d.timeline_advance(frames=1)
            point=timeline['point'];node=next(n for n in timeline['nodes'] if n['id']==point)
            assert node['checkpoint']['storage']['kind']=='delta'
        else:point=timeline['point']
        original=d.registers(),_mem(d,0x300),d.chip8_environment()
        keys=d.keyboard_state()['keyboard']['native'];hooks=d.hooks()
        d.cpu_delta_start(_selected(),registers=['v0','pc'],max_steps=4)
        assert d.cpu_delta_record(count=3)['recorded_count']==3
        assert d.cpu_delta_rewind(count=3)['partial_restored'] and d.cpu_delta_status()['frozen']
        owner=d.vm.process;frozen=d.registers(),d.chip8_environment()
        with project.transaction(True):project.db.execute('update debug_artifacts set data=? where id=?',(b'corrupt',bad['artifact']))
        with pytest.raises(ValueError):d.load_state(bad['artifact'])
        assert d.vm.process is owner and owner.poll() is None and not d.closed and d.cpu_delta_status()['frozen']
        assert (d.registers(),d.chip8_environment())==frozen
        d.timeline_rewind(timeline=timeline['timeline'],point=point,frames=0)
        assert not d.cpu_delta_status()['frozen']
        assert (d.registers(),_mem(d,0x300),d.chip8_environment())==original
        restored_keys=d.keyboard_state()['keyboard']['native']
        assert restored_keys['held']==keys['held']==['f'] and restored_keys['accepted-edges']==keys['accepted-edges']
        assert d.layers()['active']==[ram,code] and _mem(d,0x350)==b'\x7a'
        assert d.hooks()['hooks'][0]['hook']==hook['hook'] and d.hooks()['hooks'][0]['hits']==hooks['hooks'][0]['hits']==0
        assert point in {n['id'] for n in d.timeline_status()['nodes']}
        assert d.step()['outcome']=='step'


def test_invalid_ranges_and_caller_transaction_refuse_without_effect(tmp_path):
    with _machine(tmp_path) as (project,d):
        before=d.registers(),d.chip8_environment(),_mem(d,0,4096)
        for ranges,registers in [([{'address':4096,'length':1}],['v0']),
                                 ([{'address':0x300,'length':2},{'address':0x301,'length':1}],['v0']),
                                 (_selected(),['sp']),(_selected(),['stack0'])]:
            with pytest.raises(ValueError):d.cpu_delta_start(ranges,registers=registers)
        with project.transaction(True):
            with pytest.raises(ValueError):d.cpu_delta_start(_selected(),registers=['v0'])
        assert (d.registers(),d.chip8_environment(),_mem(d,0,4096))==before and not d.closed


def test_corrupt_anchor_refuses_recovery_without_thaw(tmp_path):
    with _machine(tmp_path) as (project,d):
        start=d.cpu_delta_start(_selected(),registers=['v0','pc'],max_steps=4)
        assert d.cpu_delta_record(count=1)['recorded_count']==1
        assert d.cpu_delta_rewind(count=1)['partial_restored']
        owner=d.vm.process;before=d.registers(),d.chip8_environment()
        with project.transaction(True):project.db.execute('update debug_artifacts set data=? where id=?',(b'bad',start['anchor']['artifact']))
        with pytest.raises(ValueError):d.cpu_delta_recover()
        assert d.vm.process is owner and owner.poll() is None and not d.closed and d.cpu_delta_status()['frozen']
        assert (d.registers(),d.chip8_environment())==before


def test_ram_undo_preserves_active_fetch_and_overlapping_ram_layer(tmp_path):
    with _machine(tmp_path,'6001 a300 f055 1206') as (_,d):
        ram=d.layer_patch('overlap',0x300,expected_hex='00',data_hex='7a',kind='ram',activate=False)['layer']
        code=d.layer_patch('fetch',0x221,expected_hex='00',data_hex='01',kind='execute',activate=False)['layer']
        d.layers([ram,code]);before=d.code(0x220,length=2,view='execute')['hex']
        assert _mem(d,0x300)==b'\x7a'
        d.cpu_delta_start(_selected(),registers=['v0','pc'],max_steps=4)
        assert d.cpu_delta_record(count=3)['recorded_count']==3 and _mem(d,0x300)==b'\x01'
        assert d.cpu_delta_rewind(count=3)['partial_restored'] and _mem(d,0x300)==b'\x7a'
        assert d.layers()['active']==[ram,code] and d.code(0x220,length=2,view='execute')['hex']==before
        assert d.cpu_delta_status()['frozen']


def test_preserve_policy_keeps_selected_register_and_memory(tmp_path):
    with _machine(tmp_path) as (_,d):
        d.cpu_delta_start(_selected(),registers=['v0','pc'],max_steps=4)
        assert d.cpu_delta_record(count=3)['recorded_count']==3
        result=d.cpu_delta_rewind(count=3,policy={'preserve_registers':['v0'],
            'preserve_memory':[{'address':0x300,'length':1}]})
        assert result['partial_restored'] and _regs(d)['v0']==1 and _regs(d)['pc']==0x200
        assert _mem(d,0x300)==b'\x01' and not result['execution_allowed']


def test_corrupt_interval_refuses_before_partial_write(tmp_path):
    with _machine(tmp_path) as (project,d):
        d.cpu_delta_start(_selected(),registers=['v0','pc'],max_steps=4)
        recorded=d.cpu_delta_record(count=1);artifact=recorded['records'][0]['artifact']
        with project.transaction(True):project.db.execute('update debug_artifacts set data=? where id=?',(b'bad',artifact))
        before=d.registers(),d.chip8_environment(),_mem(d,0,4096);owner=d.vm.process
        with pytest.raises(ValueError):d.cpu_delta_rewind(count=1)
        assert (d.registers(),d.chip8_environment(),_mem(d,0,4096))==before
        assert d.vm.process is owner and owner.poll() is None and not d.closed
        assert not d.cpu_delta_status()['frozen']


def test_future_hook_stop_retains_recorded_prefix_without_dispatch(tmp_path):
    with _machine(tmp_path,'6001 7001 1204') as (_,d):
        hook=d.hook(0x204,actions=[{'op':'registers','registers':{'i':{'expected':0,'value':0}}}],once=False,max_hits=3)
        d.cpu_delta_start(_selected(),registers=['v0','pc'],max_steps=5)
        result=d.cpu_delta_record(count=3)
        assert result['outcome']=='interrupted' and result['recorded_count']==1 and len(result['records'])==1
        assert result['stop']['outcome']=='breakpoint' and _regs(d)['pc']==0x204 and _regs(d)['v0']==2
        state=d.hooks();assert state['pending'] is None and state['hooks'][0]['hook']==hook['hook'] and state['hooks'][0]['hits']==0
        assert not d.cpu_delta_status()['valid'] and not d.closed


def test_saved_script_selected_undo_and_full_recovery_preserve_owned_key(tmp_path):
    with _machine(tmp_path,'6001 a300 f055 1206') as (project,d):
        d.frame_inputs([{'key':'f','pressed':True}])
        before_regs=d.registers();before_ram=_mem(d,0x300)
        before_keys=d.keyboard_state()['keyboard']['native']
        program={'format':'fdisbull-script-1','backend':'qemu-chip8','steps':[
            {'op':'delta-start','ranges':[{'address':0x300,'length':1}],'registers':['v0','pc']},
            {'op':'delta-record','count':3},
            {'op':'delta-rewind','count':3},
            {'op':'delta-status'},
            {'op':'delta-recover'}]}
        saved=project.debug_save_script('chip8-selected-undo',program)
        report=d.script(script_id=saved['script_id'],timeout_ms=60000)
        assert report['ok'] and report['completed_steps']==5,report
        results=[step['result'] for step in report['steps']]
        assert results[1]['outcome']=='completed' and results[1]['recorded_count']==3
        assert results[2]['partial_restored'] and not results[2]['execution_allowed']
        assert results[3]['frozen'] and not results[3]['execution_allowed']
        assert results[4]['full_native_anchor_loaded'] and not d.cpu_delta_status()['frozen']
        assert d.registers()==before_regs and _mem(d,0x300)==before_ram
        after_keys=d.keyboard_state()['keyboard']['native']
        assert after_keys['held']==before_keys['held']==['f']
        assert after_keys['accepted-edges']==before_keys['accepted-edges']
