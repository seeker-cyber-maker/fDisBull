# WebAssembly and WebGPU scalar UDC profiles

`build-web-block` resolves a persisted UDL selection and emits one qualified,
pure scalar invocation as WebAssembly or WGSL. Both targets consume the same
module UIL and contract. The selected implementation supplies the logic; no
game formula, executable address or DOS layout enters either backend or its
JavaScript adapter.

This is a bounded analysis scaffold. WebAssembly supplies a CPU function and
WebGPU an asynchronous compute provider. Game shells, rendering, files, audio,
browser UI and end-turn scheduling remain outside these profiles. Returned
values do not automatically commit application state.

## Build a persisted selection

Use a matching checkout/wheel and inspect `methods` before assuming a system
installation includes this new method. Register a pure `uil` layer against an
existing contract, then choose `wasm32-scalar-1` or `webgpu-wgsl-scalar-1`:

```python
from fdisbull.udc_layers import register_layer, select_layers
from fdisbull.udc_web import build_web_block

layer = register_layer(project, {
    "format": "fdisbull-udl-layer-1", "name": "portable.block",
    "contract": contract_id,
    "implementation": {"backend": "uil", "program": block_program}
})
choice = select_layers(project, "portable.cpu", {"food": layer["id"]},
    program=module_uil, target="wasm32-scalar-1")
receipt = build_web_block(project, choice["id"], private_new_directory)
```

Keep `program` unchanged when selecting the other target. The JSON method takes
`selection` and `destination` in the normal project request. It is build-only.
The output must be new and outside Git; existing/dangling output symlinks refuse.

Wasm output contains `block.wasm`, readable `block.wat`, `host.mjs` and
`build.json`. GPU output contains `block.wgsl` with the same adapter/receipt
names. The Python Wasm encoder needs no external assembler. Hosts validate the
binary; the study independently assembles WAT with WABT and compares outputs.
Receipts bind selection/layer/contract/program identities, model qualification,
ABI and artifact hashes. Emission records `execution:false` and
`source_to_uil:false`; model qualification does not establish original fidelity.

## ABI and semantics

- One canonical invocation with sorted ports: 1..64 inputs/outputs and at most
  256 variables. Logical `bool`, i8/u8 and i16/u16 use signed i32 carriers.
- Input types and both contract/layer domains are guarded in emitted code.
  Signed population bytes arrive as -128..127, not unsigned 0..255 encodings.
- Pure `set/add/subtract/if/require`, equality, bit tests 0..31, not/and.
  Arithmetic wraps at the destination width; narrowing assignments refuse.
- Status 0 returns declared outputs; status 1 commits none. Late preconditions
  cannot expose partial local updates. Wasm has no imports or memory.
- Resources, additional physical adapters, return/notification bindings, wider
  types and other effects refuse. Flags, timing and callbacks are unqualified.

`instantiateWasm(bytes, build)` verifies bytes and interface;
`runWASM(instance, build.abi, rows)` runs that bound instance.
`runGPU(device, source, build, rows)` verifies the WGSL hash, owns an input
snapshot, dispatches compute and awaits/validates mapped readback. Full rows
are checked before execution, including sparse arrays, arity and i32 range.
The batch limit is 8,192; GPU device limits are checked separately.

GPU storage uses explicit little-endian i32 serialization. Owned buffers and
validation scopes are cleaned up after success/failure. One in-flight request
per device prevents error-scope interleaving. Refusals retain seeded output
words; inactive invocations retain canaries. No provider fallback or application
commit occurs. A future scene shell must validate state/selection revision
before applying delayed results.

## Original-backed CivD result

The UIL remains
`332f84e5067fa7aee5405a001ac68efb991fd644bcf34cd62a232f453df057ed`,
the exact definition from [the DOS/ARM64 study](CIVD_SHARED_FOOD_AND_Z.md).
The signed-word update, signed-byte population and cost domain 1..2 are retained.

Original → UIL was rerun against CivD 474.01, 474.03 and 474.05: **6,054 guarded
original CPU executions and 6,054 fresh DOSBox executions** of unchanged original
instruction blocks. DOSBox uses an authored MASM/LINK harness with explicit
data/stack adapters, rather than an ordinary game turn. Results also match all
three independently retained original DOSBox output sets.

