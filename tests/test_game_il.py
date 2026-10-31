import copy
import hashlib
import os
from pathlib import Path
import subprocess
import pytest

pytest.importorskip('pycparser')
from fdisbull.game_il import GameMachine, author_program, canonical, emit_c, validate_program

HEADER = '''typedef unsigned char u8; typedef signed char i8;
typedef unsigned short u16; typedef signed short i16;
typedef unsigned long u32; typedef signed long i32;
u8 rom8(u8 r,u32 p);u16 rom16(u8 r,u32 p);u32 rom32(u8 r,u32 p);
void emit(u8 k,u8 i);u16 hv16(void);u8 sound_busy(void);
'''


def machine(body, **kwargs):
    return GameMachine(author_program(HEADER + body), **kwargs)


def test_integer_model_is_target_abi_not_host_abi():
    m = machine('''u8 a;u16 b;u32 c;i8 d;i16 e;i32 f;
    void run(void){a=(u8)(250+10);b=(u16)(65535U+2U);
    c=0xFFFFFFFFUL+2UL;d=(i8)255;e=(i16)0x8000;
    f=(i32)-7/3;}''')
    m.call('run')
    assert m.snapshot() == dict(a=4,b=1,c=1,d=-1,e=-32768,f=-2)


def test_unsigned_promotion_and_signed_shift():
    m = machine('''u8 a;u8 b;i16 c;u32 d;
    void run(void){a=((u16)65535 < (i16)-1);b=((u32)65535 < (i32)-1);
    c=((i16)-8)>>2;d=((u32)65535)*65535UL;}''')
    m.call('run')
    assert m.snapshot() == dict(a=0,b=1,c=-2,d=4294836225)


def test_procedures_loops_arrays_and_tree_round_trip():
    p = author_program(HEADER + '''u8 data[4];u8 total;
    u8 twice(u8 n){return (u8)(n*2);}
    void run(void){u8 i;for(i=0;i<4;i=i+1){data[i]=twice(i);}
    total=data[0]+data[1]+data[2]+data[3];}''')
    q = author_program(emit_c(p))
    assert canonical(p) == canonical(q)
    m = GameMachine(q);m.call('run')
    assert m.snapshot() == dict(data=[0,2,4,6],total=12)


def test_bounds_failure_restores_state_events_and_environment_cursor():
    m = machine('''u8 data[2];u16 value;
    void bad(void){data[0]=7;value=hv16();emit(1,2);data[2]=9;}''', environment={'hv16':[100,200]})
    before=m.snapshot()
    with pytest.raises(ValueError,match='out of bounds'):m.call('bad')
    assert m.snapshot()==before and m.events==[] and m.environment_cursor=={}


def test_recorded_environment_never_repeats_when_exhausted():
    m = machine('u16 x;void run(void){x=hv16();}',environment={'hv16':[123,456]})
    m.call('run');assert m.snapshot()['x']==123
    m.call('run');assert m.snapshot()['x']==456
    with pytest.raises(ValueError,match='exhausted'):m.call('run')
    assert m.snapshot()['x']==456


def test_region_hash_and_big_endian_word_contract():
    raw=bytes.fromhex('12345678')
    p=author_program(HEADER+'u32 x;void run(void){x=rom32(0,0);}',
                     [{'id':0,'length':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}])
    with pytest.raises(ValueError,match='binding'):GameMachine(p,{0:b'\0'*4})
    m=GameMachine(p,{0:raw});m.call('run');assert m.snapshot()['x']==0x12345678


def test_recursion_indirect_calls_pointers_and_unbounded_execution_rejected():
    with pytest.raises(ValueError,match='Recursive'):author_program(HEADER+'void f(void){f();}')
    with pytest.raises(ValueError,match='PtrDecl'):author_program(HEADER+'u8 *p;')
    m=machine('void run(void){for(;;){}}')
    with pytest.raises(ValueError,match='budget'):m.call('run',max_steps=100)


