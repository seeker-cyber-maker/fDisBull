# Distinct Library tool source snapshot

This source ZIP contains 704 text files and no embedded wheel, executable,
image, savestate or database payload. All paths exist in the exact v0.29.0 tag
`09a820952ad3f54d0d0707db0515a8010f7eceb1`. Of those files, 698 match the tag
byte-for-byte. Its six differing files are:

- `AGENTS.md`
- `docs/RELEASE-0.29.0.md`
- `docs/RELEASE_STATUS.md`
- `docs/SYSTEM_INSTALLATION.md`
- `docs/evidence/0.29.0-release/README.md`
- `scripts/offline_dependencies.py`

The first five contain earlier guidance or release/installation status snapshots.
The script differs only by an additional unused `import os`. The application
package files match the tag; no changed application source was found. This is
a source comparison, not a new execution, install or runtime equivalence claim.

All 704 files also occur in the canonical, hash-verified source distribution.
Only three differ from that distribution: `docs/OFFLINE_KIT_0.20.md`,
`docs/RELEASE-0.29.0.md` and `docs/evidence/0.29.0-release/README.md`.
No wheel archives are embedded, so the ZIP has no bundled wheel identity to
substitute for the canonical core/player wheel hashes.

[manifest.json](manifest.json) records every file's size, SHA-256 and tag blob
comparison. The archive's size/SHA-256 differ from the published tool ZIP.
The original is retained as its own private artifact, with its location in the
parent inventory; the published package remains unchanged. No archived source
or release instruction was applied to the working tree.

The bounded scan found no unsafe path, symlink or credential token. Fourteen
existing docs/tests contain historical host-path examples; they remain private
inside this original archive. Three initial `sk-` regex candidates in two
unchanged DinoPark documents were word substrings, rejected by a token-boundary
check. Only hashes, paths and comparison metadata are selected into this ledger.
