// Deterministic shell checks around real Wasm and optional physical GPU work.
// Usage: node web_shell_checks.mjs PRIVATE_SHELL_BUNDLE [PRIVATE_NPM_ROOT]
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';

const root = path.resolve(process.argv[2]);
const manifest = JSON.parse(await fs.readFile(path.join(root, 'shell.json')));
const {createShell, createWasmProvider, createGPUProvider, loadShell} = await import(pathToFileURL(path.join(root, 'shell.mjs')));
const UIL = '332f84e5067fa7aee5405a001ac68efb991fd644bcf34cd62a232f453df057ed';
const BASE = {stock:10,produced:9,population:3,supported:2,support_cost:1,sentinel:23130};
const checks = [];
const result = {format:'fdisbull-web-shell-checks-1',status:'running',runtime:process.version,
  module_uil_sha256:UIL,gpu:{status:'not_requested'},checks};

async function deadline(promise,message) {
  let timer;
  try {
    return await Promise.race([promise,new Promise((_,reject)=>{
      timer=setTimeout(()=>reject(Error(message)),5000);
    })]);
  } finally {clearTimeout(timer);}
}

const bundles = {};
for (const name of ['wasm','webgpu']) {
  const variant = manifest.variants[name];
  const directory = path.join(root, variant.directory);
  const build = JSON.parse(await fs.readFile(path.join(directory,'build.json')));
  assert.deepEqual(build,variant.build,'shell manifest must pin its exact leaf build');
  assert.equal(build.module_uil_sha256,UIL,'fixture must retain the shared food UIL');
  bundles[name] = {build,data:await fs.readFile(path.join(directory,name==='wasm'?'block.wasm':'block.wgsl'))};
}
assert.equal(bundles.wasm.build.contract_sha256,bundles.webgpu.build.contract_sha256);
assert.equal(manifest.module_uil_sha256,UIL);

let gpu = null,adapter = null,device = null;
if (process.argv[3]) {
  const require = createRequire(path.join(path.resolve(process.argv[3]),'package.json'));
  const module = await import(pathToFileURL(require.resolve('webgpu')));
  Object.assign(globalThis,module.globals);
  gpu = module.create(['backend='+(process.env.FDISBULL_GPU_BACKEND || 'metal')]);
  adapter = await gpu.requestAdapter();
  assert(adapter,'actual GPU adapter required');
  assert.equal(adapter.info.isFallbackAdapter,false,'a fallback adapter cannot qualify GPU orchestration');
  device = await adapter.requestDevice();
  result.gpu = {status:'physical_device',vendor:adapter.info.vendor,
    architecture:adapter.info.architecture,device:adapter.info.device,isFallbackAdapter:false};
}

async function providers(gpuDevice=device) {
  const wasm = await createWasmProvider(bundles.wasm.build,bundles.wasm.data);
  const registry = {wasm};
  if (gpuDevice) registry.webgpu = await createGPUProvider(
    bundles.webgpu.build,bundles.webgpu.data.toString('utf8'),{device:gpuDevice,ownsDevice:false});
  return registry;
}

async function additionalDevice() {
  // Dawn's adapter handle is consumed by requestDevice; acquire a new handle.
  const available = await gpu.requestAdapter();
  assert(available,'physical GPU adapter required for lifecycle check');
  assert.equal(available.info.isFallbackAdapter,false);
  return available.requestDevice();
}

