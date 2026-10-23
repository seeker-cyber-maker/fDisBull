# Temporal code layers — 0.11.0

Code layers are immutable, version-bound experiment definitions with an ordered active stack in each live debugger session. They preserve original static bytes. Runtime captures and the event timeline record when a view changed, which definitions were active, and which bytes the CPU could fetch. This supports self-modifying code investigations and reversible theories without promoting runtime observations into static instruction facts.

Two layer kinds have different visibility:

| Kind | Guest data reads, including checksums | CPU instruction fetch | Disabling |
| --- | --- | --- | --- |
| `ram` | Composed patched RAM | Composed patched RAM, with execution overlays above it | Restore guarded original bytes |
| `execute` | Underlying RAM | Alternate bytes held in the emulator | Remove the fetch overlay; RAM stays intact |

RAM layers compose in their stack order, then execution layers compose above that physical view in their own stack order. The last layer covering a byte wins within its view. All definitions covering the same address must agree on the unpatched base bytes. An expected-byte mismatch rejects the transition. A complete stack switch preflights all RAM writes and execution guards on the emulation thread before changing either view; no guest instruction runs during the transition.

An execution overlay has **zero additional guest RAM or disk bytes**. It requires neither an INT3 patch nor a trampoline in guest RAM. It has host-side lookup/guard costs. Breakpoint actions currently pause and dispatch through the foreground Python owner, adding RPC latency. Redirected paths, virtual cave instructions, and changed branch outcomes can alter guest cycles and program state. This is not a zero-time or undetectability guarantee.

## Save definitions and switch views

Use the layers backend described in [the backend build instructions](../experimental/dosbox-x/layers/README.md). The 0.10.0 backend lacks the fetch overlay capability and is refused when activation is requested. Existing unlayered debugging remains available with that backend.

The following addresses and bytes illustrate the authored test fixture; obtain the actual expected bytes from your own live program:

```python
layer = project.debug_layer(
    "try a different immediate",
    kind="execute",
    patches=[{"address": "1000:0003",
              "expected_hex": "1111", "data_hex": "2222"}],
)
debug.layers([layer["layer"]])
debug.memory("1000:0003", length=2)          # physical RAM: 1111
debug.code("1000:0002", length=3)            # effective instruction: mov ax,2222h
debug.code("1000:0002", length=3, view="ram") # physical instruction bytes: B8 11 11
debug.layer_enable(layer["layer"], enabled=False)
```

`project.debug_layers()` lists definitions; `project.debug_layer_info(ID)` verifies and reads one. Definitions are immutable: save a new layer to revise a theory. `debug.layers()` inspects the active order; `debug.layers([ID_B, ID_A])` reorders it. `debug.layer_patch(name, address, expected_hex=..., data_hex=..., kind="ram"|"execute", activate=True)` is the create-and-enable convenience operation. Activation failure preserves the previous stack; the new immutable definition can still be inspected.

Definitions use project addresses in the selected MZ load context. The session translates them into runtime addresses. Patches must fit a mapped DOS allocation, cannot resize memory, and must translate to conventional RAM below `0xa0000`. Limits are 64 KiB per layer, 64 patches per definition, 256 saved definitions per static version, and 64 active layers with at most 256 patches and 64 KiB of touched bytes per transition.

Execution breakpoints keep their existing default: `view="static"` requires analyzed, relocated-byte-verified original instructions. `debug.breakpoint(address, view="execute")` explicitly binds to a decoded live instruction view, including a layer or self-modified instruction. Its receipt distinguishes runtime byte verification from static byte verification. It does not add an instruction to static analysis.

## Branch theories and virtual code caves

`debug.branch(name, address, mode="invert"|"taken"|"fallthrough", activate=True)` creates an execution layer for an observed, unprefixed 16-bit short or near Jcc. Inversion changes the condition. Forced fallthrough uses NOPs. A forced near jump adjusts the displacement and retains the original byte span. Unsupported instructions are rejected instead of being guessed.

`debug.cave(name, address=..., code_hex=..., return_to=..., activate=False)` creates fetch-only code at an explicit mapped address and appends a normalized far jump back to the runtime return address. For runtime linear target `L`, the return is:

```python
b"\xEA" + struct.pack("<HH", L & 0xF, L >> 4)
```

The immediate is offset first, segment second, both little-endian. The helper never encodes the flat address's low word as the segment-relative offset. A virtual cave reserves no guest RAM, but normal execution entering its enabled address range will also see its code. Choose that address deliberately; virtual placement does not prove the range is unused.

## Breakpoint actions

```python
cave = debug.cave("test return", address="1000:0100",
                  code_hex="b8efbe", return_to="1000:0009")
hook = debug.hook("1000:0002", actions=[
    {"op": "layers", "layers": [cave["layer"]]},
    {"op": "redirect", "address": "1000:0100"},
])
result = debug.run(timeout_ms=3000, fast_forward=True)
```

The hook owns native byte-free breakpoints. On a hit, the Python owner records the stop, applies the declarative actions while paused, and continues within the original run budget. No arbitrary Python or shell runs from an action. Available actions replace the layer stack, redirect CS:IP to a project address, or apply checked register edits using the same expected/value format as native state editing. A redirect uses normalized runtime CS:IP and verifies the resulting linear address.

