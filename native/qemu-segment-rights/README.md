# QEMU x86 segment-access-rights delta

This package is an incremental source patch from the committed QEMU 10.0.13
segment-access postimage to the current access-rights source candidate. It
contains changes to exactly five files. It is not a standalone replacement for
the preceding `qemu-segment-access` patch; apply it after that patch, to a source
tree whose five files match the `pre_sha256` values in `manifest.json`.

## Apply

From the root of the matching QEMU 10.0.13 segment-access source tree:

```sh
patch -p1 < /path/to/qemu-segment-rights/segment-rights.patch
```

Check each `pre_sha256` value before applying and each `post_sha256` value
afterward. Do not apply this delta to the original QEMU preimage or an unrelated
source tree.

## Reverse

From the patched source root:

```sh
patch -R -p1 < /path/to/qemu-segment-rights/segment-rights.patch
```

Check that all five files return to their `pre_sha256` values.

## Reproduce the package

The patch is a zero-context unified diff of the exact five paths in manifest
order, labeled `a/<path>` and `b/<path>`, from the committed
`qemu-segment-access` postimage to the current private source candidate. The
manifest records the exact input and output SHA-256 for every file and the
patch digest.

## Scope and evidence limits

This delta adds read/write access-right direction to the segment checks already
introduced by the preceding segment-access patch. The selected protected-mode
integer and ModRM scalar paths and string source/destination paths pass the
access direction to the checker. The checker rejects system descriptors,
write access to code or read-only data, and read access to execute-only code;
its selected protection-fault path distinguishes SS from general-protection
faults. The translation call sites skip these checks in virtual-8086 and 64-bit
modes.

This is a bounded source delta, not qualification of all x86 memory-access
forms or architectural parity. Packaging inspected hashes and patch
reversibility only. No VM, build, or tests were run as part of this packaging
pass.
