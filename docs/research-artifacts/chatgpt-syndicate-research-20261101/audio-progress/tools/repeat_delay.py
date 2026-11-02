"""Continue the successful delayed-loop preparation for two more callback ticks."""
import os,json,struct,hashlib,time,collections
from pathlib import Path
R=Path(os.environ['SYNDICATE_PRIVATE']).resolve()
if (R/'delay-continuation-summary.json').exists(): raise FileExistsError('Existing continuation results')
import fm_probe
B=0x10000;SEQ=0x1000000;EVENT=0x1001000
initial=json.loads((R/'summary.json').read_text())
previous=next(c for c in initial['cases'] if c['case']=='zero_count_with_delay')
old=json.loads((R/'evidence'/previous['receipt']).read_text());out=[]
for tick in (2,3):
 writes={int(addr,16):bytes.fromhex(o['after']) for addr,o in old['observations'].items()}
 writes[EVENT]=bytes.fromhex('b0740001b0757f01')
 rec=fm_probe.run(B+0x3072,writes=writes,observe=[(SEQ,0x218),(B+0x26cb,0x2a)],max_steps=8000,seconds=12)
 text=json.dumps(rec,indent=2);fn=f'{time.time_ns()}-delay-tick-{tick}.json';(R/'evidence'/fn).write_text(text)
 after=bytes.fromhex(rec['observations'][hex(SEQ)]['after']);counts=collections.Counter(rec['trace'])
 row={'case':f'zero_count_with_delay_tick_{tick}','reason':rec['reason'],'expected':'returned','expectation_met':rec['reason']=='returned','steps':rec['steps'],'rewind_path_visits':counts[hex(B+0x2dc6)],'event_fetch_visits':counts[hex(B+0x31bf)],'after_cursor_offset':struct.unpack_from('<I',after,12)[0]-EVENT,'loop_counter0':struct.unpack_from('<H',after,0x70)[0],'sequence_state':struct.unpack_from('<H',after,0x1e)[0],'child_reaped':rec.get('child_reaped',False),'receipt':fn,'receipt_sha256':hashlib.sha256(text.encode()).hexdigest(),'preparation':'Prior callback post-state for the observed sequence and driver-global ranges; fresh host process, not a DOS restore.'}
 print(json.dumps(row));out.append(row);old=rec
(R/'delay-continuation-summary.json').write_text(json.dumps({'cases':out,'all_expected':all(x['expectation_met'] for x in out)},indent=2)+'\n')
