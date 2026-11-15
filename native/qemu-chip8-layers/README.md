# CHIP-8 RAM and execute layers

This incremental QEMU 10.0.13 patch adds guarded, target-local memory and
instruction-fetch layers to the sealed `native/qemu-chip8-classic/` target.
The earlier v1 through v3 source packages and binaries remain separate.

The new CPU subset is `fdisbull-chip8-layers-hooks-4`, the environment model is
`fdisbull-chip8-display-keypad-timers-rng-layers-3`, and the layer model is
`fdisbull-chip8-native-layers-1`. CHIP-8 RAM remains a fixed flat 4 KiB.

`query-chip8-layers` returns the complete execute mask, overlay bytes and their
RAM preimage, layer generation, backing validity, mismatch address, and layer
fault/stop attribution. `x-chip8-configure-layers` is stopped-only and uses
both layer and CPU state generations as compare-and-swap guards. It accepts
bounded guarded RAM writes and a complete replacement execute map; execute
expected bytes are checked against RAM after those writes. A successful
configuration replaces the map, advances each generation once, clears a
latched layer fault and pending stop attribution, and flushes translated
blocks. Malformed, overlapping, stale, out-of-range, or oversized patches
refuse before mutation.

Instruction fetch consults the execute overlay. Data reads and writes continue
to use physical guest RAM. Before each instruction can change CHIP-8 state, the
CPU checks every active overlay backing byte. A changed backing byte latches a
layer fault and stops at the unchanged PC before that instruction takes
effect. Reconfiguration is required to clear the fault. QEMU saves the mask,
overlay, preimage, generation and fault fields in CHIP-8 VMState version 4;
the pending stop attribution is intentionally ephemeral and is cleared on
restore. Cross-binary VMState compatibility is not claimed.

Host-side execution hooks remain paused RPC/GDB operations. This native
increment does not add a native hook table, data overlay, or general-purpose
QEMU layer manager.

## Build evidence

The patch replays against the sealed v3 source hashes. QAPI generation passed.
An isolated `chip8-softmmu` TCG target configured and built locally for
macOS arm64. The candidate binary is
`/Volumes/CACHE/fdisbull-ci-builds/chip8-layers-runtime-20261112/build-layers/qemu-system-chip8`
with SHA-256
`31f7d6d45a719d83ebd0e974f52490fcd55577ced7784dd4c146bca6827a49f3`.

The final guarded candidate passed 13 native layer cases with zero skips,
including malformed delimiter-injection refusals, and 49 retained
classic/device/CPU cases with zero skips. One obsolete v1-only `00e0` refusal
case was deselected because CLS is supported. The integrated preservation run
remains pending. An earlier candidate was
replaced before a copy could be retained; its SHA and first selection receipts
are recorded as historical evidence only in the private build-correction
receipt. The final candidate is preserved at the path and hash in
`source-manifest.json`. No CI or other-host build is claimed.
