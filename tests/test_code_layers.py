"""Temporal byte views must be proved by actual guest execution, not host readback."""
import json
import os
from pathlib import Path

import pytest

from fdisbull.project import Project
from test_dos_loader import mz_file


@pytest.fixture
def layered_game(tmp_path):
    # DS=CS; AX=1111; BX reads the original AX immediate as guest data; loop.
    module=bytes.fromhex('0e1fb811118b1e0300ebfe')+bytes(501)
    binary=tmp_path/'LAYER.EXE';binary.write_bytes(mz_file(module,ss=0,sp=0x200))
    project=tmp_path/'layer.fdb'
    with Project.create(project,binary) as p:p.analyze(max_instructions=20)
    return project,binary


@pytest.fixture
def layer_backend():
    path=os.environ.get('FDISBULL_DOSBOX')
    if not path:pytest.skip('Set FDISBULL_DOSBOX to the layers backend')
    return str(Path(path).resolve(strict=True))


def patch(p,name,kind,value):
    return p.debug_layer(name,kind=kind,patches=[{
        'address':'1000:0003','expected_hex':'1111','data_hex':value}])['layer']


def test_layer_definitions_survive_restart_without_changing_static_bytes(layered_game):
    path,binary=layered_game
    with Project(path) as p:
        layer=patch(p,'theory','execute','2222')
        assert p.disassembly('1000:0002',lines=1)['instructions'][0]['bytes']=='b81111'
    with Project(path) as p:
        info=p.debug_layer_info(layer)
        assert info['kind']=='execute' and info['patches'][0]['data_hex']=='2222'
        assert [x['id'] for x in p.debug_layers()['layers']]==[layer]
        assert len(p.versions())==1


def test_real_fetch_overlay_preserves_guest_data_and_stacks_over_ram(layered_game,layer_backend,tmp_path):
    path,binary=layered_game
    with Project(path) as p, p.debugger(layer_backend,binary.parent) as d:
        entry=d.save_state('entry.sav')
        overlay=patch(p,'alternate immediate','execute','2222')
        ram=patch(p,'visible immediate','ram','3333')
        top=patch(p,'top immediate','execute','4444')
        bp=d.breakpoint('1000:0009')
        for layers,ax,bx in [([overlay],0x2222,0x1111),([ram],0x3333,0x3333),
                             ([ram,overlay],0x2222,0x3333),([overlay,top],0x4444,0x1111),
                             ([top,overlay],0x2222,0x1111),([],0x1111,0x1111)]:
            d.load_state(entry['artifact']);d.layers(layers)
            assert d.run(timeout_ms=2000)['outcome']=='breakpoint'
            regs=d.registers()['general']
            assert int(regs['eax'],16)==ax and int(regs['ebx'],16)==bx
        d.load_state(entry['artifact']);d.layers([overlay])
        trace=d.trace(count=4)
        data=p.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(trace['artifact'],)).fetchone()[0]
        events=json.loads(bytes(data))['events']
        changed=next(e for e in events if e['project_address']=='0x10002')
        assert changed['ram_bytes'].startswith('b81111') and changed['execution_bytes'].startswith('b82222')
        assert '2222' in changed['instruction'].lower()
        capture=d.capture_code('1000:0002',length=3)
        assert capture['metadata']['view']=='execute'
        assert p.disassembly('1000:0002',lines=1)['instructions'][0]['bytes']=='b81111'


