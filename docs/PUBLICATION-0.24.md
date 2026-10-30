# fDisBull 0.24.0 publication and shared activation

[Version 0.24.0 is published](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.24.0) at annotated tag `v0.24.0`, source commit `031b53eb953bfdc1d0e23c0ed49441031bad6e06` and tag object `18afd1cdedba9861725dc9cd4f1ea946d24dc52f`. All eight public assets were downloaded without authentication and matched staged bytes, GitHub digests and the seven-entry checksum file. Tagged documents retain their source-finalization context; this record describes subsequent publication and system activation.

[Tag ordinary Linux CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40972253170) passed 1,590 tests with 103 skips. [Tag native Linux CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40972253084) passed 450 stable-DOS, 761 layers-DOS, 16 PE64 and 13 DOS/boot tests with zero native failures, errors or skips. The PE-tested, ordinary and kit core wheels have all 146 uncompressed entries in common; the ordinary and kit player wheels match across all 10 entries. Separately built wheel archive hashes differ.

## Public asset readback

Readback completed `2026-10-30T00:11:52.087749+00:00`.

| Asset | Bytes | SHA-256 | Download |
| --- | ---: | --- | --- |
| `SHA256SUMS` | 702 | `dea51f8381984ed53e5ba95a427989d86f61adc071cb82956c404768af39e38b` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.24.0/SHA256SUMS) |
| `VERIFICATION-0.24.0.json` | 26,587 | `4c793d5c85fac3092aa14e0559c456aba8ae01472ac07765027d257aa7b5572f` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.24.0/VERIFICATION-0.24.0.json) |
| `fdisbull-0.24.0-linux-x86_64-offline.tar.gz` | 102,337,700 | `a924fdbf4f34c22c79afa0d2481fa347a99a51be375e3d026191871bef5bd4fe` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.24.0/fdisbull-0.24.0-linux-x86_64-offline.tar.gz) |
| `fdisbull-0.24.0-linux-x86_64-source-companion.tar` | 106,885,120 | `433db874b67c8fafb5d4b213a2b9eee52b8519f951758a9da996060bd20c9998` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.24.0/fdisbull-0.24.0-linux-x86_64-source-companion.tar) |
| `fdisbull-0.24.0-py3-none-any.whl` | 567,754 | `ad7d98e0ae60015a2a05168661c2ca33f7f0c71137d076e64aed60328377cd22` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.24.0/fdisbull-0.24.0-py3-none-any.whl) |
| `fdisbull-0.24.0-tool.zip` | 1,502,474 | `2345847af0c2b3bf55e89717cc73f0c904bcaddb2fe7ff0fe1eda0cae06cdbf7` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.24.0/fdisbull-0.24.0-tool.zip) |
| `fdisbull-0.24.0.tar.gz` | 1,251,820 | `b6646366af5ecebeef25475b134fa7a6845c31f20c63ac96fe40990c7f5d454b` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.24.0/fdisbull-0.24.0.tar.gz) |
| `fdisbull_player-0.24.0-py3-none-any.whl` | 14,496 | `364f80cb26f2c1a119e5e733b757549a1e40612e38654151253effca5205c718` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.24.0/fdisbull_player-0.24.0-py3-none-any.whl) |

The Linux x86-64 kit targets Python 3.13.5 and includes genuine dependencies, Z3 and the tested DOSBox binary with SDL2_net. It requires compatible host glibc, SDL2, GL/X11, FreeType, PNG, ncurses and zlib as stated in its README. The corresponding source companion retains the pinned upstream source/test/build inputs, including ROM snapshots, IBM ROM BASIC and COM/EXE fixtures; it is not a binary-free archive. The 29-file final overlay, patch manifests and companion checksums were verified. User game files, native states and project databases are excluded from the tool packages and delivery.

## Shared Mac activation

`/Users/Shared/fDisBull/current` selects `/Users/Shared/fDisBull/releases/0.24.0-031b53e`. The fresh Python 3.13.17 ARM64 environment contains the published core and player plus genuine decoding, managed-analysis and Z3 dependencies. The selected installed-package gate passed **700 tests**, zero failures/errors/skips, with one source-only `-S` doctor CLI test deliberately deselected. Five source build/distribution suites and the full Mac source suite are outside that installed selection. The installed skill gate and blank backend-command smoke passed. All 141 core and five player package files match the public wheels.

DOSBox, DOS-in-QEMU and Wine/QEMU doctors passed native save/restore, overlays, breakpoints/watchpoints, memory, screenshots, clicks, traces and stored-evidence reopening on authored targets. Native boot/watchpoint tests also passed in the selected suite. Both fresh runtime images passed streamed path and resource-hash audits; the two known static OS support `.state` files are hash-identified, not emulator checkpoints. The images were rebuilt after removing 242 stale build/cache/profile entries (17,100,034 expanded bytes). Mac executable provenance is retained unchanged and the binaries were freshly tested with the new package; no Mac rebuild is claimed.

Postflight verified all three global core aliases, six fresh player save/resume processes through three aliases, the runtime profile and the global DOS doctor. All **2,968 managed entries** passed the payload check and `INSTALLATION.json` records `active_verified`. The previous 0.23 prefix and all 14 wrappers are preserved. The guarded `share/rollback-to-0.23.py` preflight returned `rollback_ready`; no rollback was applied. The system update did not migrate existing projects or user checkpoint directories.

## Limits and retained setup failures

The first installed attempt recorded 690 passes, one failure, six skips and one deselection: the ZIP regression source path was omitted, five native QEMU checks lacked their executable setting, and the authored UDC example helper was absent from the isolated snapshot. Supplying the pinned source fixture, enabling the existing QEMU and copying the exact-tag authored examples corrected the harness; the complete 700-test rerun passed. This does not change the tagged source or its Linux CI evidence.

The full Mac source suite remains outside this qualification because of known Linux ELF fixture/toolchain differences. Earlier long-path DOSBox startup aborts remain unresolved, and interactive dot-mode is unqualified here. Runtime audits are bounded path/hash checks; native doctor results cover their authored targets. The documented DinoPark development run remains separate evidence, not a fresh original-game replay in this publication turn. Core output limits concern fDisBull replies; they do not establish the cause of earlier ChatGPT conversation retrieval failures.

The [sanitized evidence manifest](https://github.com/seeker-cyber-maker/fDisBull/blob/main/experimental/remote-debugger/evidence/2026-10-29-published-0.24/MANIFEST.json) indexes CI, public readback, installation, runtime audits and doctor receipts. The live [system installation guide](SYSTEM_INSTALLATION.md) gives verification and rollback commands.
