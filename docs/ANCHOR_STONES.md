# Anchor Stones and delta rewind

An **Anchor Stone** is a full native saved state. Loading it jumps directly to
that saved machine context: CPU registers, memory and the device state covered
by the selected backend. It does not walk through intermediate recorded steps.
The name is a reference to the Anchor Stones in TiGa's **Blob to General** game.

**Delta rewind** follows recorded changes between earlier and later states.
The current experimental implementation records exposed real-mode registers and
selected RAM at debugger next-fetch boundaries. Those are recorded debugger
steps, not synchronized video frames. Its partial-state and recovery limits
remain unchanged.

| Method | User-facing meaning | Current API |
| --- | --- | --- |
| Anchor Stone | Save a full native point, or jump directly back to it | `debug-save-anchor-stone`, `debug-load-anchor-stone`, `debug-anchor-stone-info` |
| Delta rewind | Walk backward through recorded CPU/RAM changes | `debug-delta-start`, `debug-delta-record`, `debug-delta-rewind`, `debug-delta-status` |

Python callers use `debug.save_anchor_stone()`,
`debug.load_anchor_stone(artifact)` and `project.debug_anchor_stone_info(artifact)`.
Routes use `save-anchor-stone` and `load-anchor-stone`:

```json
{"format":"fdisbull-script-1","steps":[
  {"op":"save-anchor-stone","as":"stone"},
  {"op":"trace","count":2},
  {"op":"load-anchor-stone","artifact":"$stone.artifact"}
]}
```

`debug-anchor-stone-info PROJECT ARTIFACT` also works offline. Existing
`debug-save-state`, `debug-load-state`, `debug-state-info`, Python `save_state`
and `load_state`, and the `save-state`/`load-state` route operations remain
compatible. Persisted artifact kind `state`, native formats, hashes and receipt
keys such as `anchor` are retained. Existing authored artifact names are not
rewritten. The new save alias defaults to `anchor-stone.sav`.

The legacy MR !14 `debug-rewind-*` interface is an indexed history of full
Anchor Stones. It remains available, and should not be mistaken for the separate
delta recorder. See [Anchor Stone history](DEBUGGER_REWIND.md) and
[experimental delta rewind](CPU_RAM_DELTAS.md).

## Host and target support

The host running fDisBull and the target being debugged are separate choices.
On macOS/ARM64, the prepared ARM64 DOSBox backend runs DOS x86 targets; the
prepared QEMU x86-64 runtime runs Windows PE64 programs through Wine.

| Target/backend | Anchor Stones | Delta rewind |
| --- | --- | --- |
| DOS x86 in native DOSBox | Native saved machine context | Experimental real-mode exposed registers and selected RAM |
| Windows x86-64 PE through Wine/QEMU | Whole-VM migration state and debugger context | Unsupported |
| DOSBox inside QEMU | Existing native state path with runtime identity checks | Unsupported |
| IDA/Wine/QEMU | Explicitly refused; native states remain unqualified | Unsupported |
| Native macOS/ARM64 executable | No native target execution backend | Unsupported |

Mac host checks do not qualify a native Windows host. Static Mach-O/ARM64
analysis does not supply a live debugger or rewind backend. Wine/QEMU states
require their private sidecar and matching runtime inputs; they do not restore
host files. See [PE64 native checkpoints](WINE_DEBUGGER.md).

Loading is a direct restore, not a zero-time guarantee. The measured native
restore cost was around 17 ms on the small local DOSBox benchmark; this does
not measure Wine/QEMU migration latency. Backend compatibility
and mounted-file identity checks still apply; host files are not rolled back.
After partial delta rewind, loading a valid full Anchor Stone clears the partial
state guard through the existing verified native-load path. Merely renaming an
operation never bypasses that guard or enables an unsupported backend.
