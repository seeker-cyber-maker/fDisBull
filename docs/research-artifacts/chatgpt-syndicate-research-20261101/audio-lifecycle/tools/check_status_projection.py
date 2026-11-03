"""Check a source-informed partial-register model, not game reachability.

Requires the separately installed z3-solver. No original input bytes are used.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import z3


def check() -> dict:
    eax = z3.BitVec('eax_before_projection', 32)
    equal_bit = z3.If(eax == 1, z3.BitVecVal(1, 8), z3.BitVecVal(0, 8))
    after_sete_al = z3.Concat(z3.Extract(31, 8, eax), equal_bit)
    after_xor_ah = z3.Concat(z3.Extract(31, 16, after_sete_al), z3.BitVecVal(0, 8), z3.Extract(7, 0, after_sete_al))
    expected = z3.If(eax == 1, z3.BitVecVal(1, 32), z3.BitVecVal(0, 32))
    solver = z3.Solver()
    solver.add(z3.Or(eax == 0, eax == 1, eax == 2), after_xor_ah != expected)
    valid = str(solver.check())
    solver = z3.Solver()
    solver.add(eax == 0xffffffff, after_xor_ah != 0)
    sentinel = str(solver.check())
    if valid != 'unsat' or sentinel != 'sat':
        raise RuntimeError(f'Unexpected solver results: {valid}, {sentinel}')
    result = solver.model().eval(after_xor_ah).as_long()
    if result != 0xffff0000:
        raise RuntimeError('Unexpected sentinel projection')
    return {
        'scope': 'Source-informed CMP/SETE AL/XOR AH model, not original-code execution or normal-game reachability.',
        'main_preferred_helper': '0x3ba10',
        'valid_status_domain': [0, 1, 2],
        'valid_domain_mismatch_solver_result': valid,
        'sentinel': {'eax_in': '0xffffffff', 'eax_out': hex(result), 'nonzero_solver_result': sentinel},
        'driver_sentinel_handle': '0xffffffff',
        'z3_version': z3.get_version_string(),
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'interpretation': 'Finite valid statuses project correctly. The driver sentinel does not become full-width false. No ordinary caller path supplying that sentinel was established.',
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = check()
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
