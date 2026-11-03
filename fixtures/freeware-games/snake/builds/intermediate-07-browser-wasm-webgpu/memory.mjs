// Generic owned-arena Wasm/WebGPU providers. No game rules or application commits.
const queues = new WeakMap();
const CANARY = 0x6b6b6b6b;
const fail = message => { throw Error(message); };
const check = (ok, message) => { if (!ok) fail(message); };

function enqueue(device, operation) {
  const prior = queues.get(device) || Promise.resolve();
  const work = prior.catch(() => {}).then(operation);
  const tail = work.catch(() => {});
  queues.set(device, tail);
  tail.finally(() => { if (queues.get(device) === tail) queues.delete(device); });
  return work;
}

function arena(words, count) {
  // Validate before narrowing. Uint32Array.from([-1]) would conceal invalid input.
  check(Array.isArray(words) || ArrayBuffer.isView(words), 'Expected a word arena');
  check(words.length === count, 'Wrong word arena length');
  const copy = new Uint32Array(count);
  for (let i = 0; i < count; i++) {
    const value = words[i];
    check(Number.isInteger(value) && value >= 0 && value <= 0xffffffff, 'Invalid unsigned word');
    copy[i] = value;
  }
  return copy;
}

function snapshotBytes(bytes) {
  if (ArrayBuffer.isView(bytes)) return new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength).slice();
  if (bytes instanceof ArrayBuffer) return new Uint8Array(bytes.slice(0));
  fail('Expected byte buffer');
}

async function verify(build, target, name, bytes) {
  check(build?.format === 'fdisbull-web-memory-block-1' && build.target === target,
    'Wrong bounded-memory build profile');
  check(build.abi?.format === 'fdisbull-web-memory-abi-1' && build.abi.word === 'u32-le' &&
    Number.isInteger(build.abi.memory_words) && build.abi.memory_words >= 1 && build.abi.memory_words <= 131072 &&
    Number.isInteger(build.abi.max_steps) && build.abi.max_steps >= 1 && build.abi.max_steps <= 4000000 &&
    build.abi.status?.complete === 0 && build.abi.status?.refused === 1,
    'Invalid bounded-memory ABI');
  check(/^[0-9a-f]{64}$/.test(build.module_uil_sha256) &&
    typeof build.function === 'string' && /^[A-Za-z_][A-Za-z0-9_]*$/.test(build.function),
    'Unbound bounded-memory identity');
  const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
    value => value.toString(16).padStart(2, '0')).join('');
  check(hash === build.artifacts?.[name], 'Bounded-memory artifact hash differs');
}

export async function createWasmMemoryProvider(build, bytes) {
  const pinned = structuredClone(build);
  bytes = snapshotBytes(bytes);
  await verify(pinned, 'wasm32-memory-1', 'block.wasm', bytes);
  const {module, instance} = await WebAssembly.instantiate(bytes, {});
  const exports = WebAssembly.Module.exports(module);
  check(WebAssembly.Module.imports(module).length === 0 && exports.length === 2 &&
    exports.some(x => x.name === 'block' && x.kind === 'function') &&
    exports.some(x => x.name === 'memory' && x.kind === 'memory') && instance.exports.block.length === 0,
    'Unexpected bounded-memory Wasm interface');
  const count = pinned.abi.memory_words;
  const maximumBytes = Math.ceil(count * 4 / 65536) * 65536;
  check(instance.exports.memory.buffer.byteLength === maximumBytes, 'Unexpected Wasm memory size');
  let closed = false, epoch = 0;
  let tail = Promise.resolve();
  return Object.freeze({
    describe: () => structuredClone(pinned),
    get epoch() { return epoch; }, get closed() { return closed; }, get lost() { return false; },
    invoke(words) {
      // Snapshot before any await, including time spent waiting for the instance.
      const input = arena(words, count);
      if (closed) return Promise.reject(Error('Wasm provider closed'));
      const job = tail.catch(() => {}).then(() => {
        check(!closed, 'Wasm provider closed');
        const view = new DataView(instance.exports.memory.buffer);
        for (let i = 0; i < count; i++) view.setUint32(i * 4, input[i], true);
        let status;
        try { status = instance.exports.block(); }
        catch (error) {
          if (!(error instanceof WebAssembly.RuntimeError)) throw error;
          return {status: 'refused', words: input.slice()};
        }
        check(status === 0 || status === 1, 'Invalid Wasm completion status');
        if (status === 1) return {status: 'refused', words: input.slice()};
        const result = new Uint32Array(count);
        for (let i = 0; i < count; i++) result[i] = view.getUint32(i * 4, true);
        return {status: 'complete', words: result};
      });
      tail = job.catch(() => {});
      return job;
    },
    dispose() {
      if (!closed) { closed = true; epoch++; }
      return tail;
    },
  });
}

