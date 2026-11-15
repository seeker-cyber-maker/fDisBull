# Native FreeDOS save-operation witness

This incremental QEMU patch extends the existing source-bound FreeDOS save
witness with an opt-in operation ledger for one root-level D: 8.3 file and an
optional temporary path. It records DOS create/open, write, seek, commit,
close, delete, rename and flush calls at the native INT 21h entry/return seam.
The host independently replays the bounded ledger against the supplied
preimage and the observed FAT workspace bytes before it publishes a file
generation.

The existing v1 QMP command and v1 proof protocol remain available. The new
`x-fdisbull-arm-dos-save-operations` command selects API 2 and reports model
`qemu-pc-dos-save-witness-v2`; `query` and `disarm` are shared. Version 2
reports the original file preimage, selected current path, final/temp
existence, current file size and cursor, captured write stream, and ordered
operation events. Writes are bounded to a cumulative 64 KiB capture and a
64 KiB logical file size. Successful zero-byte AH=40h truncation, bounded
AH=42h seek, and temp-to-final replacement are represented in the event
stream. Unrelated getter events have empty path and zero file cursor/size
extensions.

## Scope and limits

- One stopped x86 TCG CPU; arming requires real mode. Query and disarm remain
  available in other stopped modes for checkpoint and cleanup compatibility.
- At most 32 sorted, disjoint source-code ranges ending below `0xA0000`; the
  combined code-range size is not the file-payload limit. At most 256 events,
  64 KiB of captured write bytes, and 16 tracked hardware interrupt frames.
- One canonical absolute D: 8.3 final path and, optionally, one distinct
  canonical D: 8.3 temporary path. Writes must be sequential or overwrite
  existing bytes; holes and unsupported file operations taint the witness.
- AH=3Dh accepts write or read/write mode on the currently tracked file.
  AH=3Ch/5Bh create the final or temporary file; AH=41h may delete only an
  eligible tracked path; AH=56h may rename the closed current image between
  those paths. Final readiness requires a closed final file, no temporary
  file, a successful DOS disk flush, and no pending DOS call or hardware
  interrupt frame.
- Unsupported DOS mutations, process changes, source escapes, a changed INT
  21h vector, and unowned raw storage/DMA/PCI writes invalidate evidence
  without changing guest execution. A ready or tainted witness remains owned
  until explicitly disarmed.
- The N23 native VMState schema is version 2 with minimum version 2. It
  preserves v2 operation state and pending call data; older native streams are
  rejected. Same-binary restore is the only qualified restore boundary.
- This does not establish generic DOS filesystem coverage, host filesystem
  visibility, DOSBox parity, cross-binary restore, hosted CI, or behavior for
  unsupported operations. The host still validates workspace identity,
  preimage, protection rules and final file bytes before publication.

## Apply and build

The patch is an incremental delta over the sealed N22 `guest-provenance-runtime`
QEMU 10.0.13 source, which itself requires the N21 frame-keys patch and its
prerequisite chain. Verify and apply it to that exact N22 source:

```sh
patch --dry-run -p1 -d <N22-qemu-10.0.13> < qemu-10.0.13-fdisbull-dos-save-operations-v2.patch
patch -p1 -d <N22-qemu-10.0.13> < qemu-10.0.13-fdisbull-dos-save-operations-v2.patch
```

Configure a fresh `build-n23` from the patched source with the configure
profile recorded in `source-manifest.json`, then build:

```sh
TMPDIR=<guest-write-provenance-runtime/tmp-n23> \
  /Users/tiga/miniconda/bin/ninja -C build-n23 -j4 qemu-system-x86_64
```

The manifest records the N22 prerequisite patch identity, exact touched-file
hashes, patch hash and binary hash. An isolated touched-file apply-and-hash
replay against N22 reproduced both N23 output files exactly. Build 04 compiled
and linked the candidate binary. The root-owned native v2 suite passed 13
cases with no skips, including a stored v2 predecessor rearm across FDB reopen
and explicit keep; the retained v1 witness suite passed 13 cases with no skips.
These are bounded local results, not hosted CI. The patch author did not
control guest execution.
