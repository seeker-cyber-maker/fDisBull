// Deterministic orchestration checks delegate computation to actual Wasm/GPU.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';

const root=path.resolve(process.argv[2]),badRoot=path.resolve(process.argv[3]);
const useGPU=process.argv.includes('--gpu'),checks=[];
const initial=()=>[0,0,0,7,...Array(12).fill(0)];
const manifest=JSON.parse(await fs.readFile(path.join(root,'memory-shell.json')));
const {MemoryShell}=await import(pathToFileURL(path.join(root,'memory-shell.mjs')));
const {createWasmMemoryProvider,createGPUMemoryProvider}=await import(pathToFileURL(path.join(root,'memory.mjs')));
let gpu=null,device=null,adapter=null;
if(useGPU){
 const require=createRequire(path.join(process.env.FDISBULL_WEBGPU_MODULE_ROOT,'package.json'));
 const {create,globals}=await import(pathToFileURL(require.resolve('webgpu')));Object.assign(globalThis,globals);
 gpu=create(['backend='+(process.env.FDISBULL_GPU_BACKEND||'metal')]);adapter=await gpu.requestAdapter();
 assert.equal(adapter.info.isFallbackAdapter,false);device=await adapter.requestDevice();
}
const allShells=[];
async function make(bundle=root,{gate=null}={}){
 const m=JSON.parse(await fs.readFile(path.join(bundle,'memory-shell.json'))),providers={wasm:{}};
 for(const [fn,v]of Object.entries(m.variants.wasm))providers.wasm[fn]=await createWasmMemoryProvider(v.build,await fs.readFile(path.join(bundle,v.directory,'block.wasm')));
 if(device){providers.webgpu={};for(const[fn,v]of Object.entries(m.variants.webgpu))providers.webgpu[fn]=await createGPUMemoryProvider(v.build,await fs.readFile(path.join(bundle,v.directory,'block.wgsl'),'utf8'),{device});}
 if(gate){
  const real=providers.wasm.advance;
  providers.wasm.advance=Object.freeze({describe:()=>real.describe(),get closed(){return real.closed;},get lost(){return real.lost;},get epoch(){return real.epoch;},dispose:()=>real.dispose(),
   async invoke(words){const result=await real.invoke(words);gate.enter();await gate.wait;return result;}});
 }
 const shell=new MemoryShell(m,providers,initial());allShells.push(shell);return{shell,providers,manifest:m};
}
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return{promise,resolve};}
function barrier(){const entered=deferred(),release=deferred();return{enter:entered.resolve,entered:entered.promise,wait:release.promise,release:release.resolve};}
const passed=name=>checks.push(name);
try{
 {
  const {shell}=await make();const arena=shell.snapshot();arena.words[0]=99;arena.bindings.advance='bad';
  const description=shell.describe();description.plan.commit_ranges[0][0]=3;
  assert.equal(shell.snapshot().words[0],0);assert.equal(shell.snapshot().bindings.advance,'wasm');
  const patch={9:2},ticket=shell.start('advance',patch);patch[9]=99;
  await ticket.ready;assert.equal(shell.snapshot().words[0],0);
  const result=await shell.finish(ticket.id);assert.equal(result.status,'committed');
  const state=shell.snapshot();assert.equal(state.words[0],3);assert.equal(state.words[9],0);assert.equal(state.words[3],7);
  assert.deepEqual(Array.from(state.words.slice(4,8)),[1,0,1,1]);
  await assert.rejects(shell.finish(ticket.id));passed('owned-input-output-description-and-staging');
 }
 {
  const {shell}=await make();await Promise.all([shell.dispatch('advance'),shell.dispatch('advance',{9:3}),shell.dispatch('advance')]);
  assert.equal(shell.snapshot().words[0],6);assert.equal(shell.snapshot().revision,3);passed('fifo-inputs-use-preceding-committed-state');
 }
 {
  const {shell}=await make();const t=shell.start('advance');shell.cancel(t.id);await t.ready;
  assert.equal((await shell.finish(t.id)).status,'discarded');assert.equal(shell.snapshot().words[0],0);
  const next=await shell.dispatch('advance');assert.equal(next.status,'committed');passed('cancel-does-not-poison-replacement');
 }
 {
  const {shell}=await make();const t=shell.start('advance');const one=shell.finish(t.id);await assert.rejects(shell.finish(t.id));
  assert.equal((await one).status,'committed');passed('one-use-concurrent-finish');
 }
 {
  const {shell}=await make();const t=shell.start('advance');shell.replace(initial());await t.ready;
  assert.equal((await shell.finish(t.id)).status,'discarded');assert.equal(shell.snapshot().words[0],0);passed('replacement-generation-stales-staged-result');
 }
 {
  const gate=barrier(),{shell}=await make(root,{gate});
  const first=shell.dispatch('advance');await gate.entered;
  const staleQueued=shell.dispatch('advance');const replacement=initial();replacement[0]=100;shell.replace(replacement);gate.release();
  assert.equal((await first).status,'discarded');assert.equal((await staleQueued).status,'discarded');assert.equal(shell.snapshot().words[0],100);
  passed('replacement-invalidates-already-queued-input');
 }
 {
  const gate=barrier(),{shell}=await make(root,{gate});
  const queued=[shell.dispatch('advance')];await gate.entered;
  for(let i=0;i<63;i++)queued.push(shell.dispatch('advance'));
  assert.throws(()=>shell.dispatch('advance'),/queue full/);
  const drain=shell.discardPending();gate.release();await drain;
  assert((await Promise.all(queued)).every(r=>r.status==='discarded'));
  assert.equal(shell.snapshot().words[0],0);
  assert.equal((await shell.dispatch('advance',{9:0})).status,'committed');
  assert.equal(shell.snapshot().words[0],1);
  passed('overloaded-queue-invalidates-and-admits-fresh-control-event');
 }
 {
  const {shell}=await make();const t=shell.start('advance');shell.selectBackend('wasm');shell.selectBackend('wasm');await t.ready;
  assert.equal((await shell.finish(t.id)).status,'discarded');passed('binding-epoch-prevents-aba');
 }
 {
  const {shell}=await make();const patch=initial();patch[3]=8;assert.throws(()=>shell.replace(patch));assert.equal(shell.snapshot().words[3],7);
  assert.throws(()=>shell.start('advance',{3:8}));passed('readonly-host-replacement-and-input-refused');
 }
 {
  const {shell}=await make(badRoot);const before=shell.snapshot();const result=await shell.dispatch('advance');
  assert.equal(result.status,'failed');assert.match(result.reason,/outside declared output/);assert.deepEqual(shell.snapshot(),before);
  passed('actual-wasm-readonly-write-refused-without-commit');
 }
 {
  const {shell,providers}=await make();delete providers.wasm.advance;
  assert.equal((await shell.dispatch('advance')).status,'committed');assert.equal(shell.snapshot().words[0],1);
  passed('caller-registry-mutation-cannot-rebind-provider');
 }
 {
  const {shell,providers,manifest:m}=await make();
  assert.throws(()=>new MemoryShell(m,providers,initial()));
  assert.equal((await shell.dispatch('advance')).status,'committed');
  passed('one-provider-wrapper-has-one-shell-owner');
 }
 {
  const {shell}=await make();const t=shell.start('advance');const finishing=shell.finish(t.id),disposed=shell.dispose();
  assert.equal((await finishing).status,'discarded');assert.deepEqual(await disposed,{settled:true});
  assert.throws(()=>shell.snapshot());await assert.rejects(shell.finish(t.id));passed('dispose-invalidates-and-drains-tickets');
 }
 {
  const {shell}=await make();const t=shell.start('advance');await t.ready;
  const changed=initial();changed[0]=8;shell.replace(changed);const fresh=await shell.dispatch('advance');
  assert.equal(fresh.status,'committed');assert.equal((await shell.finish(t.id)).status,'discarded');assert.equal(shell.snapshot().words[0],9);
  passed('old-finish-cannot-clear-new-committed-operation');
 }
 if(device){
  const {shell}=await make();shell.selectBackend('webgpu',['draw']);
  for(let i=0;i<12;i++){
   shell.selectBackend(i%2?'webgpu':'wasm',['advance']);shell.selectBackend(i%2?'wasm':'webgpu',['draw']);
   const result=await shell.dispatch('advance');assert.equal(result.status,'committed');assert.equal(shell.snapshot().words[0],i+1);
   assert.deepEqual(Array.from(shell.snapshot().words.slice(4,8)),[(i+1)%2,0,1,(i+1)%2]);
  }
  passed('mixed-bindings-and-carried-state');
  const a=await make(),b=await make();a.shell.selectBackend('webgpu');b.shell.selectBackend('webgpu');
  await Promise.all([a.shell.dispatch('advance',{9:10}),b.shell.dispatch('advance',{9:100})]);
  assert.equal(a.shell.snapshot().words[0],11);assert.equal(b.shell.snapshot().words[0],101);passed('shared-device-shells-have-independent-arenas');
 }
 for(const shell of allShells)await shell.dispose();
 if(device){const test=device.createBuffer({size:4,usage:GPUBufferUsage.COPY_SRC});test.destroy();passed('borrowed-device-survives-all-shell-disposals');}
 console.log(JSON.stringify({status:'passed',checks,adapter:adapter?{isFallbackAdapter:adapter.info.isFallbackAdapter,vendor:adapter.info.vendor,architecture:adapter.info.architecture}:null}));
}finally{for(const shell of allShells)await shell.dispose();device?.destroy();gpu=null;}
