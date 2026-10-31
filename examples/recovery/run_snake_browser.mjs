// Finite original-backed Node/Chrome qualification. No original EXE/FDB is served.
// BUNDLE STUDY PRIVATE_NPM_ROOT CHROME --run-dir NEW_OUTPUT
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import {spawn} from 'node:child_process';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {exerciseSnake} from './snake_browser_study.mjs';
import {exerciseRng} from './snake_rng_study.mjs';
const check=(ok,m)=>{if(!ok)throw Error(m);};
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const [bundleArg,studyArg,npmArg,chromeArg,...options]=process.argv.slice(2);
check(options[0]==='--run-dir'&&options[1]&&options.length===2,'BUNDLE STUDY PRIVATE_NPM_ROOT CHROME --run-dir NEW_OUTPUT');
const root=path.resolve(bundleArg),studyPath=path.resolve(studyArg),npmRoot=path.resolve(npmArg),chrome=path.resolve(chromeArg),output=path.resolve(options[1]);
await fs.mkdir(output,{recursive:false,mode:0o700});
const manifestBytes=await fs.readFile(path.join(root,'memory-shell.json')),studyBytes=await fs.readFile(studyPath);
const manifest=JSON.parse(manifestBytes),study=JSON.parse(studyBytes),verified=new Map();
for(const[name,expected]of Object.entries(manifest.artifacts)){
 check(name.split('/').every(x=>x&&x!=='.'&&x!=='..')&&!/[\\?#:]/.test(name),'Unsafe artifact');
 const p=path.join(root,name);check((await fs.realpath(p)).startsWith((await fs.realpath(root))+path.sep),'Escaping artifact');
 const data=await fs.readFile(p);check(sha(data)===expected,'Artifact changed: '+name);verified.set(name,data);
}
const helper=await fs.readFile(fileURLToPath(new URL('./snake_browser_study.mjs',import.meta.url)));
const initial=JSON.parse(verified.get('initial.json'));
const identities={module_uil_sha256:manifest.module_uil_sha256,manifest_sha256:sha(manifestBytes),study_sha256:sha(studyBytes),helper_sha256:sha(helper),runner_sha256:sha(await fs.readFile(fileURLToPath(import.meta.url))),artifacts:manifest.artifacts};
const deadline=Date.now()+420000;
const timed=async(p,ms,label,cleanup=false)=>{let t;const wait=cleanup?ms:Math.max(1,Math.min(ms,deadline-Date.now()));try{return await Promise.race([p,new Promise((_,reject)=>t=setTimeout(()=>reject(Error(label+' timeout')),wait))]);}finally{clearTimeout(t);}};
async function nodeRun(){
 const require=createRequire(path.join(npmRoot,'package.json'));
 const{create,globals}=await import(pathToFileURL(require.resolve('webgpu')));Object.assign(globalThis,globals);
 let gpu=create(['backend='+(process.env.FDISBULL_GPU_BACKEND||'metal')]),device,shell;
 const providers={wasm:{},webgpu:{}},phases={wasm:{},webgpu:{}},regions={wasm:{},webgpu:{}};
 try{
  const adapter=await gpu.requestAdapter();check(adapter&&adapter.info.isFallbackAdapter===false,'Real Node adapter required');device=await adapter.requestDevice();
  const{MemoryShell}=await import(pathToFileURL(path.join(root,'memory-shell.mjs')));
  const{createWasmMemoryProvider,createGPUMemoryProvider}=await import(pathToFileURL(path.join(root,'memory.mjs')));
  for(const[kind,functions]of Object.entries(manifest.variants))for(const[fn,v]of Object.entries(functions)){
   providers[kind][fn]=kind==='wasm'?await createWasmMemoryProvider(v.build,verified.get(v.directory+'/block.wasm')):
    await createGPUMemoryProvider(v.build,verified.get(v.directory+'/block.wgsl').toString(),{device});
  }
  for(const[kind,functions]of Object.entries(manifest.cut_variants||{}))for(const[fn,entries]of Object.entries(functions)){
   phases[kind][fn]={};
   for(const[name,v]of Object.entries(entries))phases[kind][fn][name]=kind==='wasm'?
    await createWasmMemoryProvider(v.build,verified.get(v.directory+'/block.wasm')):
    await createGPUMemoryProvider(v.build,verified.get(v.directory+'/block.wgsl').toString(),{device});
  }
  for(const[kind,functions]of Object.entries(manifest.region_variants||{}))for(const[fn,entries]of Object.entries(functions)){
   regions[kind][fn]={};
   for(const[name,v]of Object.entries(entries))regions[kind][fn][name]=kind==='wasm'?
    await createWasmMemoryProvider(v.build,verified.get(v.directory+'/block.wasm')):
    await createGPUMemoryProvider(v.build,verified.get(v.directory+'/block.wgsl').toString(),{device});
  }
  shell=new MemoryShell(manifest,providers,initial,phases,regions);
  const result=await timed(exerciseSnake(shell,manifest,study,initial),150000,'Node original study');
  if(manifest.regions)result.rng=await timed(exerciseRng(shell,manifest,study,initial),180000,'Node RNG study');
  result.host='node';result.runtime=process.version;result.adapter={vendor:adapter.info.vendor,architecture:adapter.info.architecture,isFallbackAdapter:adapter.info.isFallbackAdapter};result.identities=identities;
  await fs.writeFile(path.join(output,'node-result.json'),JSON.stringify(result,null,2)+'\n',{flag:'wx'});return result;
 }finally{if(shell)await shell.dispose();else await Promise.allSettled([
  ...Object.values(providers).flatMap(x=>Object.values(x)),
  ...[phases,regions].flatMap(r=>Object.values(r).flatMap(x=>Object.values(x).flatMap(y=>Object.values(y))))].map(p=>p.dispose()));device?.destroy();gpu=null;}
}

async function connect(profile){
 const deadline=Date.now()+15000;let port;
 while(Date.now()<deadline){try{[port]=String(await fs.readFile(path.join(profile,'DevToolsActivePort'))).trim().split('\n');break;}catch{await new Promise(r=>setTimeout(r,30));}}
 check(port,'Chrome debugging endpoint absent');
 const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json(),page=pages.find(x=>x.type==='page');check(page,'Chrome page absent');
 const socket=new WebSocket(page.webSocketDebuggerUrl),pending=new Map(),events=new Map();let sequence=0;
 await timed(new Promise((r,j)=>{socket.addEventListener('open',r,{once:true});socket.addEventListener('error',j,{once:true});}),5000,'CDP connection');
 socket.addEventListener('message',event=>{const m=JSON.parse(event.data),p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result);}else if(m.method){for(const resolve of events.get(m.method)||[])resolve(m.params);events.delete(m.method);}});
 const call=(method,params={})=>{const id=++sequence;return timed(new Promise((resolve,reject)=>{pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));}),160000,'CDP '+method);};
 return{call,event:method=>timed(new Promise(resolve=>{const list=events.get(method)||[];list.push(resolve);events.set(method,list);}),15000,method),close:()=>socket.close(),async evaluate(expression){const r=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});check(!r.exceptionDetails,r.exceptionDetails?.exception?.description||r.exceptionDetails?.text);return r.result.value;}};
}

