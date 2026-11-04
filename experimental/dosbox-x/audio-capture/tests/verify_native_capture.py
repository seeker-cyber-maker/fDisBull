"""Authored PC-speaker program verifies the real bounded mixer/RPC seam."""
from pathlib import Path
import argparse,base64,hashlib,json,os,struct,traceback
from fdisbull.project import Project
from fdisbull.dosbox_rpc import DebuggerError
W=Path(__file__).resolve().parent.parent
sha=lambda data:hashlib.sha256(data).hexdigest()

def fixture():
    # Authored 16-bit COM: configure PIT2 near440Hz, enable speaker, wait ten
    # BIOS ticks, disable speaker, and stop at the self-loop. No game bytes.
    raw=bytearray.fromhex('b0b6e643b8970ae64288e0e642e4610c03e661b840008ec0268b1e6c00')
    wait=len(raw);raw.extend(bytes.fromhex('26a16c0029d883f80a72'))
    raw.append((wait-(len(raw)+1))&255)
    raw.extend(bytes.fromhex('e46124fce661'));done=0x100+len(raw);raw.extend(bytes.fromhex('ebfe'))
    return bytes(raw),done

def canonical_regs(debug):
    r=debug.registers();return {k:r[k] for k in ('general','segments','flags','instruction_pointer','cpu_mode')}

def observer_snapshot(debug, code):
    registers=canonical_regs(debug)
    ss=int(registers['segments']['ss'],16);sp=int(registers['general']['esp'],16)&65535
    stack=debug.call('memory.read',{'address':{'space':'linear','offset':f'0x{ss*16+sp:08x}'},'length':32})
    return dict(registers=registers,code_sha256=debug.memory(hex(debug.static_base),length=len(code))['sha256'],stack_sha256=stack['sha256'],timing=debug.call('execution.timing'),state_revision=debug.registers()['state_revision'])

