# Native FreeDOS save provenance witness

This incremental QEMU patch adds an opt-in native observer for one bounded
FreeDOS save operation. The host arms it only after verifying the original
program-entry checkpoint and the helper's child-PSP setup. The observer records
the successful exclusive create, sequential write bytes, close and DOS flush
events for one absolute `D:\\` 8.3 destination. Its QMP receipt exposes the
captured payload and bounded event ledger so the host can compare them with the
sealed FAT workspace before publishing a new immutable file generation.

The witness follows the pinned process lifetime. It invalidates evidence on process-changing
DOS calls, checks the IVT INT 21h vector, and requires observed AH=51h/AH=62h
results to match the pinned child PSP. The packaged FreeDOS source identifies
`_cu_psp` at offset `+0x10` from `_internal_data`; no runtime link address was
available to justify an unconditional direct read of that kernel global. This
patch therefore does not claim an independent kernel-global PSP read when the
guest makes no AH=51h/AH=62h query.

## QMP interface

- `x-fdisbull-query-dos-save-witness` reads the current observer and VMState
  proof. It works on a stopped x86 TCG CPU in any CPU mode, including protected
  mode and V86, so existing checkpoint inspection remains available.
- `x-fdisbull-arm-dos-save-witness` requires one stopped real-mode x86 TCG CPU,
  a validated original process-entry boundary, a fresh owner token, child PSP,
  source ranges, expected INT 21h IVT vector, and one absolute D: 8.3 path.
- `x-fdisbull-disarm-dos-save-witness` requires the matching token and current
  generation. A ready or tainted witness remains owned until explicitly
  disarmed.

The receipt includes `active`, `valid`, `phase`, `epoch`, `generation`, the
target path, source ranges, event and write counts, actual payload bytes in
hexadecimal, pending INT 21h call metadata, hardware-return frames, and any
taint reason. The observer state and in-flight call/frame data are serialized
in the instrumented QEMU VMState. Load validates that state and advances the
native epoch/generation; the host must bind the restored receipt before using
the witness.

## Bounds and limits

- One x86 TCG CPU; arming supports real mode only. Query and disarm remain
  available in other stopped modes for checkpoint and cleanup compatibility.
- One host-pinned process lifetime, at most 32 source ranges below `0xA0000`
  (64 KiB total), and one absolute D: 8.3 target. The captured write payload
  is at most 64 KiB, the event ledger at most 256 events, and tracked hardware
  interrupt nesting at most 16 frames.
- Only exclusive AH=5Bh creation, sequential AH=40h writes, optional AH=68h,
  AH=3Eh close, and AH=0Dh flush can produce a ready witness. Unsupported DOS
  mutation, process changes, source escapes, mismatched INT 21h vector, and
  unowned raw storage/DMA/PCI paths taint the witness.
- Hardware interrupt return frames are tracked across checkpoint/restore.
  Writes through storage/DMA/PCI port paths outside the admitted DOS operation
  invalidate the witness without changing guest execution. Every observed DOS
  interrupt also invalidates the witness if protected mode, PAE, LMA, or guest
  mode is active.
- This does not prove arbitrary DOS filesystem behavior, host filesystem
  visibility, typematic/input parity, DOSBox parity, generic QEMU migration, or
  cross-binary VMState compatibility. A ready witness means the bounded native
  event sequence and bytes were observed; the host still validates the target
  FAT image and provenance policy before publication.

## Apply and build

The patch applies to the sealed N21 `frame-keys-runtime` QEMU 10.0.13 source.
First prepare that exact prerequisite source tree, then dry-run and apply this
patch:

```sh
patch --dry-run -p1 -d <N21-qemu-10.0.13> < qemu-10.0.13-fdisbull-dos-provenance-v1.patch
patch -p1 -d <N21-qemu-10.0.13> < qemu-10.0.13-fdisbull-dos-provenance-v1.patch
```

Configure a fresh `build-n22` directory from the patched source with the
configure command recorded in `source-manifest.json`, then build:

```sh
TMPDIR=<guest-provenance-runtime/tmp-n22> \
  /Users/tiga/miniconda/bin/ninja -C build-n22 -j4 qemu-system-x86_64
```

The manifest records every changed-file before/after hash, the N21 prerequisite
patch identity, the source patch hash, and the exact local build profile. Build
09 compiled and linked the packaged source; its binary SHA-256 is recorded in
the manifest. Root-owned native witnesses passed 13 cases with no skips,
including PIT IRQ/BDA advancement and a failed exclusive-create carry/error
guard (`R/provenance-native-09.log`). This is bounded local evidence, not hosted
CI. The patch author did not run guests or CI.