async function chromeRun(){
 const prefix='/'+crypto.randomBytes(20).toString('hex')+'/',allowed=new Map([...verified].map(([n,b])=>[prefix+n,b]));
 allowed.set(prefix+'memory-shell.json',manifestBytes);allowed.set(prefix+'study.json',studyBytes);allowed.set(prefix+'snake_browser_study.mjs',helper);
 allowed.set(prefix+'snake_rng_study.mjs',await fs.readFile(fileURLToPath(new URL('./snake_rng_study.mjs',import.meta.url))));
 const server=http.createServer((req,res)=>{
  const name=new URL(req.url,'http://127.0.0.1').pathname,body=allowed.get(name);
  if(req.method!=='GET'||!body){res.writeHead(404);res.end();return;}
  res.setHeader('Content-Type',name.endsWith('.mjs')?'text/javascript':name.endsWith('.json')?'application/json':name.endsWith('.html')?'text/html':'application/octet-stream');res.end(body);
 });
 let child,childExit,log,cdp;const profile=path.join(output,'chrome-profile');
 try{
  await new Promise((r,j)=>{server.once('error',j);server.listen(0,'127.0.0.1',r);});await fs.mkdir(profile,{mode:0o700});log=await fs.open(path.join(output,'chrome.log'),'wx');
  const flags=['--headless=new','--no-first-run','--no-default-browser-check','--enable-unsafe-webgpu','--use-angle=metal','--window-size=1100,1000','--remote-debugging-port=0','--user-data-dir='+profile];
  child=spawn(chrome,[...flags,'about:blank'],{detached:true,stdio:['ignore',log.fd,log.fd]});
  childExit=new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',(code,signal)=>resolve({code,signal}));});
  cdp=await connect(profile);await cdp.call('Page.enable');
  await cdp.call('Page.addScriptToEvaluateOnNewDocument',{source:`globalThis.__snakeAdapters=[];if(navigator.gpu){globalThis.__snakeNativeAdapter=navigator.gpu.requestAdapter;navigator.gpu.requestAdapter=async function(...a){const x=await Reflect.apply(__snakeNativeAdapter,navigator.gpu,a);if(x)__snakeAdapters.push({vendor:x.info.vendor,architecture:x.info.architecture,isFallbackAdapter:x.info.isFallbackAdapter});return x;};}`});
  const url=`http://127.0.0.1:${server.address().port}${prefix}index.html`;
  const loaded=cdp.event('Page.loadEventFired');await cdp.call('Page.navigate',{url});await loaded;
  const result=await cdp.evaluate(`(async()=>{while(!globalThis.fdisbullMemoryReady)await new Promise(r=>setTimeout(r,10));const ctl=await fdisbullMemoryReady;ctl.pauseClock();navigator.gpu.requestAdapter=__snakeNativeAdapter;const manifest=await(await fetch('memory-shell.json')).json(),study=await(await fetch('study.json')).json(),initial=await(await fetch('initial.json')).json();const{exerciseSnake}=await import('./snake_browser_study.mjs');const r=await exerciseSnake(ctl.api,manifest,study,initial);r.host='chrome';r.runtime=navigator.userAgent;r.adapter=__snakeAdapters[0];if(!r.adapter||r.adapter.isFallbackAdapter!==false)throw Error('Real browser adapter required');globalThis.__snakeResult=r;return r;})()`);
  result.identities=identities;result.launch_flags=flags;
  if(manifest.regions)result.rng=await cdp.evaluate(`(async()=>{const ctl=await fdisbullMemoryReady;const manifest=ctl.api.describe(),study=await(await fetch('study.json')).json(),initial=await(await fetch('initial.json')).json();const{exerciseRng}=await import('./snake_rng_study.mjs');return exerciseRng(ctl.api,manifest,study,initial);})()`);
  result.instrumentation={gpu_observer:'Delegates native requestAdapter and returns original objects; restored after loading',core:'Public production shell API; normalized original input/clock adapters; ordinary state carried between events'};
  // Restore an independent initial scene for the production canvas screenshot.
  await cdp.evaluate(`(async()=>{const ctl=await fdisbullMemoryReady,initial=await(await fetch('initial.json')).json();ctl.api.selectBackend('wasm');ctl.api.replace(initial);await ctl.api.dispatch(ctl.api.describe().plan.initialize,{});ctl.paint();})()`);
  const shot=await cdp.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await fs.writeFile(path.join(output,'snake-browser.png'),Buffer.from(shot.data,'base64'),{flag:'wx'});
  result.screenshot={file:'snake-browser.png',sha256:sha(Buffer.from(shot.data,'base64'))};
  result.uiChecks=await trustedUI(cdp,url);
  result.uiRegressions=await browserRegressions(cdp,url);
  await cdp.evaluate(`fdisbullMemoryReady.then(c=>c.stop())`);cdp.close();cdp=null;
  try{process.kill(-child.pid,'SIGTERM');}catch{}
  result.chrome_exit=await timed(childExit,5000,'Chrome process cleanup',true);result.process_reaped=true;child=null;return result;
 }finally{
  cdp?.close();if(child?.pid){try{process.kill(-child.pid,'SIGTERM');}catch{}
   try{await timed(childExit,5000,'Chrome failure cleanup',true);}catch{try{process.kill(-child.pid,'SIGKILL');}catch{}await timed(childExit,5000,'Chrome forced cleanup',true);}}
  server.closeAllConnections();if(server.listening)await new Promise(r=>server.close(r));await log?.close();
 }
}