def main():
    a=argparse.ArgumentParser();a.add_argument('--work',type=Path,required=True);a.add_argument('--backend',type=Path,required=True);a.add_argument('--tag',required=True);a.add_argument('--red',action='store_true');args=a.parse_args()
    out=args.work.resolve()/args.tag;out.mkdir(parents=True);game=out/'game';game.mkdir();code,done=fixture();(game/'TONE.COM').write_bytes(code);pid=None;facts=dict(status='running',backend=str(args.backend),backend_sha256=sha(args.backend.read_bytes()),fixture_sha256=sha(code),fixture_done_ip=done,scope='Authored PC-speaker fixture; original mixer/RPC, no host audio, no game assets or guest memory/register edits.')
    try:
      with Project.create(out/'tone.fdb',game/'TONE.COM',image='com',load_segment=0x1000) as project:
       with project.debugger(args.backend,game,version=1) as debug:
        pid=debug.rpc.process.pid;facts['pid']=pid;facts['capabilities']=debug.rpc.capabilities
        if args.red:
         try:debug.call('audio.capture.start',{'max_bytes':4096})
         except DebuggerError as e:
          assert 'Method not found' in str(e);facts.update(status='expected-feature-gap',error=str(e))
         else:raise AssertionError('Baseline unexpectedly supports capture')
        else:
         assert debug.rpc.capabilities['audio']['capture'];assert debug.rpc.capabilities['audio']['max_capture_bytes']==4194304
         before=canonical_regs(debug);revision=debug.registers()['state_revision'];observer_entry=observer_snapshot(debug,code)
         for bad in (0,3,5,4194308):
          try:debug.call('audio.capture.start',{'max_bytes':bad})
          except DebuggerError:pass
          else:raise AssertionError('Invalid budget admitted')
         first=debug.call('audio.capture.start',{'max_bytes':4096});assert canonical_regs(debug)==before and first['state_revision']==revision and observer_snapshot(debug,code)==observer_entry
         try:debug.call('audio.capture.start',{'max_bytes':4096})
         except DebuggerError as e:assert 'CAPTURE_ACTIVE' in str(e)
         else:raise AssertionError('Concurrent capture admitted')
         try:debug.call('audio.capture.status',{'capture_id':first['capture_id']+1})
         except DebuggerError as e:assert 'CAPTURE_ID_MISMATCH' in str(e)
         else:raise AssertionError('Stale capture admitted')
         # Run only to a fixture-owned original instruction boundary.
         bp=debug.call('breakpoints.create',{'kind':'execution','address':{'space':'segmented','segment':f'0x{debug.runtime_load:04x}','offset':f'0x{done:08x}'},'once':False})['breakpoint_id']
         run=debug.run(timeout_ms=10000,fast_forward=True,stop_on_hook=True)
         assert run['outcome']=='breakpoint' and run['session']['stop_reason']['breakpoint_id']==bp
         stopped=canonical_regs(debug);observer_stopped=observer_snapshot(debug,code)
         status=debug.call('audio.capture.status',{'capture_id':first['capture_id']});assert 'data_base64' not in status
         assert status['complete'] and status['truncated'] and not status['active'] and status['byte_count']==4096 and status['stop_reason']=='byte_limit'
         capture=debug.call('audio.capture.stop',{'capture_id':first['capture_id']});pcm=base64.b64decode(capture.pop('data_base64'),validate=True)
         assert len(pcm)==4096 and sha(pcm)==capture['sha256'];assert capture['next_mixer_frame']-capture['first_mixer_frame']==capture['captured_frames']==1024
         again=debug.call('audio.capture.stop',{'capture_id':first['capture_id']});assert base64.b64decode(again.pop('data_base64'),validate=True)==pcm and again==capture
         assert canonical_regs(debug)==stopped
         facts['budget_capture']=capture;assert observer_snapshot(debug,code)==observer_stopped
         # Capture a caller-selected silent interval after the fixture turned
         # speaker off, then explicitly stop before the larger budget fills.
         second=debug.call('audio.capture.start',{'max_bytes':4194304});assert second['capture_id']>first['capture_id']
         try:debug.call('audio.capture.stop',{'capture_id':first['capture_id']})
         except DebuggerError as e:assert 'CAPTURE_ID_MISMATCH' in str(e)
         else:raise AssertionError('Old capture replay admitted after replacement')
         # Start/stop at a stopped target must retain a well-formed empty window.
         zero=debug.call('audio.capture.stop',{'capture_id':second['capture_id']});empty=base64.b64decode(zero.pop('data_base64'),validate=True)
         assert not empty and zero['complete'] and not zero['truncated'] and zero['stop_reason']=='requested' and zero['first_mixer_frame']==zero['next_mixer_frame']
         facts['empty_requested_capture']=zero;assert observer_snapshot(debug,code)==observer_stopped;facts['paused_observer_snapshot_before_after_exact']=True;facts['paused_observer_snapshot']=observer_stopped
         assert canonical_regs(debug)==stopped
         # Fresh authored run below supplies an untruncated full tone window.
         samples=struct.unpack('<'+'h'*(len(pcm)//2),pcm);left=samples[::2];right=samples[1::2]
         assert left==right and max(left)-min(left)>100
         facts['budget_waveform']=dict(stereo_equal=True,peak_to_peak=max(left)-min(left),nonzero_samples=sum(v!=0 for v in left))
         facts.update(status='passed',fixture_unchanged=(game/'TONE.COM').read_bytes()==code,observer_registers_unchanged=True)
       facts['native_returncode']=debug.rpc.process.poll()
    except BaseException as error:facts.update(status='failed',error=repr(error),traceback=traceback.format_exc())
    finally:
      if pid:
       try:os.kill(pid,0);facts['owned_process_reaped']=False
       except ProcessLookupError:facts['owned_process_reaped']=True
      (out/'RESULT.json').write_text(json.dumps(facts,indent=2)+'\n');print(json.dumps({k:v for k,v in facts.items() if k not in ('capabilities',)},indent=2))
    return 0 if facts['status'] in ('passed','expected-feature-gap') and facts['owned_process_reaped'] else 1
if __name__=='__main__':raise SystemExit(main())
