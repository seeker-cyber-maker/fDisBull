// Orchestration owns state. Providers own computation and activation resources.
import {instantiateWasm, runWASM, runGPU} from './block.mjs';

const providerStates = new WeakMap();
const deviceQueues = new WeakMap();
const TYPES = {bool:[0,1,1],i8:[-128,127,1],u8:[0,255,1],i16:[-32768,32767,2],u16:[0,65535,2]};
const clone = value => structuredClone(value);
const check = (ok,message) => {if(!ok)throw Error(message);};
const own = (object,key) => Object.hasOwn(object,key);
function stable(value) {
  if(Array.isArray(value))return '['+value.map(stable).join(',')+']';
  if(value!==null && typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+stable(value[k])).join(',')+'}';
  check(typeof value!=='number' || Number.isFinite(value),'Non-finite manifest number');
  const result=JSON.stringify(value);check(result!==undefined,'Non-JSON manifest value');return result;
}
async function hash(bytes) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
}
const digest = value => hash(new TextEncoder().encode(stable(value)));
function increment(value) {check(Number.isSafeInteger(value+1),'Epoch exhausted');return value+1;}
function typed(value,type) {
  return type==='bool' ? typeof value==='boolean' : Number.isInteger(value) && value>=TYPES[type][0] && value<=TYPES[type][1];
}
function provider(build,kind,execute,device=null,ownsDevice=false) {
  const state={build:clone(build),kind,epoch:0,closed:false,lost:false,pending:new Set(),owner:null,disposing:null};
  const handle=Object.freeze({kind,dispose:()=>state.dispose()});
  state.run=rows=>{
    check(!state.closed && !state.lost,'Provider unavailable');
    const owned=clone(rows);
    const previous=device ? deviceQueues.get(device) || Promise.resolve() : Promise.resolve();
    const work=previous.then(()=>{check(!state.closed && !state.lost,'Provider unavailable');return execute(owned);});
    if(device)deviceQueues.set(device,work.then(()=>undefined,()=>undefined));
    state.pending.add(work);
    // Observe both outcomes without producing an unhandled rejected finally.
    work.then(()=>state.pending.delete(work),()=>state.pending.delete(work));
    return work;
  };
  state.dispose=()=>{
    if(state.disposing)return state.disposing;
    state.closed=true;state.epoch=increment(state.epoch);
    if(ownsDevice)device.destroy();
    state.disposing=Promise.allSettled([...state.pending]).then(()=>({settled:true}));
    return state.disposing;
  };
  if(device) {
    const reference=new WeakRef(state);
    device.lost.then(()=>{const current=reference.deref();if(current && !current.closed) {current.lost=true;current.epoch=increment(current.epoch);}});
  }
  providerStates.set(handle,state);
  return handle;
}

export async function createWasmProvider(build,bytes) {
  const pinned=clone(build),instance=await instantiateWasm(bytes,pinned);
  return provider(pinned,'wasm',rows=>runWASM(instance,pinned.abi,rows));
}

export async function createGPUProvider(build,code,{device,ownsDevice=false}={}) {
  check(device && typeof device.destroy==='function' && typeof device.lost?.then==='function' && typeof ownsDevice==='boolean','GPU device/ownership required');
  const pinned=clone(build);
  // Empty batch verifies profile/hash without claiming shader execution.
  await runGPU(device,code,pinned,[]);
  return provider(pinned,'webgpu',rows=>runGPU(device,code,pinned,rows),device,ownsDevice);
}

function validateMemory(manifest) {
  const {plan,layout,interface:ports}=manifest;
  check(plan?.format==='fdisbull-web-orchestration-1' && plan.concurrency==='latest-request-wins','Unsupported orchestration');
  check(plan.state && !Array.isArray(plan.state) && Object.keys(plan.state).length>0 && Object.keys(plan.state).length<=256,'Invalid state arena');
  let offset=0;
  const cells=Object.fromEntries(Object.keys(plan.state).sort().map(name=>{
    const d=plan.state[name];check(/^[A-Za-z_][A-Za-z0-9_]*$/.test(name) && own(TYPES,d.type) && typed(d.initial,d.type),'Invalid state cell');
    check(Object.keys(d).every(k=>['type','initial','label'].includes(k)),'Unknown state descriptor');
    const size=TYPES[d.type][2];offset+=offset%size;
    const cell={offset,size,type:d.type};offset+=size;return [name,cell];
  }));
  const expected={cells,stride:offset+(offset%2)};
  check(stable(expected)===stable(layout),'State arena layout differs');
  for(const side of ['inputs','outputs']) {
    check(stable(Object.keys(plan[side]).sort())===stable(Object.keys(ports[side]).sort()),'Incomplete shell ports');
    for(const [name,cell] of Object.entries(plan[side]))
      check(own(cells,cell) && cells[cell].type===ports[side][name],'Shell port type differs');
  }
  check(new Set(Object.values(plan.outputs)).size===Object.keys(plan.outputs).length,'Aliased output commits');
  for(const [name,type] of Object.entries(ports.inputs)) {
    const domain=ports.domain[name];check(own(TYPES,type) && domain && Number.isInteger(domain.min) && Number.isInteger(domain.max) && domain.min>=TYPES[type][0] && domain.max<=TYPES[type][1] && domain.min<=domain.max,'Invalid admission domain');
  }
}