def test_serialized_tree_is_not_an_unchecked_c_injection_container():
    p=author_program(HEADER+'u8 x;void run(void){x=1;}')
    q=copy.deepcopy(p)
    q['tree']['ext'][-1]['body']['block_items'][0]['lvalue']['name']='x; malicious()'
    with pytest.raises(ValueError,match='identifier'):validate_program(q)


@pytest.mark.parametrize(('expression','after','result'),[
    ('data[index++]++',5,4),('++data[index++]',5,5),
    ('data[index++]--',3,4),('--data[index++]',3,3),
])
def test_incremented_array_lvalue_is_evaluated_once(expression,after,result):
    m=machine('u8 data[2]={4,8};u8 index;u8 result;'
              'void run(void){result='+expression+';}')
    m.call('run')
    assert m.snapshot()==dict(data=[after,8],index=1,result=result)


def test_array_postincrement_agrees_with_independent_native_6502(tmp_path):
    root=Path(os.environ.get('FDISBULL_CC65_ROOT',''))
    compiler,simulator=root/'bin/cl65',root/'bin/sim65'
    if not compiler.is_file() or not simulator.is_file():
        pytest.skip('prepared private cc65/sim65 toolchain required')
    source=('typedef unsigned char u8;u8 data[2]={4,8};u8 index;u8 result;'
            'void run(void){result=data[index++]++;}')
    m=GameMachine(author_program(source));m.call('run')
    native_source=tmp_path/'array-postincrement.c'
    native_source.write_text('#include <stdio.h>\n'+source+
        '\nint main(void){run();printf("%u %u %u %u\\n",'
        'data[0],data[1],index,result);return 0;}\n')
    executable=tmp_path/'array-postincrement'
    subprocess.run([str(compiler),'-t','sim6502','-Oirs','-o',str(executable),
                    str(native_source)],check=True,capture_output=True,timeout=30)
    native=subprocess.run([str(simulator),str(executable)],check=True,
                          capture_output=True,text=True,timeout=30)
    assert tuple(map(int,native.stdout.split()))==(5,8,1,4)
    assert m.snapshot()==dict(data=[5,8],index=1,result=4)


@pytest.mark.parametrize('storage',['static','extern'])
def test_procedure_local_persistent_storage_is_rejected(storage):
    source=('typedef unsigned char u8;u8 n;u8 take(void){'
            +storage+' u8 n;return ++n;}')
    with pytest.raises(ValueError,match='procedure-local static/extern'):
        author_program(source)


def test_static_global_storage_and_function_linkage_remain_supported():
    m=machine('static u8 n;u8 first;u8 second;'
              'static u8 take(void){return ++n;}'
              'void run(void){first=take();second=take();}')
    m.call('run')
    assert m.snapshot()==dict(n=2,first=1,second=2)


def test_rejected_static_counter_has_persistent_native_6502_semantics(tmp_path):
    root=Path(os.environ.get('FDISBULL_CC65_ROOT',''))
    compiler,simulator=root/'bin/cl65',root/'bin/sim65'
    if not compiler.is_file() or not simulator.is_file():
        pytest.skip('prepared private cc65/sim65 toolchain required')
    source=('typedef unsigned char u8;u8 first;u8 second;'
            'u8 take(void){static u8 n;return ++n;}'
            'void run(void){first=take();second=take();}')
    with pytest.raises(ValueError,match='procedure-local static/extern'):
        author_program(source)
    native_source=tmp_path/'static-counter.c'
    native_source.write_text('#include <stdio.h>\n'+source+
        '\nint main(void){run();printf("%u %u\\n",first,second);return 0;}\n')
    executable=tmp_path/'static-counter'
    subprocess.run([str(compiler),'-t','sim6502','-Oirs','-o',str(executable),
                    str(native_source)],check=True,capture_output=True,timeout=30)
    native=subprocess.run([str(simulator),str(executable)],check=True,
                          capture_output=True,text=True,timeout=30)
    assert tuple(map(int,native.stdout.split()))==(1,2)
