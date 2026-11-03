// Owned state and ordered events around pure bounded-memory blocks.
// Geometry, input bindings and drawing rules belong to the supplied UIL/plan.
import {createWasmMemoryProvider,createGPUMemoryProvider} from './memory.mjs';
const check=(ok,message)=>{if(!ok)throw Error(message);};
const clone=x=>structuredClone(x);
const u32=x=>Number.isInteger(x)&&x>=0&&x<=0xffffffff;
const inc=x=>{check(Number.isSafeInteger(x+1),'Epoch exhausted');return x+1;};
const providerOwners=new WeakMap();
const own=(object,key)=>object&&Object.hasOwn(object,key);
const plain=value=>Array.isArray(value)?value.map(plain):value&&typeof value==='object'?Object.fromEntries(Object.entries(value).filter(([key])=>key!=='id'&&key!=='evidence').map(([key,item])=>[key,plain(item)])):value;

function checkRegionLinks(manifest){
  const resolved=manifest.regions,document=resolved.document,execution=manifest.execution_program;
  check(resolved.format==='fdisbull-memory-region-resolution-1'&&resolved.module_uil_sha256===manifest.module_uil_sha256&&document?.format==='fdisbull-memory-regions-1'&&document.module_uil_sha256===manifest.module_uil_sha256&&typeof document.allow_behavior_variants==='boolean','Region source identity differs');
  check(canonical(resolved.execution_program)===canonical(execution)&&resolved.execution_uil_sha256===manifest.execution_uil_sha256,'Region execution view differs');
  const restored=clone(execution);restored.functions=clone(manifest.program.functions);
  check(canonical(restored)===canonical(manifest.program),'Region view changed canonical program');
  const slots=resolved.slots,names=Object.keys(slots);
  check(names.length>0&&names.length<=16&&canonical(names.sort())===canonical(Object.keys(document.slots).sort())&&canonical(Object.keys(execution.functions).sort())===canonical([...Object.keys(manifest.program.functions),...names].sort()),'Region binding set differs');
  const walk=function*(nodes){for(const node of nodes){yield node;if(node.op==='if'){yield*walk(node.then);yield*walk(node.else);}else if(node.op==='while')yield*walk(node.body);}};
  for(const [name,slot] of Object.entries(slots)){
    const source=slot.region.source,declared=document.slots[name],output=slot.region.output;
    check(!own(manifest.program.functions,name)&&slot.region.name===name&&source.count===1&&own(manifest.program.functions,source.function),'Invalid region source');
    const matches=[...walk(manifest.program.functions[source.function].body)].filter(node=>node.id===source.entry);
    check(matches.length===1&&matches[0].op==='store'&&matches[0].index===output.index&&u32(output.min)&&u32(output.max)&&output.min<=output.max,'Region source boundary differs');
    check(canonical(execution.functions[name])===canonical({max_steps:1,body:[plain(matches[0])]}),'Virtual region changed source update');
    check(slot.label===declared.label&&slot.default===declared.default&&own(slot.variants,slot.default)&&slot.variants[slot.default].assurance==='exact-source-region'&&canonical(Object.keys(slot.variants).sort())===canonical(Object.keys(declared.variants).sort()),'Region variants or default differ');
    for(const [variant,spec] of Object.entries(slot.variants)){
      const program=spec.program,fn=program.functions[name],policy=spec.assurance,exact=canonical(plain(fn?.body))===canonical([plain(matches[0])]);
      check(spec.function===name&&spec.label===declared.variants[variant].label&&program.format==='fdisbull-memory-uil-1'&&program.role==='uil'&&canonical(program.memory)===canonical(manifest.program.memory)&&canonical(program.variables)==='{}'&&canonical(Object.keys(program.functions))===canonical([name])&&fn.max_steps===1&&fn.body.length===1&&fn.body[0].op==='store'&&fn.body[0].index===output.index,'Invalid region realization');
      check((policy==='exact-source-region'&&exact)||(policy==='intentional-behavior-variant'&&!exact&&document.allow_behavior_variants),'Region behavior policy differs');
      for(const backend of ['wasm','webgpu']){
        const ids=spec.identities[backend],build=manifest.region_variants?.[backend]?.[name]?.[variant]?.build;
        check(ids.selection===declared.variants[variant].selections[backend]&&ids.assurance===policy&&ids.module_uil_sha256===manifest.module_uil_sha256&&canonical(ids.region)===canonical(slot.region)&&build?.module_uil_sha256===ids.implementation_uil_sha256,'Region endpoint identity differs');
      }
    }
  }
  const requested=manifest.source_cut_document;
  check(requested?.format==='fdisbull-memory-cuts-2'&&requested.module_uil_sha256===manifest.module_uil_sha256&&canonical(manifest.cuts.document)===canonical({...requested,format:'fdisbull-memory-cuts-1',module_uil_sha256:manifest.execution_uil_sha256}),'Region source cut mapping differs');
}

