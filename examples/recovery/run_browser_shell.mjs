// Finite Node + real Chrome qualification around the production browser shell.
// Arguments: BUNDLE PRIVATE_NPM_ROOT CHROME_EXECUTABLE.
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {exerciseShell} from './web_shell_study.mjs';

const check=(value,message)=>{if(!value)throw Error(message);};
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
const root=path.resolve(process.argv[2]);
const npmRoot=path.resolve(process.argv[3]),chrome=path.resolve(process.argv[4]);
const manifestBytes=await fs.readFile(path.join(root,'shell.json'));
const studyBytes=await fs.readFile(path.join(root,'study.json'));
const manifest=JSON.parse(manifestBytes),study=JSON.parse(studyBytes);
const helperPath=fileURLToPath(new URL('./web_shell_study.mjs',import.meta.url));
const helperBytes=await fs.readFile(helperPath);
const verified=new Map();
for(const [name,expected] of Object.entries(manifest.artifacts)) {
  check(name.split('/').every(part=>part && part!=='.' && part!=='..') && !/[\\?#:]/.test(name),'Unsafe artifact path');
  check(['.html','.mjs','.json','.wasm','.wat','.wgsl'].includes(path.extname(name)),'Non-shell artifact refused');
  const filename=path.join(root,name),real=await fs.realpath(filename);
  check(real.startsWith((await fs.realpath(root))+path.sep),'Artifact outside bundle');
  const bytes=await fs.readFile(filename);check(sha(bytes)===expected,'Artifact hash differs: '+name);
  verified.set(name,bytes);
}
const identity={shell_manifest_sha256:sha(manifestBytes),study_sha256:sha(studyBytes),
  study_helper_sha256:sha(helperBytes),artifacts:structuredClone(manifest.artifacts)};
const timed=async(work,milliseconds,label)=>{
  let timer;
  try {return await Promise.race([work,new Promise((resolve,reject)=>{timer=setTimeout(()=>reject(Error(label+' timed out')),milliseconds);})]);}
  finally {clearTimeout(timer);}
};

async function nodeRun() {
  const require=createRequire(path.join(npmRoot,'package.json'));
  const {create,globals}=await import(pathToFileURL(require.resolve('webgpu')));
  Object.assign(globalThis,globals);
  const {createShell,createWasmProvider,createGPUProvider}=await import(pathToFileURL(path.join(root,'shell.mjs')));
  let gpu=create(['backend='+(process.env.FDISBULL_GPU_BACKEND || 'metal')]);
  let shell,device;
  const providers={};
  try {
    const adapter=await gpu.requestAdapter();
    check(adapter && adapter.info.isFallbackAdapter===false,'Non-fallback Node GPU required');
    device=await adapter.requestDevice();
    const w=manifest.variants.wasm.directory,g=manifest.variants.webgpu.directory;
    providers.wasm=await createWasmProvider(JSON.parse(verified.get(w+'/build.json')),verified.get(w+'/block.wasm'));
    providers.webgpu=await createGPUProvider(JSON.parse(verified.get(g+'/build.json')),
      verified.get(g+'/block.wgsl').toString(),{device,ownsDevice:false});
    shell=await createShell(manifest,providers);
    shell.addRecord('city-a',{});shell.addRecord('city-b',{});shell.selectEntity('city-a');
    const result=await timed(exerciseShell(shell,manifest,study),110000,'Node shell study');
    await timed(shell.dispose(),5000,'Borrowed-provider disposal');
    device.pushErrorScope('validation');
    const probe=device.createBuffer({size:4,usage:GPUBufferUsage.COPY_SRC});probe.destroy();
    check(await device.popErrorScope()===null,'Borrowed device was destroyed by shell');
    result.host='node';result.runtime=process.version;
    result.adapter={vendor:adapter.info.vendor,architecture:adapter.info.architecture,
      device:adapter.info.device,isFallbackAdapter:adapter.info.isFallbackAdapter};
    result.identities=identity;
    result.checks.push({name:'borrowed-device-retained-after-shell-disposal',status:'passed'});
    await fs.writeFile(path.join(root,'node-shell-result.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
    return result;
  } finally {
    const disposal=shell ? shell.dispose() : Promise.allSettled(Object.values(providers).map(provider=>provider.dispose()));
    device?.destroy();await timed(disposal,5000,'Node cleanup');gpu=null;
  }
}

async function browserMain() {
  const base=location.pathname.slice(0,location.pathname.lastIndexOf('/')+1);
  const ensure=(condition,message)=>{if(!condition)throw Error(message);};
  const same=(a,b,message)=>ensure(JSON.stringify(a)===JSON.stringify(b),message);
  const wait=async(predicate,label,milliseconds=10000)=>{
    const deadline=performance.now()+milliseconds;
    while(!predicate()) {if(performance.now()>deadline)throw Error(label+' timed out');await new Promise(resolve=>setTimeout(resolve,5));}
  };
  const json=async name=>{const response=await fetch(base+name);ensure(response.ok,'Study resource unavailable');return response.json();};
  let api,nativeRequestAdapter;
  const adapters=[];
  try {
    ensure(navigator.gpu,'Browser WebGPU unavailable');
    nativeRequestAdapter=navigator.gpu.requestAdapter;
    // Test instrumentation delegates every native call and returns the exact adapter.
    navigator.gpu.requestAdapter=async function(...args) {
      const adapter=await Reflect.apply(nativeRequestAdapter,navigator.gpu,args);
      if(adapter)adapters.push({vendor:adapter.info.vendor,architecture:adapter.info.architecture,
        device:adapter.info.device,isFallbackAdapter:adapter.info.isFallbackAdapter});
      return adapter;
    };
    await wait(()=>globalThis.fdisbullShellReady,'Production app initialization');
    api=await globalThis.fdisbullShellReady;
    navigator.gpu.requestAdapter=nativeRequestAdapter;
    ensure(adapters.length>0 && adapters.every(a=>a.isFallbackAdapter===false),'Production app did not acquire a real non-fallback adapter');
    const manifest=await json('shell.json'),study=await json('study.json');
    const {exerciseShell}=await import(base+'web_shell_study.mjs');
    const result=await exerciseShell(api,manifest,study);
    const uiChecks=[];
    const passed=name=>uiChecks.push({name,status:'passed'});
    const element=id=>document.getElementById(id);
    const inputs=Array.from(document.querySelectorAll('#inputs input'));
    same(inputs.map(input=>input.dataset.cell).sort(),[...new Set(Object.values(manifest.plan.inputs))].sort(),'UI exposes extra state controls');
    passed('production-controls-follow-pinned-input-map');
    const record=element('record'),backend=element('backend'),run=element('run-step');
    function select(control,value) {control.value=value;control.dispatchEvent(new Event('change',{bubbles:true}));}
    function edit(vector) {
      for(const input of inputs) {
        const port=Object.keys(manifest.plan.inputs).find(name=>manifest.plan.inputs[name]===input.dataset.cell);
        if(input.type==='checkbox')input.checked=vector.inputs[port];else input.value=String(vector.inputs[port]);
        input.dispatchEvent(new Event('input',{bubbles:true}));
      }
    }
    function commitOnly(before,after,expected) {
      ensure(after.revision===before.revision+1,'UI step revision differs');
      const writes=new Set();
      for(const [port,value] of Object.entries(expected)) {
        const cell=manifest.plan.outputs[port],layout=manifest.layout.cells[cell];
        ensure(after.values[cell]===value,'UI output differs from original');
        for(let i=0;i<layout.size;i++)writes.add(layout.offset+i);
      }
      for(let i=0;i<before.bytes.length;i++)if(!writes.has(i))ensure(before.bytes[i]===after.bytes[i],'UI commit changed unrelated memory');
    }
    for(const [index,name] of ['wasm','webgpu'].entries()) {
      const vector=study.normal[index] || study.normal[0];
      select(record,'city-b');select(backend,name);edit(vector);
      ensure(api.capabilities().selected===name && api.snapshot().id==='city-b','UI selection did not reach shell');
      const before=api.snapshot();run.click();
      await wait(()=>api.snapshot('city-b').revision>before.revision && !run.disabled,'UI '+name+' step');
      commitOnly(before,api.snapshot('city-b'),vector.expected);
      ensure(element('status').textContent.startsWith('Committed'),'UI did not report committed outcome');
      passed('actual-'+name+'-control-step-matches-original');
    }
    {
      const vector=study.normal[0];edit(vector);const before=api.snapshot();run.click();
      ensure(run.disabled && !record.disabled && !backend.disabled && inputs.every(input=>!input.disabled),'Pending controls are incorrectly locked');
      select(record,'city-a');select(record,'city-b');
      await wait(()=>!run.disabled,'Stale UI view result');
      same(Array.from(api.snapshot('city-b').bytes),Array.from(before.bytes),'Stale UI result committed');
      ensure(api.snapshot('city-b').revision===before.revision,'Stale UI result advanced revision');
      ensure(element('status').textContent.startsWith('Discarded'),'UI did not report discarded result');
      passed('pending-view-aba-discards-through-real-controls');
    }
    {
      const vector=study.normal[0];edit(vector);const before=api.snapshot();run.click();
      element('cancel-step').click();ensure(!run.disabled,'Cancel did not release logical UI action');run.click();
      await wait(()=>{
        const state=api.snapshot('city-b');
        ensure(run.disabled || state.revision!==before.revision,'Old finally handler unlocked a newer operation');
        return !run.disabled;
      },'Cancel/new UI step');
      commitOnly(before,api.snapshot('city-b'),vector.expected);
      ensure(element('status').textContent.startsWith('Committed'),'An older action overwrote the new outcome');
      passed('cancel-new-run-guards-current-action-and-commits-once');
    }
    element('new-record-name').value='city-ui';element('add-record').click();
    ensure(api.snapshot().id==='city-ui','Add-record control did not select new entity');
    for(const [name,descriptor] of Object.entries(manifest.plan.state))ensure(api.snapshot().values[name]===descriptor.initial,'New UI entity has incorrect initial state');
    passed('add-record-reuses-the-same-scene');select(record,'city-b');
    result.host='chrome';result.runtime=navigator.userAgent.match(/Chrome\/[\d.]+/)?.[0] || 'unknown';
    result.adapter=adapters[0];result.uiChecks=uiChecks;
    result.instrumentation={production_html:'unchanged apart from test module inserted before app.mjs',
      gpu_observer:'delegates native requestAdapter and returns exact native objects; removed after initialization',
      interface:'public production UI facade; real DOM events'};
    await new Promise(requestAnimationFrame);await new Promise(requestAnimationFrame);
    await fetch(base+'result',{method:'POST',body:JSON.stringify({result})});
  } catch(error) {
    await fetch(base+'result',{method:'POST',body:JSON.stringify({error:String(error)})});
  } finally {
    if(nativeRequestAdapter)navigator.gpu.requestAdapter=nativeRequestAdapter;
    if(api)await api.dispose();
  }
}

async function screenshot(profile) {
  const [port]=String(await fs.readFile(path.join(profile,'DevToolsActivePort'))).trim().split('\n');
  const pages=await (await fetch('http://127.0.0.1:'+port+'/json/list',{signal:AbortSignal.timeout(3000)})).json();
  const target=pages.find(page=>page.type==='page');check(target,'No browser page');
  const socket=new WebSocket(target.webSocketDebuggerUrl);
  try {
    await timed(new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});}),3000,'Screenshot socket');
    const response=new Promise((resolve,reject)=>socket.addEventListener('message',event=>{
      const value=JSON.parse(event.data);if(value.id===1) value.error?reject(Error(value.error.message)):resolve(value.result);
    }));
    socket.send(JSON.stringify({id:1,method:'Page.captureScreenshot',params:{format:'png',captureBeyondViewport:false}}));
    const {data}=await timed(response,5000,'Screenshot');
    const bytes=Buffer.from(data,'base64');await fs.writeFile(path.join(root,'browser-shell.png'),bytes,{flag:'wx'});
    return {status:'captured',file:'browser-shell.png',sha256:sha(bytes)};
  } finally {socket.close();}
}