async function missingGPUResource(body) {
  const allowed = new Map([['/shell.json',path.join(root,'shell.json')]]);
  for (const name of Object.keys(manifest.artifacts)) {
    const file=path.resolve(root,name);
    assert(file.startsWith(root+path.sep),'loopback fixture must stay inside the authored bundle');
    allowed.set('/'+name,file);
  }
  const missing='/'+manifest.variants.webgpu.directory+'/block.wgsl';
  let missingRequests=0;
  const server=http.createServer(async(request,response)=>{
    try {
      const name=new URL(request.url,'http://127.0.0.1').pathname;
      if(request.method!=='GET') {response.writeHead(405);response.end();return;}
      if(name===missing) {missingRequests++;response.writeHead(404);response.end('Deliberately absent GPU source');return;}
      const file=allowed.get(name);
      if(!file) {response.writeHead(404);response.end();return;}
      response.setHeader('Content-Type',file.endsWith('.json')?'application/json':'application/octet-stream');
      response.end(await fs.readFile(file));
    } catch {
      response.writeHead(500);response.end('Fixture resource unavailable');
    }
  });
  await new Promise((resolve,reject)=>{
    server.once('error',reject);server.listen(0,'127.0.0.1',resolve);
  });
  try {
    await body(new URL(`http://127.0.0.1:${server.address().port}/`));
    assert(missingRequests>0,'loader must reach the injected GPU source fetch failure');
  } finally {
    server.closeAllConnections();await new Promise(resolve=>server.close(resolve));
  }
}

async function deviceUsable(device) {
  device.pushErrorScope('validation');
  const buffer=device.createBuffer({size:4,usage:GPUBufferUsage.COPY_DST|GPUBufferUsage.STORAGE});
  try {
    device.queue.writeBuffer(buffer,0,new Uint8Array([1,2,3,4]));await device.queue.onSubmittedWorkDone();
    const error=await device.popErrorScope();assert.equal(error,null);
  } finally {buffer.destroy();}
}

async function fresh(backend='wasm',gpuDevice=device,document=manifest) {
  const shell = await createShell(document,await providers(gpuDevice));
  shell.addRecord('alpha',BASE);
  shell.addRecord('beta',{...BASE,stock:77});
  shell.selectEntity('alpha');
  shell.selectBackend(backend);
  return shell;
}

function unchanged(before,after) {
  assert.equal(after.id,before.id);
  assert.equal(after.generation,before.generation);
  assert.equal(after.revision,before.revision,'discard/refusal must not advance record state');
  assert.deepEqual(after.values,before.values);
  assert.deepEqual(after.bytes,before.bytes);
}

function committed(before,after,receipt,expected) {
  assert.equal(receipt.status,'committed');assert.equal(receipt.committed,true);
  assert.deepEqual(Object.keys(receipt.outputs),['new_stock']);
  assert.equal(receipt.outputs.new_stock,expected);
  assert.equal(after.values.stock,expected);
  assert.equal(after.values.sentinel,23130);
  assert.equal(after.revision,before.revision+1);
  assert.equal(after.generation,before.generation);
  for (const key of Object.keys(before.values)) if (key!=='stock')
    assert.equal(after.values[key],before.values[key],`unrelated field ${key} changed`);
  const outputCell = manifest.plan.outputs.new_stock;
  const {offset,size} = manifest.layout.cells[outputCell];
  assert.equal(size,2);
  assert.equal(new DataView(after.bytes.buffer,after.bytes.byteOffset,after.bytes.byteLength).getInt16(offset,true),expected);
  for (let i=0;i<before.bytes.length;i++) if (i<offset || i>=offset+size)
    assert.equal(after.bytes[i],before.bytes[i],`unrelated arena byte ${i} changed`);
}

function discarded(receipt) {
  assert.equal(receipt.status,'discarded');assert.equal(receipt.committed,false);
  assert.deepEqual(receipt.outputs,{});
}

async function test(name,backend,body) {
  const shell = await fresh(backend);
  try {await body(shell);checks.push({name,backend,status:'passed'});}
  finally {await shell.dispose();}
}

