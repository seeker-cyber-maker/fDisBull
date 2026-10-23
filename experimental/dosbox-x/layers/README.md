# Temporal code layers backend — 0.11.0

This optional backend adds guarded instruction-fetch overlays for the fDisBull 0.11.0 code-layer API. The published 0.10.0 backend patch, binary identity, releases and local deliveries remain unchanged in the parent directory and delivery storage. The source manifest and earlier receipts retain the identity of the initial development build; the patch and Mac executable hashes are unchanged for this release.

`headless-agent.patch` is a **complete patch** against DOSBox-X baseline `029bd65c5dcc7cdc7f2e14e35278620d9707d969`. Apply it to a pristine checkout of that commit. Do not apply the parent 0.10.0 patch first. The source manifest records every resulting changed file and the tested local binary hash; selected pristine baseline files were replayed independently and all resulting hashes compared.

```bash
git checkout 029bd65c5dcc7cdc7f2e14e35278620d9707d969
git apply /absolute/path/to/layers/headless-agent.patch
./autogen.sh
./configure --enable-sdl2 --enable-debug=heavy --enable-dosbox_agent \
  --disable-avcodec --disable-libslirp --disable-libfluidsynth
make -j6
```

Build prerequisites and upstream GPL notices are described in the [parent backend documentation](../README.md) and [COPYING](../COPYING). The current local build is macOS ARM64 and uses the existing host libraries. New native checkpoints require this exact compatible backend identity; older 0.10.0 machine states cannot be assumed portable.

The new capability is `code_layers: normal_core_real_mode_guarded_fetch_v1`. `layers.configure` atomically preflights and applies conventional-RAM edits plus a sparse guarded execution view while stopped. `memory.read` supports explicit `view: ram|execute`, an overlay validity flag, and a generation counter. Instruction byte, word and dword fetches plus prefix inspection use the sparse execution map. Guest data access continues to use physical RAM.

Before decoding, the normal core checks execution guards in the next 15-byte window. Stale bytes pause the target with `layer_conflict`. The scope is 16-bit real-mode code on the normal core; operand-size-prefixed instructions are supported. Non-heavy builds report no layer capability. Execution overlay maps are process/session controls, cleared when starting a target or restoring native machine state; fDisBull restores the corresponding layer metadata after a compatible checkpoint load.

Trace events retain both RAM and execution byte windows plus their layer generation. The backend disassembly string retains the RAM view and explicitly labels it. fDisBull's primary trace instruction is decoded from the execution bytes, while preserving the native RAM disassembly separately.

The Python foreground owner implements bounded breakpoint actions through paused RPC dispatch. They are not an in-core action scheduler. There are no extra guest RAM bytes for execution overlays, but host lookup/guard/IPC costs and changes to guest timing remain possible. See [code-layer semantics and API](../../../docs/CODE_LAYERS.md).

The development executable is a local build artifact under `.recovery/2026-10-23/dosbox-layers/src/dosbox-x`; it is excluded from Git and Python distribution packages.
