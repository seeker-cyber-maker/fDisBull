# QEMU REP terminal-step incremental patch

This package contains one source patch for `target/i386/tcg/translate.c`. It adds a zero-count exit after the iteration when REP translation cannot emit an internal loop. The patch is prepared against the v2 source tree identified below.

## Apply

From the root of the already-patched v2 QEMU source tree, first verify that `target/i386/tcg/translate.c` has the manifest's `preimage_sha256`, then run:

```sh
patch --forward -p1 < /path/to/0001-i386-tcg-rep-terminal-step.patch
```

The resulting file should have the manifest's `postimage_sha256`. To undo this incremental patch, use `patch --reverse -p1` with the same patch from the source root.

The preimage is the previously validated QEMU source with the v2 trace and fault-retry patches. The exact preimage hash, rather than a local directory name, identifies the applicable source. The postimage hash identifies the resulting file.

## Local patch check

The patch applied to a temporary copy of the exact preimage and produced the exact postimage hash. Reverse application restored the preimage hash. A separate macOS arm64 x86_64-softmmu build and bounded native comparisons passed on the candidate SHA in the manifest. See the linked evidence for the exact test selection and remaining parity limits.

No private game files, VM images, binaries, or media are included.
