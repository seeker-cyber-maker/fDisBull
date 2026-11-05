#!/usr/bin/env python3
"""Run generated Python game code. No fDisBull installation or story file needed."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

# -I permits no ambient project imports. Only this product directory is admitted.
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from runtime import DirectGame
from asset_package import PackageError, canonical, parse_json, sha
from state_services import Word16Error, MAX_CHECKPOINT_BYTES


def read_json(path,limit):
    with Path(path).open('rb') as f:data=f.read(limit+1)
    if len(data)>limit:raise ValueError('JSON input exceeds size limit')
    return parse_json(data)


def atomic(path,value):
    path=Path(path)
    payload=canonical(value)
    if len(payload)>MAX_CHECKPOINT_BYTES:raise ValueError('Output exceeds size limit')
    fd,name=tempfile.mkstemp(dir=path.parent,prefix='.z3-state-')
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(payload)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--commands',type=Path,help='JSON list of input commands')
    ap.add_argument('--jsonl',action='store_true',help='JSON line input and full turn output')
    ap.add_argument('--checkpoint',type=Path,help='Save complete mutable state after each turn')
    ap.add_argument('--resume',type=Path)
    ap.add_argument('--transcript',type=Path)
    ap.add_argument('--metrics',type=Path)
    ap.add_argument('--seed',type=int,default=12)
    ap.add_argument('--strict-text',action='store_true')
    args=ap.parse_args()
    try:
        inputs=[p.resolve() for p in (args.commands,args.resume) if p]
        outputs=[p for p in (args.checkpoint,args.transcript,args.metrics) if p]
        resolved=[p.resolve() for p in outputs]
        if len(set(resolved))!=len(resolved):raise ValueError('Output paths alias')
        for p in outputs:
            target=p.resolve()
            if p.is_symlink() or target==ROOT or ROOT in target.parents:
                raise ValueError('Outputs must be outside the immutable product directory')
            if any(target==i or (target.exists() and i.exists() and target.samefile(i)) for i in inputs):
                raise ValueError('Output would overwrite input')
            if any((d/'.git').exists() for d in target.parents):
                raise ValueError('Private game outputs must remain outside Git')
        commands=read_json(args.commands,1024*1024) if args.commands else None
        if commands is not None and (not isinstance(commands,list) or len(commands)>10000 or
                                    any(type(s) is not str for s in commands)):
            raise ValueError('Expected bounded command string list')
        game=DirectGame(ROOT,seed=args.seed,strict_text=args.strict_text)
        if args.resume:game.restore_memory_container(read_json(args.resume,MAX_CHECKPOINT_BYTES))
        turns=[]
        def present(result,command=None):
            row={'command':command,**result};turns.append(row)
            if len(turns)>10000:raise ValueError('Turn budget exceeded')
            if args.jsonl:print(json.dumps(row,ensure_ascii=False),flush=True)
            else:print(result['text'],end='',flush=True)
            if args.checkpoint:atomic(args.checkpoint,game.memory_container())
            return result
        result=present(game.run())
        if commands is not None:
            for command in commands:
                if result['status']!='input':break
                result=present(game.command(command),command)
        else:
            while result['status']=='input':
                line=sys.stdin.readline(16385)
                if not line:break
                if len(line)>16384:raise ValueError('Input line too large')
                if args.jsonl:
                    req=parse_json(line)
                    if not isinstance(req,dict) or set(req)!={'command'}:raise ValueError('Expected command object')
                    command=req['command']
                else:command=line.rstrip('\r\n')
                result=present(game.command(command),command)
        if args.transcript:atomic(args.transcript,turns)
        if args.metrics:
            atomic(args.metrics,{'turns':len(turns),'executed_blocks':len(game.executed_blocks),
                'asset_hits':game.asset_hits,'codec_misses':game.codec_misses,'codec_calls':game.codec_calls,
                'loaded_python_modules':len(game._shards),'state_sha256':sha(canonical(game.snapshot())),
                'product_sha256':game.product_digest})
        return 2 if result['status']=='budget_exhausted' else 0
    except (ValueError,Word16Error,PackageError,OSError) as exc:
        ap.exit(1,'z3-python: '+str(exc)+'\n')

if __name__=='__main__':raise SystemExit(main())
