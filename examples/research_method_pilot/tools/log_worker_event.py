#!/usr/bin/env python3
"""Record observable experiment milestones, never private model reasoning.

Run in each worker's own directory. This logger does not launch an agent, enforce
sandbox isolation, or measure token usage automatically.
"""
from __future__ import annotations
import argparse, datetime, json, os, time
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('event',choices=['start','research_complete','hypotheses_frozen','first_candidate','first_code_binding','candidate_submitted','review_returned','accepted','budget_stop','blocked'])
    p.add_argument('--log',type=Path,default=Path('events.jsonl'))
    p.add_argument('--run-id',required=True)
    p.add_argument('--note',default='')
    p.add_argument('--tokens',type=int)
    p.add_argument('--tool-calls',type=int)
    a=p.parse_args()
    if len(a.note)>2000:p.error('note exceeds 2000 characters')
    for v in [a.tokens,a.tool_calls]:
        if v is not None and v<0:p.error('counts cannot be negative')
    prior=[]
    if a.log.exists():
        prior=[json.loads(x) for x in a.log.read_text().splitlines() if x]
        if any(x['run_id']!=a.run_id for x in prior):p.error('log belongs to a different run')
    if a.event=='start' and prior:p.error('cannot overwrite/restart an existing log')
    if a.event!='start' and not prior:p.error('start must be recorded first')
    if prior and prior[-1]['event'] in ['accepted','budget_stop','blocked']:
        p.error('run is terminal; preserve it and use a new run ID for a retry')
    now=time.monotonic_ns()
    row={'run_id':a.run_id,'event':a.event,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'monotonic_ns':now,
         'elapsed_seconds':(now-prior[0]['monotonic_ns'])/1e9 if prior else 0.0,'tokens_reported':a.tokens,'tool_calls_reported':a.tool_calls,'note':a.note}
    flags=os.O_WRONLY|os.O_CREAT|os.O_APPEND
    if a.event=='start':flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    a.log.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(a.log,flags,0o600)
    with os.fdopen(fd,'a',encoding='utf-8') as f:f.write(json.dumps(row,sort_keys=True)+'\n')
    print(json.dumps(row,sort_keys=True))
if __name__=='__main__':main()
