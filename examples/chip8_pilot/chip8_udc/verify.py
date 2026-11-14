"""Differentially check generated Python UDC against the original pilot VM.

Same VM implementation is the reference; this is not an independent historical
oracle. Every step compares full state digests plus family/status/faults.
"""
from __future__ import annotations
from collections import Counter
import importlib.util
from pathlib import Path
from chip8lab.vm import Machine, Trap, Quirks


def import_generated(path:Path):
    path=Path(path)
    spec=importlib.util.spec_from_file_location(path.stem,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def drive(module, rom:bytes, *, budget:int=1600, seed:int=42, quirks:Quirks|None=None,
          key_schedule:dict[int,set[int]]|None=None, ticks_every:int=9):
    if budget<=0: raise ValueError('positive budget required')
    ref=Machine(seed=seed, quirks=quirks or Quirks());ref.load_rom(rom)
    sub=module.create_machine(rom,seed=seed,quirks=quirks)
    assert ref.state_digest() == sub.state_digest()
    counters={'specialized':0,'fallback':0}
    result={'completed_attempts':0, 'status':'budget_exhausted','exception':None}
    observed=Counter()
    for t in range(budget):
        if key_schedule is not None and t in key_schedule:
            ref.keys=set(key_schedule[t]);sub.keys=set(key_schedule[t])
        if t and ticks_every and t%ticks_every==0:
            ref.tick_60hz();sub.tick_60hz()
        outcomes=[]
        for machine,step in ((ref,lambda:ref.step()),(sub,lambda:module.step(sub,counters))):
            try:
                outcomes.append(('ok',step()))
            except Trap as err:
                outcomes.append(('trap',err.code,err.address,err.word))
        if outcomes[0]!=outcomes[1] or ref.state_digest()!=sub.state_digest() or ref.last_family != sub.last_family or ref.waiting!=sub.waiting:
            raise AssertionError({'turn':t,'pc_ref':ref.pc,'pc_udc':sub.pc,
                                  'outcomes':outcomes,'ref_family':ref.last_family,
                                  'udc_family':sub.last_family,'ref_sha256':ref.state_digest(),
                                  'udc_sha256':sub.state_digest(), 'counts':counters})
        result['completed_attempts']+=1
        if outcomes[0][0]=='trap':
            result['status']='trapped';result['exception']=outcomes[0][1:];break
        if outcomes[0][1]=='waiting':
            result['status']='key_wait';break
        observed[ref.last_family]+=1
    return {**result,'family_executions':dict(sorted(observed.items())),
            'specialized_steps':counters['specialized'], 'fallback_steps':counters['fallback'],
            'state_sha256':sub.state_digest(),
            'evidence_scope':'same authored reference VM differential; fixed host inputs and finite budget'}
