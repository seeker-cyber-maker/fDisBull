"""A real ELF image shares its pure module bytes with the PE64 compiler."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import lief
import pytest
from fdisbull.project import Project
from fdisbull.udc_shell import build_windows_shell
from fdisbull.udc_linux import build_linux_shell


def example():
 program={'format':'fdisbull-il-1','role':'uil','variables':{n:{'type':'u16','initial':0} for n in ('$left','$right','$sum','$scratch')},'resources':{},'body':[
 {'id':'copy','op':'set','var':'$sum','value':{'var':'$left'}},{'id':'add','op':'add','var':'$sum','value':{'var':'$right'}},{'id':'init','op':'add','var':'$sum','value':{'var':'$scratch'}},{'id':'private','op':'set','var':'$left','value':17}]}
 plan={'format':'fdisbull-native-shell-1','entry':'main','state':{'$left':{'type':'u16','initial':65535},'$right':{'type':'u16','initial':2},'$sum':{'type':'u16','initial':60000},'$scratch':{'type':'u16','initial':12345}},'resources':{'win':{'kind':'text','text':'Win'},'lose':{'kind':'text','text':'Lose'}},'functions':{'main':{'body':[{'op':'call','binding':'math'},{'op':'notify','binding':'present','value':{'var':'$sum'}}]}}}
 modules={'math':{'backend':'uil','program':program,'return':'$sum','state_adapter':{'inputs':['$left','$right'],'outputs':['$sum']}},'present':{'backend':'message-box-a','title':'UDC','messages':{'1':'win'},'default':'lose','style':64}}
 return plan,modules


def adapters():return {'present':{'backend':'linux-stdout','acknowledgment':'none'}}


def test_real_elf_load_and_exact_same_math_and_program_function_slots(tmp_path):
 plan,modules=example();before=copy.deepcopy((plan,modules))
 win=build_windows_shell(plan,modules,tmp_path/'win');elf=build_linux_shell(plan,modules,tmp_path/'linux',service_adapters=adapters(),capture_state=True)
 binary=lief.ELF.parse(str(tmp_path/'linux/program'))
 assert binary.header.machine_type==lief.ELF.ARCH.X86_64 and binary.header.entrypoint==0x401000
 assert len(binary.segments)==3 and not binary.libraries
 for name in ('module:math','fn:main'):
  a,b=win['slots'][name],elf['slots'][name]
  left=(tmp_path/'win/program.exe').read_bytes()[a['file_offset']:a['file_offset']+a['size']]
  right=(tmp_path/'linux/program').read_bytes()[b['file_offset']:b['file_offset']+b['size']]
  assert left==right and a['sha256']==b['sha256']
 assert win['plan_sha256']==elf['plan_sha256'] and win['modules_sha256']==elf['modules_sha256']
 assert win['slots']['entry']['sha256']!=elf['slots']['entry']['sha256']
 assert win['slots']['module:present']['sha256']!=elf['slots']['module:present']['sha256']
 assert before==(plan,modules)
 with Project.create(tmp_path/'elf.fdb',tmp_path/'linux/program') as p:
  p.analyze(max_instructions=100);assert p.meta['format']=='ELF' and p.bits==64
  assert p.disassembly('0x401000',lines=1)['instructions'][0]['mnemonic']=='and'
 with Project(tmp_path/'elf.fdb') as p:assert p.meta['entry']==0x401000


def test_linux_requires_explicit_presentation_and_new_private_output(tmp_path):
 plan,modules=example()
 for mapping in (None,{}, {'present':{'backend':'linux-stdout'}}, {'present':{'backend':'linux-stdout','acknowledgment':'yes'}}):
  with pytest.raises(ValueError,match='adapter'):build_linux_shell(plan,modules,tmp_path/'bad',service_adapters=mapping)
  assert not (tmp_path/'bad').exists()
 repo=tmp_path/'repo';repo.mkdir();(repo/'.git').write_text('gitdir: elsewhere')
 with pytest.raises(ValueError,match='outside Git'):build_linux_shell(plan,modules,repo/'bad',service_adapters=adapters())
 build_linux_shell(plan,modules,tmp_path/'kept',service_adapters=adapters())
 with pytest.raises(ValueError,match='new'):build_linux_shell(plan,modules,tmp_path/'kept',service_adapters=adapters())


def run_native_linux(path,tmp_path):
 import platform,os,subprocess
 if platform.system()!='Linux' or platform.machine() not in ('x86_64','AMD64'):
  pytest.skip('Real Linux x86-64 process acceptance; macOS uses a separate QEMU native batch')
 frame_path=tmp_path/'frame.bin'
 # A shell's explicit descriptor redirect avoids inheriting any unrelated FDs.
 script='exec "$1" 3>"$2"'
 run=subprocess.run(['/bin/sh','-c',script,'udc-run',str(path),str(frame_path)],capture_output=True,timeout=10)
 return run,frame_path.read_bytes()


@pytest.mark.parametrize('backend',['uil','c-uil'])
@pytest.mark.parametrize('case',['success','require','loop-budget','typed'])
def test_actual_linux_process_outputs_state_and_failure_semantics(tmp_path,backend,case):
 import shutil
 plan,modules=example();modules['math']['backend']=backend
 if backend=='c-uil' and not shutil.which('clang'):pytest.skip('clang required')
 if case=='require':modules['math']['program']['body'].append({'id':'fail','op':'require','condition':{'op':'eq','left':0,'right':1}})
 if case=='loop-budget':
  plan['functions']['main']['body']=[{'op':'while','condition':{'op':'eq','left':1,'right':1},'limit':1,'body':[{'op':'call','binding':'math'}]}]
 if case=='typed':
  plan['state']['$signed']={'type':'i16','initial':-1};modules['math']['program']['variables']['$signed']={'type':'i16','initial':-1}
  modules['math']['program']['body'].insert(0,{'id':'sign','op':'require','condition':{'op':'bit_test','value':{'var':'$signed'},'bit':63}})
  # Callee's signed local remains separate from caller's equal-spelled field.
 out=build_linux_shell(plan,modules,tmp_path/'linux',service_adapters=adapters(),capture_state=True,c_compiler=shutil.which('clang'))
 run,frame=run_native_linux(tmp_path/'linux/program',tmp_path)
 assert frame[:4]==b'UDC1';status,value,size=struct.unpack_from('<III',frame,4)
 expected_status={'success':0,'typed':0,'require':1,'loop-budget':2}[case]
 assert run.returncode==status==expected_status and len(frame)==16+size
 values=struct.unpack('<'+'H'*(size//2),frame[16:]);state=dict(zip(sorted(plan['state']),values))
 assert state['$left']==65535 and state['$right']==2 and state['$scratch']==12345
 assert state['$sum']==(60000 if case=='require' else 1)
 assert run.stdout==(b'Win' if case in ('success','typed') else b'')


def test_frame_decoder_refuses_partial_and_wrong_typed_observations(tmp_path):
 from fdisbull.udc_linux import decode_observation
 plan,modules=example();build=build_linux_shell(plan,modules,tmp_path/'linux',service_adapters=adapters(),capture_state=True)
 frame=b'UDC1'+struct.pack('<III',0,0,8)+struct.pack('<HHHH',65535,2,12345,1)
 assert decode_observation(frame,build)['state']['$sum']==1
 for bad in (frame[:-1],frame+b'x',b'nope'+frame[4:]):
  with pytest.raises(ValueError):decode_observation(bad,build)


@pytest.mark.parametrize('fault',['stdout','observation'])
def test_closed_pipe_has_structured_failure_instead_of_signal_termination(tmp_path,fault):
 import os,platform,subprocess
 from fdisbull.udc_linux import decode_observation
 if platform.system()!='Linux' or platform.machine() not in ('x86_64','AMD64'):
  pytest.skip('Real Linux closed-reader pipe acceptance')
 import fcntl
 plan,modules=example()
 build=build_linux_shell(plan,modules,tmp_path/'linux',service_adapters=adapters(),capture_state=True)
 reader,writer=os.pipe();os.close(reader)
 frame=tmp_path/'frame.bin'
 try:
  high_writer=fcntl.fcntl(writer,fcntl.F_DUPFD_CLOEXEC,64)
  os.close(writer);writer=high_writer
  if fault=='stdout':
   run=subprocess.run(['/bin/sh','-c','exec "$1" 3>"$2"','udc-run',str(tmp_path/'linux/program'),str(frame)],stdout=writer,stderr=subprocess.PIPE,timeout=10)
   decoded=decode_observation(frame.read_bytes(),build)
   assert run.returncode==decoded['status']==3 and decoded['state']['$sum']==1
  else:
   # Pass any high source FD through stdin; Dash only accepts single-digit
   # redirection operands. Duplicate it to FD3, then restore ordinary stdin.
   run=subprocess.run(['/bin/sh','-c','exec "$1" 3>&0 0</dev/null','udc-run',str(tmp_path/'linux/program')],stdin=writer,capture_output=True,timeout=10)
   assert run.returncode==4 and run.stdout==b'Win'
 finally:os.close(writer)


def test_canonical_notification_map_order_does_not_change_linux_bytes(tmp_path):
 plan,m=example();m['present']['messages']={'1':'win','2':'lose'}
 a=build_linux_shell(plan,m,tmp_path/'a',service_adapters=adapters())
 m['present']['messages']={'2':'lose','1':'win'}
 b=build_linux_shell(plan,m,tmp_path/'b',service_adapters=adapters())
 assert a['modules_sha256']==b['modules_sha256'] and a['output']['sha256']==b['output']['sha256']