async function chromeRun() {
  const token=crypto.randomBytes(24).toString('hex'),prefix='/'+token+'/';
  const instrument='('+browserMain.toString()+')();';
  const tag='<script type="module" src="./app.mjs"></script>';
  const html=verified.get('index.html').toString();check(html.includes(tag),'Production app script not found');
  const servedHTML=html.replace(tag,'<script type="module" src="./shell-acceptance.mjs"></script>'+tag);
  const allowed=new Map([...verified].map(([name,bytes])=>[prefix+name,bytes]));
  allowed.set(prefix+'index.html',Buffer.from(servedHTML));allowed.set(prefix+'shell.json',manifestBytes);
  allowed.set(prefix+'study.json',studyBytes);allowed.set(prefix+'web_shell_study.mjs',helperBytes);
  allowed.set(prefix+'shell-acceptance.mjs',Buffer.from(instrument));
  let resolveDone,rejectDone;
  const done=new Promise((resolve,reject)=>{resolveDone=resolve;rejectDone=reject;});
  const server=http.createServer(async(request,response)=>{
    try {
      const name=new URL(request.url,'http://127.0.0.1').pathname;
      if(request.method==='POST' && name===prefix+'result') {
        let size=0;const chunks=[];
        for await(const chunk of request) {size+=chunk.length;check(size<=8*1024*1024,'Reply limit');chunks.push(chunk);}
        const value=JSON.parse(Buffer.concat(chunks));response.end('received');resolveDone(value);return;
      }
      if(request.method!=='GET') {response.writeHead(405);response.end();return;}
      const body=allowed.get(name);if(!body) {response.writeHead(404);response.end();return;}
      response.setHeader('Content-Type',name.endsWith('.mjs')?'text/javascript':name.endsWith('.html')?'text/html':name.endsWith('.json')?'application/json':'application/octet-stream');
      response.end(body);
    } catch(error) {if(!response.headersSent)response.writeHead(500);response.end('Request failed');rejectDone(error);}
  });
  const profile=path.join(root,'browser-shell-profile');
  const flags=['--headless=new','--no-first-run','--no-default-browser-check','--enable-unsafe-webgpu','--use-angle=metal','--window-size=1280,1100','--remote-debugging-port=0'];
  let log,child,timer;
  try {
    await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
    await fs.mkdir(profile,{mode:0o700});
    log=await fs.open(path.join(root,'browser-shell.log'),'wx');
    child=spawn(chrome,[...flags,'--user-data-dir='+profile,`http://127.0.0.1:${server.address().port}${prefix}index.html`],
      {detached:true,stdio:['ignore',log.fd,log.fd]});
    timer=setTimeout(()=>rejectDone(Error('Browser shell study timed out')),115000);
    child.once('error',rejectDone);child.once('exit',code=>rejectDone(Error('Browser exited before completion: '+code)));
    const {result,error}=await done;check(!error && result?.status==='passed',error || 'Incomplete browser study');
    result.identities=identity;result.launch_flags=flags;
    result.instrumentation.test_module_sha256=sha(instrument);
    result.instrumentation.original_html_sha256=sha(verified.get('index.html'));
    result.instrumentation.served_html_sha256=sha(servedHTML);
    try {result.screenshot=await timed(screenshot(profile),4000,'Optional screenshot');} catch(error) {result.screenshot={status:'unavailable',reason:String(error)};}
    await fs.writeFile(path.join(root,'browser-shell-result.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});
    return result;
  } finally {
    clearTimeout(timer);if(child?.pid) {try {process.kill(-child.pid,'SIGTERM');} catch { /* Already exited. */ }}
    server.closeAllConnections();if(server.listening)await new Promise(resolve=>server.close(resolve));await log?.close();
  }
}

const node=await nodeRun();
const browser=await chromeRun();
for(const name of ['wasm','webgpu'])check(JSON.stringify(node.normal[name].outputs)===JSON.stringify(browser.normal[name].outputs),'Node/browser original output arrays differ');
check(JSON.stringify(node.chain.outputs)===JSON.stringify(browser.chain.outputs),'Node/browser carried-state chain differs');
for(const [name,expected] of Object.entries(manifest.artifacts))check(sha(await fs.readFile(path.join(root,name)))===expected,'Bundle mutated during study');
console.log(JSON.stringify({status:'passed',module_uil_sha256:manifest.module_uil_sha256,
  normal_cases_per_backend_per_host:node.normal.wasm.cases,chain_steps_per_host:node.chain.steps,
  node_checks:node.checks.length,browser_checks:browser.checks.length,ui_checks:browser.uiChecks.length,
  screenshot:browser.screenshot.status}));