def test_real_breakpoint_actions_and_zero_ram_cave(layered_game,layer_backend):
    path,binary=layered_game
    with Project(path) as p, p.debugger(layer_backend,binary.parent) as d:
        cave=d.cave('virtual return',address='1000:0100',code_hex='b8efbe',return_to='1000:0009')
        assert d.memory('1000:0100',length=8)['hex']=='00'*8
        d.hook('1000:0002',actions=[{'op':'layers','layers':[cave['layer']]},
                                  {'op':'redirect','address':'1000:0100'}])
        d.breakpoint('1000:0009')
        trace=d.trace(count=20,timeout_ms=2000)
        result=trace['metadata']['run']
        assert result['outcome']=='breakpoint' and len(result['hook_hits'])==1
        assert int(d.registers()['general']['eax'],16)==0xbeef
        assert d.memory('1000:0100',length=8)['hex']=='00'*8
        assert d.layers()['active']==[cave['layer']]
        content=bytes(p.db.execute('SELECT data FROM debug_artifacts WHERE id=?',(trace['artifact'],)).fetchone()[0])
        events=json.loads(content)['events']
        assert any(e['project_address'] in ('0x10100','0x10103') and
                   e['ram_bytes'].startswith('000000') and e['execution_bytes']!=e['ram_bytes'] for e in events)


def test_real_layered_checkpoint_restarts_with_both_views(layered_game,layer_backend):
    path,binary=layered_game
    with Project(path) as p:
        with p.debugger(layer_backend,binary.parent) as d:
            ram=patch(p,'RAM','ram','3333');overlay=patch(p,'fetch','execute','2222')
            d.layers([ram,overlay]);state=d.save_state('layered.sav')
        with p.debugger(layer_backend,binary.parent) as d:
            d.load_state(state['artifact'])
            assert d.layers()['active']==[ram,overlay]
            d.breakpoint('1000:0009')
            assert d.run(timeout_ms=2000)['outcome']=='breakpoint'
            regs=d.registers()['general']
            assert int(regs['eax'],16)==0x2222 and int(regs['ebx'],16)==0x3333
            d.layers([])
            assert d.memory('1000:0003',length=2)['hex']=='1111'


def test_real_guest_self_modification_stops_stale_overlay_before_execution(tmp_path,layer_backend):
    module=bytearray(512)
    module[:9]=bytes.fromhex('0e1fc606210044eb17')
    module[0x20:0x25]=bytes.fromhex('b81111ebfe')
    binary=tmp_path/'SMC.EXE';binary.write_bytes(mz_file(bytes(module),ss=0,sp=0x200))
    with Project.create(tmp_path/'smc.fdb',binary) as p:
        p.analyze(max_instructions=20)
        with p.debugger(layer_backend,binary.parent) as d:
            entry=d.save_state('entry.sav')
            layer=p.debug_layer('guard',kind='execute',patches=[{'address':'1000:0021',
                'expected_hex':'1111','data_hex':'2222'}])['layer']
            d.layers([layer])
            result=d.run(timeout_ms=2000)
            assert result['outcome']=='layer_conflict',result
            assert d.memory('1000:0021',length=2)['hex']=='4411'
            d.layers([])
            assert d.run(timeout_ms=20)['outcome']=='timeout'
            assert int(d.registers()['general']['eax'],16)==0x1144
            d.load_state(entry['artifact'])
            d.layer_patch('RAM guard','1000:0021',expected_hex='1111',data_hex='3333')
            assert d.run(timeout_ms=20)['outcome']=='timeout'
            with pytest.raises(ValueError,match='changed memory'):
                d.layers([])
            cleared=d.layers([],conflict='keep_changed')
            assert len(cleared['preserved_changed_bytes'])==1
            assert d.memory('1000:0021',length=2)['hex']=='4411'


@pytest.mark.parametrize('mode,value',[('invert',0x1111),('taken',0x2222),('fallthrough',0x1111)])
@pytest.mark.parametrize('code,stop',[
    ('31c07405b81111eb03b82222ebfe',12),
    ('31c00f840600b81111e90300b82222ebfe',15),
])
def test_real_short_and_near_branch_theories_leave_original_bytes(tmp_path,layer_backend,mode,value,code,stop):
    module=bytes.fromhex(code)+bytes(512-len(bytes.fromhex(code)))
    binary=tmp_path/'BRANCH.EXE';binary.write_bytes(mz_file(module,ss=0,sp=0x200))
    with Project.create(tmp_path/'branch.fdb',binary) as p:
        p.analyze(max_instructions=30)
        with p.debugger(layer_backend,binary.parent) as d:
            original=d.memory('1000:0002',length=4)['hex']
            d.branch('hypothesis','1000:0002',mode=mode)
            d.breakpoint(f'1000:{stop:04x}')
            assert d.run(timeout_ms=2000)['outcome']=='breakpoint'
            assert int(d.registers()['general']['eax'],16)==value
            assert d.memory('1000:0002',length=4)['hex']==original


