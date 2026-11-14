"""Authored golden device witnesses against the real opt-in CHIP-8 QEMU."""
from contextlib import contextmanager
from io import BytesIO
import hashlib
import os
import pytest
from PIL import Image
from fdisbull.project import Project


def _inputs():
    binary=os.environ.get('FDISBULL_CHIP8_DEVICES_QEMU')
    image=os.environ.get('FDISBULL_CHIP8_DEVICES_QEMU_IMG')
    if not binary or not image:
        if os.environ.get('FDISBULL_REQUIRE_CHIP8_DEVICES') == '1':
            pytest.fail('CHIP-8 device QEMU and qemu-img are required')
        pytest.skip('Set FDISBULL_CHIP8_DEVICES_QEMU and FDISBULL_CHIP8_DEVICES_QEMU_IMG')
    return binary,image


@contextmanager
def _machine(tmp_path, words):
    binary,tool=_inputs();rom=tmp_path/'device.ch8';source=bytes.fromhex(words);rom.write_bytes(source)
    with Project.create(tmp_path/'project.fdb',rom,arch='chip8',bits=16) as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as debug:
            yield project,debug
    assert rom.read_bytes()==source


def _registers(d):return {k:int(v,16) for k,v in d.registers()['registers'].items()}


def _step(d,pc,**expected):
    result=d.step(timeout_ms=5000);assert result['outcome']=='step',result
    regs=_registers(d);assert regs['pc']==pc
    for name,value in expected.items():assert regs[name]==value,(name,regs)
    return result


def _pixels(d):
    receipt=d.frame_rgba()
    assert receipt['format']=='rgba8888' and (receipt['width'],receipt['height'])==(64,32)
    value=receipt['rgba']
    assert isinstance(value,bytes) and len(value)==64*32*4
    assert hashlib.sha256(value).hexdigest()==receipt['sha256']
    return value