Execution hooks use the live execution view. Data hooks can use `access="r"|"w"|"rw"` and `length`; they inherit the backend's post-instruction access-watch semantics. `once=True` is the default. With `once=False`, specify `max_hits` (1..1000); a hook is removed when its hit bound is reached. There are at most 16 actions per hook. `debug.hooks()` lists active controls; `debug.delete_hook(ID)` removes their owned breakpoints. A failed multi-action hook is recorded and closes the emulator; it is never silently resumed after a partial change.

`run()` reports each dispatch in `hook_hits`. Hook dispatch is paused RPC work, not an in-core JIT callback. A guest-time target and host timeout remain separate, and the host run budget includes dispatch time. Already dispatched RPCs retain their own RPC deadline.

## Guest software checking its own code

The integrity-check use case means the **guest program reading its own instruction bytes to detect patches**. An `execute` layer leaves those data reads on underlying RAM even while instruction fetches use alternate bytes. This was verified with a real guest CRC loop over its own code; it is not a host checksum of fDisBull or its packages.

A `ram` layer is visible to that self-check while enabled. For a known integrity routine, install an execution hook **before its first code read** to remove the experimental layer, and a second at the successful check's exit to restore it. For example, with addresses discovered from your own trace:

```python
before = debug.layers()["active"]
during_check = [identifier for identifier in before if identifier != experiment_id]
debug.hook(check_entry, actions=[{"op": "layers", "layers": during_check}])
debug.hook(check_exit, actions=[{"op": "layers", "layers": before}])
debug.run(timeout_ms=5000, fast_forward=True)
```

This restores original patched bytes during the check and re-enables the experiment afterward, while preserving the saved stack order. Include any other overlapping layers that must be suspended in `during_check`. A read watchpoint is useful for finding the check, but access watches stop after the instruction: they cannot undo the value already read. Hooks do not automatically identify integrity routines. The authored acceptance program actually branches to failure with the RAM layer active, then passes with the two hooks and executes the re-enabled patched instruction.

For repeated checks, arm both hooks with `once=False` and an explicit `max_hits`; the default is one dispatch. Inspect `hook_hits`, `hooks()` and the event timeline for exhausted controls. Disabling a RAM layer still honors changed-byte conflict guards. These mechanisms do not guarantee arbitrary self-checking software is undetectably patched or that modified timing/state will be accepted.

## Self-modification, snapshots, and temporal evidence

Execution layers retain guards on underlying RAM. Before decoding, the normal core checks overlay guards in the next 15-byte instruction window. A changed guard stops with `outcome="layer_conflict"` before executing that window. Because this covers the maximum architectural instruction length, a nearby guarded byte can cause a conservative stop slightly before the modified instruction. Device/DMA and protected-mode execution are outside this profile.

Inspect both views, then use `debug.capture_code(address, length=..., view="ram"|"execute")` to save a `code-snapshot` artifact. These runtime disassemblies retain bytes, hashes, view, generation, and active IDs. Static instructions and versions remain untouched. Disable the stale execution layer, capture the changed RAM, and create a new guarded definition if you want to rebase the theory.

Disabling a RAM patch refuses to overwrite bytes that differ from its last applied values. After inspecting them, `debug.layers([], conflict="keep_changed")` explicitly clears the stack while retaining those differing bytes and restoring unchanged patched bytes. The event records the preserved differences. This comparison does not establish the cause of a change or detect a same-value write; use a data watch when that distinction matters.

Native checkpoints retain the active layer IDs and RAM-layer restoration information in project metadata. Loading in a compatible fresh session restores the two byte views as well as machine state. The backend executable's identity must match exactly; 0.10.0 checkpoints are not automatically portable to the new layers binary. Existing breakpoint/hook controls remain session-owned, and restoring a checkpoint does not reset their hit counts or recreate deleted hooks. Re-arm them explicitly for another trial.

Traces from the layers backend carry per-event `ram_bytes`, `execution_bytes`, and a native layer generation. fDisBull decodes the effective bytes for the primary `instruction` field and preserves the backend RAM disassembly as `native_instruction`. Raw backend consumers must honor `native_instruction_view="ram"` and the explicit effective byte stream. A bounded trace may stop on a hook, conflict, breakpoint, or timeout; completeness remains explicit.

`project.debug_events(run, after=0, limit=1000)` reads persisted transitions, hook events, captures and run outcomes after restart. This is an event/snapshot history, not automatic instruction-by-instruction rewind.

A code snapshot decodes observed bytes into its own runtime artifact. It does not automatically create a new static version/context, enqueue traversal of the observed targets, or regenerate static xrefs for that interpretation. Previous static facts and runtime snapshots are retained separately. The automatic loop from observed self-modification to a connected static interpretation is not implemented by this layer API.

## JSON and scripts

Offline methods are `debug-layer`, `debug-layer-info`, `debug-layers`, and `debug-events`. Live methods are `debug-layer-stack`, `debug-layer-enable`, `debug-layer-patch`, `debug-code`, `debug-capture-code`, `debug-branch`, `debug-cave`, `debug-hook`, `debug-hooks`, and `debug-delete-hook`. All are listed by `methods` and accepted by the existing JSON request/foreground server interfaces.

Bounded routes additionally support `layer-stack`, `layer-enable`, `layer-patch`, `code`, `capture-code`, `branch`, `cave`, `hook`, `hooks`, and `delete-hook`. Their fields match the Python methods, and named results/assertions work as before. Layer definitions and artifacts may contain original or experimental program bytes: keep byte-retaining project databases and native states local.
