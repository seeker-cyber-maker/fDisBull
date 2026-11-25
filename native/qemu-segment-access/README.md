# QEMU x86 segment-access candidate delta

This package is an incremental source patch from the private QEMU 10.0.13
preimage named in `manifest.json` to the isolated segment-limit candidate. It
contains changes to exactly five files. The source trees remain separate; apply
the patch to a disposable or intentionally selected QEMU 10.0.13 source copy.

## Apply

From the root of a matching QEMU 10.0.13 source tree whose five files match the
manifest preimage hashes:

```sh
patch -p1 < /path/to/qemu-segment-access/segment-access.patch
```

Check every `pre_sha256` entry before applying and every `post_sha256` entry
afterward. Do not apply to an unrelated QEMU tree or a tree that already
contains this delta.

## Reverse

From the patched source root:

```sh
patch -R -p1 < /path/to/qemu-segment-access/segment-access.patch
```

Check that the five files match their `pre_sha256` values afterward.

## Reproduce the package

The patch is the unified diff of these exact source roots, limited to the five
paths listed in `manifest.json`:

- Preimage: `fDisBull-private/qemu-rep-terminal-20261124/source`
- Postimage: `fDisBull-private/qemu-segment-limit-20261124-source`

For each listed path, generate a zero-context unified diff with labels
`a/<path>` and `b/<path>`, concatenate the five diffs in manifest order, and
hash the resulting `segment-access.patch`. The expected patch digest is recorded
in the manifest.
The manifest also records exact SHA-256 values for both source versions.

## Scope and evidence limits

The candidate adds protected/compatibility-mode segment-limit checks for the
implemented scalar integer loads/stores, legacy ModRM scalar accesses, locked
scalar accesses, and per-element string memory accesses covered by the source
changes. It includes address-size truncation, segment overrides, expand-down
checks, null-selector faults, and the stated SS/GP fault selection. This is a
bounded source candidate; it does not establish coverage for every x86 data
access family, architectural parity, or runtime correctness.

The packaging pass did not build or run a VM. The coordinating native pass
independently hashed the candidate binary and ran the selected local tests on
that exact executable; see
`docs/evidence/qemu-segment-access-2026-11-25/verification.json`. Overall parity
and any release or installation remain separate gates.
