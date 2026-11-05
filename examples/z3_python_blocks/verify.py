#!/usr/bin/env python3
"""Private differential check: generated Python vs the retained reference model.

This isolates the code-generation and container edges. It is not an independent
original-interpreter proof. Source, outputs and complete state stay private.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from fdisbull.zork_uil import compile_story
from fdisbull_player.word16 import Word16Runtime


def compare(story,product,routes,out):
    sys.path.insert(0,str(product.resolve()))
    from runtime import DirectGame
    from asset_package import canonical,sha
    before=sha(story.read_bytes())
    program,_=compile_story(story)
    result={'format':'fdisbull-z3-python-differential-1','source_sha256':before,
            'product_sha256':sha((product/'product.json').read_bytes()),
            'oracle':'unchanged fDisBull 0.31.1 word16 model',
            'independent_original_interpreter':'not-run','routes':[]}
    for route in routes:
        b,g=Word16Runtime(program,seed=route['seed']),DirectGame(product,seed=route['seed'])
        matches=0;total_steps=0;ticks=[]
        # Compare complete state including RNG, frames, stream state and game SAVE slot.
        actual,expected=g.run(),b.run()
        assert actual==expected,'startup result mismatch'
        assert g.snapshot()==b.snapshot(),'startup state mismatch'
        matches+=1;total_steps+=actual['steps']
        t0=time.monotonic()
        for command in route['commands']:
            if actual['status']!='input':raise AssertionError('route stopped before command '+command)
            actual,expected=g.command(command),b.command(command)
            assert actual==expected,'result mismatch at '+command
            assert g.snapshot()==b.snapshot(),'state mismatch at '+command
            matches+=1;total_steps+=actual['steps']
            ticks.append({'result_sha256':sha(canonical(actual)),'state_sha256':sha(canonical(g.snapshot()))})
        # Transfer a fully typed memory container into a new runtime instance.
        restored=DirectGame(product,seed=999)
        restored.restore_memory_container(g.memory_container())
        assert restored.snapshot()==g.snapshot(),'live memory roundtrip mismatch'
        result['routes'].append({'name':route['name'],'seed':route['seed'],
            'commands':len(route['commands']),'matched_boundaries':matches,
            'executed_steps':total_steps,'unique_python_blocks':len(g.executed_blocks),
            'python_modules_loaded':len(g._shards),'asset_hits':g.asset_hits,'codec_misses':g.codec_misses,
            'codec_calls':g.codec_calls,'memory_roundtrip':True,
            'final_state_sha256':sha(canonical(g.snapshot())),
            'per_command_hashes':ticks,'paired_execution_seconds':round(time.monotonic()-t0,6)})
    assert sha(story.read_bytes())==before,'original changed'
    result['source_unchanged']=True
    out.write_bytes(canonical(result))
    print(json.dumps({k:v for k,v in result.items() if k!='routes'},indent=2))
    for r in result['routes']:print(json.dumps({k:v for k,v in r.items() if k!='per_command_hashes'}))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('story',type=Path);ap.add_argument('product',type=Path)
    ap.add_argument('routes',type=Path);ap.add_argument('output',type=Path)
    a=ap.parse_args()
    if a.output.exists():raise ValueError('Fresh verification output required')
    if any((p/'.git').exists() for p in a.output.resolve().parents):raise ValueError('Private receipts stay outside Git')
    compare(a.story,a.product,json.loads(a.routes.read_text()),a.output)

if __name__=='__main__':main()
