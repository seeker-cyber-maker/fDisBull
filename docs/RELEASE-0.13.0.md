# fDisBull 0.13.0

PE64 Wine/QEMU debugging now supports scalar read/write watchpoints, reversible code layers and editable native machine states. The original executable and every static byte version remain unchanged; runtime observations retain their own project timeline and artifacts.

## PE64 changes

- `breakpoint(address, access="r"|"w"|"rw", length=N)` stops before a qualified memory access. Native guard faults and iced operand facts identify overlapping ranges, including a byte inside a wider store. Read-only watches ignore pure stores. Unsupported or ambiguous accesses fail explicitly instead of silently losing a watch.
- Immutable `ram` and `execute` layers support ordered stacks, toggles, runtime code captures and short/near conditional-branch theories. RAM patches are visible to the software's self-CRC. Execution layers preserve source RAM while the CPU executes alternate instructions in a private 4 KiB buffer, with host stepping and relocation overhead.
- `save_state`, `load_state` and launch-time `state=ARTIFACT` use native whole-QEMU migration, capturing the CPU, RAM, devices, Linux, Wine and guest RAM-backed files. Host debugger state restores watches and active layers. These are resumable emulator states, not Wine minidumps.
- `debug_fork_state` restores a parent in a fresh VM, checks all expected memory/register values, edits mapped main-image memory and 64-bit registers while the target EXE is paused, and captures an immutable child. It reuses the parent's explicit asset allowlist and verifies host input hashes. Linux/broker services continue running around the edits.
- Checked register editing is available as `write_registers`, `debug-write-registers`, and the script operation `write-registers`. RIP preflight validates actual runtime addresses through the observed relocation delta.

The existing PE disassembly breakpoints, screenshots, 8px coordinate grids, click-frame, bounded traces, scripts and offline project exports remain available. Native images live in a required hash-bound `PROJECT.fdisbull-states/` sidecar; state export streams a ZIP with `state.json` and `machine.mig.gz`.

## Runtime compatibility and limits

Prepare a new Wine runtime with the 0.13 package. Its packaged Win32 agent and broker changed; a 0.12 prepared image is rejected by source-fingerprint checks. The trusted base image may be reused without modification. QEMU >=9.1 remains required. Native states bind the exact emulator, kernel, prepared runtime, uploaded files, static version and layer definitions. Existing DOS backends and their native state format remain separate.

The qualified PE scope is an original native x86-64 EXE, mapped main-image addresses and the authored GDI fixture. Watchpoints use observable guard protections and support resolved non-repeated scalar operands. PE execution layers use guest scratch memory and host work; calls/returns, multi-instruction relocations, DOS virtual caves and breakpoint action hooks are unsupported. This is not a zero-footprint, unchanged-timing or arbitrary-game compatibility guarantee. The real state test edits memory and RAX; rebased RIP preflight has a static mapping regression check rather than a live rebased redirect qualification.

Native checkpoints are limited to 2 GiB compressed/8 GiB expanded each and 6 GiB per project, with at least 2 GiB free before capture. The authored fixture used roughly 950 MB per state. Preserve the database and private state sidecar together. Neither state restore nor the offline guest rolls back host files.

## Verification and packaging

[Verification gates](VERIFICATION-0.13.md) distinguish the immutable local development receipts from required CI on the exact release commit. Local proof includes a software self-CRC comparison, a relocated instruction reading original source RAM under a data watch, parent/child state restore after project and VM restart, real screenshots/clicks, and traces retaining RAM and execution bytes. The ordinary and native Linux workflows must pass before creating the release tag.

The wheel contains all Win32 agent/broker/launcher sources and host backend modules. Tool packages exclude games, compiled fixtures, native state images/exports, local project databases and runtime images. The separately prepared emulator/runtime is not bundled in the Python packages. Existing 0.12.0 packages and DeepSeek delivery are not replaced by source/tag preparation.

The README prominently states that fDisBull is not currently suitable for malware analysis or security work and retains the requested “Safety Not Guaranteed” newspaper-ad reference. The GitHub About description is filled in.
