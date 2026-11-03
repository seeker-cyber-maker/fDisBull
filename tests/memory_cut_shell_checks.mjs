// Only wrappers for counting/delaying are used; calculations run in real blocks.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';

const root=path.resolve(process.argv[2]),budgetRoot=path.resolve(process.argv[3]);
const vectors=JSON.parse(await fs.readFile(path.resolve(process.argv[4])));
const useGPU=process.argv.includes('--gpu'),checks=[],shells=[],rawProviders=[];
const initial=()=>[0,0,0,7,...Array(12).fill(0)];
const {MemoryShell}=await import(pathToFileURL(path.join(root,'memory-shell.mjs')));
const {createWasmMemoryProvider,createGPUMemoryProvider}=await import(pathToFileURL(path.join(root,'memory.mjs')));
let gpu=null,device=null,adapter=null;
if(useGPU){
 const require=createRequire(path.join(process.env.FDISBULL_WEBGPU_MODULE_ROOT,'package.json'));
 const {create,globals}=await import(pathToFileURL(require.resolve('webgpu')));Object.assign(globalThis,globals);
 gpu=create(['backend='+(process.env.FDISBULL_GPU_BACKEND||'metal')]);adapter=await gpu.requestAdapter();
 assert.equal(adapter.info.isFallbackAdapter,false);device=await adapter.requestDevice();
}
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return{promise,resolve};}
function barrier(){const entered=deferred(),release=deferred();return{enter:entered.resolve,entered:entered.promise,wait:release.promise,release:release.resolve};}
const passed=name=>checks.push(name);
async function make(bundle=root,{gate=null,gateKey='wasm.math',instantiate=true}={}){
 const manifest=JSON.parse(await fs.readFile(path.join(bundle,'memory-shell.json')));
 const providers={wasm:{}},phases={wasm:{}},counts=Object.create(null),inputs=Object.create(null),wrappers=[];
 async function load(kind,entry,key){
  const real=kind==='wasm'?
   await createWasmMemoryProvider(entry.build,await fs.readFile(path.join(bundle,entry.directory,'block.wasm'))):
   await createGPUMemoryProvider(entry.build,await fs.readFile(path.join(bundle,entry.directory,'block.wgsl'),'utf8'),{device});
  rawProviders.push(real);counts[key]=0;inputs[key]=[];
  const wrapper=Object.freeze({describe:()=>real.describe(),get epoch(){return real.epoch;},get closed(){return real.closed;},get lost(){return real.lost;},dispose:()=>real.dispose(),
   async invoke(words){counts[key]++;inputs[key].push({guarded_word:words[3]});const result=await real.invoke(words);if(gate&&key===gateKey){gate.enter();await gate.wait;}return result;}});
  wrappers.push(wrapper);return wrapper;
 }
 for(const kind of device?['wasm','webgpu']:['wasm']){
  providers[kind]={};phases[kind]={};
  for(const [fn,entry]of Object.entries(manifest.variants[kind]))providers[kind][fn]=await load(kind,entry,kind+'.'+fn);
  for(const [fn,entries]of Object.entries(manifest.cut_variants[kind])){
   phases[kind][fn]={};for(const [name,entry]of Object.entries(entries))phases[kind][fn][name]=await load(kind,entry,kind+'.'+fn+'.'+name);
  }
 }
 const shell=instantiate?new MemoryShell(manifest,providers,initial(),phases):null;
 if(shell)shells.push(shell);return{shell,providers,phases,counts,inputs,manifest,wrappers};
}
try{
 {
  const {shell,counts,inputs}=await make();
  const ticket=shell.start('advance',{10:1,9:2});await ticket.ready;
  assert.deepEqual(Array.from(shell.snapshot().words),initial());
  const result=await shell.finish(ticket.id);assert.equal(result.status,'committed');
  assert.deepEqual(Array.from(shell.snapshot().words),vectors[0].words);
  assert.equal(counts['wasm.math'],1);assert.equal(counts['wasm.advance'],0);
  assert.equal(inputs['wasm.math'][0].guarded_word,8);assert.equal(shell.snapshot().words[3],7);
  assert.equal(counts['wasm.advance.entry'],1);assert.equal(counts['wasm.advance.resume_1'],1);
  assert.deepEqual(result.execution.map(x=>[x.function,x.kind,x.phase||null]),[
   ['advance','phase','entry'],['math','block',null],['advance','phase','resume_1'],['draw','block',null]]);
  assert.equal(result.execution.filter(x=>x.function!=='draw').reduce((s,x)=>s+x.steps,0)-2,vectors[0].caller_steps);
  result.execution[0].steps=999;assert.equal(shell.describe().program.functions.advance.max_steps,7);
  passed('actual-selected-nested-block-and-lexical-tails-stage-once');
  passed('private-phases-do-not-introduce-application-guard-or-footprint-checkpoints');
 }
 {
  const {shell,counts}=await make();
  const result=await shell.dispatch('advance',{10:0});assert.equal(result.status,'committed');
  assert.equal(counts['wasm.math'],0);assert.equal(counts['wasm.advance.resume_1'],0);
  assert.deepEqual(result.execution.map(x=>x.kind),['phase']);assert.equal(shell.snapshot().words[0],1);
  passed('untaken-cut-does-not-call-callee-or-continuation');
 }
 {
  const {shell,counts}=await make();
  const result=await shell.dispatch('constructor',{}, {render:false});
  assert.equal(result.status,'committed');assert.equal(shell.snapshot().words[0],3);
  assert.equal(counts['wasm.constructor'],1);assert.equal(counts['wasm.advance.entry'],0);
  assert.deepEqual(result.execution.map(x=>[x.function,x.kind]),[['constructor','block']]);
  passed('reserved-javascript-function-name-is-not-an-inherited-cut-owner');
 }
 {
  const {shell}=await make();
  for(const vector of vectors){const result=await shell.dispatch('advance',vector.patch);assert.equal(result.status,'committed');assert.deepEqual(Array.from(shell.snapshot().words),vector.words);}
  passed('exact-source-budget-and-carried-source-reference-state');
 }
 {
  const {shell,counts}=await make(budgetRoot),before=shell.snapshot();
  const result=await shell.dispatch('advance',{10:1});assert.equal(result.status,'failed');
  assert.match(result.reason,/budget exhausted/);assert.deepEqual(shell.snapshot(),before);
  assert.equal(counts['wasm.math'],1);assert.equal(counts['wasm.advance.resume_1'],1);
  assert.equal(counts['wasm.draw'],0);passed('aggregate-caller-budget-refuses-and-rolls-back-all-stages');
 }
 {
  const {shell,counts}=await make(),before=shell.snapshot();
  const result=await shell.dispatch('advance',{10:1,11:16});assert.equal(result.status,'failed');
  assert.match(result.reason,/refused/);assert.deepEqual(shell.snapshot(),before);
  assert.equal(counts['wasm.math'],0);assert.equal(shell.describe().program.memory.words,16);
  passed('private-control-cannot-be-addressed-as-an-extra-app-word');
 }
 {
  const gate=barrier(),{shell,counts}=await make(root,{gate});
  const ticket=shell.start('advance',{10:1});await gate.entered;shell.cancel(ticket.id);gate.release();
  assert.equal((await shell.finish(ticket.id)).status,'discarded');assert.deepEqual(Array.from(shell.snapshot().words),initial());
  assert.equal(counts['wasm.math'],1);passed('nested-child-cancellation-discards-private-state');
 }
 {
  const gate=barrier(),{shell}=await make(root,{gate,gateKey:'wasm.advance.entry'});
  const ticket=shell.start('advance',{10:1});await gate.entered;shell.selectBackend('wasm',['math']);shell.selectBackend('wasm',['math']);gate.release();
  const result=await shell.finish(ticket.id);assert.equal(result.status,'discarded');assert.deepEqual(Array.from(shell.snapshot().words),initial());
  passed('nested-selection-aba-stales-whole-transaction');
 }
 {
  const gate=barrier(),{shell,wrappers}=await make(root,{gate});
  const ticket=shell.start('advance',{10:1});await gate.entered;
  const finishing=shell.finish(ticket.id);let settled=false;const disposed=shell.dispose().then(x=>(settled=true,x));
  await Promise.resolve();assert.equal(settled,false);gate.release();
  assert.equal((await finishing).status,'discarded');assert.deepEqual(await disposed,{settled:true});
  assert(wrappers.every(x=>x.closed));assert.throws(()=>shell.snapshot());
  passed('dispose-drains-child-and-all-phase-owners-before-settlement');
 }
 {
  const a=await make(),b=await make(root,{instantiate:false});
  b.phases.wasm.advance.entry=a.phases.wasm.advance.entry;
  assert.throws(()=>new MemoryShell(b.manifest,b.providers,initial(),b.phases),/already belongs/);
  assert.equal((await a.shell.dispatch('advance',{10:1})).status,'committed');
  passed('phase-wrapper-cannot-belong-to-two-shells');
 }
 {
  const a=await make(root,{instantiate:false});delete a.phases.wasm.advance.entry;
  assert.throws(()=>new MemoryShell(a.manifest,a.providers,initial(),a.phases),/phase unavailable/);
  passed('missing-phase-refuses-admission');
 }
 {
  const a=await make(root,{instantiate:false});
  a.manifest.cuts.functions.advance.yields['1'].callee='draw';
  assert.throws(()=>new MemoryShell(a.manifest,a.providers,initial(),a.phases),/Cut callee or continuation differs/);
  passed('lowered-callee-cannot-depart-from-exact-cut-document');
 }
 {
  const {shell,phases}=await make();delete phases.wasm.advance.entry;
  assert.equal((await shell.dispatch('advance',{10:1})).status,'committed');
  passed('phase-registry-is-owned-and-copied-at-admission');
 }
 {
  const {shell,phases}=await make();await phases.wasm.advance.resume_1.dispose();
  assert.equal(shell.capabilities().backends.wasm,false);
  assert.throws(()=>shell.selectBackend('wasm',['advance']),/phase unavailable/);
  const before=shell.snapshot(),result=await shell.dispatch('advance',{10:1});
  assert.equal(result.status,'failed');assert.deepEqual(shell.snapshot(),before);
  passed('closed-phase-refuses-selection-and-execution-without-commit');
 }
 {
  const {shell,phases}=await make();const ticket=shell.start('advance',{10:1});await ticket.ready;
  await phases.wasm.advance.entry.dispose();
  assert.equal((await shell.finish(ticket.id)).status,'discarded');
  assert.deepEqual(Array.from(shell.snapshot().words),initial());
  passed('completed-phase-lease-remains-validity-condition-until-final-commit');
 }
 if(device){
  {
   for(const [owner,math]of [['wasm','webgpu'],['webgpu','wasm'],['webgpu','webgpu']]){
    const {shell,counts}=await make();shell.selectBackend(owner,['advance','draw']);shell.selectBackend(math,['math']);
    for(const vector of vectors){const result=await shell.dispatch('advance',vector.patch);assert.equal(result.status,'committed');assert.deepEqual(Array.from(shell.snapshot().words),vector.words);if(vector.patch[10]===1)assert(result.execution.some(x=>x.function==='math'&&x.backend===math));}
    assert.equal(counts[math+'.math'],3);assert.equal(counts[(math==='wasm'?'webgpu':'wasm')+'.math'],0);
   }
   passed('selected-nested-gpu-and-wasm-backings-carry-reference-state');
  }
  {
   const gate=barrier(),{shell,counts}=await make(root,{gate,gateKey:'wasm.advance.entry'});
   const ticket=shell.start('advance',{10:1});await gate.entered;shell.selectBackend('webgpu',['math']);gate.release();
   const result=await shell.finish(ticket.id);assert.equal(result.status,'discarded');
   assert.equal(counts['wasm.math'],1);assert.equal(counts['webgpu.math'],0);
   assert(result.execution.some(x=>x.function==='math'&&x.backend==='wasm'));
   assert.deepEqual(Array.from(shell.snapshot().words),initial());
   passed('nested-call-uses-captured-binding-even-after-prefix-await');
  }
 }
 for(const shell of shells)await shell.dispose();
 if(device){const buffer=device.createBuffer({size:4,usage:GPUBufferUsage.COPY_SRC});buffer.destroy();passed('phase-wrappers-borrow-shared-device');}
 console.log(JSON.stringify({status:'passed',checks,adapter:adapter?{isFallbackAdapter:adapter.info.isFallbackAdapter,vendor:adapter.info.vendor,architecture:adapter.info.architecture}:null}));
}finally{for(const shell of shells)await shell.dispose();await Promise.allSettled(rawProviders.map(x=>x.dispose()));device?.destroy();gpu=null;}
