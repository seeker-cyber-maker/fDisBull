import fs from 'node:fs/promises';
import assert from 'node:assert/strict';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import {createWasmMemoryProvider, createGPUMemoryProvider} from './memory.mjs';

const kind = process.argv[2], cases = JSON.parse(await fs.readFile('cases.json', 'utf8'));
let gpu = null, device = null, invocations = 0;
if (kind === 'gpu') {
  const require = createRequire(path.join(process.env.FDISBULL_WEBGPU_MODULE_ROOT, 'package.json'));
  const {create, globals} = await import(pathToFileURL(require.resolve('webgpu')));
  Object.assign(globalThis, globals);
  gpu = create(['backend=' + (process.env.FDISBULL_GPU_BACKEND || 'metal')]);
  const adapter = await gpu.requestAdapter();
  assert.equal(adapter.info.isFallbackAdapter, false);
  device = await adapter.requestDevice();
}
try {
  for (const [name, test] of Object.entries(cases)) {
    const base = `${name}/${kind}`, build = JSON.parse(await fs.readFile(`${base}/build.json`, 'utf8'));
    const provider = kind === 'wasm'
      ? await createWasmMemoryProvider(build, await fs.readFile(`${base}/block.wasm`))
      : await createGPUMemoryProvider(build, await fs.readFile(`${base}/block.wgsl`, 'utf8'), {device});
    assert.equal(provider.describe().abi.report_steps, build.abi.report_steps);
    const description = provider.describe(); description.abi.report_steps = false;
    if (description.abi.capture_locals) description.abi.capture_locals.length = 0;
    assert.deepEqual(provider.describe().abi.capture_locals, build.abi.capture_locals);
    try {
      // Reuse verifies the remaining counter is initialized for each invocation.
      for (let i = 0; i < 2; i++) {
        const input = test.input.slice(), work = provider.invoke(input);
        input.fill(12345);
        const result = await work;
        assert.deepEqual({...result, words: Array.from(result.words)}, test.expected, name);
        assert.equal(result.words.length, 8);
        result.words.fill(55);
        if (result.locals) result.locals.$i = 0x12345678;
        invocations++;
      }
    } finally { await provider.dispose(); }
  }
} finally { device?.destroy(); gpu = null; }
console.log(JSON.stringify({backend: kind, invocations}));
