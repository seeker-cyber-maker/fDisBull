// Finite Chrome acceptance, isolated profile and an exact loopback artifact list.
// Arguments: private prepared study directory, Chrome executable.
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';

async function browserMain() {
  const base = location.pathname.slice(0,location.pathname.lastIndexOf('/')+1);
  async function json(name) {const r=await fetch(base+name);if(!r.ok)throw Error('Fetch failed');return r.json();}
  async function bytes(name) {const r=await fetch(base+name);if(!r.ok)throw Error('Fetch failed');return r.arrayBuffer();}
  let device;
  try {
    const manifest=await json('cases.json');
    const adapter=await navigator.gpu?.requestAdapter();
    if(!adapter || adapter.info.isFallbackAdapter!==false)throw Error('Non-fallback browser GPU unavailable');
    device=await adapter.requestDevice();
    const result={format:'fdisbull-browser-web-execution-2',status:'running',
      runtime:navigator.userAgent.match(/Chrome\/[\d.]+/)?.[0] || 'unknown',
      adapter:{vendor:adapter.info.vendor,architecture:adapter.info.architecture,
               device:adapter.info.device,isFallbackAdapter:adapter.info.isFallbackAdapter},
      module_uil_sha256:manifest.module_uil_sha256,suites:[]};
    const observations={};
    for(const suite of manifest.suites) {
      const wt='wasm32-scalar-1',gt='webgpu-wgsl-scalar-1';
      const wdir=suite.builds[wt].directory+'/',gdir=suite.builds[gt].directory+'/';
      const wb=await json(wdir+'build.json'),gb=await json(gdir+'build.json');
      const {instantiateWasm,runWASM,runGPU}=await import(base+wdir+'host.mjs');
      const wasm=await bytes(wdir+'block.wasm');
      const wgsl=new TextDecoder().decode(await bytes(gdir+'block.wgsl'));
      const instance=await instantiateWasm(wasm,wb),rows=suite.vectors.map(v=>v.input);
      const cpu=runWASM(instance,wb.abi,rows),gpu=await runGPU(device,wgsl,gb,rows);
      observations[suite.name]={[wt]:cpu,[gt]:gpu};
      const summary={name:suite.name,negative_control:!!suite.negative_control};
      for(const [target,actual] of [[wt,cpu],[gt,gpu]]) {
        const mismatches=actual.filter((a,i)=>JSON.stringify(a)!==JSON.stringify(suite.vectors[i].expected)).length;
        if(suite.negative_control?mismatches===0:mismatches!==0)throw Error('Browser output mismatch');
        summary[target]={cases:actual.length,mismatches,refusals:actual.filter(a=>a.status===1).length};
      }
      result.suites.push(summary);
    }
    result.status='passed';
    document.body.textContent=JSON.stringify(result,null,2);
    await fetch(base+'result',{method:'POST',body:JSON.stringify({result,observations})});
  } catch(error) {
    document.body.textContent=String(error);
    await fetch(base+'result',{method:'POST',body:JSON.stringify({error:String(error)})});
  } finally {device?.destroy();}
}

const root=path.resolve(process.argv[2]),chrome=path.resolve(process.argv[3]);
const manifest=JSON.parse(await fs.readFile(path.join(root,'cases.json')));
const token=crypto.randomBytes(24).toString('hex'),prefix='/'+token+'/';
const publicManifest={module_uil_sha256:manifest.module_uil_sha256,suites:manifest.suites};
const allowed=new Map();
for(const suite of manifest.suites) for(const entry of Object.values(suite.builds)) {
  for(const name of ['build.json',...Object.keys(entry.build.artifacts)]) {
    const relative=entry.directory+'/'+name;
    allowed.set(prefix+relative,path.join(root,relative));
  }
}
let resolveDone,rejectDone;
const done=new Promise((resolve,reject)=>{resolveDone=resolve;rejectDone=reject;});
const server=http.createServer(async(req,res)=>{
  try {
    const name=new URL(req.url,'http://127.0.0.1').pathname;
    if(req.method==='POST' && name===prefix+'result') {
      const chunks=[];let size=0;
      for await(const chunk of req) {size+=chunk.length;if(size>8*1024*1024)throw Error('Reply limit');chunks.push(chunk);}
      const value=JSON.parse(Buffer.concat(chunks).toString());res.end('received');resolveDone(value);return;
    }
    if(req.method!=='GET') {res.writeHead(405);res.end();return;}
    if(name===prefix+'run') {
      res.setHeader('Content-Type','text/html');res.end('<!doctype html><title>UDC acceptance</title><body>Running<script type="module">('+browserMain.toString()+')();</script>');return;
    }
    if(name===prefix+'cases.json') {res.setHeader('Content-Type','application/json');res.end(JSON.stringify(publicManifest));return;}
    const file=allowed.get(name);
    if(!file) {res.writeHead(404);res.end();return;}
    res.setHeader('Content-Type',file.endsWith('.mjs')?'text/javascript':file.endsWith('.json')?'application/json':'application/octet-stream');
    res.end(await fs.readFile(file));
  } catch(error) {res.writeHead(500);res.end('Request failed');rejectDone(error);}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const flags=['--headless=new','--no-first-run','--no-default-browser-check','--enable-unsafe-webgpu','--use-angle=metal'];
const log=await fs.open(path.join(root,'browser.log'),'wx');
const child=spawn(chrome,[...flags,'--user-data-dir='+path.join(root,'browser-profile'),
  `http://127.0.0.1:${server.address().port}${prefix}run`],{detached:true,stdio:['ignore',log.fd,log.fd]});
const timer=setTimeout(()=>rejectDone(Error('Browser acceptance timed out')),60000);
child.once('error',rejectDone);
child.once('exit',code=>rejectDone(Error('Browser exited before acceptance: '+code)));
try {
  const {result,observations,error}=await done;
  if(error || result?.status!=='passed')throw Error(error || 'Incomplete browser receipt');
  result.launch_flags=flags;
  await fs.writeFile(path.join(root,'browser-result.json'),JSON.stringify(result,null,2)+'\n');
  await fs.writeFile(path.join(root,'browser-observations.json'),JSON.stringify(observations));
  console.log(JSON.stringify(result));
} finally {
  clearTimeout(timer);
  if(child.pid) {try {process.kill(-child.pid,'SIGTERM');} catch { /* Child already exited. */ }}
  server.closeAllConnections();await new Promise(resolve=>server.close(resolve));await log.close();
}
