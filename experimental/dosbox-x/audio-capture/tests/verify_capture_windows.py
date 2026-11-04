"""Full authored tone window, paused invalidation and observer-off controls."""
from pathlib import Path
import argparse,base64,hashlib,json,os,struct,traceback
from fdisbull.project import Project
from fdisbull.dosbox_rpc import DebuggerError
from verify_native_capture import fixture,observer_snapshot,canonical_regs
parser=argparse.ArgumentParser();parser.add_argument('--work',type=Path,required=True);parser.add_argument('--backend',type=Path,required=True);args=parser.parse_args();W=args.work.resolve();W.mkdir(parents=True,exist_ok=True);BACKEND=args.backend.resolve();sha=lambda data:hashlib.sha256(data).hexdigest()
results=[]
for kind in ['tone_on','tone_off','state_load_invalidation','guest_exit']:
 out=W/('window-'+kind+'-01');out.mkdir();game=out/'game';game.mkdir();code,done=fixture()
 if kind=='guest_exit':code=bytes.fromhex('b8004ccd21')
 (game/'FIXTURE.COM').write_bytes(code);facts=dict(case=kind,backend_sha256=sha(BACKEND.read_bytes()),fixture_sha256=sha(code));pid=None
 try:
  with Project.create(out/'fixture.fdb',game/'FIXTURE.COM',image='com',load_segment=0x1000) as p:
   with p.debugger(BACKEND,game,version=1) as debug:
    pid=debug.rpc.process.pid;facts['pid']=pid;entry=observer_snapshot(debug,code)
    arm=None if kind=='tone_off' else debug.call('audio.capture.start',{'max_bytes':1048576})
    assert observer_snapshot(debug,code)==entry
    if kind=='state_load_invalidation':
     try:debug.call('state.load',{'path':str(out/'missing-authored-state.sav')})
     except DebuggerError:pass
     else:raise AssertionError('Missing state should refuse')
    else:
     if kind!='guest_exit':
      bp=debug.call('breakpoints.create',{'kind':'execution','address':{'space':'segmented','segment':f'0x{debug.runtime_load:04x}','offset':f'0x{done:08x}'},'once':False})['breakpoint_id']
     run=debug.run(timeout_ms=10000,fast_forward=True,stop_on_hook=True)
     assert run['outcome']==('guest_exit' if kind=='guest_exit' else 'breakpoint'),run
    before=None if kind=='guest_exit' else observer_snapshot(debug,code)
    if arm:
     status=debug.call('audio.capture.status',{'capture_id':arm['capture_id']});assert 'data_base64' not in status
     stop=debug.call('audio.capture.stop',{'capture_id':arm['capture_id']});raw=base64.b64decode(stop.pop('data_base64'),validate=True);assert sha(raw)==stop['sha256'] and len(raw)==stop['byte_count']
     assert stop['captured_frames']*4==len(raw) and stop['next_mixer_frame']-stop['first_mixer_frame']==stop['captured_frames']
     if kind=='tone_on':
      assert stop['complete'] and not stop['truncated'] and stop['stop_reason']=='requested'
      values=struct.unpack('<'+'h'*(len(raw)//2),raw);left=values[::2];right=values[1::2];assert left==right
      mid=left[512:-512];edges=[i for i in range(1,len(mid)) if mid[i-1]<=0<mid[i]];frequency=stop['sample_rate']*(len(edges)-1)/(edges[-1]-edges[0]);expected=1193182/2711
      assert abs(frequency-expected)/expected<0.02,(frequency,expected)
      duration=stop['captured_frames']/stop['sample_rate'];assert 0.45<duration<0.65
      assert abs(duration-(stop['end_guest_ticks']-stop['start_guest_ticks'])/1000)<0.003
      facts.update(measured_frequency_hz=frequency,expected_pit_frequency_hz=expected,duration_seconds=duration,stereo_exact=True)
     else:assert stop['truncated'] and stop['complete'] and stop['stop_reason']==('state_load' if kind=='state_load_invalidation' else 'guest_exit')
     facts['capture']=stop
    if before is not None:
     assert observer_snapshot(debug,code)==before;facts['paused_observer_unchanged']=True;facts['terminal_observer']=before
    facts.update(status='passed',fixture_unchanged=(game/'FIXTURE.COM').read_bytes()==code)
   facts['native_returncode']=debug.rpc.process.poll()
 except BaseException as error:facts.update(status='failed',error=repr(error),traceback=traceback.format_exc())
 finally:
  if pid:
   try:os.kill(pid,0);facts['owned_process_reaped']=False
   except ProcessLookupError:facts['owned_process_reaped']=True
  (out/'RESULT.json').write_text(json.dumps(facts,indent=2)+'\n');results.append(facts)
  print(kind,facts['status'],facts.get('error'),flush=True)
# Compare exactly the same completed authored program with the tap on/off.
on,off=results[:2];same=on.get('terminal_observer')==off.get('terminal_observer');summary=dict(status='passed' if all(r['status']=='passed' and r['owned_process_reaped'] for r in results) else 'failed',authored_tone_capture_on_off_terminal_snapshot_exact=same,cases=[{k:v for k,v in r.items() if k!='terminal_observer'} for r in results],claim_ceiling='Only this finite authored fixture; no general timing or whole-game neutrality claim.')
(W/'NATIVE-WINDOWS.json').write_text(json.dumps(summary,indent=2)+'\n');print('on/off authored terminal snapshot exact:',same);raise SystemExit(0 if summary['status']=='passed' else 1)
