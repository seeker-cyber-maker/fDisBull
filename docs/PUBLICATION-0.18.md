# Published fDisBull 0.18.0 and system installation

[GitHub release](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.18.0)
was published on 2026-10-27 at 06:06:56 UTC. It is not a draft or prerelease.
Tag `v0.18.0` is fixed at `416b64d9f4bfcf56e2876656d43f1d6a3d6cfdae`.
Publication documentation on main does not change that tag or package bytes.

## CI and artifact identity

Both ordinary and native workflows passed on main before tagging. Tag
[ordinary CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40453499822)
passed **1,089 tests, 72 skipped**. Tag
[native CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40453499853)
passed **54 stable DOS, 335 layered DOS (Python 3.13.5), 16 PE64 and 10 unified
DOS/boot tests**, without native failures, errors or skips. All 101 wheel entry
contents match the native-tested wheel; all 96 packaged tool resources match
the tag source. Package audits exclude game files, native states and project DBs.

All five published assets were downloaded again. Their exact bytes and sizes
match the audited inputs and GitHub SHA-256 digests.

| Asset | SHA-256 |
| --- | --- |
| [fdisbull-0.18.0-py3-none-any.whl](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.18.0/fdisbull-0.18.0-py3-none-any.whl) | `415d0b5a70418e69e8668d135139f1e09a8e94b7143f232f426c400f293f35e3` |
| [fdisbull-0.18.0-tool.zip](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.18.0/fdisbull-0.18.0-tool.zip) | `7de206c39dd0c2a9f557660ae6a5267a1500fb30fa629169c3cbdcee549ec488` |
| [fdisbull-0.18.0.tar.gz](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.18.0/fdisbull-0.18.0.tar.gz) | `e3d0e769422eccf5d0d6f2add37b57e23034e14fb4f15128508054d687582622` |
| [SHA256SUMS](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.18.0/SHA256SUMS) | `ad8884846560e45e28fae547724173ad522146ca4fb0b01420a3ecc0a70fff04` |
| [VERIFICATION-0.18.0.json](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.18.0/VERIFICATION-0.18.0.json) | `8a92f31ac621fa3550fd63b6d9cb48e70c94d8b407008c9d6be07c0d15e9ad42` |

## Activated shared installation

The user replaced the DeepSeek packaging request with a system-wide update.
The active selector is `/Users/Shared/fDisBull/current`, pointing to
`releases/0.18.0-416b64d`. Global commands in `/usr/local/bin` and Homebrew's bin
directory select the verified package/backends. The prior user-local 0.8.1
launcher is backed up and forwards to the shared install. Existing Conda/project
environments and system Python packages were not changed. Python API scripts
use `fdisbull-python`. See [usage and rollback information](SYSTEM_INSTALLATION.md).

The shared installation includes tested native Mac DOSBox, copied QEMU and
matching firmware, audited pristine DOS/Wine boot inputs, Linux DOSBox with
private SDL2_net libraries, source patches, docs, examples and the tag's bundled
skill. Pristine runtime images are OS inputs, not captured emulator states.
Mac binaries still depend on this machine's existing Homebrew libraries; this
is not an arbitrary-host portability claim. No vendor IDA executable or key is
included. No new DeepSeek folder, archive or latest pointer was created.

Fresh copied-pair checks passed 335 DOS tests on Mac Python 3.13.17, seven
boot/GDB tests and DOS/QEMU and Wine/QEMU runtime doctors. A separate no-network
Linux guest with Python 3.13.5 installed the genuine wheel/dependencies and
passed 335 checks, 51 ZIP CRC checks (18 saves, 33 loads) and all 96 installed
resource identities. This is local qualification, separate from tag CI.

The actual shared root and global entry points then passed direct DOS,
DOS/QEMU and Wine/QEMU doctors with native restoration, seven boot/GDB checks,
and a complete 1,805-entry payload verification. The system copies of the three
published packages match the downloaded release assets. No game/project DB was
opened or migrated as part of installation. Private runtime test states and
DBs stay outside Git and the installed payload.

## Evidence and limits

[Evidence manifest](../experimental/remote-debugger/evidence/2026-10-27-published-0.18/MANIFEST.json)
binds tag artifact audits, asset readback, system identities/qualification,
Linux 3.13.5 checks, native XML reports and final system verification.
The [DinoPark development evidence](VERIFICATION-SCENE-IMPROVEMENTS.md) remains
sealed as 0.18.0.dev0; these publication checks do not relabel it as fresh tag
original-game gameplay. The C/C++ source debugger and proposed game-language
extension architecture are not implemented in this release.

Known launch limitation: the DOS debugger requires an 8.3-style target name
with an extension. Static MZ import is structure-based. An authored extensionless
`AGI` MZ imports successfully but is rejected at launch; source bytes remain
unchanged. Private guest aliases for unsupported host names are follow-up work.