async function trustedUI(cdp,url){
 const results=[];
 const choices=manifest.regions?['original','lfsr16']:['original'];
 for(const choice of choices)for(const backend of ['wasm','webgpu']){
  await cdp.evaluate(`fdisbullMemoryReady.then(c=>c.stop())`);
  const loaded=cdp.event('Page.loadEventFired');await cdp.call('Page.navigate',{url});await loaded;
  await cdp.evaluate(`(async()=>{
   const ctl=await fdisbullMemoryReady;ctl.pauseClock();
   navigator.gpu.requestAdapter=__snakeNativeAdapter;
   const study=await(await fetch('study.json')).json(),manifest=ctl.api.describe(),initial=await(await fetch('initial.json')).json();
   const helper=await import('./snake_browser_study.mjs'),{MemoryShell}=await import('./memory-shell.mjs');
   globalThis.__snakeUI={ctl,study,manifest,helper,last:null,trusted:[],clock:study.initial_services.last_tick};
   const originalFinish=MemoryShell.prototype.finish;
   MemoryShell.prototype.finish=async function(...args){const result=await Reflect.apply(originalFinish,this,args);if(result.committed)__snakeUI.last=this.snapshot();return result;};
   // Only the clock service is controlled. Input handlers and commit/math code
   // run unchanged. The observation hook copies state after a real commit.
   Object.defineProperty(performance,'now',{configurable:true,value:()=> (__snakeUI.clock+.25)*manifest.plan.events.tick_ms});
   for(const type of ['keydown','pointerdown','pointerup','pointermove'])document.addEventListener(type,e=>__snakeUI.trusted.push({type,isTrusted:e.isTrusted,code:e.code||null}),true);
  })()`);
  await chooseBackend(cdp,'logic-backend',backend,manifest.plan.logic_functions);
  await chooseBackend(cdp,'render-backend',backend,[manifest.plan.render.function]);
  if(manifest.regions){
   await chooseBackend(cdp,'region-backend-rng',backend,['rng']);
   await cdp.evaluate(`(()=>{const s=document.getElementById('region-implementation-rng');s.value=${JSON.stringify(choice)};s.dispatchEvent(new Event('change',{bubbles:true}));if(__snakeUI.ctl.api.snapshot().implementations.rng!==${JSON.stringify(choice)})throw Error('RNG selector did not change actual implementation');})()`);
  }
  await cdp.evaluate(`(async()=>{
   const {ctl,study,manifest,helper}=__snakeUI,initial=await(await fetch('initial.json')).json();
   await ctl.api.discardPending();
   ctl.api.replace(helper.sourceInitial(initial,study));
   const result=await ctl.api.dispatch(manifest.plan.initialize,{[manifest.plan.events.clock]:study.initial_services.last_tick});
   if(!result.committed)throw Error('UI source initialization refused');ctl.paint();document.getElementById('game').focus();
  })()`);
  const rows=[];let buttons=0,events=0;
  for(const observation of choice==='original'?study.observations:study.rng.alternate_observations){
   if(observation.intervention)await cdp.evaluate(`(()=>{const w=__snakeUI.ctl.api.snapshot().words;w.set(${JSON.stringify(observation.intervention.words)},0);__snakeUI.ctl.api.replace(w);})()`);
   for(const event of observation.events){
    const before=await cdp.evaluate(`(__snakeUI.clock=${event.clock},__snakeUI.ctl.api.snapshot().revision)`);
    if(event.kind===manifest.plan.events.keyboard_kind){
     const pair=Object.entries(manifest.plan.keymap).find(([,v])=>v.ascii===event.ascii&&v.scan===event.scan);check(pair,'No DOM key for native input');
     const code=pair[0],key=code.startsWith('Key')?code.slice(3).toLowerCase():code==='Space'?' ':code;
     const virtual={ArrowLeft:37,ArrowUp:38,ArrowRight:39,ArrowDown:40,Space:32,Escape:27}[code]||code.charCodeAt(3);
     await cdp.call('Input.dispatchKeyEvent',{type:'keyDown',code,key,windowsVirtualKeyCode:virtual,...(event.ascii>=32?{text:String.fromCharCode(event.ascii),unmodifiedText:String.fromCharCode(event.ascii)}:{})});
     await cdp.call('Input.dispatchKeyEvent',{type:'keyUp',code,key,windowsVirtualKeyCode:virtual});
    }else if(event.kind===manifest.plan.events.pointer_kind){
     const position=await cdp.evaluate(`(()=>{const c=document.getElementById('game'),b=c.getBoundingClientRect(),sx=b.width/c.offsetWidth,sy=b.height/c.offsetHeight;return{x:b.left+c.clientLeft*sx+(${event.x}+.25)*c.clientWidth*sx/c.width,y:b.top+c.clientTop*sy+(${event.y}+.25)*c.clientHeight*sy/c.height};})()`);
     const type=(event.buttons&1)&&!(buttons&1)?'mousePressed':!(event.buttons&1)&&(buttons&1)?'mouseReleased':'mouseMoved';
     await cdp.call('Input.dispatchMouseEvent',{type,x:position.x,y:position.y,button:type==='mouseMoved'?'none':'left',buttons:event.buttons,clickCount:type==='mouseMoved'?0:1});buttons=event.buttons;
    }else{
     check(event.kind===manifest.plan.events.clock_kind,'Unknown original event');
     await cdp.evaluate(`(async()=>{await __snakeUI.ctl.api.dispatch(__snakeUI.manifest.plan.events.function,__snakeUI.helper.eventPatch(${JSON.stringify(event)},__snakeUI.manifest.plan));__snakeUI.ctl.paint();})()`);
    }
    await cdp.evaluate(`(async()=>{const end=Date.now()+10000;while(!__snakeUI.last||__snakeUI.last.revision<=${before}){if(Date.now()>end)throw Error('Trusted input was not committed');await new Promise(r=>setTimeout(r,5));}await new Promise(r=>setTimeout(r,0));})()`);events++;
   }
   const row=await cdp.evaluate(`(async()=>{const u=__snakeUI,o=${JSON.stringify(observation)},r=await u.helper.compareObservation(u.last.words,o,u.manifest,u.study);const canvas=document.getElementById('game'),image=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data,f=u.manifest.plan.frame;for(let i=0;i<f.width*f.height;i++){const color=f.palette[u.last.words[f.offset+i]];for(let c=0;c<3;c++)if(image[i*4+c]!==color[c])throw Error(o.id+' canvas RGB byte '+(i*4+c));if(image[i*4+3]!==255)throw Error('Canvas alpha differs');}return{id:o.id,...r};})()`);
   rows.push(row);
  }
  const trust=await cdp.evaluate(`({events:__snakeUI.trusted,closed:__snakeUI.ctl.api.capabilities().closed,status:document.getElementById('status').textContent})`);
  check(trust.events.length&&trust.events.every(e=>e.isTrusted),'Synthetic input reached DOM acceptance');
  check(trust.events.some(e=>e.type==='keydown')&&trust.events.some(e=>e.type==='pointerdown'),'Missing keyboard/pointer acceptance');
  check(trust.closed&&trust.status.includes('Exited'),'Esc did not dispose production input shell');
  results.push({backend,implementation:choice,status:'passed',observations:rows,normalized_events:events,trusted_dom_events:trust.events.length,full_canvas_rgb:true,exit_disposed:true,
   dom_backend_selectors:'value+change through the production handler; native select-popup keyboard driver is unavailable in this headless Mac profile',instrumentation:'Real CDP trusted game keyboard/mouse; declared frozen clock adapter; explicit DOM change events for backend selectors; read-only after-commit snapshot observer; initialization once and one declared original RAM intervention'});
 }
 return results;
}