async function backendChecks(backend) {
  await test('owned snapshots and output-only commit',backend,async shell=>{
    const before = shell.snapshot();
    const exposed = shell.snapshot();
    Reflect.set(exposed.values,'stock',32000);exposed.bytes.fill(0);
    unchanged(before,shell.snapshot());
    const operation = shell.start();assert(Object.isFrozen(operation));
    assert.equal((await operation.ready).status,'complete');
    unchanged(before,shell.snapshot()); // readiness itself must never commit
    const receipt = await shell.finish(operation.id);
    committed(before,shell.snapshot(),receipt,11);
    await assert.rejects(()=>shell.finish(operation.id));
    await assert.rejects(()=>shell.finish('never-issued-here'));
  });

  await test('independent signed-word and signed-byte answer',backend,async shell=>{
    shell.editRecord('alpha',{stock:32767,produced:32767,population:-128,supported:-32768,support_cost:2});
    const before = shell.snapshot();
    const receipt = await shell.step();
    committed(before,shell.snapshot(),receipt,254);
  });

  await test('same-value edit invalidates a staged result',backend,async shell=>{
    const op = shell.start();await op.ready;
    const beforeEdit = shell.snapshot();shell.editRecord('alpha',{stock:10});
    const edited = shell.snapshot();assert.equal(edited.revision,beforeEdit.revision+1);
    discarded(await shell.finish(op.id));unchanged(edited,shell.snapshot());
  });

  await test('state ABA invalidates a staged result',backend,async shell=>{
    const op = shell.start();await op.ready;
    shell.editRecord('alpha',{stock:20});shell.editRecord('alpha',{stock:10});
    const before = shell.snapshot();discarded(await shell.finish(op.id));unchanged(before,shell.snapshot());
  });

  await test('entity selection ABA invalidates a staged result',backend,async shell=>{
    const op = shell.start();await op.ready;
    const beforeA=shell.snapshot('alpha'),beforeB=shell.snapshot('beta');
    shell.selectEntity('beta');shell.selectEntity('alpha');
    discarded(await shell.finish(op.id));
    unchanged(beforeA,shell.snapshot('alpha'));unchanged(beforeB,shell.snapshot('beta'));
  });

  await test('removed and recreated entity has a new generation',backend,async shell=>{
    const op=shell.start();await op.ready;const previous=shell.snapshot();
    shell.removeRecord('alpha');shell.addRecord('alpha',BASE);shell.selectEntity('alpha');
    const replacement=shell.snapshot();assert.notEqual(replacement.generation,previous.generation);
    discarded(await shell.finish(op.id));unchanged(replacement,shell.snapshot());
  });

  await test('reselecting a backend invalidates a staged result',backend,async shell=>{
    const op=shell.start();await op.ready;const before=shell.snapshot();
    shell.selectBackend(backend);discarded(await shell.finish(op.id));unchanged(before,shell.snapshot());
  });

  await test('superseded completion cannot clear a newer operation',backend,async shell=>{
    const old=shell.start();await old.ready;const current=shell.start();
    const before=shell.snapshot();discarded(await shell.finish(old.id));unchanged(before,shell.snapshot());
    const receipt=await shell.finish(current.id);
    committed(before,shell.snapshot(),receipt,11);
  });

  await test('reverse completion order commits the latest request once',backend,async shell=>{
    const old=shell.start();await old.ready;const current=shell.start();await current.ready;
    const before=shell.snapshot();const receipt=await shell.finish(current.id);
    committed(before,shell.snapshot(),receipt,11);
    const after=shell.snapshot();discarded(await shell.finish(old.id));unchanged(after,shell.snapshot());
  });

  await test('overlapping starts retain the device lease and commit only the latest request',backend,async shell=>{
    const before=shell.snapshot(),old=shell.start(),current=shell.start();
    const receipt=await shell.finish(current.id);
    committed(before,shell.snapshot(),receipt,11);
    const after=shell.snapshot();discarded(await shell.finish(old.id));unchanged(after,shell.snapshot());
  });

  await test('cancel and immediate replacement retain the physical compute lease',backend,async shell=>{
    const before=shell.snapshot(),old=shell.start();shell.cancel(old.id);
    const current=shell.start(),receipt=await shell.finish(current.id);
    committed(before,shell.snapshot(),receipt,11);
    const after=shell.snapshot();discarded(await shell.finish(old.id));unchanged(after,shell.snapshot());
  });

  await test('concurrent finish calls cannot consume one result twice',backend,async shell=>{
    const op=shell.start();await op.ready;const before=shell.snapshot();
    const finished=await Promise.allSettled([shell.finish(op.id),shell.finish(op.id)]);
    const fulfilled=finished.filter(x=>x.status==='fulfilled'),rejected=finished.filter(x=>x.status==='rejected');
    assert.equal(fulfilled.length,1);assert.equal(rejected.length,1);
    committed(before,shell.snapshot(),fulfilled[0].value,11);
  });

  await test('cancellation invalidates before physical completion',backend,async shell=>{
    const before=shell.snapshot(),op=shell.start();shell.cancel(op.id);await op.ready;
    discarded(await shell.finish(op.id));unchanged(before,shell.snapshot());
  });

  await test('typed edit validates the whole transaction',backend,async shell=>{
    const before=shell.snapshot();
    assert.throws(()=>shell.editRecord('alpha',{stock:20,population:128}));
    unchanged(before,shell.snapshot());
    assert.throws(()=>shell.editRecord('alpha',{stock:NaN}));
    assert.throws(()=>shell.editRecord('alpha',{sentinel:-1}));
    unchanged(before,shell.snapshot());
  });

  await test('domain refusal never commits partial state',backend,async shell=>{
    shell.editRecord('alpha',{support_cost:3});const before=shell.snapshot();
    const receipt=await shell.step();assert.equal(receipt.status,'refused');assert.equal(receipt.committed,false);
    assert.deepEqual(receipt.outputs,{});unchanged(before,shell.snapshot());
  });

  await test('disposal invalidates synchronously and drains computation',backend,async shell=>{
    const before=shell.snapshot(),op=shell.start();
    const disposing=shell.dispose();
    assert.throws(()=>shell.editRecord('alpha',{stock:999}));assert.throws(()=>shell.start());
    const receipt=await shell.finish(op.id);discarded(receipt);
    await disposing;
    assert.equal(before.values.stock,10);assert.equal(before.values.sentinel,23130);
    await assert.rejects(()=>shell.finish(op.id));
  });
}

