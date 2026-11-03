# GOG Galaxy wrapper unpacking with CHimpREC reconstruction

Date: 2026-11-02. Implementation base:
`f861d17ed4837f753e000f53cc777a7d906fde82`.

## Result

The captured-image CHimpREC writer was exercised against two privately retained
GOG Galaxy X-COM wrapper captures. Both source files are PE32 UPX wrappers whose
packed entry lies in `UPX1`; their original application code transfers into
`UPX0` at virtual address `0x00435143`.

| Target | Source bytes | Observed transfer | Qualified IAT cells | Rebuilt imports | Output bytes |
| --- | ---: | --- | ---: | ---: | ---: |
| X-COM: UFO Defense Galaxy wrapper | 500,296 | `0x004FCA14 -> 0x00435143` | 158 | 158 | 1,150,976 |
| X-COM: Terror from the Deep Galaxy wrapper | 518,216 | `0x005003F4 -> 0x00435143` | 158 | 158 | 1,183,744 |

Each output contains the captured `UPX0`, `UPX1` and `.rsrc` sections plus a new
`.reimp` section. The rebuilt descriptors retain the original IAT addresses and
supply new OriginalFirstThunk arrays. A manual parser and LIEF independently
report 158 imports. All differences within the retained original section bytes
are confined to the 158 qualified IAT cells.

The outputs are fixed-base, unsigned **analysis reconstructions**. Their invalid
certificates, bound-import metadata and relocation/ASLR claims are cleared. The
files are not claimed to reproduce GOG's unknown pre-UPX originals byte-for-byte.

## Evidence boundary

The mapped images and import-request records came from an earlier private run
that executed each original UPX stub in a traced 32-bit compatibility process.
The final transfers were observed, and loader calls were intercepted with
synthetic function-address tokens. Those tokens are not genuine Windows DLL
exports. This implementation pass reused the retained captures; it did not
perform a new Windows/Wine attachment, Galaxy download or wrapper execution.

The source wrappers, mapped images, rebuilt binaries and private validation logs
remain outside Git. The committed receipt contains hashes, counts and claim
limits only.

## Historical CHimpREC compatibility incorporated

The implementation also turns the retained legacy tool decisions into explicit
APIs and tests:

- runtime code ranges can override stale section execute flags without marking an
  entire dump as code;
- OEP provenance distinguishes jump, call, resumed-thread and thread-start
  transfers;
- aliases, forwarded exports and ordinal imports remain explicit;
- ambiguous exports require selection;
- invalid candidate thunks require `cut` or `separator` decisions;
- noncandidate expansion junk is retained as evidence but omitted from imports;
- PE32 and PE32+ use new lookup tables while preserving original IAT cells;
- process/thread/region topology is retained by a source-free capture receipt.

This does not implement a universal anti-debugging bypass, 32-bit Wine attachment
backend, protector-specific API emulation or automatic classification of decoy
thunks. Those are capture and investigation responsibilities, not permissions for
the writer to guess.

## Verification

- 11 retained CHimpREC recovery tests pass unchanged.
- 8 new authored reconstruction/capture/Galaxy tests pass, for 19 focused tests.
- PE32 and PE32+ fixtures cover named and ordinal imports, OEP changes,
  OriginalFirstThunk rebuilding, checksum, certificate removal and fixed-base
  metadata.
- A synthetic UPX0/UPX1 Galaxy fixture exercises the file API and module CLI.
- Both private Galaxy captures rebuild to the exact output sizes from the earlier
  study, with 158 imports and zero section-byte differences outside qualified IAT
  cells.

Machine-readable details are in
[`docs/evidence/gog-galaxy-chimprec-2026-11-02/receipt.json`](evidence/gog-galaxy-chimprec-2026-11-02/receipt.json).
