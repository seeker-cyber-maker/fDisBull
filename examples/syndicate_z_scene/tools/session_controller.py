"""Local single-owner diagnostic controller. All commands and replies are private."""
from pathlib import Path
import os,json,socket,traceback,time,hashlib,base64
from fdisbull.project import Project
import argparse
ap=argparse.ArgumentParser(description='Own one original-game debugger session in a private directory')
ap.add_argument('--root',type=Path,required=True);ap.add_argument('--game-dir',type=Path,required=True);ap.add_argument('--dosbox',type=Path,required=True)
a=ap.parse_args();ROOT=a.root.absolute();GAME=a.game_dir.absolute();BACK=a.dosbox.absolute()
for directory in (ROOT,GAME):
    if any((p/'.git').exists() for p in [directory,*directory.parents]):raise ValueError('Use private directories outside Git')
if ROOT.exists():raise ValueError('Controller root must be a new directory')
ROOT.mkdir(parents=True,mode=0o700)
if hashlib.sha256((GAME/'MAIN.EXE').read_bytes()).hexdigest()!='bfbed760ab2def1fbe9f73588dc5a24747826c9b7660d615b02a8847d92bf078':
    raise ValueError('This research controller requires the examined MAIN release')
SOCK=ROOT/'control.sock'
P=Project.create(ROOT/'native.fdb',GAME/'MAIN.EXE',image='mz')
D=P.debugger(BACK,GAME)
LOG=(ROOT/'rpc-controller.jsonl').open('x')
(ROOT/'launch.json').write_text(json.dumps({'run':D.run_id,'pid':D.rpc.process.pid,'capabilities':D.rpc.capabilities,'metadata':D.metadata},indent=2))
count=0
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as srv:
 srv.bind(str(SOCK));srv.listen(1)
 try:
  while True:
   c,_=srv.accept()
   with c:
    f=c.makefile('r'); q=json.loads(f.readline());count+=1
    try:
     op=q['op'];a=q.get('args',{});t=time.monotonic()
     if op=='rpc':r=D.call(q['method'],a)
     elif op=='run':r=D.run(**a)
     elif op=='regs':r=D.registers()
     elif op=='key':r=D.keyboard_press(**a)
     elif op=='screenshot':
      r=D.call('video.screenshot');png=base64.b64decode(r.pop('png_base64'));p=ROOT/(q.get('name',f'frame-{count}.png'));p.write_bytes(png);r['local_path']=str(p)
     elif op=='click':r=D.click(**a)
     elif op=='save':r=D.save_state(**a)
     elif op=='load':r=D.load_state(**a)
     elif op=='close':r={'closed':True}
     else:raise ValueError('unknown action')
     ans={'ok':True,'result':r,'elapsed':time.monotonic()-t}
    except BaseException as e:ans={'ok':False,'error':repr(e),'traceback':traceback.format_exc()}
    LOG.write(json.dumps({'n':count,'q':q,'a':ans})+'\n');LOG.flush()
    c.sendall((json.dumps(ans)+'\n').encode())
   if q.get('op')=='close':break
 finally:
  pid=D.rpc.process.pid
  errors=[]
  try:
   D.close()
  except Exception as exc:errors.append(repr(exc))
  finally:
   try:P.__exit__()
   except Exception as exc:errors.append(repr(exc))
   LOG.close()
   (ROOT/'cleanup.json').write_text(json.dumps({'pid':pid,'closed_at':time.time(),'alive':Path(f'/proc/{pid}').exists(),'errors':errors}))
   SOCK.unlink(missing_ok=True)