def test_real_guest_crc_reads_original_code_while_overlay_executes(tmp_path,layer_backend):
    import binascii
    # CRC-16/XMODEM over B8 11 11 at 0050, computed using guest data reads.
    code=bytearray.fromhex('0e1fbe5000b9030031d2ac30c6b308d1e2730481f22110fecb75f4e2ede90000')
    # JNC skips the four-byte XOR; JNZ repeats at SHL; LOOP repeats at LODSB.
    # The final near jump selects the inspected instruction at 0050.
    code[-2:]=(0x50-len(code)).to_bytes(2,'little')
    module=bytearray(512);module[:len(code)]=code
    module[0x50:0x55]=bytes.fromhex('b81111ebfe')
    binary=tmp_path/'CRC.EXE';binary.write_bytes(mz_file(bytes(module),ss=0,sp=0x200))
    with Project.create(tmp_path/'crc.fdb',binary) as p:
        p.analyze(max_instructions=100)
        with p.debugger(layer_backend,binary.parent) as d:
            d.layer_patch('different execution','1000:0051',expected_hex='1111',data_hex='2222',kind='execute')
            d.breakpoint('1000:0053')
            assert d.run(timeout_ms=2000)['outcome']=='breakpoint'
            regs=d.registers()['general']
            assert int(regs['eax'],16)==0x2222
            assert int(regs['edx'],16)==binascii.crc_hqx(bytes.fromhex('b81111'),0)
            assert int(regs['edx'],16)!=binascii.crc_hqx(bytes.fromhex('b82222'),0)


def test_real_guest_self_integrity_can_disable_and_restore_ram_layer(tmp_path,layer_backend):
    import binascii
    expected=binascii.crc_hqx(bytes.fromhex('b81111'),0)
    # Guest checks its own instruction bytes, branches to failure on mismatch,
    # then executes those same instructions after the successful check.
    code=bytes.fromhex('0e1fbe5000b9030031d2ac30c6b308d1e2730481f22110fecb75f4e2ed')
    code+=bytes.fromhex('81fa')+expected.to_bytes(2,'little')
    code+=bytes.fromhex('7503e92a00b8addeebfe')
    module=bytearray(512);module[:len(code)]=code
    module[0x50:0x55]=bytes.fromhex('b81111ebfe')
    binary=tmp_path/'CHECK.EXE';binary.write_bytes(mz_file(bytes(module),ss=0,sp=0x200))
    with Project.create(tmp_path/'check.fdb',binary) as p:
        p.analyze(max_instructions=100)
        with p.debugger(layer_backend,binary.parent) as d:
            entry=d.save_state('entry.sav')
            ram=d.layer_patch('visible experiment','1000:0051',expected_hex='1111',data_hex='2222')['layer']
            d.breakpoint('1000:0029');d.breakpoint('1000:0053')
            detected=d.run(timeout_ms=2000)
            assert detected['outcome']=='breakpoint'
            assert int(d.registers()['general']['eax'],16)==0xdead
            assert int(d.registers()['general']['edx'],16)!=expected
            d.load_state(entry['artifact']);d.layers([ram])
            d.hook('1000:000a',actions=[{'op':'layers','layers':[]}])
            d.hook('1000:0023',actions=[{'op':'layers','layers':[ram]}])
            restored=d.run(timeout_ms=2000)
            assert restored['outcome']=='breakpoint' and len(restored['hook_hits'])==2
            regs=d.registers()
            assert int(regs['general']['edx'],16)==expected
            assert int(regs['general']['eax'],16)==0x2222
            assert int(regs['ip'],16)==0x53
            assert d.layers()['active']==[ram]
            assert d.memory('1000:0051',length=2)['hex']=='2222'
        events=p.debug_events(d.run_id)['events']
        transitions=[e['evidence']['active'] for e in events if e['operation']=='layer-transition']
        assert transitions[-2:]==[[],[ram]]


