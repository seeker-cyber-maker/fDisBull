# fDisBull 0.25.0 publication and shared activation

[Version 0.25.0 is published](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.25.0) at annotated tag `v0.25.0`, source `70eb4e38bf4bf8d47e52e38b8fab6a6cd718f15e` and tag object `143c0ece41c432cb8f4f98f62dcb3166fe92376a`. Both main workflows passed before tagging. Both complete tag workflows passed before publication. All eight public assets were downloaded without authentication and matched staged bytes, GitHub digests and the seven-entry checksum file. Tagged documents preserve their source-cut context; this record describes subsequent publication and activation.

[Ordinary tag CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/41039693542) passed **1,919 tests, 103 skipped**. [Required-native tag CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/41039693576) passed **779 stable-DOS, 1090 layers-DOS, 16 PE64 and 13 DOS/boot tests**, with zero native failures, errors or skips. The genuine-Z3 offline acceptance and both installed-skill gates passed. All 161 uncompressed core wheel entries match between ordinary, PE-tested and kit builds; all 14 player entries match between ordinary and kit builds. Separately built ZIP hashes can differ.

## Public assets

Readback completed `2026-10-30T10:55:46.899104+00:00`.

| Asset | Bytes | SHA-256 | Download |
| --- | ---: | --- | --- |
| `SHA256SUMS` | 702 | `9893f0b4a08efd2d56c0cd3253330e10011f94a6b88d56cb327dece17b561817` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.25.0/SHA256SUMS) |
| `VERIFICATION-0.25.0.json` | 8,213 | `3a055953ac7cce03e344875c7f65c504dea05b1dfa9bcd78d14604775e452cdb` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.25.0/VERIFICATION-0.25.0.json) |
| `fdisbull-0.25.0-linux-x86_64-offline.tar.gz` | 102,460,974 | `efc51b07ef0299d207c7e910840750ca2f97dfaaea86286e407387c5eff15aad` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.25.0/fdisbull-0.25.0-linux-x86_64-offline.tar.gz) |
| `fdisbull-0.25.0-linux-x86_64-source-companion.tar` | 106,885,120 | `af8db1df6f6109fa769233a979803bcb2b201f4827a8f6b80e04b46d8133d582` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.25.0/fdisbull-0.25.0-linux-x86_64-source-companion.tar) |
| `fdisbull-0.25.0-py3-none-any.whl` | 657,911 | `08d6369b24ec6b89aa991f46813d161f5b5529e8768cc8d64ef707bebcb11a50` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.25.0/fdisbull-0.25.0-py3-none-any.whl) |
| `fdisbull-0.25.0-tool.zip` | 1,836,295 | `3867fcb023cf30315cc0b6eb0480c58c516daadcd3874bd472f74fc7e77e3bf6` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.25.0/fdisbull-0.25.0-tool.zip) |
| `fdisbull-0.25.0.tar.gz` | 1,537,904 | `215cf1beec56185e420f9e3376d65c87a30d453949e26f290ddf282797fa9fbb` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.25.0/fdisbull-0.25.0.tar.gz) |
| `fdisbull_player-0.25.0-py3-none-any.whl` | 49,649 | `81b9da936e2064f1f485fc1a992d28da7b754ecdecf773f3083062750b7d75fc` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.25.0/fdisbull_player-0.25.0-py3-none-any.whl) |

The Linux x86-64 kit targets Python 3.13.5 and includes genuine dependencies, Z3 5.3.2, the separate player, the tested DOSBox backend and SDL2_net. Its README specifies host library requirements. The matching source companion contains pinned upstream source/test/build inputs, including ROM snapshots and COM/EXE fixtures. It is not binary-free. Its checksums and all 29 overlay files were verified. User game/story inputs, saved states and project databases are excluded from the release payload.

## Shared installation

`/Users/Shared/fDisBull/current` selects `/Users/Shared/fDisBull/releases/0.25.0-70eb4e3`. Core and player resolve to 0.25.0 in the fresh Python 3.13.17 ARM64 environment, with genuine decoders, managed-analysis dependencies and Z3 5.3.2. All **3,040 managed entries** passed the sealed payload check. The installed gate passed **1,107 tests**, zero failures/errors/skips, with two explicit source/Linux-only deselections. This is a selected installed-package gate, not the full Mac source suite. All 156 core and 9 player package resources match public wheels.

Direct DOSBox, DOS-in-QEMU and Wine/QEMU doctors passed on authored disposable programs, including native save/restore, execution overlays, breakpoints/watchpoints, memory, screenshots, clicks, traces and stored-evidence reopening. Fresh runtime images passed streamed path/resource/hash audits. The Mac binaries retain their earlier build provenance; they were freshly tested with 0.25 and were not rebuilt. The Linux ELF and notices match the public kit; inherited 0.24 kit receipts and companions are explicitly historical.

Postflight checked three core aliases, six player save/resume processes through three aliases, the runtime selector and a further global DOS doctor. The global Zork producer emitted the same qualified package, and first/repeated mailbox results and complete checkpoints matched across fresh processes. These are two text boundaries compared with the earlier qualified path, not a fresh native DOS/Frotz or whole-game replay. Original story bytes remained unchanged. Retaining packages and checkpoints stayed private.

The previous 0.24 prefix and all 14 wrappers remain intact. Guarded rollback preflight returned `rollback_ready`; it was not applied. Existing projects and user checkpoint directories were not migrated. The [installation guide](SYSTEM_INSTALLATION.md) gives verification and rollback commands.

## Retained setup failure and limits

The first installed attempt reported 1,104 passes and three failures. Its isolated fixture snapshot lacked the skill Markdown expected by two round-trip tests and two player modules copied by the fresh-consumer test. Exact-tag resources and hash-verified installed consumer links corrected the harness; the three focused checks and complete 1,107-test rerun passed. Source and tag were unchanged, and the initial attempt remains recorded.

The draft upload initially succeeded but lookup by tag returned 404. Reading the existing draft by release ID and explicitly supplying its intended tag/source restored the draft metadata; the guards stopped publication until all fields and assets were rechecked. The annotated tag was unchanged, and the final public readback passed.

The original-game findings and their bounds remain in [the source verification record](VERIFICATION-0.25.md). Static LE support does not provide protected-mode native debugging; Zork intent recovery remains edition-specific and partial. This publication does not close the [remaining PR requirements](PR_BACKLOG.md). Earlier long-path DOSBox startup aborts remain unresolved. Interactive dot-mode and the full Mac source suite were not qualified here. The [sanitized manifest](https://github.com/seeker-cyber-maker/fDisBull/blob/main/experimental/remote-debugger/evidence/2026-10-30-published-0.25/MANIFEST.json) binds the CI, public assets and installed receipts without including game files, states or databases.
