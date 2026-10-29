# fDisBull 0.21.0 publication and system activation

## Published release

[Version 0.21.0 is published](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.21.0)
at tag `v0.21.0`, source commit
`a253600b94f7006f8962ada842eba699279fdbfe`. The source tag and the eight
published assets were read back and checked against GitHub's SHA-256 digests.
The exact tag packages match the ordinary build artifacts; the installed-wheel
PE64 suite also tested the same 0.21.0 tool wheel byte-for-byte by entry.

The final ordinary workflow
[passed 1,333 tests with 100 skips](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40801426999).
The final tag-native workflow
[passed all required native suites](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40801427016):
218 stable-backend tests, 529 layers-backend tests, 16 installed-wheel PE64
tests, and 13 DOS-in-QEMU/boot-context tests. Native suites reported zero
failures, errors, or skips. The layers profile built and verified the Linux
x86-64 offline kit with genuine Z3; its audit covered 19 kit files and 18
checksummed payload files.

The source-finalization text in [release notes](RELEASE-0.21.0.md),
[candidate scope](UNRELEASED-0.21.md), and [verification](VERIFICATION-0.21.md)
was created before final CI and promotion. Their pending-state statements are
historical. This publication record and the top follow-up in the release notes
record later status on the main branch. They do not change the release tag or
its published bytes.

## Public assets and download readback

All eight release assets were downloaded and matched to both the recorded
GitHub digest and local readback bytes.

| Asset | Size | SHA-256 | Download |
| --- | ---: | --- | --- |
| `fdisbull-0.21.0-linux-x86_64-offline.tar.gz` | 102,217,596 bytes | `5f031f181e72c365ec14424215d8c2bf3ab174ce5a9f7a3c1931d77beb1a975f` | [offline kit](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.21.0/fdisbull-0.21.0-linux-x86_64-offline.tar.gz) |
| `fdisbull-0.21.0-linux-x86_64-source-companion.tar` | 106,885,120 bytes | `d829f674022ae0497e6207b985e91965479f6d5b2bd65af322450a02fac58772` | [source companion](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.21.0/fdisbull-0.21.0-linux-x86_64-source-companion.tar) |
| `fdisbull-0.21.0-py3-none-any.whl` | 447,419 bytes | `e185e7275c2082c1698d66680cdf3fb0e4dfa28b4bce2732e65df8a3b32e7c81` | [tool wheel](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.21.0/fdisbull-0.21.0-py3-none-any.whl) |
| `fdisbull-0.21.0-tool.zip` | 1,170,413 bytes | `1e88a6cf383aabcd26d9ff352bd0a30326b07d84dcb0bfdfc8a18914a860aa22` | [tool ZIP](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.21.0/fdisbull-0.21.0-tool.zip) |
| `fdisbull-0.21.0.tar.gz` | 974,670 bytes | `e614fbf25d1035ebb2ee460524ef572958089801b6c2bdff420c6dfbb2a76fc7` | [source distribution](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.21.0/fdisbull-0.21.0.tar.gz) |
| `fdisbull_player-0.21.0-py3-none-any.whl` | 13,147 bytes | `c2ddae376e4ccc21672be195e4295c4ff96f57eed119a57c1e216c3d6a2bcbfb` | [player wheel](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.21.0/fdisbull_player-0.21.0-py3-none-any.whl) |
| `SHA256SUMS` | 702 bytes | `0e4752933b27589e60d1be62044c8675bb63565790b01c5fed3b574d9d605916` | [checksums](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.21.0/SHA256SUMS) |
| `VERIFICATION-0.21.0.json` | 3,651 bytes | `e5857ef8779deb4fb42e9db3d294d2fb7fe775a54ed81da62928fbc7e4f98618` | [verification receipt](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.21.0/VERIFICATION-0.21.0.json) |

The checked-in source tree and release packages exclude game files, user save
states, and private project databases.

## Shared Mac activation

The installed selector `/Users/Shared/fDisBull/current` now points to
`/Users/Shared/fDisBull/releases/0.21.0-a253600`. The sealed installation
contains 2,430 payload entries, including core and standalone-player 0.21.0
packages in the managed Python environment. The global core and player command paths resolve through the managed 0.21.0
Python environment with guards verified. The three global player entry-point
paths were read back. A fresh-process player check passed automatic save/resume
across two processes, with checkpoints kept outside the installation and
private permissions verified.

Before activation, installed-wheel qualification passed 546 tests with zero
skips in 85.51 seconds. The DOS, DOS/QEMU and Wine/QEMU runtime doctors also
passed with native state restored. After activation, the global DOS doctor and
global player save/resume checks passed. These results qualify the tested Mac
and its installed prefix; they do not establish portability to other macOS
machines. Existing projects and captures were preserved. The previous
`/Users/Shared/fDisBull/releases/0.20.0-4f7791b` installation remains available
and can be restored with the guarded `current/share/rollback-to-0.20.py` helper. Rollback preflight was checked; an actual rollback was not performed.

Managed Python package directories are read-only, and global Python/player
launchers explicitly disable bytecode writes. Generated cache files discovered
during post-activation checks were quarantined outside the prefix; no installed
source/resource bytes changed. The complete payload verifier and global DOS
doctor passed again after this reconciliation. Existing 0.20 caches were left
untouched, and its 1,796 sealed entries were reverified. User state and project
data remain outside the managed prefix.

The supporting publication evidence is indexed by the
[0.21.0 evidence manifest](../experimental/remote-debugger/evidence/2026-10-28-published-0.21/MANIFEST.json).
The installed command and selector documentation remains in
[SYSTEM_INSTALLATION.md](SYSTEM_INSTALLATION.md).

## Limits and non-deliveries

Interactive Mac dot-mode remains unqualified. The release does not provide a
full AGI interpreter, complete UIL/world model, whole-game reconstruction, or
proof of equivalence to original game worlds. Voice input and output are future
work: local Qwen TTS availability is user-reported, while speech recognition
and a complete voice interaction remain unqualified. No DeepSeek delivery was
created for 0.21.0. The earlier 0.20 installation and its guarded rollback path
remain preserved.