async function key(cdp,code,keyValue,virtual,modifiers=0){
 await cdp.call('Input.dispatchKeyEvent',{type:'rawKeyDown',code,key:keyValue,windowsVirtualKeyCode:virtual,modifiers});
 await cdp.call('Input.dispatchKeyEvent',{type:'keyUp',code,key:keyValue,windowsVirtualKeyCode:virtual,modifiers:0});
}
async function chooseBackend(cdp,id,backend,functions){
 // Headless Mac native popup widgets ignored CDP Arrow/Space/Enter despite
 // receiving trusted DOM key events. Exercise the actual production change
 // handler explicitly; this instrumentation is not game-input acceptance.
 await cdp.evaluate(`(()=>{const s=document.getElementById(${JSON.stringify(id)});if([...s.options].find(o=>o.value===${JSON.stringify(backend)})?.disabled)throw Error('Requested backend is unavailable');s.focus();s.value=${JSON.stringify(backend)};s.dispatchEvent(new Event('change',{bubbles:true}));})()`);
 await cdp.evaluate(`(async()=>{const end=Date.now()+10000;while(true){const ctl=await fdisbullMemoryReady,b=ctl.api.capabilities().bindings,value=document.getElementById(${JSON.stringify(id)}).value;if(value===${JSON.stringify(backend)}&&${JSON.stringify(functions)}.every(fn=>b[fn]===${JSON.stringify(backend)}))break;if(Date.now()>end)throw Error('DOM selector did not change actual bindings: '+JSON.stringify({control:${JSON.stringify(id)},wanted:${JSON.stringify(backend)},value,bindings:b,active:document.activeElement.id,status:document.getElementById('status').textContent}));await new Promise(r=>setTimeout(r,5));}})()`);
}
async function browserRegressions(cdp,url){
 const checks=[];
 // This diagnostic changes presentation only after the original-backed quit.
 const square=await cdp.evaluate(`(()=>{const c=document.getElementById('game');c.width=2;c.height=2;const b=c.getBoundingClientRect();return{intrinsic:[c.width,c.height],content:[c.clientWidth,c.clientHeight],border_box:[b.width,b.height],closed:__snakeUI.ctl.api.capabilities().closed};})()`);
 check(square.closed&&square.intrinsic[0]===2&&square.intrinsic[1]===2&&Math.abs(square.content[0]-square.content[1])<=1,'Intrinsic square distorted by canvas layout');
 checks.push({name:'post-exit-square-canvas-uses-intrinsic-aspect',status:'passed',measurements:square});
 const loaded=cdp.event('Page.loadEventFired');await cdp.call('Page.navigate',{url});await loaded;
 await cdp.evaluate(`(async()=>{const ctl=await fdisbullMemoryReady;ctl.pauseClock();navigator.gpu.requestAdapter=__snakeNativeAdapter;await ctl.api.discardPending();globalThis.__reg={ctl,plan:ctl.api.describe().plan,pointerId:null,blurs:[]};document.getElementById('game').addEventListener('pointerdown',e=>__reg.pointerId=e.pointerId);window.addEventListener('blur',e=>__reg.blurs.push({isTrusted:e.isTrusted}));Object.defineProperty(performance,'now',{configurable:true,value:()=>0});document.getElementById('game').focus();})()`);
 const wait=async expression=>cdp.evaluate(`(async()=>{const end=Date.now()+10000;while(!(${expression})){if(Date.now()>end)throw Error('UI regression predicate timeout: '+${JSON.stringify(expression)});await new Promise(r=>setTimeout(r,5));}await new Promise(r=>setTimeout(r,0));return true;})()`);
 const state=()=>cdp.evaluate(`Array.from(__reg.ctl.api.snapshot().words.subarray(0,621))`);
 const before=await state();
 for(const[modifier,label]of[[2,'ctrl'],[1,'alt'],[4,'meta']]){
  await key(cdp,'ArrowUp','ArrowUp',38,modifier);
  await cdp.evaluate(`new Promise(r=>setTimeout(r,20))`);
  check(JSON.stringify(await state())===JSON.stringify(before),'Modifier shortcut affected game: '+label);
  checks.push({name:label+'-modified-key-does-not-reach-game',status:'passed'});
 }
 await cdp.evaluate(`document.getElementById('logic-backend').focus()`);
 await key(cdp,'KeyN','n',78);
 await cdp.evaluate(`new Promise(r=>setTimeout(r,20))`);
 check(JSON.stringify(await state())===JSON.stringify(before),'Unfocused canvas consumed a game key');
 checks.push({name:'keyboard-focus-excludes-toolbar-keys',status:'passed'});
 await chooseBackend(cdp,'logic-backend','webgpu',manifest.plan.logic_functions);
 await chooseBackend(cdp,'render-backend','webgpu',[manifest.plan.render.function]);
 await chooseBackend(cdp,'logic-backend','wasm',manifest.plan.logic_functions);
 await chooseBackend(cdp,'render-backend','wasm',[manifest.plan.render.function]);
 checks.push({name:'production-logic-and-render-change-handlers-change-bindings-both-ways',status:'passed',instrumentation:'Explicit value+change; native popup driver not qualified'});
 const point=()=>cdp.evaluate(`(()=>{const c=document.getElementById('game'),b=c.getBoundingClientRect(),sx=b.width/c.offsetWidth,sy=b.height/c.offsetHeight;return{x:b.left+c.clientLeft*sx+290.25*c.clientWidth*sx/c.width,y:b.top+c.clientTop*sy+50.25*c.clientHeight*sy/c.height};})()`);
 const press=async()=>{const p=await point();await cdp.call('Input.dispatchMouseEvent',{type:'mousePressed',...p,button:'left',buttons:1,clickCount:1});await wait(`__reg.ctl.api.snapshot().words[617]===1`);};
 const release=async()=>{const p=await point();await cdp.call('Input.dispatchMouseEvent',{type:'mouseReleased',...p,button:'left',buttons:0,clickCount:1});await wait(`__reg.ctl.api.snapshot().words[617]===0`);};
 await press();
 await cdp.evaluate(`(()=>{const c=document.getElementById('game');if(!c.hasPointerCapture(__reg.pointerId))throw Error('Trusted press did not capture pointer');c.releasePointerCapture(__reg.pointerId);})()`);
 await cdp.call('Input.dispatchMouseEvent',{type:'mouseMoved',x:5,y:5,button:'none',buttons:1});
 await wait(`__reg.ctl.api.snapshot().words[617]===0`);
 await cdp.call('Input.dispatchMouseEvent',{type:'mouseReleased',x:5,y:5,button:'left',buttons:0,clickCount:1});
 checks.push({name:'lost-native-pointer-capture-ends-logical-gesture',status:'passed'});
 await press();
 const other=await cdp.call('Target.createTarget',{url:'about:blank',background:false});
 let nativeBlur;
 try{
  await cdp.call('Target.activateTarget',{targetId:other.targetId});
  nativeBlur=await cdp.evaluate(`(async()=>{await new Promise(r=>setTimeout(r,100));return __reg.blurs.some(e=>e.isTrusted);})()`);
  if(!nativeBlur)await cdp.evaluate(`window.dispatchEvent(new Event('blur'))`);
  await wait(`__reg.ctl.api.snapshot().words[617]===0`);
 }finally{await cdp.call('Target.closeTarget',{targetId:other.targetId});await cdp.call('Page.bringToFront');}
 await release();
 checks.push({name:'window-blur-handler-releases-held-button',status:'passed',native_blur_observed:nativeBlur,
  instrumentation:nativeBlur?'Trusted native blur observed':'Native blur unavailable in this headless profile; explicit isTrusted:false blur event tests the production handler only'});
 await press();await chooseBackend(cdp,'logic-backend','webgpu',manifest.plan.logic_functions);
 await wait(`__reg.ctl.api.snapshot().words[617]===0`);await release();
 const counter=(await state())[609];await press();await release();
 check((await state())[609]===counter+1,'A new gesture after binding change remained stuck');
 checks.push({name:'backend-change-ends-held-gesture-and-next-press-is-consumed',status:'passed'});
 await cdp.evaluate(`__reg.ctl.stop()`);
 return checks;
}

