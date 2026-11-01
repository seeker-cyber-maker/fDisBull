"""Authored event-loop probes using exact driver instructions, not real game music."""
import os,json,struct,hashlib,time,collections
from pathlib import Path
R=Path(os.environ['SYNDICATE_PRIVATE']).resolve()
if (R/'summary.json').exists(): raise FileExistsError('Existing results; prepare a new private profile')
import fm_probe
B=0x10000;SEQ=0x1000000;EVENT=0x1001000

def setup(events):
 st=bytearray(0x218)
 struct.pack_into('<I',st,0x0c,EVENT)
 for o in (0x1c,0x1e):struct.pack_into('<H',st,o,1)
 for o in (0x2a,0x2e,0x3e,0x42):struct.pack_into('<I',st,o,100)
 struct.pack_into('<I',st,0x54,0x208d5);struct.pack_into('<I',st,0x5c,8000000)
 st[0x70:0x78]=b'\xff'*8;st[0xb8:0xc8]=b'\xff'*16;st[0x158:0x178]=b'\xff'*32
 return {SEQ:bytes(st),EVENT:events,B+0x26cb:struct.pack('<I',SEQ)+bytes(28),B+0x26eb:struct.pack('<I',1),B+0x26f3:bytes(2)}

cases=[('finite_count_one',bytes.fromhex('b07401b0757f01'), 'returned'),('finite_count_two',bytes.fromhex('b07402b0757f01'),'returned'),('zero_count_no_delay',bytes.fromhex('b07400b0757f01'),'instruction_budget'),('zero_count_with_delay',bytes.fromhex('b0740001b0757f01'),'returned')]
summary=[]
for name,events,expected in cases:
 rec=fm_probe.run(B+0x3072,writes=setup(events),observe=[(SEQ,0x218),(B+0x26cb,0x2a)],max_steps=8000,seconds=12)
 raw=json.dumps(rec,indent=2);fn=f'{time.time_ns()}-{name}.json';(R/'evidence'/fn).write_text(raw)
 after=bytes.fromhex(rec['observations'][hex(SEQ)]['after']);cnt=collections.Counter(rec['trace'])
 item={'case':name,'authored_events_hex':events.hex(),'reason':rec['reason'],'expected':expected,'expectation_met':rec['reason']==expected,'steps':rec['steps'],'rewind_path_visits':cnt[hex(B+0x2dc6)],'event_fetch_visits':cnt[hex(B+0x31bf)],'after_cursor_offset':struct.unpack_from('<I',after,0xc)[0]-EVENT,'loop_counter0':struct.unpack_from('<H',after,0x70)[0],'sequence_state':struct.unpack_from('<H',after,0x1e)[0],'child_reaped':rec.get('child_reaped',False),'receipt':fn,'receipt_sha256':hashlib.sha256(raw.encode()).hexdigest()}
 summary.append(item);print(json.dumps(item),flush=True)
 if not item['expectation_met']:break
out={'profile':'Original GAMEFM x86-32 callback under Linux compatibility harness, fabricated initialized state and synthetic events; not DOS/4GW or current-asset behavior. Ports, CLI/STI and system services stop before execution.','cases':summary,'all_expected':len(summary)==4 and all(x['expectation_met'] for x in summary)}
(R/'summary.json').write_text(json.dumps(out,indent=2)+'\n')