try {
  await backendChecks('wasm');
  {
    const registry=await providers(null),document=structuredClone(manifest);
    const shell=await createShell(document,registry);
    try {
      shell.addRecord('alpha',{stock:10});shell.selectEntity('alpha');
      assert.deepEqual(shell.snapshot().values,BASE,'unspecified cells must use declared initial state');
      assert.throws(()=>shell.selectBackend('webgpu'),'missing GPU cannot silently fall back');
      document.plan.inputs.stock='sentinel';document.plan.outputs.new_stock='sentinel';
      const before=shell.snapshot(),receipt=await shell.step();
      committed(before,shell.snapshot(),receipt,11);
      await assert.rejects(()=>createShell(manifest,registry),'provider ownership must not be shared across shells');
      checks.push({name:'manifest ownership, defaults, missing GPU and exclusive provider ownership',backend:'wasm',status:'passed'});
    } finally {await shell.dispose();}
  }

  if (device) {
    await backendChecks('webgpu');
    await test('backend ABA invalidates even after returning to the original provider','wasm',async shell=>{
      const op=shell.start();await op.ready;const before=shell.snapshot();
      shell.selectBackend('webgpu');shell.selectBackend('wasm');
      discarded(await shell.finish(op.id));unchanged(before,shell.snapshot());
    });
    await test('Wasm and GPU alternate through one persistent stock arena','wasm',async shell=>{
      for(let index=0;index<12;index++) {
        shell.selectBackend(index%2 ? 'webgpu':'wasm');
        const before=shell.snapshot();assert.equal(before.values.stock,10+index);
        const receipt=await shell.step();committed(before,shell.snapshot(),receipt,11+index);
      }
    });
    {
      const first=await fresh('webgpu'),second=await fresh('webgpu');
      try {
        second.editRecord('alpha',{stock:100});
        const beforeFirst=first.snapshot(),beforeSecond=second.snapshot();
        const a=first.start(),b=second.start();
        assert.notEqual(a.id,b.id,'operation identities must include their owning shell session');
        const [ra,rb]=await Promise.all([first.finish(a.id),second.finish(b.id)]);
        committed(beforeFirst,first.snapshot(),ra,11);
        committed(beforeSecond,second.snapshot(),rb,101);
        checks.push({name:'independent shells share a borrowed GPU device without state or token contamination',backend:'webgpu',status:'passed'});
      } finally {await Promise.all([first.dispose(),second.dispose()]);}
    }
    // All wrappers above borrowed this physical device; disposal must leave it usable.
    await deviceUsable(device);
    checks.push({name:'borrowed GPU device remains usable after shell disposal',backend:'webgpu',status:'passed'});

    for(const ownsDevice of [true,false]) {
      const loadDevice=await additionalDevice();
      try {
        await missingGPUResource(async base=>{
          await assert.rejects(()=>loadShell(base,{device:loadDevice,ownsDevice}));
          if(ownsDevice) {
            const loss=await deadline(loadDevice.lost,'Transferred device leaked after GPU source fetch failure');
            assert.equal(loss.reason,'destroyed');
          } else await deviceUsable(loadDevice);
        });
        checks.push({name:ownsDevice ? 'loader failure destroys a transferred device before GPU provider assignment'
          : 'loader failure preserves a borrowed device before GPU provider assignment',backend:'webgpu',status:'passed'});
      } finally {loadDevice.destroy();}
    }

    const ownedDevice=await additionalDevice();
    let ownedShell;
    try {
      const registry={
        wasm:await createWasmProvider(bundles.wasm.build,bundles.wasm.data),
        webgpu:await createGPUProvider(bundles.webgpu.build,bundles.webgpu.data.toString('utf8'),
          {device:ownedDevice,ownsDevice:true})};
      ownedShell=await createShell(manifest,registry);
      ownedShell.addRecord('alpha',BASE);ownedShell.selectEntity('alpha');ownedShell.selectBackend('webgpu');
      const op=ownedShell.start();assert.equal((await op.ready).status,'complete');
      const disposal=ownedShell.dispose();
      const loss=await deadline(ownedDevice.lost,'Owned device did not close on shell disposal');
      assert.equal(loss.reason,'destroyed');await disposal;
      checks.push({name:'owned GPU device is destroyed and drained on shell disposal',backend:'webgpu',status:'passed'});
    } finally {await ownedShell?.dispose();ownedDevice.destroy();}

    const lostDevice=await additionalDevice();
    const shell=await fresh('webgpu',lostDevice);
    try {
      const op=shell.start();assert.equal((await op.ready).status,'complete');
      const before=shell.snapshot();lostDevice.destroy();await lostDevice.lost;
      discarded(await shell.finish(op.id));unchanged(before,shell.snapshot());
      let refused=null,unavailable=null;
      try {refused=await shell.step();} catch(error) {unavailable=error;}
      if(!unavailable) {assert.equal(refused.committed,false);assert.notEqual(refused.status,'committed');}
      unchanged(before,shell.snapshot());
      shell.selectBackend('wasm');const recovered=await shell.step();
      committed(before,shell.snapshot(),recovered,11);
      checks.push({name:'device loss discards staged GPU output; explicit Wasm switch remains usable',backend:'webgpu',status:'passed'});
    } finally {await shell.dispose();lostDevice.destroy();}
  }
  result.status='passed';result.check_count=checks.length;
  result.wasm_cases=checks.filter(check=>check.backend==='wasm').length;
  result.gpu_cases=checks.filter(check=>check.backend==='webgpu').length;
  console.log(JSON.stringify(result));
} finally {device?.destroy();gpu=null;}
