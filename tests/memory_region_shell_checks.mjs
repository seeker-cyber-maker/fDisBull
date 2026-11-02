// Counting and delay wrappers delegate every calculation to an actual block.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';

const root=path.resolve(process.argv[2]);
const expected=JSON.parse(await fs.readFile(path.resolve(process.argv[3])));
const useGPU=process.argv.includes('--gpu'),checks=[],shells=[],rawProviders=[];
const initial=()=>[10,0,0,7,...Array(12).fill(0)];
const {MemoryShell}=await import(pathToFileURL(path.join(root,'memory-shell.mjs')));
const {createWasmMemoryProvider,createGPUMemoryProvider}=await import(pathToFileURL(path.join(root,'memory.mjs')));
let gpu=null,device=null,adapter=null;
if(useGPU){
 const require=createRequire(path.join(process.env.FDISBULL_WEBGPU_MODULE_ROOT,'package.json'));
 const {create,globals}=await import(pathToFileURL(require.resolve('webgpu')));Object.assign(globalThis,globals);
 gpu=create(['backend='+(process.env.FDISBULL_GPU_BACKEND||'metal')]);adapter=await gpu.requestAdapter();
 assert.equal(adapter.info.isFallbackAdapter,false);device=await adapter.requestDevice();
}
function barrier(){let enter,release;return{entered:new Promise(r=>enter=r),wait:new Promise(r=>release=r),enter:()=>enter(),release:()=>release()};}
const passed=name=>checks.push(name);
async function make({gate=null,gateKey='wasm.update.original',instantiate=true}={}){
 const manifest=JSON.parse(await fs.readFile(path.join(root,'memory-shell.json')));
 const providers={},phases={},regions={},counts=Object.create(null),wrappers=[];
 async function load(kind,entry,key){
  const real=kind==='wasm'?
   await createWasmMemoryProvider(entry.build,await fs.readFile(path.join(root,entry.directory,'block.wasm'))):
   await createGPUMemoryProvider(entry.build,await fs.readFile(path.join(root,entry.directory,'block.wgsl'),'utf8'),{device});
  rawProviders.push(real);counts[key]=0;
  const wrapper=Object.freeze({describe:()=>real.describe(),get epoch(){return real.epoch;},get closed(){return real.closed;},get lost(){return real.lost;},dispose:()=>real.dispose(),
   async invoke(words){counts[key]++;const result=await real.invoke(words);if(gate&&key===gateKey){gate.enter();await gate.wait;}return result;}});
  wrappers.push(wrapper);return wrapper;
 }
 for(const kind of device?['wasm','webgpu']:['wasm']){
  providers[kind]={};phases[kind]={};regions[kind]={};
  for(const [fn,entry]of Object.entries(manifest.variants[kind]))providers[kind][fn]=await load(kind,entry,kind+'.'+fn);
  for(const [fn,entries]of Object.entries(manifest.cut_variants[kind])){
   phases[kind][fn]={};for(const [name,entry]of Object.entries(entries))phases[kind][fn][name]=await load(kind,entry,kind+'.'+fn+'.'+name);
  }
  for(const [fn,entries]of Object.entries(manifest.region_variants[kind])){
   regions[kind][fn]={};for(const [name,entry]of Object.entries(entries))regions[kind][fn][name]=await load(kind,entry,kind+'.'+fn+'.'+name);
  }
 }
 const shell=instantiate?new MemoryShell(manifest,providers,initial(),phases,regions):null;
 if(shell)shells.push(shell);return{shell,providers,phases,regions,counts,manifest,wrappers};
}
function construct(a){return new MemoryShell(a.manifest,a.providers,initial(),a.phases,a.regions);}
try{
 {
  const {shell,counts,manifest}=await make(),source=shell.describe().program;
  assert.deepEqual(shell.snapshot().implementations,{update:'original'});
  const result=await shell.dispatch('advance',{10:1});assert.equal(result.status,'committed');
  assert.deepEqual(Array.from(shell.snapshot().words),expected);
  assert.equal(counts['wasm.advance'],0);assert.equal(counts['wasm.update.original'],1);
  const call=result.execution.find(x=>x.function==='update');
  assert.equal(call.implementation,'original');
  assert.equal(call.implementation_uil_sha256,manifest.region_variants.wasm.update.original.build.module_uil_sha256);
  assert.equal(call.steps,1);assert.notEqual(call.implementation_uil_sha256,manifest.module_uil_sha256);
  assert.deepEqual(shell.describe().program,source);
  passed('original-region-matches-source-with-honest-implementation-identity');
 }
 {
  const {shell,counts}=await make();
  const choices=['original','alternate','original'],values=[11,58,59];
  for(let i=0;i<choices.length;i++){
   shell.selectRegionImplementation('update',choices[i]);
   const result=await shell.dispatch('advance',{10:1});assert.equal(result.status,'committed');
   assert.equal(shell.snapshot().words[0],values[i]);assert.equal(shell.snapshot().words[2],2*(i+1));
   assert.equal(result.execution.find(x=>x.function==='update').implementation,choices[i]);
  }
  assert.equal(counts['wasm.update.original'],2);assert.equal(counts['wasm.update.alternate'],1);
  passed('original-alternate-original-switch-carries-current-state-without-reseed');
 }
 {
  const {shell,counts}=await make();shell.selectRegionImplementation('update','alternate');
  const before=shell.snapshot().words;const result=await shell.dispatch('update',{}, {render:false});
  assert.equal(result.status,'committed');const after=shell.snapshot().words;
  assert.equal(after[0],53);assert.deepEqual(Array.from(after.subarray(1)),Array.from(before.subarray(1)));
  assert.equal(counts['wasm.update.alternate'],1);passed('direct-selected-region-changes-only-its-declared-word');
 }
 {
  const {shell,counts}=await make();shell.selectRegionImplementation('update','alternate');
  const result=await shell.dispatch('advance',{10:0});assert.equal(result.status,'committed');
  assert.equal(counts['wasm.update.original'],0);assert.equal(counts['wasm.update.alternate'],0);
  assert.equal(shell.snapshot().words[0],10);passed('untaken-region-consumes-no-generator-value');
 }
 {
  const {shell}=await make(),before=shell.snapshot();
  assert.throws(()=>shell.selectRegionImplementation('missing','original'));
  assert.throws(()=>shell.selectRegionImplementation('update','missing'));
  assert.deepEqual(shell.snapshot(),before);passed('unknown-region-and-variant-refuse-without-state-change');
 }
 {
  const {shell,counts}=await make();shell.selectRegionImplementation('update','outside');const before=shell.snapshot();
  const result=await shell.dispatch('advance',{10:1});assert.equal(result.status,'failed');
  assert.match(result.reason,/region|domain|range/i);assert.deepEqual(shell.snapshot(),before);
  assert.equal(counts['wasm.update.outside'],1);assert.equal(counts['wasm.draw'],0);
  passed('variant-output-domain-is-enforced-before-continuation-or-commit');
 }
 {
  const gate=barrier(),{shell,counts}=await make({gate,gateKey:'wasm.advance.entry'});
  const ticket=shell.start('advance',{10:1});await gate.entered;
  shell.selectRegionImplementation('update','alternate');gate.release();
  const result=await shell.finish(ticket.id);assert.equal(result.status,'discarded');
  assert.equal(counts['wasm.update.original'],1);assert.equal(counts['wasm.update.alternate'],0);
  assert.equal(result.execution.find(x=>x.function==='update').implementation,'original');
  assert.deepEqual(Array.from(shell.snapshot().words),initial());
  passed('algorithm-choice-is-captured-before-prefix-await-and-stales-whole-operation');
 }
 {
  const gate=barrier(),{shell}=await make({gate});const ticket=shell.start('advance',{10:1});await gate.entered;
  shell.selectRegionImplementation('update','alternate');shell.selectRegionImplementation('update','original');gate.release();
  assert.equal((await shell.finish(ticket.id)).status,'discarded');
  assert.deepEqual(Array.from(shell.snapshot().words),initial());passed('algorithm-aba-invalidates-pending-region-result');
 }
 {
  const gate=barrier(),{shell,wrappers}=await make({gate});const ticket=shell.start('advance',{10:1});await gate.entered;
  const finishing=shell.finish(ticket.id);let settled=false;
  const dispose=shell.dispose().then(x=>(settled=true,x));await Promise.resolve();assert.equal(settled,false);gate.release();
  assert.equal((await finishing).status,'discarded');await dispose;assert(wrappers.every(x=>x.closed));
  passed('dispose-drains-region-and-all-variant-provider-owners');
 }
 {
  const a=await make(),b=await make({instantiate:false});b.regions.wasm.update.original=a.regions.wasm.update.original;
  assert.throws(()=>construct(b),/already belongs/);passed('region-wrapper-has-one-shell-owner');
 }
 {
  const a=await make({instantiate:false});delete a.regions.wasm.update.original;
  assert.throws(()=>construct(a),/unavailable/i);passed('missing-default-region-provider-refuses-admission');
 }
 {
  const a=await make({instantiate:false});
  a.regions.wasm.update.original=a.regions.wasm.update.alternate;
  assert.throws(()=>construct(a),/identity|differs/i);passed('variant-wrapper-cannot-impersonate-another-artifact');
 }
 {
  const a=await make({instantiate:false});a.manifest.regions.slots.update.default='alternate';
  assert.throws(()=>construct(a));passed('derived-default-cannot-depart-from-exact-source-policy');
 }
 {
  const {shell,regions}=await make();delete regions.wasm.update.original;
  assert.equal((await shell.dispatch('advance',{10:1})).status,'committed');
  const copy=shell.snapshot();copy.implementations.update='outside';
  assert.equal(shell.snapshot().implementations.update,'original');
  passed('region-provider-registry-and-choice-snapshots-are-owned');
 }
 {
  const {shell,regions}=await make();const ticket=shell.start('advance',{10:1});await ticket.ready;
  await regions.wasm.update.original.dispose();assert.equal(shell.capabilities().backends.wasm,false);
  assert.equal((await shell.finish(ticket.id)).status,'discarded');
  assert.deepEqual(Array.from(shell.snapshot().words),initial());passed('completed-region-lease-must-survive-until-public-commit');
 }
 if(device){
  for(const [owner,region]of [['wasm','webgpu'],['webgpu','wasm'],['webgpu','webgpu']]){
   const {shell,counts}=await make();shell.selectBackend(owner,['advance','draw']);shell.selectBackend(region,['update']);
   for(const [choice,expectedValue]of [['original',11],['alternate',58],['original',59]]){
    shell.selectRegionImplementation('update',choice);const result=await shell.dispatch('advance',{10:1});
    assert.equal(result.status,'committed');assert.equal(shell.snapshot().words[0],expectedValue);
    assert(result.execution.some(x=>x.function==='update'&&x.backend===region&&x.implementation===choice));
   }
   assert.equal(counts[region+'.update.original'],2);assert.equal(counts[region+'.update.alternate'],1);
  }
  passed('independent-algorithm-and-real-gpu-wasm-region-choices-carry-state');
  {
   const gate=barrier(),{shell,counts}=await make({gate,gateKey:'wasm.advance.entry'});
   const ticket=shell.start('advance',{10:1});await gate.entered;shell.selectBackend('webgpu',['update']);gate.release();
   const result=await shell.finish(ticket.id);assert.equal(result.status,'discarded');
   assert.equal(counts['wasm.update.original'],1);assert.equal(counts['webgpu.update.original'],0);
   passed('region-backend-choice-is-captured-across-prefix-await');
  }
 }
 for(const shell of shells)await shell.dispose();
 if(device){const buffer=device.createBuffer({size:4,usage:GPUBufferUsage.COPY_SRC});buffer.destroy();passed('all-region-variants-borrow-the-shared-device');}
 console.log(JSON.stringify({status:'passed',checks,adapter:adapter?{isFallbackAdapter:adapter.info.isFallbackAdapter,vendor:adapter.info.vendor,architecture:adapter.info.architecture}:null}));
}finally{for(const shell of shells)await shell.dispose();await Promise.allSettled(rawProviders.map(x=>x.dispose()));device?.destroy();gpu=null;}