class BrowserShell {
  #m;#providers;#records=new Map();#operations=new Map();#generation=0;
  #view=0;#binding=0;#latest=0;#selected=null;#backend='wasm';#closed=false;#disposing=null;#active=null;
  #session=crypto.randomUUID();
  constructor(manifest,providers) {this.#m=manifest;this.#providers=providers;}
  #open() {check(!this.#closed,'Shell disposed');}
  #record(id=this.#selected) {check(this.#records.has(id),'Unknown selected record');return this.#records.get(id);}
  #read(record,name) {
    const c=this.#m.layout.cells[name],v=new DataView(record.memory);
    if(c.type==='bool')return v.getUint8(c.offset)===1;
    if(c.type==='i8')return v.getInt8(c.offset);
    if(c.type==='u8')return v.getUint8(c.offset);
    return c.type==='i16'?v.getInt16(c.offset,true):v.getUint16(c.offset,true);
  }
  #write(memory,name,value) {
    const c=this.#m.layout.cells[name],v=new DataView(memory);
    if(c.type==='bool' || c.type==='u8')v.setUint8(c.offset,Number(value));
    else if(c.type==='i8')v.setInt8(c.offset,value);
    else if(c.type==='i16')v.setInt16(c.offset,value,true);
    else v.setUint16(c.offset,value,true);
  }
  #changes(changes) {
    check(changes && typeof changes==='object' && !Array.isArray(changes),'Expected typed state changes');
    const copy=clone(changes);
    for(const [name,value] of Object.entries(copy))
      check(own(this.#m.layout.cells,name) && typed(value,this.#m.layout.cells[name].type),'Invalid typed state change');
    return copy;
  }
  addRecord(id,values={}) {
    this.#open();check(typeof id==='string' && id.length>0 && id.length<=96 && !this.#records.has(id),'Invalid/new record identity');
    check(this.#records.size<4096,'Record limit');const changes=this.#changes(values);
    const memory=new ArrayBuffer(this.#m.layout.stride);new Uint8Array(memory).fill(0xa5);
    for(const [name,d] of Object.entries(this.#m.plan.state))this.#write(memory,name,own(changes,name)?changes[name]:d.initial);
    this.#generation=increment(this.#generation);
    this.#records.set(id,{id,generation:this.#generation,revision:0,memory});
    return this.snapshot(id);
  }
  editRecord(id,changes) {
    this.#open();const record=this.#record(id),copy=this.#changes(changes);
    // Validate the entire edit before touching the arena.
    const revision=increment(record.revision);
    for(const [name,value] of Object.entries(copy))this.#write(record.memory,name,value);
    record.revision=revision;return this.snapshot(id);
  }
  removeRecord(id) {
    this.#open();this.#record(id);this.#records.delete(id);
    if(id===this.#selected) {this.#selected=null;this.#view=increment(this.#view);}
  }
  selectEntity(id) {this.#open();this.#record(id);this.#selected=id;this.#view=increment(this.#view);}
  selectBackend(name) {
    this.#open();const state=this.#providers[name];check(state && !state.closed && !state.lost,'Backend unavailable');
    this.#backend=name;this.#binding=increment(this.#binding);
  }
  capabilities() {
    return {selected:this.#backend,backends:Object.fromEntries(['wasm','webgpu'].map(name=>{
      const p=this.#providers[name];return [name,{available:!this.#closed && !!p && !p.closed && !p.lost}];
    }))};
  }
  describe() {
    this.#open();return clone({module_uil_sha256:this.#m.module_uil_sha256,
      plan:this.#m.plan,layout:this.#m.layout,interface:this.#m.interface});
  }
  snapshot(id=this.#selected) {
    this.#open();const record=this.#record(id);
    return {id:record.id,generation:record.generation,revision:record.revision,
      values:Object.fromEntries(Object.keys(this.#m.plan.state).map(name=>[name,this.#read(record,name)])),
      bytes:new Uint8Array(record.memory.slice(0))};
  }
  start() {
    this.#open();check(this.#operations.size<64,'Outstanding operation limit');
    const record=this.#record(),backend=this.#backend,driver=this.#providers[backend];
    check(driver && !driver.closed && !driver.lost,'Backend unavailable');
    this.#latest=increment(this.#latest);
    const id=this.#session+':'+this.#latest;
    const token={session:this.#session,entity:record.id,generation:record.generation,revision:record.revision,
      view:this.#view,binding:this.#binding,operation:this.#latest,providerEpoch:driver.epoch};
    const rows=[driver.build.abi.inputs.map(port=>Number(this.#read(record,this.#m.plan.inputs[port])))];
    const op={id,token,backend,driver,canceled:false,finishing:false,outcome:null,ready:null};
    this.#active=id;this.#operations.set(id,op);
    op.ready=Promise.resolve().then(()=>driver.run(rows)).then(frames=>{op.outcome={frames};},error=>{
      op.outcome={error:String(error?.message||error)};
    });
    const ready=op.ready.then(()=>({status:op.outcome.error?'failed':op.outcome.frames?.[0]?.status===1?'refused':'complete'}));
    return Object.freeze({id,ready});
  }
  cancel(id=this.#active) {
    this.#open();const op=this.#operations.get(id);check(op,'Unknown operation');op.canceled=true;
    if(this.#active===id)this.#active=null;
    return {status:'canceled',physical_cancellation:false};
  }
  #stale(op) {
    const t=op.token,r=this.#records.get(t.entity);
    if(this.#closed || t.session!==this.#session)return 'disposed';
    if(op.canceled)return 'canceled';
    if(t.operation!==this.#latest)return 'superseded';
    if(t.view!==this.#view || t.entity!==this.#selected)return 'view-changed';
    if(t.binding!==this.#binding || op.backend!==this.#backend)return 'binding-changed';
    if(!r || r.generation!==t.generation)return 'entity-replaced';
    if(r.revision!==t.revision)return 'state-changed';
    if(op.driver.closed || op.driver.lost || op.driver.epoch!==t.providerEpoch)return 'provider-unavailable';
    return null;
  }
  async finish(id) {
    const op=this.#operations.get(id);check(op && !op.finishing,'Unknown or consumed operation');op.finishing=true;
    try {
      await op.ready;
      const result={operation:id,backend:op.backend,entity:op.token.entity,committed:false,outputs:{},
        module_uil_sha256:this.#m.module_uil_sha256};
      const stale=this.#stale(op);
      if(stale)return {...result,status:'discarded',reason:stale,computation:op.outcome.error?'failed':'settled'};
      if(op.outcome.error)return {...result,status:'failed',reason:op.outcome.error};
      const frames=op.outcome.frames;
      if(!Array.isArray(frames) || frames.length!==1 || !frames[0] || !Array.isArray(frames[0].data))
        return {...result,status:'failed',reason:'Invalid result frame'};
      const frame=frames[0],names=op.driver.build.abi.outputs;
      if(frame.status===1 && frame.data.length===0)return {...result,status:'refused'};
      if(frame.status!==0 || frame.data.length!==names.length)
        return {...result,status:'failed',reason:'Invalid result status/arity'};
      const outputs=Object.create(null);
      for(let i=0;i<names.length;i++) {
        const port=names[i],type=this.#m.interface.outputs[port],value=frame.data[i];
        if(!Number.isInteger(value) || value<TYPES[type][0] || value>TYPES[type][1])
          return {...result,status:'failed',reason:'Invalid logical output type'};
        outputs[port]=type==='bool'?Boolean(value):value;
      }
      // No await or callback between final freshness validation and atomic commit.
      const record=this.#record(op.token.entity),revision=increment(record.revision);
      const work=record.memory.slice(0);
      for(const [port,value] of Object.entries(outputs))this.#write(work,this.#m.plan.outputs[port],value);
      record.memory=work;record.revision=revision;
      return {...result,status:'committed',committed:true,outputs,revision};
    } finally {
      this.#operations.delete(id);
      if(this.#active===id)this.#active=null;
    }
  }
  async step() {const operation=this.start();return this.finish(operation.id);}
  dispose() {
    if(this.#disposing)return this.#disposing;
    this.#closed=true;this.#records.clear();this.#view=increment(this.#view);
    for(const op of this.#operations.values())op.canceled=true;
    this.#disposing=Promise.allSettled(Object.values(this.#providers).map(p=>p.dispose())).then(()=>{
      this.#operations.clear();this.#active=null;return {status:'disposed',settled:true};
    });
    return this.#disposing;
  }
}

export async function createShell(document,providers) {
  const manifest=clone(document);
  check(manifest.format==='fdisbull-browser-shell-1','Unsupported browser shell');
  check(await digest(manifest.program)===manifest.module_uil_sha256,'Module UIL hash differs');
  check(await digest(manifest.plan)===manifest.plan_sha256,'Orchestration hash differs');
  check(await digest(manifest.contract)===manifest.contract_sha256,'Contract hash differs');
  for(const side of ['inputs','outputs'])
    check(stable(manifest.contract[side])===stable(manifest.interface[side]),'Shell interface differs from contract');
  for(const variant of Object.values(manifest.variants)) {
    const domain=Object.fromEntries(Object.entries(manifest.interface.inputs).map(([name,type])=>{
      check(own(TYPES,type),'Unsupported logical type');
      let [min,max]=TYPES[type];
      for(const bounds of [manifest.contract.domain||{},variant.layer_domain||{}])
        if(own(bounds,name)) {min=Math.max(min,bounds[name].min);max=Math.min(max,bounds[name].max);}
      return [name,{min,max}];
    }));
    check(stable(domain)===stable(variant.effective_domain) && stable(domain)===stable(manifest.interface.domain),'Provider admission differs');
  }
  check(manifest.program.body.length===1 && manifest.program.body[0].op==='invoke' && Object.keys(manifest.program.resources).length===0,'One pure invocation required');
  validateMemory(manifest);
  const states=Object.create(null);
  check(providers.wasm && Object.keys(providers).every(k=>['wasm','webgpu'].includes(k)),'Wasm provider required');
  for(const [name,handle] of Object.entries(providers)) {
    const state=providerStates.get(handle),expected=manifest.variants[name];
    check(state && state.kind===name && !state.owner && !state.closed && !state.lost,'Invalid or owned provider');
    check(expected && stable(state.build)===stable(expected.build),'Provider selection differs');
    check(state.build.module_uil_sha256===manifest.module_uil_sha256 && state.build.contract_sha256===manifest.contract_sha256,'Provider semantic identity differs');
    for(const side of ['inputs','outputs'])
      check(stable(state.build.abi[side])===stable(Object.keys(manifest.interface[side]).sort()),'Provider ABI differs');
    states[name]=state;
  }
  const shell=new BrowserShell(manifest,states);
  for(const state of Object.values(states))state.owner=true;
  return shell;
}

export async function loadShell(baseURL,{device=null,ownsDevice=false,gpu=true}={}) {
  check(typeof ownsDevice==='boolean' && typeof gpu==='boolean','Invalid device ownership options');
  check(gpu || !device || !ownsDevice,'Cannot transfer device ownership with GPU disabled');
  const base=new URL(baseURL),read=async name=>{
    check(typeof name==='string' && name.split('/').every(p=>p && p!=='.' && p!=='..') && !/[\\?#:]/.test(name),'Invalid shell resource path');
    const url=new URL(name,base);check(url.origin===base.origin && url.pathname.startsWith(base.pathname),'Resource outside shell');
    const response=await fetch(url);check(response.ok,'Shell resource unavailable');return new Uint8Array(await response.arrayBuffer());
  };
  const providers={};let responsible=!!device && ownsDevice;
  try {
    const manifest=JSON.parse(new TextDecoder().decode(await read('shell.json')));
    const resource=async name=>{
      const bytes=await read(name);check(await hash(bytes)===manifest.artifacts[name],'Shell artifact hash differs');return bytes;
    };
    const json=async name=>JSON.parse(new TextDecoder().decode(await resource(name)));
    const w=manifest.variants.wasm.directory;
    providers.wasm=await createWasmProvider(await json(w+'/build.json'),await resource(w+'/block.wasm'));
    if(gpu && !device && globalThis.navigator?.gpu) {
      const adapter=await navigator.gpu.requestAdapter();
      if(adapter) {device=await adapter.requestDevice();ownsDevice=true;responsible=true;}
    }
    if(gpu && device) {
      const g=manifest.variants.webgpu.directory;
      providers.webgpu=await createGPUProvider(await json(g+'/build.json'),new TextDecoder().decode(await resource(g+'/block.wgsl')),{device,ownsDevice});
      responsible=false; // Ownership, when requested, is now held by this provider.
    }
    return await createShell(manifest,providers);
  } catch(error) {
    await Promise.allSettled(Object.values(providers).map(p=>providerStates.get(p).dispose()));
    if(responsible)device.destroy();
    throw error;
  }
}
