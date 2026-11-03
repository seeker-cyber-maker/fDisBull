#!/usr/bin/env python3
"""Check already-generated authored SH-2 translator outputs; never runs a game."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from fdisbull.rom_asm import disassemble_rom
from fdisbull.interaction_il import execute_il
from fdisbull.rom_semantics import lift_sh2, lift_ghidra_c, lift_saturn_cpp, compare


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sh2', type=Path, required=True)
    p.add_argument('--ghidra-c', type=Path, required=True)
    p.add_argument('--saturn-cpp', type=Path, required=True)
    p.add_argument('--ghidra-home', required=True)
    p.add_argument('--saturn-root', type=Path, required=True)
    p.add_argument('--cc', default='cc')
    p.add_argument('--cxx', default='c++')
    args = p.parse_args()
    root = args.saturn_root.resolve()
    revision = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != '532fd6054ba3171339c972fab05ebd159f29260d':
        raise ValueError('unsupported saturn-recomp revision')
    dirty = subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain', '--', 'src/saturnrecomp', 'runtime/include/saturn/sh2.h'], text=True)
    if dirty:
        raise ValueError('saturn-recomp source modified')
    header = (root/'runtime/include/saturn/sh2.h').read_bytes()
    if b'uint32_t r[16]' not in header:
        raise ValueError('unexpected register type')
    code = args.sh2.read_bytes()
    expected = [('mov', 'r4,r0'), ('add', '#1,r0'), ('rts', ''), ('nop', '')]
    decodes = {}
    for backend in ('capstone', 'ghidra', 'saturn-recomp'):
        report = disassemble_rom(code, base_address=0x06010000, backend=backend, length=8, max_instructions=4,
                                 mode='linear', ghidra_home=args.ghidra_home, saturn_recomp_root=str(root))
        if [(i['normalized']['mnemonic'], i['normalized']['operands']) for i in report['instructions']] != expected:
            raise ValueError('unexpected decoder output: ' + backend)
        decodes[backend] = report
    c, cpp = args.ghidra_c.read_text(), args.saturn_cpp.read_text()
    asm, ghidra, saturn = lift_sh2(code), lift_ghidra_c(c), lift_saturn_cpp(cpp)
    proofs = {'sh2_to_ghidra': compare(asm, ghidra), 'sh2_to_saturn': compare(asm, saturn)}
    mutant = lift_ghidra_c('uint authored(uint value) { return value + 2; }')
    proofs['negative_mutant'] = compare(asm, mutant)
    if any(proofs[k]['status'] != 'equivalent_under_assumptions' for k in ('sh2_to_ghidra', 'sh2_to_saturn')) or proofs['negative_mutant']['status'] != 'counterexample':
        raise RuntimeError('proof gate did not pass')
    versions = {tool: subprocess.check_output([tool, '--version'], text=True, stderr=subprocess.STDOUT).splitlines()[0] for tool in (args.cc, args.cxx)}
    with tempfile.TemporaryDirectory(prefix='rom-semantic-route-', dir='/tmp') as tmp:
        d = Path(tmp)
        # Ghidra's uint alias is an explicit 32-bit ABI assumption.
        (d/'ghidra.c').write_text('#include <stdint.h>\n#include <inttypes.h>\n#include <stdio.h>\ntypedef uint32_t uint;\n' + c + '\nint main(void) { uint32_t x[]={0,0x7fffffffU,0xffffffffU}; for(int i=0;i<3;i++) printf("%" PRIu32 "\\n",authored(x[i])); }\n')
        (d/'p_typed_funcs.h').write_text('#include <cstdint>\nstruct SH2Context { uint32_t r[16] = {}; uint32_t pr = 0; uint32_t pc = 0; };\nnamespace p_typed { inline int ran[1] = {}; }\n')
        (d/'saturn.cpp').write_text(cpp + '\n#include <cstdio>\n#include <cinttypes>\nint main() { uint32_t a[]={0,0x7fffffffU,0xffffffffU}; for(auto x:a) { SH2Context c; c.r[4]=x; p_typed::f_06010000(c); std::printf("%" PRIu32 "\\n",c.r[0]); } }\n')
        compile_source_hashes = {name: hashlib.sha256((d/name).read_bytes()).hexdigest() for name in ('ghidra.c', 'saturn.cpp', 'p_typed_funcs.h')}
        commands = [[args.cc, '-std=c11', str(d/'ghidra.c'), '-o', str(d/'c')], [args.cxx, '-std=c++17', str(d/'saturn.cpp'), '-o', str(d/'cpp')]]
        for cmd in commands:
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
        values = [0, 0x7fffffff, 0xffffffff]
        native = {name: [int(x) for x in subprocess.check_output([str(d/name)], text=True, timeout=10).splitlines()] for name in ('c', 'cpp')}
        uil = [execute_il(asm['uil'], {'$r0': 0, '$r4': x})['state']['$r0'] for x in values]
        if native['c'] != uil or native['cpp'] != uil:
            raise RuntimeError('native edge outputs differ from UIL')
    print(json.dumps({'format': 'fdisbull-authored-rom-semantic-experiment-1', 'lifts': [asm, ghidra, saturn], 'proofs': proofs,
                      'decodes': decodes, 'compiler_versions': versions, 'compile_commands': commands, 'compiled_source_sha256': compile_source_hashes,
                      'generation_recipe': 'scripts/rom_semantic_route/README.md',
                      'ghidra_generator_sha256': hashlib.sha256((Path(__file__).resolve().parent/'rom_semantic_route/DecompileAuthoredSh2.java').read_bytes()).hexdigest(),
                      'saturn_revision': revision, 'saturn_sh2_header_sha256': hashlib.sha256(header).hexdigest(),
                      'native_edge_inputs': values, 'native_edge_outputs': native, 'uil_edge_outputs': uil,
                      'limitations': ['ABI and uint32 type bindings are assumed', 'proof compares parsed arithmetic models, not native execution for all inputs', 'return control, instrumentation, memory, flags, timing, other registers and game behavior excluded']}, indent=2))


if __name__ == '__main__':
    main()
