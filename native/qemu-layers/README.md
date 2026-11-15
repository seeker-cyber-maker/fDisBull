# Experimental QEMU physical RAM layers

Apply the pinned prerequisites from `source-manifest.json` in order to QEMU 10.0.13. The manifest records the archive, patch and modified file hashes. Apply the layer patch from the parent directory of `qemu-10.0.13/` with `patch -p1`.

The patch adds two experimental QMP commands:

- `x-fdisbull-layer-configure`: compare-and-swap generation, guard physical RAM and execute bytes, commit real RAM writes, and replace the complete instruction-fetch overlay map. Replies include `generation`, `ram-bytes`, and `execution-bytes`.
- `x-fdisbull-layer-observe`: report generation and active execution byte count. Supplying both `address` and `length` returns effective fetch bytes as `data-hex`; supplying only one is rejected.

Both commands require a stopped, single-vCPU, system-mode TCG VM. Patches are bounded to 64 KiB, use lowercase hex, and require direct writable RAM. Execute overlays are keyed by QEMU's resolved RAM backing identity, so guest physical remaps that resolve to another backing select another layer identity. Ordinary data reads are unchanged.

Configure preflights all guard bytes before changing RAM or publishing a new layer. It marks execute backing pages for code-write tracking, flushes their TLB mappings, and flushes translated blocks. A guest write to an active execute backing invalidates the complete overlay and requests a debug stop. The translator also compares guarded underlying bytes before applying an overlay and clears the layer on mismatch.

The extension covers direct RAM and instruction fetch through TCG translation.
Guest page-table edits and QEMM, EMS and XMS services remain guest responsibilities.
Active layer state stays outside the supported checkpoint profiles.

The local native witnesses use authored boot sectors and an authored COM
program under FreeDOS. They exercise warmed translations, live backing
remaps, an atomic guard refusal, and a guest write that stops the machine
before the changed target instruction executes.
