"""Internal IP/TF writes send control groups without unrelated context state."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_native_control_setter_preserves_input_and_limits_both_architecture_masks(tmp_path):
    compiler=shutil.which('cc')
    if compiler is None:pytest.skip('C compiler required for native context-mask contract')
    source=(Path(__file__).resolve().parents[1]/'src/fdisbull/wine_guest/agent.c').read_text()
    first=source.index('static void setcontrolcontext(')
    end=source.index('\n}',first)+2
    function=source[first:end]
    harness=r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
enum { WOW64_CONTEXT_CONTROL=0x10001, CONTEXT_CONTROL=0x100001 };
typedef struct { uint32_t ContextFlags; unsigned char registers[128]; } Context;
typedef struct { Context native, wow; } TargetContext;
static int target_bits, calls;
static TargetContext delivered;
static void setcontext(TargetContext *value) { delivered=*value; ++calls; }
''' + function + r'''
int main(void) {
    TargetContext original, before, expected;
    memset(&original,0xa5,sizeof(original));
    original.wow.ContextFlags=0x10007;
    original.native.ContextFlags=0x10000b;
    before=original;
    target_bits=32;
    setcontrolcontext(&original);
    expected=before; expected.wow.ContextFlags=WOW64_CONTEXT_CONTROL;
    assert(calls==1 && memcmp(&delivered,&expected,sizeof(expected))==0);
    assert(memcmp(&original,&before,sizeof(original))==0);
    target_bits=64;
    setcontrolcontext(&original);
    expected=before; expected.native.ContextFlags=CONTEXT_CONTROL;
    assert(calls==2 && memcmp(&delivered,&expected,sizeof(expected))==0);
    assert(memcmp(&original,&before,sizeof(original))==0);
}
'''
    path=tmp_path/'context-mask.c';path.write_text(harness)
    binary=tmp_path/'context-mask'
    subprocess.run([compiler,'-std=c99','-Wall','-Wextra','-Werror',str(path),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
