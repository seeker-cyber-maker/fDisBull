// Qualification consumes original observations; it never implements food math.
const UIL = '332f84e5067fa7aee5405a001ac68efb991fd644bcf34cd62a232f453df057ed';
const check = (value, message) => {if (!value) throw Error(message);};
const canonical = value => Array.isArray(value) ? value.map(canonical) : value!==null && typeof value==='object'
  ? Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])])) : value;
const equal = (left, right, message) => check(JSON.stringify(canonical(left)) === JSON.stringify(canonical(right)), message);
const bytes = snapshot => Array.from(snapshot.bytes);

function sameState(before, after, message) {
  equal({id:after.id,generation:after.generation,revision:after.revision,values:after.values,bytes:bytes(after)},
        {id:before.id,generation:before.generation,revision:before.revision,values:before.values,bytes:bytes(before)},message);
}

function inputState(manifest, ports) {
  const changes = Object.create(null);
  for (const [port, cell] of Object.entries(manifest.plan.inputs)) {
    check(Object.hasOwn(ports,port),'Missing observed input port');
    if (Object.hasOwn(changes,cell)) check(changes[cell]===ports[port],'Conflicting aliased test input');
    changes[cell]=ports[port];
  }
  return changes;
}

function cellBytes(manifest, cells) {
  const writable = new Set();
  for (const cell of cells) {
    const descriptor=manifest.layout.cells[cell];
    for (let index=0;index<descriptor.size;index++) writable.add(descriptor.offset+index);
  }
  return writable;
}

function preserved(before, after, writable, message) {
  check(before.bytes.length===after.bytes.length,message+': arena size');
  for (let index=0;index<before.bytes.length;index++)
    if (!writable.has(index)) check(before.bytes[index]===after.bytes[index],message+': byte '+index);
}

