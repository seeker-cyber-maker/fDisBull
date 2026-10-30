#!/usr/bin/env python3
"""Time the existing bounded ASM/C readers on authored register examples.

This is a representation-cost probe, not a general decompiler benchmark. The
already-rendered C path excludes the cost of deriving that C from machine code;
the round-trip path includes it. Imports, native execution and analyst effort
are outside these in-process timings. No proprietary inputs are required.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import platform
import statistics
import time

from fdisbull.interaction_il import execute_il
from fdisbull.udl_blocks import asm_to_c, lift_asm_block, lift_c_block, verify_block


def measure(call, *, iterations, batches):
    call()  # Explicit unmeasured warm-up.
    samples = []
    for _ in range(batches):
        start = time.perf_counter_ns()
        for _ in range(iterations): call()
        samples.append((time.perf_counter_ns()-start)/iterations/1_000_000)
    return {'unit':'ms_per_call','iterations_per_batch':iterations,'batches':batches,
            'median':statistics.median(samples),'minimum':min(samples),'maximum':max(samples),
            'batch_means':samples}


def run(iterations=100, batches=5):
    reports = []
    for pairs in (1,8):
        # Each pair adds200 then subtracts1: unsigned16 output=(input+199*pairs)%65536.
        raw = bytes.fromhex('05c80048')*pairs
        binding = {'ax':'$value'}
        def from_asm(): return lift_asm_block(raw,binding,inputs=['ax'],outputs=['ax'])
        lifted = from_asm(); text = asm_to_c(lifted)['text']
        def from_c(): return lift_c_block(text,binding,inputs=['ax'],outputs=['ax'])
        def through_c():
            view = asm_to_c(from_asm())
            return lift_c_block(view['text'],binding,inputs=['ax'],outputs=['ax'])
        c_lift = from_c()
        cases = []
        for initial in (0,1,65535,65536-199*pairs):
            expected = (initial+199*pairs)%65536
            a = execute_il(lifted['uil'],{'$value':initial})
            c = execute_il(c_lift['uil'],{'$value':initial})
            if a['state']['$value'] != expected or c['state']['$value'] != expected:
                raise AssertionError('Reader disagrees with independently calculated uint16 output')
            cases.append({'input':initial,'expected':expected,'passed':True})
        proof = verify_block(lifted,c_lift['uil'])
        altered = copy.deepcopy(c_lift['uil']); altered['body'][0]['value'] += 1
        wrong = verify_block(lifted,altered)
        if proof['status']=='equivalent_under_assumptions' and wrong['status']!='counterexample':
            raise AssertionError('Changed arithmetic was not detected')
        reports.append({'instructions':2*pairs,'source_bytes':len(raw),'c_characters':len(text),
            'authored_source_hex':raw.hex(),'derived_c':text,'semantic_cases':cases,
            'asm_bytes_to_il':measure(from_asm,iterations=iterations,batches=batches),
            'already_available_c_to_il':measure(from_c,iterations=iterations,batches=batches),
            'asm_bytes_through_c_to_il':measure(through_c,iterations=iterations,batches=batches),
            'proof_status':proof['status'],'altered_candidate_status':wrong['status']})
    return {'format':'fdisbull-representation-path-benchmark-1','python':platform.python_version(),
            'platform':platform.system()+' '+platform.machine(),'cases':reports,
            'scope':'Existing straight-line uint16 register subset; authored examples only',
            'limits':['Warm in-process batch means; not end-to-end scene recovery',
                      'Already available C excludes decompilation',
                      'Derived C shares the ASM decoder; no independent source proof',
                      'No memory, branch, flags, ABI, timing, host effects or native execution',
                      'No measured human/agent interpretation speed or general C-decompiler comparison']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--iterations',type=int,default=100)
    parser.add_argument('--batches',type=int,default=5)
    args=parser.parse_args()
    if not 1 <= args.iterations <= 10000 or not 1 <= args.batches <= 100:
        parser.error('Use 1..10000 iterations and 1..100 batches')
    result=run(args.iterations,args.batches)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'cases':len(result['cases']),
                      'proof_statuses':[c['proof_status'] for c in result['cases']],
                      'output':str(args.output)}))
