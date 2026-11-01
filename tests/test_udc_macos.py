"""Native GameIL integer semantics, context isolation and transactional faults."""
import ctypes
import hashlib
import platform
from pathlib import Path

import pytest

from fdisbull.game_il import GameMachine, author_program
from fdisbull.udc_macos import build_macos

pytestmark = pytest.mark.skipif(platform.system() != 'Darwin' or platform.machine() != 'arm64',
                                reason='macOS arm64 native compiler required')


def test_integer_execution_and_atomic_boundaries(tmp_path):
    raw = b'reviewed immutable region'
    rom = tmp_path/'rom.bin';rom.write_bytes(raw)
    program = author_program('''
        typedef unsigned char u8; typedef signed int i16;
        typedef unsigned int u16; typedef unsigned long u32;
        u16 value; i16 signed_value; u8 data[3]; u8 shadowrun_arena_frame_status;
        u16 shadow=7; u16 observed;
        void shadow_test(void) { u16 shadow=shadow+1; observed=shadow; }
        void shadowrun_arena_frame(u8 pad) {
            u32 shift;
            if (pad==1) { value=65535U; value+=2U; signed_value=-7; signed_value/=3; data[1]=255; }
            if (pad==2) { value=31; value/=0; }
            if (pad==3) { value=31; data[4]=2; }
            if (pad==4) { value=31; shadowrun_arena_frame_status=2; }
            if (pad==5) { shift=16; value=1; value <<= shift; }
            if (pad==6) shadow_test();
            if (pad==7) { value=77; value=1 << 16; }
        }
    ''', [{'id':0,'length':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}])
    ref=GameMachine(program,{0:raw})
    out=tmp_path/'native';build_macos(program,ref.snapshot(),out)
    lib=ctypes.CDLL(str(out/'libfdisbull_native.dylib'))
    ptr=ctypes.c_void_p
    lib.fdisbull_create.argtypes=[ctypes.c_char_p,ctypes.POINTER(ptr)];lib.fdisbull_create.restype=ctypes.c_int
    lib.fdisbull_destroy.argtypes=[ptr]
    lib.fdisbull_reset.argtypes=[ptr];lib.fdisbull_step.argtypes=[ptr,ctypes.c_uint8]
    lib.fdisbull_state_get.argtypes=[ptr,ctypes.c_char_p,ctypes.c_uint32,ctypes.POINTER(ctypes.c_int64)]
    lib.fdisbull_state_set.argtypes=[ptr,ctypes.c_char_p,ctypes.c_uint32,ctypes.c_int64]
    a=ptr();b=ptr();assert lib.fdisbull_create(str(rom).encode(),ctypes.byref(a))==0
    assert lib.fdisbull_create(str(rom).encode(),ctypes.byref(b))==0
    def get(ctx,name,i=0):
        v=ctypes.c_int64();assert lib.fdisbull_state_get(ctx,name.encode(),i,ctypes.byref(v))==0;return v.value
    try:
        assert lib.fdisbull_step(a,1)==0;ref.call('shadowrun_arena_frame',1)
        assert (get(a,'value'),get(a,'signed_value'),get(a,'data',1))==(ref.snapshot()['value'],ref.snapshot()['signed_value'],ref.snapshot()['data'][1])
        assert get(b,'value')==0
        for pad,code in ((2,2),(3,2),(4,1),(7,2)):
            assert lib.fdisbull_step(a,pad)==code
            assert (get(a,'value'),get(a,'signed_value'),get(a,'data',1),get(a,'shadowrun_arena_frame_status'))==(1,-2,255,0)
        assert lib.fdisbull_step(a,5)==0;ref.call('shadowrun_arena_frame',5)
        assert get(a,'value')==ref.snapshot()['value']
        assert lib.fdisbull_step(a,6)==0;ref.call('shadowrun_arena_frame',6)
        assert get(a,'observed')==ref.snapshot()['observed']==8
        assert lib.fdisbull_state_set(a,b'data',1,257)==0 and get(a,'data',1)==1
        assert lib.fdisbull_state_get(a,b'data',3,ctypes.byref(ctypes.c_int64()))==1
        assert lib.fdisbull_state_get(a,b'missing',0,ctypes.byref(ctypes.c_int64()))==1
        assert lib.fdisbull_reset(a)==0 and get(a,'value')==0 and get(a,'data',1)==0
        rom.write_bytes(b'x'*len(raw))
        c=ptr();assert lib.fdisbull_create(str(rom).encode(),ctypes.byref(c))==1 and not c.value
    finally:
        lib.fdisbull_destroy(a);lib.fdisbull_destroy(b)


def test_unbound_environment_refused(tmp_path):
    raw=b'rom';program=author_program("typedef unsigned char u8; u8 x; void shadowrun_arena_frame(u8 pad) { x=hv16(); }", [{'id':0,'length':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}])
    machine=GameMachine(program,{0:raw})
    with pytest.raises(ValueError,match='explicit environment adapter'):
        build_macos(program,machine.snapshot(),tmp_path/'unbound')


def test_call_depth_bound():
    from fdisbull.udc_macos import _Compiler
    def program(count):
        source='typedef unsigned char u8;\n'
        source+='\n'.join('void f%d(void) {%s}' % (i, ('f%d();' % (i+1)) if i+1<count else '') for i in reversed(range(count)))
        source+='\nvoid shadowrun_arena_frame(u8 pad) {%s}' % ('f0();' if count else '')
        return author_program(source)
    accepted=program(127);_Compiler(accepted,GameMachine(accepted).snapshot())
    rejected=program(128)
    with pytest.raises(ValueError,match='128-frame limit'):
        _Compiler(rejected,GameMachine(rejected).snapshot())