function checkCutLinks(manifest){
  const lowered=manifest.cuts,document=lowered.document,grouped=Object.create(null);
  const program=manifest.execution_program||manifest.program,identity=manifest.execution_uil_sha256||manifest.module_uil_sha256;
  check(document?.format==='fdisbull-memory-cuts-1'&&document.module_uil_sha256===identity&&Array.isArray(document.cuts)&&document.cuts.length>0&&document.cuts.length<=32,'Invalid cut document');
  for(const cut of document.cuts){
    check(Object.hasOwn(program.functions,cut.caller)&&Object.hasOwn(program.functions,cut.callee),'Unknown cut endpoint');
    (grouped[cut.caller]??=[]).push(cut);
  }
  check(canonical(Object.keys(grouped).sort())===canonical(Object.keys(lowered.functions).sort()),'Cut owners differ from document');
  for(const [fn,entries] of Object.entries(grouped)){
    const owner=lowered.functions[fn],numbers=entries.map((_,i)=>String(i+1));
    check(canonical(Object.keys(owner.yields).sort())===canonical(numbers.slice().sort())&&canonical(Object.keys(owner.phases).sort())===canonical(['entry',...numbers.map(n=>'resume_'+n)].sort()),'Cut phase set differs from document');
    entries.forEach((cut,i)=>check(canonical(owner.yields[String(i+1)])===canonical({callee:cut.callee,resume:'resume_'+(i+1),adapter_steps:2}),'Cut callee or continuation differs from document'));
  }
}

