"""Native equivalence of the generated arena lookup and the original reader."""
import ctypes
import subprocess
import shutil
import sys

import pytest

from fdisbull.shadowrun_nes_rom_reader import emit_arena_reader


SPANS = [(0x62b0,0x63f8),(0x6ed0,0x6f30),(0x7320,0x7380),(0x77d4,0x7834),
         (0x8ec4,0x8f04),(0x8ffc,0x9004),(0x9354,0x9360),(0x9e8e,0x9e92),
         (0xa30e,0xa41e),(0xbd72,0xc082),(0x13e7c,0x13f7c),
         (0xa9c6a,0xa9c6c),(0xace14,0xace16),(0xad026,0xad028),
         (0xad238,0xad23a),(0xad24a,0xad24c),(0xad45c,0xad45e),
         (0xad46e,0xad470),(0xad600,0xad602),(0xad612,0xad614),
         (0xd4540,0xd4780),(0xd4d50,0xd4ea0),(0x166ad4,0x166ad7)]


def test_invalid_spans():
    for spans in ([], [(2,2)], [(2,3),(1,2)], [(1,4),(3,5)], [(1,8194)], [(1,2**32)], [(0,1)]):
        with pytest.raises(ValueError):
            emit_arena_reader(spans, 3)
    with pytest.raises(ValueError):
        emit_arena_reader([(1,2)], 256)


@pytest.mark.skipif(shutil.which("cc") is None, reason="native C compiler unavailable")
def test_native_reader_matches_prior_scans(tmp_path):
    reader = emit_arena_reader(SPANS, 7)
    source = '''#include <stdint.h>
#define __fastcall__
typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32;
const u8 shadowrun_arena_tables[8192] = {CONTENT};
u8 bank, fault;
void shadowrun_data_select(u8 v) {bank=v;}
''' .replace('CONTENT', ','.join(str((i*37+13)&255) for i in range(sum(b-a for a,b in SPANS))))
    source += reader.declarations
    source += '''
u8 old8(u8 region,u32 offset) {
    u8 i;if(region==0) for(i=0;i<23;i++) if(offset>=arena_lo[i] && offset<arena_hi[i]) {
        shadowrun_data_select(7);return shadowrun_arena_tables[(u16)(offset-arena_lo[i])+arena_base[i]];
    }
    fault=1;return 0;
}
u16 old16(u8 region,u32 offset) {
    u8 k;if(region!=0) {fault=1;return 0;}
    for(k=0;k<23;k++) if(offset>=arena_lo[k] && offset+1UL<arena_hi[k])
        return ((u16)old8(region,offset)<<8)|old8(region,offset+1UL);
    fault=1;return 0;
}
u8 new8(u8 region,u32 offset) {
''' + reader.byte_lookup + '''    fault=1;return 0;
}
u16 new16(u8 region,u32 offset) {
    if(region!=0) {fault=1;return 0;}
''' + reader.word_lookup + '''    fault=1;return 0;
}
u32 run(u8 which,u8 region,u32 offset) {
    u16 value;bank=99;fault=0;
    if(which==0)value=old8(region,offset);else if(which==1)value=new8(region,offset);
    else if(which==2)value=old16(region,offset);else value=new16(region,offset);
    return value|((u32)fault<<16)|((u32)bank<<24);
}
'''
    cfile=tmp_path/'reader.c';libfile=tmp_path/'reader.dylib'
    cfile.write_text(source)
    flags = ['-dynamiclib'] if sys.platform == 'darwin' else ['-shared', '-fPIC']
    subprocess.run(['cc','-std=c99',*flags,str(cfile),'-o',str(libfile)],check=True)
    lib=ctypes.CDLL(str(libfile));lib.run.argtypes=[ctypes.c_uint8,ctypes.c_uint8,ctypes.c_uint32];lib.run.restype=ctypes.c_uint32
    points={0,0xffffffff,0xfffffffe}
    for lo,hi in SPANS:
        points.update(range(lo,hi))
        points.update((lo-1,hi,hi+1))
    for region in (0,1,255):
        for address in points:
            assert lib.run(0,region,address)==lib.run(1,region,address), (region,address,'byte')
            assert lib.run(2,region,address)==lib.run(3,region,address), (region,address,'word')