def _on(pixels):
    # Compare exact display states independently of a black/white channel order.
    colors={pixels[i:i+4] for i in range(0,len(pixels),4)}
    assert colors <= {bytes.fromhex('000000ff'),bytes.fromhex('ffffffff')}
    return {i//4 for i in range(0,len(pixels),4) if pixels[i:i+4]==bytes.fromhex('ffffffff')}


def test_clipped_xor_collision_cls_and_stored_png(tmp_path):
    with _machine(tmp_path,'603f 611f a300 d012 d012 00e0') as (project,d):
        d.write_memory(0x300,'c0c0',expected_hex='0000')
        _step(d,0x202,v0=63);_step(d,0x204,v1=31);_step(d,0x206,i=0x300)
        _step(d,0x208,vf=0);frame=_pixels(d)
        assert _on(frame)=={31*64+63}
        shot=d.screenshot();row=project.db.execute('SELECT data,sha256 FROM debug_artifacts WHERE id=?',(shot['artifact'],)).fetchone()
        payload=bytes(row['data']);assert hashlib.sha256(payload).hexdigest()==row['sha256']
        assert shot['pixel_sha256']==hashlib.sha256(frame).hexdigest()
        with Image.open(BytesIO(payload)) as image:
            assert image.size==(64,32) and image.convert('RGBA').tobytes()==frame
        _step(d,0x20a,vf=1);assert _on(_pixels(d))==set()
        _step(d,0x20c);assert _on(_pixels(d))==set()


def test_draw_vf_coordinate_alias_and_oob_are_atomic(tmp_path):
    with _machine(tmp_path,'6f3f 6100 a300 df11 afff d012') as (_,d):
        d.write_memory(0x300,'80',expected_hex='00')
        _step(d,0x202,vf=63);_step(d,0x204,v1=0);_step(d,0x206,i=0x300)
        _step(d,0x208,vf=0);assert _on(_pixels(d))=={63}
        _step(d,0x20a,i=0xfff);before=_pixels(d);registers=_registers(d)
        result=d.step(timeout_ms=5000)
        assert result['outcome']=='exception' and result['fault']['faulted']
        assert _registers(d)==registers and _pixels(d)==before


def test_font_address_and_bytes_match_declared_pilot_table(tmp_path):
    # Font A = F0 90 F0 90 90; FX29 uses the low nibble of Vx.
    with _machine(tmp_path,'61fa f129') as (_,d):
        _step(d,0x202,v1=0xfa);_step(d,0x204,i=0x82)
        assert d.memory(0x82,length=5)['hex']=='f090f09090'


def test_key_wait_lowest_held_including_zero_and_key_skip_bounds(tmp_path):
    # FX0A must wait at its original PC until an explicit host key state.
    with _machine(tmp_path,'f00a e09e 6101 61ff e19e 6201 e1a1 6202') as (_,d):
        waiting=d.step(timeout_ms=5000)
        assert waiting['outcome']=='key_wait' and _registers(d)['pc']==0x200
        d.chip8_keypad([0,5,15])
        _step(d,0x202,v0=0)
        _step(d,0x206,v0=0)  # pressed key 0 skips 6101
        _step(d,0x208,v1=0xff)
        _step(d,0x20a)       # FF is outside keypad; SKP is not taken
        _step(d,0x20c,v2=1)
        _step(d,0x210,v2=1)  # SKNP of FF skips 6202
        d.chip8_keypad([])
        d.write_registers({'pc':{'expected':0x210,'value':0x202}})
        _step(d,0x204,v0=0)  # Released key 0 is no longer pressed.


def test_manual_ticks_decrement_clamp_without_advancing_virtual_phase(tmp_path):
    with _machine(tmp_path,'6005 f015 6003 f018 f107') as (_,d):
        _step(d,0x202,v0=5);_step(d,0x204)
        _step(d,0x206,v0=3);_step(d,0x208)
        before=d.chip8_environment()
        assert before['delay-timer']==5 and before['sound-timer']==3 and before['sound-active']
        after=d.chip8_tick(2)
        assert (after['delay-timer'],after['sound-timer'])==(3,1)
        assert after['manual-ticks']==before['manual-ticks']+2
        assert after['virtual-ticks']==before['virtual-ticks']
        assert after['phase-numerator']==before['phase-numerator']
        _step(d,0x20a,v1=3)
        final=d.chip8_tick(10)
        assert (final['delay-timer'],final['sound-timer'])==(0,0)
        assert not final['sound-active']


def test_wait_held_keys_frame_and_timer_phase_survive_cold_fdb_restore(tmp_path):
    binary,tool=_inputs();source=bytes.fromhex('6005 f015 6003 f018 6100 a300 d011 f20a')
    rom=tmp_path/'save.ch8';rom.write_bytes(source);db=tmp_path/'project.fdb'
    with Project.create(db,rom,arch='chip8',bits=16) as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            d.write_memory(0x300,'80',expected_hex='00')
            for pc in (0x202,0x204,0x206,0x208,0x20a,0x20c,0x20e):_step(d,pc)
            assert _on(_pixels(d))=={3}
            d.chip8_tick(2)
            result=d.step(timeout_ms=5000);assert result['outcome']=='key_wait'
            d.chip8_keypad([0,5])
            saved=d.chip8_environment();assert saved['key-mask']==0x21 and saved['key-wait']
            checkpoint=d.save_state(timeout_ms=30000)['artifact']
    with Project(db) as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            old=d.vm.process;d.load_state(checkpoint,timeout_ms=30000)
            assert old.poll() is not None
            restored=d.chip8_environment()
            for key in ('pixels-hex','pixels-sha256','frame-generation','key-mask','key-wait',
                        'delay-timer','sound-timer','sound-active','virtual-ticks','manual-ticks','phase-numerator'):
                assert restored[key]==saved[key],key
            assert not restored['key-wait-stop-owned']
            _step(d,0x210,v2=0)
            d.chip8_keypad([])
            assert d.chip8_environment()['key-mask']==0
    assert rom.read_bytes()==source


def test_running_virtual_clock_drives_timer_without_wall_clock_rate_claim(tmp_path):
    binary,tool=_inputs();db=tmp_path/'project.fdb'
    with _machine(tmp_path,'60ff f015 1204') as (_,d):
        _step(d,0x202,v0=255);_step(d,0x204)
        before=d.chip8_environment()
        # Establish virtual tick progress, then sample in short intervals if
        # the first stop landed at the zero remainder of the 60 Hz cycle.
        result=d.run(timeout_ms=250)
        assert result['outcome']=='timeout',result
        after=d.chip8_environment()
        for _ in range(16):
            if (after['virtual-ticks']>before['virtual-ticks'] and
                    after['virtual-now-ns']>0 and after['phase-numerator']>0):
                break
            result=d.run(timeout_ms=10)
            assert result['outcome']=='timeout',result
            after=d.chip8_environment()
        assert after['virtual-now-ns']>0 and after['phase-numerator']>0
        ticks=after['virtual-ticks']-before['virtual-ticks']
        assert ticks>0
        # Each period is exactly 1e9/60 ns. The stored numerator is the
        # remainder in sixtieths, so independently carry the fractional part
        # from the observed baseline rather than measuring host wall time.
        numerator=before['phase-numerator'] + ticks*1_000_000_000
        whole_ns,phase=divmod(numerator,60)
        assert after['next-deadline-ns']==before['next-deadline-ns']+whole_ns
        assert after['phase-numerator']==phase
        assert after['delay-timer']==max(0,before['delay-timer']-ticks)
        assert after['manual-ticks']==before['manual-ticks']
        checkpoint=d.save_state(timeout_ms=30000)['artifact']
        d.chip8_keypad([7]);d.chip8_tick(1)
        changed=d.chip8_environment()
        assert changed['key-mask']!=after['key-mask'] and changed['manual-ticks']==after['manual-ticks']+1
    with Project(db) as project:
        with project.debugger(binary,str(tmp_path),backend='qemu-chip8',qemu_checkpoint_tool=tool,boot_timeout_ms=10000) as d:
            old=d.vm.process;d.load_state(checkpoint,timeout_ms=30000)
            assert old.poll() is not None
            restored=d.chip8_environment()
            for key in ('virtual-now-ns','next-deadline-ns','phase-numerator','virtual-ticks',
                        'manual-ticks','delay-timer','sound-timer','sound-active','key-mask'):
                assert restored[key]==after[key],key
