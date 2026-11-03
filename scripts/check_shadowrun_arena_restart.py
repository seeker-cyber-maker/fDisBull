#!/usr/bin/env python3
"""Verify the target-authored START restart after a terminal arena result."""
import argparse
import hashlib
import json
from pathlib import Path

def sha(b):return hashlib.sha256(b).hexdigest()

def main():
    p=argparse.ArgumentParser()
    for n in ('build','run','terminal-check','output'):p.add_argument('--'+n,required=True,type=Path)
    a=p.parse_args();build=json.loads((a.build/'play-receipt.json').read_text());term_raw=a.terminal_check.read_bytes();term=json.loads(term_raw)
    receipt_raw=(a.run/'receipt.json').read_bytes();receipt=json.loads(receipt_raw);trace=(a.run/'ram_trace.json').read_bytes()
    if (build['arena_preset']!='stationary' or sha((a.build/'play.nes').read_bytes())!=build['output_sha256'] or
        term['nes_sha256']!=build['output_sha256'] or receipt['rom_sha256']!=build['output_sha256'] or
        receipt['core_sha256']!='5d1db7d31c0dc810ad44888d7a00ea1b77897f9d0d883ec81954694cbfb6fc60' or
        receipt['ram_trace_sha256']!=sha(trace) or receipt['patches'] or
        receipt['inputs']!=[{'start':960,'end':968,'buttons':['START']}]):raise ValueError('Restart provenance mismatch')
    terminal=None;restarted=None
    for row in json.loads(trace)['frames']:
        data=bytes.fromhex(row['raw']['state']);frame=row['frame']
        if data[:2]!=b'SW' or data[22]&1:continue
        if frame<960 and data[85]==3 and data[84]==0:terminal=frame
        if frame>=968 and data[23]==1 and data[85]==1 and data[84]==5 and data[88]==47:
            restarted=frame;break
    if terminal is None or restarted is None:raise ValueError('Did not observe terminal state followed by a fresh arena')
    if a.output.exists():raise ValueError('Output exists')
    a.output.write_text(json.dumps({'status':'passed','nes_sha256':build['output_sha256'],
        'terminal_check_sha256':sha(term_raw),'native_receipt_sha256':sha(receipt_raw),'native_trace_sha256':sha(trace),
        'terminal_observed_frame':terminal,'restart_first_tick_frame':restarted,
        'scope':'target-authored START reset after terminal HP0; original death scene excluded'},indent=2)+'\n')

if __name__=='__main__':main()