def test_real_native_layer_preflight_is_atomic(layered_game,layer_backend):
    import base64
    from fdisbull.dosbox_rpc import DebuggerError
    path,binary=layered_game
    with Project(path) as p,p.debugger(layer_backend,binary.parent) as d:
        ram=patch(p,'ram','ram','3333');overlay=patch(p,'overlay','execute','2222')
        d.layers([ram,overlay])
        def chunk(offset,before,after):
            return {'address':d.runtime_base+offset,
                    'before':base64.b64encode(bytes.fromhex(before)).decode(),
                    'after':base64.b64encode(bytes.fromhex(after)).decode()}
        with pytest.raises(DebuggerError,match='LAYER_PRECONDITION_FAILED'):
            d.call('layers.configure',{'ram':[chunk(3,'3333','4444'),chunk(0x10,'ff','aa')],'execute':[]})
        assert d.memory('1000:0003',length=2)['hex']=='3333'
        assert d.code('1000:0002',length=3)['hex']=='b82222'
        assert d.layers()['active']==[ram,overlay]


def test_real_script_layer_controls_and_hook_removal(layered_game,layer_backend):
    path,binary=layered_game
    with Project(path) as p,p.debugger(layer_backend,binary.parent) as d:
        overlay=patch(p,'scripted','execute','2222')
        hook=d.hook('1000:0002',actions=[{'op':'layers','layers':[]}])
        assert len(d.hooks()['hooks'])==1
        d.delete_hook(hook['hook'])
        assert d.hooks()['hooks']==[]
        result=d.script({'format':'fdisbull-script-1','steps':[
            {'op':'layer-stack','active':[overlay]},
            {'op':'code','address':'1000:0002','length':3,'as':'code'},
            {'op':'assert','value':'$code.hex','equals':'b82222'},
            {'op':'capture-code','address':'1000:0002','length':3},
            {'op':'breakpoint','address':'1000:0009'},
            {'op':'run','timeout_ms':2000,'as':'run'},
            {'op':'assert','value':'$run.hook_hits','equals':[]}]})
        assert result['ok'],result
        assert int(d.registers()['general']['eax'],16)==0x2222
    with Project(path) as p:
        events=p.debug_events(d.run_id)['events']
        assert {'layer-transition','hook-create','hook-delete'}<={e['operation'] for e in events}
        assert {'code-snapshot','script','script-result'}<={a['kind'] for a in p.debug_artifacts()['artifacts']}


def test_layer_guards_reject_malformed_or_overlapping_definitions(layered_game):
    path,binary=layered_game
    with Project(path) as p:
        for patches in ([{'address':'1000:0003','expected_hex':'11','data_hex':'2222'}],
                        [{'address':'1000:0003','expected_hex':'1111','data_hex':'2222'},
                         {'address':'1000:0004','expected_hex':'11','data_hex':'22'}]):
            with pytest.raises(ValueError):p.debug_layer('bad',kind='execute',patches=patches)
        assert p.debug_layers()['layers']==[]


def test_real_dword_immediate_fetch_has_a_separate_data_view(tmp_path,layer_backend):
    module=bytes.fromhex('0e1f66b811112222668b1e0400ebfe')+bytes(497)
    binary=tmp_path/'DWORD.EXE';binary.write_bytes(mz_file(module,ss=0,sp=0x200))
    with Project.create(tmp_path/'dword.fdb',binary) as p:
        p.analyze(max_instructions=20)
        with p.debugger(layer_backend,binary.parent) as d:
            d.layer_patch('32-bit immediate','1000:0004',expected_hex='11112222',data_hex='33334444',kind='execute')
            d.breakpoint('1000:000d')
            assert d.run(timeout_ms=2000)['outcome']=='breakpoint'
            regs=d.registers()['general']
            assert int(regs['eax'],16)==0x44443333 and int(regs['ebx'],16)==0x22221111
