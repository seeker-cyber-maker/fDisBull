// Typed batch adapters only: no game formula, provider fallback or state commit.
const wasmABIs = new WeakMap();
const gpuInFlight = new WeakSet();
const CANARY = 0x5a5a5a5a;

function checkABI(abi) {
  if (abi?.format !== 'fdisbull-web-scalar-abi-1' ||
      !Number.isInteger(abi.row_limit) || abi.row_limit < 1 || abi.row_limit > 8192)
    throw Error('Unsupported scalar ABI');
  for (const ports of [abi.inputs, abi.outputs]) {
    if (!Array.isArray(ports) || !ports.length || ports.length > 64 ||
        Array.from(ports).some(p => typeof p !== 'string') || new Set(ports).size !== ports.length)
      throw Error('Invalid scalar ports');
  }
}

function snapshot(abi, rows) {
  checkABI(abi);
  if (!Array.isArray(rows) || rows.length > abi.row_limit) throw Error('Batch row limit');
  return Array.from(rows, row => {
    if (!Array.isArray(row) || row.length !== abi.inputs.length ||
        Array.from(row).some(x => !Number.isInteger(x) || x < -2147483648 || x > 2147483647))
      throw Error('Expected one signed i32 carrier per input port');
    return [...row];
  });
}

async function verifySource(build, target, name, bytes) {
  checkABI(build?.abi);
  if (build.format !== 'fdisbull-web-block-1' || build.target !== target)
    throw Error('Wrong build profile');
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
  const hash = Array.from(digest, x => x.toString(16).padStart(2, '0')).join('');
  if (hash !== build.artifacts?.[name]) throw Error('Artifact hash mismatch');
}

export async function instantiateWasm(bytes, build) {
  // Own the byte snapshot across asynchronous verification/compilation.
  if (ArrayBuffer.isView(bytes))
    bytes = new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength).slice();
  else if (bytes instanceof ArrayBuffer) bytes = new Uint8Array(bytes.slice(0));
  else throw Error('Expected an ArrayBuffer or byte view');
  const abi = structuredClone(build.abi);
  const pinned = structuredClone(build);
  await verifySource(pinned, 'wasm32-scalar-1', 'block.wasm', bytes);
  const {instance, module} = await WebAssembly.instantiate(bytes, {});
  const exports = WebAssembly.Module.exports(module);
  if (WebAssembly.Module.imports(module).length || exports.length !== 1 ||
      exports[0].kind !== 'function' || exports[0].name !== 'block' ||
      instance.exports.block.length !== abi.inputs.length)
    throw Error('Unexpected Wasm interface');
  wasmABIs.set(instance, JSON.stringify(abi));
  return instance;
}

export function runWASM(instance, abi, rows) {
  if (wasmABIs.get(instance) !== JSON.stringify(abi)) throw Error('Unbound Wasm ABI');
  rows = snapshot(abi, rows);
  return rows.map(row => {
    const values = instance.exports.block(...row);
    if (!Array.isArray(values) || values.length !== 1 + abi.outputs.length ||
        values.some(x => !Number.isInteger(x)) || (values[0] !== 0 && values[0] !== 1))
      throw Error('Invalid Wasm result frame');
    return {status: values[0], data: values[0] === 0 ? values.slice(1) : []};
  });
}

export async function runGPU(device, code, build, rows) {
  const pinned = structuredClone(build);
  const abi = pinned.abi;
  rows = snapshot(abi, rows);
  if (typeof code !== 'string') throw Error('Expected WGSL source text');
  await verifySource(pinned, 'webgpu-wgsl-scalar-1', 'block.wgsl', new TextEncoder().encode(code));
  if (!rows.length) return [];
  if (gpuInFlight.has(device)) throw Error('One in-flight batch per GPU device');
  gpuInFlight.add(device);
  const buffers = [];
  let scoped = false, popped = false;
  try {
    const width = abi.inputs.length, stride = 1 + abi.outputs.length, count = rows.length;
    const inputs = new Uint8Array(count * width * 4);
    const inputView = new DataView(inputs.buffer);
    rows.flat().forEach((value, index) => inputView.setInt32(index * 4, value, true));
    const seed = new Int32Array((count + 2) * stride).fill(CANARY);
    if (Math.max(inputs.byteLength, seed.byteLength) > device.limits.maxStorageBufferBindingSize ||
        Math.max(inputs.byteLength, seed.byteLength) > device.limits.maxBufferSize ||
        Math.ceil(count / 64) > device.limits.maxComputeWorkgroupsPerDimension)
      throw Error('Batch exceeds GPU limits');
    device.pushErrorScope('validation'); scoped = true;
    const shader = device.createShaderModule({code});
    const compilation = await shader.getCompilationInfo();
    const errors = compilation.messages.filter(m => m.type === 'error');
    if (errors.length) throw Error(errors.map(m => m.message).join('\n'));
    const pipeline = await device.createComputePipelineAsync({layout: 'auto', compute: {module: shader, entryPoint: 'main'}});
    const create = descriptor => {const b = device.createBuffer(descriptor); buffers.push(b); return b;};
    const ib = create({size: inputs.byteLength, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST});
    const ob = create({size: seed.byteLength, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC | GPUBufferUsage.COPY_DST});
    const rb = create({size: seed.byteLength, usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST});
    device.queue.writeBuffer(ib, 0, inputs); device.queue.writeBuffer(ob, 0, seed);
    const bindings = device.createBindGroup({layout: pipeline.getBindGroupLayout(0), entries: [
      {binding: 0, resource: {buffer: ib}}, {binding: 1, resource: {buffer: ob}}]});
    const encoder = device.createCommandEncoder();
    const pass = encoder.beginComputePass();
    pass.setPipeline(pipeline); pass.setBindGroup(0, bindings);
    pass.dispatchWorkgroups(Math.ceil(count / 64)); pass.end();
    encoder.copyBufferToBuffer(ob, 0, rb, 0, seed.byteLength);
    device.queue.submit([encoder.finish()]);
    await rb.mapAsync(GPUMapMode.READ);
    const readback = new DataView(rb.getMappedRange().slice(0)); rb.unmap();
    const result = Array.from({length: readback.byteLength / 4}, (_, i) => readback.getInt32(i * 4, true));
    const validation = await device.popErrorScope(); popped = true;
    if (validation) throw Error(validation.message);
    if (!result.slice(count * stride).every(x => x === CANARY))
      throw Error('Inactive invocation modified canary');
    return rows.map((row, i) => {
      const status = result[i * stride];
      const data = Array.from(result.slice(i * stride + 1, (i + 1) * stride));
      if (status !== 0 && status !== 1) throw Error('Invalid GPU result status');
      if (status === 1 && !data.every(x => x === CANARY)) throw Error('Refusal committed output');
      return {status, data: status === 0 ? data : []};
    });
  } finally {
    if (scoped && !popped) {try {await device.popErrorScope();} catch { /* Preserve original failure. */ }}
    for (const buffer of buffers) buffer.destroy();
    gpuInFlight.delete(device);
  }
}