export async function exerciseShell(shell, manifest, study) {
  check(study.format==='fdisbull-browser-shell-study-1','Wrong study format');
  check(study.module_uil_sha256===UIL && manifest.module_uil_sha256===UIL,'Food UIL identity differs');
  check(study.normal.length>0 && study.chain.steps===24 && study.chain.vectors.length===24,'Incomplete original observations');
  const capabilities=shell.capabilities();
  check(capabilities.backends.wasm.available && capabilities.backends.webgpu.available,'Both real providers required');
  const outputCells=cellBytes(manifest,Object.values(manifest.plan.outputs));
  const mutableCells=cellBytes(manifest,[...Object.values(manifest.plan.inputs),...Object.values(manifest.plan.outputs)]);
  const checks=[];
  const passed=(name,backend,extra={})=>checks.push({name,...(backend?{backend}:{}),status:'passed',...extra});
  const result={status:'running',module_uil_sha256:UIL,normal:{},chain:{steps:24,outputs:[]},checks};
  const first=study.normal[0],second=study.normal[1] || first;
  const stockCell=manifest.plan.outputs.new_stock;
  check(typeof stockCell==='string','Food output mapping missing');
  const description=shell.describe();
  equal(description,{module_uil_sha256:UIL,plan:manifest.plan,layout:manifest.layout,interface:manifest.interface},'Actual shell description differs');
  const mutated=shell.describe();mutated.plan.title='external mutation';
  equal(shell.describe(),description,'Description aliases the shell manifest');
  passed('owned-pinned-description');

  async function computed(ticket) {
    const ready=await ticket.ready;
    check(ready.status==='complete','Admitted original computation failed or refused');
    return ready;
  }

  function committed(before,after,receipt,expected,backend,label) {
    check(receipt.status==='committed' && receipt.committed===true,label+': not committed');
    check(receipt.backend===backend && receipt.module_uil_sha256===UIL,label+': wrong provider/UIL');
    equal(receipt.outputs,expected,label+': original output differs');
    for (const [port,value] of Object.entries(expected))
      check(after.values[manifest.plan.outputs[port]]===value,label+': stored output differs');
    check(after.revision===before.revision+1 && receipt.revision===after.revision,label+': revision');
    check(after.generation===before.generation && after.id===before.id,label+': entity changed');
    preserved(before,after,outputCells,label+': non-output commit');
  }

  shell.selectEntity('city-a');
  const owned=shell.snapshot('city-a'),copy=shell.snapshot('city-a');
  copy.bytes.fill(0);for (const name of Object.keys(copy.values)) copy.values[name]=null;
  sameState(owned,shell.snapshot('city-a'),'Snapshot aliases shell memory');
  passed('snapshot-memory-ownership');

  for (const backend of ['wasm','webgpu']) {
    shell.selectBackend(backend);shell.selectEntity('city-a');
    const readonly=shell.snapshot('city-a'),otherRecord=shell.snapshot('city-b');
    const outputs=[];
    for (const [index,vector] of study.normal.entries()) {
      shell.editRecord('city-a',inputState(manifest,vector.inputs));
      const before=shell.snapshot('city-a'),ticket=shell.start();
      preserved(readonly,before,mutableCells,'Input edit changed hidden memory');
      await computed(ticket);
      sameState(before,shell.snapshot('city-a'),'Ready computation committed before finish');
      const receipt=await shell.finish(ticket.id),after=shell.snapshot('city-a');
      committed(before,after,receipt,vector.expected,backend,backend+' original row '+index);
      preserved(readonly,after,mutableCells,'Hidden memory changed across normal rows');
      outputs.push(after.values[stockCell]);
    }
    sameState(otherRecord,shell.snapshot('city-b'),'Another entity arena changed');
    result.normal[backend]={cases:outputs.length,outputs};
    passed('original-rows-and-output-only-commits',backend,{cases:outputs.length});
    passed('computed-ready-is-not-committed',backend,{cases:outputs.length});
    passed('other-record-and-hidden-memory-preserved',backend);

    let typedRefusals=0,domainRefusals=0;
    for (const vector of study.invalid) {
      shell.editRecord('city-a',inputState(manifest,first.inputs));
      const beforeEdit=shell.snapshot('city-a');
      if (vector.expected==='state-type-refused') {
        let rejected=false;
        try {shell.editRecord('city-a',inputState(manifest,vector.inputs));} catch {rejected=true;}
        check(rejected,'Invalid typed state was accepted');
        sameState(beforeEdit,shell.snapshot('city-a'),'Rejected edit changed state');
        typedRefusals++;
      } else {
        check(vector.expected==='refused','Unknown invalid-case expectation');
        shell.editRecord('city-a',inputState(manifest,vector.inputs));
        const before=shell.snapshot('city-a'),ticket=shell.start(),ready=await ticket.ready;
        check(ready.status==='refused','Out-of-domain computation did not refuse');
        sameState(before,shell.snapshot('city-a'),'Refused readiness mutated state');
        const receipt=await shell.finish(ticket.id);
        check(receipt.status==='refused' && !receipt.committed,'Refused computation committed');
        equal(receipt.outputs,{},'Refusal exposed outputs');
        sameState(before,shell.snapshot('city-a'),'Refusal changed arena or revision');
        domainRefusals++;
      }
    }
    passed('typed-edit-refusal-is-atomic',backend,{cases:typedRefusals});
    passed('domain-refusal-never-commits',backend,{cases:domainRefusals});

    const reset=()=>{
      shell.selectEntity('city-a');shell.selectBackend(backend);
      shell.editRecord('city-a',inputState(manifest,first.inputs));
    };
    async function discard(name,alter) {
      reset();const before=shell.snapshot('city-a'),ticket=shell.start();await computed(ticket);
      sameState(before,shell.snapshot('city-a'),name+': pre-finish mutation');
      alter(before,ticket);
      const changed=shell.snapshot('city-a'),receipt=await shell.finish(ticket.id);
      check(receipt.status==='discarded' && !receipt.committed,name+': stale result committed');
      equal(receipt.outputs,{},name+': stale outputs exposed');
      sameState(changed,shell.snapshot('city-a'),name+': discard changed arena');
      passed(name,backend,{computed:'complete',outcome:'discarded',reason:receipt.reason});
    }
    await discard('state-change-after-computation',()=>shell.editRecord('city-a',inputState(manifest,second.inputs)));
    await discard('state-aba-after-computation',before=>{
      shell.editRecord('city-a',inputState(manifest,second.inputs));
      shell.editRecord('city-a',inputState(manifest,first.inputs));
      equal(bytes(before),bytes(shell.snapshot('city-a')),'State ABA did not restore bytes');
    });
    await discard('view-aba-after-computation',()=>{shell.selectEntity('city-b');shell.selectEntity('city-a');});
    await discard('binding-aba-after-computation',()=>{
      shell.selectBackend(backend==='wasm'?'webgpu':'wasm');shell.selectBackend(backend);
    });
    await discard('entity-generation-aba-after-computation',before=>{
      shell.removeRecord('city-a');shell.addRecord('city-a',before.values);shell.selectEntity('city-a');
      check(shell.snapshot('city-a').generation!==before.generation,'Recreated identity reused generation');
    });
    await discard('cancel-computed-result',(before,ticket)=>shell.cancel(ticket.id));

    reset();
    {
      const before=shell.snapshot('city-a'),older=shell.start(),newer=shell.start();
      await Promise.all([computed(older),computed(newer)]);
      sameState(before,shell.snapshot('city-a'),'Overlapping computations auto-committed');
      const oldReceipt=await shell.finish(older.id);
      check(oldReceipt.status==='discarded' && !oldReceipt.committed,'Superseded request committed');
      const newReceipt=await shell.finish(newer.id);
      committed(before,shell.snapshot('city-a'),newReceipt,first.expected,backend,'Overlapping latest request');
      passed('overlap-physical-completion-latest-only-commit',backend,{computed:2,committed:1});
    }
    reset();
    {
      const before=shell.snapshot('city-a'),canceled=shell.start();shell.cancel(canceled.id);
      const newer=shell.start();
      await Promise.all([computed(canceled),computed(newer)]);
      const oldReceipt=await shell.finish(canceled.id);
      check(oldReceipt.status==='discarded' && !oldReceipt.committed,'Canceled request committed');
      const newReceipt=await shell.finish(newer.id);
      committed(before,shell.snapshot('city-a'),newReceipt,first.expected,backend,'Cancel/new run');
      passed('cancel-and-new-run-without-fallback',backend,{computed:2,committed:1});
    }
    reset();
    {
      const before=shell.snapshot('city-a'),ticket=shell.start();
      const accepted=shell.finish(ticket.id);let rejected=false;
      try {await shell.finish(ticket.id);} catch {rejected=true;}
      check(rejected,'A second finish consumed one operation twice');
      const receipt=await accepted;
      committed(before,shell.snapshot('city-a'),receipt,first.expected,backend,'Single consumer');
      passed('single-finish-consumer',backend);
    }
  }

  shell.selectEntity('city-a');shell.editRecord('city-a',inputState(manifest,study.chain.initial));
  for (const [index,vector] of study.chain.vectors.entries()) {
    const backend=index%2===0?'wasm':'webgpu';shell.selectBackend(backend);
    const before=shell.snapshot('city-a');
    for (const [port,value] of Object.entries(vector.inputs))
      check(before.values[manifest.plan.inputs[port]]===value,'Chain input is not previous committed original state');
    const ticket=shell.start();await computed(ticket);
    sameState(before,shell.snapshot('city-a'),'Chain computation auto-committed');
    const receipt=await shell.finish(ticket.id),after=shell.snapshot('city-a');
    committed(before,after,receipt,vector.expected,backend,'Alternating original chain '+index);
    result.chain.outputs.push(after.values[stockCell]);
  }
  passed('alternating-backend-carried-state-chain',null,{steps:24,initializations:1});
  result.status='passed';
  return result;
}