| Suite | Cases per backend per host | Result |
| --- | ---: | --- |
| Original-backed food | 2,018 | Zero mismatches |
| Food admission guards | 6 | Refused |
| Late precondition/bool guards | 19 | Correct completion/refusal |
| Narrowing assignments | 9 | Correct completion/refusal |
| Branches, signed bits, word wrap | 15 | Zero mismatches |
| Deliberately corrupted lowering | 2,024 | 1,765 mismatches detected |

Node runs Wasm and Dawn WebGPU on Apple M1 Max / Metal with no fallback adapter.
Chrome 156 runs the identical Wasm/WGSL artifacts through browser APIs, reporting
Apple / Metal with no fallback. Its isolated headless run explicitly enables
WebGPU; flags remain in the receipt. Browser/Node arrays match exactly. This is
two hosts on one Mac, not an OS/browser/driver matrix or an acceleration claim.

Both new food outputs pass **12,108 host-layout decode/commit round trips**
across the three editions. These checks run in Python, preserve all non-output
bytes and reuse the existing city-index/frame adapters. Original executables
and retained code hashes are unchanged. Generated code was not spliced into a
graphical game; callers, flags, timing and full city/turn behavior remain open.
The [sanitized receipt](evidence/civd-food-web/verification.json) contains hashes,
aggregate results and build metadata. Inputs/FDBs/tools/harnesses/outputs stay
in the private workspace.

## Reproduce and verify

Use matching source plus `test,source,udc` dependencies, the prior verified
food-swap study, original build root, pinned period tools and compatible DOSBox.
Choose a new output outside Git:

```sh
PYTHONPATH=src:. python examples/recovery/civd_food_web.py prepare \
  "$PREVIOUS_FOOD_STUDY" "$VERIFIED_BUILD_ROOT" "$NEW_OUTPUT" \
  "$PERIOD_TOOL_ROOT" "$DOSBOX"
npm install --prefix "$PRIVATE_NPM_ROOT" wabt@1.0.39 webgpu@0.6.2
node examples/recovery/run_web_blocks.mjs "$NEW_OUTPUT" "$PRIVATE_NPM_ROOT"
node examples/recovery/run_web_browser.mjs "$NEW_OUTPUT" "$CHROME_EXECUTABLE"
PYTHONPATH=src:. python examples/recovery/civd_food_web.py verify "$NEW_OUTPUT"
```

The browser runner serves an exact artifact allowlist on ephemeral loopback,
uses a new Chrome profile and stops its own process/server. It never serves an
executable, FDB or oracle harness. The Node recipe defaults to Metal; another
host must select/qualify its backend explicitly. Fallback adapters cannot pass.

Ordinary tests execute Node Wasm; CI prepares Node 22. Real GPU tests require
`FDISBULL_WEBGPU_MODULE_ROOT` pointing to the private npm directory. Once supplied,
missing/fallback hardware fails instead of skipping. Without the dependency
root, that GPU test reports an explicit skip. Hardware evidence and ordinary/
required-native Linux CI are separate gates.

## Frictions and next shell boundary

The external prototype needed an assembler, and target names alone granted no
executable capability. The built-in method now resolves actual selected layers,
enforces a profile and emits Wasm without npm. WABT is an independent check.
The public qualifier rejects a wrong selected model; a separate corrupted
lowering tests sensitivity of the execution comparison.

i32 carriers alone lost byte/word meaning, so widening, wrapping, narrowing
refusal and domains are explicit. JavaScript's missing/sparse-value conversion
could hide malformed calls, so whole rows validate first. Real shader failure
followed by successful dispatch tests scope/buffer cleanup. Input mutation while
dispatch is pending tests snapshot ownership.

macOS GNU ELF fixtures reproduce on the unchanged parent: two failed compiler
probes and 23 setup errors. They remain separate from this backend and Linux CI.
The next shell step needs services, orchestration, memory/state ownership and
interruption/revision rules. This tiny food kernel is a fidelity fixture, not
evidence of a useful GPU speedup.

Primary contracts: [Wasm](https://webassembly.github.io/spec/core/syntax/instructions.html),
[WGSL](https://www.w3.org/TR/WGSL/), [WebGPU](https://www.w3.org/TR/webgpu/),
[Chrome headless](https://developer.chrome.com/docs/automation-and-testing/headless).
