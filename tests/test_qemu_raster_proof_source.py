"""Compile the exact new native admission/copy helper, without a guest.

This is a source contract probe. Native renderer routing, dirty-cache behavior,
reset and checkpoint invalidation are tested separately on the real producer.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

import pytest


PACKAGE = Path(__file__).resolve().parents[1] / 'native/qemu-raster-proof'


@pytest.fixture(scope='module')
def raster_probe(tmp_path_factory):
    compiler = shutil.which('cc')
    if compiler is None:
        pytest.skip('C compiler required for native source contract probe')
    manifest = json.loads((PACKAGE / 'source-manifest.json').read_text())
    patch = (PACKAGE / manifest['patch']).read_bytes()
    assert hashlib.sha256(patch).hexdigest() == manifest['patch_sha256']
    lines = patch.decode().splitlines(keepends=True)
    begin = next(i for i, line in enumerate(lines)
                 if line == '+++ b/hw/display/fdisbull-raster.h\n') + 1
    end = next((i for i in range(begin, len(lines))
                if lines[i].startswith('--- ')), len(lines))
    header = ''.join(line[1:] for line in lines[begin:end]
                     if line.startswith('+') and not line.startswith('+++')).encode()
    member = next(item for item in manifest['files']
                  if item['path'] == 'hw/display/fdisbull-raster.h')
    assert hashlib.sha256(header).hexdigest() == member['patched_sha256']
    directory = tmp_path_factory.mktemp('raster-source')
    (directory / 'fdisbull-raster.h').write_bytes(header)
    source = directory / 'probe.c'
    source.write_text(r'''
#include <assert.h>
#include <limits.h>
#include <stdlib.h>
#include <stdio.h>
#include "fdisbull-raster.h"

static FdisbullChain4Geometry valid(void) {
    return (FdisbullChain4Geometry) {
        .display_enabled=true,.graphics=true,.chain4=true,
        .width=640,.height=400,.depth=0,.shift_control=2,.multi_scan=1,
        .crtc_mode=0xa3,.attribute_mode=0x41,.plane_enable=15,
        .line_offset=320,.line_compare=1023,.vram_size=262144
    };
}
static void rejected(FdisbullChain4Geometry g) {
    assert(fdisbull_chain4_admission(&g) != NULL);
}

static uint8_t indices[64000], rgb[640*400*3], src[320*200*3];
static uint32_t pixels[640*400], palette[256];
static void image(void) {
    unsigned i,x,y;
    for(i=0;i<256;i++) palette[i]=(i<<16)|((255-i)<<8)|(i^0x5a);
    palette[1]=0x0757a8;
    for(i=0;i<64000;i++) indices[i]=(i*17+1)%256;
    for(y=0;y<400;y++) for(x=0;x<640;x++)
        pixels[y*640+x]=0xff000000|palette[indices[(y/2)*320+x/2]];
    memset(rgb,0xa5,sizeof(rgb)); memset(src,0xa5,sizeof(src));
}
static bool copy(void) {
    return fdisbull_chain4_copy_verify((const uint8_t*)pixels,sizeof(pixels),
        indices,sizeof(indices),palette,rgb,sizeof(rgb),src,sizeof(src));
}
int main(int argc,char**argv) {
    FdisbullChain4Geometry g;
    unsigned i,x,y;
    assert(argc==2);
    if(!strcmp(argv[1],"admitted")) {
        g=valid(); assert(!fdisbull_chain4_admission(&g));
        g.vram_size=64000; g.line_compare=400;
        assert(!fdisbull_chain4_admission(&g));
    } else if(!strcmp(argv[1],"mode")) {
        g=valid();g.display_enabled=false;rejected(g);
        g=valid();g.graphics=false;rejected(g);
        g=valid();g.vbe_enabled=true;rejected(g);
        g=valid();g.chain4=false;rejected(g);
        g=valid();g.depth=8;rejected(g);
        g=valid();g.shift_control=3;rejected(g);
        g=valid();g.crtc_mode&=~1u;rejected(g);
        g=valid();g.crtc_mode&=~2u;rejected(g);
        g=valid();g.attribute_mode=0x61;rejected(g);
        g=valid();g.plane_enable=7;rejected(g);
    } else if(!strcmp(argv[1],"extent")) {
        g=valid();g.width=0;rejected(g);
        g=valid();g.width=INT_MAX;rejected(g);
        g=valid();g.width=638;rejected(g);
        g=valid();g.height=-1;rejected(g);
        g=valid();g.height=INT_MAX;rejected(g);
        g=valid();g.multi_scan=0;rejected(g);
        g=valid();g.multi_scan=2;rejected(g);
        g=valid();g.vram_size=63999;rejected(g);
    } else if(!strcmp(argv[1],"address")) {
        g=valid();g.start_address=4;rejected(g);
        g=valid();g.start_address=UINT64_MAX;rejected(g);
        g=valid();g.bank_offset=-1;rejected(g);
        g=valid();g.bank_offset=65536;rejected(g);
        g=valid();g.line_offset=0;rejected(g);
        g=valid();g.line_offset=UINT64_MAX;rejected(g);
        g=valid();g.line_compare=399;rejected(g);
        g=valid();g.hpel=1;rejected(g);
    } else if(!strcmp(argv[1],"copy")) {
        image(); assert(copy());
        for(y=0;y<400;y++) for(x=0;x<640;x++) {
            uint32_t c=palette[indices[(y/2)*320+x/2]];
            const uint8_t*p=rgb+(y*640+x)*3;
            assert(p[0]==(c>>16) && p[1]==((c>>8)&255) && p[2]==(c&255));
        }
        for(i=0;i<64000;i++) {
            uint32_t c=palette[indices[i]];
            assert(src[i*3]==(c>>16) && src[i*3+1]==((c>>8)&255) && src[i*3+2]==(c&255));
        }
        assert(src[0]==7 && src[1]==87 && src[2]==168);
    } else if(!strcmp(argv[1],"partial")) {
        const unsigned offsets[]={0,1,640,640*200,640*399,640*400-1};
        for(i=0;i<sizeof(offsets)/sizeof(offsets[0]);i++) {
            image();pixels[offsets[i]]^=1;assert(!copy());
        }
    } else if(!strcmp(argv[1],"source")) {
        image();indices[63999]^=1;assert(!copy());
        image();palette[indices[63999]]^=1;assert(!copy());
    } else if(!strcmp(argv[1],"bounds")) {
        image();
        assert(!fdisbull_chain4_copy_verify((const uint8_t*)pixels,sizeof(pixels)-1,
            indices,sizeof(indices),palette,rgb,sizeof(rgb),src,sizeof(src)));
        assert(!fdisbull_chain4_copy_verify((const uint8_t*)pixels,sizeof(pixels),
            indices,sizeof(indices)-1,palette,rgb,sizeof(rgb),src,sizeof(src)));
        assert(!fdisbull_chain4_copy_verify((const uint8_t*)pixels,sizeof(pixels),
            indices,sizeof(indices),palette,rgb,sizeof(rgb)-1,src,sizeof(src)));
        assert(!fdisbull_chain4_copy_verify((const uint8_t*)pixels,sizeof(pixels),
            indices,sizeof(indices),palette,rgb,sizeof(rgb),src,sizeof(src)-1));
        for(i=0;i<sizeof(rgb);i++)assert(rgb[i]==0xa5);
        for(i=0;i<sizeof(src);i++)assert(src[i]==0xa5);
    } else if(!strcmp(argv[1],"null")) {
        image();assert(!fdisbull_chain4_copy_verify(NULL,sizeof(pixels),
            indices,sizeof(indices),palette,rgb,sizeof(rgb),src,sizeof(src)));
        assert(!fdisbull_chain4_copy_verify((const uint8_t*)pixels,sizeof(pixels),
            NULL,sizeof(indices),palette,rgb,sizeof(rgb),src,sizeof(src)));
        assert(!fdisbull_chain4_copy_verify((const uint8_t*)pixels,sizeof(pixels),
            indices,sizeof(indices),NULL,rgb,sizeof(rgb),src,sizeof(src)));
    } else return 2;
    puts("source contract passed");
    return 0;
}
''')
    binary = directory / 'probe'
    result = subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra',
                             '-Werror', str(source), '-o', str(binary)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    return binary


@pytest.mark.parametrize('case', ['admitted', 'mode', 'extent', 'address',
                                 'copy', 'partial', 'source', 'bounds', 'null'])
def test_actual_native_raster_helper(raster_probe, case):
    result = subprocess.run([str(raster_probe), case], capture_output=True,
                            text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == 'source contract passed\n'
