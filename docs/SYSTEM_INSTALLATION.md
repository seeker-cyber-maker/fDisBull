# fDisBull 0.21.0 — versioned shared Mac installation

This prefix contains source commit `a253600b94f7006f8962ada842eba699279fdbfe`,
release tag `v0.21.0`. The global commands resolve through
`/Users/Shared/fDisBull/current`; `INSTALLATION.json` records activation status
and readback, while `RUNTIME.json` identifies this prefix's native profiles.

The independent `fdisbull-player` supports automatic model-turn saves and resume,
and a bounded external agent can choose commands and narrate observed results.
Progressive scene workflows and qualified movement keep content and player
separate. Unknown content remains partial. There is no complete AGI/UIL engine,
arbitrary room teleportation or deterministic replay. Voice is future work:
Qwen TTS is available locally according to the user; speech recognition and the
combined interaction still need qualification. See share/docs/PLAYER_LIVE.md.

The installed candidate passed 546 checks with no skips and an independent
fresh-process player resume test. Direct DOSBox, DOS-in-QEMU and Wine/QEMU
runtime doctors passed native-state restoration. Boot/GDB checks and genuine
Z3 model checks are part of the installed selection. Both pristine boot inputs
were streamed and audited against this version's installed package resources.
These results qualify this Mac; its native executables use existing host
libraries and are not portable Mac binaries. Interactive dot-mode window
behavior remains unqualified by this installation.

The published core/player wheels, source distribution, source ZIP and small
verification/checksum manifests are retained in share/packages. The Linux kit
and corresponding-source companion remain public release assets and in the
artifact cache, without duplicating their large archives in this Mac prefix.
share/verification/ASSET-READBACK.json records all eight downloaded assets.

The existing 0.20 prefix is retained. After activation,
share/rollback-to-0.20.py checks the current selector, payload and owned command
identities before restoring it. Existing projects, running sessions and user
checkpoint directories are not migrated. Keep game files, saved states and
project databases outside this prefix. Authored examples under share/examples
contain no supplied game resources. Live saves default to private user data,
scoped by the authored package hash; an explicit --save-dir can override this.

Verify the complete sealed payload using the managed interpreter with -B and
share/verify-system.py. Source-package documentation is fixed at tag build time;
this installation receipt records later publication and local qualification.

This tool is not currently suitable for malware analysis or security work.
Must bring your own weapons. I have only done this once before. Safety not guaranteed.

Release: https://github.com/seeker-cyber-maker/fDisBull/releases/tag/v0.21.0

Installed Python package directories are read-only. Global Python and player
launchers disable bytecode writes explicitly, including isolated Python runs.
User saves and project data remain writable outside the managed prefix; updates
use a new versioned prefix. The guarded rollback helper is
`/Users/Shared/fDisBull/current/share/rollback-to-0.20.py`; its preflight was
checked without switching the current release back.
