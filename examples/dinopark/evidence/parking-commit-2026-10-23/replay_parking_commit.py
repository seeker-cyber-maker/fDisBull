"""Repeat the parking commit observation from the captured local native checkpoint."""
from pathlib import Path
import sys,json,hashlib,struct
root=Path(__file__).parent
bundle=root/'delivery/fdisbull-native-debugger-cd13636'
sys.path.insert(0,str(bundle/'packages/fdisbull-0.9.0-py3-none-any.whl'))
from fdisbull.project import Project
from fdisbull import debugger
assert '.whl/' in debugger.__file__
backend=bundle/'backend/native-macos-arm64/dosbox-x'
assert hashlib.sha256(backend.read_bytes()).hexdigest()=='e749b6e50775de2807c2515f83e455dc705cdf6ddcdfb257e781f215d987865a'
with Project(root/'parking.fdb') as p, p.debugger(backend,root/'game') as d:
 restored=d.load_state('ce4393d16aff4b4fa81f7fad3c2afb5b')
 d.run(guest_ms=120,timeout_ms=3000)
 before=d.memory('0x471a6',length=8)
 pending=d.memory('0x4bb14',length=8)
 assert before['hex']=='0000000000000000' and pending['hex']=='0000000000000100'
 watch=d.breakpoint('0x471ac',access='w',length=2)
 d.click(218,188,hold_ms=100)
 hit=d.run(timeout_ms=3000)
 assert hit['outcome']=='breakpoint',hit
 event=hit['session']['stop_reason']['data_access']
 assert event['address']=='0x0003F3EC' and event['length']==2 and event['project_instruction']=='0x14fcb'
 after=d.memory('0x471a6',length=8)
 assert after['hex']=='0000000000000100'
 trace=d.trace('22-fresh-session-return.json',count=128,timeout_ms=3000)
 assert trace['metadata']['complete'] and trace['metadata']['run']['guest_elapsed_ms']==0
 p.debug_export(trace['artifact'],root/'22-fresh-session-return.json')
 report={'result':'pass','run':d.run_id,'module':debugger.__file__,'restored':restored,
   'before':before,'pending_order':pending,'watch':watch,'hit':hit,'after':after,'continuation':trace}
(root/'fresh-session-replay.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: fresh delivered-wheel/emulator session restored pre-OK machine state; actual parking-word write and unchanged-tick 128-event continuation verified')
