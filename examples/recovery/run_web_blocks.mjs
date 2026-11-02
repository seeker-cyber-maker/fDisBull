// Finite execution: Node's Wasm VM, independent WABT assembly, real Dawn GPU.
// Arguments: private prepared study directory, private npm dependency root.
import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import assert from 'node:assert/strict';

const root = path.resolve(process.argv[2]);
const require = createRequire(path.join(path.resolve(process.argv[3]), 'package.json'));
const {create, globals} = await import(pathToFileURL(require.resolve('webgpu')));
const wabtFactory = (await import(pathToFileURL(require.resolve('wabt')))).default;
Object.assign(globalThis, globals);
const sha = data => crypto.createHash('sha256').update(data).digest('hex');
const manifest = JSON.parse(await fs.readFile(path.join(root, 'cases.json')));
const wasmTarget = 'wasm32-scalar-1', gpuTarget = 'webgpu-wgsl-scalar-1';
let gpu = create([`backend=${process.env.FDISBULL_GPU_BACKEND || 'metal'}`]);
const adapter = await gpu.requestAdapter();
if (!adapter || adapter.info.isFallbackAdapter !== false) throw Error('Real non-fallback GPU adapter required');
const device = await adapter.requestDevice();
const wabt = await wabtFactory();
const result = {format:'fdisbull-web-execution-2',status:'running',runtime:process.version,
  module_uil_sha256:manifest.module_uil_sha256,
  adapter:{vendor:adapter.info.vendor,architecture:adapter.info.architecture,
           device:adapter.info.device,isFallbackAdapter:adapter.info.isFallbackAdapter},
  suites:[],scope:'same host CPU/GPU; no cross-platform or performance claim'};
const observations = {};
try {
  for (const suite of manifest.suites) {
    const wdir = path.join(root, suite.builds[wasmTarget].directory);
    const gdir = path.join(root, suite.builds[gpuTarget].directory);
    const wb = JSON.parse(await fs.readFile(path.join(wdir,'build.json')));
    const gb = JSON.parse(await fs.readFile(path.join(gdir,'build.json')));
    const {instantiateWasm,runWASM,runGPU} = await import(pathToFileURL(path.join(wdir,'host.mjs')));
    const rows = suite.vectors.map(v=>v.input);
    const bytes = await fs.readFile(path.join(wdir,'block.wasm'));
    const wgsl = await fs.readFile(path.join(gdir,'block.wgsl'),'utf8');
    const instance = await instantiateWasm(bytes,wb);
    const cpu = runWASM(instance,wb.abi,rows);
    if (suite.name==='food') {
      await assert.rejects(()=>runGPU(device,wgsl+'\n// altered',gb,rows),/hash mismatch/);
      await assert.rejects(()=>runGPU(device,wgsl,gb,[[1]]),/carrier/);
      const broken = structuredClone(gb), invalidSource = 'not valid WGSL';
      broken.artifacts['block.wgsl']=sha(invalidSource);
      await assert.rejects(()=>runGPU(device,invalidSource,broken,rows));
      result.host_error_checks = ['shader hash','row arity','shader compilation failure followed by recovery'];
    }
    const saved = rows[0][0];
    const pending = runGPU(device,wgsl,gb,rows);
    rows[0][0] = saved === 0 ? 1 : 0;
    let hardware;
    try {hardware=await pending;} finally {rows[0][0]=saved;}
    const wat = await fs.readFile(path.join(wdir,'block.wat'),'utf8');
    const parsed = wabt.parseWat('block.wat',wat,{multi_value:true});
    let assembled;
    try {parsed.validate(); assembled=parsed.toBinary({write_debug_names:false}).buffer;}
    finally {parsed.destroy();}
    const rebuilt = await WebAssembly.instantiate(assembled,{});
    const independent = rows.map(row=>{
      const v=rebuilt.instance.exports.block(...row);return {status:v[0],data:v[0]===0?v.slice(1):[]};
    });
    if (JSON.stringify(independent)!==JSON.stringify(cpu)) throw Error('Independent assembly differs');
    observations[suite.name] = {[wasmTarget]:cpu,[gpuTarget]:hardware};
    const summary = {};
    for (const [target,actual] of [[wasmTarget,cpu],[gpuTarget,hardware]]) {
      const indices = actual.flatMap((a,i)=>JSON.stringify(a)===JSON.stringify(suite.vectors[i].expected)?[]:[i]);
      if (suite.negative_control ? indices.length===0 : indices.length!==0)
        throw Error(`${suite.name}/${target}: ${indices.length} mismatches`);
      summary[target] = {cases:actual.length,refusals:actual.filter(a=>a.status===1).length,
        mismatches:indices.length,outputs_sha256:sha(JSON.stringify(actual)),
        first_counterexample:indices.length?{index:indices[0],input:rows[indices[0]],
          expected:suite.vectors[indices[0]].expected,actual:actual[indices[0]]}:null};
    }
    result.suites.push({name:suite.name,negative_control:!!suite.negative_control,
      wasm_sha256:sha(bytes),wgsl_sha256:sha(wgsl),independent_wat_assembly:'matched',
      gpu_input_snapshot_mutation:'isolated',...summary});
  }
  result.status = 'passed';
  await fs.writeFile(path.join(root,'node-observations.json'),JSON.stringify(observations));
  await fs.writeFile(path.join(root,'node-result.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result));
} finally {device.destroy(); gpu=null;}
