# fDisBull 0.23.0 publication and shared activation

[Version 0.23.0 is published](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.23.0) at annotated tag `v0.23.0`, source commit `ed89abca061964385b176537bc9fd275dd02afa5` and tag object `7b153779f9d8e3fea23d807bd9c7307d02e558ec`. All eight public assets were downloaded and matched to their staged bytes, checksums and GitHub digests. Tagged package documents remain source-finalization snapshots; this record describes later publication and activation.

[Tag ordinary Linux CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40937203880) passed 1,493 tests with 103 skips. [Tag native CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40937203834) passed 353 stable-DOS, 664 layers-DOS, 16 installed-wheel PE64 and 13 DOS/boot tests, with no native failures, errors or skips. All 134 entries in the PE-tested and ordinary wheels match; their ZIP hashes differ because they were built separately. Core/player wheels inside the offline kit also match the ordinary wheels entry-for-entry.

## Public asset readback

Readback completed 2026-10-29T20:07:21.479095+00:00.

| Asset | Bytes | SHA-256 | Download |
| --- | ---: | --- | --- |
| `SHA256SUMS` | 702 | `d7b760821fe15b2652dc522dd118f4392e5f375b95e1b7f4dffa795689a01aaa` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.23.0/SHA256SUMS) |
| `VERIFICATION-0.23.0.json` | 10,862 | `246c7995ddc42e800533a1d2f21a7653590bfc6baa200841246f9af0d4af8e54` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.23.0/VERIFICATION-0.23.0.json) |
| `fdisbull-0.23.0-linux-x86_64-offline.tar.gz` | 102,274,975 | `a1f6f370617e1a92af894d72fd3343a3556012f87d2a7ffc3d994a1b998ce310` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.23.0/fdisbull-0.23.0-linux-x86_64-offline.tar.gz) |
| `fdisbull-0.23.0-linux-x86_64-source-companion.tar` | 106,885,120 | `4126942fbd114463aa5ab1c98cf2bee41008cad89f740bc5aedd836758880b4a` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.23.0/fdisbull-0.23.0-linux-x86_64-source-companion.tar) |
| `fdisbull-0.23.0-py3-none-any.whl` | 505,577 | `69d365b9d4a22ed2a58e06b29ae8e56323477f03724c8ec2a8db0fd31a56e83c` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.23.0/fdisbull-0.23.0-py3-none-any.whl) |
| `fdisbull-0.23.0-tool.zip` | 1,364,015 | `5f6297a5398a65f1e1fea47521497d2923a40c3a0944c4814be3befa83be28fd` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.23.0/fdisbull-0.23.0-tool.zip) |
| `fdisbull-0.23.0.tar.gz` | 1,134,867 | `7d07befbf71f93b1333859800bcb0b13cb48fa467bb93e6ddcddbe0e4af2a3d2` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.23.0/fdisbull-0.23.0.tar.gz) |
| `fdisbull_player-0.23.0-py3-none-any.whl` | 13,203 | `ce3e79b36a766d3dadfb98b658d496c31378fd370f4f74863147bd52a2f56f79` | [Download](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.23.0/fdisbull_player-0.23.0-py3-none-any.whl) |

The Linux x86-64 / Python 3.13.5 kit includes genuine dependencies and Z3 5.3.2. Its tested backend, source commit, 29-file overlay and source companion are hash-linked. The companion preserves pinned upstream DOSBox-X source/test/build inputs, including its ROM/COM/EXE categories; these are distinguished from user game assets. Tool packages and delivery assets exclude user games, native checkpoints and project databases.

## Shared Mac activation

`/Users/Shared/fDisBull/current` selects `/Users/Shared/fDisBull/releases/0.23.0-ed89abc`. The installed package passed 709 required-native qualification tests with zero skips or failures. All three backend doctors passed native-state restoration, both runtime-image audits passed, and the player passed fresh-process save/resume. Post-activation verified all three core aliases, all three player aliases across six processes, the global DOS restore doctor, and the complete 2,464-entry payload. `INSTALLATION.json` records `active_verified`.

The previous 0.22.0 prefix and all 14 global wrappers are preserved. The guarded `share/rollback-to-0.22.py` preflight reports `rollback_ready`; it requires `--apply` to change the selector, and no rollback was performed. Existing projects and user checkpoint directories are not migrated. The Mac backends/pristine runtime images were reused only after hash/source-resource compatibility checks and fresh doctors with the new package.

## Limits and retained failures

The first installed qualification attempt reported 697 passes and 12 failures. Ten failures correctly rejected UDC output because the harness put temporary directories inside Git. Two DOSBox startups separately aborted with macOS SIGABRT / stack-buffer-overflow reports in `DEBUG_ShowMsg`/`main`. Moving basetemp to a shorter private directory outside Git yielded a complete 709-pass rerun, but does not establish the cause of those aborts. That native startup issue remains unresolved; this record qualifies the tested Mac and paths, not all path lengths or macOS hosts. Interactive dot-mode remains unqualified.

A post-publication probe of installed 0.23.0 reproduced a 53,583-byte valid IL input producing 13,152,686 bytes from `il-run`, exit 0 and `complete: true`. General core response budgeting and artifact references remain follow-up work. Redirect potentially large IL replies to a private file and inspect selected fields. This is not a diagnosis of the earlier ChatGPT conversation retrieval failures. The GitHub release notes include this addendum; assets and tag were not changed.

The historical full Mac source suite remains non-green because of Linux ELF fixtures on Apple's toolchain. The [UDC verification](VERIFICATION-0.23.md) separates original-byte preservation, modeled block equivalence and bounded native observations; no whole-game recovery or general C/C++ decompilation is claimed. The local discovery-index follow-up is outside 0.23.0.

The sanitized [publication evidence manifest](https://github.com/seeker-cyber-maker/fDisBull/blob/main/experimental/remote-debugger/evidence/2026-10-29-published-0.23/MANIFEST.json) indexes CI, asset-readback and installation receipts.