let node;
if(process.env.FDISBULL_SNAKE_REUSE_NODE_RESULT){
 // Reuse only a sealed successful Node stage for exactly the same helper,
 // study and generated assets. Preserve its original runner identity.
 const source=path.resolve(process.env.FDISBULL_SNAKE_REUSE_NODE_RESULT),raw=await fs.readFile(source);node=JSON.parse(raw);
 check(node.status==='passed','Cannot reuse unsuccessful Node evidence');
 for(const k of ['module_uil_sha256','manifest_sha256','study_sha256','helper_sha256'])check(node.identities[k]===identities[k],'Reused Node identity differs: '+k);
 check(JSON.stringify(node.identities.artifacts)===JSON.stringify(identities.artifacts),'Reused Node artifacts differ');
 await fs.writeFile(path.join(output,'node-result.json'),raw,{flag:'wx'});
 await fs.writeFile(path.join(output,'node-reuse.json'),JSON.stringify({source,source_sha256:sha(raw),original_runner_sha256:node.identities.runner_sha256,current_runner_sha256:identities.runner_sha256,scope:'unchanged successful original-backed Node stage; browser and UI re-executed'},null,2)+'\n',{flag:'wx'});
}else node=await nodeRun();
const browser=await chromeRun();
browser.server_closed=true;
await fs.writeFile(path.join(output,'browser-result.json'),JSON.stringify(browser,null,2)+'\n',{flag:'wx'});
for(const backend of ['wasm','webgpu'])check(node.cpu[backend].projection_sha256===browser.cpu[backend].projection_sha256,'Host CPU projections differ');
check(JSON.stringify(node.arms)===JSON.stringify(browser.arms),'Host carried-state projections differ');
for(const[n,expected]of Object.entries(manifest.artifacts))check(sha(await fs.readFile(path.join(root,n)))===expected,'Bundle changed during execution');
console.log(JSON.stringify({status:'passed',node_cases:node.cpu.wasm.cases,browser_cases:browser.cpu.wasm.cases,arms:node.arms.length,observations_per_arm:node.arms[0].observations.length,ui_checks:browser.uiChecks.length,output}));
