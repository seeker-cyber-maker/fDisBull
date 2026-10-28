# Published fDisBull 0.20.0 and shared installation

[fDisBull 0.20.0](https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.20.0) is published, not draft or prerelease.
The annotated tag remains fixed at `4f7791baa2cca7bb3c62fc9a997dc8f86316c98d`. This documentation records the
later publication and installation; it does not change the tagged packages.

## Tag CI and release assets

[Ordinary tag CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40770388692)
passed 1,236 checks, with 98 skips. [Native tag CI](https://github.com/seeker-cyber-maker/fDisBull/actions/runs/40770388455)
passed 109 stable DOSBox, 415 layers, 16 installed-wheel PE64 and 13 DOS/QEMU/boot
checks. All native suites had zero failures, errors or skips. All 114 ordinary
wheel entries match the separately native-tested wheel. The 109 package
implementation/resource files match the fixed tag.

All seven published assets were downloaded again and matched their sizes,
GitHub SHA-256 digests and audited local bytes. The standard packages passed
tool-only archive checks (114 wheel, 326 tool ZIP, 334 source-distribution entries).

| Asset | SHA-256 |
| --- | --- |
| [fdisbull-0.20.0-linux-x86_64-offline.tar.gz](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.20.0/fdisbull-0.20.0-linux-x86_64-offline.tar.gz) | `7de3024f731363dc926447b0fe777592528b984f4638e6ddc6ee3f9c5b350f38` |
| [fdisbull-0.20.0-linux-x86_64-source-companion.tar](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.20.0/fdisbull-0.20.0-linux-x86_64-source-companion.tar) | `b655a9edc2364fc6572051845b59172bf5d90b110ad9aa464f51f6ebb07010d8` |
| [fdisbull-0.20.0-py3-none-any.whl](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.20.0/fdisbull-0.20.0-py3-none-any.whl) | `4dc75da040dd33dbdf95d4c409315f28ece8571191577c5f1c13bb890cdf3f7c` |
| [fdisbull-0.20.0-tool.zip](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.20.0/fdisbull-0.20.0-tool.zip) | `7f35f37f8da3b32d300a54641a6aca910eafac76e78ed5f8df09c683ce8579a1` |
| [fdisbull-0.20.0.tar.gz](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.20.0/fdisbull-0.20.0.tar.gz) | `40d00af1287502dd5088e941e909b1e454d83de7f57cc367438fc9175bc4c8de` |
| [SHA256SUMS](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.20.0/SHA256SUMS) | `46b1fffde25111579fb3f9ef284df09ed30302ae67c0a90fa8cc568f7c39bad2` |
| [VERIFICATION-0.20.0.json](https://github.com/seeker-cyber-maker/fDisBull/releases/download/v0.20.0/VERIFICATION-0.20.0.json) | `48bfc80ae904cc6171ed01c0e405a3dfd68fdc92b656adaa4a6afe0604e32ead` |

## Z3 offline installation

The Linux x86-64 kit includes genuine `z3-solver==5.3.2.0` and the exact tagged
package/backend. Its corresponding source companion is paired by hash and
includes the pinned upstream archive, 29 verified overlay files and notices.
All 17 internal payload checksums and the paired source readback passed.

The fresh Python 3.13.5 installation used no package index and passed solver
counterexample/equivalence checks, guest keyboard consumption, memory readback,
screenshot storage, native restore, post-restore input and project restart.
This qualifies the Ubuntu 24.04 CI environment, not an unspecified external
host. The documented compatible Linux system libraries remain prerequisites.

## Activated shared Mac installation

`/Users/Shared/fDisBull/current` selects `releases/0.20.0-4f7791b`. The global
CLI, managed Python and runtime launchers resolve through the selector. The
managed environment includes genuine Z3 and all decoding dependencies. All
109 installed package resources match the tag wheel and tagged source.

The current Mac layers DOSBox and exact tag-CI Linux DOSBox are installed with
their patches and provenance. The copied Mac QEMU/firmware pair matches the
previous sealed inputs. The Wine boot input was retained after resource and
exclusion audits; the DOS boot input was rebuilt with the new Linux backend
and current broker. Both are pristine runtime inputs, not captured sessions.

Local installed-wheel qualification passed 415 layers checks, seven boot/GDB
checks and nine proof checks. Direct DOS, DOS-in-QEMU and Wine/QEMU runtime
doctors all passed with native-state restoration. After activation, the global
entry points and a further direct-DOS runtime doctor passed. The complete
1796-entry payload verification passed. Large Linux offline/source archives
remain public release assets; the Mac prefix retains the three standard
packages and two small manifests, plus the seven-asset readback receipt.

The previous `releases/0.19.0-57824bd` prefix remains intact for rollback and
checkpoints bound to that backend. The guarded rollback helper is under
`current/share/rollback-to-0.19.py`. Existing running sessions and private
projects were not migrated. See [system commands](SYSTEM_INSTALLATION.md).

## Evidence and scope

The [evidence manifest](../experimental/remote-debugger/evidence/2026-10-28-published-0.20/MANIFEST.json)
binds the tag audits, public download readback, installed qualification and
runtime-image audits. Game files, saved states and project databases are
excluded from Git, release assets and the installed payload. Authenticated pip
and Z3 platform resources are dependency files, not game executables.

Current installation qualification uses authored fixtures. The earlier bounded
Police Quest game run retains the source and observation limits in the
[reconciliation record](RECONCILIATION-0.20.md). Z3 checks supplied bounded models;
they do not establish recovered-program correspondence or whole-game fidelity.
The AGI inspector remains partial and static. Interactive Mac dot-mode is
unqualified. No new DeepSeek delivery was produced.
