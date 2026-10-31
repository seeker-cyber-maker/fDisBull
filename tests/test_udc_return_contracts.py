"""Authored scalar callees preserve typed return values across native adapters."""
import struct

import pytest

from fdisbull.udc_shell import _Code, _module
from fdisbull.udc_c import lower_c_module


@pytest.mark.parametrize('backend', ['uil', 'c-adapter'])
@pytest.mark.parametrize('typ,value', [('i16', -32768), ('i16', -1), ('i16', 0),
                                      ('i16', 32767), ('u16', 65535), ('u8', 255), ('bool', True)])
def test_native_module_return_retains_declared_type(backend, typ, value):
    unicorn = pytest.importorskip('unicorn')
    from unicorn.x86_const import UC_X86_REG_RAX, UC_X86_REG_RDX, UC_X86_REG_RCX, UC_X86_REG_RSP
    base, arena, stack, stop = 0x100000, 0x200000, 0x300000, 0x400000
    variables = {'$answer': {'type': typ, 'initial': value}}
    module = {'backend': 'uil', 'program': {'format': 'fdisbull-il-1', 'role': 'uil',
              'variables': variables, 'resources': {}, 'body': []}, 'return': '$answer'}
    code = _Code(base, 'test')
    if backend == 'uil':
        _module(code, module, variables, {'$answer': 0})
    else:
        # The generated-C ABI packs status in the upper word and raw result
        # in the lower word. This authored callee isolates the port adapter.
        raw = b'\x48\xb8' + struct.pack('<Q', int(value) & 65535) + b'\xc3'
        lower_c_module(code, module, variables, {'$answer': 0},
                       {'inputs': [], 'outputs': [], 'code_hex': raw.hex(),
                        'code_size': len(raw), 'source_sha256': '0' * 64})
    uc = unicorn.Uc(unicorn.UC_ARCH_X86, unicorn.UC_MODE_64)
    for address in (base, arena, stack, stop): uc.mem_map(address, 0x10000)
    uc.mem_write(base, code.resolve({}))
    uc.mem_write(arena, struct.pack('<H', int(value) & 65535))
    sp = stack + 0x8008
    uc.mem_write(sp, struct.pack('<Q', stop))
    uc.reg_write(UC_X86_REG_RSP, sp)
    uc.reg_write(UC_X86_REG_RCX, arena)
    uc.emu_start(base, stop, count=1000)
    assert uc.reg_read(UC_X86_REG_RDX) == 0
    assert uc.reg_read(UC_X86_REG_RAX) == int(value) % (1 << 64)


@pytest.mark.parametrize('backend', ['uil', 'c-uil'])
@pytest.mark.parametrize('value', [-32768, -1, 0, 32767])
def test_actual_linux_caller_accepts_signed_module_result(tmp_path, backend, value):
    import shutil
    from fdisbull.udc_linux import build_linux_shell, decode_observation
    from test_udc_linux import run_native_linux
    compiler = shutil.which('clang')
    if backend == 'c-uil' and not compiler: pytest.skip('Explicit clang required')
    variables = {'$answer': {'type': 'i16', 'initial': value}}
    module = {'backend': backend, 'program': {'format': 'fdisbull-il-1', 'role': 'uil',
              'variables': variables, 'resources': {}, 'body': []}, 'return': '$answer'}
    plan = {'format': 'fdisbull-native-shell-1', 'entry': 'main',
            'state': {'$answer': {'type': 'i16', 'initial': value},
                      '$result': {'type': 'i16', 'initial': 123}}, 'resources': {},
            'functions': {'main': {'body': [{'op': 'call', 'binding': 'math', 'result': '$result'}]}}}
    build = build_linux_shell(plan, {'math': module}, tmp_path / 'native',
                              capture_state=True, c_compiler=compiler)
    run, frame = run_native_linux(tmp_path / 'native/program', tmp_path)
    decoded = decode_observation(frame, build)
    assert run.returncode == decoded['status'] == 0
    assert decoded['state']['$result'] == value