export async function createGPUMemoryProvider(build, source, {device, ownsDevice = false} = {}) {
  check(device && typeof ownsDevice === 'boolean', 'Explicit GPU device ownership required');
  const pinned = structuredClone(build);
  check(typeof source === 'string', 'Expected WGSL text');
  const state = {closed: false, lost: false, epoch: 0};
  const weak = new WeakRef(state);
  device.lost.then(() => { const live = weak.deref(); if (live) { live.lost = true; live.epoch++; } });
  let pipeline, tail = Promise.resolve(), destroyed = false;
  const count = pinned.abi?.memory_words;
  function active() { check(!state.closed && !state.lost, 'GPU provider closed or device lost'); }
  function destroyOwned() { if (ownsDevice && !destroyed) { destroyed = true; device.destroy(); } }
  try {
    await verify(pinned, 'webgpu-wgsl-memory-1', 'block.wgsl', new TextEncoder().encode(source));
    check(Math.max(count * 4, (count + 3) * 4) <= device.limits.maxStorageBufferBindingSize &&
      (count + 3) * 4 <= device.limits.maxBufferSize, 'Arena exceeds GPU storage limits');
    await enqueue(device, async () => {
      active(); device.pushErrorScope('validation');
      let popped = false;
      try {
        const shader = device.createShaderModule({code: source});
        const info = await shader.getCompilationInfo();
        const errors = info.messages.filter(m => m.type === 'error');
        check(!errors.length, errors.map(m => m.message).join('\n'));
        pipeline = await device.createComputePipelineAsync({layout: 'auto', compute: {module: shader, entryPoint: 'main'}});
        const validation = await device.popErrorScope(); popped = true;
        check(!validation, validation?.message); active();
      } finally { if (!popped) { try { await device.popErrorScope(); } catch {} } }
    });
  } catch (error) { destroyOwned(); throw error; }
  return Object.freeze({
    describe: () => structuredClone(pinned),
    get epoch() { return state.epoch; }, get closed() { return state.closed; }, get lost() { return state.lost; },
    invoke(words) {
      const input = arena(words, count);
      if (state.closed || state.lost) return Promise.reject(Error('GPU provider closed or device lost'));
      const job = enqueue(device, async () => {
        active();
        const buffers = [];
        let scoped = false, popped = false, submitted = false;
        const create = descriptor => { const buffer = device.createBuffer(descriptor); buffers.push(buffer); return buffer; };
        try {
          device.pushErrorScope('validation'); scoped = true;
          const ib = create({size: count * 4, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST});
          const ob = create({size: (count + 3) * 4, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC | GPUBufferUsage.COPY_DST});
          const rb = create({size: (count + 3) * 4, usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST});
          // Explicit LE encoding, independent of the host TypedArray byte order.
          const rawInput = new DataView(new ArrayBuffer(count * 4));
          for (let i = 0; i < count; i++) rawInput.setUint32(i * 4, input[i], true);
          const seed = new DataView(new ArrayBuffer((count + 3) * 4));
          for (let i = 0; i < count + 3; i++) seed.setUint32(i * 4, CANARY, true);
          device.queue.writeBuffer(ib, 0, rawInput.buffer); device.queue.writeBuffer(ob, 0, seed.buffer);
          const bindings = device.createBindGroup({layout: pipeline.getBindGroupLayout(0), entries: [
            {binding: 0, resource: {buffer: ib}}, {binding: 1, resource: {buffer: ob}}]});
          const encoder = device.createCommandEncoder();
          const pass = encoder.beginComputePass(); pass.setPipeline(pipeline); pass.setBindGroup(0, bindings);
          pass.dispatchWorkgroups(1); pass.end();
          encoder.copyBufferToBuffer(ob, 0, rb, 0, (count + 3) * 4);
          device.queue.submit([encoder.finish()]); submitted = true;
          await rb.mapAsync(GPUMapMode.READ);
          const data = new DataView(rb.getMappedRange().slice(0)); rb.unmap();
          const validation = await device.popErrorScope(); popped = true;
          check(!validation, validation?.message); active();
          check(data.getUint32((count + 1) * 4, true) === CANARY && data.getUint32((count + 2) * 4, true) === CANARY,
            'GPU memory canary modified');
          const status = data.getUint32(0, true);
          check(status === 0 || status === 1, 'Invalid GPU completion status');
          const output = new Uint32Array(count);
          for (let i = 0; i < count; i++) output[i] = data.getUint32((i + 1) * 4, true);
          if (status === 1) {
            check(output.every((v, i) => v === input[i]), 'GPU refusal changed the arena');
            return {status: 'refused', words: input.slice()};
          }
          return {status: 'complete', words: output};
        } finally {
          // A failed map/pop still retains physical resources until submitted work settles.
          if (submitted) { try { await device.queue.onSubmittedWorkDone(); } catch {} }
          if (scoped && !popped) { try { await device.popErrorScope(); } catch {} }
          for (const buffer of buffers) buffer.destroy();
        }
      });
      tail = job.catch(() => {});
      return job;
    },
    async dispose() {
      if (!state.closed) { state.closed = true; state.epoch++; }
      await tail; destroyOwned();
    },
  });
}
