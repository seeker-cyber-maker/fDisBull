// Owned state and ordered events around pure bounded-memory blocks.
// Geometry, input bindings and drawing rules belong to the supplied UIL/plan.
import {createWasmMemoryProvider,createGPUMemoryProvider} from './memory.mjs';
const check=(ok,message)=>{if(!ok)throw Error(message);};
const clone=x=>structuredClone(x);
const u32=x=>Number.isInteger(x)&&x>=0&&x<=0xffffffff;
const inc=x=>{check(Number.isSafeInteger(x+1),'Epoch exhausted');return x+1;};

export class MemoryShell {
  #manifest;#providers;#words;#bindings;#revision=0;#epoch=0;#generation=0;
  #session=crypto.randomUUID();#closed=false;#disposing=null;#tail=Promise.resolve();#pending=0;#tickets=new Map();#sequence=0;
  constructor(manifest,providers,initial) {
    this.#manifest=clone(manifest);this.#providers=Object.fromEntries(Object.entries(providers).map(([kind,functions])=>[kind,{...functions}]));
    const {plan,program}=this.#manifest;
    check(plan?.format==='fdisbull-memory-orchestration-1'&&program?.format==='fdisbull-memory-uil-1','Unsupported memory shell');
    check(plan.concurrency==='ordered-events'&&Number.isInteger(program.memory.words),'Unsupported event policy');
    this.#words=this.#arena(initial);this.#bindings=clone(plan.bindings);
    for(const [fn,backend] of Object.entries(this.#bindings))this.#provider(fn,backend);
    this.#validate(this.#words);
  }
  #open(){check(!this.#closed,'Shell disposed');}
  #arena(values){
    check((Array.isArray(values)||ArrayBuffer.isView(values))&&values.length===this.#manifest.program.memory.words,'Invalid arena length');
    check(Array.from(values).every(u32),'Invalid arena word');return Uint32Array.from(values);
  }
  #provider(fn,backend=this.#bindings[fn]) {
    const p=this.#providers[backend]?.[fn];check(p&&!p.closed&&!p.lost,'Provider unavailable');
    const b=p.describe();check(b.target===({wasm:'wasm32-memory-1',webgpu:'webgpu-wgsl-memory-1'})[backend]&&b.function===fn&&b.module_uil_sha256===this.#manifest.module_uil_sha256&&b.abi.memory_words===this.#words.length,'Provider identity differs');
    return p;
  }
  #validate(words){
    for(const g of this.#manifest.plan.guards||[])check(words[g.index]>=g.min&&words[g.index]<=g.max,'State guard refused');
    const f=this.#manifest.plan.frame;
    for(let n=f.offset;n<f.offset+f.width*f.height;n++)check(words[n]<=255&&Object.hasOwn(f.palette,String(words[n])),'Invalid indexed pixel');
  }
  describe(){this.#open();return clone(this.#manifest);}
  snapshot(){this.#open();return {session:this.#session,generation:this.#generation,revision:this.#revision,words:this.#words.slice(),bindings:clone(this.#bindings)};}
  capabilities(){return {closed:this.#closed,bindings:clone(this.#bindings),backends:Object.fromEntries(Object.entries(this.#providers).map(([kind,functions])=>[kind,Object.values(functions).every(p=>!p.closed&&!p.lost)]))};}
  selectBackend(backend,functions=Object.keys(this.#bindings)){
    this.#open();check(Array.isArray(functions)&&functions.length>0,'Select named functions');
    for(const fn of functions){check(Object.hasOwn(this.#bindings,fn),'Unknown binding');this.#provider(fn,backend);}
    for(const fn of functions)this.#bindings[fn]=backend;
    this.#epoch=inc(this.#epoch);return this.capabilities();
  }
  replace(values){
    this.#open();const copy=this.#arena(values);this.#validate(copy);
    const mutable=new Set(this.#manifest.plan.replace_ranges.flatMap(([start,count])=>Array.from({length:count},(_,i)=>start+i)));
    for(let n=0;n<copy.length;n++)if(!mutable.has(n))check(copy[n]===this.#words[n],'Replacement touched immutable input');
    this.#words=copy;this.#generation=inc(this.#generation);this.#revision=inc(this.#revision);return this.snapshot();
  }
  start(fn,patch={},options={render:true}){
    this.#open();check(this.#tickets.size<64&&Object.hasOwn(this.#bindings,fn),'Unknown function or operation limit');
    check(options&&typeof options.render==='boolean'&&Object.keys(options).every(k=>k==='render'),'Invalid transaction options');
    const snapshot=this.#words.slice(),input=clone(patch);
    for(const [key,value] of Object.entries(input))check(this.#manifest.plan.inputs.includes(Number(key))&&String(Number(key))===key&&u32(value),'Invalid input patch');
    for(const [key,value] of Object.entries(input))snapshot[Number(key)]=value;
    const operation=++this.#sequence,id=this.#session+':'+operation;
    const token={epoch:this.#epoch,generation:this.#generation,revision:this.#revision,session:this.#session};
    const bindings=clone(this.#bindings),leases=[];
    const call=async(name,words)=>{
      const provider=this.#provider(name,bindings[name]);leases.push([provider,provider.epoch]);
      const result=await provider.invoke(words);
      check(result.status==='complete','Memory block refused');const output=this.#arena(result.words);
      const ranges=this.#manifest.plan.outputs[name];
      for(let n=0;n<words.length;n++)if(!ranges.some(([start,count])=>n>=start&&n<start+count))check(output[n]===words[n],'Kernel wrote outside declared output');
      this.#validate(output);return output;
    };
    const ticket={id,token,canceled:false,finishing:false,result:null,ready:null};this.#tickets.set(id,ticket);
    ticket.ready=Promise.resolve().then(async()=>{
      let words=await call(fn,snapshot);
      if(options.render&&fn!==this.#manifest.plan.render.function&&words[this.#manifest.plan.render.when_nonzero]!==0)
        words=await call(this.#manifest.plan.render.function,words);
      ticket.result={words,leases};
    }).catch(error=>{ticket.result={error:String(error?.message||error),leases};});
    return Object.freeze({id,ready:ticket.ready.then(()=>({status:ticket.result.error?'failed':'complete'}))});
  }
  cancel(id){this.#open();const ticket=this.#tickets.get(id);check(ticket,'Unknown operation');ticket.canceled=true;return {status:'canceled',physical_cancellation:false};}
  async finish(id){
    const t=this.#tickets.get(id);check(t&&!t.finishing,'Unknown or consumed operation');t.finishing=true;
    try {
      await t.ready;const result={operation:id,committed:false};
      if(this.#closed||t.canceled||t.token.session!==this.#session||t.token.epoch!==this.#epoch||t.token.generation!==this.#generation||t.token.revision!==this.#revision||t.result.leases.some(([p,e])=>p.closed||p.lost||p.epoch!==e))
        return {...result,status:'discarded',reason:'stale-or-canceled'};
      if(t.result.error)return {...result,status:'failed',reason:t.result.error};
      const next=this.#words.slice();
      for(const [start,count] of this.#manifest.plan.commit_ranges)next.set(t.result.words.subarray(start,start+count),start);
      this.#validate(next);
      // No await, host callback or externally aliased memory at final commit.
      const revision=inc(this.#revision);this.#words=next;this.#revision=revision;
      return {...result,status:'committed',committed:true,revision};
    } finally {this.#tickets.delete(id);}
  }
  dispatch(fn,patch={},options={render:true}){
    this.#open();check(this.#pending<64,'Input queue full');
    // Snapshot host input now; game state is captured at its FIFO turn.
    const owned=clone(patch),policy=clone(options),epoch=this.#epoch,generation=this.#generation;this.#pending++;
    const job=this.#tail.then(async()=>{
      if(this.#closed||epoch!==this.#epoch||generation!==this.#generation)return {status:'discarded',committed:false,reason:'context-changed-before-dispatch'};
      const ticket=this.start(fn,owned,policy);return this.finish(ticket.id);
    });
    this.#tail=job.catch(()=>{}).then(()=>{this.#pending--;});return job;
  }
  dispose(){
    if(this.#disposing)return this.#disposing;
    this.#closed=true;this.#epoch=inc(this.#epoch);this.#words.fill(0);
    const providers=[...new Set(Object.values(this.#providers).flatMap(x=>Object.values(x)))];
    this.#disposing=Promise.allSettled([...this.#tickets.values()].map(t=>t.ready).concat(providers.map(p=>p.dispose()),[this.#tail])).then(()=>{this.#tickets.clear();return {settled:true};});
    return this.#disposing;
  }
}

function canonical(value){
  if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
  if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
  const result=JSON.stringify(value);check(result!==undefined,'Non-JSON identity');return result;
}
async function sha(bytes){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');}

export async function loadMemoryShell(url='memory-shell.json'){
  const base=new URL(url,location.href);check(base.origin===location.origin,'Same-origin shell required');
  const response=await fetch(base);check(response.ok,'Shell manifest unavailable');const manifest=await response.json();
  check(manifest.format==='fdisbull-memory-browser-1','Unsupported shell manifest');
  const encode=x=>new TextEncoder().encode(canonical(x));
  check(await sha(encode(manifest.program))===manifest.module_uil_sha256,'UIL identity differs');
  check(await sha(encode(manifest.plan))===manifest.plan_sha256,'Orchestration identity differs');
  const assets=new Map();
  await Promise.all(Object.entries(manifest.artifacts).map(async([name,expected])=>{
    check(name.split('/').every(x=>x&&x!=='.'&&x!=='..')&&!/[\\?#:]/.test(name),'Unsafe artifact path');
    const path=new URL(name,base);check(path.origin===base.origin,'Cross-origin artifact');
    const r=await fetch(path);check(r.ok,'Shell asset unavailable: '+name);const bytes=await r.arrayBuffer();
    check(await sha(bytes)===expected,'Shell asset hash differs: '+name);assets.set(name,bytes);
  }));
  const providers={wasm:{},webgpu:{}};let device=null,shell=null;
  try {
    for(const [fn,v] of Object.entries(manifest.variants.wasm))
      providers.wasm[fn]=await createWasmMemoryProvider(v.build,assets.get(v.directory+'/block.wasm'));
    if(navigator.gpu){
      const adapter=await navigator.gpu.requestAdapter();
      if(adapter){device=await adapter.requestDevice();
        for(const [fn,v] of Object.entries(manifest.variants.webgpu))
          providers.webgpu[fn]=await createGPUMemoryProvider(v.build,new TextDecoder().decode(assets.get(v.directory+'/block.wgsl')),{device,ownsDevice:false});
      }
    }
    if(!Object.keys(providers.webgpu).length)delete providers.webgpu;
    const initial=JSON.parse(new TextDecoder().decode(assets.get('initial.json')));
    shell=new MemoryShell(manifest,providers,initial);
    const owner=shell,ownedDevice=device;let disposed=null;
    // Device creation is a loader responsibility. Every function wrapper borrows
    // it; only this owner destroys it, after all physical jobs have drained.
    return Object.freeze({
      describe:()=>owner.describe(),snapshot:()=>owner.snapshot(),capabilities:()=>owner.capabilities(),
      selectBackend:(...a)=>owner.selectBackend(...a),replace:(...a)=>owner.replace(...a),
      start:(...a)=>owner.start(...a),finish:(...a)=>owner.finish(...a),cancel:(...a)=>owner.cancel(...a),dispatch:(...a)=>owner.dispatch(...a),
      dispose(){return disposed??=(async()=>{await owner.dispose();ownedDevice?.destroy();return {settled:true};})();}
    });
  } catch(error){
    if(shell)await shell.dispose();else await Promise.allSettled(Object.values(providers).flatMap(x=>Object.values(x)).map(p=>p.dispose()));
    device?.destroy();throw error;
  }
}
