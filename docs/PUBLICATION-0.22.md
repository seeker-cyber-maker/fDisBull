# fDisBull 0.22.0 publication and system activation

[Version 0.22.0 is published](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.22.0) at annotated tag `v0.22.0`, source commit `75bbd7ee65118c0186844f73ef6c79245854eba0` and tag object `20a51f133098595cfc62cc81c388e85ba2a3bb3b`. All eight release assets were downloaded and matched to GitHub digests and staged bytes. This record follows the source-finalization snapshots in the tagged release notes and verification documents; it does not alter tagged packages.

The [tag ordinary workflow](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40895109575) passed 1,458 tests with 101 skips. The [tag-native workflow](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40895109415) passed 316 stable-backend, 627 layers-backend, 16 PE64 and 13 DOS/boot tests; those native suites had no failures, errors or skips. The PE-tested wheel and tag package have different archive hashes but their 130 entries match byte-for-byte. One bounded PE layer execution trace was incomplete; it is not promoted to a complete trace.

## Public asset download readback

Readback completed 2026-10-29T15:36:32.565533+00:00. Sizes and SHA-256 values are from the downloaded release assets.

| Asset | Bytes | SHA-256 | Download |
| --- | ---: | --- | --- |
| `SHA256SUMS` | 702 | `a9ee39f4bf898b72c4f1da14b3da0edc96d6177d2148686b1cb1d74578f285dc` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.22.0/SHA256SUMS) |
| `VERIFICATION-0.22.0.json` | 13,033 | `9883a993377bdfb78293f4291ef90f52da4359af1a0137264e4b007009a8867a` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.22.0/VERIFICATION-0.22.0.json) |
| `fdisbull-0.22.0-linux-x86_64-offline.tar.gz` | 102,260,039 | `3f1e0f93f510406e9b09d655feed293e3379827de7a47d00bcf5575469a94032` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.22.0/fdisbull-0.22.0-linux-x86_64-offline.tar.gz) |
| `fdisbull-0.22.0-linux-x86_64-source-companion.tar` | 106,885,120 | `f5f9bea3a5c766d66de941a923ff09bb657ced4a2474d00891c003b58e3c40e3` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.22.0/fdisbull-0.22.0-linux-x86_64-source-companion.tar) |
| `fdisbull-0.22.0-py3-none-any.whl` | 490,713 | `7f73ca157ee1313024d7ab11b299246c387002ca1dc91bdbfbf4fe1ddcfc6b36` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.22.0/fdisbull-0.22.0-py3-none-any.whl) |
| `fdisbull-0.22.0-tool.zip` | 1,275,507 | `8b662ff250143fb909c360810fa6d60556ee95758b5d1cf3f99f462827d30467` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.22.0/fdisbull-0.22.0-tool.zip) |
| `fdisbull-0.22.0.tar.gz` | 1,062,963 | `b8e3e7945174100789df6d62e41fcb08dd7e8308ed9d4982d856210df1ee2ad9` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.22.0/fdisbull-0.22.0.tar.gz) |
| `fdisbull_player-0.22.0-py3-none-any.whl` | 13,201 | `4d36f7ec3b23c828177860a3b616dcbe54e894f3fbf4d0a4688e7b129d069ca4` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.22.0/fdisbull_player-0.22.0-py3-none-any.whl) |

The Linux x86-64 offline kit and source companion are the tag-native CI outputs. The kit links its source companion and release commit by hash; its separately built core and player wheels differ in archive hash from the ordinary tag packages, while all corresponding entry names and bytes match. The companion preserves pinned upstream DOSBox-X source, including upstream test/build data. User game files, saves and project databases are excluded.

## Shared Mac activation

The selector `/Users/Shared/fDisBull/current` points to `/Users/Shared/fDisBull/releases/0.22.0-75bbd7e`. A postflight readback verified all three global core aliases and the three player aliases; the latter completed six fresh processes across save/resume checks. The global DOS doctor passed with native state restored. The sealed candidate contained 2,459 payload entries at its postflight check.

Before activation, the installed candidate passed 672 tests with zero failures, errors or skips. DOSBox, DOS-in-QEMU and Wine/QEMU doctors passed native-state restoration; the player passed a two-process resume. The installed Zork CLI passed a bounded mailbox autosave and fresh-process resume using a separately selected existing Jericho 3.3.1 worker. This does not requalify DOS parity or whole-game behavior. These observations qualify this Mac and the tested prefix, not other macOS hosts.

The complete active payload verification passed for all 2,459 entries, and installation metadata records `active_verified`. The 0.21 prefix is preserved; the guarded `share/rollback-to-0.21.py` preflight reported `rollback_ready` and 14 wrappers preserved. The helper checks by default and requires `--apply` to change the selector; no rollback was performed. Existing projects and private checkpoints are not migrated.

The Mac executables and pristine runtime images were reused from the preceding
sealed prefix after hash and source-resource eligibility checks. Both images
were audited against the installed 0.22 resources, and the three backend doctors
were run with the new package. Managed package directories are read-only;
generated bytecode was quarantined outside the prefix before sealing.

The sanitized [publication evidence manifest](../experimental/remote-debugger/evidence/2026-10-29-published-0.22/MANIFEST.json)
indexes the public CI, asset-readback and system-acceptance receipts.

## Limits

The historical full Mac source suite was not green: 1,429 passed, 104 skipped, 2 failed and 23 setup errors involving Linux ELF fixtures on the Apple toolchain. The [spatial](VERIFICATION-SPATIAL-2026-10-29.md) and [Zork](VERIFICATION-ZORK-2026-10-29.md) records describe bounded original-game evidence. No complete AGI interpreter, arbitrary position-free action or whole-game equivalence is claimed. Interactive dot-mode remains unqualified.
