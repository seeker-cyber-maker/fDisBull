# fDisBull 0.11.0

This release adds reversible runtime code experiments and a shorter screenshot-to-click workflow. A theory can be saved as a guarded layer, enabled during a run, compared with original RAM and static bytes, then removed or restored from a compatible checkpoint. Native and ordinary Linux CI are separate release gates.

## Code layers and breakpoint actions

- Save immutable, project-version-bound `ram` and `execute` layers. RAM layers change guest-visible bytes and restore guarded originals when disabled. Execution layers supply alternate instruction-fetch bytes while guest data reads keep seeing underlying RAM.
- Compose, toggle and reorder explicit layer stacks. Preflight both byte views atomically while the emulator is paused. A stale execution guard stops before the affected decode window; changed RAM bytes are not silently overwritten during removal.
- Capture and decode observed code views as temporal artifacts without rewriting static instructions, earlier versions or xrefs. Traces retain RAM bytes, execution bytes, layer generation and active definitions.
- Invert or force supported short/near 16-bit conditional branches. Create fetch-only virtual caves with correctly normalized far returns: offset `linear & 0xF`, segment `linear >> 4`.
- Attach bounded breakpoint actions to switch layers, redirect CS:IP or apply checked register edits. Native checkpoints retain the active layer stack and RAM restoration information.
- Suspend a RAM experiment before a known guest integrity routine reads its own code, then restore it after the check. The authored guest acceptance actually detects an enabled RAM patch, passes with entry/exit toggles, and executes the restored experiment. Execution-only overlays separately preserve self-code data reads. These are scoped observations, not a general undetectability guarantee.

## Native-coordinate screenshots and clicking

- Add optional grids to real screenshots while preserving the clean source image. Grids can be regenerated from stored project state after emulator exit and database restart.
- Support steps from 8 to 512 pixels. An eight-pixel art grid has faint minor lines and readable labels every 32 pixels. Coordinates remain native screenshot pixels, regardless of display-doubling flags.
- Use `click-frame` to capture a clean frame, label the chosen point and queue the click using that frame's mode ID in one client action. A script can run afterward and capture the resulting screen in the same request. Mode mismatches and out-of-frame targets are rejected before queuing input.
- Preserve the source-only DinoPark route that reaches the Load Game dialog through one script request. Original game files, saved states and local project databases remain local inputs.

## Acceptance and compatibility

`--require-native` rejects missing or unusable backend paths before collection. The native CI matrix builds both the established backend and the new layers backend from pinned DOSBox-X source plus complete, hash-checked patches, then runs the existing integration tests. Ordinary Python/package CI remains a separate check where native tests may skip.

The Python packages contain no emulator or game. Existing unlayered debugging and grids work with the published 0.10 backend; execution layers require the separate layers backend. Native states still require an exact compatible backend/profile and matching mounted files. The original 0.10 patch, Mac executable identity and delivery stay unchanged.

The normal-core, real-mode profile remains the supported overlay/watchpoint scope. There is host lookup and paused-RPC overhead; zero extra guest installation bytes does not mean zero timing changes. Automatic static reanalysis/xref rebuilding from self-modification, automatic rewind, protected-mode/dynamic-core overlays and device/DMA watch coverage are outside this release. Headless execution is not security isolation, and checkpoint restore does not roll back mounted host files.

See [code layers](CODE_LAYERS.md), [debugger and coordinate API](DOSBOX_DEBUGGER.md), [scripts and checkpoints](DEBUGGER_SCRIPTS.md), and [verification/release gates](VERIFICATION-0.11.md).
