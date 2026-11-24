# Experimental high-physical execute layers

Apply `qemu-10.0.13-fdisbull-high-execute-v1.patch` to the existing fully
patched QEMU 10.0.13 producer source (including `qemu-task-private`) described by the [manifest](source-manifest.json). Verify the exact preimages before applying the delta with `git apply --whitespace=error` from the source root. It adds the
`x-fdisbull-layer-observe-physical64` QMP command, with required `address`
(uint64) and `length` (uint16, 1–4096), returning the existing layer-observe
result. The command requires one stopped TCG vCPU and direct writable RAM;
MMIO, ROM, discarded RAM and overflow are rejected. On an overlay hit, the
new observer rejects stale underlying bytes without changing layer state. Its presence identifies
support for high-physical execute entries in `x-fdisbull-layer-configure`.
Real RAM writes remain restricted to 32-bit physical addresses.

Execute entries use QEMU's resolved RAM backing identity, including alias
collision checks; page dirty tracking and TLB invalidation use the resolved
backing, and all translated blocks are flushed. Readback describes the stopped
layer view, not proof that an instruction subsequently fetched those bytes.
The [paired local results](../../docs/DOS_QEMU_HANDOFF.md#high-backed-execute-capture-with-active-overlays-2026-11-24)
cover the guest-authored PSE-36 and PAE mappings and a one-instruction trial
before and after cold restore.

Patch baseline: `system/fdisbull-layers.c` SHA-256
`9148e8e8531132536a8f6c7f81f070e22b4c405bbefd6841eb8d05650fc09408` and
`qapi/fdisbull-layers.json` SHA-256
`8fca76717ee015d2c4423e914e607592ab3cc79fb7a37f7f247d44bb720a25b8`.

The existing guest-write hook triggers on QEMU code-dirty handling. A prior
write elsewhere on the same page may prevent eager notification of a later
overlaid-byte write; the new observer checks the backing at observation time.
Eager guest-write notification timing remains unqualified.