export class MemoryShell {
  #manifest;#providers;#phases;#regions;#implementations;#words;#bindings;#revision=0;#epoch=0;#generation=0;
  #session=crypto.randomUUID();#closed=false;#disposing=null;#tail=Promise.resolve();#pending=0;#tickets=new Map();#sequence=0;
  constructor(manifest,providers,initial,phases={},regions={}) {
    this.#manifest=clone(manifest);this.#providers=Object.fromEntries(Object.entries(providers).map(([kind,functions])=>[kind,{...functions}]));
    this.#phases=Object.fromEntries(Object.entries(phases).map(([kind,functions])=>[kind,Object.fromEntries(Object.entries(functions).map(([fn,entries])=>[fn,{...entries}]))]));
    this.#regions=Object.fromEntries(Object.entries(regions).map(([kind,functions])=>[kind,Object.fromEntries(Object.entries(functions).map(([fn,entries])=>[fn,{...entries}]))]));
    const {plan,program}=this.#manifest;
    check(plan?.format==='fdisbull-memory-orchestration-1'&&program?.format==='fdisbull-memory-uil-1','Unsupported memory shell');
    check(plan.concurrency==='ordered-events'&&Number.isInteger(program.memory.words),'Unsupported event policy');
    this.#words=this.#arena(initial);this.#bindings=clone(plan.bindings);
    this.#implementations=Object.fromEntries(Object.entries(manifest.regions?.slots||{}).map(([name,slot])=>[name,slot.default]));
    if(manifest.regions)checkRegionLinks(this.#manifest);
    if(manifest.cuts){
      check(manifest.cuts.format==='fdisbull-memory-cut-lowering-1'&&manifest.cuts.module_uil_sha256===(manifest.execution_uil_sha256||manifest.module_uil_sha256),'Cut source identity differs');
      checkCutLinks(this.#manifest);
      for(const [fn,cut] of Object.entries(manifest.cuts.functions))
        check(Object.hasOwn((manifest.execution_program||program).functions,fn)&&cut.max_steps===(manifest.execution_program||program).functions[fn].max_steps&&Object.hasOwn(cut.phases,'entry'),'Invalid cut owner');
    }
    for(const [fn,backend] of Object.entries(this.#bindings))this.#provider(fn,backend);
    this.#validate(this.#words);
    const handles=this.#handles();
    for(const p of handles)check(!providerOwners.has(p),'Provider wrapper already belongs to a shell');
    for(const p of handles)providerOwners.set(p,this);
  }
  #open(){check(!this.#closed,'Shell disposed');}
  #handles(){return [...new Set([...Object.values(this.#providers).flatMap(x=>Object.values(x)),...[this.#phases,this.#regions].flatMap(r=>Object.values(r).flatMap(x=>Object.values(x).flatMap(y=>Object.values(y))))])];}
  #slot(fn){return own(this.#manifest.regions?.slots,fn)?this.#manifest.regions.slots[fn]:null;}
  #arena(values){
    check((Array.isArray(values)||ArrayBuffer.isView(values))&&values.length===this.#manifest.program.memory.words,'Invalid arena length');
    check(Array.from(values).every(u32),'Invalid arena word');return Uint32Array.from(values);
  }
  #provider(fn,backend=this.#bindings[fn],implementation=this.#implementations[fn]) {
    const slot=this.#slot(fn);
    if(slot){
      check(own(slot.variants,implementation),'Unknown region implementation');
      const p=this.#regions[backend]?.[fn]?.[implementation],expected=this.#manifest.region_variants?.[backend]?.[fn]?.[implementation]?.build;
      check(p&&!p.closed&&!p.lost,'Region provider unavailable');
      const b=p.describe();
      check(expected&&canonical(b)===canonical(expected)&&b.target===({wasm:'wasm32-memory-1',webgpu:'webgpu-wgsl-memory-1'})[backend]&&b.function===fn&&b.module_uil_sha256===slot.variants[implementation].identities[backend].implementation_uil_sha256&&b.abi.memory_words===this.#words.length&&b.abi.max_steps===1&&b.abi.report_steps===true,'Region provider identity differs');
      return p;
    }
    const p=this.#providers[backend]?.[fn];check(p&&!p.closed&&!p.lost,'Provider unavailable');
    const b=p.describe();check(b.target===({wasm:'wasm32-memory-1',webgpu:'webgpu-wgsl-memory-1'})[backend]&&b.function===fn&&b.module_uil_sha256===this.#manifest.module_uil_sha256&&b.abi.memory_words===this.#words.length,'Provider identity differs');
    if(this.#manifest.cuts){
      check(b.abi.report_steps===true,'Cut execution requires step receipts');
      const cut=Object.hasOwn(this.#manifest.cuts.functions,fn)?this.#manifest.cuts.functions[fn]:null;
      if(cut)for(const phase of Object.keys(cut.phases))this.#phase(fn,backend,phase);
    }
    return p;
  }
  #phase(fn,backend,name){
    const cut=this.#manifest.cuts.functions[fn],spec=cut.phases[name],p=this.#phases[backend]?.[fn]?.[name];
    check(spec&&p&&!p.closed&&!p.lost,'Cut phase unavailable');
    const b=p.describe(),expected=this.#manifest.cut_variants?.[backend]?.[fn]?.[name]?.build;
    check(expected&&canonical(b)===canonical(expected)&&b.target===({wasm:'wasm32-memory-1',webgpu:'webgpu-wgsl-memory-1'})[backend]&&b.function===fn&&b.abi.memory_words===this.#words.length&&b.abi.report_steps===true&&canonical(b.abi.capture_locals)===canonical([cut.token_local]),'Cut phase identity differs');
    return p;
  }
  #validate(words){
    for(const g of this.#manifest.plan.guards||[])check(words[g.index]>=g.min&&words[g.index]<=g.max,'State guard refused');
    for(const g of this.#manifest.plan.array_guards||[]){
      const n=words[g.length_index];check(n<=g.capacity,'Array prefix length refused');
      const seen=new Set();let previous=null;
      for(let i=0;i<n;i++){
        const value=words[g.offset+i];check(value>=g.min&&value<=g.max,'Array value refused');
        if(g.unique)check(!seen.has(value),'Duplicate active array item');seen.add(value);
        if(previous!==null){const distance=Math.abs(value-previous);check(distance===g.adjacent_columns||(distance===1&&Math.floor(value/g.adjacent_columns)===Math.floor(previous/g.adjacent_columns)),'Nonadjacent array items');}
        previous=value;
      }
      if(words[g.exclude.when_index]===g.exclude.when_value){const value=words[g.exclude.index];check(value>=g.min&&value<=g.max&&!seen.has(value),'Excluded value outside domain or overlaps active array');}
    }
    const f=this.#manifest.plan.frame;
    for(let n=f.offset;n<f.offset+f.width*f.height;n++)check(words[n]<=255&&Object.hasOwn(f.palette,String(words[n])),'Invalid indexed pixel');
  }
  describe(){this.#open();return clone(this.#manifest);}
  snapshot(){this.#open();return {session:this.#session,generation:this.#generation,revision:this.#revision,words:this.#words.slice(),bindings:clone(this.#bindings),...(this.#manifest.regions?{implementations:clone(this.#implementations)}:{})};}
  capabilities(){return {closed:this.#closed,bindings:clone(this.#bindings),...(this.#manifest.regions?{implementations:clone(this.#implementations)}:{}),backends:Object.fromEntries(Object.keys(this.#providers).map(kind=>[kind,!this.#closed&&Object.keys(this.#bindings).every(fn=>{try{this.#provider(fn,kind);return true;}catch{return false;}})]))};}
  selectBackend(backend,functions=Object.keys(this.#bindings)){
    this.#open();check(Array.isArray(functions)&&functions.length>0,'Select named functions');
    for(const fn of functions){check(Object.hasOwn(this.#bindings,fn),'Unknown binding');this.#provider(fn,backend);}
    for(const fn of functions)this.#bindings[fn]=backend;
    this.#epoch=inc(this.#epoch);return this.capabilities();
  }
  selectRegionImplementation(region,implementation){
    this.#open();check(this.#slot(region),'Unknown region binding');
    this.#provider(region,this.#bindings[region],implementation);
    this.#implementations[region]=implementation;this.#epoch=inc(this.#epoch);return this.capabilities();
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
    const bindings=clone(this.#bindings),implementations=clone(this.#implementations),leases=[],execution=[];
    const invoke=async(provider,name,words,detail)=>{
      leases.push([provider,provider.epoch]);
      const result=await provider.invoke(words);
      if(this.#manifest.cuts){
        check(Number.isInteger(result.steps)&&result.steps>=0&&result.steps<=provider.describe().abi.max_steps,'Invalid step receipt');
        execution.push({function:name,backend:bindings[name],...detail,status:result.status,steps:result.steps});
      }
      check(result.status==='complete','Memory block refused');const output=this.#arena(result.words);
      return {...result,words:output};
    };
    const execute=async(name,words,depth)=>{
      check(depth<16,'Cut call depth exceeded');
      const provider=this.#provider(name,bindings[name],implementations[name]),owners=this.#manifest.cuts?.functions,slot=this.#slot(name);
      if(slot)return invoke(provider,name,words,{kind:'region',implementation:implementations[name],implementation_uil_sha256:provider.describe().module_uil_sha256,assurance:slot.variants[implementations[name]].assurance});
      const cut=owners&&Object.hasOwn(owners,name)?owners[name]:null;
      if(!cut)return invoke(provider,name,words,{kind:'block'});
      let phase='entry',total=0,staged=words;
      // Cuts cannot have loop ancestors. Every continuation moves forward in
      // its lexical function, so an admitted owner can yield at most once per cut.
      for(let n=0;n<=Object.keys(cut.yields).length;n++){
        const result=await invoke(this.#phase(name,bindings[name],phase),name,staged,{kind:'phase',phase});
        const value=result.locals?.[cut.token_local];
        check(u32(value),'Invalid continuation token');
        if(value===0){
          total+=result.steps;check(total<=cut.max_steps,'Canonical caller budget exhausted');
          return {status:'complete',words:result.words,steps:total};
        }
        const next=cut.yields[String(value)];
        check(next&&next.adapter_steps===2&&result.steps>=next.adapter_steps,'Unknown continuation token');
        total+=result.steps-next.adapter_steps;
        check(total<=cut.max_steps,'Canonical caller budget exhausted');
        const child=await call(next.callee,result.words,depth+1);
        total+=child.steps;check(total<=cut.max_steps,'Canonical caller budget exhausted');
        staged=child.words;phase=next.resume;
      }
      throw Error('Cut continuation limit exceeded');
    };
    const call=async(name,words,depth=0)=>{
      const result=await execute(name,words,depth),slot=this.#slot(name),ranges=slot?[[slot.region.output.index,1]]:this.#manifest.plan.outputs[name];
      for(let n=0;n<words.length;n++)if(!ranges.some(([start,count])=>n>=start&&n<start+count))check(result.words[n]===words[n],'Kernel wrote outside declared output');
      if(slot){const output=slot.region.output;check(result.steps===1&&result.words[output.index]>=output.min&&result.words[output.index]<=output.max,'Region output domain refused');}
      // A cut is not an application observation point. Intermediate phases and
      // nested callees may temporarily violate invariants restored by the owner.
      if(depth===0)this.#validate(result.words);
      return result;
    };
    const ticket={id,token,canceled:false,finishing:false,result:null,ready:null};this.#tickets.set(id,ticket);
    ticket.ready=Promise.resolve().then(async()=>{
      let {words}=await call(fn,snapshot);
      if(options.render&&fn!==this.#manifest.plan.render.function&&words[this.#manifest.plan.render.when_nonzero]!==0)
        ({words}=await call(this.#manifest.plan.render.function,words));
      ticket.result={words,leases,execution};
    }).catch(error=>{ticket.result={error:String(error?.message||error),leases,execution};});
    return Object.freeze({id,ready:ticket.ready.then(()=>({status:ticket.result.error?'failed':'complete'}))});
  }
  cancel(id){this.#open();const ticket=this.#tickets.get(id);check(ticket,'Unknown operation');ticket.canceled=true;return {status:'canceled',physical_cancellation:false};}
  async finish(id){
    const t=this.#tickets.get(id);check(t&&!t.finishing,'Unknown or consumed operation');t.finishing=true;
    try {
      await t.ready;const result={operation:id,committed:false,...(this.#manifest.cuts?{execution:clone(t.result.execution)}:{})};
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
  discardPending(){
    this.#open();this.#epoch=inc(this.#epoch);
    // Logical invalidation is immediate; physical leases still drain through
    // the ordered tail. The caller may then admit a new control event safely.
    return this.#tail.then(()=>({settled:true,physical_cancellation:false}));
  }
  dispose(){
    if(this.#disposing)return this.#disposing;
    this.#closed=true;this.#epoch=inc(this.#epoch);this.#words.fill(0);
    const providers=this.#handles();
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
  if(manifest.regions){
    checkRegionLinks(manifest);
    check(await sha(encode(manifest.regions))===manifest.regions_sha256&&await sha(encode(manifest.regions.document))===manifest.regions.region_plan_sha256,'Region plan identity differs');
    check(await sha(encode(manifest.execution_program))===manifest.execution_uil_sha256&&await sha(encode(manifest.source_cut_document))===manifest.source_cut_plan_sha256,'Region derivation identity differs');
    for(const [name,slot] of Object.entries(manifest.regions.slots))for(const spec of Object.values(slot.variants)){
      const hash=await sha(encode(spec.program));
      for(const backend of ['wasm','webgpu'])check(spec.identities[backend].implementation_uil_sha256===hash,'Region implementation UIL differs');
    }
  }
  if(manifest.cuts){
    checkCutLinks(manifest);
    check(await sha(encode(manifest.cuts))===manifest.cuts_sha256,'Cut lowering identity differs');
    check(manifest.cuts.module_uil_sha256===(manifest.execution_uil_sha256||manifest.module_uil_sha256)&&await sha(encode(manifest.cuts.document))===manifest.cuts.cut_plan_sha256,'Cut plan identity differs');
    for(const [fn,cut] of Object.entries(manifest.cuts.functions))for(const [name,phase] of Object.entries(cut.phases)){
      const identity=await sha(encode(phase.program));
      for(const backend of ['wasm','webgpu'])check(manifest.cut_variants?.[backend]?.[fn]?.[name]?.build?.module_uil_sha256===identity,'Cut phase UIL identity differs');
    }
  }
  const assets=new Map();
  await Promise.all(Object.entries(manifest.artifacts).map(async([name,expected])=>{
    check(name.split('/').every(x=>x&&x!=='.'&&x!=='..')&&!/[\\?#:]/.test(name),'Unsafe artifact path');
    const path=new URL(name,base);check(path.origin===base.origin,'Cross-origin artifact');
    const r=await fetch(path);check(r.ok,'Shell asset unavailable: '+name);const bytes=await r.arrayBuffer();
    check(await sha(bytes)===expected,'Shell asset hash differs: '+name);assets.set(name,bytes);
  }));
  const providers={wasm:Object.create(null),webgpu:Object.create(null)},phases={wasm:Object.create(null),webgpu:Object.create(null)},regions={wasm:Object.create(null),webgpu:Object.create(null)};let device=null,shell=null;
  const loadPhases=async backend=>{
    for(const [fn,entries] of Object.entries(manifest.cut_variants?.[backend]||{})){
      phases[backend][fn]=Object.create(null);
      for(const [name,v] of Object.entries(entries))phases[backend][fn][name]=backend==='wasm'?
        await createWasmMemoryProvider(v.build,assets.get(v.directory+'/block.wasm')):
        await createGPUMemoryProvider(v.build,new TextDecoder().decode(assets.get(v.directory+'/block.wgsl')),{device,ownsDevice:false});
    }
  };
  const loadRegions=async backend=>{
    for(const [fn,entries] of Object.entries(manifest.region_variants?.[backend]||{})){
      regions[backend][fn]=Object.create(null);
      for(const [name,v] of Object.entries(entries))regions[backend][fn][name]=backend==='wasm'?
        await createWasmMemoryProvider(v.build,assets.get(v.directory+'/block.wasm')):
        await createGPUMemoryProvider(v.build,new TextDecoder().decode(assets.get(v.directory+'/block.wgsl')),{device,ownsDevice:false});
    }
  };
  try {
    for(const [fn,v] of Object.entries(manifest.variants.wasm))
      providers.wasm[fn]=await createWasmMemoryProvider(v.build,assets.get(v.directory+'/block.wasm'));
    await loadPhases('wasm');
    await loadRegions('wasm');
    if(navigator.gpu){
      const adapter=await navigator.gpu.requestAdapter();
      if(adapter){device=await adapter.requestDevice();
        for(const [fn,v] of Object.entries(manifest.variants.webgpu))
          providers.webgpu[fn]=await createGPUMemoryProvider(v.build,new TextDecoder().decode(assets.get(v.directory+'/block.wgsl')),{device,ownsDevice:false});
        await loadPhases('webgpu');
        await loadRegions('webgpu');
      }
    }
    if(!Object.keys(providers.webgpu).length)delete providers.webgpu;
    const initial=JSON.parse(new TextDecoder().decode(assets.get('initial.json')));
    shell=new MemoryShell(manifest,providers,initial,phases,regions);
    const owner=shell,ownedDevice=device;let disposed=null;
    // Device creation is a loader responsibility. Every function wrapper borrows
    // it; only this owner destroys it, after all physical jobs have drained.
    return Object.freeze({
      describe:()=>owner.describe(),snapshot:()=>owner.snapshot(),capabilities:()=>owner.capabilities(),
      selectBackend:(...a)=>owner.selectBackend(...a),replace:(...a)=>owner.replace(...a),
      selectRegionImplementation:(...a)=>owner.selectRegionImplementation(...a),
      start:(...a)=>owner.start(...a),finish:(...a)=>owner.finish(...a),cancel:(...a)=>owner.cancel(...a),dispatch:(...a)=>owner.dispatch(...a),
      discardPending:()=>owner.discardPending(),
      dispose(){return disposed??=(async()=>{await owner.dispose();ownedDevice?.destroy();return {settled:true};})();}
    });
  } catch(error){
    if(shell)await shell.dispose();else await Promise.allSettled([
      ...Object.values(providers).flatMap(x=>Object.values(x)),
      ...[phases,regions].flatMap(r=>Object.values(r).flatMap(x=>Object.values(x).flatMap(y=>Object.values(y))))].map(p=>p.dispose()));
    device?.destroy();throw error;
  }
}