@pytest.mark.parametrize('status_name,explicit', [('snes_tick_status',False),('boundary',True)])
def test_source_specific_entry_and_atomic_boundary(tmp_path,status_name,explicit):
    raw=b'authored source adapter test'
    rom=tmp_path/'source.rom';rom.write_bytes(raw)
    program=author_program('''
        typedef unsigned char u8; typedef unsigned int u16;
        u16 position=65534U; u8 STATUS;
        void snes_tick(u8 pad) { position+=pad; if(pad==7) STATUS=2; }
    '''.replace('STATUS',status_name),
        [{'id':0,'length':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}])
    machine=GameMachine(program,{0:raw})
    options={'entry':'snes_tick'}
    if explicit:options['unsupported_status']=status_name
    out=tmp_path/'native'
    receipt=build_macos(program,machine.snapshot(),out,**options)
    assert receipt['entry']=='snes_tick' and receipt['unsupported_status']==status_name
    assert receipt['logical_input_bits']==8
    lib=ctypes.CDLL(str(out/'libfdisbull_native.dylib'))
    pointer=ctypes.c_void_p
    lib.fdisbull_create.argtypes=[ctypes.c_char_p,ctypes.POINTER(pointer)]
    lib.fdisbull_step.argtypes=[pointer,ctypes.c_uint8]
    lib.fdisbull_destroy.argtypes=[pointer]
    lib.fdisbull_state_get.argtypes=[pointer,ctypes.c_char_p,ctypes.c_uint32,ctypes.POINTER(ctypes.c_int64)]
    context=pointer()
    assert lib.fdisbull_create(str(rom).encode(),ctypes.byref(context))==0
    def get(name):
        value=ctypes.c_int64()
        assert lib.fdisbull_state_get(context,name.encode(),0,ctypes.byref(value))==0
        return value.value
    try:
        for pad in (1,3,255):
            assert lib.fdisbull_step(context,pad)==0
            machine.call('snes_tick',pad)
            assert get('position')==machine.snapshot()['position']
        before=(get('position'),get(status_name))
        assert lib.fdisbull_step(context,7)==1
        assert (get('position'),get(status_name))==before
    finally:
        lib.fdisbull_destroy(context)


def test_entry_contract_validation():
    from fdisbull.udc_macos import _Compiler
    source='typedef unsigned char u8; u8 boundary[2]; void step(void) {}'
    program=author_program(source)
    seed=GameMachine(program).snapshot()
    with pytest.raises(ValueError,match='requires entry procedure'):
        _Compiler(program,seed,entry='missing')
    with pytest.raises(ValueError,match='one integer logical pad'):
        _Compiler(program,seed,entry='step')
    valid=author_program('typedef unsigned char u8; u8 boundary[2]; void step(u8 pad) {}')
    seed=GameMachine(valid).snapshot()
    for status in ('missing','boundary'):
        with pytest.raises(ValueError,match='scalar global'):
            _Compiler(valid,seed,entry='step',unsupported_status=status)


def test_hash_bound_extra_region_and_transactional_bounds(tmp_path):
    raw=b'caller original';geometry=b'\x34\x12\x78\x56'
    bindings=[{'id':i,'length':len(data),'sha256':hashlib.sha256(data).hexdigest()}
              for i,data in ((0,raw),(1,geometry))]
    program=author_program('''
        typedef unsigned char u8; typedef unsigned int u16;
        u16 value; void scene_tick(u8 pad) {
            value=(u16)rom8(1,0)|((u16)rom8(1,1)<<8);
            if(pad) value=rom16(1,3);
        }
    ''',bindings)
    machine=GameMachine(program,{0:raw,1:geometry})
    from fdisbull.udc_macos import _Compiler
    for extras in ({},{2:geometry},{1:b'wrong'},{1:geometry,0:raw}):
        with pytest.raises(ValueError,match='immutable region'):
            _Compiler(program,machine.snapshot(),entry='scene_tick',immutable_regions=extras)
    out=tmp_path/'native'
    receipt=build_macos(program,machine.snapshot(),out,entry='scene_tick',immutable_regions={1:geometry})
    assert receipt['immutable_regions']==[
        {**bindings[0],'storage':'caller-ROM'}, {**bindings[1],'storage':'private-embedded'}]
    rom=tmp_path/'source.rom';rom.write_bytes(raw)
    lib=ctypes.CDLL(str(out/'libfdisbull_native.dylib'))
    pointer=ctypes.c_void_p
    lib.fdisbull_create.argtypes=[ctypes.c_char_p,ctypes.POINTER(pointer)]
    lib.fdisbull_step.argtypes=[pointer,ctypes.c_uint8]
    lib.fdisbull_state_get.argtypes=[pointer,ctypes.c_char_p,ctypes.c_uint32,ctypes.POINTER(ctypes.c_int64)]
    lib.fdisbull_destroy.argtypes=[pointer]
    ctx=pointer();assert lib.fdisbull_create(str(rom).encode(),ctypes.byref(ctx))==0
    try:
        assert lib.fdisbull_step(ctx,0)==0
        machine.call('scene_tick',0)
        value=ctypes.c_int64()
        assert lib.fdisbull_state_get(ctx,b'value',0,ctypes.byref(value))==0
        assert value.value==machine.snapshot()['value']==0x1234
        assert lib.fdisbull_step(ctx,1)==2
        assert lib.fdisbull_state_get(ctx,b'value',0,ctypes.byref(value))==0 and value.value==0x1234
    finally:
        lib.fdisbull_destroy(ctx)
