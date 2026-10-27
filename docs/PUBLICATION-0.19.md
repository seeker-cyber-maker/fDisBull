# Published fDisBull 0.19.0 and shared installation

[GitHub release](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.19.0)
is published, not a draft or prerelease. Tag `v0.19.0` remains fixed at
`57824bd9a06c7f25f6a25172b3f4dcb4dfcfdc95`. Publication documentation on main
does not alter that source or its package bytes.

## Tag CI and published assets

The final commit passed ordinary and native Linux CI before tagging. Tag
[ordinary CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40517808271)
passed **1,112 tests, 91 skipped**. Tag
[native CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40517808062)
passed **66 stable DOSBox, 372 layers (Python 3.13.5), 16 PE64 and 13 DOS/QEMU/boot
checks**. Native suites had zero failures, errors or skips. The complete tag
workflow and all three native jobs finished successfully.

All 105 wheel entry contents match the separately native-tested installed-wheel
build; all 100 package code/resource files match the tag. The wheel, tool ZIP
and source distribution passed tool-only audits (105, 288 and 296 entries).
Five published assets were downloaded again and matched their local bytes,
sizes and GitHub SHA-256 digests.

| Asset | SHA-256 |
| --- | --- |
| [fdisbull-0.19.0-py3-none-any.whl](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.19.0/fdisbull-0.19.0-py3-none-any.whl) | `c169d90f46c706469fe06b198006f45182d43df246650276d71c016e9eae3b1e` |
| [fdisbull-0.19.0-tool.zip](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.19.0/fdisbull-0.19.0-tool.zip) | `00357d2a0ee109306d75310ebb2e9c1053962eb4aeefab3ce906ed6b6101ee5a` |
| [fdisbull-0.19.0.tar.gz](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.19.0/fdisbull-0.19.0.tar.gz) | `db18531eee23224dbdae3222423635a3c6bf6495f4146858cd68bc47efaf8201` |
| [SHA256SUMS](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.19.0/SHA256SUMS) | `65c8feacf1aee4789dc3bc4c983553f3a3d2a7edaeda9b1e638a1c4b1a401a20` |
| [VERIFICATION-0.19.0.json](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.19.0/VERIFICATION-0.19.0.json) | `0aa90be203d43c36b57fadb5ac956ff5d073dd44e83d4f222edf368016e51142` |

## Activated shared installation

`/Users/Shared/fDisBull/current` selects `releases/0.19.0-57824bd`. The global
CLI, managed Python, runtime-profile helper and DOSBox/QEMU launchers select
this prefix through the existing command wrappers. `/usr/local/bin`, Homebrew
and the prior user-local launcher all report 0.19.0. Existing project and Conda
environments were preserved; no private project database was opened or migrated.

The installed package and genuine dependencies were installed offline from
hash-locked wheels into a new environment. The corrected native Mac DOSBox
and exact tag-CI Linux DOSBox are included, with complete patches and provenance.
Copied QEMU and its firmware remain paired. The pristine Wine boot input was
retained, and the DOS boot filesystem was regenerated with the corrected Linux
backend. Every required runtime resource and both image hashes were audited;
no captured emulator states, games or project databases were admitted.

The Linux private loader/library closure is retained from the earlier verified
installation. No new standalone Linux private-loader acceptance is claimed.
The new Linux binary is tested by tag Linux CI and by the DOS-in-QEMU runtime
check. Mac executables use this machine's existing Homebrew libraries; this is
qualification on this Mac, not an arbitrary-host portability claim.

The installed Mac pair passed **372 DOSBox checks, zero failures/errors/skips**.
All three profiles (direct DOS, DOS-in-QEMU and Wine/QEMU) passed runtime doctor
checks with native-state restoration. Seven boot/GDB checks passed. Following
activation, the global entry points and a further direct-DOS runtime doctor
passed, including native restoration. The active prefix's complete **1,738-entry
payload verification** passed. Published package copies inside the installation
match the release downloads.

The original 0.18.0 prefix remains intact at
`/Users/Shared/fDisBull/releases/0.18.0-416b64d`; its 1,805-entry payload was
verified before activation. The new prefix contains a guarded rollback helper.
Retain the earlier executable for checkpoints bound to its identity. Existing
running processes and private game files were not migrated or terminated.
See [system commands and rollback](SYSTEM_INSTALLATION.md).

## Evidence and limits

The [evidence manifest](../experimental/remote-debugger/evidence/2026-10-27-published-0.19/MANIFEST.json)
binds CI audits, published-asset readback, installed identities, native XML,
runtime-image audits and activation checks. Verification states and project
DBs are private and remain outside Git and the installed payload. PIP's bundled
platform-launcher resources are authenticated against its genuine hash-locked
wheel; they are toolchain files, not game executables.

The new 0.19.0 checks use authored native fixtures, not a fresh original-game
DinoPark campaign. Earlier game evidence retains its original source/version
scope. C/C++ decompilation, source-view debugging, semantic movement/navigation
and runtime-resource resolution remain proposals. No new DeepSeek delivery or
offline archive was produced.
